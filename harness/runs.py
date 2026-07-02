"""Run folder lifecycle: minting run_ids, creating/locating runs/<run_id>/.

Engine-agnostic — no chainladder import (ARCHITECTURE.md).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RUNS_ROOT = Path("runs")

_TAG_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9]+")
RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[a-z0-9_]+_[0-9a-f]{6}$")


class RunNotFoundError(Exception):
    def __init__(self, run_id: str, out_root: Path):
        super().__init__(f"run '{run_id}' not found under {out_root}")
        self.run_id = run_id
        self.out_root = out_root


def input_tag(*parts: str) -> str:
    """Sanitizes free-form parts (input filename stem, method name, ...)
    into the run_id's input-tag segment: lowercase, alnum, underscore-joined.
    """
    tag = "_".join(p for p in parts if p)
    tag = _TAG_SANITIZE_RE.sub("_", tag).strip("_").lower()
    return tag or "run"


def new_run_id(*tag_parts: str, when: datetime | None = None) -> str:
    """Mints a run_id: <UTC timestamp>_<input tag>_<short hash>.

    The short hash is a random nonce (not content-derived) purely to avoid
    collisions between runs minted within the same second; input/engine
    provenance is already captured in manifest.json's own fields.
    """
    when = when or datetime.now(timezone.utc)
    timestamp = when.strftime("%Y-%m-%dT%H-%M-%S")
    tag = input_tag(*tag_parts)
    short_hash = secrets.token_hex(3)
    return f"{timestamp}_{tag}_{short_hash}"


def run_dir_path(run_id: str, out_root: Path = DEFAULT_RUNS_ROOT) -> Path:
    return Path(out_root) / run_id


def create_run_dir(run_id: str, out_root: Path = DEFAULT_RUNS_ROOT) -> Path:
    path = run_dir_path(run_id, out_root)
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_exists(run_id: str, out_root: Path = DEFAULT_RUNS_ROOT) -> bool:
    return run_dir_path(run_id, out_root).is_dir()


def resolve_run_dir(run_id: str, out_root: Path = DEFAULT_RUNS_ROOT) -> Path:
    """Looks up an existing run folder; raises RunNotFoundError if absent."""
    path = run_dir_path(run_id, out_root)
    if not path.is_dir():
        raise RunNotFoundError(run_id, out_root)
    return path


def list_run_ids(out_root: Path = DEFAULT_RUNS_ROOT) -> list[str]:
    root = Path(out_root)
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and (p / "manifest.json").is_file()
    )
