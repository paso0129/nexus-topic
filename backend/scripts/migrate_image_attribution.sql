-- Migration: Add image_attribution column and fix article_list_view
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
