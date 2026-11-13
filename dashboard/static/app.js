const artifactNames = [
  "manifest.json",
  "validation.json",
  "fit.json",
  "triangle.json",
  "diagnostics.json",
  "sensitivity.json",
  "validation_tasks.json",
  "scenario_index.json"
];

const appState = {
  runs: [],
  runId: null,
  status: null,
  tasks: null,
  decisions: null,
  decisionJournal: null,
  scenarios: null,
  comparison: null,
  chainLadderSummary: null,
  chainLadderFactors: null,
  chainLadderProjection: null,
  triangleExplorer: null,
  reportReadiness: null,
  factorSelection: null,
  factorPreview: null,
  selectionDraft: { factors: {}, exclusions: { origins: "", originRationale: "", valuations: "", valuationRationale: "" } },
  selectionSetPreview: null,
  artifacts: {},
  selectedTask: null,
  selectedDevelopmentAge: null,
  selectedTriangleCell: null,
  selectedScenarioId: null,
  triangleMode: "cumulative",
  activeTab: "overview",
  artifactName: "manifest.json"
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_error) {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  return response.json();
}

function fmt(value) {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return String(value);
}

function fmtAvailable(value) {
  if (value === null || value === undefined) return "not available";
  if (typeof value === "object") return "available";
  return fmt(value);
}

function fmtFactor(value) {
  if (value === null || value === undefined) return "not available";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
  return String(value);
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

function percentText(value) {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  return String(value);
}

function barWidth(value) {
  if (typeof value !== "number") return "0%";
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2, useGrouping: false })}%`;
}

function badgeClass(status) {
  const normalized = String(status || "").toLowerCase().replaceAll(" ", "_");
  return `pill status-${safe(normalized)}`;
}

async function loadRuns() {
  const payload = await api("/api/runs");
  appState.runs = payload.runs || [];
  const select = $("runSelect");
  select.innerHTML = appState.runs
    .map((run) => `<option value="${safe(run.run_id)}">${safe(run.run_id)}</option>`)
    .join("");
  if (!appState.runId && appState.runs.length) {
    appState.runId = appState.runs[appState.runs.length - 1].run_id;
  }
  if (appState.runId) {
    select.value = appState.runId;
    await openRun(appState.runId);
  } else {
    render();
  }
}

async function openRun(runId) {
  appState.runId = runId;
  appState.selectedTask = null;
  appState.selectedTriangleCell = null;
  appState.selectedDevelopmentAge = null;
  appState.selectedScenarioId = null;
  appState.comparison = null;
  appState.factorSelection = null;
  appState.factorPreview = null;
  appState.selectionDraft = { factors: {}, exclusions: { origins: "", originRationale: "", valuations: "", valuationRationale: "" } };
  appState.selectionSetPreview = null;
  await refreshRun();
}

async function refreshRun() {
  if (!appState.runId) return;
  const run = encodeURIComponent(appState.runId);
  const [
    status,
    tasks,
    decisions,
    decisionJournal,
    scenarios,
    chainLadderSummary,
    chainLadderFactors,
    chainLadderProjection,
    triangleExplorer,
    reportReadiness
  ] = await Promise.all([
    api(`/api/runs/${run}/status`),
    api(`/api/runs/${run}/tasks`),
    api(`/api/runs/${run}/decisions`),
    api(`/api/runs/${run}/decision-journal`),
    api(`/api/runs/${run}/scenarios`),
    api(`/api/runs/${run}/chain-ladder/summary`),
    api(`/api/runs/${run}/chain-ladder/factors`),
    api(`/api/runs/${run}/chain-ladder/projection`),
    api(`/api/runs/${run}/chain-ladder/triangle`),
    api(`/api/runs/${run}/report-readiness`)
  ]);
  appState.status = status;
  appState.tasks = tasks;
  appState.decisions = decisions;
  appState.decisionJournal = decisionJournal;
  appState.scenarios = scenarios;
  appState.chainLadderSummary = chainLadderSummary;
  appState.chainLadderFactors = chainLadderFactors;
  appState.chainLadderProjection = chainLadderProjection;
  appState.triangleExplorer = triangleExplorer;
  appState.reportReadiness = reportReadiness;
  await loadArtifacts();
  render();
}

async function refreshTasks() {
  if (!appState.runId) return;
  const run = encodeURIComponent(appState.runId);
  appState.tasks = await api(`/api/runs/${run}/tasks/refresh`, { method: "POST" });
  appState.status = await api(`/api/runs/${run}/status`);
  render();
}

async function loadArtifacts() {
  appState.artifacts = {};
  const run = encodeURIComponent(appState.runId);
  await Promise.all(
    artifactNames.map(async (name) => {
      try {
        appState.artifacts[name] = await api(`/api/runs/${run}/artifacts/${encodeURIComponent(name)}`);
      } catch (_error) {
        appState.artifacts[name] = null;
      }
    })
  );
}

async function selectScenario(scenarioId) {
  appState.selectedScenarioId = scenarioId;
  const run = encodeURIComponent(appState.runId);
  appState.comparison = await api(
    `/api/runs/${run}/compare?scenario_id=${encodeURIComponent(scenarioId)}`
  );
  const scenarioTask = (appState.tasks?.tasks || []).find((task) => task.task_type === "scenario_selection");
  if (scenarioTask) appState.selectedTask = scenarioTask;
  await loadArtifacts();
  render();
}

async function selectTask(taskId) {
  appState.selectedTask = (appState.tasks?.tasks || []).find((task) => task.task_id === taskId) || null;
  render();
}

function setTab(tabName) {
  appState.activeTab = tabName;
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${tabName}Tab`);
  });
}

function render() {
  renderHeader();
  renderLeftRail();
  renderOverview();
  renderTriangle();
  renderFactors();
  renderScenarios();
  renderDecisionsTab();
  renderReportTab();
  renderArtifacts();
  renderReportReadiness();
  renderValidationPanel();
  renderDecisions();
  setTab(appState.activeTab);
}

function renderHeader() {
  const method = appState.chainLadderSummary?.display_method || appState.artifacts["fit.json"]?.method || "No method";
  const input = appState.chainLadderSummary?.input_file || appState.artifacts["manifest.json"]?.inputs?.[0]?.path || "No input";
  const totals = appState.artifacts["fit.json"]?.totals || {};
  const comparison = activeSelectionComparison();
  const deltas = comparison?.deltas || {};
  $("runTitle").textContent = appState.runId || "Select a run";
  $("runSubtitle").textContent = `${method} | ${input}`;
  const readiness = appState.reportReadiness?.status || "not_ready";
  const status = appState.status?.status || "no_run";
  $("headerBadges").innerHTML = `
    <span class="${badgeClass(status)}">${safe(status)}</span>
    <span class="${badgeClass(readiness)}">${safe(readiness)}</span>
  `;
  $("commandStrip").innerHTML = `
    <div class="command-cell wide"><span>Run</span><strong>${safe(appState.runId || "n/a")}</strong></div>
    <div class="command-cell"><span>Method</span><strong>${safe(method)}</strong></div>
    <div class="command-cell wide"><span>Input</span><strong>${safe(input)}</strong></div>
    <div class="command-cell status-cell"><span>Status</span><strong>${safe(status)}</strong></div>
    <div class="command-cell number-cell"><span>Latest</span><strong>${fmt(totals.latest)}</strong></div>
    <div class="command-cell number-cell"><span>Ultimate</span><strong>${fmt(totals.ultimate)}</strong></div>
    <div class="command-cell number-cell"><span>IBNR</span><strong>${fmt(totals.ibnr)}</strong></div>
    <div class="command-cell number-cell"><span>Scenario delta</span><strong>${fmt(deltas.ibnr)}</strong></div>
    <div class="command-cell status-cell"><span>Report gate</span><strong>${safe(readiness)}</strong></div>
  `;
}

function renderLeftRail() {
  const status = appState.status?.status || "no_run";
  $("statusBadge").textContent = status;
  $("statusBadge").className = `status-badge status-${status}`;

  const unresolved = appState.status?.unresolved_task_count ?? 0;
  const activeDecisions = appState.decisions?.active_decision_count ?? 0;
  const scenarioCount = appState.scenarios?.scenarios?.length ?? 0;
  const selectedScenario = appState.chainLadderSummary?.selected_scenario_id || "none";
  $("runCounts").innerHTML = `
    <dt>Unresolved tasks</dt><dd>${unresolved}</dd>
    <dt>Active decisions</dt><dd>${activeDecisions}</dd>
    <dt>Scenarios</dt><dd>${scenarioCount}</dd>
    <dt>Selected scenario</dt><dd>${safe(selectedScenario)}</dd>
  `;

  const artifactList = $("artifactList");
  if (!artifactList) return;
  const artifacts = appState.status?.artifacts || {};
  const presentArtifacts = Object.entries(artifacts).filter(([_name, exists]) => exists);
  const missingCount = Object.entries(artifacts).filter(([_name, exists]) => !exists).length;
  artifactList.innerHTML = `
    ${presentArtifacts
      .map(([name]) => `<span class="artifact-chip">${safe(name)}</span>`)
      .join("") || '<span class="artifact-chip missing">none available</span>'}
    ${missingCount ? `<span class="artifact-chip missing">${missingCount} missing</span>` : ""}
  `;
}

