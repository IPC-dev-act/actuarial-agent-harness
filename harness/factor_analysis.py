"""Deterministic BCL link-ratio analysis and review-suggestion artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from harness import manifest, model_runner
from harness.workbench import chain_ladder, io, schemas


class FactorAnalysisError(ValueError):
    """Raised when factor analysis cannot be produced from a run."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactorAnalysisError(message)


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]}"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _delta(candidate: Any, base: Any) -> float | None:
    if not _is_number(candidate) or not _is_number(base):
        return None
    return float(candidate) - float(base)


def _factor_for(fit: dict[str, Any], from_dev: Any) -> dict[str, Any] | None:
    return next(
        (row for row in fit.get("development_factors", []) if str(row.get("from_dev")) == str(from_dev)),
        None,
    )


def axis_percent(value: Any, minimum: float, maximum: float, *, log_scale: bool = False) -> float | None:
    if not _is_number(value):
        return None
    numeric = float(value)
    if log_scale:
        if numeric <= 0 or minimum <= 0 or maximum <= 0:
            return None
        numeric = math.log(numeric)
        minimum = math.log(minimum)
        maximum = math.log(maximum)
    if maximum == minimum:
        return 50.0
    ratio = (numeric - minimum) / (maximum - minimum)
    return max(7.0, min(93.0, 93.0 - ratio * 86.0))


