"""Local FastAPI surface for the interactive workbench MVP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from harness import __version__, factor_analysis, manifest, runs, selection_sets
from harness import factor_selection
from harness.runs import RunNotFoundError
from harness.workbench import chain_ladder, dashboard, decisions, explore, handoff, io, scenarios, schemas, state, tasks

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "dashboard" / "static"
V2_STATIC_DIR = Path(__file__).resolve().parent / "static_v2"
SAFE_JSON_ARTIFACTS = {
    "manifest.json",
    "validation.json",
    "fit.json",
    "triangle.json",
    "diagnostics.json",
    "sensitivity.json",
    schemas.TASKS_FILENAME,
    schemas.SCENARIO_INDEX_FILENAME,
    schemas.HANDOFF_FILENAME,
    schemas.FACTOR_ANALYSIS_FILENAME,
    schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
}
SAFE_JSON_DIRS = {
    schemas.DECISIONS_DIRNAME,
    schemas.COMPARISONS_DIRNAME,
    schemas.FACTOR_PREVIEWS_DIRNAME,
    schemas.SELECTION_SETS_DIRNAME,
    schemas.REVIEW_SNAPSHOTS_DIRNAME,
}


def _append_outputs_preserving_exit(run_dir: Path, outputs: list[str]) -> None:
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.is_file():
        return
    current = manifest.read_manifest(run_dir)
    manifest.update_manifest(run_dir, add_outputs=outputs, exit_code=current["exit_code"])


def _resolve_run_dir(run_id: str, runs_root: Path) -> Path:
    try:
        return runs.resolve_run_dir(run_id, out_root=runs_root)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _safe_artifact_path(run_dir: Path, artifact_name: str) -> Path:
    candidate = Path(artifact_name)
    if (
        not artifact_name
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.suffix != ".json"
    ):
        raise HTTPException(status_code=400, detail="unsafe artifact path")

    parts = candidate.parts
    if len(parts) == 1:
        if parts[0] not in SAFE_JSON_ARTIFACTS:
            raise HTTPException(status_code=404, detail="artifact is not exposed by the dashboard API")
    elif len(parts) == 2:
        if parts[0] not in SAFE_JSON_DIRS:
            raise HTTPException(status_code=404, detail="artifact directory is not exposed by the dashboard API")
    else:
        raise HTTPException(status_code=400, detail="nested artifact paths are not supported")

    root = Path(run_dir).resolve()
    path = (root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="unsafe artifact path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return path


def _read_optional_artifact(run_dir: Path, artifact_name: str) -> dict[str, Any] | None:
    path = Path(run_dir) / artifact_name
    if not path.is_file():
        return None
    return io.read_json(path)


def _decision_payload(run_dir: Path) -> dict[str, Any]:
    all_decisions = io.load_decisions(run_dir)
    superseded_ids = io.superseded_decision_ids(all_decisions)
    active = [d for d in all_decisions if d.get("decision_id") not in superseded_ids]
    superseded = [d for d in all_decisions if d.get("decision_id") in superseded_ids]
    return {
        "decisions": all_decisions,
        "active_decisions": active,
        "superseded_decisions": superseded,
        "decision_count": len(all_decisions),
        "active_decision_count": len(active),
        "superseded_decision_count": len(superseded),
    }


def create_app(runs_root: Path | str | None = None) -> FastAPI:
    root = Path(runs_root or os.environ.get("RESERVE_RUNS_ROOT", runs.DEFAULT_RUNS_ROOT))
    app = FastAPI(
        title="Interactive Reserving Workbench",
        version=__version__,
        description="Local MVP API for audited human validation artifacts. No production authentication.",
    )
    app.state.runs_root = root

    @app.middleware("http")
    async def no_cache_for_local_dashboard(request, call_next):
        response = await call_next(request)
        if (
            request.url.path in {"/", "/workbench-v2", "/workbench-v2/"}
            or request.url.path.endswith((".html", ".js", ".css"))
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "runs_root": str(app.state.runs_root),
            "auth": "local-mvp-none",
        }

    @app.get("/api/runs")
    def list_runs() -> dict[str, Any]:
        entries = []
        for run_id in runs.list_run_ids(out_root=app.state.runs_root):
            run_dir = runs.run_dir_path(run_id, app.state.runs_root)
            run_manifest = _read_optional_artifact(run_dir, "manifest.json") or {}
            entries.append(
                {
                    "run_id": run_id,
                    "created_utc": run_manifest.get("created_utc"),
                    "command": run_manifest.get("command"),
                    "outputs": run_manifest.get("outputs", []),
                    "exit_code": run_manifest.get("exit_code"),
                }
            )
        return {"runs_root": str(app.state.runs_root), "runs": entries}

    @app.get("/api/runs/{run_id}/status")
    def run_status(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return state.derive_status(run_id, run_dir)

    @app.get("/api/runs/{run_id}/tasks")
    def get_tasks(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return _read_optional_artifact(run_dir, schemas.TASKS_FILENAME) or tasks.build_validation_tasks(
            run_id, run_dir
        )

    @app.post("/api/runs/{run_id}/tasks/refresh")
    def refresh_tasks(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        payload = tasks.write_validation_tasks(run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, [schemas.TASKS_FILENAME])
        return payload

    @app.get("/api/runs/{run_id}/decisions")
    def list_decisions(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return _decision_payload(run_dir)

    @app.get("/api/runs/{run_id}/decision-journal")
    def decision_journal(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return dashboard.build_decision_journal(run_id, run_dir)

    @app.post("/api/runs/{run_id}/decisions")
    def commit_decision(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            decision = decisions.commit_decision_payload(run_id, run_dir, payload)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except decisions.DecisionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        tasks.write_validation_tasks(run_id, run_dir)
        output_artifacts = [
            f"{schemas.DECISIONS_DIRNAME}/{decision['decision_id']}.json",
            schemas.TASKS_FILENAME,
        ]
        if decision.get("review_snapshot_id"):
            output_artifacts.append(
                f"{schemas.REVIEW_SNAPSHOTS_DIRNAME}/{decision['review_snapshot_id']}.json"
            )
        _append_outputs_preserving_exit(
            run_dir,
            output_artifacts,
        )
        return {
            "decision": decision,
            "status": state.derive_status(run_id, run_dir),
            "decisions": _decision_payload(run_dir),
        }

    @app.get("/api/runs/{run_id}/scenarios")
    def list_scenarios(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        payload = scenarios.write_scenario_index(run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, [schemas.SCENARIO_INDEX_FILENAME])
        return payload

    @app.get("/api/runs/{run_id}/chain-ladder/summary")
    def chain_ladder_summary(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return chain_ladder.build_summary(run_id, run_dir)

    @app.get("/api/runs/{run_id}/chain-ladder/factors")
    def chain_ladder_factors(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return chain_ladder.build_factors(run_id, run_dir)

    @app.get("/api/runs/{run_id}/chain-ladder/factors/{from_dev}")
    def chain_ladder_factor_detail(run_id: str, from_dev: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return chain_ladder.build_factor_detail(run_id, run_dir, from_dev)

    @app.post("/api/runs/{run_id}/chain-ladder/factor-drag")
    def map_chain_ladder_factor_drag(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            return chain_ladder.map_factor_drag(run_id, run_dir, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/factor-analysis")
    def get_factor_analysis(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return _read_optional_artifact(run_dir, schemas.FACTOR_ANALYSIS_FILENAME) or {
            "run_id": run_id,
            "available": False,
            "status": "not_generated",
            "command": f"reserve factor-analysis {run_id} --format json --out {app.state.runs_root}",
        }

    @app.post("/api/runs/{run_id}/factor-analysis/refresh")
    def refresh_factor_analysis(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            analysis, suggestions = factor_analysis.write_factor_analysis(run_id, run_dir)
        except factor_analysis.FactorAnalysisError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        outputs = [schemas.FACTOR_ANALYSIS_FILENAME, schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME]
        _append_outputs_preserving_exit(run_dir, outputs)
        return {"analysis": analysis, "review_suggestions": suggestions, "outputs": outputs}

    @app.get("/api/runs/{run_id}/factor-review-suggestions")
    def get_factor_review_suggestions(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return _read_optional_artifact(run_dir, schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME) or {
            "run_id": run_id,
            "available": False,
            "status": "not_generated",
            "suggestions": [],
        }

    @app.get("/api/runs/{run_id}/chain-ladder/projection")
    def chain_ladder_projection(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return chain_ladder.build_projection(run_id, run_dir)

    @app.get("/api/runs/{run_id}/chain-ladder/triangle")
    def chain_ladder_triangle(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return chain_ladder.build_triangle_explorer(run_id, run_dir)

    @app.get("/api/runs/{run_id}/report-readiness")
    def report_readiness(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return dashboard.build_report_readiness(run_id, run_dir)

    @app.get("/api/runs/{run_id}/handoff")
    def review_handoff(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        payload = handoff.write_review_handoff(run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, [schemas.HANDOFF_FILENAME])
        return payload

    @app.post("/api/runs/{run_id}/factor-preview")
    def preview_factor_selection(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            preview = factor_selection.build_factor_preview(run_id, run_dir, payload)
        except factor_selection.FactorPreviewError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(
            run_dir,
            [preview["preview_artifact"]],
        )
        return preview

    @app.get("/api/runs/{run_id}/selection-sets")
    def list_selection_sets(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return {
            "run_id": run_id,
            "selection_sets": selection_sets.list_selection_sets(run_dir),
        }

    @app.post("/api/runs/{run_id}/selection-sets/preview")
    def preview_selection_set(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            preview = selection_sets.build_selection_set_preview(run_id, run_dir, payload)
            preview["candidate_triangle"] = chain_ladder.build_preview_triangle_explorer(
                run_id,
                run_dir,
                preview["candidate_triangle"],
                preview["candidate_fit"],
            )
        except selection_sets.SelectionSetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(run_dir, [preview["selection_set_artifact"]])
        return preview

    @app.post("/api/runs/{run_id}/selection-sets/live-preview")
    def live_preview_selection_set(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Return a transient deterministic rerun for workbench display.

        This endpoint is intentionally separate from the governed preview
        endpoint: it accepts incomplete rationale while an actuary is
        exploring a staged change, writes no artifacts, and cannot be
        committed or reported.
        """
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            preview = selection_sets.build_selection_set_preview(
                run_id,
                run_dir,
                payload,
                command=f"POST /api/runs/{run_id}/selection-sets/live-preview",
                dry_run=True,
                allow_incomplete_rationale=True,
            )
            preview["candidate_triangle"] = chain_ladder.build_preview_triangle_explorer(
                run_id,
                run_dir,
                preview["candidate_triangle"],
                preview["candidate_fit"],
            )
        except selection_sets.SelectionSetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return preview

    @app.post("/api/runs/{run_id}/selection-sets/{selection_set_id}/commit")
    def commit_selection_set(
        run_id: str,
        selection_set_id: str,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        original = selection_sets.load_selection_set(run_dir, selection_set_id)
        try:
            committed = selection_sets.commit_selection_set(run_id, run_dir, selection_set_id, payload)
            approval_candidate = payload.get("decision")
            approval_decision = None
            if approval_candidate is not None:
                if not isinstance(approval_candidate, dict):
                    raise decisions.DecisionValidationError("selection-set approval decision must be an object")
                if approval_candidate.get("decision_type") != "selection_set_approval":
                    raise decisions.DecisionValidationError(
                        "selection-set commit requires a selection_set_approval decision"
                    )
                if str(approval_candidate.get("selection_set_id") or "") != str(selection_set_id):
                    raise decisions.DecisionValidationError(
                        "approval decision selection_set_id does not match the committed selection set"
                    )
                approval_decision = decisions.commit_decision_payload(run_id, run_dir, approval_candidate)
        except (FileExistsError, decisions.DecisionValidationError) as exc:
            if original is not None:
                io.write_json(selection_sets.selection_set_path(run_dir, selection_set_id), original)
            status_code = 409 if isinstance(exc, FileExistsError) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except selection_sets.SelectionSetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        output_artifacts = [committed["selection_set_artifact"]]
        if approval_decision:
            tasks.write_validation_tasks(run_id, run_dir)
            output_artifacts.extend(
                [
                    f"{schemas.DECISIONS_DIRNAME}/{approval_decision['decision_id']}.json",
                    schemas.TASKS_FILENAME,
                ]
            )
        _append_outputs_preserving_exit(run_dir, output_artifacts)
        return {**committed, "approval_decision": approval_decision}

    @app.get("/api/runs/{run_id}/explore")
    def list_explore(run_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return explore.list_explore_scenarios(run_id, run_dir)

    @app.get("/api/runs/{run_id}/explore/compare")
    def compare_explore(run_id: str, left: str = Query(..., min_length=1), right: str = Query(..., min_length=1)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            comparison = explore.compare_explore_scenarios(run_id, run_dir, left, right)
        except explore.ExploreError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(
            run_dir,
            [f"{schemas.EXPLORE_DIRNAME}/comparisons/{comparison['comparison_id']}.json"],
        )
        return comparison

    @app.get("/api/runs/{run_id}/explore/{explore_scenario_id}")
    def get_explore(run_id: str, explore_scenario_id: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        scenario = explore.load_explore_scenario(run_dir, explore_scenario_id)
        if scenario is None:
            raise HTTPException(status_code=404, detail=f"explore_scenario_id not found: {explore_scenario_id}")
        return scenario

    @app.post("/api/runs/{run_id}/explore/preview")
    def preview_explore(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            scenario = explore.save_explore_scenario(run_id, run_dir, payload)
        except (explore.ExploreError, selection_sets.SelectionSetError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(
            run_dir,
            [
                f"{schemas.EXPLORE_DIRNAME}/explore_state.json",
                f"{schemas.EXPLORE_DIRNAME}/scenarios/{scenario['explore_scenario_id']}.json",
            ],
        )
        return scenario

    @app.post("/api/runs/{run_id}/explore/{explore_scenario_id}")
    def update_explore(run_id: str, explore_scenario_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            scenario = explore.save_explore_scenario(run_id, run_dir, payload, scenario_id=explore_scenario_id)
        except (explore.ExploreError, selection_sets.SelectionSetError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(
            run_dir,
            [
                f"{schemas.EXPLORE_DIRNAME}/explore_state.json",
                f"{schemas.EXPLORE_DIRNAME}/scenarios/{scenario['explore_scenario_id']}.json",
            ],
        )
        return scenario

    @app.post("/api/runs/{run_id}/explore/{explore_scenario_id}/promote")
    def promote_explore(run_id: str, explore_scenario_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            promoted = explore.promote_explore_scenario(run_id, run_dir, explore_scenario_id, payload)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (explore.ExploreError, selection_sets.SelectionSetError, decisions.DecisionValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        selection_set = promoted["selection_set"]
        decision = promoted["decision"]
        _append_outputs_preserving_exit(
            run_dir,
            [
                selection_set["selection_set_artifact"],
                f"{schemas.DECISIONS_DIRNAME}/{decision['decision_id']}.json",
                schemas.TASKS_FILENAME,
            ],
        )
        return {
            "promotion": promoted,
            "status": state.derive_status(run_id, run_dir),
            "readiness": dashboard.build_report_readiness(run_id, run_dir),
        }

    @app.get("/api/runs/{run_id}/compare")
    def compare_scenario(
        run_id: str,
        scenario_id: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        try:
            scenarios.write_scenario_index(run_id, run_dir)
            payload = scenarios.write_comparison(run_id, run_dir, scenario_id)
        except scenarios.ScenarioValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _append_outputs_preserving_exit(
            run_dir,
            [schemas.SCENARIO_INDEX_FILENAME, f"{schemas.COMPARISONS_DIRNAME}/{payload['comparison_id']}.json"],
        )
        return payload

    @app.get("/api/runs/{run_id}/artifacts/{artifact_name:path}")
    def get_artifact(run_id: str, artifact_name: str) -> dict[str, Any]:
        run_dir = _resolve_run_dir(run_id, app.state.runs_root)
        return io.read_json(_safe_artifact_path(run_dir, artifact_name))

    if V2_STATIC_DIR.is_dir():
        app.mount("/workbench-v2", StaticFiles(directory=V2_STATIC_DIR, html=True), name="workbench-v2")

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

    return app


app = create_app()
