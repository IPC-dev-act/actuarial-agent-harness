"""Reference EngineAdapter implementation over chainladder-python (MPL-2.0).

The only module in this codebase allowed to `import chainladder`
(ARCHITECTURE.md's adapter boundary — nothing in harness/ may import it).
"""

from __future__ import annotations

from pathlib import Path

import chainladder as cl
import numpy as np
import pandas as pd

from engine.base import (
    DiagnosticsResult,
    EngineAdapter,
    FitResult,
    TriangleFormatError,
    TriangleHandle,
    UnsupportedMethodError,
)

ADAPTER_NAME = "chainladder_adapter"
METHODS = ["mack"]
ROADMAP_METHODS = ["bf", "capecod", "bootstrap"]
DIAGNOSTIC_TESTS = [
    "dev_correlation",
    "calendar_year_effect",
    "residual_pattern_dev",
    "residual_pattern_origin",
    "outlier_link_ratios",
]

SIGMA_INTERPOLATION_CHOICES = ["mack", "log-linear"]
# "mack" (Mack's own minimum rule for the last-period sigma), not
# chainladder's own library default ("log-linear"). Verified against the
# published RAA figures (VALIDATION.md): "mack" reproduces every published
# standard error exactly; "log-linear" understates SE for origins that
# depend most heavily on the extrapolated final sigma (e.g. 143 vs the
# published 206 for origin 1982). Both are legitimate statistical choices —
# this pins the one that matches the literature as the default, not because
# the other is wrong, and leaves it overridable via --sigma-interpolation.
DEFAULT_SIGMA_INTERPOLATION = "mack"


