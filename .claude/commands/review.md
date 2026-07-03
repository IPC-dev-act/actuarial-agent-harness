---
description: Full reserving review — validate, fit, diagnostics, sensitivity if flagged, then a cited review
argument-hint: <triangle.csv>
---

Run the full pipeline against the triangle CSV given as `$1`, in order,
never skipping a step:

1. `reserve validate $1 --format json`. `verdict: fail` → stop; report each
   failed check per the `data-validation` skill and do not proceed to
   `fit`. `verdict: warn` → note it, continue (CLAUDE.md rule 4: validate
   always runs, even if it warns, even if this file was already validated
   earlier in the session).
2. `reserve fit $1 --method mack --format json`. Exit 2 means the internal
   validate-first check refused — report the same as step 1 and stop. Note
   the `run_id`.
3. `reserve diagnostics <run-id> --format json`. Narrate every test's
   verdict using only the fixed prose mapped to its `narrative_key` in the
   `mack-diagnostics` skill — never invent or paraphrase it.
4. For every test with `verdict: warn`, run its `prescribed_actions`
   (`reserve sensitivity`/`reserve fit` invocations). Placeholders like
   `<flagged-origin>`/`<flagged-valuation>` aren't in `diagnostics.json` as
   a field — determine the specific value from `fit.json` (e.g.
   `by_origin`, `development_factors`) before substituting; if you can't
   determine it, run `reserve sensitivity <run-id> --grid default` instead
   of guessing. Do not proceed to a headline figure with any flag
   unresolved and unacknowledged (CLAUDE.md rule 5).
5. Assemble the review following the `reserving-report` skill's section
   structure (0–8) exactly. Every quantitative statement cited as
   `[runs/<run-id>/<file>.json: field]` (CLAUDE.md rule 1) — if a number
   isn't in a run output, you don't have it, full stop.

Frozen constraints, no exceptions: never skip validation; never state a
figure absent from a file under `runs/`; never override, soften, or drop a
warned/failed test to make the review read cleaner (CLAUDE.md rule 6).
