import os
import json
import logging
from google import genai
from google.genai import types
from database.connection import get_db_cursor, get_db_connection

logger = logging.getLogger(__name__)

# Inline raw schema definition mapping to integer list indices for safety
ENRICHMENT_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'enrichments': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'review_index': {
                        'type': 'INTEGER',
                        'description': 'The index of the review in the input list (e.g. 0, 1, 2, ...)'
                    },
                    'sentiment': {
                        'type': 'STRING',
                        'description': 'Overall sentiment: positive, neutral, or negative'
                    },
                    'themes': {
                        'type': 'ARRAY',
                        'items': {'type': 'STRING'},
                        'description': "Themes associated with the review, e.g. 'music_discovery', 'recommendations', 'playlists', 'personalization', 'search', 'exploration'"
                    },
                    'frustrations': {
                        'type': 'ARRAY',
                        'items': {'type': 'STRING'},
                        'description': "User frustrations mentioned, e.g. 'repetitive_recommendations', 'mainstream_bias', 'poor_niche_discovery', 'playlist_quality', 'recommendation_accuracy'"
                    },
                    'jobs_to_be_done': {
                        'type': 'ARRAY',
                        'items': {'type': 'STRING'},
                        'description': "Jobs-to-be-done statements (what the user is trying to achieve), e.g. 'discover_new_artists', 'explore_new_genres', 'reduce_search_effort', 'find_music_for_moods', 'escape_repetition'"
                    },
                    'user_segment': {
                        'type': 'STRING',
                        'description': "Categorization of the user segment: 'casual_listener', 'playlist_listener', 'music_explorer', 'genre_specialist', 'heavy_listener'"
                    },
                    'listening_behavior': {
                        'type': 'STRING',
                        'description': "Categorization of listening behavior: 'passive_listening', 'active_exploration', 'comfort_listening', 'mood_based_listening', 'social_discovery'"
                    },
                    'summary': {
                        'type': 'STRING',
                        'description': 'A brief 1-sentence summary of the review content'
                    }
                },
                'required': [
                    'review_index', 'sentiment', 'themes', 'frustrations', 
                    'jobs_to_be_done', 'user_segment', 'listening_behavior', 'summary'
                ]
            }
        }
    },
    'required': ['enrichments']
}

def get_unenriched_reviews(limit: int = 100) -> list[dict]:
    """Retrieve up to 'limit' reviews that have not been analyzed yet."""
    query = """
    SELECT review_id, review_text
    FROM play_store_reviews
    WHERE review_id NOT IN (
        SELECT review_id FROM review_analysis
    )
    ORDER BY inserted_at DESC
    LIMIT %s;
    """
    with get_db_cursor() as cur:
        cur.execute(query, (limit,))
        return cur.fetchall()

def find_existing_analysis_for_text(review_text: str) -> dict | None:
    """
    Check if a review with the exact same text has already been enriched.
    Returns the enrichment dict if found, else None.
    """
    query = """
    SELECT ra.sentiment, ra.themes, ra.frustrations, ra.jobs_to_be_done, ra.user_segment, ra.listening_behavior, ra.summary
    FROM review_analysis ra
    JOIN play_store_reviews psr ON ra.review_id = psr.review_id
    WHERE psr.review_text = %s
    LIMIT 1;
    """
    with get_db_cursor() as cur:
        cur.execute(query, (review_text,))
        return cur.fetchone()

def save_enrichment(review_id: str, enrichment: dict) -> None:
    """Save an enrichment record in the database."""
    query = """
    INSERT INTO review_analysis (
        review_id, sentiment, themes, frustrations, jobs_to_be_done, user_segment, listening_behavior, summary
    ) VALUES (
        %(review_id)s, %(sentiment)s, %(themes)s, %(frustrations)s, %(jobs_to_be_done)s, %(user_segment)s, %(listening_behavior)s, %(summary)s
    ) ON CONFLICT (review_id) DO UPDATE SET
        sentiment = EXCLUDED.sentiment,
        themes = EXCLUDED.themes,
        frustrations = EXCLUDED.frustrations,
        jobs_to_be_done = EXCLUDED.jobs_to_be_done,
        user_segment = EXCLUDED.user_segment,
        listening_behavior = EXCLUDED.listening_behavior,
        summary = EXCLUDED.summary,
        analyzed_at = NOW();
    """
    # Ensure JSON fields are serialized
    themes_json = json.dumps(enrichment.get('themes', []))
    frustrations_json = json.dumps(enrichment.get('frustrations', []))
    jtbd_json = json.dumps(enrichment.get('jobs_to_be_done', []))
    
    data = {
        'review_id': review_id,
        'sentiment': enrichment.get('sentiment'),
        'themes': themes_json,
        'frustrations': frustrations_json,
        'jobs_to_be_done': jtbd_json,
        'user_segment': enrichment.get('user_segment'),
        'listening_behavior': enrichment.get('listening_behavior'),
        'summary': enrichment.get('summary')
    }
    
    with get_db_cursor() as cur:
        cur.execute(query, data)

