"""The Inheritance, Episode 2: "The Will". Same look as Episode 1: dark background, speaker pills, gold progress bar.
Renders 1080x1920 at 30 fps and pipes raw frames to ffmpeg. Usage: python3 render_ep2.py OUT.mp4 [preview_dir]"""
import sys, subprocess, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FD = "/usr/share/fonts/truetype/google-fonts/"
BOLD, MED, REG = FD + "Poppins-Bold.ttf", FD + "Poppins-Medium.ttf", FD + "Poppins-Regular.ttf"
GOLD = (242, 195, 106)
GREY = (165, 159, 182)
HEAD = (162, 156, 179)
WHITE = (253, 252, 255)
SPEAKERS = {
    "IDRIS": (253, 149, 89), "AMINA": (109, 213, 199), "YUSUF": (248, 213, 88),
    "UNCLE FARAH": (242, 104, 118), "MAMA": (195, 158, 253),
}

# (kind, speaker or None, text, seconds)
SCRIPT = [
    ("title", None, "The Will", 3.6),
    ("narr", None, "Ten o'clock. The whole family sits in Father's shop.", 4.2),
    ("narr", None, "Uncle Farah opens the envelope.", 3.4),
    ("say", "UNCLE FARAH", "“To my wife, the house. To Amina and Yusuf, my savings, shared equally.”", 5.2),
    ("say", "IDRIS", "“And the shop?”", 2.8),
    ("say", "UNCLE FARAH", "“The shop goes to Layla.”", 3.8),
    ("narr", None, "Nobody moves. Then Idris stands up so fast his chair falls.", 4.4),
    ("say", "IDRIS", "“Who is Layla? Say it, Uncle.”", 3.8),
    ("say", "YUSUF", "“Mama. You knew. You had that letter all along.”", 4.4),
    ("narr", None, "Mama looks at her hands for a long time.", 3.8),
    ("say", "MAMA", "“Layla is your sister.”", 3.6),
    ("say", "AMINA", "“We don't have a sister.”", 3.2),
    ("say", "MAMA", "“You have had one for twenty-two years.”", 4.2),
    ("narr", None, "Uncle Farah slides a photo across the table. A young woman, standing in front of this same shop.", 5.6),
    ("say", "UNCLE FARAH", "“She is coming here. Today.”", 3.8),
    ("narr", None, "Outside, a car stops.", 3.4),
    ("end", None, "Who opens the door?", 5.0),
]
FADE, RISE = 0.35, 14

_f = {}
def font(p, s):
    if (p, s) not in _f:
        _f[(p, s)] = ImageFont.truetype(p, s)
    return _f[(p, s)]

