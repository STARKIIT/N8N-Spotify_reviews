import os
import pytest
import psycopg
from datetime import datetime
from unittest.mock import patch, MagicMock

# Set testing environment variable BEFORE importing connection module
os.environ["TESTING"] = "True"

from database.connection import setup_database, get_db_connection, get_db_cursor, DB_HOST, DB_PORT, DB_USER, DB_PASSWORD
from scraper.play_store import scrape_play_store_reviews, save_reviews_to_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create the test database if it does not exist, and set up schemas."""
    # Connect to the default 'postgres' database to manage test db creation
    conn_info = f"host={DB_HOST} port={DB_PORT} dbname=postgres"
    if DB_USER:
        conn_info += f" user={DB_USER}"
    if DB_PASSWORD:
        conn_info += f" password={DB_PASSWORD}"
        
    conn = psycopg.connect(conn_info, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'spotify_voc_test'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE spotify_voc_test")
    cur.close()
    conn.close()
    
    # Initialize schema in test db
    setup_database()
    
    yield
    
    # Clean up database tables after the session
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS play_store_reviews CASCADE;")

@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate tables before each test to ensure test isolation."""
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE play_store_reviews CASCADE;")

def test_database_tables_exist():
    """Verify that the required tables exist in the database."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'play_store_reviews'
            );
        """)
        assert cur.fetchone()['exists'] is True

def test_scrape_play_store_reviews_mocked():
    """Test that Google Play Store reviews are correctly scraped and normalized."""
    mock_raw_reviews = [
        {
            'reviewId': 'rev1',
            'content': 'Great app!',
            'score': 5,
            'thumbsUpCount': 10,
            'reviewCreatedVersion': '1.0.0',
            'at': datetime(2026, 6, 1, 12, 0, 0)
        },
        {
            'reviewId': 'rev2',
            'content': 'Too many bugs',
            'score': 2,
            'thumbsUpCount': 3,
            'reviewCreatedVersion': '0.9.0',
            'at': datetime(2026, 6, 2, 14, 0, 0)
        }
    ]
    
    with patch('scraper.play_store.reviews') as mock_reviews:
        mock_reviews.return_value = (mock_raw_reviews, None)
        
        normalized = scrape_play_store_reviews('com.spotify.music', count=2)
        
        assert len(normalized) == 2
        assert normalized[0]['review_id'] == 'rev1'
        assert normalized[0]['review_text'] == 'Great app!'
        assert normalized[0]['rating'] == 5
        assert normalized[0]['thumbs_up'] == 10
        assert normalized[0]['app_version'] == '1.0.0'
        assert normalized[0]['review_date'] == datetime(2026, 6, 1, 12, 0, 0)

def test_save_reviews_to_db_and_deduplication():
    """Test saving reviews to the database and ensuring duplicate reviews are skipped."""
    mock_reviews = [
        {
            'review_id': 'rev_dup_test_1',
            'review_text': 'I love Spotify',
            'rating': 5,
            'thumbs_up': 2,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        },
        {
            'review_id': 'rev_dup_test_2',
            'review_text': 'Sometimes crashes',
            'rating': 3,
            'thumbs_up': 0,
            'app_version': '1.0.0',
            'review_date': datetime.now()
        }
    ]
    
    # Save for the first time
    inserted = save_reviews_to_db(mock_reviews, 'Spotify')
    assert inserted == 2
    
    # Verify records in db
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM play_store_reviews;")
        count = cur.fetchone()['count']
        assert count == 2
        
        cur.execute("SELECT review_text, rating FROM play_store_reviews WHERE review_id = 'rev_dup_test_1';")
        row = cur.fetchone()
        assert row['review_text'] == 'I love Spotify'
        assert row['rating'] == 5

    # Try inserting the same list again (should skip all of them)
    inserted_again = save_reviews_to_db(mock_reviews, 'Spotify')
    assert inserted_again == 0
    
    # Verify the count remains 2
    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM play_store_reviews;")
        assert cur.fetchone()['count'] == 2
