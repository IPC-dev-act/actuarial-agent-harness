---
name: sensitivity-analysis
description: Reading reserve sensitivity's grid and range — including the degenerate null-total case and what null means.
---

# Sensitivity analysis

`reserve sensitivity <run-id>` re-runs an existing fit across a standard
perturbation grid. It is **descriptive, not a verdict** — always exits 0,
regardless of any scenario's result, and never carries a pass/warn/fail of
its own (`docs/cli-spec.md`). It is the harness's answer to CLAUDE.md rule
5's "propose the prescribed sensitivity commands" — this skill is how you
read what comes back.

## The grid (`--grid default`)

Any entry identical to the base fit's own parameters is skipped (not a
perturbation). Up to eight scenarios: `drop_oldest_origin`,
`drop_latest_diagonal`, the averaging method *not* used by the base fit,
`n_periods` ∈ {3, 5, all}, constant tail ∈ {1.00, 1.02, 1.05}.

## Reading `sensitivity.json`

`{"run_id", "scenarios": [{"scenario_id", "delta_from_base", "totals":
{"ultimate","ibnr","mack_se"}}], "range": {"ibnr_min","ibnr_max","base_ibnr"}}`.
`range` is computed by the engine over the *finite* scenario totals only — cite
it directly (CLAUDE.md rule 2: never recompute a min/max/average yourself from
the scenario rows).

## Worked example: `drop_oldest_origin` on RAA (degenerate case)

RAA's oldest origin (1981) is the *only* origin with data at the final
(108→120) development transition. `drop_oldest_origin` removes it from
development-factor selection — that transition's LDF becomes genuinely
inestimable (no data left to estimate it from), and Mack's standard error,
built from it, is undefined as a result.
`scenarios[].totals.mack_se` for this scenario is `null`. (Verified by
actually running it: `ibnr`/`ultimate` for this specific RAA scenario remain
finite — only `mack_se` goes null. That is not guaranteed in general; check
each field independently rather than assuming they fail together.)

**Required narration**: this is a **data-thinness finding, not a model
failure**. It says "there isn't enough data left to estimate this parameter
under this exclusion," not "the chain ladder is broken" or "something
crashed." Name which parameter went undefined and why (which origin, which
transition) — don't report the scenario as failed, and don't drop it from the
review. This is the same underlying gap a governed tail assumption (roadmap —
`docs/cli-spec.md`'s `bf`/`capecod` a priori, currently "declared, not
governed") would eventually need to fill responsibly, rather than leave
undefined.

**Required rule**: `null` in any `totals` field means the quantity is
**undefined — never report or treat it as zero**. This is a hard distinction
from a fully-developed origin's *own* fit, where `ibnr`/`mack_se` of exactly
`0.0` is the analytically correct answer (no further development possible, no
uncertainty left) — one is "computed to be nothing," the other is "could not
be computed at all," and conflating them is a fabrication either direction.
Don't average, interpolate, or silently omit a null when discussing `range` or
any other aggregate — the engine's own `range` computation already excludes
non-finite scenarios from the min/max rather than corrupting them; do the
same in prose (state the null plainly, don't paper over it).

> **Scope note:** Narration in this reference implementation is deliberately
> factual-only; causal interpretation of warnings is reserved for the
> reviewing actuary. The mechanical distinction above (`null` = undefined,
> `0.0` = analytically zero, never conflated) is a hard rule this skill
> enforces; "data-thinness finding" itself is a factual description of what
> the exclusion did to the data, not a causal or client-facing judgment —
> anything beyond that framing is the reviewing actuary's call, not this
> skill's.

## What NOT to do

- Never treat `sensitivity` output as a verdict — no scenario here "fails" or
  "passes"; that language belongs to `diagnostics`, not this command.
- Never recompute `range` from the scenario rows yourself, and never let a
  `null` scenario total silently vanish from a written review.
- Never present a single perturbed scenario's total as *the* reserve —
  `sensitivity` exists precisely so no single fit gets treated as ground
  truth; the base fit's own figure (already cited elsewhere) stays the
  headline, with the range contextualizing it.
