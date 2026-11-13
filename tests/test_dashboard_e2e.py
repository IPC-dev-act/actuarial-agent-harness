from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
RAA_CSV = REPO_ROOT / "examples" / "raa.csv"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _fit(tmp_path: Path, method: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "fit",
            str(RAA_CSV),
            "--method",
            method,
            "--format",
            "json",
            "--out",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode in {0, 3}, result.stderr
    return str(json.loads(result.stdout)["run_id"])


def _factor_analysis(tmp_path: Path, run_id: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "factor-analysis",
            run_id,
            "--format",
            "json",
            "--out",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def _wait_for_server(url: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"dashboard server did not start: {url}")


def test_dashboard_v2_loads_bcl_and_mack_without_browser_errors(tmp_path):
    bcl_run_id = _fit(tmp_path, "chain_ladder")
    _factor_analysis(tmp_path, bcl_run_id)
    mack_run_id = _fit(tmp_path, "mack")
    port = _free_port()
    env = {**os.environ, "RESERVE_RUNS_ROOT": str(tmp_path)}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "harness.workbench.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{base_url}/api/health")
        browser_errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: browser_errors.append(str(error)))
            page.goto(f"{base_url}/workbench-v2/", wait_until="networkidle")
            expect(page.locator("#toggleLeftRail")).to_have_attribute("aria-expanded", "false")
            page.locator("#toggleLeftRail").click()
            page.locator("#runSelect").select_option(bcl_run_id)
            page.locator("#toggleLeftRail").click()
            method_value = page.locator(".command-cell", has_text="Method").locator("strong")
            expect(method_value).to_have_text("Deterministic Chain Ladder")
            layout = page.evaluate(
                """() => ({
                    viewport: window.innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    mainWidth: document.querySelector('.v2-main').getBoundingClientRect().width,
                    metricOverflow: document.querySelector('#globalMetricStrip').scrollWidth > document.querySelector('#globalMetricStrip').clientWidth
                })"""
            )
            assert layout["documentWidth"] == layout["viewport"], layout
            assert layout["mainWidth"] >= 840, layout
            assert layout["metricOverflow"] is False, layout
            assert page.locator(".v2-shell").evaluate("node => node.classList.contains('left-collapsed')")
            assert page.locator(".v2-shell").evaluate("node => node.classList.contains('right-collapsed')")
            expect(page.locator("#toggleLeftRail")).to_have_attribute("aria-expanded", "false")
            expect(page.locator("#toggleRightRail")).to_have_attribute("aria-expanded", "false")
            page.locator("#toggleLeftRail").click()
            assert not page.locator(".v2-shell").evaluate("node => node.classList.contains('left-collapsed')")
            expect(page.locator("#toggleLeftRail")).to_have_attribute("aria-expanded", "true")
            expanded_left_main_width = page.evaluate(
                "() => Math.round(document.querySelector('.v2-main').getBoundingClientRect().width)"
            )
            assert expanded_left_main_width < layout["mainWidth"]
            page.locator("#toggleLeftRail").click()
            expect(page.locator("#toggleLeftRail")).to_have_attribute("aria-expanded", "false")

            page.locator("#toggleRightRail").click()
            assert not page.locator(".v2-shell").evaluate("node => node.classList.contains('right-collapsed')")
            expect(page.locator("#toggleRightRail")).to_have_attribute("aria-expanded", "true")
            expect(page.locator("#validationDrawer")).to_be_visible()
            expanded_right_main_width = page.evaluate(
                "() => Math.round(document.querySelector('.v2-main').getBoundingClientRect().width)"
            )
            assert expanded_right_main_width < layout["mainWidth"]
            page.locator("#toggleRightRail").click()
            expect(page.locator("#toggleRightRail")).to_have_attribute("aria-expanded", "false")

            # The graph-first default leaves both optional rails collapsed,
            # allowing the paired Development instruments to share a row.
            page.get_by_role("button", name="Development", exact=True).click()
            assert page.get_by_text("Triangle and Factor Selection", exact=True).is_visible()
            assert page.locator(".triangle-cell.projected").count() > 0
            assert page.locator(".projection-label").count() == 0
            expect(page.locator(".triangle-instrument")).to_have_count(2)
            expect(page.locator(".ratio-triangle-instrument").get_by_role("heading", name="Link Ratios")).to_be_visible()
            expect(page.locator(".all-factor-curve")).to_be_visible()
            development_layout = page.evaluate(
                """() => {
                  const value = document.querySelector('.value-triangle-instrument').getBoundingClientRect();
                  const ibnr = document.querySelector('.development-ibnr-panel .bar-list').closest('.surface').getBoundingClientRect();
                  const ratios = document.querySelector('.ratio-triangle-instrument').getBoundingClientRect();
                  const curve = document.querySelector('.development-factor-panel .all-factor-curve').getBoundingClientRect();
                  const pointChart = document.querySelector('.factor-chart-shell').getBoundingClientRect();
                  const sharedFittings = document.querySelector('.shared-fitting-options').getBoundingClientRect();
                  return {
                    ibnrBelowValue: ibnr.top >= value.bottom,
                    curveBelowRatios: curve.top >= ratios.bottom,
                    lowerInstrumentsAligned: Math.abs(ibnr.top - curve.top) <= 1,
                    sharedFittingsBelowGraphs: sharedFittings.top >= pointChart.bottom
                  };
                }"""
            )
            assert development_layout == {
                "ibnrBelowValue": True,
                "curveBelowRatios": True,
                "lowerInstrumentsAligned": True,
                "sharedFittingsBelowGraphs": True,
            }
            expect(page.locator(".factor-analysis-chart")).to_be_visible()
            expect(page.locator(".factor-curve-series")).to_have_count(1)
            expect(page.locator(".candidate-line-control")).to_have_count(1)
            page.get_by_role("button", name="Show all", exact=True).click()
            expect(page.locator(".factor-curve-series")).to_have_count(7)
            expect(page.locator(".candidate-line-control")).to_have_count(7)
            assert page.locator("details.mode-banner").get_attribute("open") is None
            assert page.locator(".selection-panel").get_attribute("open") is None
            ratio_observation = page.locator(".ratio-observation").first
            ratio_observation.click()
            expect(page.locator(".staged-factor-point")).to_have_count(2)
            expect(page.locator(".ratio-triangle-instrument .staged-factor-point")).to_have_count(1)
            assert page.locator(".selection-panel").get_attribute("open") is None
            ratio_observation.click()
            expect(page.locator(".staged-factor-point")).to_have_count(0)
            page.get_by_role("button", name="Cumulative", exact=True).click()
            all_age_handle = page.locator(".all-factor-drag-handle circle").first
            all_age_handle.dblclick()
            expect(page.locator(".factor-analysis-chart")).to_be_visible()
            expect(page.locator(".manual-override-panel.active")).to_have_count(0)
            page.locator(".focus-disclosure").locator("summary").click()
            simple_average = page.locator(".factor-card", has_text="Simple average")
            simple_average.locator('input[type="checkbox"]').uncheck()
            expect(page.locator(".candidate-line-control")).to_have_count(6)
            expect(page.locator(".factor-curve-series")).to_have_count(6)
            simple_average.locator('input[type="checkbox"]').check()
            expect(page.locator(".candidate-line-control")).to_have_count(7)
            expect(page.locator(".factor-curve-series")).to_have_count(7)
            page.locator(".value-triangle-instrument").get_by_role("button", name="5", exact=True).click()
            expect(page.locator(".factor-focus h3").first).to_have_text("5 -> 6")
            review_disclosure = page.locator(".workbench-disclosure", has_text="AI review evidence")
            review_disclosure.locator("summary").click()
            assert page.get_by_text("AI review queue", exact=True).is_visible()
            assert page.get_by_text("Evidence for actuarial judgment", exact=True).is_visible()
            first_suggestion = page.locator(".review-suggestion").first
            first_suggestion.get_by_role("button", name="Inspect", exact=True).click()
            expect(page.locator(".factor-point-detail")).to_contain_text("Exclusion delta IBNR")
            page.locator(".review-suggestion").first.get_by_role("button", name="Reviewed", exact=True).click()
            expect(page.locator(".selection-panel summary")).to_contain_text("No governed selection staged")
            page.get_by_role("button", name="Log", exact=True).click()
            expect(page.get_by_role("button", name="Log", exact=True)).to_have_class("active")
            selected_handle = page.locator(".manual-drag-hit")
            selected_handle.scroll_into_view_if_needed()
            selected_box = selected_handle.bounding_box()
            assert selected_box is not None
            hit_target = page.evaluate(
                "([x, y]) => { const node = document.elementFromPoint(x, y); return { tag: node?.tagName, classes: node?.getAttribute('class') }; }",
                [selected_box["x"] + 190, selected_box["y"] + selected_box["height"] / 2],
            )
            assert hit_target["classes"] == "manual-drag-hit", hit_target
            preview_line = page.locator(".manual-factor-line")
            before_drag_y = preview_line.get_attribute("y1")
            page.mouse.move(selected_box["x"] + 190, selected_box["y"] + selected_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(selected_box["x"] + 190, selected_box["y"] - 28)
            assert preview_line.get_attribute("y1") != before_drag_y
            expect(page.locator(".manual-override-panel.active")).to_have_count(0)
            page.mouse.up()
            expect(page.locator(".manual-override-panel.active")).to_be_visible()
            assert page.locator(".manual-override-panel").get_attribute("open") is None
            assert page.locator(".selection-panel").get_attribute("open") is None
            expect(page.locator(".triangle-table-wrap.is-live-preview")).to_have_count(1, timeout=20000)
            expect(page.locator("#globalMetricStrip")).not_to_contain_text("preview required")
            expect(page.locator(".factor-curve-series")).to_have_count(7)
            page.get_by_role("button", name="Smooth display", exact=True).click()
            expect(page.locator('.factor-curve-series[data-mode="smooth"]')).to_have_count(7)
            expect(page.locator(".all-factor-drag-handle")).to_have_count(9)
            all_age_handle = page.locator(".all-factor-drag-handle circle").first
            all_age_box = all_age_handle.bounding_box()
            assert all_age_box is not None
            before_all_age_y = all_age_handle.get_attribute("cy")
            page.mouse.move(all_age_box["x"] + all_age_box["width"] / 2, all_age_box["y"] + all_age_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(all_age_box["x"] + all_age_box["width"] / 2, all_age_box["y"] + 24)
            assert all_age_handle.get_attribute("cy") != before_all_age_y
            page.mouse.up()
            staged_delta = page.locator("#globalMetricStrip .metric", has_text="Delta IBNR").locator("strong")
            selected_ibnr = page.locator("#globalMetricStrip .metric", has_text="Selected IBNR").locator("strong")
            expect(page.locator(".triangle-table-wrap.is-live-preview")).to_have_count(1, timeout=20000)
            expect(selected_ibnr).not_to_contain_text("preview required")
            expect(selected_ibnr).not_to_contain_text("n/a")
            expect(staged_delta).not_to_contain_text("2 staged")
            expect(page.locator(".development-ibnr-panel .bar-fill.base-bar")).to_have_count(10)
            expect(page.locator(".development-ibnr-panel .bar-fill.selected-bar")).to_have_count(10)
            expect(page.locator(".development-ibnr-panel .chart-comparison-key")).to_contain_text("Base IBNR")
            expect(page.locator(".development-ibnr-panel")).to_contain_text("live deterministic preview")

            page.locator("#toggleLeftRail").click()
            page.locator("#toggleRightRail").click()

            page.set_viewport_size({"width": 980, "height": 900})
            tablet_layout = page.evaluate(
                """() => ({
                    viewport: window.innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    mainWidth: Math.round(document.querySelector('.v2-main').getBoundingClientRect().width),
                    drawerTop: Math.round(document.querySelector('.v2-drawer').getBoundingClientRect().top),
                    mainTop: Math.round(document.querySelector('.v2-main').getBoundingClientRect().top)
                })"""
            )
            assert tablet_layout["documentWidth"] == tablet_layout["viewport"], tablet_layout
            assert tablet_layout["mainWidth"] > 700, tablet_layout
            assert tablet_layout["drawerTop"] > tablet_layout["mainTop"], tablet_layout

            page.set_viewport_size({"width": 390, "height": 844})
            mobile_layout = page.evaluate(
                """() => ({
                    viewport: window.innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    railHeight: Math.round(document.querySelector('.v2-left').getBoundingClientRect().height),
                    metricColumns: getComputedStyle(document.querySelector('.metric-strip')).gridTemplateColumns.split(' ').length
                })"""
            )
            assert mobile_layout["documentWidth"] == mobile_layout["viewport"], mobile_layout
            assert mobile_layout["railHeight"] < 480, mobile_layout
            assert mobile_layout["metricColumns"] == 2, mobile_layout

            page.set_viewport_size({"width": 1440, "height": 1000})

            page.locator("#runSelect").select_option(mack_run_id)
            expect(method_value).to_have_text("Mack Chain Ladder", timeout=15000)

            screenshot_dir = os.environ.get("DASHBOARD_SCREENSHOT_DIR")
            if screenshot_dir:
                output = Path(screenshot_dir)
                output.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=output / "dashboard-v2-desktop.png", full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=output / "dashboard-v2-mobile.png", full_page=True)
            browser.close()
        assert browser_errors == []
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
