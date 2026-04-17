-- Add indexing tracking column to articles.
-- Run once in Supabase SQL Editor.
--
-- NULL      → not yet submitted or last attempt failed → eligible for next cron
-- Timestamp → successfully submitted to Google Indexing API at that time

ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS indexing_submitted_at TIMESTAMPTZ;

-- Partial index: queries only target rows with NULL value (pending).
CREATE INDEX IF NOT EXISTS idx_articles_indexing_pending
  ON articles(created_at DESC)
  WHERE indexing_submitted_at IS NULL AND published = true;
