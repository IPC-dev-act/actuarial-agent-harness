import json
import subprocess
import sys
from pathlib import Path

import pytest

from harness import validation

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _write_csv(tmp_path: Path, rows: list[tuple], columns=("origin", "development", "value")) -> Path:
    path = tmp_path / "triangle.csv"
    lines = [",".join(columns)]
    lines += [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


# --- clean data -------------------------------------------------------------


def test_raa_csv_structural_checks_pass_real_triangle_has_expected_warns():
    # RAA is a real incurred triangle: origin 1982 legitimately decreases
    # between age 84 and 96 (15599.0 -> 15496.0) — a case reserve
    # reduction, exactly the v0.1.2 warn-not-fail scenario, not a data bug.
    result = validation.validate_triangle_csv(RAA_CSV)
    verdicts = {c.check_id: c.verdict for c in result.checks}
    assert verdicts == {
        "file_readable": "pass",
        "origin_dev_parseable": "pass",
        "shape_triangular": "pass",
        "no_gaps": "pass",
        "basis_consistent": "pass",
        "monotone_cumulative": "warn",
        "nonneg_incrementals": "warn",
    }
    assert result.basis == "cumulative"
    assert result.dimensions == {"origins": 10, "devs": 10}
    assert result.verdict == "warn"  # warn-only must not block exit 0 / a fit


def test_development_age_convention_parses_equivalently(tmp_path):
    # Same shape as RAA's first 3 origins/4 devs, but development column
    # given as ages (12/24/36/48) instead of valuation years.
    rows = [
        (1981, 12, 100.0), (1981, 24, 150.0), (1981, 36, 170.0), (1981, 48, 180.0),
        (1982, 12, 90.0), (1982, 24, 140.0), (1982, 36, 160.0),
        (1983, 12, 80.0), (1983, 24, 120.0),
        (1984, 12, 70.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    assert result.verdict == "pass"
    assert result.dimensions == {"origins": 4, "devs": 4}


# --- fail-class ---------------------------------------------------------


def test_missing_file_fails_file_readable():
    result = validation.validate_triangle_csv(Path("/nonexistent/triangle.csv"))
    assert [c.check_id for c in result.checks] == ["file_readable"]
    assert result.checks[0].verdict == "fail"
    assert result.verdict == "fail"


def test_missing_required_column_fails_origin_dev_parseable(tmp_path):
    path = tmp_path / "triangle.csv"
    path.write_text("origin,value\n1981,100.0\n")
    result = validation.validate_triangle_csv(path)
    check_ids = [c.check_id for c in result.checks]
    assert check_ids == ["file_readable", "origin_dev_parseable"]
    assert result.checks[-1].verdict == "fail"
    assert "development" in result.checks[-1].details["missing_columns"]


def test_interior_gap_fails_no_gaps(tmp_path):
    # origin 1981 has devs 1 and 3 but not 2 (an interior hole)
    rows = [
        (1981, 1981, 100.0), (1981, 1983, 170.0),
        (1982, 1982, 90.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    gaps_check = next(c for c in result.checks if c.check_id == "no_gaps")
    assert gaps_check.verdict == "fail"
    assert result.verdict == "fail"


def test_newer_origin_with_more_development_fails_shape_triangular(tmp_path):
    # origin 1982 (newer) has 3 devs, origin 1981 (older) only has 2 — not
    # a valid staircase.
    rows = [
        (1981, 1981, 100.0), (1981, 1982, 150.0),
        (1982, 1982, 90.0), (1982, 1983, 140.0), (1982, 1984, 160.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    shape_check = next(c for c in result.checks if c.check_id == "shape_triangular")
    assert shape_check.verdict == "fail"
    assert result.verdict == "fail"


def test_tied_basis_votes_fail_basis_consistent(tmp_path):
    # one origin looks cumulative (increasing), one looks incremental
    # (decreasing) — a genuine tie, no single basis explains both.
    rows = [
        (1981, 1981, 100.0), (1981, 1982, 150.0),
        (1982, 1982, 150.0), (1982, 1983, 100.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    basis_check = next(c for c in result.checks if c.check_id == "basis_consistent")
    assert basis_check.verdict == "fail"
    assert result.verdict == "fail"
    assert result.basis is None


# --- warn-class (v0.1.2: must not block, exit stays 0) ----------------------


def test_interior_decrease_warns_monotone_cumulative_but_does_not_fail(tmp_path):
    # Incurred-style data: case reserve reduction between dev 2 and dev 3.
    rows = [
        (1981, 1981, 100.0), (1981, 1982, 150.0), (1981, 1983, 140.0), (1981, 1984, 160.0),
        (1982, 1982, 90.0), (1982, 1983, 130.0), (1982, 1984, 150.0),
        (1983, 1983, 80.0), (1983, 1984, 120.0),
        (1984, 1984, 70.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    mono_check = next(c for c in result.checks if c.check_id == "monotone_cumulative")
    assert mono_check.verdict == "warn"
    assert mono_check.details["origin"] == "1981"
    assert mono_check.details["values"] == [150.0, 140.0]
    assert result.verdict == "warn"  # not "fail" — must not block a fit
    assert result.basis == "cumulative"  # single interior dip doesn't flip inference


def test_negative_incremental_warns_but_does_not_fail(tmp_path):
    rows = [
        (1981, 1981, 100.0), (1981, 1982, 150.0), (1981, 1983, 140.0),
        (1982, 1982, 90.0), (1982, 1983, 130.0),
        (1983, 1983, 80.0),
    ]
    path = _write_csv(tmp_path, rows)
    result = validation.validate_triangle_csv(path)
    neg_check = next(c for c in result.checks if c.check_id == "nonneg_incrementals")
    assert neg_check.verdict == "warn"
    assert result.verdict == "warn"


# --- CLI integration ---------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_validate_raa_exit_0_and_writes_run_folder(tmp_path):
    result = _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr  # warn-class must not fail exit
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "warn"

    run_ids = list(tmp_path.iterdir())
    assert len(run_ids) == 1
    run_dir = run_ids[0]
    assert (run_dir / "validation.json").is_file()
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["exit_code"] == 0
    assert manifest_payload["outputs"] == ["validation.json"]
    assert manifest_payload["engine"] is None


def test_cli_validate_missing_file_exit_2(tmp_path):
    result = _run_cli(
        "validate", str(tmp_path / "nope.csv"), "--format", "json", "--out", str(tmp_path / "runs")
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "fail"


def test_cli_validate_text_format_is_human_readable(tmp_path):
    result = _run_cli("validate", str(RAA_CSV), "--format", "text", "--out", str(tmp_path))
    assert result.returncode == 0
    assert "verdict: WARN" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)
