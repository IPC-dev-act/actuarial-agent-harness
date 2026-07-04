#!/usr/bin/env python3
"""scripts/record_demo/record_report.py — Clip B's report-review segment.

Opens the newest run folder's report.html in a real Chromium browser via
Playwright and records a short video: smooth-scroll top to bottom, hover one
figure's trace tooltip for 2s, hold 3s on the development-triangle visual,
hold 3s on the governance footer, then close.

Selectors below are read from harness/render/templates/report.html and
harness/render/report_html.py, not guessed:
  - `span.fig` — every traceable figure (title attribute carries its source
    field, e.g. "fit.json: totals.ibnr"; see report_html.py's `_fig` helper).
  - `.triangle-wrap` — wraps the development-triangle grid (`table.triangle-grid`).
  - `#governance` — the governance footer section (`<section id="governance"
    class="footer">`, report_html.py Section 8).

Prerequisites: pip install playwright && playwright install chromium
(see scripts/record_demo/README.md).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed — see scripts/record_demo/README.md", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_ROOT = REPO_ROOT / "runs"
OUTPUT_DIR = Path(__file__).resolve().parent

VIEWPORT = {"width": 1920, "height": 1080}

_SMOOTH_SCROLL_JS = """
() => new Promise((resolve) => {
  const step = () => {
    window.scrollBy(0, 18);
    if (window.scrollY + window.innerHeight < document.body.scrollHeight - 2) {
      requestAnimationFrame(step);
    } else {
      resolve();
    }
  };
  requestAnimationFrame(step);
})
"""


def _newest_report_html() -> Path:
    candidates = [
        d / "report.html"
        for d in RUNS_ROOT.iterdir()
        if d.is_dir() and (d / "report.html").is_file()
    ]
    if not candidates:
        raise SystemExit(
            "no run folder with report.html under runs/ — run "
            "`reserve fit examples/raa.csv --method mack --out runs/` then "
            "`reserve report <run-id> --format-out html --out runs/` first"
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> None:
    report_path = _newest_report_html()
    print(f"Recording {report_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(OUTPUT_DIR),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()
        page.goto(report_path.as_uri())
        page.wait_for_load_state("networkidle")

        # Smooth-scroll top to bottom.
        page.evaluate(_SMOOTH_SCROLL_JS)

        # Hover one figure's trace tooltip for 2s.
        figure = page.locator("span.fig").first
        figure.scroll_into_view_if_needed()
        figure.hover()
        time.sleep(2)

        # Hold 3s on the development-triangle visual.
        triangle = page.locator(".triangle-wrap").first
        triangle.scroll_into_view_if_needed()
        time.sleep(3)

        # Hold 3s on the governance footer.
        footer = page.locator("#governance")
        footer.scroll_into_view_if_needed()
        time.sleep(3)

        context.close()
        browser.close()

    videos = sorted(OUTPUT_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not videos:
        raise SystemExit("playwright did not produce a video file")
    final = OUTPUT_DIR / "report_review.webm"
    videos[-1].rename(final)
    print(f"Wrote {final}")


if __name__ == "__main__":
    main()
