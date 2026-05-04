-- slug_aliases: persistent legacy-slug → current article mapping
--
-- Why: 2026-03 migration overwrote `articles.old_slug` with numeric IDs,
-- losing original English slugs that GSC was still indexing. This table
-- is the safe long-term home for ALL historical slugs (English, numeric,
-- Korean, romanized) — regardless of how many migrations happen later.
--
-- Middleware reads this with the anon key to 301-redirect legacy URLs
-- instead of returning 410 Gone.

CREATE TABLE IF NOT EXISTS slug_aliases (
  alias        TEXT PRIMARY KEY,
  article_id   UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  source       TEXT NOT NULL,                       -- 'gsc', 'manual', 'migration_v1', 'migration_v2', 'auto'
  confidence   NUMERIC(3,2) NOT NULL DEFAULT 1.00,  -- 0.00–1.00 (fuzzy-match score)
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slug_aliases_article_id
  ON slug_aliases(article_id);

CREATE INDEX IF NOT EXISTS idx_slug_aliases_source
  ON slug_aliases(source);

ALTER TABLE slug_aliases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS slug_aliases_anon_read ON slug_aliases;
CREATE POLICY slug_aliases_anon_read ON slug_aliases
  FOR SELECT TO anon
  USING (true);

DROP POLICY IF EXISTS slug_aliases_service_write ON slug_aliases;
CREATE POLICY slug_aliases_service_write ON slug_aliases
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- Backfill: bring existing articles.old_slug values into slug_aliases so the
-- middleware has a single source of truth from day one.
INSERT INTO slug_aliases (alias, article_id, source, confidence)
SELECT old_slug, id, 'migration_v2', 1.00
FROM articles
WHERE old_slug IS NOT NULL
  AND old_slug <> slug
ON CONFLICT (alias) DO NOTHING;
