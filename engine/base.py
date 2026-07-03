"""EngineAdapter contract (ARCHITECTURE.md#engine-adapter-contract).

No engine-specific imports here — this module must stay adoptable by any
company's model (Prophet, Tyche, an internal Python stack), not just
chainladder. `engine/chainladder_adapter.py` is the reference
implementation and the only module allowed to `import chainladder`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TriangleFormatError(Exception):
    """Raised by load_triangle on an engine-specific parse failure."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class UnsupportedMethodError(Exception):
    """Raised when a --method value is outside the adapter's capabilities()."""

    def __init__(self, method: str):
        super().__init__(f"method '{method}' is not supported by this adapter")
        self.method = method


@dataclass
class TriangleHandle:
    """Opaque wrapper around an engine-native triangle object. The harness
    never inspects `native` — it only round-trips this between
    `load_triangle`, `fit`, and `diagnostics`.
    """

    native: Any
    basis: str


@dataclass
class FitResult:
    method: str
    parameters: dict
    development_factors: list[dict]
    by_origin: list[dict]
    totals: dict
    units: str = "as-input"
    fit_warnings: list[dict] = field(default_factory=list)
    # Opaque engine-native fitted objects (e.g. the fitted Development/Mack
    # estimators), for the SAME adapter's own diagnostics() to reuse. Never
    # serialized — absent from to_fit_json().
    native: Any = None

    def to_fit_json(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "method": self.method,
            "parameters": self.parameters,
            "development_factors": self.development_factors,
            "by_origin": self.by_origin,
            "totals": self.totals,
            "units": self.units,
        }


@dataclass
class DiagnosticsResult:
    tests: list[dict]

    @property
    def overall(self) -> str:
        # pass|warn only (docs/cli-spec.md v0.1.4) — fail is exclusive to
        # validate's structural checks, never a diagnostics verdict.
        verdicts = {t["verdict"] for t in self.tests}
        return "warn" if "warn" in verdicts else "pass"

    def to_diagnostics_json(self, run_id: str) -> dict:
        return {"run_id": run_id, "tests": self.tests, "overall": self.overall}


class EngineAdapter(ABC):
    @abstractmethod
    def load_triangle(self, path: Path) -> TriangleHandle:
        """Parse input into the engine's native triangle. Raise
        TriangleFormatError with structured details on failure."""

    @abstractmethod
    def fit(self, tri: TriangleHandle, method: str, params: dict) -> FitResult:
        """Run the method. Returns ultimates, reserves (incl. std errors
        where the method provides them), factors — as plain dicts
        conforming to docs/cli-spec.md schemas."""

    @abstractmethod
    def diagnostics(self, tri: TriangleHandle, fit: FitResult) -> DiagnosticsResult:
        """Assumption tests as {test_id, statistic, threshold,
        verdict: pass|warn|fail, narrative_key}."""

    @abstractmethod
    def capabilities(self) -> dict:
        """Declared methods, diagnostics, and limits — the harness
        refuses requests outside declared capabilities."""
