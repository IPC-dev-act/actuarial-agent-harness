# scripts/carousel/ — LinkedIn launch carousel

A single self-contained `presentation.html` (same discipline as the report
renderer: one file, inline CSS only, no scripts, no external assets) and a
deterministic PDF build. 10 slides, each exactly 1080×1080 CSS pixels (810×810
PDF points at 96dpi — the same physical size, just PDF's native unit is
points, not pixels), designed to be read in ~3 seconds on a phone.

## Prerequisites

```bash
pip install playwright
playwright install chromium
```

Verify with `python3 -c "import playwright"` and `playwright --version`.

## Building

```bash
make carousel          # from the repo root
# or directly:
scripts/carousel/build.sh
```

Renders `presentation.html` to `carousel.pdf` via Playwright's chromium in
headless print mode — deterministic, no manual print dialog. Two non-default
PDF options matter: `prefer_css_page_size` (respects the CSS's own
`@page { size: 1080px 1080px; margin: 0 }` instead of defaulting to a fixed
paper format) and `print_background` (Chromium drops CSS background colors
when printing by default — without this the status badges, dark terminal
blocks, and shaded architecture box would render as plain white).

## Design conventions

Reuses `harness/render/templates/report.html`'s house palette verbatim —
same status colors for pass/warn/fail badges, same
`font-variant-numeric: tabular-nums` on figures — so the report and this
deck read as visibly the same system. One addition with no report
equivalent: `--terminal-bg`/`--terminal-ink`/`--terminal-muted` for the two
dark monospace blocks (the red-team hero quote, the manifest excerpt).

Minimum font sizes (never shrunk below these — see "What didn't fit" below
for the one case that came close): content-slide body copy ≥40px, the two
hook-tier headlines (S1, S10) ≥80px, monospace terminal blocks ≥28px. The
footer strip and the small `WARN` badge are deliberately-small chrome
elements outside this floor, not body copy.

## A layout trap worth knowing about if you edit this

Slides 3, 6, and 9 originally used `flex: 1; justify-content: center;` on
their content block to vertically center it. This has a non-obvious
failure mode: a flex item with `flex: 1` **always** grows to consume all
remaining space in its flex container, regardless of how much its own
content shrinks — so trimming padding/gaps inside a `flex:1` block changes
nothing about where the *next sibling* (a closing line, here) ends up
sitting, because the flex item just gains more invisible centered padding
instead of getting shorter. The closing lines on those three slides were
overlapping the footer strip for exactly this reason, and reducing spacing
*inside* the centered block didn't fix it — only removing `flex: 1` (letting
the block size to its natural content instead of stretching) did. Slide 4's
dark terminal block hit the same trap for the same reason. If a future edit
re-adds `flex: 1` + `justify-content: center` to vertically center a block
above a closing line, re-check the gap before the footer strip, not just
whether the slide overflows — `scrollHeight <= clientHeight` (no clipping)
and "nothing overlaps the absolutely-positioned footer" are two different
checks, and this deck's build process checks both (see below).

## Verifying a render (what this pipeline actually checks)

`build.sh` only builds; it doesn't check the result. Before trusting a
render, two checks matter — both were run against every slide while
building this deck, via a throwaway Playwright script (not part of the
build itself):

1. **No clipping**: each `.slide`'s `scrollHeight` must not exceed its
   `clientHeight` (1080px) — content silently cut off by `overflow: hidden`
   otherwise.
2. **No footer collision**: the last content element before `.footer-strip`
   must end *above* the footer strip's own top edge, not just above 1080px
   — `.footer-strip` is `position: absolute` and doesn't participate in flex
   layout, so check 1 alone can pass while text still visually overlaps it
   (see the layout trap above).

## What didn't fit at minimum size

Nothing. All 10 slides render with zero overflow and a positive gap above
the footer strip once the `flex: 1` layout trap above was fixed. Slide 4 (the
red-team hero quote) is the most content-dense — the full prompt plus the
full refusal at 30px monospace — and was the tightest before that fix, but
holds a comfortable margin now.

## Output (gitignored)

`carousel.pdf` is a pipeline *output*, not the pipeline itself — versioned
here is `presentation.html` and `build.sh`, not the render (see
`.gitignore`).
