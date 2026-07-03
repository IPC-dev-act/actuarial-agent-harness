import json
import math
import subprocess
import sys
from pathlib import Path

from harness import sensitivity

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


# --- compute_range: min()/max() are unsafe over a list that may contain
# None (fit.json is already sanitized) or raw NaN (fit.json is not yet
# sanitized at this point) — synthetic values here since chainladder's
# deterministic ultimate/ibnr path turned out to be robust enough that no
# real RAA exclusion combination naturally drives it non-finite (only
# mack_se, Mack's separate stochastic calc, goes non-finite in practice).


def test_compute_range_all_finite():
    r = sensitivity.compute_range(100.0, [90.0, 110.0, 105.0])
    assert r == {"ibnr_min": 90.0, "ibnr_max": 110.0, "base_ibnr": 100.0}


def test_compute_range_excludes_nonfinite_scenario_from_min_max():
    r = sensitivity.compute_range(100.0, [90.0, float("nan"), 110.0])
    assert r["ibnr_min"] == 90.0
    assert r["ibnr_max"] == 110.0
    assert r["base_ibnr"] == 100.0


def test_compute_range_all_nonfinite_returns_nan_not_a_crash():
    r = sensitivity.compute_range(float("nan"), [float("nan"), float("nan")])
    assert math.isnan(r["ibnr_min"])
    assert math.isnan(r["ibnr_max"])


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- harness/sensitivity.py grid logic --------------------------------


def test_triangle_origins_and_valuations_raa():
    origins, valuations = sensitivity.triangle_origins_and_valuations(RAA_CSV)
    assert origins == [str(y) for y in range(1981, 1991)]
    assert valuations == list(range(1981, 1991))


def test_default_grid_base_case_has_all_dimensions():
    base_params = {
        "averaging": "volume",
        "tail": "none",
        "n_periods": None,
        "excluded_origins": [],
        "excluded_valuations": [],
    }
    grid = sensitivity.build_default_grid(
        base_params, [str(y) for y in range(1981, 1991)], list(range(1981, 1991))
    )
    scenario_ids = {s["scenario_id"] for s in grid}
    assert "drop_oldest_origin" in scenario_ids
    assert "drop_latest_diagonal" in scenario_ids
    assert "averaging_simple" in scenario_ids
    assert "n_periods_3" in scenario_ids
    assert "n_periods_5" in scenario_ids
    assert "n_periods_all" not in scenario_ids  # base n_periods already "all"
    assert "tail_constant_1.0" in scenario_ids
    assert "tail_constant_1.02" in scenario_ids
    assert "tail_constant_1.05" in scenario_ids


def test_default_grid_skips_entries_identical_to_base():
    base_params = {
        "averaging": "simple",
        "tail": "constant:1.02",
        "n_periods": 5,
        "excluded_origins": ["1981"],
        "excluded_valuations": [],
    }
    grid = sensitivity.build_default_grid(
        base_params, [str(y) for y in range(1981, 1991)], list(range(1981, 1991))
    )
    scenario_ids = {s["scenario_id"] for s in grid}
    assert "drop_oldest_origin" not in scenario_ids  # 1981 already excluded
    assert "averaging_volume" in scenario_ids  # alt of "simple"
    assert "n_periods_5" not in scenario_ids  # matches base
    assert "n_periods_3" in scenario_ids
    assert "n_periods_all" in scenario_ids
    assert "tail_constant_1.02" not in scenario_ids  # matches base
    assert "tail_constant_1.0" in scenario_ids


def test_apply_overrides_does_not_mutate_base():
    base = {"averaging": "volume", "n_periods": None}
    overridden = sensitivity.apply_overrides(base, {"averaging": "simple"})
    assert overridden["averaging"] == "simple"
    assert base["averaging"] == "volume"


# --- CLI integration ------------------------------------------------------


def test_cli_sensitivity_unknown_run_id_exit_4(tmp_path):
    result = _run_cli("sensitivity", "does-not-exist", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 4


def test_cli_sensitivity_non_default_grid_exit_4(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    result = _run_cli(
        "sensitivity", run_id, "--grid", "custom.json", "--format", "json", "--out", str(tmp_path)
    )
    assert result.returncode == 4


def test_cli_sensitivity_raa_base_case(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]

    result = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr  # sensitivity is always exit 0
    payload = json.loads(result.stdout)  # strict json.loads — no NaN tokens allowed
    assert payload["run_id"] == run_id
    assert len(payload["scenarios"]) == 8
    for row in payload["scenarios"]:
        assert set(row["totals"]) == {"ultimate", "ibnr", "mack_se"}
    assert payload["range"]["base_ibnr"] == json.loads(fit_result.stdout)["totals"]["ibnr"]
    assert payload["range"]["ibnr_min"] <= payload["range"]["base_ibnr"] <= payload["range"]["ibnr_max"]

    run_dir = tmp_path / run_id
    manifest_payload = json.loads((run_dir / "manifest.json").read_text())
    assert manifest_payload["outputs"] == [
        "validation.json",
        "fit.json",
        "triangle.json",
        "sensitivity.json",
    ]
    assert manifest_payload["exit_code"] == 0


def test_cli_sensitivity_non_finite_scenario_serializes_as_null_not_exit_3(tmp_path):
    # drop_oldest_origin removes 1981, the only origin with data at the
    # final (108-120) transition — that LDF (and everything downstream,
    # including mack_se) is genuinely undefined for that scenario. Must
    # come back as JSON null, not the invalid literal NaN token, and must
    # not affect sensitivity's own exit code (always 0 per docs/cli-spec.md).
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]

    result = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0
    assert "NaN" not in result.stdout
    payload = json.loads(result.stdout)
    drop_oldest = next(s for s in payload["scenarios"] if s["scenario_id"] == "drop_oldest_origin")
    assert drop_oldest["totals"]["mack_se"] is None


def test_cli_sensitivity_exclude_origins_layers_onto_every_scenario(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]

    unconstrained = _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))
    unconstrained_averaging = next(
        s for s in json.loads(unconstrained.stdout)["scenarios"] if s["scenario_id"] == "averaging_simple"
    )

    # 1985 has meaningful link ratios (mid-triangle, unlike 1990's single
    # diagonal) — excluding it via --exclude-origins should change results
    # even for a grid dimension (averaging) that never touches origins
    # itself, proving the baseline exclusion really reached every scenario
    # fit, not just ones the grid already perturbs on that axis.
    constrained = _run_cli(
        "sensitivity",
        run_id,
        "--exclude-origins",
        "1985",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert constrained.returncode == 0
    constrained_payload = json.loads(constrained.stdout)
    constrained_averaging = next(
        s for s in constrained_payload["scenarios"] if s["scenario_id"] == "averaging_simple"
    )
    assert constrained_averaging["totals"]["ibnr"] != unconstrained_averaging["totals"]["ibnr"]
    assert constrained_averaging["delta_from_base"] == unconstrained_averaging["delta_from_base"]
