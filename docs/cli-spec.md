# `reserve` CLI — command specification (v0.2.9, FROZEN)

Contract for the current workbench implementation. Changes after freeze require
a version bump and a note in this file's changelog.

## Global behaviour

- Every command accepts `--format json|text` (default `text` for humans; the agent
  always passes `json`). JSON goes to stdout; logs to stderr.
- Every command that produces output writes into `runs/<run-id>/` and updates
  `manifest.json` (schema in ARCHITECTURE.md).
- `--out DIR` overrides the runs root (default `./runs`).
- `--dry-run` on any writing command: print intended actions, write nothing.
- No command ever modifies its inputs.

## Exit codes (harness-wide)

| Code | Meaning |
|---|---|
| 0 | Success, no flags |
| 1 | Internal error (traceback logged to stderr), or a structured `input_integrity_violation` from `diagnostics`/`sensitivity`'s audit replay (v0.1.12 — see the `diagnostics` section) |
| 2 | Data validation failure — structured errors in output |
| 3 | Success with model warnings — one or more assumption flags ≠ pass |
| 4 | Usage error (bad arguments, unknown method, missing file) |

## Commands

### `reserve validate <triangle.csv> [--basis cumulative|incremental] [--format] [--out]`

Structural checks, engine-agnostic. Checks (each with a stable `check_id`):
`file_readable`, `shape_triangular`, `no_gaps`, `monotone_cumulative` (warn
only, v0.1.2), `basis_consistent`, `origin_dev_parseable`,
`nonneg_incrementals` (warn only).

`basis_consistent` (v0.1.1; revisited v0.1.13): basis is *inferred* by
default (monotone non-decreasing per origin ⇒ cumulative, else incremental).
The check verifies the inference is not internally contradictory (e.g. no
mix of origins that no single basis explains) — "mixed basis", `fail`, when
votes tie or too few origins have enough history to vote at all.

`--basis cumulative|incremental` (v0.1.13): an optional, authoritative
declaration, on both `validate` and `fit`. Independent-review evidence
(`data-validation` skill) showed the inference heuristic can be fooled by a
smoothly, monotonically increasing *incremental* series, which votes
"cumulative" the same way genuinely cumulative data does — a real class of
data this harness had no way to flag before v0.1.13. When `--basis` is
given:
- If the inference vote is inconclusive (a tie, or too little history) —
  the case that would otherwise fail as "mixed basis" — the declaration
  resolves it: `basis_consistent` passes on the declared value.
- If the inference vote *does* reach a definite, opposing conclusion, that
  disagreement is itself a **fail** — "declared-vs-inferred conflict" — not
  a silent override in either direction:
  ```json
  {"check_id": "basis_consistent", "verdict": "fail",
   "details": {"reason": "declared-vs-inferred conflict — the declared basis does not match what the data appears to be",
               "declared_basis": "cumulative", "inferred_basis": "incremental",
               "votes_cumulative": 2, "votes_incremental": 8}}
  ```
- If the inference vote agrees with the declaration, `basis_consistent`
  passes on that (shared) value, same as if it were undeclared.
- Absent (the default): inference stands exactly as before v0.1.13 — no
  behavioural change to the undeclared path.

`monotone_cumulative` (v0.1.2): warn-class, not fail-class. A decrease
between consecutive development periods is legitimate on incurred data
(case reserve reductions) and must not by itself block a fit — it is
reported as a `warn` verdict, same `details` shape as before (offending
origin/dev/values). Fail-class is reserved for `no_gaps`,
`origin_dev_parseable`, and `basis_consistent` — structural problems no
method can safely fit through, as opposed to a plausible data feature.

`origin_dev_parseable` (v0.1.2): the development column is accepted in
either convention — a valuation year (e.g. `1982`, the calendar year of
that observation) or a development age (e.g. `12`, `24`, periods since
origin). Both are valid triangle CSV encodings and must parse.

Output `validation.json`:
```json
{
  "input": {"path": "…", "sha256": "…"},
  "basis": "cumulative",
  "basis_source": "inferred",
  "dimensions": {"origins": 10, "devs": 10},
  "checks": [
    {"check_id": "no_gaps", "verdict": "pass", "details": null},
    {"check_id": "monotone_cumulative", "verdict": "warn",
     "details": {"origin": "1984", "dev": 4, "values": [1234.0, 1201.5]}}
  ],
  "verdict": "warn"
}
```
`basis_source` (v0.1.13): `"declared"` if `--basis` was given, `"inferred"`
otherwise — always `null` alongside `basis` until parsing succeeds, same as
before.

Exit: 0 all pass or warn-only (verdicts stay visible) · 2 any fail
(`no_gaps`, `origin_dev_parseable`, or `basis_consistent`).

### `reserve fit <triangle.csv> --method mack|chain_ladder [--averaging volume|simple] [--tail none|constant:<f>] [--n-periods N] [--exclude-origins LIST] [--exclude-valuations LIST] [--basis cumulative|incremental] [--sigma-interpolation mack|log-linear] [--format] [--out] [--dry-run]`

Runs validate first (hard rule); refuses with exit 2 if validation fails.
Dispatches to the engine adapter. `--method` values outside adapter
`capabilities()` ⇒ exit 4. `--basis` (v0.1.13) is passed straight through to
the internal `validate` call — see the `validate` section for its full
semantics (declared-vs-inferred conflict fails `basis_consistent`, and thus
`fit`, before the adapter is ever consulted).

Supported reference-adapter methods:
- `mack` — Mack chain ladder with Mack standard errors.
- `chain_ladder` — deterministic/basic chain ladder using the same selected
  development factors and projection path, but no Mack standard-error
  calculation. Its `mack_se` fields are `null`, not zero.

**Basis mismatch** (v0.1.10; `basis_source` added v0.1.13): `capabilities()`
now declares `"basis": ["cumulative"]` — the adapter's `load_triangle` has
always hardcoded cumulative handling, previously an undeclared, silent
limitation. If the basis in effect (`validation.json: basis` — the declared
value when one was given and it agreed with inference, the inferred value
otherwise) isn't in that list, `fit` refuses with exit 2, printing a
structured error instead of the `validate` output:
```json
{"error": "unsupported_basis",
 "message": "engine adapter supports cumulative input only; inferred basis: incremental",
 "adapter_supported_basis": ["cumulative"], "inferred_basis": "incremental"}
```
When the basis in effect was declared rather than inferred, `message` says
so explicitly ("declared basis: …") and the payload gains `"basis_source":
"declared"` — the undeclared payload shape above is unchanged, byte for
byte, this key is only ever present when `--basis` was given.

The run folder still persists `validation.json` + `manifest.json`
(`exit_code: 2`, `outputs: ["validation.json"]`, no `fit.json`) — same
storage convention as any other validate-first refusal (v0.1.1), even
though `validate`'s own verdict was pass/warn: the refusal is about
declared adapter capability, not a structural defect in the data.

