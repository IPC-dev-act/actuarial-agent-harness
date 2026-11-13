"""Derived run status for the workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import io
from .tasks import build_validation_tasks


def _missing_required_for_workflow(artifacts: dict[str, bool]) -> list[str]:
    missing = []
    for name in ("manifest.json", "fit.json", "triangle.json"):
        if not artifacts.get(name):
            missing.append(name)
    # Diagnostics are required before report approval in the controlled
    # review workflow, but a just-fit run can still be "ready" for the next
    # CLI step rather than broken.
    if artifacts.get("fit.json") and not artifacts.get("diagnostics.json"):
        missing.append("diagnostics.json")
    return missing


def derive_status(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    artifacts = io.artifact_availability(run_dir)
    decisions = io.load_decisions(run_dir)
    task_payload = build_validation_tasks(run_id, run_dir)
    tasks = task_payload["tasks"]

    unresolved = [t for t in tasks if t.get("status") == "pending"]
    completed_decisions = [
        d for d in decisions if d.get("status") in {"accepted", "modified"}
    ]

    return {
        "run_id": run_id,
        "status": task_payload["status"],
        "artifacts": artifacts,
        "missing_required_artifacts": _missing_required_for_workflow(artifacts),
        "task_count": len(tasks),
        "unresolved_task_count": len(unresolved),
        "completed_decision_count": len(completed_decisions),
        "decision_count": len(decisions),
        "validation_tasks_path": str(run_dir / "validation_tasks.json"),
    }
