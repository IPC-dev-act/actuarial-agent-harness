---
description: Second-review challenge of a run's governance and computed artifacts
argument-hint: <run-id>
---

Peer-review run `$1` adversarially using only artifacts already under
`runs/$1/`. Apply the `reserving-selection-challenge`,
`reserving-scenario-compare`, `sensitivity-analysis`, and `reserving-report`
skills where relevant. If an artifact needed for a conclusion does not exist,
say which command or dashboard workflow would create it; do not infer it.

Inspect, when present:

- `manifest.json`
- `validation.json`
- `fit.json`
- `triangle.json`
- `diagnostics.json`
- `sensitivity.json`
- `validation_tasks.json`
- `decisions/*.json`
- `selection_sets/*.json`
- `scenario_index.json`
- `comparisons/*.json`
- `report.html`

Challenge specifically:

- unresolved validation or diagnostics warning tasks;
- missing, weak, or generic decision rationale;
- one-sided factor choices in committed selection sets;
- exclusions without sufficient artifact-backed rationale;
- scenario selections that do not match a valid committed decision;
- selected scenario shown in dashboard artifacts but not supported by an
  active decision;
- report generated before `report_approval`;
- report approval while prerequisite warning, scenario, or BCL tasks remain
  pending;
- null totals or data-thinness findings that were omitted from the narrative.

Output using this operational shape:

- What I read
- What artifacts are missing
- Findings
- What requires dashboard validation
- What I will not do without human decision
- Next step

Never supersede, reject, approve, or write a decision. Produce a concise
challenge note and direct the actuary back to the dashboard for any further
validation. Every quantitative statement must cite an artifact under
`runs/$1/`.
