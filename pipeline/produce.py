#!/usr/bin/env python3
"""Render a narrated YouTube Short from a spec JSON (script + storyboard + metadata + fact-check).

Usage: produce.py SPEC.json OUT_DIR [--preview]

What it makes in OUT_DIR:
  SLUG.mp4          1080x1920 30 fps H.264 + AAC, narration + original music, burned-in captions
  SLUG.srt          the captions as a file (timed from the narration audio itself)
  SLUG_thumb.jpg    the first frame (the hook)
  SLUG.render.json  durations, scene timings and the files made, for qc.py

Narration: Kokoro TTS (open weights, runs on CPU). Each sentence is synthesised separately, its silence
trimmed, and the caption chunks are timed inside that sentence by syllable count, so captions cannot
drift by more than a sentence. Visuals are drawn here, so there is no third-party media to license.
"""
import json, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import shorts as S  # noqa: E402  (fonts, text, fit, make_bg, prog)

CH = json.load(open(os.path.join(HERE, "config", "channel.json")))
W, H, FPS = 1080, 1920, 30
SR = 24000
KOKORO = os.environ.get("KOKORO_DIR", os.path.expanduser("~/.cache/kokoro"))
GAP = 0.16            # pause between sentences
LEAD = {"hook": 0.12}  # silence before the first word of a scene (the hook speaks at once)
TAIL = 0.45           # hold after the last word of a scene
CAP_Y, CAP_MAXW = 1480, 760   # caption band: clear of the Shorts title area and the right-hand buttons


# ---------------------------------------------------------------- narration
def tts_engine():
    from kokoro_onnx import Kokoro
    model = os.path.join(KOKORO, "kokoro-v1.0.int8.onnx")
    voices = os.path.join(KOKORO, "voices-v1.0.bin")
    if not (os.path.exists(model) and os.path.exists(voices)):
        sys.exit(f"Kokoro model missing in {KOKORO}: run pipeline/setup.sh")
    return Kokoro(model, voices)


def trim(x, thr=0.012, keep=0.04):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a, b = max(0, idx[0] - int(keep * SR)), min(len(x), idx[-1] + int(keep * SR))
    return x[a:b]


UNITS = {"km": "kilometres", "MW": "megawatts", "GW": "gigawatts", "GWh": "gigawatt hours", "%": "percent",
         "bn": "billion", "m3": "cubic metres", "TEU": "containers"}


def _n(s):
    from num2words import num2words
    v = float(s.replace(",", ""))
    if abs(v - 0.5 - int(v)) < 1e-9 and v < 1000:           # 12.5 -> twelve and a half
        return f"{num2words(int(v))} and a half"
    return num2words(int(v) if v.is_integer() else v)


def _year(m):
    from num2words import num2words
    y = int(m.group(0))
    if 2000 <= y <= 2009:
        return num2words(y)
    if y % 100 == 0:
        return f"{num2words(y // 100)} hundred"
    if y % 100 < 10:
        return f"{num2words(y // 100)} oh {num2words(y % 100)}"
    return f"{num2words(y // 100)} {num2words(y % 100)}"