def run_enrichment_batch(reviews_batch: list[dict], client: genai.Client) -> int:
    """
    Process a list of reviews: checks duplicates, calls Gemini for new ones, and stores everything.
    """
    if not reviews_batch:
        return 0

    enriched_count = 0
    to_llm_batch = []
    
    # Text-to-review_id mapping to resolve duplicates inside the current batch
    text_to_ids = {}

    for r in reviews_batch:
        r_id = r['review_id']
        r_text = r['review_text'] or ""
        
        # 1. Check if exact text was already enriched in the database
        existing = find_existing_analysis_for_text(r_text)
        if existing:
            logger.info(f"Deduplication: Reusing existing analysis for review {r_id}")
            save_enrichment(r_id, existing)
            enriched_count += 1
            continue

        # 2. Check if text is a duplicate within the current batch
        if r_text in text_to_ids:
            text_to_ids[r_text].append(r_id)
            continue
        else:
            text_to_ids[r_text] = [r_id]
            to_llm_batch.append(r)

    # If there are reviews to analyze with LLM
    if to_llm_batch:
        logger.info(f"Sending {len(to_llm_batch)} unique reviews to Gemini for analysis...")
        
        # Prepare content prompt
        reviews_prompt_list = []
        for index, r in enumerate(to_llm_batch):
            reviews_prompt_list.append(f"Review Index: {index}\nText: {r['review_text'] or '[Empty]'}\n---")
        
        prompt = (
            "Analyze the following user reviews for the music app Spotify.\n"
            "For each review, determine the sentiment, themes, frustrations, jobs_to_be_done, "
            "user_segment, listening_behavior, and provide a 1-sentence summary.\n\n"
            "Reviews list:\n"
            + "\n".join(reviews_prompt_list)
        )
        
        # Call Gemini API
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ENRICHMENT_SCHEMA,
                system_instruction=(
                    "You are an expert Voice-of-Customer researcher analyzing user feedback. "
                    "For each review, extract taxonomy fields accurately and return its corresponding review_index. Be concise."
                )
            )
        )
        
        try:
            response_dict = json.loads(response.text)
            enrichment_list = response_dict.get('enrichments', [])
            
            for enrichment_item in enrichment_list:
                idx = enrichment_item.get('review_index')
                if idx is None or not (0 <= idx < len(to_llm_batch)):
                    logger.warning(f"Invalid review index returned from LLM: {idx}")
                    continue
                
                canonical_review = to_llm_batch[idx]
                canonical_id = canonical_review['review_id']
                
                analysis_dict = {
                    'sentiment': enrichment_item.get('sentiment'),
                    'themes': enrichment_item.get('themes', []),
                    'frustrations': enrichment_item.get('frustrations', []),
                    'jobs_to_be_done': enrichment_item.get('jobs_to_be_done', []),
                    'user_segment': enrichment_item.get('user_segment'),
                    'listening_behavior': enrichment_item.get('listening_behavior'),
                    'summary': enrichment_item.get('summary')
                }
                
                # Save canonical review
                save_enrichment(canonical_id, analysis_dict)
                enriched_count += 1
                
                # Copy to all duplicates in current batch
                text = canonical_review['review_text']
                for dup_id in text_to_ids.get(text, []):
                    if dup_id != canonical_id:
                        logger.info(f"Deduplication (Batch): Reusing LLM analysis from {canonical_id} for {dup_id}")
                        save_enrichment(dup_id, analysis_dict)
                        enriched_count += 1
                        
        except Exception as e:
            logger.error(f"Error parsing Gemini response or saving to database: {e}")
            logger.debug(f"Raw response: {response.text}")
            raise

    return enriched_count

def enrich_reviews(batch_size: int = 50, limit: int = 100) -> int:
    """Retrieve unenriched reviews and enrich them in batches."""
    # Initialize client (uses GEMINI_API_KEY environment variable)
    if not os.getenv("GEMINI_API_KEY") and os.getenv("TESTING") != "True":
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
    client = genai.Client()
    unenriched = get_unenriched_reviews(limit=limit)
    
    if not unenriched:
        logger.info("No unenriched reviews found.")
        return 0
        
    logger.info(f"Found {len(unenriched)} unenriched reviews to process.")
    total_enriched = 0
    
    # Process in batches of size batch_size
    for i in range(0, len(unenriched), batch_size):
        batch = unenriched[i : i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} reviews)...")
        enriched = run_enrichment_batch(batch, client)
        total_enriched += enriched
        
    logger.info(f"Enrichment pipeline complete. Enriched {total_enriched} reviews.")
    return total_enriched
