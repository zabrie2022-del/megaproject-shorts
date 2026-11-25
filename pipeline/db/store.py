#!/usr/bin/env python3
"""SQLite store with the same tables as schema.sql (PostgreSQL), so the pipeline runs without a server.

The database file lives in the repo (data/media_company.db) and is committed after each run, which
keeps the history when the laptop is off and every run starts in a fresh cloud session.

CLI:
  store.py init
  store.py publish SLUG YOUTUBE_ID URL PRIVACY "TITLE"      record an upload (status from YouTube's answer)
  store.py privacy YOUTUBE_ID public|private|unlisted       record a privacy change
  store.py review SLUG "REASON"                             send an item to the review queue
  store.py published                                        list recorded uploads
  store.py queue                                            list open review items
  store.py snapshot YOUTUBE_ID DATE VIEWS ENGAGED AVGPCT LIKES SUBS
"""
import json, os, sqlite3, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB = os.environ.get("MEDIA_DB", os.path.join(ROOT, "data", "media_company.db"))

DDL = """
CREATE TABLE IF NOT EXISTS categories (id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  weight INTEGER NOT NULL DEFAULT 10, rules TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE, domain TEXT NOT NULL,
  title TEXT, trusted INTEGER NOT NULL DEFAULT 0, fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
  project TEXT, summary TEXT, category_id TEXT, region TEXT, news_date TEXT, source_url TEXT, score REAL,
  score_detail TEXT, status TEXT NOT NULL DEFAULT 'new', duplicate_of TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS scripts (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  spec TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (topic_slug, version));
CREATE TABLE IF NOT EXISTS assets (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT NOT NULL, kind TEXT NOT NULL,
  path TEXT NOT NULL, origin TEXT NOT NULL, license TEXT NOT NULL, attribution TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS production_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT NOT NULL, stage TEXT NOT NULL,
  status TEXT NOT NULL, detail TEXT, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT);
CREATE TABLE IF NOT EXISTS qc_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT NOT NULL, passed INTEGER NOT NULL,
  checks TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS review_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT NOT NULL, reason TEXT NOT NULL,
  resolved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS publications (id INTEGER PRIMARY KEY AUTOINCREMENT, topic_slug TEXT, youtube_id TEXT UNIQUE, url TEXT,
  title TEXT NOT NULL, format TEXT NOT NULL DEFAULT 'short', privacy_status TEXT NOT NULL, uploaded_at TEXT, published_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS analytics_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, youtube_id TEXT NOT NULL, snapshot_date TEXT NOT NULL,
  views INTEGER, engaged_views INTEGER, avg_view_pct REAL, likes INTEGER, subscribers_gained INTEGER, UNIQUE (youtube_id, snapshot_date));
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    return con


def audit(con, action, detail=None, actor="claude"):
    con.execute("INSERT INTO audit_log (actor, action, detail) VALUES (?,?,?)",
                (actor, action, json.dumps(detail) if detail is not None else None))


def sync_categories(con, cfg):
    for c in cfg["categories"]:
        con.execute("""INSERT INTO categories (id,name,enabled,weight,rules) VALUES (?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET name=excluded.name, enabled=excluded.enabled,
                       weight=excluded.weight, rules=excluded.rules""",
                    (c["id"], c["name"], int(c["enabled"]), c["weight"], c["rules"]))


def ensure_topic(con, slug, title, **kw):
    row = con.execute("SELECT slug FROM topics WHERE slug=?", (slug,)).fetchone()
    if row is None:
        con.execute("INSERT INTO topics (slug,title,project,category_id,status) VALUES (?,?,?,?,?)",
                    (slug, title, kw.get("project"), kw.get("category_id"), kw.get("status", "produced")))


def set_topic_status(con, slug, status):
    con.execute("UPDATE topics SET status=?, updated_at=? WHERE slug=?", (status, now(), slug))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    con = connect()
    if cmd == "init":
        cfg = json.load(open(os.path.join(ROOT, "pipeline", "config", "categories.json")))
        sync_categories(con, cfg)
        audit(con, "init")
        print("database ready:", DB)
    elif cmd == "publish":
        slug, yid, url, privacy, title = args[:5]
        ensure_topic(con, slug, title)
        con.execute("""INSERT INTO publications (topic_slug,youtube_id,url,title,privacy_status,uploaded_at,published_at)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(youtube_id) DO UPDATE SET privacy_status=excluded.privacy_status""",
                    (slug, yid, url, title, privacy, now(), now() if privacy == "public" else None))
        set_topic_status(con, slug, "published" if privacy == "public" else "produced")
        audit(con, "upload", {"slug": slug, "youtube_id": yid, "privacy": privacy})
        print("recorded", yid, privacy)
    elif cmd == "privacy":
        yid, privacy = args[:2]
        con.execute("UPDATE publications SET privacy_status=?, published_at=CASE WHEN ?='public' THEN ? ELSE published_at END "
                    "WHERE youtube_id=?", (privacy, privacy, now(), yid))
        row = con.execute("SELECT topic_slug FROM publications WHERE youtube_id=?", (yid,)).fetchone()
        if row and privacy == "public":
            set_topic_status(con, row["topic_slug"], "published")
        audit(con, "privacy_change", {"youtube_id": yid, "privacy": privacy}, actor="owner-approved")
        print("updated", yid, privacy)
    elif cmd == "review":
        slug, reason = args[:2]
        con.execute("INSERT INTO review_queue (topic_slug, reason) VALUES (?,?)", (slug, reason))
        set_topic_status(con, slug, "review")
        audit(con, "review_queue", {"slug": slug, "reason": reason})
        print("queued for review:", slug)
    elif cmd == "published":
        for r in con.execute("SELECT topic_slug,youtube_id,privacy_status,title,uploaded_at FROM publications ORDER BY id"):
            print(dict(r))
    elif cmd == "queue":
        for r in con.execute("SELECT id,topic_slug,reason,created_at FROM review_queue WHERE resolved=0"):
            print(dict(r))
    elif cmd == "snapshot":
        yid, d, views, eng, avg, likes, subs = args[:7]
        con.execute("""INSERT INTO analytics_snapshots (youtube_id,snapshot_date,views,engaged_views,avg_view_pct,likes,subscribers_gained)
                       VALUES (?,?,?,?,?,?,?) ON CONFLICT(youtube_id,snapshot_date) DO UPDATE SET views=excluded.views,
                       engaged_views=excluded.engaged_views, avg_view_pct=excluded.avg_view_pct, likes=excluded.likes,
                       subscribers_gained=excluded.subscribers_gained""",
                    (yid, d, int(float(views)), int(float(eng)), float(avg or 0), int(float(likes)), int(float(subs))))
        print("snapshot saved", yid, d)
    else:
        print(__doc__)
        return 1
    con.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
