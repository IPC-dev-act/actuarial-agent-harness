import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- fit: snapshot is written and recorded ---------------------------------


def test_fit_writes_snapshot_and_records_it_in_manifest(tmp_path):
    result = _run_cli("fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    run_dir = tmp_path / run_id

    snapshot_path = run_dir / "inputs" / "raa.csv"
    assert snapshot_path.is_file()
    assert snapshot_path.read_bytes() == RAA_CSV.read_bytes()

    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    input_entry = manifest_payload["inputs"][0]
    assert input_entry["snapshot"] == "inputs/raa.csv"
    assert input_entry["sha256"] is not None


def test_fit_dry_run_writes_no_snapshot(tmp_path):
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path), "--dry-run"
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_fit_validate_failure_run_still_gets_snapshot(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("origin,value\n1981,100\n")  # missing the dev column -> fail-class
    result = _run_cli(
        "fit", str(bad_csv), "--method", "mack", "--format", "json", "--out", str(tmp_path / "runs")
    )
    assert result.returncode == 2
    run_dir = next((tmp_path / "runs").iterdir())
    assert (run_dir / "inputs" / "bad.csv").is_file()
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["inputs"][0]["snapshot"] == "inputs/bad.csv"


# --- diagnostics/sensitivity: replay from the snapshot ---------------------


def test_diagnostics_replays_from_snapshot_even_after_original_deleted_and_cwd_changed(tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    local_csv = workdir / "raa.csv"
    local_csv.write_bytes(RAA_CSV.read_bytes())

    fit_result = _run_cli(
        "fit", "raa.csv", "--method", "mack", "--format", "json", "--out", "runs", cwd=workdir
    )
    assert fit_result.returncode == 0, fit_result.stderr
    run_id = json.loads(fit_result.stdout)["run_id"]

    # The original file is deleted and we invoke from a totally different
    # cwd — if diagnostics still depended on the originally recorded
    # relative path, this would now fail (file gone, and even if it
    # existed, "raa.csv" wouldn't resolve from this cwd).
    local_csv.unlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    diag_result = _run_cli(
        "diagnostics", run_id, "--format", "json", "--out", str(workdir / "runs"), cwd=elsewhere
    )
    assert diag_result.returncode in (0, 3), diag_result.stderr
    payload = json.loads(diag_result.stdout)
    assert payload["run_id"] == run_id


def test_sensitivity_replays_from_snapshot_even_after_original_deleted(tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    local_csv = workdir / "raa.csv"
    local_csv.write_bytes(RAA_CSV.read_bytes())

    fit_result = _run_cli(
        "fit", "raa.csv", "--method", "mack", "--format", "json", "--out", "runs", cwd=workdir
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    local_csv.unlink()

    sens_result = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(workdir / "runs"))
    assert sens_result.returncode == 0, sens_result.stderr


def test_diagnostics_refuses_when_snapshot_tampered(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    run_dir = tmp_path / run_id

    snapshot_path = run_dir / "inputs" / "raa.csv"
    snapshot_path.write_text("origin,dev,value\n1981,1,999\n")

    diag_result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    assert diag_result.returncode == 1
    payload = json.loads(diag_result.stdout)
    assert payload["error"] == "input_integrity_violation"
    assert payload["expected_sha256"] != payload["actual_sha256"]

    # diagnostics.json must not have been written on an integrity refusal.
    assert not (run_dir / "diagnostics.json").exists()


def test_sensitivity_refuses_when_snapshot_tampered(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    run_dir = tmp_path / run_id
    (run_dir / "inputs" / "raa.csv").write_text("origin,dev,value\n1981,1,999\n")

    sens_result = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))
    assert sens_result.returncode == 1
    payload = json.loads(sens_result.stdout)
    assert payload["error"] == "input_integrity_violation"


# --- legacy (pre-v0.1.12, no "snapshot" key) fallback ----------------------


def _make_legacy_run(tmp_path: Path) -> tuple[str, Path]:
    """Fits a run, then strips its manifest's "snapshot" key and deletes the
    snapshot file, simulating a run folder minted before v0.1.12.
    """
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    run_dir = tmp_path / run_id
    shutil.rmtree(run_dir / "inputs")

    manifest_path = run_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text())
    del manifest_payload["inputs"][0]["snapshot"]
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n")
    return run_id, run_dir


def test_legacy_run_falls_back_to_recorded_path_when_it_still_matches(tmp_path):
    run_id, _run_dir = _make_legacy_run(tmp_path)
    # RAA_CSV itself (the recorded path) is untouched, so the fallback
    # should succeed using it directly.
    diag_result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    assert diag_result.returncode in (0, 3), diag_result.stderr


def test_legacy_run_refuses_when_recorded_path_no_longer_matches(tmp_path):
    run_id, run_dir = _make_legacy_run(tmp_path)
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())

    # Point the recorded path at a file with different content instead of
    # mutating examples/raa.csv itself (CLAUDE.md: never modify inputs).
    tampered = tmp_path / "tampered_raa.csv"
    tampered.write_text("origin,dev,value\n1981,1,999\n")
    manifest_payload["inputs"][0]["path"] = str(tampered)
    (run_dir / "manifest.json").write_text(json.dumps(manifest_payload, indent=2) + "\n")

    diag_result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    assert diag_result.returncode == 1
    payload = json.loads(diag_result.stdout)
    assert payload["error"] == "input_integrity_violation"
    assert payload["path_checked"] == str(tampered)