class ChainladderAdapter(EngineAdapter):
    def capabilities(self) -> dict:
        return {
            "adapter": ADAPTER_NAME,
            "package": "chainladder",
            "version": cl.__version__,
            "methods": list(METHODS),
            "roadmap_methods": list(ROADMAP_METHODS),
            "diagnostics": list(DIAGNOSTIC_TESTS),
        }

    def load_triangle(self, path: Path) -> TriangleHandle:
        path = Path(path)
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            raise TriangleFormatError(f"could not read {path}: {exc}") from exc

        required = {"origin", "development", "value"}
        missing = required - set(frame.columns)
        if missing:
            raise TriangleFormatError(
                f"missing required columns: {sorted(missing)}",
                {"missing_columns": sorted(missing)},
            )

        working = frame[["origin", "development", "value"]].copy()
        for col in ("origin", "development", "value"):
            working[col] = pd.to_numeric(working[col], errors="coerce")
        if working.isna().any().any():
            raise TriangleFormatError("non-numeric origin/development/value cells")
        working["origin"] = working["origin"].astype(int)
        working["development"] = working["development"].astype(int)

        # Accept both conventions (docs/cli-spec.md v0.1.2): valuation-year
        # iff every origin's minimum development label equals that origin's
        # own value; convert age-labelled data to valuation-year so
        # chainladder's date-based lag inference applies. Ages are ranked
        # (not used raw) since real age labels are typically month counts
        # (12, 24, 36, ...), not small 1-indexed period ranks.
        min_dev_by_origin = working.groupby("origin")["development"].min()
        is_valuation_year = bool((min_dev_by_origin == min_dev_by_origin.index).all())
        if not is_valuation_year:
            distinct_ages = sorted(working["development"].unique())
            age_rank = {age: i + 1 for i, age in enumerate(distinct_ages)}
            working["development"] = working["origin"] + working["development"].map(age_rank) - 1

        try:
            triangle = cl.Triangle(
                working,
                origin="origin",
                development="development",
                columns="value",
                cumulative=True,
            )
        except Exception as exc:
            raise TriangleFormatError(f"chainladder could not build a Triangle: {exc}") from exc

        return TriangleHandle(native=triangle, basis="cumulative")

    def fit(self, tri: TriangleHandle, method: str, params: dict) -> FitResult:
        if method not in METHODS:
            raise UnsupportedMethodError(method)
        return self._fit_mack(tri, params)

    def _fit_mack(self, tri: TriangleHandle, params: dict) -> FitResult:
        triangle = tri.native
        averaging = params.get("averaging", "volume")
        tail = params.get("tail") or {"type": "none"}
        n_periods = params.get("n_periods")
        excluded_origins = params.get("excluded_origins") or []
        excluded_valuations = params.get("excluded_valuations") or []
        sigma_interpolation = params.get("sigma_interpolation") or DEFAULT_SIGMA_INTERPOLATION
        if sigma_interpolation not in SIGMA_INTERPOLATION_CHOICES:
            raise ValueError(
                f"invalid sigma_interpolation: {sigma_interpolation!r} "
                f"(expected one of {SIGMA_INTERPOLATION_CHOICES})"
            )

        drop_pairs = self._exclude_origin_drop_pairs(triangle, excluded_origins)

        dev = cl.Development(
            average=averaging,
            n_periods=n_periods if n_periods is not None else -1,
            drop=drop_pairs or None,
            drop_valuation=excluded_valuations or None,
            sigma_interpolation=sigma_interpolation,
        ).fit(triangle)
        developed = dev.transform(triangle)

        if tail["type"] == "constant":
            tail_fitted = cl.TailConstant(tail=tail["factor"]).fit(developed)
            developed = tail_fitted.transform(developed)

        mack = cl.MackChainladder().fit(developed)

        development_factors = self._development_factors(dev, tail)
        by_origin = self._by_origin(mack)
        totals = self._totals(mack)

        return FitResult(
            method="mack",
            parameters={
                "averaging": averaging,
                "tail": _tail_to_param_string(tail),
                "n_periods": n_periods,
                "excluded_origins": list(excluded_origins),
                "excluded_valuations": list(excluded_valuations),
                "sigma_interpolation": sigma_interpolation,
            },
            development_factors=development_factors,
            by_origin=by_origin,
            totals=totals,
            native={"dev": dev, "mack": mack},
        )

    @staticmethod
    def _exclude_origin_drop_pairs(triangle, excluded_origins: list[str]) -> list[tuple]:
        """Builds (origin, dev) drop tuples for cl.Development(drop=...) —
        origin as str, dev as raw int (chainladder 0.9.2 requires this exact
        typing, confirmed empirically against the library's own test suite).
        Origins with
        fewer than 2 observed periods contribute no link ratios to begin
        with, so "excluding" them via drop is a meaningless no-op that also
        happens to crash chainladder's std-error weight computation — they
        are skipped rather than passed through.
        """
        if not excluded_origins:
            return []
        origin_labels = {str(o) for o in triangle.origin.year}
        all_devs = list(triangle.development)
        non_terminal_devs = all_devs[:-1]  # last period has no outgoing transition
        pairs = []
        for origin_label in excluded_origins:
            if origin_label not in origin_labels:
                continue
            origin_slice = triangle[triangle.origin.year == int(origin_label)]
            observed_count = int(np.sum(~np.isnan(origin_slice.values)))
            if observed_count < 2:
                continue
            pairs.extend((origin_label, d) for d in non_terminal_devs)
        return pairs

    @staticmethod
    def _development_factors(dev, tail: dict) -> list[dict]:
        ldf_frame = dev.ldf_.to_frame()
        sigma_frame = dev.sigma_.to_frame()
        labels = list(ldf_frame.columns)
        factors = []
        for i, label in enumerate(labels):
            factors.append(
                {
                    "from_dev": i + 1,
                    "to_dev": i + 2,
                    "ldf": float(ldf_frame.iloc[0][label]),
                    "sigma": float(sigma_frame.iloc[0][label]),
                }
            )
        if tail["type"] == "constant":
            factors.append(
                {
                    "from_dev": len(labels) + 1,
                    "to_dev": "ult",
                    "ldf": float(tail["factor"]),
                    "sigma": None,
                }
            )
        return factors

    @staticmethod
    def _by_origin(mack) -> list[dict]:
        """chainladder reports IBNR/mack_se as NaN in two, very different
        cases that must not be conflated: (a) a fully-developed origin
        (Latest == Ultimate), where Mack's recursive formula is a genuine
        0/0 but the answer is analytically exactly 0 — safe to fill; and
        (b) an origin whose ultimate genuinely can't be computed (e.g. a
        sensitivity scenario excludes the only origin with data for some
        development transition), where the right answer is "undefined",
        not 0. Blanket-filling NaN with 0.0 would silently misreport case
        (b) as a known-zero reserve, which is worse than surfacing NaN —
        only (a) gets filled.
        """
        summary = mack.summary_.to_frame()
        rows = []
        for origin_ts, row in summary.iterrows():
            fully_developed = row["Latest"] == row["Ultimate"]
            ibnr = 0.0 if fully_developed and pd.isna(row["IBNR"]) else row["IBNR"]
            mack_se = 0.0 if fully_developed and pd.isna(row["Mack Std Err"]) else row["Mack Std Err"]
            rows.append(
                {
                    "origin": str(origin_ts.year),
                    "latest": float(row["Latest"]),
                    "ultimate": float(row["Ultimate"]),
                    "ibnr": float(ibnr),
                    "mack_se": float(mack_se),
                }
            )
        return rows

    @staticmethod
    def _totals(mack) -> dict:
        """Sums by_origin (not mack.summary_.to_frame().sum() directly):
        pandas' Series.sum() defaults to skipna=True, which would silently
        drop an undefined origin from the total rather than propagating
        its undefined-ness — an incomplete total that looks like a valid
        one. total_mack_std_err_ is Mack's own proper aggregate (not a
        naive sum of per-origin std errors, which would double-count
        correlation) and already propagates NaN correctly on its own.
        """
        by_origin = ChainladderAdapter._by_origin(mack)

        def _sum(field: str) -> float:
            values = [row[field] for row in by_origin]
            if any(np.isnan(v) for v in values):
                return float("nan")
            return float(sum(values))

        return {
            "latest": _sum("latest"),
            "ultimate": _sum("ultimate"),
            "ibnr": _sum("ibnr"),
            "mack_se": float(mack.total_mack_std_err_.iloc[0, 0]),
        }

    def diagnostics(self, tri: TriangleHandle, fit: FitResult) -> DiagnosticsResult:
        if not fit.native or "dev" not in fit.native:
            raise ValueError("diagnostics requires a FitResult produced by this adapter's fit()")
        triangle = tri.native
        dev = fit.native["dev"]
        tests = [
            _test_dev_correlation(triangle),
            _test_calendar_year_effect(dev),
            _test_residual_pattern_dev(dev),
            _test_residual_pattern_origin(dev),
            _test_outlier_link_ratios(triangle),
        ]
        return DiagnosticsResult(tests=tests)


