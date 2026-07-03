"""--basis cumulative|incremental (docs/cli-spec.md v0.1.13): an optional
declaration on validate/fit, authoritative over the inference heuristic.
Two distinct conflict types are covered here: declared-vs-adapter-capability
(exit 2, unsupported_basis) and declared-vs-inference (basis_consistent
fails, "declared-vs-inferred conflict") — plus the undeclared path staying
byte-for-byte unchanged.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness import validation

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"
INCREMENTAL_CSV = REPO_ROOT / "examples" / "triangle_incremental.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- harness/validation.py: declared basis, unit level ---------------------


def test_declared_basis_agreeing_with_inference_passes_and_is_flagged_declared():
    result = validation.validate_triangle_csv(RAA_CSV, declared_basis="cumulative")
    basis_check = next(c for c in result.checks if c.check_id == "basis_consistent")
    assert basis_check.verdict == "pass"
    assert result.basis == "cumulative"
    assert result.basis_source == "declared"


def test_declared_basis_conflicting_with_inference_fails_basis_consistent():
    # triangle_incremental.csv is genuinely incremental (asserted by its own
    # generator and by test_flawed_triangles.py) — declaring "cumulative"
    # against it is a stated assumption the data doesn't support.
    result = validation.validate_triangle_csv(INCREMENTAL_CSV, declared_basis="cumulative")
    basis_check = next(c for c in result.checks if c.check_id == "basis_consistent")
    assert basis_check.verdict == "fail"
    assert basis_check.details["reason"].startswith("declared-vs-inferred conflict")
    assert basis_check.details["declared_basis"] == "cumulative"
    assert basis_check.details["inferred_basis"] == "incremental"
    assert result.basis is None
    assert result.verdict == "fail"


def test_declared_basis_matching_inference_on_incremental_file_passes():
    result = validation.validate_triangle_csv(INCREMENTAL_CSV, declared_basis="incremental")
    basis_check = next(c for c in result.checks if c.check_id == "basis_consistent")
    assert basis_check.verdict == "pass"
    assert result.basis == "incremental"
    assert result.basis_source == "declared"


def test_undeclared_basis_inference_unchanged(tmp_path):
    # (c): with no --basis, behaviour is byte-for-byte what it was before
    # v0.1.13 — same basis, same source label, same pass/warn/fail shape.
    result = validation.validate_triangle_csv(RAA_CSV)
    assert result.basis == "cumulative"
    assert result.basis_source == "inferred"
    basis_check = next(c for c in result.checks if c.check_id == "basis_consistent")
    assert basis_check.verdict == "pass"
    assert basis_check.details is None


# --- CLI: validate --basis --------------------------------------------------


def test_cli_validate_declared_basis_conflict_exit_2(tmp_path):
    result = _run_cli(
        "validate", str(INCREMENTAL_CSV), "--basis", "cumulative", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "fail"
    assert payload["basis_source"] == "declared"
    basis_check = next(c for c in payload["checks"] if c["check_id"] == "basis_consistent")
    assert basis_check["verdict"] == "fail"
    assert basis_check["details"]["declared_basis"] == "cumulative"

    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": None, "source": "declared"}


def test_cli_validate_declared_basis_records_manifest_parameters(tmp_path):
    result = _run_cli(
        "validate", str(RAA_CSV), "--basis", "cumulative", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": "cumulative", "source": "declared"}


def test_cli_validate_undeclared_basis_records_inferred_in_manifest(tmp_path):
    result = _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": "cumulative", "source": "inferred"}


def test_cli_validate_bad_basis_value_exit_4(tmp_path):
    result = _run_cli(
        "validate", str(RAA_CSV), "--basis", "bogus", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 4


# --- CLI: fit --basis --------------------------------------------------


def test_cli_fit_declared_incremental_refused_by_cumulative_only_adapter(tmp_path):
    # Declaring "incremental" against triangle_incremental.csv *agrees* with
    # inference (both conclude incremental) — basis_consistent passes, and
    # the refusal that follows is purely about adapter capability, isolating
    # this conflict type from the declared-vs-inferred one below.
    result = _run_cli(
        "fit",
        str(INCREMENTAL_CSV),
        "--method",
        "mack",
        "--basis",
        "incremental",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["error"] == "unsupported_basis"
    assert payload["basis_source"] == "declared"
    assert payload["inferred_basis"] == "incremental"
    assert "declared basis: incremental" in payload["message"]

    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": "incremental", "source": "declared"}
    assert not (run_dir / "fit.json").exists()


def test_cli_fit_declared_cumulative_on_incremental_file_validation_fails(tmp_path):
    # The other conflict type: declared basis disagrees with what inference
    # concludes — basis_consistent fails before the adapter is even
    # consulted, via the ordinary validate-first refusal path.
    result = _run_cli(
        "fit",
        str(INCREMENTAL_CSV),
        "--method",
        "mack",
        "--basis",
        "cumulative",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "fail"
    basis_check = next(c for c in payload["checks"] if c["check_id"] == "basis_consistent")
    assert basis_check["details"]["reason"].startswith("declared-vs-inferred conflict")

    run_dir = next(tmp_path.iterdir())
    assert not (run_dir / "fit.json").exists()


def test_cli_fit_declared_basis_matching_everything_succeeds(tmp_path):
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "mack",
        "--basis",
        "cumulative",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["ibnr"] == pytest.approx(52135.228261, abs=1e-3)

    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": "cumulative", "source": "declared"}


def test_cli_fit_undeclared_basis_unchanged(tmp_path):
    # (c): no --basis at all — same manifest shape as any pre-v0.1.13 fit,
    # just with an explicit "inferred" source label alongside it now.
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    run_dir = next(tmp_path.iterdir())
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["parameters"]["basis"] == {"value": "cumulative", "source": "inferred"}
