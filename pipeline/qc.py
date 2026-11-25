#!/usr/bin/env python3
"""Quality gates before anything is uploaded.

Usage: qc.py SPEC.json OUT_DIR
Exit code 0 = every check passed. Exit code 1 = at least one failed: the item is recorded in the
review queue and must not be uploaded. The report is written to data/qc/SLUG.json and to the database.
"""
import json, os, re, subprocess, sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "db"))
import store  # noqa: E402

CH = json.load(open(os.path.join(HERE, "config", "channel.json")))
CATS = json.load(open(os.path.join(HERE, "config", "categories.json")))


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def loudness(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    return (float(i[-1]) if i else None), (float(tp[-1]) if tp else None)


def long_silences(path, end, min_len=1.2):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", f"silencedetect=noise=-42dB:d={min_len}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    return [s for s in starts if s < end - 1.5]       # silence in the last 1.5 s is the ending hold


def domain(u):
    d = urlparse(u).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    slug = spec["slug"]
    info = json.load(open(os.path.join(out, f"{slug}.render.json")))
    video = info["files"]["video"]
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    # 1-3 technical
    p = probe(video)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    dur = float(p["format"]["duration"])
    size_mb = int(p["format"]["size"]) / 1e6
    sh = CH["short"]
    check("resolution 1080x1920 (9:16)", v.get("width") == sh["width"] and v.get("height") == sh["height"],
          f"{v.get('width')}x{v.get('height')}")
    check("frame rate 30 fps", v.get("r_frame_rate") == "30/1", v.get("r_frame_rate", ""))
    check(f"duration {sh['min_seconds']}-{sh['max_seconds']} s", sh["min_seconds"] <= dur <= sh["max_seconds"], f"{dur:.1f} s")
    check("file under 100 MB (upload limit)", size_mb < 100, f"{size_mb:.1f} MB")
    check("audio stream present (AAC)", a is not None and a.get("codec_name") == "aac", a.get("codec_name") if a else "none")
    lufs, peak = loudness(video)
    check("loudness -17 to -11 LUFS", lufs is not None and -17 <= lufs <= -11, f"{lufs} LUFS")
    check("true peak at or below -1 dBFS", peak is not None and peak <= -0.9, f"{peak} dBFS")
    gaps = long_silences(video, dur)
    check("no silent gaps in the narration", not gaps, f"silence at {gaps}" if gaps else "")

    # 4 captions
    cues = info["cues"]
    ok = bool(cues) and all(c["start"] < c["end"] for c in cues) and \
        all(cues[i]["end"] <= cues[i + 1]["start"] + 1e-3 for i in range(len(cues) - 1)) and cues[-1]["end"] <= dur + 0.05
    check("captions in order, inside the video, not overlapping", ok, f"{len(cues)} cues")
    inside = all(any(s["start"] <= c["start"] and c["end"] <= s["end"] + 1e-3 for s in info["scenes"]) for c in cues)
    check("every caption sits inside its scene's narration", inside)
    check("captions file written", os.path.exists(info["files"]["captions"]))

    # 5 metadata
    t = spec.get("title", "")
    check("title 20-70 characters", 20 <= len(t) <= 70, f"{len(t)} chars")
    d = spec.get("description", "")
    check("description has text, sources and the AI-voice note",
          len(d) >= 150 and "http" in d and "AI-generated" in d, f"{len(d)} chars")
    check("3-15 tags", 3 <= len(spec.get("tags", [])) <= 15, f"{len(spec.get('tags', []))} tags")
    check("thumbnail (first frame) made", os.path.exists(info["files"]["thumbnail"]))
    hook = spec["scenes"][0]
    check("hook on the first frame", hook["type"] == "hook" and bool(hook.get("big")) and bool(hook.get("headline")))
    check("closing asks to subscribe", "subscribe" in spec["scenes"][-1]["say"].lower())

    # 6 facts and sources
    fc = spec.get("fact_check", [])
    unverified = [f["claim"] for f in fc if not f.get("verified") or not f.get("sources")]
    check("every claim verified with a source", fc and not unverified, "; ".join(unverified))
    doms = {domain(u) for f in fc for u in f.get("sources", [])}
    check("at least 3 different source websites", len(doms) >= 3, ", ".join(sorted(doms)))
    numbers = set(re.findall(r"\d[\d.,]*", " ".join(json.dumps(s) for s in spec["scenes"] if s["type"] != "closing")))
    check("claims listed for the on-screen numbers", len(fc) >= min(len(numbers), 5), f"{len(fc)} claims, {len(numbers)} numbers")

    # 7 real footage (owner's rule) and licensing
    if CH.get("require_real_footage"):
        real = [m for m in spec.get("media", []) if m.get("kind") in ("video", "photo") and m.get("real")
                and m.get("license") and m.get("source")]
        check("shows real footage or photos (owner's rule)", len(real) >= 3,
              f"{len(real)} licensed real clips/photos; at least 3 needed, graphics-only videos are not allowed")
    bad = [x for x in spec.get("assets", []) + info["assets"] if not x.get("license") or not x.get("origin")]
    check("every media asset has an origin and licence", not bad, json.dumps(bad) if bad else "all generated in-house")

    # 8 duplicates
    con = store.connect()
    dup = con.execute("SELECT youtube_id FROM publications WHERE topic_slug=? OR lower(title)=lower(?)", (slug, t)).fetchone()
    check("not already uploaded", dup is None, dup["youtube_id"] if dup else "")

    # 9 policy
    text = (t + " " + d + " " + json.dumps(spec["scenes"])).lower()
    hit = [b for b in CATS["banned_topics"] if b in text]
    check("no banned topics (investment tips, gambling, crypto)", not hit, ", ".join(hit))
    check("not made for kids flag set", CH["upload_defaults"]["made_for_kids"] is False)

    # 10 synthetic media
    sm = spec.get("synthetic_media", {})
    check("synthetic-media decision recorded", "disclosure_required" in sm, sm.get("reason", ""))
    check("no YouTube AI disclosure needed (the upload tool cannot set it)", sm.get("disclosure_required") is False,
          "set 'altered or synthetic content' in YouTube Studio by hand" if sm.get("disclosure_required") else "")

    passed = all(c["passed"] for c in checks)
    report = {"slug": slug, "passed": passed, "checks": checks}
    os.makedirs(os.path.join(ROOT, "data", "qc"), exist_ok=True)
    json.dump(report, open(os.path.join(ROOT, "data", "qc", f"{slug}.json"), "w"), indent=1)
    store.ensure_topic(con, slug, t, project=spec.get("project"), category_id=spec.get("category"), status="produced")
    con.execute("INSERT INTO qc_reports (topic_slug, passed, checks) VALUES (?,?,?)", (slug, int(passed), json.dumps(checks)))
    con.execute("INSERT OR IGNORE INTO scripts (topic_slug, version, spec) VALUES (?,?,?)", (slug, 1, json.dumps(spec)))
    for x in info["assets"]:
        con.execute("INSERT INTO assets (topic_slug, kind, path, origin, license) VALUES (?,?,?,?,?)",
                    (slug, x["kind"], video, x["origin"], x["license"]))
    if not passed:
        failed = [c["check"] for c in checks if not c["passed"]]
        con.execute("INSERT INTO review_queue (topic_slug, reason) VALUES (?,?)", (slug, "QC failed: " + "; ".join(failed)))
        store.set_topic_status(con, slug, "review")
    else:
        store.set_topic_status(con, slug, "produced")
    store.audit(con, "qc", {"slug": slug, "passed": passed})
    con.commit()
    for c in checks:
        print(("PASS " if c["passed"] else "FAIL ") + c["check"] + (f"  [{c['detail']}]" if c["detail"] else ""))
    print("\nRESULT:", "PASSED - ready to upload as private" if passed else "FAILED - sent to the review queue, do not upload")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