def parse_tail_param(raw: str) -> dict:
    """CLI-facing parser for --tail none|constant:<f>."""
    if raw == "none":
        return {"type": "none"}
    if raw.startswith("constant:"):
        _, _, factor_str = raw.partition(":")
        try:
            factor = float(factor_str)
        except ValueError as exc:
            raise ValueError(f"invalid tail factor: {factor_str!r}") from exc
        return {"type": "constant", "factor": factor}
    raise ValueError(f"invalid --tail value: {raw!r} (expected none|constant:<f>)")


def _tail_to_param_string(tail: dict) -> str:
    if tail["type"] == "none":
        return "none"
    return f"constant:{tail['factor']}"


# --- diagnostics: Mack (1993/1994) assumption tests -------------------------
#
# These are reference-implementation approximations of the concepts named by
# each test_id, not independently verified against the exact formulas in
# Mack (1993/1994) — see VALIDATION.md's "known caveats". Unlike the RAA/
# GenIns reserve and standard-error figures (tests/test_mack_vs_literature.py,
# verified exactly), the five assumption tests below are screening
# indicators, not certified reproductions of the papers' test statistics.
# All five report a z-score-style
# `statistic` against a fixed `threshold=1.96` (matching docs/cli-spec.md's
# own worked example for calendar_year_effect) with a binary pass/warn
# verdict — deliberately no "fail" here, since calibrating a second,
# harder threshold for a soft statistical assumption test isn't something
# this reference implementation is in a position to certify. CLAUDE.md's
# workflow treats warn and fail identically anyway (exit 3, propose
# sensitivities, no headline figure until resolved).

