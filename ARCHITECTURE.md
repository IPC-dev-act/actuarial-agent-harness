# Architecture

## Directory layout

```
actuarial-agent-harness/
├── README.md
├── CLAUDE.md                     # agent constitution (repo root — auto-loaded)
├── VALIDATION.md                 # manual check vs Mack (1993, 1994) & Taylor–Ashe
├── LICENSE
├── pyproject.toml                # pinned deps; entry point: reserve
├── demo.sh                       # Layer 2 headless demo (flawed triangle)
│
├── .claude/
│   ├── skills/
│   │   ├── data-validation/SKILL.md
│   │   ├── mack-diagnostics/SKILL.md
│   │   ├── sensitivity-analysis/SKILL.md
│   │   ├── reserving-report/SKILL.md
│   │   ├── reserving-triangle-triage/SKILL.md
│   │   ├── reserving-factor-review/SKILL.md
│   │   ├── reserving-scenario-compare/SKILL.md
│   │   └── reserving-selection-challenge/SKILL.md
│   └── commands/
│       ├── review.md             # /review <triangle.csv>
│       ├── diagnose.md           # /diagnose <run-id>
│       ├── challenge.md          # /challenge <run-id>
│       ├── report.md             # /report <run-id>
│       ├── triangle-triage.md    # /triangle-triage <run-id>
│       ├── factor-review.md      # /factor-review <run-id>
│       └── scenario-explain.md   # /scenario-explain <run-id>
│
├── harness/                      # the product: everything model-agnostic
│   ├── cli.py                    # `reserve` — parsing, exit codes, dispatch
│   ├── manifest.py               # run manifests: hashes, versions, timestamps
│   ├── validation.py             # triangle structure checks (engine-agnostic)
│   ├── runs.py                   # run folder lifecycle
│   ├── workbench/                # human-validation task/decision artifacts
│   └── render/
│       ├── report_html.py        # deterministic renderer (Phase 5, agent-built)
│       └── templates/
│
├── engine/                       # the commodity: swappable
│   ├── base.py                   # EngineAdapter ABC — THE contract
│   └── chainladder_adapter.py    # reference implementation
│
├── corpus/                       # optional; empty scaffold in the public repo
│   └── README.md                 # explains the three-tier corpus concept
│
├── examples/
│   ├── raa.csv                   # exported from cl.load_sample('raa')
│   ├── genins.csv
│   ├── triangle_calendar_effect.csv   # generated — see scripts/
│   ├── triangle_gapped.csv
│   └── triangle_nonmonotone.csv
│
├── scripts/
│   ├── export_samples.py         # writes examples/ from chainladder samples
│   └── make_flawed_triangles.py  # seeded pathology injection + ground truth
│
├── runs/                         # gitignored except runs/README.md
│   └── README.md
│
├── docs/
│   ├── cli-spec.md               # frozen contract (this phase)
│   ├── workbench-dashboard.md    # local dashboard MVP startup/workflow
│   └── red-team.md               # adversarial prompts + refusals (Phase 6)
│
├── dashboard/
│   └── static/                   # local workbench HTML/CSS/JS
│
└── tests/
    ├── test_validation.py
    ├── test_mack_vs_literature.py   # asserts RAA vs Mack (1994) & GenIns vs Mack (1993)
    ├── test_flawed_triangles.py     # each injected flaw fires its expected flag
    └── test_manifest.py
```

Design rule: **nothing in `harness/` imports chainladder.** All model access goes
through `engine/base.py`. That line is what makes "swap the engine" a fact rather
than a slogan — and it is checkable in CI with a one-line import-linter rule.

## Engine adapter contract

A company adopts the harness by implementing one class:

```python
class EngineAdapter(ABC):

    @abstractmethod
    def load_triangle(self, path: Path) -> TriangleHandle:
        """Parse input into the engine's native triangle. Raise
        TriangleFormatError with structured details on failure."""

    @abstractmethod
    def fit(self, tri: TriangleHandle, method: str,
            params: dict) -> FitResult:
        """Run the method. Returns ultimates, reserves (incl. std errors
        where the method provides them), factors — as plain dicts
        conforming to docs/cli-spec.md schemas."""

    @abstractmethod
    def diagnostics(self, tri: TriangleHandle,
                    fit: FitResult) -> DiagnosticsResult:
        """Assumption tests as {test_id, statistic, threshold,
        verdict: pass|warn|fail, narrative_key}."""

    @abstractmethod
    def capabilities(self) -> dict:
        """Declared methods, diagnostics, and limits — the harness
        refuses requests outside declared capabilities."""
```