def _candidate_rows(factor: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = factor.get("candidate_averages") or {}
    rows = [
        {"basis": "fitted", "label": "Fitted / current", "value": factor.get("fitted_factor", factor.get("ldf"))},
        {"basis": "volume_weighted", "label": "Volume weighted", "value": candidates.get("volume_weighted")},
        {"basis": "simple_average", "label": "Simple average", "value": candidates.get("simple_average")},
        {"basis": "last_3", "label": "Last 3", "value": candidates.get("last_3")},
        {"basis": "last_5", "label": "Last 5", "value": candidates.get("last_5")},
        {"basis": "trimmed_mean", "label": "Trimmed mean", "value": candidates.get("trimmed_mean")},
        {"basis": "median", "label": "Median", "value": candidates.get("median")},
    ]
    notes = factor.get("candidate_average_notes") or {}
    for row in rows:
        row["available"] = _is_number(row.get("value"))
        row["reason"] = None if row["available"] else notes.get(row["basis"], "not available")
        row["source_ref"] = f"fit.json: development_factors[from_dev={factor.get('from_dev')}].candidate_averages.{row['basis']}"
    return rows


def _point_id(origin: Any, from_dev: Any) -> str:
    return f"origin:{origin}:from_dev:{from_dev}"


def _run_exclusion(
    triangle_csv: Path,
    run_id: str,
    fit: dict[str, Any],
    point: dict[str, Any],
) -> dict[str, Any]:
    params = model_runner.parameters_from_fit(fit)
    exclusion = {
        "origin": str(point["origin"]),
        "from_dev": point["from_dev"],
        "to_dev": point.get("to_dev"),
        "development_age": point.get("development_age"),
    }
    params["excluded_factor_points"] = [*params.get("excluded_factor_points", []), exclusion]
    _triangle, result = model_runner.fit_triangle(triangle_csv, "chain_ladder", params)
    candidate_fit = result.to_fit_json(run_id)
    candidate_factor = _factor_for(candidate_fit, point["from_dev"]) or {}
    return {
        "status": "available",
        "candidate_factor": candidate_factor.get("selected_factor", candidate_factor.get("ldf")),
        "candidate_ultimate": (candidate_fit.get("totals") or {}).get("ultimate"),
        "candidate_ibnr": (candidate_fit.get("totals") or {}).get("ibnr"),
        "delta_factor": _delta(
            candidate_factor.get("selected_factor", candidate_factor.get("ldf")),
            point.get("base_factor"),
        ),
        "delta_ultimate": _delta(
            (candidate_fit.get("totals") or {}).get("ultimate"),
            (fit.get("totals") or {}).get("ultimate"),
        ),
        "delta_ibnr": _delta(
            (candidate_fit.get("totals") or {}).get("ibnr"),
            (fit.get("totals") or {}).get("ibnr"),
        ),
    }


def build_factor_analysis(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    run_manifest = io.maybe_read_json(run_dir, "manifest.json")
    _require(fit is not None, "factor analysis requires fit.json")
    _require(run_manifest is not None, "factor analysis requires manifest.json")
    _require(
        chain_ladder.is_chain_ladder_method(fit.get("method")),
        "factor analysis is currently supported only for deterministic chain ladder runs",
    )
    triangle_csv = model_runner.replay_input(run_dir, run_manifest)
    source_artifacts = [name for name in ("fit.json", "triangle.json", "validation.json") if (run_dir / name).is_file()]
    input_hashes = io.artifact_hashes(run_dir, source_artifacts)
    analysis_id = _stable_id(
        "factor_analysis",
        {"run_id": run_id, "method": fit.get("method"), "input_hashes": input_hashes, "analysis": "leave_one_out_v1"},
    )

    development_periods = []
    all_influences = []
    for factor in fit.get("development_factors", []):
        if factor.get("to_dev") == "ult":
            continue
        from_dev = factor.get("from_dev")
        development_age = factor.get("development_age") or f"{from_dev} -> {factor.get('to_dev')}"
        candidates = _candidate_rows(factor)
        link_ratios = factor.get("link_ratios") or []
        values = [float(row["link_ratio"]) for row in link_ratios if _is_number(row.get("link_ratio"))]
        values.extend(float(row["value"]) for row in candidates if row["available"])
        minimum = min(values) if values else 0.0
        maximum = max(values) if values else 1.0
        positive = [value for value in values if value > 0]
        log_minimum = min(positive) if positive else 1.0
        log_maximum = max(positive) if positive else 1.0
        points = []
        for index, ratio in enumerate(link_ratios):
            point = {
                "point_id": _point_id(ratio.get("origin"), from_dev),
                "origin": str(ratio.get("origin")),
                "from_dev": from_dev,
                "to_dev": factor.get("to_dev"),
                "development_age": development_age,
                "link_ratio": ratio.get("link_ratio"),
                "current_value": ratio.get("current_value"),
                "next_value": ratio.get("next_value"),
                "base_factor": factor.get("selected_factor", factor.get("ldf")),
                "included": True,
                "source_ref": f"fit.json: development_factors[from_dev={from_dev}].link_ratios[{index}]",
                "x_pct": 8.0 + (84.0 * index / max(1, len(link_ratios) - 1)),
                "linear_y_pct": axis_percent(ratio.get("link_ratio"), minimum, maximum),
                "log_y_pct": axis_percent(ratio.get("link_ratio"), log_minimum, log_maximum, log_scale=True),
            }
            try:
                point["influence"] = _run_exclusion(triangle_csv, run_id, fit, point)
            except Exception as exc:
                point["influence"] = {"status": "unavailable", "reason": str(exc)}
            points.append(point)
            if _is_number((point.get("influence") or {}).get("delta_ibnr")):
                all_influences.append(point)

        available_candidate_values = [float(row["value"]) for row in candidates if row["available"]]
        base_factor = factor.get("selected_factor", factor.get("ldf"))
        spread = max(available_candidate_values) - min(available_candidate_values) if available_candidate_values else None
        spread_pct = abs(spread / float(base_factor) * 100.0) if _is_number(spread) and _is_number(base_factor) and float(base_factor) else None
        for candidate in candidates:
            candidate["linear_y_pct"] = axis_percent(candidate.get("value"), minimum, maximum)
            candidate["log_y_pct"] = axis_percent(candidate.get("value"), log_minimum, log_maximum, log_scale=True)
        development_periods.append(
            {
                "development_age": development_age,
                "from_dev": from_dev,
                "to_dev": factor.get("to_dev"),
                "from_age": factor.get("from_age"),
                "to_age": factor.get("to_age"),
                "base_factor": base_factor,
                "observation_count": len(points),
                "candidate_spread": spread,
                "candidate_spread_pct": spread_pct,
                "thin_data": len(points) < 5,
                "candidates": candidates,
                "points": points,
                "plot": {
                    "linear_min": minimum,
                    "linear_max": maximum,
                    "log_min": log_minimum,
                    "log_max": log_maximum,
                },
            }
        )

    ranked = sorted(
        all_influences,
        key=lambda point: abs(float(point["influence"]["delta_ibnr"])),
        reverse=True,
    )
    for rank, point in enumerate(ranked, start=1):
        point["influence"]["rank"] = rank
        point["influence"]["high_influence"] = rank <= min(5, len(ranked))

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "analysis_id": analysis_id,
        "run_id": run_id,
        "method": fit.get("method"),
        "analysis_type": "bcl_link_ratio_leave_one_out",
        "status": "available",
        # Anchor generation metadata to the immutable run. Rebuilding the same
        # deterministic analysis must not invalidate an otherwise current preview.
        "created_utc": run_manifest.get("created_utc"),
        "development_periods": development_periods,
        "influence_ranking": [
            {
                "rank": point["influence"]["rank"],
                "point_id": point["point_id"],
                "origin": point["origin"],
                "development_age": point["development_age"],
                "link_ratio": point["link_ratio"],
                **point["influence"],
            }
            for point in ranked
        ],
        "source_artifacts": source_artifacts,
        "input_hashes": input_hashes,
        "command": f"reserve factor-analysis {run_id} --out runs",
    }


def build_review_suggestions(analysis: dict[str, Any]) -> dict[str, Any]:
    suggestions = []
    for row in analysis.get("influence_ranking", [])[:5]:
        evidence = {
            "point_id": row.get("point_id"),
            "origin": row.get("origin"),
            "development_age": row.get("development_age"),
            "link_ratio": row.get("link_ratio"),
            "delta_factor": row.get("delta_factor"),
            "delta_ultimate": row.get("delta_ultimate"),
            "delta_ibnr": row.get("delta_ibnr"),
            "influence_rank": row.get("rank"),
        }
        suggestions.append(
            {
                "suggestion_id": _stable_id("factor_review", evidence),
                "suggestion_type": "review_influential_link_ratio",
                "priority": "high" if row.get("rank", 99) <= 3 else "medium",
                "status": "suggested",
                "title": f"Review influential link ratio at {row.get('development_age')}",
                "summary": (
                    f"Origin {row.get('origin')} is influence rank {row.get('rank')}. "
                    "Inspect the point and compare a governed exclusion preview before selecting a factor."
                ),
                "target": {
                    "point_id": row.get("point_id"),
                    "origin": row.get("origin"),
                    "development_age": row.get("development_age"),
                },
                "evidence": evidence,
                "evidence_refs": [
                    f"factor_analysis.json: influence_ranking[rank={row.get('rank')}]",
                    f"fit.json: development_factors[from_dev={str(row.get('point_id')).partition('from_dev:')[2]}]",
                ],
                "proposed_review_action": {
                    "type": "inspect_then_preview_point_exclusion",
                    "exclusion": {
                        "type": "factor_point",
                        "value": f"{row.get('origin')}:{str(row.get('point_id')).partition('from_dev:')[2]}",
                        "origin": row.get("origin"),
                        "from_dev": str(row.get("point_id")).partition("from_dev:")[2],
                        "development_age": row.get("development_age"),
                    },
                },
                "governance": "non_governed_review_suggestion",
            }
        )

    for period in analysis.get("development_periods", []):
        if not period.get("thin_data"):
            continue
        evidence = {
            "development_age": period.get("development_age"),
            "observation_count": period.get("observation_count"),
            "candidate_spread_pct": period.get("candidate_spread_pct"),
        }
        suggestions.append(
            {
                "suggestion_id": _stable_id("factor_review", evidence),
                "suggestion_type": "review_thin_development_period",
                "priority": "medium",
                "status": "suggested",
                "title": f"Review thin data at {period.get('development_age')}",
                "summary": (
                    f"Only {period.get('observation_count')} observed link ratios support this development age. "
                    "Compare available candidates and document the selected basis."
                ),
                "target": {"development_age": period.get("development_age"), "from_dev": period.get("from_dev")},
                "evidence": evidence,
                "evidence_refs": [
                    f"factor_analysis.json: development_periods[from_dev={period.get('from_dev')}]"
                ],
                "proposed_review_action": {"type": "inspect_candidate_basis"},
                "governance": "non_governed_review_suggestion",
            }
        )

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": analysis["run_id"],
        "analysis_id": analysis["analysis_id"],
        "status": "available",
        "generated_utc": analysis.get("created_utc"),
        "generator": {
            "type": "deterministic_review_screen",
            "intended_consumer": "AI review workflow and senior actuary",
            "final_selection_authority": False,
        },
        "suggestions": suggestions,
        "source_artifacts": [schemas.FACTOR_ANALYSIS_FILENAME],
        "input_hashes": {},
        "governance": "suggestions_are_exploratory_and_never_commit_judgment",
    }


def write_factor_analysis(run_id: str, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = Path(run_dir)
    analysis = build_factor_analysis(run_id, run_dir)
    io.write_json(run_dir / schemas.FACTOR_ANALYSIS_FILENAME, analysis)
    suggestions = build_review_suggestions(analysis)
    suggestions["input_hashes"] = io.artifact_hashes(run_dir, [schemas.FACTOR_ANALYSIS_FILENAME])
    io.write_json(run_dir / schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME, suggestions)
    return analysis, suggestions
