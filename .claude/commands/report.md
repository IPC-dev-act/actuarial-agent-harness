---
description: Assemble (or regenerate) the review pack for an existing run
argument-hint: <run-id>
---

Run `reserve report $1 --format-out html` to render the deterministic HTML
review pack. It reads only `runs/$1/` — no numeric argument, no way to
inject a figure through this command. Report the exit code plainly: `0`
success, `4` if the run folder is incomplete for reporting (say which
required file is missing) or if `--format-out md` was requested (not yet
implemented).

The renderer produces every quantitative section (0 Scope & basis of
preparation, 1 Executive summary, 2 Data & validation, 3 Method &
parameters, 4 Results, 5 Diagnostics, 6 Sensitivity, 7 Limitations &
reliances, 8 Governance — `reserving-report` skill) deterministically from
`runs/$1/`'s own JSON. Your job after it succeeds is the *commentary* only —
the prose alongside those sections, not new figures (CLAUDE.md: "You may
write the commentary sections of a review, but every quantitative statement
in your commentary follows rule 1"). Do not re-run `fit` or change any
parameter as part of this command. If `diagnostics.json` or
`sensitivity.json` don't exist for this run, the rendered report already
says so plainly in its own sections — don't fabricate their content in your
commentary either; run them first only if that's separately being asked
for.
