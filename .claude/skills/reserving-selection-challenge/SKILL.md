---
name: reserving-selection-challenge
description: Challenge committed selection sets and governance decisions without approving, rejecting, or superseding them.
---

# Reserving selection challenge

Use this skill for second-review governance challenge of committed selection
sets, decisions, and report readiness. The output is a challenge note for the
actuary. It is not itself a decision.

## Inputs

Read:

- `runs/<run-id>/validation_tasks.json`
- `runs/<run-id>/decisions/*.json`
- `runs/<run-id>/selection_sets/*.json`
- `runs/<run-id>/scenario_index.json`, when present
- `runs/<run-id>/comparisons/*.json`, when present
- `runs/<run-id>/diagnostics.json`, when present
- `runs/<run-id>/sensitivity.json`, when present
- `runs/<run-id>/report.html`, when present

If task state is stale, run `reserve tasks <run-id> --format json` and
`reserve status <run-id> --format json`.

## Challenge checks

- Pending warning, scenario, BCL, or report tasks in `validation_tasks.json`.
- Missing rationale or generic rationale in `decisions/*.json`.
- Committed `selection_sets/*.json` without global rationale.
- Factor changes without per-age rationale.
- Exclusions without sufficient rationale.
- One-sided factor choices across a selection set, described factually from
  artifact fields only.
- `selection_set_approval` whose `resulting_scenario_id` does not match the
  committed selection set.
- Scenario selection not supported by a valid `scenario_index.json` entry.
- Report generated before an active `report_approval` decision.
- Report approval while prerequisite tasks remained pending.
- Warnings, null totals, or data-thinness findings omitted from the report
  narrative.

## Output style

Use this operational summary:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Every quantitative statement must cite a run artifact.

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

- Do not reject a decision.
- Do not approve a decision.
- Do not supersede a decision.
- Do not edit a committed selection set.
- Do not commit a follow-up decision.
- Do not claim the selection is wrong solely because it differs from fitted
  factors; challenge the support and rationale, then send the issue back to
  the dashboard.
