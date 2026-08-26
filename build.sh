#!/usr/bin/env bash
# Rebuild the site end to end.
#
#   ./build.sh          refresh from ORCID/Crossref, render any new first pages, rebuild
#   ./build.sh --local  skip the network; just rebuild from what's already on disk
#
# Safe to re-run: first pages that already exist are left alone unless you pass
# --force to scripts/render_first_pages.py yourself.
#
# To move the site to a different domain, run scripts/set_domain.py <domain> once;
# it is re-run below on every build so sitemap.xml always carries a current date.

set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" != "--local" ]]; then
  echo "==> Refreshing publication list (ORCID -> Crossref -> Europe PMC)"
  python3 scripts/refresh_publications.py

  echo
  echo "==> Filing any new PDFs by the DOI printed inside them"
  python3 scripts/match_pdfs.py

  echo
  echo "==> Rendering first pages for anything new"
  python3 scripts/render_first_pages.py
  echo
fi

echo "==> Writing data/site-data.js and the no-JavaScript publication list"
python3 scripts/embed_publications.py

echo
echo "==> Building the link-preview card and the tab icons"
python3 scripts/make_social_images.py

echo
echo "==> Writing robots.txt, sitemap.xml, CNAME, 404.html, _headers"
python3 scripts/set_domain.py

echo
echo "==> Building the standalone copy in dist/"
python3 scripts/build_artifact.py

echo
echo "Done. Preview with:  python3 -m http.server 4321   then open http://localhost:4321"
