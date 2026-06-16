import os
import sys
import io
import json
import logging
from google import genai
from database.connection import get_db_cursor, get_db_connection

logger = logging.getLogger(__name__)

def db_schema_inspector() -> str:
    """Return a detailed text description of all tables and columns in the database."""
    query = """
    SELECT 
        table_name, 
        column_name, 
        data_type 
    FROM 
        information_schema.columns 
    WHERE 
        table_schema = 'public'
    ORDER BY 
        table_name, ordinal_position;
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            
        tables = {}
        for r in rows:
            t_name = r['table_name']
            if t_name not in tables:
                tables[t_name] = []
            tables[t_name].append(f"  {r['column_name']} ({r['data_type']})")
            
        schema_desc = "Database Schema:\n"
        for t_name, cols in tables.items():
            schema_desc += f"Table: {t_name}\n" + "\n".join(cols) + "\n\n"
        return schema_desc.strip()
    except Exception as e:
        return f"Error inspecting schema: {e}"

def sql_query_tool(sql: str) -> str:
    """
    Execute a read-only SQL query against the database and return results in JSON.
    Only SELECT statements are allowed.
    """
    stripped = sql.strip().lower()
    if not stripped.startswith("select"):
        return "Error: Only SELECT queries are permitted for safety."
        
    try:
        with get_db_cursor() as cur:
            cur.execute(sql)
            results = cur.fetchall()
            
        # Serialize datetime objects to string
        def serialize_datetime(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return str(obj)

        return json.dumps(results, default=serialize_datetime, indent=2)
    except Exception as e:
        return f"SQL Execution Error: {e}"

def vector_search_tool(query_text: str, limit: int = 5) -> str:
    """
    Perform a semantic vector similarity search on the review database.
    Generates embedding for the query using Gemini and searches review_embeddings.
    """
    if not os.getenv("GEMINI_API_KEY") and os.getenv("TESTING") != "True":
        return "Error: GEMINI_API_KEY environment variable is not set."
        
    try:
        # 1. Generate query embedding
        # Use mock vector if testing and GEMINI_API_KEY is not set
        if os.getenv("TESTING") == "True" and not os.getenv("GEMINI_API_KEY"):
            query_vector = [0.1] * 3072
        else:
            client = genai.Client()
            response = client.models.embed_content(
                model='gemini-embedding-2',
                contents=query_text
            )
            query_vector = response.embeddings[0].values
            
        vector_str = f"[{','.join(map(str, query_vector))}]"
        
        # 2. Perform pgvector query
        search_query = """
        SELECT 
            re.review_id, 
            r.review_text, 
            r.rating,
            ra.sentiment,
            ra.themes,
            ra.frustrations,
            (re.embedding <=> %s::vector) as distance
        FROM review_embeddings re
        JOIN play_store_reviews r ON re.review_id = r.review_id
        JOIN review_analysis ra ON re.review_id = ra.review_id
        ORDER BY distance ASC
        LIMIT %s;
        """
        
        with get_db_cursor() as cur:
            cur.execute(search_query, (vector_str, limit))
            results = cur.fetchall()
            
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Vector Search Error: {e}"

def python_analysis_tool(code: str) -> str:
    """
    Run an arbitrary python script for data analysis/plotting calculations.
    Provides utility context variables (like sql_query_tool) to the execution scope.
    """
    # Redirect stdout and stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    
    # Setup execution context
    local_vars = {
        'sql_query': sql_query_tool,
        'vector_search': vector_search_tool,
        'schema_inspector': db_schema_inspector
    }
    
    try:
        # Run code
        exec(code, globals(), local_vars)
        stdout_val = sys.stdout.getvalue()
        stderr_val = sys.stderr.getvalue()
        
        output = stdout_val
        if stderr_val:
            output += f"\nStderr:\n{stderr_val}"
        return output if output else "Execution completed with no output."
    except Exception as e:
        return f"Python Execution Error: {e}\nStdout:\n{sys.stdout.getvalue()}\nStderr:\n{sys.stderr.getvalue()}"
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
