"""Deterministic HTML renderer for a run folder (docs/cli-spec.md `report`).

Reads only runs/<run-id>/*.json — no numeric arguments, no network, no LLM
call. Every number is read directly from those files and wrapped with a
title="" attribute naming its source field; render() never computes a
figure, only formats one that already exists (CLAUDE.md rule 1 extends to
this renderer as much as to agent narration).

Section structure (0-8) per .claude/skills/reserving-report/SKILL.md.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).parent / "templates" / "report.html"
REQUIRED_FILES = ["manifest.json", "fit.json"]

# Mirrors .claude/skills/mack-diagnostics/SKILL.md's fixed narration verbatim.
# Duplicated deliberately: that skill governs an *agent's* narration (an LLM
# reading markdown); this renderer has no LLM in the loop at all (per
# docs/cli-spec.md: no LLM calls), so the same fixed prose has to exist as
# plain Python data here too. If the skill's wording changes, this dict needs
# updating to match — nothing enforces the two staying in sync automatically.
NARRATIVE_KEY_TEXT = {
    "dev_correlation_pass": (
        "No significant correlation detected between adjacent development-period "
        "link ratios — no evidence against the assumption that consecutive "
        "factors develop independently."
    ),
    "dev_correlation_warn": (
        "Adjacent development-period link ratios are correlated beyond this "
        "screen's threshold — evidence against the chain ladder's independence "
        "assumption between development periods."
    ),
    "cy_effect_pass": "No significant calendar-year clustering detected in standardized residuals.",
    "cy_effect_warn": (
        "Standardized residuals cluster by sign on at least one calendar-year "
        "diagonal beyond this screen's threshold — consistent with a "
        "calendar-year effect (something hitting every open origin at the same "
        "valuation date)."
    ),
    "residual_pattern_dev_pass": (
        "No significant trend detected between standardized residuals and "
        "development period."
    ),
    "residual_pattern_dev_warn": (
        "Standardized residuals trend with development period beyond this "
        "screen's threshold — the fitted development pattern may not fit "
        "uniformly across the whole triangle."
    ),
    "residual_pattern_origin_pass": (
        "No significant trend detected between standardized residuals and origin year."
    ),
    "residual_pattern_origin_warn": (
        "Standardized residuals trend with origin year beyond this screen's "
        "threshold — suggests an origin-year effect the single chain-ladder "
        "pattern doesn't capture."
    ),
    "outlier_link_ratios_pass": (
        "No individual link ratio beyond this screen's threshold relative to its "
        "own column's average."
    ),
    "outlier_link_ratios_warn": (
        "At least one individual link ratio is unusually far from its column's "
        "average — one origin's development is disproportionately driving "
        "that period's factor."
    ),
}


def check_complete(run_dir: Path) -> str | None:
    """Returns None if the run folder has what `report` needs; otherwise a
    human-readable reason it's incomplete (docs/cli-spec.md: exit 4)."""
    if not run_dir.is_dir():
        return f"run folder does not exist: {run_dir}"
    missing = [f for f in REQUIRED_FILES if not (run_dir / f).is_file()]
    if missing:
        return f"missing required file(s): {', '.join(missing)}"
    return None


def render(run_id: str, run_dir: Path) -> str:
    manifest = _read_json(run_dir / "manifest.json")
    fit = _read_json(run_dir / "fit.json")
    validation = _maybe_read_json(run_dir / "validation.json")
    triangle = _maybe_read_json(run_dir / "triangle.json")
    diagnostics = _maybe_read_json(run_dir / "diagnostics.json")
    sensitivity = _maybe_read_json(run_dir / "sensitivity.json")

    sections = [
        _section_scope(run_id, manifest, fit),
        _section_executive_summary(fit, diagnostics),
        _section_data_validation(manifest, validation),
        _section_method(fit),
        _section_results(fit, triangle, validation),
        _section_diagnostics(diagnostics),
        _section_sensitivity(sensitivity),
        _section_limitations(),
        _section_governance(manifest),
    ]
    body = "\n".join(sections)

    template = TEMPLATE_PATH.read_text()
    title = f"Reserving review — {run_id}"
    return template.replace("__REPORT_TITLE__", _esc(title)).replace("__REPORT_BODY__", body)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _maybe_read_json(path: Path) -> dict | None:
    return _read_json(path) if path.is_file() else None


