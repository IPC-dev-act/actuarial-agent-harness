"""Test the Databricks reserving wheel in a Snowpark Python stored procedure."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


PYTHON_RUNTIME = "3.12"
PACKAGES = (
    "snowflake-snowpark-python",
    "chainladder==0.9.2",
    "pandas==2.3.3",
    "numpy==2.4.6",
)
ARCHIVE_NAME = "ipc_reserving_harness.zip"
WHEEL_NAME = "actuarial_agent_harness-0.2.9.post2-py3-none-any.whl"
RAA_HASH = "4cfaf9385ad50751d668d3ba33d64fa6f75b394d915a9f6318017c4777607643"


def run_probe(session):
    import json
    import sys
    from importlib.metadata import version
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from zipfile import ZipFile

    archive = Path(sys._xoptions["snowflake_import_directory"]) / "ipc_reserving_harness.zip"
    with TemporaryDirectory(prefix="ipc-harness-") as folder:
        # The shared report renderer reads its template through pathlib.
        # Unpack the wheel so its package data is on the local filesystem.
        with ZipFile(archive) as wheel:
            wheel.extractall(folder)
        sys.path.insert(0, folder)
        try:
            from databricks_demo.reserving import run_reserving

            cases = []
            for dataset, filename, method in (
                ("raa", "raa.csv", "mack"),
                ("raa", "raa.csv", "chain_ladder"),
                ("gapped", "triangle_gapped.csv", "mack"),
            ):
                csv_text = (Path(folder) / "examples" / filename).read_bytes().decode("utf-8")
                row = run_reserving(csv_text, dataset, method, f"wheel:{filename}", None)
                artifacts = row.pop("artifacts")
                row.pop("input_csv")
                validation = json.loads(artifacts.get("validation/validation.json", "{}"))
                row["checks"] = [check for check in validation.get("checks", []) if check["verdict"] != "pass"]
                row["report_is_draft"] = "draft/incomplete" in artifacts.get("model/report.html", "")
                row["artifacts"] = sorted(artifacts)
                cases.append(row)
            return {
                "python": sys.version.split()[0],
                "packages": {name: version(name) for name in ("chainladder", "pandas", "numpy")},
                "cases": cases,
            }
        finally:
            sys.path.remove(folder)


def check_probe(result):
    mack, basic, blocked = result["cases"]
    for row in (mack, basic):
        if (
            row["input_sha256"] != RAA_HASH
            or row["status"] != "review_required"
            or row["validation_verdict"] != "warn"
            or not row["report_is_draft"]
            or row["ibnr"] is None
            or not isclose(row["ibnr"], 52135.228261210155, abs_tol=0.001, rel_tol=0)
        ):
            raise ValueError(f"RAA parity failed for {row['method']}: {row['stage_exit_codes']}")
    if (
        mack["diagnostics_verdict"] != "warn"
        or mack["mack_se"] is None
        or not isclose(mack["mack_se"], 26909.01115564366, abs_tol=0.001, rel_tol=0)
        or basic["mack_se"] is not None
    ):
        raise ValueError("Mack and Basic Chain Ladder uncertainty results differ from the baseline.")
    if (
        blocked["status"] != "blocked_by_validation"
        or blocked["stage_exit_codes"] != {"validate": 2}
        or blocked["model_run_id"] is not None
        or blocked["ibnr"] is not None
        or "model/report.html" in blocked["artifacts"]
        or not any(check["check_id"] == "no_gaps" and check["verdict"] == "fail" for check in blocked["checks"])
    ):
        raise ValueError("Gapped input did not stop at validation as expected.")


def snowflake_probe(archive, connection_name):
    import inspect

    import snowflake.connector

    suffix = uuid4().hex[:12]
    stage = f"ipc_reserving_probe_stage_{suffix}"
    procedure = f"ipc_reserving_probe_{suffix}"
    packages = ", ".join(f"'{package}'" for package in PACKAGES)
    archive_path = archive.resolve().as_posix().replace("'", "''")
    handler = inspect.getsource(run_probe)

    with snowflake.connector.connect(connection_name=connection_name) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE()")
            if not all(cursor.fetchone()):
                raise ValueError("Set database, schema and warehouse in the named Snowflake connection.")
            cursor.execute(f"CREATE TEMPORARY STAGE {stage}")
            cursor.execute(f"PUT 'file://{archive_path}' @{stage} AUTO_COMPRESS = FALSE SOURCE_COMPRESSION = NONE")
            cursor.execute(f"""
                CREATE TEMPORARY PROCEDURE {procedure}()
                RETURNS VARIANT
                LANGUAGE PYTHON
                RUNTIME_VERSION = '{PYTHON_RUNTIME}'
                ARTIFACT_REPOSITORY = snowflake.snowpark.pypi_shared_repository
                PACKAGES = ({packages})
                IMPORTS = ('@{stage}/{ARCHIVE_NAME}')
                HANDLER = 'run_probe'
                EXECUTE AS CALLER
                AS $$
{handler}
$$
            """)
            cursor.execute(f"CALL {procedure}()")
            query_id = cursor.sfqid
            payload = cursor.fetchone()[0]
            result = json.loads(payload) if isinstance(payload, str) else payload
            return {"snowflake_query_id": query_id, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help=f"Path to {WHEEL_NAME}")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true", help="Run the packaged handler locally.")
    mode.add_argument("--connection", help="Named Python Connector connection in connections.toml.")
    options = parser.parse_args()
    if not options.wheel.is_file() or options.wheel.name != WHEEL_NAME:
        parser.error(f"provide the pinned wheel {WHEEL_NAME}")

    with TemporaryDirectory(prefix="ipc-snowflake-probe-") as folder:
        archive = Path(folder) / ARCHIVE_NAME
        shutil.copyfile(options.wheel, archive)
        if options.local:
            sys._xoptions["snowflake_import_directory"] = folder
            result = run_probe(None)
        else:
            result = snowflake_probe(archive, options.connection)
    print(json.dumps(result, indent=2, allow_nan=False))
    check_probe(result)


if __name__ == "__main__":
    main()
