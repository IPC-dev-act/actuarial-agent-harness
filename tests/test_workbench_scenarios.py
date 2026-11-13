import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )


def _fit(tmp_path: Path) -> tuple[str, Path, dict]:
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return payload["run_id"], tmp_path / payload["run_id"], payload


def _sensitivity(run_id: str, tmp_path: Path) -> dict:
    result = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _scenarios(run_id: str, tmp_path: Path) -> dict:
    result = _run_cli("scenarios", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _tasks(run_id: str, tmp_path: Path) -> dict:
    result = _run_cli("tasks", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _decision_payload(decision_id: str, run_id: str, task_id: str, scenario_id: str) -> dict:
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": task_id,
        "decision_type": "scenario_selection",
        "status": "accepted",
        "rationale": "",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": ["fit.json", "sensitivity.json", "scenario_index.json"],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": scenario_id,
        "supersedes_decision_id": None,
    }


def _commit_decision(run_id: str, tmp_path: Path, decision: dict) -> subprocess.CompletedProcess:
    decision_file = tmp_path / f"{decision['decision_id']}.json"
    decision_file.write_text(json.dumps(decision, indent=2) + "\n")
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


def test_scenarios_indexes_base_and_sensitivity_candidates(tmp_path):
    run_id, run_dir, fit_payload = _fit(tmp_path)
    sensitivity_payload = _sensitivity(run_id, tmp_path)

    payload = _scenarios(run_id, tmp_path)

    assert payload["run_id"] == run_id
    assert payload["status"] == "available"
    by_id = {scenario["scenario_id"]: scenario for scenario in payload["scenarios"]}
    assert "base" in by_id
    assert "drop_oldest_origin" in by_id
    assert by_id["base"]["scenario_type"] == "base"
    assert by_id["drop_oldest_origin"]["scenario_type"] == "exclusion"
    assert by_id["base"]["key_metrics"]["latest"] == fit_payload["totals"]["latest"]
    assert by_id["drop_oldest_origin"]["key_metrics"]["ibnr"] == next(
        row for row in sensitivity_payload["scenarios"] if row["scenario_id"] == "drop_oldest_origin"
    )["totals"]["ibnr"]
    assert "fit.json" in by_id["base"]["input_hashes"]
    assert "sensitivity.json" in by_id["drop_oldest_origin"]["input_hashes"]
    assert (run_dir / "scenario_index.json").is_file()

    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["outputs"][-1] == "scenario_index.json"
    assert manifest_payload["exit_code"] == 0


def test_compare_writes_candidate_comparison_against_base(tmp_path):
    run_id, run_dir, fit_payload = _fit(tmp_path)
    sensitivity_payload = _sensitivity(run_id, tmp_path)
    candidate = next(
        row for row in sensitivity_payload["scenarios"] if row["scenario_id"] == "drop_oldest_origin"
    )

    result = _run_cli(
        "compare",
        run_id,
        "--scenario-id",
        "drop_oldest_origin",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["base_run_id"] == run_id
    assert payload["candidate_scenario_id"] == "drop_oldest_origin"
    assert payload["compared_metrics"]["ibnr"]["base"] == fit_payload["totals"]["ibnr"]
    assert payload["compared_metrics"]["ibnr"]["candidate"] == candidate["totals"]["ibnr"]
    assert payload["deltas"]["ibnr"] == candidate["totals"]["ibnr"] - fit_payload["totals"]["ibnr"]
    assert "scenario_index.json" in payload["source_artifacts"]
    assert "sensitivity.json" in payload["source_artifacts"]
    assert (run_dir / "comparisons" / f"{payload['comparison_id']}.json").is_file()


def test_scenario_selection_decision_requires_indexed_scenario(tmp_path):
    run_id, run_dir, _fit_payload = _fit(tmp_path)
    _sensitivity(run_id, tmp_path)
    _scenarios(run_id, tmp_path)
    scenario_task = next(
        task for task in _tasks(run_id, tmp_path)["tasks"] if task["task_type"] == "scenario_selection"
    )
    decision = _decision_payload(
        "select_drop_oldest_origin",
        run_id,
        scenario_task["task_id"],
        "drop_oldest_origin",
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 0, result.stderr
    written = json.loads((run_dir / "decisions" / "select_drop_oldest_origin.json").read_text())
    assert written["resulting_scenario_id"] == "drop_oldest_origin"
    assert "scenario_index.json" in written["input_hashes"]


def test_scenario_selection_rejects_unknown_scenario_id(tmp_path):
    run_id, _run_dir, _fit_payload = _fit(tmp_path)
    _sensitivity(run_id, tmp_path)
    _scenarios(run_id, tmp_path)
    scenario_task = next(
        task for task in _tasks(run_id, tmp_path)["tasks"] if task["task_type"] == "scenario_selection"
    )
    decision = _decision_payload(
        "select_missing_scenario",
        run_id,
        scenario_task["task_id"],
        "not_a_real_scenario",
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 4
    assert "resulting_scenario_id does not exist" in result.stderr


def test_scenario_selection_rejects_stale_scenario_index(tmp_path):
    run_id, run_dir, _fit_payload = _fit(tmp_path)
    _sensitivity(run_id, tmp_path)
    _scenarios(run_id, tmp_path)
    sensitivity_path = run_dir / "sensitivity.json"
    sensitivity_payload = json.loads(sensitivity_path.read_text())
    sensitivity_payload["scenarios"][0]["totals"]["ibnr"] += 1
    sensitivity_path.write_text(json.dumps(sensitivity_payload, indent=2) + "\n")
    scenario_task = next(
        task for task in _tasks(run_id, tmp_path)["tasks"] if task["task_type"] == "scenario_selection"
    )
    decision = _decision_payload(
        "select_from_stale_index",
        run_id,
        scenario_task["task_id"],
        "drop_oldest_origin",
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 4
    assert "scenario_index entry is stale" in result.stderr


def test_scenario_selection_requires_materialized_scenario_index(tmp_path):
    run_id, _run_dir, _fit_payload = _fit(tmp_path)
    _sensitivity(run_id, tmp_path)
    scenario_task = next(
        task for task in _tasks(run_id, tmp_path)["tasks"] if task["task_type"] == "scenario_selection"
    )
    decision = _decision_payload(
        "select_without_index",
        run_id,
        scenario_task["task_id"],
        "drop_oldest_origin",
    )

    result = _commit_decision(run_id, tmp_path, decision)

    assert result.returncode == 4
    assert "scenario_index.json" in result.stderr