def _esc(value: Any) -> str:
    """Escapes for text-node content (between tags) — quotes don't need
    escaping there, only &, <, >. Keeping quote=False here (rather than
    escaping everything indiscriminately) means an apostrophe in narration
    text stays a literal `'` in the page source, not an opaque `&#x27;` —
    worth preserving for a renderer whose whole point is a transparent,
    directly-readable source. Attribute values (title="...") need the
    stricter quote=True escaping instead — use _esc_attr for those."""
    return html.escape(str(value), quote=False)


def _esc_attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fig(value: Any, source: str, *, money: bool = False, decimals: int | None = None, null_text: str | None = None) -> str:
    """Wraps one figure with a hover tooltip naming its source field.

    `value is None` normally means "computed, but genuinely undefined" (a
    result field like a total or a by-origin reserve/std-err) — rendered as
    "undefined", never 0, never blank (docs/cli-spec.md v0.1.5). Some
    *parameter* fields (e.g. `n_periods: null` meaning "all periods", or a
    fixed tail's `sigma: null` meaning "not applicable, no distribution") are
    a different, ordinary kind of null — pass `null_text` for those so they
    don't get the alarming "undefined" treatment they don't deserve.
    """
    if value is None:
        if null_text is not None:
            return f'<span class="fig" title="{_esc_attr(source)}">{_esc(null_text)}</span>'
        tooltip = f"{source} — undefined, not zero (data-thinness; see §7)"
        return f'<span class="fig undefined" title="{_esc_attr(tooltip)}">undefined</span>'
    if isinstance(value, bool):
        text = _esc(value)
    elif isinstance(value, (int, float)):
        text = _format_number(value, money=money, decimals=decimals)
    elif isinstance(value, list):
        text = _esc(", ".join(str(v) for v in value)) if value else "<em>none</em>"
    else:
        text = _esc(value)
    return f'<span class="fig" title="{_esc_attr(source)}">{text}</span>'


def _format_number(value: float, *, money: bool, decimals: int | None = None) -> str:
    if decimals is None:
        decimals = 1 if money else 4
    if money:
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"


def _badge(verdict: str) -> str:
    return f'<span class="badge {_esc_attr(verdict)}">{_esc(verdict.upper())}</span>'


# --- sections ----------------------------------------------------------


def _section_scope(run_id: str, manifest: dict, fit: dict) -> str:
    input_path = manifest["inputs"][0]["path"]
    origins = sorted((row["origin"] for row in fit["by_origin"]), key=int)
    origin_range = f"{origins[0]}–{origins[-1]}" if origins else "n/a"
    return f"""
<section id="scope">
<h1>Reserving review</h1>
<p class="subtitle">Run {_esc(run_id)}</p>
<h2>0. Scope &amp; basis of preparation</h2>
<p class="source">Source: manifest.json, fit.json</p>
<p>This review covers a single {_fig(fit['method'], 'fit.json: method')}
chain-ladder fit of {_fig(input_path, 'manifest.json: inputs[0].path')},
spanning {_fig(len(origins), 'fit.json: by_origin (count)')} origin years
({_fig(origin_range, 'fit.json: by_origin[].origin (min–max)')}) —
nothing broader than the run cited throughout this document. Figures are
stated {_fig(fit.get('units', 'as-input'), 'fit.json: units')}; no currency,
scale, or independent valuation-date conversion has been applied.</p>
<p class="disclaimer">This is a reference implementation on public data. It
is not actuarial advice, offers no opinion on reserve adequacy for any real
entity, and nothing in this document is signed by anyone.</p>
</section>
"""


def _section_executive_summary(fit: dict, diagnostics: dict | None) -> str:
    totals = fit["totals"]
    if diagnostics is None:
        diag_line = "Diagnostics have not been run for this fit — no assumption-test result to report yet."
    else:
        overall = diagnostics["overall"]
        diag_line = f"Diagnostics overall: {_badge(overall)}"
        if overall == "warn":
            diag_line += " — see §5 before treating this figure as settled."
        else:
            diag_line += "."
    return f"""
<section id="executive-summary">
<h2>1. Executive summary</h2>
<p class="source">Source: fit.json{', diagnostics.json' if diagnostics else ''}</p>
<table>
<thead><tr><th>Latest</th><th>Ultimate</th><th>IBNR</th><th>Mack std. err.</th></tr></thead>
<tbody><tr>
<td>{_fig(totals['latest'], 'fit.json: totals.latest', money=True)}</td>
<td>{_fig(totals['ultimate'], 'fit.json: totals.ultimate', money=True)}</td>
<td>{_fig(totals['ibnr'], 'fit.json: totals.ibnr', money=True)}</td>
<td>{_fig(totals['mack_se'], 'fit.json: totals.mack_se', money=True)}</td>
</tr></tbody>
</table>
<p>{diag_line}</p>
</section>
"""


