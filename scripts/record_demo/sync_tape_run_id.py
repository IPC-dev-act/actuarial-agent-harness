#!/usr/bin/env python3
"""scripts/record_demo/sync_tape_run_id.py — replaces every run-id-shaped
string in demo.tape with a freshly minted one.

Invoked by `make tape-sync`, which does the actual `reserve fit`/`reserve
report` calls and passes the resulting run-id as this script's only
argument — this script itself never runs `reserve`, `claude`, or any
recording tool, only a text substitution, so it can be exercised directly
in tests without any of those.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TAPE_PATH = Path(__file__).resolve().parent / "demo.tape"

# Matches harness/runs.py's own RUN_ID_RE shape (timestamp_tag_shorthash),
# unanchored so it finds occurrences embedded in prose/comments too.
RUN_ID_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[a-z0-9_]+_[0-9a-f]{6}")


def sync(tape_path: Path, new_run_id: str) -> int:
    """Replaces every run-id-shaped substring in `tape_path` with
    `new_run_id`, in place. Returns the number of occurrences replaced.
    """
    text = tape_path.read_text()
    new_text, count = RUN_ID_PATTERN.subn(new_run_id, text)
    tape_path.write_text(new_text)
    return count


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: sync_tape_run_id.py <run-id>", file=sys.stderr)
        sys.exit(1)
    new_run_id = sys.argv[1]

    count = sync(TAPE_PATH, new_run_id)
    if count == 0:
        print(f"warning: no run-id-shaped string found in {TAPE_PATH} — nothing replaced", file=sys.stderr)
    print(f"Synced {TAPE_PATH} to run-id: {new_run_id} ({count} occurrence(s) replaced)")


if __name__ == "__main__":
    main()
