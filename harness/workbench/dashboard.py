"""Display-oriented dashboard payloads over existing workbench artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import explore, io, review_snapshots, schemas, tasks


def _active_by_type(run_dir: Path, decision_type: str) -> list[dict[str, Any]]:
    return [
        decision
        for decision in io.active_decisions(io.load_decisions(run_dir))
        if decision.get("decision_type") == decision_type
        and decision.get("status") in {"accepted", "modified"}
    ]


def _material_hashes_current(run_dir: Path, decision: dict[str, Any]) -> bool:
    reviewed = decision.get("source_artifacts_reviewed", [])
    if not isinstance(reviewed, list):
        return False
    material_reviewed = [name for name in reviewed if name != "manifest.json"]
    expected = {
        name: digest
        for name, digest in (decision.get("input_hashes") or {}).items()
        if name in material_reviewed
    }
    return io.artifact_hashes(run_dir, material_reviewed) == expected


def _report_snapshot_error(run_id: str, run_dir: Path, decision: dict[str, Any]) -> str | None:
    snapshot_id = str(decision.get("review_snapshot_id") or "").strip()
    if not snapshot_id:
        return "report approval is not bound to a review snapshot"
    try:
        snapshot = review_snapshots.load_review_snapshot(run_dir, snapshot_id)
    except review_snapshots.ReviewSnapshotError as exc:
        return str(exc)
    if snapshot is None:
        return f"review snapshot is missing: {snapshot_id}"
    try:
        review_snapshots.validate_review_snapshot(run_id, run_dir, snapshot)
    except review_snapshots.ReviewSnapshotError as exc:
        return str(exc)
    return None


def _selection_sets(run_dir: Path) -> list[dict[str, Any]]:
    root = Path(run_dir) / schemas.SELECTION_SETS_DIRNAME
    if not root.is_dir():
        return []
    return [io.read_json(path) for path in sorted(root.glob("*.json"))]


def _blocker(code: str, label: str, severity: str = "blocked") -> dict[str, str]:
    return {"code": code, "label": label, "severity": severity}


def _latest_decision_id(decisions: list[dict[str, Any]], decision_type: str) -> str | None:
    matches = [
        decision
        for decision in decisions
        if decision.get("decision_type") == decision_type
        and decision.get("status") in {"accepted", "modified"}
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda d: (d.get("timestamp_utc") or "", d.get("decision_id") or ""))[-1].get(
        "decision_id"
    )


def _latest_selection_set_id(selection_sets: list[dict[str, Any]]) -> str | None:
    committed = [
        selection_set
        for selection_set in selection_sets
        if selection_set.get("status") == "committed" and selection_set.get("selection_set_id")
    ]
    if not committed:
        return None
    return sorted(
        committed,
        key=lambda s: (s.get("committed_utc") or s.get("generated_utc") or "", s.get("selection_set_id") or ""),
    )[-1].get("selection_set_id")


def _latest_selected_scenario_id(decisions: list[dict[str, Any]]) -> str | None:
    governed = [
        decision
        for decision in decisions
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
        and decision.get("resulting_scenario_id")
    ]
    if len(governed) == 1:
        return governed[0].get("resulting_scenario_id")
    matches = [
        decision
        for decision in decisions
        if decision.get("decision_type") in {"scenario_selection", "factor_selection"}
        and decision.get("status") in {"accepted", "modified"}
        and decision.get("resulting_scenario_id")
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda d: (d.get("timestamp_utc") or "", d.get("decision_id") or ""))[-1].get(
        "resulting_scenario_id"
    )


def _next_action(
    *,
    pending_validation: list[dict[str, Any]],
    pending_diagnostics: list[dict[str, Any]],
    pending_bcl: list[dict[str, Any]],
    pending_scenario: list[dict[str, Any]],
    missing_selection_approvals: list[str],
    stale_selection_approvals: list[str],
    stale_report_approvals: list[str],
    has_report_approval: bool,
    has_report: bool,
    readiness_status: str,
) -> dict[str, Any]:
    if pending_validation:
        task = pending_validation[0]
        return {
            "label": "Review validation warning",
            "detail": task.get("title") or "A validation warning is unresolved.",
            "target_tab": "decisions",
            "task_id": task.get("task_id"),
            "decision_type": "warning_ack",
            "blocked": True,
        }
    if pending_diagnostics:
        task = pending_diagnostics[0]
        return {
            "label": "Review diagnostics warning",
            "detail": task.get("title") or "A diagnostics warning is unresolved.",
            "target_tab": "decisions",
            "task_id": task.get("task_id"),
            "decision_type": "warning_ack",
            "blocked": True,
        }
    if pending_bcl:
        task = pending_bcl[0]
        return {
            "label": "Review deterministic chain ladder output",
            "detail": "A governed method review acknowledgement is required before reporting.",
            "target_tab": "decisions",
            "task_id": task.get("task_id"),
            "decision_type": "method_review_ack",
            "blocked": True,
        }
    if pending_scenario:
        task = pending_scenario[0]
        return {
            "label": "Select scenario treatment",
            "detail": "Sensitivity or preview scenarios need a governed scenario-selection decision.",
            "target_tab": "scenarios",
            "task_id": task.get("task_id"),
            "decision_type": "scenario_selection",
            "blocked": True,
        }
    if missing_selection_approvals:
        return {
            "label": "Approve committed selection set",
            "detail": f"Selection set {missing_selection_approvals[0]} is committed but not approved.",
            "target_tab": "factors",
            "selection_set_id": missing_selection_approvals[0],
            "decision_type": "selection_set_approval",
            "blocked": True,
        }
    if stale_selection_approvals:
        return {
            "label": "Refresh selection-set approval",
            "detail": f"Approval {stale_selection_approvals[0]} is stale against current artifacts.",
            "target_tab": "factors",
            "decision_type": "selection_set_approval",
            "blocked": True,
        }
    if stale_report_approvals:
        return {
            "label": "Refresh report approval",
            "detail": f"Report approval {stale_report_approvals[0]} is stale against current artifacts.",
            "target_tab": "report",
            "decision_type": "report_approval",
            "blocked": True,
        }
    if not has_report_approval:
        return {
            "label": "Approve report generation",
            "detail": "Prerequisites are clear; a report approval decision is still required.",
            "target_tab": "report",
            "decision_type": "report_approval",
            "blocked": False,
        }
    if not has_report:
        return {
            "label": "Generate approved report pack",
            "detail": "The approval gate would pass; run the guarded report command.",
            "target_tab": "report",
            "decision_type": None,
            "blocked": False,
        }
    return {
        "label": "Review generated report pack",
        "detail": f"Readiness state is {readiness_status}.",
        "target_tab": "report",
        "decision_type": None,
        "blocked": False,
    }


def build_report_readiness(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    task_payload = tasks.build_validation_tasks(run_id, run_dir)
    pending = [task for task in task_payload.get("tasks", []) if task.get("status") == "pending"]
    pending_validation = [
        task
        for task in pending
        if task.get("task_type") == "warning_review"
        and "validation.json" in task.get("source_artifacts", [])
    ]
    pending_diagnostics = [
        task
        for task in pending
        if task.get("task_type") == "warning_review"
        and "diagnostics.json" in task.get("source_artifacts", [])
    ]
    pending_bcl = [task for task in pending if task.get("task_type") == "bcl_review"]
    pending_scenario = [task for task in pending if task.get("task_type") == "scenario_selection"]

    committed_selection_sets = [
        selection_set
        for selection_set in _selection_sets(run_dir)
        if selection_set.get("status") == "committed"
    ]
    all_decisions = io.load_decisions(run_dir)
    selection_approvals = _active_by_type(run_dir, "selection_set_approval")
    approved_selection_ids = {
        decision.get("selection_set_id")
        for decision in all_decisions
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
        if decision.get("selection_set_id")
    }
    missing_selection_approvals = [
        selection_set.get("selection_set_id")
        for selection_set in committed_selection_sets
        if selection_set.get("selection_set_id") not in approved_selection_ids
    ]
    stale_selection_approvals = [
        decision.get("decision_id")
        for decision in selection_approvals
        if not _material_hashes_current(run_dir, decision)
    ]
    ambiguous_selection_approvals = len(selection_approvals) > 1

    report_approvals = _active_by_type(run_dir, "report_approval")
    stale_report_approvals = []
    for decision in report_approvals:
        if not _material_hashes_current(run_dir, decision) or _report_snapshot_error(run_id, run_dir, decision):
            stale_report_approvals.append(decision.get("decision_id"))
    if len(report_approvals) > 1:
        stale_report_approvals.extend(
            decision.get("decision_id")
            for decision in report_approvals
            if decision.get("decision_id") not in stale_report_approvals
        )
    has_report_approval = len(report_approvals) == 1 and not stale_report_approvals
    has_report = (run_dir / "report.html").is_file()
    has_sensitivity = (run_dir / "sensitivity.json").is_file()
    has_scenario_selection = bool(
        _active_by_type(run_dir, "scenario_selection")
        or _active_by_type(run_dir, "selection_set_approval")
        or _active_by_type(run_dir, "factor_selection")
    )

    blockers: list[dict[str, str]] = []
    if pending_validation:
        blockers.append(_blocker("validation_warnings", "validation warnings are unresolved"))
    if pending_diagnostics:
        blockers.append(_blocker("diagnostics_warnings", "diagnostics warnings are unresolved"))
    if pending_bcl:
        blockers.append(_blocker("bcl_review", "deterministic chain ladder review is unresolved"))
    if pending_scenario:
        blockers.append(_blocker("scenario_selection", "scenario selection is unresolved"))
    if missing_selection_approvals:
        blockers.append(_blocker("selection_set_approval", "committed selection set is not approved"))
    if stale_selection_approvals:
        blockers.append(_blocker("stale_selection_set_approval", "selection-set approval is stale"))
    if ambiguous_selection_approvals:
        blockers.append(_blocker("ambiguous_selection_set_approval", "multiple active selection-set approvals exist"))
    if stale_report_approvals:
        blockers.append(_blocker("stale_report_approval", "report approval is stale"))

    prerequisite_blocked = bool(blockers)
    if not has_report_approval:
        blockers.append(_blocker("report_approval", "report approval is missing", "ready" if not prerequisite_blocked else "blocked"))
    if not has_report:
        blockers.append(_blocker("report_html", "report.html has not been generated", "info"))

    if prerequisite_blocked:
        readiness_status = "blocked"
    elif has_report_approval and has_report:
        readiness_status = "generated"
    elif has_report_approval:
        readiness_status = "approved"
    elif has_report:
        readiness_status = "draft"
    else:
        readiness_status = "ready_for_approval"

    checklist = [
        {
            "key": "validation_warnings_reviewed",
            "label": "validation warnings reviewed",
            "status": "complete" if not pending_validation else "blocked",
        },
        {
            "key": "diagnostics_reviewed",
            "label": "diagnostics reviewed",
            "status": "complete" if (run_dir / "diagnostics.json").is_file() and not pending_diagnostics else "blocked",
        },
        {
            "key": "selection_set_approved",
            "label": "selection set approved",
            "status": "complete" if not missing_selection_approvals and not stale_selection_approvals else "blocked",
        },
        {
            "key": "scenario_selected",
            "label": "scenario selected",
            "status": "complete" if not has_sensitivity or has_scenario_selection else "blocked",
        },
        {
            "key": "report_approval_exists",
            "label": "report approval exists",
            "status": "complete" if has_report_approval else "pending",
        },
        {
            "key": "report_generated",
            "label": "report generated",
            "status": "complete" if has_report else "pending",
        },
    ]

    require_approval_would_pass = not prerequisite_blocked and has_report_approval
    if prerequisite_blocked:
        require_approval_failure = blockers[0]["label"]
    elif not has_report_approval:
        require_approval_failure = "report approval decision is required"
    else:
        require_approval_failure = None

    active = io.active_decisions(io.load_decisions(run_dir))
    selection_set_payloads = _selection_sets(run_dir)
    active_selection_set_id = (
        selection_approvals[0].get("selection_set_id")
        if len(selection_approvals) == 1
        else None
    )
    explore_payload = explore.list_explore_scenarios(run_id, run_dir)
    explore_count = explore_payload.get("exploratory_scenario_count", 0)
    governed_selection_set_exists = bool(_latest_selection_set_id(selection_set_payloads))
    governed_selection_approval_exists = bool(_active_by_type(run_dir, "selection_set_approval"))
    report_command = f"reserve report {run_id} --format-out html --require-approval --out runs"
    if explore_count and not governed_selection_set_exists:
        blockers.append(
            _blocker(
                "explore_not_governed",
                "Promote an exploratory scenario to governed selection before report approval.",
                "info",
            )
        )

    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "status": readiness_status,
        "require_approval_would_pass": require_approval_would_pass,
        "require_approval_failure": require_approval_failure,
        "next_action": _next_action(
            pending_validation=pending_validation,
            pending_diagnostics=pending_diagnostics,
            pending_bcl=pending_bcl,
            pending_scenario=pending_scenario,
            missing_selection_approvals=missing_selection_approvals,
            stale_selection_approvals=stale_selection_approvals,
            stale_report_approvals=stale_report_approvals,
            has_report_approval=has_report_approval,
            has_report=has_report,
            readiness_status=readiness_status,
        ),
        "blockers": blockers,
        "checklist": checklist,
        "report_path": "report.html" if has_report else None,
        "report_command": report_command,
        "selected_scenario_id": _latest_selected_scenario_id(active),
        "selection_set_id": active_selection_set_id,
        "exploratory_scenarios_exist": bool(explore_count),
        "exploratory_scenario_count": explore_count,
        "governed_selection_set_exists": governed_selection_set_exists,
        "governed_selection_approval_exists": governed_selection_approval_exists,
        "report_approval_exists": has_report_approval,
        "explore_message": "Explore freely. Promote deliberately. Only governed selections enter the report pack.",
        "report_approval_decision_id": _latest_decision_id(active, "report_approval"),
        "review_snapshot_id": (
            report_approvals[0].get("review_snapshot_id")
            if len(report_approvals) == 1
            else None
        ),
        "source_artifacts": [
            name
            for name in (
                "manifest.json",
                "validation.json",
                "fit.json",
                "diagnostics.json",
                schemas.TASKS_FILENAME,
                schemas.SELECTION_SETS_DIRNAME,
                schemas.EXPLORE_DIRNAME,
                schemas.DECISIONS_DIRNAME,
                schemas.REVIEW_SNAPSHOTS_DIRNAME,
                "report.html",
            )
            if (run_dir / name).exists()
        ],
    }


def _superseded_by_map(decisions: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for decision in decisions:
        supersedes = decision.get("supersedes_decision_id")
        if supersedes:
            mapping[str(supersedes)] = str(decision.get("decision_id"))
    return mapping


def _journal_entry(decision: dict[str, Any], active: bool, superseded_by: str | None) -> dict[str, Any]:
    user = decision.get("user") or {}
    return {
        "decision_id": decision.get("decision_id"),
        "decision_type": decision.get("decision_type"),
        "status": decision.get("status"),
        "active": active,
        "timestamp_utc": decision.get("timestamp_utc"),
        "user_id": user.get("id"),
        "display_name": user.get("display_name"),
        "task_id": decision.get("task_id"),
        "selection_set_id": decision.get("selection_set_id"),
        "scenario_id": decision.get("resulting_scenario_id"),
        "development_age": decision.get("development_age"),
        "selected_basis": decision.get("selected_basis"),
        "factor_selections": decision.get("factor_selections", []),
        "manual_overrides": decision.get("manual_overrides", []),
        "exclusions": decision.get("exclusions", []),
        "factor_point_exclusions": decision.get("factor_point_exclusions", []),
        "tail_selection": decision.get("tail_selection"),
        "review_snapshot_id": decision.get("review_snapshot_id"),
        "selection_set_artifact": decision.get("selection_set_artifact"),
        "source_explore_scenario_id": decision.get("source_explore_scenario_id"),
        "source_artifacts_reviewed": decision.get("source_artifacts_reviewed", []),
        "rationale": decision.get("rationale"),
        "supersedes_decision_id": decision.get("supersedes_decision_id"),
        "superseded_by_decision_id": superseded_by,
    }


def build_decision_journal(run_id: str, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    all_decisions = io.load_decisions(run_dir)
    superseded_ids = io.superseded_decision_ids(all_decisions)
    superseded_by = _superseded_by_map(all_decisions)
    active_entries = [
        _journal_entry(decision, True, None)
        for decision in all_decisions
        if decision.get("decision_id") not in superseded_ids
    ]
    superseded_entries = [
        _journal_entry(decision, False, superseded_by.get(str(decision.get("decision_id"))))
        for decision in all_decisions
        if decision.get("decision_id") in superseded_ids
    ]
    return {
        "schema_version": schemas.SCHEMA_VERSION,
        "run_id": run_id,
        "active_decisions": active_entries,
        "superseded_decisions": superseded_entries,
        "decision_count": len(all_decisions),
        "source_artifacts": [schemas.DECISIONS_DIRNAME] if (run_dir / schemas.DECISIONS_DIRNAME).is_dir() else [],
    }