_THRESHOLD = 1.96

_NARRATIVE_KEY_PREFIX = {
    "dev_correlation": "dev_correlation",
    "calendar_year_effect": "cy_effect",
    "residual_pattern_dev": "residual_pattern_dev",
    "residual_pattern_origin": "residual_pattern_origin",
    "outlier_link_ratios": "outlier_link_ratios",
}

# Placeholder-templated, matching docs/cli-spec.md's own example verbatim
# ("<run-id>", "<flagged>") — the adapter has no run_id or triangle path to
# fill in (diagnostics(tri, fit) carries neither), so the agent fills these
# in; cli-spec.md: "prescribed_actions is the agent's menu — it proposes
# from this list, nothing else."
_PRESCRIBED_ACTIONS = {
    "dev_correlation": ["reserve sensitivity <run-id> --grid default"],
    "calendar_year_effect": [
        "reserve sensitivity <run-id> --exclude-valuations <flagged>",
        "reserve fit <triangle.csv> --method mack --n-periods 5",
    ],
    "residual_pattern_dev": [
        "reserve sensitivity <run-id> --grid default",
        "reserve fit <triangle.csv> --method mack --averaging simple",
    ],
    "residual_pattern_origin": ["reserve sensitivity <run-id> --exclude-origins <flagged-origin>"],
    "outlier_link_ratios": [
        "reserve sensitivity <run-id> --exclude-origins <flagged-origin>",
        "reserve sensitivity <run-id> --exclude-valuations <flagged-valuation>",
    ],
}


def _test_result(test_id: str, statistic: float, verdict: str) -> dict:
    prefix = _NARRATIVE_KEY_PREFIX[test_id]
    return {
        "test_id": test_id,
        "statistic": float(statistic),
        "threshold": _THRESHOLD,
        "verdict": verdict,
        "narrative_key": f"{prefix}_{verdict}",
        "prescribed_actions": _PRESCRIBED_ACTIONS[test_id] if verdict != "pass" else [],
    }


def _fisher_z(r: float, n: int) -> float:
    """Significance z-score for a Pearson correlation r over n pairs."""
    if n <= 3:
        return 0.0
    r_clipped = max(-0.999999, min(0.999999, r))
    return float(np.arctanh(r_clipped) * np.sqrt(n - 3))


def _correlation_test(test_id: str, values_a: list[float], values_b: list[float]) -> dict:
    n = len(values_a)
    if n < 4 or np.std(values_a) == 0 or np.std(values_b) == 0:
        return _test_result(test_id, 0.0, "pass")
    r = float(np.corrcoef(values_a, values_b)[0, 1])
    statistic = abs(_fisher_z(r, n))
    verdict = "pass" if statistic <= _THRESHOLD else "warn"
    return _test_result(test_id, statistic, verdict)


def _individual_link_ratios(triangle) -> pd.DataFrame:
    """Wide frame: index=origin, columns=from-age, values=individual
    (unweighted) link ratio value[to_age] / value[from_age]."""
    wide = triangle.to_frame()
    ages = sorted(wide.columns)
    ratios = pd.DataFrame(index=wide.index, columns=ages[:-1], dtype=float)
    for a0, a1 in zip(ages, ages[1:]):
        ratios[a0] = wide[a1] / wide[a0]
    return ratios


