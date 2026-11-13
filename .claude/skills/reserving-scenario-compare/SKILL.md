---
name: reserving-scenario-compare
description: Explain scenario and selection-set movements using scenario_index, comparisons, and selection-set artifacts only.
---

# Reserving scenario compare

Use this skill to explain scenario movement for an existing run. It reads
scenario artifacts and comparison artifacts; it does not compute new
actuarial figures in prose.

## Inputs

Read:

- `runs/<run-id>/scenario_index.json`
- `runs/<run-id>/comparisons/*.json`
- `runs/<run-id>/selection_sets/*.json`
- `runs/<run-id>/factor_previews/*.json`, when present
- `runs/<run-id>/fit.json`
- `runs/<run-id>/sensitivity.json`, when present
- `runs/<run-id>/decisions/*.json`, when present

If `scenario_index.json` is missing and sensitivity exists, run
`reserve scenarios <run-id> --format json`. If a specific scenario needs a
comparison and no comparison artifact exists, run
`reserve compare <run-id> --scenario-id <scenario-id> --format json`.

## Responsibilities

- Explain base vs candidate movement using
  `comparisons/*.json: compared_metrics` and `deltas`.
- Explain selected-set movement using `selection_sets/*.json: comparison`.
- Identify by-origin drivers only when an artifact contains origin-level
  impact rows.
- Attribute movement to factor basis, exclusions, tail, method, or selected
  scenario only when the scenario or selection-set artifact records that
  source.
- Draft reviewer notes based only on artifacts.
- Point the actuary to dashboard scenario selection or selection-set approval
  when decisions are missing.

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

- Do not calculate deltas mentally.
- Do not invent movement drivers.
- Do not attribute movement without artifact support.
- Do not select a scenario.
- Do not approve or reject a scenario decision.
