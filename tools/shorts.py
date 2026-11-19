import subprocess, sys, os
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FD = "/usr/share/fonts/truetype/google-fonts/"
BOLD, MED, REG = FD + "Poppins-Bold.ttf", FD + "Poppins-Medium.ttf", FD + "Poppins-Regular.ttf"
WHITE, MUTED = (255, 255, 255), (154, 167, 192)
_fonts = {}


def font(path, size):
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def fit(s, path, size, maxw):
    while size > 20 and font(path, size).getlength(s) > maxw:
        size -= 4
    return size


def make_bg(top, bot):
    col = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        col.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    img = col.resize((W, H))
    d = ImageDraw.Draw(img)
    line = tuple(min(255, c + 12) for c in bot)
    for y in range(0, H, 120):
        d.line([(0, y), (W, y)], fill=line, width=1)
    return img


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def prog(t, start, dur):
    return ease((t - start) / dur)


def text(layer, s, y, path, size, color, alpha=1.0, x=None, anchor="ma", dy=0):
    if alpha <= 0:
        return
    a = int(255 * max(0.0, min(1.0, alpha)))
    ImageDraw.Draw(layer).text((W // 2 if x is None else x, y + dy), s, font=font(path, size),
                               fill=tuple(color) + (a,), anchor=anchor)


def header(layer):
    text(layer, "A F R I C A N   M E G A P R O J E C T S", 230, MED, 30, MUTED)


def fmt(n):
    return f"{int(round(n)):,}"


def scene_a(v, t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    header(L)
    p = prog(t, 0.2, 1.6)
    final = f"{fmt(v['hero'])} {v['unit']}"
    size = fit(final, BOLD, 290, 980)
    text(L, f"{fmt(v['hero'] * p)} {v['unit']}", 620, BOLD, size, WHITE, prog(t, 0.1, 0.4))
    a = prog(t, 1.3, 0.5)
    text(L, v["headline"], 1010, MED, fit(v["headline"], MED, 68, 980), WHITE, a, dy=int(30 * (1 - a)))
    a = prog(t, 1.9, 0.5)
    text(L, v["sub"], 1130, BOLD, fit(v["sub"], BOLD, 60, 980), v["accent"], a, dy=int(30 * (1 - a)))
    return L


def scene_b(v, t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    header(L)
    text(L, v["question"], 310, BOLD, fit(v["question"], BOLD, 72, 980), WHITE, prog(t, 0.0, 0.4))
    mx = max(r[1] for r in v["rows"])
    for i, (name, val, hot) in enumerate(v["rows"]):
        start = 0.5 + 1.7 * i
        a = prog(t, start, 0.4)
        if a <= 0:
            continue
        y = 520 + i * 225
        col = v["accent"] if hot else WHITE
        p = prog(t, start + 0.1, 1.2)
        text(L, name, y, MED, fit(name, MED, 44, 600), col, a, x=90, anchor="la")
        text(L, f"{fmt(val * p)} {v['row_unit']}", y - 4, BOLD, 50, col, a, x=990, anchor="ra")
        d.rounded_rectangle([90, y + 78, 990, y + 124], radius=23, fill=v["track"] + (int(255 * a),))
        wbar = max(46, int(900 * (val / mx) * p))
        d.rounded_rectangle([90, y + 78, 90 + wbar, y + 124], radius=23,
                            fill=tuple(v["accent"] if hot else v["bar"]) + (int(255 * a),))
    a = prog(t, 0.5 + 1.7 * len(v["rows"]), 0.5)
    text(L, v["caption"], 1460, BOLD, fit(v["caption"], BOLD, 54, 980), v["accent"], a, dy=int(20 * (1 - a)))
    return L


def scene_c(v, t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    header(L)
    text(L, v["name"], 310, BOLD, fit(v["name"], BOLD, 92, 980), v["accent"], prog(t, 0.0, 0.4))
    text(L, v["place"], 440, MED, fit(v["place"], MED, 42, 980), WHITE, prog(t, 0.2, 0.4))
    for i, (val, lab) in enumerate(v["facts"]):
        a = prog(t, 0.6 + 0.9 * i, 0.5)
        if a <= 0:
            continue
        if v["layout"] == "grid":
            x = 80 + (i % 2) * 475
            y = 580 + (i // 2) * 360
            off = int(30 * (1 - a))
            d.rounded_rectangle([x, y + off, x + 445, y + 320 + off], radius=28, fill=v["card"] + (int(255 * a),))
            text(L, val, y + 70 + off, BOLD, fit(val, BOLD, 92, 390), WHITE, a, x=x + 222)
            text(L, lab, y + 205 + off, REG, fit(lab, REG, 38, 400), MUTED, a, x=x + 222)
        else:
            y = 600 + i * 215
            off = int(60 * (1 - a))
            d.rectangle([110 - off, y + 12, 118 - off, y + 170], fill=tuple(v["accent"]) + (int(255 * a),))
            text(L, val, y, BOLD, fit(val, BOLD, 100, 820), WHITE, a, x=160 - off, anchor="la")
            text(L, lab, y + 122, REG, 44, MUTED, a, x=160 - off, anchor="la")
    return L


def scene_d(v, t):
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    header(L)
    for i, (line, hot) in enumerate(v["closing"]):
        a = prog(t, 0.1 + 0.35 * i, 0.5)
        text(L, line, 720 + i * 112, BOLD, fit(line, BOLD, 82, 980), v["accent"] if hot else WHITE, a,
             dy=int(30 * (1 - a)))
    a = prog(t, 1.5, 0.5)
    text(L, "Follow for more megaprojects", 720 + len(v["closing"]) * 112 + 110, MED, 46, WHITE, a)
    return L


SCENES = [("a", scene_a, 3.5), ("b", scene_b, 9.0), ("c", scene_c, 5.5), ("d", scene_d, 3.0)]

VIDEOS = {
    "kenya-sgr-railway": dict(
        accent=(64, 201, 162), bar=(70, 92, 138), track=(27, 42, 74), card=(22, 35, 63),
        bg=((8, 16, 24), (14, 38, 46)), layout="grid",
        hero=472, unit="km", headline="Kenya's biggest project since 1963", sub="Standard Gauge Railway · Kenya",
        question="How far does it go?", row_unit="km",
        rows=[("Mombasa to Nairobi", 472, False), ("Extension to Naivasha", 120, False), ("Total line", 592, True)],
        caption="From the coast to the Rift Valley",
        name="Kenya's SGR", place="Mombasa to Nairobi, opened 2017",
        facts=[("120 km/h", "passenger train speed"), ("$3.8 bn", "cost of the first phase"),
               ("22 million", "tonnes of cargo a year"), ("2017", "first passengers")],
        closing=[("East Africa's biggest", False), ("port now has a", False), ("modern railway.", True)]),
    "morocco-noor-solar": dict(
        accent=(255, 159, 67), bar=(92, 78, 120), track=(46, 34, 58), card=(44, 30, 52),
        bg=((20, 10, 22), (48, 24, 40)), layout="list",
        hero=580, unit="MW", headline="A solar giant at the edge of the Sahara", sub="Noor Ouarzazate · Morocco",
        question="Four plants, one complex", row_unit="MW",
        rows=[("Noor I", 160, False), ("Noor II", 200, False), ("Noor III", 150, False), ("Noor IV", 70, False)],
        caption="Together: 580 megawatts",
        name="Noor Ouarzazate", place="Drâa-Tafilalet region, Morocco",
        facts=[("3,000 hectares", "of mirrors and panels"), ("247 m", "height of the Noor III tower"),
               ("8 hours", "of stored heat after sunset"), ("2016", "first plant switched on")],
        closing=[("It keeps making", False), ("electricity", False), ("after dark.", True)]),
    "tanzania-nyerere-dam": dict(
        accent=(88, 176, 255), bar=(70, 92, 138), track=(24, 36, 70), card=(20, 32, 64),
        bg=((8, 12, 30), (16, 30, 66)), layout="grid",
        hero=2115, unit="MW", headline="Africa's second-biggest hydropower dam", sub="Julius Nyerere Dam · Tanzania",
        question="How big is 2,115 MW?", row_unit="MW",
        rows=[("Ethiopia's GERD", 5150, False), ("Tanzania's peak demand", 2270, False),
              ("Julius Nyerere Dam", 2115, True)],
        caption="Almost a whole country's peak demand",
        name="Julius Nyerere Dam", place="Rufiji River, Tanzania",
        facts=[("9", "turbines of 235 MW each"), ("$2.9 bn", "cost of the project"),
               ("34 billion", "cubic metres of water"), ("2026", "officially opened")],
        closing=[("Tanzania now makes", False), ("more power than", False), ("it can use.", True)]),
}


def frame(v, bg, fn, t):
    img = bg.copy().convert("RGBA")
    img.alpha_composite(fn(v, t))
    return img.convert("RGB")


def render(slug, v, out):
    bg = make_bg(*v["bg"])
    parts = []
    for name, fn, dur in SCENES:
        tmp = os.path.join(out, f"tmp_{slug}_{name}.mp4")
        final = os.path.join(out, f"{slug}_{name}.mp4")
        p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                              "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "18",
                              "-preset", "veryfast", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
        for i in range(int(round(dur * FPS))):
            p.stdin.write(frame(v, bg, fn, i / FPS).tobytes())
        p.stdin.close()
        if p.wait() != 0:
            sys.exit(f"ffmpeg failed on {slug} {name}")
        os.replace(tmp, final)
        parts.append(final)
    lst = os.path.join(out, f"{slug}.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
    tmp = os.path.join(out, f"tmp_{slug}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", tmp],
                   check=True)
    os.replace(tmp, os.path.join(out, f"{slug}.mp4"))


if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    if mode == "preview":
        sheet = Image.new("RGB", (4 * 360, len(VIDEOS) * 640))
        for r, (slug, v) in enumerate(VIDEOS.items()):
            bg = make_bg(*v["bg"])
            for c, (name, fn, dur) in enumerate(SCENES):
                sheet.paste(frame(v, bg, fn, dur - 0.1).resize((360, 640)), (c * 360, r * 640))
        sheet.save(os.path.join(out, "batch_sheet.jpg"), quality=85)
    else:
        for slug, v in VIDEOS.items():
            render(slug, v, out)
