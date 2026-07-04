# scripts/record_demo/demo.tape — Clip A (vhs), per docs/RECORDING-PLAN.md.
# Render from the repo root: vhs scripts/record_demo/demo.tape
#
# The run-id below is hardcoded to a real one, produced by actually running
# the sequence once before writing this tape (RECORDING-PLAN.md's own
# documented workflow — vhs tapes are static text, so `diagnostics`/`report`
# can't discover a run-id `fit` mints fresh on every invocation):
#   reserve validate examples/raa.csv
#     -> verdict WARN (monotone_cumulative, nonneg_incrementals — RAA's own
#        incurred-data feature per v0.1.2/mack-diagnostics, non-blocking)
#   reserve fit examples/raa.csv --method mack --out runs/
#     -> run_id 2026-07-04T13-57-22_raa_mack_779705
#   reserve diagnostics 2026-07-04T13-57-22_raa_mack_779705 --format json
#     -> exit 3 (outlier_link_ratios warns: statistic 2.61 > threshold 1.96)
#   reserve report 2026-07-04T13-57-22_raa_mack_779705 --format-out html
#     -> wrote report.html
#
# REMAINING MANUAL STEP after any future re-render: this tape's own `fit`
# line mints a NEW run-id every time it actually runs (timestamp + random
# nonce, by design — see harness/runs.py's new_run_id docstring). Run once,
# read the new run_id from its output, paste it into the two hardcoded
# occurrences below, then re-render — otherwise `diagnostics`/`report` will
# exit 4 (run not found) against a stale id. See scripts/record_demo/README.md.

Output scripts/record_demo/demo_cli.mp4
Set FontSize 20
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "# The engine is a commodity. The harness is the asset."
Enter
Sleep 1.5s
Type "reserve validate examples/raa.csv"
Enter
Sleep 3s
Type "reserve fit examples/raa.csv --method mack --out runs/"
Enter
Sleep 4s
Type "# every run: hashed inputs, pinned versions, audit manifest"
Enter
Type "cat runs/*/manifest.json | head -20"
Enter
Sleep 4s
Type "reserve diagnostics 2026-07-04T13-57-22_raa_mack_779705 --format json | head -30"
Enter
Sleep 4s
Type "# exit code 3: assumption flag raised — the agent may not present"
Type " a settled figure past this point"
Enter
Sleep 3s
Type "reserve report 2026-07-04T13-57-22_raa_mack_779705 --format-out html"
Enter
Sleep 3s
