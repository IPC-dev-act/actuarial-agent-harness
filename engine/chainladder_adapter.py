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
METHOD_MACK = "mack"
METHOD_CHAIN_LADDER = "chain_ladder"
METHODS = [METHOD_MACK, METHOD_CHAIN_LADDER]
ROADMAP_METHODS = ["bf", "capecod", "bootstrap"]
# load_triangle() has always hardcoded cumulative=True regardless of what
# the input actually is — a silent-fabrication risk if a genuinely
# incremental triangle were ever fit as if it were cumulative. Declaring it
# here makes the limitation explicit and checkable rather than implicit
# adapter behavior nobody can query (see cli.py's basis-mismatch check in
# cmd_fit, docs/cli-spec.md v0.1.10).
SUPPORTED_BASIS = ["cumulative"]
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

# Roadmap surfacing only (docs/cli-spec.md v0.1.11) — no new functionality.
# Broader than ROADMAP_METHODS (alternative *fitting* methods only):
# "selections" and "ifrs17_bridge" aren't fit methods, they're workflow/
# reporting destinations this harness doesn't implement yet. Naming them
# here, with their governance status, is the whole point — declaring a gap
# is different from leaving it undiscoverable.
ROADMAP = {
    "bf": "declared, not governed",
    "capecod": "declared, not governed",
    "bootstrap": "declared, not governed",
    "selections": "partially governed — BCL candidate-basis and dashboard selection-set manual override preview/decision only; manual overrides remain future work for --selections CLI",
    "ifrs17_bridge": "declared, not governed",
}


