# `reserve` CLI — command specification (v0.1.1, FROZEN)

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
`file_readable`, `shape_triangular`, `no_gaps`, `monotone_cumulative`,
`basis_consistent`, `origin_dev_parseable`, `nonneg_incrementals` (warn only).

`basis_consistent` (v0.1.1): there is no `--basis` flag in v0.1 — basis is
always *inferred* (monotone non-decreasing per origin ⇒ cumulative, else
incremental). The check verifies the inference is not internally
contradictory (e.g. no mix of origins that no single basis explains), not
declared-vs-inferred agreement. A `--basis` override flag is left as a
forward-compatible hook, not a v0.1 requirement.

Output `validation.json`:
```json
{
  "input": {"path": "…", "sha256": "…"},
  "basis": "cumulative",
  "dimensions": {"origins": 10, "devs": 10},
  "checks": [
    {"check_id": "no_gaps", "verdict": "pass", "details": null},
    {"check_id": "monotone_cumulative", "verdict": "fail",
     "details": {"origin": "1984", "dev": 4, "values": [1234.0, 1201.5]}}
  ],
  "verdict": "fail"
}
```
Exit: 0 all pass · 2 any fail · (warn-only ⇒ 0 with verdicts visible).

### `reserve fit <triangle.csv> --method mack [--averaging volume|simple] [--tail none|constant:<f>] [--n-periods N] [--exclude-origins LIST] [--exclude-valuations LIST] [--format] [--out] [--dry-run]`

Runs validate first (hard rule); refuses with exit 2 if validation fails.
Dispatches to the engine adapter. `--method` values outside adapter
`capabilities()` ⇒ exit 4.

`fit` mints its `run_id`/folder before validating. If the internal
validate-first check fails, it still persists `validation.json` (same shape
as the standalone `validate` command's output) and `manifest.json`
(`exit_code: 2`, `outputs: ["validation.json"]`) into that folder — no
`fit.json` is written. A failed `fit` call is auditable the same way a
failed standalone `validate` call is (v0.1.1).

Output `fit.json`:
```json
{
  "run_id": "…",
  "method": "mack",
  "parameters": {"averaging": "volume", "tail": "none", "n_periods": null,
                  "excluded_origins": [], "excluded_valuations": []},
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

### `reserve diagnostics <run-id> [--format]`

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
Exit: 0 all pass · 3 any warn/fail. `narrative_key` maps to fixed prose in the
`mack-diagnostics` skill; `prescribed_actions` is the agent's menu — it proposes
from this list, nothing else.

### `reserve sensitivity <run-id> [--grid default|FILE] [--exclude-origins …] [--exclude-valuations …] [--format] [--out]`

Re-runs the fit over a perturbation grid. `--grid default` =
{drop oldest origin; drop latest diagonal; simple vs volume averaging;
n-periods ∈ {3, 5, all}; constant tail 1.00/1.02/1.05}. Custom grids as JSON file.

Output `sensitivity.json`: array of scenario rows —
`{"scenario_id", "delta_from_base": {"parameter": "…", "value": "…"},
"totals": {"ultimate", "ibnr", "mack_se"}}` — plus
`"range": {"ibnr_min", "ibnr_max", "base_ibnr"}`.
Exit 0. No verdicts: sensitivity output is descriptive; interpretation language
lives in the `sensitivity-analysis` skill.

### `reserve report <run-id> [--format-out html|md] [--out]`

Deterministic renderer over the run folder's JSON. **Reads only `runs/<run-id>/`;
takes no numeric arguments** — there is no way to inject a figure through this
command. Emits `report.html` with governance footer: run_id, input sha256,
engine + version, harness version, timestamp. Exit 0 · 4 if run folder
incomplete.

### `reserve runs [list|show <run-id>] [--format]`

Inventory of the runs root from manifests. Read-only. Exit 0.

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
