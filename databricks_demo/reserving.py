"""Run the existing reserving CLI and persist the evidence to Delta."""

from __future__ import annotations

import csv
import json
import re
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from harness import __version__, manifest
from harness.cli import EXIT_MODEL_WARNING, EXIT_SUCCESS, EXIT_VALIDATION_FAILURE, main as reserve


SAMPLES = {"raa": "raa.csv", "gapped": "triangle_gapped.csv"}
METHODS = {"mack", "chain_ladder"}
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
RUN_COLUMNS = """
    attempt_id STRING, started_at TIMESTAMP, job_run_id STRING,
    dataset STRING, method STRING, status STRING,
    source_table STRING, source_version BIGINT, input_sha256 STRING, input_csv STRING,
    harness_version STRING, model_run_id STRING,
    validation_verdict STRING, diagnostics_verdict STRING,
    latest DOUBLE, ultimate DOUBLE, ibnr DOUBLE, mack_se DOUBLE,
    stage_exit_codes MAP<STRING, INT>, artifacts MAP<STRING, STRING>
"""


def _run_command(args, output_root, stage, record):
    stdout, stderr = StringIO(), StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = reserve([*args, "--out", str(output_root)])
        except SystemExit as error:
            code = int(error.code)
    record["stage_exit_codes"][stage] = code
    if code not in {EXIT_SUCCESS, EXIT_VALIDATION_FAILURE, EXIT_MODEL_WARNING}:
        record["artifacts"][f"errors/{stage}.txt"] = stderr.getvalue() or stdout.getvalue()
    return code


def _run_directory(root):
    manifests = list(root.glob("*/manifest.json"))
    return manifests[0].parent if manifests else None


def _collect_artifacts(run_dir, label, record):
    if run_dir is not None:
        for path in run_dir.iterdir():
            if path.suffix in {".json", ".html"}:
                record["artifacts"][f"{label}/{path.name}"] = path.read_text(encoding="utf-8")


def run_reserving(input_csv, dataset, method, source_table, source_version, job_run_id=""):
    if dataset not in SAMPLES or method not in METHODS:
        raise ValueError("Choose a demo dataset and either Mack or basic chain ladder.")

    record = {
        "attempt_id": uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "job_run_id": job_run_id or None,
        "dataset": dataset,
        "method": method,
        "status": "execution_failed",
        "source_table": source_table,
        "source_version": source_version,
        "input_sha256": manifest.sha256_text(input_csv),
        "input_csv": input_csv,
        "harness_version": __version__,
        "model_run_id": None,
        "validation_verdict": None,
        "diagnostics_verdict": None,
        "latest": None,
        "ultimate": None,
        "ibnr": None,
        "mack_se": None,
        "stage_exit_codes": {},
        "artifacts": {},
    }
    with TemporaryDirectory(prefix="reserving-demo-") as folder:
        scratch = Path(folder)
        triangle = scratch / SAMPLES[dataset]
        triangle.write_bytes(input_csv.encode("utf-8"))
        validation_root, model_root = scratch / "validation", scratch / "model"

        validation_code = _run_command(["validate", str(triangle)], validation_root, "validate", record)
        _collect_artifacts(_run_directory(validation_root), "validation", record)
        validation = json.loads(record["artifacts"].get("validation/validation.json", "{}"))
        record["validation_verdict"] = validation.get("verdict")
        if validation_code == EXIT_VALIDATION_FAILURE and record["validation_verdict"] == "fail":
            record["status"] = "blocked_by_validation"
            return record
        if validation_code != EXIT_SUCCESS or not validation:
            return record

        fit_code = _run_command(["fit", str(triangle), "--method", method], model_root, "fit", record)
        model_dir = _run_directory(model_root)
        _collect_artifacts(model_dir, "model", record)
        fit = json.loads(record["artifacts"].get("model/fit.json", "{}"))
        if fit_code not in {EXIT_SUCCESS, EXIT_MODEL_WARNING} or not fit:
            return record
        run_id = model_dir.name
        record["model_run_id"] = run_id
        record.update({key: fit["totals"].get(key) for key in ("latest", "ultimate", "ibnr", "mack_se")})

        diagnostics_code = _run_command(["diagnostics", run_id], model_root, "diagnostics", record)
        _collect_artifacts(model_dir, "model", record)
        diagnostics = json.loads(record["artifacts"].get("model/diagnostics.json", "{}"))
        record["diagnostics_verdict"] = diagnostics.get("overall")
        if diagnostics_code not in {EXIT_SUCCESS, EXIT_MODEL_WARNING} or not diagnostics:
            return record

        model_warned = EXIT_MODEL_WARNING in {fit_code, diagnostics_code}
        if model_warned:
            sensitivity_code = _run_command(
                ["sensitivity", run_id, "--grid", "default"], model_root, "sensitivity", record
            )
            _collect_artifacts(model_dir, "model", record)
            if sensitivity_code != EXIT_SUCCESS or "model/sensitivity.json" not in record["artifacts"]:
                return record

        report_code = _run_command(["report", run_id, "--format-out", "html"], model_root, "report", record)
        _collect_artifacts(model_dir, "model", record)
        if report_code == EXIT_SUCCESS and "model/report.html" in record["artifacts"]:
            record["status"] = (
                "review_required" if model_warned or record["validation_verdict"] == "warn" else "draft_ready"
            )
    return record