`fit` mints its `run_id`/folder before validating. If the internal
validate-first check fails, it still persists `validation.json` (same shape
as the standalone `validate` command's output) and `manifest.json`
(`exit_code: 2`, `outputs: ["validation.json"]`) into that folder — no
`fit.json` is written. A failed `fit` call is auditable the same way a
failed standalone `validate` call is (v0.1.1).

`validation.json` is now persisted on **every** successful `fit` too, not
just a failed one (v0.1.9 — previously `validation.json` and `fit.json`
never coexisted in one run folder). Needed so a rendered report can
highlight warn-class cells (`monotone_cumulative`, `nonneg_incrementals`)
against the actual triangle grid: those checks don't block a fit, so
without this change their details were computed in memory and then
discarded, with nothing on disk to reference. `outputs` for a successful
fit is now `["validation.json", "fit.json", "triangle.json"]`.

`--sigma-interpolation` (v0.1.7): controls how development-period sigma is
extrapolated for the last period. For `mack`, that sigma feeds Mack's
recursive standard-error formula, where the final period is otherwise
undefined for lack of a second data point. Default `mack` (Mack's own
minimum rule) — verified exactly against the published RAA standard errors
(VALIDATION.md). chainladder's own library default, `log-linear`, is also
available explicitly; it understates SE for origins that depend most heavily
on the extrapolated final sigma (e.g. 143 vs the published 206 for RAA
origin 1982) but is not "wrong" — both are legitimate statistical choices,
and the persisted `fit.json` always states which one was used. For
`chain_ladder`, sigma is retained in `development_factors` for review, but
the method does not produce Mack standard errors.

**Input snapshot** (v0.1.12): `fit` copies the input triangle CSV into
`runs/<run-id>/inputs/<original-filename>` before persisting anything else,
verifies the copy's sha256 against the hash already computed at validate
time, and records `"snapshot": "inputs/<filename>"` on the manifest's input
entry. This happens on every run folder `fit` creates — a validate-first
refusal and a basis-mismatch refusal included, not just a successful fit —
since each is its own self-contained audit object. `--dry-run` writes
nothing, snapshot included. See **Audit replay** under `diagnostics` for why.

Output `fit.json`:
```json
{
  "run_id": "…",
  "method": "mack",
  "parameters": {"averaging": "volume", "tail": "none", "n_periods": null,
                  "excluded_origins": [], "excluded_valuations": [],
                  "sigma_interpolation": "mack"},
  "development_factors": [
    {"from_dev": 1, "to_dev": 2, "ldf": 2.9994, "sigma": 0.4232}
  ],
  "by_origin": [
    {"origin": "1981", "latest": 18834.0, "ultimate": 18834.0,
     "ibnr": 0.0, "mack_se": 0.0}
  ],
  "totals": {"latest": 160987.0, "ultimate": 213122.2,
              "ibnr": 52135.2, "mack_se": 26909.0},
  "units": "as-input"
}
```
For `method: "chain_ladder"`, the same schema is used and every `mack_se`
field is `null`.

Output `triangle.json` (v0.1.9): the full origin × development grid — every
input (actual) cell plus every projected (lower-triangle) cell, cumulative,
full precision, bounded to the input triangle's own development range (a
tail beyond it is not represented here — see `fit.json: totals`/`by_origin`
for a tail-inclusive ultimate). `dev` is the same 1-indexed rank as
`development_factors`' `from_dev`/`to_dev`, not a raw age or valuation
year. Projected cells are reconstructed harness-side by applying `fit.json`'s
own `development_factors` LDFs forward from each origin's last actual
value — the same numbers `fit()` already returned, not re-derived from the
engine (engine-agnostic, like `sensitivity`). A projected cell is `null`
(never fabricated) if any LDF needed to reach it is itself undefined
(v0.1.5's null-as-undefined convention) — e.g. an aggressive
`--exclude-origins` leaving some transition inestimable.
```json
{
  "run_id": "…",
  "basis": "cumulative",
  "cells": [
    {"origin": "1981", "dev": 1, "value": 5012.0, "type": "actual"},
    {"origin": "1990", "dev": 2, "value": 6187.676897704888, "type": "projected"}
  ]
}
```
All floats at full precision; rounding is a rendering concern. Exit: 0, or 3 if
the engine emits fit-time warnings.

### `reserve diagnostics <run-id> [--format] [--out] [--dry-run]`

`--out` (v0.1.3): the runs root to locate `<run-id>` under (default
`./runs`) — needed because `diagnostics` amends an existing `fit` run's
folder in place (docs/QUESTIONS.md Q1) rather than minting its own, so it
must be told where that folder lives if `fit` used a non-default `--out`.
`sensitivity` already had this flag in v0.1; its absence here was an
inconsistency between two commands sharing the same run-folder model, not
a deliberate distinction.

`--dry-run` (v0.1.12): computes and prints `diagnostics.json` exactly as a
normal run would (`--format json`/`text` both work identically), but writes
nothing — `diagnostics.json` is not created and the run's manifest is not
amended. Exit code is unaffected: still 0 (`overall: pass`) or 3
(`overall: warn`), computed the same way regardless of `--dry-run`; a dry
run previews the *write*, not the assessment. Contract alignment: the
Global section has always said "`--dry-run` on any writing command", but
only `fit` had it wired in through v0.1.11 — `diagnostics` write to
`runs/` exactly as `fit` does and were missing it by oversight, not design.

**Audit replay** (v0.1.12): `diagnostics` re-fits internally to run its
assumption tests, which means re-reading the input triangle CSV. It replays
**exclusively** from the run's own snapshot (`runs/<run-id>/inputs/`,
written by `fit` — see the `fit` section) — never from the originally
recorded path, which may since have moved, changed, or been deleted. Before
any recompute, the snapshot's current sha256 is checked against the hash
`fit` recorded in the manifest; on a mismatch, `diagnostics` exits 1 with a
structured error instead of silently replaying against data that may not be
what was actually fit:
```json
{"error": "input_integrity_violation",
 "message": "input file at … does not match the sha256 recorded in this run's manifest — refusing to replay against data that may not be what was actually fit",
 "path_checked": "…", "expected_sha256": "…", "actual_sha256": "…"}
```
Run folders minted before v0.1.12 have no `"snapshot"` key in their
manifest's input entry; for these, `diagnostics` falls back to the
originally recorded path, but only after the same check — that path's
current sha256 must still match the manifest's recorded hash, or the same
integrity error is raised. Either way, a run folder is never replayed
against a file that doesn't match what was actually fit.

Runs assumption tests against an existing fit. Tests for chain-ladder-family
fits at v0.1:

| test_id | What it tests (Mack 1993/1994) |
|---|---|
| `dev_correlation` | Correlation of adjacent development factors |
| `calendar_year_effect` | Calendar-year (diagonal) effects |
| `residual_pattern_dev` | Standardised residuals vs development period |
| `residual_pattern_origin` | Standardised residuals vs origin |
| `outlier_link_ratios` | Individual link ratios beyond tolerance |

Output `diagnostics.json`:
```json
{
  "run_id": "…",
  "tests": [
    {"test_id": "calendar_year_effect", "statistic": 3.02,
     "threshold": 1.96, "verdict": "warn",
     "narrative_key": "cy_effect_warn",
     "prescribed_actions": [
       "reserve sensitivity <run-id> --exclude-valuations <flagged>",
       "reserve fit … --n-periods 5"
     ]}
  ],
  "overall": "warn"
}
```
Per-test `verdict` (v0.1.4) is two-way — `pass` or `warn` only. `fail` is
reserved for `validate`'s structural checks (data problems no method can
safely fit through); a diagnostics test is a soft statistical assumption
signal, not a hard block, so there is no second, harder threshold here to
distinguish a "fail" from a "warn" — `overall` is accordingly `pass` or
`warn` too, never `fail`. Exit: 0 all pass · 3 any warn. `narrative_key`
maps to fixed prose in the
`mack-diagnostics` skill; `prescribed_actions` is the agent's menu — it proposes
from this list, nothing else.

### `reserve sensitivity <run-id> [--grid default|FILE] [--exclude-origins …] [--exclude-valuations …] [--format] [--out] [--dry-run]`

**Audit replay** (v0.1.12): identical rule and mechanism as `diagnostics` —
`sensitivity` also re-fits internally (once per scenario) and so also
replays exclusively from the run's own snapshot, verifying its sha256
against the manifest first and exiting 1 with the same structured
`input_integrity_violation` error on mismatch, with the same legacy-folder
fallback for run folders minted before v0.1.12. See `diagnostics`' "Audit
replay" for the exact error shape.

`--dry-run` (v0.1.12): same contract as `diagnostics`' — the full grid is
still computed and printed, `sensitivity.json` is not written and the
manifest is not amended. Exit code is unaffected (always 0, `sensitivity`
never carries a verdict of its own).

