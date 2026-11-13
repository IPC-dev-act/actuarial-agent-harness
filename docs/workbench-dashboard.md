# Workbench Dashboard

The interactive reserving workbench is a local MVP for human validation of
AI-controlled reserving runs. It is not a chatbot, not a calculator, and not
production-authenticated. The dashboard reads and writes the same audited
run-folder artifacts as the CLI.

Claude commands and skills are the operating layer around this dashboard:
they run controlled CLI commands, prepare artifacts, explain diagnostics and
scenarios, refresh validation tasks, and stop when human judgment is needed.
The dashboard is the human-validation layer. Decisions remain committed only
through structured artifacts under `decisions/`; chat text or skill output is
not an approval.

## Start

From the repository root:

```bash
reserve dashboard --out runs --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/workbench-v2/
```

Equivalent uvicorn command:

```bash
RESERVE_RUNS_ROOT=runs .venv/bin/python -m uvicorn harness.workbench.api:app --host 127.0.0.1 --port 8000
```

## API Surface

- `GET /api/runs`
- `GET /api/runs/{run_id}/status`
- `GET /api/runs/{run_id}/tasks`
- `POST /api/runs/{run_id}/tasks/refresh`
- `GET /api/runs/{run_id}/decisions`
- `GET /api/runs/{run_id}/decision-journal`
- `POST /api/runs/{run_id}/decisions`
- `GET /api/runs/{run_id}/scenarios`
- `GET /api/runs/{run_id}/chain-ladder/summary`
- `GET /api/runs/{run_id}/chain-ladder/factors`
- `GET /api/runs/{run_id}/chain-ladder/projection`
- `GET /api/runs/{run_id}/chain-ladder/triangle`
- `GET /api/runs/{run_id}/report-readiness`
- `GET /api/runs/{run_id}/handoff`
- `GET /api/runs/{run_id}/factor-analysis`
- `POST /api/runs/{run_id}/factor-analysis/refresh`
- `GET /api/runs/{run_id}/factor-review-suggestions`
- `POST /api/runs/{run_id}/factor-preview`
- `GET /api/runs/{run_id}/selection-sets`
- `POST /api/runs/{run_id}/selection-sets/live-preview`
- `POST /api/runs/{run_id}/selection-sets/preview`
- `POST /api/runs/{run_id}/selection-sets/{selection_set_id}/commit`
- `GET /api/runs/{run_id}/explore`
- `GET /api/runs/{run_id}/explore/{explore_scenario_id}`
- `POST /api/runs/{run_id}/explore/preview`
- `POST /api/runs/{run_id}/explore/{explore_scenario_id}`
- `GET /api/runs/{run_id}/explore/compare?left=...&right=...`
- `POST /api/runs/{run_id}/explore/{explore_scenario_id}/promote`
- `GET /api/runs/{run_id}/compare?scenario_id=...`
- `GET /api/runs/{run_id}/artifacts/{artifact_name}`

Artifact reads are restricted to safe JSON artifacts inside the run folder.
Path traversal and non-exposed artifact paths are rejected.

## Explore vs Governed

The workbench uses this product rule:

> Explore freely. Promote deliberately. Only governed selections enter the
> report pack.

**EXPLORE** mode is for fast actuarial scenario testing. It can stage factor
basis choices, manual overrides, origin or valuation exclusions, and
factor-point exclusions, then preview the deterministic impact through the
backend. Explore scenarios are written under `explore/` with
`mode: "explore"` and `status: "exploratory"`. They are labelled **NOT
GOVERNED**, may be revised, do not create decision artifacts, do not satisfy
report readiness, and are ignored by `report --require-approval`.

**GOVERNED** mode is the existing audit workflow. It requires preview,
global rationale, rationale for changed factors and exclusions, user
identity, immutable `selection_sets/*.json`, validated
`selection_set_approval` decisions, reviewed source artifacts, and hash
validation. Only governed selections enter the report pack.

