from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from snowflake_demo import demo, procedure
from snowflake_demo.runtime_probe import ARCHIVE_NAME, RAA_HASH


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
IMPORT_ID = "a" * 32
ATTEMPT_ID = "b" * 32


def test_import_pins_matching_uploaded_observations(monkeypatch):
    cursor = Mock(sfqid="copy-query-id")
    source = EXAMPLES / "raa.csv"
    expected = demo.parse_triangle(source.read_bytes())
    cursor.fetchall.return_value = expected
    monkeypatch.setattr(demo, "uuid4", lambda: SimpleNamespace(hex=IMPORT_ID))
    uploads = []
    monkeypatch.setattr(demo, "upload", lambda _, path, stage: uploads.append((path.read_bytes(), stage)))

    result = demo.import_triangle(cursor, "IPC.DEMO", "raa", source)
    statements = cursor.execute.call_args_list
    assert uploads == [(source.read_bytes(), f"@IPC.DEMO.RESERVING_FILES/inputs/{IMPORT_ID}")]
    assert "COPY INTO IPC.DEMO.TRIANGLE_LOAD_" in statements[1].args[0]
    assert "METADATA$FILE_ROW_NUMBER" in statements[1].args[0]
    assert "INSERT INTO IPC.DEMO.RESERVING_IMPORTS" in statements[3].args[0]
    parameters = statements[3].args[1]
    assert result["rows"] == 55
    assert result["input_sha256"] == parameters[4] == RAA_HASH
    assert parameters[5] == source.read_text(encoding="utf-8")
    assert json.loads(parameters[6]) == [list(row) for row in expected]

    cursor.reset_mock()
    cursor.fetchall.return_value = expected[:-1]
    with pytest.raises(ValueError, match="different observations"):
        demo.import_triangle(cursor, "IPC.DEMO", "raa", source)
    assert not any("INSERT INTO" in statement.args[0] for statement in cursor.execute.call_args_list)


@pytest.fixture(scope="module")
def mounted_bundle(tmp_path_factory):
    folder = tmp_path_factory.mktemp("snowflake_imports")
    with ZipFile(folder / ARCHIVE_NAME, "w") as archive:
        for package in ("harness", "engine", "databricks_demo"):
            for file in (ROOT / package).rglob("*"):
                if file.is_file() and file.suffix != ".pyc":
                    archive.write(file, file.relative_to(ROOT))
    return folder


class StoredProcedureSession:
    def __init__(self, source):
        self.source = source
        self.saved = None

    def sql(self, query, params):
        if query.startswith("SELECT"):
            assert params == [IMPORT_ID]
            return SimpleNamespace(collect=lambda: [self.source])
        assert query.startswith("INSERT INTO RESERVING_ATTEMPTS")
        assert self.saved is None
        self.saved = params
        return SimpleNamespace(collect=lambda: [])


@pytest.mark.parametrize(
    "dataset,method,status,report,expected_se",
    [
        ("raa", "mack", "review_required", True, 26909.01115564366),
        ("raa", "chain_ladder", "review_required", True, None),
        ("gapped", "mack", "blocked_by_validation", False, None),
    ],
)
def test_procedure_persists_harness_evidence(mounted_bundle, monkeypatch, dataset, method, status, report, expected_se):
    csv_text = (EXAMPLES / demo.SAMPLES[dataset]).read_bytes().decode("utf-8")
    input_hash = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    session = StoredProcedureSession({"DATASET": dataset, "INPUT_CSV": csv_text, "INPUT_SHA256": input_hash})
    monkeypatch.setitem(sys._xoptions, "snowflake_import_directory", str(mounted_bundle))

    output = procedure.run_attempt(session, IMPORT_ID, method, ATTEMPT_ID, "task-run-group")
    assert session.saved[:3] == [ATTEMPT_ID, IMPORT_ID, "task-run-group"]
    payload, validation, diagnostics, artifacts = map(json.loads, session.saved[3:])
    assert output["status"] == payload["status"] == status
    assert payload["input_sha256"] == input_hash
    assert payload["bundle_sha256"] == hashlib.sha256((mounted_bundle / ARCHIVE_NAME).read_bytes()).hexdigest()
    assert output["report_available"] is report
    if expected_se is None:
        assert output["mack_se"] is None
    else:
        assert output["mack_se"] == pytest.approx(expected_se, abs=0.001)
    if report:
        assert output["ibnr"] == pytest.approx(52135.228261210155, abs=0.001)
        check = next(check for check in validation["checks"] if check["check_id"] == "nonneg_incrementals")
        assert check["details"] == {"origin": "1982", "dev": 7, "incremental": -103.0}
        assert diagnostics["overall"] == "warn"
        assert "draft/incomplete" in artifacts["model/report.html"]
    else:
        assert payload["model_run_id"] is output["ibnr"] is None
        assert payload["stage_exit_codes"] == {"validate": 2}
        assert any(check["check_id"] == "no_gaps" and check["verdict"] == "fail" for check in validation["checks"])
        assert "model/report.html" not in artifacts


def test_procedure_rejects_changed_snapshot_before_running():
    session = StoredProcedureSession({"DATASET": "raa", "INPUT_CSV": "changed", "INPUT_SHA256": RAA_HASH})
    with pytest.raises(ValueError, match="saved import hash"):
        procedure.run_attempt(session, IMPORT_ID, "mack", ATTEMPT_ID, None)
    assert session.saved is None


def test_interactive_run_records_the_call_query_id(monkeypatch):
    cursor = Mock(sfqid="call-query-id")
    cursor.fetchone.return_value = (json.dumps({"attempt_id": ATTEMPT_ID, "status": "review_required"}),)
    monkeypatch.setattr(demo, "uuid4", lambda: SimpleNamespace(hex=ATTEMPT_ID))
    result = demo.run_reserving(cursor, "IPC.DEMO", IMPORT_ID, "mack")
    tag, call, save = cursor.execute.call_args_list
    assert ATTEMPT_ID in tag.args[0]
    assert call.args == ("CALL IPC.DEMO.RUN_RESERVING(?, ?, ?, ?)", (IMPORT_ID, "mack", ATTEMPT_ID, None))
    assert save.args[1] == ("call-query-id", ATTEMPT_ID)
    assert result["platform_query_id"] == "call-query-id"
