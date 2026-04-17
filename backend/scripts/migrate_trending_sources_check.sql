-- Pre-migration DDL required before running migrate_numeric_slugs.py.
--
-- Run this in the Supabase Dashboard → SQL Editor once.
-- Safe to re-run; all statements are idempotent.

-- 1. Add old_slug column for legacy URL redirects.
ALTER TABLE articles ADD COLUMN IF NOT EXISTS old_slug TEXT;

-- Lookup index on old_slug (used by middleware for 301 redirects).
CREATE INDEX IF NOT EXISTS idx_articles_old_slug
  ON articles(old_slug) WHERE old_slug IS NOT NULL;

-- 2. Relax trending_sources.source CHECK constraint.
-- Old enum blocked dynamic source values (reddit_<sub>, naver_news,
-- sbs_*, hankyung_*, etnews_*, arstechnica, google_news (<publisher>), ...).
-- New rule: source is non-empty free-form text, capped at 100 chars.
ALTER TABLE trending_sources
  DROP CONSTRAINT IF EXISTS trending_sources_source_check;

ALTER TABLE trending_sources
  ADD CONSTRAINT trending_sources_source_check
  CHECK (char_length(source) BETWEEN 1 AND 100);