def _section_data_validation(manifest: dict, validation: dict | None) -> str:
    input_info = manifest["inputs"][0]
    if validation is None:
        body = """
<p>No <code>validation.json</code> is present in this run folder: this
fit's internal validate-first check passed without needing to persist
structural check details (docs/cli-spec.md v0.1.1 — a failed check
would have produced one instead, with no <code>fit.json</code> alongside
it, since the two never coexist in one run folder). If a separate,
standalone <code>reserve validate</code> run exists for this input, consult
it directly for the full structural check breakdown.</p>
"""
    else:
        rows = []
        for c in validation["checks"]:
            details = _esc(json.dumps(c["details"])) if c["details"] else "—"
            rows.append(
                f"<tr><td>{_esc(c['check_id'])}</td><td>{_badge(c['verdict'])}</td>"
                f"<td>{details}</td></tr>"
            )
        body = f"""
<table>
<thead><tr><th>Check</th><th>Verdict</th><th>Details</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
"""
    return f"""
<section id="data-validation">
<h2>2. Data &amp; validation</h2>
<p class="source">Source: manifest.json{', validation.json' if validation else ''}</p>
<p>Input: {_fig(input_info['path'], 'manifest.json: inputs[0].path')},
sha256 {_fig(input_info['sha256'], 'manifest.json: inputs[0].sha256')}.</p>
{body}
</section>
"""


def _section_method(fit: dict) -> str:
    rows = []
    for key, value in fit["parameters"].items():
        null_text = "all (default)" if key == "n_periods" and value is None else None
        rows.append(
            f"<tr><td>{_esc(key)}</td>"
            f"<td>{_fig(value, f'fit.json: parameters.{key}', null_text=null_text)}</td></tr>"
        )
    return f"""
<section id="method">
<h2>3. Method &amp; parameters</h2>
<p class="source">Source: fit.json</p>
<p>Method: {_fig(fit['method'], 'fit.json: method')}.</p>
<table>
<thead><tr><th>Parameter</th><th>Value</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</section>
"""


def _section_results(fit: dict, triangle: dict | None, validation: dict | None) -> str:
    triangle_html = (
        _triangle_grid_html(triangle, validation)
        if triangle is not None
        else '<p>triangle.json is not available for this run (written by fit as of '
        "docs/cli-spec.md v0.1.9 — absent for a run from before that change).</p>"
    )

    df_rows = []
    for i, f in enumerate(fit["development_factors"]):
        df_rows.append(
            f"<tr><td>{_esc(f['from_dev'])} → {_esc(f['to_dev'])}</td>"
            f"<td>{_fig(f['ldf'], f'fit.json: development_factors[{i}].ldf', decimals=4)}</td>"
            f"<td>{_fig(f['sigma'], f'fit.json: development_factors[{i}].sigma', decimals=4, null_text='n/a (fixed tail factor)')}</td></tr>"
        )

    origin_rows = []
    any_undefined = False
    for i, o in enumerate(fit["by_origin"]):
        if o["ibnr"] is None or o["mack_se"] is None:
            any_undefined = True
        origin_rows.append(
            f"<tr><td>{_esc(o['origin'])}</td>"
            f"<td>{_fig(o['latest'], f'fit.json: by_origin[{i}].latest', money=True)}</td>"
            f"<td>{_fig(o['ultimate'], f'fit.json: by_origin[{i}].ultimate', money=True)}</td>"
            f"<td>{_fig(o['ibnr'], f'fit.json: by_origin[{i}].ibnr', money=True)}</td>"
            f"<td>{_fig(o['mack_se'], f'fit.json: by_origin[{i}].mack_se', money=True)}</td></tr>"
        )

    totals = fit["totals"]
    if any(v is None for v in totals.values()):
        any_undefined = True

    note = ""
    if any_undefined:
        note = (
            '<p class="note"><strong>undefined</strong> means the underlying figure '
            "could not be estimated from the data available under this fit's "
            "parameters — it is not zero, and is never reported as zero. "
            "See §7, Limitations &amp; reliances.</p>"
        )

    bars_html = _ibnr_bars_html(fit["by_origin"])

    return f"""
<section id="results">
<h2>4. Results</h2>
<p class="source">Source: fit.json{', triangle.json' if triangle else ''}{', validation.json' if validation else ''} — units {_esc(fit.get('units', 'as-input'))}</p>
{note}
<h3>Development triangle</h3>
{triangle_html}
<h3>Development factors</h3>
<table>
<thead><tr><th>Dev</th><th>LDF</th><th>Sigma</th></tr></thead>
<tbody>{''.join(df_rows)}</tbody>
</table>
<h3>Reserves by origin</h3>
<table>
<thead><tr><th>Origin</th><th>Latest</th><th>Ultimate</th><th>IBNR</th><th>Mack std. err.</th></tr></thead>
<tbody>
{''.join(origin_rows)}
<tr style="font-weight:700;border-top:2px solid var(--ink);">
<td>Total</td>
<td>{_fig(totals['latest'], 'fit.json: totals.latest', money=True)}</td>
<td>{_fig(totals['ultimate'], 'fit.json: totals.ultimate', money=True)}</td>
<td>{_fig(totals['ibnr'], 'fit.json: totals.ibnr', money=True)}</td>
<td>{_fig(totals['mack_se'], 'fit.json: totals.mack_se', money=True)}</td>
</tr>
</tbody>
</table>
<h3>IBNR by origin, ±1 standard error</h3>
{bars_html}
</section>
"""


