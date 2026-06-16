# architecture.md

# AI-Powered Music Discovery Research Engine

## Project Goal

Build an AI-powered Voice-of-Customer (VoC) intelligence platform that analyzes large volumes of user feedback to answer questions such as:

* Why do users struggle to discover new music?
* What are the biggest frustrations with recommendation systems?
* What listening behaviors are users trying to achieve?
* Why do users repeatedly listen to the same content?
* Which user segments experience different discovery challenges?
* What unmet needs consistently emerge across feedback?

The system must support:

* Retrieval-Augmented Generation (RAG)
* SQL-based analytics
* Python-based analytics
* AI-driven theme extraction
* User segmentation
* JTBD (Jobs-To-Be-Done) extraction
* Future multi-source expansion

---

# Guiding Principles

1. Database First
2. AI as an enrichment layer, not the primary datastore
3. SQL + Analytics before LLM reasoning
4. Incremental processing only
5. Cost-aware architecture
6. Start with a single source and expand gradually
7. Preserve raw data forever

---

# Phase 1 Scope

Initial source:

* Spotify Play Store Reviews

Future sources:

* Apple Music Play Store Reviews
* App Store Reviews
* Spotify Community
* Reddit
* Other Music Communities

---

# High-Level Architecture

```text
                    ┌────────────────────┐
                    │    Data Sources     │
                    └──────────┬─────────┘
                               │
                               ▼

                    ┌────────────────────┐
                    │       n8n          │
                    │ Orchestration Layer │
                    └──────────┬─────────┘
                               │
                               ▼

                    ┌────────────────────┐
                    │    PostgreSQL      │
                    │ Source of Truth    │
                    └──────────┬─────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼

 ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
 │ AI Enrichment  │  │ SQL Analytics  │  │ Python Analysis│
 └────────────────┘  └────────────────┘  └────────────────┘

                               │
                               ▼

                    ┌────────────────────┐
                    │      pgvector      │
                    │ Vector Retrieval   │
                    └──────────┬─────────┘
                               │
                               ▼

                    ┌────────────────────┐
                    │ Antigravity Agent  │
                    └────────────────────┘
```

---

# System Components

## Data Collection Layer

### Responsibilities

* Collect reviews
* Validate records
* Normalize fields
* Store raw records
* Prevent duplicate ingestion

### Current Source

* Spotify Play Store Reviews

### Future Sources

* Apple Music Reviews
* Spotify Community
* Reddit
* Forums

---

## Orchestration Layer

Technology:

* n8n

Responsibilities:

* Schedule collection jobs
* Trigger enrichment jobs
* Trigger embedding jobs
* Monitor failures
* Retry failed jobs

n8n should not contain business logic.

---

# Database Design

PostgreSQL is the source of truth.

---

## Table: play_store_reviews

Stores raw review data.

```sql
CREATE TABLE play_store_reviews (
    review_id TEXT PRIMARY KEY,

    app_name TEXT,

    review_text TEXT,

    rating INTEGER,

    thumbs_up INTEGER,

    review_date TIMESTAMP,

    app_version TEXT,

    source TEXT DEFAULT 'play_store',

    inserted_at TIMESTAMP DEFAULT NOW()
);
```

Example:

```json
{
  "review_id": "abc123",
  "app_name": "Spotify",
  "review_text": "Recommendations keep repeating the same artists",
  "rating": 2,
  "thumbs_up": 15
}
```

---

## Table: review_analysis

Stores AI-generated enrichments.

```sql
CREATE TABLE review_analysis (

    review_id TEXT PRIMARY KEY,

    sentiment TEXT,

    themes JSONB,

    frustrations JSONB,

    jobs_to_be_done JSONB,

    user_segment TEXT,

    listening_behavior TEXT,

    summary TEXT,

    analyzed_at TIMESTAMP DEFAULT NOW()
);
```

Example:

```json
{
  "sentiment": "negative",
  "themes": [
    "music_discovery",
    "recommendations"
  ],
  "frustrations": [
    "repetitive_recommendations"
  ],
  "jobs_to_be_done": [
    "discover_new_artists"
  ],
  "user_segment": "music_explorer",
  "listening_behavior": "active_discovery"
}
```

---

## Table: review_embeddings

Stores vector embeddings.

```sql
CREATE TABLE review_embeddings (
    review_id TEXT PRIMARY KEY,
    embedding VECTOR(1536)
);
```

---

