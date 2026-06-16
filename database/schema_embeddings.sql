-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create review_embeddings table with 3072 dimensions (matching Gemini's gemini-embedding-2 model)
CREATE TABLE IF NOT EXISTS review_embeddings (
    review_id TEXT PRIMARY KEY,
    embedding VECTOR(3072),
    CONSTRAINT fk_review_emb FOREIGN KEY (review_id) REFERENCES play_store_reviews(review_id) ON DELETE CASCADE
);
