#!/usr/bin/env python3
"""Build the images a link preview and a browser tab need.

    python3 scripts/make_social_images.py

Writes, at the top level so they sit at the URLs browsers probe by default:

    images/og-card.jpg    1200x630, what X / LinkedIn / Slack / iMessage show
    icon.svg              the tab icon, drawn as geometry so no font is needed
    favicon.ico           the same mark at 16, 32 and 48px for older browsers
    apple-touch-icon.png  180x180, for a page saved to an iOS home screen

It also right-sizes images/hamilton-oh.jpg if it is larger than the page can use.
The untouched original stays in source/.

The card is set in Barlow, matching the site. The fonts are fetched once from the
Google Fonts repository and cached in source/fonts/; without a network the script
falls back to a condensed system face, which is close enough and still readable.
"""

import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PORTRAIT = ROOT / "images" / "hamilton-oh.jpg"
FONT_DIR = ROOT / "source" / "fonts"

INK = (11, 11, 12)
RED = (216, 38, 27)
MUTED = (110, 115, 118)
WHITE = (255, 255, 255)

NAME = "Hamilton Se-Hwee Oh"
ROLE = "Postdoctoral fellow · Icahn School of Medicine at Mount Sinai"
TOPICS = "Aging · Neurodegeneration · Brain–body communication"

GOOGLE_FONTS = "https://raw.githubusercontent.com/google/fonts/main/ofl"
WANTED = {
    "BarlowCondensed-Regular.ttf": f"{GOOGLE_FONTS}/barlowcondensed/BarlowCondensed-Regular.ttf",
    "Barlow-Regular.ttf": f"{GOOGLE_FONTS}/barlow/Barlow-Regular.ttf",
}
# Used when the fonts cannot be fetched. Arial Narrow stands in for the condensed
# face; both ship with macOS.
FALLBACK = {
    "BarlowCondensed-Regular.ttf": "/System/Library/Fonts/Supplemental/Arial Narrow.ttf",
    "Barlow-Regular.ttf": "/System/Library/Fonts/Supplemental/Arial.ttf",
}


def font(name, size):
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    cached = FONT_DIR / name
    if not cached.exists():
        try:
            with urllib.request.urlopen(WANTED[name], timeout=30) as response:
                cached.write_bytes(response.read(6_000_000))
            print(f"  fetched {name}")
        except Exception as exc:
            print(f"  could not fetch {name} ({type(exc).__name__}); using a system face")
            return ImageFont.truetype(FALLBACK[name], size)
    return ImageFont.truetype(str(cached), size)


