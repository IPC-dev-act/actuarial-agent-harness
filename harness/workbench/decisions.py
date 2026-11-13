"""Decision artifact validation and immutable writes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness import manifest

from . import io, schemas, scenarios
from .tasks import build_validation_tasks

_DECISION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class DecisionValidationError(ValueError):
    """Raised when a decision artifact cannot be accepted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DecisionValidationError(message)


def _task_by_id(task_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {task["task_id"]: task for task in task_payload.get("tasks", [])}


def _validate_user(decision: dict[str, Any]) -> None:
    user = decision.get("user")
    _require(isinstance(user, dict), "decision.user is required")
    _require(bool(str(user.get("id", "")).strip()), "decision.user.id is required")
    _require(
        bool(str(user.get("display_name", "")).strip()),
        "decision.user.display_name is required",
    )


def _validate_reviewed_artifacts(decision: dict[str, Any]) -> None:
    reviewed = decision["source_artifacts_reviewed"]
    _require(isinstance(reviewed, list), "source_artifacts_reviewed must be a list")
    for name in reviewed:
        _require(isinstance(name, str), "source_artifacts_reviewed entries must be strings")
        path = Path(name)
        _require(
            name
            and not path.is_absolute()
            and ".." not in path.parts,
            f"source_artifacts_reviewed contains an unsafe run-relative path: {name}",
        )


def _validate_task_reference(
    *,
    decision: dict[str, Any],
    run_dir: Path,
    task_payload: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    decision_type = decision["decision_type"]
    task_id = decision.get("task_id")
    tasks = _task_by_id(task_payload)

    if not task_id:
        _require(
            decision_type in {"factor_selection", "selection_set_approval", "report_approval"},
            "decision.task_id is required unless decision_type is factor_selection, selection_set_approval, or report_approval",
        )
        if decision_type in {"factor_selection", "selection_set_approval"}:
            return None
        pending_prerequisites = [
            t
            for t in task_payload.get("tasks", [])
            if t.get("status") == "pending"
            and t.get("task_type") in {"warning_review", "scenario_selection", "bcl_review"}
        ]
        _require(
            not pending_prerequisites,
            "standalone report_approval is not allowed while prerequisite tasks are pending",
        )
        _require(
            (Path(run_dir) / "diagnostics.json").is_file(),
            "standalone report_approval requires diagnostics.json",
        )
        return None

    _require(task_id in tasks, f"decision.task_id does not exist for this run: {task_id}")
    task = tasks[task_id]
    _require(
        decision_type in task.get("allowed_decision_types", []),
        f"decision_type {decision_type!r} is not allowed for task {task_id}",
    )

    completed = io.completing_decisions_by_task(decisions)
    previous = completed.get(task_id)
    if previous is not None:
        _require(
            decision.get("supersedes_decision_id") == previous.get("decision_id"),
            "task already has a completing decision; a new decision must supersede it",
        )
    return task


def _validate_scenario_selection(decision: dict[str, Any], run_dir: Path) -> None:
    if decision["decision_type"] != "scenario_selection":
        return
    if decision["status"] not in {"accepted", "modified"}:
        return

    scenario_id = decision.get("resulting_scenario_id")
    _require(
        bool(str(scenario_id or "").strip()),
        "scenario_selection requires resulting_scenario_id",
    )
    index = scenarios.load_scenario_index(run_dir)
    _require(
        index is not None,
        "scenario_selection requires scenario_index.json; run reserve scenarios first",
    )
    scenario = scenarios.scenario_by_id(index, str(scenario_id))
    _require(
        scenario is not None,
        f"resulting_scenario_id does not exist in scenario_index.json: {scenario_id}",
    )
    _require(
        scenario.get("status") == "available",
        f"resulting_scenario_id is not available: {scenario_id}",
    )
    _require(
        schemas.SCENARIO_INDEX_FILENAME in decision.get("source_artifacts_reviewed", []),
        "scenario_selection source_artifacts_reviewed must include scenario_index.json",
    )
    source_artifacts = scenario.get("source_artifacts", [])
    missing = [name for name in source_artifacts if not (Path(run_dir) / name).is_file()]
    _require(
        not missing,
        f"scenario_index entry references missing source artifacts: {', '.join(missing)}",
    )
    current_hashes = io.artifact_hashes(run_dir, source_artifacts)
    _require(
        current_hashes == scenario.get("input_hashes", {}),
        "scenario_index entry is stale; run reserve scenarios first",
    )


def _validate_factor_selection(decision: dict[str, Any], run_dir: Path) -> None:
    if decision["decision_type"] != "factor_selection":
        return
    if decision["status"] not in {"accepted", "modified"}:
        return
    from harness import factor_selection

    scenario_id = str(decision.get("resulting_scenario_id") or "").strip()
    _require(bool(scenario_id), "factor_selection requires resulting_scenario_id")
    preview = factor_selection.load_preview(run_dir, scenario_id)
    _require(
        preview is not None,
        f"resulting_scenario_id does not exist in factor preview artifacts: {scenario_id}",
    )
    _require(preview.get("status") == "available", f"factor preview is not available: {scenario_id}")

    preview_artifact = preview.get("preview_artifact") or f"{schemas.FACTOR_PREVIEWS_DIRNAME}/{scenario_id}.json"
    _require(
        preview_artifact in decision.get("source_artifacts_reviewed", []),
        f"factor_selection source_artifacts_reviewed must include {preview_artifact}",
    )

    selection = preview.get("selection") or {}
    required_matches = {
        "development_age": str(selection.get("development_age")),
        "selected_basis": selection.get("selected_basis"),
    }
    for field, expected in required_matches.items():
        _require(
            str(decision.get(field)) == str(expected),
            f"factor_selection {field} does not match preview scenario",
        )
    for field, preview_field in (
        ("previous_factor", "previous_factor"),
        ("selected_factor", "selected_factor"),
    ):
        actual = decision.get(field)
        expected = selection.get(preview_field)
        _require(
            isinstance(actual, (int, float)) and isinstance(expected, (int, float)),
            f"factor_selection {field} must be numeric",
        )
        _require(
            abs(float(actual) - float(expected)) <= max(1e-10, abs(float(expected)) * 1e-10),
            f"factor_selection {field} does not match preview scenario",
        )

    source_artifacts = preview.get("source_artifacts", [])
    current_hashes = io.artifact_hashes(run_dir, source_artifacts)
    _require(
        current_hashes == preview.get("input_hashes", {}),
        "factor preview is stale; request a new preview before committing",
    )


def _validate_selection_set_approval(decision: dict[str, Any], run_dir: Path) -> None:
    if decision["decision_type"] != "selection_set_approval":
        return
    if decision["status"] not in {"accepted", "modified"}:
        return
    from harness import selection_sets

    selection_set_id = str(decision.get("selection_set_id") or "").strip()
    scenario_id = str(decision.get("resulting_scenario_id") or "").strip()
    _require(bool(selection_set_id), "selection_set_approval requires selection_set_id")
    _require(bool(scenario_id), "selection_set_approval requires resulting_scenario_id")
    selection_set = selection_sets.load_selection_set(run_dir, selection_set_id)
    _require(selection_set is not None, f"selection_set_id does not exist: {selection_set_id}")
    _require(selection_set.get("status") == "committed", f"selection_set_id is not committed: {selection_set_id}")
    _require(
        scenario_id == selection_set.get("preview_scenario_id"),
        "selection_set_approval resulting_scenario_id does not match selection set preview_scenario_id",
    )
    artifact = selection_set.get("selection_set_artifact") or selection_sets.selection_set_artifact(selection_set_id)
    _require(
        artifact in decision.get("source_artifacts_reviewed", []),
        f"selection_set_approval source_artifacts_reviewed must include {artifact}",
    )
    current_hashes = io.artifact_hashes(run_dir, selection_set.get("source_artifacts", []))
    _require(
        current_hashes == selection_set.get("input_hashes", {}),
        "selection set is stale; preview and commit a new selection set before approval",
    )


def _validate_single_active_selection(decision: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    if decision.get("decision_type") != "selection_set_approval":
        return
    if decision.get("status") not in {"accepted", "modified"}:
        return
    active = [
        existing
        for existing in io.active_decisions(decisions)
        if existing.get("decision_type") == "selection_set_approval"
        and existing.get("status") in {"accepted", "modified"}
    ]
    if active:
        _require(
            len(active) == 1,
            "multiple active selection_set_approval decisions already exist; repair governance before continuing",
        )
        _require(
            decision.get("supersedes_decision_id") == active[0].get("decision_id"),
            "an active selection_set_approval already exists; a new one must supersede it",
        )


def _validate_report_approval(
    decision: dict[str, Any],
    run_id: str,
    run_dir: Path,
    snapshot_override: dict[str, Any] | None = None,
) -> None:
    if decision.get("decision_type") != "report_approval":
        return
    from . import review_snapshots

    snapshot_id = str(decision.get("review_snapshot_id") or "").strip()
    _require(bool(snapshot_id), "report_approval requires review_snapshot_id")
    snapshot = snapshot_override or review_snapshots.load_review_snapshot(run_dir, snapshot_id)
    _require(snapshot is not None, f"review_snapshot_id does not exist: {snapshot_id}")
    artifact = review_snapshots.snapshot_artifact(snapshot_id)
    _require(
        artifact in decision.get("source_artifacts_reviewed", []),
        f"report_approval source_artifacts_reviewed must include {artifact}",
    )
    try:
        review_snapshots.validate_review_snapshot(run_id, run_dir, snapshot)
    except review_snapshots.ReviewSnapshotError as exc:
        raise DecisionValidationError(str(exc)) from exc


def validate_decision(
    run_id: str,
    run_dir: Path,
    decision: dict[str, Any],
    *,
    report_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    decision = dict(decision)

    _require(decision.get("schema_version") == schemas.SCHEMA_VERSION, "unsupported decision schema_version")
    decision_id = decision.get("decision_id")
    _require(bool(decision_id), "decision.decision_id is required")
    _require(bool(_DECISION_ID_RE.match(str(decision_id))), "decision.decision_id contains unsafe characters")
    _require(decision.get("run_id", run_id) == run_id, "decision.run_id does not match target run_id")
    decision["run_id"] = run_id

    _require(decision.get("decision_type") in schemas.DECISION_TYPES, "unsupported decision_type")
    _require(decision.get("status") in schemas.DECISION_STATUSES, "unsupported decision status")
    _validate_user(decision)

    rationale = str(decision.get("rationale", "")).strip()
    if (
        decision["decision_type"] in schemas.RATIONALE_REQUIRED_DECISION_TYPES
        or decision["status"] in schemas.RATIONALE_REQUIRED_STATUSES
    ):
        _require(bool(rationale), "decision.rationale is required for this decision")
    decision["rationale"] = rationale

    decisions = io.load_decisions(run_dir)
    supersedes = decision.get("supersedes_decision_id")
    if supersedes:
        known_ids = {d.get("decision_id") for d in decisions}
        _require(supersedes in known_ids, f"supersedes_decision_id not found: {supersedes}")

    if decision["decision_type"] == "report_approval":
        active_approval = [
            d
            for d in io.active_decisions(decisions)
            if d.get("decision_type") == "report_approval"
            and d.get("status") in {"accepted", "modified"}
        ]
        if active_approval:
            _require(
                decision.get("supersedes_decision_id") == active_approval[-1].get("decision_id"),
                "an active report_approval already exists; a new one must supersede it",
            )

    _validate_single_active_selection(decision, decisions)

    task_payload = build_validation_tasks(run_id, run_dir)
    task = _validate_task_reference(
        decision=decision,
        run_dir=run_dir,
        task_payload=task_payload,
        decisions=decisions,
    )

    if not decision.get("timestamp_utc"):
        decision["timestamp_utc"] = manifest.utc_now_iso()
    decision.setdefault("commands_or_parameters_affected", [])
    decision.setdefault("resulting_scenario_id", None)
    decision.setdefault("supersedes_decision_id", None)

    if not decision.get("source_artifacts_reviewed"):
        decision["source_artifacts_reviewed"] = task.get("source_artifacts", []) if task else [
            "manifest.json",
            "fit.json",
            "diagnostics.json",
        ]
    _validate_reviewed_artifacts(decision)
    _validate_scenario_selection(decision, run_dir)
    _validate_factor_selection(decision, run_dir)
    _validate_selection_set_approval(decision, run_dir)
    _validate_report_approval(decision, run_id, run_dir, report_snapshot)
    decision["input_hashes"] = io.artifact_hashes(run_dir, decision["source_artifacts_reviewed"])
    return decision


def commit_decision_payload(
    run_id: str, run_dir: Path, candidate: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise DecisionValidationError("decision artifact must be a JSON object")
    candidate = dict(candidate)
    report_snapshot = None
    if candidate.get("decision_type") == "report_approval" and not candidate.get("review_snapshot_id"):
        from . import review_snapshots

        report_snapshot = (
            review_snapshots.build_review_snapshot(run_id, run_dir)
            if dry_run
            else review_snapshots.create_review_snapshot(run_id, run_dir)
        )
        if report_snapshot.get("status") != "ready":
            raise DecisionValidationError("current reporting basis is not ready for report approval")
        snapshot_id = report_snapshot["review_snapshot_id"]
        candidate["review_snapshot_id"] = snapshot_id
        artifact = review_snapshots.snapshot_artifact(snapshot_id)
        reviewed = list(candidate.get("source_artifacts_reviewed") or [])
        if artifact not in reviewed:
            reviewed.append(artifact)
        candidate["source_artifacts_reviewed"] = reviewed
    decision_id = candidate.get("decision_id")
    if decision_id and io.decision_path(run_dir, str(decision_id)).exists():
        raise FileExistsError(f"decision already exists: {io.decision_path(run_dir, str(decision_id))}")
    decision = validate_decision(run_id, run_dir, candidate, report_snapshot=report_snapshot)
    path = io.decision_path(run_dir, decision["decision_id"])
    if path.exists():
        raise FileExistsError(f"decision already exists: {path}")
    if not dry_run:
        io.write_json(path, decision, exclusive=True)
    return decision


def commit_decision(run_id: str, run_dir: Path, decision_file: Path, *, dry_run: bool = False) -> dict[str, Any]:
    return commit_decision_payload(run_id, run_dir, io.read_json(Path(decision_file)), dry_run=dry_run)
