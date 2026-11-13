from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_ROOT = REPO_ROOT / ".claude"

NEW_SKILLS = [
    "reserving-triangle-triage",
    "reserving-factor-review",
    "reserving-scenario-compare",
    "reserving-selection-challenge",
]

GUARDRAILS = [
    "Every number must cite a run artifact.",
    "No mental arithmetic.",
    "No invented figures.",
    "No hidden factor selection.",
    "No committing actuarial judgment.",
    "No report approval without human decision.",
    "No overriding warnings.",
    "No final report while required tasks are pending.",
    "Preview artifacts are exploratory.",
    "Decision artifacts are the only source of committed judgment.",
]


def _read(path: Path) -> str:
    return path.read_text()


def test_new_claude_skill_files_exist_and_include_guardrails():
    for skill_name in NEW_SKILLS:
        path = CLAUDE_ROOT / "skills" / skill_name / "SKILL.md"

        assert path.is_file(), f"missing skill file: {path}"
        text = _read(path)
        for phrase in GUARDRAILS:
            assert phrase in text


def test_review_command_mentions_bcl_dashboard_tasks_and_status():
    text = _read(CLAUDE_ROOT / "commands" / "review.md")

    assert "deterministic chain ladder" in text
    assert "BCL" in text
    assert "reserve tasks" in text
    assert "reserve status" in text
    assert "dashboard" in text
    assert "selection_sets/*.json" in text
    assert "decisions/*.json" in text
    assert "report_approval" in text


def test_review_command_does_not_instruct_claude_to_commit_decisions():
    text = _read(CLAUDE_ROOT / "commands" / "review.md")

    assert "Do not write or commit decisions." in text
    assert "Do not commit a selection set." in text
    assert "Do not approve a report." in text
    assert "Claude may prepare artifacts" in text


def test_report_command_checks_governance_state_before_generation():
    text = _read(CLAUDE_ROOT / "commands" / "report.md")

    assert "reserve status" in text
    assert "validation_tasks.json" in text
    assert "decisions/*.json" in text
    assert "selection_sets/*.json" in text
    assert "report_approval" in text
    assert "--require-approval" in text


def test_challenge_command_checks_selection_sets_and_decisions():
    text = _read(CLAUDE_ROOT / "commands" / "challenge.md")

    assert "selection_sets/*.json" in text
    assert "decisions/*.json" in text
    assert "scenario_index.json" in text
    assert "comparisons/*.json" in text
    assert "report.html" in text
    assert "Never supersede, reject, approve, or write a decision." in text


def test_command_wrappers_exist_and_delegate_to_skills():
    expected = {
        "triangle-triage.md": "reserving-triangle-triage",
        "factor-review.md": "reserving-factor-review",
        "scenario-explain.md": "reserving-scenario-compare",
    }
    for command_name, skill_name in expected.items():
        text = _read(CLAUDE_ROOT / "commands" / command_name)
        assert skill_name in text
        assert "What I ran" in text
        assert "What artifacts were created or read" in text


def test_factor_review_skill_does_not_authorize_final_factor_choice():
    text = _read(CLAUDE_ROOT / "skills" / "reserving-factor-review" / "SKILL.md")

    assert "Do not select final factors." in text
    assert "Do not commit selection sets." in text
    assert "Do not write decisions." in text
    assert "Direct the actuary to the dashboard" in text


def test_architecture_documents_claude_dashboard_boundary():
    text = _read(REPO_ROOT / "ARCHITECTURE.md")

    assert "Claude operating layer" in text
    assert "The dashboard remains the human-validation layer" in text
    assert "decisions/*.json" in text
