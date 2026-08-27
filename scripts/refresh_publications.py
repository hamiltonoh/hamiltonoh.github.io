#!/usr/bin/env python3
"""Rebuild data/publications.json from ORCID, Crossref, and Europe PMC.

Run this whenever a new paper lands. It reads the ORCID record as the source of
truth for *which* works exist, then enriches each one with author position and
citation count from Crossref and an abstract from Europe PMC.

    python3 scripts/refresh_publications.py

Then run scripts/embed_publications.py to fold the result back into index.html.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ORCID = "0000-0001-8192-7593"
UA = {
    "User-Agent": f"hamiltonoh.com publication refresh (orcid:{ORCID})",
    # ORCID serves XML unless JSON is asked for explicitly.
    "Accept": "application/json",
}
ROOT = Path(__file__).resolve().parent.parent

# DOI prefixes that identify preprint servers rather than journals.
PREPRINT_PREFIXES = ("10.1101", "10.21203", "10.64898")

# Works that are about Hamilton rather than by him, excluded from the paper list.
SKIP_TITLE_PREFIXES = ("Hamilton Oh: A journey",)

# Papers missing from the ORCID record. Large consortium papers often are, because no
# one claims them individually. Adding the DOI to ORCID is the better fix — then it can
# be deleted from here — but this keeps the site correct in the meantime.
EXTRA_DOIS = (
    "10.1038/s41591-025-03834-0",   # Global Neurodegeneration Proteomics Consortium, Nat Med 2025
    "10.1038/s41586-025-09987-9",   # Ageing promotes microglial accumulation…, Nature
    "10.1038/s41586-026-10524-5",   # Sleep chart of biological ageing clocks, Nature
    "10.1016/j.neuron.2026.02.035",  # Large-scale CSF and plasma proteomics, Neuron 2026
    "10.1016/j.celrep.2025.116624",  # Cerebellar microglia with aging, Cell Reports 2025
    "10.1016/j.landig.2025.01.006",  # Whitehall II organ ageing, Lancet Digital Health 2025
    "10.1002/advs.202513872",        # APOE-stratified proteomics/metabolomics, Advanced Science
)

# Preprints whose published version is already listed. Titles change enough on
# acceptance that automatic matching can't be relied on, so the pairs are explicit.
SUPERSEDED = {
    "10.64898/2026.02.10.704909": "10.1038/s41591-026-04446-y",   # Cellular aging signatures
    "10.1101/2025.03.01.640978":  "10.1016/j.celrep.2025.116624",  # Cerebellar microglia
}

# Crossref records author order but not shared first authorship, so papers whose
# bylines carry an asterisk are listed here by hand: DOI -> how many of the leading
# authors share first authorship. The site puts a * after each of those names and a
# note on the card, and without this the "First author" view silently drops any paper
# where Hamilton is second of two co-firsts.
#
# ADD A LINE HERE whenever a new paper has co-first authors — including papers where
# Hamilton is not one of them. Two is the usual count; use whatever the byline says.
CO_FIRST = {
    "10.1038/s41576-022-00511-7": 2,   # Rutledge J*, Oh H*  — Nature Reviews Genetics 2022
    "10.1038/s41586-023-06802-1": 2,   # Oh HS*, Rutledge J* — Nature 2023
}


def get_json(url, timeout=30):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))


# Sub/superscripts bind tight to the text before them, and Crossref often pretty-prints
# newlines around the tags (CD4\n  <sup>+</sup>\n  T cells). Eat the whitespace that leads
# into each tag — but not the space *after* a closing tag, or "CD4+ T cells" loses its gap.
SCRIPT_TAGS = r"sub|sup"
# Other inline tags carry no spacing of their own; drop them and leave the text alone.
INLINE_TAGS = r"i|b|em|strong|italic|bold|sc|inline-formula|tex-math"


def clean(text):
    """Strip the JATS/HTML markup that Crossref and Europe PMC leave in strings."""
    text = text or ""
    text = re.sub(rf"\s*<(?:{SCRIPT_TAGS})(?:\s[^>]*)?>\s*", "", text, flags=re.I)
    text = re.sub(rf"\s*</(?:{SCRIPT_TAGS})>", "", text, flags=re.I)
    text = re.sub(rf"</?(?:{INLINE_TAGS})(?:\s[^>]*)?>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(entity, char)
    text = re.sub(r"\s+([,.;:)])", r"\1", text)   # tidy punctuation left stranded
    # stripped italics can leave a gap before a word-joining hyphen: "APOE ‐stratified"
    text = re.sub(r"\s+([\u2010\u2011])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def orcid_dois():
    data = get_json(f"https://pub.orcid.org/v3.0/{ORCID}/works")
    dois = []
    for group in data["group"]:
        ids = {i["external-id-type"]: i["external-id-value"] for i in group["external-ids"]["external-id"]}
        if ids.get("doi"):
            dois.append(ids["doi"])

    known = {d.lower() for d in dois}
    for doi in EXTRA_DOIS:
        if doi.lower() not in known:
            dois.append(doi)
            print(f"  added manually (not on ORCID): {doi}")
    return dois


def author_name(entry):
    """Crossref gives people given/family, but consortia a single `name` field."""
    if entry.get("name"):
        return entry["name"]
    return f"{entry.get('given', '')} {entry.get('family', '')}".strip()


def crossref(doi):
    msg = get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")["message"]
    authors = [name for name in map(author_name, msg.get("author", [])) if name]
    position = next((i + 1 for i, a in enumerate(authors) if "Oh" in a and ("Hamilton" in a or "H." in a)), None)
    journal = clean((msg.get("container-title") or [""])[0])
    # Hamilton is a co-first author only if he is actually among the shared positions,
    # not merely on a paper that has them.
    shared = CO_FIRST.get(doi, 0)
    co_first = bool(position and position <= shared)
    return {
        "doi": doi,
        "first": position == 1 or co_first,
        "cofirst": co_first,
        "shared": shared,
        "title": clean(msg.get("title", [""])[0]),
        "journal": journal or "Preprint",
        "year": msg.get("issued", {}).get("date-parts", [[None]])[0][0],
        "pos": position,
        "n": len(authors),
        "authors": [clean(a) for a in authors],
        "senior": clean(authors[-1]) if authors else "",
        "cites": msg.get("is-referenced-by-count") or 0,
        "preprint": any(doi.startswith(p) for p in PREPRINT_PREFIXES) or not journal,
        "abstract": clean(msg.get("abstract", "")),
    }


def europepmc_abstract(doi):
    query = urllib.parse.quote(f'DOI:"{doi}"')
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={query}&resultType=core&format=json&pageSize=1"
    )
    results = get_json(url)["resultList"]["result"]
    return clean(results[0].get("abstractText", "")) if results else ""


STOPWORDS = {"the", "of", "and", "in", "a", "an", "for", "with", "to", "across", "on", "human"}


def title_tokens(title):
    words = re.findall(r"[a-z]+", title.lower())
    # crude stemming so "proteome"/"proteomic"/"proteomics" and "signature"/"signatures" match
    return {w[:7].rstrip("s") for w in words if w not in STOPWORDS and len(w) > 3}


def same_paper(a, b):
    """Is one of these the preprint of the other?

    Journals routinely retitle a paper on acceptance, so exact-title matching misses those
    pairs. Require the same year, the same first and senior author, and a substantially
    overlapping title before merging — matching on authors and year alone would wrongly
    collapse two genuine papers from the same group in the same year.
    """
    if a["preprint"] == b["preprint"] or a["year"] != b["year"]:
        return False
    if not (a["authors"] and b["authors"]):
        return False
    if a["authors"][0] != b["authors"][0] or a["senior"] != b["senior"]:
        return False
    ta, tb = title_tokens(a["title"]), title_tokens(b["title"])
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.3


def dedupe(pubs):
    """Collapse preprint/journal pairs of the same paper, preferring the journal version."""
    # pass 1: identical titles
    best = {}
    for pub in pubs:
        key = re.sub(r"[^a-z0-9]", "", pub["title"].lower())[:80]
        current = best.get(key)
        beats_current = current is None or (
            (current["preprint"] and not pub["preprint"])
            or (current["preprint"] == pub["preprint"] and pub["cites"] > current["cites"])
        )
        if beats_current:
            best[key] = pub

    # pass 2: retitled preprints, matched on year, authors, and title overlap
    kept = []
    for pub in best.values():
        match = next((k for k in kept if same_paper(k, pub)), None)
        if match is None:
            kept.append(pub)
        elif match["preprint"] and not pub["preprint"]:
            kept[kept.index(match)] = pub   # the journal version wins
        else:
            print(f"  merged preprint: {pub['title'][:58]}")

    return sorted(kept, key=lambda p: (-(p["year"] or 0), -p["cites"]))


def main():
    pubs = []
    for doi in orcid_dois():
        try:
            pub = crossref(doi)
        except Exception as exc:  # a single unreachable DOI shouldn't sink the whole refresh
            print(f"  skipped {doi}: {exc}")
            continue
        if any(pub["title"].startswith(p) for p in SKIP_TITLE_PREFIXES):
            continue
        if not pub["abstract"]:
            try:
                pub["abstract"] = europepmc_abstract(doi)
            except Exception:
                pass
        pubs.append(pub)
        print(f"  {pub['year']} {pub['journal'][:28]:28s} {pub['title'][:52]}")
        time.sleep(0.15)

    pubs = dedupe(pubs)

    published = [p for p in pubs if not p["preprint"]]
    published_dois = {p["doi"].lower() for p in published}

    # A preprint belongs on the site only until its journal version appears.
    preprints = []
    for pub in (p for p in pubs if p["preprint"]):
        replacement = SUPERSEDED.get(pub["doi"])
        if replacement and replacement.lower() in published_dois:
            print(f"  superseded by {replacement}: {pub['title'][:44]}")
            continue
        preprints.append(pub)

    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    (data / "publications.json").write_text(json.dumps(published, indent=1) + "\n")
    (data / "preprints.json").write_text(json.dumps(preprints, indent=1) + "\n")

    first = sum(1 for p in published if p["first"])
    print(f"\nwrote data/publications.json — {len(published)} papers, {first} first-author, "
          f"{sum(p['cites'] for p in published)} citations")
    print(f"wrote data/preprints.json    — {len(preprints)} preprints")


if __name__ == "__main__":
    main()
