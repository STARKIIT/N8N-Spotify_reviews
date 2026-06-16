import argparse
import sys
import logging
from database.connection import setup_database, update_daily_statistics
from scraper.play_store import scrape_play_store_reviews, save_reviews_to_db
from enrichment.pipeline import enrich_reviews
from embeddings.generator import generate_embeddings
from agent.engine import answer_research_question

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cli")

def main():
    parser = argparse.ArgumentParser(description="Spotify Reviews Scraper & Analyzer CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: setup-db
    subparsers.add_parser("setup-db", help="Initialize PostgreSQL tables")

    # Command: scrape
    scrape_parser = subparsers.add_parser("scrape", help="Scrape reviews from Google Play Store")
    scrape_parser.add_argument("--app-id", default="com.spotify.music", help="App package ID to scrape")
    scrape_parser.add_argument("--app-name", default="Spotify", help="Human-readable app name")
    scrape_parser.add_argument("--count", type=int, default=100, help="Number of reviews to fetch")
    scrape_parser.add_argument("--lang", default="en", help="Language code")
    scrape_parser.add_argument("--country", default="in", help="Country code")

    # Command: enrich
    enrich_parser = subparsers.add_parser("enrich", help="Enrich raw reviews using Gemini LLM analysis")
    enrich_parser.add_argument("--batch-size", type=int, default=50, help="Batch size for LLM calls")
    enrich_parser.add_argument("--limit", type=int, default=100, help="Maximum number of reviews to process")

    # Command: embed
    embed_parser = subparsers.add_parser("embed", help="Generate vector embeddings for enriched reviews")
    embed_parser.add_argument("--limit", type=int, default=100, help="Maximum number of reviews to process")

    # Command: update-stats
    subparsers.add_parser("update-stats", help="Aggregate review analytics and update statistics tables")

    # Command: ask
    ask_parser = subparsers.add_parser("ask", help="Ask the research agent a question using hybrid database retrieval")
    ask_parser.add_argument("--question", "-q", required=True, help="Research question to answer")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "setup-db":
            logger.info("Initializing database...")
            setup_database()
            logger.info("Database initialization complete.")
        elif args.command == "scrape":
            logger.info(f"Starting scraper for {args.app_name} ({args.app_id})...")
            reviews_list = scrape_play_store_reviews(
                app_id=args.app_id,
                count=args.count,
                lang=args.lang,
                country=args.country
            )
            new_count = save_reviews_to_db(reviews_list, args.app_name)
            logger.info(f"Scrape command completed. {new_count} new reviews saved.")
        elif args.command == "enrich":
            logger.info(f"Starting enrichment pipeline (limit: {args.limit}, batch_size: {args.batch_size})...")
            enriched_count = enrich_reviews(
                batch_size=args.batch_size,
                limit=args.limit
            )
            logger.info(f"Enrichment command completed. {enriched_count} reviews enriched.")
        elif args.command == "embed":
            logger.info(f"Starting embeddings generation (limit: {args.limit})...")
            embedded_count = generate_embeddings(limit=args.limit)
            logger.info(f"Embed command completed. {embedded_count} reviews embedded.")
        elif args.command == "update-stats":
            logger.info("Starting daily stats update aggregation...")
            update_daily_statistics()
            logger.info("Update statistics completed.")
        elif args.command == "ask":
            logger.info(f"Submitting query to research agent...")
            report = answer_research_question(args.question)
            print("\n=== RESEARCH REPORT ===")
            print(report)
            print("=======================\n")
    except Exception as e:
        logger.error(f"Error executing command '{args.command}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
