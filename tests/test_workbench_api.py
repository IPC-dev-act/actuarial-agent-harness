import json
from pathlib import Path

from fastapi.testclient import TestClient

from engine.chainladder_adapter import ChainladderAdapter
from harness import factor_analysis, manifest, triangle_io, triangle_projection
from harness.render import report_html
from harness.workbench.api import create_app

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "dashboard" / "static"
V2_STATIC_DIR = REPO_ROOT / "dashboard-v2" / "static"
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _make_run(tmp_path: Path, method: str = "mack") -> tuple[str, Path, TestClient]:
    method_slug = method.replace("_", "-")
    run_id = f"2026-07-06T12-00-00_api_{method_slug}_abc123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    mack_se = 42.0 if method == "mack" else None
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_utc": "2026-07-06T12:00:00Z",
            "command": f"reserve fit examples/raa.csv --method {method}",
            "inputs": [{"path": "examples/raa.csv", "sha256": "input-hash"}],
            "engine": {"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
            "environment": {"python": "3.12.0", "harness_version": "0.1.0"},
            "parameters": {"method": method},
            "outputs": [
                "validation.json",
                "fit.json",
                "triangle.json",
                "diagnostics.json",
                "sensitivity.json",
            ],
            "exit_code": 3,
        },
    )
    _write_json(
        run_dir / "validation.json",
        {
            "checks": [
                {
                    "check_id": "monotone_cumulative",
                    "verdict": "warn",
                    "details": {"origin": "1984", "dev": 4},
                }
            ],
            "verdict": "warn",
        },
    )
    _write_json(
        run_dir / "diagnostics.json",
        {
            "tests": [
                {
                    "test_id": "calendar_year_effect",
                    "verdict": "warn",
                    "statistic": 1.4,
                    "threshold": 1.0,
                    "narrative_key": "calendar_year_effect",
                    "prescribed_actions": ["review calendar pattern"],
                }
            ],
            "overall": "warn",
        },
    )
    _write_json(
        run_dir / "fit.json",
        {
            "run_id": run_id,
            "method": method,
            "parameters": {
                "averaging": "volume",
                "tail": "none",
                "n_periods": None,
                "excluded_origins": [],
                "excluded_valuations": [],
                "sigma_interpolation": "mack",
            },
            "totals": {"latest": 1000.0, "ultimate": 1300.0, "ibnr": 300.0, "mack_se": mack_se},
            "development_factors": [
                {
                    "from_dev": 1,
                    "to_dev": 2,
                    "ldf": 1.5,
                    "sigma": None if method != "mack" else 0.2,
                    "cumulative_development_factor": 1.5,
                    "candidate_averages": {"volume_weighted": 1.5, "simple_average": 1.4},
                    "link_ratios": [
                        {
                            "origin": "1981",
                            "from_dev": 1,
                            "to_dev": 2,
                            "current_value": 400.0,
                            "next_value": 600.0,
                            "link_ratio": 1.5,
                        }
                    ],
                },
                {"from_dev": 2, "to_dev": "ult", "ldf": 1.1, "sigma": None},
            ],
            "by_origin": [
                {"origin": "1981", "latest": 600.0, "ultimate": 750.0, "ibnr": 150.0, "mack_se": mack_se},
                {"origin": "1982", "latest": 400.0, "ultimate": 550.0, "ibnr": 150.0, "mack_se": mack_se},
            ],
        },
    )
    _write_json(
        run_dir / "triangle.json",
        {
            "run_id": run_id,
            "cells": [
                {"origin": "1981", "dev": 1, "value": 400.0},
                {"origin": "1981", "dev": 2, "value": 600.0},
                {"origin": "1982", "dev": 1, "value": 400.0},
            ],
        },
    )
    _write_json(
        run_dir / "sensitivity.json",
        {
            "run_id": run_id,
            "base_parameters": {
                "averaging": "volume",
                "tail": "none",
                "n_periods": None,
                "excluded_origins": [],
                "excluded_valuations": [],
                "sigma_interpolation": "mack",
            },
            "scenarios": [
                {
                    "scenario_id": "drop_oldest_origin",
                    "delta_from_base": {"parameter": "excluded_origins", "value": "1981"},
                    "totals": {"ultimate": 1250.0, "ibnr": 250.0, "mack_se": None},
                }
            ],
            "range": {"ibnr_min": 250.0, "ibnr_max": 300.0, "base_ibnr": 300.0},
        },
    )
    return run_id, run_dir, TestClient(create_app(tmp_path))


def _make_real_bcl_run(tmp_path: Path) -> tuple[str, Path, TestClient]:
    run_id = "2026-07-06T12-30-00_api_real_bcl_abc123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    adapter = ChainladderAdapter()
    tri_handle = adapter.load_triangle(RAA_CSV)
    fit_result = adapter.fit(tri_handle, "chain_ladder", {"averaging": "volume"})
    actual_cells, _triangle_error = triangle_io.load_and_normalize(RAA_CSV)
    input_sha = manifest.sha256_file(RAA_CSV)
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "created_utc": "2026-07-06T12:30:00Z",
            "command": "reserve fit examples/raa.csv --method chain_ladder",
            "inputs": [{"path": str(RAA_CSV), "sha256": input_sha}],
            "engine": {"adapter": "chainladder_adapter", "package": "chainladder", "version": "0.9.2"},
            "environment": {"python": "3.12.0", "harness_version": "0.1.0"},
            "parameters": {"method": "chain_ladder"},
            "outputs": ["validation.json", "fit.json", "triangle.json", "diagnostics.json"],
            "exit_code": 0,
        },
    )
    _write_json(run_dir / "validation.json", {"checks": [], "verdict": "pass"})
    _write_json(run_dir / "diagnostics.json", {"tests": [], "overall": "pass"})
    _write_json(run_dir / "fit.json", fit_result.to_fit_json(run_id))
    _write_json(
        run_dir / "triangle.json",
        {
            "run_id": run_id,
            "basis": tri_handle.basis,
            "cells": triangle_projection.build_cells(
                actual_cells.to_dict("records"), fit_result.development_factors
            ),
        },
    )
    return run_id, run_dir, TestClient(create_app(tmp_path))


def _warning_ack_payload(run_id: str, task_id: str, decision_id: str = "ack_warning_api") -> dict:
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": task_id,
        "decision_type": "warning_ack",
        "status": "accepted",
        "rationale": "Reviewed through the local workbench API.",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": ["validation.json", "fit.json", "diagnostics.json"],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": None,
        "supersedes_decision_id": None,
    }


