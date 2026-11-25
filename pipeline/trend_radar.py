#!/usr/bin/env python3
"""Trend Radar: classify, de-duplicate, score and store candidate topics.

Discovery itself is done by Claude in the scheduled run (web search over news from the last 7 days),
because the run's sandbox cannot reach news sites or RSS feeds directly. Claude writes what it found
to a JSON file and this script does the rest, the same way every day.

Candidate file: a JSON list of objects
  {"title": "...", "project": "Bishoftu International Airport", "summary": "...",
   "url": "https://...", "news_date": "2026-11-24", "region": "Africa"}

CLI:
  trend_radar.py add CANDIDATES.json     classify, de-duplicate, score, save; prints what happened
  trend_radar.py top [N]                 best unused topics (status new), highest score first
  trend_radar.py select SLUG             mark a topic as selected for production
  trend_radar.py seed-published FILE     record already-made videos so they are never repeated
"""
import json, os, re, sys
from datetime import date, datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "db"))
import store  # noqa: E402

CFG = json.load(open(os.path.join(os.path.dirname(__file__), "config", "categories.json")))
STOP = set("""a an the of in on at to for and or with from by is are was were be been its it this that new
africa african africas world worlds biggest largest first project projects megaproject mega built build builds
how why what just now into over after up out than more most has have had will can""".split())
DUP_THRESHOLD = 0.5


def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:60]


