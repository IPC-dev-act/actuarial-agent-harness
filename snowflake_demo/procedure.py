"""Snowpark handler for a pinned reserving import and its saved evidence."""

import hashlib
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile


@contextmanager
def unpack_harness(archive):
    # The report renderer opens its bundled template as a regular file.
    with TemporaryDirectory(prefix="ipc-harness-") as folder:
        with ZipFile(archive) as wheel:
            wheel.extractall(folder)
        sys.path.insert(0, folder)
        try:
            yield Path(folder)
        finally:
            sys.path.remove(folder)
            for name, module in list(sys.modules.items()):
                filename = getattr(module, "__file__", None)
                if isinstance(filename, str) and filename.startswith(folder + "/"):
                    del sys.modules[name]


def run_attempt(session, import_id, method, attempt_id, task_run_group_id):
    """Run the same stages as Databricks and save one immutable evidence record."""
    if not all(re.fullmatch(r"[0-9a-f]{32}", value or "") for value in (import_id, attempt_id)):
        raise ValueError("Use the 32-character import and attempt IDs.")
    if method not in {"mack", "chain_ladder"}:
        raise ValueError("Choose mack or chain_ladder.")
    rows = session.sql(
        "SELECT DATASET, INPUT_CSV, INPUT_SHA256 FROM RESERVING_IMPORTS WHERE IMPORT_ID = ?",
        params=[import_id],
    ).collect()
    if len(rows) != 1:
        raise ValueError(f"No unique reserving import found for {import_id}.")
    source = rows[0]
    csv_text = source["INPUT_CSV"]
    if hashlib.sha256(csv_text.encode("utf-8")).hexdigest() != source["INPUT_SHA256"]:
        raise ValueError("The saved import hash does not match the input CSV.")

    archive = Path(sys._xoptions["snowflake_import_directory"]) / "ipc_reserving_harness.zip"
    with unpack_harness(archive):
        from databricks_demo.reserving import run_reserving

        result = run_reserving(csv_text, source["DATASET"], method, "RESERVING_IMPORTS", None)
    result.pop("input_csv")  # The canonical bytes are preserved on the import record.
    result["import_id"] = import_id
    result["attempt_id"] = attempt_id
    result["bundle_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    artifacts = result.pop("artifacts")
    validation = json.loads(artifacts.get("validation/validation.json", "{}"))
    diagnostics = json.loads(artifacts.get("model/diagnostics.json", "{}"))
    session.sql(
        """INSERT INTO RESERVING_ATTEMPTS
           (ATTEMPT_ID, IMPORT_ID, TASK_RUN_GROUP_ID, PAYLOAD, VALIDATION, DIAGNOSTICS, ARTIFACTS)
           SELECT ?, ?, ?, PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?), PARSE_JSON(?)""",
        params=[
            attempt_id, import_id, task_run_group_id,
            json.dumps(result, allow_nan=False), json.dumps(validation, allow_nan=False),
            json.dumps(diagnostics, allow_nan=False), json.dumps(artifacts, allow_nan=False),
        ],
    ).collect()
    return {
        "attempt_id": attempt_id,
        "import_id": import_id,
        "status": result["status"],
        "method": method,
        "ibnr": result["ibnr"],
        "mack_se": result["mack_se"],
        "report_available": "model/report.html" in artifacts,
    }
