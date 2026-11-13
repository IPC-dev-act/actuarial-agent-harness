# scripts/record_demo/demo.tape — Clip A (vhs), per docs/RECORDING-PLAN.md.
# Render from the repo root: vhs scripts/record_demo/demo.tape
#
# The run-id below is hardcoded (vhs tapes are static text, so
# `diagnostics`/`report` can't discover a run-id `fit` mints fresh on every
# invocation) but kept in sync automatically: run `make tape-sync` before
# rendering and it fits examples/raa.csv for real, renders that run's
# report, and rewrites every run-id-shaped string below to match — no
# manual copy-paste, and no stale-id risk. See
# scripts/record_demo/README.md's "make tape-sync" section.
#
# Sequence this tape narrates (last synced against a real run — RAA's own
# outlier_link_ratios test warns, so diagnostics genuinely exits 3):
#   reserve validate examples/raa.csv                                -> verdict WARN (monotone_cumulative, nonneg_incrementals — non-blocking)
#   reserve fit examples/raa.csv --method mack --out runs/           -> mints the run-id below
#   reserve diagnostics <run-id> --format json                       -> exit 3 (outlier_link_ratios warns)
#   reserve report <run-id> --format-out html                        -> wrote report.html

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
Type "reserve diagnostics 2026-07-04T17-22-49_raa_mack_829e1a --format json | head -30"
Enter
Sleep 4s
Type "# exit code 3: assumption flag raised — the agent may not present"
Type " a settled figure past this point"
Enter
Sleep 3s
Type "reserve report 2026-07-04T17-22-49_raa_mack_829e1a --format-out html"
Enter
Sleep 3s