def _triangle_grid_html(triangle: dict, validation: dict | None) -> str:
    cells = triangle["cells"]
    origins = sorted({c["origin"] for c in cells}, key=int)
    max_dev = max((c["dev"] for c in cells), default=1)
    cell_by_key = {(c["origin"], c["dev"]): c for c in cells}

    # warn-class cells to highlight, keyed by (origin, dev) -> footnote texts.
    # More than one check can legitimately fire on the same cell (RAA's own
    # 1982/dev-7 cell trips both monotone_cumulative and
    # nonneg_incrementals) — a plain dict keyed by cell would silently drop
    # all but the last one; accumulate a list per cell instead.
    warn_cells: dict[tuple[str, int], list[str]] = {}
    if validation is not None:
        for check in validation["checks"]:
            details = check.get("details")
            if check["verdict"] != "warn" or not details:
                continue
            if "origin" in details and "dev" in details:
                key = (str(details["origin"]), int(details["dev"]))
                warn_cells.setdefault(key, []).append(f"{check['check_id']}: {json.dumps(details)}")

    # latest diagonal: each origin's own max *actual* dev
    diagonal: dict[str, int] = {}
    for c in cells:
        if c["type"] == "actual":
            diagonal[c["origin"]] = max(diagonal.get(c["origin"], 0), c["dev"])

    header = "".join(f"<th>{i}</th>" for i in range(1, max_dev + 1))
    rows = []
    footnotes: list[str] = []
    for origin in origins:
        cell_tds = []
        for dev in range(1, max_dev + 1):
            cell = cell_by_key.get((origin, dev))
            if cell is None:
                cell_tds.append("<td></td>")
                continue
            classes = [cell["type"]]
            if diagonal.get(origin) == dev:
                classes.append("diagonal")
            marker = ""
            key = (origin, dev)
            if key in warn_cells:
                classes.append("warn-cell")
                footnotes.append("; ".join(warn_cells[key]))
                marker = f'<sup class="footnote-marker">{len(footnotes)}</sup>'
            source = f"triangle.json: cells[origin={origin},dev={dev}]"
            if cell["value"] is None:
                value_html = f'<span class="fig undefined" title="{_esc_attr(source)} — undefined, not zero">undefined</span>'
            else:
                value_html = f'<span class="fig" title="{_esc_attr(source)}">{_format_number(cell["value"], money=True, decimals=1)}</span>'
            cell_tds.append(f'<td class="{" ".join(classes)}">{value_html}{marker}</td>')
        rows.append(f"<tr><td>{_esc(origin)}</td>{''.join(cell_tds)}</tr>")

    footnotes_html = ""
    if footnotes:
        items = "".join(f"<li>{_esc(f)}</li>" for f in footnotes)
        footnotes_html = f'<ol class="footnotes">{items}</ol>'

    return f"""<div class="triangle-wrap">
<table class="triangle-grid">
<thead><tr><th>Origin</th>{header}</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
<p class="legend-key">
<span class="swatch diagonal"></span>actual, latest diagonal outlined
&nbsp;&nbsp;<span class="swatch projected"></span>projected
&nbsp;&nbsp;<span class="swatch warn"></span>warn-class check — see footnote
</p>
{footnotes_html}"""


