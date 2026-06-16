import os
import hashlib
import logging
from google import genai
from database.connection import get_db_cursor
from agent.tools import db_schema_inspector, sql_query_tool, vector_search_tool

logger = logging.getLogger(__name__)

def get_query_hash(question: str) -> str:
    """Generate SHA256 hash for a given question string."""
    return hashlib.sha256(question.strip().lower().encode('utf-8')).hexdigest()

def get_cached_response(question: str) -> str | None:
    """Retrieve cached response for a question if it exists."""
    q_hash = get_query_hash(question)
    query = "SELECT response FROM query_cache WHERE query_hash = %s;"
    try:
        with get_db_cursor() as cur:
            cur.execute(query, (q_hash,))
            row = cur.fetchone()
            if row:
                logger.info("Cache Hit: Found cached response for question.")
                return row['response']
    except Exception as e:
        logger.error(f"Error checking query cache: {e}")
    return None

def cache_response(question: str, response_text: str) -> None:
    """Save the agent response in the query_cache table."""
    q_hash = get_query_hash(question)
    query = """
    INSERT INTO query_cache (query_hash, response)
    VALUES (%s, %s)
    ON CONFLICT (query_hash) DO UPDATE SET response = EXCLUDED.response, created_at = NOW();
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(query, (q_hash, response_text))
        logger.info("Saved agent response to query cache.")
    except Exception as e:
        logger.error(f"Error saving to query cache: {e}")

def answer_research_question(question: str) -> str:
    """
    Main research agent workflow.
    Implements a hybrid retrieval strategy: cache check -> schema -> SQL stats -> vector search -> LLM synthesis.
    """
    # 1. Check cache first
    cached = get_cached_response(question)
    if cached:
        return cached

    logger.info(f"Synthesizing response for query: {question}")
    
    # Check Gemini API Key
    if not os.getenv("GEMINI_API_KEY") and os.getenv("TESTING") != "True":
        return "Error: GEMINI_API_KEY environment variable is not set."

    # 2. Gather Schema Context
    schema_desc = db_schema_inspector()

    # 3. Perform SQL Aggregation Stats
    # Get top 5 daily themes and frustrations
    sql_themes = sql_query_tool("""
        SELECT theme, SUM(count) as total_count 
        FROM theme_statistics_daily 
        GROUP BY theme 
        ORDER BY total_count DESC 
        LIMIT 5;
    """)
    
    sql_frustrations = sql_query_tool("""
        SELECT frustration, SUM(count) as total_count 
        FROM frustration_statistics_daily 
        GROUP BY frustration 
        ORDER BY total_count DESC 
        LIMIT 5;
    """)
    
    sql_ratings = sql_query_tool("""
        SELECT rating, COUNT(*) as count 
        FROM play_store_reviews 
        GROUP BY rating 
        ORDER BY rating DESC;
    """)

    # 4. Perform Semantic Vector Retrieval (retrieve top 10 relevant reviews)
    vector_evidence = vector_search_tool(question, limit=10)

    # 5. Call LLM for final Synthesis
    # Mock LLM synthesis for testing if GEMINI_API_KEY is not set
    if os.getenv("TESTING") == "True" and not os.getenv("GEMINI_API_KEY"):
        synthesis = (
            "Mock Report:\n"
            f"Based on SQL aggregate evidence, the top frustration is repetitive recommendations. "
            f"Semantic reviews highlight users struggle to discover music because songs repeat. "
            f"Question answered: {question}"
        )
    else:
        client = genai.Client()
        prompt = (
            f"User Research Query: {question}\n\n"
            "Analyze the retrieved quantitative and qualitative database evidence below to construct a comprehensive "
            "and grounded research report answering the research query. Be objective, thorough, and reference specific statistics "
            "and review snippets from the evidence.\n\n"
            "--- DATABASE EVIDENCE ---\n\n"
            f"Database Schema:\n{schema_desc}\n\n"
            f"Top Themes (SQL aggregate stats):\n{sql_themes}\n\n"
            f"Top Frustrations (SQL aggregate stats):\n{sql_frustrations}\n\n"
            f"Ratings Distribution:\n{sql_ratings}\n\n"
            f"Relevant Raw Reviews & AI Enrichments (Semantic vector search):\n{vector_evidence}\n\n"
            "--- INSTRUCTIONS ---\n\n"
            "Format the report in markdown with the following sections:\n"
            "1. Executive Summary\n"
            "2. Quantitative Insights (citing frequencies, ratings, database percentages)\n"
            "3. Qualitative Insights (citing specific review complaints and sentiments)\n"
            "4. Recommendations & Unmet Needs"
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        synthesis = response.text

    # 6. Cache the response
    cache_response(question, synthesis)
    
    return synthesis