**Manifest `exit_code` is carried forward, not overwritten** (v0.1.14 —
found by independent review): `sensitivity` always exits 0 itself, but
`docs/QUESTIONS.md` Q1's "overwrite `exit_code` with the latest command's
code" rule was written for commands that perform a genuine new pass/warn
assessment (`fit`, `diagnostics`). `sensitivity` doesn't assess anything —
it only computes descriptive scenarios over an already-assessed fit — so
literally applying Q1's rule let a clean `sensitivity` run silently erase a
real `diagnostics` warning (`exit_code: 3`) from the shared manifest,
letting a warned run read as clean from `reserve runs list`. `sensitivity`
now reads the run's current `exit_code` before amending the manifest and
passes that value straight through, same as `report` already did (see the
`report` section's `--dry-run` note) — the manifest keeps whatever the last
genuine assessment (`fit` or `diagnostics`) recorded, regardless of how many
non-assessing commands (`sensitivity`, `report`) run against the folder
afterwards.

Re-runs the fit over a perturbation grid. `--grid default` =
{drop oldest origin; drop latest diagonal; simple vs volume averaging;
n-periods ∈ {3, 5, all}; constant tail 1.00/1.02/1.05}. Custom grids as JSON
file (not yet implemented — v0.1 accepts only `--grid default`). Any grid
entry identical to the base fit's own parameters is skipped — a
"perturbation" that changes nothing isn't a scenario.

`--exclude-origins`/`--exclude-valuations` (v0.1.5): applied as an
additional baseline constraint layered onto *every* scenario in the grid —
the same semantics as on `fit`, not a standalone scenario and not a
replacement for `--grid`. Useful for "run the default grid, but always
excluding this known-bad origin regardless of scenario."

Output `sensitivity.json` (v0.1.5 — the exact shape, elided in the original
v0.1 text, spelled out here; `base_parameters` added v0.1.14):
```json
{
  "run_id": "…",
  "base_parameters": {"averaging": "volume", "tail": "none", "n_periods": null,
                        "excluded_origins": [], "excluded_valuations": [],
                        "sigma_interpolation": "mack"},
  "scenarios": [
    {"scenario_id": "drop_oldest_origin",
     "delta_from_base": {"parameter": "excluded_origins", "value": "1981"},
     "totals": {"ultimate": 215888.6, "ibnr": 54901.6, "mack_se": null}}
  ],
  "range": {"ibnr_min": 47823.2, "ibnr_max": 62099.2, "base_ibnr": 52135.2}
}
```
`scenarios` excludes the base case itself (already given via `range.base_ibnr`).

`base_parameters` (v0.1.14 — found by independent review): the base fit's own
parameters, with this call's `--exclude-origins`/`--exclude-valuations`
already layered on. Without it, a `sensitivity.json` produced with either
flag had no record of the baseline exclusion every `delta_from_base` in the
file was actually relative to — reconstructing it required the exact CLI
invocation used, which lived only in the free-text manifest `command` string,
not in `sensitivity.json` itself.

Null-as-undefined (v0.1.5): a `totals` field is `null` when that quantity
is genuinely undefined for the scenario — e.g. excluding the one origin
with data for a given development transition leaves that transition's LDF,
and Mack's standard error built from it, undefined. This is not the same
as a fully-developed origin's IBNR/mack_se, which is analytically exactly
`0.0`, not undefined — the two are never conflated. `range.ibnr_min`/
`ibnr_max` are computed over the finite scenario totals only; a scenario
with an undefined `ibnr` still reports that plainly in its own row, but is
excluded from the aggregate rather than corrupting it (undefined values
mixed into a naive min/max are unsafe either way: `None` raises, raw `NaN`
silently returns a wrong, comparison-order-dependent result without ever
raising). Applies to every command's `--format json` output, not just
`sensitivity` — `json.dumps` on a raw NaN/Infinity float emits the literal
tokens `NaN`/`Infinity`, which is not valid JSON per RFC 8259.

Exit 0 always, regardless of any scenario producing an undefined total —
sensitivity output is descriptive; interpretation language lives in the
`sensitivity-analysis` skill, and no output shape here should be read as a
verdict.

### `reserve report <run-id> [--format-out html|md] [--require-approval] [--out] [--dry-run]`

Deterministic renderer over the run folder's JSON. **Reads only `runs/<run-id>/`;
takes no numeric arguments** — there is no way to inject a figure through this
command. No LLM call and no network access — every number on the page is read
directly from `manifest.json`/`validation.json`/`fit.json`/`diagnostics.json`/
`sensitivity.json`; the last two are read if present, otherwise that section
states plainly they haven't been run rather than fabricating content.
`--format-out md` is declared but not yet implemented (exit 4) — v0.1 only
requires `html`.

**Why `--format-out`, not `--format`** (v0.1.12 — spec text corrected to
match the implementation, which has used `--format-out` since Phase 5/
v0.1.8): every other command's `--format` selects `json|text`, the
*encoding* of the same structured payload on stdout. `report`'s own flag
selects a fundamentally different axis — which *document* to produce
(`html` vs `md`), not how to encode one. Reusing `--format` for both would
silently overload one flag with two unrelated meanings depending which
command it's given to; `--format-out` keeps the axes separate. This is a
naming correction to this file only — `report` never actually accepted
`--format`, and no code changes accompany this entry.

`--dry-run` (v0.1.12): renders the HTML in memory and still prints the
would-be `report.html` path to stdout (the "intended action"), but writes
neither the file nor the manifest update. Contract alignment, same as
`diagnostics`/`sensitivity` above — `report` writes to `runs/` exactly like
every other command in this table and was missing `--dry-run` by
oversight, not design.

`--require-approval` (v0.2.8): enforces the workbench governance gate before
rendering. The command exits 4 and writes no report if any required warning,
scenario-selection, or BCL-review tasks are still pending; if a committed
selection set has never been approved; if multiple active selection approvals
make the reporting basis ambiguous; if material hashes are stale; if there is
no active `report_approval`; or if its immutable review snapshot no longer
matches the active decisions, selected basis, source hashes, and renderer.
This is the final-report path for Claude commands and dashboard workflows.

Without `--require-approval`, current draft rendering remains available for
exploration and testing, but the HTML Governance section must mark the output
as `draft/incomplete` whenever governance is incomplete and state why, for
example `no active report_approval decision` or a pending-task count. A draft
report is not a governed approval artifact.

**Section structure** (v0.2.7): 0 Scope & basis of preparation, 1 Executive
summary, 2 Data & validation, 3 Method & parameters, 4 Results, 5 Diagnostics,
6 Sensitivity, 7 Selection set, 8 Limitations & reliances, 9 Governance —
matching `.claude/skills/reserving-report/SKILL.md`'s current structure.
Diagnostics tests
render with a pass/warn badge (visual and textual, not color-only) and the
fixed narration keyed by `narrative_key` — the same prose as the
`mack-diagnostics` skill, necessarily duplicated as plain data here since
this renderer has no LLM in the loop to read the skill's markdown.

**Null-as-undefined** (v0.1.8): any `null` result field (a total, a
by-origin reserve/std-err, a sensitivity scenario/range value, or a
development factor left inestimable by an exclusion) renders as the literal
word "undefined" with a note that it is not zero — never as `0` and never
as a blank cell. This is distinct from a `null` that has an ordinary,
non-alarming meaning as a *parameter* (`parameters.n_periods: null` meaning
"all periods"; a fixed tail's `development_factors[].sigma: null` meaning
"not applicable, no distribution") — those render as their plain meaning,
not as "undefined."

**Traceability** (v0.1.8): every rendered figure is wrapped with a hover
title attribute naming its exact source field (e.g.
`fit.json: totals.ibnr`) — inline, native HTML, no JavaScript.

**Self-contained** (v0.1.8): single HTML file, inline CSS, no external
assets (fonts, scripts, images) of any kind — must render fully offline.
Print-formatted for A4 (`@page` rules; tables and diagnostic blocks avoid
breaking across a page boundary) since review packs are expected to be
archived as PDFs.

**Visuals** (v0.1.9), all pure HTML/CSS — no `<script>`, no SVG/canvas:
- **Development-triangle grid** (§4, from `triangle.json`): the full
  origin × dev grid, actual cells on the plain surface, projected cells on
  a light tint (secondary encoding: also italicized, not color-alone). The
  latest diagonal (the actual/projected boundary) is outlined, not filled —
  a structural marker, not a value encoding. Any cell named in a
  `validation.json` warn-class check's `details` (`monotone_cumulative`,
  `nonneg_incrementals`) gets the status "warning" color plus a superscript
  footnote marker, with the explanation below the grid — the visible label
  is the required relief channel for a warning-level color that sits below
  3:1 contrast by itself.