def _ibnr_bars_html(by_origin: list[dict]) -> str:
    extents = [
        o["ibnr"] + (o["mack_se"] or 0.0)
        for o in by_origin
        if o["ibnr"] is not None
    ]
    max_extent = max(extents) if extents and max(extents) > 0 else 1.0

    rows = []
    for o in by_origin:
        ibnr, se = o["ibnr"], o["mack_se"]
        if ibnr is None:
            rows.append(
                f'<div class="bar-row"><div class="bar-label">{_esc(o["origin"])}</div>'
                '<div class="bar-track"></div>'
                '<div class="bar-value undefined">undefined</div></div>'
            )
            continue
        pct = max(0.0, min(100.0, (ibnr / max_extent) * 100))
        whisker_html = ""
        if se is not None and se > 0:
            lo = max(0.0, ((ibnr - se) / max_extent) * 100)
            hi = min(100.0, ((ibnr + se) / max_extent) * 100)
            whisker_html = f'<div class="bar-whisker" style="left:{lo:.2f}%;width:{max(hi - lo, 0):.2f}%;"></div>'
        value_text = _format_number(ibnr, money=True)
        value_label = (
            f"{value_text} ± {_format_number(se, money=True)}"
            if se is not None
            else f"{value_text} (SE undefined)"
        )
        source = f"fit.json: by_origin[origin={o['origin']}]"
        rows.append(
            f'<div class="bar-row"><div class="bar-label">{_esc(o["origin"])}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.2f}%;" '
            f'title="{_esc_attr(source)}.ibnr"></div>{whisker_html}</div>'
            f'<div class="bar-value">{_esc(value_label)}</div></div>'
        )
    return f'<div class="bar-chart">{"".join(rows)}</div>'


def _section_diagnostics(diagnostics: dict | None) -> str:
    if diagnostics is None:
        return """
<section id="diagnostics">
<h2>5. Diagnostics</h2>
<p>Diagnostics have not been run for this fit. Run
<code>reserve diagnostics &lt;run-id&gt;</code> to generate this section —
no assumption-test result is fabricated here in its absence.</p>
</section>
"""
    blocks = []
    for i, t in enumerate(diagnostics["tests"]):
        narrative = NARRATIVE_KEY_TEXT.get(
            t["narrative_key"], "(no fixed narration mapped for this narrative_key)"
        )
        actions_html = ""
        if t["prescribed_actions"]:
            items = "".join(f"<li><code>{_esc(a)}</code></li>" for a in t["prescribed_actions"])
            actions_html = f'<div class="actions">Prescribed actions:<ul class="plain">{items}</ul></div>'
        blocks.append(
            f"""<div class="test-block">
{_badge(t['verdict'])} <strong>{_esc(t['test_id'])}</strong>
<p class="stat">statistic {_fig(t['statistic'], f'diagnostics.json: tests[{i}].statistic', decimals=4)}
vs. threshold {_fig(t['threshold'], f'diagnostics.json: tests[{i}].threshold', decimals=2)}</p>
<p>{_esc(narrative)}</p>
{actions_html}
</div>"""
        )
    return f"""
<section id="diagnostics">
<h2>5. Diagnostics</h2>
<p class="source">Source: diagnostics.json</p>
<p>Overall: {_badge(diagnostics['overall'])}</p>
{''.join(blocks)}
</section>
"""


