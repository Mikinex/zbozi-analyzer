#!/usr/bin/env python3
"""Generuje infografiku datového toku Zboží.cz Dashboard Analyzeru."""

from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1400, 900
BG = (18, 25, 43)        # --zbozi-dark
BLUE = (26, 107, 255)    # --zbozi-blue
ORANGE = (255, 106, 0)   # --zbozi-orange
WHITE = (255, 255, 255)
LIGHT = (200, 215, 240)
GREEN = (25, 135, 84)
RED = (220, 53, 69)
GRAY = (100, 120, 150)
CARD_BG = (30, 40, 60)
CARD_BORDER = (50, 70, 100)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# Fonts - use default, sized
try:
    font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    font_head = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    font_body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    font_label = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
except:
    font_title = ImageFont.load_default()
    font_head = font_body = font_small = font_label = font_title


def rounded_rect(xy, fill, border=None, r=12):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=border, width=2)


def draw_arrow(x1, y1, x2, y2, color=GRAY, width=2):
    d.line([(x1, y1), (x2, y2)], fill=color, width=width)
    # Arrowhead
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 8
    d.polygon([
        (x2, y2),
        (x2 - size * math.cos(angle - 0.4), y2 - size * math.sin(angle - 0.4)),
        (x2 - size * math.cos(angle + 0.4), y2 - size * math.sin(angle + 0.4)),
    ], fill=color)


def draw_box(x, y, w, h, title, items, color=BLUE, icon=""):
    rounded_rect((x, y, x + w, y + h), CARD_BG, CARD_BORDER)
    # Color accent bar
    d.rounded_rectangle((x, y, x + w, y + 4), radius=2, fill=color)
    # Title
    tx = x + 14
    ty = y + 14
    if icon:
        d.text((tx, ty - 2), icon, fill=color, font=font_head)
        tx += 24
    d.text((tx, ty), title, fill=WHITE, font=font_head)
    # Items
    for i, item in enumerate(items):
        d.text((x + 18, y + 42 + i * 18), item, fill=LIGHT, font=font_small)


# ═══════════════════════════════════════════
# Title
# ═══════════════════════════════════════════
d.text((40, 25), "Zbozi.cz Dashboard Analyzer", fill=WHITE, font=font_title)
d.text((40, 65), "Datovy tok a architektura systemu", fill=GRAY, font=font_head)

# Subtitle line
d.line([(40, 95), (W - 40, 95)], fill=CARD_BORDER, width=1)

# ═══════════════════════════════════════════
# Row 1: Input → API → Feed Download
# ═══════════════════════════════════════════

# Box 1: User Input
draw_box(40, 120, 220, 130,
         "Uzivatel", [
             "Shop ID (provozovna)",
             "API klic (Basic Auth)",
             "Tlacitko: Nacist",
         ], ORANGE, "")

# Arrow →
draw_arrow(270, 185, 310, 185, ORANGE, 3)

# Box 2: Zbozi.cz API
draw_box(320, 120, 280, 130,
         "Zbozi.cz API v1", [
             "/v1/shop/feeds → feed URL",
             "/v1/shop/diagnostics/item",
             "/v1/shop/items (30/stranka)",
             "/v1/products/{ids} (davky 10)",
         ], BLUE, "")

# Arrow →
draw_arrow(610, 185, 650, 185, BLUE, 3)

# Box 3: XML Feed
draw_box(660, 120, 280, 130,
         "XML Feed (stazeni)", [
             "HTTP GET → feed URL",
             "Parsovani SHOPITEM elementu",
             "PRICE_VAT, DELIVERY_DATE",
             "EAN, PARAM, URL, IMGURL",
         ], GREEN, "")

# Arrow →
draw_arrow(950, 185, 990, 185, GREEN, 3)

# Box 4: Stats & Reviews
draw_box(1000, 120, 360, 130,
         "Doplnkova data", [
             "Statistiky: agregovane, kategorie, zarizeni",
             "Recenze: obchod + produkty (max 180d)",
             "Kampan, bidding info",
             "Kategorie: parametry/atributy",
         ], ORANGE, "")

# ═══════════════════════════════════════════
# Row 2: Processing
# ═══════════════════════════════════════════

# Arrow ↓ from API
draw_arrow(460, 250, 460, 290, BLUE, 3)
# Arrow ↓ from Feed
draw_arrow(800, 250, 800, 290, GREEN, 3)

# Big processing box
rounded_rect((120, 290, 1080, 470), CARD_BG, CARD_BORDER)
d.rounded_rectangle((120, 290, 1080, 294), radius=2, fill=ORANGE)
d.text((140, 305), "Analyticke jadro (analyzer.py)", fill=WHITE, font=font_head)