- **Per-origin IBNR bars with ±1 SE whiskers** (§4): one bar per origin,
  single series (the sequential blue ramp, one hue), value labelled past
  the bar's end so it's never clipped; the whisker is omitted (not
  zero-length) for a `null` `mack_se`, consistent with null-as-undefined.
- **Sensitivity min–base–max strip** (§6, from `sensitivity.json: range`):
  a single horizontal track, a wash spanning min→max, a marker at base. If
  every scenario and the base are non-finite, the strip is replaced with a
  plain "range unavailable" note rather than drawing an empty track.
- **`tabular-nums`** throughout every column of numbers (grid cells, table
  cells, bar/whisker/strip labels) so digits align vertically — proportional
  figures are for prose, not columns.
- Status/sequential colors are the fixed, pre-validated steps from the
  house palette, not eyeballed — see the palette reference the renderer's
  CSS comments point to.

**Governance footer** (updated v0.2.7): `run_id`, input `sha256`,
`engine.package`/`engine.version`, `environment.harness_version`,
`created_utc`, governance status, and governance detail. Static run metadata
is read verbatim from `manifest.json`; governance status is derived from
`validation_tasks.json`/`decisions/*.json`.

Exit 0 · 4 if the run folder is incomplete for reporting (folder doesn't
exist, or is missing `manifest.json`/`fit.json` — the two files every
section other than Diagnostics/Sensitivity depends on) · 4 for
`--require-approval` governance failures · 4 for `--format-out md` until it
exists.

### `reserve runs [list|show <run-id>] [--format] [--out]`

`--out` (v0.1.6): same gap as `diagnostics` had pre-v0.1.3 — "inventory of
the runs root" needs to be told which root when it isn't the default
`./runs`. Read-only. `list` output: `{"runs": [<manifest>, ...]}`, one
entry per run under the root, sorted by run_id (chronologically, since
run_id is timestamp-prefixed). `show <run-id>` output: that run's
`manifest.json` content verbatim. Exit 0 for `list` always; `show` on an
unknown run-id is a usage error (exit 4), same as `diagnostics`/
`sensitivity` on an unknown run-id.

### `reserve tasks <run-id> [--format] [--out] [--dry-run]`

Phase 1 workbench command. Builds or refreshes
`runs/<run-id>/validation_tasks.json`, the dashboard/agent work queue for
human validation. It reads only existing run artifacts and immutable
decision files under `runs/<run-id>/decisions/`; it does not call the
engine and never computes reserve figures.

Task generation is deterministic from run artifacts:
- warn-class checks in `validation.json` create `warning_review` tasks;
- warning verdicts in `diagnostics.json` create `warning_review` tasks;
- if `sensitivity.json` exists, a `scenario_selection` task is created;
- deterministic chain ladder runs (`chain_ladder`, `chainladder`, or `bcl`)
  create a `bcl_review` task when no active report approval exists;
- once prerequisite warning/scenario/BCL-review tasks are completed, and no
  active report approval exists, a `report_approval` task is created;
- if `diagnostics.json` is missing, no diagnostics warning task is
  fabricated and report approval is not created.

Output `validation_tasks.json`:
```json
{
  "schema_version": "0.1",
  "run_id": "…",
  "status": "ready|needs_judgment|report_ready|signed_off|incomplete",
  "tasks": [
    {
      "task_id": "warning_diagnostics_…",
      "task_type": "warning_review",
      "status": "pending",
      "severity": "warning",
      "title": "Review diagnostics warning: calendar_year_effect",
      "description": "…",
      "source_artifacts": ["diagnostics.json"],
      "evidence_refs": [{"artifact": "diagnostics.json", "path": "$.tests[0].verdict"}],
      "allowed_decision_types": ["warning_ack"],
      "created_utc": "…",
      "completed_by_decision_id": null
    }
  ]
}
```

`validation_tasks.json` may be regenerated. Completed decisions are never
stored by mutating this file; they live as immutable JSON files under
`decisions/`, and task completion is derived from those files on refresh.

### `reserve status <run-id> [--format] [--out]`

Phase 1 workbench read-only command. Prints derived run status, artifact
availability, unresolved task count, and decision counts. This command does
not write `validation_tasks.json`; it derives status in memory from the
same artifact and decision rules as `reserve tasks`.

Output:
```json
{
  "run_id": "…",
  "status": "needs_judgment",
  "artifacts": {"manifest.json": true, "diagnostics.json": true},
  "missing_required_artifacts": [],
  "task_count": 2,
  "unresolved_task_count": 1,
  "completed_decision_count": 1,
  "decision_count": 1,
  "validation_tasks_path": "runs/<run-id>/validation_tasks.json"
}
```

### `reserve handoff <run-id> [--format] [--out] [--dry-run]`

Writes `review_handoff.json`, the structured AI-to-actuary pause/resume
contract. It contains the method, workflow phase, pending judgment tasks and
allowed decisions, current governed reporting basis, next deterministic AI
commands, `/review <run-id>` resume command, and source hashes. It never
constitutes approval and does not choose factors or scenarios.

### `reserve scenarios <run-id> [--format] [--out] [--dry-run]`

Phase 1.5 workbench command. Builds or refreshes
`runs/<run-id>/scenario_index.json`, a model-agnostic scenario preview index
for the future dashboard. This command reads deterministic outputs already
written by existing commands; it does not call the engine and does not
change reserve calculations.

At v0.2.1 the index contains:
- a `base` scenario from `fit.json`;
- sensitivity candidates from `sensitivity.json`, when present.

Output `scenario_index.json`:
```json
{
  "schema_version": "0.1",
  "run_id": "…",
  "status": "available",
  "generated_from": ["fit.json", "sensitivity.json"],
  "scenarios": [
    {
      "scenario_id": "drop_oldest_origin",
      "basis_run_id": "…",
      "scenario_run_id": null,
      "artifact_path": "sensitivity.json#/scenarios/0",
      "scenario_type": "exclusion",
      "parameters": {"excluded_origins": ["1981"]},
      "command": "reserve sensitivity <run-id> --grid default",
      "created_utc": "…",
      "source_artifacts": ["fit.json", "sensitivity.json"],
      "output_artifacts": ["sensitivity.json"],
      "key_metrics": {"ultimate": 210000.0, "ibnr": 50000.0, "mack_se": null},
      "input_hashes": {"fit.json": "…", "sensitivity.json": "…"},
      "status": "available"
    }
  ]
}
```

Scenario preview is exploratory. Scenario selection is governed separately
by a committed `scenario_selection` decision.

### `reserve compare <run-id> --scenario-id ID [--format] [--out] [--dry-run]`

Phase 1.5 workbench command. Compares one indexed scenario candidate against
the base scenario and writes
`runs/<run-id>/comparisons/<comparison_id>.json`. The command refreshes
`scenario_index.json` before writing a comparison, then computes metric
deltas from the indexed artifacts only.

