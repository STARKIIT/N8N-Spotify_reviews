import os
import json
import logging
from google import genai
from database.connection import get_db_cursor

logger = logging.getLogger(__name__)

def get_unembedded_reviews(limit: int = 100) -> list[dict]:
    """Retrieve reviews that have been enriched but do not have embeddings yet."""
    query = """
    SELECT r.review_id, r.review_text, ra.themes, ra.frustrations, ra.jobs_to_be_done, ra.summary
    FROM play_store_reviews r
    JOIN review_analysis ra ON r.review_id = ra.review_id
    LEFT JOIN review_embeddings re ON r.review_id = re.review_id
    WHERE re.review_id IS NULL
    LIMIT %s;
    """
    with get_db_cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()

def build_embedding_chunk(review: dict) -> str:
    """Combine review text, themes, frustrations, JTBD, and summary into a search chunk."""
    text = review.get('review_text') or ""
    
    # Parse JSON list fields if they are strings, otherwise use them directly
    def parse_list_field(field):
        if isinstance(field, str):
            try:
                return json.loads(field)
            except Exception:
                return [field]
        elif isinstance(field, list):
            return field
        return []

    themes = parse_list_field(review.get('themes'))
    frustrations = parse_list_field(review.get('frustrations'))
    jtbd = parse_list_field(review.get('jobs_to_be_done'))
    summary = review.get('summary') or ""
    
    chunk_parts = [f"Review:\n{text}"]
    if themes:
        chunk_parts.append(f"Themes:\n{', '.join(themes)}")
    if frustrations:
        chunk_parts.append(f"Frustrations:\n{', '.join(frustrations)}")
    if jtbd:
        chunk_parts.append(f"Jobs To Be Done:\n{', '.join(jtbd)}")
    if summary:
        chunk_parts.append(f"Summary:\n{summary}")
        
    return "\n\n".join(chunk_parts).strip()

def save_embedding(review_id: str, embedding: list[float]) -> None:
    """Save the embedding vector to the review_embeddings table."""
    # Convert list of floats to Postgres vector format: '[0.1, 0.2, 0.3...]'
    vector_str = f"[{','.join(map(str, embedding))}]"
    
    query = """
    INSERT INTO review_embeddings (review_id, embedding)
    VALUES (%s, %s)
    ON CONFLICT (review_id) DO UPDATE SET embedding = EXCLUDED.embedding;
    """
    with get_db_cursor() as cur:
        cur.execute(query, (review_id, vector_str))

def generate_embeddings(limit: int = 100) -> int:
    """Fetch unembedded records, generate embeddings using Gemini API, and store them."""
    if not os.getenv("GEMINI_API_KEY") and os.getenv("TESTING") != "True":
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
    unembedded = get_unembedded_reviews(limit=limit)
    if not unembedded:
        logger.info("No unembedded reviews found.")
        return 0
        
    logger.info(f"Generating embeddings for {len(unembedded)} reviews...")
    client = genai.Client()
    
    embedded_count = 0
    for review in unembedded:
        review_id = review['review_id']
        chunk_text = build_embedding_chunk(review)
        
        try:
            # Call Gemini embedding API
            response = client.models.embed_content(
                model='gemini-embedding-2',
                contents=chunk_text
            )
            # Retrieve vector values
            embedding_vector = response.embeddings[0].values
            
            save_embedding(review_id, embedding_vector)
            embedded_count += 1
        except Exception as e:
            logger.error(f"Error generating or saving embedding for review {review_id}: {e}")
            raise
            
    logger.info(f"Embeddings generation complete. Processed {embedded_count} reviews.")
    return embedded_count
