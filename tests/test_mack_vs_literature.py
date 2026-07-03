"""Checks engine output against the published Mack literature figures.

Verified manually against the primary sources 2026-07-02 (VALIDATION.md) —
these are hard assertions, not xfail. Two datasets, two distinct papers, not
to be conflated (a correction applied throughout this repo, corridor of a
long-standing common misattribution):

- RAA (examples/raa.csv): Mack (1994), "Measuring the variability of chain
  ladder reserve estimates", CAS Spring Forum. Reserves AND standard errors
  verified exactly, the latter only under `--sigma-interpolation mack`
  (chainladder's own library default, "log-linear", understates SE for
  origins depending most on the extrapolated final-period sigma).
- GenIns (examples/genins.csv): Mack (1993), "Distribution-free calculation
  of the standard error of chain ladder reserve estimates", ASTIN Bulletin
  23(2), Table 2. Reserves verified; the paper's values are in 1000s.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"
GENINS_CSV = REPO_ROOT / "examples" / "genins.csv"

# Mack (1994), CAS Spring Forum — RAA triangle, Table of reserves and
# Mack standard errors by origin year. Standard errors verified under
# sigma_interpolation="mack" specifically (VALIDATION.md).
RAA_LITERATURE_IBNR_BY_ORIGIN = {
    "1981": 0.0,
    "1982": 154.0,
    "1983": 617.0,
    "1984": 1636.0,
    "1985": 2747.0,
    "1986": 3649.0,
    "1987": 5435.0,
    "1988": 10907.0,
    "1989": 10650.0,
    "1990": 16339.0,
}
RAA_LITERATURE_SE_BY_ORIGIN = {
    "1981": 0.0,
    "1982": 206.0,
    "1983": 623.0,
    "1984": 747.0,
    "1985": 1469.0,
    "1986": 2002.0,
    "1987": 2209.0,
    "1988": 5358.0,
    "1989": 6333.0,
    "1990": 24566.0,
}
RAA_LITERATURE_TOTALS = {
    "latest": 160987.0,
    "ultimate": 213122.0,
    "ibnr": 52135.0,
    "mack_se": 26909.0,
}

# Mack (1993), ASTIN Bulletin 23(2), Table 2 — GenIns/Taylor-Ashe triangle,
# chain ladder reserves by origin year, in 1000s. Origin 2001 (oldest) is
# fully developed; the paper's table starts from the first origin with a
# nonzero reserve, matching 2002 onward here.
GENINS_LITERATURE_IBNR_BY_ORIGIN_1000S = {
    "2001": 0.0,
    "2002": 95.0,
    "2003": 470.0,
    "2004": 710.0,
    "2005": 985.0,
    "2006": 1419.0,
    "2007": 2178.0,
    "2008": 3920.0,
    "2009": 4279.0,
    "2010": 4626.0,
}
GENINS_LITERATURE_TOTAL_IBNR_1000S = 18681.0


def _run_fit(csv_path: Path, out_dir: Path, *extra_args: str) -> dict:
    """Runs `reserve fit` and returns parsed fit.json."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "fit",
            str(csv_path),
            "--method",
            "mack",
            "--averaging",
            "volume",
            "--format",
            "json",
            "--out",
            str(out_dir),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode in (0, 3), (
        f"reserve fit exited {result.returncode}\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    payload = json.loads(result.stdout)
    run_id = payload["run_id"]
    fit_path = out_dir / run_id / "fit.json"
    return json.loads(fit_path.read_text())


# --- RAA vs Mack (1994) ---------------------------------------------------


def test_raa_totals_match_mack_1994(tmp_path):
    fit = _run_fit(RAA_CSV, tmp_path, "--sigma-interpolation", "mack")
    totals = fit["totals"]
    assert totals["latest"] == pytest.approx(RAA_LITERATURE_TOTALS["latest"], abs=0.5)
    assert totals["ultimate"] == pytest.approx(RAA_LITERATURE_TOTALS["ultimate"], abs=1.0)
    assert totals["ibnr"] == pytest.approx(RAA_LITERATURE_TOTALS["ibnr"], abs=1.0)
    assert totals["mack_se"] == pytest.approx(RAA_LITERATURE_TOTALS["mack_se"], abs=1.0)


def test_raa_per_origin_ibnr_matches_mack_1994(tmp_path):
    fit = _run_fit(RAA_CSV, tmp_path, "--sigma-interpolation", "mack")
    by_origin = {row["origin"]: row for row in fit["by_origin"]}
    for origin, expected_ibnr in RAA_LITERATURE_IBNR_BY_ORIGIN.items():
        assert origin in by_origin, f"origin {origin} missing from fit.json"
        assert by_origin[origin]["ibnr"] == pytest.approx(expected_ibnr, abs=1.0)


def test_raa_per_origin_mack_se_matches_mack_1994_under_mack_interpolation(tmp_path):
    fit = _run_fit(RAA_CSV, tmp_path, "--sigma-interpolation", "mack")
    assert fit["parameters"]["sigma_interpolation"] == "mack"
    by_origin = {row["origin"]: row for row in fit["by_origin"]}
    for origin, expected_se in RAA_LITERATURE_SE_BY_ORIGIN.items():
        assert by_origin[origin]["mack_se"] == pytest.approx(expected_se, abs=1.0)


def test_raa_mack_se_is_the_default_sigma_interpolation(tmp_path):
    # No explicit --sigma-interpolation: the default must already be "mack"
    # (docs/cli-spec.md v0.1.7), so this reproduces the same literature
    # match without the flag.
    fit = _run_fit(RAA_CSV, tmp_path)
    assert fit["parameters"]["sigma_interpolation"] == "mack"
    assert fit["totals"]["mack_se"] == pytest.approx(RAA_LITERATURE_TOTALS["mack_se"], abs=1.0)


# --- GenIns vs Mack (1993) -------------------------------------------------


def test_genins_per_origin_ibnr_matches_mack_1993_table_2(tmp_path):
    fit = _run_fit(GENINS_CSV, tmp_path)
    by_origin = {row["origin"]: row for row in fit["by_origin"]}
    for origin, expected_ibnr_1000s in GENINS_LITERATURE_IBNR_BY_ORIGIN_1000S.items():
        assert origin in by_origin, f"origin {origin} missing from fit.json"
        computed_1000s = by_origin[origin]["ibnr"] / 1000.0
        assert computed_1000s == pytest.approx(expected_ibnr_1000s, abs=1.0)


def test_genins_total_ibnr_matches_mack_1993_table_2(tmp_path):
    fit = _run_fit(GENINS_CSV, tmp_path)
    computed_1000s = fit["totals"]["ibnr"] / 1000.0
    assert computed_1000s == pytest.approx(GENINS_LITERATURE_TOTAL_IBNR_1000S, abs=1.0)
