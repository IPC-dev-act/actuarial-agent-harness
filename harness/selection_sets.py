"""Governed deterministic chain ladder selection-set previews."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import factor_analysis, factor_selection, manifest, model_runner, triangle_projection
from harness.workbench import chain_ladder, io, schemas


class SelectionSetError(ValueError):
    """Raised when a selection-set artifact cannot be built or committed."""


_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_artifact_id(value: str, label: str) -> str:
    text = str(value)
    _require(bool(text) and bool(_ARTIFACT_ID_RE.fullmatch(text)), f"invalid {label}: {value}")
    return text


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SelectionSetError(message)


def selection_set_path(run_dir: Path, selection_set_id: str) -> Path:
    safe_id = _safe_artifact_id(selection_set_id, "selection_set_id")
    return Path(run_dir) / schemas.SELECTION_SETS_DIRNAME / f"{safe_id}.json"


def load_selection_set(run_dir: Path, selection_set_id: str) -> dict[str, Any] | None:
    path = selection_set_path(run_dir, selection_set_id)
    return io.read_json(path) if path.is_file() else None


def list_selection_sets(run_dir: Path) -> list[dict[str, Any]]:
    root = Path(run_dir) / schemas.SELECTION_SETS_DIRNAME
    if not root.is_dir():
        return []
    return [io.read_json(path) for path in sorted(root.glob("*.json"))]


def selection_set_artifact(selection_set_id: str) -> str:
    safe_id = _safe_artifact_id(selection_set_id, "selection_set_id")
    return f"{schemas.SELECTION_SETS_DIRNAME}/{safe_id}.json"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _approx_equal(left: Any, right: Any) -> bool:
    if not _is_number(left) or not _is_number(right):
        return False
    return abs(float(left) - float(right)) <= max(1e-10, abs(float(right)) * 1e-10)


def _normalise_review_metadata(run_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
    analysis = io.maybe_read_json(run_dir, schemas.FACTOR_ANALYSIS_FILENAME)
    suggestion_artifact = io.maybe_read_json(run_dir, schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME)
    requested_analysis_id = str(request.get("factor_analysis_id") or "").strip() or None
    if requested_analysis_id:
        _require(analysis is not None, "factor_analysis_id requires factor_analysis.json")
        _require(
            requested_analysis_id == analysis.get("analysis_id"),
            "factor_analysis_id does not match factor_analysis.json",
        )

    valid_ids = {
        str(item.get("suggestion_id"))
        for item in (suggestion_artifact or {}).get("suggestions", [])
        if item.get("suggestion_id")
    }
    reviewed_ids = sorted({str(value) for value in request.get("reviewed_suggestion_ids", []) if value})
    raw_dispositions = request.get("suggestion_dispositions") or []
    _require(isinstance(raw_dispositions, list), "suggestion_dispositions must be a list")
    dispositions = []
    seen: set[str] = set()
    for raw in raw_dispositions:
        _require(isinstance(raw, dict), "suggestion_dispositions entries must be objects")
        suggestion_id = str(raw.get("suggestion_id") or "").strip()
        status = str(raw.get("status") or "").strip()
        _require(suggestion_id in valid_ids, f"unknown factor review suggestion_id: {suggestion_id}")
        _require(status in {"reviewed", "dismissed"}, f"unsupported suggestion disposition: {status}")
        _require(suggestion_id not in seen, f"duplicate suggestion disposition: {suggestion_id}")
        seen.add(suggestion_id)
        dispositions.append(
            {
                "suggestion_id": suggestion_id,
                "status": status,
                "rationale": str(raw.get("rationale") or "").strip() or None,
            }
        )
    for suggestion_id in reviewed_ids:
        _require(suggestion_id in valid_ids, f"unknown reviewed suggestion_id: {suggestion_id}")
    return {
        "factor_analysis_id": (analysis or {}).get("analysis_id"),
        "reviewed_suggestion_ids": reviewed_ids,
        "suggestion_dispositions": dispositions,
    }


def _candidate_value(factor: dict[str, Any], selected_basis: str) -> float | None:
    if selected_basis == "fitted":
        value = factor.get("fitted_factor", factor.get("selected_factor"))
    elif selected_basis == "manual_override":
        return None
    else:
        value = (factor.get("candidate_averages") or {}).get(selected_basis)
    return float(value) if _is_number(value) else None


def _factor_by_age_or_from_dev(factors: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, Any] | None:
    development_age = str(request.get("development_age") or "").strip()
    from_dev = request.get("from_dev")
    for factor in factors:
        label = factor.get("development_age") or f"{factor.get('from_dev')} -> {factor.get('to_dev')}"
        if development_age and str(label) == development_age:
            return factor
        if from_dev is not None and str(factor.get("from_dev")) == str(from_dev):
            return factor
    return None


def _normalise_factor_selections(
    run_id: str,
    run_dir: Path,
    requested: list[dict[str, Any]],
    *,
    allow_incomplete_rationale: bool = False,
) -> list[dict[str, Any]]:
    factors = chain_ladder.build_factors(run_id, run_dir).get("factors", [])
    normalised = []
    seen_from_devs: set[int] = set()
    for raw in requested:
        _require(isinstance(raw, dict), "factor_selections entries must be objects")
        selected_basis = str(raw.get("selected_basis") or raw.get("basis") or "").strip()
        _require(
            selected_basis
            in {
                "fitted",
                "volume_weighted",
                "simple_average",
                "last_3",
                "last_5",
                "trimmed_mean",
                "median",
                "manual_override",
            },
            f"unsupported selected_basis: {selected_basis}",
        )
        factor = _factor_by_age_or_from_dev(factors, raw)
        _require(factor is not None, "factor selection development age is not available in fit.json")
        from_dev = int(factor["from_dev"])
        _require(from_dev not in seen_from_devs, f"duplicate factor selection for from_dev {from_dev}")
        seen_from_devs.add(from_dev)
        manual_override = selected_basis == "manual_override"
        expected_value = _candidate_value(factor, selected_basis)
        provided = raw.get("selected_factor", raw.get("selected_factor_value", expected_value))
        _require(_is_number(provided), "selected_factor must be numeric")
        selected_value = float(provided)
        _require(selected_value > 0, "selected_factor must be positive")
        if manual_override:
            if not allow_incomplete_rationale:
                _require(
                    bool(str(raw.get("rationale") or "").strip()),
                    f"rationale is required for manual override {factor['development_age']}",
                )
        else:
            _require(
                expected_value is not None,
                f"selected_basis is not available for {factor['development_age']}: {selected_basis}",
            )
            _require(
                _approx_equal(selected_value, expected_value),
                "selected_factor does not match the selected basis candidate",
            )
            selected_value = float(expected_value)
        previous = factor.get("selected_factor")
        rationale = str(raw.get("rationale") or "").strip()
        if not allow_incomplete_rationale and not _approx_equal(selected_value, previous):
            _require(bool(rationale), f"rationale is required for changed factor {factor['development_age']}")
        row = {
            "from_dev": from_dev,
            "to_dev": factor["to_dev"],
            "development_age": factor["development_age"],
            "previous_factor": previous,
            "selected_factor": selected_value,
            "selected_basis": selected_basis,
            "selection_source": "manual" if manual_override else "candidate",
            "manual_override": manual_override,
            "rationale": rationale or None,
        }
        if not manual_override:
            row["candidate_value"] = selected_value
        normalised.append(row)
    return normalised


def _normalise_exclusions(
    requested: list[dict[str, Any]],
    *,
    allow_incomplete_rationale: bool = False,
) -> list[dict[str, Any]]:
    exclusions = []
    for raw in requested:
        _require(isinstance(raw, dict), "exclusions entries must be objects")
        exclusion_type = str(raw.get("type") or "").strip()
        value = str(raw.get("value") or "").strip()
        rationale = str(raw.get("rationale") or "").strip()
        _require(exclusion_type in {"origin", "valuation", "factor_point"}, f"unsupported exclusion type: {exclusion_type}")
        _require(bool(value), "exclusion value is required")
        if not allow_incomplete_rationale:
            _require(bool(rationale), "exclusion rationale is required")
        if exclusion_type == "factor_point":
            origin = str(raw.get("origin") or "").strip()
            from_dev = raw.get("from_dev")
            _require(bool(origin), "factor_point exclusion origin is required")
            try:
                from_dev = int(from_dev)
            except (TypeError, ValueError) as exc:
                raise SelectionSetError("factor_point exclusion from_dev is required") from exc
            exclusions.append(
                {
                    "type": exclusion_type,
                    "value": value,
                    "origin": origin,
                    "from_dev": from_dev,
                    "to_dev": raw.get("to_dev"),
                    "development_age": raw.get("development_age"),
                    "rationale": rationale,
                }
            )
        else:
            exclusions.append({"type": exclusion_type, "value": value, "rationale": rationale})
    return exclusions


def _normalise_tail_selection(
    fit: dict[str, Any],
    raw: Any,
    *,
    allow_incomplete_rationale: bool = False,
) -> dict[str, Any] | None:
    if raw is None:
        return None
    _require(isinstance(raw, dict), "tail_selection must be an object")
    tail_type = str(raw.get("type") or "").strip()
    _require(tail_type in {"none", "constant"}, "tail_selection.type must be none or constant")
    factor = raw.get("factor")
    if tail_type == "constant":
        _require(_is_number(factor), "constant tail_selection.factor must be numeric")
        _require(float(factor) >= 1.0, "constant tail_selection.factor must be at least 1.0")
        selected_parameter = f"constant:{float(factor)}"
    else:
        factor = None
        selected_parameter = "none"
    base_parameter = str((fit.get("parameters") or {}).get("tail") or "none")
    rationale = str(raw.get("rationale") or "").strip()
    _require(selected_parameter != base_parameter, "tail_selection must differ from the base tail")
    if not allow_incomplete_rationale:
        _require(bool(rationale), "changed tail selection requires rationale")
    return {
        "type": tail_type,
        "factor": float(factor) if _is_number(factor) else None,
        "base_parameter": base_parameter,
        "selected_parameter": selected_parameter,
        "rationale": rationale,
    }


def _params_from_fit(
    fit: dict[str, Any],
    factor_selections: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    tail_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters = fit.get("parameters") or {}
    excluded_origins = list(parameters.get("excluded_origins", []))
    excluded_valuations = list(parameters.get("excluded_valuations", []))
    excluded_factor_points = list(parameters.get("excluded_factor_points", []))
    for exclusion in exclusions:
        if exclusion["type"] == "origin" and exclusion["value"] not in excluded_origins:
            excluded_origins.append(exclusion["value"])
        if exclusion["type"] == "valuation" and exclusion["value"] not in excluded_valuations:
            excluded_valuations.append(exclusion["value"])
        if exclusion["type"] == "factor_point":
            point = {
                "origin": exclusion["origin"],
                "from_dev": exclusion["from_dev"],
                "to_dev": exclusion.get("to_dev"),
                "development_age": exclusion.get("development_age"),
                "rationale": exclusion.get("rationale"),
            }
            if point not in excluded_factor_points:
                excluded_factor_points.append(point)
    return {
        "averaging": parameters.get("averaging", "volume"),
        "tail": factor_selection._parse_tail(
            tail_selection["selected_parameter"] if tail_selection else parameters.get("tail", "none")
        ),
        "n_periods": parameters.get("n_periods"),
        "excluded_origins": excluded_origins,
        "excluded_valuations": excluded_valuations,
        "excluded_factor_points": excluded_factor_points,
        "sigma_interpolation": parameters.get("sigma_interpolation", "mack"),
        "selected_factors": [
            {
                "from_dev": row["from_dev"],
                "to_dev": row["to_dev"],
                "development_age": row["development_age"],
                "basis": row["selected_basis"],
                "factor": row["selected_factor"],
                "manual_override": row.get("manual_override", False),
            }
            for row in factor_selections
        ],
    }


def _comparison(base_fit: dict[str, Any], candidate_fit: dict[str, Any]) -> dict[str, Any]:
    base_totals = base_fit.get("totals") or {}
    candidate_totals = candidate_fit.get("totals") or {}
    return {
        "base": {
            "latest": base_totals.get("latest"),
            "ultimate": base_totals.get("ultimate"),
            "ibnr": base_totals.get("ibnr"),
        },
        "candidate": {
            "latest": candidate_totals.get("latest"),
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
        "by_origin_ibnr_impact": factor_selection._by_origin_impacts(base_fit, candidate_fit),
    }


def _factor_overlay(run_dir: Path, base_fit: dict[str, Any], candidate_fit: dict[str, Any]) -> list[dict[str, Any]]:
    analysis = io.maybe_read_json(run_dir, schemas.FACTOR_ANALYSIS_FILENAME) or {}
    periods = {
        str(period.get("from_dev")): period
        for period in analysis.get("development_periods", [])
    }
    overlays = []
    for base_factor in base_fit.get("development_factors", []):
        from_dev = str(base_factor.get("from_dev"))
        period = periods.get(from_dev)
        if not period:
            continue
        candidate_factor = _factor_by_age_or_from_dev(
            candidate_fit.get("development_factors", []),
            {"from_dev": from_dev},
        ) or {}
        base_value = base_factor.get("selected_factor", base_factor.get("ldf"))
        selected_value = candidate_factor.get("selected_factor", candidate_factor.get("ldf"))
        plot = period.get("plot") or {}
        overlays.append(
            {
                "from_dev": base_factor.get("from_dev"),
                "development_age": period.get("development_age"),
                "base_factor": base_value,
                "selected_factor": selected_value,
                "delta_factor": (
                    float(selected_value) - float(base_value)
                    if _is_number(selected_value) and _is_number(base_value)
                    else None
                ),
                "base_linear_y_pct": factor_analysis.axis_percent(
                    base_value, plot.get("linear_min", 0.0), plot.get("linear_max", 1.0)
                ),
                "selected_linear_y_pct": factor_analysis.axis_percent(
                    selected_value, plot.get("linear_min", 0.0), plot.get("linear_max", 1.0)
                ),
                "base_log_y_pct": factor_analysis.axis_percent(
                    base_value,
                    plot.get("log_min", 1.0),
                    plot.get("log_max", 1.0),
                    log_scale=True,
                ),
                "selected_log_y_pct": factor_analysis.axis_percent(
                    selected_value,
                    plot.get("log_min", 1.0),
                    plot.get("log_max", 1.0),
                    log_scale=True,
                ),
                "source_ref": "selection_set.candidate_fit.development_factors",
            }
        )
    return overlays


def build_selection_set_preview(
    run_id: str,
    run_dir: Path,
    request: dict[str, Any],
    *,
    command: str | None = None,
    dry_run: bool = False,
    allow_incomplete_rationale: bool = False,
) -> dict[str, Any]:
    """Run a deterministic selection preview.

    ``dry_run`` with ``allow_incomplete_rationale`` is reserved for the
    workbench's transient live display. It never writes a selection-set
    artifact and is not eligible for commit or report generation.
    """
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    run_manifest = io.maybe_read_json(run_dir, "manifest.json")
    _require(fit is not None, "selection set preview requires fit.json")
    _require(run_manifest is not None, "selection set preview requires manifest.json")
    _require(
        chain_ladder.is_chain_ladder_method(fit.get("method")),
        "selection set preview is currently supported only for deterministic chain ladder runs",
    )

    factor_selections = _normalise_factor_selections(
        run_id,
        run_dir,
        list(request.get("factor_selections") or []),
        allow_incomplete_rationale=allow_incomplete_rationale,
    )
    exclusions = _normalise_exclusions(
        list(request.get("exclusions") or []),
        allow_incomplete_rationale=allow_incomplete_rationale,
    )
    tail_selection = _normalise_tail_selection(
        fit,
        request.get("tail_selection"),
        allow_incomplete_rationale=allow_incomplete_rationale,
    )
    _require(
        factor_selections or exclusions or tail_selection,
        "selection set preview requires at least one factor selection, exclusion, or tail selection",
    )

    global_rationale = str(request.get("global_rationale") or request.get("global_note") or "").strip()
    created_by = request.get("created_by") or {}
    review_metadata = _normalise_review_metadata(run_dir, request)
    source_artifacts = [
        name
        for name in (
            "fit.json",
            "triangle.json",
            "validation.json",
            schemas.FACTOR_ANALYSIS_FILENAME,
            schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
        )
        if (run_dir / name).is_file()
    ]
    input_hashes = io.artifact_hashes(run_dir, source_artifacts)
    stable_payload = {
        "run_id": run_id,
        "factor_selections": factor_selections,
        "exclusions": exclusions,
        "tail_selection": tail_selection,
        **review_metadata,
        "input_hashes": input_hashes,
    }
    selection_set_id = _stable_id("selection_set", stable_payload)
    path = selection_set_path(run_dir, selection_set_id)
    if not dry_run and path.is_file():
        current = io.read_json(path)
        _require(current.get("status") == "preview", f"committed selection set cannot be overwritten: {selection_set_id}")
        return current

    params = _params_from_fit(fit, factor_selections, exclusions, tail_selection)
    triangle_csv = factor_selection._resolve_replay_input(run_dir, run_manifest)
    _tri_handle, candidate_result = model_runner.fit_triangle(
        triangle_csv,
        "chain_ladder",
        params,
    )
    candidate_fit = candidate_result.to_fit_json(run_id)
    base_triangle = io.maybe_read_json(run_dir, "triangle.json") or {}
    actual_cells = [cell for cell in base_triangle.get("cells", []) if cell.get("type") == "actual"]
    candidate_triangle = {
        "run_id": run_id,
        "basis": base_triangle.get("basis"),
        "cells": triangle_projection.build_cells(actual_cells, candidate_fit.get("development_factors", [])),
    }
    preview_scenario_id = selection_set_id
    payload = {
        "schema_version": schemas.SCHEMA_VERSION,
        "selection_set_id": selection_set_id,
        "preview_scenario_id": preview_scenario_id,
        "run_id": run_id,
        "basis_run_id": run_id,
        "status": "live_preview" if dry_run else "preview",
        "preview_kind": "transient" if dry_run else "governed",
        "source_explore_scenario_id": request.get("source_explore_scenario_id"),
        "factor_selections": factor_selections,
        "exclusions": exclusions,
        "manual_overrides": [row for row in factor_selections if row.get("manual_override")],
        "factor_point_exclusions": [row for row in exclusions if row.get("type") == "factor_point"],
        "tail_selection": tail_selection,
        **review_metadata,
        "global_rationale": global_rationale or None,
        "created_utc": manifest.utc_now_iso(),
        "created_by": {
            "id": str(created_by.get("id") or "").strip() or None,
            "display_name": str(created_by.get("display_name") or "").strip() or None,
        },
        "source_artifacts_reviewed": source_artifacts,
        "source_artifacts": source_artifacts,
        "input_hashes": input_hashes,
        "selected_factors_used": params["selected_factors"],
        "exclusions_used": exclusions,
        "parameters": params,
        "command": command or f"POST /api/runs/{run_id}/selection-sets/preview",
        "comparison": _comparison(fit, candidate_fit),
        "factor_overlay": _factor_overlay(run_dir, fit, candidate_fit),
        "candidate_fit": candidate_fit,
        "candidate_triangle": candidate_triangle,
        "selection_set_artifact": None if dry_run else selection_set_artifact(selection_set_id),
    }
    if not dry_run:
        io.write_json(path, payload)
    return payload


def commit_selection_set(
    run_id: str,
    run_dir: Path,
    selection_set_id: str,
    payload: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    path = selection_set_path(run_dir, selection_set_id)
    _require(path.is_file(), f"selection_set_id does not exist: {selection_set_id}")
    selection_set = io.read_json(path)
    _require(selection_set.get("run_id") == run_id, "selection set run_id does not match target run_id")
    _require(selection_set.get("status") == "preview", f"committed selection set cannot be overwritten: {selection_set_id}")
    current_hashes = io.artifact_hashes(run_dir, selection_set.get("source_artifacts", []))
    _require(
        current_hashes == selection_set.get("input_hashes", {}),
        "selection set source artifacts are stale; preview a new selection set before commit",
    )

    global_rationale = str(payload.get("global_rationale") or selection_set.get("global_rationale") or "").strip()
    _require(bool(global_rationale), "committed selection set requires global_rationale")
    for factor in selection_set.get("factor_selections", []):
        changed = not _approx_equal(factor.get("previous_factor"), factor.get("selected_factor"))
        _require(not changed or bool(str(factor.get("rationale") or "").strip()), "changed factor selections require rationale")
    for exclusion in selection_set.get("exclusions", []):
        _require(bool(str(exclusion.get("rationale") or "").strip()), "exclusions require rationale")
    tail_selection = selection_set.get("tail_selection")
    if tail_selection:
        _require(bool(str(tail_selection.get("rationale") or "").strip()), "tail selection requires rationale")

    created_by = payload.get("created_by") or selection_set.get("created_by") or {}
    committed = dict(selection_set)
    committed["status"] = "committed"
    committed["global_rationale"] = global_rationale
    committed["created_by"] = {
        "id": str(created_by.get("id") or "").strip() or None,
        "display_name": str(created_by.get("display_name") or "").strip() or None,
    }
    committed["committed_utc"] = manifest.utc_now_iso()
    if not dry_run:
        io.write_json(path, committed)
    return committed
