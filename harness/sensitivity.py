"""Sensitivity grid (docs/cli-spec.md `sensitivity`).

Not in engine/base.py's EngineAdapter contract — ARCHITECTURE.md's ABC has
no sensitivity() method, deliberately: a sensitivity grid is just repeated
calls to fit() with different parameters, so every adapter gets it for
free. Engine-agnostic, no chainladder import.
"""

from __future__ import annotations

import math
from pathlib import Path

from harness import triangle_io

DEFAULT_TAIL_CANDIDATES = (1.00, 1.02, 1.05)
DEFAULT_N_PERIODS_CANDIDATES = (3, 5, None)


def triangle_origins_and_valuations(path: Path) -> tuple[list[str], list[int]]:
    """All distinct origins (sorted, string) and valuation years (sorted,
    int) observed in the triangle — needed to resolve "drop oldest origin"
    / "drop latest diagonal" into concrete values."""
    normalized, error = triangle_io.load_and_normalize(path)
    if error is not None:
        raise ValueError(f"could not parse {path} for sensitivity grid: {error}")
    origins = sorted(normalized["origin"].unique(), key=int)
    valuations = sorted(int(v) for v in normalized["valuation_year"].unique())
    return origins, valuations


def build_default_grid(
    base_params: dict, all_origins: list[str], all_valuations: list[int]
) -> list[dict]:
    """Builds the concrete scenario list for `--grid default`
    (docs/cli-spec.md): drop oldest origin; drop latest diagonal; simple vs
    volume averaging; n-periods in {3, 5, all}; constant tail in
    {1.00, 1.02, 1.05}. Any entry identical to `base_params` is skipped —
    a "perturbation" that doesn't actually change anything isn't
    informative. Each returned entry is
    {"scenario_id", "delta_from_base": {"parameter", "value"}, "param_overrides"}.
    """
    base_excluded_origins = list(base_params.get("excluded_origins") or [])
    base_excluded_valuations = list(base_params.get("excluded_valuations") or [])
    scenarios: list[dict] = []

    oldest_origin = all_origins[0]
    if oldest_origin not in base_excluded_origins:
        scenarios.append(
            {
                "scenario_id": "drop_oldest_origin",
                "delta_from_base": {"parameter": "excluded_origins", "value": oldest_origin},
                "param_overrides": {
                    "excluded_origins": base_excluded_origins + [oldest_origin]
                },
            }
        )

    latest_valuation = str(all_valuations[-1])
    if latest_valuation not in base_excluded_valuations:
        scenarios.append(
            {
                "scenario_id": "drop_latest_diagonal",
                "delta_from_base": {"parameter": "excluded_valuations", "value": latest_valuation},
                "param_overrides": {
                    "excluded_valuations": base_excluded_valuations + [latest_valuation]
                },
            }
        )

    base_averaging = base_params.get("averaging", "volume")
    alt_averaging = "simple" if base_averaging == "volume" else "volume"
    scenarios.append(
        {
            "scenario_id": f"averaging_{alt_averaging}",
            "delta_from_base": {"parameter": "averaging", "value": alt_averaging},
            "param_overrides": {"averaging": alt_averaging},
        }
    )

    base_n_periods = base_params.get("n_periods")
    for n in DEFAULT_N_PERIODS_CANDIDATES:
        if n != base_n_periods:
            scenarios.append(
                {
                    "scenario_id": f"n_periods_{n if n is not None else 'all'}",
                    "delta_from_base": {"parameter": "n_periods", "value": n},
                    "param_overrides": {"n_periods": n},
                }
            )

    base_tail = base_params.get("tail", "none")
    for factor in DEFAULT_TAIL_CANDIDATES:
        candidate = f"constant:{factor}"
        if candidate != base_tail:
            scenarios.append(
                {
                    "scenario_id": f"tail_constant_{factor}",
                    "delta_from_base": {"parameter": "tail", "value": candidate},
                    # kept as the same raw string form as base_params's own
                    # "tail" (matching fit.json's persisted schema) — every
                    # param_overrides value stays in that raw form; the one
                    # conversion to the adapter's runtime dict form happens
                    # in one place, right before adapter.fit() is called.
                    "param_overrides": {"tail": candidate},
                }
            )

    return scenarios


def apply_overrides(base_params: dict, overrides: dict) -> dict:
    merged = dict(base_params)
    merged.update(overrides)
    return merged


def compute_range(base_ibnr: float, scenario_ibnr_values: list[float]) -> dict:
    """min()/max() over a list that may contain NaN (a scenario whose
    ibnr is genuinely undefined) is unsafe either way: mixed with None it
    raises TypeError; mixed with raw NaN floats it silently returns a
    wrong, comparison-order-dependent result without ever raising (NaN
    comparisons are always False). Non-finite values are excluded from the
    range aggregate — a scenario with an undefined total still reports
    that in its own row, but doesn't corrupt everyone else's min/max.
    """
    finite_values = [v for v in ([base_ibnr] + scenario_ibnr_values) if math.isfinite(v)]
    return {
        "ibnr_min": min(finite_values) if finite_values else float("nan"),
        "ibnr_max": max(finite_values) if finite_values else float("nan"),
        "base_ibnr": base_ibnr,
    }
