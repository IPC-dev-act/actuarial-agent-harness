---
name: reserving-report
description: Review-pack structure and the citation rule for every quantitative statement in commentary.
---

# Reserving report

`reserve report` (the deterministic HTML/MD renderer) is **not yet built**
(Phase 5). Until it exists, this skill defines the structure your own
commentary should follow when assembling a review by hand (e.g. a `/review`
walkthrough chaining `validate` → `fit` → `diagnostics` → `sensitivity`) — and
the structure the eventual renderer should target. The section layout below is
**my proposed structure, not a certified format** — flag it for whatever house
style you actually want; I have no basis for what a reviewing actuary expects
a review pack to look like beyond "organize by the pipeline stage that
produced each piece."

## The one rule everything else follows

**CLAUDE.md rule 1**: every quantitative statement in your commentary must
come from a file under `runs/`, cited inline as
`[runs/<run-id>/<file>.json: field]`. If a number isn't in a run output, you
don't have it — run the command that produces it, or say plainly that it's
unavailable. This applies to every section below without exception.

Correct: "Total IBNR is 52,135.2 `[runs/<id>/fit.json: totals.ibnr]`."
Incorrect: "Total IBNR is roughly 52,000" (rounded without saying so, and not
cited) or "the reserve looks adequate" (an opinion this harness doesn't offer
— see Scope, below).

## Proposed section structure

0. **Scope & basis of preparation** — what this review covers (the specific
   input triangle, method, and run(s) cited — nothing broader) and the basis
   it's prepared on: `units: "as-input"` (no currency/scale conversion
   applied), no independent valuation date (the triangle's own origin/
   development range is the review's window, per `validation.json:
   dimensions`). State the standing disclaimer here too (CLAUDE.md Scope):
   this is a reference implementation on public data, not actuarial advice,
   no opinion offered on reserve adequacy for any real entity, and nothing
   here is signed by anyone. Frame every figure that follows with this
   section first, not last.
1. **Executive summary** — headline reserve figure(s), citing `fit.json`
   directly; one line on whether any diagnostics flags are outstanding
   (never silently omitted, per `mack-diagnostics`).
2. **Data & validation** — input file, sha256, `validate`'s verdict and any
   check details worth surfacing (`data-validation` skill governs this
   section's language).
3. **Method & parameters** — method, averaging, tail, n-periods, exclusions,
   `sigma_interpolation`, all read verbatim from `fit.json: parameters` — never
   re-described from memory of what was typed.
4. **Results** — development factors and by-origin/total reserves and
   standard errors, from `fit.json`. State `units: "as-input"` explicitly;
   never rescale or round beyond what's asked.
4a. **Selected vs indicated** *(reserved — renders only when a selections
   input exists in the run; `selections` is currently roadmap, "declared,
   not governed" — see `docs/cli-spec.md`'s Roadmap section)*. Per
   development period: the indicated factor, the selected factor, the
   deviation between them, the recorded rationale for that deviation, and
   the aggregate impact of all selections on ultimates. A selection without
   a recorded rationale for every deviation isn't auditable — don't narrate
   one from a future run as if it were (CLAUDE.md rule 1 applies to a
   selection file's rationale field exactly as it does to any other cited
   figure).
5. **Diagnostics** — every test's verdict, narrated per `mack-diagnostics`'
   fixed language; if `overall` is `warn`, the prescribed actions considered
   and (if run) their results, before any headline figure is presented as
   settled (CLAUDE.md rule 5).
6. **Sensitivity** — the grid and range, narrated per `sensitivity-analysis`,
   if a flag prescribed it or it was otherwise run.
7. **Limitations & reliances** — reliance on the input data as provided
   (`validate`'s checks are structural only; they don't audit the source
   system or confirm the underlying claim records); the five diagnostics
   tests are reference-implementation screening indicators (`mack-
   diagnostics`), not certified reproductions of Mack's published test
   statistics; `sensitivity`'s grid is a fixed standard perturbation set,
   showing directional sensitivity, not an exhaustive uncertainty
   quantification; no regulatory/standards opinion is offered unless a
   `corpus/` document is cited (below); this harness does not provide
   actuarial advice or opine on reserve adequacy — any decision this review
   informs remains a qualified actuary's own judgment.
8. **Governance footer** — `run_id`, input `sha256`, `engine.package`/
   `engine.version`, `environment.harness_version`, `created_utc` — the exact
   fields ARCHITECTURE.md's manifest schema already carries; don't compose a
   new footer format, read this one back.

## Regulatory/standards claims

CLAUDE.md rule 7: cited or not made. `corpus/` is an empty scaffold in this
public repo — there is currently no document to cite at paragraph level, so
**no regulatory or standards claim can be made right now**, full stop. If
`corpus/` is ever populated, cite the specific paragraph; a claim without one
is refused the same as any other unsourced figure.

## What NOT to do

- Never compute a portfolio total, a weighted average, or any other figure
  the engine didn't already produce (CLAUDE.md rule 2) — propose the
  engine-level change instead of doing the arithmetic by hand.
- Never smooth, round up, or omit an uncertainty/flag to make a section read
  better (CLAUDE.md rule 6) — refuse that instruction plainly, citing this
  constitution, regardless of who's asking.
- Never present a report as final while a diagnostics flag sits unaddressed.
