---
description: Prepare deterministic chain ladder factor review guidance
argument-hint: <run-id>
---

Apply the `reserving-factor-review` skill to run `$1`.

Run `reserve factor-analysis $1 --format json` when the deterministic
analysis artifacts are missing. Read factor information from `fit.json`,
`factor_analysis.json`, `factor_review_suggestions.json`, `triangle.json`,
existing `selection_sets/*.json`, and `validation_tasks.json`. Use
dashboard/API or CLI selection-set preview workflows
only to prepare exploratory selection-set previews when the user asks for
preparation; do not commit selection sets or decisions.

Use the standard operational output:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Direct the actuary to the dashboard Development tab for final factor selection,
exclusion review, selection-set commit, and approval.
