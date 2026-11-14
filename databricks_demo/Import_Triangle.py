# Databricks notebook source
# MAGIC %md
# MAGIC # Import the RAA claims triangle
# MAGIC Upload the supplied `raa.csv` to a Unity Catalog volume and enter its catalog, schema and volume below.
# MAGIC This notebook writes only the input table. Open it in Catalog Explorer before running **Reserving_Demo**.

# COMMAND ----------

import csv
import json
import math
import re
from pathlib import Path

dbutils.widgets.text("catalog", "", "Unity Catalog catalog")
dbutils.widgets.text("schema", "default", "Unity Catalog schema")
dbutils.widgets.text("volume", "reserving_demo_files", "Unity Catalog volume")
dbutils.widgets.text("file_name", "raa.csv", "Uploaded CSV filename")
dbutils.widgets.text("job_run_id", "", "Lakeflow job run ID")

# COMMAND ----------

catalog = dbutils.widgets.get("catalog").strip() or spark.sql("SELECT current_catalog()").first()[0]
schema = dbutils.widgets.get("schema").strip()
volume = dbutils.widgets.get("volume").strip()
file_name = dbutils.widgets.get("file_name").strip()
if not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", name) for name in (catalog, schema, volume)):
    raise ValueError("Use catalog, schema and volume names with letters, digits, underscores or hyphens.")
if not re.fullmatch(r"raa(?:-[a-f0-9]{32})?\.csv", file_name):
    raise ValueError("Choose the uploaded RAA demo CSV.")

path = Path("/Volumes") / catalog / schema / volume / file_name
rows = []
with path.open(encoding="utf-8-sig", newline="") as source:
    reader = csv.DictReader(source)
    if reader.fieldnames != ["origin", "development", "value"]:
        raise ValueError("The CSV needs origin, development and value columns in that order.")
    for record in reader:
        if None in record:
            raise ValueError("Each observation must contain exactly three values.")
        rows.append({"origin": int(record["origin"]), "development": int(record["development"]),
                     "value": float(record["value"])})
if not rows or not all(math.isfinite(row["value"]) for row in rows):
    raise ValueError("The CSV must contain finite triangle observations.")
if len({(row["origin"], row["development"]) for row in rows}) != len(rows):
    raise ValueError("Each origin and development pair must be unique.")

# COMMAND ----------

table = f"`{catalog}`.`{schema}`.`ipc_reserving_demo_triangles`"
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {table}
    (dataset STRING, origin INT, development INT, value DOUBLE) USING DELTA
""").collect()

# The dedicated demo table retains other datasets, such as the earlier gapped fixture.
# Delta records the replacement as one transaction.
spark.sql(f"""
    INSERT INTO {table} REPLACE WHERE dataset = 'raa'
    SELECT 'raa', observation.origin, observation.development, observation.value
    FROM (SELECT explode(from_json(
        :rows, 'ARRAY<STRUCT<origin: INT, development: INT, value: DOUBLE>>'
    )) AS observation)
""", args={"rows": json.dumps(rows, allow_nan=False)}).collect()
version = int(spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").first()["version"])
preview = spark.sql(f"""
    SELECT origin, development, value FROM {table} VERSION AS OF {version}
    WHERE dataset = 'raa' ORDER BY origin, development
""")
expected = sorted((row["origin"], row["development"], row["value"]) for row in rows)
if [tuple(row) for row in preview.collect()] != expected:
    raise RuntimeError("Another import changed the triangle. Retry before running reserving.")
print(f"Imported {len(rows)} observations into {table}. Delta version: {version}")
display(preview)
if dbutils.widgets.get("job_run_id"):
    dbutils.notebook.exit(json.dumps({"table": table, "source_version": version, "observations": len(rows)}))
