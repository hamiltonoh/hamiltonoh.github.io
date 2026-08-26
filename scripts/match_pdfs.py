#!/usr/bin/env python3
"""Rename PDFs in pdfs/ to the <doi-slug>.pdf names render_first_pages.py expects.

Publisher downloads arrive named things like `1-s2.0-S0092867422014635-main.pdf` or
`s41586-023-06802-1.pdf`. Rather than renaming by hand, identify each file by the DOI
printed inside it and match that against data/publications.json.

    python3 scripts/match_pdfs.py [--dry-run]

Anything that can't be matched confidently is listed and left alone.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "pdfs"
PUBLISHED_DIR = PDF_DIR / "published"
PREPRINT_DIR = PDF_DIR / "preprints"

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.I)


def slug(doi):
    return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")


def normalize(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def dois_in_pdf(path, pages=2):
    """Collect every DOI-looking string from the opening pages and the metadata."""
    found = []
    with fitz.open(path) as document:
        meta = " ".join(str(v) for v in (document.metadata or {}).values() if v)
        found += DOI_RE.findall(meta)
        for index in range(min(pages, document.page_count)):
            found += DOI_RE.findall(document[index].get_text())
    # Trailing punctuation and line-wrap artefacts cling to DOIs in extracted text.
    return [d.rstrip(".,;)") for d in found]


def title_of(path):
    """First page's largest-type line, which is nearly always the article title."""
    with fitz.open(path) as document:
        if not document.page_count:
            return ""
        blocks = document[0].get_text("dict")["blocks"]
        spans = [
            (span["size"], span["text"])
            for block in blocks for line in block.get("lines", [])
            for span in line.get("spans", []) if span["text"].strip()
        ]
    if not spans:
        return ""
    biggest = max(size for size, _ in spans)
    return " ".join(text for size, text in spans if size >= biggest - 0.5)


def identify(path, pubs):
    """Return (doi, how) for a PDF, or (None, reason)."""
    known = {p["doi"].lower(): p for p in pubs}

    # 1. a DOI printed in the file that we recognise
    for doi in dois_in_pdf(path):
        if doi.lower() in known:
            return known[doi.lower()]["doi"], "DOI in file"

    # 2. the filename carries the DOI suffix (publisher download names often do)
    stem = normalize(path.stem)
    for doi, pub in known.items():
        suffix = normalize(doi.split("/", 1)[1])
        if suffix and suffix in stem:
            return pub["doi"], "DOI suffix in filename"

    # 3. fall back to matching the title printed on page one
    title = normalize(title_of(path))
    if len(title) > 25:
        for pub in pubs:
            target = normalize(pub["title"])
            if title[:60] in target or target[:60] in title:
                return pub["doi"], "title match"

    return None, "no match"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report matches without renaming")
    args = parser.parse_args()

    pubs = json.loads((ROOT / "data" / "publications.json").read_text())
    preprint_path = ROOT / "data" / "preprints.json"
    preprints = json.loads(preprint_path.read_text()) if preprint_path.exists() else []
    is_preprint = {p["doi"] for p in preprints}
    pubs = pubs + preprints

    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    PREPRINT_DIR.mkdir(parents=True, exist_ok=True)
    # Scan the loose folder and both subfolders, so a publisher-named file dropped
    # straight into pdfs/published/ still gets identified and renamed.
    files = sorted(set(PDF_DIR.glob("*.pdf")) | set(PUBLISHED_DIR.glob("*.pdf"))
                   | set(PREPRINT_DIR.glob("*.pdf")))
    if not files:
        print(f"no PDFs in {PDF_DIR.relative_to(ROOT)}")
        return 1

    matched, unmatched = {}, []
    for path in files:
        doi, how = identify(path, pubs)
        if not doi:
            unmatched.append(path)
            print(f"  ?  {path.name}  — {how}")
            continue
        folder = PREPRINT_DIR if doi in is_preprint else PUBLISHED_DIR
        target = folder / f"{slug(doi)}.pdf"
        if target == path:
            print(f"  =  {path.name}  already in place")
            matched[doi] = target
            continue
        if target.exists():
            print(f"  !  {path.name} → {target.name} already exists, skipping")
            continue
        print(f"  ✓  {path.name}\n     → {folder.name}/{target.name}   ({how})")
        if not args.dry_run:
            path.rename(target)
        matched[doi] = target

    print(f"\n{len(matched)}/{len(files)} PDFs identified"
          + ("  (dry run, nothing renamed)" if args.dry_run else ""))

    listed = {p["doi"] for p in pubs}
    def have(pub):
        name = f"{slug(pub['doi'])}.pdf"
        return (PUBLISHED_DIR / name).exists() or (PREPRINT_DIR / name).exists()

    still_missing = [p for p in pubs if p["doi"] not in matched and not have(p)]
    if still_missing:
        print("\nPapers on the site with no PDF supplied:")
        for pub in still_missing:
            print(f"  · {pub['year']} {pub['journal']}: {pub['title'][:56]}")
            folder = "preprints" if pub["doi"] in is_preprint else "published"
            print(f"      wants pdfs/{folder}/{slug(pub['doi'])}.pdf")
    extra = [d for d in matched if d not in listed]
    if extra:
        print("\nPDFs matched to papers not listed on the site:")
        for doi in extra:
            print(f"  · {doi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
