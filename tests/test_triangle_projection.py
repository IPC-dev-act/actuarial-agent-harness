import pytest

from harness import triangle_projection


def test_fully_observed_origin_has_no_projected_cells():
    actual = [
        {"origin": "1981", "dev": 1, "value": 100.0},
        {"origin": "1981", "dev": 2, "value": 150.0},
    ]
    development_factors = [{"from_dev": 1, "to_dev": 2, "ldf": 1.5, "sigma": 0.1}]
    cells = triangle_projection.build_cells(actual, development_factors)
    assert cells == [
        {"origin": "1981", "dev": 1, "value": 100.0, "type": "actual"},
        {"origin": "1981", "dev": 2, "value": 150.0, "type": "actual"},
    ]


def test_partial_origin_projects_forward_from_latest_actual():
    actual = [
        {"origin": "1981", "dev": 1, "value": 100.0},
        {"origin": "1981", "dev": 2, "value": 150.0},
        {"origin": "1982", "dev": 1, "value": 80.0},
    ]
    development_factors = [
        {"from_dev": 1, "to_dev": 2, "ldf": 1.5, "sigma": 0.1},
    ]
    cells = triangle_projection.build_cells(actual, development_factors)
    by_key = {(c["origin"], c["dev"]): c for c in cells}
    assert by_key[("1982", 1)]["type"] == "actual"
    assert by_key[("1982", 1)]["value"] == 80.0
    assert by_key[("1982", 2)]["type"] == "projected"
    assert by_key[("1982", 2)]["value"] == pytest.approx(80.0 * 1.5)


def test_tail_synthetic_entry_ignored_grid_stays_bounded_to_input_devs():
    actual = [{"origin": "1981", "dev": 1, "value": 100.0}]
    development_factors = [
        {"from_dev": 1, "to_dev": 2, "ldf": 1.5, "sigma": 0.1},
        {"from_dev": 2, "to_dev": "ult", "ldf": 1.05, "sigma": None},
    ]
    cells = triangle_projection.build_cells(actual, development_factors)
    devs_present = {c["dev"] for c in cells}
    assert devs_present == {1, 2}  # not 3 — the tail entry doesn't extend the grid


def test_undefined_ldf_propagates_as_null_not_fabricated():
    actual = [
        {"origin": "1981", "dev": 1, "value": 100.0},
        {"origin": "1981", "dev": 2, "value": 150.0},
        {"origin": "1981", "dev": 3, "value": 180.0},
    ]
    development_factors = [
        {"from_dev": 1, "to_dev": 2, "ldf": 1.5, "sigma": 0.1},
        {"from_dev": 2, "to_dev": 3, "ldf": None, "sigma": None},
    ]
    actual_thin = [{"origin": "1982", "dev": 1, "value": 80.0}]
    cells = triangle_projection.build_cells(actual + actual_thin, development_factors)
    by_key = {(c["origin"], c["dev"]): c for c in cells}
    # dev1->dev2 uses a well-defined LDF (1.5) — only the dev2->dev3
    # transition is null, so dev=2 is fine and dev=3 is where it breaks.
    assert by_key[("1982", 2)]["value"] == pytest.approx(80.0 * 1.5)
    assert by_key[("1982", 3)]["value"] is None  # stays undefined once broken, not reset


def test_multiple_origins_sorted_numerically_in_output():
    actual = [
        {"origin": "1990", "dev": 1, "value": 1.0},
        {"origin": "1981", "dev": 1, "value": 1.0},
        {"origin": "1985", "dev": 1, "value": 1.0},
    ]
    cells = triangle_projection.build_cells(actual, [])
    assert [c["origin"] for c in cells] == ["1981", "1985", "1990"]


def test_matches_chainladder_full_triangle_for_real_raa_origin_1990():
    # Empirically verified once against chainladder's own full_triangle_
    # (session notes) — pinned here as a regression check using fit's own
    # real RAA development_factors, not synthetic numbers.
    ldfs = [
        2.9993586513353794, 1.6235227537534538, 1.2708881150356526,
        1.1716746330883747, 1.113384886206463, 1.0419346379110106,
        1.033263553789384, 1.0169364810075625, 1.0092165898617511,
    ]
    development_factors = [
        {"from_dev": i + 1, "to_dev": i + 2, "ldf": ldf, "sigma": 1.0}
        for i, ldf in enumerate(ldfs)
    ]
    actual = [{"origin": "1990", "dev": 1, "value": 2063.0}]
    cells = triangle_projection.build_cells(actual, development_factors)
    by_dev = {c["dev"]: c["value"] for c in cells}
    assert by_dev[2] == pytest.approx(6187.676898, abs=1e-5)
    assert by_dev[10] == pytest.approx(18402.442529, abs=1e-5)