def tokens(s):
    words = re.findall(r"[a-z0-9]+", (s or "").lower().replace("'s", ""))
    return {w for w in words if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def classify(text):
    text = " " + text.lower() + " "
    best, best_hits = None, 0
    for c in CFG["categories"]:
        if not c["enabled"]:
            continue
        hits = sum(1 for k in c["keywords"] if re.search(r"\b" + re.escape(k) + r"\b", text))
        if hits > best_hits:
            best, best_hits = c, hits
    return best


def domain_of(url):
    d = urlparse(url or "").netloc.lower()
    return d[4:] if d.startswith("www.") else d


def trusted(dom):
    return any(dom == t or dom.endswith("." + t) or (t == "gov" and (".gov" in dom)) for t in CFG["trusted_domains"])


def score(c, cat, today):
    text = f"{c.get('title', '')} {c.get('summary', '')}"
    detail = {}
    try:
        age = (today - datetime.strptime(c.get("news_date", ""), "%Y-%m-%d").date()).days
    except ValueError:
        age = 30
    detail["freshness"] = max(0, 30 - 4 * max(0, age))                       # 30 today, 0 after a week
    mag = 0
    if re.search(r"(\$|€|£|usd)\s?\d|billion|bn\b", text, re.I):
        mag += 12
    if re.search(r"\d[\d,.]*\s?(km|mw|gw|m\b|metres|meters|teu|tonnes|million)", text, re.I):
        mag += 7
    if re.search(r"largest|biggest|tallest|longest|record|fastest|\bfirst\b(?! phase| stage| section| lot)", text, re.I):
        mag += 6
    detail["magnitude"] = min(25, mag)
    detail["africa"] = 15 if (c.get("region", "").lower() == "africa") else 5
    detail["category"] = cat["weight"] if cat else 0
    detail["source"] = 15 if trusted(domain_of(c.get("url"))) else 5
    return sum(detail.values()), detail


def find_duplicate(con, c):
    """Return (duplicate_slug, possible_duplicate_slug).

    Same project name, or project words overlapping by 75 % or more, is a duplicate. An overlap of
    50-75 % (e.g. 'Dangote Lamu Refinery' vs 'Dangote Refinery') is only flagged, because a new
    place name usually means a different project; Claude decides those by reading the summary."""
    proj = (c.get("project") or "").strip().lower()
    cand = tokens(c.get("project") or c.get("title"))
    possible, best = None, 0.0
    for r in con.execute("SELECT slug, title, project FROM topics WHERE status != 'duplicate'"):
        if proj and r["project"] and proj == r["project"].strip().lower():
            return r["slug"], None
        j = jaccard(cand, tokens(r["project"] or r["title"]))
        if j >= 0.75:
            return r["slug"], None
        if j >= DUP_THRESHOLD and j > best:
            possible, best = r["slug"], j
    return None, possible


def banned(text):
    t = text.lower()
    return next((b for b in CFG["banned_topics"] if b in t), None)


def cmd_add(path):
    con = store.connect()
    store.sync_categories(con, CFG)
    today = date.today()
    added = []
    for c in json.load(open(path)):
        title = c["title"].strip()
        slug = slugify(c.get("project") or title)
        text = f"{title} {c.get('summary', '')} {c.get('project', '')}"
        cat = classify(text)
        dup, possible = find_duplicate(con, c)
        bad = banned(text)
        s, detail = score(c, cat, today)
        if possible:
            detail["possible_duplicate_of"] = possible
            detail["penalty"] = -15
            s -= 15
        status = "duplicate" if dup else "rejected" if (bad or cat is None) else "new"
        if status == "rejected":
            detail["reason"] = f"banned topic: {bad}" if bad else "no enabled category matched"
        if con.execute("SELECT 1 FROM topics WHERE slug=?", (slug,)).fetchone():
            status, dup = "duplicate", slug
            slug = f"{slug}-{today:%Y%m%d}"
            if con.execute("SELECT 1 FROM topics WHERE slug=?", (slug,)).fetchone():
                continue
        con.execute("""INSERT INTO topics (slug,title,project,summary,category_id,region,news_date,source_url,score,score_detail,
                       status,duplicate_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (slug, title, c.get("project"), c.get("summary"), cat["id"] if cat else None, c.get("region"),
                     c.get("news_date"), c.get("url"), s, json.dumps(detail), status, dup))
        if c.get("url"):
            dom = domain_of(c["url"])
            con.execute("INSERT OR IGNORE INTO sources (url, domain, title, trusted) VALUES (?,?,?,?)",
                        (c["url"], dom, title, int(trusted(dom))))
        added.append((status, s, slug, cat["id"] if cat else "-",
                      f"same as {dup}" if dup else (f"possible duplicate of {possible}: check" if possible else "")))
    store.audit(con, "trend_radar_add", {"file": os.path.basename(path), "count": len(added)})
    con.commit()
    for status, s, slug, cat, note in sorted(added, key=lambda x: -x[1]):
        print(f"{status:9} {s:5.1f}  {cat:16} {slug}" + (f"   ({note})" if note else ""))


def cmd_top(n=5):
    con = store.connect()
    rows = con.execute("SELECT slug,title,category_id,score,news_date,source_url FROM topics WHERE status='new' "
                       "ORDER BY score DESC, news_date DESC LIMIT ?", (n,)).fetchall()
    for r in rows:
        print(json.dumps(dict(r)))
    if not rows:
        print("no unused topics: run add first")


def cmd_select(slug):
    con = store.connect()
    store.set_topic_status(con, slug, "selected")
    store.audit(con, "topic_selected", {"slug": slug})
    con.commit()
    print("selected", slug)


def cmd_seed(path):
    con = store.connect()
    store.sync_categories(con, CFG)
    n = 0
    for item in json.load(open(path)):
        slug = slugify(item.get("slug") or item.get("project") or item["title"])
        cat = classify(item["title"] + " " + item.get("project", ""))
        if not con.execute("SELECT 1 FROM topics WHERE slug=?", (slug,)).fetchone():
            con.execute("INSERT INTO topics (slug,title,project,category_id,status) VALUES (?,?,?,?,?)",
                        (slug, item["title"], item.get("project"), cat["id"] if cat else None, "published"))
            n += 1
        if item.get("youtube_id"):
            con.execute("""INSERT OR IGNORE INTO publications (topic_slug,youtube_id,url,title,privacy_status,published_at)
                           VALUES (?,?,?,?,?,?)""", (slug, item["youtube_id"], f"https://youtube.com/shorts/{item['youtube_id']}",
                                                    item["title"], "public", item.get("published_at")))
    store.audit(con, "seed_published", {"count": n})
    con.commit()
    print(f"seeded {n} published topics")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "add":
        cmd_add(a[1])
    elif a[0] == "top":
        cmd_top(int(a[1]) if len(a) > 1 else 5)
    elif a[0] == "select":
        cmd_select(a[1])
    elif a[0] == "seed-published":
        cmd_seed(a[1])
    else:
        print(__doc__)
