"""Scenario preview artifacts for the workbench.

Scenario previews are descriptive projections of already-written run
artifacts. They do not invoke an engine or recompute reserves; governed
selection happens later through immutable decisions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness import manifest

from . import io, schemas


class ScenarioValidationError(ValueError):
    """Raised when a requested scenario artifact cannot be derived."""


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def _available_artifacts(run_dir: Path, names: list[str]) -> list[str]:
    return [name for name in names if (Path(run_dir) / name).is_file()]


def _metric_subset(totals: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {name: totals[name] for name in names if name in totals}


def _base_entry(run_id: str, run_dir: Path, created_utc: str) -> dict[str, Any] | None:
    fit = io.maybe_read_json(run_dir, "fit.json")
    run_manifest = io.maybe_read_json(run_dir, "manifest.json")
    if not fit:
        return None

    source_artifacts = _available_artifacts(run_dir, ["validation.json", "fit.json", "triangle.json"])
    output_artifacts = _available_artifacts(
        run_dir,
        [
            "validation.json",
            "fit.json",
            "triangle.json",
            "diagnostics.json",
            "sensitivity.json",
            "report.html",
        ],
    )
    return {
        "scenario_id": "base",
        "basis_run_id": run_id,
        "scenario_run_id": run_id,
        "artifact_path": "fit.json",
        "scenario_type": "base",
        "parameters": fit.get("parameters", {}),
        "command": run_manifest.get("command") if run_manifest else None,
        "created_utc": created_utc,
        "source_artifacts": source_artifacts,
        "output_artifacts": output_artifacts,
        "key_metrics": _metric_subset(
            fit.get("totals", {}), ("latest", "ultimate", "ibnr", "mack_se")
        ),
        "input_hashes": io.artifact_hashes(run_dir, source_artifacts),
        "status": "available",
    }


def _scenario_type_from_delta(delta: dict[str, Any]) -> str:
    parameter = delta.get("parameter")
    if parameter in {"excluded_origins", "excluded_valuations"}:
        return "exclusion"
    return "sensitivity"


def _parameters_for_sensitivity_row(base_parameters: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    parameters = dict(base_parameters)
    delta = row.get("delta_from_base") or {}
    parameter = delta.get("parameter")
    value = delta.get("value")
    if parameter in {"excluded_origins", "excluded_valuations"}:
        values = list(parameters.get(parameter) or [])
        if value not in values:
            values.append(value)
        parameters[parameter] = values
    elif parameter:
        parameters[parameter] = value
    return parameters


def _sensitivity_entries(run_id: str, run_dir: Path, created_utc: str) -> list[dict[str, Any]]:
    sensitivity = io.maybe_read_json(run_dir, "sensitivity.json")
    fit = io.maybe_read_json(run_dir, "fit.json") or {}
    if not sensitivity:
        return []

    fit_parameters = dict(fit.get("parameters") or {})
    base_parameters = dict(sensitivity.get("base_parameters") or fit_parameters)
    command = _sensitivity_command(run_id, fit_parameters, base_parameters)
    source_artifacts = _available_artifacts(run_dir, ["fit.json", "sensitivity.json"])
    entries = []
    for i, row in enumerate(sensitivity.get("scenarios", [])):
        delta = row.get("delta_from_base") or {}
        entries.append(
            {
                "scenario_id": row["scenario_id"],
                "basis_run_id": run_id,
                "scenario_run_id": None,
                "artifact_path": f"sensitivity.json#/scenarios/{i}",
                "scenario_type": _scenario_type_from_delta(delta),
                "parameters": _parameters_for_sensitivity_row(base_parameters, row),
                "command": command,
                "created_utc": created_utc,
                "source_artifacts": source_artifacts,
                "output_artifacts": ["sensitivity.json"],
                "key_metrics": _metric_subset(
                    row.get("totals", {}), ("latest", "ultimate", "ibnr", "mack_se")
                ),
                "input_hashes": io.artifact_hashes(run_dir, source_artifacts),
                "status": "available" if row.get("totals") else "incomplete",
            }
        )
    return entries


def _sensitivity_command(run_id: str, fit_parameters: dict[str, Any], base_parameters: dict[str, Any]) -> str:
    parts = [f"reserve sensitivity {run_id}", "--grid default"]
    for parameter, flag in (
        ("excluded_origins", "--exclude-origins"),
        ("excluded_valuations", "--exclude-valuations"),
    ):
        fit_values = list(fit_parameters.get(parameter) or [])
        base_values = list(base_parameters.get(parameter) or [])
        extra_values = [value for value in base_values if value not in fit_values]
        if extra_values:
            parts.append(f"{flag} {','.join(str(value) for value in extra_values)}")
    return " ".join(parts)


def build_scenario_index(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    created_utc = io.run_created_utc(run_id, run_dir)
    scenarios: list[dict[str, Any]] = []
    base = _base_entry(run_id, run_dir, created_utc)
    if base:
        scenarios.append(base)
    scenarios.extend(_sensitivity_entries(run_id, run_dir, created_utc))
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "status": "available" if scenarios else "incomplete",
        "generated_from": _available_artifacts(run_dir, ["fit.json", "sensitivity.json"]),
        "scenarios": scenarios,
    }


def write_scenario_index(run_id: str, run_dir: Path) -> dict[str, Any]:
    payload = build_scenario_index(run_id, run_dir)
    io.write_json(Path(run_dir) / schemas.SCENARIO_INDEX_FILENAME, payload)
    return payload


def load_scenario_index(run_dir: Path) -> dict[str, Any] | None:
    return io.maybe_read_json(run_dir, schemas.SCENARIO_INDEX_FILENAME)


def scenario_by_id(index: dict[str, Any], scenario_id: str) -> dict[str, Any] | None:
    for scenario in index.get("scenarios", []):
        if scenario.get("scenario_id") == scenario_id:
            return scenario
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def build_comparison(run_id: str, run_dir: Path, scenario_id: str) -> dict[str, Any]:
    run_dir = Path(run_dir)
    index = load_scenario_index(run_dir) or build_scenario_index(run_id, run_dir)
    base = scenario_by_id(index, "base")
    candidate = scenario_by_id(index, scenario_id)
    if base is None:
        raise ScenarioValidationError("run has no base scenario; fit.json is required")
    if candidate is None:
        raise ScenarioValidationError(f"scenario_id not found for this run: {scenario_id}")

    metric_names = [
        name
        for name in ("latest", "ultimate", "ibnr", "mack_se")
        if name in base.get("key_metrics", {}) or name in candidate.get("key_metrics", {})
    ]
    compared_metrics = {}
    deltas = {}
    for name in metric_names:
        base_value = base.get("key_metrics", {}).get(name)
        candidate_value = candidate.get("key_metrics", {}).get(name)
        compared_metrics[name] = {"base": base_value, "candidate": candidate_value}
        deltas[name] = (
            candidate_value - base_value
            if _is_number(base_value) and _is_number(candidate_value)
            else None
        )

    source_artifacts = []
    comparison_sources = [
        schemas.SCENARIO_INDEX_FILENAME,
        *base.get("source_artifacts", []),
        *candidate.get("source_artifacts", []),
    ]
    for name in comparison_sources:
        if name not in source_artifacts and (run_dir / name).is_file():
            source_artifacts.append(name)
    input_hashes = io.artifact_hashes(run_dir, source_artifacts)
    comparison_id = _stable_id(
        "comparison",
        {
            "run_id": run_id,
            "candidate_scenario_id": scenario_id,
            "input_hashes": input_hashes,
        },
    )
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "base_run_id": run_id,
        "candidate_scenario_id": scenario_id,
        "compared_metrics": compared_metrics,
        "deltas": deltas,
        "source_artifacts": source_artifacts,
        "input_hashes": input_hashes,
        "generated_utc": manifest.utc_now_iso(),
    }


def comparison_path(run_dir: Path, comparison_id: str) -> Path:
    return Path(run_dir) / schemas.COMPARISONS_DIRNAME / f"{comparison_id}.json"


def write_comparison(run_id: str, run_dir: Path, scenario_id: str) -> dict[str, Any]:
    payload = build_comparison(run_id, run_dir, scenario_id)
    path = comparison_path(run_dir, payload["comparison_id"])
    if path.is_file():
        return io.read_json(path)
    io.write_json(path, payload)
    return payload
