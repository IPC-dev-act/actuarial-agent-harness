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
│   │   └── reserving-report/SKILL.md
│   └── commands/
│       ├── review.md             # /review <triangle.csv>
│       ├── diagnose.md           # /diagnose <run-id>
│       ├── challenge.md          # /challenge <run-id>
│       └── report.md             # /report <run-id>
│
├── harness/                      # the product: everything model-agnostic
│   ├── cli.py                    # `reserve` — parsing, exit codes, dispatch
│   ├── manifest.py               # run manifests: hashes, versions, timestamps
│   ├── validation.py             # triangle structure checks (engine-agnostic)
│   ├── runs.py                   # run folder lifecycle
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
│   └── red-team.md               # adversarial prompts + refusals (Phase 6)
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
- The reference `chainladder_adapter` implements `mack` at v1; `bf`, `capecod`,
  `bootstrap` are declared roadmap in `capabilities()`.
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
  "inputs": [{"path": "examples/raa.csv", "sha256": "…"}],
  "engine": {"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
  "environment": {"python": "3.12.1", "harness_version": "0.1.0", "locked_deps_sha256": "…"},
  "parameters": {"method": "mack", "averaging": "volume", "tail": "none"},
  "outputs": ["fit.json", "diagnostics.json"],
  "exit_code": 3
}
```

`run_id` is deterministic in structure (timestamp + input tag + short hash) so the
agent can cite it stably.
