"""Deploy and run the Snowflake reserving demo using a named connection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from io import StringIO
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from snowflake_demo.runtime_probe import ARCHIVE_NAME, PACKAGES, PYTHON_RUNTIME, WHEEL_NAME


HERE = Path(__file__).resolve().parent
SAMPLES = {"raa": "raa.csv", "gapped": "triangle_gapped.csv"}
METHODS = ("mack", "chain_ladder")
HEADER = ("origin", "development", "value")


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,254}", value):
        raise ValueError("Use an unquoted Snowflake identifier with letters, digits and underscores.")
    return value.upper()


def demo_id(value):
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise argparse.ArgumentTypeError("Use the 32-character hex ID printed by the demo.")
    return value


def connect(options):
    import snowflake.connector

    return snowflake.connector.connect(
        connection_name=options.connection, warehouse=identifier(options.warehouse), paramstyle="qmark",
    )


def rows(cursor, query, params=None):
    cursor.execute(query, params)
    names = [column.name.lower() for column in cursor.description]
    return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def check_connection(cursor):
    result = rows(cursor, "SELECT CURRENT_ROLE() AS ROLE_NAME, CURRENT_WAREHOUSE() AS WAREHOUSE_NAME")[0]
    if not result["warehouse_name"]:
        raise ValueError("Select a usable Snowflake warehouse with --warehouse.")
    return result


def upload(cursor, path, stage_location):
    path_sql = path.resolve().as_posix().replace("'", "''")
    cursor.execute(f"PUT 'file://{path_sql}' {stage_location} AUTO_COMPRESS = FALSE SOURCE_COMPRESSION = NONE")
    transfers = cursor.fetchall()
    if len(transfers) != 1 or transfers[0][6] not in {"UPLOADED", "SKIPPED"}:
        raise RuntimeError(f"Upload to {stage_location} did not complete: {transfers}")


def setup(cursor, database, schema, wheel):
    if not wheel.is_file() or wheel.name != WHEEL_NAME:
        raise ValueError(f"Build or provide {WHEEL_NAME} before setup.")
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
    namespace = f"{database}.{schema}"
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {namespace}")
    cursor.execute(f"USE SCHEMA {namespace}")
    for statement in (HERE / "schema.sql").read_text(encoding="utf-8").split(";"):
        if statement.strip():
            cursor.execute(statement)

    bundle_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    bundle_stage = f"@{namespace}.RESERVING_FILES/bundles/{bundle_sha256}"
    with TemporaryDirectory(prefix="ipc-snowflake-bundle-") as folder:
        archive = Path(folder) / ARCHIVE_NAME
        shutil.copyfile(wheel, archive)
        upload(cursor, archive, bundle_stage)

    packages = ", ".join(f"'{package}'" for package in PACKAGES)
    handler = (HERE / "procedure.py").read_text(encoding="utf-8")
    cursor.execute(f"""
        CREATE OR REPLACE PROCEDURE {namespace}.RUN_RESERVING(
            IMPORT_ID VARCHAR, METHOD VARCHAR, ATTEMPT_ID VARCHAR, TASK_RUN_GROUP_ID VARCHAR
        ) COPY GRANTS
        RETURNS VARIANT
        LANGUAGE PYTHON
        RUNTIME_VERSION = '{PYTHON_RUNTIME}'
        ARTIFACT_REPOSITORY = snowflake.snowpark.pypi_shared_repository
        PACKAGES = ({packages})
        IMPORTS = ('{bundle_stage}/{ARCHIVE_NAME}')
        HANDLER = 'run_attempt'
        EXECUTE AS OWNER
        AS $$
{handler}
$$
    """)
    return {"schema": namespace, "bundle_sha256": bundle_sha256, "procedure": f"{namespace}.RUN_RESERVING"}


def parse_triangle(source):
    reader = csv.reader(StringIO(source.decode("utf-8"), newline=""), strict=True)
    if tuple(next(reader, ())) != HEADER:
        raise ValueError("Expected CSV header origin,development,value.")
    result = []
    for origin, development, value in reader:
        row = (int(origin), int(development), float(value))
        if not isfinite(row[2]):
            raise ValueError("Triangle values must be finite.")
        result.append(row)
    if not result:
        raise ValueError("The triangle CSV has no observations.")
    return sorted(result, key=lambda row: row[:2])


def canonical_csv(observations):
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(observations)
    return buffer.getvalue()


def import_triangle(cursor, namespace, dataset, source_path):
    source = source_path.read_bytes()
    expected = parse_triangle(source)
    import_id = uuid4().hex
    stage = f"@{namespace}.RESERVING_FILES/inputs/{import_id}"
    landing = f"{namespace}.TRIANGLE_LOAD_{import_id}"
    with TemporaryDirectory(prefix="ipc-snowflake-input-") as folder:
        path = Path(folder) / "triangle.csv"
        path.write_bytes(source)
        upload(cursor, path, stage)
    cursor.execute(f"""
        CREATE TEMPORARY TABLE {landing} (
            ORIGIN INTEGER, DEVELOPMENT INTEGER, CLAIM_VALUE DOUBLE, FILE_ROW_NUMBER INTEGER
        )
    """)
    cursor.execute(f"""
        COPY INTO {landing} (ORIGIN, DEVELOPMENT, CLAIM_VALUE, FILE_ROW_NUMBER)
        FROM (SELECT t.$1, t.$2, t.$3, METADATA$FILE_ROW_NUMBER FROM {stage}/triangle.csv t)
        FILE_FORMAT = (FORMAT_NAME = '{namespace}.RESERVING_CSV') ON_ERROR = ABORT_STATEMENT
    """)
    copy_query_id = cursor.sfqid
    cursor.execute(f"SELECT ORIGIN, DEVELOPMENT, CLAIM_VALUE FROM {landing} ORDER BY ORIGIN, DEVELOPMENT, FILE_ROW_NUMBER")
    loaded = cursor.fetchall()
    if loaded != expected:
        raise ValueError("Snowflake loaded different observations from the supplied CSV.")
    input_csv = canonical_csv(loaded)
    input_hash = hashlib.sha256(input_csv.encode("utf-8")).hexdigest()
    file_hash = hashlib.sha256(source).hexdigest()
    stage_file = f"{stage}/triangle.csv"
    cursor.execute(f"""
        INSERT INTO {namespace}.RESERVING_IMPORTS
            (IMPORT_ID, DATASET, STAGE_FILE, FILE_SHA256, INPUT_SHA256, INPUT_CSV, OBSERVATIONS)
        SELECT ?, ?, ?, ?, ?, ?, AS_ARRAY(PARSE_JSON(?))
    """, (import_id, dataset, stage_file, file_hash, input_hash, input_csv, json.dumps(loaded, allow_nan=False)))
    return {
        "import_id": import_id, "dataset": dataset, "rows": len(loaded), "input_sha256": input_hash,
        "file_sha256": file_hash, "stage_file": stage_file, "copy_query_id": copy_query_id,
        "observations_view": f"{namespace}.RESERVING_TRIANGLES",
    }


def run_reserving(cursor, namespace, import_id, method):
    attempt_id = uuid4().hex
    cursor.execute(f"ALTER SESSION SET QUERY_TAG = 'ipc-reserving:{attempt_id}'")
    cursor.execute(f"CALL {namespace}.RUN_RESERVING(?, ?, ?, ?)", (import_id, method, attempt_id, None))
    query_id = cursor.sfqid
    payload = cursor.fetchone()[0]
    result = json.loads(payload) if isinstance(payload, str) else payload
    cursor.execute(f"""
        UPDATE {namespace}.RESERVING_ATTEMPTS SET PLATFORM_QUERY_ID = ?
        WHERE ATTEMPT_ID = ? AND PLATFORM_QUERY_ID IS NULL
    """, (query_id, attempt_id))
    return {**result, "platform_query_id": query_id}


def deploy_task(cursor, namespace, warehouse):
    cursor.execute(f"""
        CREATE TASK IF NOT EXISTS {namespace}.RESERVING_JOB WAREHOUSE = {warehouse}
        AS CALL {namespace}.RUN_RESERVING(
            SYSTEM$GET_TASK_GRAPH_CONFIG('import_id')::VARCHAR,
            SYSTEM$GET_TASK_GRAPH_CONFIG('method')::VARCHAR,
            SYSTEM$GET_TASK_GRAPH_CONFIG('attempt_id')::VARCHAR,
            SYSTEM$TASK_RUNTIME_INFO('CURRENT_TASK_GRAPH_RUN_GROUP_ID')::VARCHAR
        )
    """)
    return {"task": f"{namespace}.RESERVING_JOB"}


def start_task(cursor, namespace, import_id, method):
    attempt_id = uuid4().hex
    config = json.dumps({"import_id": import_id, "method": method, "attempt_id": attempt_id})
    cursor.execute(f"EXECUTE TASK {namespace}.RESERVING_JOB USING CONFIG = '{config}'")
    return {
        "attempt_id": attempt_id, "import_id": import_id, "method": method,
        "submission_query_id": cursor.sfqid, "submission": cursor.fetchone()[0],
    }


def deploy_viewer(cursor, namespace, warehouse):
    source = (HERE / "streamlit_app.py").read_text(encoding="utf-8").replace("__DEMO_SCHEMA__", namespace)
    stage = f"@{namespace}.RESERVING_FILES/viewer/{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
    with TemporaryDirectory(prefix="ipc-snowflake-viewer-") as folder:
        path = Path(folder) / "streamlit_app.py"
        path.write_text(source, encoding="utf-8")
        upload(cursor, path, stage)
    cursor.execute(f"""
        CREATE OR REPLACE STREAMLIT {namespace}.RESERVING_REVIEW
        FROM '{stage}' MAIN_FILE = 'streamlit_app.py' QUERY_WAREHOUSE = {warehouse}
        RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
    """)
    return {"streamlit": f"{namespace}.RESERVING_REVIEW"}


def inspect_attempt(cursor, namespace, attempt_id):
    result = rows(cursor, f"SELECT * FROM {namespace}.RESERVING_RUNS WHERE ATTEMPT_ID = ?", (attempt_id,))
    if not result:
        raise ValueError(f"Attempt {attempt_id} is not saved. For a queued task, check Task History and retry.")
    warnings = rows(cursor, f"""
        SELECT CHECK_STAGE, CHECK_ID, VERDICT, DETAILS FROM {namespace}.RESERVING_WARNINGS
        WHERE ATTEMPT_ID = ? ORDER BY CHECK_STAGE, CHECK_ID
    """, (attempt_id,))
    for warning in warnings:
        if isinstance(warning["details"], str):
            warning["details"] = json.loads(warning["details"])
    return {**result[0], "warnings": warnings}


def save_report(cursor, namespace, attempt_id, output):
    result = rows(cursor, f"SELECT REPORT_HTML FROM {namespace}.RESERVING_REPORTS WHERE ATTEMPT_ID = ?", (attempt_id,))
    if not result:
        raise ValueError(f"Attempt {attempt_id} has no saved draft report.")
    with output.open("x", encoding="utf-8") as handle:
        handle.write(result[0]["report_html"])
    return {"attempt_id": attempt_id, "report": str(output.resolve())}


def add_connection_options(parser):
    parser.add_argument("--connection", default="ipc_demo", help="Named Python Connector connection.")
    parser.add_argument("--database", default="IPC_RESERVING_DEMO")
    parser.add_argument("--schema", default="DEMO")
    parser.add_argument("--warehouse", default="COMPUTE_WH")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_options(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Verify sign-in, role and warehouse before deploying.")
    deploy = commands.add_parser("setup", help="Create the demo schema and deploy the Python procedure.")
    deploy.add_argument("--wheel", type=Path, default=Path("dist") / WHEEL_NAME)
    upload_csv = commands.add_parser("import", help="Load an immutable input snapshot from the internal stage.")
    upload_csv.add_argument("--dataset", choices=SAMPLES, default="raa")
    upload_csv.add_argument("--file", type=Path, help="CSV override. The default is the named demo fixture.")
    for name in ("run", "run-task"):
        run = commands.add_parser(name, help="Run Mack or Basic Chain Ladder on a saved import.")
        run.add_argument("import_id", type=demo_id)
        run.add_argument("--method", choices=METHODS, default="mack")
    commands.add_parser("setup-task", help="Create an on-demand Snowflake Task.")
    commands.add_parser("setup-viewer", help="Deploy the warehouse-runtime Streamlit report viewer.")
    commands.add_parser("setup-qa", help="Deploy the optional native Cortex Q&A assistant.")
    commands.add_parser("inspect", help="Read a saved attempt and its warnings.").add_argument("attempt_id", type=demo_id)
    report = commands.add_parser("report", help="Save the original draft HTML for a completed attempt.")
    report.add_argument("attempt_id", type=demo_id)
    report.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    database, schema, warehouse = map(identifier, (options.database, options.schema, options.warehouse))
    namespace = f"{database}.{schema}"

    with connect(options) as connection, connection.cursor() as cursor:
        match options.command:
            case "check":
                result = check_connection(cursor)
            case "setup":
                result = setup(cursor, database, schema, options.wheel)
            case "import":
                source = options.file or HERE.parent / "examples" / SAMPLES[options.dataset]
                result = import_triangle(cursor, namespace, options.dataset, source)
            case "run":
                result = run_reserving(cursor, namespace, options.import_id, options.method)
            case "setup-task":
                result = deploy_task(cursor, namespace, warehouse)
            case "run-task":
                result = start_task(cursor, namespace, options.import_id, options.method)
            case "setup-viewer":
                result = deploy_viewer(cursor, namespace, warehouse)
            case "setup-qa":
                from snowflake_demo.cortex import deploy_qa

                result = deploy_qa(cursor, namespace, warehouse)
            case "inspect":
                result = inspect_attempt(cursor, namespace, options.attempt_id)
            case "report":
                result = save_report(cursor, namespace, options.attempt_id, options.output)
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    return int(result.get("status") == "execution_failed")


if __name__ == "__main__":
    raise SystemExit(main())
