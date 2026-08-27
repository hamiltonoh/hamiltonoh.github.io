# hamiltonsehweeoh.com

A static personal site. One HTML file, a handful of Python scripts, no framework and
no build tooling beyond Python. Everything needed to rebuild it lives in this folder.

## Quick start

```bash
python3 -m http.server 4321     # then open http://localhost:4321
```

Rebuild after adding a paper or a PDF:

```bash
./build.sh                      # or: ./build.sh --local  to skip network calls
```

## What to edit

**All prose lives in `index.html`.** Open it in any editor and type. Each section
starts with a comment banner — search for the name in capitals:

| Search for | Holds |
|---|---|
| `ABOUT ME` | the portrait and the bio paragraph (no heading — it runs straight in) |
| `NOW` | the c-Fos figure, the Russo paragraph, the numbered questions, the Goate paragraph |
| `PREVIOUSLY` | three research themes, each with an image, a description and key papers |
| `PUBLICATIONS` | the heading and the three tabs — the papers themselves are generated |
| `TALKS` | every invited talk, one `<div class="venue">` per row |
| `CODE` | the four repositories |
| `CONTACT` | email, social links and their inline SVG icons |

The `SEARCH & SHARING` block at the very top holds the page title and the description
Google shows underneath it. Those are worth editing; the absolute URLs beside them are
not — see **Domain** below.

To add a talk, copy an existing row and edit the three spans — name, place, date.
Rows are listed newest first; nothing sorts them for you.

Three things you should *not* hand-edit: `data/site-data.js`, `dist/`, and the block
between the `PUBLICATION-FALLBACK` markers inside `index.html` — all generated.

**Editing CSS?** Your browser caches `styles/*.css`, so a change can look like it did
nothing. Hard-reload with Cmd+Shift+R. Editing `index.html` has no such problem.

## Look and feel

The active theme is one line near the top of `index.html`:

```html
<link rel="stylesheet" href="styles/swiss-mid-light.css">
```

Swap the filename to change the whole design. Three themes are kept:

- `swiss-mid-light.css` — **adopted.** White ground, Barlow Condensed, one red accent,
  sentence case, light headings. Its header comment explains how to restore bold headings.
- `swiss.css` — the same language at poster scale: much larger uppercase headings.
- `signal.css` — a quieter alternative in plain Barlow rather than condensed.

`python3 scripts/make_variants.py` renders every theme in `styles/` to
`dist/style-<name>.html` so they can be compared side by side. Those previews are
~11 MB each and safe to delete; regenerate whenever you want them.

## What is generated

The publication list is built from your ORCID record, enriched with Crossref
(authors, citation counts) and Europe PMC (abstracts). Each card image is page one of
that paper's PDF.

```
scripts/refresh_publications.py   ORCID -> data/publications.json + data/preprints.json
scripts/match_pdfs.py             names loose PDFs by the DOI printed inside them
scripts/render_first_pages.py     PDF page 1 -> images/pubs/<doi-slug>.jpg
scripts/embed_publications.py     the two JSON files -> data/site-data.js, and the
                                  no-JavaScript list inside index.html
scripts/build_artifact.py         index.html + images -> dist/index.html (standalone)
scripts/make_variants.py          styles/*.css -> dist/style-*.html (theme previews)
scripts/make_social_images.py     portrait -> og-card.jpg, favicon.ico, icon.svg
scripts/set_domain.py             domain    -> robots.txt, sitemap.xml, CNAME, 404.html
```

### Adding a paper

1. If it is on your ORCID record, `./build.sh` picks it up.
2. If not — consortium papers often are not — add the DOI to `EXTRA_DOIS` at the top of
   `scripts/refresh_publications.py`. Adding it to ORCID instead is better; then you can
   delete the line.
3. Drop the PDF anywhere in `pdfs/` (any filename) and run `./build.sh`. It is identified
   by the DOI printed inside it, filed under `pdfs/published/` or `pdfs/preprints/`, and
   its first page rendered.

Paywalled papers cannot be fetched automatically, so supplying your own reprint is what
fills those gaps. A local PDF always wins over a fetched one.

### Other hand-maintained lists

All near the top of `scripts/refresh_publications.py`:

- `EXTRA_DOIS` — papers missing from ORCID.
- `CO_FIRST` — papers whose byline carries an asterisk, written as
  `"<doi>": <how many leading authors share first authorship>`. Crossref records author
  order but not shared first authorship, so nothing can detect this; it has to be typed.

  **Add a line here whenever a new paper has co-first authors** — including papers where
  you are not one of them. The site then prints a `*` after each of those names wherever
  the paper appears, adds *\*equal contribution* to the card, and keeps the paper in the
  "First author" view when you are the second of two co-firsts.
- `SUPERSEDED` — maps a preprint DOI to its published version, for cases where the title
  changed too much on acceptance for automatic matching.

A preprint drops off the site once its published version appears, or if it has no PDF.

## Domain

