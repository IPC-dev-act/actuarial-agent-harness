---
name: reserving-triangle-triage
description: Inspect validation, triangle, and fit artifacts to prepare dashboard data-quality review without changing inputs or judgment.
---

# Reserving triangle triage

Use this skill when asked to prepare a triangle quality review for an
existing run. It complements the dashboard's triangle explorer and future
link-ratio heatmap. It does not replace actuarial judgment.

## Inputs

Read only run artifacts:

- `runs/<run-id>/validation.json`
- `runs/<run-id>/triangle.json`
- `runs/<run-id>/fit.json`
- `runs/<run-id>/validation_tasks.json`, when present
- `runs/<run-id>/diagnostics.json`, when present

If tasks are missing or stale, run `reserve tasks <run-id> --format json`.
Do not hand-write task files and do not write decisions.

## What to look for

- `validation.json: checks[]` warn/fail details, especially
  `monotone_cumulative`, `nonneg_incrementals`, `no_gaps`, and
  `basis_consistent`.
- Missing cells from `triangle.json` that are actual data gaps rather than
  normal future development.
- Non-monotone cumulative values and negative implied incrementals already
  surfaced by validation.
- Thin development ages, using artifact fields such as
  `fit.json: development_factors[].link_ratios` count when present.
- Abnormal link ratios already emitted in `fit.json:
  development_factors[].link_ratios`.
- Suspicious calendar diagonals only when supported by `diagnostics.json` or
  other run artifacts; do not invent a calendar effect by visual impression.
- Origin years that require dashboard review because they appear in warning
  details, diagnostic details, link-ratio outliers, or selection/exclusion
  evidence.

## Output style

Use this operational summary:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Produce a short reviewer note. Every quantitative statement must cite a run
artifact, for example `[runs/<run-id>/validation.json: checks[2].details]`.

## Guardrails

- Every number must cite a run artifact.
- No mental arithmetic.
- No invented figures.
- No hidden factor selection.
- No committing actuarial judgment.
- No report approval without human decision.
- No overriding warnings.
- No final report while required tasks are pending.
- Preview artifacts are exploratory.
- Decision artifacts are the only source of committed judgment.

## What not to do

- Do not modify input data.
- Do not repair triangle values.
- Do not choose development factors.
- Do not commit decisions.
- Do not override warning tasks.
- Do not say a warning is immaterial unless a decision artifact supports that
  human judgment.