def spoken(s):
    """Text the narrator says: digits on screen, words in the voice ($12.5 billion -> twelve and a half billion dollars)."""
    def money(m):
        scale = UNITS.get(m.group(2), m.group(2))
        nxt = (m.group(3) or "").lower()
        # "$12.5 billion airport" -> "dollar airport"; "$12.5 billion." / "$12.5 billion in" -> "dollars"
        unit = "dollar" if nxt and nxt not in {"in", "on", "to", "a", "an", "for", "of", "and", "or", "is", "was", "will",
                                                 "per", "each", "from", "by", "with", "over", "this", "last", "since"} \
            else "dollars"
        return f"{_n(m.group(1))} {scale + ' ' if scale else ''}{unit}{(' ' + m.group(3)) if m.group(3) else ''}"
    s = re.sub(r"\$(\d[\d,]*(?:\.\d+)?)\s*(billion|million|trillion|bn)?(?:\s+([A-Za-z]+))?", money, s)
    s = re.sub(r"\b(1[89]|20)\d\d\b(?![,.]?\d)", _year, s)
    s = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s?(km|MW|GWh|GW|%|bn|m3|TEU)(?!\w)",
               lambda m: f"{_n(m.group(1))} {UNITS[m.group(2)]}", s)
    s = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: _n(m.group(0)), s)
    return s


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1 if re.search(r"\d", word) else 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def chunks(sentence, max_words=4, max_chars=24):
    out, cur = [], []
    for w in sentence.split():
        if cur and (len(cur) >= max_words or len(" ".join(cur + [w])) > max_chars):
            out.append(" ".join(cur))
            cur = []
        cur.append(w)
        if w.endswith((",", ";", ":")):          # break at a pause
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def narrate(spec, engine):
    """Return (audio float32 array, per-scene timings, caption cues)."""
    voice = spec.get("voice", CH["voice"])
    speed = spec.get("speed", CH["voice_speed"])
    audio, t, scenes, cues = [], 0.0, [], []

    def add(x):
        nonlocal t
        audio.append(x.astype(np.float32))
        t += len(x) / SR

    for sc in spec["scenes"]:
        start = t
        add(np.zeros(int(LEAD.get(sc["type"], 0.3) * SR)))
        for i, sent in enumerate(sentences(sc["say"])):
            if i:
                add(np.zeros(int(GAP * SR)))
            x, sr = engine.create(spoken(sent), voice=voice, speed=speed, lang="en-us")
            assert sr == SR, sr
            x = trim(np.asarray(x))
            s0, dur = t, len(x) / SR
            parts = chunks(sent)
            weights = [max(1, sum(syllables(w) for w in spoken(p).split())) for p in parts]
            acc = s0
            for p, wgt in zip(parts, weights):
                d = dur * wgt / sum(weights)
                cues.append({"start": round(acc, 3), "end": round(acc + d, 3), "text": p.strip(" ,;:.!")})
                acc += d
            add(x)
        add(np.zeros(int(TAIL * SR)))
        scenes.append({"type": sc["type"], "start": round(start, 3), "end": round(t, 3)})
    return np.concatenate(audio), scenes, cues


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((x * 32767).astype(np.int16).tobytes())


def srt_time(s):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


# ---------------------------------------------------------------- drawing
def num(v):
    return f"{v:,.1f}" if abs(v - round(v)) > 1e-9 else f"{int(round(v)):,}"


def header(L):
    S.text(L, CH["header"], 230, S.MED, 30, S.MUTED)


def draw_hook(st, sc, t, dur):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    header(L)
    big = sc["big"]
    size = S.fit(big, S.BOLD, 230, 960)
    pop = 1 + 0.03 * (1 - S.prog(t, 0.0, 0.4))
    S.text(L, big, 600, S.BOLD, int(size * pop), S.WHITE, 1.0)
    S.text(L, sc["headline"], 930, S.MED, S.fit(sc["headline"], S.MED, 66, 960), S.WHITE, max(0.9, S.prog(t, 0, 0.3)))
    a = max(0.85, S.prog(t, 0.0, 0.4))          # readable on the very first frame
    S.text(L, sc["sub"], 1050, S.BOLD, S.fit(sc["sub"], S.BOLD, 54, 960), st["accent"], a, dy=int(12 * (1 - a)))
    return L


def draw_bars(st, sc, t, dur):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    header(L)
    S.text(L, sc["question"], 310, S.BOLD, S.fit(sc["question"], S.BOLD, 70, 960), S.WHITE, S.prog(t, 0.0, 0.4))
    rows = sc["rows"]
    mx = max(r[1] for r in rows)
    times = sc.get("_row_times") or [0.5 + i * max(1.0, (dur - 1.5) / len(rows)) for i in range(len(rows))]
    for i, (name, val, hot) in enumerate(rows):
        a = S.prog(t, times[i], 0.4)
        if a <= 0:
            continue
        y = 470 + i * 205
        col = st["accent"] if hot else S.WHITE
        p = S.prog(t, times[i] + 0.1, 1.0)
        S.text(L, name, y, S.MED, S.fit(name, S.MED, 42, 560), col, a, x=90, anchor="la")
        S.text(L, f"{num(round(val * p)) if p < 1 else num(val)} {sc['unit']}", y - 2, S.BOLD, 46, col, a, x=990, anchor="ra")
        d.rounded_rectangle([90, y + 72, 990, y + 116], radius=22, fill=tuple(st["track"]) + (int(255 * a),))
        wbar = max(44, int(900 * (val / mx) * p))
        d.rounded_rectangle([90, y + 72, 90 + wbar, y + 116], radius=22,
                            fill=tuple(st["accent"] if hot else st["bar"]) + (int(255 * a),))
    return L


