import os
import pytest
import psycopg
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

# Set testing environment variable BEFORE imports
os.environ["TESTING"] = "True"

from database.connection import setup_database, get_db_connection, get_db_cursor
from scraper.play_store import save_reviews_to_db
from enrichment.pipeline import enrich_reviews, find_existing_analysis_for_text, save_enrichment

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure test tables exist."""
    setup_database()
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS review_analysis CASCADE;")
            cur.execute("DROP TABLE IF EXISTS play_store_reviews CASCADE;")
            cur.execute("DROP TABLE IF EXISTS frustration_statistics_daily CASCADE;")
            cur.execute("DROP TABLE IF EXISTS theme_statistics_daily CASCADE;")
            cur.execute("DROP TABLE IF EXISTS segment_statistics_daily CASCADE;")

@pytest.fixture(autouse=True)
def clean_tables():
    """Clean tables before each test."""
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE review_analysis CASCADE;")
            cur.execute("TRUNCATE TABLE play_store_reviews CASCADE;")

def test_enrichment_tables_exist():
    """Verify that the required enrichment tables exist in the database."""
    with get_db_cursor() as cur:
        for t in ['review_analysis', 'frustration_statistics_daily', 'theme_statistics_daily', 'segment_statistics_daily']:
            cur.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{t}'
                );
            """)
            assert cur.fetchone()['exists'] is True

@patch('google.genai.Client')
def test_enrich_reviews_successful(mock_genai_client_class):
    """Test successful review enrichment using mocked Gemini Client response."""
    # 1. Insert mock raw reviews
    mock_raw = [
        {
            'review_id': 'rev_enrich_1',
            'review_text': 'I cannot find my favorite songs, the recommendations are bad.',
            'rating': 2,
            'thumbs_up': 5,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        }
    ]
    save_reviews_to_db(mock_raw, 'Spotify')

    # 2. Mock Gemini Client responses
    mock_client = MagicMock()
    mock_genai_client_class.return_value = mock_client
    
    # Structure matching the expected schema
    mock_json_response = {
        "enrichments": [
            {
                "review_index": 0,
                "sentiment": "negative",
                "themes": ["music_discovery", "recommendations"],
                "frustrations": ["repetitive_recommendations"],
                "jobs_to_be_done": ["discover_new_artists"],
                "user_segment": "music_explorer",
                "listening_behavior": "active_exploration",
                "summary": "User complains about bad recommendations and finding songs."
            }
        ]
    }
    
    mock_response_obj = MagicMock()
    mock_response_obj.text = json.dumps(mock_json_response)
    mock_client.models.generate_content.return_value = mock_response_obj

    # 3. Trigger enrichment
    enriched_count = enrich_reviews(batch_size=50, limit=10)
    assert enriched_count == 1

    # 4. Assert saved in DB
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM review_analysis WHERE review_id = 'rev_enrich_1';")
        row = cur.fetchone()
        assert row is not None
        assert row['sentiment'] == 'negative'
        assert row['user_segment'] == 'music_explorer'
        assert 'music_discovery' in row['themes']
        assert 'repetitive_recommendations' in row['frustrations']

@patch('google.genai.Client')
def test_enrichment_deduplication(mock_genai_client_class):
    """Test exact text deduplication logic (db-lookup and intra-batch duplicates)."""
    # 1. Insert raw reviews with duplicate texts
    mock_raw = [
        {
            'review_id': 'rev_original',
            'review_text': 'Identical complaint text here.',
            'rating': 1,
            'thumbs_up': 1,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        },
        {
            'review_id': 'rev_dup_in_batch',
            'review_text': 'Identical complaint text here.',
            'rating': 1,
            'thumbs_up': 0,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        },
        {
            'review_id': 'rev_dup_already_in_db',
            'review_text': 'Already analyzed text in database.',
            'rating': 2,
            'thumbs_up': 0,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        }
    ]
    save_reviews_to_db(mock_raw, 'Spotify')

    # Pre-populate db with an analysis for the text 'Already analyzed text in database.'
    # We first need a raw review with that text that was already analyzed
    already_analyzed_raw_id = 'rev_analyzed_past'
    save_reviews_to_db([{
        'review_id': already_analyzed_raw_id,
        'review_text': 'Already analyzed text in database.',
        'rating': 2,
        'thumbs_up': 0,
        'app_version': '1.0.0',
        'review_date': datetime.now()
    }], 'Spotify')
    
    past_enrichment = {
        'sentiment': 'neutral',
        'themes': ['search'],
        'frustrations': ['search_accuracy'],
        'jobs_to_be_done': ['reduce_search_effort'],
        'user_segment': 'casual_listener',
        'listening_behavior': 'passive_listening',
        'summary': 'Past test summary'
    }
    save_enrichment(already_analyzed_raw_id, past_enrichment)

    # 2. Mock GenAI Client
    mock_client = MagicMock()
    mock_genai_client_class.return_value = mock_client
    
    mock_json_response = {
        "enrichments": [
            {
                "review_index": 0,
                "sentiment": "negative",
                "themes": ["recommendations"],
                "frustrations": ["repetitive_recommendations"],
                "jobs_to_be_done": ["escape_repetition"],
                "user_segment": "heavy_listener",
                "listening_behavior": "comfort_listening",
                "summary": "Original complaint summary."
            }
        ]
    }
    
    mock_response_obj = MagicMock()
    mock_response_obj.text = json.dumps(mock_json_response)
    mock_client.models.generate_content.return_value = mock_response_obj

    # 3. Run enrichment
    # Unenriched reviews are: rev_original, rev_dup_in_batch, rev_dup_already_in_db
    enriched_count = enrich_reviews(batch_size=50, limit=10)
    
    # We should have enriched 3 reviews
    assert enriched_count == 3
    
    # Assert LLM was called exactly ONCE for 'rev_original'
    mock_client.models.generate_content.assert_called_once()
    
    # Verify DB contains correct analysis for all 3 reviews
    with get_db_cursor() as cur:
        # Check rev_dup_in_batch (got analysis copied from rev_original)
        cur.execute("SELECT sentiment, user_segment FROM review_analysis WHERE review_id = 'rev_dup_in_batch';")
        row_batch_dup = cur.fetchone()
        assert row_batch_dup['sentiment'] == 'negative'
        assert row_batch_dup['user_segment'] == 'heavy_listener'

        # Check rev_dup_already_in_db (got analysis copied from database lookup of rev_analyzed_past)
        cur.execute("SELECT sentiment, user_segment FROM review_analysis WHERE review_id = 'rev_dup_already_in_db';")
        row_db_dup = cur.fetchone()
        assert row_db_dup['sentiment'] == 'neutral'
        assert row_db_dup['user_segment'] == 'casual_listener'
