"""Synthetic flawed triangles with documented, seeded pathologies.

Each generated CSV starts from a clean synthetic base triangle — not
derived from any literature dataset, to keep it clearly separate from the
literature-verified examples/raa.csv — with exactly one pathology injected,
so tests/test_flawed_triangles.py can assert the specific check/test each
one is expected to fire. Build-time tooling only, like export_samples.py —
not part of the harness product.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
SEED = 20260702
N_ORIGINS = 8
FIRST_ORIGIN_YEAR = 2015
TRUE_LDFS = [2.2, 1.5, 1.25, 1.12, 1.06, 1.03, 1.01]  # 7 transitions -> 8 dev periods


def _base_triangle(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    origin_years = [FIRST_ORIGIN_YEAR + i for i in range(N_ORIGINS)]
    base_premium = 10_000 * (1.05 ** np.arange(N_ORIGINS)) * rng.uniform(0.9, 1.1, N_ORIGINS)

    rows = []
    for i, origin in enumerate(origin_years):
        cum = base_premium[i] * rng.uniform(0.35, 0.45)
        rows.append((origin, origin, cum))
        for k, ldf in enumerate(TRUE_LDFS):
            noise = rng.normal(1.0, 0.02)
            # Floor at a small guaranteed increment: noise alone could
            # occasionally dip cum*ldf*noise below the prior value, adding
            # an *incidental* non-monotone cell that would contaminate the
            # gapped/calendar_effect fixtures, which are meant to be clean
            # everywhere except their one deliberately injected flaw.
            cum = max(cum * ldf * noise, cum * 1.001)
            dev_year = origin + k + 1
            rows.append((origin, dev_year, cum))

    frame = pd.DataFrame(rows, columns=["origin", "development", "value"])
    max_valuation = max(origin_years)  # keep only the observed upper-left triangle
    frame = frame[frame["development"] <= max_valuation].reset_index(drop=True)
    frame["value"] = frame["value"].round(1)

    for _origin, group in frame.groupby("origin"):
        values = group.sort_values("development")["value"].tolist()
        assert values == sorted(values), "base triangle must be strictly monotonic by construction"
    return frame


def make_gapped(frame: pd.DataFrame) -> pd.DataFrame:
    """Removes one interior cell — origin 2017's 3rd observation. Expected
    to fire `no_gaps` (fail-class) at `reserve validate`."""
    origin = FIRST_ORIGIN_YEAR + 2
    devs = sorted(frame.loc[frame["origin"] == origin, "development"])
    drop_dev = devs[2]
    return frame[
        ~((frame["origin"] == origin) & (frame["development"] == drop_dev))
    ].reset_index(drop=True)


def make_nonmonotone(frame: pd.DataFrame) -> pd.DataFrame:
    """Shrinks one interior cell below its predecessor — a case reserve
    reduction on origin 2016's 4th observation. Expected to fire
    `monotone_cumulative` (warn-class, v0.1.2) at `reserve validate`, and
    must NOT block a subsequent fit."""
    frame = frame.copy()
    origin = FIRST_ORIGIN_YEAR + 1
    devs = sorted(frame.loc[frame["origin"] == origin, "development"])
    target_dev, prior_dev = devs[3], devs[2]
    prior_value = frame.loc[
        (frame["origin"] == origin) & (frame["development"] == prior_dev), "value"
    ].iloc[0]
    idx = frame[(frame["origin"] == origin) & (frame["development"] == target_dev)].index[0]
    frame.loc[idx, "value"] = round(prior_value * 0.9, 1)
    return frame


def make_calendar_effect(frame: pd.DataFrame, shock_valuation: int, factor: float = 1.35) -> pd.DataFrame:
    """Multiplies every cell at calendar valuation year `shock_valuation`
    or later by `factor` — a shock (e.g. a reserve strengthening exercise)
    hitting every open origin at the same valuation date and persisting
    afterward. Persisting the shock (rather than a single-diagonal-only
    bump) keeps each origin's own sequence monotonically increasing, so
    this stays clean at `reserve validate` and is only caught by
    `reserve diagnostics`'s `calendar_year_effect` test — the jump
    concentrates specifically at the transition into `shock_valuation` for
    every origin that reaches it, which is exactly the diagonal-clustering
    signal that test looks for."""
    frame = frame.copy()
    mask = frame["development"] >= shock_valuation
    frame.loc[mask, "value"] = (frame.loc[mask, "value"] * factor).round(1)
    return frame


def main() -> None:
    EXAMPLES_DIR.mkdir(exist_ok=True)
    base = _base_triangle()

    gapped_path = EXAMPLES_DIR / "triangle_gapped.csv"
    make_gapped(base).to_csv(gapped_path, index=False)

    nonmonotone_path = EXAMPLES_DIR / "triangle_nonmonotone.csv"
    make_nonmonotone(base).to_csv(nonmonotone_path, index=False)

    # Middle calendar diagonal, so every origin has history on both sides.
    shock_valuation = FIRST_ORIGIN_YEAR + N_ORIGINS // 2
    calendar_path = EXAMPLES_DIR / "triangle_calendar_effect.csv"
    make_calendar_effect(base, shock_valuation).to_csv(calendar_path, index=False)

    for path in (gapped_path, nonmonotone_path, calendar_path):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
