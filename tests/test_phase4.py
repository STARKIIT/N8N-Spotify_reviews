import os
import pytest
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

# Set testing environment variable BEFORE imports
os.environ["TESTING"] = "True"

from database.connection import setup_database, get_db_connection, get_db_cursor
from scraper.play_store import save_reviews_to_db
from enrichment.pipeline import save_enrichment
from cli import main

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
            cur.execute("DROP TABLE IF EXISTS frustration_statistics_daily CASCADE;")
            cur.execute("DROP TABLE IF EXISTS theme_statistics_daily CASCADE;")
            cur.execute("DROP TABLE IF EXISTS segment_statistics_daily CASCADE;")

@pytest.fixture(autouse=True)
def clean_tables():
    """Clean tables before each test."""
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE review_embeddings CASCADE;")
            cur.execute("TRUNCATE TABLE review_analysis CASCADE;")
            cur.execute("TRUNCATE TABLE play_store_reviews CASCADE;")
            cur.execute("TRUNCATE TABLE frustration_statistics_daily CASCADE;")
            cur.execute("TRUNCATE TABLE theme_statistics_daily CASCADE;")
            cur.execute("TRUNCATE TABLE segment_statistics_daily CASCADE;")

def test_cli_help():
    """Verify that cli.py prints help and exits cleanly when no arguments are provided."""
    with patch("sys.argv", ["cli.py"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

def test_cli_setup_db():
    """Verify that cli.py setup-db executes successfully."""
    with patch("sys.argv", ["cli.py", "setup-db"]):
        main() # Should not raise any exceptions and exit cleanly

@patch('cli.scrape_play_store_reviews')
def test_cli_scrape(mock_scrape):
    """Verify that cli.py scrape parses arguments and runs correctly."""
    mock_scrape.return_value = [
        {
            'review_id': 'cli_test_1',
            'review_text': 'test content',
            'rating': 5,
            'thumbs_up': 1,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        }
    ]
    with patch("sys.argv", ["cli.py", "scrape", "--count", "1"]):
        main()
        
    # Check that it saved in test database
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM play_store_reviews WHERE review_id = 'cli_test_1';")
        assert cur.fetchone()['count'] == 1

@patch('cli.enrich_reviews')
def test_cli_enrich(mock_enrich):
    """Verify that cli.py enrich parses arguments and runs correctly."""
    mock_enrich.return_value = 5
    with patch("sys.argv", ["cli.py", "enrich", "--limit", "10", "--batch-size", "5"]):
        main()
    mock_enrich.assert_called_once_with(batch_size=5, limit=10)

@patch('cli.generate_embeddings')
def test_cli_embed(mock_embed):
    """Verify that cli.py embed parses arguments and runs correctly."""
    mock_embed.return_value = 3
    with patch("sys.argv", ["cli.py", "embed", "--limit", "15"]):
        main()
    mock_embed.assert_called_once_with(limit=15)

def test_cli_update_stats():
    """Verify that cli.py update-stats runs statistics aggregation."""
    # 1. Setup mock review and analysis in database
    review_id = 'stats_cli_test_1'
    save_reviews_to_db([{
        'review_id': review_id,
        'review_text': 'I like search.',
        'rating': 4,
        'thumbs_up': 1,
        'app_version': '1.0.0',
        'review_date': datetime(2026, 6, 15, 12, 0, 0)
    }], 'Spotify')
    
    save_enrichment(review_id, {
        'sentiment': 'positive',
        'themes': ['search'],
        'frustrations': ['repetitive_recommendations'],
        'jobs_to_be_done': ['escape_repetition'],
        'user_segment': 'music_explorer',
        'listening_behavior': 'active_exploration',
        'summary': 'Summary text'
    })
    
    # 2. Trigger statistics updates
    with patch("sys.argv", ["cli.py", "update-stats"]):
        main()
        
    # 3. Assert stats databases are filled
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM theme_statistics_daily WHERE theme = 'search';")
        row = cur.fetchone()
        assert row is not None
        assert row['count'] == 1
        assert str(row['date']) == '2026-06-15'
        
        cur.execute("SELECT * FROM frustration_statistics_daily WHERE frustration = 'repetitive_recommendations';")
        assert cur.fetchone() is not None
        
        cur.execute("SELECT * FROM segment_statistics_daily WHERE segment = 'music_explorer';")
        assert cur.fetchone() is not None