def draw_facts(st, sc, t, dur):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    header(L)
    S.text(L, sc["name"], 300, S.BOLD, S.fit(sc["name"], S.BOLD, 84, 960), st["accent"], S.prog(t, 0.0, 0.4))
    S.text(L, sc["place"], 420, S.MED, S.fit(sc["place"], S.MED, 42, 960), S.WHITE, S.prog(t, 0.2, 0.4))
    step = max(0.6, (dur - 1.2) / len(sc["facts"]))
    for i, (val, lab) in enumerate(sc["facts"]):
        a = S.prog(t, 0.5 + step * i, 0.5)
        if a <= 0:
            continue
        x, y = 80 + (i % 2) * 475, 540 + (i // 2) * 360
        off = int(30 * (1 - a))
        d.rounded_rectangle([x, y + off, x + 445, y + 320 + off], radius=28, fill=tuple(st["card"]) + (int(255 * a),))
        S.text(L, val, y + 70 + off, S.BOLD, S.fit(val, S.BOLD, 88, 390), S.WHITE, a, x=x + 222)
        S.text(L, lab, y + 205 + off, S.REG, S.fit(lab, S.REG, 36, 400), S.MUTED, a, x=x + 222)
    return L


def draw_closing(st, sc, t, dur):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    header(L)
    for i, (line, hot) in enumerate(sc["lines"]):
        a = S.prog(t, 0.1 + 0.35 * i, 0.5)
        S.text(L, line, 640 + i * 112, S.BOLD, S.fit(line, S.BOLD, 82, 960), st["accent"] if hot else S.WHITE, a,
               dy=int(30 * (1 - a)))
    a = S.prog(t, max(1.2, dur - 2.6), 0.5)
    S.text(L, CH["closing_line"], 640 + len(sc["lines"]) * 112 + 90, S.MED, 46, S.WHITE, a)
    return L


DRAW = {"hook": draw_hook, "bars": draw_bars, "facts": draw_facts, "closing": draw_closing}


def draw_caption(L, cue, t):
    if not cue:
        return
    s = cue["text"]
    size = S.fit(s, S.BOLD, 72, CAP_MAXW)
    f = S.font(S.BOLD, size)
    w = f.getlength(s)
    a = S.prog(t, cue["start"], 0.08)
    d = ImageDraw.Draw(L)
    pad_x, pad_y = 30, 18
    d.rounded_rectangle([W / 2 - w / 2 - pad_x, CAP_Y - pad_y, W / 2 + w / 2 + pad_x, CAP_Y + size + pad_y + 6],
                        radius=24, fill=(0, 0, 0, int(165 * a)))
    S.text(L, s, CAP_Y, S.BOLD, size, (255, 236, 140) if re.search(r"\d", s) else S.WHITE, a)


def progress_bar(L, t, total, accent):
    d = ImageDraw.Draw(L)
    d.rectangle([0, 0, int(W * min(1, t / total)), 10], fill=tuple(accent) + (230,))


def render(spec, scenes, cues, out_mp4, total, thumb_path):
    st = spec["style"]
    bg = S.make_bg(tuple(st["bg"][0]), tuple(st["bg"][1]))
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_mp4], stdin=subprocess.PIPE)
    nframes = int(np.ceil(total * FPS))
    si, ci = 0, 0
    for n in range(nframes):
        t = n / FPS
        while si < len(scenes) - 1 and t >= scenes[si]["end"]:
            si += 1
        sc_t = scenes[si]
        sc = spec["scenes"][si]
        img = bg.copy().convert("RGBA")
        img.alpha_composite(DRAW[sc["type"]](st, sc, t - sc_t["start"], sc_t["end"] - sc_t["start"]))
        while ci < len(cues) - 1 and t >= cues[ci]["end"]:
            ci += 1
        cue = cues[ci] if cues and cues[ci]["start"] <= t < cues[ci]["end"] + 0.05 else None
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_caption(ov, cue, t)
        progress_bar(ov, t, total, st["accent"])
        img.alpha_composite(ov)
        p.stdin.write(img.convert("RGB").tobytes())
        if n == 0:
            img.convert("RGB").save(thumb_path, quality=90)
    p.stdin.close()
    if p.wait() != 0:
        sys.exit("ffmpeg failed while rendering frames")