Output:
```json
{
  "schema_version": "0.1",
  "comparison_id": "comparison_…",
  "base_run_id": "…",
  "candidate_scenario_id": "drop_oldest_origin",
  "compared_metrics": {
    "ibnr": {"base": 52135.2, "candidate": 50000.0}
  },
  "deltas": {"ibnr": -2135.2},
  "source_artifacts": ["scenario_index.json", "fit.json", "sensitivity.json"],
  "input_hashes": {"scenario_index.json": "…", "fit.json": "…"},
  "generated_utc": "…"
}
```

### `reserve selection-sets list <run-id> [--format] [--out]`

Phase 2.2 workbench command. Lists governed deterministic chain ladder
selection-set artifacts already present under
`runs/<run-id>/selection_sets/`. This command is read-only.

Output:
```json
{
  "schema_version": "0.1",
  "run_id": "…",
  "selection_sets": [
    {
      "selection_set_id": "selection_set_abc123",
      "preview_scenario_id": "selection_set_abc123",
      "status": "preview|committed",
      "selection_set_artifact": "selection_sets/selection_set_abc123.json"
    }
  ]
}
```

### `reserve selection-sets show <run-id> <selection-set-id> [--format] [--out]`

Phase 2.2 workbench command. Prints one selection-set artifact exactly as it
is stored. It exits 4 if the artifact does not exist.

### `reserve selection-sets preview <run-id> --request-file FILE [--format] [--out] [--dry-run]`

Phase 2.2 workbench command. Uses the same backend selection-set preview
logic as the dashboard endpoint
`POST /api/runs/{run_id}/selection-sets/preview`. It is currently supported
only for deterministic chain ladder runs (`chain_ladder`, `chainladder`, or
`bcl`). The command validates requested factor choices against available
fitted/candidate bases in `fit.json`, validates required rationale, reruns
the deterministic chain ladder through the existing engine path, and writes
`selection_sets/<selection_set_id>.json` with `status: preview`.

The frontend and CLI do not compute actuarial outputs. Preview metrics are
returned from the backend artifact produced by this deterministic replay.
If the stable selection-set id already exists as `status: preview`, the
existing artifact is returned. If it already exists as `status: committed`,
the command exits 4 rather than overwriting it.

Request file schema:
```json
{
  "schema_version": "0.1",
  "run_id": "optional, must match the CLI run id when present",
  "factor_selections": [
    {
      "development_age": "1 -> 2",
      "from_dev": 1,
      "selected_basis": "fitted|volume_weighted|simple_average|last_3|last_5",
      "selected_factor": 4.693781280053931,
      "rationale": "Required when the selected factor differs from the fitted factor."
    }
  ],
  "exclusions": [
    {
      "type": "origin|valuation",
      "value": "1981",
      "rationale": "Required for every exclusion."
    }
  ],
  "global_rationale": "Scenario-level rationale for the combined selection set.",
  "created_by": {"id": "actuary", "display_name": "Actuary"}
}
```

`development_age` or `from_dev` may identify the factor. `selected_factor`
is optional; when present it must match the candidate value for
`selected_basis`. `factor_selections` and `exclusions` cannot both be empty.

Output selection-set artifact:
```json
{
  "schema_version": "0.1",
  "selection_set_id": "selection_set_abc123",
  "preview_scenario_id": "selection_set_abc123",
  "run_id": "…",
  "basis_run_id": "…",
  "status": "preview",
  "factor_selections": [],
  "exclusions": [],
  "global_rationale": "…",
  "source_artifacts": ["fit.json", "triangle.json", "validation.json"],
  "input_hashes": {"fit.json": "…"},
  "selected_factors_used": [],
  "exclusions_used": [],
  "parameters": {},
  "command": "reserve selection-sets preview …",
  "comparison": {
    "base": {"latest": 160987.0, "ultimate": 213122.2, "ibnr": 52135.2},
    "candidate": {"latest": 160987.0, "ultimate": 215000.0, "ibnr": 54013.0},
    "deltas": {"ultimate": 1877.8, "ibnr": 1877.8},
    "by_origin_ibnr_impact": []
  },
  "candidate_fit": {},
  "selection_set_artifact": "selection_sets/selection_set_abc123.json"
}
```

### `reserve selection-sets commit <run-id> --selection-set-id ID --decision-file FILE [--format] [--out] [--dry-run]`

Phase 2.2 workbench command. Commits an existing preview selection set and
the required approval decision as one governed CLI workflow. The command
uses `harness.selection_sets.commit_selection_set` for the selection-set
lifecycle and `harness.workbench.decisions.commit_decision_payload` for the
decision write, so it enforces the same validation rules as
`reserve decide`.

The decision file must be a valid `selection_set_approval` artifact whose
`selection_set_id` matches `--selection-set-id`. The referenced selection
set must exist, must still be a preview, must have current source-artifact
hashes, and must contain required rationale. The decision must reference the
selection-set artifact in `source_artifacts_reviewed`, and
`resulting_scenario_id` must match the selection set's
`preview_scenario_id`.

On success, the command:
- marks `selection_sets/<selection_set_id>.json` as `status: committed`;
- writes `decisions/<decision_id>.json` immutably;
- refreshes `validation_tasks.json`;
- appends those outputs to the manifest without changing the run's current
  assessment `exit_code`.

If the decision artifact fails validation after the selection set has been
temporarily marked committed, the command restores the original preview
artifact and exits 4. `--dry-run` validates the full workflow, returns the
would-be committed selection set and decision payload, and restores the
preview without writing a decision or manifest update.

Output:
```json
{
  "selection_set": {"selection_set_id": "selection_set_abc123", "status": "committed"},
  "decision": {"decision_id": "approve_selection_set_001", "decision_type": "selection_set_approval"},
  "status": {
    "run_id": "…",
    "status": "report_ready",
    "unresolved_task_count": 1
  }
}
```

### `reserve decide <run-id> --decision-file FILE [--format] [--out] [--dry-run]`

Phase 1 workbench command. Validates a human decision JSON file and writes it
immutably to `runs/<run-id>/decisions/<decision_id>.json`. It fails with
exit 4 if that file already exists; decisions are never overwritten in
place. A later decision can change an outcome only by referencing
`supersedes_decision_id`.

Supported workbench `decision_type` values:
`warning_ack`, `scenario_selection`, `method_review_ack`,
`factor_selection`, `selection_set_approval`, `report_approval`.
Governed selection sets support backend-previewed candidate factors, manual
overrides, origin/valuation/factor-point exclusions, and constant tails. The
actuary must provide rationale and identity; the browser does not calculate
the resulting reserves.

Decision artifact:
```json
{
  "schema_version": "0.1",
  "decision_id": "ack_calendar_warning_001",
  "run_id": "…",
  "task_id": "warning_diagnostics_…",
  "decision_type": "warning_ack",
  "status": "accepted",
  "rationale": "Reviewed and acknowledged by the actuary.",
  "user": {"id": "user-id", "display_name": "User Name"},
  "timestamp_utc": "…",
  "source_artifacts_reviewed": ["fit.json", "triangle.json", "diagnostics.json"],
  "commands_or_parameters_affected": [],
  "resulting_scenario_id": null,
  "supersedes_decision_id": null,
  "input_hashes": {"fit.json": "…", "diagnostics.json": "…"}
}
```

Rules:
- `rationale` is required for every `warning_ack`, `method_review_ack`,
  `factor_selection`, and `selection_set_approval`, and for any decision
  with status `modified` or `rejected`.
- non-approval decisions must reference an existing task id, except
  `factor_selection` and `selection_set_approval`, which may be standalone
  when they reference known preview artifacts; `report_approval` may be
  standalone only when prerequisite tasks are not pending and diagnostics
  exist.
- `scenario_selection` with status `accepted` or `modified` must include
  `resulting_scenario_id`, that id must exist in `scenario_index.json`,
  `source_artifacts_reviewed` must include `scenario_index.json`, and the
  indexed scenario's source-artifact hashes must still match the current
  run folder. If not, refresh with `reserve scenarios` before committing.
