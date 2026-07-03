#!/usr/bin/env bash
# Layer 2 demo: an unattended agent runs the full reserving review pipeline
# (validate -> fit -> diagnostics -> sensitivity if flagged -> report) against
# a deliberately flawed triangle. examples/triangle_calendar_effect.csv is
# clean at `validate` but trips the `calendar_year_effect` Mack assumption
# test at `diagnostics` (exit 3) — the point of this demo is watching the
# agent surface that warning and run the prescribed sensitivities instead of
# reporting a clean headline figure, not watching a fit succeed quietly.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v claude >/dev/null 2>&1; then
  echo "claude CLI not found on PATH — this demo needs Claude Code (Layer 1/2)." >&2
  echo "Run the same pipeline directly instead (Layer 0, no agent narration):" >&2
  echo "  reserve validate examples/triangle_calendar_effect.csv" >&2
  echo "  reserve fit examples/triangle_calendar_effect.csv --method mack --out runs/" >&2
  echo "  reserve diagnostics <run-id> --format json --out runs/" >&2
  echo "  reserve sensitivity <run-id> --format json --out runs/" >&2
  echo "  reserve report <run-id> --format-out html --out runs/" >&2
  exit 1
fi

claude -p "/review examples/triangle_calendar_effect.csv" \
  --allowedTools "Bash,Read,Write" \
  --output-format json