def _method_review_payload(
    run_id: str,
    task_id: str,
    decision_id: str = "ack_bcl_review_api",
) -> dict:
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": task_id,
        "decision_type": "method_review_ack",
        "status": "accepted",
        "rationale": "Reviewed deterministic chain ladder output and approved continuing.",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": ["fit.json", "triangle.json"],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": None,
        "supersedes_decision_id": None,
    }


def _factor_selection_payload(
    run_id: str,
    preview: dict,
    decision_id: str = "select_factor_api",
    rationale: str = "Selected after reviewing backend preview.",
) -> dict:
    selection = preview["selection"]
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": None,
        "decision_type": "factor_selection",
        "status": "accepted",
        "development_age": selection["development_age"],
        "previous_factor": selection["previous_factor"],
        "selected_factor": selection["selected_factor"],
        "selected_basis": selection["selected_basis"],
        "rationale": rationale,
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": [*preview["source_artifacts"], preview["preview_artifact"]],
        "commands_or_parameters_affected": [],
        "resulting_scenario_id": preview["scenario_id"],
        "supersedes_decision_id": None,
    }


def _preview_request_from_first_factor(client: TestClient, run_id: str, basis: str = "last_3") -> dict:
    factors = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"]
    row = factors[0]
    return {
        "development_age": row["development_age"],
        "selected_basis": basis,
        "selected_factor_value": row["candidate_averages"][basis],
        "user_note": "Preview through API test.",
    }


def _selection_set_request(client: TestClient, run_id: str, *, include_exclusion: bool = True) -> dict:
    factors = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"]
    rows = factors[:2]
    request = {
        "factor_selections": [
            {
                "development_age": row["development_age"],
                "from_dev": row["from_dev"],
                "selected_basis": "last_3",
                "selected_factor": row["candidate_averages"]["last_3"],
                "rationale": f"Recent development selected for {row['development_age']}.",
            }
            for row in rows
        ],
        "exclusions": [],
        "global_rationale": "Combined selected factors reviewed for dashboard workflow test.",
        "created_by": {"id": "tester", "display_name": "Test User"},
    }
    if include_exclusion:
        request["exclusions"].append(
            {
                "type": "origin",
                "value": "1981",
                "rationale": "Oldest origin excluded for sensitivity review.",
            }
        )
    return request


def _selection_set_approval_payload(run_id: str, selection_set: dict, decision_id: str = "approve_selection_set_api") -> dict:
    return {
        "schema_version": "0.1",
        "decision_id": decision_id,
        "run_id": run_id,
        "task_id": None,
        "decision_type": "selection_set_approval",
        "status": "accepted",
        "selection_set_id": selection_set["selection_set_id"],
        "resulting_scenario_id": selection_set["preview_scenario_id"],
        "base_run_id": run_id,
        "rationale": "Approved committed selection set for report disclosure.",
        "user": {"id": "tester", "display_name": "Test User"},
        "source_artifacts_reviewed": [*selection_set["source_artifacts"], selection_set["selection_set_artifact"]],
        "commands_or_parameters_affected": [],
        "supersedes_decision_id": None,
    }


def _explore_request_from_first_factor(client: TestClient, run_id: str, *, name: str = "Explore last 3") -> dict:
    factors = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"]
    row = factors[0]
    return {
        "name": name,
        "notes": "",
        "factor_selections": [
            {
                "development_age": row["development_age"],
                "from_dev": row["from_dev"],
                "selected_basis": "last_3",
                "selected_factor": row["candidate_averages"]["last_3"],
            }
        ],
        "exclusions": [],
    }


def test_api_rejects_path_traversal(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)

    response = client.get(f"/api/runs/{run_id}/artifacts/comparisons/%2e%2e%2fmanifest.json")

    assert response.status_code == 400


