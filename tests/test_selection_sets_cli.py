import json
import hashlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _run_cli(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_committed_selection_set(run_id: str, run_dir: Path, selection_set_id: str) -> dict:
    artifact = f"selection_sets/{selection_set_id}.json"
    payload = {
        "schema_version": "0.1",
        "selection_set_id": selection_set_id,
        "preview_scenario_id": selection_set_id,
        "run_id": run_id,
        "basis_run_id": run_id,
        "status": "committed",
        "factor_selections": [],
        "exclusions": [],
        "global_rationale": "Controlled reporting-basis test selection.",
        "source_artifacts": ["fit.json"],
        "input_hashes": {"fit.json": _sha256(run_dir / "fit.json")},
        "selection_set_artifact": artifact,
    }
    return json.loads(_write_json(run_dir / artifact, payload).read_text())


def _commit_manual_selection_approval(
    tmp_path: Path,
    run_id: str,
    selection_set: dict,
    decision_id: str,
    supersedes: str | None = None,
) -> subprocess.CompletedProcess:
    decision = _selection_approval(run_id, selection_set, decision_id=decision_id)
    decision["supersedes_decision_id"] = supersedes
    decision_file = _write_json(tmp_path / f"{decision_id}.json", decision)
    return _run_cli(
        "decide",
        run_id,
        "--decision-file",
        str(decision_file),
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )


def _fit_bcl(tmp_path: Path) -> tuple[str, Path]:
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "chain_ladder",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    return run_id, tmp_path / run_id


def _request_file(tmp_path: Path, run_id: str) -> Path:
    return _write_json(
        tmp_path / "selection_request.json",
        {
            "schema_version": "0.1",
            "run_id": run_id,
            "factor_selections": [
                {
                    "development_age": "1 -> 2",
                    "selected_basis": "last_3",
                    "rationale": "Recent periods reviewed as more representative.",
                }
            ],
            "exclusions": [
                {
                    "type": "origin",
                    "value": "1981",
                    "rationale": "Oldest origin reviewed as exclusion.",
                }
            ],
            "global_rationale": "Combined deterministic chain ladder scenario prepared for actuarial review.",
            "created_by": {"id": "tester", "display_name": "Test User"},
        },
    )


def _preview_selection_set(tmp_path: Path, run_id: str) -> dict:
    result = _run_cli(
        "selection-sets",
        "preview",
        run_id,
        "--request-file",
        str(_request_file(tmp_path, run_id)),
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _selection_approval(run_id: str, selection_set: dict, decision_id: str = "approve_selection_set_cli") -> dict:
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": None,
        "decision_type": "selection_set_approval",
        "status": "accepted",
        "selection_set_id": selection_set["selection_set_id"],
        "resulting_scenario_id": selection_set["preview_scenario_id"],
        "base_run_id": run_id,
        "rationale": "Approved committed selection set for CLI test.",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": [
            *selection_set["source_artifacts"],
            selection_set["selection_set_artifact"],
        ],
        "commands_or_parameters_affected": [],
        "supersedes_decision_id": None,
    }


def _commit_selection_set(tmp_path: Path, run_id: str, selection_set: dict, decision: dict | None = None):
    decision = decision or _selection_approval(run_id, selection_set)
    decision_file = _write_json(tmp_path / f"{decision['decision_id']}.json", decision)
    return _run_cli(
        "selection-sets",
        "commit",
        run_id,
        "--selection-set-id",
        selection_set["selection_set_id"],
        "--decision-file",
        str(decision_file),
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )


def _make_report_run(tmp_path: Path, *, validation_warn: bool = False) -> tuple[str, Path]:
    run_id = "2026-07-06T12-00-00_report_gate_abc123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_utc": "2026-07-06T12:00:00Z",
            "command": "reserve fit examples/raa.csv --method mack",
            "inputs": [{"path": "examples/raa.csv", "sha256": "input-hash"}],
            "engine": {"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
            "environment": {"python": "3.12.0", "harness_version": "0.1.0"},
            "parameters": {"method": "mack"},
            "outputs": ["validation.json", "fit.json", "triangle.json", "diagnostics.json"],
            "exit_code": 3 if validation_warn else 0,
        },
    )
    _write_json(
        run_dir / "validation.json",
        {
            "checks": [
                {
                    "check_id": "monotone_cumulative",
                    "verdict": "warn",
                    "details": {"origin": "1984", "dev": 4},
                }
            ]
            if validation_warn
            else [],
            "verdict": "warn" if validation_warn else "pass",
        },
    )
    _write_json(run_dir / "diagnostics.json", {"tests": [], "overall": "pass"})
    _write_json(
        run_dir / "fit.json",
        {
            "run_id": run_id,
            "method": "mack",
            "parameters": {
                "averaging": "volume",
                "tail": "none",
                "n_periods": None,
                "excluded_origins": [],
                "excluded_valuations": [],
                "sigma_interpolation": "mack",
            },
            "totals": {"latest": 1000.0, "ultimate": 1300.0, "ibnr": 300.0, "mack_se": 42.0},
            "development_factors": [{"from_dev": 1, "to_dev": 2, "ldf": 1.5, "sigma": 0.2}],
            "by_origin": [
                {"origin": "1981", "latest": 600.0, "ultimate": 750.0, "ibnr": 150.0, "mack_se": 20.0},
                {"origin": "1982", "latest": 400.0, "ultimate": 550.0, "ibnr": 150.0, "mack_se": 22.0},
            ],
            "units": "as-input",
        },
    )
    _write_json(
        run_dir / "triangle.json",
        {
            "run_id": run_id,
            "basis": "cumulative",
            "cells": [
                {"origin": "1981", "dev": 1, "value": 400.0, "type": "actual"},
                {"origin": "1981", "dev": 2, "value": 600.0, "type": "actual"},
                {"origin": "1982", "dev": 1, "value": 400.0, "type": "actual"},
            ],
        },
    )
    return run_id, run_dir


