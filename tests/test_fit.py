import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from engine.base import UnsupportedMethodError
from engine.chainladder_adapter import ChainladderAdapter, parse_tail_param

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


# --- parse_tail_param ---------------------------------------------------


def test_parse_tail_none():
    assert parse_tail_param("none") == {"type": "none"}


def test_parse_tail_constant():
    assert parse_tail_param("constant:1.05") == {"type": "constant", "factor": 1.05}


def test_parse_tail_invalid_raises():
    with pytest.raises(ValueError):
        parse_tail_param("bogus")
    with pytest.raises(ValueError):
        parse_tail_param("constant:notanumber")


# --- adapter: capabilities / load_triangle -------------------------------


def test_capabilities_declares_mack_only_and_roadmap():
    caps = ChainladderAdapter().capabilities()
    assert caps["methods"] == ["mack"]
    assert set(caps["roadmap_methods"]) == {"bf", "capecod", "bootstrap"}
    assert caps["package"] == "chainladder"
    assert caps["adapter"] == "chainladder_adapter"


def test_load_triangle_valuation_year_convention():
    handle = ChainladderAdapter().load_triangle(RAA_CSV)
    assert handle.basis == "cumulative"
    assert handle.native.shape == (1, 1, 10, 10)


def test_load_triangle_development_age_convention(tmp_path):
    rows = [
        (1981, 12, 100.0), (1981, 24, 150.0),
        (1982, 12, 90.0),
    ]
    path = tmp_path / "triangle.csv"
    path.write_text(
        "origin,development,value\n" + "\n".join(f"{o},{d},{v}" for o, d, v in rows) + "\n"
    )
    handle = ChainladderAdapter().load_triangle(path)
    assert handle.native.shape == (1, 1, 2, 2)


# --- adapter: fit (mack) -------------------------------------------------


def test_fit_mack_base_case_totals():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    result = adapter.fit(handle, "mack", {"averaging": "volume"})
    assert result.totals["latest"] == pytest.approx(160987.0)
    assert result.totals["ultimate"] == pytest.approx(213122.228261, abs=1e-3)
    assert result.totals["ibnr"] == pytest.approx(52135.228261, abs=1e-3)
    assert len(result.by_origin) == 10
    assert len(result.development_factors) == 9  # 10 periods -> 9 transitions
    assert result.development_factors[0] == {
        "from_dev": 1,
        "to_dev": 2,
        "ldf": pytest.approx(2.9993586513353794),
        "sigma": pytest.approx(166.98347042160677),
    }


def test_fit_mack_mature_origin_has_zero_ibnr_not_nan():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    result = adapter.fit(handle, "mack", {"averaging": "volume"})
    origin_1981 = next(r for r in result.by_origin if r["origin"] == "1981")
    assert origin_1981["ibnr"] == 0.0
    assert origin_1981["mack_se"] == 0.0


def test_fit_unsupported_method_raises():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    with pytest.raises(UnsupportedMethodError):
        adapter.fit(handle, "bootstrap", {})


def test_fit_tail_constant_increases_ultimate():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    base = adapter.fit(handle, "mack", {"averaging": "volume", "tail": {"type": "none"}})
    tailed = adapter.fit(
        handle, "mack", {"averaging": "volume", "tail": {"type": "constant", "factor": 1.05}}
    )
    assert tailed.totals["ultimate"] > base.totals["ultimate"]
    assert tailed.development_factors[-1] == {
        "from_dev": 10,
        "to_dev": "ult",
        "ldf": 1.05,
        "sigma": None,
    }


def test_fit_exclude_origins_changes_totals_and_tolerates_zero_transition_origin():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    base = adapter.fit(handle, "mack", {"averaging": "volume"})
    # 1990 has a single observed diagonal (no link ratios) — excluding it
    # must not crash, and since it contributes nothing to LDF selection
    # anyway, totals should be identical to the unexcluded base case.
    excl_newest = adapter.fit(
        handle, "mack", {"averaging": "volume", "excluded_origins": ["1990"]}
    )
    assert excl_newest.totals["ibnr"] == pytest.approx(base.totals["ibnr"])

    excl_mid = adapter.fit(
        handle, "mack", {"averaging": "volume", "excluded_origins": ["1985"]}
    )
    assert excl_mid.totals["ibnr"] != pytest.approx(base.totals["ibnr"])
    assert excl_mid.parameters["excluded_origins"] == ["1985"]


