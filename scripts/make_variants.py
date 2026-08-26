#!/usr/bin/env python3
"""Build a style preview for each stylesheet in styles/.

Each variant is dist/index.html — the standalone build, images already inlined —
with one theme stylesheet appended after the page's own <style>. The themes
override tokens and selectors rather than replacing the base CSS, so the markup
and behaviour stay identical and only the look changes.

    python3 scripts/make_variants.py

Writes dist/style-<name>.html for each. Open them next to dist/index.html to
compare. To adopt one, see the note this prints at the end.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "dist" / "index.html"
STYLES = ROOT / "styles"
OUT = ROOT / "dist"


def main():
    if not BASE.exists():
        print("dist/index.html missing — run scripts/build_artifact.py first")
        return 1

    html = BASE.read_text()

    # dist/index.html has the adopted theme folded in. Remove it so each preview shows
    # its own theme against the bare base, not stacked on top of the current one.
    html, removed = re.subn(r'<style data-theme-file="[^"]*">.*?</style>\n?', '', html, flags=re.S)
    if removed:
        print(f"  (removed {removed} adopted theme block from the base)")
    themes = sorted(STYLES.glob("*.css"))
    if not themes:
        print(f"no stylesheets in {STYLES.relative_to(ROOT)}")
        return 1

    # The theme goes in immediately after the page's own stylesheet, so its rules win
    # on equal specificity without needing !important anywhere.
    close = html.rindex("</style>") + len("</style>")

    for theme in themes:
        css = theme.read_text()

        # @import has to sit at the top of a stylesheet, so lift the font imports into
        # their own <style> ahead of the theme block. Match to end of line rather than
        # to the first semicolon — Google Fonts URLs contain semicolons of their own
        # (family=Barlow:wght@400;500;600), and cutting there leaves broken CSS behind.
        imports = re.findall(r'^@import[^\n]*;', css, re.M)
        css = re.sub(r'^@import[^\n]*;\s*', '', css, flags=re.M)

        block = ""
        if imports:
            block += "\n<style>\n" + "\n".join(imports) + "\n</style>"
        block += f'\n<style data-theme-name="{theme.stem}">\n{css}\n</style>'

        page = html[:close] + block + html[close:]
        # Give each preview its own <title> so the variants are tellable apart in a
        # browser tab or an artifact gallery.
        page = page.replace("<title>Hamilton Oh</title>",
                            f"<title>{theme.stem.title()} — style preview</title>", 1)

        dest = OUT / f"style-{theme.stem}.html"
        dest.write_text(page)
        print(f"  wrote {dest.relative_to(ROOT)}  ({dest.stat().st_size / 1e6:.1f} MB)")

    print("\nCompare against dist/index.html (the current look).")
    print("To adopt one: append its CSS to the <style> block in index.html,")
    print("or add <link rel=\"stylesheet\" href=\"styles/<name>.css\"> after it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
