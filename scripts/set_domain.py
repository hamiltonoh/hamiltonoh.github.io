#!/usr/bin/env python3
"""Point the site at a domain, and write the files a search engine looks for.

Every absolute URL on the site — the canonical link, the Open Graph tags, the
JSON-LD identifiers — has to name the real domain, so they all have to move
together. This is the one place that happens.

    python3 scripts/set_domain.py hamiltonoh.me    switch to a new domain
    python3 scripts/set_domain.py                  regenerate using the current one

It rewrites index.html in place and (re)writes robots.txt, sitemap.xml, 404.html,
CNAME and _headers at the top level. All of those belong in the upload.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

VALID = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


def current_domain(html):
    """The domain the page already claims, taken from its canonical link."""
    match = re.search(r'<link rel="canonical" href="https://([^/"]+)/?"', html)
    if not match:
        raise SystemExit("no <link rel=\"canonical\"> in index.html — cannot tell "
                         "which domain to replace. Add one and re-run.")
    return match.group(1)


NOT_FOUND = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page not found | Hamilton Se-Hwee Oh</title>
<meta name="robots" content="noindex">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400&family=Barlow:wght@400&display=swap">
<style>
  body {{
    margin: 0; min-height: 100vh; background: #FFFFFF; color: #3C4043;
    font-family: "Barlow", Helvetica, Arial, sans-serif; font-size: 16.5px; line-height: 1.62;
    display: flex; align-items: center; justify-content: center; padding: 40px;
  }}
  main {{ max-width: 420px; }}
  h1 {{
    margin: 0 0 14px; color: #0B0B0C; font-weight: 400; font-size: 44px; line-height: 1;
    font-family: "Barlow Condensed", "Barlow", Helvetica, sans-serif;
  }}
  p {{ margin: 0; }}
  a {{ color: #D8261B; text-decoration: none; border-bottom: 1px solid currentColor; }}
</style>
</head>
<body>
<main>
  <h1>Page not found</h1>
  <p>Nothing lives at that address. <a href="https://{domain}/">Go to the front page</a>.</p>
</main>
</body>
</html>
"""

# Images are named after a paper's DOI and effectively never change, so a week of
# caching is safe and saves a repeat visitor the whole payload. index.html changes
# whenever a paper is added, so it must always be revalidated.
HEADERS = """# Netlify and Cloudflare Pages read this file. Other hosts ignore it.

/images/*
  Cache-Control: public, max-age=604800

/styles/*
  Cache-Control: public, max-age=604800

/data/*
  Cache-Control: public, max-age=86400

/index.html
  Cache-Control: public, max-age=0, must-revalidate

/
  Cache-Control: public, max-age=0, must-revalidate
"""


def main():
    html = INDEX.read_text()
    old = current_domain(html)

    if len(sys.argv) > 2:
        raise SystemExit(__doc__)
    new = sys.argv[1].strip().lower() if len(sys.argv) == 2 else old
    new = re.sub(r"^https?://", "", new).rstrip("/")
    if not VALID.match(new):
        raise SystemExit(f"{new!r} does not look like a domain name")

    if new != old:
        html, count = re.subn(r"https://" + re.escape(old), "https://" + new, html)
        INDEX.write_text(html)
        print(f"index.html — {count} absolute URL(s): {old} -> {new}")
    else:
        print(f"index.html — already pointing at {new}")

    # git records when the page last actually changed; the file's own mtime moves
    # every time anything is rebuilt, which would make lastmod meaningless.
    stamp = time.strftime("%Y-%m-%d", time.gmtime(INDEX.stat().st_mtime))
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", "index.html"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            stamp = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    written = {
        "robots.txt": (
            "User-agent: *\n"
            "Allow: /\n\n"
            f"Sitemap: https://{new}/sitemap.xml\n"
        ),
        "sitemap.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <url>\n"
            f"    <loc>https://{new}/</loc>\n"
            f"    <lastmod>{stamp}</lastmod>\n"
            "  </url>\n"
            "</urlset>\n"
        ),
        # GitHub Pages reads CNAME to serve the custom domain. Harmless elsewhere.
        "CNAME": new + "\n",
        "404.html": NOT_FOUND.format(domain=new),
        "_headers": HEADERS,
    }
    for name, body in written.items():
        (ROOT / name).write_text(body)
    print("wrote " + ", ".join(written))
    print(f"\nSite is now https://{new}/ — rebuild with ./build.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
