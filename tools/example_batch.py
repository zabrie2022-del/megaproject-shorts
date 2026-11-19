import sys, os
from PIL import Image
import shorts as b

b.VIDEOS = {
    "kenya-turkana-wind": dict(
        accent=(110, 220, 200), bar=(64, 100, 110), track=(20, 44, 52), card=(16, 40, 48),
        bg=((6, 16, 22), (10, 44, 54)), layout="grid",
        hero=365, unit="turbines", headline="Africa's largest wind farm",
        sub="Lake Turkana Wind Power · Kenya",
        question="Wind power in Kenya", row_unit="MW",
        rows=[("Before (Ngong Hills)", 26, False), ("Lake Turkana alone", 310, True)],
        caption="About 12 times more wind power",
        name="Lake Turkana Wind", place="Marsabit County, Kenya",
        facts=[("310 MW", "total capacity"), ("850 kW", "per turbine"),
               ("$700 m", "approximate cost"), ("2019", "inaugurated")],
        closing=[("365 turbines", False), ("went up in", False), ("365 days.", True)]),
    "kenya-nairobi-expressway": dict(
        accent=(250, 204, 70), bar=(92, 96, 120), track=(36, 38, 58), card=(32, 34, 54),
        bg=((12, 12, 22), (30, 30, 52)), layout="list",
        hero=27, unit="km", headline="From the airport to Westlands",
        sub="Nairobi Expressway · Kenya",
        question="Across Nairobi at rush hour", row_unit="min",
        rows=[("Before", 120, False), ("On the expressway", 20, True)],
        caption="Two hours cut to about 20 minutes",
        name="Nairobi Expressway", place="Mlolongo to Westlands, Nairobi",
        facts=[("$668 million", "cost"), ("8.5 km", "elevated above the city"),
               ("27 years", "toll concession"), ("2022", "opened")],
        closing=[("Built in under", False), ("three years,", False), ("ahead of schedule.", True)]),
    "egypt-grand-museum": dict(
        accent=(236, 182, 112), bar=(120, 96, 80), track=(52, 38, 30), card=(48, 34, 28),
        bg=((20, 12, 8), (52, 32, 22)), layout="grid",
        hero=100000, unit="artifacts", headline="The largest museum for one civilization",
        sub="Grand Egyptian Museum · Egypt",
        question="What is inside?", row_unit="",
        rows=[("Artifacts in total", 100000, True), ("Never displayed before", 20000, False)],
        caption="With Tutankhamun's complete collection",
        name="Grand Egyptian Museum", place="Giza, Egypt",
        facts=[("$1 billion", "approximate cost"), ("2 km", "from the pyramids"),
               ("50 hectares", "size of the complex"), ("2025", "opened")],
        closing=[("Open at last,", False), ("after more than", False), ("20 years.", True)]),
    "egypt-new-suez-canal": dict(
        accent=(96, 165, 255), bar=(70, 92, 138), track=(22, 34, 68), card=(18, 30, 62),
        bg=((6, 10, 28), (14, 28, 66)), layout="list",
        hero=72, unit="km", headline="Built in one year, not three",
        sub="New Suez Canal · Egypt",
        question="What was built?", row_unit="km",
        rows=[("New parallel channel", 35, True), ("Widened and deepened", 37, False),
              ("The whole canal", 193, False)],
        caption="Two-way traffic on part of the route",
        name="New Suez Canal", place="Opened 6 August 2015",
        facts=[("$8.5 billion", "cost"), ("1 year", "construction time"),
               ("11 hours", "transit time, down from 18"), ("2015", "opened")],
        closing=[("Egyptians funded it", False), ("in just", False), ("six days.", True)]),
}

if __name__ == "__main__":
    mode, out = sys.argv[1], sys.argv[2]
    if mode == "preview":
        sheet = Image.new("RGB", (4 * 360, len(b.VIDEOS) * 640))
        for r, (slug, v) in enumerate(b.VIDEOS.items()):
            bg = b.make_bg(*v["bg"])
            for c, (name, fn, dur) in enumerate(b.SCENES):
                sheet.paste(b.frame(v, bg, fn, dur - 0.1).resize((360, 640)), (c * 360, r * 640))
        sheet.save(os.path.join(out, "batch3_sheet.jpg"), quality=85)
    else:
        for slug, v in b.VIDEOS.items():
            b.render(slug, v, out)