def table_names(spark, catalog, schema):
    catalog = catalog or spark.sql("SELECT current_catalog() AS catalog").first()["catalog"]
    if catalog.lower() in {"hive_metastore", "samples", "system", "spark_catalog"}:
        raise ValueError("Choose a writable Unity Catalog catalog in the catalog widget.")
    if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", item) for item in (catalog, schema)):
        raise ValueError("Use a catalog and schema name containing letters, digits, underscores, or hyphens.")
    prefix = f"`{catalog}`.`{schema}`"
    return f"{prefix}.`ipc_reserving_demo_triangles`", f"{prefix}.`ipc_reserving_demo_run_history`"


def seed_triangles(spark, table):
    rows = []
    for dataset, filename in SAMPLES.items():
        with (EXAMPLES / filename).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append({
                    "dataset": dataset, "origin": int(row["origin"]),
                    "development": int(row["development"]), "value": float(row["value"]),
                })
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {table}
        (dataset STRING, origin INT, development INT, value DOUBLE) USING DELTA
    """).collect()
    spark.sql(f"""
        MERGE INTO {table} AS target
        USING (
            SELECT observation.* FROM (
                SELECT explode(from_json(
                    :rows, 'ARRAY<STRUCT<dataset: STRING, origin: INT, development: INT, value: DOUBLE>>'
                )) AS observation
            )
        ) AS source
        ON target.dataset = source.dataset AND target.origin = source.origin
           AND target.development = source.development
        WHEN NOT MATCHED THEN INSERT (dataset, origin, development, value)
            VALUES (source.dataset, source.origin, source.development, source.value)
    """, args={"rows": json.dumps(rows, allow_nan=False)}).collect()


def read_triangle(spark, table, dataset, source_version=None):
    if source_version is None:
        source_version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"]
    version = int(source_version)
    if version < 0:
        raise ValueError("Use a non-negative Delta input version.")
    rows = spark.sql(f"""
        SELECT origin, development, value FROM {table} VERSION AS OF {version}
        WHERE dataset = :dataset ORDER BY origin, development
    """, args={"dataset": dataset}).collect()
    if not rows:
        raise ValueError(f"No rows for the {dataset!r} triangle in {table} at version {version}. Run Import_Triangle first.")
    handle = StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(("origin", "development", "value"))
    writer.writerows((row["origin"], row["development"], row["value"]) for row in rows)
    return version, handle.getvalue()


def save_run(spark, table, record):
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({RUN_COLUMNS}) USING DELTA").collect()
    values = {
        **record,
        "stage_exit_codes": json.dumps(record["stage_exit_codes"]),
        "artifacts": json.dumps(record["artifacts"]),
    }
    spark.sql(f"""
        INSERT INTO {table} (
            attempt_id, started_at, job_run_id, dataset, method, status,
            source_table, source_version, input_sha256, input_csv, harness_version, model_run_id,
            validation_verdict, diagnostics_verdict, latest, ultimate, ibnr, mack_se,
            stage_exit_codes, artifacts
        )
        SELECT :attempt_id, CAST(:started_at AS TIMESTAMP), :job_run_id, :dataset, :method, :status,
            :source_table, :source_version, :input_sha256, :input_csv, :harness_version, :model_run_id,
            :validation_verdict, :diagnostics_verdict, :latest, :ultimate, :ibnr, :mack_se,
            from_json(:stage_exit_codes, 'MAP<STRING, INT>'),
            from_json(:artifacts, 'MAP<STRING, STRING>')
    """, args=values).collect()
