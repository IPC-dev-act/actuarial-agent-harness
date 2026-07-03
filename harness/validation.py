"""Structural triangle checks, engine-agnostic (docs/cli-spec.md `validate`).

No chainladder import — ARCHITECTURE.md's adapter boundary. Everything here
operates on a plain long-format CSV: columns `origin,development,value`.

`development` is accepted in either convention (v0.1.2):
  - valuation-year: the calendar year of the observation (chainladder's own
    bundled sample convention — for origin O the first cell is development
    == O). Detected when every origin's minimum development equals that
    origin's value.
  - development-age: periods elapsed since origin (1, 2, 3, ...). Detected
    otherwise.
Both are normalized to a 1-indexed `dev` rank per origin before any other
check runs.

Fail-class (blocks a fit, exit 2): `file_readable`, `shape_triangular`,
`no_gaps`, `origin_dev_parseable`, `basis_consistent`.
Warn-class (exit 0, flagged): `monotone_cumulative`, `nonneg_incrementals`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from harness import triangle_io
from harness.manifest import sha256_file

FAIL_CLASS_CHECKS = {
    "file_readable",
    "shape_triangular",
    "no_gaps",
    "origin_dev_parseable",
    "basis_consistent",
}
WARN_CLASS_CHECKS = {"monotone_cumulative", "nonneg_incrementals"}


@dataclass
class Check:
    check_id: str
    verdict: str  # pass | warn | fail
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        return {"check_id": self.check_id, "verdict": self.verdict, "details": self.details}


@dataclass
class ValidationResult:
    input_path: Path
    input_sha256: str | None
    basis: str | None
    dimensions: dict[str, int] | None
    checks: list[Check] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        verdicts = {c.verdict for c in self.checks}
        if "fail" in verdicts:
            return "fail"
        if "warn" in verdicts:
            return "warn"
        return "pass"

    def to_dict(self) -> dict:
        return {
            "input": {"path": str(self.input_path), "sha256": self.input_sha256},
            "basis": self.basis,
            "dimensions": self.dimensions,
            "checks": [c.to_dict() for c in self.checks],
            "verdict": self.verdict,
        }


def validate_triangle_csv(path: Path) -> ValidationResult:
    path = Path(path)
    result = ValidationResult(input_path=path, input_sha256=None, basis=None, dimensions=None)

    frame, read_error = _read_csv(path)
    if read_error is not None:
        result.checks.append(Check("file_readable", "fail", read_error))
        return result
    result.input_sha256 = sha256_file(path)
    result.checks.append(Check("file_readable", "pass"))

    normalized, parse_error = triangle_io.parse_and_normalize(frame)
    if parse_error is not None:
        result.checks.append(Check("origin_dev_parseable", "fail", parse_error))
        return result
    result.checks.append(Check("origin_dev_parseable", "pass"))

    n_origins = normalized["origin"].nunique()
    n_devs = int(normalized["dev"].max())
    result.dimensions = {"origins": int(n_origins), "devs": n_devs}

    shape_check = _check_shape_triangular(normalized)
    result.checks.append(shape_check)
    gaps_check = _check_no_gaps(normalized)
    result.checks.append(gaps_check)
    if shape_check.verdict == "fail" or gaps_check.verdict == "fail":
        # Interior/staircase problems make basis inference and the
        # monotonicity/sign checks below meaningless — stop here.
        return result

    basis, basis_check = _check_basis_consistent(normalized)
    result.basis = basis
    result.checks.append(basis_check)
    if basis_check.verdict == "fail":
        return result

    result.checks.append(_check_monotone_cumulative(normalized, basis))
    result.checks.append(_check_nonneg_incrementals(normalized, basis))
    return result


def _read_csv(path: Path) -> tuple[pd.DataFrame | None, dict | None]:
    if not path.exists():
        return None, {"path": str(path), "error": "file does not exist"}
    if not path.is_file():
        return None, {"path": str(path), "error": "not a regular file"}
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # pandas raises various error types on bad CSVs
        return None, {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}
    if frame.empty:
        return None, {"path": str(path), "error": "file has no data rows"}
    return frame, None


def _check_shape_triangular(df: pd.DataFrame) -> Check:
    """Staircase check across origins: ranked oldest→newest, max observed
    dev must be non-increasing (older origins have at least as much
    development as newer ones) — the defining shape of a loss triangle as
    opposed to a rectangle or a scattered/irregular dataset.
    """
    max_dev_by_origin = df.groupby("origin")["dev"].max()
    ordered_origins = sorted(max_dev_by_origin.index, key=int)
    max_devs = [int(max_dev_by_origin[o]) for o in ordered_origins]

    violations = []
    for i in range(1, len(max_devs)):
        if max_devs[i] > max_devs[i - 1]:
            violations.append(
                {
                    "origin": ordered_origins[i],
                    "max_dev": max_devs[i],
                    "prior_origin": ordered_origins[i - 1],
                    "prior_max_dev": max_devs[i - 1],
                }
            )
    if violations:
        return Check("shape_triangular", "fail", {"violations": violations[:5]})
    return Check("shape_triangular", "pass")


def _check_no_gaps(df: pd.DataFrame) -> Check:
    """Within each origin, observed devs must be a contiguous 1..k run."""
    violations = []
    for origin, group in df.groupby("origin"):
        devs = sorted(group["dev"].tolist())
        expected = list(range(1, len(devs) + 1))
        if devs != expected:
            missing = sorted(set(expected) - set(devs))
            violations.append({"origin": origin, "observed_devs": devs, "missing_devs": missing})
    if violations:
        return Check("no_gaps", "fail", {"violations": violations[:5]})
    return Check("no_gaps", "pass")


def _check_basis_consistent(df: pd.DataFrame) -> tuple[str | None, Check]:
    """Infers cumulative vs incremental by comparing each origin's first and
    last observed value (endpoint comparison — robust to an interior
    decrease, which v0.1.2 treats as a legitimate warn-class feature of
    incurred data, not a basis-breaking signal). Fails only when the votes
    are genuinely tied or no origin has enough history to vote at all —
    "mixed basis": no single interpretation explains the data.
    """
    votes_cumulative = 0
    votes_incremental = 0
    for _origin, group in df.groupby("origin"):
        ordered = group.sort_values("dev")
        if len(ordered) < 2:
            continue
        first_value = ordered["value"].iloc[0]
        last_value = ordered["value"].iloc[-1]
        if last_value >= first_value:
            votes_cumulative += 1
        else:
            votes_incremental += 1

    total_votes = votes_cumulative + votes_incremental
    if total_votes == 0 or votes_cumulative == votes_incremental:
        return None, Check(
            "basis_consistent",
            "fail",
            {
                "reason": "no single basis (cumulative or incremental) explains the data",
                "votes_cumulative": votes_cumulative,
                "votes_incremental": votes_incremental,
            },
        )
    basis = "cumulative" if votes_cumulative > votes_incremental else "incremental"
    return basis, Check("basis_consistent", "pass")


def _cumulative_view(df: pd.DataFrame, basis: str) -> pd.DataFrame:
    if basis == "cumulative":
        return df
    cumulative = df.sort_values(["origin", "dev"]).copy()
    cumulative["value"] = cumulative.groupby("origin")["value"].cumsum()
    return cumulative


def _incremental_view(df: pd.DataFrame, basis: str) -> pd.DataFrame:
    if basis == "incremental":
        return df
    incremental = df.sort_values(["origin", "dev"]).copy()
    incremental["value"] = incremental.groupby("origin")["value"].diff().fillna(incremental["value"])
    return incremental


def _check_monotone_cumulative(df: pd.DataFrame, basis: str) -> Check:
    cumulative = _cumulative_view(df, basis)
    for origin, group in cumulative.groupby("origin"):
        ordered = group.sort_values("dev")
        values = ordered["value"].tolist()
        devs = ordered["dev"].tolist()
        for i in range(1, len(values)):
            if values[i] < values[i - 1]:
                return Check(
                    "monotone_cumulative",
                    "warn",
                    {"origin": origin, "dev": int(devs[i]), "values": [values[i - 1], values[i]]},
                )
    return Check("monotone_cumulative", "pass")


def _check_nonneg_incrementals(df: pd.DataFrame, basis: str) -> Check:
    incremental = _incremental_view(df, basis)
    negatives = incremental[incremental["value"] < 0]
    if not negatives.empty:
        row = negatives.iloc[0]
        return Check(
            "nonneg_incrementals",
            "warn",
            {"origin": row["origin"], "dev": int(row["dev"]), "incremental": float(row["value"])},
        )
    return Check("nonneg_incrementals", "pass")
