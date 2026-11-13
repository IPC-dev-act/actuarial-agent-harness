---
name: reserving-report
description: Review-pack structure and the citation rule for every quantitative statement in commentary.
---

# Reserving report

`reserve report <run-id> --format-out html --require-approval`
(`harness/render/report_html.py`) is the governed final-report path. The same
renderer can still be run without `--require-approval` for draft output, but
the Governance section must mark incomplete approval state as
`draft/incomplete`. It produces every quantitative section below directly
from `runs/<run-id>/`'s own JSON, with no LLM in its loop. This skill governs
two things: the structure the renderer implements (below — matched exactly,
section for section), and the *commentary* you write alongside it, since the
renderer has no narrative judgment of its own. Use it both ways: to read a
rendered report (know what each section is drawing from and why) and to write
the prose that goes around it, whether that's `/report`'s commentary pass
over an existing render or a `/review` walkthrough narrating the same
pipeline as it runs.

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

## Section structure

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
5. **Diagnostics** — every test's verdict, narrated per `mack-diagnostics`'
   fixed language; if `overall` is `warn`, the prescribed actions considered
   and (if run) their results, before any headline figure is presented as
   settled (CLAUDE.md rule 5).
6. **Sensitivity** — the grid and range, narrated per `sensitivity-analysis`,
   if a flag prescribed it or it was otherwise run.
7. **Selection set** — if `selection_sets/<selection_set_id>.json` exists
   with `status: committed`, the renderer discloses selected factors,
   exclusions, global rationale, base-vs-selected comparison, scenario id,
   decision id when an active `selection_set_approval` exists, command trail,
   and input hashes. A committed selection set is not report approval. A
   preview selection set is exploratory and must not be narrated as committed
   judgment. If no committed selection set exists, state that base fit
   assumptions remain the displayed basis unless a separate approval
   decision is committed.
8. **Limitations & reliances** — reliance on the input data as provided
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
9. **Governance footer** — `run_id`, input `sha256`, `engine.package`/
   `engine.version`, `environment.harness_version`, `created_utc`,
   governance status, and governance detail. Static run metadata comes from
   the exact fields ARCHITECTURE.md's manifest schema already carries;
   governance state is derived from workbench tasks and decisions.

## Workbench governance before report

Before presenting a report as final or approved, check `reserve status
<run-id> --format json`, `validation_tasks.json`, and `decisions/*.json`.
Required dashboard tasks must be complete and an active `report_approval`
decision must exist. Run final reports with
`reserve report <run-id> --format-out html --require-approval`. If approval
is missing, do not run the final command. Only render without
`--require-approval` when the user explicitly asks for a draft, and label it
draft/incomplete.

Selection-set report disclosure comes from `selection_sets/*.json` and
`selection_set_approval` decisions only. Do not infer selected factors from
conversation or from preview artifacts alone.

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
- Never present a report as approved without an active `report_approval`
  decision artifact.
- Never treat `selection_sets/*.json` with `status: preview` as committed
  actuarial judgment.
