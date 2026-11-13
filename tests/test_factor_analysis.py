from __future__ import annotations

import hashlib
import html as html_module
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from harness import selection_sets
from harness.render import report_html
from harness.workbench import io
from harness.workbench.api import create_app


REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bcl_run(tmp_path: Path) -> tuple[str, Path]:
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "chain_ladder",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    return run_id, tmp_path / run_id


def test_factor_analysis_is_deterministic_ranked_and_exposed_by_api(tmp_path):
    run_id, run_dir = _bcl_run(tmp_path)
    command = (
        "factor-analysis",
        run_id,
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    first = _run_cli(*command)
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    analysis = payload["analysis"]
    assert analysis["analysis_type"] == "bcl_link_ratio_leave_one_out"
    assert len(analysis["development_periods"]) == 9
    assert len(analysis["influence_ranking"]) == 45
    assert [row["rank"] for row in analysis["influence_ranking"]] == list(range(1, 46))
    assert analysis["influence_ranking"][0]["high_influence"] is True
    assert analysis["influence_ranking"][0]["delta_ibnr"] is not None
    assert payload["review_suggestions"]["generator"]["final_selection_authority"] is False

    hashes = (_sha(run_dir / "factor_analysis.json"), _sha(run_dir / "factor_review_suggestions.json"))
    second = _run_cli(*command)
    assert second.returncode == 0, second.stderr
    assert hashes == (_sha(run_dir / "factor_analysis.json"), _sha(run_dir / "factor_review_suggestions.json"))

    client = TestClient(create_app(tmp_path))
    assert client.get(f"/api/runs/{run_id}/factor-analysis").json()["analysis_id"] == analysis["analysis_id"]
    suggestions = client.get(f"/api/runs/{run_id}/factor-review-suggestions").json()
    assert len(suggestions["suggestions"]) >= 5
    assert client.get(f"/api/runs/{run_id}/artifacts/factor_analysis.json").status_code == 200


def test_governed_preview_binds_review_dispositions_and_report_exhibits(tmp_path):
    run_id, run_dir = _bcl_run(tmp_path)
    result = _run_cli("factor-analysis", run_id, "--format", "json", "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    generated = json.loads(result.stdout)
    suggestion = generated["review_suggestions"]["suggestions"][0]
    target = suggestion["target"]
    request = {
        "factor_selections": [
            {
                "development_age": "1 -> 2",
                "selected_basis": "last_3",
                "rationale": "Recent observations were inspected and selected for the governed demo.",
            }
        ],
        "exclusions": [
            {
                "type": "factor_point",
                "value": f"{target['origin']}:{target['point_id'].partition('from_dev:')[2]}",
                "origin": target["origin"],
                "from_dev": int(target["point_id"].partition("from_dev:")[2]),
                "development_age": target["development_age"],
                "rationale": "Influence evidence was inspected and the point was excluded for preview.",
            }
        ],
        "global_rationale": "Senior actuarial review of deterministic link-ratio evidence.",
        "created_by": {"id": "senior-actuary", "display_name": "Senior Actuary"},
        "factor_analysis_id": generated["analysis"]["analysis_id"],
        "reviewed_suggestion_ids": [suggestion["suggestion_id"]],
        "suggestion_dispositions": [
            {
                "suggestion_id": suggestion["suggestion_id"],
                "status": "reviewed",
                "rationale": "Reviewed against link-ratio and leave-one-out evidence.",
            }
        ],
    }
    preview = selection_sets.build_selection_set_preview(run_id, run_dir, request)
    assert preview["factor_analysis_id"] == generated["analysis"]["analysis_id"]
    assert preview["suggestion_dispositions"][0]["status"] == "reviewed"
    assert "factor_analysis.json" in preview["input_hashes"]
    assert "factor_review_suggestions.json" in preview["input_hashes"]
    assert preview["factor_overlay"]

    committed = selection_sets.commit_selection_set(
        run_id,
        run_dir,
        preview["selection_set_id"],
        {"global_rationale": request["global_rationale"], "created_by": request["created_by"]},
    )
    io.write_json(
        run_dir / "decisions" / "selection_set_approval_factor_analysis.json",
        {
            "decision_id": "selection_set_approval_factor_analysis",
            "decision_type": "selection_set_approval",
            "status": "accepted",
            "selection_set_id": committed["selection_set_id"],
            "resulting_scenario_id": committed["preview_scenario_id"],
            "rationale": request["global_rationale"],
        },
    )
    html = report_html.render(run_id, run_dir)
    assert "Base and governed selected development factor curve" in html
    assert "Link-ratio review exhibits" in html
    assert "AI review evidence disposition" in html
    assert html_module.escape(suggestion["title"], quote=False) in html
    assert "Reviewed against link-ratio and leave-one-out evidence." in html


def test_frontend_uses_artifact_backed_factor_analysis_without_raw_json():
    app_js = (REPO_ROOT / "harness" / "workbench" / "static_v2" / "app.js").read_text()
    assert "/factor-analysis" in app_js
    assert "factor-analysis-chart" in app_js
    assert "Exclusion delta IBNR" in app_js
    assert "Deterministic screening only" in app_js
    assert "JSON.stringify(state.factorAnalysis" not in app_js
    assert "JSON.stringify(state.factorSuggestions" not in app_js
