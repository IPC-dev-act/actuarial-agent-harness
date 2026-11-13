"""Structured AI-to-actuary handoff and deterministic resume guidance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness import manifest

from . import chain_ladder, dashboard, io, schemas, state, tasks


def build_review_handoff(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    task_payload = tasks.build_validation_tasks(run_id, run_dir)
    readiness = dashboard.build_report_readiness(run_id, run_dir)
    run_status = state.derive_status(run_id, run_dir)
    fit = io.maybe_read_json(run_dir, "fit.json") or {}
    pending = [task for task in task_payload.get("tasks", []) if task.get("status") == "pending"]

    next_ai_commands = []
    if fit and not (run_dir / "diagnostics.json").is_file():
        next_ai_commands.append(f"reserve diagnostics {run_id} --format json --out runs")
    if (
        chain_ladder.is_chain_ladder_method(fit.get("method"))
        and not (run_dir / schemas.FACTOR_ANALYSIS_FILENAME).is_file()
    ):
        next_ai_commands.append(f"reserve factor-analysis {run_id} --format json --out runs")
    if (run_dir / "sensitivity.json").is_file() and not (run_dir / schemas.SCENARIO_INDEX_FILENAME).is_file():
        next_ai_commands.append(f"reserve scenarios {run_id} --format json --out runs")
    if readiness.get("require_approval_would_pass") and not (run_dir / "report.html").is_file():
        next_ai_commands.append(readiness.get("report_command"))

    if readiness.get("status") == "generated" and not pending:
        phase = "complete"
    elif next_ai_commands and not pending:
        phase = "ready_for_ai_resume"
    else:
        phase = "awaiting_human_judgment"

    source_artifacts = [
        name
        for name in (
            "validation.json",
            "fit.json",
            "triangle.json",
            "diagnostics.json",
            "sensitivity.json",
            schemas.TASKS_FILENAME,
            schemas.SCENARIO_INDEX_FILENAME,
            schemas.FACTOR_ANALYSIS_FILENAME,
            schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
        )
        if (run_dir / name).is_file()
    ]
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "generated_utc": manifest.utc_now_iso(),
        "phase": phase,
        "method": fit.get("method"),
        "display_method": chain_ladder.display_method(fit.get("method")),
        "run_status": run_status.get("status"),
        "report_readiness": readiness.get("status"),
        "pending_judgment": [
            {
                "task_id": task.get("task_id"),
                "task_type": task.get("task_type"),
                "title": task.get("title"),
                "severity": task.get("severity"),
                "allowed_decision_types": task.get("allowed_decision_types", []),
                "source_artifacts": task.get("source_artifacts", []),
            }
            for task in pending
        ],
        "next_action": readiness.get("next_action"),
        "reporting_basis": {
            "selection_set_id": readiness.get("selection_set_id"),
            "selected_scenario_id": readiness.get("selected_scenario_id"),
            "report_approval_decision_id": readiness.get("report_approval_decision_id"),
            "review_snapshot_id": readiness.get("review_snapshot_id"),
        },
        "next_ai_commands": [command for command in next_ai_commands if command],
        "resume_command": f"/review {run_id}",
        "dashboard_path": "/workbench-v2/",
        "source_artifacts": source_artifacts,
        "input_hashes": io.artifact_hashes(run_dir, source_artifacts),
    }


def write_review_handoff(run_id: str, run_dir: Path) -> dict[str, Any]:
    payload = build_review_handoff(run_id, run_dir)
    io.write_json(Path(run_dir) / schemas.HANDOFF_FILENAME, payload)
    return payload
