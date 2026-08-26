#!/usr/bin/env python3
"""Render the first page of each paper into images/pubs/ as a JPEG.

The publication grid shows the article's opening page — journal masthead, title,
authors, abstract — the way a reprint looks on a shelf. That means rendering page
one of the PDF, not scraping a figure out of the landing page.

Sources are tried in order:

  1. pdfs/<doi-slug>.pdf      your own reprint, dropped in by hand
  2. Unpaywall's best open-access PDF
  3. the publisher's conventional PDF URL (Nature, BMC, bioRxiv, medRxiv)
  4. the PubMed Central copy

A local PDF always wins, because publisher typesetting looks better than an
accepted-manuscript deposit. For anything paywalled, save your reprint as
pdfs/<doi-slug>.pdf and re-run; the script prints the exact filename it wants.

    python3 scripts/render_first_pages.py [--force]
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "images" / "pubs"
PDF_DIR = ROOT / "pdfs"
PDF_DIRS = (PDF_DIR / "published", PDF_DIR / "preprints", PDF_DIR)
EMAIL = "hamilton.oh@mssm.edu"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

RENDER_DPI = 220          # ~1870px wide, so a ~500px tile stays sharp at 2x and beyond
JPEG_QUALITY = 88
MAX_WIDTH = 1300     # cap on the stored render; see render()


def slug(doi):
    return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")


def fetch(url, timeout=45, retries=2):
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(request, timeout=timeout, context=SSL_CTX)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < retries:
                time.sleep(20 * (attempt + 1))   # bioRxiv throttles aggressively
                continue
            raise


def looks_like_pdf(blob):
    return blob[:5] == b"%PDF-"


def try_download(url):
    if not url:
        return None
    try:
        with fetch(url) as response:
            blob = response.read(60_000_000)
        return blob if looks_like_pdf(blob) else None
    except Exception:
        return None


def unpaywall_pdf(doi):
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={EMAIL}"
    try:
        with fetch(url) as response:
            data = json.loads(response.read(400_000))
    except Exception:
        return None
    locations = [data.get("best_oa_location")] + (data.get("oa_locations") or [])
    for location in locations:
        if not location:
            continue
        blob = try_download(location.get("url_for_pdf"))
        if blob:
            return blob
    return None


def conventional_pdf(doi):
    """Publisher URLs that follow a predictable pattern from the DOI."""
    candidates = []
    if doi.startswith("10.1038/"):
        candidates.append(f"https://www.nature.com/articles/{doi.split('/', 1)[1]}.pdf")
    if doi.startswith("10.1186/"):
        suffix = doi.split("/", 1)[1]
        candidates.append(
            "https://molecularneurodegeneration.biomedcentral.com/counter/pdf/"
            f"10.1186/{suffix}.pdf"
        )
    if doi.startswith("10.21203/"):
        tail = doi.split("/", 1)[1].replace("rs.3.", "").split("/")[0]
        candidates.append(f"https://www.researchsquare.com/article/{tail}/latest.pdf")
    if doi.startswith(("10.1101/", "10.64898/")):
        prefix, tail = doi.split("/", 1)
        for host in ("biorxiv", "medrxiv"):
            for version in ("v1", "v2"):
                candidates.append(f"https://www.{host}.org/content/{prefix}/{tail}{version}.full.pdf")
    for url in candidates:
        blob = try_download(url)
        if blob:
            return blob
    return None


def pmc_pdf(doi):
    query = urllib.parse.quote(f'DOI:"{doi}"')
    search = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={query}&resultType=core&format=json&pageSize=1"
    )
    try:
        with fetch(search) as response:
            results = json.loads(response.read(400_000))["resultList"]["result"]
    except Exception:
        return None
    if not results or not results[0].get("pmcid"):
        return None
    pmcid = results[0]["pmcid"]
    for url in (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextPDF",
        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
    ):
        blob = try_download(url)
        if blob:
            return blob
    return None


# Publisher downloads can carry a personal access stamp rotated into the outer margin
# ("Downloaded from … at <your institution> on <date>"). That should not go on a public
# page, so the margin holding it is cropped away before rendering.
WATERMARK_RE = re.compile(r"downloaded from|by guest on|provided by .* on \d", re.I)


def content_box(page):
    """Page rect minus any outer margin occupied by a download watermark."""
    rect = page.rect
    left, right = rect.x0, rect.x1
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = " ".join(span["text"] for span in line.get("spans", []))
            if not WATERMARK_RE.search(text):
                continue
            x0, _, x1, _ = line["bbox"]
            # Only trust it if it sits in the outer 12% — otherwise it's body text
            # quoting the phrase, and cropping would eat the article.
            if x0 > rect.x0 + rect.width * 0.88:
                right = min(right, x0 - 2)
            elif x1 < rect.x0 + rect.width * 0.12:
                left = max(left, x1 + 2)
    return fitz.Rect(left, rect.y0, right, rect.y1)


def render(blob, dest):
    document = fitz.open(stream=blob, filetype="pdf")
    try:
        if document.page_count == 0:
            raise ValueError("PDF has no pages")
        page = document[0]
        pixmap = page.get_pixmap(dpi=RENDER_DPI, clip=content_box(page))
        if pixmap.width < 200 or pixmap.height < 200:
            raise ValueError(f"page renders too small ({pixmap.width}x{pixmap.height})")
        pixmap.save(dest, jpg_quality=JPEG_QUALITY)

        # Cards display around 478 CSS px, so anything past ~1300 is weight the
        # visitor downloads and never sees. Cap it.
        if pixmap.width > MAX_WIDTH:
            from PIL import Image
            image = Image.open(dest)
            image.load()
            height = round(image.height * MAX_WIDTH / image.width)
            image.convert("RGB").resize((MAX_WIDTH, height), Image.LANCZOS).save(
                dest, "JPEG", quality=86, optimize=True, progressive=True)
            return MAX_WIDTH, height
        return pixmap.width, pixmap.height
    finally:
        document.close()


def source_for(doi):
    """Return (pdf_bytes, label) from the first source that yields a PDF."""
    for folder in PDF_DIRS:
        local = folder / f"{slug(doi)}.pdf"
        if local.exists():
            blob = local.read_bytes()
            if looks_like_pdf(blob):
                return blob, "local reprint"

    for loader, label in (
        (unpaywall_pdf, "Unpaywall"),
        (conventional_pdf, "publisher"),
        (pmc_pdf, "PMC"),
    ):
        blob = loader(doi)
        if blob:
            return blob, label
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-render pages that already exist")
    args = parser.parse_args()

    pubs = json.loads((ROOT / "data" / "publications.json").read_text())
    preprint_path = ROOT / "data" / "preprints.json"
    preprints = json.loads(preprint_path.read_text()) if preprint_path.exists() else []
    is_preprint = {p["doi"] for p in preprints}
    pubs = pubs + preprints
    OUT.mkdir(parents=True, exist_ok=True)
    for folder in PDF_DIRS:
        folder.mkdir(parents=True, exist_ok=True)

    missing = []
    for pub in pubs:
        dest = OUT / f"{slug(pub['doi'])}.jpg"
        label = f"{pub['year']} {pub['journal'][:26]:26s}"

        if dest.exists() and not args.force:
            print(f"  {label} · have {dest.name}")
            continue

        blob, source = source_for(pub["doi"])
        if not blob:
            print(f"  {label} · no PDF found")
            missing.append(pub)
            continue

        # Keep whatever we fetched, so the PDF library ends up complete and the next
        # run works offline.
        if source != "local reprint":
            folder = (PDF_DIR / "preprints") if pub["doi"] in is_preprint else (PDF_DIR / "published")
            folder.mkdir(parents=True, exist_ok=True)
            saved = folder / f"{slug(pub['doi'])}.pdf"
            if not saved.exists():
                saved.write_bytes(blob)
                source += f", saved to {folder.name}/"
        try:
            width, height = render(blob, dest)
            print(f"  {label} · {dest.name} ({width}x{height}) from {source}")
        except Exception as exc:
            print(f"  {label} · render failed: {type(exc).__name__}: {str(exc)[:60]}")
            missing.append(pub)
        time.sleep(0.4)

    print(f"\n{len(pubs) - len(missing)}/{len(pubs)} first pages in {OUT.relative_to(ROOT)}")
    if missing:
        print("\nPaywalled or unavailable — drop your reprint at the path shown and re-run:")
        for pub in missing:
            folder = "preprints" if pub["doi"] in is_preprint else "published"
            print(f"  pdfs/{folder}/{slug(pub['doi'])}.pdf   {pub['journal']}: {pub['title'][:52]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
