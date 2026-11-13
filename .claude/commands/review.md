---
description: Governed reserving review - operate CLI workflow, hand off judgment to dashboard, resume after decisions
argument-hint: <triangle.csv|run-id> [mack|chain_ladder|bcl]
---

Run or resume the governed reserving workflow for `$1`. The default method
for a new triangle is `mack`; if the user requested deterministic chain
ladder or BCL, use `--method chain_ladder`. If `$1` is an existing
`runs/<run-id>/` folder name, treat this as a resume and do not re-fit.

Core rule: Claude operates the workflow, the actuary controls judgment, the
engine computes numbers, the harness preserves the audit trail, and the
dashboard is where human validation happens.

## New run workflow

1. Run `reserve validate $1 --format json`. A `verdict: fail` stops the
   workflow; report failed checks per the `data-validation` skill and do not
   proceed to `fit`. A `verdict: warn` is surfaced, cited, and carried into
   workbench tasks; it is not overridden.
2. Run `reserve fit $1 --method <method> --format json`. Use `mack` or
   `chain_ladder` only. Exit 2 means the internal validate-first check
   refused; report it as validation failure and stop. Record the `run_id`.
3. Run `reserve diagnostics <run-id> --format json` when `fit.json` exists.
   For deterministic chain ladder/BCL runs, also run
   `reserve factor-analysis <run-id> --format json`. Treat its leave-one-out
   influence ranking and review suggestions as evidence to present, never as
   authority to select or commit a factor.
   Narrate diagnostics with the fixed `mack-diagnostics` language only.
4. If diagnostics, validation, or the requested workflow call for sensitivity
   review, run `reserve sensitivity <run-id> --format json`. Do not invent
   substitutions for prescribed actions; if a flagged origin or valuation
   cannot be determined from artifacts, use `--grid default`.
5. Run `reserve scenarios <run-id> --format json` whenever
   `sensitivity.json` exists, so scenario candidates are available for the
   dashboard.
6. Run `reserve tasks <run-id> --format json`, then
   `reserve status <run-id> --format json`.
7. Run `reserve handoff <run-id> --format json`. Treat
   `review_handoff.json` as the structured pause/resume contract with the
   dashboard, not as an approval.

## Resume workflow

If `$1` is a run id, start with:

1. `reserve tasks $1 --format json`
2. `reserve status $1 --format json`
3. Read `runs/$1/validation_tasks.json`, `runs/$1/decisions/*.json`,
   `runs/$1/scenario_index.json`, `runs/$1/comparisons/*.json`, and
   `runs/$1/selection_sets/*.json` when present.
4. Run `reserve handoff $1 --format json` and follow only the deterministic
   `next_ai_commands` after all pending human judgment has been resolved.

Do not re-run `fit` during resume unless the user explicitly asks for a new
run. Do refresh `tasks` and `status`, because decisions are immutable and task
state is derived.

## Dashboard handoff

When `reserve status` or `validation_tasks.json` shows pending tasks, stop and
direct the actuary to the dashboard. Use this operational output shape:

- What I ran
- What artifacts were created or read
- What I found
- What requires dashboard validation
- What I will not do without human decision
- Next step

Example required wording:

"The run is ready for actuarial review. I have prepared the artifacts and
refreshed validation tasks. The dashboard has pending judgment items. I will
not generate a final report until the required decisions are committed."

For deterministic chain ladder/BCL runs, explicitly mention that factor
selection, exclusion review, selection set approval, scenario selection, and
report approval belong in the dashboard. Claude may prepare artifacts and
explain them, but must not choose final factors, commit a selection set, or
approve a report.

## Report gating

Generate
`reserve report <run-id> --format-out html --require-approval`
only when governance state allows it:

- `reserve status` has no unresolved prerequisite tasks; and
- required warning/scenario/BCL tasks are completed by decisions; and
- an active `report_approval` decision exists and is bound to the current
  immutable `review_snapshot`; and
- `reserve handoff <run-id> --format json` reports a phase that permits AI
  resume/report generation.

If report approval is missing, do not run the final report command. Only run
`reserve report <run-id> --format-out html` without `--require-approval` when
the user explicitly asks for a draft/incomplete review pack, and say plainly
that the report is not approved. Do not hide pending tasks or warnings.

## Hard prohibitions

- Do not override unresolved warnings.
- Do not choose factors yourself.
- Do not commit a selection set.
- Do not write or commit decisions.
- Do not approve a report.
- Do not hide pending tasks.
- Do not invent numbers.
- Do not do mental arithmetic.
- Do not treat preview artifacts as committed judgment.
- Treat `decisions/*.json` as the only source of committed human judgment.

Every quantitative statement must cite a run artifact as
`[runs/<run-id>/<file>.json: field]`.
