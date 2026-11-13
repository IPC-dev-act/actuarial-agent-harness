"""Schema constants for Phase 1 workbench artifacts."""

from __future__ import annotations

SCHEMA_VERSION = "0.1"

TASKS_FILENAME = "validation_tasks.json"
HANDOFF_FILENAME = "review_handoff.json"
FACTOR_ANALYSIS_FILENAME = "factor_analysis.json"
FACTOR_REVIEW_SUGGESTIONS_FILENAME = "factor_review_suggestions.json"
DECISIONS_DIRNAME = "decisions"
SCENARIO_INDEX_FILENAME = "scenario_index.json"
COMPARISONS_DIRNAME = "comparisons"
FACTOR_PREVIEWS_DIRNAME = "factor_previews"
SELECTION_SETS_DIRNAME = "selection_sets"
EXPLORE_DIRNAME = "explore"
REVIEW_SNAPSHOTS_DIRNAME = "review_snapshots"

ARTIFACTS = [
    "manifest.json",
    "validation.json",
    "fit.json",
    "triangle.json",
    "diagnostics.json",
    "sensitivity.json",
    "report.html",
    TASKS_FILENAME,
    HANDOFF_FILENAME,
    FACTOR_ANALYSIS_FILENAME,
    FACTOR_REVIEW_SUGGESTIONS_FILENAME,
    SCENARIO_INDEX_FILENAME,
]

RUN_STATUSES = {
    "incomplete",
    "ready",
    "needs_judgment",
    "validated",
    "report_ready",
    "signed_off",
}
TASK_TYPES = {"warning_review", "scenario_selection", "bcl_review", "report_approval"}
TASK_STATUSES = {"pending", "completed", "superseded"}
TASK_SEVERITIES = {"info", "warning", "critical"}

DECISION_TYPES = {
    "warning_ack",
    "scenario_selection",
    "method_review_ack",
    "factor_selection",
    "selection_set_approval",
    "report_approval",
}
DECISION_STATUSES = {"accepted", "modified", "rejected"}
RATIONALE_REQUIRED_DECISION_TYPES = {
    "warning_ack",
    "method_review_ack",
    "factor_selection",
    "selection_set_approval",
}
RATIONALE_REQUIRED_STATUSES = {"modified", "rejected"}

SCENARIO_TYPES = {
    "base",
    "sensitivity",
    "exclusion",
    "method_alternative",
    "selected_factors_later",
}
SCENARIO_STATUSES = {"available", "incomplete"}
