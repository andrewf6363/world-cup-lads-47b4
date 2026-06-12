#!/usr/bin/env python3
"""Generate a shareable PNG card per manager into cards/<slug>.png. Reads the built index.html
DATA blob. Needs Pillow; if it's missing this exits 0 (so the core build never breaks)."""
import os, re, json, sys
try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    print("Pillow not installed — skipping cards (pip install pillow)"); sys.exit(0)

HERE = os.path.dirname(__file__); ROOT = os.path.join(HERE, ".."); FD = os.path.join(ROOT, "assets", "fonts")
OUT = os.path.join(ROOT, "cards"); os.makedirs(OUT, exist_ok=True)
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
DATA = json.loads(re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1))
players, meta = DATA["players"], DATA["meta"]

def F(name, size): return ImageFont.truetype(os.path.join(FD, name), size)
def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def ordn(n): return f"{n}{'TH' if 10 <= n % 100 <= 20 else {1:'ST',2:'ND',3:'RD'}.get(n % 10,'TH')}"

INK=(247,240,225); NAVY=(16,36,58); GOLD=(227,165,42)
GRASS=(36,170,84); MUT=(139,151,166)
W = Hh = 1080

for p in players:
    img = Image.new("RGB", (W, Hh), NAVY); d = ImageDraw.Draw(img)
    for i in range(Hh):                                   # vertical gradient (midnight navy)
        t = i / Hh; d.line([(0, i), (W, i)], fill=(int(16-7*t), int(36-14*t), int(58-21*t)))
    d.rectangle([0, 0, W, 14], fill=GOLD)
    pad = 84
    d.text((pad, 70),  "WORLD CUP LADS", font=F("Barlow-Bold.ttf", 30), fill=GOLD)
    d.text((pad, 112), "FRIENDS LEAGUE · 2026", font=F("Barlow-SemiBold.ttf", 24), fill=MUT)
    d.text((pad, 178), p["name"].upper()[:16], font=F("Anton-Regular.ttf", 90), fill=INK)
    rcol = {1: GOLD, 2: (175,181,186), 3: (190,123,60)}.get(p["rank"], MUT)
    d.text((pad, 300), f"{ordn(p['rank'])} OF {meta['managers']}", font=F("Barlow-Bold.ttf", 34), fill=rcol)
    pts = f"{p['total']:,}"; pf = F("Anton-Regular.ttf", 190)
    d.text((pad, 350), pts, font=pf, fill=GOLD)
    d.text((pad + d.textlength(pts, font=pf) + 22, 470), "PTS", font=F("Barlow-Bold.ttf", 40), fill=MUT)
    y = 590
    if len(players) > 1 and meta.get("graded", 0) >= 10:
        d.text((pad, y), f"{p.get('winpct',0)}% TO LEAD", font=F("Barlow-Bold.ttf", 46), fill=GRASS); y += 72
    if p.get("champ"):
        d.text((pad, y), f"RIDING WITH {p['champ'].upper()}", font=F("Barlow-Bold.ttf", 40), fill=INK); y += 64
    bx = pad
    for b in (p.get("badges") or [])[:3]:
        bf = F("Barlow-Bold.ttf", 28); bw = d.textlength(b.upper(), font=bf)
        d.rounded_rectangle([bx, y, bx + bw + 36, y + 52], radius=26, outline=GOLD, width=2)
        d.text((bx + 18, y + 11), b.upper(), font=bf, fill=GOLD); bx += bw + 52
    d.text((pad, Hh - 86), "andrewf6363.github.io/world-cup-lads-47b4", font=F("Barlow-SemiBold.ttf", 26), fill=MUT)
    img.save(os.path.join(OUT, slug(p["name"]) + ".png"))

# ---- league-level renders: og.png (link unfurl image) + apple-touch-icon.png ----
def gradient(w, h):
    img = Image.new("RGB", (w, h), NAVY); d = ImageDraw.Draw(img)
    for i in range(h):
        t = i / h; d.line([(0, i), (w, i)], fill=(int(16-7*t), int(36-14*t), int(58-21*t)))
    return img, d

def render_og():
    W2, H2 = 1200, 630; img, d = gradient(W2, H2)
    d.rectangle([0, 0, W2, 16], fill=GOLD)
    pad = 84
    d.text((pad, 84), "THE FRIENDS LEAGUE · 2026", font=F("Barlow-Bold.ttf", 32), fill=MUT)
    d.text((pad, 132), "WORLD CUP LADS", font=F("Anton-Regular.ttf", 124), fill=INK)
    if meta.get("started") and players:
        tied = sum(1 for p in players if p.get("rank") == 1)
        sub = (f"{tied} TIED AT THE TOP — {meta.get('phase','').upper()}" if tied > 1
               else f"{players[0]['name'].upper()} LEADS — {meta.get('phase','').upper()}")
    else:
        sub = f"KICKS OFF JUNE 11 · ${meta.get('pot', 200)} POT · WINNER TAKES ALL"
    d.text((pad, 312), sub, font=F("Barlow-Bold.ttf", 44), fill=GOLD)
    y = 402
    if meta.get("started") and players:
        for p in players[:3]:
            d.text((pad, y), f"{p['rank']}. {p['name'].upper()}", font=F("Barlow-Bold.ttf", 36), fill=INK)
            d.text((pad + 560, y), f"{p['total']:,} PTS", font=F("Barlow-Bold.ttf", 36), fill=MUT); y += 56
    else:
        for ln in (f"{meta.get('managers', 8)} MANAGERS · ALL 72 GROUP MATCHES PICKED",
                   "100 PTS A CORRECT PICK · KNOCKOUT POINTS DOUBLE EVERY ROUND"):
            d.text((pad, y), ln, font=F("Barlow-Bold.ttf", 34), fill=INK); y += 56
    d.text((pad, H2 - 84), "andrewf6363.github.io/world-cup-lads-47b4", font=F("Barlow-SemiBold.ttf", 28), fill=MUT)
    img.save(os.path.join(OUT, "og.png"))

def render_touch_icon():
    import math
    S = 180; img, d = gradient(S, S)
    cx = cy = S / 2
    d.ellipse([cx-50, cy-50, cx+50, cy+50], fill=GOLD)
    pts = [(cx + 24*math.cos(math.radians(a)), cy - 24*math.sin(math.radians(a))) for a in (90, 162, 234, 306, 18)]
    d.polygon(pts, fill=NAVY)
    img.save(os.path.join(ROOT, "apple-touch-icon.png"))

render_og()
render_touch_icon()
print(f"generated {len(players)} card(s) + og.png + apple-touch-icon.png")
