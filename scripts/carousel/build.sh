#!/usr/bin/env bash
# scripts/carousel/build.sh — renders presentation.html to carousel.pdf via
# Playwright's chromium in headless print mode: deterministic, no manual
# print dialog, no browser UI involved.
#
# Two Playwright PDF options matter here, not just defaults:
#   - prefer_css_page_size=True: respects the CSS's own
#     @page { size: 1080px 1080px; margin: 0 } rule instead of defaulting
#     to a fixed paper format (Letter/A4) that would rescale every slide.
#   - print_background=True: Chromium drops CSS background colors by
#     default when printing to save ink — without this, the palette
#     (status badges, the dark terminal blocks, the harness-box shading)
#     would render as plain white. Same concern report_html.py's own
#     print-color-adjust rule addresses in the browser print-dialog path;
#     this is the equivalent for Playwright's own PDF path.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! python3 -c "import playwright" >/dev/null 2>&1; then
  echo "playwright (Python) not installed — see scripts/carousel/README.md for prerequisites." >&2
  exit 1
fi

HTML_PATH="$SCRIPT_DIR/presentation.html"
PDF_PATH="$SCRIPT_DIR/carousel.pdf"

python3 - "$HTML_PATH" "$PDF_PATH" <<'PY'
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

html_path = Path(sys.argv[1]).resolve()
pdf_path = Path(sys.argv[2]).resolve()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(html_path.as_uri())
    page.wait_for_load_state("networkidle")
    page.pdf(
        path=str(pdf_path),
        print_background=True,
        prefer_css_page_size=True,
    )
    browser.close()

print(f"Wrote {pdf_path}")
PY
