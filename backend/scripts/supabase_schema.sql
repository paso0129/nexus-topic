-- NexusTopic Blog - Supabase Database Schema
-- Execute this in Supabase SQL Editor after creating your project

-- Main articles table
CREATE TABLE articles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  meta_description TEXT,
  content TEXT NOT NULL,
  keywords TEXT[] DEFAULT '{}',
  reading_time INTEGER DEFAULT 5,
  word_count INTEGER DEFAULT 0,
  topic TEXT,
  published BOOLEAN DEFAULT true,
  featured_image TEXT,
  author JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(meta_description, '') || ' ' || coalesce(topic, ''))
  ) STORED,
  CONSTRAINT valid_slug CHECK (slug ~ '^[a-z0-9-]+$'),
  CONSTRAINT positive_reading_time CHECK (reading_time > 0)
);

-- Trending sources table (separated for normalization)
CREATE TABLE trending_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('hackernews', 'reddit', 'google_trends')),
  score INTEGER DEFAULT 0,
  region TEXT DEFAULT 'US',
  url TEXT,
  timestamp TIMESTAMPTZ DEFAULT now(),
  UNIQUE(article_id)
);

-- Analytics table (future-ready)
CREATE TABLE article_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id UUID REFERENCES articles(id) ON DELETE CASCADE,
  views INTEGER DEFAULT 0,
  unique_visitors INTEGER DEFAULT 0,
  date DATE DEFAULT CURRENT_DATE,
  UNIQUE(article_id, date)
);

-- Indexes for performance
CREATE INDEX idx_articles_slug ON articles(slug);
CREATE INDEX idx_articles_published_created_at ON articles(published, created_at DESC);
CREATE INDEX idx_articles_search_vector ON articles USING GIN(search_vector);
CREATE INDEX idx_articles_keywords ON articles USING GIN(keywords);
CREATE INDEX idx_trending_sources_article_id ON trending_sources(article_id);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_articles_updated_at
  BEFORE UPDATE ON articles
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Views for optimized queries
CREATE VIEW article_list_view AS
SELECT
  a.id, a.slug, a.title, a.meta_description, a.reading_time,
  a.keywords, a.created_at, a.topic, ts.source, ts.score
FROM articles a
LEFT JOIN trending_sources ts ON a.id = ts.article_id
WHERE a.published = true
ORDER BY a.created_at DESC;

CREATE VIEW article_detail_view AS
SELECT
  a.*,
  json_build_object(
    'keyword', ts.keyword, 'source', ts.source, 'score', ts.score,
    'region', ts.region, 'url', ts.url, 'timestamp', ts.timestamp
  ) as source_data
FROM articles a
LEFT JOIN trending_sources ts ON a.id = ts.article_id
WHERE a.published = true;

-- Row Level Security
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE trending_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read published articles"
  ON articles FOR SELECT
  USING (published = true);

CREATE POLICY "Service role full access"
  ON articles FOR ALL
  USING (auth.role() = 'service_role');

CREATE POLICY "Public read sources"
  ON trending_sources FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM articles
    WHERE articles.id = trending_sources.article_id
    AND articles.published = true
  ));

CREATE POLICY "Service role sources access"
  ON trending_sources FOR ALL
  USING (auth.role() = 'service_role');
