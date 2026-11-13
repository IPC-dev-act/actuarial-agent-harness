"""Read-only deterministic chain ladder projections for the workbench.

This module adapts existing run artifacts for dashboard display. It does not
fit, refit, or recompute actuarial outputs.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from . import io, schemas, scenarios

CHAIN_LADDER_METHODS = {"bcl", "chain_ladder", "chainladder"}
MACK_METHOD = "mack"


def _normalise_method(method: Any) -> str:
    return str(method or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_chain_ladder_method(method: Any) -> bool:
    return _normalise_method(method) in CHAIN_LADDER_METHODS


def display_method(method: Any) -> str:
    normalised = _normalise_method(method)
    if normalised in CHAIN_LADDER_METHODS:
        return "Deterministic Chain Ladder"
    if normalised == MACK_METHOD:
        return "Mack Chain Ladder"
    return str(method or "n/a")


def _available_artifacts(run_dir: Path, names: list[str]) -> list[str]:
    return [name for name in names if (Path(run_dir) / name).is_file()]


def _manifest_input_path(run_dir: Path) -> str | None:
    run_manifest = io.maybe_read_json(run_dir, "manifest.json") or {}
    inputs = run_manifest.get("inputs") or []
    if not inputs:
        return None
    return inputs[0].get("path")


def _triangle_counts(run_dir: Path) -> tuple[int | None, int | None]:
    triangle = io.maybe_read_json(run_dir, "triangle.json")
    if not triangle:
        return None, None
    origins = set()
    developments = set()
    for cell in triangle.get("cells", []):
        if "origin" in cell and cell.get("origin") is not None:
            origins.add(str(cell["origin"]))
        development = cell.get("dev", cell.get("development"))
        if development is not None:
            developments.add(str(development))
    return (len(origins) or None, len(developments) or None)


def _active_scenario_selection(run_dir: Path) -> dict[str, Any] | None:
    active = io.active_decisions(io.load_decisions(run_dir))
    approved_selection_sets = [
        decision
        for decision in active
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
        and decision.get("resulting_scenario_id")
    ]
    if len(approved_selection_sets) == 1:
        return approved_selection_sets[0]
    selections = [
        decision
        for decision in active
        if decision.get("decision_type") in {"factor_selection", "scenario_selection"}
        and decision.get("status") in {"accepted", "modified"}
        and decision.get("resulting_scenario_id")
    ]
    if not selections:
        return None
    return sorted(selections, key=lambda d: (d.get("timestamp_utc") or "", d.get("decision_id") or ""))[-1]


def _selected_scenario(run_dir: Path) -> tuple[str | None, dict[str, Any] | None]:
    decision = _active_scenario_selection(run_dir)
    if not decision:
        return None, None
    scenario_id = str(decision["resulting_scenario_id"])
    index = scenarios.load_scenario_index(run_dir)
    scenario = scenarios.scenario_by_id(index, scenario_id) if index else None
    if scenario is None:
        preview_path = Path(run_dir) / schemas.FACTOR_PREVIEWS_DIRNAME / f"{scenario_id}.json"
        scenario = io.read_json(preview_path) if preview_path.is_file() else None
    if scenario is None and decision.get("decision_type") == "selection_set_approval":
        selection_set_id = decision.get("selection_set_id") or scenario_id
        selection_set_path = Path(run_dir) / schemas.SELECTION_SETS_DIRNAME / f"{selection_set_id}.json"
        scenario = io.read_json(selection_set_path) if selection_set_path.is_file() else None
    return scenario_id, scenario


def _first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _development_age(row: dict[str, Any]) -> str | None:
    if "development_age" in row:
        return str(row["development_age"])
    if "from_dev" in row and "to_dev" in row:
        return f"{row['from_dev']} -> {row['to_dev']}"
    return None


def _candidate_averages(row: dict[str, Any]) -> dict[str, Any]:
    candidates = row.get("candidate_averages")
    if isinstance(candidates, dict):
        return {
            "volume_weighted": _first_present(candidates, ("volume_weighted", "volume_weighted_average")),
            "simple_average": _first_present(candidates, ("simple_average", "simple")),
            "last_3": _first_present(candidates, ("last_3", "last3")),
            "last_5": _first_present(candidates, ("last_5", "last5")),
            "all_years": _first_present(candidates, ("all_years", "all")),
            "trimmed_mean": _first_present(candidates, ("trimmed_mean", "trimmed")),
            "median": _first_present(candidates, ("median",)),
        }
    return {
        "volume_weighted": _first_present(row, ("volume_weighted", "volume_weighted_average")),
        "simple_average": _first_present(row, ("simple_average", "simple")),
        "last_3": _first_present(row, ("last_3", "last3")),
        "last_5": _first_present(row, ("last_5", "last5")),
        "all_years": _first_present(row, ("all_years", "all")),
        "trimmed_mean": _first_present(row, ("trimmed_mean", "trimmed")),
        "median": _first_present(row, ("median",)),
    }


def build_summary(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    method = fit.get("method") if fit else None
    origin_count, development_count = _triangle_counts(run_dir)
    selected_scenario_id, selected_scenario = _selected_scenario(run_dir)

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "available": bool(fit),
        "method": method,
        "display_method": display_method(method),
        "is_chain_ladder": is_chain_ladder_method(method),
        "input_file": _manifest_input_path(run_dir),
        "totals": {
            "latest": (fit.get("totals") or {}).get("latest") if fit else None,
            "ultimate": (fit.get("totals") or {}).get("ultimate") if fit else None,
            "ibnr": (fit.get("totals") or {}).get("ibnr") if fit else None,
            "mack_se": (fit.get("totals") or {}).get("mack_se") if fit else None,
        },
        "origin_period_count": origin_count,
        "development_period_count": development_count,
        "selected_scenario_id": selected_scenario_id,
        "selected_scenario": selected_scenario,
        "source_artifacts": _available_artifacts(
            run_dir,
            ["manifest.json", "fit.json", "triangle.json", schemas.SCENARIO_INDEX_FILENAME],
        ),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _chart_percent(value: Any, maximum: float | None) -> float | None:
    if not _is_number(value) or not maximum:
        return None
    return max(0.0, min(100.0, abs(float(value)) / maximum * 100.0))


def _candidate_cards(row: dict[str, Any]) -> list[dict[str, Any]]:
    current = row.get("selected_factor")
    candidates = row.get("candidate_averages") or {}
    notes = row.get("candidate_average_notes") or {}
    cards = [
        {
            "basis": "fitted",
            "label": "Fitted / current",
            "value": row.get("fitted_factor") if row.get("fitted_factor") is not None else current,
            "source": "fit.json development_factors",
        },
        {
            "basis": "volume_weighted",
            "label": "Volume weighted",
            "value": candidates.get("volume_weighted"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "simple_average",
            "label": "Simple average",
            "value": candidates.get("simple_average"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "last_3",
            "label": "Last 3",
            "value": candidates.get("last_3"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "last_5",
            "label": "Last 5",
            "value": candidates.get("last_5"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "trimmed_mean",
            "label": "Trimmed mean",
            "value": candidates.get("trimmed_mean"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "median",
            "label": "Median",
            "value": candidates.get("median"),
            "source": "fit.json candidate_averages",
        },
        {
            "basis": "log_linear_smoothing",
            "label": "Log-linear smoothing",
            "value": candidates.get("log_linear_smoothing"),
            "source": "not available in current deterministic output",
        },
        {
            "basis": "manual_override",
            "label": "Manual override",
            "value": None,
            "source": "actuary-entered value staged through selection_set preview",
            "input_required": True,
        },
    ]
    for card in cards:
        value = card.get("value")
        card["available"] = _is_number(value)
        if card["basis"] == "manual_override":
            card["available"] = False
            card["reason"] = "enter a positive selected factor and rationale"
        elif card["basis"] == "log_linear_smoothing" and not card["available"]:
            card["reason"] = notes.get("log_linear_smoothing") or "not available in the deterministic fit artifact"
        elif not card["available"]:
            card["reason"] = notes.get(card["basis"]) or "not available"
        card["delta_vs_current"] = float(value) - float(current) if _is_number(value) and _is_number(current) else None
        card["rationale_required"] = bool(card["available"] and card["basis"] != "fitted")
    return cards


def _attach_factor_curve_percents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        for key in ("base_factor", "selected_factor", "fitted_factor"):
            if _is_number(row.get(key)):
                values.append(abs(float(row[key])))
        for card in row.get("candidate_cards", []) or []:
            if _is_number(card.get("value")):
                values.append(abs(float(card["value"])))
    maximum = max(values) if values else None
    for row in rows:
        row["base_chart_pct"] = _chart_percent(row.get("base_factor"), maximum)
        row["selected_chart_pct"] = _chart_percent(row.get("selected_factor"), maximum)
        row["fitted_chart_pct"] = _chart_percent(row.get("fitted_factor"), maximum)
        for card in row.get("candidate_cards", []) or []:
            card["chart_pct"] = _chart_percent(card.get("value"), maximum)
    return rows


def _smooth_display_path(points: list[dict[str, Any]]) -> str:
    if not points:
        return ""
    if len(points) < 3:
        return " ".join(
            f"{'M' if index == 0 else 'L'}{point['x']:.1f},{point['y']:.1f}"
            for index, point in enumerate(points)
        )
    path = f"M{points[0]['x']:.1f},{points[0]['y']:.1f}"
    for index in range(len(points) - 1):
        previous = points[max(0, index - 1)]
        current = points[index]
        next_point = points[index + 1]
        after = points[min(len(points) - 1, index + 2)]
        c1x = current["x"] + (next_point["x"] - previous["x"]) / 6
        c1y = current["y"] + (next_point["y"] - previous["y"]) / 6
        c2x = next_point["x"] - (after["x"] - current["x"]) / 6
        c2y = next_point["y"] - (after["y"] - current["y"]) / 6
        path += f" C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {next_point['x']:.1f},{next_point['y']:.1f}"
    return path


def _all_factor_curve_display(rows: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = (
        ("fitted", "Fitted / current"),
        ("volume_weighted", "Volume weighted"),
        ("simple_average", "Simple average"),
        ("last_3", "Last 3"),
        ("last_5", "Last 5"),
        ("trimmed_mean", "Trimmed mean"),
        ("median", "Median"),
    )
    raw_series = []
    all_values = []
    denominator = max(1, len(rows) - 1)
    for basis, label in definitions:
        points = []
        for index, row in enumerate(rows):
            value = row.get("fitted_factor") if basis == "fitted" else (row.get("candidate_averages") or {}).get(basis)
            if not _is_number(value) or float(value) <= 0:
                continue
            numeric = float(value)
            all_values.append(numeric)
            points.append(
                {
                    "development_age": row.get("development_age"),
                    "from_dev": row.get("from_dev"),
                    "value": numeric,
                    "x": 65.0 + index * (830.0 / denominator),
                }
            )
        raw_series.append({"basis": basis, "label": label, "points": points})
    max_log = max([math.log(value) for value in all_values] + [0.0001])
    for series in raw_series:
        for point in series["points"]:
            point["y"] = 35.0 + ((max_log - math.log(point["value"])) / max_log) * 215.0
        series["raw_path"] = " ".join(
            f"{'M' if index == 0 else 'L'}{point['x']:.1f},{point['y']:.1f}"
            for index, point in enumerate(series["points"])
        )
        series["smooth_path"] = _smooth_display_path(series["points"])
    return {
        "display_only": True,
        "scale": "log_factor_above_one",
        "max_log": max_log,
        "one_reference_y": 250.0,
        "ages": [
            {
                "development_age": row.get("development_age"),
                "x": 65.0 + index * (830.0 / denominator),
            }
            for index, row in enumerate(rows)
        ],
        "series": raw_series,
    }


def map_factor_drag(run_id: str, run_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Map raw pointer geometry to a manual factor through backend display scales."""
    run_dir = Path(run_dir)
    factors_payload = build_factors(run_id, run_dir)
    from_dev = request.get("from_dev")
    row = _factor_row_by_from_dev(factors_payload.get("factors", []), from_dev)
    if row is None:
        raise ValueError("drag target development age is unavailable")
    try:
        client_y = float(request["client_y"])
        rect_top = float(request["rect_top"])
        rect_height = float(request["rect_height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("drag mapping requires numeric client_y, rect_top, and rect_height") from exc
    if rect_height <= 0:
        raise ValueError("drag mapping rect_height must be positive")

    graph = str(request.get("graph") or "selected_age")
    scale = str(request.get("scale") or "linear")
    if graph == "selected_age":
        analysis = io.maybe_read_json(run_dir, schemas.FACTOR_ANALYSIS_FILENAME) or {}
        period = next(
            (item for item in analysis.get("development_periods", []) if str(item.get("from_dev")) == str(from_dev)),
            None,
        )
        if period is None:
            raise ValueError("selected-age drag mapping requires factor_analysis.json")
        svg_y = (client_y - rect_top) / rect_height * 360.0
        y_pct = max(7.0, min(93.0, (svg_y - 28.0) / 2.84))
        ratio = (93.0 - y_pct) / 86.0
        plot = period.get("plot") or {}
        if scale == "log":
            low = float(plot.get("log_min", 1.0))
            high = float(plot.get("log_max", 1.0))
            factor = math.exp(math.log(low) + ratio * (math.log(high) - math.log(low)))
        else:
            low = float(plot.get("linear_min", 0.0))
            high = float(plot.get("linear_max", 1.0))
            factor = low + ratio * (high - low)
    elif graph == "all_development":
        display = factors_payload.get("factor_curve_display") or {}
        max_log = float(display.get("max_log") or 0.0001)
        svg_y = (client_y - rect_top) / rect_height * 310.0
        y = max(35.0, min(250.0, svg_y))
        factor = math.exp(max_log - ((y - 35.0) / 215.0) * max_log)
    else:
        raise ValueError(f"unsupported factor drag graph: {graph}")

    analysis = io.maybe_read_json(run_dir, schemas.FACTOR_ANALYSIS_FILENAME) or {}
    period = next(
        (item for item in analysis.get("development_periods", []) if str(item.get("from_dev")) == str(from_dev)),
        None,
    )
    selected_positions = {"linear_y_pct": None, "log_y_pct": None}
    if period:
        plot = period.get("plot") or {}
        selected_positions = {
            "linear_y_pct": _axis_percent(factor, float(plot.get("linear_min", 0.0)), float(plot.get("linear_max", 1.0))),
            "log_y_pct": _log_axis_percent(factor, float(plot.get("log_min", 1.0)), float(plot.get("log_max", 1.0))),
        }
    display = factors_payload.get("factor_curve_display") or {}
    max_log = float(display.get("max_log") or 0.0001)
    all_curve_y = max(35.0, min(250.0, 35.0 + ((max_log - math.log(max(factor, 1e-12))) / max_log) * 215.0))
    return {
        "run_id": run_id,
        "from_dev": row.get("from_dev"),
        "to_dev": row.get("to_dev"),
        "development_age": row.get("development_age"),
        "base_factor": row.get("selected_factor"),
        "manual_factor": factor,
        "selected_graph": selected_positions,
        "all_curve_y": all_curve_y,
        "source_artifacts": [name for name in ("fit.json", schemas.FACTOR_ANALYSIS_FILENAME) if (run_dir / name).is_file()],
        "status": "staged_value_only",
        "governance": "manual override requires rationale and deterministic preview before commit",
    }


def _log_axis_percent(value: Any, minimum: float, maximum: float) -> float | None:
    if not _is_number(value) or float(value) <= 0 or minimum <= 0 or maximum <= 0:
        return None
    if maximum == minimum:
        return 50.0
    ratio = (math.log(float(value)) - math.log(minimum)) / (math.log(maximum) - math.log(minimum))
    return max(7.0, min(93.0, 93.0 - ratio * 86.0))


def build_factors(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    method = fit.get("method") if fit else None
    parameters = (fit.get("parameters") if fit else {}) or {}
    rows = []
    for row in (fit.get("development_factors", []) if fit else []):
        rows.append(
            {
                "development_age": _development_age(row),
                "from_dev": row.get("from_dev"),
                "to_dev": row.get("to_dev"),
                "from_age": row.get("from_age"),
                "to_age": row.get("to_age"),
                "selected_factor": _first_present(row, ("selected_factor", "fitted_factor", "ldf", "factor")),
                "fitted_factor": _first_present(row, ("fitted_factor", "ldf", "factor")),
                "factor_basis": _first_present(row, ("factor_basis", "basis")) or parameters.get("averaging"),
                "cumulative_development_factor": _first_present(
                    row,
                    ("cumulative_development_factor", "cdf"),
                ),
                "candidate_averages": _candidate_averages(row),
                "candidate_average_notes": row.get("candidate_average_notes", {}),
                "link_ratios": row.get("link_ratios", []),
            }
        )
    for row in rows:
        row["candidate_cards"] = _candidate_cards(row)
    _attach_factor_curve_percents(rows)
    factor_curve = [
        {
            "development_age": row.get("development_age"),
            "from_dev": row.get("from_dev"),
            "to_dev": row.get("to_dev"),
            "base_factor": row.get("fitted_factor"),
            "selected_factor": row.get("selected_factor"),
            "base_chart_pct": row.get("fitted_chart_pct"),
            "selected_chart_pct": row.get("selected_chart_pct"),
            "candidate_cards": row.get("candidate_cards", []),
        }
        for row in rows
    ]

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "available": bool(fit),
        "method": method,
        "display_method": display_method(method),
        "is_chain_ladder": is_chain_ladder_method(method),
        "factors": rows,
        "factor_curve": factor_curve,
        "factor_curve_display": _all_factor_curve_display(rows),
        "source_artifacts": _available_artifacts(run_dir, ["fit.json"]),
    }


def _factor_row_by_from_dev(rows: list[dict[str, Any]], from_dev: int | str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("from_dev")) == str(from_dev):
            return row
    return None


def _axis_percent(value: Any, minimum: float, maximum: float) -> float | None:
    if not _is_number(value):
        return None
    if maximum == minimum:
        return 50.0
    ratio = (float(value) - minimum) / (maximum - minimum)
    return max(8.0, min(92.0, 92.0 - ratio * 84.0))


def _point_x_percent(index: int, count: int) -> float:
    if count <= 1:
        return 50.0
    return 7.0 + (86.0 * index / (count - 1))


def _factor_point_id(origin: Any, from_dev: Any) -> str:
    return f"origin:{origin}:from_dev:{from_dev}"


def _factor_point_value(origin: Any, from_dev: Any) -> str:
    return f"{origin}:{from_dev}"


def _factor_point_action(origin: Any, from_dev: Any, to_dev: Any, development_age: str | None) -> dict[str, Any]:
    return {
        "point_exclusion": {
            "supported": True,
            "type": "factor_point",
            "value": _factor_point_value(origin, from_dev),
            "origin": str(origin),
            "from_dev": from_dev,
            "to_dev": to_dev,
            "development_age": development_age,
        },
        "origin_exclusion": {"supported": True, "type": "origin", "value": str(origin)},
        "valuation_exclusion": {"supported": True, "type": "valuation", "value": str(to_dev)},
    }


def build_factor_detail(run_id: str, run_dir: Path, from_dev: int | str) -> dict[str, Any]:
    run_dir = Path(run_dir)
    factors_payload = build_factors(run_id, run_dir)
    row = _factor_row_by_from_dev(factors_payload.get("factors", []), from_dev)
    if row is None:
        return {
            "schema_version": schemas.SCHEMA_VERSION,
            "run_id": run_id,
            "available": False,
            "from_dev": from_dev,
            "points": [],
            "candidate_lines": [],
            "source_artifacts": _available_artifacts(run_dir, ["fit.json"]),
        }

    exclusions = _selection_exclusions(run_dir)
    excluded_origins = set(exclusions.get("origins", []))
    excluded_valuations = set(exclusions.get("valuations", []))
    excluded_points = {
        (str(point.get("origin")), str(point.get("from_dev")))
        for point in exclusions.get("factor_points", [])
        if isinstance(point, dict)
    }
    point_rows = sorted(row.get("link_ratios") or [], key=lambda item: _sort_key(item.get("origin")))
    numeric_values = [
        float(point["link_ratio"])
        for point in point_rows
        if _is_number(point.get("link_ratio"))
    ]
    for card in row.get("candidate_cards", []) or []:
        if _is_number(card.get("value")):
            numeric_values.append(float(card["value"]))
    minimum = min(numeric_values) if numeric_values else 0.0
    maximum = max(numeric_values) if numeric_values else 1.0

    points = []
    for index, point in enumerate(point_rows):
        origin = str(point.get("origin"))
        point_from_dev = point.get("from_dev", row.get("from_dev"))
        point_to_dev = point.get("to_dev", row.get("to_dev"))
        excluded = (
            origin in excluded_origins
            or str(point_to_dev) in excluded_valuations
            or (origin, str(point_from_dev)) in excluded_points
        )
        points.append(
            {
                "point_id": _factor_point_id(origin, point_from_dev),
                "origin": origin,
                "development_age": row.get("development_age"),
                "from_dev": point_from_dev,
                "to_dev": point_to_dev,
                "from_age": point.get("from_age", row.get("from_age")),
                "to_age": point.get("to_age", row.get("to_age")),
                "link_ratio": point.get("link_ratio"),
                "current_value": point.get("current_value"),
                "next_value": point.get("next_value"),
                "included": not excluded,
                "excluded": excluded,
                "source_artifact": "fit.json",
                "x_pct": _point_x_percent(index, len(point_rows)),
                "y_pct": _axis_percent(point.get("link_ratio"), minimum, maximum),
                "actions": _factor_point_action(origin, point_from_dev, point_to_dev, row.get("development_age")),
            }
        )

    candidate_lines = []
    for card in row.get("candidate_cards", []) or []:
        candidate_lines.append(
            {
                "basis": card.get("basis"),
                "label": card.get("label") or card.get("basis"),
                "value": card.get("value"),
                "available": bool(card.get("available")),
                "reason": card.get("reason"),
                "source": card.get("source"),
                "y_pct": _axis_percent(card.get("value"), minimum, maximum) if card.get("available") else None,
            }
        )

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "available": True,
        "method": factors_payload.get("method"),
        "display_method": factors_payload.get("display_method"),
        "development_age": row.get("development_age"),
        "from_dev": row.get("from_dev"),
        "to_dev": row.get("to_dev"),
        "from_age": row.get("from_age"),
        "to_age": row.get("to_age"),
        "selected_factor": row.get("selected_factor"),
        "fitted_factor": row.get("fitted_factor"),
        "factor_basis": row.get("factor_basis"),
        "candidate_cards": row.get("candidate_cards", []),
        "candidate_lines": candidate_lines,
        "points": points,
        "point_count": len(points),
        "plot": {
            "x_axis": "origin",
            "y_axis": "link_ratio",
            "x_min_pct": 7.0,
            "x_max_pct": 93.0,
            "y_min": minimum,
            "y_max": maximum,
        },
        "source_artifacts": _available_artifacts(run_dir, ["fit.json", schemas.SELECTION_SETS_DIRNAME]),
    }


def _comparison_payloads(run_dir: Path) -> list[dict[str, Any]]:
    root = Path(run_dir) / schemas.COMPARISONS_DIRNAME
    if not root.is_dir():
        return []
    return [io.read_json(path) for path in sorted(root.glob("*.json"))]


def _scenario_impact_by_origin(run_dir: Path, scenario_id: str | None) -> dict[str, Any]:
    if not scenario_id:
        return {}
    preview_path = Path(run_dir) / schemas.FACTOR_PREVIEWS_DIRNAME / f"{scenario_id}.json"
    if preview_path.is_file():
        preview = io.read_json(preview_path)
        rows = (preview.get("comparison") or {}).get("by_origin_ibnr_impact")
        if isinstance(rows, list):
            return {
                str(row["origin"]): row
                for row in rows
                if isinstance(row, dict) and row.get("origin") is not None
            }
    selection_root = Path(run_dir) / schemas.SELECTION_SETS_DIRNAME
    if selection_root.is_dir():
        for selection_path in sorted(selection_root.glob("*.json")):
            selection_set = io.read_json(selection_path)
            if selection_set.get("preview_scenario_id") != scenario_id:
                continue
            rows = (selection_set.get("comparison") or {}).get("by_origin_ibnr_impact")
            if isinstance(rows, list):
                return {
                    str(row["origin"]): row
                    for row in rows
                    if isinstance(row, dict) and row.get("origin") is not None
                }
    for comparison in _comparison_payloads(run_dir):
        if comparison.get("candidate_scenario_id") != scenario_id:
            continue
        for key in ("by_origin_deltas", "origin_deltas", "projection_deltas"):
            rows = comparison.get(key)
            if isinstance(rows, dict):
                return {str(origin): value for origin, value in rows.items()}
            if isinstance(rows, list):
                return {
                    str(row["origin"]): row
                    for row in rows
                    if isinstance(row, dict) and row.get("origin") is not None
                }
    return {}


def build_projection(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json")
    method = fit.get("method") if fit else None
    selected_scenario_id, _scenario = _selected_scenario(run_dir)
    impacts = _scenario_impact_by_origin(run_dir, selected_scenario_id)
    rows = []
    max_ibnr = max(
        [abs(float(row.get("ibnr"))) for row in fit.get("by_origin", []) if _is_number(row.get("ibnr"))],
        default=None,
    ) if fit else None
    max_selected_ibnr = max(
        [
            abs(float(impact.get("candidate_ibnr")))
            for impact in impacts.values()
            if isinstance(impact, dict) and _is_number(impact.get("candidate_ibnr"))
        ],
        default=None,
    )
    for row in (fit.get("by_origin", []) if fit else []):
        origin = str(row.get("origin"))
        impact = impacts.get(origin)
        selected_ibnr = impact.get("candidate_ibnr") if isinstance(impact, dict) else None
        delta_ibnr = impact.get("delta_ibnr") if isinstance(impact, dict) else None
        delta_ibnr_pct = impact.get("delta_ibnr_pct") if isinstance(impact, dict) else None
        rows.append(
            {
                "origin": row.get("origin"),
                "latest": row.get("latest"),
                "ultimate": row.get("ultimate"),
                "ibnr": row.get("ibnr"),
                "mack_se": row.get("mack_se"),
                "selected_ibnr": selected_ibnr,
                "delta_ibnr": delta_ibnr,
                "delta_ibnr_pct": delta_ibnr_pct,
                "ibnr_chart_pct": _chart_percent(row.get("ibnr"), max_ibnr),
                "selected_ibnr_chart_pct": (
                    impact.get("candidate_ibnr_chart_pct")
                    if isinstance(impact, dict) and impact.get("candidate_ibnr_chart_pct") is not None
                    else _chart_percent(selected_ibnr, max_selected_ibnr)
                ),
                "selected_scenario_impact": impact,
            }
        )

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "available": bool(fit),
        "method": method,
        "display_method": display_method(method),
        "is_chain_ladder": is_chain_ladder_method(method),
        "selected_scenario_id": selected_scenario_id,
        "projection": rows,
        "source_artifacts": _available_artifacts(
            run_dir,
            ["fit.json", schemas.SCENARIO_INDEX_FILENAME, schemas.COMPARISONS_DIRNAME],
        ),
    }


def _sort_key(value: Any) -> tuple[int, Any]:
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _warning_cells(run_dir: Path) -> set[tuple[str, str]]:
    validation = io.maybe_read_json(run_dir, "validation.json") or {}
    warnings: set[tuple[str, str]] = set()
    for check in validation.get("checks", []):
        if check.get("verdict") != "warn":
            continue
        details = check.get("details")
        detail_rows = details if isinstance(details, list) else [details]
        for detail in detail_rows:
            if not isinstance(detail, dict):
                continue
            origin = detail.get("origin")
            dev = detail.get("dev") or detail.get("development")
            if origin is not None and dev is not None:
                warnings.add((str(origin), str(dev)))
    return warnings


def _committed_selection_set(run_dir: Path) -> dict[str, Any] | None:
    _scenario_id, scenario = _selected_scenario(run_dir)
    if isinstance(scenario, dict) and scenario.get("selection_set_id") and scenario.get("status") == "committed":
        return scenario
    return None


def _selection_exclusions(run_dir: Path) -> dict[str, Any]:
    selection_set = _committed_selection_set(run_dir)
    exclusions: dict[str, Any] = {"origins": [], "valuations": [], "factor_points": []}
    if not selection_set:
        return exclusions
    for exclusion in selection_set.get("exclusions", []):
        if not isinstance(exclusion, dict):
            continue
        if exclusion.get("type") == "origin":
            exclusions["origins"].append(str(exclusion.get("value")))
        if exclusion.get("type") == "valuation":
            exclusions["valuations"].append(str(exclusion.get("value")))
        if exclusion.get("type") == "factor_point":
            exclusions["factor_points"].append(
                {
                    "value": str(exclusion.get("value")),
                    "origin": str(exclusion.get("origin")),
                    "from_dev": exclusion.get("from_dev"),
                    "development_age": exclusion.get("development_age"),
                }
            )
    return exclusions


def _heat_bucket(value: Any, maximum: float | None) -> int | None:
    if not _is_number(value) or not maximum:
        return None
    ratio = abs(float(value)) / maximum
    if ratio >= 0.8:
        return 5
    if ratio >= 0.6:
        return 4
    if ratio >= 0.4:
        return 3
    if ratio >= 0.2:
        return 2
    return 1


def _link_ratio_lookup(fit: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for factor in (fit.get("development_factors", []) if fit else []):
        for ratio in factor.get("link_ratios", []) or []:
            origin = ratio.get("origin")
            from_dev = ratio.get("from_dev")
            if origin is None or from_dev is None:
                continue
            lookup[(str(origin), str(from_dev))] = {
                "value": ratio.get("link_ratio"),
                "current_value": ratio.get("current_value"),
                "next_value": ratio.get("next_value"),
                "to_dev": ratio.get("to_dev"),
                "source_artifact": "fit.json",
            }
    return lookup


def _cell_action_support(origin: str, dev: str) -> dict[str, Any]:
    return {
        "origin_exclusion": {"supported": True, "value": origin},
        "valuation_exclusion": {"supported": True, "value": dev},
        "cell_exclusion": {
            "supported": False,
            "reason": "cell-level exclusions are not supported by the deterministic CLI path yet",
        },
    }


def build_triangle_explorer(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    triangle = io.maybe_read_json(run_dir, "triangle.json")
    fit = io.maybe_read_json(run_dir, "fit.json")
    return _build_triangle_explorer(run_id, run_dir, triangle, fit)


def build_preview_triangle_explorer(
    run_id: str,
    run_dir: Path,
    candidate_triangle: dict[str, Any],
    candidate_fit: dict[str, Any],
) -> dict[str, Any]:
    """Adapt a transient deterministic rerun for the workbench triangle.

    The candidate values are built by the engine-backed preview path. This
    display adapter only annotates those returned values; it does not fit or
    calculate any actuarial output.
    """
    payload = _build_triangle_explorer(run_id, Path(run_dir), candidate_triangle, candidate_fit)
    payload["preview"] = {"kind": "transient", "source": "deterministic selection preview"}
    return payload


def _build_triangle_explorer(
    run_id: str,
    run_dir: Path,
    triangle: dict[str, Any] | None,
    fit: dict[str, Any] | None,
) -> dict[str, Any]:
    method = fit.get("method") if fit else None
    warning_cells = _warning_cells(run_dir)
    exclusions = _selection_exclusions(run_dir)
    excluded_origins = set(exclusions["origins"])
    excluded_valuations = set(exclusions["valuations"])

    source_cells = triangle.get("cells", []) if triangle else []
    origins = sorted({str(cell.get("origin")) for cell in source_cells if cell.get("origin") is not None}, key=_sort_key)
    developments = sorted(
        {str(cell.get("dev", cell.get("development"))) for cell in source_cells if cell.get("dev", cell.get("development")) is not None},
        key=_sort_key,
    )
    actual_devs_by_origin: dict[str, list[str]] = {}
    values = []
    for cell in source_cells:
        origin = str(cell.get("origin"))
        dev = str(cell.get("dev", cell.get("development")))
        cell_type = str(cell.get("type") or "actual")
        if cell_type == "actual":
            actual_devs_by_origin.setdefault(origin, []).append(dev)
        if _is_number(cell.get("value")):
            values.append(abs(float(cell["value"])))
    maximum = max(values) if values else None
    latest_by_origin = {
        origin: sorted(devs, key=_sort_key)[-1]
        for origin, devs in actual_devs_by_origin.items()
        if devs
    }
    ratio_lookup = _link_ratio_lookup(fit)
    cells = []
    for cell in source_cells:
        origin = str(cell.get("origin"))
        dev = str(cell.get("dev", cell.get("development")))
        cell_type = str(cell.get("type") or "actual")
        excluded_origin = origin in excluded_origins
        excluded_valuation = dev in excluded_valuations
        cells.append(
            {
                "origin": origin,
                "dev": dev,
                "value": cell.get("value"),
                "cell_type": cell_type,
                "is_projected": cell_type == "projected",
                "is_latest_diagonal": latest_by_origin.get(origin) == dev,
                "warning": (origin, dev) in warning_cells,
                "excluded": excluded_origin or excluded_valuation,
                "excluded_origin": excluded_origin,
                "excluded_valuation": excluded_valuation,
                "heat_bucket": _heat_bucket(cell.get("value"), maximum),
                "source_artifact": "triangle.json",
                "actions": _cell_action_support(origin, dev),
                "link_ratio": ratio_lookup.get((origin, dev)),
            }
        )

    value_by_cell = {(cell["origin"], cell["dev"]): cell.get("value") for cell in cells}
    cumulative_by_cell = {(cell["origin"], cell["dev"]): cell for cell in cells}
    incremental_values = []
    for origin in origins:
        previous_value = None
        for dev in developments:
            current_value = value_by_cell.get((origin, dev))
            incremental = None
            if _is_number(current_value):
                incremental = current_value if not _is_number(previous_value) else float(current_value) - float(previous_value)
                previous_value = current_value
            if _is_number(incremental):
                incremental_values.append(abs(float(incremental)))
    incremental_maximum = max(incremental_values) if incremental_values else None
    incremental_cells = []
    for origin in origins:
        previous_value = None
        for dev in developments:
            cumulative_cell = cumulative_by_cell.get((origin, dev))
            current_value = value_by_cell.get((origin, dev))
            incremental = None
            if _is_number(current_value):
                incremental = current_value if not _is_number(previous_value) else float(current_value) - float(previous_value)
                previous_value = current_value
            if cumulative_cell is not None:
                cumulative_cell["incremental_value"] = incremental
            incremental_cells.append(
                {
                    "origin": origin,
                    "dev": dev,
                    "value": incremental,
                    "cumulative_value": current_value,
                    "cell_type": cumulative_cell.get("cell_type") if cumulative_cell else "blank",
                    "is_projected": bool(cumulative_cell and cumulative_cell.get("is_projected")),
                    "is_latest_diagonal": bool(cumulative_cell and cumulative_cell.get("is_latest_diagonal")),
                    "warning": bool(cumulative_cell and cumulative_cell.get("warning")),
                    "excluded": bool(cumulative_cell and cumulative_cell.get("excluded")),
                    "excluded_origin": bool(cumulative_cell and cumulative_cell.get("excluded_origin")),
                    "excluded_valuation": bool(cumulative_cell and cumulative_cell.get("excluded_valuation")),
                    "heat_bucket": _heat_bucket(incremental, incremental_maximum),
                    "source_artifact": "triangle.json",
                    "derived_from": "cumulative triangle by backend display endpoint",
                    "actions": _cell_action_support(origin, dev),
                    "link_ratio": ratio_lookup.get((origin, dev)),
                }
            )

    link_ratio_rows = []
    ratio_values = []
    for factor in (fit.get("development_factors", []) if fit else []):
        for ratio in factor.get("link_ratios", []) or []:
            value = ratio.get("link_ratio")
            if _is_number(value):
                ratio_values.append(abs(float(value)))
            link_ratio_rows.append(
                {
                    "origin": str(ratio.get("origin")),
                    "from_dev": ratio.get("from_dev"),
                    "to_dev": ratio.get("to_dev"),
                    "development_age": f"{ratio.get('from_dev')} -> {ratio.get('to_dev')}",
                    "value": value,
                    "current_value": ratio.get("current_value"),
                    "next_value": ratio.get("next_value"),
                }
            )
    ratio_maximum = max(ratio_values) if ratio_values else None
    for row in link_ratio_rows:
        row["heat_bucket"] = _heat_bucket(row.get("value"), ratio_maximum)
        row["source_artifact"] = "fit.json"
        row["actions"] = _cell_action_support(str(row.get("origin")), str(row.get("from_dev")))

    link_ratio_cells = [
        {
            "origin": row.get("origin"),
            "dev": str(row.get("from_dev")),
            "to_dev": row.get("to_dev"),
            "development_age": row.get("development_age"),
            "value": row.get("value"),
            "current_value": row.get("current_value"),
            "next_value": row.get("next_value"),
            "cell_type": "link_ratio",
            "is_projected": False,
            "is_latest_diagonal": False,
            "warning": False,
            "excluded": False,
            "heat_bucket": row.get("heat_bucket"),
            "source_artifact": "fit.json",
            "actions": row.get("actions"),
        }
        for row in link_ratio_rows
    ]

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "available": bool(triangle),
        "method": method,
        "display_method": display_method(method),
        "origins": origins,
        "developments": developments,
        "cells": cells,
        "views": {
            "cumulative": {
                "label": "Cumulative",
                "cells": cells,
                "source_artifacts": _available_artifacts(run_dir, ["triangle.json", "validation.json"]),
            },
            "incremental": {
                "label": "Incremental",
                "cells": incremental_cells,
                "source_artifacts": _available_artifacts(run_dir, ["triangle.json", "validation.json"]),
                "derived_by_backend": True,
            },
            "link_ratios": {
                "label": "Link ratios",
                "cells": link_ratio_cells,
                "rows": link_ratio_rows,
                "source_artifacts": _available_artifacts(run_dir, ["fit.json"]),
            },
        },
        "incremental_cells": incremental_cells,
        "link_ratio_rows": link_ratio_rows,
        "exclusions": exclusions,
        "source_artifacts": _available_artifacts(
            run_dir,
            ["triangle.json", "fit.json", "validation.json", schemas.SELECTION_SETS_DIRNAME],
        ),
    }
