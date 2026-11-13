---
name: reserving-factor-review
description: Prepare deterministic chain ladder factor review guidance and preview candidates without selecting final factors.
---

# Reserving factor review

Use this skill when asked to prepare deterministic chain ladder/BCL factor
review. It complements the dashboard Development tab and Selection Scenario
panel. The skill prepares the work; the actuary validates judgment in the
dashboard.

## Inputs

Read only run artifacts unless a preview is explicitly requested:

- `runs/<run-id>/fit.json`
- `runs/<run-id>/triangle.json`
- `runs/<run-id>/factor_analysis.json`, generating it with
  `reserve factor-analysis <run-id> --format json` when absent
- `runs/<run-id>/factor_review_suggestions.json`
- `runs/<run-id>/validation_tasks.json`, when present
- `runs/<run-id>/selection_sets/*.json`, when present
- `runs/<run-id>/factor_previews/*.json`, when present
- `runs/<run-id>/decisions/*.json`, when present

For deterministic chain ladder/BCL runs, factor candidates live in
`fit.json: development_factors[]` fields such as `selected_factor`,
`fitted_factor`, `factor_basis`, `cumulative_development_factor`, and
`candidate_averages` (`volume_weighted`, `simple_average`, `last_3`,
`last_5`, `trimmed_mean`, `median`). If a candidate is not present, say
`not available`; do not fabricate it.

## Responsibilities

- Identify development ages where candidate bases differ enough to warrant
  dashboard review, citing only artifact fields.
- Present leave-one-out point influence from `factor_analysis.json` without
  turning influence rank into a factor recommendation.
- Present `factor_review_suggestions.json` as a review queue. Make clear that
  its generator is deterministic screening for AI/senior review and has no
  final-selection authority.
- Surface which factors have candidate bases available.
- Identify thin development ages from available link-ratio counts or
  candidate-average notes.
- Review existing preview and committed selection-set artifacts.
- Draft suggested rationale language for the actuary to edit and approve.
- Recommend scenario previews when supported by the dashboard/API or future
  CLI parity.
- Surface manual overrides, factor-point exclusions, and constant-tail
  assumptions for explicit senior-actuary review; never choose them.
- Direct the actuary to the dashboard Development tab for final selection,
  exclusion review, selection-set commit, and `selection_set_approval`.

## Preview handling

Selection-set previews are exploratory. If asked to prepare preview inputs,
use artifact-backed candidates and clearly label any actuary-supplied manual
override, exclusion, or tail. Do not call any preview endpoint unless the
user asked for preparation, and never describe a preview as approved. A committed selection set plus
`selection_set_approval` decision is required before it is committed
judgment.

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

- Do not select final factors.
- Do not commit selection sets.
- Do not write decisions.
- Do not claim judgment has been approved.
- Do not recommend a basis that is not present in `fit.json`.
- Do not choose a manual factor override, exclusion, or tail assumption for
  the actuary. These are supported only as human-staged, backend-previewed,
  governed decisions.
