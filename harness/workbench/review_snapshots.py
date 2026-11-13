"""Immutable reporting-basis snapshots for governed report approval."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from harness import manifest, selection_sets

from . import io, schemas

_SNAPSHOT_ID_RE = re.compile(r"^review_snapshot_[0-9a-f]{16}$")
_MATERIAL_ARTIFACTS = (
    "validation.json",
    "fit.json",
    "triangle.json",
    "diagnostics.json",
    "sensitivity.json",
    schemas.SCENARIO_INDEX_FILENAME,
    schemas.FACTOR_ANALYSIS_FILENAME,
    schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
)


class ReviewSnapshotError(ValueError):
    """Raised when a reporting-basis snapshot is missing, stale, or ambiguous."""


def snapshot_artifact(snapshot_id: str) -> str:
    if not _SNAPSHOT_ID_RE.fullmatch(str(snapshot_id)):
        raise ReviewSnapshotError(f"invalid review_snapshot_id: {snapshot_id}")
    return f"{schemas.REVIEW_SNAPSHOTS_DIRNAME}/{snapshot_id}.json"


def snapshot_path(run_dir: Path, snapshot_id: str) -> Path:
    return Path(run_dir) / snapshot_artifact(snapshot_id)


def load_review_snapshot(run_dir: Path, snapshot_id: str) -> dict[str, Any] | None:
    path = snapshot_path(run_dir, snapshot_id)
    return io.read_json(path) if path.is_file() else None


def _stable_id(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"review_snapshot_{hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]}"


def _active_governed_decisions(run_dir: Path) -> list[dict[str, Any]]:
    return sorted(
        [
            decision
            for decision in io.active_decisions(io.load_decisions(run_dir))
            if decision.get("decision_type") != "report_approval"
        ],
        key=lambda decision: str(decision.get("decision_id") or ""),
    )


def _approved_selection_ids(run_dir: Path) -> set[str]:
    return {
        str(decision.get("selection_set_id"))
        for decision in io.load_decisions(run_dir)
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
        and decision.get("selection_set_id")
    }


def _renderer_hashes() -> dict[str, str]:
    from harness.render import report_html

    renderer_path = Path(report_html.__file__).resolve()
    return {
        "harness/render/report_html.py": manifest.sha256_file(renderer_path),
        "harness/render/templates/report.html": manifest.sha256_file(report_html.TEMPLATE_PATH),
    }


def _snapshot_basis(run_id: str, run_dir: Path) -> dict[str, Any]:
    # Local import avoids a module cycle: tasks project decisions, while
    # report approval validation creates this snapshot.
    from .tasks import build_prerequisite_tasks

    run_dir = Path(run_dir)
    active_decisions = _active_governed_decisions(run_dir)
    active_selection_approvals = [
        decision
        for decision in active_decisions
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
    ]
    committed_selection_sets = [
        item
        for item in selection_sets.list_selection_sets(run_dir)
        if item.get("status") == "committed" and item.get("selection_set_id")
    ]
    approved_ids = _approved_selection_ids(run_dir)
    unapproved_ids = sorted(
        str(item["selection_set_id"])
        for item in committed_selection_sets
        if str(item["selection_set_id"]) not in approved_ids
    )

    selection_approval = active_selection_approvals[0] if len(active_selection_approvals) == 1 else None
    selection_set_id = str(selection_approval.get("selection_set_id")) if selection_approval else None
    selection_artifact = None
    if selection_set_id:
        selected = selection_sets.load_selection_set(run_dir, selection_set_id)
        if selected is not None:
            selection_artifact = selected.get("selection_set_artifact") or selection_sets.selection_set_artifact(
                selection_set_id
            )

    material_artifacts = [name for name in _MATERIAL_ARTIFACTS if (run_dir / name).is_file()]
    if selection_artifact:
        material_artifacts.append(str(selection_artifact))
    decision_artifacts = [
        f"{schemas.DECISIONS_DIRNAME}/{decision['decision_id']}.json"
        for decision in active_decisions
    ]
    tasks = build_prerequisite_tasks(run_id, run_dir, io.load_decisions(run_dir))
    prerequisite_tasks = [
        task
        for task in tasks
        if task.get("status") == "pending"
        and task.get("task_type") in {"warning_review", "scenario_selection", "bcl_review"}
    ]

    selected_scenario_id = None
    if selection_approval:
        selected_scenario_id = selection_approval.get("resulting_scenario_id")
    else:
        scenario_decisions = [
            decision
            for decision in active_decisions
            if decision.get("decision_type") in {"scenario_selection", "factor_selection"}
            and decision.get("status") in {"accepted", "modified"}
            and decision.get("resulting_scenario_id")
        ]
        if len(scenario_decisions) == 1:
            selected_scenario_id = scenario_decisions[0].get("resulting_scenario_id")

    return {
        "run_id": run_id,
        "material_artifacts": material_artifacts,
        "input_hashes": io.artifact_hashes(run_dir, material_artifacts),
        "active_decision_ids": [str(decision["decision_id"]) for decision in active_decisions],
        "decision_hashes": io.artifact_hashes(run_dir, decision_artifacts),
        "reporting_basis": {
            "selection_set_id": selection_set_id,
            "selection_approval_decision_id": (
                selection_approval.get("decision_id") if selection_approval else None
            ),
            "selected_scenario_id": selected_scenario_id,
        },
        "active_selection_approval_count": len(active_selection_approvals),
        "unapproved_selection_set_ids": unapproved_ids,
        "pending_prerequisite_task_ids": sorted(str(task["task_id"]) for task in prerequisite_tasks),
        "renderer_hashes": _renderer_hashes(),
    }


def build_review_snapshot(run_id: str, run_dir: Path) -> dict[str, Any]:
    basis = _snapshot_basis(run_id, run_dir)
    ready = (
        not basis["pending_prerequisite_task_ids"]
        and basis["active_selection_approval_count"] <= 1
        and not basis["unapproved_selection_set_ids"]
    )
    snapshot_id = _stable_id(basis)
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "review_snapshot_id": snapshot_id,
        "status": "ready" if ready else "blocked",
        "generated_utc": manifest.utc_now_iso(),
        **basis,
    }


def create_review_snapshot(run_id: str, run_dir: Path) -> dict[str, Any]:
    snapshot = build_review_snapshot(run_id, run_dir)
    path = snapshot_path(run_dir, snapshot["review_snapshot_id"])
    if path.is_file():
        existing = io.read_json(path)
        if _basis_from_snapshot(existing) != _basis_from_snapshot(snapshot):
            raise ReviewSnapshotError(f"review snapshot id collision: {snapshot['review_snapshot_id']}")
        return existing
    try:
        io.write_json(path, snapshot, exclusive=True)
    except FileExistsError:
        existing = io.read_json(path)
        if _basis_from_snapshot(existing) != _basis_from_snapshot(snapshot):
            raise ReviewSnapshotError(f"review snapshot id collision: {snapshot['review_snapshot_id']}")
        return existing
    return snapshot


def _basis_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"schema_version", "review_snapshot_id", "status", "generated_utc"}
    }


def validate_review_snapshot(run_id: str, run_dir: Path, snapshot: dict[str, Any]) -> None:
    if snapshot.get("run_id") != run_id:
        raise ReviewSnapshotError("review snapshot run_id does not match target run")
    if snapshot.get("status") != "ready":
        raise ReviewSnapshotError("review snapshot is blocked and cannot be approved")
    current = build_review_snapshot(run_id, run_dir)
    if snapshot.get("review_snapshot_id") != current.get("review_snapshot_id"):
        raise ReviewSnapshotError("review snapshot is stale against the current reporting basis")
    if _basis_from_snapshot(snapshot) != _basis_from_snapshot(current):
        raise ReviewSnapshotError("review snapshot contents do not match the current reporting basis")
