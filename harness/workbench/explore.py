"""Exploratory scenario artifacts for dashboard-v2.

Explore artifacts are deliberately not decisions. They can be updated while
their status is exploratory, and they never satisfy report-readiness gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import manifest, selection_sets

from . import io, schemas


class ExploreError(ValueError):
    """Raised when an exploratory scenario cannot be created or promoted."""


EXPLORE_PLACEHOLDER_RATIONALE = "Exploratory preview only; rationale is required when promoted to governed."
_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExploreError(message)


def _root(run_dir: Path) -> Path:
    return Path(run_dir) / schemas.EXPLORE_DIRNAME


def _scenario_root(run_dir: Path) -> Path:
    return _root(run_dir) / "scenarios"


def _comparison_root(run_dir: Path) -> Path:
    return _root(run_dir) / "comparisons"


def scenario_path(run_dir: Path, explore_scenario_id: str) -> Path:
    _require(
        bool(_ARTIFACT_ID_RE.fullmatch(str(explore_scenario_id))),
        f"invalid explore_scenario_id: {explore_scenario_id}",
    )
    return _scenario_root(run_dir) / f"{explore_scenario_id}.json"


def _source_artifacts(run_dir: Path) -> list[str]:
    return [name for name in ("fit.json", "triangle.json") if (Path(run_dir) / name).is_file()]


def _is_manual(selection: dict[str, Any]) -> bool:
    return str(selection.get("selected_basis") or selection.get("basis") or "") == "manual_override"


def _canonical_request(request: dict[str, Any]) -> dict[str, Any]:
    factors = [dict(item) for item in request.get("factor_selections", []) if isinstance(item, dict)]
    manual_overrides = [dict(item) for item in request.get("manual_overrides", []) if isinstance(item, dict)]
    for item in list(factors):
        if _is_manual(item):
            manual_overrides.append(item)
    factors = [item for item in factors if not _is_manual(item)]

    origin_exclusions = [dict(item) for item in request.get("origin_exclusions", []) if isinstance(item, dict)]
    valuation_exclusions = [dict(item) for item in request.get("valuation_exclusions", []) if isinstance(item, dict)]
    factor_point_exclusions = [dict(item) for item in request.get("factor_point_exclusions", []) if isinstance(item, dict)]
    for exclusion in request.get("exclusions", []) or []:
        if not isinstance(exclusion, dict):
            continue
        if exclusion.get("type") == "origin":
            origin_exclusions.append(dict(exclusion))
        elif exclusion.get("type") == "valuation":
            valuation_exclusions.append(dict(exclusion))
        elif exclusion.get("type") == "factor_point":
            factor_point_exclusions.append(dict(exclusion))

    return {
        "name": str(request.get("name") or "Exploratory scenario").strip() or "Exploratory scenario",
        "notes": str(request.get("notes") or request.get("global_note") or request.get("global_rationale") or "").strip(),
        "factor_selections": factors,
        "manual_overrides": manual_overrides,
        "factor_point_exclusions": factor_point_exclusions,
        "origin_exclusions": origin_exclusions,
        "valuation_exclusions": valuation_exclusions,
    }


def _with_preview_rationale(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if not str(result.get("rationale") or "").strip():
        result["rationale"] = EXPLORE_PLACEHOLDER_RATIONALE
    return result


def _selection_set_request(canonical: dict[str, Any]) -> dict[str, Any]:
    factor_selections = [
        _with_preview_rationale(item)
        for item in [*canonical.get("factor_selections", []), *canonical.get("manual_overrides", [])]
    ]
    exclusions = []
    for item in canonical.get("origin_exclusions", []):
        row = _with_preview_rationale(item)
        row["type"] = "origin"
        exclusions.append(row)
    for item in canonical.get("valuation_exclusions", []):
        row = _with_preview_rationale(item)
        row["type"] = "valuation"
        exclusions.append(row)
    for item in canonical.get("factor_point_exclusions", []):
        row = _with_preview_rationale(item)
        row["type"] = "factor_point"
        exclusions.append(row)
    return {
        "factor_selections": factor_selections,
        "exclusions": exclusions,
        "global_rationale": canonical.get("notes") or EXPLORE_PLACEHOLDER_RATIONALE,
        "created_by": {},
    }


def _preview(run_id: str, run_dir: Path, canonical: dict[str, Any]) -> dict[str, Any]:
    request = _selection_set_request(canonical)
    preview = selection_sets.build_selection_set_preview(
        run_id,
        run_dir,
        request,
        command=f"POST /api/runs/{run_id}/explore/preview",
        dry_run=True,
    )
    comparison = preview.get("comparison") or {}
    base = comparison.get("base") or {}
    candidate = comparison.get("candidate") or {}
    deltas = comparison.get("deltas") or {}
    return {
        "base_ultimate": base.get("ultimate"),
        "selected_ultimate": candidate.get("ultimate"),
        "delta_ultimate": deltas.get("ultimate"),
        "base_ibnr": base.get("ibnr"),
        "selected_ibnr": candidate.get("ibnr"),
        "delta_ibnr": deltas.get("ibnr"),
        "delta_ibnr_pct": deltas.get("ibnr_pct"),
        "by_origin_ibnr_impact": comparison.get("by_origin_ibnr_impact", []),
        "comparison": comparison,
        "candidate_fit": preview.get("candidate_fit"),
    }


def _payload(run_id: str, run_dir: Path, request: dict[str, Any], *, scenario_id: str | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    canonical = _canonical_request(request)
    source_artifacts = _source_artifacts(run_dir)
    input_hashes = io.artifact_hashes(run_dir, source_artifacts)
    stable_payload = {
        "run_id": run_id,
        "canonical": canonical,
        "input_hashes": input_hashes,
    }
    explore_scenario_id = scenario_id or str(request.get("explore_scenario_id") or "").strip() or _stable_id("explore", stable_payload)
    now = manifest.utc_now_iso()
    previous = load_explore_scenario(run_dir, explore_scenario_id)
    preview_result = _preview(run_id, run_dir, canonical)
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "mode": "explore",
        "status": "exploratory",
        "governed": False,
        "not_governed": True,
        "explore_scenario_id": explore_scenario_id,
        "run_id": run_id,
        "name": canonical["name"],
        "factor_selections": canonical["factor_selections"],
        "manual_overrides": canonical["manual_overrides"],
        "factor_point_exclusions": canonical["factor_point_exclusions"],
        "origin_exclusions": canonical["origin_exclusions"],
        "valuation_exclusions": canonical["valuation_exclusions"],
        "notes": canonical["notes"] or None,
        "preview_result": {key: value for key, value in preview_result.items() if key not in {"candidate_fit"}},
        "candidate_fit": preview_result.get("candidate_fit"),
        "source_artifacts": source_artifacts,
        "input_hashes": input_hashes,
        "created_utc": (previous or {}).get("created_utc") or now,
        "updated_utc": now,
    }


def save_explore_scenario(run_id: str, run_dir: Path, request: dict[str, Any], *, scenario_id: str | None = None) -> dict[str, Any]:
    payload = _payload(run_id, run_dir, request, scenario_id=scenario_id)
    path = scenario_path(run_dir, payload["explore_scenario_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        current = io.read_json(path)
        _require(current.get("mode") == "explore" and current.get("status") == "exploratory", "only exploratory scenarios can be updated")
    io.write_json(path, payload)
    write_explore_state(run_id, run_dir)
    return payload


def load_explore_scenario(run_dir: Path, explore_scenario_id: str) -> dict[str, Any] | None:
    path = scenario_path(run_dir, explore_scenario_id)
    return io.read_json(path) if path.is_file() else None


def list_explore_scenarios(run_id: str, run_dir: Path) -> dict[str, Any]:
    root = _scenario_root(run_dir)
    scenarios = [io.read_json(path) for path in sorted(root.glob("*.json"))] if root.is_dir() else []
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "mode": "explore",
        "run_id": run_id,
        "exploratory_scenario_count": len(scenarios),
        "scenarios": scenarios,
        "source_artifacts": [f"{schemas.EXPLORE_DIRNAME}/scenarios"] if scenarios else [],
    }


def write_explore_state(run_id: str, run_dir: Path) -> dict[str, Any]:
    scenarios = list_explore_scenarios(run_id, run_dir).get("scenarios", [])
    payload = {
        "schema_version": schemas.SCHEMA_VERSION,
        "mode": "explore",
        "run_id": run_id,
        "status": "exploratory" if scenarios else "empty",
        "exploratory_scenario_count": len(scenarios),
        "explore_scenario_ids": [scenario.get("explore_scenario_id") for scenario in scenarios],
        "updated_utc": manifest.utc_now_iso(),
        "message": "Explore freely. Promote deliberately. Only governed selections enter the report pack.",
    }
    io.write_json(_root(run_dir) / "explore_state.json", payload)
    return payload


def compare_explore_scenarios(run_id: str, run_dir: Path, left_id: str, right_id: str) -> dict[str, Any]:
    left = load_explore_scenario(run_dir, left_id)
    right = load_explore_scenario(run_dir, right_id)
    _require(left is not None, f"explore_scenario_id not found: {left_id}")
    _require(right is not None, f"explore_scenario_id not found: {right_id}")
    left_preview = left.get("preview_result") or {}
    right_preview = right.get("preview_result") or {}
    deltas = {}
    for key in ("selected_ultimate", "selected_ibnr", "delta_ultimate", "delta_ibnr"):
        lvalue = left_preview.get(key)
        rvalue = right_preview.get(key)
        deltas[key] = rvalue - lvalue if isinstance(lvalue, (int, float)) and isinstance(rvalue, (int, float)) else None
    comparison_id = _stable_id("explore_comparison", {"run_id": run_id, "left": left_id, "right": right_id, "deltas": deltas})
    payload = {
        "schema_version": schemas.SCHEMA_VERSION,
        "mode": "explore",
        "comparison_id": comparison_id,
        "run_id": run_id,
        "left_explore_scenario_id": left_id,
        "right_explore_scenario_id": right_id,
        "deltas": deltas,
        "generated_utc": manifest.utc_now_iso(),
    }
    path = _comparison_root(run_dir) / f"{comparison_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    io.write_json(path, payload)
    return payload


def _scenario_to_governed_request(scenario: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    global_rationale = str(payload.get("global_rationale") or scenario.get("notes") or "").strip()
    factor_rationales = {str(k): v for k, v in (payload.get("factor_rationales") or {}).items()}
    exclusion_rationales = {str(k): v for k, v in (payload.get("exclusion_rationales") or {}).items()}

    factor_selections = []
    for factor in [*scenario.get("factor_selections", []), *scenario.get("manual_overrides", [])]:
        row = dict(factor)
        key = str(row.get("from_dev") or row.get("development_age") or "")
        row["rationale"] = str(row.get("rationale") or factor_rationales.get(key) or global_rationale).strip()
        factor_selections.append(row)

    exclusions = []
    for collection, exclusion_type in (
        ("origin_exclusions", "origin"),
        ("valuation_exclusions", "valuation"),
        ("factor_point_exclusions", "factor_point"),
    ):
        for exclusion in scenario.get(collection, []):
            row = dict(exclusion)
            row["type"] = exclusion_type
            key = str(row.get("value") or row.get("origin") or "")
            row["rationale"] = str(row.get("rationale") or exclusion_rationales.get(key) or global_rationale).strip()
            exclusions.append(row)

    return {
        "factor_selections": factor_selections,
        "exclusions": exclusions,
        "global_rationale": global_rationale,
        "created_by": payload.get("created_by") or {},
        "source_explore_scenario_id": scenario.get("explore_scenario_id"),
    }


def promote_explore_scenario(run_id: str, run_dir: Path, explore_scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from . import decisions, tasks

    scenario = load_explore_scenario(run_dir, explore_scenario_id)
    _require(scenario is not None, f"explore_scenario_id not found: {explore_scenario_id}")
    _require(scenario.get("mode") == "explore", "only explore scenarios can be promoted")
    current_hashes = io.artifact_hashes(run_dir, scenario.get("source_artifacts", []))
    _require(current_hashes == scenario.get("input_hashes", {}), "source artifacts changed; preview the exploratory scenario again before promotion")

    request = _scenario_to_governed_request(scenario, payload)
    created_by = request.get("created_by") or {}
    _require(bool(str(created_by.get("id") or "").strip()), "promotion requires user id")
    _require(bool(str(created_by.get("display_name") or "").strip()), "promotion requires user display_name")
    _require(bool(str(request.get("global_rationale") or "").strip()), "promotion requires global_rationale")
    for factor in request["factor_selections"]:
        _require(bool(str(factor.get("rationale") or "").strip()), "promotion requires rationale for every selected factor")
    for exclusion in request["exclusions"]:
        _require(bool(str(exclusion.get("rationale") or "").strip()), "promotion requires rationale for every exclusion")

    preview = selection_sets.build_selection_set_preview(run_id, run_dir, request)
    committed = selection_sets.commit_selection_set(
        run_id,
        run_dir,
        preview["selection_set_id"],
        {"global_rationale": request["global_rationale"], "created_by": created_by},
    )
    reviewed = list(dict.fromkeys([*(committed.get("source_artifacts") or []), committed["selection_set_artifact"]]))
    decision_payload = {
        "schema_version": schemas.SCHEMA_VERSION,
        "decision_id": str(payload.get("decision_id") or f"selection_set_approval_{_stable_id('explore', {'id': explore_scenario_id})}"),
        "run_id": run_id,
        "task_id": payload.get("task_id"),
        "decision_type": "selection_set_approval",
        "status": "accepted",
        "selection_set_id": committed["selection_set_id"],
        "resulting_scenario_id": committed["preview_scenario_id"],
        "base_run_id": run_id,
        "rationale": request["global_rationale"],
        "user": created_by,
        "source_artifacts_reviewed": reviewed,
        "factor_selections": committed.get("factor_selections", []),
        "manual_overrides": committed.get("manual_overrides", []),
        "exclusions": committed.get("exclusions", []),
        "factor_point_exclusions": committed.get("factor_point_exclusions", []),
        "selection_set_artifact": committed.get("selection_set_artifact"),
        "source_explore_scenario_id": explore_scenario_id,
        "commands_or_parameters_affected": [],
        "supersedes_decision_id": payload.get("supersedes_decision_id"),
    }
    decision = decisions.commit_decision_payload(run_id, run_dir, decision_payload)
    tasks.write_validation_tasks(run_id, run_dir)
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "mode": "governed",
        "source_explore_scenario_id": explore_scenario_id,
        "selection_set": committed,
        "decision": decision,
    }
