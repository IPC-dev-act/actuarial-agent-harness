"""MCP tools for the RAA demo using a signed-in Databricks CLI profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def databricks_api(profile, method, path, *, query=None, body=None):
    if query:
        path += "?" + urlencode(query)
    command = ["databricks", "api", method, path, "--profile", profile]
    if body is not None:
        command += ["--json", json.dumps(body)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Databricks API failed for {method.upper()} {path}.")
    return json.loads(result.stdout)


def read_sql(api, warehouse_id, statement, run_id=None):
    response = api("post", "/api/2.0/sql/statements", body={
        "warehouse_id": warehouse_id,
        "statement": statement,
        "parameters": [] if run_id is None else [{"name": "run_id", "value": str(run_id)}],
        "wait_timeout": "10s",
    })
    deadline = time.monotonic() + 90
    while response["status"]["state"] in {"PENDING", "RUNNING"}:
        if time.monotonic() >= deadline:
            raise TimeoutError("The SQL warehouse is still starting. Retry the result lookup shortly.")
        time.sleep(2)
        response = api("get", f"/api/2.0/sql/statements/{response['statement_id']}")
    if response["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(response["status"].get("error", {}).get("message", "The evidence query failed."))
    rows = (response.get("result") or {}).get("data_array") or []
    if not rows:
        return []
    columns = [column["name"] for column in response["manifest"]["schema"]["columns"]]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def restore_workbench_run(root, row):
    """Restore the model artifacts and exact input snapshot from a Delta row."""
    run_id = row["model_run_id"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_raa_(mack|chain_ladder)_[0-9a-f]{6}", run_id or ""):
        raise ValueError("This attempt has no RAA model run to open.")
    artifacts = json.loads(row["artifacts"])
    manifest = json.loads(artifacts["model/manifest.json"])
    input_entry = manifest["inputs"][0]
    source = row["input_csv"].encode("utf-8")
    if (
        manifest["run_id"] != run_id
        or input_entry["snapshot"] != "inputs/raa.csv"
        or hashlib.sha256(source).hexdigest() != row["input_sha256"]
        or input_entry["sha256"] != row["input_sha256"]
    ):
        raise ValueError("The saved run and input snapshot do not match.")

    root.mkdir(parents=True, exist_ok=True)
    target = root / run_id
    if target.is_dir():
        return target
    with TemporaryDirectory(dir=root, prefix=".delta-run-") as temporary:
        staging = Path(temporary) / run_id
        (staging / "inputs").mkdir(parents=True)
        (staging / input_entry["snapshot"]).write_bytes(source)
        for key, value in artifacts.items():
            if re.fullmatch(r"model/[a-zA-Z0-9_-]+\.(json|html)", key):
                (staging / key.removeprefix("model/")).write_bytes(value.encode("utf-8"))
        try:
            staging.rename(target)
        except OSError:
            if not target.is_dir():
                raise
    return target


def create_server(profile, job_id, warehouse_id, catalog, schema, workbench_runs, *, import_job_id, volume):
    if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", name) for name in (catalog, schema, volume)):
        raise ValueError("Use catalog, schema and volume names with letters, digits, underscores or hyphens.")
    triangles = f"`{catalog}`.`{schema}`.`ipc_reserving_demo_triangles`"
    table = f"`{catalog}`.`{schema}`.`ipc_reserving_demo_run_history`"
    csv_file = Path(__file__).resolve().with_name("raa.csv")
    mcp = FastMCP("Actuary in Databricks")

    def api(method, path, **options):
        return databricks_api(profile, method, path, **options)

    def get_job_run(run_id, expected_job_id):
        run = api("get", "/api/2.2/jobs/runs/get", query={"run_id": run_id})
        if run["job_id"] != expected_job_id:
            raise ValueError("This run belongs to another Lakeflow job.")
        return run

    def job_summary(run):
        state = run.get("state") or {}
        return {
            "run_url": run.get("run_page_url"),
            "job_state": state.get("life_cycle_state"),
            "job_result": state.get("result_state"),
            "job_message": state.get("state_message"),
        }

    def get_evidence(run_id, columns):
        query = f"""
            SELECT {columns} FROM {table}
            WHERE job_run_id = :run_id AND dataset = 'raa'
            ORDER BY started_at DESC, attempt_id DESC LIMIT 1
        """
        return next(iter(read_sql(api, warehouse_id, query, run_id)), None)

    @mcp.tool(annotations=ToolAnnotations(idempotentHint=True, openWorldHint=True))
    def import_raa_triangle(request_id: UUID) -> dict[str, Any]:
        """Upload the bundled public RAA CSV to the configured volume and start Import_Triangle, which replaces the demo RAA rows. Reuse request_id to retry."""
        file_name = f"raa-{request_id.hex}.csv"
        volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{file_name}"
        source = csv_file if csv_file.is_file() else csv_file.parents[1] / "examples" / "raa.csv"
        upload = subprocess.run(["databricks", "fs", "cp", str(source), f"dbfs:{volume_path}",
                                 "--overwrite", "--profile", profile], capture_output=True, text=True, timeout=60)
        upload.check_returncode()
        started = api("post", "/api/2.2/jobs/run-now", body={
            "job_id": import_job_id,
            "idempotency_token": f"import-{request_id}",
            "job_parameters": {"catalog": catalog, "schema": schema, "volume": volume, "file_name": file_name},
        })
        return {**started, "uploaded_csv": volume_path}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def get_raa_import(run_id: int) -> dict[str, Any]:
        """Check the import job. On success, return the Delta table and version and preview five rows from that version."""
        run = get_job_run(run_id, import_job_id)
        summary = {"job_run_id": run_id, **job_summary(run)}
        if summary["job_result"] != "SUCCESS":
            return summary
        task_id = run["tasks"][0]["run_id"]
        output = api("get", "/api/2.2/jobs/runs/get-output", query={"run_id": task_id})
        imported = json.loads(output["notebook_output"]["result"])
        if imported["table"] != triangles:
            raise ValueError("The import used a different catalog or schema.")
        version = int(imported["source_version"])
        rows = read_sql(api, warehouse_id, f"""
            SELECT origin, development, value FROM {triangles} VERSION AS OF {version}
            WHERE dataset = 'raa' ORDER BY origin, development LIMIT 5
        """)
        return {**summary, **imported, "preview": rows}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def run_raa_reserving(method: Literal["mack", "chain_ladder"], request_id: UUID, source_version: int | None = None) -> dict[str, Any]:
        """Start reserving from Delta. Pass the version returned by the import to use that snapshot. Reuse request_id to retry."""
        if source_version is not None and source_version < 0:
            raise ValueError("Use a non-negative Delta input version.")
        version = "" if source_version is None else str(source_version)
        return api("post", "/api/2.2/jobs/run-now", body={
            "job_id": job_id,
            "idempotency_token": f"reserve-{request_id}",
            "job_parameters": {"dataset": "raa", "method": method, "source_version": version,
                               "catalog": catalog, "schema": schema},
        })

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True))
    def get_raa_run(run_id: int) -> dict[str, Any]:
        """Check job progress and read the completed run, including Mack uncertainty and saved diagnostic warnings."""
        run = get_job_run(run_id, job_id)
        summary = {"job_run_id": run_id, **job_summary(run)}
        if summary["job_result"] != "SUCCESS":
            return summary

        evidence = get_evidence(run_id, """
            attempt_id, model_run_id, method, status, source_table, source_version, input_sha256,
            ibnr, mack_se, harness_version,
            artifacts['validation/validation.json'] AS validation,
            artifacts['model/diagnostics.json'] AS diagnostics,
            artifacts['model/report.html'] IS NOT NULL AS draft_report_available
        """)
        if evidence is None:
            return {**summary, "evidence_status": "No Delta row found for this job run ID."}
        validation = json.loads(evidence.pop("validation") or "{}")
        diagnostics = json.loads(evidence.pop("diagnostics") or "{}")
        evidence["validation_warnings"] = [item for item in validation.get("checks", []) if item["verdict"] == "warn"]
        evidence["diagnostics_warnings"] = [item for item in diagnostics.get("tests", []) if item["verdict"] == "warn"]
        for key in ("ibnr", "mack_se"):
            if evidence[key] is not None:
                evidence[key] = float(evidence[key])
        evidence["source_version"] = int(evidence["source_version"])
        evidence["draft_report_available"] = str(evidence["draft_report_available"]).lower() == "true"
        return {**summary, **evidence}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True, openWorldHint=True))
    def prepare_raa_workbench(run_id: int) -> dict[str, str | None]:
        """Restore a completed Lakeflow run into the local actuarial workbench for human review."""
        run = get_job_run(run_id, job_id)
        if (run.get("state") or {}).get("result_state") != "SUCCESS":
            raise ValueError("Wait for the Lakeflow job to complete successfully.")
        evidence = get_evidence(run_id, "attempt_id, model_run_id, input_csv, input_sha256, to_json(artifacts) AS artifacts")
        if evidence is None:
            raise ValueError("No Delta row found for this job run ID.")
        directory = restore_workbench_run(workbench_runs, evidence)
        return {"attempt_id": evidence["attempt_id"], "model_run_id": directory.name,
                "runs_directory": str(workbench_runs), "run_url": run.get("run_page_url"),
                "draft_report_path": str(directory / "report.html")}

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="ipc-demo")
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--import-job-id", type=int, required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", default="default")
    parser.add_argument("--volume", default="reserving_demo_files")
    parser.add_argument("--workbench-runs", type=Path, default=Path("databricks-workbench-runs"))
    args = parser.parse_args()
    create_server(args.profile, args.job_id, args.warehouse_id, args.catalog, args.schema,
                  args.workbench_runs.resolve(), import_job_id=args.import_job_id, volume=args.volume).run()
