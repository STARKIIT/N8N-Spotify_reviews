import os
import logging
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "spotify_voc")
if os.getenv("TESTING") == "True":
    DB_NAME = DB_NAME + "_test"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_conn_info():
    """Return database connection info string or parameters."""
    conn_info = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME}"
    if DB_USER:
        conn_info += f" user={DB_USER}"
    if DB_PASSWORD:
        conn_info += f" password={DB_PASSWORD}"
    return conn_info

@contextmanager
def get_db_connection():
    """Context manager for database connections and transactions."""
    conn_info = get_conn_info()
    conn = psycopg.connect(conn_info)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction error: {e}")
        raise
    finally:
        conn.close()

@contextmanager
def get_db_cursor(row_factory=dict_row):
    """Context manager for database cursors."""
    with get_db_connection() as conn:
        with conn.cursor(row_factory=row_factory) as cur:
            yield cur

def setup_database():
    """Create the database tables required for the application."""
    create_table_query = """
    CREATE TABLE IF NOT EXISTS play_store_reviews (
        review_id TEXT PRIMARY KEY,
        app_name TEXT NOT NULL,
        review_text TEXT,
        rating INTEGER,
        thumbs_up INTEGER,
        review_date TIMESTAMP,
        app_version TEXT,
        source TEXT DEFAULT 'play_store',
        country TEXT DEFAULT 'us',
        inserted_at TIMESTAMP DEFAULT NOW()
    );
    """
    logger.info("Setting up database tables...")
    with get_db_cursor() as cur:
        cur.execute(create_table_query)
        # Migrate existing table to include country column if it doesn't exist
        cur.execute("ALTER TABLE play_store_reviews ADD COLUMN IF NOT EXISTS country TEXT DEFAULT 'us';")
        
        # Read and run schema_enrichment.sql if it exists
        dir_path = os.path.dirname(os.path.abspath(__file__))
        enrich_path = os.path.join(dir_path, "schema_enrichment.sql")
        if os.path.exists(enrich_path):
            logger.info(f"Running migration: {enrich_path}")
            with open(enrich_path, "r") as f:
                cur.execute(f.read())

        # Read and run schema_embeddings.sql if it exists
        embed_path = os.path.join(dir_path, "schema_embeddings.sql")
        if os.path.exists(embed_path):
            logger.info(f"Running migration: {embed_path}")
            with open(embed_path, "r") as f:
                cur.execute(f.read())

        # Read and run schema_agent.sql if it exists
        agent_path = os.path.join(dir_path, "schema_agent.sql")
        if os.path.exists(agent_path):
            logger.info(f"Running migration: {agent_path}")
            with open(agent_path, "r") as f:
                cur.execute(f.read())
                
    logger.info("Database tables set up successfully.")

def update_daily_statistics():
    """Aggregate review analysis data and update daily stats tables."""
    theme_query = """
    INSERT INTO theme_statistics_daily (date, theme, count)
    SELECT 
        psr.review_date::date as date,
        theme.value::text as theme,
        COUNT(*) as count
    FROM review_analysis ra
    JOIN play_store_reviews psr ON ra.review_id = psr.review_id
    CROSS JOIN LATERAL jsonb_array_elements_text(ra.themes) as theme
    GROUP BY date, theme
    ON CONFLICT (date, theme) DO UPDATE SET count = EXCLUDED.count;
    """
    
    frustration_query = """
    INSERT INTO frustration_statistics_daily (date, frustration, count)
    SELECT 
        psr.review_date::date as date,
        frust.value::text as frustration,
        COUNT(*) as count
    FROM review_analysis ra
    JOIN play_store_reviews psr ON ra.review_id = psr.review_id
    CROSS JOIN LATERAL jsonb_array_elements_text(ra.frustrations) as frust
    GROUP BY date, frustration
    ON CONFLICT (date, frustration) DO UPDATE SET count = EXCLUDED.count;
    """
    
    segment_query = """
    INSERT INTO segment_statistics_daily (date, segment, count)
    SELECT 
        psr.review_date::date as date,
        ra.user_segment as segment,
        COUNT(*) as count
    FROM review_analysis ra
    JOIN play_store_reviews psr ON ra.review_id = psr.review_id
    WHERE ra.user_segment IS NOT NULL
    GROUP BY date, segment
    ON CONFLICT (date, segment) DO UPDATE SET count = EXCLUDED.count;
    """
    
    logger.info("Updating daily statistics tables...")
    with get_db_cursor() as cur:
        cur.execute(theme_query)
        cur.execute(frustration_query)
        cur.execute(segment_query)
    logger.info("Daily statistics tables updated successfully.")
