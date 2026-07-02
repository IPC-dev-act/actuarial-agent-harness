import json
import re

import pytest

from harness import manifest, runs


def test_new_run_id_matches_expected_shape():
    run_id = runs.new_run_id("raa", "mack")
    assert runs.RUN_ID_RE.match(run_id), run_id


def test_new_run_id_sanitizes_and_lowercases_tag():
    run_id = runs.new_run_id("RAA Triangle!!", "Mack")
    tag_segment = run_id.split("_", 1)[1].rsplit("_", 1)[0]
    assert tag_segment == "raa_triangle_mack"


def test_new_run_id_unique_across_calls():
    ids = {runs.new_run_id("raa", "mack") for _ in range(20)}
    assert len(ids) == 20


def test_create_and_resolve_run_dir(tmp_path):
    run_id = runs.new_run_id("raa", "mack")
    created = runs.create_run_dir(run_id, out_root=tmp_path)
    assert created.is_dir()
    resolved = runs.resolve_run_dir(run_id, out_root=tmp_path)
    assert resolved == created


def test_resolve_missing_run_dir_raises(tmp_path):
    with pytest.raises(runs.RunNotFoundError):
        runs.resolve_run_dir("does-not-exist", out_root=tmp_path)


def test_run_exists(tmp_path):
    run_id = runs.new_run_id("raa", "mack")
    assert not runs.run_exists(run_id, out_root=tmp_path)
    runs.create_run_dir(run_id, out_root=tmp_path)
    assert runs.run_exists(run_id, out_root=tmp_path)


def test_list_run_ids_only_returns_dirs_with_manifest(tmp_path):
    good = runs.create_run_dir(runs.new_run_id("raa"), out_root=tmp_path)
    (good / "manifest.json").write_text("{}")
    runs.create_run_dir(runs.new_run_id("genins"), out_root=tmp_path)  # no manifest
    (tmp_path / "not_a_run.txt").write_text("stray file")

    listed = runs.list_run_ids(out_root=tmp_path)
    assert listed == [good.name]


def test_sha256_file_matches_known_content(tmp_path):
    import hashlib

    f = tmp_path / "x.csv"
    f.write_text("origin,development,value\n1981,1981,5012.0\n")
    direct = hashlib.sha256(f.read_bytes()).hexdigest()
    assert manifest.sha256_file(f) == direct


def test_locked_deps_sha256_is_stable_and_content_derived():
    a = manifest.locked_deps_sha256()
    b = manifest.locked_deps_sha256()
    assert a == b
    assert re.match(r"^[0-9a-f]{64}$", a)


def test_build_and_write_and_read_manifest_round_trips(tmp_path):
    run_id = runs.new_run_id("raa", "mack")
    run_dir = runs.create_run_dir(run_id, out_root=tmp_path)
    input_csv = tmp_path / "raa.csv"
    input_csv.write_text("origin,development,value\n1981,1981,5012.0\n")

    m = manifest.build_manifest(
        run_id=run_id,
        command="reserve fit examples/raa.csv --method mack",
        inputs=manifest.build_inputs([input_csv]),
        engine={"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
        parameters={"method": "mack"},
        outputs=["fit.json"],
        exit_code=0,
    )
    manifest.write_manifest(run_dir, m)

    read_back = manifest.read_manifest(run_dir)
    assert read_back == m
    assert read_back["run_id"] == run_id
    assert read_back["inputs"][0]["path"] == str(input_csv)
    assert len(read_back["inputs"][0]["sha256"]) == 64
    # created_utc parses as the documented format, e.g. 2026-07-02T14:31:08Z
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", read_back["created_utc"])


def test_update_manifest_appends_outputs_and_overwrites_exit_code(tmp_path):
    run_id = runs.new_run_id("raa", "mack")
    run_dir = runs.create_run_dir(run_id, out_root=tmp_path)
    m = manifest.build_manifest(
        run_id=run_id,
        command="reserve fit examples/raa.csv --method mack",
        inputs=[],
        engine={"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
        parameters={"method": "mack"},
        outputs=["fit.json"],
        exit_code=3,
    )
    manifest.write_manifest(run_dir, m)

    updated = manifest.update_manifest(run_dir, add_outputs=["diagnostics.json"], exit_code=3)
    assert updated["outputs"] == ["fit.json", "diagnostics.json"]
    assert updated["exit_code"] == 3
    assert updated["command"] == m["command"]  # provenance untouched

    # idempotent: re-adding an already-present output doesn't duplicate it
    updated_again = manifest.update_manifest(run_dir, add_outputs=["diagnostics.json"], exit_code=0)
    assert updated_again["outputs"] == ["fit.json", "diagnostics.json"]
    assert updated_again["exit_code"] == 0

    on_disk = json.loads((run_dir / "manifest.json").read_text())
    assert on_disk == updated_again
