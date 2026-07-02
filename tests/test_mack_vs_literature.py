"""Checks engine output against the published Mack (1993) RAA figures.

Written before any implementation exists (harness/cli.py, engine/*), per the
Phase 2 build order — every test here is expected to xfail until the CLI is
built (subprocess call fails outright), and to keep xfailing afterwards
because the literature comparison itself is not settled: fitting the actual
RAA triangle through chainladder 0.9.2 with volume-weighted averaging
reproduces the published reserve totals (52135.2 / 213122.2) but NOT the
published total standard error (26909) — chainladder's default tail-sigma
extrapolation for the final development period gives 26880.74, a known class
of divergence between Mack implementations documented in the actuarial
literature. Resolving that divergence (confirming which figure, if either,
this engine should be expected to match) needs a human actuary to check
against the original 1993 ASTIN Bulletin paper page-by-page — hence
`xfail(strict=False)`, never asserted as a hard pass here.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"

# Mack (1993), Table 2 (RAA triangle) — cumulative chain ladder reserves and
# their standard errors by origin year, plus totals. Transcribed from the
# commonly-reproduced literature values (also the worked example baked into
# docs/cli-spec.md's fit.json schema sample). NOT independently re-verified
# against the original paper page image — that verification is exactly what
# is pending.
LITERATURE_IBNR_BY_ORIGIN = {
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
LITERATURE_TOTALS = {
    "latest": 160987.0,
    "ultimate": 213122.0,
    "ibnr": 52135.0,
    "mack_se": 26909.0,
}


def _run_fit_raa(out_dir: Path) -> dict:
    """Runs `reserve fit` on the RAA sample and returns parsed fit.json.

    Any failure (CLI not implemented yet, non-zero exit, malformed output)
    raises from here, inside the test's call phase, so xfail catches it.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "fit",
            str(RAA_CSV),
            "--method",
            "mack",
            "--averaging",
            "volume",
            "--format",
            "json",
            "--out",
            str(out_dir),
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


@pytest.mark.xfail(reason="pending manual verification vs Mack 1993", strict=False)
def test_raa_totals_match_mack_1993(tmp_path):
    fit = _run_fit_raa(tmp_path)
    totals = fit["totals"]
    assert totals["latest"] == pytest.approx(LITERATURE_TOTALS["latest"], abs=0.5)
    assert totals["ultimate"] == pytest.approx(LITERATURE_TOTALS["ultimate"], abs=1.0)
    assert totals["ibnr"] == pytest.approx(LITERATURE_TOTALS["ibnr"], abs=1.0)
    assert totals["mack_se"] == pytest.approx(LITERATURE_TOTALS["mack_se"], abs=1.0)


@pytest.mark.xfail(reason="pending manual verification vs Mack 1993", strict=False)
def test_raa_per_origin_ibnr_matches_mack_1993(tmp_path):
    fit = _run_fit_raa(tmp_path)
    by_origin = {row["origin"]: row for row in fit["by_origin"]}
    for origin, expected_ibnr in LITERATURE_IBNR_BY_ORIGIN.items():
        assert origin in by_origin, f"origin {origin} missing from fit.json"
        assert by_origin[origin]["ibnr"] == pytest.approx(expected_ibnr, abs=1.0)