def _test_dev_correlation(triangle) -> dict:
    """Correlation of adjacent development factors: pools each origin's
    individual link ratio at column k against its own ratio at column k+1
    across every adjacent column pair, and tests whether the pooled
    correlation is significantly different from zero."""
    ratios = _individual_link_ratios(triangle)
    cols = list(ratios.columns)
    pairs_a: list[float] = []
    pairs_b: list[float] = []
    for col_a, col_b in zip(cols, cols[1:]):
        both = ratios[[col_a, col_b]].dropna()
        pairs_a.extend(both[col_a].tolist())
        pairs_b.extend(both[col_b].tolist())
    return _correlation_test("dev_correlation", pairs_a, pairs_b)


def _test_calendar_year_effect(dev) -> dict:
    """Diagonal sign-clustering test: under no calendar-year effect, the
    standardized residuals on any calendar diagonal should split roughly
    evenly in sign. For each diagonal with n>=2 non-zero residuals, let
    S = min(#positive, #negative); E[S]=(n-1)/2, Var[S]=(n-1)/4 approximate
    a fair-coin minority count. Aggregated across diagonals into one
    z-score; a value much larger than expected (S well below E[S]) means
    residuals cluster by sign on individual diagonals — a calendar effect.
    """
    resid = dev.std_residuals_.to_frame()
    diagonals: dict[int, list[float]] = {}
    for i, (_origin, row) in enumerate(resid.iterrows()):
        for j, val in enumerate(row.tolist()):
            if val is None or (isinstance(val, float) and (np.isnan(val) or val == 0)):
                continue
            diagonals.setdefault(i + j, []).append(val)

    sum_s = sum_e = sum_var = 0.0
    for values in diagonals.values():
        n = len(values)
        if n < 2:
            continue
        pos = sum(1 for v in values if v > 0)
        neg = n - pos
        sum_s += min(pos, neg)
        sum_e += (n - 1) / 2
        sum_var += (n - 1) / 4

    if sum_var <= 0:
        return _test_result("calendar_year_effect", 0.0, "pass")
    statistic = max(0.0, (sum_e - sum_s) / (sum_var**0.5))
    verdict = "pass" if statistic <= _THRESHOLD else "warn"
    return _test_result("calendar_year_effect", statistic, verdict)


def _test_residual_pattern_dev(dev) -> dict:
    """Standardized residuals vs development period: correlation between
    each residual and its column's rank, testing for a trend across
    development periods (a sign the LDF pattern is misspecified)."""
    resid = dev.std_residuals_.to_frame()
    values: list[float] = []
    dev_ranks: list[float] = []
    for j, col in enumerate(resid.columns):
        for val in resid[col]:
            if pd.notna(val):
                values.append(float(val))
                dev_ranks.append(j + 1)
    return _correlation_test("residual_pattern_dev", values, dev_ranks)


def _test_residual_pattern_origin(dev) -> dict:
    """Standardized residuals vs origin: correlation between each residual
    and its row's rank, testing for a trend across origin years."""
    resid = dev.std_residuals_.to_frame()
    values: list[float] = []
    origin_ranks: list[float] = []
    for i, (_origin, row) in enumerate(resid.iterrows()):
        for val in row.tolist():
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                values.append(float(val))
                origin_ranks.append(i + 1)
    return _correlation_test("residual_pattern_origin", values, origin_ranks)


def _test_outlier_link_ratios(triangle) -> dict:
    """Individual link ratios beyond tolerance: for each development
    column, z-score each origin's individual link ratio against that
    column's own mean/std; reports the single largest |z| found anywhere
    in the triangle."""
    ratios = _individual_link_ratios(triangle)
    max_z = 0.0
    for col in ratios.columns:
        series = ratios[col].dropna()
        if len(series) < 2:
            continue
        std = series.std(ddof=1)
        if not std or np.isnan(std):
            continue
        z = ((series - series.mean()) / std).abs().max()
        max_z = max(max_z, float(z))
    verdict = "pass" if max_z <= _THRESHOLD else "warn"
    return _test_result("outlier_link_ratios", max_z, verdict)
