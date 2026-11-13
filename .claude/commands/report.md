---
description: Governed report-pack generation for an existing run
argument-hint: <run-id>
---

Prepare the report pack for run `$1` without bypassing workbench governance.
Use the `reserving-report` skill for report structure and citation rules.

Before rendering, run and read:

1. `reserve tasks $1 --format json`
2. `reserve status $1 --format json`
3. `runs/$1/validation_tasks.json`
4. `runs/$1/decisions/*.json`
5. `runs/$1/selection_sets/*.json`, if present
6. `runs/$1/scenario_index.json` and `runs/$1/comparisons/*.json`, if present
7. `runs/$1/review_handoff.json` and `runs/$1/review_snapshots/*.json`, if present

If unresolved prerequisite tasks remain, do not present the report as final.
Direct the actuary to the dashboard and list the pending task titles and
allowed decision types from `validation_tasks.json`.

If there is no active `report_approval` decision, do not run the final report
command. Only render a draft/incomplete report if the user explicitly asks for
a draft; label it as draft/incomplete in the response.

If governance is complete, run:

`reserve report $1 --format-out html --require-approval`

The guarded command must reject an approval whose review snapshot no longer
matches the active selection, decisions, source hashes, or report renderer.

Then report:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation, if anything
- What I will not do without human decision
- Next step

Never hide warnings or unresolved tasks. Never approve a report, commit a
decision, select a scenario, or select factors. Every quantitative statement
must cite an artifact under `runs/$1/`.
