"""Validation task generation for the workbench.

Tasks are deterministic projections of run artifacts plus immutable
decisions. Regenerating validation_tasks.json is allowed; decision files are
the durable source of completed human judgment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import chain_ladder, io, schemas


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:12]}"


def _completion_for(task_id: str, decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = io.completing_decisions_by_task(decisions)
    return completed.get(task_id)


def _with_completion(task: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    completion = _completion_for(task["task_id"], decisions)
    if completion is None:
        return task
    updated = dict(task)
    updated["status"] = "completed"
    updated["completed_by_decision_id"] = completion["decision_id"]
    return updated


def _validation_warning_tasks(run_dir: Path, created_utc: str, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validation = io.maybe_read_json(run_dir, "validation.json")
    if not validation:
        return []

    tasks = []
    for i, check in enumerate(validation.get("checks", [])):
        if check.get("verdict") != "warn":
            continue
        evidence = {
            "artifact": "validation.json",
            "index": i,
            "check_id": check.get("check_id"),
            "details": check.get("details"),
        }
        task = {
            "task_id": _stable_id("warning_validation", evidence),
            "task_type": "warning_review",
            "status": "pending",
            "severity": "warning",
            "title": f"Review validation warning: {check.get('check_id')}",
            "description": (
                "A warn-class validation check was emitted. Confirm the warning "
                "has been reviewed before the run is treated as ready for report approval."
            ),
            "source_artifacts": ["validation.json"],
            "evidence_refs": [
                {"artifact": "validation.json", "path": f"$.checks[{i}].verdict"},
                {"artifact": "validation.json", "path": f"$.checks[{i}].details"},
            ],
            "allowed_decision_types": ["warning_ack"],
            "created_utc": created_utc,
            "completed_by_decision_id": None,
        }
        tasks.append(_with_completion(task, decisions))
    return tasks


def _diagnostics_warning_tasks(run_dir: Path, created_utc: str, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics = io.maybe_read_json(run_dir, "diagnostics.json")
    if not diagnostics:
        return []

    tasks = []
    for i, test in enumerate(diagnostics.get("tests", [])):
        if test.get("verdict") != "warn":
            continue
        evidence = {
            "artifact": "diagnostics.json",
            "index": i,
            "test_id": test.get("test_id"),
            "narrative_key": test.get("narrative_key"),
        }
        task = {
            "task_id": _stable_id("warning_diagnostics", evidence),
            "task_type": "warning_review",
            "status": "pending",
            "severity": "warning",
            "title": f"Review diagnostics warning: {test.get('test_id')}",
            "description": (
                "A diagnostics screen emitted a warning. The actuary must review "
                "the statistic, fixed narration, and prescribed actions."
            ),
            "source_artifacts": ["diagnostics.json"],
            "evidence_refs": [
                {"artifact": "diagnostics.json", "path": f"$.tests[{i}].verdict"},
                {"artifact": "diagnostics.json", "path": f"$.tests[{i}].statistic"},
                {"artifact": "diagnostics.json", "path": f"$.tests[{i}].prescribed_actions"},
            ],
            "allowed_decision_types": ["warning_ack"],
            "created_utc": created_utc,
            "completed_by_decision_id": None,
        }
        tasks.append(_with_completion(task, decisions))
    return tasks


def _scenario_selection_task(run_dir: Path, created_utc: str, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sensitivity = io.maybe_read_json(run_dir, "sensitivity.json")
    if not sensitivity:
        return []
    has_scenario_index = (Path(run_dir) / schemas.SCENARIO_INDEX_FILENAME).is_file()

    evidence = {
        "artifact": "sensitivity.json",
        "scenario_count": len(sensitivity.get("scenarios", [])),
        "base_parameters": sensitivity.get("base_parameters"),
    }
    task = {
        "task_id": _stable_id("scenario_selection", evidence),
        "task_type": "scenario_selection",
        "status": "pending",
        "severity": "info",
        "title": "Select scenario treatment for report",
        "description": (
            "Sensitivity results are available. Confirm whether the base scenario "
            "remains the report basis or whether a sensitivity scenario should be referenced."
        ),
        "source_artifacts": [
            name
            for name in ("fit.json", "sensitivity.json", schemas.SCENARIO_INDEX_FILENAME)
            if name != schemas.SCENARIO_INDEX_FILENAME or has_scenario_index
        ],
        "evidence_refs": [
            {"artifact": "sensitivity.json", "path": "$.base_parameters"},
            {"artifact": "sensitivity.json", "path": "$.scenarios"},
            {"artifact": "sensitivity.json", "path": "$.range"},
        ],
        "allowed_decision_types": ["scenario_selection"],
        "created_utc": created_utc,
        "completed_by_decision_id": None,
    }
    return [_with_completion(task, decisions)]


def _bcl_review_task(run_dir: Path, created_utc: str, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fit = io.maybe_read_json(run_dir, "fit.json")
    if not fit or not chain_ladder.is_chain_ladder_method(fit.get("method")):
        return []

    has_scenario_index = (Path(run_dir) / schemas.SCENARIO_INDEX_FILENAME).is_file()
    source_artifacts = [
        name
        for name in (
            "manifest.json",
            "fit.json",
            "triangle.json",
            schemas.FACTOR_ANALYSIS_FILENAME,
            schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
            schemas.SCENARIO_INDEX_FILENAME,
        )
        if name != schemas.SCENARIO_INDEX_FILENAME or has_scenario_index
    ]
    source_artifacts = [name for name in source_artifacts if (Path(run_dir) / name).is_file()]
    evidence = {
        "artifact": "fit.json",
        "method": fit.get("method"),
        "totals": fit.get("totals"),
        "development_factor_count": len(fit.get("development_factors", [])),
        "by_origin_count": len(fit.get("by_origin", [])),
    }
    task = {
        "task_id": _stable_id("bcl_review", evidence),
        "task_type": "bcl_review",
        "status": "pending",
        "severity": "info",
        "title": "Review deterministic chain ladder selections",
        "description": (
            "The actuary reviewed the deterministic chain ladder output and "
            "approves continuing to report generation or scenario comparison. "
            "This does not approve individual manual selected-factor overrides."
        ),
        "source_artifacts": source_artifacts,
        "evidence_refs": [
            {"artifact": "fit.json", "path": "$.method"},
            {"artifact": "fit.json", "path": "$.totals"},
            {"artifact": "fit.json", "path": "$.development_factors"},
            {"artifact": "fit.json", "path": "$.by_origin"},
            {"artifact": "triangle.json", "path": "$.cells"},
        ],
        "allowed_decision_types": ["method_review_ack"],
        "created_utc": created_utc,
        "completed_by_decision_id": None,
    }
    if has_scenario_index:
        task["evidence_refs"].append({"artifact": schemas.SCENARIO_INDEX_FILENAME, "path": "$.scenarios"})
    if (Path(run_dir) / schemas.FACTOR_ANALYSIS_FILENAME).is_file():
        task["evidence_refs"].append(
            {"artifact": schemas.FACTOR_ANALYSIS_FILENAME, "path": "$.influence_ranking"}
        )
    if (Path(run_dir) / schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME).is_file():
        task["evidence_refs"].append(
            {"artifact": schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME, "path": "$.suggestions"}
        )
    return [_with_completion(task, decisions)]


def _current_report_approval(run_id: str, run_dir: Path, decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    from . import review_snapshots

    approvals = [
        decision
        for decision in io.active_decisions(decisions)
        if decision.get("decision_type") == "report_approval"
        and decision.get("status") in {"accepted", "modified"}
    ]
    if len(approvals) != 1:
        return None
    snapshot_id = str(approvals[0].get("review_snapshot_id") or "").strip()
    if not snapshot_id:
        return None
    try:
        snapshot = review_snapshots.load_review_snapshot(run_dir, snapshot_id)
        if snapshot is None:
            return None
        review_snapshots.validate_review_snapshot(run_id, run_dir, snapshot)
    except review_snapshots.ReviewSnapshotError:
        return None
    return approvals[0]


def _report_approval_task(
    run_id: str,
    run_dir: Path,
    created_utc: str,
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if _current_report_approval(run_id, run_dir, decisions):
        return []
    if not (Path(run_dir) / "fit.json").is_file():
        return []
    if not (Path(run_dir) / "diagnostics.json").is_file():
        # Diagnostics are part of the controlled review workflow; do not
        # fabricate readiness for report approval when they have not run.
        return []

    from . import review_snapshots

    current_snapshot = review_snapshots.build_review_snapshot(run_id, run_dir)
    evidence = {
        "artifact": "manifest.json",
        "approval": "report",
        "review_snapshot_id": current_snapshot["review_snapshot_id"],
    }
    task = {
        "task_id": _stable_id("report_approval", evidence),
        "task_type": "report_approval",
        "status": "pending",
        "severity": "info",
        "title": "Approve review pack generation",
        "description": (
            "All prerequisite workbench tasks are resolved. Approve generation "
            "or regeneration of the deterministic review pack."
        ),
        "source_artifacts": [
            name
            for name in ("manifest.json", "validation.json", "fit.json", "diagnostics.json", "sensitivity.json")
            if (Path(run_dir) / name).is_file()
        ],
        "evidence_refs": [
            {"artifact": "manifest.json", "path": "$.outputs"},
            {"artifact": "fit.json", "path": "$.totals"},
        ],
        "allowed_decision_types": ["report_approval"],
        "created_utc": created_utc,
        "completed_by_decision_id": None,
    }
    return [_with_completion(task, decisions)]


def _queue_status(run_id: str, run_dir: Path, tasks: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> str:
    if _current_report_approval(run_id, run_dir, decisions):
        return "signed_off"
    if any(t["status"] == "pending" for t in tasks):
        return "needs_judgment"
    if not (Path(run_dir) / "manifest.json").is_file() or not (Path(run_dir) / "fit.json").is_file():
        return "incomplete"
    if not (Path(run_dir) / "diagnostics.json").is_file():
        return "ready"
    return "report_ready"


def build_prerequisite_tasks(
    run_id: str,
    run_dir: Path,
    decisions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    run_dir = Path(run_dir)
    decisions = decisions if decisions is not None else io.load_decisions(run_dir)
    created_utc = io.run_created_utc(run_id, run_dir)
    tasks: list[dict[str, Any]] = []
    tasks.extend(_validation_warning_tasks(run_dir, created_utc, decisions))
    tasks.extend(_diagnostics_warning_tasks(run_dir, created_utc, decisions))
    tasks.extend(_scenario_selection_task(run_dir, created_utc, decisions))
    tasks.extend(_bcl_review_task(run_dir, created_utc, decisions))
    return tasks


def build_validation_tasks(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    decisions = io.load_decisions(run_dir)
    created_utc = io.run_created_utc(run_id, run_dir)
    tasks = build_prerequisite_tasks(run_id, run_dir, decisions)

    prerequisite_pending = any(
        t["status"] == "pending" and t["task_type"] in {"warning_review", "scenario_selection", "bcl_review"}
        for t in tasks
    )
    if not prerequisite_pending:
        tasks.extend(_report_approval_task(run_id, run_dir, created_utc, decisions))

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "status": _queue_status(run_id, run_dir, tasks, decisions),
        "tasks": tasks,
    }


def write_validation_tasks(run_id: str, run_dir: Path) -> dict[str, Any]:
    payload = build_validation_tasks(run_id, run_dir)
    io.write_json(Path(run_dir) / schemas.TASKS_FILENAME, payload)
    return payload