def wrap(s, f, maxw):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.getlength(t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

def balanced(s, f, maxw):
    # same number of lines as a plain wrap, but with line lengths as even as possible
    n = len(wrap(s, f, maxw))
    lo, hi = 200, maxw
    while hi - lo > 4:
        mid = (lo + hi) / 2
        if len(wrap(s, f, mid)) > n: lo = mid
        else: hi = mid
    return wrap(s, f, hi)

def background():
    y = np.linspace(0, 1, H)[:, None]
    top, mid, bot = np.array([9, 7, 15]), np.array([40, 35, 51]), np.array([28, 19, 43])
    k1 = np.clip(y / 0.5, 0, 1)
    col = np.where(y < 0.5, top + (mid - top) * (k1 ** 1.3), mid + (bot - mid) * ((y - 0.5) / 0.5))
    x = np.linspace(-1, 1, W)[None, :]
    vign = 1 - 0.22 * x ** 2
    img = col[:, None, :] * vign[..., None]
    lines = (np.arange(H) % 64 == 0)[:, None, None] * 3.0     # faint ruled lines, as in Episode 1
    img = np.clip(img + lines, 0, 255).astype(np.uint8)
    return np.broadcast_to(img, (H, W, 3)).copy()

def header_layer(ep):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = f"THE INHERITANCE · EPISODE {ep}"
    f = font(MED, 22)
    spacing = 5
    total = sum(f.getlength(c) for c in s) + spacing * (len(s) - 1)
    x = (W - total) / 2
    for c in s:
        d.text((x, 236), c, font=f, fill=HEAD + (255,))
        x += f.getlength(c) + spacing
    return im

def scene_layer(kind, who, txt):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    CY = 870
    if kind == "say":
        f = font(BOLD, 60)
        lines = balanced(txt, f, 760)
        lh = 97
        pf = font(BOLD, 26)
        pw = pf.getlength(who) + 56
        ph = 62
        block = ph + 56 + lh * len(lines)
        y0 = CY - block / 2
        col = SPEAKERS[who]
        d.rounded_rectangle([(W - pw) / 2, y0, (W + pw) / 2, y0 + ph], radius=ph / 2, fill=col + (255,))
        d.text((W / 2, y0 + ph / 2 + 1), who, font=pf, fill=(24, 18, 32, 255), anchor="mm")
        y = y0 + ph + 56
        for ln in lines:
            d.text((W / 2, y), ln, font=f, fill=WHITE + (255,), anchor="ma")
            y += lh
    elif kind == "narr":
        f = font(MED, 42)
        lines = balanced(txt, f, 800)
        lh = 62
        y = CY - lh * len(lines) / 2
        for ln in lines:
            d.text((W / 2, y), ln, font=f, fill=GREY + (255,), anchor="ma")
            y += lh
    elif kind == "title":
        d.text((W / 2, 790), "Episode 2", font=font(MED, 42), fill=GOLD + (255,), anchor="ma")
        d.text((W / 2, 860), txt, font=font(BOLD, 104), fill=WHITE + (255,), anchor="ma")
    elif kind == "end":
        f = font(BOLD, 96)
        lines = balanced(txt, f, 900)
        y = 900 - 120 * len(lines)
        for ln in lines:
            d.text((W / 2, y), ln, font=f, fill=GOLD + (255,), anchor="ma")
            y += 120
        d.text((W / 2, y + 60), "Episode 3 coming soon", font=font(MED, 46), fill=WHITE + (255,), anchor="ma")
        d.text((W / 2, y + 150), "Follow so you don't miss it", font=font(REG, 36), fill=GREY + (255,), anchor="ma")
    return np.asarray(im).astype(np.float32)

def ease(t):
    t = min(max(t, 0), 1)
    return 1 - (1 - t) ** 3

def main():
    out = sys.argv[1]
    preview = sys.argv[2] if len(sys.argv) > 2 else None
    bg = background().astype(np.float32)
    hdr = np.asarray(header_layer(2)).astype(np.float32)
    a = hdr[..., 3:4] / 255
    base = bg * (1 - a) + hdr[..., :3] * a
    layers = [scene_layer(k, w, t) for k, w, t, _ in SCRIPT]
    total = sum(s[3] for s in SCRIPT)
    n = int(round(total * FPS))
    starts = np.cumsum([0] + [s[3] for s in SCRIPT])
    if preview:
        frames = {int((starts[i] + SCRIPT[i][3] / 2) * FPS) for i in range(len(SCRIPT))}
    proc = None if preview else subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)
    bar_x0, bar_x1, bar_y = 140, 940, 290
    for i in range(n):
        if preview and i not in frames:
            continue
        t = i / FPS
        si = int(np.searchsorted(starts, t, side="right") - 1)
        si = min(si, len(SCRIPT) - 1)
        lt, dur = t - starts[si], SCRIPT[si][3]
        fin = ease(lt / FADE)
        fout = 1.0 if si == len(SCRIPT) - 1 else ease((dur - lt) / FADE)
        alpha = min(fin, fout)
        dy = int(round(RISE * (1 - fin)))
        frame = base.copy()
        L = layers[si]
        if dy:
            L = np.roll(L, dy, axis=0)
        la = L[..., 3:4] / 255 * alpha
        frame = frame * (1 - la) + L[..., :3] * la
        # progress bar: track and gold fill
        frame[bar_y:bar_y + 6, bar_x0:bar_x1] = frame[bar_y:bar_y + 6, bar_x0:bar_x1] * 0.4 + np.array([70, 64, 86]) * 0.6
        fx = bar_x0 + int((bar_x1 - bar_x0) * min(1, t / total))
        frame[bar_y:bar_y + 6, bar_x0:fx] = GOLD
        fr = np.clip(frame, 0, 255).astype(np.uint8)
        if preview:
            Image.fromarray(fr).resize((360, 640)).save(f"{preview}/f{si:02d}.png")
        else:
            proc.stdin.write(fr.tobytes())
    if proc:
        proc.stdin.close(); proc.wait()
    print(f"{out}: {total:.1f}s, {n} frames")

if __name__ == "__main__":
    main()