While a factor basis, manual override, or exclusion is being staged, the
Development tab requests a debounced **live deterministic preview**. It
updates the selected IBNR and future triangle cells only with values returned
by the backend rerun. This response is transient: it accepts incomplete
rationale while the actuary is working, writes no selection-set artifact,
does not update the manifest, cannot be committed, and is never included in a
report. The explicit **Preview Scenario** action remains the governed
artifact-producing checkpoint.

Promotion copies an exploratory scenario's assumptions into the governed
selection workflow. Promotion does not silently approve anything: missing
rationales and missing user identity still block commit, and stale source
artifacts require a fresh preview. The API also exposes a promotion endpoint
that creates the governed selection set and approval decision only through
the existing validators.

CLI parity for `reserve explore list/show/preview/promote` is documented as
next work. This phase implements dashboard/API support first.

## Example Workflow

1. Create a deterministic chain ladder run:

   ```bash
   reserve fit examples/raa.csv --method chain_ladder --format json --out runs
   ```

   Use `--method mack` instead when Mack standard errors are part of the
   review.

2. Run diagnostics:

   ```bash
   reserve diagnostics <run-id> --format json --out runs
   ```

   Build link-ratio influence evidence for deterministic chain ladder:

   ```bash
   reserve factor-analysis <run-id> --format json --out runs
   ```

3. Create or refresh validation tasks:

   ```bash
   reserve tasks <run-id> --format json --out runs
   reserve handoff <run-id> --format json --out runs
   ```

4. Optionally generate sensitivity scenarios:

   ```bash
   reserve sensitivity <run-id> --format json --out runs
   reserve scenarios <run-id> --format json --out runs
   ```

5. Start the dashboard:

   ```bash
   reserve dashboard --out runs
   ```

6. In the dashboard:

   - Select the run in the left rail.
   - Use Overview to see method, IBNR, selected scenario state, blockers,
     and the next required action.
   - Review warning tasks in the Decisions tab.
   - Use Development to inspect cumulative, incremental, and link-ratio
     displays. Cell actions stage exclusions only; preview and commit still
     run through backend validation.
   - For deterministic chain ladder runs, open the
     `Review deterministic chain ladder selections` task and commit a
     `method_review_ack` decision with a review note.
   - In the Development tab, select a triangle column, review candidate
     factors, and stage candidate-basis
     choices, manual overrides, factor-point exclusions, origin/valuation
     exclusions, or a constant tail.
   - Staging a factor basis or dragging a manual override immediately marks
     the future triangle and selected IBNR as recalculating; completed values
     are from a transient deterministic backend rerun and remain uncommitted.
   - Use the AI Review Queue to inspect deterministic evidence. It ranks
     point influence and thin development ages for review but never selects
     or stages a factor automatically. Mark prompts reviewed or dismissed so
     the disposition is retained in the selection set.
   - Use the dynamic link-ratio graph to switch between linear and log
     display, inspect point-level exclusion impact, activate only the
     fitting lines needed for comparison,
     and compare the backend-refitted preview line.
   - Add rationale for every changed development age and every exclusion.
   - Optionally stage a governed constant tail with its own rationale.
   - Click `Preview Scenario`. The backend writes
     `selection_sets/<selection_set_id>.json` with `status: preview` and
     returns combined impact figures from a deterministic backend rerun.
   - If the preview is acceptable, click `Commit Selection Set`. One backend
     transaction marks the selection set committed and writes the immutable
     `selection_set_approval` decision; validation failure restores preview.
   - Compare sensitivity scenarios in the Scenarios tab when
     `scenario_index.json` exists.
   - Use the Report tab to see whether the guarded report command would pass.
   - Commit `report_approval` only after prerequisite validation tasks are
     resolved. The approval is bound to an immutable review snapshot of the
     active decisions, selected basis, source hashes, and renderer.

7. Generate the deterministic review pack through the CLI:

   ```bash
   reserve report <run-id> --format-out html --require-approval --out runs
   ```

## Demo Workflow

The dashboard is organized around this path for a deterministic chain ladder
demo:

1. Open the deterministic chain ladder run from the left rail.
2. Use **Overview** to inspect KPIs, selected scenario state, blockers, and
   the guided next action.
