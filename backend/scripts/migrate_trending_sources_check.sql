-- Relax trending_sources.source CHECK constraint.
--
-- Old CHECK enumerated 26 source values; code now emits dynamic values
-- (reddit_<subreddit>, naver_news, sbs_*, hankyung_*, etnews_*, arstechnica,
-- google_news (<publisher>), etc.) which would silently fail the old rule.
--
-- New rule: source is non-empty free-form text, capped at 100 chars.
-- Run on Supabase:
--   psql $DATABASE_URL -f migrate_trending_sources_check.sql
-- Or via Supabase SQL editor.

ALTER TABLE trending_sources
  DROP CONSTRAINT IF EXISTS trending_sources_source_check;

ALTER TABLE trending_sources
  ADD CONSTRAINT trending_sources_source_check
  CHECK (char_length(source) BETWEEN 1 AND 100);
