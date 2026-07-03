# `reserve` CLI — command specification (v0.1.13, FROZEN)

Contract for Phase 2 implementation. Changes after freeze require a version bump
and a note in this file's changelog.

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

### `reserve fit <triangle.csv> --method mack [--averaging volume|simple] [--tail none|constant:<f>] [--n-periods N] [--exclude-origins LIST] [--exclude-valuations LIST] [--basis cumulative|incremental] [--sigma-interpolation mack|log-linear] [--format] [--out] [--dry-run]`

Runs validate first (hard rule); refuses with exit 2 if validation fails.
Dispatches to the engine adapter. `--method` values outside adapter
`capabilities()` ⇒ exit 4. `--basis` (v0.1.13) is passed straight through to
the internal `validate` call — see the `validate` section for its full
semantics (declared-vs-inferred conflict fails `basis_consistent`, and thus
`fit`, before the adapter is ever consulted).

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

`--sigma-interpolation` (v0.1.7): controls how the `mack` method
extrapolates sigma for the last development period, where Mack's recursive
formula is otherwise undefined for lack of a second data point. Default
`mack` (Mack's own minimum rule) — verified exactly against the published
RAA standard errors (VALIDATION.md). chainladder's own library default,
`log-linear`, is also available explicitly; it understates SE for origins
that depend most heavily on the extrapolated final sigma (e.g. 143 vs the
published 206 for RAA origin 1982) but is not "wrong" — both are legitimate
statistical choices, and the persisted `fit.json` always states which one
was used.

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

Runs assumption tests against an existing fit. Tests for `mack` at v0.1:

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
v0.1 text, spelled out here):
```json
{
  "run_id": "…",
  "scenarios": [
    {"scenario_id": "drop_oldest_origin",
     "delta_from_base": {"parameter": "excluded_origins", "value": "1981"},
     "totals": {"ultimate": 215888.6, "ibnr": 54901.6, "mack_se": null}}
  ],
  "range": {"ibnr_min": 47823.2, "ibnr_max": 62099.2, "base_ibnr": 52135.2}
}
```
`scenarios` excludes the base case itself (already given via `range.base_ibnr`).

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

### `reserve report <run-id> [--format-out html|md] [--out] [--dry-run]`

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

**Section structure** (v0.1.8): 0 Scope & basis of preparation, 1 Executive
summary, 2 Data & validation, 3 Method & parameters, 4 Results, 5 Diagnostics,
6 Sensitivity, 7 Limitations & reliances, 8 Governance — exactly
`.claude/skills/reserving-report/SKILL.md`'s structure. Diagnostics tests
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

**Governance footer** (unchanged from v0.1): `run_id`, input `sha256`,
`engine.package`/`engine.version`, `environment.harness_version`,
`created_utc` — read verbatim from `manifest.json`, not recomposed.

Exit 0 · 4 if the run folder is incomplete for reporting (folder doesn't
exist, or is missing `manifest.json`/`fit.json` — the two files every
section other than Diagnostics/Sensitivity depends on) · 4 for
`--format-out md` until it exists.

### `reserve runs [list|show <run-id>] [--format] [--out]`

`--out` (v0.1.6): same gap as `diagnostics` had pre-v0.1.3 — "inventory of
the runs root" needs to be told which root when it isn't the default
`./runs`. Read-only. `list` output: `{"runs": [<manifest>, ...]}`, one
entry per run under the root, sorted by run_id (chronologically, since
run_id is timestamp-prefixed). `show <run-id>` output: that run's
`manifest.json` content verbatim. Exit 0 for `list` always; `show` on an
unknown run-id is a usage error (exit 4), same as `diagnostics`/
`sensitivity` on an unknown run-id.

### Roadmap (declared, not in v0.1)

`reserve backtest` (CLRD upper-triangle fit vs realised outcomes) ·
methods `bf`, `capecod`, `bootstrap` · portfolio mode (multi-segment + roll-up).

**Governance surface per destination** (v0.1.11 — declared here, not
implemented; `capabilities()["roadmap"]` carries the same statuses so an
agent can query them without reading this file):
- **`selections`** (judgment overriding a computed factor): a declared
  selection file with a per-deviation rationale, hashed into the manifest —
  a selection is only auditable if the reason for every deviation from the
  indicated factor is itself a recorded, traceable input.
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
  `selections`, `ifrs17_bridge`), each "declared, not governed"; `selections`
  additionally notes "judgment inputs require governance schema". `fit`
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
