import os
import pytest
import psycopg
from datetime import datetime
from unittest.mock import patch, MagicMock

# Set testing environment variable BEFORE imports
os.environ["TESTING"] = "True"

from database.connection import setup_database, get_db_connection, get_db_cursor
from scraper.play_store import save_reviews_to_db
from enrichment.pipeline import save_enrichment
from embeddings.generator import generate_embeddings, build_embedding_chunk, save_embedding

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure test tables exist."""
    setup_database()
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS review_embeddings CASCADE;")
            cur.execute("DROP TABLE IF EXISTS review_analysis CASCADE;")
            cur.execute("DROP TABLE IF EXISTS play_store_reviews CASCADE;")

@pytest.fixture(autouse=True)
def clean_tables():
    """Clean tables before each test."""
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE review_embeddings CASCADE;")
            cur.execute("TRUNCATE TABLE review_analysis CASCADE;")
            cur.execute("TRUNCATE TABLE play_store_reviews CASCADE;")

def test_vector_extension_and_table_exist():
    """Verify pgvector extension is enabled and review_embeddings exists."""
    with get_db_cursor() as cur:
        # Check pgvector extension
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        assert cur.fetchone() is not None
        
        # Check review_embeddings table
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'review_embeddings'
            );
        """)
        assert cur.fetchone()['exists'] is True

def test_build_embedding_chunk():
    """Test text chunk builder combines review text, themes, frustrations, JTBD, and summary."""
    mock_review_data = {
        'review_text': 'I get the same recommendations every week.',
        'themes': ['music_discovery', 'recommendations'],
        'frustrations': ['repetitive_recommendations'],
        'jobs_to_be_done': ['escape_repetition'],
        'summary': 'User is frustrated with repetitive weekly recommendations.'
    }
    
    chunk = build_embedding_chunk(mock_review_data)
    
    assert "Review:\nI get the same recommendations every week." in chunk
    assert "Themes:\nmusic_discovery, recommendations" in chunk
    assert "Frustrations:\nrepetitive_recommendations" in chunk
    assert "Jobs To Be Done:\nescape_repetition" in chunk
    assert "Summary:\nUser is frustrated with repetitive weekly recommendations." in chunk

@patch('google.genai.Client')
def test_generate_and_save_embeddings(mock_genai_client_class):
    """Test generating embeddings using mocked API and inserting into pgvector."""
    # 1. Setup mock reviews and enrichment in DB
    review_id = 'rev_embed_test'
    save_reviews_to_db([{
        'review_id': review_id,
        'review_text': 'Scraper testing content',
        'rating': 4,
        'thumbs_up': 1,
        'app_version': '1.0.0',
        'review_date': datetime.now()
    }], 'Spotify')
    
    save_enrichment(review_id, {
        'sentiment': 'positive',
        'themes': ['testing'],
        'frustrations': [],
        'jobs_to_be_done': [],
        'summary': 'Test summary'
    })

    # 2. Mock Gemini embed response (3072 dimensions)
    mock_client = MagicMock()
    mock_genai_client_class.return_value = mock_client
    
    # Let's create a mockup 3072 float vector
    mock_vector = [0.1] * 3072
    
    mock_response_obj = MagicMock()
    mock_embedding_obj = MagicMock()
    mock_embedding_obj.values = mock_vector
    mock_response_obj.embeddings = [mock_embedding_obj]
    mock_client.models.embed_content.return_value = mock_response_obj

    # 3. Run embedding generator
    count = generate_embeddings(limit=10)
    assert count == 1
    
    # 4. Assert saved in DB and retrieve it
    with get_db_cursor() as cur:
        cur.execute("SELECT review_id, embedding::text FROM review_embeddings WHERE review_id = %s;", (review_id,))
        row = cur.fetchone()
        assert row is not None
        
        # Verify it can execute a vector cosine distance query
        cur.execute("""
            SELECT review_id, (embedding <=> %s::vector) as distance 
            FROM review_embeddings 
            ORDER BY distance LIMIT 1;
        """, (f"[{','.join(map(str, [0.1]*3072))}]",))
        search_res = cur.fetchone()
        assert search_res is not None
        assert search_res['review_id'] == review_id
        # distance of identical vector should be extremely close to 0
        assert float(search_res['distance']) < 1e-5