class ChainladderAdapter(EngineAdapter):
    def capabilities(self) -> dict:
        return {
            "adapter": ADAPTER_NAME,
            "package": "chainladder",
            "version": cl.__version__,
            "methods": list(METHODS),
            "roadmap_methods": list(ROADMAP_METHODS),
            "diagnostics": list(DIAGNOSTIC_TESTS),
            "basis": list(SUPPORTED_BASIS),
            "roadmap": dict(ROADMAP),
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
        if method == METHOD_MACK:
            return self._fit_mack(tri, params)
        return self._fit_chain_ladder(tri, params)

    def _fit_mack(self, tri: TriangleHandle, params: dict) -> FitResult:
        prepared = self._prepare_developed_triangle(tri, params)
        dev = prepared["dev"]
        tail = prepared["tail"]
        developed = prepared["developed"]

        mack = cl.MackChainladder().fit(developed)

        development_factors = self._development_factors(dev, tail)
        by_origin = self._by_origin(mack)
        totals = self._totals(mack)

        return FitResult(
            method="mack",
            parameters={
                "averaging": prepared["averaging"],
                "tail": _tail_to_param_string(tail),
                "n_periods": prepared["n_periods"],
                "excluded_origins": list(prepared["excluded_origins"]),
                "excluded_valuations": list(prepared["excluded_valuations"]),
                "excluded_factor_points": list(prepared["excluded_factor_points"]),
                "sigma_interpolation": prepared["sigma_interpolation"],
            },
            development_factors=development_factors,
            by_origin=by_origin,
            totals=totals,
            native={"dev": dev, "mack": mack},
        )

    def _fit_chain_ladder(self, tri: TriangleHandle, params: dict) -> FitResult:
        prepared = self._prepare_developed_triangle(tri, params)
        dev = prepared["dev"]
        tail = prepared["tail"]
        chain_ladder = cl.Chainladder().fit(prepared["developed"])

        development_factors = self._development_factors(
            dev,
            tail,
            triangle=tri.native,
            basis=prepared["averaging"],
            selected_factors=prepared["selected_factors"],
            fitted_dev=prepared["fitted_dev"],
            excluded_origins=prepared["excluded_origins"],
            excluded_valuations=prepared["excluded_valuations"],
            excluded_factor_points=prepared["excluded_factor_points"],
        )
        by_origin = self._chain_ladder_by_origin(chain_ladder)
        totals = self._chain_ladder_totals(by_origin)

        return FitResult(
            method=METHOD_CHAIN_LADDER,
            parameters={
                "averaging": prepared["averaging"],
                "tail": _tail_to_param_string(tail),
                "n_periods": prepared["n_periods"],
                "excluded_origins": list(prepared["excluded_origins"]),
                "excluded_valuations": list(prepared["excluded_valuations"]),
                "excluded_factor_points": list(prepared["excluded_factor_points"]),
                "sigma_interpolation": prepared["sigma_interpolation"],
                "selected_factors": list(prepared["selected_factors"]),
            },
            development_factors=development_factors,
            by_origin=by_origin,
            totals=totals,
            native={"dev": dev, "chain_ladder": chain_ladder},
        )

    def _prepare_developed_triangle(self, tri: TriangleHandle, params: dict) -> dict:
        triangle = tri.native
        averaging = params.get("averaging", "volume")
        tail = params.get("tail") or {"type": "none"}
        n_periods = params.get("n_periods")
        excluded_origins = params.get("excluded_origins") or []
        excluded_valuations = params.get("excluded_valuations") or []
        excluded_factor_points = params.get("excluded_factor_points") or []
        sigma_interpolation = params.get("sigma_interpolation") or DEFAULT_SIGMA_INTERPOLATION
        selected_factors = params.get("selected_factors") or []
        if sigma_interpolation not in SIGMA_INTERPOLATION_CHOICES:
            raise ValueError(
                f"invalid sigma_interpolation: {sigma_interpolation!r} "
                f"(expected one of {SIGMA_INTERPOLATION_CHOICES})"
            )

        drop_pairs = [
            *self._exclude_origin_drop_pairs(triangle, excluded_origins),
            *self._exclude_factor_point_drop_pairs(triangle, excluded_factor_points),
        ]
        drop_pairs = list(dict.fromkeys(drop_pairs))

        dev = cl.Development(
            average=averaging,
            n_periods=n_periods if n_periods is not None else -1,
            drop=drop_pairs or None,
            drop_valuation=excluded_valuations or None,
            sigma_interpolation=sigma_interpolation,
        ).fit(triangle)
        fitted_dev = dev
        if selected_factors:
            dev = self._selected_factor_development(triangle, dev, selected_factors)
        developed = dev.transform(triangle)

        if tail["type"] == "constant":
            tail_fitted = cl.TailConstant(tail=tail["factor"]).fit(developed)
            developed = tail_fitted.transform(developed)

        return {
            "averaging": averaging,
            "tail": tail,
            "n_periods": n_periods,
            "excluded_origins": excluded_origins,
            "excluded_valuations": excluded_valuations,
            "excluded_factor_points": excluded_factor_points,
            "sigma_interpolation": sigma_interpolation,
            "selected_factors": selected_factors,
            "fitted_dev": fitted_dev,
            "dev": dev,
            "developed": developed,
        }

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
    def _exclude_factor_point_drop_pairs(triangle, excluded_factor_points: list[dict]) -> list[tuple]:
        rank_to_raw_age = ChainladderAdapter._rank_to_raw_development_age(triangle)
        origin_labels = {str(o) for o in triangle.origin.year}
        pairs = []
        for point in excluded_factor_points:
            if not isinstance(point, dict):
                continue
            origin_label = str(point.get("origin") or "").strip()
            if origin_label not in origin_labels:
                continue
            try:
                from_dev = int(point.get("from_dev"))
            except (TypeError, ValueError):
                continue
            raw_age = rank_to_raw_age.get(from_dev)
            if raw_age is not None:
                pairs.append((origin_label, raw_age))
        return pairs

    @staticmethod
    def _selected_factor_development(triangle, fitted_dev, selected_factors: list[dict]):
        patterns = ChainladderAdapter._ldf_patterns_by_raw_age(fitted_dev)
        rank_to_raw_age = ChainladderAdapter._rank_to_raw_development_age(triangle)
        for selection in selected_factors:
            from_dev = int(selection["from_dev"])
            if from_dev not in rank_to_raw_age:
                raise ValueError(f"selected factor from_dev is not in the triangle development ages: {from_dev}")
            factor = float(selection["factor"])
            if not np.isfinite(factor) or factor <= 0:
                raise ValueError(f"selected factor must be a positive finite number: {factor!r}")
            patterns[rank_to_raw_age[from_dev]] = factor
        return cl.DevelopmentConstant(patterns=patterns, style="ldf").fit(triangle)

    @staticmethod
    def _rank_to_raw_development_age(triangle) -> dict[int, int]:
        return {i + 1: int(age) for i, age in enumerate(list(triangle.development)[:-1])}

    @staticmethod
    def _ldf_patterns_by_raw_age(dev) -> dict[int, float]:
        ldf_frame = dev.ldf_.to_frame()
        patterns: dict[int, float] = {}
        for label in ldf_frame.columns:
            raw_age = int(str(label).split("-")[0])
            patterns[raw_age] = float(ldf_frame.iloc[0][label])
        return patterns

    @staticmethod
    def _selected_factor_by_from_dev(selected_factors: list[dict]) -> dict[int, dict]:
        return {int(selection["from_dev"]): dict(selection) for selection in selected_factors}

    @staticmethod
    def _development_factors(
        dev,
        tail: dict,
        *,
        triangle=None,
        basis: str | None = None,
        selected_factors: list[dict] | None = None,
        fitted_dev=None,
        excluded_origins: list[str] | None = None,
        excluded_valuations: list[str] | None = None,
        excluded_factor_points: list[dict] | None = None,
    ) -> list[dict]:
        ldf_frame = dev.ldf_.to_frame()
        sigma_frame = dev.sigma_.to_frame() if hasattr(dev, "sigma_") else None
        fitted_ldf_frame = fitted_dev.ldf_.to_frame() if fitted_dev is not None else ldf_frame
        labels = list(ldf_frame.columns)
        detail_by_from_dev = (
            ChainladderAdapter._factor_detail_by_from_dev(
                triangle,
                excluded_origins=excluded_origins or [],
                excluded_valuations=excluded_valuations or [],
                excluded_factor_points=excluded_factor_points or [],
            )
            if triangle is not None
            else {}
        )
        selections = ChainladderAdapter._selected_factor_by_from_dev(selected_factors or [])
        factors = []
        for i, label in enumerate(labels):
            from_dev = i + 1
            ldf = float(ldf_frame.iloc[0][label])
            selection = selections.get(from_dev)
            row = {
                "from_dev": from_dev,
                "to_dev": i + 2,
                "ldf": ldf,
                "sigma": float(sigma_frame.iloc[0][label]) if sigma_frame is not None else None,
            }
            if triangle is not None:
                detail = detail_by_from_dev.get(from_dev, {})
                row.update(
                    {
                        "from_age": detail.get("from_age"),
                        "to_age": detail.get("to_age"),
                        "selected_factor": ldf,
                        "fitted_factor": float(fitted_ldf_frame.iloc[0][label]),
                        "factor_basis": selection.get("basis") if selection else basis,
                        "link_ratios": detail.get("link_ratios", []),
                        "candidate_averages": detail.get("candidate_averages", {}),
                        "candidate_average_notes": detail.get("candidate_average_notes", {}),
                    }
                )
            factors.append(row)
        if tail["type"] == "constant":
            factors.append(
                {
                    "from_dev": len(labels) + 1,
                    "to_dev": "ult",
                    "ldf": float(tail["factor"]),
                    "sigma": None,
                }
            )
        if triangle is not None:
            ChainladderAdapter._attach_cumulative_development_factors(factors)
        return factors

    @staticmethod
    def _attach_cumulative_development_factors(factors: list[dict]) -> None:
        running = 1.0
        for row in reversed(factors):
            ldf = row.get("ldf")
            if ldf is None or not np.isfinite(float(ldf)):
                running = float("nan")
                row["cumulative_development_factor"] = None
                continue
            running *= float(ldf)
            row["cumulative_development_factor"] = float(running) if np.isfinite(running) else None

    @staticmethod
    def _factor_detail_by_from_dev(
        triangle,
        *,
        excluded_origins: list[str],
        excluded_valuations: list[str],
        excluded_factor_points: list[dict],
    ) -> dict[int, dict]:
        wide = triangle.to_frame()
        ages = list(wide.columns)
        excluded_origin_set = {str(origin) for origin in excluded_origins}
        excluded_valuation_set = {str(valuation) for valuation in excluded_valuations}
        excluded_point_set = {
            (str(point.get("origin")), str(point.get("from_dev")))
            for point in excluded_factor_points
            if isinstance(point, dict)
        }
        details: dict[int, dict] = {}
        for i, (from_age, to_age) in enumerate(zip(ages, ages[1:]), start=1):
            link_ratios = []
            for origin_ts, row in wide.iterrows():
                origin = str(origin_ts.year)
                if (
                    origin in excluded_origin_set
                    or str(to_age) in excluded_valuation_set
                    or str(i + 1) in excluded_valuation_set
                    or (origin, str(i)) in excluded_point_set
                ):
                    continue
                current = row[from_age]
                next_value = row[to_age]
                if pd.isna(current) or pd.isna(next_value) or current == 0:
                    continue
                link_ratios.append(
                    {
                        "origin": origin,
                        "from_dev": i,
                        "to_dev": i + 1,
                        "from_age": int(from_age),
                        "to_age": int(to_age),
                        "current_value": float(current),
                        "next_value": float(next_value),
                        "link_ratio": float(next_value / current),
                    }
                )
            candidates, notes = ChainladderAdapter._candidate_averages(link_ratios)
            details[i] = {
                "from_age": int(from_age),
                "to_age": int(to_age),
                "link_ratios": link_ratios,
                "candidate_averages": candidates,
                "candidate_average_notes": notes,
            }
        return details

    @staticmethod
    def _candidate_averages(link_ratios: list[dict]) -> tuple[dict, dict]:
        ratios = [row["link_ratio"] for row in link_ratios]
        current_values = [row["current_value"] for row in link_ratios]
        next_values = [row["next_value"] for row in link_ratios]

        candidates = {
            "volume_weighted": None,
            "simple_average": None,
            "last_3": None,
            "last_5": None,
            "all_years": None,
            "trimmed_mean": None,
            "median": None,
        }
        notes = {
            "volume_weighted": "no link ratios available",
            "simple_average": "no link ratios available",
            "last_3": "requires at least 3 link ratios",
            "last_5": "requires at least 5 link ratios",
            "all_years": "same as simple_average for the unweighted all-year candidate",
            "trimmed_mean": "requires at least 3 link ratios",
            "median": "no link ratios available",
        }
        if not ratios:
            return candidates, notes

        total_current = float(sum(current_values))
        if total_current > 0:
            candidates["volume_weighted"] = float(sum(next_values) / total_current)
            notes["volume_weighted"] = "available"
        else:
            notes["volume_weighted"] = "no positive denominator volume"

        candidates["simple_average"] = float(sum(ratios) / len(ratios))
        notes["simple_average"] = "available"
        candidates["median"] = float(np.median(ratios))
        notes["median"] = "available"

        if len(ratios) >= 3:
            sorted_ratios = sorted(ratios)
            trimmed = sorted_ratios[1:-1]
            candidates["trimmed_mean"] = float(sum(trimmed) / len(trimmed))
            notes["trimmed_mean"] = "available"
        else:
            notes["trimmed_mean"] = f"requires at least 3 link ratios; found {len(ratios)}"

        for size, key in ((3, "last_3"), (5, "last_5")):
            if len(ratios) >= size:
                last_values = ratios[-size:]
                candidates[key] = float(sum(last_values) / size)
                notes[key] = "available"
            else:
                notes[key] = f"requires at least {size} link ratios; found {len(ratios)}"

        return candidates, notes

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

    @staticmethod
    def _chain_ladder_by_origin(chain_ladder) -> list[dict]:
        latest = chain_ladder.latest_diagonal.to_frame()
        ultimate = chain_ladder.ultimate_.to_frame()
        ibnr = chain_ladder.ibnr_.to_frame()
        rows = []
        for origin_ts, latest_row in latest.iterrows():
            origin = str(origin_ts.year)
            latest_value = float(latest_row.iloc[0])
            ultimate_value = float(ultimate.loc[origin_ts].iloc[0])
            ibnr_value = ibnr.loc[origin_ts].iloc[0]
            if latest_value == ultimate_value and pd.isna(ibnr_value):
                ibnr_value = 0.0
            rows.append(
                {
                    "origin": origin,
                    "latest": latest_value,
                    "ultimate": ultimate_value,
                    "ibnr": float(ibnr_value),
                    "mack_se": None,
                }
            )
        return rows

    @staticmethod
    def _chain_ladder_totals(by_origin: list[dict]) -> dict:
        def _sum(field: str) -> float:
            values = [row[field] for row in by_origin]
            if any(np.isnan(v) for v in values):
                return float("nan")
            return float(sum(values))

        return {
            "latest": _sum("latest"),
            "ultimate": _sum("ultimate"),
            "ibnr": _sum("ibnr"),
            "mack_se": None,
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