3. Use **Triangles** to inspect cumulative values, backend-derived
   incremental values, projected cells, warning cells, exclusions, and
   backend-provided link ratios.
4. Use **Factors** to select a development age, inspect fitted/candidate
   factor cards, stage candidate-basis selections, add rationale, and preview
   the combined scenario.
5. Commit the selection set only after previewing; the dashboard writes the
   committed selection-set artifact and immutable `selection_set_approval`
   decision through backend validation.
6. Use **Scenarios** to compare indexed sensitivity scenarios when
   `scenario_index.json` exists.
7. Use **Decisions** and the right-side validation panel to commit remaining
   workbench decisions, including BCL review, scenario selection, and report
   approval.
8. Use **Report** to see whether
   `reserve report <run-id> --format-out html --require-approval --out runs`
   would pass. The panel lists blockers instead of hiding them.
9. Generate the report through the governed CLI command after approval.

## Screens

**Overview** shows run id, method, input file, engine, latest, ultimate,
IBNR, Mack standard error when available, selected scenario, run status,
governance checklist, IBNR by-origin bars, selected scenario impact cards,
warnings, and the next required action. Values come from `manifest.json`,
`fit.json`, `validation_tasks.json`, decisions, and selection/scenario
artifacts.

**Triangles** has a view toggle for cumulative, incremental, and link-ratio
displays. Cumulative values come from `triangle.json`. Incremental values
are derived by the backend display endpoint from controlled cumulative
artifacts and carry source metadata. Link ratios come from
`fit.json: development_factors[].link_ratios`. Cell selection shows origin,
development age, cumulative value, incremental value, link ratio, source
artifact, warning state, exclusion state, and supported actions. Origin and
valuation/development exclusions can be staged; cell-level exclusion is
labelled as planned because the deterministic CLI path does not support it
yet.

**Factors** centers the review on one selected development age. Candidate
cards show fitted/current, volume weighted, simple average, last 3, last 5,
trimmed mean, and median when the backend payload provides them. Selecting a candidate
stages a draft change. The factor table remains the index of development
ages and shows base fitted factor, current draft selected factor, candidate
averages, cumulative development factor, selected basis, rationale status,
and preview status. The factor curve uses backend chart percentages.
Log-linear smoothing is explicitly unavailable until it has a reproducible,
governed implementation.

**Selection Scenario** in the Development tab shows changed development ages,
previous factor, selected factor, basis, rationale status, staged
exclusions, global rationale, preview status, base IBNR, selected IBNR,
delta IBNR, delta percent when available, scenario id, and by-origin impact.
If the backend cannot split factor-selection impact from exclusion impact,
the UI shows the total selected scenario impact and marks attribution as
future.

**Scenarios** shows scenario cards with id, type, status, ultimate, IBNR,
delta IBNR after comparison, source artifact, and compare actions.
Comparison output is shown as a base-versus-candidate table with source
artifacts and deterministic deltas.

**Decisions** shows pending review tasks, completed review tasks, active
decisions, and superseded decisions. Journal rows include selection set id,
scenario id, decision type, user, timestamp, source artifacts reviewed,
rationale, and supersession state. Committed decisions cannot be edited.

**Report** shows `blocked`, `draft`, `ready_for_approval`, `approved`, or
`generated`; the guarded CLI command; whether `reserve report
--require-approval` would pass; selected scenario; selection set id; report
approval decision id; readiness checklist; and blockers.

**Artifacts** is the only normal workflow tab that exposes raw JSON. It is
for inspection and debugging, not for making approval decisions.

The right-side validation panel shows the selected task, allowed decision
type, preview status, source artifacts reviewed, required rationale, and the
commit form. It never approves anything by UI state alone; decisions are
written through `POST /api/runs/{run_id}/decisions`.

**Report Readiness** shows `blocked`, `draft`, `ready_for_approval`,
`approved`, or `generated`, plus blockers such as unresolved validation
tasks, unresolved diagnostics warnings, unapproved committed selection sets,
missing scenario selection, missing report approval, or missing
`report.html`.

## Deterministic Chain Ladder Dashboard