Notes:
- The harness owns validation of triangle *structure* (gaps, monotonicity,
  cumulative/incremental consistency); the adapter owns anything
  engine-specific.
- Verdicts (`pass|warn|fail`) and thresholds live in the adapter output, not in
  agent judgment. `narrative_key` maps to fixed language in the
  `mack-diagnostics` skill — the agent selects narration, never invents it.
- The reference `chainladder_adapter` implements `chain_ladder` and `mack`;
  `bf`, `capecod`, `bootstrap` are declared roadmap in `capabilities()`.
- `EngineAdapter` has no `sensitivity()` method, deliberately. A sensitivity
  grid is nothing but repeated calls to `fit()` with different parameters —
  `harness/sensitivity.py` builds the perturbation grid and re-invokes
  `fit()` once per scenario, entirely engine-agnostic. Every adapter gets
  `reserve sensitivity` for free the moment `fit()` works; there is nothing
  engine-specific to implement or swap for it.

## Manifest

Written by every command that produces output, at `runs/<run-id>/manifest.json`:

```json
{
  "run_id": "2026-07-02T14-31-08_raa_mack_a1b2c3",
  "created_utc": "2026-07-02T14:31:08Z",
  "command": "reserve fit examples/raa.csv --method mack",
  "inputs": [{"path": "examples/raa.csv", "sha256": "…", "snapshot": "inputs/raa.csv"}],
  "engine": {"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
  "environment": {"python": "3.12.1", "harness_version": "0.1.0", "locked_deps_sha256": "…"},
  "parameters": {"method": "mack", "averaging": "volume", "tail": "none",
                  "basis": {"value": "cumulative", "source": "inferred"}},
  "outputs": ["fit.json", "diagnostics.json"],
  "exit_code": 3
}
```

`run_id` is deterministic in structure (timestamp + input tag + short hash) so the
agent can cite it stably.