function warningRows() {
  const validation = appState.artifacts["validation.json"];
  const diagnostics = appState.artifacts["diagnostics.json"];
  const rows = [];
  for (const check of validation?.checks || []) {
    if (check.verdict === "warn") rows.push(`validation: ${check.check_id}`);
  }
  for (const test of diagnostics?.tests || []) {
    if (test.verdict === "warn") rows.push(`diagnostics: ${test.test_id}`);
  }
  return rows;
}

function renderOverview() {
  const manifest = appState.artifacts["manifest.json"] || {};
  const fit = appState.artifacts["fit.json"] || {};
  const totals = fit.totals || {};
  const input = (manifest.inputs || [])[0] || {};
  const methodLabel = appState.chainLadderSummary?.display_method || fit.method || "n/a";
  const warnings = warningRows();
  const selectedScenario = appState.chainLadderSummary?.selected_scenario_id || "none";
  const comparison = activeSelectionComparison();
  const selectedTotals = comparison?.candidate || {};
  const deltas = comparison?.deltas || {};

  $("overviewTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Overview cockpit</p>
        <h2>${safe(methodLabel)}</h2>
        <p class="muted">${safe(input.path || "n/a")}</p>
      </div>
      <span class="${badgeClass(appState.reportReadiness?.status)}">${safe(appState.reportReadiness?.status || "not ready")}</span>
    </div>
    <section class="overview-hero">
      <div class="hero-label">
        <span>Next required action</span>
        <span class="${badgeClass(appState.reportReadiness?.next_action?.blocked ? "blocked" : "ready")}">${safe(appState.reportReadiness?.next_action?.blocked ? "blocked" : "ready")}</span>
      </div>
      ${renderNextActionCard()}
    </section>
    <div class="metric-band">
      <div class="metric-item"><span>Latest</span><strong>${fmt(totals.latest)}</strong></div>
      <div class="metric-item"><span>Ultimate</span><strong>${fmt(totals.ultimate)}</strong></div>
      <div class="metric-item primary"><span>IBNR</span><strong>${fmt(totals.ibnr)}</strong></div>
      <div class="metric-item"><span>Selected IBNR</span><strong>${fmt(selectedTotals.ibnr)}</strong></div>
      <div class="metric-item"><span>Delta IBNR</span><strong>${fmt(deltas.ibnr)}</strong></div>
      <div class="metric-item gate"><span>Report readiness</span><strong>${safe(appState.reportReadiness?.status || "n/a")}</strong></div>
    </div>
    <div class="overview-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>Governance Readiness</h2>
          <span class="${badgeClass(appState.reportReadiness?.status)}">${safe(appState.reportReadiness?.status || "n/a")}</span>
        </div>
        ${renderGovernanceChecklist()}
      </div>
      <div class="panel chart-panel">
        <div class="panel-header">
          <h2>IBNR by Origin</h2>
          <span class="chip">fit.json</span>
        </div>
        ${renderIbnrByOriginChart()}
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2>Selected Scenario Impact</h2>
          <span class="chip">${safe(selectedScenario)}</span>
        </div>
        ${renderSelectedScenarioSummary()}
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2>Warnings</h2>
          <span class="chip">${warnings.length}</span>
        </div>
        <ul class="clean-list">${warnings.length ? warnings.map((w) => `<li>${safe(w)}</li>`).join("") : "<li>none</li>"}</ul>
      </div>
    </div>
    ${renderChainLadderSummary()}
  `;
}

function renderNextActionCard() {
  const action = appState.reportReadiness?.next_action;
  if (!action) return '<p class="empty">No guided action is available.</p>';
  const taskButton = action.task_id
    ? `<button class="primary-button" onclick="openTaskFromNextAction('${safe(action.task_id)}', '${safe(action.target_tab || "decisions")}')">Open Review</button>`
    : `<button class="primary-button" onclick="setTab('${safe(action.target_tab || "overview")}')">Open ${safe(action.target_tab || "section")}</button>`;
  return `
    <article class="next-action-card">
      <p class="action-kicker">${safe(action.label)}</p>
      <h3>${safe(action.detail || action.label)}</h3>
      <dl class="metric-list compact">
        <dt>Workflow</dt><dd>${safe(action.target_tab || "n/a")}</dd>
        <dt>Decision required</dt><dd>${safe(action.decision_type || "n/a")}</dd>
      </dl>
      <div class="row-actions">${taskButton}</div>
    </article>
  `;
}

function openTaskFromNextAction(taskId, tabName) {
  appState.selectedTask = (appState.tasks?.tasks || []).find((task) => task.task_id === taskId) || null;
  setTab(tabName);
  renderValidationPanel();
}

function renderGovernanceChecklist() {
  const items = appState.reportReadiness?.checklist || [];
  if (!items.length) return '<p class="empty">No readiness checklist available.</p>';
  return `
    <div class="checklist">
      ${items.map((item) => `
        <div class="check-item ${safe(item.status)}">
          <span class="check-dot"></span>
          <span>${safe(item.label)}</span>
          <strong>${safe(item.status)}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderIbnrByOriginChart() {
  const rows = appState.chainLadderProjection?.projection || [];
  if (!rows.length) return '<p class="empty">No by-origin projection available.</p>';
  return `
    <div class="bar-list">
      ${rows.map((row) => `
        <div class="bar-row">
          <span>${safe(row.origin)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${barWidth(row.ibnr_chart_pct)}"></div></div>
          <strong>${fmt(row.ibnr)}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function activeSelectionComparison() {
  const selected = appState.chainLadderSummary?.selected_scenario;
  return selected?.comparison || appState.selectionSetPreview?.comparison || null;
}

function renderSelectedScenarioSummary() {
  const comparison = activeSelectionComparison();
  if (!comparison) return '<p class="empty">No selected scenario impact is available.</p>';
  const base = comparison.base || {};
  const candidate = comparison.candidate || {};
  const deltas = comparison.deltas || {};
  return `
    <div class="delta-grid">
      <div class="delta-card"><span>Base IBNR</span><strong>${fmt(base.ibnr)}</strong></div>
      <div class="delta-card"><span>Selected IBNR</span><strong>${fmt(candidate.ibnr)}</strong></div>
      <div class="delta-card"><span>Delta Ultimate</span><strong>${fmt(deltas.ultimate)}</strong></div>
      <div class="delta-card"><span>Delta IBNR</span><strong>${fmt(deltas.ibnr)}</strong></div>
    </div>
  `;
}

function renderChainLadderSummary() {
  const summary = appState.chainLadderSummary;
  if (!summary?.is_chain_ladder) return "";
  const totals = summary.totals || {};
  return `
    <div class="summary-panel">
      <h2>Chain Ladder Summary</h2>
      <div class="section-grid">
        <div class="summary-block"><h2>Method</h2><p>${safe(summary.display_method)}</p></div>
        <div class="summary-block"><h2>Input File</h2><p>${safe(summary.input_file || "n/a")}</p></div>
        <div class="summary-block"><h2>Total Latest</h2><p>${fmt(totals.latest)}</p></div>
        <div class="summary-block"><h2>Total Ultimate</h2><p>${fmt(totals.ultimate)}</p></div>
        <div class="summary-block"><h2>Total IBNR</h2><p>${fmt(totals.ibnr)}</p></div>
        <div class="summary-block"><h2>Mack SE</h2><p>${fmt(totals.mack_se)}</p></div>
        <div class="summary-block"><h2>Origin Periods</h2><p>${fmt(summary.origin_period_count)}</p></div>
        <div class="summary-block"><h2>Development Periods</h2><p>${fmt(summary.development_period_count)}</p></div>
        <div class="summary-block"><h2>Selected Scenario</h2><p>${safe(summary.selected_scenario_id || "none")}</p></div>
      </div>
    </div>
  `;
}

function triangleModePayload(payload) {
  const mode = appState.triangleMode || "cumulative";
  return payload?.views?.[mode] || { label: "Cumulative", cells: payload?.cells || [] };
}

function triangleCellMap(cells) {
  const map = {};
  for (const cell of cells || []) {
    map[`${cell.origin}::${cell.dev}`] = cell;
  }
  return map;
}

function triangleCellClass(cell) {
  if (!cell) return "triangle-cell blank";
  const classes = ["triangle-cell", `heat-${cell.heat_bucket || 0}`];
  const selected = appState.selectedTriangleCell;
  if (cell.is_projected) classes.push("projected");
  if (cell.is_latest_diagonal) classes.push("latest-diagonal");
  if (cell.warning) classes.push("warning-cell");
  if (cell.excluded) classes.push("excluded-cell");
  if (
    selected &&
    String(selected.origin) === String(cell.origin) &&
    String(selected.dev) === String(cell.dev)
  ) {
    classes.push("selected-cell");
  }
  return classes.join(" ");
}

function triangleValue(cell) {
  if (!cell) return "";
  return cell.value === null || cell.value === undefined ? "" : fmt(cell.value);
}

function selectTriangleMode(mode) {
  appState.triangleMode = mode;
  appState.selectedTriangleCell = null;
  renderTriangle();
  renderValidationPanel();
}

function selectTriangleCell(origin, dev, mode) {
  const view = appState.triangleExplorer?.views?.[mode || appState.triangleMode];
  const cell = (view?.cells || []).find((item) => String(item.origin) === String(origin) && String(item.dev) === String(dev));
  appState.selectedTriangleCell = cell ? { ...cell, mode: mode || appState.triangleMode } : null;
  renderTriangle();
  renderValidationPanel();
}

function appendCommaValue(raw, value) {
  const values = commaValues(raw);
  if (!values.includes(String(value))) values.push(String(value));
  return values.join(", ");
}

function removeCommaValue(raw, value) {
  return commaValues(raw).filter((item) => item !== String(value)).join(", ");
}

function stageOriginExclusionFromCell(origin) {
  appState.selectionDraft.exclusions.origins = appendCommaValue(appState.selectionDraft.exclusions.origins, origin);
  appState.selectionSetPreview = null;
  showToast("Origin exclusion staged.");
  renderFactors();
  renderTriangle();
  renderValidationPanel();
}

function stageValuationExclusionFromCell(dev) {
  appState.selectionDraft.exclusions.valuations = appendCommaValue(appState.selectionDraft.exclusions.valuations, dev);
  appState.selectionSetPreview = null;
  showToast("Valuation/development exclusion staged.");
  renderFactors();
  renderTriangle();
  renderValidationPanel();
}

function clearStagedExclusionFromCell(origin, dev) {
  appState.selectionDraft.exclusions.origins = removeCommaValue(appState.selectionDraft.exclusions.origins, origin);
  appState.selectionDraft.exclusions.valuations = removeCommaValue(appState.selectionDraft.exclusions.valuations, dev);
  appState.selectionSetPreview = null;
  renderFactors();
  renderTriangle();
  renderValidationPanel();
}

function renderTriangle() {
  const payload = appState.triangleExplorer;
  if (!payload?.available) {
    $("triangleTab").innerHTML = '<p class="empty">No triangle artifact is available for this run.</p>';
    return;
  }
  const mode = appState.triangleMode || "cumulative";
  const view = triangleModePayload(payload);
  $("triangleTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Triangle explorer</p>
        <h2>${safe(view.label || "Triangle")}</h2>
        <p class="muted">Cumulative, incremental, and link-ratio values come from backend display payloads with source metadata.</p>
      </div>
      <span class="chip">${safe(payload.display_method)}</span>
    </div>
    <div class="segmented-control" role="group" aria-label="Triangle view">
      <button class="${mode === "cumulative" ? "active" : ""}" onclick="selectTriangleMode('cumulative')">Cumulative</button>
      <button class="${mode === "incremental" ? "active" : ""}" onclick="selectTriangleMode('incremental')">Incremental</button>
      <button class="${mode === "link_ratios" ? "active" : ""}" onclick="selectTriangleMode('link_ratios')">Link ratios</button>
    </div>
    <div class="dashboard-grid guided-grid">
      <div class="panel wide-panel">
        <div class="panel-header">
          <h2>${safe(view.label || "Triangle")} heatmap</h2>
          <div class="legend">
            <span><i class="legend-projected"></i>projected</span>
            <span><i class="legend-latest"></i>latest diagonal</span>
            <span><i class="legend-warning"></i>warning</span>
            <span><i class="legend-excluded"></i>excluded</span>
          </div>
        </div>
        ${renderTriangleGrid(payload, view.cells || [], mode)}
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2>Cell Detail</h2>
          <span class="chip">${safe(mode)}</span>
        </div>
        ${renderTriangleCellDetail()}
      </div>
    </div>
  `;
}

function renderTriangleGrid(payload, viewCells, mode) {
  const cells = triangleCellMap(viewCells);
  const headers = payload.developments || [];
  const origins = payload.origins || [];
  return `
    <div class="table-wrap">
      <table class="triangle-table">
        <thead>
          <tr><th>Origin</th>${headers.map((dev) => `<th>${safe(dev)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${origins.map((origin) => `
            <tr>
              <th>${safe(origin)}</th>
              ${headers.map((dev) => {
                const cell = cells[`${origin}::${dev}`];
                return `
                  <td class="${triangleCellClass(cell)}" onclick="selectTriangleCell('${safe(origin)}', '${safe(dev)}', '${safe(mode)}')">
                    ${triangleValue(cell)}
                  </td>
                `;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTriangleCellDetail() {
  const cell = appState.selectedTriangleCell;
  if (!cell) return '<p class="empty">Select a triangle cell to inspect source values and supported actions.</p>';
  const link = cell.link_ratio || {};
  const source = cell.source_artifact || (cell.mode === "link_ratios" ? "fit.json" : "triangle.json");
  const stagedOrigins = commaValues(appState.selectionDraft.exclusions.origins);
  const stagedValuations = commaValues(appState.selectionDraft.exclusions.valuations);
  const originStaged = stagedOrigins.includes(String(cell.origin));
  const valuationStaged = stagedValuations.includes(String(cell.dev));
  return `
    <div class="cell-detail">
      <dl class="metric-list compact">
        <dt>Origin</dt><dd>${safe(cell.origin)}</dd>
        <dt>Development age</dt><dd>${safe(cell.development_age || cell.dev)}</dd>
        <dt>Cumulative</dt><dd>${fmt(cell.cumulative_value ?? (cell.mode === "cumulative" ? cell.value : null))}</dd>
        <dt>Incremental</dt><dd>${fmt(cell.mode === "incremental" ? cell.value : cell.incremental_value)}</dd>
        <dt>Link ratio</dt><dd>${fmtFactor(cell.mode === "link_ratios" ? cell.value : link.value)}</dd>
        <dt>Source</dt><dd>${safe(source)}</dd>
        <dt>Warning</dt><dd>${cell.warning ? "yes" : "no"}</dd>
        <dt>Excluded</dt><dd>${cell.excluded ? "yes" : "no"}</dd>
      </dl>
      <div class="row-actions cell-actions">
        <button class="secondary-button" onclick="stageOriginExclusionFromCell('${safe(cell.origin)}')">${originStaged ? "Origin staged" : "Stage origin exclusion"}</button>
        <button class="secondary-button" onclick="stageValuationExclusionFromCell('${safe(cell.dev)}')">${valuationStaged ? "Valuation staged" : "Stage valuation exclusion"}</button>
        <button class="secondary-button" disabled>Cell exclusion planned</button>
        <button class="secondary-button" onclick="clearStagedExclusionFromCell('${safe(cell.origin)}', '${safe(cell.dev)}')">Clear staged</button>
      </div>
      <p class="evidence">Actions only stage a selection scenario. Preview and commit still run through backend validation.</p>
    </div>
  `;
}

function renderTasks() {
  const taskRows = appState.tasks?.tasks || [];
  const pending = taskRows.filter((task) => task.status === "pending");
  const completed = taskRows.filter((task) => task.status !== "pending");
  $("tasksTab").innerHTML = `
    <div class="row-actions" style="margin-bottom: 12px;">
      <button class="secondary-button" onclick="refreshTasks()">Refresh Tasks</button>
    </div>
    <h2>Pending</h2>
    ${pending.map(renderTaskRow).join("") || '<p class="empty">No pending tasks.</p>'}
    <h2 style="margin-top: 18px;">Completed</h2>
    ${completed.map(renderTaskRow).join("") || '<p class="empty">No completed tasks.</p>'}
  `;
}

function renderTaskRow(task) {
  const selected = appState.selectedTask?.task_id === task.task_id;
  return `
    <article class="task-row ${selected ? "selected" : ""}">
      <div>
        <div class="title-line">
          <h3>${safe(task.title)}</h3>
          <span class="pill severity-${safe(task.severity)}">${safe(task.task_type)}</span>
          <span class="pill">${safe(task.status)}</span>
        </div>
        <p>${safe(task.description)}</p>
        <div class="evidence">
          Sources: ${(task.source_artifacts || []).map(safe).join(", ") || "none"}<br />
          Evidence: ${(task.evidence_refs || []).map((ref) => `${safe(ref.artifact)} ${safe(ref.path)}`).join("; ") || "none"}
        </div>
      </div>
      <div class="row-actions">
        <button onclick="selectTask('${safe(task.task_id)}')">Review</button>
      </div>
    </article>
  `;
}

function renderScenarios() {
  const scenarios = appState.scenarios?.scenarios || [];
  const selected = scenarios.find((scenario) => scenario.scenario_id === appState.selectedScenarioId);
  $("scenariosTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Scenario analysis</p>
        <h2>Scenario Candidates</h2>
      </div>
      <span class="chip">${scenarios.length} candidates</span>
    </div>
    <div class="scenario-card-grid">
      ${scenarios.map(renderScenarioCard).join("") || '<p class="empty">No scenarios available.</p>'}
    </div>
    <div class="panel comparison-panel">
      <div class="panel-header">
        <h2>Comparison</h2>
        <span class="chip">${safe(appState.selectedScenarioId || "none selected")}</span>
      </div>
      ${renderComparison(selected)}
    </div>
  `;
}

function renderScenarioCard(scenario) {
  const metrics = scenario.key_metrics || {};
  const selected = appState.selectedScenarioId === scenario.scenario_id;
  const comparedDelta = selected ? appState.comparison?.deltas?.ibnr : null;
  return `
    <article class="scenario-card ${selected ? "selected" : ""}">
      <div class="title-line">
        <h3>${safe(scenario.scenario_id)}</h3>
        <span class="pill">${safe(scenario.scenario_type)}</span>
        <span class="${badgeClass(scenario.status)}">${safe(scenario.status)}</span>
      </div>
      <dl class="metric-list compact">
        <dt>Ultimate</dt><dd>${fmt(metrics.ultimate)}</dd>
        <dt>IBNR</dt><dd>${fmt(metrics.ibnr)}</dd>
        <dt>Delta IBNR</dt><dd>${fmt(comparedDelta)}</dd>
        <dt>Source</dt><dd>${safe((scenario.output_artifacts || [scenario.artifact_path || "n/a"])[0] || "n/a")}</dd>
      </dl>
      <div class="row-actions scenario-actions">
        <button ${scenario.scenario_id === "base" ? "disabled" : ""} onclick="selectScenario('${safe(scenario.scenario_id)}')">Compare</button>
      </div>
    </article>
  `;
}

function renderComparison(selected) {
  if (!appState.comparison || !selected) {
    return '<p class="empty">Select a scenario candidate to compare.</p>';
  }
  const metrics = Object.entries(appState.comparison.compared_metrics || {});
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Metric</th><th>Base</th><th>Candidate</th><th>Delta</th></tr></thead>
        <tbody>
          ${metrics
            .map(([name, values]) => {
              const delta = appState.comparison.deltas?.[name];
              return `<tr><td>${safe(name)}</td><td>${fmt(values.base)}</td><td>${fmt(values.candidate)}</td><td>${fmt(delta)}</td></tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>
    <div class="review-note-placeholder">
      <h3>Reviewer note</h3>
      <p class="empty">Add scenario rationale in the Human Validation panel before committing a scenario-selection decision.</p>
    </div>
    <div class="row-actions" style="margin-top: 10px;">
      <button class="primary-button" onclick="prepareScenarioDecision()">Select Scenario</button>
    </div>
  `;
}

function factorValueForBasis(row, basis) {
  if (basis === "fitted") return row.fitted_factor ?? row.selected_factor;
  return row.candidate_averages?.[basis];
}

function factorBasisLabel(basis) {
  return {
    fitted: "fitted",
    volume_weighted: "volume weighted",
    simple_average: "simple average",
    last_3: "last 3",
    last_5: "last 5"
  }[basis] || basis;
}

function renderFactorActions(row) {
  const bases = ["fitted", "volume_weighted", "simple_average", "last_3", "last_5"];
  return bases
    .map((basis) => {
      const value = factorValueForBasis(row, basis);
      const disabled = typeof value !== "number";
      return `<button class="secondary-button compact-button" ${disabled ? "disabled" : ""} onclick="selectFactorCandidate('${safe(row.from_dev)}', '${safe(basis)}')">Use ${safe(factorBasisLabel(basis))}</button>`;
    })
    .join("");
}

function draftFactors() {
  return Object.values(appState.selectionDraft?.factors || {});
}

function draftForRow(row) {
  return appState.selectionDraft?.factors?.[String(row.from_dev)] || null;
}

function selectedFactorRow(rows) {
  if (!rows.length) return null;
  const selected = appState.selectedDevelopmentAge;
  return rows.find((row) => String(row.from_dev) === String(selected)) || rows[0];
}

function selectDevelopmentAge(fromDev) {
  appState.selectedDevelopmentAge = String(fromDev);
  renderFactors();
}

function selectFactorCandidate(fromDev, basis) {
  const row = (appState.chainLadderFactors?.factors || []).find((item) => String(item.from_dev) === String(fromDev));
  if (!row) {
    showToast("Factor row not found.");
    return;
  }
  const value = factorValueForBasis(row, basis);
  if (typeof value !== "number") {
    showToast("Candidate basis is not available for this development age.");
    return;
  }
  appState.selectionDraft.factors[String(row.from_dev)] = {
    development_age: row.development_age,
    from_dev: row.from_dev,
    to_dev: row.to_dev,
    selected_basis: basis,
    selected_factor: value,
    previous_factor: row.selected_factor,
    rationale: appState.selectionDraft.factors[String(row.from_dev)]?.rationale || ""
  };
  appState.selectionSetPreview = null;
  renderFactors();
}

function removeDraftFactor(fromDev) {
  delete appState.selectionDraft.factors[String(fromDev)];
  appState.selectionSetPreview = null;
  renderFactors();
}

function setDraftFactorRationale(fromDev, value) {
  const draft = appState.selectionDraft.factors[String(fromDev)];
  if (draft) draft.rationale = value;
  appState.selectionSetPreview = null;
}

function setDraftExclusion(field, value) {
  appState.selectionDraft.exclusions[field] = value;
  appState.selectionSetPreview = null;
}

function renderFactors() {
  const payload = appState.chainLadderFactors;
  if (!payload?.available) {
    $("factorsTab").innerHTML = '<p class="empty">No factor output is available for this run.</p>';
    return;
  }
  const rows = payload.factors || [];
  const selectedRow = selectedFactorRow(rows);
  if (selectedRow && !appState.selectedDevelopmentAge) {
    appState.selectedDevelopmentAge = String(selectedRow.from_dev);
  }
  $("factorsTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Factor selection workbench</p>
        <h2>Development Factors</h2>
        <p class="muted">${safe(payload.display_method)}. Candidate values are read from fit.json; previews are produced by the backend.</p>
      </div>
      <span class="chip">${draftFactors().length} staged</span>
    </div>
    ${renderSelectedDevelopmentWorkbench(selectedRow)}
    ${renderFactorCurve(rows)}
    <div class="table-wrap factor-table">
      <table>
        <thead>
          <tr>
            <th>Development Age</th>
            <th>Base Fitted Factor</th>
            <th>Current Draft Selected Factor</th>
            <th>Volume Weighted Average</th>
            <th>Simple Average</th>
            <th>Last 3 Average</th>
            <th>Last 5 Average</th>
            <th>Cumulative Development Factor</th>
            <th>Basis</th>
            <th>Rationale</th>
            <th>Impact</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(renderFactorRow).join("") || '<tr><td colspan="12">not available</td></tr>'}
        </tbody>
      </table>
    </div>
    ${renderSelectionScenarioPanel()}
  `;
}

function renderSelectedDevelopmentWorkbench(row) {
  if (!row) return "";
  return `
    <div class="panel selected-age-panel">
      <div class="panel-header">
        <div>
          <h2>Selected Development Age</h2>
          <p class="muted">${safe(row.development_age || "not available")}</p>
        </div>
        <span class="chip">fit.json candidate values</span>
      </div>
      <div class="factor-card-grid">
        ${(row.candidate_cards || []).map((card) => renderCandidateCard(row, card)).join("") || '<p class="empty">Candidate averages are not available.</p>'}
        ${renderPlannedFactorCard("Curve fitting / smoothing")}
        ${renderPlannedFactorCard("Manual override")}
      </div>
      <p class="required-note">Selecting a non-current basis stages a draft change. Add rationale and preview before commit.</p>
    </div>
  `;
}

function renderCandidateCard(row, card) {
  const draft = draftForRow(row);
  const active = draft && draft.selected_basis === card.basis;
  const disabled = !card.available;
  return `
    <button class="factor-card ${active ? "active switch-on" : ""}" ${disabled ? "disabled" : ""} onclick="selectFactorCandidate('${safe(row.from_dev)}', '${safe(card.basis)}')">
      <span>${safe(card.label || factorBasisLabel(card.basis))}</span>
      <strong>${fmtFactor(card.value)}</strong>
      <small>${card.available ? `Delta ${fmtFactor(card.delta_vs_current)}` : "not available"}</small>
      <em>${card.rationale_required ? "rationale required" : "current basis"}</em>
    </button>
  `;
}

function renderPlannedFactorCard(label) {
  return `
    <button class="factor-card planned-control" disabled>
      <span>${safe(label)}</span>
      <strong>planned</strong>
      <small>not implemented</small>
      <em>governance design required</em>
    </button>
  `;
}

function renderFactorCurve(rows) {
  if (!rows.length) return '<p class="empty">No factor curve values are available.</p>';
  return `
    <div class="panel factor-curve-panel">
      <div class="panel-header">
        <h2>Factor Curve</h2>
        <div class="legend curve-legend">
          <span><i class="legend-source"></i>backend factor values</span>
          <span><i class="legend-base"></i>base fitted</span>
          <span><i class="legend-selected"></i>draft selected</span>
          <span><i class="legend-candidate"></i>candidate basis</span>
        </div>
      </div>
      <div class="curve-list">
        ${rows.map((row) => {
          const draft = draftForRow(row);
          const card = (row.candidate_cards || []).find((item) => draft && item.basis === draft.selected_basis);
          return `
            <div class="curve-row">
              <span>${safe(row.development_age || "n/a")}</span>
              <div class="curve-track">
                <div class="curve-bar base" style="width:${barWidth(row.fitted_chart_pct)}"></div>
                <div class="curve-bar selected" style="width:${barWidth(card?.chart_pct ?? row.selected_chart_pct)}"></div>
                ${(row.candidate_cards || []).map((candidate) => (
                  candidate.available
                    ? `<span class="curve-tick" title="${safe(candidate.label)}" style="left:${barWidth(candidate.chart_pct)}"></span>`
                    : ""
                )).join("")}
              </div>
              <strong>${fmtFactor(row.fitted_factor)} / ${draft ? fmtFactor(draft.selected_factor) : fmtFactor(row.selected_factor)}</strong>
            </div>
          `;
        }).join("")}
      </div>
      <div class="planned-placeholder">
        <strong>Curve fitting / smoothing</strong>
        <span>planned</span>
      </div>
    </div>
  `;
}

function renderFactorRow(row) {
  const draft = draftForRow(row);
  const selected = String(appState.selectedDevelopmentAge) === String(row.from_dev);
  const previewed = appState.selectionSetPreview ? "previewed" : "not previewed";
  const rationaleState = draft ? (draft.rationale?.trim() ? "present" : "missing") : "n/a";
  return `
    <tr class="${draft ? "draft-row" : ""} ${selected ? "selected-row" : ""}" onclick="selectDevelopmentAge('${safe(row.from_dev)}')">
      <td>${safe(row.development_age || "not available")}</td>
      <td>${fmtFactor(row.fitted_factor ?? row.selected_factor)}</td>
      <td>${draft ? fmtFactor(draft.selected_factor) : fmtFactor(row.selected_factor)}</td>
      <td>${fmtFactor(row.candidate_averages?.volume_weighted)}</td>
      <td>${fmtFactor(row.candidate_averages?.simple_average)}</td>
      <td>${fmtFactor(row.candidate_averages?.last_3)}</td>
      <td>${fmtFactor(row.candidate_averages?.last_5)}</td>
      <td>${fmtFactor(row.cumulative_development_factor)}</td>
      <td>${safe(draft ? factorBasisLabel(draft.selected_basis) : row.factor_basis || "not available")}</td>
      <td>${safe(rationaleState)}</td>
      <td>${safe(draft ? previewed : "n/a")}</td>
      <td>
        <div class="row-actions factor-actions">
          <button class="secondary-button compact-button" onclick="event.stopPropagation(); selectDevelopmentAge('${safe(row.from_dev)}')">Review</button>
          ${draft ? `<button class="secondary-button compact-button" onclick="event.stopPropagation(); removeDraftFactor('${safe(row.from_dev)}')">Clear</button>` : ""}
        </div>
      </td>
    </tr>
  `;
}

function renderSelectionScenarioPanel() {
  const factors = draftFactors();
  const exclusions = appState.selectionDraft.exclusions;
  const preview = appState.selectionSetPreview;
  const comparison = preview?.comparison || {};
  const base = comparison.base || {};
  const candidate = comparison.candidate || {};
  const deltas = comparison.deltas || {};
  return `
    <div class="summary-panel selection-scenario-panel">
      <h2>Selection Scenario</h2>
      <div class="draft-grid">
        <div>
          <h3>Pending Factor Changes</h3>
          ${factors.length ? factors.map(renderDraftFactor).join("") : '<p class="empty">No factor changes staged.</p>'}
        </div>
        <div>
          <h3>Exclusions</h3>
          <div class="form-grid">
            <div class="form-row">
              <label for="originExclusions">Origin years</label>
              <input id="originExclusions" value="${safe(exclusions.origins || "")}" placeholder="comma-separated" oninput="setDraftExclusion('origins', this.value)" />
            </div>
            <div class="form-row">
              <label for="originExclusionRationale">Origin exclusion rationale</label>
              <textarea id="originExclusionRationale" oninput="setDraftExclusion('originRationale', this.value)">${safe(exclusions.originRationale || "")}</textarea>
            </div>
            <div class="form-row">
              <label for="valuationExclusions">Valuation years</label>
              <input id="valuationExclusions" value="${safe(exclusions.valuations || "")}" placeholder="comma-separated" oninput="setDraftExclusion('valuations', this.value)" />
            </div>
            <div class="form-row">
              <label for="valuationExclusionRationale">Valuation exclusion rationale</label>
              <textarea id="valuationExclusionRationale" oninput="setDraftExclusion('valuationRationale', this.value)">${safe(exclusions.valuationRationale || "")}</textarea>
            </div>
          </div>
        </div>
      </div>
      <h3 style="margin-top: 14px;">Impact Preview</h3>
      ${preview ? renderScenarioBridgePreview(preview, base, candidate, deltas) : '<div class="empty-state">Stage factor choices and preview scenario.</div>'}
      ${renderOriginImpact(preview)}
      <div class="form-grid factor-decision-form">
        <div class="form-row">
          <label for="selectionGlobalRationale">Global rationale</label>
          <textarea id="selectionGlobalRationale">${safe($("selectionGlobalRationale")?.value || preview?.global_rationale || "")}</textarea>
        </div>
        <div class="form-row">
          <label for="factorUserId">User id</label>
          <input id="factorUserId" value="${safe(localStorage.getItem("reserveUserId") || "")}" />
        </div>
        <div class="form-row">
          <label for="factorDisplayName">Display name</label>
          <input id="factorDisplayName" value="${safe(localStorage.getItem("reserveDisplayName") || "")}" />
        </div>
        <div class="row-actions" style="justify-content: flex-start;">
          <button class="secondary-button" onclick="previewSelectionSet()">Preview Scenario</button>
          <button class="primary-button" ${preview ? "" : "disabled"} onclick="commitSelectionSet()">Commit Selection Set</button>
        </div>
      </div>
    </div>
  `;
}

function renderScenarioBridgePreview(preview, base, candidate, deltas) {
  return `
    <div class="section-grid scenario-bridge">
      <div class="summary-block"><h2>Base Ultimate</h2><p>${fmt(base.ultimate)}</p></div>
      <div class="summary-block"><h2>Selected Ultimate</h2><p>${fmt(candidate.ultimate)}</p></div>
      <div class="summary-block"><h2>Delta Ultimate</h2><p>${fmt(deltas.ultimate)}</p></div>
      <div class="summary-block"><h2>Base IBNR</h2><p>${fmt(base.ibnr)}</p></div>
      <div class="summary-block"><h2>Selected IBNR</h2><p>${fmt(candidate.ibnr)}</p></div>
      <div class="summary-block"><h2>Delta IBNR</h2><p>${fmt(deltas.ibnr)}</p></div>
      <div class="summary-block"><h2>Delta %</h2><p>${percentText(deltas.ibnr_pct)}</p></div>
      <div class="summary-block"><h2>Attribution</h2><p>${fmt(deltas.factor_selection_ibnr ?? deltas.exclusion_ibnr)}</p><span>factor/exclusion split future if not available</span></div>
      <div class="summary-block"><h2>Scenario</h2><p>${safe(preview.preview_scenario_id)}</p></div>
    </div>
  `;
}

function renderDraftFactor(draft) {
  const previewStatus = appState.selectionSetPreview ? "previewed" : "not previewed";
  const rationaleStatus = draft.rationale?.trim() ? "present" : "missing";
  return `
    <article class="draft-item">
      <div class="title-line">
        <strong>${safe(draft.development_age)}</strong>
        <span class="pill">${safe(factorBasisLabel(draft.selected_basis))}</span>
        <span class="${badgeClass(rationaleStatus === "present" ? "complete" : "pending")}">${safe(rationaleStatus)}</span>
      </div>
      <dl class="metric-list compact">
        <dt>Previous factor</dt><dd>${fmtFactor(draft.previous_factor)}</dd>
        <dt>Selected factor</dt><dd>${fmtFactor(draft.selected_factor)}</dd>
        <dt>Basis</dt><dd>${safe(factorBasisLabel(draft.selected_basis))}</dd>
        <dt>Preview</dt><dd>${safe(previewStatus)}</dd>
      </dl>
      <div class="form-row">
        <label for="draftRationale_${safe(draft.from_dev)}">Rationale</label>
        <textarea id="draftRationale_${safe(draft.from_dev)}" oninput="setDraftFactorRationale('${safe(draft.from_dev)}', this.value)">${safe(draft.rationale || "")}</textarea>
      </div>
    </article>
  `;
}

function commaValues(raw) {
  return String(raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function draftExclusions() {
  const values = appState.selectionDraft.exclusions;
  const exclusions = [];
  for (const value of commaValues(values.origins)) {
    exclusions.push({ type: "origin", value, rationale: values.originRationale || "" });
  }
  for (const value of commaValues(values.valuations)) {
    exclusions.push({ type: "valuation", value, rationale: values.valuationRationale || "" });
  }
  return exclusions;
}

function selectionSetRequest() {
  const userId = $("factorUserId")?.value.trim() || localStorage.getItem("reserveUserId") || "";
  const displayName = $("factorDisplayName")?.value.trim() || localStorage.getItem("reserveDisplayName") || "";
  return {
    factor_selections: draftFactors().map((draft) => ({
      development_age: draft.development_age,
      from_dev: draft.from_dev,
      to_dev: draft.to_dev,
      selected_basis: draft.selected_basis,
      selected_factor: draft.selected_factor,
      rationale: draft.rationale || ""
    })),
    exclusions: draftExclusions(),
    global_rationale: $("selectionGlobalRationale")?.value.trim() || "",
    created_by: { id: userId, display_name: displayName }
  };
}

async function previewSelectionSet() {
  const request = selectionSetRequest();
  if (!request.factor_selections.length && !request.exclusions.length) {
    showToast("Stage at least one factor selection or exclusion.");
    return;
  }
  const run = encodeURIComponent(appState.runId);
  try {
    appState.selectionSetPreview = await api(`/api/runs/${run}/selection-sets/preview`, {
      method: "POST",
      body: JSON.stringify(request)
    });
    localStorage.setItem("reserveUserId", request.created_by.id);
    localStorage.setItem("reserveDisplayName", request.created_by.display_name);
    await refreshRun();
    showToast("Selection scenario previewed.");
  } catch (error) {
    showToast(error.message);
  }
}

function activeSelectionSetApprovalToSupersede() {
  const active = appState.decisions?.active_decisions || [];
  const approvals = active.filter((decision) => decision.decision_type === "selection_set_approval");
  return approvals.length ? approvals[approvals.length - 1].decision_id : null;
}

async function commitSelectionSet() {
  const preview = appState.selectionSetPreview;
  if (!preview) {
    showToast("Preview the selection scenario before committing.");
    return;
  }
  const request = selectionSetRequest();
  const user = request.created_by;
  localStorage.setItem("reserveUserId", user.id);
  localStorage.setItem("reserveDisplayName", user.display_name);
  const run = encodeURIComponent(appState.runId);
  try {
    const committed = await api(`/api/runs/${run}/selection-sets/${encodeURIComponent(preview.selection_set_id)}/commit`, {
      method: "POST",
      body: JSON.stringify({ global_rationale: request.global_rationale, created_by: user })
    });
    const reviewed = Array.from(new Set([...(committed.source_artifacts || []), committed.selection_set_artifact]));
    const decision = {
      schema_version: "0.1",
      decision_id: `selection_set_approval_${Date.now().toString(36)}`,
      run_id: appState.runId,
      task_id: null,
      decision_type: "selection_set_approval",
      status: "accepted",
      selection_set_id: committed.selection_set_id,
      resulting_scenario_id: committed.preview_scenario_id,
      base_run_id: appState.runId,
      rationale: request.global_rationale,
      user,
      source_artifacts_reviewed: reviewed,
      commands_or_parameters_affected: [],
      supersedes_decision_id: activeSelectionSetApprovalToSupersede()
    };
    await api(`/api/runs/${run}/decisions`, {
      method: "POST",
      body: JSON.stringify(decision)
    });
    appState.selectionDraft = { factors: {}, exclusions: { origins: "", originRationale: "", valuations: "", valuationRationale: "" } };
    appState.selectionSetPreview = null;
    showToast("Selection set committed.");
    await refreshRun();
  } catch (error) {
    showToast(error.message);
  }
}

function renderFactorPreviewPanel() {
  const selection = appState.factorSelection;
  if (!selection) {
    return '<div class="summary-panel"><p class="empty">Choose a candidate basis to preview selection impact.</p></div>';
  }
  const preview = appState.factorPreview;
  const comparison = preview?.comparison || {};
  const base = comparison.base || {};
  const candidate = comparison.candidate || {};
  const deltas = comparison.deltas || {};
  return `
    <div class="summary-panel">
      <h2>Impact Preview</h2>
      <div class="section-grid">
        <div class="summary-block"><h2>Development Age</h2><p>${safe(selection.development_age)}</p></div>
        <div class="summary-block"><h2>Previous Factor</h2><p>${fmtFactor(selection.previous_factor)}</p></div>
        <div class="summary-block"><h2>New Factor</h2><p>${fmtFactor(selection.selected_factor_value)}</p></div>
        <div class="summary-block"><h2>Selected Basis</h2><p>${safe(factorBasisLabel(selection.selected_basis))}</p></div>
        <div class="summary-block"><h2>Total IBNR Before</h2><p>${fmt(base.ibnr)}</p></div>
        <div class="summary-block"><h2>Total IBNR After</h2><p>${fmt(candidate.ibnr)}</p></div>
        <div class="summary-block"><h2>Delta IBNR</h2><p>${fmt(deltas.ibnr)}</p></div>
      </div>
      ${renderOriginImpact(preview)}
      <div class="form-grid factor-decision-form">
        <div class="form-row">
          <label for="factorRationale">Rationale / review note</label>
          <textarea id="factorRationale">${safe($("factorRationale")?.value || "")}</textarea>
        </div>
        <div class="form-row">
          <label for="factorUserId">User id</label>
          <input id="factorUserId" value="${safe(localStorage.getItem("reserveUserId") || "")}" />
        </div>
        <div class="form-row">
          <label for="factorDisplayName">Display name</label>
          <input id="factorDisplayName" value="${safe(localStorage.getItem("reserveDisplayName") || "")}" />
        </div>
        <div class="row-actions" style="justify-content: flex-start;">
          <button class="secondary-button" onclick="previewFactorSelection()">Preview</button>
          <button class="primary-button" ${preview ? "" : "disabled"} onclick="commitFactorSelection()">Commit Selection</button>
        </div>
      </div>
    </div>
  `;
}

function renderOriginImpact(preview) {
  const rows = preview?.comparison?.by_origin_ibnr_impact || [];
  if (!rows.length) return "";
  return `
    <h2 style="margin-top: 14px;">Affected Origins</h2>
    <div class="table-wrap" style="margin-top: 8px;">
      <table>
        <thead><tr><th>Origin</th><th>Base IBNR</th><th>Selected IBNR</th><th>Delta IBNR</th><th>Delta %</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${safe(row.origin)}</td>
              <td>${fmt(row.base_ibnr)}</td>
              <td>${fmt(row.candidate_ibnr)}</td>
              <td>${fmt(row.delta_ibnr)}</td>
              <td>${percentText(row.delta_ibnr_pct)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function previewFactorSelection() {
  const selection = appState.factorSelection;
  if (!selection) return;
  const note = $("factorRationale")?.value.trim() || "";
  const run = encodeURIComponent(appState.runId);
  try {
    appState.factorPreview = await api(`/api/runs/${run}/factor-preview`, {
      method: "POST",
      body: JSON.stringify({
        development_age: selection.development_age,
        selected_basis: selection.selected_basis,
        selected_factor_value: selection.selected_factor_value,
        user_note: note
      })
    });
    await refreshRun();
    showToast("Preview generated.");
  } catch (error) {
    showToast(error.message);
  }
}

function activeFactorSelectionToSupersede(developmentAge) {
  const active = appState.decisions?.active_decisions || [];
  const matches = active.filter((decision) => (
    decision.decision_type === "factor_selection" &&
    String(decision.development_age) === String(developmentAge)
  ));
  return matches.length ? matches[matches.length - 1].decision_id : null;
}

async function commitFactorSelection() {
  const selection = appState.factorSelection;
  const preview = appState.factorPreview;
  if (!selection || !preview) {
    showToast("Preview the selection before committing.");
    return;
  }
  const userId = $("factorUserId").value.trim();
  const displayName = $("factorDisplayName").value.trim();
  const rationale = $("factorRationale").value.trim();
  localStorage.setItem("reserveUserId", userId);
  localStorage.setItem("reserveDisplayName", displayName);
  const reviewed = Array.from(new Set([...(preview.source_artifacts || []), preview.preview_artifact]));
  const decision = {
    schema_version: "0.1",
    decision_id: `factor_selection_${Date.now().toString(36)}`,
    run_id: appState.runId,
    task_id: null,
    decision_type: "factor_selection",
    status: "accepted",
    development_age: selection.development_age,
    previous_factor: selection.previous_factor,
    selected_factor: selection.selected_factor_value,
    selected_basis: selection.selected_basis,
    rationale,
    user: { id: userId, display_name: displayName },
    source_artifacts_reviewed: reviewed,
    commands_or_parameters_affected: [],
    resulting_scenario_id: preview.scenario_id,
    supersedes_decision_id: activeFactorSelectionToSupersede(selection.development_age)
  };
  const run = encodeURIComponent(appState.runId);
  try {
    await api(`/api/runs/${run}/decisions`, {
      method: "POST",
      body: JSON.stringify(decision)
    });
    showToast("Factor selection committed.");
    appState.factorSelection = null;
    appState.factorPreview = null;
    await refreshRun();
  } catch (error) {
    showToast(error.message);
  }
}

function renderProjection() {
  const payload = appState.chainLadderProjection;
  if (!payload?.available) {
    $("projectionTab").innerHTML = '<p class="empty">No projection output is available for this run.</p>';
    return;
  }
  const rows = payload.projection || [];
  $("projectionTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Projection</p>
        <h2>By-Origin Projection</h2>
        <p class="muted">${safe(payload.display_method)}. Read-only values from fit.json and comparison artifacts.</p>
      </div>
      <span class="chip">${safe(payload.selected_scenario_id || "no selected scenario")}</span>
    </div>
    <div class="panel">
      <div class="panel-header">
        <h2>By-origin IBNR impact</h2>
        <span class="chip">backend comparison artifacts</span>
      </div>
      ${renderProjectionImpactChart(rows)}
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Origin</th>
            <th>Base Latest</th>
            <th>Base Ultimate</th>
            <th>Base IBNR</th>
            <th>Selected IBNR</th>
            <th>Delta IBNR</th>
            <th>Delta %</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${safe(row.origin)}</td>
              <td>${fmt(row.latest)}</td>
              <td>${fmt(row.ultimate)}</td>
              <td>${fmt(row.ibnr)}</td>
              <td>${fmt(row.selected_ibnr)}</td>
              <td>${fmt(row.delta_ibnr)}</td>
              <td>${percentText(row.delta_ibnr_pct)}</td>
            </tr>
          `).join("") || '<tr><td colspan="7">not available</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderProjectionImpactChart(rows) {
  const hasImpact = rows.some((row) => row.delta_ibnr !== null && row.delta_ibnr !== undefined);
  if (!hasImpact) return '<p class="empty">Selected scenario impact is not available.</p>';
  return `
    <div class="bar-list">
      ${rows.map((row) => `
        <div class="bar-row">
          <span>${safe(row.origin)}</span>
          <div class="bar-track"><div class="bar-fill impact" style="width:${barWidth(row.ibnr_chart_pct)}"></div></div>
          <strong>${fmt(row.delta_ibnr)}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function prepareScenarioDecision() {
  const scenarioTask = (appState.tasks?.tasks || []).find((task) => task.task_type === "scenario_selection");
  if (!scenarioTask) {
    showToast("No scenario_selection task is available.");
    return;
  }
  appState.selectedTask = scenarioTask;
  renderValidationPanel();
}

function renderDecisionsTab() {
  const taskRows = appState.tasks?.tasks || [];
  const pending = taskRows.filter((task) => task.status === "pending");
  const completed = taskRows.filter((task) => task.status !== "pending");
  const journal = appState.decisionJournal || {};
  $("decisionsTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Decision journal</p>
        <h2>Human Review Queue</h2>
        <p class="muted">Tasks are workflow prompts. Committed decisions are immutable artifacts.</p>
      </div>
      <button class="secondary-button" onclick="refreshTasks()">Refresh Tasks</button>
    </div>
    <div class="dashboard-grid guided-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>Pending Reviews</h2>
          <span class="chip">${pending.length}</span>
        </div>
        ${pending.map(renderTaskRow).join("") || '<p class="empty">No pending tasks.</p>'}
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2>Completed Reviews</h2>
          <span class="chip">${completed.length}</span>
        </div>
        ${completed.map(renderTaskRow).join("") || '<p class="empty">No completed tasks.</p>'}
      </div>
    </div>
    <div class="panel decision-journal-panel">
      <div class="panel-header">
        <h2>Active Decisions</h2>
        <span class="chip">${journal.active_decisions?.length || 0}</span>
      </div>
      ${renderJournalEntries(journal.active_decisions || [])}
    </div>
    <div class="panel decision-journal-panel">
      <div class="panel-header">
        <h2>Superseded Decisions</h2>
        <span class="chip">${journal.superseded_decisions?.length || 0}</span>
      </div>
      ${renderJournalEntries(journal.superseded_decisions || [])}
    </div>
  `;
}

function renderJournalEntries(entries) {
  if (!entries.length) return '<p class="empty">No decisions in this state.</p>';
  return `
    <div class="journal-grid">
      ${entries.map((decision) => `
        <article class="journal-card">
          <div class="title-line">
            <h3>${safe(decision.decision_id)}</h3>
            <span class="pill">${safe(decision.decision_type)}</span>
            <span class="${badgeClass(decision.active ? "active" : "superseded")}">${decision.active ? "active" : "superseded"}</span>
          </div>
          <dl class="metric-list compact">
            <dt>User</dt><dd>${safe(decision.display_name || decision.user_id || "n/a")}</dd>
            <dt>Timestamp</dt><dd>${safe(decision.timestamp_utc || "n/a")}</dd>
            <dt>Scenario</dt><dd>${safe(decision.scenario_id || "n/a")}</dd>
            <dt>Selection set</dt><dd>${safe(decision.selection_set_id || "n/a")}</dd>
            <dt>Supersedes</dt><dd>${safe(decision.supersedes_decision_id || "n/a")}</dd>
            <dt>Superseded by</dt><dd>${safe(decision.superseded_by_decision_id || "n/a")}</dd>
          </dl>
          <p>${safe(decision.rationale || "No rationale captured.")}</p>
          <p class="evidence">${(decision.source_artifacts_reviewed || []).map(safe).join(", ") || "no reviewed artifacts"}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderReportTab() {
  const payload = appState.reportReadiness;
  if (!payload) {
    $("reportTab").innerHTML = '<p class="empty">No report readiness payload is available.</p>';
    return;
  }
  const blockers = payload.blockers || [];
  $("reportTab").innerHTML = `
    <div class="page-heading">
      <div>
        <p class="eyebrow">Report readiness</p>
        <h2>${safe(payload.status)}</h2>
        <p class="muted">The final review pack only uses committed governed decisions.</p>
      </div>
      <span class="${badgeClass(payload.status)}">${safe(payload.status)}</span>
    </div>
    <div class="dashboard-grid guided-grid">
      <div class="panel">
        <div class="panel-header">
          <h2>Approval Gate</h2>
          <span class="${badgeClass(payload.require_approval_would_pass ? "pass" : "blocked")}">${payload.require_approval_would_pass ? "pass" : "blocked"}</span>
        </div>
        <dl class="metric-list">
          <dt>Command</dt><dd><code>${safe(payload.report_command || "")}</code></dd>
          <dt>Would pass</dt><dd>${payload.require_approval_would_pass ? "yes" : "no"}</dd>
          <dt>Failure</dt><dd>${safe(payload.require_approval_failure || "n/a")}</dd>
          <dt>Selected scenario</dt><dd>${safe(payload.selected_scenario_id || "none")}</dd>
          <dt>Selection set</dt><dd>${safe(payload.selection_set_id || "none")}</dd>
          <dt>Report approval</dt><dd>${safe(payload.report_approval_decision_id || "none")}</dd>
        </dl>
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2>Blockers</h2>
          <span class="chip">${blockers.length}</span>
        </div>
        ${renderBlockerSummary(blockers)}
      </div>
      <div class="panel wide-panel">
        <div class="panel-header">
          <h2>Readiness Checklist</h2>
          <span class="chip">backend status</span>
        </div>
        ${renderGovernanceChecklist()}
      </div>
    </div>
  `;
}

function renderArtifacts() {
  const artifactButtons = artifactNames
    .map((name) => {
      const exists = Boolean(appState.artifacts[name]);
      return `<button class="${appState.artifactName === name ? "primary-button" : "secondary-button"}" ${exists ? "" : "disabled"} onclick="selectArtifact('${safe(name)}')">${safe(name)}</button>`;
    })
    .join("");
  const payload = appState.artifacts[appState.artifactName];
  $("artifactsTab").innerHTML = `
    <div class="row-actions" style="justify-content: flex-start; margin-bottom: 12px;">${artifactButtons}</div>
    <pre class="json-viewer">${payload ? safe(JSON.stringify(payload, null, 2)) : "Artifact not available."}</pre>
  `;
}

function selectArtifact(name) {
  appState.artifactName = name;
  renderArtifacts();
}

function renderChainLadderReviewContext() {
  const summary = appState.chainLadderSummary;
  if (!summary?.is_chain_ladder) return "";
  const totals = summary.totals || {};
  return `
    <div class="review-context">
      <h3>Chain Ladder Summary</h3>
      <dl class="metric-list">
        <dt>Method</dt><dd>${safe(summary.display_method)}</dd>
        <dt>Input</dt><dd>${safe(summary.input_file || "n/a")}</dd>
        <dt>Latest</dt><dd>${fmt(totals.latest)}</dd>
        <dt>Ultimate</dt><dd>${fmt(totals.ultimate)}</dd>
        <dt>IBNR</dt><dd>${fmt(totals.ibnr)}</dd>
        <dt>Selected scenario</dt><dd>${safe(summary.selected_scenario_id || "none")}</dd>
      </dl>
    </div>
  `;
}

function renderReportReadiness() {
  const payload = appState.reportReadiness;
  if (!payload) {
    $("reportReadinessPanel").innerHTML = `
      <h2>Report Readiness</h2>
      <p class="empty">No run selected.</p>
    `;
    return;
  }
  const blockers = payload.blockers || [];
  const command = payload.report_command || `reserve report ${appState.runId || "<run-id>"} --format-out html --require-approval --out runs`;
  $("reportReadinessPanel").innerHTML = `
    <div class="readiness-drawer-head">
      <div>
        <p class="eyebrow">Report readiness</p>
        <h2>${safe(payload.status)}</h2>
      </div>
      <span class="${badgeClass(payload.status)}">${safe(payload.status)}</span>
    </div>
    <p class="drawer-summary">${blockers.length} blocker${blockers.length === 1 ? "" : "s"} | require-approval ${payload.require_approval_would_pass ? "would pass" : "blocked"}</p>
    ${renderBlockerSummary(blockers)}
    <div class="next-action-mini">
      <strong>${safe(payload.next_action?.label || "No next action")}</strong>
      <span>${safe(payload.next_action?.detail || "")}</span>
    </div>
    <div class="readiness-command">
      <span>Guarded command</span>
      <code>${safe(command)}</code>
    </div>
  `;
}

function renderBlockerSummary(blockers) {
  if (!blockers.length) return '<p class="empty">No blockers.</p>';
  return `
    <div class="blocker-summary">
      <h3>${blockers.length} blocker${blockers.length === 1 ? "" : "s"}</h3>
      <ul class="clean-list">
        ${blockers.map((blocker) => `<li class="${safe(blocker.severity)}">${safe(blocker.label)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderValidationPanel() {
  const task = appState.selectedTask;
  if (!task) {
    if (appState.selectedTriangleCell) {
      $("validationPanel").innerHTML = `
        <h2>Triangle Cell</h2>
        ${renderTriangleCellDetail()}
      `;
      return;
    }
    $("validationPanel").innerHTML = `
      <h2>Guided Action</h2>
      ${renderNextActionCard()}
    `;
    return;
  }
  const allowed = task.allowed_decision_types || [];
  const decisionTypeOptions = allowed
    .map((type) => `<option value="${safe(type)}">${safe(type)}</option>`)
    .join("");
  const sourceArtifacts = Array.from(
    new Set([
      ...(task.source_artifacts || []),
      ...(task.task_type === "scenario_selection" ? ["scenario_index.json"] : [])
    ])
  );
  const previewStatus = appState.selectionSetPreview?.status || appState.factorPreview?.status || "no active preview";
  const scenarioRow = allowed.includes("scenario_selection")
    ? `
        <div class="form-row">
          <label for="scenarioId">Resulting scenario id</label>
          <input id="scenarioId" value="${safe(appState.selectedScenarioId || "")}" placeholder="required for scenario_selection" />
        </div>
      `
    : "";
  $("validationPanel").innerHTML = `
    <h2>Human Validation</h2>
    <div class="form-section">
      <h3>${safe(task.title)}</h3>
      <p>${safe(task.description)}</p>
      <dl class="metric-list compact">
        <dt>Decision type</dt><dd>${allowed.map(safe).join(", ") || "n/a"}</dd>
        <dt>Preview status</dt><dd>${safe(previewStatus)}</dd>
        <dt>Task status</dt><dd>${safe(task.status)}</dd>
      </dl>
      <div class="evidence">Reviewed artifacts: ${sourceArtifacts.map(safe).join(", ") || "none"}</div>
      <p class="required-note">A rationale is required for governed acknowledgements and selections. The commit button writes a decision artifact through backend validation.</p>
      ${task.task_type === "bcl_review" ? renderChainLadderReviewContext() : ""}
      <form id="decisionForm" class="form-grid">
        <div class="form-row">
          <label for="decisionType">Decision type</label>
          <select id="decisionType">${decisionTypeOptions}</select>
        </div>
        <div class="form-row">
          <label for="decisionStatus">Status</label>
          <select id="decisionStatus">
            <option value="accepted">accepted</option>
            <option value="modified">modified</option>
            <option value="rejected">rejected</option>
          </select>
        </div>
        ${scenarioRow}
        <div class="form-row">
          <label for="rationale">Rationale / review note</label>
          <textarea id="rationale"></textarea>
        </div>
        <div class="form-row">
          <label for="userId">User id</label>
          <input id="userId" value="${safe(localStorage.getItem("reserveUserId") || "")}" />
        </div>
        <div class="form-row">
          <label for="displayName">Display name</label>
          <input id="displayName" value="${safe(localStorage.getItem("reserveDisplayName") || "")}" />
        </div>
        <button class="primary-button" type="submit">Commit Decision</button>
      </form>
    </div>
  `;
  $("decisionForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await commitDecision(task, sourceArtifacts);
  });
}

async function commitDecision(task, sourceArtifacts) {
  const decisionType = $("decisionType").value;
  const userId = $("userId").value.trim();
  const displayName = $("displayName").value.trim();
  localStorage.setItem("reserveUserId", userId);
  localStorage.setItem("reserveDisplayName", displayName);
  const decision = {
    schema_version: "0.1",
    decision_id: `${decisionType}_${Date.now().toString(36)}`,
    run_id: appState.runId,
    task_id: task.task_id,
    decision_type: decisionType,
    status: $("decisionStatus").value,
    rationale: $("rationale").value.trim(),
    user: { id: userId, display_name: displayName },
    source_artifacts_reviewed: sourceArtifacts,
    commands_or_parameters_affected: [],
    resulting_scenario_id: decisionType === "scenario_selection" ? $("scenarioId")?.value.trim() || null : null,
    supersedes_decision_id: null
  };
  const run = encodeURIComponent(appState.runId);
  try {
    await api(`/api/runs/${run}/decisions`, {
      method: "POST",
      body: JSON.stringify(decision)
    });
    showToast("Decision committed.");
    appState.selectedTask = null;
    await refreshRun();
  } catch (error) {
    showToast(error.message);
  }
}

function renderDecisions() {
  const active = appState.decisions?.active_decisions || [];
  const superseded = appState.decisions?.superseded_decisions || [];
  const rows = [...active, ...superseded];
  $("decisionList").innerHTML =
    rows
      .map((decision) => {
        const isSuperseded = superseded.some((item) => item.decision_id === decision.decision_id);
        return `
          <article class="decision-row">
            <div class="title-line">
              <strong>${safe(decision.decision_id)}</strong>
              <span class="pill">${safe(decision.decision_type)}</span>
              <span class="${badgeClass(isSuperseded ? "superseded" : "active")}">${isSuperseded ? "superseded" : "active"}</span>
            </div>
            <p>${safe(decision.status)} ${decision.resulting_scenario_id ? `| ${safe(decision.resulting_scenario_id)}` : ""}</p>
            <p class="evidence">${(decision.source_artifacts_reviewed || []).map(safe).join(", ") || "no reviewed artifacts"}</p>
          </article>
        `;
      })
      .join("") || '<p class="empty">No decisions committed.</p>';
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    appState.activeTab = tab.dataset.tab;
    render();
  });
});

$("runSelect").addEventListener("change", (event) => openRun(event.target.value));
$("refreshRun").addEventListener("click", refreshRun);

loadRuns().catch((error) => showToast(error.message));
