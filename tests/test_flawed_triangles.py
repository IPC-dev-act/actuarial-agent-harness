"""Each synthetic flawed triangle (scripts/make_flawed_triangles.py) has one
deliberately injected pathology; each test here asserts that pathology's
expected check/test fires. Triangles are pre-generated into examples/ (not
regenerated per test run) so the CSVs stay stable, reviewable artifacts —
same treatment as examples/raa.csv.
"""

import json
import subprocess
import sys
from pathlib import Path

from harness import validation

REPO_ROOT = Path(__file__).resolve().parent.parent
GAPPED_CSV = REPO_ROOT / "examples" / "triangle_gapped.csv"
NONMONOTONE_CSV = REPO_ROOT / "examples" / "triangle_nonmonotone.csv"
CALENDAR_EFFECT_CSV = REPO_ROOT / "examples" / "triangle_calendar_effect.csv"
INCREMENTAL_CSV = REPO_ROOT / "examples" / "triangle_incremental.csv"
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"
GENINS_CSV = REPO_ROOT / "examples" / "genins.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_gapped_triangle_fails_no_gaps():
    result = validation.validate_triangle_csv(GAPPED_CSV)
    gaps_check = next(c for c in result.checks if c.check_id == "no_gaps")
    assert gaps_check.verdict == "fail"
    assert result.verdict == "fail"


def test_gapped_triangle_blocks_fit_at_exit_2(tmp_path):
    result = _run_cli(
        "fit", str(GAPPED_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "fail"


def test_nonmonotone_triangle_warns_but_does_not_block_validate():
    result = validation.validate_triangle_csv(NONMONOTONE_CSV)
    mono_check = next(c for c in result.checks if c.check_id == "monotone_cumulative")
    assert mono_check.verdict == "warn"
    assert result.verdict == "warn"  # not "fail" — v0.1.2


def test_nonmonotone_triangle_still_fits_successfully(tmp_path):
    result = _run_cli(
        "fit", str(NONMONOTONE_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode in (0, 3), result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["ultimate"] > 0


def test_calendar_effect_triangle_is_clean_at_validate():
    # The shock persists forward per origin, so each origin's own sequence
    # stays monotonic — validate should see nothing wrong structurally.
    result = validation.validate_triangle_csv(CALENDAR_EFFECT_CSV)
    assert result.verdict == "pass"


def test_calendar_effect_triangle_fires_calendar_year_effect_diagnostic(tmp_path):
    fit_result = _run_cli(
        "fit",
        str(CALENDAR_EFFECT_CSV),
        "--method",
        "mack",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert fit_result.returncode in (0, 3), fit_result.stderr
    run_id = json.loads(fit_result.stdout)["run_id"]

    diag_result = _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    assert diag_result.returncode == 3, diag_result.stderr
    payload = json.loads(diag_result.stdout)
    cy_test = next(t for t in payload["tests"] if t["test_id"] == "calendar_year_effect")
    assert cy_test["verdict"] == "warn"
    assert cy_test["statistic"] > cy_test["threshold"]
    assert payload["overall"] == "warn"


# --- basis mismatch (docs/cli-spec.md v0.1.10) -----------------------------


def test_incremental_triangle_validates_as_incremental_basis():
    # The generator already asserts this ground truth at build time
    # (scripts/make_flawed_triangles.py); re-asserted here so a future
    # regeneration that breaks it fails the test suite too, not just a
    # one-off script run.
    result = validation.validate_triangle_csv(INCREMENTAL_CSV)
    assert result.basis == "incremental"
    assert result.verdict == "pass"  # clean data — genuinely incremental, not flawed


def test_incremental_triangle_fit_refuses_exit_2_with_structured_error(tmp_path):
    result = _run_cli(
        "fit", str(INCREMENTAL_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "error": "unsupported_basis",
        "message": "engine adapter supports cumulative input only; inferred basis: incremental",
        "adapter_supported_basis": ["cumulative"],
        "inferred_basis": "incremental",
    }

    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "validation.json").is_file()
    assert not (run_dir / "fit.json").exists()
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["exit_code"] == 2
    assert manifest_payload["outputs"] == ["validation.json"]
    assert manifest_payload["engine"] is None


def test_cumulative_fixtures_unaffected_by_basis_check(tmp_path):
    for csv_path in (RAA_CSV, GENINS_CSV, NONMONOTONE_CSV, CALENDAR_EFFECT_CSV):
        assert validation.validate_triangle_csv(csv_path).basis == "cumulative"
        result = _run_cli(
            "fit", str(csv_path), "--method", "mack", "--format", "json", "--out", str(tmp_path)
        )
        assert result.returncode in (0, 3), (csv_path, result.stderr)