Runs whose `fit.json` method is `chain_ladder`, `chainladder`, or `bcl` are
displayed as **Deterministic Chain Ladder**. Mack runs remain labelled
separately as **Mack Chain Ladder**.

The Overview tab shows a **Chain Ladder Summary** panel for deterministic
chain ladder runs. It displays method, input file, total latest, total
ultimate, total IBNR, origin period count, development period count, and the
selected scenario when one has been committed. These values come from
`fit.json`, `triangle.json`, and scenario or selection-set artifacts through
the backend API.

The Development tab is the current judgment surface for deterministic chain
ladder selections. It links triangle columns to each development age and displays the base fitted factor,
current draft selected factor, candidate averages, cumulative development
factor, current basis, rationale status, preview status, and the selected
development-age candidate cards. Candidate averages come from `fit.json`.
Missing candidate averages are shown as `not available`; the frontend does
not invent replacements.

The triangle and factor surfaces are merged. The all-development factor curve
is shown directly below the triangle by default, with the fitted/current line
as the initial display. Double-click an outlined fitted point in that curve to
open the relevant per-development-age graph and fitting controls. Dragging a
point vertically is reserved for a manual override; a click or double-click
does not stage one. Fitting choices, manual entry, the staged-scenario form,
review evidence, factor table, tail controls, and governed-mode explanation
use progressive disclosure so the default surface stays focused on triangle
review and the all-age curve. Each available fitting has two separate actions:
`Show on graph` changes display state only, while `Use as basis` stages a
governed factor selection. Inactive fittings are omitted to keep comparisons
readable.

Observed, latest-diagonal, and future-projection cells have distinct visual
treatments. Future cells use hatching and the legend rather than repeated
`forecast` labels. In the Link Ratios view, clicking an observed ratio directly
toggles that exact origin/development factor point between included and staged
for exclusion. Projected cells remain outputs and cannot be excluded as
observations.

The all-development curve can display the fitted series alone or all
available backend candidate series through its collapsed `Compare fittings`
control. `Smooth display` interpolates the chart path through unchanged
backend points; it is visual only and cannot be used as a selected factor or
report basis. Governed smoothing remains blocked until a deterministic backend
fitting and preview contract is implemented.

Both factor graphs expose draggable manual-selection controls. The selected
age graph uses an orange horizontal manual-factor line that can be dragged
vertically anywhere along its length; the all-age curve exposes one outlined
fitted point per development age. Pointer geometry is sent to
`POST /api/runs/{run_id}/chain-ladder/factor-drag`; the backend maps it through
the artifact-backed chart scale and returns the manual factor. Releasing a
control stages a `manual_override`, never a final selection. Rationale and
deterministic preview remain required. The command and KPI strips immediately
show `preview required` for staged changes and switch to backend-selected
ultimate, IBNR, and delta values after preview.

The Selection Scenario panel in the Development tab lets the actuary stage a
complete deterministic chain ladder scenario:

- multiple development-age factor choices;
- rationale for each changed age;
- simple origin-year exclusions;
- simple valuation/calendar-year exclusions;
- a global rationale;
- a backend preview of combined impact;
- a governed commit into `selection_sets/` plus a `selection_set_approval`
  decision.

The backend projection endpoint remains read-only. It displays
`fit.json: by_origin` values: origin, latest, ultimate, IBNR, selected IBNR,
delta IBNR, and delta percentage. In the guided UI, by-origin projection and
impact information appears in Overview and the Selection Scenario preview
instead of a standalone Projection tab. Selected scenario impact is shown
only when an existing preview, selection set, or comparison artifact contains
origin-level impact data.

## Selection Set Lifecycle

Selection set preview is exploratory. Selection set approval is governed.
The browser may stage choices, but it does not compute actuarial results.
All preview numbers are produced by the backend through the deterministic
harness and engine path.

The same lifecycle is available from the CLI:

```bash
reserve selection-sets list <run-id> --format json --out runs
reserve selection-sets show <run-id> <selection-set-id> --format json --out runs
reserve selection-sets preview <run-id> --request-file selection-request.json --format json --out runs
reserve selection-sets commit <run-id> --selection-set-id <selection-set-id> --decision-file selection-approval.json --format json --out runs
```

