#!/usr/bin/env python3
"""Check that every IMMUTABLE block in content-pack.md survives, verbatim,
in a carousel presentation.html.

"Verbatim" here means whitespace-normalised, nothing else: every run of
whitespace (including line-wrap newlines introduced by HTML's own layout)
collapses to a single space before comparison, on both sides. No other
normalisation happens — HTML tags are stripped (via a proper parser, not a
regex, so <style>/<script> contents are excluded from the searchable text
rather than polluting it) and entities are decoded, but literal characters
survive as-is. Two consequences worth knowing before wiring a slide:

- Markdown decoration in the source files (the `**bold**` markers and
  `` `backtick` `` code-spans inside the CLAUDE.md rules pulled into BLOCK 1)
  is part of the extracted text and is NOT stripped here. If a slide design
  renders "Every figure you state must come from a file under `runs/`."
  as styled bold/code text without the literal `**`/backtick characters in
  the page's own text content, this script will (correctly, by its own
  contract) report FAIL for that block. Either keep the literal characters
  visible somewhere in the slide's text (e.g. a caption), or get sign-off
  to trim content-pack.md's block to a designer-approved plain-text
  variant the same way BLOCK 1's PROPOSED TRIM sub-blocks work.
- PROPOSED TRIM and GENERATED blocks are never checked — only lines
  immediately marked "Status: IMMUTABLE" in content-pack.md are. A trim
  isn't checked until it's approved and content-pack.md is updated to mark
  it IMMUTABLE; a GENERATED block (a live run's run-id, a directory
  listing) isn't expected to reproduce byte-for-byte on a future run, so
  checking it would be checking the wrong thing.

Usage:
    python3 verify_carousel.py [path/to/presentation.html]

Defaults to presentation.html next to this script. Exit code 0 if every
IMMUTABLE block passes, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONTENT_PACK = SCRIPT_DIR / "content-pack.md"
DEFAULT_HTML = SCRIPT_DIR / "presentation.html"

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")
STATUS_RE = re.compile(r"^Status:\s*(.*\S)\s*$")
FENCE_RE = re.compile(r"^```")


@dataclass
class ImmutableBlock:
    heading: str
    ordinal: int
    content: str

    @property
    def label(self) -> str:
        return f"{self.heading} — immutable #{self.ordinal}"


def extract_immutable_blocks(pack_path: Path) -> list[ImmutableBlock]:
    """Parse content-pack.md's own micro-format: a "Status: IMMUTABLE" line
    immediately (modulo blank lines / prose) ahead of a fenced code block
    marks that fenced block's content as one to verify. Any other Status
    value (PROPOSED TRIM, GENERATED ...) marks the next fenced block as
    exempt. Blocks are labelled by the nearest preceding ## or ### heading
    plus a running count, since one heading can cover several quotes."""
    lines = pack_path.read_text().splitlines()
    blocks: list[ImmutableBlock] = []
    current_heading = "(preamble)"
    pending_status: str | None = None
    counts: dict[str, int] = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        heading_match = HEADING_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(2)
            i += 1
            continue

        status_match = STATUS_RE.match(line)
        if status_match:
            pending_status = status_match.group(1)
            i += 1
            continue

        if FENCE_RE.match(line):
            fence_body: list[str] = []
            i += 1
            while i < len(lines) and not FENCE_RE.match(lines[i]):
                fence_body.append(lines[i])
                i += 1
            i += 1  # skip closing fence

            if pending_status == "IMMUTABLE":
                counts[current_heading] = counts.get(current_heading, 0) + 1
                blocks.append(
                    ImmutableBlock(
                        heading=current_heading,
                        ordinal=counts[current_heading],
                        content="\n".join(fence_body),
                    )
                )
            pending_status = None
            continue

        i += 1

    return blocks


class _VisibleTextExtractor(HTMLParser):
    """Collects text nodes, skipping <style>/<script> contents so CSS rules
    and inline JS never leak into the searchable text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.chunks.append(data)


def visible_text(html_path: Path) -> str:
    parser = _VisibleTextExtractor()
    parser.feed(html_path.read_text())
    return "".join(parser.chunks)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HTML
    if not html_path.exists():
        print(f"error: {html_path} not found", file=sys.stderr)
        return 1
    if not CONTENT_PACK.exists():
        print(f"error: {CONTENT_PACK} not found", file=sys.stderr)
        return 1

    blocks = extract_immutable_blocks(CONTENT_PACK)
    if not blocks:
        print("error: no IMMUTABLE blocks found in content-pack.md — parser or file changed?", file=sys.stderr)
        return 1

    deck_text = normalise(visible_text(html_path))

    failures = 0
    for block in blocks:
        needle = normalise(block.content)
        ok = bool(needle) and needle in deck_text
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {block.label}")
        if not ok:
            failures += 1
            preview = needle[:100] + ("…" if len(needle) > 100 else "")
            print(f"         not found verbatim (whitespace-normalised): {preview!r}")

    total = len(blocks)
    print(f"\n{total - failures}/{total} IMMUTABLE blocks verified against {html_path.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
