"""Builds the full origin x dev grid — actual + projected — for
triangle.json (docs/cli-spec.md v0.1.9).

Engine-agnostic: the projected (lower-triangle) cells are reconstructed by
applying fit.json's own `development_factors` LDFs forward from each
origin's own last actual value — the same numbers `fit()` already
returned, not re-derived from or by the engine. No chainladder import.
Verified empirically to reproduce chainladder's own full_triangle_ exactly
(to float precision) for every origin, including partially-excluded ones.
"""

from __future__ import annotations


def build_cells(actual_cells: list[dict], development_factors: list[dict]) -> list[dict]:
    """
    actual_cells: normalized {"origin": str, "dev": int, "value": float}
        dicts, e.g. from harness.triangle_io.load_and_normalize — the
        observed data as given.
    development_factors: fit.json's own list, [{"from_dev", "to_dev", "ldf", ...}].
        A tail's synthetic entry (`"to_dev": "ult"`) is ignored — it
        projects beyond this grid's own dev range, which stays bounded to
        the input triangle's own shape; `fit.json: totals`/`by_origin` is
        where a tail-inclusive ultimate already lives.

    Returns a flat list of {"origin", "dev", "value", "type"} dicts,
    "type" one of "actual"/"projected". A projected value is `None`
    (never fabricated) if any LDF needed to reach it is itself undefined
    (docs/cli-spec.md v0.1.5's null-as-undefined convention) — e.g. an
    aggressive --exclude-origins leaving some transition inestimable.
    """
    ldf_by_from_dev = {
        f["from_dev"]: f["ldf"] for f in development_factors if isinstance(f["to_dev"], int)
    }
    max_dev = max(ldf_by_from_dev) + 1 if ldf_by_from_dev else 1

    actual_by_origin: dict[str, dict[int, float]] = {}
    for cell in actual_cells:
        actual_by_origin.setdefault(cell["origin"], {})[cell["dev"]] = cell["value"]

    cells: list[dict] = []
    for origin in sorted(actual_by_origin, key=int):
        devs = actual_by_origin[origin]
        for dev in sorted(devs):
            cells.append({"origin": origin, "dev": dev, "value": devs[dev], "type": "actual"})

        observed_max_dev = max(devs)
        projected_value = devs[observed_max_dev]
        undefined = False
        for dev in range(observed_max_dev + 1, max_dev + 1):
            ldf = ldf_by_from_dev.get(dev - 1)
            if undefined or ldf is None:
                undefined = True
                projected_value = None
            else:
                projected_value *= ldf
            cells.append({"origin": origin, "dev": dev, "value": projected_value, "type": "projected"})

    return cells
