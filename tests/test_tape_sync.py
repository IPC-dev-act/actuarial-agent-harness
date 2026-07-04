"""Tests scripts/record_demo/sync_tape_run_id.py's substitution logic in
isolation — no `reserve`, `claude`, or recording tool invoked, so this can
run as part of the normal suite (unlike the rest of scripts/record_demo/,
which either bills real API usage or needs tools not installed in CI).

The `make tape-sync` Makefile target itself (which actually runs `reserve
fit`/`reserve report` and calls this script with a real run-id) is
manually verified instead — see the commit message for the before/after
`scripts/record_demo/demo.tape` diff from that manual run.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC_SCRIPT = REPO_ROOT / "scripts" / "record_demo" / "sync_tape_run_id.py"

OLD_RUN_ID = "2026-07-04T13-57-22_raa_mack_779705"
NEW_RUN_ID = "2026-08-01T09-00-00_raa_mack_abcdef"


def _load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_tape_run_id", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_replaces_every_occurrence(tmp_path):
    module = _load_sync_module()
    tape = tmp_path / "demo.tape"
    tape.write_text(
        f"# real run-id observed: {OLD_RUN_ID}\n"
        f'Type "reserve diagnostics {OLD_RUN_ID} --format json | head -30"\n'
        f'Type "reserve report {OLD_RUN_ID} --format-out html"\n'
    )

    count = module.sync(tape, NEW_RUN_ID)

    assert count == 3
    text = tape.read_text()
    assert OLD_RUN_ID not in text
    assert text.count(NEW_RUN_ID) == 3


def test_sync_no_match_replaces_nothing(tmp_path):
    module = _load_sync_module()
    tape = tmp_path / "demo.tape"
    original = 'Type "echo hello"\n'
    tape.write_text(original)

    count = module.sync(tape, NEW_RUN_ID)

    assert count == 0
    assert tape.read_text() == original


def test_sync_against_the_real_tape_pattern_shape(tmp_path):
    # Guards against the regex silently stopping matching real run_ids —
    # harness/runs.py's own RUN_ID_RE shape: timestamp_tag_shorthash, where
    # the tag itself may contain underscores (e.g. "raa_mack").
    module = _load_sync_module()
    tape = tmp_path / "demo.tape"
    tape.write_text("2026-01-01T00-00-00_some_long_tag_abc123\n")

    count = module.sync(tape, NEW_RUN_ID)

    assert count == 1
    assert tape.read_text().strip() == NEW_RUN_ID
