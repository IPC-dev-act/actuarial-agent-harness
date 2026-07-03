---
description: Explain an existing run's diagnostics tests using fixed narration only
argument-hint: <run-id>
---

Explain the diagnostics on run `$1`.

If `runs/$1/diagnostics.json` doesn't exist yet, run `reserve diagnostics $1
--format json` first — don't reason about a test result you don't have.
Otherwise read it directly; no need to re-run it.

For each entry in `tests[]`: state the `statistic` and `threshold`, cited as
`[runs/$1/diagnostics.json: tests[i].statistic]` etc., then narrate the
verdict using **only** the fixed prose mapped to that test's
`narrative_key` in the `mack-diagnostics` skill — never paraphrase,
soften, or strengthen it, and never describe these as certified Mack
tests (they're the harness's own screening indicators — the skill says
exactly how to frame that).

For any test with `verdict: warn`, list its `prescribed_actions` verbatim —
that's the only menu to propose from (CLAUDE.md rule 5), nothing else.

State `overall` plainly. If it's `warn`, don't characterize the underlying
fit as sound or settled until the prescribed actions have been run or the
flag has been explicitly acknowledged.
