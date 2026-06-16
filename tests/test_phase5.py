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
from enrichment.pipeline import save_enrichment
from embeddings.generator import save_embedding
from agent.tools import db_schema_inspector, sql_query_tool, vector_search_tool, python_analysis_tool
from agent.engine import answer_research_question, get_query_hash, get_cached_response, cache_response

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure test tables exist."""
    setup_database()
    yield
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS query_cache CASCADE;")
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
            cur.execute("TRUNCATE TABLE query_cache CASCADE;")
            cur.execute("TRUNCATE TABLE review_embeddings CASCADE;")
            cur.execute("TRUNCATE TABLE review_analysis CASCADE;")
            cur.execute("TRUNCATE TABLE play_store_reviews CASCADE;")

def test_query_cache_table_exists():
    """Verify query_cache exists in database."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'query_cache'
            );
        """)
        assert cur.fetchone()['exists'] is True

def test_sql_query_tool_security():
    """Verify that only SELECT queries are permitted by the sql_query_tool."""
    res_select = sql_query_tool("SELECT COUNT(*) FROM play_store_reviews;")
    assert "SQL Execution Error" not in res_select
    assert "Error: Only SELECT queries are permitted" not in res_select
    
    res_drop = sql_query_tool("DROP TABLE play_store_reviews;")
    assert "Error: Only SELECT queries are permitted" in res_drop
    
    res_insert = sql_query_tool("INSERT INTO play_store_reviews (review_id) VALUES ('evil');")
    assert "Error: Only SELECT queries are permitted" in res_insert

def test_db_schema_inspector():
    """Verify that the database schema is correctly inspected and described."""
    schema_info = db_schema_inspector()
    assert "play_store_reviews" in schema_info
    assert "review_analysis" in schema_info
    assert "review_embeddings" in schema_info
    assert "query_cache" in schema_info

def test_python_analysis_tool():
    """Verify Python tool redirects stdout and operates variables."""
    code = """
import json
print("hello world")
"""
    output = python_analysis_tool(code)
    assert "hello world" in output

    code_db = """
schema = schema_inspector()
print("inspect:", "query_cache" in schema)
"""
    output_db = python_analysis_tool(code_db)
    assert "inspect: True" in output_db

def test_query_caching_and_hashing():
    """Test SHA256 caching functions."""
    question = "What are the common listening behaviors?"
    h = get_query_hash(question)
    
    # Check cache miss
    assert get_cached_response(question) is None
    
    # Cache response
    response_text = "Analysis shows social discovery is common."
    cache_response(question, response_text)
    
    # Check cache hit
    assert get_cached_response(question) == response_text
    
    # Check in DB directly
    with get_db_cursor() as cur:
        cur.execute("SELECT response FROM query_cache WHERE query_hash = %s;", (h,))
        assert cur.fetchone()['response'] == response_text

@patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""})
def test_answer_research_question_workflow():
    """Test full hybrid retrieval workflow."""
    # 1. Setup mock reviews and embeddings in DB
    review_id = 'agent_test_1'
    save_reviews_to_db([{
        'review_id': review_id,
        'review_text': 'Spotify recommendations keep repeating.',
        'rating': 2,
        'thumbs_up': 5,
        'app_version': '1.0.0',
        'review_date': datetime.now()
    }], 'Spotify')
    
    save_enrichment(review_id, {
        'sentiment': 'negative',
        'themes': ['recommendations'],
        'frustrations': ['repetitive_recommendations'],
        'jobs_to_be_done': ['escape_repetition'],
        'user_segment': 'casual_listener',
        'listening_behavior': 'comfort_listening',
        'summary': 'Repeating songs frustration'
    })
    
    # 3072-dim mock vector
    save_embedding(review_id, [0.1] * 3072)

    # 2. Run query orchestrator
    question = "Why do users complain about repeating recommendations?"
    
    # Since GEMINI_API_KEY is not set under tests, it will fall back to mock synthesis output
    report = answer_research_question(question)
    
    assert "Mock Report:" in report
    assert "repetitive recommendations" in report
    assert question in report
    
    # Verify report is now cached in database
    cached_report = get_cached_response(question)
    assert cached_report == report
