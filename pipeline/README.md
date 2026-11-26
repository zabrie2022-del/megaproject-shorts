# Mega Africa Builds: automated Shorts pipeline

> **Owner's standing instructions (night of 25 Nov 2026, these replace the morning rule):**
> choose the best option without asking, make the videos and publish them after QC. Real or AI-generated
> footage only when a connected app gives it free and without a watermark; otherwise the pipeline's drawn
> graphics are the standard (`require_real_footage: false`). Never use watermarking tools or paid plans.
> The Bishoftu Short from 25 Nov was rejected by the owner and must never be uploaded.

This folder turns the channel into a daily, mostly automatic production line that runs in Claude
scheduled tasks in the cloud, so it keeps working when the owner's laptop is off. It costs nothing to run
(open-source TTS, generated graphics and music, SQLite in this repo, Windsor.ai for YouTube).

```
Claude web search ─► data/candidates/DATE.json ─► trend_radar.py (classify, de-duplicate, score, store)
      │                                                       │ top topic
      ▼                                                       ▼
fact-check (2+ sources per claim) ─► data/specs/SLUG.json (script, storyboard, metadata, sources)
      ▼
produce.py (Kokoro voice, captions from the audio, drawn graphics, original music, -14 LUFS)
      ▼
qc.py (26 gates) ── fail ─► review_queue, stop, tell the owner
      │ pass
      ▼
git push videos/SLUG.mp4 ─► Windsor upload_video (PRIVATE) ─► owner replies "publish" ─► update_video_details public
      ▼
store.py records every step in data/media_company.db; weekly analytics snapshots feed topic choice
```

## Daily run (what the scheduled task does)

```bash
git clone --depth 1 https://github.com/zabrie2022-del/megaproject-shorts && cd megaproject-shorts
bash pipeline/setup.sh
# 1. Claude searches the web for megaproject news from the last 7 days and writes data/candidates/YYYY-MM-DD.json
python3 pipeline/trend_radar.py add data/candidates/YYYY-MM-DD.json
python3 pipeline/trend_radar.py top 5          # pick one; read "possible duplicate" notes
python3 pipeline/trend_radar.py select SLUG
# 2. Claude opens the sources, verifies every number, writes data/specs/SLUG.json (see the Bishoftu spec)
python3 pipeline/produce.py data/specs/SLUG.json /tmp/out --preview   # look at the contact sheet
python3 pipeline/produce.py data/specs/SLUG.json /tmp/out
python3 pipeline/qc.py data/specs/SLUG.json /tmp/out                  # must print PASSED
mkdir -p videos && cp /tmp/out/SLUG.mp4 /tmp/out/SLUG.srt videos/
git add -A && git commit -m "SLUG Short" && git push
# 3. Windsor upload_video with video_url = https://raw.githubusercontent.com/zabrie2022-del/megaproject-shorts/<SHA>/videos/SLUG.mp4
#    privacy_status private, made_for_kids false, category_id 27, title/description/tags from the spec
python3 pipeline/db/store.py publish SLUG VIDEO_ID URL private "TITLE" && git commit -am "record upload" && git push
# 4. After the owner replies "publish": Windsor update_video_details privacy_status public, then
python3 pipeline/db/store.py privacy VIDEO_ID public && git commit -am "published SLUG" && git push
```

## Spec rules

- Numbers on screen and in `say` are digits ($12.5 billion, 84.5 million, 2030); `produce.py` speaks them as words.
- Scene types: `hook` (big number on the first frame), `bars` (comparison, `row_cues` sync rows to the voice),
  `facts` (4 cards), `closing` (3 lines; the voice ends with "Subscribe for more megaprojects").
- Every number needs an entry in `fact_check` with sources; QC refuses unverified claims.
- `synthetic_media.disclosure_required` must be false for automatic upload. If a video shows realistic people
  or events made by AI, it goes to review: the owner ticks "altered or synthetic content" in YouTube Studio.

## Limits that are real

- The run's sandbox cannot open news sites, Wikimedia or stock-photo sites directly; Claude's web search does
  discovery and research, and visuals are drawn rather than downloaded.
- Windsor's YouTube connection is on a trial with 30 days of analytics history; uploads count against
  YouTube's daily API quota (100 uploads/day per project, far above our 1/day).
- Windsor cannot set custom thumbnails, upload caption files or set the AI-disclosure flag. Captions are burned in.

## Server mode (optional, later)

`db/schema.sql` is the PostgreSQL version of the same tables. Moving to n8n + PostgreSQL needs an always-on
server (for example a free-tier VM). Nothing in the daily run depends on it.