def _section_sensitivity(sensitivity: dict | None) -> str:
    if sensitivity is None:
        return """
<section id="sensitivity">
<h2>6. Sensitivity</h2>
<p>Sensitivity has not been run for this fit. Run
<code>reserve sensitivity &lt;run-id&gt;</code> to generate this section.</p>
</section>
"""
    rows = []
    any_undefined = False
    for i, s in enumerate(sensitivity["scenarios"]):
        t = s["totals"]
        if any(v is None for v in t.values()):
            any_undefined = True
        delta = s["delta_from_base"]
        rows.append(
            f"<tr><td>{_esc(s['scenario_id'])}</td>"
            f"<td>{_esc(delta['parameter'])} = {_esc(delta['value'])}</td>"
            f"<td>{_fig(t['ultimate'], f'sensitivity.json: scenarios[{i}].totals.ultimate', money=True)}</td>"
            f"<td>{_fig(t['ibnr'], f'sensitivity.json: scenarios[{i}].totals.ibnr', money=True)}</td>"
            f"<td>{_fig(t['mack_se'], f'sensitivity.json: scenarios[{i}].totals.mack_se', money=True)}</td></tr>"
        )
    r = sensitivity["range"]
    if any(v is None for v in r.values()):
        any_undefined = True

    note = ""
    if any_undefined:
        note = (
            '<p class="note"><strong>undefined</strong> scenarios are excluded from the '
            "<code>range</code> aggregate below, not treated as zero — a scenario "
            "that removes the only data for some development transition can leave that "
            "transition's factor (and anything built from it) genuinely inestimable. "
            "That is a data-thinness finding about that specific perturbation, not a "
            "model failure. See §7.</p>"
        )

    return f"""
<section id="sensitivity">
<h2>6. Sensitivity</h2>
<p class="source">Source: sensitivity.json</p>
{note}
<table>
<thead><tr><th>Scenario</th><th>Change from base</th><th>Ultimate</th><th>IBNR</th><th>Mack std. err.</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<h3>IBNR range across scenarios</h3>
{_range_strip_html(r)}
</section>
"""


def _range_strip_html(r: dict) -> str:
    lo, base, hi = r["ibnr_min"], r["base_ibnr"], r["ibnr_max"]
    if lo is None or base is None or hi is None:
        return '<p class="note">Range unavailable — every scenario, and the base fit itself, was undefined.</p>'
    span = (hi - lo) or 1.0
    base_pct = max(0.0, min(100.0, ((base - lo) / span) * 100))
    return f"""<div class="range-strip">
<div class="range-track">
<div class="range-wash" style="left:0%;width:100%;"></div>
<div class="range-marker" style="left:{base_pct:.2f}%;" title="sensitivity.json: range.base_ibnr"></div>
</div>
<div class="range-labels">
<span>{_fig(lo, 'sensitivity.json: range.ibnr_min', money=True)}</span>
<span>base {_fig(base, 'sensitivity.json: range.base_ibnr', money=True)}</span>
<span>{_fig(hi, 'sensitivity.json: range.ibnr_max', money=True)}</span>
</div>
</div>"""


def _section_limitations() -> str:
    return """
<section id="limitations">
<h2>7. Limitations &amp; reliances</h2>
<ul class="plain">
<li>This review relies on the input triangle as provided. <code>validate</code>'s
checks are structural only — they do not audit the source system or confirm
the underlying claim records.</li>
<li>The five diagnostics tests are reference-implementation screening
indicators, not certified reproductions of Mack's published test statistics
(<code>.claude/skills/mack-diagnostics/SKILL.md</code>).</li>
<li><code>sensitivity</code>'s grid is a fixed, standard perturbation set —
it shows directional sensitivity to modeling choices, not an exhaustive
uncertainty quantification.</li>
<li>No regulatory or standards opinion is offered. This repository's
<code>corpus/</code> is an empty scaffold; a claim without a cited paragraph
is not made.</li>
<li>This harness does not provide actuarial advice and does not opine on
reserve adequacy. Any decision this review informs remains a qualified
actuary's own judgment.</li>
</ul>
</section>
"""


def _section_governance(manifest: dict) -> str:
    engine = manifest.get("engine") or {}
    env = manifest["environment"]
    input_info = manifest["inputs"][0]
    engine_text = (
        f"{engine.get('package', 'n/a')} {engine.get('version', '')}".strip()
        if engine
        else "n/a"
    )
    return f"""
<section id="governance" class="footer">
<h2>8. Governance</h2>
<dl>
<dt>Run ID</dt><dd>{_fig(manifest['run_id'], 'manifest.json: run_id')}</dd>
<dt>Command</dt><dd>{_fig(manifest['command'], 'manifest.json: command')}</dd>
<dt>Input</dt><dd>{_fig(input_info['path'], 'manifest.json: inputs[0].path')}</dd>
<dt>Input SHA-256</dt><dd>{_fig(input_info['sha256'], 'manifest.json: inputs[0].sha256')}</dd>
<dt>Engine</dt><dd>{_fig(engine_text, 'manifest.json: engine.package/version')}</dd>
<dt>Harness version</dt><dd>{_fig(env['harness_version'], 'manifest.json: environment.harness_version')}</dd>
<dt>Generated (UTC)</dt><dd>{_fig(manifest['created_utc'], 'manifest.json: created_utc')}</dd>
</dl>
</section>
"""
