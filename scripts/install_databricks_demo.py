"""Deploy, rehearse and configure Genie for the public RAA demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from reserving_mcp import databricks_api, read_sql


ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
WHEEL = f"actuarial_agent_harness-{VERSION}-py3-none-any.whl"
VOLUME = "reserving_demo_files"


def bundle(args, project, command, *options):
    return subprocess.run(
        ["databricks", "bundle", command, "--profile", args.profile,
         "--var", f"catalog={args.catalog},schema={args.schema},wheel={WHEEL}", *options],
        cwd=project, check=True, text=True, capture_output=command == "summary",
    )


def deployment(args, project):
    summary = json.loads(bundle(args, project, "summary", "--force-pull", "--output", "json").stdout)
    jobs = summary["resources"]["jobs"]
    url = summary["workspace"]["host"]
    return {
        "workspace": url,
        "notebook_folder": f"{summary['workspace']['file_path']}/databricks_demo",
        "volume": f"/Volumes/{args.catalog}/{args.schema}/{VOLUME}",
        "input_table": f"{args.catalog}.{args.schema}.ipc_reserving_demo_triangles",
        "run_history": f"{args.catalog}.{args.schema}.ipc_reserving_demo_run_history",
        "import_job": job_pointer(url, jobs["import_raa"]),
        "reserving_job": job_pointer(url, jobs["run_reserving"]),
    }


def job_pointer(workspace, job):
    job_id = int(job["id"])
    return {"id": job_id, "url": job.get("url") or f"{workspace.rstrip('/')}/jobs/{job_id}"}


def stage_bundle(project):
    shutil.copy2(ROOT / "databricks.yml", project)
    notebooks = project / "databricks_demo"
    notebooks.mkdir()
    for name in ("Import_Triangle.py", "Reserving_Demo.py"):
        shutil.copy2(ROOT / "databricks_demo" / name, notebooks)
    (project / "dist").mkdir()


def warehouse_id(args):
    if args.warehouse_id:
        return args.warehouse_id
    warehouses = databricks_api(args.profile, "get", "/api/2.0/sql/warehouses").get("warehouses", [])
    available = [row for row in warehouses if row.get("state") != "DELETED"]
    if len(available) == 1:
        return available[0]["id"]
    choices = ", ".join(f"{row['name']} ({row['id']})" for row in available)
    raise ValueError(f"Pass --warehouse-id for a SQL warehouse you can use. Available: {choices or 'none'}.")


def server_args(args, installed):
    return [
        str(ROOT / "scripts" / "reserving_mcp.py"), "--profile", args.profile,
        "--catalog", args.catalog, "--schema", args.schema, "--volume", VOLUME,
        "--import-job-id", str(installed["import_job"]["id"]),
        "--job-id", str(installed["reserving_job"]["id"]), "--warehouse-id", warehouse_id(args),
        "--workbench-runs", str(ROOT / "runs" / "databricks" / args.profile / args.catalog / args.schema),
    ]


def connect(args, installed):
    command = [
        "uv", "run", "--no-project", "--python", ">=3.11", "--with", "mcp==1.28.1",
        "python", *server_args(args, installed),
    ]
    return {
        "claude_code": shlex.join(["claude", "mcp", "add", "--scope", "local", "ipc-reserving", "--", *command]),
        "codex": shlex.join(["codex", "mcp", "add", "ipc-reserving", "--", *command]),
    }


async def rehearse(args, installed):
    env = {name: os.environ[name] for name in ("DATABRICKS_CONFIG_FILE", "HTTPS_PROXY", "NO_PROXY") if name in os.environ}
    server = StdioServerParameters(command=sys.executable, args=server_args(args, installed), env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()

            async def call(name, arguments):
                response = await client.call_tool(name, arguments)
                if response.isError or response.structuredContent is None:
                    raise RuntimeError(f"{name} failed: {response.content}")
                return response.structuredContent

            async def wait(tool, run_id):
                deadline = time.monotonic() + 900
                while time.monotonic() < deadline:
                    result = await call(tool, {"run_id": run_id})
                    if result["job_result"] == "SUCCESS":
                        return result
                    if result["job_result"] or result["job_state"] in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR", "BLOCKED"}:
                        raise RuntimeError(f"Lakeflow run stopped: {result}")
                    await asyncio.sleep(5)
                raise TimeoutError(f"Lakeflow run {run_id} is still pending. Retry with the same request ID.")

            request_id = str(args.request_id)
            started = await call("import_raa_triangle", {"request_id": request_id})
            imported = await wait("get_raa_import", started["run_id"])
            imported["uploaded_csv"] = started["uploaded_csv"]
            if imported["observations"] != 55:
                raise ValueError(f"Expected 55 RAA observations: {imported}")
            started = await call("run_raa_reserving", {
                "method": "mack", "request_id": request_id, "source_version": imported["source_version"],
            })
            run = await wait("get_raa_run", started["run_id"])
            if (
                run.get("source_version") != imported["source_version"]
                or round(run.get("ibnr") or 0, 2) != 52135.23
                or round(run.get("mack_se") or 0, 2) != 26909.01
                or not run.get("draft_report_available")
                or run.get("status") != "review_required"
            ):
                raise ValueError(f"The Mack run differs from the expected RAA result: {run}")
            report = await call("prepare_raa_workbench", {"run_id": started["run_id"]})
            return {"import": imported, "mack": run, "report": report}


def configure_genie(args, installed):
    warehouse = warehouse_id(args)
    prefix = f"`{args.catalog}`.`{args.schema}`"
    view_name = f"{args.catalog}.{args.schema}.ipc_raa_reserving_review"
    title = f"RAA reserving review ({args.catalog}.{args.schema})"

    def api(method, path, **options):
        return databricks_api(args.profile, method, path, **options)

    username = api("get", "/api/2.0/preview/scim/v2/Me")["userName"]
    parent_path = f"/Workspace/Users/{username}"

    def describe(space_id):
        url = f"{installed['workspace'].rstrip('/')}/genie/rooms/{space_id}"
        return {"title": title, "space_id": space_id, "url": url, "view": view_name}

    read_sql(api, warehouse, f"""
        CREATE OR REPLACE VIEW {prefix}.ipc_raa_reserving_review AS
        SELECT attempt_id, started_at, job_run_id, method, status, source_version,
               ibnr, mack_se,
               get_json_object(artifacts['validation/validation.json'], '$.checks') AS validation_checks,
               get_json_object(artifacts['model/diagnostics.json'], '$.tests') AS diagnostic_tests
        FROM {prefix}.ipc_reserving_demo_run_history
        WHERE dataset = 'raa' AND status IN ('review_required', 'draft_ready')
    """)
    question = "What did the latest RAA Mack run estimate, and why does it require review?"
    page_token = None
    while True:
        query = {"page_token": page_token} if page_token else None
        page = api("get", "/api/2.0/genie/spaces", query=query)
        for space in page.get("spaces", []):
            if (space.get("title"), space.get("parent_path"), space.get("warehouse_id")) == (title, parent_path, warehouse):
                detail = api("get", f"/api/2.0/genie/spaces/{space['space_id']}",
                             query={"include_serialized_space": "true"})
                sources = json.loads(detail["serialized_space"])["data_sources"]["tables"]
                if [source["identifier"] for source in sources] == [view_name]:
                    return describe(space["space_id"])
                raise ValueError(f"The existing Genie agent {space['space_id']} uses a different data source.")
        page_token = page.get("next_page_token")
        if not page_token:
            break
    serialized_space = {
        "version": 2,
        "config": {"sample_questions": [{"id": uuid4().hex, "question": [question]}]},
        "data_sources": {"tables": [{"identifier": view_name}]},
        "instructions": {"text_instructions": [{
            "id": uuid4().hex,
            "content": ["Use the stored reserve and standard error. Cite the attempt ID and input Delta version. "
                        "For review questions explain the saved checks with verdict warn."],
        }]},
    }
    created = api("post", "/api/2.0/genie/spaces", body={
        "title": title, "parent_path": parent_path, "warehouse_id": warehouse,
        "serialized_space": json.dumps(serialized_space),
    })
    return describe(created["space_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "connect", "rehearse", "genie"])
    parser.add_argument("--profile", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", default="ipc_reserving_demo")
    parser.add_argument("--warehouse-id")
    parser.add_argument("--request-id", type=UUID)
    args = parser.parse_args()
    for name in (args.profile, args.catalog, args.schema):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", name):
            parser.error("Use letters, digits, underscores or hyphens for profile, catalog and schema.")
    with TemporaryDirectory(prefix="ipc-reserving-") as directory:
        project = Path(directory)
        stage_bundle(project)
        if args.action == "deploy":
            subprocess.run(
                ["uv", "build", "--python", sys.executable, "--wheel",
                 "--out-dir", str(project / "dist"), str(ROOT)],
                check=True,
            )
            bundle(args, project, "validate")
            bundle(args, project, "deploy")
        installed = deployment(args, project)
    if args.action == "connect":
        installed["mcp"] = connect(args, installed)
    if args.action == "rehearse":
        args.request_id = args.request_id or uuid4()
        print(f"Rehearsal request ID: {args.request_id}", file=sys.stderr, flush=True)
        installed.update(asyncio.run(rehearse(args, installed)))
    if args.action == "genie":
        installed["genie"] = configure_genie(args, installed)
    print(json.dumps(installed, indent=2))


if __name__ == "__main__":
    main()