def _commit_report_approval(tmp_path: Path, run_id: str) -> None:
    tasks_result = _run_cli("tasks", run_id, "--format", "json", "--out", str(tmp_path))
    assert tasks_result.returncode == 0, tasks_result.stderr
    task = next(task for task in json.loads(tasks_result.stdout)["tasks"] if task["task_type"] == "report_approval")
    decision = {
        "schema_version": "0.1",
        "decision_id": "approve_report_cli",
        "run_id": run_id,
        "task_id": task["task_id"],
        "decision_type": "report_approval",
        "status": "accepted",
        "rationale": "",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": ["manifest.json", "fit.json", "diagnostics.json"],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": None,
        "supersedes_decision_id": None,
    }
    decision_file = _write_json(tmp_path / "approve_report_cli.json", decision)
    result = _run_cli(
        "decide",
        run_id,
        "--decision-file",
        str(decision_file),
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr


def test_selection_sets_list_and_show(tmp_path):
    run_id, _run_dir = _fit_bcl(tmp_path)
    empty = _run_cli("selection-sets", "list", run_id, "--format", "json", "--out", str(tmp_path))
    assert empty.returncode == 0, empty.stderr
    assert json.loads(empty.stdout)["selection_sets"] == []

    preview = _preview_selection_set(tmp_path, run_id)
    listed = _run_cli("selection-sets", "list", run_id, "--format", "json", "--out", str(tmp_path))
    shown = _run_cli(
        "selection-sets",
        "show",
        run_id,
        preview["selection_set_id"],
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )

    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)["selection_sets"][0]["selection_set_id"] == preview["selection_set_id"]
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["selection_set_id"] == preview["selection_set_id"]


def test_selection_sets_preview_creates_preview_artifact(tmp_path):
    run_id, run_dir = _fit_bcl(tmp_path)

    preview = _preview_selection_set(tmp_path, run_id)

    assert preview["status"] == "preview"
    assert preview["factor_selections"][0]["selected_basis"] == "last_3"
    assert preview["exclusions"][0]["type"] == "origin"
    assert (run_dir / preview["selection_set_artifact"]).is_file()


def test_selection_sets_commit_requires_decision_file(tmp_path):
    run_id, _run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)

    result = _run_cli(
        "selection-sets",
        "commit",
        run_id,
        "--selection-set-id",
        preview["selection_set_id"],
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )

    assert result.returncode == 4
    assert "--decision-file" in result.stderr


def test_selection_sets_commit_validates_decision_artifact_and_rolls_back(tmp_path):
    run_id, run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)
    bad_decision = _selection_approval(run_id, preview, decision_id="bad_selection_approval")
    bad_decision["resulting_scenario_id"] = "not_the_preview"

    result = _commit_selection_set(tmp_path, run_id, preview, bad_decision)

    assert result.returncode == 4
    assert "resulting_scenario_id does not match" in result.stderr
    assert json.loads((run_dir / preview["selection_set_artifact"]).read_text())["status"] == "preview"


def test_selection_sets_commit_writes_committed_artifact_and_decision(tmp_path):
    run_id, run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)

    result = _commit_selection_set(tmp_path, run_id, preview)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selection_set"]["status"] == "committed"
    assert payload["decision"]["decision_type"] == "selection_set_approval"
    assert (run_dir / "decisions" / "approve_selection_set_cli.json").is_file()


def test_selection_sets_commit_dry_run_validates_without_writing(tmp_path):
    run_id, run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)
    decision = _selection_approval(run_id, preview, decision_id="approve_selection_set_dry_run")
    decision_file = _write_json(tmp_path / "approve_selection_set_dry_run.json", decision)

    result = _run_cli(
        "selection-sets",
        "commit",
        run_id,
        "--selection-set-id",
        preview["selection_set_id"],
        "--decision-file",
        str(decision_file),
        "--format",
        "json",
        "--out",
        str(tmp_path),
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selection_set"]["status"] == "committed"
    assert json.loads((run_dir / preview["selection_set_artifact"]).read_text())["status"] == "preview"
    assert not (run_dir / "decisions" / "approve_selection_set_dry_run.json").exists()


def test_committed_selection_set_cannot_be_overwritten(tmp_path):
    run_id, _run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)
    first = _commit_selection_set(tmp_path, run_id, preview)
    assert first.returncode == 0, first.stderr
    second_decision = _selection_approval(run_id, preview, decision_id="approve_selection_set_again")

    second = _commit_selection_set(tmp_path, run_id, preview, second_decision)

    assert second.returncode == 4
    assert "cannot be overwritten" in second.stderr