- `factor_selection` with status `accepted` or `modified` must include
  development age, previous factor, selected factor, selected basis,
  rationale, and `resulting_scenario_id`. The scenario id must exist in
  `factor_previews/<scenario_id>.json`; selected factor fields must match
  the preview; `source_artifacts_reviewed` must include the preview artifact;
  and the preview source-artifact hashes must still match the current run
  folder.
- `selection_set_approval` with status `accepted` or `modified` must include
  `selection_set_id`, `resulting_scenario_id`, and rationale. The referenced
  artifact `selection_sets/<selection_set_id>.json` must exist, must have
  `status: committed`, and its `preview_scenario_id` must equal
  `resulting_scenario_id`. `source_artifacts_reviewed` must include the
  selection-set artifact, and the selection set's source-artifact hashes
  must still match the current run folder.
- only one accepted/modified `selection_set_approval` may be active. A new
  reporting basis must explicitly supersede the current one.
- `report_approval` is bound to
  `review_snapshots/<review_snapshot_id>.json`. The snapshot records the
  exact active decisions, selected scenario/selection set, material hashes,
  and report renderer/template hashes. A later material change requires a
  new report approval that supersedes the prior decision.
- `source_artifacts_reviewed` is hashed at commit time where files exist;
  the writer records those hashes in `input_hashes`.
- after a successful decision write, `validation_tasks.json` is refreshed and
  the manifest output list is appended without changing the run's current
  assessment `exit_code`.

### `reserve factor-analysis <run-id> [--format json|text] [--out] [--dry-run]`

Builds deterministic BCL link-ratio review evidence. For each observed
factor point, the existing chain-ladder adapter is replayed with that point
excluded. The command writes `factor_analysis.json` with leave-one-out
factor, ultimate, and IBNR influence, plus
`factor_review_suggestions.json` with model-agnostic review prompts.
Suggestions are exploratory evidence only: they cannot stage a selection,
commit judgment, or enter an approved report without the existing governed
preview and decision lifecycle.

### `reserve dashboard [--out] [--host HOST] [--port PORT]`

Phase 2 local workbench command. Starts the FastAPI-backed dashboard MVP
against the selected runs root. Default host is `127.0.0.1`; default port is
`8000`.

The dashboard is a local human-validation surface over the same artifacts
used by the CLI. It does not authenticate users, does not run actuarial
calculations in the browser, and does not contain a chat panel. Manual
overrides are supported only through governed backend preview and approval.

Dashboard chain ladder and selection endpoints:
- `GET /api/runs/{run_id}/factor-analysis` and
  `GET /api/runs/{run_id}/factor-review-suggestions`: read deterministic
  link-ratio influence and review evidence.
- `POST /api/runs/{run_id}/factor-analysis/refresh`: explicitly rebuilds
  those artifacts through deterministic engine replays.
- `GET /api/runs/{run_id}/chain-ladder/summary`: method label, input file,
  total latest, total ultimate, total IBNR, period counts, and selected
  scenario if an active `scenario_selection` decision exists.
- `GET /api/runs/{run_id}/chain-ladder/factors`: development factors from
  `fit.json`, with candidate averages shown only when already present.
- `GET /api/runs/{run_id}/chain-ladder/projection`: `fit.json: by_origin`
  latest, ultimate, and IBNR rows, plus selected scenario impact only when
  an existing comparison artifact contains origin-level impact data.
- `POST /api/runs/{run_id}/factor-preview`: writes
  `factor_previews/<scenario_id>.json` after rerunning deterministic chain
  ladder through the engine layer for a known candidate basis, then returns
  base/candidate total ultimate, total IBNR, deltas, and by-origin IBNR
  impact.
- `GET /api/runs/{run_id}/selection-sets`: lists governed selection-set
  artifacts for the run.
- `POST /api/runs/{run_id}/selection-sets/preview`: writes
  `selection_sets/<selection_set_id>.json` with `status: preview` after
  rerunning deterministic chain ladder through the engine layer for multiple
  candidate choices, manual overrides, origin/valuation/factor-point
  exclusions, and constant tails. It returns base/candidate latest, ultimate, IBNR, deltas,
  by-origin IBNR impact, selected factors used, exclusions used, replay
  parameters, command trail, and input hashes.
- `POST /api/runs/{run_id}/selection-sets/{selection_set_id}/commit`: marks
  a preview selection set committed after validating the global rationale
  and per-selection/per-exclusion rationale requirements. Committed
  selection sets are not overwritten.

### Roadmap (declared, not implemented)

`reserve backtest` (CLRD upper-triangle fit vs realised outcomes) ·
methods `bf`, `capecod`, `bootstrap` · portfolio mode (multi-segment + roll-up).

**Governance surface per destination** (v0.1.11 onward):
- **`selections`** (judgment overriding a computed factor): v0.2.7 supports
  governed BCL selection sets for multiple known candidate-basis factor
  choices plus simple origin/valuation exclusions. The browser stages
  choices, or the CLI can stage them through `reserve selection-sets
  preview`; the backend computes preview impacts through the deterministic
  harness/engine path; and `reserve selection-sets commit` validates a
  `selection_set_approval` decision against the committed artifact before
  report disclosure. Governed manual override and factor-point exclusions
  are supported; direct arbitrary cumulative-cell deletion and multi-segment
  selected-factor programs remain future work. A selection is
  only auditable if the reason for every deviation from the indicated factor
  is itself a recorded, traceable input.
- **`bf`/`capecod`** (a priori-driven methods): the a priori itself as a
  declared input with provenance — an expected loss ratio or on-level
  premium is a judgment input the same way a selection is, and needs the
  same "where did this number come from" trail.
- **`bootstrap`**: a distribution output schema (not a point estimate) plus
  the random seed recorded in the manifest — a stochastic method is only
  reproducible if the seed is itself part of the audit trail.
- **`ifrs17_bridge`**: discounting and payment-pattern assumptions as
  declared inputs, the risk adjustment derived from the stochastic output
  rather than picked, and confidence-level traceability end to end — an
  IFRS 17 figure inherits every governance requirement of the reserve it's
  built from, plus its own.

## Changelog

- v0.2.9 (2026-07-10): Dynamic BCL factor review evidence.
  - Adds deterministic leave-one-out link-ratio influence and model-agnostic
    review-suggestion artifacts, with CLI and API access.
  - Adds a dynamic linear/log Factor Workbench plot, influence inspection,
    candidate-line actions, preview-refitted overlays, and governed
    suggestion dispositions.
  - Adds approved-report factor-curve, link-ratio, exclusion, evidence-
    disposition, and impact exhibits. No suggestion can commit judgment.

- v0.2.8 (2026-07-10): Demo workflow hardening.
  - Adds immutable review snapshots and binds report approval to the exact
    reporting basis, fixing stale approval reuse after later selections.
  - Enforces one active selection approval with explicit supersession and
    uses atomic JSON writes for mutable and immutable artifacts.
  - Adds governed constant-tail preview, structured `reserve handoff`, a
    packaged v2 dashboard, browser regression coverage, and CI.
- v0.2.7 (2026-07-06): CLI parity for governed selection sets and hard
  report approval gating.
  - Adds `reserve selection-sets list`, `show`, `preview`, and `commit`.
    The CLI uses the same backend selection-set lifecycle as the dashboard
    and the same immutable decision validation path as `reserve decide`.
  - Selection-set commit now requires a valid `selection_set_approval`
    decision file, validates the referenced committed artifact, rejects
    stale source-artifact hashes, rolls back on decision-validation failure,
    and supports `--dry-run` without leaving committed artifacts behind.
  - Adds `reserve report --require-approval`, which fails before rendering
    when required workbench tasks remain unresolved, report approval is
    missing, or a committed selection set lacks active
    `selection_set_approval`. The gate also rejects stale approval decisions
    when their recorded material reviewed-artifact hashes no longer match the
    run folder.
  - Draft report rendering without `--require-approval` remains available,
    but the Governance section now labels incomplete governance as
    `draft/incomplete` and states the missing approval or pending-task
    reason.
