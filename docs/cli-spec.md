# `reserve` CLI — command specification (v0.1.7, FROZEN)

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
| 1 | Internal error (traceback logged to stderr) |
| 2 | Data validation failure — structured errors in output |
| 3 | Success with model warnings — one or more assumption flags ≠ pass |
| 4 | Usage error (bad arguments, unknown method, missing file) |

## Commands

### `reserve validate <triangle.csv> [--format] [--out]`

Structural checks, engine-agnostic. Checks (each with a stable `check_id`):
`file_readable`, `shape_triangular`, `no_gaps`, `monotone_cumulative` (warn
only, v0.1.2), `basis_consistent`, `origin_dev_parseable`,
`nonneg_incrementals` (warn only).

`basis_consistent` (v0.1.1): there is no `--basis` flag in v0.1 — basis is
always *inferred* (monotone non-decreasing per origin ⇒ cumulative, else
incremental). The check verifies the inference is not internally
contradictory (e.g. no mix of origins that no single basis explains), not
declared-vs-inferred agreement. A `--basis` override flag is left as a
forward-compatible hook, not a v0.1 requirement.

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
  "dimensions": {"origins": 10, "devs": 10},
  "checks": [
    {"check_id": "no_gaps", "verdict": "pass", "details": null},
    {"check_id": "monotone_cumulative", "verdict": "warn",
     "details": {"origin": "1984", "dev": 4, "values": [1234.0, 1201.5]}}
  ],
  "verdict": "warn"
}
```
Exit: 0 all pass or warn-only (verdicts stay visible) · 2 any fail
(`no_gaps`, `origin_dev_parseable`, or `basis_consistent`).

### `reserve fit <triangle.csv> --method mack [--averaging volume|simple] [--tail none|constant:<f>] [--n-periods N] [--exclude-origins LIST] [--exclude-valuations LIST] [--sigma-interpolation mack|log-linear] [--format] [--out] [--dry-run]`

Runs validate first (hard rule); refuses with exit 2 if validation fails.
Dispatches to the engine adapter. `--method` values outside adapter
`capabilities()` ⇒ exit 4.

`fit` mints its `run_id`/folder before validating. If the internal
validate-first check fails, it still persists `validation.json` (same shape
as the standalone `validate` command's output) and `manifest.json`
(`exit_code: 2`, `outputs: ["validation.json"]`) into that folder — no
`fit.json` is written. A failed `fit` call is auditable the same way a
failed standalone `validate` call is (v0.1.1).

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
All floats at full precision; rounding is a rendering concern. Exit: 0, or 3 if
the engine emits fit-time warnings.

### `reserve diagnostics <run-id> [--format] [--out]`

`--out` (v0.1.3): the runs root to locate `<run-id>` under (default
`./runs`) — needed because `diagnostics` amends an existing `fit` run's
folder in place (docs/QUESTIONS.md Q1) rather than minting its own, so it
must be told where that folder lives if `fit` used a non-default `--out`.
`sensitivity` already had this flag in v0.1; its absence here was an
inconsistency between two commands sharing the same run-folder model, not
a deliberate distinction.

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

### `reserve sensitivity <run-id> [--grid default|FILE] [--exclude-origins …] [--exclude-valuations …] [--format] [--out]`

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

### `reserve report <run-id> [--format-out html|md] [--out]`

Deterministic renderer over the run folder's JSON. **Reads only `runs/<run-id>/`;
takes no numeric arguments** — there is no way to inject a figure through this
command. Emits `report.html` with governance footer: run_id, input sha256,
engine + version, harness version, timestamp. Exit 0 · 4 if run folder
incomplete.

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
