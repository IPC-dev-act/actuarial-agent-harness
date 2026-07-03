import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"
GENINS_CSV = REPO_ROOT / "examples" / "genins.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_runs_list_empty_root(tmp_path):
    result = _run_cli("runs", "list", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"runs": []}


def test_runs_list_custom_out_root(tmp_path):
    _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    _run_cli("fit", str(GENINS_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path))

    result = _run_cli("runs", "list", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload["runs"]) == 2
    # sorted by run_id (timestamp-prefixed) — validate ran first
    assert payload["runs"][0]["command"].startswith("reserve validate")
    assert payload["runs"][1]["command"].startswith("reserve fit")


def test_runs_show_unknown_run_id_exit_4(tmp_path):
    result = _run_cli("runs", "show", "does-not-exist", "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 4


def test_runs_show_returns_manifest_verbatim(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]

    result = _run_cli("runs", "show", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0
    shown = json.loads(result.stdout)
    on_disk = json.loads((tmp_path / run_id / "manifest.json").read_text())
    assert shown == on_disk


def test_runs_list_text_format_renders(tmp_path):
    _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    result = _run_cli("runs", "list", "--format", "text", "--out", str(tmp_path))
    assert "reserve validate" in result.stdout