- v0.2.6 (2026-07-06): Governed BCL selection sets and exclusions.
  Adds `selection_sets/<selection_set_id>.json` artifacts for combined
  deterministic chain ladder factor choices and simple origin/valuation
  exclusions. Adds dashboard/API support for previewing and committing a
  selection set, immutable `selection_set_approval` decisions validated
  against committed selection-set artifacts, selected-scenario display from
  selection-set approval, and report disclosure of selected factors,
  exclusions, rationale, scenario id, decision id, comparison, and
  reproducibility hashes. The browser still does not calculate actuarial
  outputs; arbitrary manual override, cell-level exclusions, production auth,
  chat, and portfolio mode remain future work.
- v0.2.5 (2026-07-06): First governed BCL factor-selection workflow.
  Enriches deterministic chain ladder `fit.json` with link ratios,
  candidate averages, factor basis, and cumulative development factors.
  Adds backend factor preview artifacts under `factor_previews/`, a
  dashboard Impact Preview flow, and immutable `factor_selection` decisions
  validated against known preview scenarios. The browser still does not
  calculate actuarial impacts, arbitrary manual override is still out of
  scope, and portfolio mode remains future work.
- v0.2.4 (2026-07-06): Minimal deterministic chain ladder dashboard workflow.
  Adds read-only dashboard/API projections for chain ladder summary, factors,
  and by-origin projection from existing artifacts. Deterministic chain
  ladder runs now generate a `bcl_review` task, completed by a
  `method_review_ack` decision with rationale, before report approval can be
  reached. No manual selected-factor override or refit is implemented.
- v0.2.3 (2026-07-06): `reserve fit` gains `--method chain_ladder`.
  This is the deterministic/basic chain-ladder method over the same
  selected development factors used by Mack. It writes the same `fit.json`
  shape as `mack`, with `mack_se: null` because the method does not produce
  Mack standard errors. Sensitivity and workbench scenario previews work
  through the existing deterministic `fit()` path.
- v0.2.2 (2026-07-06): Interactive Reserving Workbench Phase 2.
  Adds a minimal local FastAPI/static dashboard MVP for the human-validation
  loop.
  - New `harness/workbench/api.py` exposes run status, task refresh,
    decisions, scenario previews, scenario comparisons, and safe JSON
    artifact reads.
  - New static dashboard under `dashboard/static/` with a three-column
    workbench layout.
  - New `reserve dashboard` command starts the local dashboard.
  - Decision writes still go through existing workbench validation and
    immutable decision writers. The frontend does not calculate actuarial
    outputs.
- v0.2.1 (2026-07-06): Interactive Reserving Workbench Phase 1.5.
  Adds scenario preview artifacts and decision lifecycle hardening without
  building dashboard UI, selected-factor refitting, or new calculation
  paths.
  - New `scenario_index.json` indexes the base fit and sensitivity
    candidates from existing deterministic artifacts.
  - New `reserve scenarios` command builds/lists scenario candidates.
  - New `reserve compare` command writes
    `comparisons/<comparison_id>.json` deltas against the base run.
  - `scenario_selection` decisions now require a valid
    `resulting_scenario_id` from `scenario_index.json`, require the decision
    to hash `scenario_index.json`, and reject stale index entries whose
    source artifacts have changed.
- v0.2.0 (2026-07-06): Interactive Reserving Workbench Phase 1.
  Adds the file-artifact foundation for a future professional dashboard
  without building the dashboard UI and without changing reserving
  calculations.
  - New `harness/workbench/` package generates validation tasks, validates
    immutable decision artifacts, and derives run status from existing run
    JSON.
  - New artifacts: `validation_tasks.json` and
    `decisions/<decision_id>.json`.
  - New commands: `reserve tasks`, `reserve status`, `reserve decide`.
  - Supported Phase 1 decision types at initial release: `warning_ack`,
    `scenario_selection`, `report_approval`. Later versions add
    `method_review_ack` for deterministic chain ladder dashboard review and
    `factor_selection` for governed BCL candidate-basis preview decisions.
    v0.2.6 adds `selection_set_approval` for committed multi-factor BCL
    selection sets with simple exclusions. Arbitrary manual selected-factor
    override remains future work.
  - The workbench layer is model-agnostic: it reads existing artifacts and
    writes human-judgment artifacts only. It does not import the reference
    chainladder adapter and does not compute reserve figures.
- v0.1 (2026-07-02): initial freeze.
- v0.1.1 (2026-07-02): clarifications resolving two gaps found during
  implementation (full discussion in `docs/QUESTIONS.md`), confirmed by
  Ivan Perincic:
  - `fit`'s internal validate-first check now explicitly persists
    `validation.json` + `manifest.json` (`exit_code: 2`) on failure, rather
    than failing silently. See the `fit` section.
  - `basis_consistent` is defined as inference-only for v0.1 — no `--basis`
    flag exists yet, so "declared vs inferred" in the original v0.1 text is
    read as a forward-compatible hook, not current behaviour. See the
    `validate` section.
- v0.1.2 (2026-07-02): actuarial correction from Ivan Perincic — negative
  development between consecutive valuations is legitimate on incurred data
  (case reserve reductions), so it must not hard-block a fit.
  - `monotone_cumulative` is now warn-class, not fail-class. Fail-class for
    `validate` is now exactly `no_gaps`, `origin_dev_parseable`, and
    `basis_consistent` ("mixed basis" — no single basis interpretation
    explains the data). `validation.json`'s top-level `verdict` is
    accordingly three-way (`pass`/`warn`/`fail`) — this was already implied
    by `nonneg_incrementals` being warn-only since v0.1, just not spelled
    out. (v0.1.4 narrows this: `diagnostics`' `overall` is two-way only,
    `pass`/`warn` — see below. `validate` keeps the three-way enum, since
    its checks include genuine hard structural failures.)
  - `origin_dev_parseable` now explicitly accepts the development column
    labelled as either a valuation year or a development age. See the
    `validate` section.
- v0.1.3 (2026-07-02): `diagnostics` gains `--out`, matching `sensitivity`'s
  signature — both amend an existing `fit` run's folder in place rather
  than minting their own (docs/QUESTIONS.md Q1), so both need to be told
  where that folder is when `fit` used a non-default `--out`. The missing
  flag in v0.1's `diagnostics` signature was an inconsistency versus
  `sensitivity` in the same document, not an intentional restriction.
- v0.1.4 (2026-07-02): per-test `verdict` (and therefore `overall`) in
  `diagnostics.json` is two-way — `pass`/`warn` only. `fail` remains
  exclusive to `validate`'s structural checks. See the `diagnostics`
  section.
- v0.1.5 (2026-07-02): documents three things the v0.1 `sensitivity` text
  left unspecified, all already true of the implementation: the exact
  `sensitivity.json` shape (`{"run_id", "scenarios": [...], "range": {...}}`
  — the array needed a wrapper key to carry `range` alongside it), the
  null-as-undefined convention for any command's `--format json` output
  (distinct from a fully-developed origin's analytically-zero IBNR/
  mack_se — never conflated), and `--exclude-origins`/`--exclude-valuations`
  layering onto every grid scenario as a baseline constraint. See the
  `sensitivity` section.
- v0.1.6 (2026-07-02): `runs` gains `--out`, the same class of gap
  `diagnostics` had before v0.1.3 — an inventory command needs to be told
  which root to inventory when it isn't the default. Also spells out
  `list`/`show`'s exact output shapes, left unstated in v0.1. See the
  `runs` section.
- v0.1.7 (2026-07-02): manual verification against the published literature
  complete (VALIDATION.md) — RAA is correctly Mack (1994, CAS Spring Forum),
  not Mack (1993) as originally (mis)cited throughout this repo; GenIns
  verified against Mack (1993) Table 2 instead. `fit` gains
  `--sigma-interpolation mack|log-linear`, default `mack` — the setting
  under which the adapter reproduces every published RAA standard error
  exactly, replacing chainladder's own library default (`log-linear`),
  which understates SE for origins that depend most on the extrapolated
  final-period sigma. See the `fit` section.