Use `reserve report <run-id> --format-out html --require-approval --out runs`
for final report-pack generation. Without `--require-approval`, the report
renderer may still write a draft, but the Governance section marks incomplete
approval state as `draft/incomplete`. The `--require-approval` gate also
rejects stale approval decisions when material reviewed-artifact hashes no
longer match the current run folder. Report approval also references an
immutable `review_snapshots/<review_snapshot_id>.json`; later changes to the
active selection, decisions, source hashes, or renderer invalidate it.

Preview:

- endpoint: `POST /api/runs/{run_id}/selection-sets/preview`;
- writes `selection_sets/<selection_set_id>.json`;
- sets `status: preview`;
- validates that selected factor values come from known candidate bases;
- requires rationale for every changed factor, exclusion, manual override,
  and tail selection;
- returns base-versus-selected totals, deltas, by-origin IBNR impact,
  selected factors used, exclusions used, replay parameters, command trail,
  and input hashes.

Commit:

- endpoint:
  `POST /api/runs/{run_id}/selection-sets/{selection_set_id}/commit`;
- requires an existing preview selection set;
- requires a global rationale;
- marks the artifact `status: committed`;
- refuses to overwrite an already committed selection set;
- accepts an approval decision in the same API request and rolls the
  selection set back to preview if decision validation fails.

Approval:

- decision type: `selection_set_approval`;
- requires `selection_set_id`;
- requires `resulting_scenario_id`;
- requires the referenced selection set to exist and be committed;
- requires `source_artifacts_reviewed` to include the selection-set artifact;
- rejects stale approvals when the selection set's source-artifact hashes no
  longer match the run folder.

CLI commit:

- command:
  `reserve selection-sets commit <run-id> --selection-set-id <id> --decision-file <file>`;
- requires the decision file to be a valid `selection_set_approval` artifact;
- uses the same immutable decision writer as `reserve decide`;
- rolls back the selection-set artifact if the decision validation fails;
- supports `--dry-run` for full validation without leaving a committed
  selection set or decision file behind.

## CLI Request File

```json
{
  "schema_version": "0.1",
  "run_id": "2026-07-06T15-59-54_raa_chain_ladder_389579",
  "factor_selections": [
    {
      "development_age": "1 -> 2",
      "selected_basis": "last_3",
      "rationale": "Recent development is more representative after mix change."
    }
  ],
  "exclusions": [
    {
      "type": "origin",
      "value": "1981",
      "rationale": "Oldest origin tested as a sensitivity exclusion."
    }
  ],
  "tail_selection": {
    "type": "constant",
    "factor": 1.01,
    "rationale": "Residual development beyond the observed triangle was reviewed."
  },
  "global_rationale": "Combined deterministic chain ladder selections reviewed.",
  "created_by": {"id": "actuary", "display_name": "Actuary"}
}
```

`selected_basis` may use an available `fit.json` candidate (`fitted`,
`volume_weighted`, `simple_average`, `last_3`, `last_5`, `trimmed_mean`, or
`median`) or a governed `manual_override` with an explicit positive factor
and rationale. Missing candidates are not fabricated.

The earlier single-factor endpoint, `POST /api/runs/{run_id}/factor-preview`,
remains available for compatibility and tests. The dashboard's current BCL
workflow uses selection sets because a realistic actuarial review often
combines multiple factor choices and exclusions.

## Example Selection Set