def test_stale_selection_set_source_hashes_are_rejected(tmp_path):
    run_id, run_dir = _fit_bcl(tmp_path)
    preview = _preview_selection_set(tmp_path, run_id)
    fit_payload = json.loads((run_dir / "fit.json").read_text())
    fit_payload["tampered_for_test"] = True
    _write_json(run_dir / "fit.json", fit_payload)

    result = _commit_selection_set(tmp_path, run_id, preview)

    assert result.returncode == 4
    assert "source artifacts are stale" in result.stderr
    assert json.loads((run_dir / preview["selection_set_artifact"]).read_text())["status"] == "preview"


def test_report_require_approval_fails_without_report_approval(tmp_path):
    run_id, _run_dir = _make_report_run(tmp_path)

    result = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert result.returncode == 4
    assert "report approval decision is required" in result.stderr


def test_report_require_approval_fails_with_unresolved_tasks(tmp_path):
    run_id, _run_dir = _make_report_run(tmp_path, validation_warn=True)

    result = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert result.returncode == 4
    assert "unresolved required workbench tasks remain" in result.stderr


def test_report_require_approval_fails_when_committed_selection_set_lacks_approval(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)
    _commit_report_approval(tmp_path, run_id)
    _write_json(
        run_dir / "selection_sets" / "selection_set_unapproved.json",
        {
            "schema_version": "0.1",
            "selection_set_id": "selection_set_unapproved",
            "preview_scenario_id": "selection_set_unapproved",
            "run_id": run_id,
            "basis_run_id": run_id,
            "status": "committed",
            "factor_selections": [],
            "exclusions": [],
            "global_rationale": "Committed selection set without approval for gate test.",
            "source_artifacts": ["fit.json"],
            "input_hashes": {},
            "selection_set_artifact": "selection_sets/selection_set_unapproved.json",
        },
    )

    result = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert result.returncode == 4
    assert "without active selection_set_approval" in result.stderr


def test_report_require_approval_succeeds_when_required_decisions_exist(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)
    _commit_report_approval(tmp_path, run_id)

    result = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (run_dir / "report.html").is_file()
    assert "approved" in (run_dir / "report.html").read_text()


def test_report_require_approval_fails_when_report_approval_is_stale(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)
    _commit_report_approval(tmp_path, run_id)
    fit_payload = json.loads((run_dir / "fit.json").read_text())
    fit_payload["tampered_for_test"] = True
    _write_json(run_dir / "fit.json", fit_payload)

    result = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert result.returncode == 4
    assert "report_approval decision source artifacts are stale" in result.stderr
    assert not (run_dir / "report.html").exists()


def test_report_approval_snapshot_is_invalidated_by_later_selection_approval(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)
    _commit_report_approval(tmp_path, run_id)
    selection_set = _write_committed_selection_set(run_id, run_dir, "selection_set_after_report_approval")
    selection_result = _commit_manual_selection_approval(
        tmp_path,
        run_id,
        selection_set,
        "approve_selection_after_report",
    )
    assert selection_result.returncode == 0, selection_result.stderr

    guarded = _run_cli("report", run_id, "--require-approval", "--out", str(tmp_path))

    assert guarded.returncode == 4
    assert "review snapshot is stale" in guarded.stderr
    assert not (run_dir / "report.html").exists()


def test_new_selection_approval_must_supersede_active_reporting_basis(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)
    first_set = _write_committed_selection_set(run_id, run_dir, "selection_set_first")
    first = _commit_manual_selection_approval(tmp_path, run_id, first_set, "approve_selection_first")
    assert first.returncode == 0, first.stderr
    second_set = _write_committed_selection_set(run_id, run_dir, "selection_set_second")

    without_supersession = _commit_manual_selection_approval(
        tmp_path,
        run_id,
        second_set,
        "approve_selection_second",
    )

    assert without_supersession.returncode == 4
    assert "must supersede" in without_supersession.stderr

    with_supersession = _commit_manual_selection_approval(
        tmp_path,
        run_id,
        second_set,
        "approve_selection_second_superseding",
        supersedes="approve_selection_first",
    )
    assert with_supersession.returncode == 0, with_supersession.stderr


def test_report_without_approval_marks_draft_incomplete(tmp_path):
    run_id, run_dir = _make_report_run(tmp_path)

    result = _run_cli("report", run_id, "--out", str(tmp_path))

    assert result.returncode == 0, result.stderr
    html = (run_dir / "report.html").read_text()
    assert "draft/incomplete" in html
    assert "no active report_approval decision" in html