`inputs[].snapshot` (v0.1.12, `fit`-written runs only): the run-folder-relative
path to a copy of the input CSV made at fit time (`runs/<run-id>/inputs/`).
`diagnostics`/`sensitivity` replay exclusively from this snapshot, verifying its
sha256 against `inputs[].sha256` before any recompute — the run folder is a
self-contained audit object, independent of the original file's path, mutation,
or deletion after the fact. Run folders minted before v0.1.12 have no
`snapshot` key; replay falls back to `inputs[].path` for those, under the same
sha256 check (`docs/cli-spec.md`'s `diagnostics` section, "Audit replay").

`parameters.basis` (v0.1.13, `validate`- and `fit`-written runs): the basis
actually used, and how it was determined — `source` is `"declared"` if
`--basis cumulative|incremental` was passed, `"inferred"` otherwise. Recorded
either way, so a manifest alone (without re-reading `validation.json`) always
answers "was this basis a stated assumption or a guess?" (`docs/cli-spec.md`'s
`validate` section).

`exit_code` (revisited v0.1.14): amended in place by every command that
shares an existing run folder (`diagnostics`, `sensitivity`, `report` —
`docs/QUESTIONS.md` Q1), but not all of them overwrite it. `fit` and
`diagnostics` perform a genuine new pass/warn assessment, so their own exit
code replaces what was there. `sensitivity` and `report` don't assess
anything — they carry the manifest's current `exit_code` forward unchanged
instead of overwriting it with their own (always-0) code, so a `diagnostics`
warning stays visible in `reserve runs list` no matter how many of those
non-assessing commands run against the folder afterwards.

## Workbench artifacts

The interactive workbench adds a human-validation layer without changing
reserving calculations. The AI/CLI still
runs the controlled workflow, the engine still computes numbers, and the
workbench layer only reads/writes structured run artifacts:

- `validation_tasks.json` — a deterministic task queue derived from
  `validation.json`, `diagnostics.json`, `sensitivity.json`, and immutable
  decisions.
- `scenario_index.json` — a model-agnostic preview index of the base run and
  deterministic scenario candidates already produced by existing CLI
  artifacts, currently `fit.json` and optional `sensitivity.json`.
- `comparisons/<comparison_id>.json` — a generated comparison of one
  scenario candidate against the base run, with metric deltas and hashes of
  the artifacts used.
- `factor_previews/<scenario_id>.json` — exploratory single-factor BCL
  preview artifacts, retained for compatibility with earlier dashboard
  workflow tests.
- `selection_sets/<selection_set_id>.json` — governed deterministic chain
  ladder preview/committed selection-set artifacts containing multiple
  candidate-basis factor choices, simple exclusions, rationale, comparison,
  command trail, and input hashes.
- `decisions/<decision_id>.json` — one immutable human judgment record per
  committed decision. A later change creates a new decision and references
  `supersedes_decision_id`; no decision file is edited in place.
- `review_handoff.json` — the structured AI-to-actuary pause/resume state.
- `review_snapshots/<review_snapshot_id>.json` — the immutable reporting
  basis approved by a `report_approval` decision.

Current workbench decision types are `warning_ack`, `scenario_selection`,
`method_review_ack`, `factor_selection`, `selection_set_approval`, and
`report_approval`.

Scenario previews are exploratory. A future dashboard or AI workflow can
refresh `scenario_index.json` and write comparison artifacts, but only a
committed `scenario_selection` decision can govern which scenario should feed
later review-pack behavior. Scenario-selection decisions must reference a
valid indexed scenario and are rejected if the indexed source-artifact hashes
are stale.

Selection-set previews are exploratory until committed. A committed
selection set still is not human approval by itself; `selection_set_approval`
is the immutable decision artifact that records the actuary's approval of
that selection set for downstream disclosure. Report approval remains a
separate `report_approval` decision and is bound to the active selection,
decisions, source hashes, and renderer through a review snapshot. The lifecycle is available through both
the dashboard API and the CLI (`reserve selection-sets list/show/preview/commit`);
the CLI commit path uses the same decision validator as `reserve decide`.

Final report generation can be hard-gated with
`reserve report <run-id> --require-approval`. That path refuses to render
when prerequisite workbench tasks remain pending, when a committed selection
set has never been approved, when multiple active selection approvals exist,
or when no current `report_approval` decision exists. It rejects stale review
snapshots after any material reporting-basis change. Draft rendering without
the flag remains available, but the report
records `draft/incomplete` governance when approval is missing.

`harness/workbench/` remains model-agnostic: it imports no reserving engine
adapter, performs no actuarial calculations, and obtains every number from
existing `runs/<run-id>/` JSON artifacts.

## Local dashboard

The FastAPI/static dashboard is a local MVP. The API lives in
`harness/workbench/api.py` so it can call the same workbench functions as the
CLI. Packaged v2 static files live under `harness/workbench/static_v2/`;
`dashboard-v2/static/` preserves convenient source-tree links.

The dashboard is a human-validation surface over existing artifacts:

- status and artifact availability come from `harness.workbench.state`;
- task refresh uses `harness.workbench.tasks`;
- scenario lists and comparisons use `harness.workbench.scenarios`;
- deterministic chain ladder summary/factors/projection use
  `harness.workbench.chain_ladder`;
- selection-set previews and commits use `harness.selection_sets`;
- decision writes use `harness.workbench.decisions`;
- JSON artifact reads are restricted to safe run-folder paths.

The dashboard supports governed manual factor overrides, factor-point and
origin/valuation exclusions, and constant tails. It has no production
authentication, no chat panel, no governed log-linear smoothing, and no
frontend actuarial calculations.

## Claude operating layer

The `.claude/commands/` and `.claude/skills/` files are the AI operating
layer around the dashboard. Claude runs controlled CLI commands, reads
artifacts, prepares scenario and review context, refreshes validation tasks,
and stops where human judgment is required. The dashboard remains the human-validation layer:
factor choices, exclusions, scenario selections,
warning acknowledgements, and report approval are governed by structured
decision artifacts, not chat text.

Skill and command guardrails:

- every number cited by Claude must come from a run artifact;
- no mental arithmetic on model outputs;
- no hidden factor selection;
- no decision writes as a substitute for dashboard human validation;
- no report approval without an immutable human decision artifact;
- no final report presentation while required tasks remain pending;
- preview artifacts are exploratory;
- `decisions/*.json` is the durable source of committed judgment.
