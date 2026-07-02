"""Writes examples/*.csv from chainladder's bundled sample triangles.

Build-time tooling only — not part of the harness product, so it is exempt
from the "nothing in harness/ imports chainladder" rule (ARCHITECTURE.md).
Run with the project's dev environment: `python scripts/export_samples.py`.

Output schema (long format, one row per observed cell):
    origin,development,value
Both origin and development are plain calendar years (the sample's native
grain — annual for raa/genins): `development` is the valuation year, so for
origin year O the first diagonal is development == O, the second O + 1, etc.
This is exactly chainladder's own bundled raw-sample CSV convention
(chainladder/utils/data/raa.csv uses `development,origin,values` with plain
years for both), chosen so the schema round-trips through
`cl.Triangle(df, origin="origin", development="development", ...)` without
a `development_format` override. `value` is cumulative. Unobserved (future)
cells are omitted rather than written as blanks/NaN.
"""

from pathlib import Path

import chainladder as cl

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

SAMPLES = ["raa", "genins"]


def export(name: str) -> Path:
    triangle = cl.load_sample(name)
    frame = triangle.to_frame()
    frame.index.name = "origin"
    long = (
        frame.reset_index()
        .melt(id_vars="origin", var_name="age_months", value_name="value")
        .dropna(subset=["value"])
    )
    long["origin"] = long["origin"].dt.year
    long["age_months"] = long["age_months"].astype(int)
    long["development"] = long["origin"] + long["age_months"] // 12 - 1
    long = long[["origin", "development", "value"]]
    long = long.sort_values(["origin", "development"]).reset_index(drop=True)

    out_path = EXAMPLES_DIR / f"{name}.csv"
    long.to_csv(out_path, index=False)
    return out_path


def main() -> None:
    EXAMPLES_DIR.mkdir(exist_ok=True)
    for name in SAMPLES:
        path = export(name)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
