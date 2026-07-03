"""Shared triangle CSV parsing/normalization, engine-agnostic.

No chainladder import — ARCHITECTURE.md's adapter boundary. Used by both
`harness/validation.py` and `harness/sensitivity.py`; kept separate from
`engine/chainladder_adapter.py`'s own (necessarily independent — see its
module docstring) copy of the same convention detection, since the adapter
must not depend on harness internals.

Long-format CSV: columns `origin,development,value`. `development` is
accepted in either convention (docs/cli-spec.md v0.1.2):
  - valuation-year: the calendar year of the observation — for origin O the
    first cell is development == O. Detected when every origin's minimum
    development equals that origin's own value.
  - development-age: periods elapsed since origin (1, 2, 3, ...).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["origin", "development", "value"]


def parse_and_normalize(frame: pd.DataFrame) -> tuple[pd.DataFrame | None, dict | None]:
    """Returns (normalized, error). normalized has columns
    origin (str), dev (1-indexed rank int), valuation_year (int — the
    resolved calendar year of that cell, under either input convention),
    value (float). error is a structured dict (None on success)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        return None, {"missing_columns": missing, "found_columns": list(frame.columns)}

    working = frame[REQUIRED_COLUMNS].copy()
    for col in ("origin", "development", "value"):
        working[col] = pd.to_numeric(working[col], errors="coerce")
    bad_rows = working[working.isna().any(axis=1)]
    if not bad_rows.empty:
        return None, {
            "unparseable_rows": bad_rows.index[:5].tolist(),
            "row_count": int(len(bad_rows)),
        }

    working["origin"] = working["origin"].astype(int)
    working["development"] = working["development"].astype(int)

    min_dev_by_origin = working.groupby("origin")["development"].min()
    is_valuation_year = bool((min_dev_by_origin == min_dev_by_origin.index).all())

    if is_valuation_year:
        working["dev"] = working["development"] - working["origin"] + 1
        working["valuation_year"] = working["development"]
    else:
        # development-age convention: ages ranked (not used raw) since real
        # age labels are typically month counts (12, 24, 36, ...), not
        # small 1-indexed period ranks.
        distinct_ages = sorted(working["development"].unique())
        age_rank = {age: i + 1 for i, age in enumerate(distinct_ages)}
        working["dev"] = working["development"].map(age_rank)
        working["valuation_year"] = working["origin"] + working["dev"] - 1

    if (working["dev"] < 1).any():
        return None, {
            "error": "development normalizes to a non-positive period",
            "convention": "valuation_year" if is_valuation_year else "development_age",
        }

    working["origin"] = working["origin"].astype(str)
    result = working[["origin", "dev", "valuation_year", "value"]]
    return result.sort_values(["origin", "dev"]).reset_index(drop=True), None


def load_and_normalize(path: Path) -> tuple[pd.DataFrame | None, dict | None]:
    frame = pd.read_csv(path)
    return parse_and_normalize(frame)
