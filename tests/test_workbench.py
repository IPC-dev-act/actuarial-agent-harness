import json
import subprocess
import sys
from pathlib import Path

from harness import manifest
from harness.workbench import tasks as workbench_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"
CALENDAR_EFFECT_CSV = REPO_ROOT / "examples" / "triangle_calendar_effect.csv"
WORKBENCH_DIR = REPO_ROOT / "harness" / "workbench"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _fit(csv_path: Path, tmp_path: Path) -> tuple[str, Path]:
    result = _run_cli(
        "fit", str(csv_path), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    return run_id, tmp_path / run_id


def _diagnostics(run_id: str, tmp_path: Path) -> subprocess.CompletedProcess:
    return _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))


def _tasks(run_id: str, tmp_path: Path) -> dict:
    result = _run_cli("tasks", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _decision_payload(decision_id: str, run_id: str, task_id: str | None, decision_type: str, **overrides):
    payload = {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": task_id,
        "decision_type": decision_type,
        "status": "accepted",
        "rationale": "Reviewed by the actuary for the workbench test.",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": ["fit.json", "triangle.json", "diagnostics.json"],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": None,
        "supersedes_decision_id": None,
    }
    payload.update(overrides)
    return payload


def _write_decision_file(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / f"{payload['decision_id']}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _commit_decision(run_id: str, tmp_path: Path, payload: dict) -> subprocess.CompletedProcess:
    decision_file = _write_decision_file(tmp_path, payload)
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


def _ack_all_warning_tasks(run_id: str, tmp_path: Path, prefix: str) -> None:
    payload = _tasks(run_id, tmp_path)
    warning_tasks = [t for t in payload["tasks"] if t["task_type"] == "warning_review"]
    assert warning_tasks
    for i, task in enumerate(warning_tasks, start=1):
        decision = _decision_payload(f"{prefix}_{i}", run_id, task["task_id"], "warning_ack")
        result = _commit_decision(run_id, tmp_path, decision)
        assert result.returncode == 0, result.stderr


def test_task_generation_from_validation_warnings(tmp_path):
    run_id, _run_dir = _fit(RAA_CSV, tmp_path)

    payload = _tasks(run_id, tmp_path)

    warning_tasks = [t for t in payload["tasks"] if t["task_type"] == "warning_review"]
    assert warning_tasks
    assert any("validation.json" in t["source_artifacts"] for t in warning_tasks)
    assert any("monotone_cumulative" in t["title"] for t in warning_tasks)


def test_task_generation_from_diagnostics_warnings(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    diag_result = _diagnostics(run_id, tmp_path)
    assert diag_result.returncode == 3, diag_result.stderr

    payload = _tasks(run_id, tmp_path)

    diagnostics_tasks = [
        t for t in payload["tasks"] if "diagnostics.json" in t["source_artifacts"]
    ]
    assert diagnostics_tasks
    assert all(t["allowed_decision_types"] == ["warning_ack"] for t in diagnostics_tasks)


def test_no_fabricated_diagnostics_task_when_diagnostics_missing(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)

    payload = _tasks(run_id, tmp_path)

    assert all("diagnostics.json" not in t["source_artifacts"] for t in payload["tasks"])
    assert not any(t["task_id"].startswith("warning_diagnostics") for t in payload["tasks"])


def test_report_approval_task_appears_only_after_warnings_resolved(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    diag_result = _diagnostics(run_id, tmp_path)
    assert diag_result.returncode == 3, diag_result.stderr

    before = _tasks(run_id, tmp_path)
    assert any(t["task_type"] == "warning_review" for t in before["tasks"])
    assert not any(t["task_type"] == "report_approval" for t in before["tasks"])

    _ack_all_warning_tasks(run_id, tmp_path, "ack_warning")

    after = _tasks(run_id, tmp_path)
    assert any(t["task_type"] == "report_approval" for t in after["tasks"])


def test_decision_write_is_immutable_and_refuses_overwrite(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)
    warning_task = next(t for t in _tasks(run_id, tmp_path)["tasks"] if t["task_type"] == "warning_review")
    decision = _decision_payload("ack_warning_immutable", run_id, warning_task["task_id"], "warning_ack")

    first = _commit_decision(run_id, tmp_path, decision)
    assert first.returncode == 0, first.stderr
    second = _commit_decision(run_id, tmp_path, decision)
    assert second.returncode == 4
    assert "decision already exists" in second.stderr


def test_rationale_required_for_warning_acknowledgements(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)
    warning_task = next(t for t in _tasks(run_id, tmp_path)["tasks"] if t["task_type"] == "warning_review")
    decision = _decision_payload(
        "ack_warning_no_rationale",
        run_id,
        warning_task["task_id"],
        "warning_ack",
        rationale="",
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 4
    assert "rationale is required" in result.stderr


def test_status_changes_after_committing_report_approval(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)
    _ack_all_warning_tasks(run_id, tmp_path, "ack_warning_for_status")

    status_before = _run_cli("status", run_id, "--format", "json", "--out", str(tmp_path))
    assert status_before.returncode == 0
    assert json.loads(status_before.stdout)["status"] == "needs_judgment"

    report_task = next(t for t in _tasks(run_id, tmp_path)["tasks"] if t["task_type"] == "report_approval")
    approval = _decision_payload(
        "approve_report_for_status",
        run_id,
        report_task["task_id"],
        "report_approval",
        rationale="",
    )
    approval["source_artifacts_reviewed"] = ["manifest.json", "fit.json", "diagnostics.json"]
    assert _commit_decision(run_id, tmp_path, approval).returncode == 0

    status_after = _run_cli("status", run_id, "--format", "json", "--out", str(tmp_path))
    assert json.loads(status_after.stdout)["status"] == "signed_off"


def test_hashes_are_recorded_for_reviewed_artifacts(tmp_path):
    run_id, run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)
    warning_task = next(t for t in _tasks(run_id, tmp_path)["tasks"] if t["task_type"] == "warning_review")
    decision = _decision_payload("ack_warning_hashes", run_id, warning_task["task_id"], "warning_ack")
    result = _commit_decision(run_id, tmp_path, decision)
    assert result.returncode == 0, result.stderr

    written = json.loads((run_dir / "decisions" / "ack_warning_hashes.json").read_text())
    assert written["input_hashes"]["fit.json"] == manifest.sha256_file(run_dir / "fit.json")
    assert written["input_hashes"]["triangle.json"] == manifest.sha256_file(run_dir / "triangle.json")
    assert written["input_hashes"]["diagnostics.json"] == manifest.sha256_file(run_dir / "diagnostics.json")


def test_handoff_writes_current_structured_pause_resume_artifact(tmp_path):
    run_id, run_dir = _fit(RAA_CSV, tmp_path)
    result = _run_cli("handoff", run_id, "--format", "json", "--out", str(tmp_path))

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads((run_dir / "review_handoff.json").read_text())
    assert payload["phase"] == "awaiting_human_judgment"
    assert payload["resume_command"] == f"/review {run_id}"
    assert payload["pending_judgment"]
    assert "manifest.json" not in payload["source_artifacts"]
    assert written["input_hashes"] == {
        name: manifest.sha256_file(run_dir / name)
        for name in written["source_artifacts"]
    }


def test_reviewed_artifact_paths_must_stay_inside_run_folder(tmp_path):
    run_id, _run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)
    warning_task = next(t for t in _tasks(run_id, tmp_path)["tasks"] if t["task_type"] == "warning_review")
    decision = _decision_payload(
        "ack_warning_unsafe_artifact",
        run_id,
        warning_task["task_id"],
        "warning_ack",
        source_artifacts_reviewed=["../manifest.json"],
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 4
    assert "unsafe run-relative path" in result.stderr


def test_workbench_package_is_model_agnostic():
    text = "\n".join(path.read_text() for path in sorted(WORKBENCH_DIR.glob("*.py")))
    assert "chainladder_adapter" not in text
    assert "import chainladder" not in text


def test_task_generation_is_deterministic_for_same_artifacts(tmp_path):
    run_id, run_dir = _fit(CALENDAR_EFFECT_CSV, tmp_path)
    _diagnostics(run_id, tmp_path)

    first = workbench_tasks.build_validation_tasks(run_id, run_dir)
    second = workbench_tasks.build_validation_tasks(run_id, run_dir)

    assert first == second


def test_task_created_utc_is_deterministic_when_manifest_missing(tmp_path):
    run_id = "2026-01-02T03-04-05_partial_abc123"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "validation.json").write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "check_id": "monotone_cumulative",
                        "verdict": "warn",
                        "details": {"origin": "1984", "dev": 4},
                    }
                ]
            }
        )
        + "\n"
    )

    first = workbench_tasks.build_validation_tasks(run_id, run_dir)
    second = workbench_tasks.build_validation_tasks(run_id, run_dir)

    assert first == second
    assert first["tasks"][0]["created_utc"] == "2026-01-02T03:04:05Z"
