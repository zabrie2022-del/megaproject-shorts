-- PostgreSQL schema for the AI YouTube media company (server mode).
-- The daily pipeline currently runs in Claude scheduled tasks with the same tables in SQLite
-- (pipeline/db/store.py, file data/media_company.db). Load this file into PostgreSQL when the
-- system moves to a server:  psql "$DATABASE_URL" -f pipeline/db/schema.sql

CREATE TABLE IF NOT EXISTS categories (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    weight      INTEGER NOT NULL DEFAULT 10,
    rules       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,
    domain      TEXT NOT NULL,
    title       TEXT,
    trusted     BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS topics (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    project       TEXT,
    summary       TEXT,
    category_id   TEXT REFERENCES categories(id),
    region        TEXT,
    news_date     DATE,
    source_url    TEXT,
    score         NUMERIC(5,1),
    score_detail  JSONB,
    status        TEXT NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','selected','duplicate','rejected','produced','published','review')),
    duplicate_of  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS topics_status_score ON topics (status, score DESC);

CREATE TABLE IF NOT EXISTS scripts (
    id           BIGSERIAL PRIMARY KEY,
    topic_slug   TEXT NOT NULL REFERENCES topics(slug),
    version      INTEGER NOT NULL DEFAULT 1,
    spec         JSONB NOT NULL,          -- script, storyboard, fact-check, sources, metadata
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (topic_slug, version)
);

CREATE TABLE IF NOT EXISTS assets (
    id           BIGSERIAL PRIMARY KEY,
    topic_slug   TEXT NOT NULL REFERENCES topics(slug),
    kind         TEXT NOT NULL CHECK (kind IN ('video','audio','music','image','thumbnail','captions','other')),
    path         TEXT NOT NULL,
    origin       TEXT NOT NULL,           -- 'generated' or the source URL
    license      TEXT NOT NULL,           -- e.g. 'original (generated)', 'CC BY-SA 4.0'
    attribution  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS production_jobs (
    id           BIGSERIAL PRIMARY KEY,
    topic_slug   TEXT NOT NULL REFERENCES topics(slug),
    stage        TEXT NOT NULL,           -- research, script, render, qc, upload, publish
    status       TEXT NOT NULL CHECK (status IN ('running','ok','failed')),
    detail       JSONB,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS qc_reports (
    id           BIGSERIAL PRIMARY KEY,
    topic_slug   TEXT NOT NULL REFERENCES topics(slug),
    passed       BOOLEAN NOT NULL,
    checks       JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_queue (
    id           BIGSERIAL PRIMARY KEY,
    topic_slug   TEXT NOT NULL REFERENCES topics(slug),
    reason       TEXT NOT NULL,
    resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS publications (
    id             BIGSERIAL PRIMARY KEY,
    topic_slug     TEXT REFERENCES topics(slug),
    youtube_id     TEXT UNIQUE,
    url            TEXT,
    title          TEXT NOT NULL,
    format         TEXT NOT NULL DEFAULT 'short' CHECK (format IN ('short','long')),
    privacy_status TEXT NOT NULL,
    uploaded_at    TIMESTAMPTZ,
    published_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id                BIGSERIAL PRIMARY KEY,
    youtube_id        TEXT NOT NULL,
    snapshot_date     DATE NOT NULL,
    views             INTEGER,
    engaged_views     INTEGER,
    avg_view_pct      NUMERIC(7,2),
    likes             INTEGER,
    subscribers_gained INTEGER,
    UNIQUE (youtube_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor       TEXT NOT NULL,            -- 'scheduled-task', 'owner', 'claude'
    action      TEXT NOT NULL,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
