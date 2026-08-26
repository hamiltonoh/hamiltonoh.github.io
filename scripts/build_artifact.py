#!/usr/bin/env python3
"""Build dist/index.html — a single file with the thumbnails inlined as data URIs.

index.html is the real, deployable site: it links images/pubs/*.jpg so browsers can
cache them. That is the right shape for a web host but useless anywhere the page
travels alone (a preview link, an email attachment, a file:// open), where the
relative paths resolve to nothing.

This produces a standalone copy for those cases. Deploy index.html; share dist/.

    python3 scripts/build_artifact.py
"""

import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "index.html"
OUT = ROOT / "dist" / "index.html"
THUMBS = ROOT / "images" / "pubs"

# Browsers refuse data: URIs past a few MB, and the artifact host caps the page at 16MB.
SIZE_WARN = 12 * 1024 * 1024


INLINE_WIDTH = 1200      # tiles render ~500 CSS px; 1200 keeps them sharp at 2x retina
INLINE_QUALITY = 80


def shrink(path):
    """Return JPEG bytes scaled down for inlining, or the original if already small."""
    from PIL import Image
    from io import BytesIO

    image = Image.open(path)
    image.load()
    if image.width <= INLINE_WIDTH:
        return path.read_bytes()
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    height = round(image.height * INLINE_WIDTH / image.width)
    image = image.resize((INLINE_WIDTH, height), Image.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=INLINE_QUALITY, optimize=True, progressive=True)
    return buffer.getvalue()


# index.html is a complete document now — doctype, <html lang>, <head>, <body> — because
# a real web host needs all of that (no doctype means quirks mode, and quirks mode
# changes the box model). The artifact host supplies its own skeleton and wraps whatever
# it is given, so those tags are unwrapped here rather than nested a second time.
SHELL = re.compile(r"^\s*<!doctype html>\s*$|^\s*</?(?:html|head|body)(?:\s[^>]*)?>\s*$",
                   re.I | re.M)

# Icons live at the site root and are fetched by relative path; standing alone, those
# paths resolve to nothing. The artifact sets its own favicon, so drop the links.
ICON_LINKS = re.compile(r'^\s*<link rel="(?:apple-touch-)?icon"[^>]*>\s*$\n?', re.I | re.M)


def unwrap(html):
    """Flatten the document back to a fragment the artifact host can wrap."""
    html, shell = SHELL.subn("", html)
    html, icons = ICON_LINKS.subn("", html)
    print(f"  unwrapped {shell} document tag(s), dropped {icons} icon link(s)")
    return re.sub(r"\n{3,}", "\n\n", html)


def main():
    html = unwrap(SRC.read_text())

    # Only inline pages for papers the site actually lists; images/pubs can hold
    # leftovers from papers since dropped (preprints, superseded versions).
    pubs = json.loads((ROOT / "data" / "publications.json").read_text())
    preprint_file = ROOT / "data" / "preprints.json"
    if preprint_file.exists():
        pubs = pubs + json.loads(preprint_file.read_text())
    wanted = {re.sub(r"[^a-z0-9]+", "-", p["doi"].lower()).strip("-") for p in pubs}
    images = sorted(path for path in THUMBS.glob("*.jpg") if path.stem in wanted)
    if not images:
        print("no page renders in images/pubs — run scripts/render_first_pages.py first")
        return 1

    # images/pubs holds full-resolution page renders, which is right for a hosted site
    # where they load lazily and get cached. Inlining them all at that size would make a
    # multi-megabyte page, so shrink to roughly what the tile actually displays.
    encoded = {path.stem: "data:image/jpeg;base64," + base64.b64encode(shrink(path)).decode()
               for path in images}

    # The page builds each src as THUMB_DIR + slug + ".jpg". Swap that expression for a
    # lookup into an inlined map, falling back to "" so a missing entry still fires the
    # img onerror handler and renders its text tile.
    lookup = "{\n" + ",\n".join(
        '"%s":"%s"' % (stem, uri) for stem, uri in sorted(encoded.items())
    ) + "\n}"

    # The active theme is a local <link>; fold it in so the standalone copy carries it.
    def inline_stylesheet(match):
        rel = match.group(1)
        path = ROOT / rel
        if not path.exists():
            print(f"  warning: {rel} linked but not found; left as-is")
            return match.group(0)
        css = path.read_text()
        # @import must lead a stylesheet, so lift the font imports into their own block.
        imports = re.findall(r"^@import[^\n]*;", css, re.M)
        css = re.sub(r"^@import[^\n]*;\s*", "", css, flags=re.M)
        head = "<style>\n" + "\n".join(imports) + "\n</style>\n" if imports else ""
        return head + f'<style data-theme-file="{rel}">\n{css}\n</style>'

    html, themed = re.subn(r'<link rel="stylesheet" href="(styles/[^"]+)">',
                           inline_stylesheet, html)
    if themed:
        print(f"  inlined {themed} local stylesheet(s)")

    data_js = ROOT / "data" / "site-data.js"
    if not data_js.exists():
        print("data/site-data.js missing — run scripts/embed_publications.py first")
        return 1
    html, inlined_data = re.subn(
        r'<script src="data/site-data\.js"></script>',
        lambda m: "<script>\n" + data_js.read_text() + "</script>",
        html, count=1,
    )
    if not inlined_data:
        print("could not find the site-data.js include in index.html")
        return 1

    old = 'var THUMB_DIR = "images/pubs/";'
    if old not in html:
        print("could not find the THUMB_DIR declaration in index.html")
        return 1
    html = html.replace(old, "var THUMBS = " + lookup + ";", 1)

    # Match the src expression by shape rather than exact text, so editing the alt
    # attribute or surrounding markup doesn't silently break the build.
    # Built by concatenation to keep the embedded quote characters readable.
    pattern = r"THUMB_DIR \+ slug\(pub\.doi\) \+ '\.jpg" + '"'
    replacement = "(THUMBS[slug(pub.doi)] || '') + '" + '"'
    html, swapped = re.subn(pattern, replacement, html, count=1)
    if not swapped:
        print("could not find the <img> src expression in index.html")
        return 1

    # Images written straight into the markup (the portrait, any hero art) need the same
    # treatment, or they'd 404 once the page is on its own.
    def inline_static(match):
        rel = match.group(1)
        path = ROOT / rel
        if not path.exists():
            print(f"  warning: {rel} referenced but not found; left as-is")
            return match.group(0)
        suffix = path.suffix.lower()
        if suffix == ".gif":
            # Never send a GIF through Pillow's resize/JPEG path — that keeps only the
            # first frame and the animation dies. Inline the file byte for byte.
            mime, blob = "image/gif", path.read_bytes()
        else:
            mime = "image/png" if suffix == ".png" else "image/jpeg"
            blob = shrink(path)
        data = base64.b64encode(blob).decode()
        return f'src="data:{mime};base64,{data}"'

    html, static_count = re.subn(r'src="(images/(?!pubs/)[^"]+)"', inline_static, html)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"  inlined {static_count} static image(s) from images/")

    size = OUT.stat().st_size
    print(f"wrote {OUT.relative_to(ROOT)} — {len(encoded)} images inlined, {size / 1e6:.1f} MB")
    if size > SIZE_WARN:
        print("warning: page is large; consider lowering INLINE_WIDTH above")
    return 0


if __name__ == "__main__":
    sys.exit(main())
