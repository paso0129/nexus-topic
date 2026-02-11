-- Migration: Add image_attribution column and fix views
-- Run this in the Supabase SQL Editor

-- 1. Add image_attribution JSONB column to articles table
ALTER TABLE articles ADD COLUMN IF NOT EXISTS image_attribution JSONB DEFAULT '{}';

-- 2. Recreate article_list_view to include featured_image and image_attribution
CREATE OR REPLACE VIEW article_list_view AS
SELECT a.id, a.slug, a.title, a.meta_description, a.reading_time,
       a.keywords, a.created_at, a.topic, a.featured_image,
       a.image_attribution, ts.source, ts.score
FROM articles a
LEFT JOIN trending_sources ts ON a.id = ts.article_id
WHERE a.published = true
ORDER BY a.created_at DESC;

-- 3. Recreate article_detail_view to include image_attribution
--    (CREATE OR REPLACE won't work if column order changed, must DROP first)
DROP VIEW IF EXISTS article_detail_view;
CREATE VIEW article_detail_view AS
SELECT a.*, json_build_object('keyword', ts.keyword, 'source', ts.source, 'score', ts.score, 'region', ts.region, 'url', ts.url, 'timestamp', ts.timestamp) as source_data
FROM articles a
LEFT JOIN trending_sources ts ON a.id = ts.article_id
WHERE a.published = true;
