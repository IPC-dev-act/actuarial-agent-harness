"""Run manifests: hashes, versions, timestamps (ARCHITECTURE.md#manifest).

Engine-agnostic — no chainladder import. Engine identity (adapter/package/
version) is supplied by the caller as a plain dict; this module never
imports an engine package itself, not even for version lookup.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from harness import __version__ as HARNESS_VERSION

MANIFEST_FILENAME = "manifest.json"

# Direct pinned dependencies (pyproject.toml) whose exact resolved versions
# feed environment.locked_deps_sha256. Read via package metadata, not import
# — this never triggers `import chainladder`.
PINNED_DEP_NAMES = ["chainladder", "pandas", "numpy"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def locked_deps_sha256(dep_names: list[str] = PINNED_DEP_NAMES) -> str:
    pinned = {name: metadata.version(name) for name in dep_names}
    joined = ",".join(f"{name}=={version}" for name, version in sorted(pinned.items()))
    return sha256_text(joined)


def build_environment() -> dict:
    return {
        "python": platform.python_version(),
        "harness_version": HARNESS_VERSION,
        "locked_deps_sha256": locked_deps_sha256(),
    }


def build_inputs(paths: list[Path]) -> list[dict]:
    return [{"path": str(p), "sha256": sha256_file(p)} for p in paths]


def build_manifest(
    *,
    run_id: str,
    command: str,
    inputs: list[dict],
    engine: dict,
    parameters: dict,
    outputs: list[str],
    exit_code: int,
    environment: dict | None = None,
    created_utc: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "created_utc": created_utc or utc_now_iso(),
        "command": command,
        "inputs": inputs,
        "engine": engine,
        "environment": environment or build_environment(),
        "parameters": parameters,
        "outputs": outputs,
        "exit_code": exit_code,
    }


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    path = Path(run_dir) / MANIFEST_FILENAME
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def read_manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / MANIFEST_FILENAME).read_text())


def update_manifest(run_dir: Path, *, add_outputs: list[str], exit_code: int) -> dict:
    """Amends an existing run's manifest in place (shared-folder model:
    `diagnostics`/`sensitivity` append to a `fit` run's manifest rather than
    minting their own — docs/QUESTIONS.md Q1). `outputs` gains any new
    filenames; `exit_code` is overwritten with the latest command's code.
    """
    manifest = read_manifest(run_dir)
    for name in add_outputs:
        if name not in manifest["outputs"]:
            manifest["outputs"].append(name)
    manifest["exit_code"] = exit_code
    write_manifest(run_dir, manifest)
    return manifest
