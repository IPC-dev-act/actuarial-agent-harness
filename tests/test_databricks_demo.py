from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from databricks_demo.reserving import read_triangle, run_reserving, save_run, seed_triangles, table_names
from harness import manifest


RAA = Path(__file__).resolve().parents[1] / "examples" / "raa.csv"


@pytest.mark.parametrize("method", ["mack", "chain_ladder"])
def test_reserving_demo_runs_existing_harness_and_keeps_review_evidence(method):
    text = RAA.read_bytes().decode("utf-8")
    row = run_reserving(text, "raa", method, "`demo`.`default`.`triangles`", 3, "42")

    assert row["status"] == "review_required", row["stage_exit_codes"]
    assert row["validation_verdict"] == "warn"
    assert row["input_sha256"] == manifest.sha256_text(text)
    assert row["source_version"] == 3
    assert row["job_run_id"] == "42"
    assert row["ibnr"] == pytest.approx(52135.228261, abs=1e-3)
    assert (row["mack_se"] is not None) == (method == "mack")
    assert row["stage_exit_codes"]["report"] == 0
    assert "model/sensitivity.json" in row["artifacts"]
    assert "draft/incomplete" in row["artifacts"]["model/report.html"]
    assert json.loads(row["artifacts"]["model/manifest.json"])["inputs"][0]["sha256"] == row["input_sha256"]


def test_reserving_demo_records_validation_failure_without_fitting():
    text = RAA.with_name("triangle_gapped.csv").read_bytes().decode("utf-8")
    row = run_reserving(text, "gapped", "mack", "demo.default.triangles", 0)

    assert row["status"] == "blocked_by_validation"
    assert row["validation_verdict"] == "fail"
    assert row["stage_exit_codes"] == {"validate": 2}
    assert row["model_run_id"] is None
    assert row["ibnr"] is None
    assert set(row["artifacts"]) == {"validation/manifest.json", "validation/validation.json"}


def test_demo_delta_queries_bind_values_and_read_the_captured_version():
    calls = []

    def sql(query, args=None):
        calls.append((query, args))
        if "current_catalog()" in query:
            return SimpleNamespace(first=lambda: {"catalog": "workspace"})
        if "DESCRIBE HISTORY" in query:
            return SimpleNamespace(first=lambda: {"version": 7})
        if "SELECT origin, development, value" in query:
            return SimpleNamespace(collect=lambda: [{"origin": 1981, "development": 1981, "value": 5012.0}])
        return SimpleNamespace(collect=lambda: [])

    spark = SimpleNamespace(sql=sql)
    triangles, history = table_names(spark, "", "default")
    assert triangles == "`workspace`.`default`.`ipc_reserving_demo_triangles`"
    with pytest.raises(ValueError, match="catalog and schema"):
        table_names(spark, "workspace", "default`")

    seed_triangles(spark, triangles)
    assert "WHEN NOT MATCHED THEN INSERT" in calls[-1][0]
    seed_rows = json.loads(calls[-1][1]["rows"])
    assert sum(row["dataset"] == "raa" for row in seed_rows) == 55
    assert sum(row["dataset"] == "gapped" for row in seed_rows) == 35
    version, source = read_triangle(spark, triangles, "raa")
    assert version == 7
    assert source == "origin,development,value\n1981,1981,5012.0\n"
    assert "VERSION AS OF 7" in calls[-1][0]
    assert calls[-1][1] == {"dataset": "raa"}

    row = run_reserving(RAA.with_name("triangle_gapped.csv").read_text(), "gapped", "mack", triangles, version)
    save_run(spark, history, row)
    query, bindings = calls[-1]
    assert f"INSERT INTO {history}" in query
    assert row["input_csv"] not in query
    assert bindings["source_version"] == 7
    assert json.loads(bindings["stage_exit_codes"]) == {"validate": 2}
    assert json.loads(bindings["artifacts"]) == row["artifacts"]
