"""Shared deterministic engine execution boundary for CLI and governed previews."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.base import FitResult, TriangleHandle
from engine.chainladder_adapter import ChainladderAdapter
from engine.chainladder_adapter import parse_tail_param
from harness import manifest


def fit_triangle(
    triangle_csv: Path,
    method: str,
    parameters: dict[str, Any],
    *,
    adapter: ChainladderAdapter | None = None,
) -> tuple[TriangleHandle, FitResult]:
    """Load and fit through the same adapter boundary used by ``reserve fit``."""
    active_adapter = adapter or ChainladderAdapter()
    triangle = active_adapter.load_triangle(Path(triangle_csv))
    return triangle, active_adapter.fit(triangle, method, parameters)


def replay_input(run_dir: Path, run_manifest: dict[str, Any]) -> Path:
    """Resolve and integrity-check the immutable run input snapshot."""
    input_entry = run_manifest["inputs"][0]
    expected_sha256 = input_entry["sha256"]
    snapshot_rel = input_entry.get("snapshot")
    path = (Path(run_dir) / snapshot_rel) if snapshot_rel else Path(input_entry["path"])
    if not path.is_file():
        raise ValueError(f"input file for deterministic replay not found: {path}")
    if manifest.sha256_file(path) != expected_sha256:
        raise ValueError("input file for deterministic replay does not match manifest sha256")
    return path


def parameters_from_fit(fit: dict[str, Any]) -> dict[str, Any]:
    """Convert persisted fit parameters back to the adapter contract."""
    parameters = fit.get("parameters") or {}
    return {
        "averaging": parameters.get("averaging", "volume"),
        "tail": parse_tail_param(parameters.get("tail", "none")),
        "n_periods": parameters.get("n_periods"),
        "excluded_origins": list(parameters.get("excluded_origins") or []),
        "excluded_valuations": list(parameters.get("excluded_valuations") or []),
        "excluded_factor_points": list(parameters.get("excluded_factor_points") or []),
        "sigma_interpolation": parameters.get("sigma_interpolation", "mack"),
        "selected_factors": list(parameters.get("selected_factors") or []),
    }
