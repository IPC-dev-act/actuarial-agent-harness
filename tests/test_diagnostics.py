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
        timeout=60,
    )


def test_diagnostics_unknown_run_id_exit_4(tmp_path):
    result = _run_cli("diagnostics", "does-not-exist", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 4


def test_diagnostics_on_validate_only_run_exit_4(tmp_path):
    _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    # validation.json has no run_id field (docs/cli-spec.md) — read it from
    # the folder name instead, same way an agent would after `reserve
    # runs list`.
    run_id = next(p.name for p in tmp_path.iterdir())

    result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 4


def test_diagnostics_raa_base_case_shared_manifest_and_exit_code(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]

    diag_result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    payload = json.loads(diag_result.stdout)
    assert {t["test_id"] for t in payload["tests"]} == {
        "dev_correlation",
        "calendar_year_effect",
        "residual_pattern_dev",
        "residual_pattern_origin",
        "outlier_link_ratios",
    }
    assert payload["overall"] in ("pass", "warn")
    assert diag_result.returncode == (0 if payload["overall"] == "pass" else 3)

    run_dir = tmp_path / run_id
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["outputs"] == [
        "validation.json",
        "fit.json",
        "triangle.json",
        "diagnostics.json",
    ]
    assert manifest_payload["exit_code"] == diag_result.returncode
    assert manifest_payload["command"].startswith("reserve fit")  # provenance untouched


def test_diagnostics_dry_run_writes_nothing_but_still_shows_result(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    run_dir = tmp_path / run_id
    manifest_before = json.loads((run_dir / "manifest.json").read_text())

    result = _run_cli(
        "diagnostics", run_id, "--format", "json", "--out", str(tmp_path), "--dry-run"
    )
    payload = json.loads(result.stdout)
    assert result.returncode == (0 if payload["overall"] == "pass" else 3)
    assert not (run_dir / "diagnostics.json").exists()
    assert "[dry-run] would write" in result.stderr

    manifest_after = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_after == manifest_before  # untouched — no outputs/exit_code changes


def test_diagnostics_text_format_renders(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    result = _run_cli("diagnostics", run_id, "--format", "text", "--out", str(tmp_path))
    assert "overall:" in result.stdout
