# 🎵 Spotify Voice of Customer (VoC) Scraper & Analyzer

A scheduled ETL and AI synthesis pipeline that scrapes Spotify Google Play Store reviews, analyzes sentiment/themes using Gemini, generates vector embeddings for semantic search, and syncs findings to Google Sheets for visualization and research.

---

## 🚀 System Architecture

![System Architecture](assets/system_architecture.png)

---

## 🛠️ Core Components

- **📁 Database Layer (`database/`):** PostgreSQL database with `pgvector` extension integration, connection handling, and schema definitions for storing raw reviews, structured enrichment analysis, daily aggregate statistics, and SHA-256 query caching for the research agent.
- **🕷️ Play Store Scraper (`scraper/`):** Automates pulling Spotify reviews filtered by country, language, and count, utilizing deduplication strategies.
- **🧠 AI Enrichment (`enrichment/`):** Leverages `gemini-2.5-flash` to perform structured JSON extraction classifying sentiment, customer themes, frustrations, and target user segments.
- **🔢 Vector Embeddings (`embeddings/`):** Converts raw text and AI analysis into dense vectors using `text-embedding-004` (Gemini embeddings) and stores them for semantic query capabilities.
- **🤖 Research Agent (`agent/`):** A hybrid agent executing SQL aggregates and semantic/vector queries to generate structured research reports answering product questions.
- **🔗 n8n Orchestration (`n8n/`):** Automates the ingestion, enrichment, and embedding workflows while syncing analysis live to a Google Sheets dashboard.

---

## 📊 Database Schema

### `play_store_reviews` (Raw Ingestion)
| Column Name | Type | Description |
| :--- | :--- | :--- |
| `review_id` | `TEXT` (PK) | Unique identifier assigned by Google Play Store. |
| `app_name` | `TEXT` | Name of the app (e.g., 'Spotify'). |
| `review_text` | `TEXT` | Raw review content left by the user. |
| `rating` | `INTEGER` | Rating score from 1 to 5. |
| `thumbs_up` | `INTEGER` | Number of users who marked this review helpful. |
| `review_date` | `TIMESTAMP` | When the review was published. |
| `app_version` | `TEXT` | Installed version of the app. |
| `country` | `TEXT` | Target country of the Play Store (e.g., `'in'`, `'us'`). |
| `source` | `TEXT` | Ingestion source (defaults to `'play_store'`). |
| `inserted_at` | `TIMESTAMP` | Database insertion timestamp. |

### `review_analysis` (AI Enrichment)
| Column Name | Type | Description |
| :--- | :--- | :--- |
| `review_id` | `TEXT` (PK, FK) | Reference to `play_store_reviews`. |
| `sentiment` | `TEXT` | `'positive'`, `'neutral'`, or `'negative'`. |
| `themes` | `JSONB` | Array of strings (e.g., `["music_discovery"]`). |
| `frustrations` | `JSONB` | Array of strings (e.g., `["ai_slop_content"]`). |
| `jobs_to_be_done` | `JSONB` | Array of user goal statements. |
| `user_segment` | `TEXT` | Identified listener cohort. |
| `listening_behavior`| `TEXT` | User's listening habit category. |
| `summary` | `TEXT` | Concise 1-sentence summary. |
| `analyzed_at` | `TIMESTAMP` | Analysis creation timestamp. |

---

## ⚙️ Setup & Installation

### 1. Prerequisites
- **Python 3.10+**
- **PostgreSQL** (with `pgvector` extension installed)
- **n8n** (optional, for automation)

### 2. Install Dependencies
Create a virtual environment and install the required Python packages:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory and configure the variables:
```env
# Gemini API Keys
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_API_KEY=your_gemini_api_key_here

# Local PostgreSQL Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=spotify_voc
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

---

## 🚀 Running the CLI Pipeline

The `cli.py` entry point manages the lifecycle of the data collection and analysis:

```bash
# 🛠️ Setup database schemas and extensions
python cli.py setup-db

# 🕷️ Scrape reviews (e.g. 1000 reviews from India)
python cli.py scrape --count 1000 --country in

# 🧠 Enrich scraped reviews using Gemini AI analysis
python cli.py enrich --limit 1000 --batch-size 50

# 🔢 Generate embeddings for semantic vector search
python cli.py embed --limit 1000

# 📊 Refresh daily stats and aggregations
python cli.py update-stats

# 🤖 Query the Research Agent for synthesis reports
python cli.py ask -q "Why do users struggle to discover new music?"
```

---

## 🎛️ n8n Integration

The workflow defined in [n8n/workflows/spotify_pipeline.json](file:///Users/likhityadav/Documents/NL-%20Spotify/n8n/workflows/spotify_pipeline.json) automates running the ingestion tasks on a schedule and maps Postgres results to Google Sheets. 

Ensure your n8n workspace has access to the PostgreSQL database and a connected Google Sheets API integration.
