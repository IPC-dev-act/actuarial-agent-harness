# scripts/record_demo/ — demo-video recording pipeline

Fully scripted production of the ~90s demo video described in
`docs/RECORDING-PLAN.md`: a deterministic CLI clip (vhs), a real headless
agent session (asciinema), a report walkthrough (Playwright), and a final
ffmpeg assembly with burned-in captions.

## Prerequisites (Ubuntu)

| Tool | Used by | Install |
|---|---|---|
| `vhs` | `demo.tape` | see below — also needs `ttyd` and `ffmpeg` at render time |
| `ttyd` | `vhs`'s own dependency | `sudo apt install ttyd` |
| `asciinema` | `record_agent_session.sh` | `sudo apt install asciinema` |
| `agg` | `record_agent_session.sh` (cast -> gif) | see below |
| `ffmpeg` | `record_agent_session.sh`, `assemble.sh` | `sudo apt install ffmpeg` |
| `claude` (Claude Code CLI) | `record_agent_session.sh` | see the repo README's Layer 1 section |
| Python `playwright` | `record_report.py` | see below |

```bash
# vhs (charm.sh apt repo)
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | sudo tee /etc/apt/sources.list.d/charm.list
sudo apt update && sudo apt install vhs ttyd

# asciinema
sudo apt install asciinema

# agg (no apt package — prebuilt binary from GitHub releases; check the
# releases page for the current asset name if this exact one has moved)
curl -fsSL -o agg https://github.com/asciinema/agg/releases/latest/download/agg-x86_64-unknown-linux-gnu
chmod +x agg && sudo mv agg /usr/local/bin/

# ffmpeg
sudo apt install ffmpeg

# Playwright (Python) — inside this repo's venv
pip install playwright
playwright install --with-deps chromium
```

Verify each with `vhs --version`, `asciinema --version`, `agg --version`,
`ffmpeg -version`, `claude --version`, `python3 -c "import playwright"`.

## Running it

```bash
make demo          # runs all four steps in order, from the repo root
# or individually:
vhs scripts/record_demo/demo.tape
scripts/record_demo/record_agent_session.sh
python3 scripts/record_demo/record_report.py
scripts/record_demo/assemble.sh
```

## Billing warning

`record_agent_session.sh` makes **two real, billed Claude API calls** every
time it runs (a full `/review` pipeline, then a follow-up turn in the same
session). It is a manual, opt-in recording step — never wire it into tests
or CI, and don't run `make demo` casually.

## What's been verified vs. assumed

None of `vhs`, `asciinema`, `agg`, or Playwright's browsers were installed
in the environment this pipeline was built in, so the full render chain has
not been run end to end. What *was* actually run and confirmed while writing
these scripts, rather than assumed:

- The full `validate` -> `fit` -> `diagnostics` -> `report` CLI sequence
  `demo.tape` narrates — real run-id baked into the tape (see its own header
  comment for the exact commands and the outcomes actually observed,
  including which diagnostics test warns and why).
- `claude -p --output-format json`'s JSON schema (a top-level `session_id`
  field, snake_case UUID) and `-r`/`--resume <session_id>` genuinely
  continuing the same session — verified against two real headless calls,
  not assumed from `--help` text alone (confirmed via matching
  cache-read/cache-creation token counts across the two calls — proof of an
  actual continued session, not a coincidentally-shared id).
- The `assemble.sh` ffmpeg pipeline (normalise, concat, burn captions) —
  tested end-to-end against three synthetic placeholder clips of different
  sizes, frame rates, and codecs (including one `.webm`, matching what
  Playwright's video recorder actually produces). This surfaced and fixed a
  real bug: ffmpeg's `concat` filter refuses to join clips whose sample
  aspect ratio doesn't match exactly, which `scale`+`pad`'s rounding can
  introduce on non-evenly-divisible source resolutions — `setsar=1` in the
  normalise step fixes it.
- The CSS selectors `record_report.py` hovers/holds on (`span.fig`,
  `.triangle-wrap`, `#governance`) — read from `harness/render/report_html.py`
  and `harness/render/templates/report.html`, then confirmed present in a
  real generated `report.html`, not guessed.

Spot-check each tool once after installing prerequisites (a single short
`claude -p` call, a one-clip `vhs` render, etc.) before trusting a full
`make demo` run — a first real run is still the best test of the parts that
couldn't be exercised here.

## Two manual steps this doesn't automate

1. **Choose the best take.** `record_agent_session.sh` and `record_report.py`
   each produce one file per run; re-run either and keep the take you like,
   the same as any screen recording.
2. **Adjust caption timestamps.** `assemble.sh`'s `CAPTION_*_START`/`_END`
   variables are positions in the *assembled* (post-concat) timeline, which
   depends on how long your specific takes of clip A and clip B's agent
   session ran. After any re-record, scrub `demo_final.mp4` (or `ffprobe`
   the normalised intermediate clips) and adjust the six numbers at the top
   of `assemble.sh` — nothing else in the script needs to change.

A third, related manual step lives inside `demo.tape` itself, not this
pipeline's other scripts: its hardcoded run-id goes stale the moment
`reserve fit` is genuinely re-run (it mints a fresh id every time — see
`harness/runs.py`'s `new_run_id`). Re-sync it per `demo.tape`'s own header
comment after any re-render.

## Outputs (gitignored)

`*.cast`, `*.mp4`, `*.gif`, and `*.webm` under this directory are pipeline
*outputs*, not the pipeline itself — the scripts are versioned, their
renders are not (see `.gitignore`).
