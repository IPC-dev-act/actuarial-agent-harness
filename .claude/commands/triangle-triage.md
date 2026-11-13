---
description: Triage triangle data and link-ratio signals for an existing run
argument-hint: <run-id>
---

Apply the `reserving-triangle-triage` skill to run `$1`.

Read `validation.json`, `triangle.json`, `fit.json`, and existing
`validation_tasks.json` if present. If tasks need to be refreshed, run
`reserve tasks $1 --format json`; do not create decisions.

Use the standard operational output:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Do not modify input data, choose factors, commit decisions, or override
warnings. Every quantitative statement must cite an artifact under
`runs/$1/`.