## Table: query_cache

Stores cached agent responses.

```sql
CREATE TABLE query_cache (
    query_hash TEXT PRIMARY KEY,
    response TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Future Tables

```sql
app_store_reviews

spotify_community_threads

spotify_community_replies

reddit_posts

reddit_comments
```

Do not merge sources initially.

Maintain source-specific tables.

---

# AI Enrichment Pipeline

Purpose:

Convert raw reviews into structured intelligence.

Workflow:

```text
Review
   ↓
AI Enrichment
   ↓
Store Results
```

Generated fields:

* Sentiment
* Themes
* Frustrations
* JTBD
* User Segment
* Listening Behavior
* Summary

---

# Analysis Taxonomy

Every review should be classified across these dimensions.

---

## Sentiment

Values:

* Positive
* Neutral
* Negative

---

## Themes

Examples:

* music_discovery
* recommendations
* playlists
* personalization
* search
* exploration

---

## Frustrations

Examples:

* repetitive_recommendations
* mainstream_bias
* poor_niche_discovery
* playlist_quality
* recommendation_accuracy

---

## Jobs To Be Done

Examples:

* discover_new_artists
* explore_new_genres
* reduce_search_effort
* find_music_for_moods
* escape_repetition

---

## User Segments

Examples:

* casual_listener
* playlist_listener
* music_explorer
* genre_specialist
* heavy_listener

---

## Listening Behaviors

Examples:

* passive_listening
* active_exploration
* comfort_listening
* mood_based_listening
* social_discovery

---

# Deduplication Strategy

Purpose:

Reduce enrichment costs.

Many reviews are near-identical.

Examples:

```text
Spotify keeps recommending the same songs.

Spotify always recommends the same songs.

I get the same songs every week.
```

Pipeline:

```text
Raw Reviews
      ↓
Deduplication
      ↓
Unique Reviews
      ↓
AI Enrichment
```

Methods:

### Exact Duplicate Detection

Hash review text.

```text
SHA256(review_text)
```

### Near Duplicate Detection

Use embeddings.

Cluster highly similar reviews.

Store:

```sql
cluster_id
canonical_review_id
```

Benefits:

* Lower costs
* Cleaner analytics
* Better signal extraction

---

# Embedding Strategy

Technology:

* pgvector

---

## Embedding Source

Combine:

```text
Review Text

Themes

Frustrations

JTBD

Summary
```

Example:

```text
Review:
Recommendations keep repeating.

Themes:
music_discovery

Frustrations:
repetitive_recommendations

JTBD:
discover_new_artists
```

---

## Chunking Strategy

For reviews:

```text
One review = One chunk
```

Chunk Size:

* 300–800 tokens

---

## Metadata

Store:

```json
{
  "rating": 1,
  "theme": "music_discovery",
  "segment": "music_explorer"
}
```

Metadata should be available during retrieval.

---

# n8n Workflows

## Workflow 1: Review Collection

```text
Schedule Trigger
      ↓
Fetch Reviews
      ↓
Validate
      ↓
Deduplicate
      ↓
Store Raw Reviews
```

Frequency:

* Daily

---

## Workflow 2: AI Enrichment

```text
New Reviews
      ↓
Batch Reviews
      ↓
LLM Analysis
      ↓
Store Enrichment
```

Output:

* Sentiment
* Themes
* JTBD
* Segments
* Behaviors

---

## Workflow 3: Embeddings

```text
New Analysis
      ↓
Generate Embedding
      ↓
Store Vector
```

---

## Workflow 4: Statistics Generation

```text
Analyzed Reviews
      ↓
Aggregate
      ↓
Statistics Tables
```

Runs:

* Daily
* Weekly

---

# Analytics Layer

Supports:

* SQL
* Python
* RAG

---

## SQL Analytics

Examples:

```sql
Most common frustrations

Review trends over time

Ratings by theme

Segment distribution
```

---

## Python Analytics

Examples:

* Clustering
* Topic modeling
* Trend analysis
* Correlation analysis
* Segment analysis
* Time-series analysis

---

# Statistics Tables

Purpose:

Reduce LLM dependency.

---

## frustration_statistics_daily

```sql
date
frustration
count
```

---

## theme_statistics_daily

```sql
date
theme
count
```

---

## segment_statistics_daily

```sql
date
segment
count
```

---

# Antigravity Agent

Antigravity is the intelligence layer.

It should NOT:

* Collect data
* Manage workflows
* Store data

It should:

* Retrieve
* Analyze
* Reason
* Generate insights

---

# Agent Tools

## Tool 1: SQL Tool

Purpose:

Structured analytics.

Examples:

```sql
Count complaints