def test_api_returns_status_for_valid_run(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)

    response = client.get(f"/api/runs/{run_id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_id
    assert payload["status"] == "needs_judgment"
    assert payload["artifacts"]["fit.json"] is True


def test_api_refreshes_tasks(tmp_path):
    run_id, run_dir, client = _make_run(tmp_path)

    response = client.post(f"/api/runs/{run_id}/tasks/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert any(task["task_type"] == "warning_review" for task in payload["tasks"])
    assert (run_dir / "validation_tasks.json").is_file()


def test_api_lists_decisions(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)
    task = next(
        task
        for task in client.post(f"/api/runs/{run_id}/tasks/refresh").json()["tasks"]
        if task["task_type"] == "warning_review"
    )
    response = client.post(f"/api/runs/{run_id}/decisions", json=_warning_ack_payload(run_id, task["task_id"]))
    assert response.status_code == 200, response.text

    listed = client.get(f"/api/runs/{run_id}/decisions")

    assert listed.status_code == 200
    payload = listed.json()
    assert payload["active_decision_count"] == 1
    assert payload["superseded_decision_count"] == 0
    assert payload["active_decisions"][0]["decision_id"] == "ack_warning_api"


def test_api_decision_journal_marks_active_and_superseded_decisions(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)
    task = next(
        task
        for task in client.post(f"/api/runs/{run_id}/tasks/refresh").json()["tasks"]
        if task["task_type"] == "warning_review"
    )
    first = _warning_ack_payload(run_id, task["task_id"], decision_id="ack_warning_first")
    second = _warning_ack_payload(run_id, task["task_id"], decision_id="ack_warning_second")
    second["supersedes_decision_id"] = "ack_warning_first"

    first_response = client.post(f"/api/runs/{run_id}/decisions", json=first)
    second_response = client.post(f"/api/runs/{run_id}/decisions", json=second)
    journal = client.get(f"/api/runs/{run_id}/decision-journal")

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert journal.status_code == 200, journal.text
    payload = journal.json()
    assert payload["active_decisions"][0]["decision_id"] == "ack_warning_second"
    assert payload["active_decisions"][0]["active"] is True
    assert payload["superseded_decisions"][0]["decision_id"] == "ack_warning_first"
    assert payload["superseded_decisions"][0]["superseded_by_decision_id"] == "ack_warning_second"


def test_api_lists_scenarios(tmp_path):
    run_id, run_dir, client = _make_run(tmp_path)

    response = client.get(f"/api/runs/{run_id}/scenarios")

    assert response.status_code == 200
    payload = response.json()
    scenario_ids = {scenario["scenario_id"] for scenario in payload["scenarios"]}
    assert {"base", "drop_oldest_origin"}.issubset(scenario_ids)
    assert (run_dir / "scenario_index.json").is_file()


def test_api_comparison_endpoint_returns_deterministic_comparison(tmp_path):
    run_id, run_dir, client = _make_run(tmp_path)

    first = client.get(f"/api/runs/{run_id}/compare", params={"scenario_id": "drop_oldest_origin"})
    second = client.get(f"/api/runs/{run_id}/compare", params={"scenario_id": "drop_oldest_origin"})

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    payload = first.json()
    assert payload["deltas"]["ibnr"] == -50.0
    assert (run_dir / "comparisons" / f"{payload['comparison_id']}.json").is_file()


def test_api_detects_bcl_method_aliases(tmp_path):
    for method in ("chain_ladder", "chainladder", "bcl"):
        run_id, _run_dir, client = _make_run(tmp_path / method, method=method)

        response = client.get(f"/api/runs/{run_id}/chain-ladder/summary")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["is_chain_ladder"] is True
        assert payload["display_method"] == "Deterministic Chain Ladder"


def test_api_keeps_mack_dashboard_method_separate(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="mack")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["is_chain_ladder"] is False
    assert payload["display_method"] == "Mack Chain Ladder"


def test_chain_ladder_summary_returns_values_from_fit_json(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["method"] == "chain_ladder"
    assert payload["input_file"] == "examples/raa.csv"
    assert payload["totals"] == {"latest": 1000.0, "ultimate": 1300.0, "ibnr": 300.0, "mack_se": None}
    assert payload["origin_period_count"] == 2
    assert payload["development_period_count"] == 2
    assert payload["selected_scenario_id"] is None


def test_factors_endpoint_returns_development_factors_from_fit_json(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/factors")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["is_chain_ladder"] is True
    assert payload["factors"][0]["development_age"] == "1 -> 2"
    assert payload["factors"][0]["selected_factor"] == 1.5
    assert payload["factors"][0]["factor_basis"] == "volume"
    assert payload["factors"][0]["cumulative_development_factor"] == 1.5
    assert payload["factors"][0]["candidate_averages"]["volume_weighted"] == 1.5
    assert payload["factors"][1]["candidate_averages"]["last_3"] is None
    assert payload["factor_curve"][0]["base_factor"] == 1.5
    assert payload["factor_curve"][0]["selected_factor"] == 1.5
    assert payload["factors"][0]["candidate_cards"][0]["basis"] == "fitted"
    assert payload["factors"][0]["candidate_cards"][1]["basis"] == "volume_weighted"
    assert payload["factors"][0]["candidate_cards"][1]["available"] is True
    assert payload["factors"][0]["candidate_cards"][1]["chart_pct"] is not None
    assert any(card["basis"] == "manual_override" for card in payload["factors"][0]["candidate_cards"])


def test_selected_development_age_endpoint_returns_backend_factor_points(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/factors/1")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["development_age"] == "1 -> 2"
    assert payload["points"][0]["origin"] == "1981"
    assert payload["points"][0]["link_ratio"] == 1.5
    assert payload["points"][0]["x_pct"] is not None
    assert payload["points"][0]["y_pct"] is not None
    assert payload["points"][0]["actions"]["point_exclusion"]["type"] == "factor_point"
    assert any(line["basis"] == "volume_weighted" for line in payload["candidate_lines"])


def test_factor_point_exclusion_preview_creates_selection_set_artifact(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    detail = client.get(f"/api/runs/{run_id}/chain-ladder/factors/1").json()
    point = detail["points"][0]
    action = point["actions"]["point_exclusion"]
    request = {
        "factor_selections": [],
        "exclusions": [
            {
                "type": "factor_point",
                "value": action["value"],
                "origin": action["origin"],
                "from_dev": action["from_dev"],
                "to_dev": action["to_dev"],
                "development_age": action["development_age"],
                "rationale": "Point excluded after reviewing anomalous link ratio.",
            }
        ],
        "global_rationale": "Point exclusion preview for governed factor review.",
        "created_by": {"id": "tester", "display_name": "Test User"},
    }

    response = client.post(f"/api/runs/{run_id}/selection-sets/preview", json=request)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["factor_point_exclusions"][0]["type"] == "factor_point"
    assert payload["parameters"]["excluded_factor_points"][0]["origin"] == action["origin"]
    assert (run_dir / payload["selection_set_artifact"]).is_file()


def test_factor_point_exclusion_commit_report_discloses_metadata(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    detail = client.get(f"/api/runs/{run_id}/chain-ladder/factors/1").json()
    point = detail["points"][0]
    action = point["actions"]["point_exclusion"]
    preview = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json={
            "factor_selections": [],
            "exclusions": [
                {
                    "type": "factor_point",
                    "value": action["value"],
                    "origin": action["origin"],
                    "from_dev": action["from_dev"],
                    "to_dev": action["to_dev"],
                    "development_age": action["development_age"],
                    "rationale": "Point excluded after reviewing anomalous link ratio.",
                }
            ],
            "global_rationale": "Point exclusion committed for report disclosure test.",
            "created_by": {"id": "tester", "display_name": "Test User"},
        },
    ).json()
    committed = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={"global_rationale": preview["global_rationale"], "created_by": preview["created_by"]},
    ).json()
    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json=_selection_set_approval_payload(run_id, committed, decision_id="approve_point_exclusion_api"),
    )

    assert response.status_code == 200, response.text
    html = report_html.render(run_id, tmp_path / run_id)
    assert "factor_point" in html
    assert action["value"] in html
    assert f"origin {action['origin']}" in html
    assert f"development age {action['development_age']}".replace(">", "&gt;") in html
    assert "Report approval state" in html


def test_factor_point_exclusion_requires_rationale(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    detail = client.get(f"/api/runs/{run_id}/chain-ladder/factors/1").json()
    action = detail["points"][0]["actions"]["point_exclusion"]

    response = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json={
            "factor_selections": [],
            "exclusions": [
                {
                    "type": "factor_point",
                    "value": action["value"],
                    "origin": action["origin"],
                    "from_dev": action["from_dev"],
                    "rationale": "",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert "exclusion rationale is required" in response.json()["detail"]


def test_manual_override_requires_rationale(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    row = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"][0]

    response = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json={
            "factor_selections": [
                {
                    "development_age": row["development_age"],
                    "from_dev": row["from_dev"],
                    "selected_basis": "manual_override",
                    "selected_factor": row["selected_factor"] * 0.98,
                    "rationale": "",
                }
            ],
            "exclusions": [],
        },
    )

    assert response.status_code == 400
    assert "rationale is required for manual override" in response.json()["detail"]


def test_manual_override_preview_commit_decision_and_report_disclosure(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    row = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"][0]
    selected_factor = row["selected_factor"] * 0.98
    request = {
        "factor_selections": [
            {
                "development_age": row["development_age"],
                "from_dev": row["from_dev"],
                "selected_basis": "manual_override",
                "selected_factor": selected_factor,
                "rationale": "Manual override selected for demonstration after point review.",
            }
        ],
        "exclusions": [],
        "global_rationale": "Manual selected factor previewed through governed replay.",
        "created_by": {"id": "tester", "display_name": "Test User"},
    }
    preview = client.post(f"/api/runs/{run_id}/selection-sets/preview", json=request)

    assert preview.status_code == 200, preview.text
    selection_set = preview.json()
    assert selection_set["manual_overrides"][0]["selected_basis"] == "manual_override"
    assert selection_set["comparison"]["candidate"]["ibnr"] is not None

    committed = client.post(
        f"/api/runs/{run_id}/selection-sets/{selection_set['selection_set_id']}/commit",
        json={"global_rationale": selection_set["global_rationale"], "created_by": selection_set["created_by"]},
    ).json()
    decision_payload = _selection_set_approval_payload(run_id, committed, decision_id="approve_manual_override_api")
    decision_payload["manual_overrides"] = committed["manual_overrides"]
    decision_payload["factor_selections"] = committed["factor_selections"]
    decision = client.post(f"/api/runs/{run_id}/decisions", json=decision_payload)

    assert decision.status_code == 200, decision.text
    decision_artifact = json.loads((run_dir / "decisions" / "approve_manual_override_api.json").read_text())
    assert decision_artifact["manual_overrides"][0]["manual_override"] is True
    journal = client.get(f"/api/runs/{run_id}/decision-journal").json()
    journal_decision = next(
        decision
        for decision in journal["active_decisions"]
        if decision["decision_id"] == "approve_manual_override_api"
    )
    assert journal_decision["manual_overrides"][0]["manual_override"] is True
    assert journal_decision["factor_selections"][0]["selected_basis"] == "manual_override"
    html = report_html.render(run_id, run_dir)
    assert "manual_override (manual override)" in html
    assert "Manual override selected for demonstration after point review." in html


def test_constant_tail_preview_commit_and_report_disclosure(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    preview_response = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json={
            "factor_selections": [],
            "exclusions": [],
            "tail_selection": {
                "type": "constant",
                "factor": 1.01,
                "rationale": "A small explicit tail was reviewed for residual development.",
            },
            "global_rationale": "Tail scenario prepared for governed review.",
            "created_by": {"id": "tester", "display_name": "Test User"},
        },
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["parameters"]["tail"]["type"] == "constant"
    assert preview["tail_selection"]["selected_parameter"] == "constant:1.01"

    approval = _selection_set_approval_payload(run_id, preview, decision_id="approve_tail_selection_api")
    approval["tail_selection"] = preview["tail_selection"]
    commit_response = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={
            "global_rationale": preview["global_rationale"],
            "created_by": preview["created_by"],
            "decision": approval,
        },
    )
    assert commit_response.status_code == 200, commit_response.text
    committed = commit_response.json()
    assert committed["approval_decision"]["decision_id"] == "approve_tail_selection_api"
    assert committed["status"] == "committed"

    html = report_html.render(run_id, run_dir)
    assert "Tail selection" in html
    assert "constant:1.01" in html
    assert "residual development" in html


def test_explore_scenario_can_be_created_previewed_and_updated_without_decision(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    request = _explore_request_from_first_factor(client, run_id)

    created = client.post(f"/api/runs/{run_id}/explore/preview", json=request)

    assert created.status_code == 200, created.text
    scenario = created.json()
    assert scenario["mode"] == "explore"
    assert scenario["status"] == "exploratory"
    assert scenario["not_governed"] is True
    assert scenario["preview_result"]["selected_ibnr"] is not None
    assert (run_dir / "explore" / "scenarios" / f"{scenario['explore_scenario_id']}.json").is_file()
    assert not (run_dir / "decisions").exists()

    request["name"] = "Updated explore scenario"
    updated = client.post(f"/api/runs/{run_id}/explore/{scenario['explore_scenario_id']}", json=request)

    assert updated.status_code == 200, updated.text
    assert updated.json()["explore_scenario_id"] == scenario["explore_scenario_id"]
    assert updated.json()["name"] == "Updated explore scenario"
    listed = client.get(f"/api/runs/{run_id}/explore").json()
    assert listed["exploratory_scenario_count"] == 1


def test_explore_scenario_does_not_satisfy_report_readiness(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    created = client.post(
        f"/api/runs/{run_id}/explore/preview",
        json=_explore_request_from_first_factor(client, run_id),
    )
    assert created.status_code == 200, created.text

    readiness = client.get(f"/api/runs/{run_id}/report-readiness").json()

    assert readiness["exploratory_scenarios_exist"] is True
    assert readiness["governed_selection_set_exists"] is False
    assert readiness["governed_selection_approval_exists"] is False
    assert readiness["require_approval_would_pass"] is False
    assert any(blocker["code"] == "explore_not_governed" for blocker in readiness["blockers"])


def test_explore_promotion_requires_user_identity_and_rationale(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    scenario = client.post(
        f"/api/runs/{run_id}/explore/preview",
        json=_explore_request_from_first_factor(client, run_id),
    ).json()

    missing_user = client.post(
        f"/api/runs/{run_id}/explore/{scenario['explore_scenario_id']}/promote",
        json={"global_rationale": "Promote after review."},
    )
    missing_rationale = client.post(
        f"/api/runs/{run_id}/explore/{scenario['explore_scenario_id']}/promote",
        json={"created_by": {"id": "tester", "display_name": "Test User"}},
    )

    assert missing_user.status_code == 400
    assert "promotion requires user id" in missing_user.json()["detail"]
    assert missing_rationale.status_code == 400
    assert "promotion requires global_rationale" in missing_rationale.json()["detail"]


def test_explore_promotion_creates_governed_selection_and_decision(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    scenario = client.post(
        f"/api/runs/{run_id}/explore/preview",
        json=_explore_request_from_first_factor(client, run_id),
    ).json()

    response = client.post(
        f"/api/runs/{run_id}/explore/{scenario['explore_scenario_id']}/promote",
        json={
            "decision_id": "approve_promoted_explore_api",
            "global_rationale": "Promoted after reviewing exploratory impact.",
            "created_by": {"id": "tester", "display_name": "Test User"},
        },
    )

    assert response.status_code == 200, response.text
    promoted = response.json()["promotion"]
    selection_set = promoted["selection_set"]
    decision = promoted["decision"]
    assert selection_set["status"] == "committed"
    assert selection_set["source_explore_scenario_id"] == scenario["explore_scenario_id"]
    assert decision["decision_type"] == "selection_set_approval"
    assert decision["source_explore_scenario_id"] == scenario["explore_scenario_id"]
    assert (run_dir / selection_set["selection_set_artifact"]).is_file()
    assert (run_dir / "decisions" / "approve_promoted_explore_api.json").is_file()
    readiness = client.get(f"/api/runs/{run_id}/report-readiness").json()
    assert readiness["governed_selection_set_exists"] is True
    assert readiness["governed_selection_approval_exists"] is True
    html = report_html.render(run_id, run_dir)
    assert scenario["explore_scenario_id"] in html


def test_projection_endpoint_returns_by_origin_values_from_fit_json(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/projection")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["projection"][0]["origin"] == "1981"
    assert payload["projection"][0]["latest"] == 600.0
    assert payload["projection"][0]["ultimate"] == 750.0
    assert payload["projection"][0]["ibnr"] == 150.0
    assert payload["projection"][0]["selected_ibnr"] is None
    assert payload["projection"][0]["delta_ibnr"] is None
    assert payload["projection"][0]["ibnr_chart_pct"] == 100.0
    assert payload["projection"][0]["selected_ibnr_chart_pct"] is None


def test_triangle_heatmap_endpoint_returns_backend_values(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/triangle")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["available"] is True
    assert payload["origins"] == ["1981", "1982"]
    first = payload["cells"][0]
    assert first["origin"] == "1981"
    assert first["dev"] == "1"
    assert first["value"] == 400.0
    assert first["heat_bucket"] is not None
    assert first["source_artifact"] == "triangle.json"
    assert first["incremental_value"] == 400.0


def test_link_ratio_heatmap_endpoint_returns_backend_values(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/triangle")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["link_ratio_rows"][0]["origin"] == "1981"
    assert payload["link_ratio_rows"][0]["value"] == 1.5
    assert payload["link_ratio_rows"][0]["current_value"] == 400.0
    assert payload["link_ratio_rows"][0]["next_value"] == 600.0


def test_triangle_display_endpoint_returns_cumulative_incremental_and_link_ratio_views(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/chain-ladder/triangle")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["views"]) == {"cumulative", "incremental", "link_ratios"}
    cumulative = payload["views"]["cumulative"]["cells"]
    incremental = payload["views"]["incremental"]["cells"]
    link_ratios = payload["views"]["link_ratios"]["cells"]
    assert next(cell for cell in cumulative if cell["origin"] == "1981" and cell["dev"] == "2")["value"] == 600.0
    assert next(cell for cell in incremental if cell["origin"] == "1981" and cell["dev"] == "2")["value"] == 200.0
    assert payload["views"]["incremental"]["derived_by_backend"] is True
    assert link_ratios[0]["value"] == 1.5
    assert link_ratios[0]["source_artifact"] == "fit.json"


def test_report_readiness_returns_blocker_list(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/report-readiness")

    assert response.status_code == 200, response.text
    payload = response.json()
    blocker_codes = {blocker["code"] for blocker in payload["blockers"]}
    assert payload["status"] == "blocked"
    assert "validation_warnings" in blocker_codes
    assert "diagnostics_warnings" in blocker_codes
    assert "scenario_selection" in blocker_codes
    assert "report_approval" in blocker_codes
    assert "report_html" in blocker_codes
    assert payload["next_action"]["label"] == "Review validation warning"
    assert payload["next_action"]["target_tab"] == "decisions"
    assert payload["report_command"] == f"reserve report {run_id} --format-out html --require-approval --out runs"


def test_factor_preview_creates_reproducible_scenario_artifact(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    request = _preview_request_from_first_factor(client, run_id)

    first = client.post(f"/api/runs/{run_id}/factor-preview", json=request)
    second = client.post(f"/api/runs/{run_id}/factor-preview", json=request)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    payload = first.json()
    assert payload["scenario_type"] == "selected_factors_later"
    assert payload["selection"]["selected_basis"] == "last_3"
    assert (run_dir / payload["preview_artifact"]).is_file()


def test_factor_preview_comparison_returns_base_candidate_deltas(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    request = _preview_request_from_first_factor(client, run_id, basis="last_3")

    response = client.post(f"/api/runs/{run_id}/factor-preview", json=request)

    assert response.status_code == 200, response.text
    comparison = response.json()["comparison"]
    assert comparison["base"]["ibnr"] is not None
    assert comparison["candidate"]["ibnr"] is not None
    assert comparison["deltas"]["ibnr"] is not None
    assert comparison["by_origin_ibnr_impact"]
    assert all(
        impact["candidate_ibnr_chart_pct"] is not None
        for impact in comparison["by_origin_ibnr_impact"]
        if impact["candidate_ibnr"] is not None
    )


def test_factor_selection_decision_requires_rationale(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/factor-preview",
        json=_preview_request_from_first_factor(client, run_id),
    ).json()

    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json=_factor_selection_payload(run_id, preview, rationale=""),
    )

    assert response.status_code == 400
    assert "rationale is required" in response.json()["detail"]


def test_factor_selection_decision_requires_known_resulting_scenario_id(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/factor-preview",
        json=_preview_request_from_first_factor(client, run_id),
    ).json()
    decision = _factor_selection_payload(run_id, preview)
    decision["decision_id"] = "select_unknown_factor_preview"
    decision["resulting_scenario_id"] = "not_a_preview"

    response = client.post(f"/api/runs/{run_id}/decisions", json=decision)

    assert response.status_code == 400
    assert "factor preview artifacts" in response.json()["detail"]


def test_factor_selection_decision_refuses_overwrite(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/factor-preview",
        json=_preview_request_from_first_factor(client, run_id),
    ).json()
    decision = _factor_selection_payload(run_id, preview)

    first = client.post(f"/api/runs/{run_id}/decisions", json=decision)
    second = client.post(f"/api/runs/{run_id}/decisions", json=decision)

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert "decision already exists" in second.json()["detail"]


def test_selection_set_preview_creates_artifact(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)

    response = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json=_selection_set_request(client, run_id),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "preview"
    assert payload["selection_set_id"].startswith("selection_set_")
    assert payload["preview_scenario_id"] == payload["selection_set_id"]
    assert len(payload["factor_selections"]) == 2
    assert payload["exclusions"][0]["type"] == "origin"
    assert (run_dir / payload["selection_set_artifact"]).is_file()


def test_live_selection_preview_returns_candidate_triangle_without_writing_artifacts(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    request = _selection_set_request(client, run_id)
    request["global_rationale"] = ""
    for factor in request["factor_selections"]:
        factor["rationale"] = ""
    for exclusion in request["exclusions"]:
        exclusion["rationale"] = ""
    manifest_before = json.loads((run_dir / "manifest.json").read_text())

    response = client.post(f"/api/runs/{run_id}/selection-sets/live-preview", json=request)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "live_preview"
    assert payload["preview_kind"] == "transient"
    assert payload["selection_set_artifact"] is None
    assert payload["comparison"]["candidate"]["ibnr"] is not None
    assert all(
        impact["candidate_ibnr_chart_pct"] is not None
        for impact in payload["comparison"]["by_origin_ibnr_impact"]
        if impact["candidate_ibnr"] is not None
    )
    triangle = payload["candidate_triangle"]
    assert triangle["preview"]["kind"] == "transient"
    assert any(cell["is_projected"] for cell in triangle["views"]["cumulative"]["cells"])
    assert not (run_dir / "selection_sets").exists()
    assert json.loads((run_dir / "manifest.json").read_text()) == manifest_before


def test_live_selection_preview_allows_unrationaled_manual_override(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    row = client.get(f"/api/runs/{run_id}/chain-ladder/factors").json()["factors"][0]

    response = client.post(
        f"/api/runs/{run_id}/selection-sets/live-preview",
        json={
            "factor_selections": [
                {
                    "development_age": row["development_age"],
                    "from_dev": row["from_dev"],
                    "selected_basis": "manual_override",
                    "selected_factor": row["selected_factor"] * 0.98,
                    "rationale": "",
                }
            ],
            "exclusions": [],
            "global_rationale": "",
            "created_by": {},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["manual_overrides"][0]["rationale"] is None
    assert not (run_dir / "selection_sets").exists()


def test_selection_set_preview_combines_multiple_factors_and_exclusion_impact(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)

    response = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json=_selection_set_request(client, run_id),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["selected_factors_used"]) == 2
    assert payload["exclusions_used"] == [
        {"type": "origin", "value": "1981", "rationale": "Oldest origin excluded for sensitivity review."}
    ]
    assert payload["comparison"]["candidate"]["ibnr"] is not None
    assert payload["comparison"]["deltas"]["ibnr"] is not None
    assert payload["comparison"]["by_origin_ibnr_impact"]


def test_selection_set_exclusion_requires_rationale(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    request = _selection_set_request(client, run_id)
    request["exclusions"][0]["rationale"] = ""

    response = client.post(f"/api/runs/{run_id}/selection-sets/preview", json=request)

    assert response.status_code == 400
    assert "exclusion rationale is required" in response.json()["detail"]


def test_selection_set_commit_is_immutable(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json=_selection_set_request(client, run_id),
    ).json()

    first = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={"global_rationale": preview["global_rationale"], "created_by": preview["created_by"]},
    )
    second = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={"global_rationale": preview["global_rationale"], "created_by": preview["created_by"]},
    )

    assert first.status_code == 200, first.text
    committed = first.json()
    assert committed["status"] == "committed"
    assert json.loads((run_dir / committed["selection_set_artifact"]).read_text())["status"] == "committed"
    assert second.status_code == 400
    assert "cannot be overwritten" in second.json()["detail"]


def test_selection_set_approval_requires_valid_selection_set_id(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)

    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json={
            "schema_version": "0.1",
            "decision_id": "approve_missing_selection_set",
            "run_id": run_id,
            "task_id": None,
            "decision_type": "selection_set_approval",
            "status": "accepted",
            "selection_set_id": "not_real",
            "resulting_scenario_id": "not_real",
            "base_run_id": run_id,
            "rationale": "Trying to approve missing set.",
            "user": {"id": "tester", "display_name": "Test User"},
            "source_artifacts_reviewed": ["fit.json", "triangle.json"],
            "commands_or_parameters_affected": [],
            "supersedes_decision_id": None,
        },
    )

    assert response.status_code == 400
    assert "selection_set_id does not exist" in response.json()["detail"]


def test_selection_set_approval_requires_valid_resulting_scenario_id(tmp_path):
    run_id, _run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json=_selection_set_request(client, run_id),
    ).json()
    committed = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={"global_rationale": preview["global_rationale"], "created_by": preview["created_by"]},
    ).json()
    decision = _selection_set_approval_payload(run_id, committed)
    decision["decision_id"] = "approve_wrong_scenario"
    decision["resulting_scenario_id"] = "not_the_preview"

    response = client.post(f"/api/runs/{run_id}/decisions", json=decision)

    assert response.status_code == 400
    assert "resulting_scenario_id does not match" in response.json()["detail"]


def test_selection_set_approval_writes_decision_and_report_discloses_assumptions(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    preview = client.post(
        f"/api/runs/{run_id}/selection-sets/preview",
        json=_selection_set_request(client, run_id),
    ).json()
    committed = client.post(
        f"/api/runs/{run_id}/selection-sets/{preview['selection_set_id']}/commit",
        json={"global_rationale": preview["global_rationale"], "created_by": preview["created_by"]},
    ).json()

    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json=_selection_set_approval_payload(run_id, committed),
    )

    assert response.status_code == 200, response.text
    assert (run_dir / "decisions" / "approve_selection_set_api.json").is_file()
    projection = client.get(f"/api/runs/{run_id}/chain-ladder/projection")
    assert projection.status_code == 200, projection.text
    selected_rows = projection.json()["projection"]
    assert all(row["selected_ibnr"] is not None for row in selected_rows)
    assert all(row["selected_ibnr_chart_pct"] is not None for row in selected_rows)
    assert max(row["selected_ibnr_chart_pct"] for row in selected_rows) == 100.0
    html = report_html.render(run_id, run_dir)
    assert "Selection set" in html
    assert committed["selection_set_id"] in html
    assert "Selected factors" in html
    assert "Oldest origin excluded for sensitivity review." in html
    assert "approve_selection_set_api" in html


def test_bcl_review_task_is_generated_for_deterministic_chain_ladder_run(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    response = client.get(f"/api/runs/{run_id}/tasks")

    assert response.status_code == 200, response.text
    task = next(task for task in response.json()["tasks"] if task["task_type"] == "bcl_review")
    assert task["title"] == "Review deterministic chain ladder selections"
    assert task["allowed_decision_types"] == ["method_review_ack"]
    assert "fit.json" in task["source_artifacts"]


def test_committing_bcl_review_decision_writes_immutable_artifact(tmp_path):
    run_id, run_dir, client = _make_run(tmp_path, method="chain_ladder")
    task = next(
        task for task in client.get(f"/api/runs/{run_id}/tasks").json()["tasks"] if task["task_type"] == "bcl_review"
    )

    response = client.post(f"/api/runs/{run_id}/decisions", json=_method_review_payload(run_id, task["task_id"]))

    assert response.status_code == 200, response.text
    assert (run_dir / "decisions" / "ack_bcl_review_api.json").is_file()
    assert response.json()["decision"]["decision_type"] == "method_review_ack"
    assert response.json()["decision"]["input_hashes"]["fit.json"]


def test_dashboard_status_updates_after_bcl_review_decision(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")
    task = next(
        task for task in client.get(f"/api/runs/{run_id}/tasks").json()["tasks"] if task["task_type"] == "bcl_review"
    )
    before = client.get(f"/api/runs/{run_id}/status").json()

    response = client.post(f"/api/runs/{run_id}/decisions", json=_method_review_payload(run_id, task["task_id"]))

    assert response.status_code == 200, response.text
    after = response.json()["status"]
    assert after["unresolved_task_count"] == before["unresolved_task_count"] - 1
    refreshed_task = next(
        task for task in client.get(f"/api/runs/{run_id}/tasks").json()["tasks"] if task["task_type"] == "bcl_review"
    )
    assert refreshed_task["status"] == "completed"


def test_dashboard_frontend_does_not_calculate_actuarial_outputs_directly():
    text = (STATIC_DIR / "app.js").read_text()

    assert ".reduce(" not in text
    assert "Math." not in text
    assert "ultimate - latest" not in text
    assert "latest - ultimate" not in text
    assert "candidate_ibnr - base_ibnr" not in text


def test_projection_selected_scenario_impact_is_not_rendered_as_raw_object():
    text = (STATIC_DIR / "app.js").read_text()

    assert "fmtAvailable(row.selected_scenario_impact)" not in text
    assert "Selected Scenario Impact</th>" not in text
    assert "Selected IBNR" in text
    assert "Delta IBNR" in text
    assert "delta_ibnr_pct" in text


def test_scenario_cards_render_available_scenarios():
    text = (STATIC_DIR / "app.js").read_text()

    assert "renderScenarioCard" in text
    assert "scenario-card-grid" in text
    assert "Delta IBNR" in text


def test_factor_curve_uses_backend_factor_values():
    text = (STATIC_DIR / "app.js").read_text()

    assert "renderFactorCurve(rows)" in text
    assert "backend factor values" in text
    assert "fitted_chart_pct" in text
    assert "selected_chart_pct" in text
    assert "candidate_cards" in text
    assert "Curve fitting / smoothing" in text


def test_dashboard_uses_guided_workbench_tabs():
    html = (STATIC_DIR / "index.html").read_text()

    assert 'data-tab="triangle">Triangles' in html
    assert 'data-tab="decisions">Decisions' in html
    assert 'data-tab="report">Report' in html
    assert 'data-tab="projection"' not in html
    assert 'data-tab="tasks"' not in html


def test_frontend_has_guided_triangle_and_factor_workbench_controls():
    text = (STATIC_DIR / "app.js").read_text()

    assert "selectTriangleMode" in text
    assert "stageOriginExclusionFromCell" in text
    assert "Cell exclusion planned" in text
    assert "selectDevelopmentAge" in text
    assert "renderCandidateCard" in text
    assert "renderScenarioBridgePreview" in text
    assert "decision-journal" in text


def test_api_decision_endpoint_writes_valid_warning_ack(tmp_path):
    run_id, run_dir, client = _make_run(tmp_path)
    task = next(
        task
        for task in client.post(f"/api/runs/{run_id}/tasks/refresh").json()["tasks"]
        if task["task_type"] == "warning_review"
    )

    response = client.post(f"/api/runs/{run_id}/decisions", json=_warning_ack_payload(run_id, task["task_id"]))

    assert response.status_code == 200, response.text
    assert (run_dir / "decisions" / "ack_warning_api.json").is_file()
    assert response.json()["decision"]["input_hashes"]["validation.json"]


def test_api_decision_endpoint_rejects_invalid_scenario_selection(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)
    scenario_task = next(
        task
        for task in client.get(f"/api/runs/{run_id}/tasks").json()["tasks"]
        if task["task_type"] == "scenario_selection"
    )

    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json={
            "schema_version": "0.1",
            "decision_id": "select_missing_api",
            "run_id": run_id,
            "task_id": scenario_task["task_id"],
            "decision_type": "scenario_selection",
            "status": "accepted",
            "rationale": "",
            "user": {"id": "tester", "display_name": "Test User"},
            "source_artifacts_reviewed": ["fit.json", "sensitivity.json"],
            "commands_or_parameters_affected": [],
            "resulting_scenario_id": "not_real",
            "supersedes_decision_id": None,
        },
    )

    assert response.status_code == 400
    assert "scenario_index.json" in response.json()["detail"]


def test_api_decision_endpoint_refuses_overwrite(tmp_path):
    run_id, _run_dir, client = _make_run(tmp_path)
    task = next(
        task
        for task in client.post(f"/api/runs/{run_id}/tasks/refresh").json()["tasks"]
        if task["task_type"] == "warning_review"
    )
    payload = _warning_ack_payload(run_id, task["task_id"])

    first = client.post(f"/api/runs/{run_id}/decisions", json=payload)
    second = client.post(f"/api/runs/{run_id}/decisions", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert "decision already exists" in second.json()["detail"]


def test_dashboard_static_files_exist():
    assert (STATIC_DIR / "index.html").is_file()
    assert (STATIC_DIR / "app.js").is_file()
    assert (STATIC_DIR / "styles.css").is_file()


def test_dashboard_v2_static_files_exist():
    assert (V2_STATIC_DIR / "index.html").is_file()
    assert (V2_STATIC_DIR / "app.js").is_file()
    assert (V2_STATIC_DIR / "styles.css").is_file()


def test_dashboard_v2_is_mounted_without_replacing_existing_dashboard(tmp_path):
    _run_id, _run_dir, client = _make_run(tmp_path, method="chain_ladder")

    v2 = client.get("/workbench-v2/")
    legacy = client.get("/")

    assert v2.status_code == 200
    assert "Reserve Workbench" in v2.text
    assert "/workbench-v2/app.js" in v2.text
    assert legacy.status_code == 200
    assert "Interactive Reserving Workbench" in legacy.text


def test_factor_drag_mapping_is_backend_derived_for_both_graphs(tmp_path):
    run_id, run_dir, client = _make_real_bcl_run(tmp_path)
    factor_analysis.write_factor_analysis(run_id, run_dir)

    selected = client.post(
        f"/api/runs/{run_id}/chain-ladder/factor-drag",
        json={
            "from_dev": 3,
            "graph": "selected_age",
            "scale": "linear",
            "client_y": 120,
            "rect_top": 20,
            "rect_height": 360,
        },
    )
    assert selected.status_code == 200
    selected_payload = selected.json()
    assert selected_payload["manual_factor"] > 0
    assert selected_payload["selected_graph"]["linear_y_pct"] is not None
    assert selected_payload["status"] == "staged_value_only"

    all_ages = client.post(
        f"/api/runs/{run_id}/chain-ladder/factor-drag",
        json={
            "from_dev": 5,
            "graph": "all_development",
            "scale": "log",
            "client_y": 180,
            "rect_top": 20,
            "rect_height": 310,
        },
    )
    assert all_ages.status_code == 200
    assert all_ages.json()["manual_factor"] >= 1.0
    assert all_ages.json()["all_curve_y"] is not None


def test_dashboard_v2_declares_product_shell_components():
    html = (V2_STATIC_DIR / "index.html").read_text()
    text = (V2_STATIC_DIR / "app.js").read_text()

    assert 'data-tab="overview"' in html
    assert 'data-tab="triangles"' in html
    assert 'data-tab="factors"' not in html
    assert ">Development</button>" in html
    assert 'data-tab="scenarios"' in html
    assert 'data-tab="decisions"' in html
    assert 'data-tab="report"' in html
    assert 'data-tab="artifacts"' in html
    for component in [
        "CommandStrip",
        "LeftRail",
        "ValidationDrawer",
        "MetricStrip",
        "ModeSwitch",
        "ModeBanner",
        "NextActionCard",
        "TriangleHeatmap",
        "FactorCandidateCard",
        "FactorCurve",
        "renderFactorPointPlot",
        "renderFactorPointInspector",
        "stageManualOverride",
        "previewExploreScenario",
        "promoteExploreToGovernedDraft",
        "ScenarioCard",
        "DecisionLogEntry",
        "ReportReadinessGate",
    ]:
        assert f"function {component}" in text


def test_dashboard_v2_uses_existing_backend_endpoints():
    text = (V2_STATIC_DIR / "app.js").read_text()

    for endpoint in [
        "/api/runs",
        "chain-ladder/summary",
        "chain-ladder/factors",
        "chain-ladder/factors/",
        "chain-ladder/projection",
        "chain-ladder/triangle",
        "report-readiness",
        "selection-sets/preview",
        "selection-sets/live-preview",
        "/explore",
        "decision-journal",
        "/decisions",
        "/compare",
    ]:
        assert endpoint in text


def test_dashboard_v2_frontend_does_not_calculate_actuarial_outputs_directly():
    text = (V2_STATIC_DIR / "app.js").read_text()

    assert ".reduce(" not in text
    assert "Math." not in text
    assert "next_value / current_value" not in text
    assert "link_ratio =" not in text
    assert "ultimate - latest" not in text
    assert "latest - ultimate" not in text
    assert "candidate_ibnr - base_ibnr" not in text
    assert "ultimate: candidate" not in text


def test_dashboard_v2_keeps_raw_json_confined_to_artifacts_tab():
    text = (V2_STATIC_DIR / "app.js").read_text()

    assert "Raw JSON is intentionally confined to this tab." in text
    assert '<pre class="json-viewer">' in text
    assert "function renderArtifacts" in text
    assert "JSON.stringify(payload, null, 2)" in text


def test_dashboard_v2_factor_workflow_clarity_affordances():
    text = (V2_STATIC_DIR / "app.js").read_text()
    styles = (V2_STATIC_DIR / "styles.css").read_text()

    assert "selectionWorkflowState" in text
    assert "No change staged" in text
    assert "Staged, not previewed" in text
    assert "Preview available" in text
    assert "Committed selection set" in text
    assert "commitBlockers" in text
    assert "preview missing" in text
    assert "global rationale missing" in text
    assert "factor rationale missing" in text
    assert "exclusion rationale missing" in text
    assert "user identity missing" in text
    assert ".commit-blockers" in styles
    assert "EXPLORE" in text
    assert "GOVERNED" in text
    assert "Explore freely. Promote deliberately. Only governed selections enter the report pack." in text
    assert "NOT GOVERNED" in text
    assert ".mode-switch" in styles
    assert ".mode-banner" in styles


def test_dashboard_v2_factor_point_manual_preview_and_journal_states():
    text = (V2_STATIC_DIR / "app.js").read_text()
    styles = (V2_STATIC_DIR / "styles.css").read_text()

    assert "staged exclusion" in text
    assert "factor_point exclusion" in text
    assert "Source artifact" in text
    assert "Rationale" in text
    assert "Manual override requires rationale, preview, committed selection set" in text
    assert "Delta vs base" in text
    assert "Preview impact" in text
    assert "Base ultimate" in text
    assert "Selected ultimate" in text
    assert "Delta ultimate" in text
    assert "Base IBNR" in text
    assert "Selected IBNR" in text
    assert "Delta IBNR" in text
    assert "renderDecisionSelectionMetadata" in text
    assert "immutable artifact" in styles
    assert ".factor-point.staged" in styles
    assert ".manual-status-grid" in styles
