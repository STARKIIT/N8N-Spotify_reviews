-- Create review_analysis table to store AI-generated enrichment results
CREATE TABLE IF NOT EXISTS review_analysis (
    review_id TEXT PRIMARY KEY,
    sentiment TEXT,
    themes JSONB,
    frustrations JSONB,
    jobs_to_be_done JSONB,
    user_segment TEXT,
    listening_behavior TEXT,
    summary TEXT,
    analyzed_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_review FOREIGN KEY (review_id) REFERENCES play_store_reviews(review_id) ON DELETE CASCADE
);

-- Create daily frustration statistics aggregation table
CREATE TABLE IF NOT EXISTS frustration_statistics_daily (
    date DATE,
    frustration TEXT,
    count INTEGER,
    PRIMARY KEY (date, frustration)
);

-- Create daily theme statistics aggregation table
CREATE TABLE IF NOT EXISTS theme_statistics_daily (
    date DATE,
    theme TEXT,
    count INTEGER,
    PRIMARY KEY (date, theme)
);

-- Create daily user segment statistics aggregation table
CREATE TABLE IF NOT EXISTS segment_statistics_daily (
    date DATE,
    segment TEXT,
    count INTEGER,
    PRIMARY KEY (date, segment)
);
