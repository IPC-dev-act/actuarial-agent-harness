import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from harness.render import report_html

REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


class _StrictHTMLCheck(HTMLParser):
    """Fails on any parse error; used to confirm the rendered page is
    well-formed, not just "some string that looks like HTML"."""

    def error(self, message):
        raise AssertionError(f"HTML parse error: {message}")


def _assert_well_formed(html_text: str) -> None:
    _StrictHTMLCheck(convert_charrefs=True).feed(html_text)


# --- report_html.check_complete ------------------------------------------


def test_check_complete_missing_folder(tmp_path):
    reason = report_html.check_complete(tmp_path / "does-not-exist")
    assert reason is not None
    assert "does not exist" in reason


def test_check_complete_missing_fit_json(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text("{}")
    reason = report_html.check_complete(run_dir)
    assert reason is not None
    assert "fit.json" in reason


def test_check_complete_ok(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text("{}")
    (run_dir / "fit.json").write_text("{}")
    assert report_html.check_complete(run_dir) is None


# --- rendering, via a real fit ---------------------------------------------


@pytest.fixture()
def raa_run(tmp_path):
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(result.stdout)["run_id"]
    return run_id, tmp_path / run_id


def test_render_is_well_formed_and_self_contained(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    _assert_well_formed(html_text)
    assert "<script" not in html_text
    assert "http://" not in html_text
    assert "https://" not in html_text
    assert "@page" in html_text  # print-clean A4 rule present


def test_render_has_all_nine_sections(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    for section_id in (
        "scope",
        "executive-summary",
        "data-validation",
        "method",
        "results",
        "diagnostics",
        "sensitivity",
        "limitations",
        "governance",
    ):
        assert f'id="{section_id}"' in html_text, section_id


def test_render_totals_traceable_and_correct(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    assert 'title="fit.json: totals.ibnr"' in html_text
    assert ">52,135.2<" in html_text  # matches the verified RAA literature figure


def test_render_validation_checks_shown_including_warns(raa_run):
    # v0.1.9: fit always persists validation.json now, so a normal RAA run
    # (which genuinely warns on monotone_cumulative/nonneg_incrementals)
    # must show the real checks table, not the "explain absence" fallback.
    run_id, run_dir = raa_run
    assert (run_dir / "validation.json").is_file()
    html_text = report_html.render(run_id, run_dir)
    assert "monotone_cumulative" in html_text
    assert '>WARN<' in html_text
    assert "internal validate-first check passed" not in html_text


def test_render_legacy_run_without_validation_json_falls_back_gracefully(raa_run):
    # Defensive path only: a run folder written before v0.1.9 (or one
    # missing validation.json for any other reason) must still render §2
    # with an explanation, not a KeyError or a fabricated checks table.
    run_id, run_dir = raa_run
    (run_dir / "validation.json").unlink()
    html_text = report_html.render(run_id, run_dir)
    assert "internal validate-first check passed" in html_text


def test_render_diagnostics_absent_says_so_not_fabricated(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    assert "Diagnostics have not been run" in html_text
    assert "reserve diagnostics" in html_text


def test_render_sensitivity_absent_says_so_not_fabricated(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    assert "Sensitivity has not been run" in html_text


def test_render_diagnostics_fixed_narration_verbatim(tmp_path):
    result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(result.stdout)["run_id"]
    _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))
    run_dir = tmp_path / run_id

    html_text = report_html.render(run_id, run_dir)
    diagnostics = json.loads((run_dir / "diagnostics.json").read_text())
    for t in diagnostics["tests"]:
        expected = report_html.NARRATIVE_KEY_TEXT[t["narrative_key"]]
        assert expected in html_text, t["narrative_key"]
        assert f'>{t["verdict"].upper()}<' in html_text


def test_render_n_periods_null_is_all_not_undefined(raa_run):
    # parameters.n_periods: null means "all periods" (an ordinary default),
    # not a data-thinness "couldn't be computed" — must not render alarming.
    run_id, run_dir = raa_run
    fit_payload = json.loads((run_dir / "fit.json").read_text())
    assert fit_payload["parameters"]["n_periods"] is None
    html_text = report_html.render(run_id, run_dir)
    assert "all (default)" in html_text


def test_render_undefined_total_not_zero_or_blank(tmp_path):
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "mack",
        "--exclude-origins",
        "1981",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    run_id = json.loads(result.stdout)["run_id"]
    fit_payload = json.loads((tmp_path / run_id / "fit.json").read_text())
    assert fit_payload["totals"]["mack_se"] is None  # confirms the fixture is exercising null

    html_text = report_html.render(run_id, tmp_path / run_id)
    assert "undefined" in html_text
    assert "data-thinness" in html_text
    # the undefined figure itself must never render as a bare 0 or 0.0
    undefined_spans = re.findall(r'<span class="fig undefined"[^>]*>([^<]*)</span>', html_text)
    assert undefined_spans, "expected at least one undefined-figure span"
    assert all(s == "undefined" for s in undefined_spans)


# --- v0.1.9 visuals: triangle grid, IBNR bars, sensitivity strip -----------


def test_render_triangle_grid_present_and_sized_correctly(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    assert 'class="triangle-grid"' in html_text
    # RAA is a 10x10 triangle: header row has 10 dev columns + the Origin column
    assert html_text.count("<th>") >= 10


def test_render_triangle_grid_combines_multiple_warns_on_one_cell_into_one_footnote(raa_run):
    # RAA origin 1982/dev 7 trips BOTH monotone_cumulative and
    # nonneg_incrementals — a dict keyed by cell would silently drop one.
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    footnote_match = re.search(r'<ol class="footnotes">(.*?)</ol>', html_text, re.S)
    assert footnote_match, "expected at least one footnote for RAA's known warn cell"
    footnote_text = footnote_match.group(1)
    assert "monotone_cumulative" in footnote_text
    assert "nonneg_incrementals" in footnote_text
    # exactly one <li> — both findings combined, not two separate footnotes
    assert footnote_text.count("<li>") == 1
    assert html_text.count('class="footnote-marker"') == 1


def test_render_triangle_grid_diagonal_outlined_on_actual_boundary(raa_run):
    run_id, run_dir = raa_run
    run_dir_triangle = json.loads((run_dir / "triangle.json").read_text())
    # origin 1990 has exactly 1 observed period -> dev=1 is its diagonal cell
    assert any(
        c["origin"] == "1990" and c["dev"] == 1 and c["type"] == "actual"
        for c in run_dir_triangle["cells"]
    )
    html_text = report_html.render(run_id, run_dir)
    assert 'class="actual diagonal"' in html_text or 'class="actual diagonal warn-cell"' in html_text


def test_render_triangle_grid_missing_falls_back_gracefully(raa_run):
    # A run written before v0.1.9 has no triangle.json — §4 must say so
    # plainly, not KeyError.
    run_id, run_dir = raa_run
    (run_dir / "triangle.json").unlink()
    html_text = report_html.render(run_id, run_dir)
    assert "not available for this run" in html_text


def test_render_triangle_grid_undefined_cell_not_zero(tmp_path):
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "mack",
        "--exclude-origins",
        "1981",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    run_id = json.loads(result.stdout)["run_id"]
    triangle_payload = json.loads((tmp_path / run_id / "triangle.json").read_text())
    null_cells = [c for c in triangle_payload["cells"] if c["value"] is None]
    assert null_cells, "expected at least one undefined projected cell in this fixture"

    html_text = report_html.render(run_id, tmp_path / run_id)
    grid_match = re.search(r'<table class="triangle-grid">.*?</table>', html_text, re.S)
    assert grid_match
    grid_html = grid_match.group(0)
    for cell in null_cells:
        source = f"triangle.json: cells[origin={cell['origin']},dev={cell['dev']}]"
        assert f'title="{source} — undefined, not zero"' in grid_html


def test_render_ibnr_bars_present_with_whiskers(raa_run):
    run_id, run_dir = raa_run
    html_text = report_html.render(run_id, run_dir)
    assert 'class="bar-chart"' in html_text
    assert html_text.count('class="bar-row"') == 10  # one per RAA origin
    assert "bar-whisker" in html_text  # at least one origin has a finite mack_se


def test_render_ibnr_bars_se_undefined_labelled_not_omitted(tmp_path):
    result = _run_cli(
        "fit",
        str(RAA_CSV),
        "--method",
        "mack",
        "--exclude-origins",
        "1981",
        "--format",
        "json",
        "--out",
        str(tmp_path),
    )
    run_id = json.loads(result.stdout)["run_id"]
    html_text = report_html.render(run_id, tmp_path / run_id)
    assert "SE undefined" in html_text


def test_render_sensitivity_strip_present(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    _run_cli("sensitivity", run_id, "--format", "json", "--out", str(tmp_path))

    html_text = report_html.render(run_id, tmp_path / run_id)
    assert 'class="range-strip"' in html_text
    assert 'class="range-marker"' in html_text


# --- CLI integration ------------------------------------------------------


def test_cli_report_unknown_run_exit_4(tmp_path):
    result = _run_cli("report", "does-not-exist", "--out", str(tmp_path))
    assert result.returncode == 4


def test_cli_report_incomplete_run_exit_4(tmp_path):
    _run_cli("validate", str(RAA_CSV), "--format", "json", "--out", str(tmp_path))
    # validation.json has no run_id field (docs/cli-spec.md) — read it from
    # the folder name instead, same as tests/test_diagnostics.py does.
    run_id = next(p.name for p in tmp_path.iterdir())
    report_result = _run_cli("report", run_id, "--out", str(tmp_path))
    assert report_result.returncode == 4
    assert not (tmp_path / run_id / "report.html").exists()


def test_cli_report_format_out_md_exit_4(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    result = _run_cli("report", run_id, "--format-out", "md", "--out", str(tmp_path))
    assert result.returncode == 4


def test_cli_report_success_writes_file_updates_manifest_preserves_exit_code(tmp_path):
    fit_result = _run_cli(
        "fit", str(RAA_CSV), "--method", "mack", "--format", "json", "--out", str(tmp_path)
    )
    run_id = json.loads(fit_result.stdout)["run_id"]
    _run_cli("diagnostics", run_id, "--format", "json", "--out", str(tmp_path))

    manifest_before = json.loads((tmp_path / run_id / "manifest.json").read_text())

    result = _run_cli("report", run_id, "--out", str(tmp_path))
    assert result.returncode == 0, result.stderr
    report_path = tmp_path / run_id / "report.html"
    assert report_path.is_file()
    assert result.stdout.strip() == str(report_path)

    manifest_after = json.loads((tmp_path / run_id / "manifest.json").read_text())
    assert manifest_after["outputs"] == [
        "validation.json",
        "fit.json",
        "triangle.json",
        "diagnostics.json",
        "report.html",
    ]
    # report is a rendering step, not a new assessment — must not clobber
    # the exit_code diagnostics already set (this run should be 3, a warn).
    assert manifest_after["exit_code"] == manifest_before["exit_code"]