Compare ratings

Trend analysis
```

---

## Tool 2: Vector Search Tool

Purpose:

Semantic retrieval.

Examples:

```text
Find reviews about discovery problems

Find complaints about recommendations

Find unmet needs
```

---

## Tool 3: Python Tool

Purpose:

Advanced analytics.

Examples:

* clustering
* distributions
* trends
* statistical analysis

---

## Tool 4: Schema Inspection Tool

Purpose:

Allow agent to inspect database metadata.

---

# Agent Workflow

Example Question:

```text
Why do users struggle to discover new music?
```

Process:

```text
Question
    ↓
Cache Check
    ↓
SQL Analysis
    ↓
Vector Retrieval
    ↓
Python Analysis
    ↓
LLM Synthesis
    ↓
Response
```

---

# Hybrid Retrieval Strategy

Never rely on vector search alone.

Use:

```text
SQL
+
Aggregated Statistics
+
Vector Search
+
Python Analysis
+
LLM Synthesis
```

---

# Cost Optimization Strategy

## Principle 1: Analyze Once

Each review is enriched exactly once.

Workflow:

```text
Review
    ↓
Check review_analysis
    ↓
Exists?
 ├─ YES → Skip
 └─ NO  → Analyze
```

---

## Principle 2: Incremental Processing

Only process unseen reviews.

Example:

```sql
SELECT *
FROM play_store_reviews
WHERE review_id NOT IN (
    SELECT review_id
    FROM review_analysis
);
```

---

## Principle 3: Store All AI Outputs

Persist:

* sentiment
* themes
* frustrations
* JTBD
* segments
* summaries

Never regenerate unnecessarily.

---

## Principle 4: Batch Processing

Instead of:

```text
1 Review
↓
1 LLM Call
```

Use:

```text
50 Reviews
↓
1 LLM Call
```

Recommended:

* 25–100 reviews per batch

---

## Principle 5: Embedding Once

Generate embeddings only after enrichment.

Regenerate only when:

* embedding model changes
* source content changes

---

## Principle 6: Cache Agent Responses

Workflow:

```text
Question
    ↓
Cache Lookup
    ↓
Found?
 ├─ YES → Return
 └─ NO  → Execute Agent
```

---

## Principle 7: SQL Before LLM

Preferred:

```text
Question
    ↓
SQL
    ↓
Retrieval
    ↓
Python
    ↓
LLM
```

Avoid:

```text
Question
    ↓
LLM
```

---

## Principle 8: Aggregate Before Reasoning

Use statistics tables whenever possible.

Avoid retrieving thousands of reviews for common questions.

---

## Principle 9: Multi-Model Strategy

Cheap Model:

* Classification
* Tagging
* Sentiment
* Theme extraction

Premium Model:

* Final reports
* Deep synthesis
* Executive summaries

---

## Principle 10: Background Processing

Never enrich during user requests.

Use:

```text
Ingestion
↓
Queue
↓
Worker
↓
Storage
```

User queries should operate on prepared data.

---

# Example Questions Supported

The system should answer:

* Why do users struggle to discover new music?
* What recommendation frustrations occur most frequently?
* What unmet needs appear repeatedly?
* Which user segments are least satisfied?
* Why do users replay the same songs?
* Which discovery behaviors correlate with dissatisfaction?
* Which themes are increasing over time?

All answers should be grounded in:

* SQL evidence
* Statistical evidence
* Retrieved review evidence
* AI synthesis

---

# MVP Success Criteria

The system is successful when it can:

1. Ingest Play Store reviews automatically.
2. Deduplicate reviews.
3. Enrich reviews using AI.
4. Store embeddings.
5. Support SQL analysis.
6. Support Python analysis.
7. Answer research questions using RAG.
8. Produce evidence-backed insights.
9. Operate incrementally.
10. Remain cost-efficient.

---

# Technology Stack

Collection:

* Play Store Scraper/API

Orchestration:

* n8n

Database:

* PostgreSQL

Vector Storage:

* pgvector

Analytics:

* Python

Agent:

* Antigravity

LLM:

* GPT or Claude

Deployment:

* Docker

Future Dashboard:

* Metabase
* Custom React Frontend