```json
{
  "schema_version": "0.1",
  "selection_set_id": "selection_set_abc123",
  "preview_scenario_id": "selection_set_abc123",
  "run_id": "2026-07-06T15-59-54_raa_chain_ladder_389579",
  "basis_run_id": "2026-07-06T15-59-54_raa_chain_ladder_389579",
  "status": "committed",
  "factor_selections": [
    {
      "from_dev": 1,
      "to_dev": 2,
      "development_age": "1 -> 2",
      "previous_factor": 2.9993586513353794,
      "selected_factor": 4.693781280053931,
      "selected_basis": "last_3",
      "rationale": "Recent development is more representative after mix change."
    }
  ],
  "exclusions": [
    {
      "type": "origin",
      "value": "1981",
      "rationale": "Oldest origin tested as a sensitivity exclusion."
    }
  ],
  "global_rationale": "Combined deterministic chain ladder selections reviewed.",
  "source_artifacts_reviewed": ["fit.json", "triangle.json", "validation.json"],
  "input_hashes": {"fit.json": "...", "triangle.json": "..."},
  "selection_set_artifact": "selection_sets/selection_set_abc123.json"
}
```

## Example Approval Decision

```json
{
  "schema_version": "0.1",
  "decision_id": "selection_set_approval_001",
  "run_id": "2026-07-06T15-59-54_raa_chain_ladder_389579",
  "task_id": null,
  "decision_type": "selection_set_approval",
  "status": "accepted",
  "selection_set_id": "selection_set_abc123",
  "resulting_scenario_id": "selection_set_abc123",
  "base_run_id": "2026-07-06T15-59-54_raa_chain_ladder_389579",
  "rationale": "Approved the committed selection set for report disclosure.",
  "user": {"id": "actuary", "display_name": "Actuary"},
  "source_artifacts_reviewed": [
    "fit.json",
    "triangle.json",
    "validation.json",
    "selection_sets/selection_set_abc123.json"
  ],
  "commands_or_parameters_affected": [],
  "supersedes_decision_id": null
}
```

## Report Integration

When a committed selection set is available for the run, the HTML report
adds a **Selection set** section. It includes:

- selection set id, status, scenario id, and approval decision id when
  present;
- global actuarial rationale;
- base-versus-selected latest, ultimate, and IBNR comparison;
- selected factors table with base factor, selected factor, basis, and
  rationale;
- exclusions used and rationale;
- constant-tail selection and rationale, when changed;
- reproducibility appendix with command trail and input hashes.
- base-versus-selected factor curve and changed-age link-ratio exhibits;
- reviewed/dismissed suggestion disposition and deterministic evidence;
- factor-point exclusions and base-versus-selected by-origin impact.

The report still displays warnings, diagnostics, sensitivity results, and
limitations. A committed selection set does not imply final report sign-off;
that remains a separate `report_approval` decision.

## Artifact Rules

The dashboard and CLI use the same backend functions:

- task refresh writes `validation_tasks.json`;
- scenario preview writes `scenario_index.json`;
- comparisons write `comparisons/<comparison_id>.json`;
- factor previews write `factor_previews/<scenario_id>.json`;
- selection-set previews and commits write
  `selection_sets/<selection_set_id>.json`;
- decisions write immutable `decisions/<decision_id>.json`;
- AI handoff writes `review_handoff.json`;
- BCL factor analysis writes `factor_analysis.json` and
  `factor_review_suggestions.json`;
- report approval binds to immutable `review_snapshots/*.json`;
- decision validation is performed by `harness.workbench.decisions`.

## Limitations

- Local MVP only; no authentication or multi-user authorization.
- Manual overrides are supported only through backend preview, required
  rationale and identity, selection-set commit, and immutable approval.
- Origin, valuation, and link-ratio factor-point exclusions are supported.
  Direct arbitrary cumulative-cell deletion is not implemented.
- Constant tails are supported; log-linear smoothing is not yet governed.
- No multi-segment portfolio workflow.
- No chat panel.
- No frontend actuarial calculation logic.
- Review suggestions are deterministic screening evidence, not autonomous
  factor selections; the AI/actuary workflow must still preview and commit.
- Comparison values are displayed only from backend artifacts.
- Raw JSON is kept in the Artifacts tab, not in the normal guided workflow.
- No production authentication, authorization, or multi-user approval policy.

## Next Phase Candidates

- Governed curve fitting and tail smoothing.
- Bornhuetter-Ferguson using the same human-judgment lifecycle.
- Enterprise identity, role policy, and multi-user approval controls.
- Read-only preview of rendered `report.html`.
- Multi-segment portfolio workflow.
