"""Governed deterministic factor-selection previews.

The dashboard uses this module to request a preview scenario. The browser
supplies a candidate basis/value, but the preview is produced by rerunning the
reference engine path and writing an auditable artifact under the base run.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import manifest, model_runner
from harness.workbench import chain_ladder, io, schemas


class FactorPreviewError(ValueError):
    """Raised when a factor-selection preview request cannot be governed."""


_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactorPreviewError(message)


def preview_path(run_dir: Path, scenario_id: str) -> Path:
    if not _ARTIFACT_ID_RE.fullmatch(str(scenario_id)):
        raise FactorPreviewError(f"invalid factor preview scenario_id: {scenario_id}")
    return Path(run_dir) / schemas.FACTOR_PREVIEWS_DIRNAME / f"{scenario_id}.json"


def load_preview(run_dir: Path, scenario_id: str) -> dict[str, Any] | None:
    path = preview_path(run_dir, scenario_id)
    return io.read_json(path) if path.is_file() else None


def _resolve_replay_input(run_dir: Path, run_manifest: dict[str, Any]) -> Path:
    input_entry = run_manifest["inputs"][0]
    expected_sha256 = input_entry["sha256"]
    snapshot_rel = input_entry.get("snapshot")
    path = (Path(run_dir) / snapshot_rel) if snapshot_rel else Path(input_entry["path"])
    _require(path.is_file(), f"input file for preview replay not found: {path}")
    actual_sha256 = manifest.sha256_file(path)
    _require(
        actual_sha256 == expected_sha256,
        "input file for preview replay does not match manifest sha256",
    )
    return path


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _approx_equal(left: Any, right: Any) -> bool:
    if not _is_number(left) or not _is_number(right):
        return False
    return abs(float(left) - float(right)) <= max(1e-10, abs(float(right)) * 1e-10)


def _chart_percent(value: Any, maximum: float | None) -> float | None:
    if not _is_number(value) or not maximum:
        return None
    return max(0.0, min(100.0, abs(float(value)) / maximum * 100.0))


def _factor_by_development_age(factors: list[dict[str, Any]], development_age: str) -> dict[str, Any] | None:
    for factor in factors:
        if str(factor.get("development_age")) == str(development_age):
            return factor
        if "from_dev" in factor and "to_dev" in factor:
            label = f"{factor['from_dev']} -> {factor['to_dev']}"
            if label == str(development_age):
                return factor
    return None


def _candidate_value(factor: dict[str, Any], selected_basis: str) -> float | None:
    if selected_basis == "fitted":
        value = factor.get("fitted_factor", factor.get("selected_factor"))
    else:
        value = (factor.get("candidate_averages") or {}).get(selected_basis)
    return float(value) if _is_number(value) else None


def _params_from_fit(fit: dict[str, Any], selected_factor: dict[str, Any]) -> dict[str, Any]:
    parameters = fit.get("parameters") or {}
    return {
        "averaging": parameters.get("averaging", "volume"),
        "tail": _parse_tail(parameters.get("tail", "none")),
        "n_periods": parameters.get("n_periods"),
        "excluded_origins": parameters.get("excluded_origins", []),
        "excluded_valuations": parameters.get("excluded_valuations", []),
        "sigma_interpolation": parameters.get("sigma_interpolation", "mack"),
        "selected_factors": [selected_factor],
    }


def _parse_tail(raw: str) -> dict[str, Any]:
    if raw == "none":
        return {"type": "none"}
    if isinstance(raw, str) and raw.startswith("constant:"):
        return {"type": "constant", "factor": float(raw.partition(":")[2])}
    raise FactorPreviewError(f"unsupported tail parameter in fit.json: {raw!r}")


def _by_origin_impacts(base_fit: dict[str, Any], candidate_fit: dict[str, Any]) -> list[dict[str, Any]]:
    base_by_origin = {str(row["origin"]): row for row in base_fit.get("by_origin", [])}
    base_maximum = max(
        [abs(float(row.get("ibnr"))) for row in base_fit.get("by_origin", []) if _is_number(row.get("ibnr"))],
        default=None,
    )
    candidate_maximum = max(
        [abs(float(row.get("ibnr"))) for row in candidate_fit.get("by_origin", []) if _is_number(row.get("ibnr"))],
        default=None,
    )
    impacts = []
    for candidate in candidate_fit.get("by_origin", []):
        origin = str(candidate["origin"])
        base = base_by_origin.get(origin, {})
        base_ibnr = base.get("ibnr")
        candidate_ibnr = candidate.get("ibnr")
        impacts.append(
            {
                "origin": origin,
                "base_ibnr": base_ibnr,
                "candidate_ibnr": candidate_ibnr,
                "base_ibnr_chart_pct": _chart_percent(base_ibnr, base_maximum),
                "candidate_ibnr_chart_pct": _chart_percent(candidate_ibnr, candidate_maximum),
                "delta_ibnr": (
                    float(candidate_ibnr) - float(base_ibnr)
                    if _is_number(base_ibnr) and _is_number(candidate_ibnr)
                    else None
                ),
                "delta_ibnr_pct": (
                    (float(candidate_ibnr) - float(base_ibnr)) / abs(float(base_ibnr)) * 100.0
                    if _is_number(base_ibnr) and _is_number(candidate_ibnr) and float(base_ibnr) != 0
                    else None
                ),
            }
        )
    return impacts


def build_factor_preview(run_id: str, run_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    run_manifest = io.maybe_read_json(run_dir, "manifest.json")
    _require(fit is not None, "factor preview requires fit.json")
    _require(run_manifest is not None, "factor preview requires manifest.json")
    _require(
        chain_ladder.is_chain_ladder_method(fit.get("method")),
        "factor preview is currently supported only for deterministic chain ladder runs",
    )

    development_age = str(request.get("development_age") or "").strip()
    selected_basis = str(request.get("selected_basis") or "").strip()
    selected_factor_value = request.get("selected_factor_value")
    _require(development_age, "development_age is required")
    _require(selected_basis in {"fitted", "volume_weighted", "simple_average", "last_3", "last_5"}, "unsupported selected_basis")
    _require(_is_number(selected_factor_value), "selected_factor_value must be numeric")

    factors_payload = chain_ladder.build_factors(run_id, run_dir)
    factor = _factor_by_development_age(factors_payload.get("factors", []), development_age)
    _require(factor is not None, f"development_age is not available in fit.json: {development_age}")
    expected_value = _candidate_value(factor, selected_basis)
    _require(expected_value is not None, f"selected_basis is not available for {development_age}: {selected_basis}")
    _require(
        _approx_equal(float(selected_factor_value), expected_value),
        "selected_factor_value does not match the selected basis candidate",
    )

    selected_factor = {
        "from_dev": factor["from_dev"],
        "to_dev": factor["to_dev"],
        "development_age": factor["development_age"],
        "basis": selected_basis,
        "factor": float(expected_value),
    }
    source_artifacts = [
        name
        for name in ("fit.json", "triangle.json")
        if (run_dir / name).is_file()
    ]
    input_hashes = io.artifact_hashes(run_dir, source_artifacts)
    scenario_id = _stable_id(
        "factor_preview",
        {
            "run_id": run_id,
            "selection": selected_factor,
            "input_hashes": input_hashes,
        },
    )
    path = preview_path(run_dir, scenario_id)
    if path.is_file():
        return io.read_json(path)

    triangle_csv = _resolve_replay_input(run_dir, run_manifest)
    _tri_handle, candidate_result = model_runner.fit_triangle(
        triangle_csv,
        "chain_ladder",
        _params_from_fit(fit, selected_factor),
    )
    candidate_fit = candidate_result.to_fit_json(run_id)

    base_totals = fit.get("totals") or {}
    candidate_totals = candidate_fit.get("totals") or {}
    comparison = {
        "base": {
            "ultimate": base_totals.get("ultimate"),
            "ibnr": base_totals.get("ibnr"),
        },
        "candidate": {
            "ultimate": candidate_totals.get("ultimate"),
            "ibnr": candidate_totals.get("ibnr"),
        },
        "deltas": {
            "ultimate": (
                float(candidate_totals["ultimate"]) - float(base_totals["ultimate"])
                if _is_number(base_totals.get("ultimate")) and _is_number(candidate_totals.get("ultimate"))
                else None
            ),
            "ibnr": (
                float(candidate_totals["ibnr"]) - float(base_totals["ibnr"])
                if _is_number(base_totals.get("ibnr")) and _is_number(candidate_totals.get("ibnr"))
                else None
            ),
            "ibnr_pct": (
                (float(candidate_totals["ibnr"]) - float(base_totals["ibnr"]))
                / abs(float(base_totals["ibnr"]))
                * 100.0
                if _is_number(base_totals.get("ibnr"))
                and _is_number(candidate_totals.get("ibnr"))
                and float(base_totals["ibnr"]) != 0.0
                else None
            ),
        },
        "by_origin_ibnr_impact": _by_origin_impacts(fit, candidate_fit),
    }
    payload = {
        "schema_version": schemas.SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "scenario_type": "selected_factors_later",
        "basis_run_id": run_id,
        "status": "available",
        "selection": {
            "development_age": factor["development_age"],
            "from_dev": factor["from_dev"],
            "to_dev": factor["to_dev"],
            "previous_factor": factor.get("selected_factor"),
            "selected_factor": float(expected_value),
            "selected_basis": selected_basis,
            "user_note": str(request.get("user_note") or "").strip() or None,
        },
        "comparison": comparison,
        "candidate_fit": candidate_fit,
        "source_artifacts": source_artifacts,
        "input_hashes": input_hashes,
        "created_utc": manifest.utc_now_iso(),
        "preview_artifact": f"{schemas.FACTOR_PREVIEWS_DIRNAME}/{scenario_id}.json",
    }
    io.write_json(path, payload)
    return payload