- v0.1.8 (2026-07-03): `reserve report` implemented (Phase 5) —
  deterministic HTML renderer, `harness/render/report_html.py` +
  `harness/render/templates/report.html`. Spells out what the original v0.1
  text left unstated: the section structure (0–8, matching
  `.claude/skills/reserving-report/SKILL.md` exactly), the null-as-undefined
  rendering convention (and its exception for parameter fields where `null`
  has an ordinary meaning), the fixed-narration duplication rationale (no
  LLM in this renderer's loop, so the same prose as `mack-diagnostics`
  exists as plain Python data here too), the hover-title traceability
  mechanism, and the self-contained/print-A4 requirement. `--format-out md`
  is declared in the signature but exits 4 (not yet implemented) — scope
  reduced to `html` only for this phase; flagging that as a deliberate cut,
  not an oversight. See the `report` section.
- v0.1.9 (2026-07-03): `fit` additionally writes `triangle.json` (the full
  origin × dev grid, actual + projected, cumulative, full precision) and
  now always persists `validation.json` too, not just on failure — needed
  so the renderer can highlight warn-class cells against the actual grid,
  since a warn (unlike a fail) doesn't block a fit and its details would
  otherwise never reach disk. `reserve report` gains three CSS-only visuals
  (development-triangle grid with actual/projected shading and warn-cell
  footnotes, per-origin IBNR bars with ±1 SE whiskers, a sensitivity
  min–base–max strip), `tabular-nums` on every numeric column, and
  print-color-adjust so the new shading survives PDF export. See the `fit`
  and `report` sections.
- v0.1.10 (2026-07-03): closes a silent-fabrication path — the adapter's
  `load_triangle` has always hardcoded cumulative handling regardless of
  what `validate` actually infers. `capabilities()` now declares `"basis":
  ["cumulative"]`; `fit` checks the inferred basis against it and refuses
  with exit 2 and a structured `unsupported_basis` error on mismatch,
  rather than silently fitting incremental data as if it were cumulative.
  `examples/triangle_incremental.csv` added as the reference fixture
  (`scripts/make_flawed_triangles.py`), its "genuinely incremental" ground
  truth asserted via the harness's own basis inference, not just by
  construction. See the `fit` section.
- v0.1.11 (2026-07-03): roadmap surfacing only — no new functionality.
  `capabilities()` gains a `"roadmap"` map (`bf`, `capecod`, `bootstrap`,
  `selections`, `ifrs17_bridge`), each "declared, not governed" at the time;
  `selections` additionally notes "judgment inputs require governance schema". `fit`
  recognizes (and refuses, exit 4) a `--selections` flag, quoting that
  roadmap status rather than a generic argparse error. See the `fit` and
  `Roadmap` sections for the governance surface named per destination.
- v0.1.12 (2026-07-03): audit replay hardened — runs are self-contained;
  found by independent review. `fit` now copies the input triangle CSV into
  `runs/<run-id>/inputs/` and records it on the manifest (`inputs[].snapshot`);
  `diagnostics`/`sensitivity` replay exclusively from that snapshot, verifying
  its sha256 against the manifest before any recompute and exiting 1 with a
  structured `input_integrity_violation` error on mismatch, instead of
  silently re-reading a path that may since have moved, changed, or been
  deleted. Pre-v0.1.12 run folders (no `snapshot` key) fall back to the
  originally recorded path under the same sha256 check. See the `fit` and
  `diagnostics` sections.
  - Contract alignment, same review pass: `--dry-run` extended to
    `diagnostics`, `sensitivity`, and `report`, closing a gap against the
    Global section's own rule ("`--dry-run` on any writing command") — an
    earlier phase had wired it into `fit` only. Each computes and prints its
    normal output under `--dry-run`; only the write (and, where applicable,
    the manifest update) is skipped. See each command's own section.
  - `report`'s `--format-out` (in place since v0.1.8/Phase 5) is confirmed as
    the correct flag name, not a deviation to fix: this file's `report`
    section text is corrected to make that explicit, since it had never
    stated the rationale for departing from every other command's `--format`.
    `--format` means output *encoding* (`json|text`) everywhere it appears;
    `report` selects a document *format* (`html|md`), a different axis —
    collapsing both onto one flag would silently overload its meaning by
    command. No behavior changes here, only this file's own text. See the
    `report` section.
- v0.1.14 (2026-07-06): two audit-trail gaps found by independent review,
  ahead of making this repository public:
  - The manifest `command` string (`_invocation_string`, `harness/cli.py`)
    recorded only `triangle_csv`/`run_id`/`--method`/`--basis`/`--format`/
    `--out`/`--dry-run` — a non-default `fit` (custom `--averaging`,
    `--tail`, `--n-periods`, `--exclude-origins`/`--exclude-valuations`,
    `--sigma-interpolation`) recorded a command string indistinguishable
    from an all-defaults one. The *effective* parameters were never actually
    at risk — they live in `fit.json`/manifest `parameters`, independent of
    this string — but the human/agent-facing narration of "what was run"
    was incomplete. `command` now includes every flag the given subcommand
    accepts. See the `fit` and `sensitivity` sections' signatures.
  - `sensitivity`'s own manifest update overwrote the run's `exit_code`
    with its own (always 0), silently erasing a genuine `diagnostics`
    warning (`exit_code: 3`) from the shared manifest — see the new note
    under the `sensitivity` section, and `docs/QUESTIONS.md` Q1 (revisited).
  - `sensitivity.json` gains `base_parameters` — the baseline every scenario
    in the file perturbs from, including this call's own
    `--exclude-origins`/`--exclude-valuations`, which were not otherwise
    reconstructable from the file. See the `sensitivity` section.
- v0.1.13 (2026-07-03): Q3 revisited on independent-review evidence:
  inference retained as default, explicit declaration added as authoritative.
  `validate`/`fit` gain `--basis cumulative|incremental`. Absent, behaviour is
  unchanged from before this entry — inference alone, exactly as v0.1.1 left
  it. Given, it is authoritative: a conflict with the adapter's declared
  basis is still an exit-2 `unsupported_basis` refusal (v0.1.10), now with
  `"basis_source": "declared"` in the payload and accurate wording; a
  conflict with what the inference heuristic independently concludes is a
  new `basis_consistent` fail mode, "declared-vs-inferred conflict" — the
  declaration doesn't silently win, or lose, against the data's apparent
  shape, it surfaces the disagreement. The basis actually used, and how it
  was determined, is recorded on `validation.json` (`basis_source`) and on
  the manifest (`parameters.basis: {value, source}`) either way. Motivated by
  independent review: the inference heuristic can be fooled by a smoothly,
  monotonically increasing incremental series, which votes "cumulative" the
  same way genuinely cumulative data does — declaration is the escape hatch
  for exactly that case. `data-validation` skill updated with this caveat and
  the recommendation to declare whenever incremental data is plausible. See
  the `validate` and `fit` sections.

## Explore Workflow CLI Parity

Dashboard-v2 now separates **EXPLORE** and **GOVERNED** workflows:

- EXPLORE writes `runs/<run-id>/explore/...` artifacts for flexible,
  non-governed scenario testing.
- GOVERNED keeps the existing immutable `selection_sets/` and `decisions/`
  path for report-gated judgment.
- Explore scenarios are not decisions, do not satisfy report readiness, and
  are ignored by `report --require-approval`.

The dashboard/API surface is implemented first. CLI commands such as
`reserve explore list`, `reserve explore show`, `reserve explore preview`,
and `reserve explore promote` are intentionally deferred and must not be
documented as available commands until implemented. The intended product
rule is: "Explore freely. Promote deliberately. Only governed selections
enter the report pack."