# Sub-steps inside
steps = [
    ("1", "Polozky z API", "items + loadProductDetail\npaginace po 30", BLUE),
    ("2", "Obohaceni z feedu", "cena, EAN, parametry\ndostupnost, URL, obrazek", GREEN),
    ("3", "Konkurencni data", "shopCount, minPrice\npriceVsMin z /products", BLUE),
    ("4", "Analyza kategorii", "CTR, CPC gap\nsilne/slabe kategorie", ORANGE),
    ("5", "Doporuceni", "feed tipy, Sklik\nstrategie, varovani", RED),
]

for i, (num, title, desc, color) in enumerate(steps):
    bx = 140 + i * 185
    by = 340
    rounded_rect((bx, by, bx + 170, by + 110), (20, 30, 50), color, r=8)
    # Number circle
    d.ellipse((bx + 8, by + 8, bx + 30, by + 30), fill=color)
    d.text((bx + 14, by + 10), num, fill=WHITE, font=font_body)
    d.text((bx + 38, by + 10), title, fill=WHITE, font=font_body)
    for j, line in enumerate(desc.split("\n")):
        d.text((bx + 12, by + 38 + j * 16), line, fill=LIGHT, font=font_small)
    # Arrow between steps
    if i < len(steps) - 1:
        draw_arrow(bx + 170, by + 55, bx + 185, by + 55, GRAY, 2)

# ═══════════════════════════════════════════
# Row 3: Output
# ═══════════════════════════════════════════

# Arrow ↓
draw_arrow(600, 470, 600, 510, ORANGE, 3)

# Dashboard output
rounded_rect((120, 510, 860, 700), CARD_BG, CARD_BORDER)
d.rounded_rectangle((120, 510, 860, 514), radius=2, fill=BLUE)
d.text((140, 524), "Dashboard (8 tabu)", fill=WHITE, font=font_head)

tabs = [
    ("Prehled", "KPI, grafy, diagnostika", BLUE),
    ("Statistiky", "Denni graf, zarizeni", BLUE),
    ("Kategorie", "Bar chart, CTR, CPC", GREEN),
    ("Polozky", "Tabulka, filtry, razeni", GREEN),
    ("Recenze", "Obchod + produkty", ORANGE),
    ("Doporuceni", "Feed + Sklik tipy", ORANGE),
    ("API stav", "Endpointy, varovani", RED),
    ("API Explorer", "Vsechny endpointy", RED),
]

for i, (name, desc, color) in enumerate(tabs):
    col = i % 4
    row = i // 4
    tx = 140 + col * 178
    ty = 560 + row * 65
    rounded_rect((tx, ty, tx + 165, ty + 55), (20, 30, 50), color, r=6)
    d.text((tx + 10, ty + 8), name, fill=WHITE, font=font_body)
    d.text((tx + 10, ty + 28), desc, fill=LIGHT, font=font_label)

# API Explorer box
rounded_rect((880, 510, 1360, 700), CARD_BG, CARD_BORDER)
d.rounded_rectangle((880, 510, 1360, 514), radius=2, fill=GREEN)
d.text((900, 524), "API Explorer (/api/call)", fill=WHITE, font=font_head)

explorer_items = [
    "23 endpointu primo z UI",
    "Dynamicke parametry per endpoint",
    "Feed download + XML parsing",
    "items (max 30) / items_basic (max 3000)",
    "Statistiky, recenze (max 180d)",
    "Produkty, kategorie, vyrobci",
    "Formatovany JSON + kopirovani",
]
for i, item in enumerate(explorer_items):
    d.text((900, 555 + i * 19), "  " + item, fill=LIGHT, font=font_small)

# Arrow from dashboard to explorer
draw_arrow(860, 605, 880, 605, GRAY, 2)

# ═══════════════════════════════════════════
# Row 4: API Limits footer
# ═══════════════════════════════════════════

rounded_rect((40, 720, W - 40, 780), (25, 35, 55), CARD_BORDER, r=8)
d.text((60, 732), "Omezeni API:", fill=ORANGE, font=font_body)
limits = [
    "items+detail: max 30/req",
    "items+search: max 300/req",
    "items basic: max 3000/req",
    "recenze: max 180d zpet",
    "products: max 10 IDs",
    "rate limit: 2s/req",
]
for i, lim in enumerate(limits):
    d.text((220 + i * 195, 732), lim, fill=LIGHT, font=font_small)

# Warning bar
rounded_rect((40, 800, W - 40, 850), (60, 40, 20), (200, 150, 50), r=8)
d.text((60, 812), "!  API api.zbozi.cz bude vypnuto 16. 3. 2026  –  Migrujte na Sklik API (api.sklik.cz)", fill=(255, 200, 100), font=font_head)

# Watermark
d.text((W - 350, H - 30), "Zbozi.cz Dashboard Analyzer v1.0 | 2026", fill=GRAY, font=font_small)

# Save
out_path = os.path.join(os.path.dirname(__file__), "infographic_dataflow.jpg")
img.save(out_path, "JPEG", quality=95)
print(f"Saved: {out_path}")
print(f"Size: {W}x{H}")
