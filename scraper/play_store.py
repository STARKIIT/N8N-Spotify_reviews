import logging
from datetime import datetime
from google_play_scraper import Sort, reviews
from database.connection import get_db_cursor

logger = logging.getLogger(__name__)

def scrape_play_store_reviews(app_id: str, count: int = 100, lang: str = 'en', country: str = 'in') -> list[dict]:
    """
    Scrape reviews for a given app from Google Play Store.
    
    Args:
        app_id: The package name of the app (e.g. 'com.spotify.music')
        count: Number of reviews to fetch
        lang: Language code
        country: Country code
        
    Returns:
        A list of normalized review dictionaries.
    """
    logger.info(f"Scraping up to {count} reviews for {app_id} (lang: {lang}, country: {country})...")
    try:
        raw_reviews, _ = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=count
        )
        logger.info(f"Successfully scraped {len(raw_reviews)} reviews.")
        
        normalized = []
        for r in raw_reviews:
            normalized.append({
                'review_id': r.get('reviewId'),
                'review_text': r.get('content'),
                'rating': r.get('score'),
                'thumbs_up': r.get('thumbsUpCount'),
                'review_date': r.get('at'),
                'app_version': r.get('reviewCreatedVersion'),
                'country': country,
            })
        return normalized
    except Exception as e:
        logger.error(f"Error scraping Play Store reviews: {e}")
        raise

def save_reviews_to_db(reviews_list: list[dict], app_name: str) -> int:
    """
    Insert scraped reviews into the play_store_reviews table.
    Uses ON CONFLICT (review_id) DO NOTHING to prevent duplicates.
    
    Args:
        reviews_list: List of normalized review dictionaries.
        app_name: The name of the app (e.g. 'Spotify')
        
    Returns:
        The number of newly inserted reviews.
    """
    insert_query = """
    INSERT INTO play_store_reviews (
        review_id, app_name, review_text, rating, thumbs_up, review_date, app_version, source, country
    ) VALUES (
        %(review_id)s, %(app_name)s, %(review_text)s, %(rating)s, %(thumbs_up)s, %(review_date)s, %(app_version)s, 'play_store', %(country)s
    ) ON CONFLICT (review_id) DO NOTHING;
    """
    
    new_inserts = 0
    with get_db_cursor() as cur:
        for r in reviews_list:
            # Prepare data
            data = {
                'review_id': r['review_id'],
                'app_name': app_name,
                'review_text': r['review_text'],
                'rating': r['rating'],
                'thumbs_up': r['thumbs_up'],
                'review_date': r['review_date'],
                'app_version': r['app_version'],
                'country': r.get('country', 'in')
            }
            cur.execute(insert_query, data)
            # rowcount is 1 if inserted, 0 if conflict occurred
            if cur.rowcount > 0:
                new_inserts += 1
                
    logger.info(f"Saved {new_inserts} new reviews for {app_name} to the database (skipped {len(reviews_list) - new_inserts} duplicates).")
    return new_inserts