def cover(image, width, height):
    """Scale and centre-crop to exactly width x height, like CSS object-fit: cover."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)),
                           Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def make_card():
    """A Swiss card: name and role on the left, portrait bled off the right edge."""
    W, H, PANEL, PAD = 1200, 630, 430, 76
    card = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(card)

    if PORTRAIT.exists():
        with Image.open(PORTRAIT) as photo:
            card.paste(cover(photo.convert("RGB"), PANEL, H), (W - PANEL, 0))
    else:
        print(f"  warning: {PORTRAIT.name} missing; card has no portrait")

    name_font = font("BarlowCondensed-Regular.ttf", 86)
    role_font = font("Barlow-Regular.ttf", 27)
    topic_font = font("Barlow-Regular.ttf", 25)

    text_width = W - PANEL - PAD * 2
    y = 176
    draw.text((PAD, y), NAME, font=name_font, fill=INK)
    y += 104
    draw.rectangle([PAD, y, PAD + 68, y + 5], fill=RED)   # the site's one accent
    y += 42

    for line, face, colour in ((ROLE, role_font, INK), (TOPICS, topic_font, MUTED)):
        for wrapped in wrap(draw, line, face, text_width):
            draw.text((PAD, y), wrapped, font=face, fill=colour)
            y += round(face.size * 1.42)
        y += 12

    out = ROOT / "images" / "og-card.jpg"
    card.save(out, "JPEG", quality=90, optimize=True, progressive=True)
    print(f"  images/og-card.jpg ({W}x{H}, {out.stat().st_size // 1024} KB)")


def wrap(draw, text, face, limit):
    lines, line = [], ""
    for word in text.split(" "):
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=face) > limit:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


# An H is three rectangles, so the mark is drawn as geometry rather than set in a
# font. That keeps the SVG and the PNGs identical, and the SVG needs no webfont on
# a machine that has never loaded the site.
BARS = [(19, 14, 27, 50), (37, 14, 45, 50), (19, 28, 45, 36)]   # x0, y0, x1, y1 on a 64 grid

ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <title>Hamilton Se-Hwee Oh</title>
  <rect width="64" height="64" rx="9" fill="#D8261B"/>
  <path fill="#FFFFFF" d="M19 14h8v14h10V14h8v36h-8V36H27v14h-8z"/>
</svg>
'''


def mark(size):
    """The same H, rasterised. Drawn large and downsampled so the edges stay clean."""
    scale = 8
    big = Image.new("RGBA", (64 * scale, 64 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle([0, 0, 64 * scale - 1, 64 * scale - 1],
                           radius=9 * scale, fill=RED)
    for x0, y0, x1, y1 in BARS:
        draw.rectangle([x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1], fill=WHITE)
    return big.resize((size, size), Image.LANCZOS)


def make_icons():
    (ROOT / "icon.svg").write_text(ICON_SVG)
    print("  icon.svg")

    mark(48).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("  favicon.ico (16, 32, 48)")

    # iOS composites its own rounded corners, so this one is a flat square.
    touch = Image.new("RGB", (180, 180), RED)
    touch.paste(mark(180).convert("RGB"), (0, 0), mark(180).split()[3])
    touch.save(ROOT / "apple-touch-icon.png", "PNG", optimize=True)
    print("  apple-touch-icon.png (180x180)")


# The portrait renders in a 265px column — about 530px on a retina screen. Anything
# much past that is weight every visitor downloads and no one sees, and page weight
# is one of the things Google measures.
PORTRAIT_WIDTH = 640


def resize_portrait():
    if not PORTRAIT.exists():
        return
    with Image.open(PORTRAIT) as image:
        if image.width <= PORTRAIT_WIDTH:
            print(f"  images/hamilton-oh.jpg already {image.width}px wide; left alone")
            return
        was = PORTRAIT.stat().st_size
        height = round(image.height * PORTRAIT_WIDTH / image.width)
        resized = image.convert("RGB").resize((PORTRAIT_WIDTH, height), Image.LANCZOS)
    resized.save(PORTRAIT, "JPEG", quality=88, optimize=True, progressive=True)
    now = PORTRAIT.stat().st_size
    print(f"  images/hamilton-oh.jpg {PORTRAIT_WIDTH}x{height} "
          f"({was // 1024} KB -> {now // 1024} KB; original kept in source/)")

    # The <img> carries the real pixel size so the browser reserves the right box before
    # the file arrives. Stale numbers there make the page jump as it loads, which is one
    # of the three things Google scores. Keep them in step with the file automatically.
    index = ROOT / "index.html"
    html = index.read_text()
    patched, count = re.subn(
        r'(<img src="images/hamilton-oh\.jpg"[^>]*?width=")\d+("\s+height=")\d+(")',
        rf"\g<1>{PORTRAIT_WIDTH}\g<2>{height}\g<3>", html)
    if count:
        index.write_text(patched)
        print(f"  index.html — portrait <img> now declares {PORTRAIT_WIDTH}x{height}")
    else:
        print(f"  WARNING: could not find the portrait <img> in index.html. Set its "
              f"width/height to {PORTRAIT_WIDTH}x{height} by hand or the page will jump "
              f"as it loads.")


def main():
    make_card()      # before the resize, so the card is cut from the larger original
    make_icons()
    resize_portrait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