def preview(spec, scenes, cues, out):
    st = spec["style"]
    bg = S.make_bg(tuple(st["bg"][0]), tuple(st["bg"][1]))
    picks = [0.0]
    for s in scenes:
        picks.append((s["start"] + s["end"]) / 2)
        picks.append(s["end"] - 0.1)
    sheet = Image.new("RGB", (len(picks) * 360, 640))
    for k, t in enumerate(picks):
        si = next(i for i, s in enumerate(scenes) if t < s["end"] or i == len(scenes) - 1)
        img = bg.copy().convert("RGBA")
        img.alpha_composite(DRAW[spec["scenes"][si]["type"]](st, spec["scenes"][si], t - scenes[si]["start"],
                                                             scenes[si]["end"] - scenes[si]["start"]))
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cue = next((c for c in cues if c["start"] <= t < c["end"]), None)
        draw_caption(ov, cue, t)
        progress_bar(ov, t, scenes[-1]["end"], st["accent"])
        img.alpha_composite(ov)
        sheet.paste(img.convert("RGB").resize((360, 640)), (k * 360, 0))
    path = os.path.join(out, spec["slug"] + "_sheet.jpg")
    sheet.save(path, quality=85)
    return path


# ---------------------------------------------------------------- main
def main():
    spec_path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    spec = json.load(open(spec_path))
    slug = spec["slug"]
    engine = tts_engine()
    voice, scenes, cues = narrate(spec, engine)
    total = len(voice) / SR
    # bar rows appear when the narration reaches them, if the spec gives the words to wait for
    for sc, tm in zip(spec["scenes"], scenes):
        if sc["type"] == "bars" and sc.get("row_cues"):
            rt = []
            for word in sc["row_cues"]:
                hit = next((c for c in cues if tm["start"] <= c["start"] < tm["end"] and word.lower() in c["text"].lower()),
                           None)
                rt.append((hit["start"] - tm["start"]) if hit else None)
            default = [0.5 + i * max(1.0, (tm["end"] - tm["start"] - 1.5) / len(rt)) for i in range(len(rt))]
            sc["_row_times"] = [r if r is not None else d for r, d in zip(rt, default)]
    if "--preview" in sys.argv:
        print(preview(spec, scenes, cues, out))
        return
    wav_v = os.path.join(out, f"{slug}_voice.wav")
    write_wav(wav_v, voice)
    wav_m = os.path.join(out, f"{slug}_music.wav")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "music.py"), wav_m, f"{total + 0.5:.2f}",
                    str(spec.get("music_seed", 7))], check=True, stdout=subprocess.DEVNULL)
    silent = os.path.join(out, f"{slug}_silent.mp4")
    render(spec, scenes, cues, silent, total, os.path.join(out, f"{slug}_thumb.jpg"))
    final = os.path.join(out, f"{slug}.mp4")
    mv = spec.get("music_volume", CH["music_volume"])
    lufs = CH["loudness_target_lufs"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav_v, "-i", wav_m, "-filter_complex",
                    f"[1:a]aresample=44100,asplit=2[v][sc];[2:a]volume={mv}[m0];"
                    f"[m0][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[m];"
                    f"[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I={lufs}:TP=-1.5:LRA=11[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-movflags", "+faststart", "-shortest", final], check=True)
    with open(os.path.join(out, f"{slug}.srt"), "w") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")
    for tmp in (silent, wav_v, wav_m):
        os.remove(tmp)
    info = {"slug": slug, "duration": round(total, 2), "scenes": scenes, "cues": cues,
            "files": {"video": final, "captions": os.path.join(out, f"{slug}.srt"),
                      "thumbnail": os.path.join(out, f"{slug}_thumb.jpg")},
            "assets": [{"kind": "audio", "origin": "generated", "license": "original (Kokoro TTS, Apache-2.0 model)"},
                       {"kind": "music", "origin": "generated", "license": "original (tools/music.py)"},
                       {"kind": "video", "origin": "generated", "license": "original (drawn by pipeline/produce.py)"}]}
    json.dump(info, open(os.path.join(out, f"{slug}.render.json"), "w"), indent=1)
    print(final, f"{total:.1f}s")


if __name__ == "__main__":
    main()