The site is `hamiltonsehweeoh.com`. That name appears in about twenty places — the
canonical link, the Open Graph tags, the JSON-LD, `sitemap.xml`, `robots.txt`,
`CNAME`, `404.html` — and they all have to agree, so one script owns all of them:

```bash
python3 scripts/set_domain.py somethingelse.com
```

Never change a URL by hand. `./build.sh` re-runs the script with the current domain
on every build, which is also what keeps `sitemap.xml`'s date current.

## Deploying

**Upload `index.html`, `data/`, `images/`, `styles/`, and the files at the top level:**
`robots.txt`, `sitemap.xml`, `404.html`, `favicon.ico`, `icon.svg`,
`apple-touch-icon.png`, `_headers` and `CNAME`. That is the whole site — about 11 MB.
It is static, so GitHub Pages, Netlify, Cloudflare Pages or any web host serves it as-is.

Two of those are read only by particular hosts and ignored everywhere else: `CNAME` by
GitHub Pages, `_headers` by Netlify and Cloudflare Pages.

`dist/index.html` is a *separate* single-file copy with every image inlined as a data
URI (~12 MB). It exists only for sharing the page as one self-contained file — a
preview link, an email attachment. Do not deploy it; it defeats image caching, and the
document shell a real host needs is stripped out of it.

`pdfs/` and `source/` are working material and do not need uploading.

## Being findable

Searching for "Hamilton Oh" is never going to land here first — `OH` is the postal
abbreviation for Ohio, and Hamilton, Ohio has 63,000 residents and a city government
with a large website. The realistic targets are **"Hamilton Se-Hwee Oh"**,
**"Hamilton Oh Mount Sinai"** and **"Hamilton Oh organ aging"**, and the domain was
chosen to match the first of those exactly.

What the page already does for itself:

- one `<h1>` naming the subject, and a `<h2>` per section
- JSON-LD `Person` data whose `sameAs` list ties this page to the ORCID, Scholar,
  GitHub, X and LinkedIn records that already rank for the name. This is the piece
  that tells Google the page and those profiles are one person rather than five.
- every paper present as plain text in the served HTML, not only as JavaScript output
- `sitemap.xml`, `robots.txt`, a canonical URL, and a link-preview card

What the page cannot do for itself, in rough order of how much it matters — a new
domain has no reputation, and links from sites that already have one are most of what
fixes that:

1. Add the URL to your **ORCID** record (Websites & Social Links).
2. Add it to **Google Scholar** → Profile → Edit → Homepage.
3. Ask for it on your **Mount Sinai** faculty/lab page. A `.edu` link is the single
   most valuable one available to you.
4. Put it in your **LinkedIn** contact info, your **GitHub** profile, and your **X** bio.
5. Verify the site in **Google Search Console** and **Bing Webmaster Tools**, and submit
   the sitemap. Search Console is also where you find out what people actually searched
   to reach you.
6. Use it in email signatures, talk slides, and preprint author notes.

Expect a few weeks before the page settles into position, and longer before it outranks
anything for the ambiguous short query.

## Layout

```
index.html            the site — all prose, base CSS, and JS
build.sh              rebuild everything
robots.txt            generated: crawler rules, points at the sitemap
sitemap.xml           generated: the one URL, with a last-modified date
404.html              generated: shown for a bad address
CNAME                 generated: the custom domain, for GitHub Pages
_headers              generated: cache lifetimes, for Netlify / Cloudflare Pages
favicon.ico           generated: tab icon, 16 / 32 / 48px
icon.svg              generated: the same mark as vector
apple-touch-icon.png  generated: 180x180, for an iOS home screen
styles/               themes; one is linked from index.html
data/
  publications.json   generated: peer-reviewed papers
  preprints.json      generated: preprints with no published version yet
  site-data.js        generated: what the page actually loads
images/
  hamilton-oh.jpg     portrait (resized to 640px wide by the build)
  og-card.jpg         generated: 1200x630 link-preview card
  now-brain-cfos.gif  c-Fos animation in the Now section
  theme-*.jpg         one image per Previously theme
  talk-goldlab.jpg    talk recording thumbnail
  pubs/               generated: first-page render per paper
pdfs/
  published/          your reprints, named <doi-slug>.pdf
  preprints/          same, for preprints
source/               original photos, figures, CV, biosketch
  fonts/              cached Barlow files, fetched once for the preview card
dist/                 generated: standalone single-file copy
```

## Notes

- Deliberately light-only, in the manner of an academic lab site.
- Publication cards scroll horizontally, three at a time, across three tabs.
- Rendering crops any personal download watermark ("Downloaded from … at Icahn School of
  Medicine …") out of the page margin before it reaches the site.
- The c-Fos GIF is cropped with CSS, never re-encoded — Pillow silently collapses its 316
  frames to 21 on a re-save.
- bioRxiv rate-limits aggressively. If a preprint fails to download, wait and re-run, or
  save the PDF yourself into `pdfs/preprints/`.