def test_fit_exclude_oldest_origin_propagates_undefined_not_masked_or_faked():
    # Excluding 1981 removes the only origin with data at the final
    # (108-120) transition, leaving that LDF genuinely undefined — which
    # Mack's std-error recursion correctly can't compute (total mack_se
    # must come back non-finite, not be silently dropped from a sum). But
    # 1982 becomes fully-developed under this scenario (its own ultimate
    # equals its latest) — that origin's IBNR/mack_se must be exactly 0.0,
    # not left as chainladder's raw NaN, since a 0/0 in a fully-matured
    # origin is analytically zero, not undefined. Getting either direction
    # wrong is a fabrication: reporting a real number when the underlying
    # quantity is actually unknown, or reporting NaN for what a fully
    # matured origin unambiguously means (zero reserve, zero uncertainty).
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    result = adapter.fit(handle, "mack", {"averaging": "volume", "excluded_origins": ["1981"]})

    assert not math.isfinite(result.totals["mack_se"])
    assert math.isfinite(result.totals["ibnr"])  # ibnr stays defined for every remaining origin

    by_origin = {row["origin"]: row for row in result.by_origin}
    assert by_origin["1982"]["latest"] == by_origin["1982"]["ultimate"]  # fully developed here
    assert by_origin["1982"]["ibnr"] == 0.0
    assert by_origin["1982"]["mack_se"] == 0.0
    for origin in ("1983", "1984", "1985", "1986", "1987", "1988", "1989", "1990"):
        assert not math.isfinite(by_origin[origin]["mack_se"])


def test_fit_n_periods_and_simple_averaging_do_not_crash():
    adapter = ChainladderAdapter()
    handle = adapter.load_triangle(RAA_CSV)
    result = adapter.fit(
        handle, "mack", {"averaging": "simple", "n_periods": 5}
    )
    assert result.totals["ultimate"] > result.totals["latest"]


# --- CLI integration ------------------------------------------------------


def test_cli_fit_raa_exit_0_matches_totals(tmp_path):
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["ibnr"] == pytest.approx(52135.228261, abs=1e-3)

    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "fit.json").is_file()
    # v0.1.9: fit always persists validation.json now (previously fail-only)
    # — needed so the report renderer can highlight warn-class cells.
    assert (run_dir / "validation.json").is_file()
    assert (run_dir / "triangle.json").is_file()
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["exit_code"] == 0
    assert manifest_payload["engine"] == {
        "adapter": "chainladder_adapter",
        "package": "chainladder",
        "version": "0.9.2",
    }


def test_cli_fit_bad_triangle_exit_2_persists_validation_json(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("origin,value\n1981,100\n")
    result = _run_cli(
        "fit", str(bad_csv), "--method", "mack", "--format", "json", "--out", str(tmp_path / "runs")
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "fail"

    run_dirs = list((tmp_path / "runs").iterdir())
    run_dir = run_dirs[0]
    assert (run_dir / "validation.json").is_file()
    assert not (run_dir / "fit.json").exists()
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["exit_code"] == 2
    assert manifest_payload["engine"] is None


def test_cli_fit_unsupported_method_exit_4_no_run_persisted(tmp_path):
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "bf", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 4
    assert list(tmp_path.iterdir()) == []


def test_cli_fit_dry_run_writes_nothing(tmp_path):
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "mack",
        "--format",
        "json",
        "--out",
        str(tmp_path),
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["totals"]["ibnr"] == pytest.approx(52135.228261, abs=1e-3)
    assert list(tmp_path.iterdir()) == []
    assert "[dry-run] would write" in result.stderr
