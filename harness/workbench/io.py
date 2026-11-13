"""Shared run-artifact I/O for the workbench layer."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from harness import manifest

from . import schemas

_RUN_ID_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})"
)
_CREATED_UTC_FALLBACK = "1970-01-01T00:00:00Z"


def read_json(path: Path) -> dict[str, Any]:
    # Older run artifacts may encode unavailable results as NaN or Infinity.
    return json.loads(Path(path).read_text(), parse_constant=lambda _token: None)


def maybe_read_json(run_dir: Path, filename: str) -> dict[str, Any] | None:
    path = Path(run_dir) / filename
    return read_json(path) if path.is_file() else None


def write_json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            # Linking a complete same-directory temporary file is atomic and
            # fails if the immutable target already exists.
            os.link(temporary_path, path)
        else:
            os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def run_created_utc(run_id: str, run_dir: Path) -> str:
    run_manifest = maybe_read_json(run_dir, "manifest.json")
    if run_manifest and run_manifest.get("created_utc"):
        return run_manifest["created_utc"]
    match = _RUN_ID_TIMESTAMP_RE.match(run_id)
    if match:
        return (
            f"{match.group('date')}T{match.group('hour')}:"
            f"{match.group('minute')}:{match.group('second')}Z"
        )
    return _CREATED_UTC_FALLBACK


def artifact_availability(run_dir: Path) -> dict[str, bool]:
    root = Path(run_dir)
    return {name: (root / name).is_file() for name in schemas.ARTIFACTS}


def artifact_hashes(run_dir: Path, artifact_names: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    root = Path(run_dir)
    for name in artifact_names:
        path = root / name
        if path.is_file():
            hashes[name] = manifest.sha256_file(path)
    return hashes


def decisions_dir(run_dir: Path) -> Path:
    return Path(run_dir) / schemas.DECISIONS_DIRNAME


def decision_path(run_dir: Path, decision_id: str) -> Path:
    return decisions_dir(run_dir) / f"{decision_id}.json"


def load_decisions(run_dir: Path) -> list[dict[str, Any]]:
    root = decisions_dir(run_dir)
    if not root.is_dir():
        return []
    decisions = []
    for path in sorted(root.glob("*.json")):
        decisions.append(read_json(path))
    return decisions


def superseded_decision_ids(decisions: list[dict[str, Any]]) -> set[str]:
    return {
        d["supersedes_decision_id"]
        for d in decisions
        if d.get("supersedes_decision_id")
    }


def active_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = superseded_decision_ids(decisions)
    return [d for d in decisions if d.get("decision_id") not in superseded]


def completing_decisions_by_task(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    completed: dict[str, dict[str, Any]] = {}
    for decision in active_decisions(decisions):
        task_id = decision.get("task_id")
        if task_id and decision.get("status") in {"accepted", "modified"}:
            completed[task_id] = decision
    return completed


def has_active_report_approval(decisions: list[dict[str, Any]]) -> bool:
    return any(
        d.get("decision_type") == "report_approval"
        and d.get("status") in {"accepted", "modified"}
        for d in active_decisions(decisions)
    )
