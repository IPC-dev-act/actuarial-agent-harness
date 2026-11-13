const artifactNames = [
  "manifest.json",
  "validation.json",
  "fit.json",
  "triangle.json",
  "diagnostics.json",
  "sensitivity.json",
  "validation_tasks.json",
  "scenario_index.json",
  "factor_analysis.json",
  "factor_review_suggestions.json"
];

const FACTOR_BASES = [
  "fitted",
  "volume_weighted",
  "simple_average",
  "last_3",
  "last_5",
  "trimmed_mean",
  "median"
];

function emptySelectionDraft() {
  return {
    factors: {},
    exclusions: { origins: "", originRationale: "", valuations: "", valuationRationale: "", points: [] },
    tail: null
  };
}

function persistedRailState(key) {
  const value = localStorage.getItem(key);
  return value === null ? true : value === "true";
}

const state = {
  runs: [],
  runId: null,
  status: null,
  tasks: null,
  decisions: null,
  decisionJournal: null,
  scenarios: null,
  comparison: null,
  exploreScenarios: null,
  exploreComparison: null,
  summary: null,
  factors: null,
  factorDetail: null,
  factorAnalysis: null,
  factorSuggestions: null,
  factorScale: "linear",
  factorCurveSeries: ["fitted"],
  factorCurveMode: "raw",
  dragOverrides: {},
  workbenchDisclosures: { governance: false, curveOptions: true, perAge: true, fittings: false, manual: false, selection: false, review: false, allFactors: false, tail: false },
  suggestionDispositions: {},
  projection: null,
  triangle: null,
  readiness: null,
  artifacts: {},
  activeTab: "overview",
  triangleMode: "cumulative",
  triangleHeatmap: false,
  selectedTriangleCell: null,
  selectedDevelopmentAge: null,
  selectedFactorPoint: null,
  factorPointPanelOpen: false,
  selectedScenarioId: null,
  selectedTask: null,
  selectionDraft: emptySelectionDraft(),
  selectionSetPreview: null,
  livePreview: null,
  livePreviewPending: false,
  livePreviewTimer: null,
  livePreviewRequestId: 0,
  commitMeta: { globalRationale: "", userId: "", displayName: "" },
  artifactName: "manifest.json",
  workflowMode: "governed",
  selectedExploreScenarioId: null,
  explorePreview: null,
  exploreMeta: { name: "Exploratory scenario", notes: "" },
  collapsedRails: {
    left: persistedRailState("reserveLeftRailCollapsed"),
    right: persistedRailState("reserveRightRailCollapsed")
  }
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`;
    const raw = await response.text();
    let detail = raw || fallback;
    try {
      const body = JSON.parse(raw);
      detail = body?.detail || fallback;
    } catch {
      // A plain-text response can still provide useful error details.
    }
    throw new Error(detail);
  }
  return response.json();
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmt(value) {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return String(value);
}

function fmtFactor(value) {
  if (value === null || value === undefined) return "not available";
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 });
  }
  return String(value);
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
  const normalized = String(status || "pending").toLowerCase().replaceAll(" ", "_");
  return `pill status-${safe(normalized)}`;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2800);
}

function applyRailState() {
  const shell = document.querySelector(".v2-shell");
  const mobile = window.matchMedia("(max-width: 760px)").matches;
  if (!shell) return;
  shell.classList.toggle("left-collapsed", state.collapsedRails.left && !mobile);
  shell.classList.toggle("right-collapsed", state.collapsedRails.right && !mobile);

  const left = $("toggleLeftRail");
  const right = $("toggleRightRail");
  if (left) {
    const collapsed = state.collapsedRails.left && !mobile;
    left.hidden = mobile;
    left.setAttribute("aria-expanded", String(!collapsed));
    left.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} navigation panel`);
    left.title = `${collapsed ? "Expand" : "Collapse"} navigation panel`;
    left.textContent = collapsed ? ">" : "<";
  }
  if (right) {
    const collapsed = state.collapsedRails.right && !mobile;
    right.hidden = mobile;
    right.setAttribute("aria-expanded", String(!collapsed));
    right.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} human validation panel`);
    right.title = `${collapsed ? "Expand" : "Collapse"} human validation panel`;
    right.textContent = collapsed ? "<" : ">";
  }
}

function toggleRail(side) {
  state.collapsedRails[side] = !state.collapsedRails[side];
  localStorage.setItem(`reserve${side === "left" ? "Left" : "Right"}RailCollapsed`, String(state.collapsedRails[side]));
  applyRailState();
}

function commaValues(raw) {
  return String(raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function addCommaValue(raw, value) {
  const values = commaValues(raw);
  if (!values.includes(String(value))) values.push(String(value));
  return values.join(", ");
}

function removeCommaValue(raw, value) {
  return commaValues(raw).filter((item) => item !== String(value)).join(", ");
}

function methodLabel() {
  return state.summary?.display_method || state.artifacts["fit.json"]?.method || "No method";
}

function totals() {
  return state.summary?.totals || state.artifacts["fit.json"]?.totals || {};
}

function pendingTasks() {
  return (state.tasks?.tasks || []).filter((task) => task.status === "pending");
}

function activeDecisions() {
  return state.decisions?.active_decisions || state.decisionJournal?.active_decisions || [];
}

function activeDecisionOfType(decisionType) {
  return activeDecisions().find(
    (decision) => decision.decision_type === decisionType && ["accepted", "modified"].includes(decision.status)
  ) || null;
}

function scenarios() {
  return state.scenarios?.scenarios || [];
}

function exploreScenarios() {
  return state.exploreScenarios?.scenarios || [];
}

function draftFactors() {
  return Object.values(state.selectionDraft.factors || {});
}

function draftForRow(row) {
  return state.selectionDraft.factors[String(row.from_dev)];
}

function factorBasisLabel(basis) {
  const labels = {
    fitted: "Fitted",
    volume_weighted: "Volume weighted",
    simple_average: "Simple average",
    last_3: "Last 3",
    last_5: "Last 5",
    trimmed_mean: "Trimmed mean",
    median: "Median",
    log_linear_smoothing: "Log-linear smoothing",
    manual_override: "Manual override"
  };
  return labels[basis] || String(basis || "not available");
}

function stagedChangeCount() {
  const exclusions = state.selectionDraft.exclusions || {};
  return (
    draftFactors().length +
    commaValues(exclusions.origins).length +
    commaValues(exclusions.valuations).length +
    factorPointDrafts().length +
    (state.selectionDraft.tail ? 1 : 0)
  );
}

function selectionWorkflowState() {
  if (state.workflowMode === "explore" && state.explorePreview) {
    return {
      key: "not_governed",
      label: "Explore preview",
      detail: `Scenario ${state.explorePreview.explore_scenario_id || "explore"} is not governed.`
    };
  }
  const committedId = state.readiness?.selection_set_id;
  if (state.selectionSetPreview) {
    return {
      key: "previewed",
      label: "Preview available",
      detail: `Scenario ${state.selectionSetPreview.preview_scenario_id || "preview"} is ready for governed commit.`
    };
  }
  const staged = stagedChangeCount();
  if (staged) {
    return {
      key: "staged",
      label: "Staged, not previewed",
      detail: `${staged} staged change${staged === 1 ? "" : "s"} require preview before commit.`
    };
  }
  if (committedId) {
    return {
      key: "committed",
      label: "Committed selection set",
      detail: `${committedId} is the latest committed selection set.`
    };
  }
  return { key: "none", label: "No change staged", detail: "Base deterministic factors are displayed." };
}

function commitBlockers() {
  const blockers = [];
  if (!state.selectionSetPreview) blockers.push("preview missing");
  if (!String(state.commitMeta.globalRationale || "").trim()) blockers.push("global rationale missing");
  if (!factorsHaveRationale()) blockers.push("factor rationale missing");
  if (!exclusionsHaveRationale()) blockers.push("exclusion rationale missing");
  if (!tailHasRationale()) blockers.push("tail rationale missing");
  if (!String(state.commitMeta.userId || "").trim() || !String(state.commitMeta.displayName || "").trim()) {
    blockers.push("user identity missing");
  }
  return blockers;
}

function modeLabel() {
  return state.workflowMode === "explore" ? "EXPLORE" : "GOVERNED";
}

function ModeSwitch() {
  return `
    <div class="mode-switch" role="group" aria-label="Workflow mode">
      <button class="${state.workflowMode === "explore" ? "active" : ""}" onclick="setWorkflowMode('explore')">EXPLORE</button>
      <button class="${state.workflowMode === "governed" ? "active" : ""}" onclick="setWorkflowMode('governed')">GOVERNED</button>
    </div>
  `;
}

function setWorkflowMode(mode) {
  state.workflowMode = mode === "explore" ? "explore" : "governed";
  state.selectionSetPreview = null;
  state.explorePreview = null;
  clearLivePreview();
  render();
}

function clearLivePreview() {
  state.livePreviewRequestId += 1;
  window.clearTimeout(state.livePreviewTimer);
  state.livePreviewTimer = null;
  state.livePreview = null;
  state.livePreviewPending = false;
}

function scheduleLivePreview() {
  clearLivePreview();
  if (!state.runId || !stagedChangeCount()) return;
  state.livePreviewPending = true;
  const requestId = ++state.livePreviewRequestId;
  state.livePreviewTimer = window.setTimeout(() => runLivePreview(requestId), 180);
}

async function runLivePreview(requestId) {
  if (!state.runId || requestId !== state.livePreviewRequestId || !stagedChangeCount()) return;
  const run = encodeURIComponent(state.runId);
  try {
    const preview = await api(`/api/runs/${run}/selection-sets/live-preview`, {
      method: "POST",
      body: JSON.stringify(selectionSetRequest({}, ""))
    });
    if (requestId !== state.livePreviewRequestId) return;
    state.livePreview = preview;
    state.livePreviewPending = false;
    render();
  } catch (error) {
    if (requestId !== state.livePreviewRequestId) return;
    state.livePreviewPending = false;
    render();
    showToast(`Live calculation unavailable: ${error.message}`);
  }
}

function ModeBanner() {
  const explore = state.workflowMode === "explore";
  return `
    <details class="mode-banner ${explore ? "explore-mode" : "governed-mode"}" ${state.workbenchDisclosures.governance ? "open" : ""} ontoggle="setWorkbenchDisclosure('governance', this.open)">
      <summary>
        <span>${explore ? "Explore mode" : "Governed mode"}</span>
        <small>${explore ? "not report-ready" : "approval controls collapsed"}</small>
      </summary>
      <div>
        <p class="section-label">${explore ? "EXPLORE" : "GOVERNED"}</p>
        <h3>${explore ? "Free scenario testing. Not governed. Not report-ready." : "Committed assumptions require rationale and enter the audit trail."}</h3>
      </div>
      <span class="${badgeClass(explore ? "not_governed" : "governed")}">${explore ? "NOT GOVERNED" : "GOVERNED"}</span>
    </details>
  `;
}

function selectedFactorRow(rows) {
  if (!rows.length) return null;
  if (state.selectedDevelopmentAge !== null && state.selectedDevelopmentAge !== undefined) {
    const selected = rows.find((row) => String(row.from_dev) === String(state.selectedDevelopmentAge));
    if (selected) return selected;
  }
  return rows[0];
}

async function loadRuns() {
  const payload = await api("/api/runs");
  state.runs = payload.runs || [];
  $("runSelect").innerHTML = state.runs
    .map((run) => `<option value="${safe(run.run_id)}">${safe(run.run_id)}</option>`)
    .join("");
  if (!state.runId && state.runs.length) {
    state.runId = state.runs[state.runs.length - 1].run_id;
  }
  if (state.runId) {
    $("runSelect").value = state.runId;
    await openRun(state.runId);
  } else {
    render();
  }
}

async function openRun(runId) {
  clearLivePreview();
  state.runId = runId;
  state.selectedTask = null;
  state.selectedTriangleCell = null;
  state.selectedFactorPoint = null;
  state.factorPointPanelOpen = false;
  state.selectedDevelopmentAge = null;
  state.factorDetail = null;
  state.factorAnalysis = null;
  state.factorSuggestions = null;
  state.factorScale = "linear";
  state.factorCurveSeries = ["fitted"];
  state.factorCurveMode = "raw";
  state.dragOverrides = {};
  state.workbenchDisclosures = { governance: false, curveOptions: true, perAge: true, fittings: false, manual: false, selection: false, review: false, allFactors: false, tail: false };
  state.suggestionDispositions = {};
  state.selectedScenarioId = null;
  state.selectedExploreScenarioId = null;
  state.comparison = null;
  state.exploreComparison = null;
  state.explorePreview = null;
  state.selectionSetPreview = null;
  state.selectionDraft = emptySelectionDraft();
  state.commitMeta = {
    globalRationale: "",
    userId: localStorage.getItem("reserveUserId") || "",
    displayName: localStorage.getItem("reserveDisplayName") || ""
  };
  state.exploreMeta = { name: "Exploratory scenario", notes: "" };
  await refreshRun();
}

async function refreshRun() {
  if (!state.runId) return;
  const run = encodeURIComponent(state.runId);
  const [
    status,
    tasks,
    decisions,
    decisionJournal,
    scenariosPayload,
    explorePayload,
    summary,
    factors,
    projection,
    triangle,
    readiness,
    factorAnalysis,
    factorSuggestions
  ] = await Promise.all([
    api(`/api/runs/${run}/status`),
    api(`/api/runs/${run}/tasks`),
    api(`/api/runs/${run}/decisions`),
    api(`/api/runs/${run}/decision-journal`),
    api(`/api/runs/${run}/scenarios`),
    api(`/api/runs/${run}/explore`),
    api(`/api/runs/${run}/chain-ladder/summary`),
    api(`/api/runs/${run}/chain-ladder/factors`),
    api(`/api/runs/${run}/chain-ladder/projection`),
    api(`/api/runs/${run}/chain-ladder/triangle`),
    api(`/api/runs/${run}/report-readiness`),
    api(`/api/runs/${run}/factor-analysis`),
    api(`/api/runs/${run}/factor-review-suggestions`)
  ]);
  state.status = status;
  state.tasks = tasks;
  state.decisions = decisions;
  state.decisionJournal = decisionJournal;
  state.scenarios = scenariosPayload;
  state.exploreScenarios = explorePayload;
  state.summary = summary;
  state.factors = factors;
  state.projection = projection;
  state.triangle = triangle;
  state.readiness = readiness;
  state.factorAnalysis = factorAnalysis;
  state.factorSuggestions = factorSuggestions;
  const factorRows = factors?.factors || [];
  if (!state.selectedDevelopmentAge && factorRows.length) {
    state.selectedDevelopmentAge = String(factorRows[0].from_dev);
  }
  if (state.selectedDevelopmentAge) {
    await loadFactorDetail(state.selectedDevelopmentAge, false);
  }
  await loadArtifacts();
  render();
}

async function loadFactorDetail(fromDev, renderAfter = true) {
  if (!state.runId || fromDev === null || fromDev === undefined) return;
  const run = encodeURIComponent(state.runId);
  state.factorDetail = await api(`/api/runs/${run}/chain-ladder/factors/${encodeURIComponent(fromDev)}`);
  if (renderAfter) render();
}

async function refreshTasks() {
  if (!state.runId) return;
  const run = encodeURIComponent(state.runId);
  state.tasks = await api(`/api/runs/${run}/tasks/refresh`, { method: "POST" });
  state.status = await api(`/api/runs/${run}/status`);
  render();
}

async function loadArtifacts() {
  state.artifacts = {};
  const run = encodeURIComponent(state.runId);
  await Promise.all(
    artifactNames.map(async (name) => {
      try {
        state.artifacts[name] = await api(`/api/runs/${run}/artifacts/${encodeURIComponent(name)}`);
      } catch (_error) {
        state.artifacts[name] = null;
      }
    })
  );
}

function setTab(tabName) {
  const normalizedTab = tabName === "factors" ? "triangles" : tabName;
  state.activeTab = normalizedTab;
  document.querySelectorAll(".v2-tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === normalizedTab);
  });
  document.querySelectorAll(".v2-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${normalizedTab}Panel`);
  });
}

function selectTask(taskId) {
  state.selectedTask = (state.tasks?.tasks || []).find((task) => task.task_id === taskId) || null;
  state.activeTab = "decisions";
  render();
}

async function selectScenario(scenarioId) {
  state.selectedScenarioId = scenarioId;
  const run = encodeURIComponent(state.runId);
  state.comparison = await api(`/api/runs/${run}/compare?scenario_id=${encodeURIComponent(scenarioId)}`);
  const scenarioTask = pendingTasks().find((task) => task.task_type === "scenario_selection");
  if (scenarioTask) state.selectedTask = scenarioTask;
  await loadArtifacts();
  render();
}

function render() {
  renderChrome();
  renderOverview();
  renderTriangles();
  renderScenarios();
  renderDecisions();
  renderReport();
  renderArtifacts();
  renderValidationDrawer();
  setTab(state.activeTab);
}

function LeftRail() {
  const readiness = state.readiness?.status || state.status?.status || "no run";
  const selectedScenario = state.summary?.selected_scenario_id || state.readiness?.selected_scenario_id || "none";
  return `
    <div class="rail-metrics">
      <div><span>Status</span><strong>${safe(state.status?.status || "n/a")}</strong></div>
      <div><span>Unresolved tasks</span><strong>${fmt(pendingTasks().length)}</strong></div>
      <div><span>Active decisions</span><strong>${fmt(state.decisions?.active_decision_count || activeDecisions().length)}</strong></div>
      <div><span>Scenarios</span><strong>${fmt(scenarios().length)}</strong></div>
      <div><span>Selected scenario</span><strong>${safe(selectedScenario)}</strong></div>
      <div><span>Report readiness</span><strong>${safe(readiness)}</strong></div>
    </div>
  `;
}

function CommandStrip() {
  const input = state.summary?.input_file || state.artifacts["manifest.json"]?.inputs?.[0]?.path || "No input";
  return [
    ["Method", methodLabel(), ""],
    ["Input", input, "wide"],
    ["Status", state.status?.status || "n/a", "chip"],
    ["Report gate", state.readiness?.status || "n/a", "chip"]
  ]
    .map(([label, value, extra]) => `
      <div class="command-cell ${safe(extra)}">
        <span>${safe(label)}</span>
        ${
          String(extra).includes("chip")
            ? `<strong class="${badgeClass(value)} command-chip">${safe(value)}</strong>`
            : `<strong>${safe(value)}</strong>`
        }
      </div>
    `)
    .join("");
}

function MetricStrip() {
  const currentTotals = totals();
  const preview = state.selectionSetPreview || state.livePreview;
  const selected = preview?.comparison?.candidate || state.summary?.selected_scenario?.comparison?.candidate || {};
  const deltas = preview?.comparison?.deltas || state.comparison?.deltas || {};
  const selectedIbnr = selected.ibnr ?? state.summary?.selected_scenario?.key_metrics?.ibnr;
  const staged = stagedChangeCount() > 0 && !state.selectionSetPreview && !state.livePreview;
  const recalculating = state.livePreviewPending && stagedChangeCount() > 0;
  const live = Boolean(state.livePreview && !state.selectionSetPreview);
  const selectedText = recalculating ? '<span class="metric-recalculating">Recalculating</span>' : fmt(selectedIbnr);
  const deltaText = recalculating ? '<span class="metric-recalculating">Updating</span>' : fmt(deltas.ibnr);
  const exploreAction = state.workflowMode === "explore" && state.runId
    ? `<div class="metric metric-handoff-action"><button id="approveExploreButton" type="button" onclick="approveExploreAndContinue()"><span>Approve all</span><strong>Continue to report →</strong></button></div>`
    : "";
  return `
    <div class="metric-strip ${exploreAction ? "has-handoff-action" : ""}">
      <div class="metric"><span>Latest</span><strong>${fmt(currentTotals.latest)}</strong></div>
      <div class="metric"><span>Ultimate</span><strong>${fmt(currentTotals.ultimate)}</strong></div>
      <div class="metric primary"><span>IBNR</span><strong>${fmt(currentTotals.ibnr)}</strong></div>
      <div class="metric ${staged || recalculating ? "staged" : ""} ${live ? "live-preview" : ""}"><span>Selected IBNR</span><strong aria-live="polite">${recalculating ? selectedText : staged ? "preview required" : selectedText}</strong></div>
      <div class="metric ${staged || recalculating ? "staged" : ""} ${live ? "live-preview" : ""}"><span>Delta IBNR</span><strong aria-live="polite">${recalculating ? deltaText : staged ? `${stagedChangeCount()} staged` : deltaText}</strong></div>
      <div class="metric"><span>Report readiness</span><strong>${safe(state.readiness?.status || "n/a")}</strong></div>
      ${exploreAction}
    </div>
  `;
}

function NextActionCard() {
  const action = state.readiness?.next_action;
  if (!action) {
    return `
      <section class="hero-action">
        <p class="section-label">Next action</p>
        <h3>No governed action is currently selected.</h3>
        <p class="empty">Choose a run to load workbench state.</p>
      </section>
    `;
  }
  return `
    <section class="hero-action">
      <div class="row-actions">
        <span class="${badgeClass(action.blocked ? "blocked" : "ready")}">${action.blocked ? "blocked" : "ready"}</span>
        <span class="pill">${safe(action.decision_type || "workflow")}</span>
      </div>
      <div>
        <p class="section-label">Next action</p>
        <h3>${safe(action.detail || action.label)}</h3>
      </div>
      <div class="row-actions">
        <button class="primary-button" onclick="openNextAction()">Open Review</button>
        <button onclick="refreshTasks()">Refresh Tasks</button>
      </div>
    </section>
  `;
}

function renderChrome() {
  const selectedRun = state.runId || "Select a run";
  $("runTitle").textContent = selectedRun;
  $("runSubtitle").textContent = "";
  $("runBadges").innerHTML = ModeSwitch();
  $("commandStrip").innerHTML = CommandStrip();
  $("globalMetricStrip").innerHTML = MetricStrip();
  $("leftRailState").innerHTML = LeftRail();
}

function screenHeading(eyebrow, title, detail, right = "") {
  return `
    <div class="screen-heading">
      <div>
        <p class="eyebrow">${safe(eyebrow)}</p>
        <h2>${safe(title)}</h2>
        <p>${safe(detail)}</p>
      </div>
      ${right}
    </div>
  `;
}

function renderOverview() {
  $("overviewPanel").innerHTML = `
    ${screenHeading("Overview cockpit", methodLabel(), "A governed review surface over deterministic run artifacts.", `<span class="${badgeClass(state.readiness?.status)}">${safe(state.readiness?.status || "n/a")}</span>`)}
    ${NextActionCard()}
    <div class="workspace-grid">
      <div>
        ${renderIbnrByOriginChart()}
        ${renderWarningSurface()}
      </div>
      <div>
        ${renderGovernanceChecklist()}
        ${renderSelectedScenarioImpact()}
      </div>
    </div>
  `;
}

function renderGovernanceChecklist() {
  const checklist = state.readiness?.checklist || [];
  return `
    <section class="surface">
      <div class="surface-header">
        <h3>Governance Readiness</h3>
        <span class="${badgeClass(state.readiness?.status)}">${safe(state.readiness?.status || "n/a")}</span>
      </div>
      <div class="checklist">
        ${checklist.map((item) => `
          <div class="check-row ${safe(item.status)}">
            <span class="check-dot"></span>
            <strong>${safe(item.label)}</strong>
            <span>${safe(item.status)}</span>
          </div>
        `).join("") || '<p class="empty">Readiness checklist unavailable.</p>'}
      </div>
    </section>
  `;
}

function ibnrByOriginDisplay() {
  const preview = state.selectionSetPreview || state.livePreview;
  const previewRows = Array.isArray(preview?.comparison?.by_origin_ibnr_impact)
    ? preview.comparison.by_origin_ibnr_impact
    : [];
  if (previewRows.length) {
    return {
      rows: previewRows.map((row) => ({
        origin: row.origin,
        base_ibnr: row.base_ibnr,
        base_ibnr_chart_pct: row.base_ibnr_chart_pct,
        selected_ibnr: row.candidate_ibnr,
        selected_ibnr_chart_pct: row.candidate_ibnr_chart_pct
      })),
      selected: true,
      source: preview.preview_kind === "transient" ? "live deterministic preview" : "governed preview"
    };
  }

  const projectionRows = state.projection?.projection || [];
  if (projectionRows.some((row) => row.selected_ibnr !== null && row.selected_ibnr !== undefined)) {
    return {
      rows: projectionRows.map((row) => ({
        origin: row.origin,
        base_ibnr: row.ibnr,
        base_ibnr_chart_pct: row.ibnr_chart_pct,
        selected_ibnr: row.selected_ibnr,
        selected_ibnr_chart_pct: row.selected_ibnr_chart_pct
      })),
      selected: true,
      source: "committed selected scenario"
    };
  }

  return {
    rows: projectionRows.map((row) => ({
      origin: row.origin,
      base_ibnr: row.ibnr,
      base_ibnr_chart_pct: row.ibnr_chart_pct,
      selected_ibnr: null,
      selected_ibnr_chart_pct: null
    })),
    selected: false,
    source: state.livePreviewPending ? "recalculating deterministic preview" : "fit.json"
  };
}

function renderIbnrByOriginChart() {
  const chart = ibnrByOriginDisplay();
  const rows = chart.rows;
  const chartHelp = chart.selected
    ? `Black shows base IBNR. Orange shows the delta to the selected deterministic backend preview. Source: ${chart.source}.`
    : `Values and chart percentages come from fit/projection artifacts. Source: ${chart.source}.`;
  return `
    <section class="surface">
      <div class="surface-header">
        <div>
          <h3>IBNR by Origin <span class="hover-help" tabindex="0" aria-label="Chart information" data-tooltip="${safe(chartHelp)}">i</span></h3>
        </div>
      </div>
      ${chart.selected ? `<p class="chart-comparison-key hover-only-key"><span class="base-key"></span>Base IBNR <span class="selected-key"></span>Selected IBNR · ${safe(chart.source)}</p>` : ""}
      <div class="bar-list">
        ${rows.map((row) => {
          const basePct = Number(row.base_ibnr_chart_pct || 0);
          const selectedPct = Number(row.selected_ibnr_chart_pct || 0);
          const deltaValue = Number(row.selected_ibnr || 0) - Number(row.base_ibnr || 0);
          const tooltip = chart.selected
            ? `Base ${fmt(row.base_ibnr)} · Selected ${fmt(row.selected_ibnr)} · Delta ${fmt(deltaValue)}`
            : `IBNR ${fmt(row.base_ibnr)}`;
          return `
          <div class="bar-row">
            <span>${safe(row.origin)}</span>
            <div class="bar-track ${chart.selected ? "comparison-bar-track" : ""}" title="${safe(tooltip)}">
              <div class="bar-fill base-bar" style="width:${barWidth(row.base_ibnr_chart_pct)}"></div>
              ${chart.selected ? `<div class="bar-fill selected-bar" style="width:${barWidth(selectedPct)}"></div><i class="selected-endpoint" style="left:${barWidth(selectedPct)}"></i>` : ""}
            </div>
            <strong class="bar-values" title="${safe(tooltip)}">${chart.selected ? fmt(row.selected_ibnr) : fmt(row.base_ibnr)}</strong>
          </div>
        `;}).join("") || '<p class="empty">Projection by origin is not available.</p>'}
      </div>
    </section>
  `;
}

function renderSelectedScenarioImpact() {
  const preview = (state.selectionSetPreview || state.livePreview)?.comparison;
  const comparison = state.comparison;
  const deltas = preview?.deltas || comparison?.deltas || {};
  const live = Boolean(state.livePreview && !state.selectionSetPreview);
  const scenarioId = state.selectionSetPreview?.preview_scenario_id || (live ? "live deterministic preview" : null) || state.selectedScenarioId || state.summary?.selected_scenario_id || "none";
  return `
    <section class="surface">
      <div class="surface-header">
        <h3>Selected Scenario Impact</h3>
        <span class="pill">${safe(scenarioId)}</span>
      </div>
      <div class="two-column">
        <div class="metric"><span>Delta Ultimate</span><strong>${fmt(deltas.ultimate)}</strong></div>
        <div class="metric"><span>Delta IBNR</span><strong>${fmt(deltas.ibnr)}</strong></div>
      </div>
      <p class="empty">${scenarioId === "none" ? "No selected scenario impact is available." : live ? "Transient deterministic calculation only. Create a governed preview before committing." : "Scenario impact is sourced from backend comparison artifacts."}</p>
    </section>
  `;
}

function renderWarningSurface() {
  const validation = state.artifacts["validation.json"];
  const diagnostics = state.artifacts["diagnostics.json"];
  const validationWarnings = (validation?.checks || []).filter((check) => check.verdict === "warn");
  const diagnosticWarnings = (diagnostics?.tests || []).filter((test) => test.verdict === "warn");
  return `
    <section class="surface">
      <div class="surface-header">
        <h3>Warnings</h3>
        <span class="pill severity-warning">${fmt(validationWarnings.length + diagnosticWarnings.length)}</span>
      </div>
      <ul class="compact-list">
        ${validationWarnings.map((warning) => `<li>validation: ${safe(warning.check_id)}</li>`).join("")}
        ${diagnosticWarnings.map((warning) => `<li>diagnostics: ${safe(warning.test_id)}</li>`).join("")}
        ${!validationWarnings.length && !diagnosticWarnings.length ? '<li class="empty">No warnings in loaded artifacts.</li>' : ""}
      </ul>
    </section>
  `;
}

function openNextAction() {
  const action = state.readiness?.next_action;
  if (!action) return;
  if (action.task_id) {
    state.selectedTask = (state.tasks?.tasks || []).find((task) => task.task_id === action.task_id) || null;
  }
  state.activeTab = action.target_tab === "scenarios" ? "scenarios" : action.target_tab || "decisions";
  render();
}

function triangleModePayload(mode = state.triangleMode, payload = displayedTrianglePayload()) {
  return payload.views?.[mode] || {
    label: mode,
    cells: payload.cells || [],
    source_artifacts: ["triangle.json"]
  };
}

function displayedTrianglePayload() {
  return state.selectionSetPreview?.candidate_triangle || state.livePreview?.candidate_triangle || state.triangle || {};
}

function triangleCellMap(cells) {
  const mapped = {};
  cells.forEach((cell) => {
    mapped[`${cell.origin}::${cell.dev}`] = cell;
  });
  return mapped;
}

function triangleCellClass(cell, mode, relativeHeatBucket = null) {
  if (!cell) return "blank-cell";
  const heatBucket = relativeHeatBucket ?? 3;
  const classes = [`triangle-cell`, `heat-${heatBucket}`];
  if (cell.is_projected || cell.projected) classes.push("projected");
  if (cell.is_latest_diagonal || cell.latest_diagonal) classes.push("latest-diagonal");
  if (cell.warning) classes.push("warning-cell");
  if (cell.excluded) classes.push("excluded-cell");
  if ((cell.is_projected || cell.projected) && state.livePreviewPending) classes.push("recalculating-cell");
  if ((cell.is_projected || cell.projected) && state.livePreview) classes.push("live-preview-cell");
  if (isTriangleFactorPointStaged(cell)) classes.push("staged-factor-point");
  if (String(cell.dev) === String(state.selectedDevelopmentAge)) classes.push("active-development-column");
  if (
    state.selectedTriangleCell &&
    String(state.selectedTriangleCell.origin) === String(cell.origin) &&
    String(state.selectedTriangleCell.dev) === String(cell.dev) &&
    state.selectedTriangleCell.mode === mode
  ) {
    classes.push("selected-cell");
  }
  return classes.join(" ");
}

function columnRelativeHeatBuckets(cells) {
  const byDevelopment = {};
  cells.forEach((cell) => {
    const value = Number(cell.value);
    if (!Number.isFinite(value) || cell.is_projected || cell.projected) return;
    (byDevelopment[String(cell.dev)] ||= []).push(cell);
  });
  const buckets = {};
  Object.values(byDevelopment).forEach((column) => {
    const sorted = [...column].sort((a, b) => Number(a.value) - Number(b.value));
    sorted.forEach((cell) => { buckets[`${cell.origin}::${cell.dev}`] = 3; });
    if (sorted.length < 4) return;
    buckets[`${sorted[0].origin}::${sorted[0].dev}`] = 5;
    buckets[`${sorted.at(-1).origin}::${sorted.at(-1).dev}`] = 0;
  });
  return buckets;
}

function triangleValue(cell, mode) {
  if (!cell) return "";
  if (cell.value === null || cell.value === undefined) return "";
  const value = mode === "link_ratios" ? fmtFactor(cell.value) : fmt(cell.value);
  return `<span class="triangle-cell-value">${value}</span>`;
}

function isTriangleFactorPointStaged(cell) {
  if (!cell || cell.is_projected || cell.projected) return false;
  return factorPointDrafts().some(
    (draft) => String(draft.origin) === String(cell.origin) && String(draft.from_dev) === String(cell.dev)
  );
}

function TriangleHeatmap(payload, view, mode) {
  const headers = mode === "link_ratios"
    ? (payload.developments || []).filter((dev) => (state.factors?.factors || []).some((row) => String(row.from_dev) === String(dev)))
    : payload.developments || [];
  const origins = payload.origins || [];
  const cells = triangleCellMap(view.cells || []);
  const relativeHeatBuckets = columnRelativeHeatBuckets(view.cells || []);
  const previewState = mode !== "link_ratios";
  return `
    <div class="triangle-table-wrap ${state.triangleHeatmap ? "heatmap-active" : ""} ${previewState && state.livePreviewPending ? "is-recalculating" : ""} ${previewState && state.livePreview ? "is-live-preview" : ""}">
      <table>
        <thead>
          <tr><th>Origin</th>${headers.map((dev) => {
            const hasFactor = (state.factors?.factors || []).some((row) => String(row.from_dev) === String(dev));
            const active = String(state.selectedDevelopmentAge) === String(dev);
            return `<th class="${active ? "active-development-header" : ""}">${hasFactor ? `<button class="development-header-button" onclick="selectDevelopmentAge('${safe(dev)}')">${safe(dev)}</button>` : safe(dev)}</th>`;
          }).join("")}</tr>
        </thead>
        <tbody>
          ${origins.map((origin) => `
            <tr>
              <th>${safe(origin)}</th>
              ${headers.map((dev) => {
                const cell = cells[`${origin}::${dev}`];
                const ratioObservation = mode === "link_ratios" && cell && !(cell.is_projected || cell.projected) && (state.factors?.factors || []).some((row) => String(row.from_dev) === String(dev));
                return `
                  <td class="${triangleCellClass(cell, mode, relativeHeatBuckets[`${origin}::${dev}`])} ${ratioObservation ? "ratio-observation" : ""}" ${ratioObservation ? 'title="Click to toggle this factor observation in the staged scenario"' : ""} onclick="selectTriangleCell('${safe(origin)}', '${safe(dev)}', '${safe(mode)}')">
                    ${triangleValue(cell, mode)}
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

function renderTriangles() {
  const payload = displayedTrianglePayload();
  if (!payload?.available) {
    $("trianglesPanel").innerHTML = `
      ${screenHeading("Triangle explorer", "Triangle unavailable", "No triangle display payload is available for this run.")}
      <p class="empty">Open the Artifacts tab to inspect available files.</p>
    `;
    return;
  }
  const factorRows = state.factors?.factors || [];
  const selectedRow = selectedFactorRow(factorRows);
  if (selectedRow && state.selectedDevelopmentAge === null) {
    state.selectedDevelopmentAge = String(selectedRow.from_dev);
  }
  const valueView = triangleModePayload();
  const evidencePayload = state.triangle || payload;
  const linkRatioView = triangleModePayload("link_ratios", evidencePayload);
  const valueCells = valueView.cells || [];
  const linkRatioCells = linkRatioView.cells || [];
  const projectionCount = valueCells.filter((cell) => cell.is_projected || cell.projected).length;
  const actualCount = valueCells.filter((cell) => !(cell.is_projected || cell.projected)).length;
  const ratioCount = linkRatioCells.filter((cell) => cell.value !== null && cell.value !== undefined).length;
  $("trianglesPanel").innerHTML = `
    ${screenHeading("01 · Development workbench", "Triangle and Factor Selection", "Inspect the observed triangle, review link ratios, and stage a fitting basis. Colour is used only to mark the current selection.", `<span class="pill">Method&nbsp;&nbsp; ${safe(payload.display_method)}</span>`)}
    ${ModeBanner()}
    <div class="triangle-layout">
        <section class="triangle-instrument value-triangle-instrument">
          <div class="surface-header">
            <div class="triangle-toolbar" role="group" aria-label="Value triangle view">
              <button class="${state.triangleMode === "cumulative" ? "active" : ""}" onclick="selectTriangleMode('cumulative')">Cumulative</button>
              <button class="${state.triangleMode === "incremental" ? "active" : ""}" onclick="selectTriangleMode('incremental')">Incremental</button>
              <button class="heatmap-toggle ${state.triangleHeatmap ? "active" : ""}" aria-pressed="${state.triangleHeatmap}" onclick="toggleTriangleHeatmap()">Heatmap</button>
            </div>
            <span class="pill">${state.livePreviewPending ? "recalculating deterministic projection" : state.selectionSetPreview ? "governed preview projection" : state.livePreview ? "live deterministic projection · not committed" : "observed values and future projection"}</span>
          </div>
          <div class="triangle-basis-legend" aria-label="Triangle cell basis legend">
            <span><i class="actual-swatch"></i><strong>Observed</strong>${actualCount} cells</span>
            <span><i class="diagonal-swatch"></i><strong>Latest diagonal</strong>valuation boundary</span>
            <span><i class="projection-swatch"></i><strong>Future projection</strong>${projectionCount} cells · ${state.livePreview ? "transient backend factors" : "backend selected factors"}</span>
          </div>
          ${TriangleHeatmap(payload, valueView, state.triangleMode)}
        </section>
        <section class="triangle-instrument ratio-triangle-instrument">
          <div class="surface-header">
            <div>
              <p class="section-label">Selection evidence</p>
              <h3>Link Ratios</h3>
            </div>
            <span class="pill">click to include or exclude</span>
          </div>
          <div class="triangle-basis-legend" aria-label="Link ratio legend">
            <span><i class="ratio-swatch"></i><strong>Factor observations</strong>${ratioCount} ratios</span>
            <span><i class="actual-swatch"></i><strong>Included</strong>base evidence</span>
            <span><i class="ratio-swatch"></i><strong>Outlined</strong>staged exclusion</span>
          </div>
          ${TriangleHeatmap(evidencePayload, linkRatioView, "link_ratios")}
        </section>
      <div class="development-instrument-panel development-ibnr-panel">${renderIbnrByOriginChart()}</div>
      <div class="development-instrument-panel development-factor-panel">${FactorCurve(factorRows)}</div>
    </div>
    ${renderIntegratedFactorWorkbench(factorRows, selectedRow, { includeFactorCurve: false })}
  `;
}

function renderIntegratedFactorWorkbench(rows, selectedRow, { includeFactorCurve = true } = {}) {
  if (!state.factors?.available) {
    return '<section class="integrated-factor-workbench"><p class="empty">Factor output is unavailable for this run.</p></section>';
  }
  const workflow = selectionWorkflowState();
  return `
    <section class="integrated-factor-workbench">
      ${includeFactorCurve ? FactorCurve(rows) : ""}
      ${renderFactorPointPlot(selectedRow)}
      ${renderCurveOptions()}
      <details class="workbench-disclosure factor-controls-disclosure" ${state.workbenchDisclosures.perAge ? "open" : ""} ontoggle="setWorkbenchDisclosure('perAge', this.open)">
        <summary><span>Development age and fitting options</span><small>${safe(selectedRow?.development_age || "double-click a fitted point")}</small></summary>
      <div class="integrated-workbench-heading">
        <div>
          <p class="section-label">Development factor review</p>
          <h2>All development ages</h2>
          <p>Double-click an outlined fitted point to inspect that development age. Drag vertically only when staging a manual override.</p>
        </div>
        <div class="state-chip-stack">
          <span class="${badgeClass(workflow.key)}">${safe(workflow.label)}</span>
          <span class="pill">${safe(selectedRow?.development_age || "no age selected")}</span>
        </div>
      </div>
        ${renderDevelopmentAgeStrip(rows)}
        ${renderSelectedDevelopmentControls(selectedRow)}
        ${selectedRow ? renderManualOverride(selectedRow) : ""}
      </details>
      ${renderSelectionScenarioPanel()}
      <details class="workbench-disclosure" ${state.workbenchDisclosures.review ? "open" : ""} ontoggle="setWorkbenchDisclosure('review', this.open)">
        <summary><span>AI review evidence</span><small>${reviewSuggestions().length} items</small></summary>
        ${renderFactorReviewQueue()}
      </details>
      <details class="workbench-disclosure" ${state.workbenchDisclosures.allFactors ? "open" : ""} ontoggle="setWorkbenchDisclosure('allFactors', this.open)">
        <summary><span>Development factor table</span><small>secondary review</small></summary>
        ${renderFactorTable(rows)}
      </details>
      <details class="workbench-disclosure" ${state.workbenchDisclosures.tail ? "open" : ""} ontoggle="setWorkbenchDisclosure('tail', this.open)">
        <summary><span>Tail assumption</span><small>${safe(state.selectionDraft.tail ? "staged" : "base fit")}</small></summary>
        ${renderTailWorkbench()}
      </details>
    </section>
  `;
}

function setWorkbenchDisclosure(name, open) {
  state.workbenchDisclosures[name] = Boolean(open);
}

function renderDevelopmentAgeStrip(rows) {
  return `
    <div class="development-age-strip" role="group" aria-label="Development age under review">
      ${rows.map((row) => {
        const active = String(row.from_dev) === String(state.selectedDevelopmentAge);
        const changed = Boolean(draftForRow(row));
        return `<button class="${active ? "active" : ""} ${changed ? "changed" : ""}" onclick="selectDevelopmentAge('${safe(row.from_dev)}')"><span>${safe(row.development_age)}</span>${changed ? "<small>staged</small>" : ""}</button>`;
      }).join("")}
    </div>
  `;
}

function selectTriangleMode(mode) {
  state.triangleMode = mode === "incremental" ? "incremental" : "cumulative";
  state.selectedTriangleCell = null;
  renderTriangles();
  renderValidationDrawer();
}

function toggleTriangleHeatmap() {
  state.triangleHeatmap = !state.triangleHeatmap;
  renderTriangles();
}

async function selectTriangleCell(origin, dev, mode) {
  const view = triangleModePayload(mode, mode === "link_ratios" ? (state.triangle || displayedTrianglePayload()) : displayedTrianglePayload());
  const cell = (view.cells || []).find((item) => String(item.origin) === String(origin) && String(item.dev) === String(dev));
  state.selectedTriangleCell = cell ? { ...cell, mode } : null;
  const factorRow = (state.factors?.factors || []).find((row) => String(row.from_dev) === String(dev));
  if (factorRow && String(state.selectedDevelopmentAge) !== String(factorRow.from_dev)) {
    state.selectedDevelopmentAge = String(factorRow.from_dev);
    state.selectedFactorPoint = null;
    await loadFactorDetail(factorRow.from_dev, false);
  }
  if (mode === "link_ratios" && cell && !(cell.is_projected || cell.projected) && factorRow) {
    const point = triangleFactorPoint(cell);
    const action = point?.actions?.point_exclusion;
    if (point && action?.supported) {
      state.selectedFactorPoint = point;
      if (isPointExclusionStaged(point)) {
        state.selectionDraft.exclusions.points = factorPointDrafts().filter((draft) => draft.value !== action.value);
        showToast("Factor observation returned to the staged inclusion set.");
      } else {
        state.selectionDraft.exclusions.points.push({
          type: "factor_point",
          value: action.value,
          origin: action.origin,
          from_dev: action.from_dev,
          to_dev: action.to_dev,
          development_age: action.development_age,
          link_ratio: point.link_ratio,
          rationale: ""
        });
        showToast("Factor observation excluded in the staged scenario.");
      }
      state.selectionSetPreview = null;
      scheduleLivePreview();
      renderTriangles();
      renderValidationDrawer();
      return;
    }
  }
  renderTriangles();
  renderValidationDrawer();
}

function stageOriginExclusionFromCell(origin) {
  state.selectionDraft.exclusions.origins = addCommaValue(state.selectionDraft.exclusions.origins, origin);
  state.selectionSetPreview = null;
  scheduleLivePreview();
  state.activeTab = "triangles";
  showToast("Origin exclusion staged for scenario preview.");
  render();
}

function stageValuationExclusionFromCell(dev) {
  state.selectionDraft.exclusions.valuations = addCommaValue(state.selectionDraft.exclusions.valuations, dev);
  state.selectionSetPreview = null;
  scheduleLivePreview();
  state.activeTab = "triangles";
  showToast("Valuation/development exclusion staged for scenario preview.");
  render();
}

function clearStagedExclusionFromCell(origin, dev) {
  state.selectionDraft.exclusions.origins = removeCommaValue(state.selectionDraft.exclusions.origins, origin);
  state.selectionDraft.exclusions.valuations = removeCommaValue(state.selectionDraft.exclusions.valuations, dev);
  state.selectionSetPreview = null;
  scheduleLivePreview();
  render();
}

function renderTriangleCellDetail() {
  const cell = state.selectedTriangleCell;
  if (!cell) return '<p class="empty">Select a triangle cell to inspect source values and supported actions.</p>';
  const link = cell.link_ratio || {};
  const source = cell.source_artifact || (cell.mode === "link_ratios" ? "fit.json" : "triangle.json");
  const originStaged = commaValues(state.selectionDraft.exclusions.origins).includes(String(cell.origin));
  const valuationStaged = commaValues(state.selectionDraft.exclusions.valuations).includes(String(cell.dev));
  const factorPoint = triangleFactorPoint(cell);
  const factorPointStaged = factorPoint ? isPointExclusionStaged(factorPoint) : false;
  const projection = cell.is_projected || cell.projected;
  return `
    <dl class="checklist">
      <div class="check-row"><span></span><strong>Origin</strong><span>${safe(cell.origin)}</span></div>
      <div class="check-row"><span></span><strong>Development</strong><span>${safe(cell.development_age || cell.dev)}</span></div>
      <div class="check-row"><span></span><strong>Cumulative</strong><span>${fmt(cell.cumulative_value ?? (cell.mode === "cumulative" ? cell.value : null))}</span></div>
      <div class="check-row"><span></span><strong>Incremental</strong><span>${fmt(cell.mode === "incremental" ? cell.value : cell.incremental_value)}</span></div>
      <div class="check-row"><span></span><strong>Link ratio</strong><span>${fmtFactor(cell.mode === "link_ratios" ? cell.value : link.value)}</span></div>
      <div class="check-row"><span></span><strong>Source</strong><span>${safe(source)}</span></div>
      <div class="check-row"><span></span><strong>Warning</strong><span>${cell.warning ? "yes" : "no"}</span></div>
      <div class="check-row"><span></span><strong>Excluded</strong><span>${cell.excluded ? "yes" : "no"}</span></div>
      <div class="check-row"><span></span><strong>Cell basis</strong><span>${projection ? "future projection" : "observed"}</span></div>
      <div class="check-row"><span></span><strong>Factor observation</strong><span>${factorPoint ? (factorPointStaged ? "exclusion staged" : "included") : "not applicable"}</span></div>
    </dl>
    <div class="row-actions" style="margin-top: 14px;">
      ${factorPoint ? `<button class="${factorPointStaged ? "danger-button" : ""}" onclick="${factorPointStaged ? `clearFactorPointExclusion('${safe(factorPoint.actions?.point_exclusion?.value)}')` : `stageFactorPointExclusion('${safe(factorPoint.point_id)}')`}">${factorPointStaged ? "Include factor observation" : "Exclude factor observation"}</button>` : ""}
      <button onclick="stageOriginExclusionFromCell('${safe(cell.origin)}')">${originStaged ? "Origin staged" : "Stage origin exclusion"}</button>
      <button onclick="stageValuationExclusionFromCell('${safe(cell.dev)}')">${valuationStaged ? "Valuation staged" : "Stage valuation exclusion"}</button>
      <button onclick="clearStagedExclusionFromCell('${safe(cell.origin)}', '${safe(cell.dev)}')">Clear staged</button>
    </div>
    <p class="empty" style="margin-top: 10px;">${projection ? "Projected cells are outputs and cannot be excluded as observations." : factorPoint ? "Factor observation exclusion is scoped to this origin and development transition." : "No outgoing observed link ratio exists for this cell."} Actions only stage a governed scenario preview.</p>
  `;
}

function triangleFactorPoint(cell) {
  if (!cell || cell.is_projected || cell.projected) return null;
  return (state.factorDetail?.points || []).find(
    (point) => String(point.origin) === String(cell.origin) && String(point.from_dev) === String(cell.dev)
  ) || null;
}

function FactorCandidateCard(row, card) {
  const draft = draftForRow(row);
  const active = draft ? draft.selected_basis === card.basis : card.basis === "fitted";
  const displayed = displayedFactorBases(row).includes(card.basis);
  return `
    <article class="factor-card ${active ? "active" : ""}">
      <div class="factor-card-heading">
        <span>${safe(card.label || factorBasisLabel(card.basis))}</span>
        ${active ? '<em>reporting basis</em>' : ""}
      </div>
      <strong>${fmtFactor(card.value)}</strong>
      <small>Delta ${fmtFactor(card.delta_vs_current)}</small>
      <div class="factor-card-actions">
        <label class="fit-display-toggle" title="Show ${safe(card.label || factorBasisLabel(card.basis))} on graph">
          <input type="checkbox" aria-label="Show ${safe(card.label || factorBasisLabel(card.basis))} on graph" ${displayed ? "checked" : ""} onchange="toggleFactorDisplay('${safe(row.from_dev)}', '${safe(card.basis)}')" />
          <span>Graph</span>
        </label>
        <button title="${card.basis === "fitted" ? "Restore the current fitted basis" : `Use ${safe(card.label || factorBasisLabel(card.basis))} as the selected basis`}" ${active && card.basis === "fitted" ? "disabled" : ""} onclick="selectFactorCandidate('${safe(row.from_dev)}', '${safe(card.basis)}')">${card.basis === "fitted" ? "Current" : "Use"}</button>
      </div>
    </article>
  `;
}

function displayedFactorBases(row) {
  const bases = [...state.factorCurveSeries];
  const draft = draftForRow(row);
  if (draft && draft.selected_basis !== "manual_override" && !bases.includes(draft.selected_basis)) {
    bases.push(draft.selected_basis);
  }
  return bases;
}

function toggleFactorDisplay(fromDev, basis) {
  if (!(state.factors?.factors || []).some((row) => String(row.from_dev) === String(fromDev))) return;
  state.factorCurveSeries = state.factorCurveSeries.includes(basis)
    ? state.factorCurveSeries.filter((item) => item !== basis)
    : [...state.factorCurveSeries, basis];
  renderTriangles();
}

function candidateColor(basis) {
  return {
    fitted: "#171512",
    volume_weighted: "#ff7900",
    simple_average: "#006f46",
    last_3: "#e10600",
    last_5: "#1464f4",
    trimmed_mean: "#7b2cbf",
    median: "#c58b00"
  }[basis] || "#ff7900";
}

function FactorCurve(rows) {
  if (!rows.length) return '<p class="empty">No factor curve values are available.</p>';
  const display = state.factors?.factor_curve_display || {};
  const series = (display.series || []).filter((item) => state.factorCurveSeries.includes(item.basis));
  const fittedSeries = (display.series || []).find((item) => item.basis === "fitted") || { points: [] };
  return `
    <section class="surface all-factor-curve">
      <div class="surface-header">
        <div><h3>All-Development Factor Curve <span class="hover-help" tabindex="0" aria-label="Chart information" data-tooltip="Double-click an outlined fitted point to inspect one age. Drag vertically to stage a manual override. Every override requires rationale and deterministic preview. Smoothing changes the display path only.">i</span></h3></div>
        <div class="scale-selector">
          <button class="${state.factorCurveMode === "raw" ? "active" : ""}" onclick="setFactorCurveMode('raw')">Raw</button>
          <button class="${state.factorCurveMode === "smooth" ? "active" : ""}" onclick="setFactorCurveMode('smooth')">Smooth display</button>
        </div>
      </div>
      <div class="all-factor-chart-shell">
        <svg viewBox="0 0 960 310" preserveAspectRatio="none" role="img" aria-label="All development factor curves converging toward one">
          <line class="factor-one-line" x1="65" y1="${display.one_reference_y ?? 250}" x2="895" y2="${display.one_reference_y ?? 250}"></line>
          <text x="900" y="254" class="factor-one-label">1.000</text>
          ${(display.ages || []).map((age) => `<text x="${age.x}" y="285" text-anchor="middle" class="factor-age-label">${safe(age.development_age)}</text>`).join("")}
          ${series.map((item) => {
            return `<g class="factor-curve-series" data-basis="${safe(item.basis)}" data-mode="${state.factorCurveMode}">
              <path d="${safe(state.factorCurveMode === "smooth" ? item.smooth_path : item.raw_path)}" style="stroke:${candidateColor(item.basis)}"></path>
              ${(item.points || []).map((point) => `<circle cx="${point.x}" cy="${point.y}" r="4" style="fill:${candidateColor(item.basis)}"><title>${safe(item.label)} · ${safe(point.development_age)} · ${fmtFactor(point.value)}</title></circle>`).join("")}
            </g>`;
          }).join("")}
          <g class="all-factor-drag-handles">
            ${(fittedSeries.points || []).map((point) => {
              const override = state.dragOverrides[String(point.from_dev)];
              const y = override?.all_curve_y ?? point.y;
              return `<g class="all-factor-drag-handle ${override ? "staged" : ""}">
                <circle cx="${point.x}" cy="${y}" r="8" role="slider" tabindex="0" aria-label="Double-click ${safe(point.development_age)} to inspect it, or drag vertically to stage a manual override" onpointerdown="beginFactorDrag(event, '${safe(point.from_dev)}', 'all_development', 'log')" ondblclick="openPerAgeGraph('${safe(point.from_dev)}', event)"></circle>
                <title>${safe(point.development_age)} · double-click to inspect · drag to stage manual override${override ? ` · ${fmtFactor(override.manual_factor)}` : ""}</title>
              </g>`;
            }).join("")}
          </g>
        </svg>
      </div>
    </section>
  `;
}

function renderCurveOptions() {
  const definitions = [
    ["fitted", "Fitted / current"], ["volume_weighted", "Volume weighted"],
    ["simple_average", "Simple average"], ["last_3", "Last 3"],
    ["last_5", "Last 5"], ["trimmed_mean", "Trimmed mean"], ["median", "Median"]
  ];
  const showingAll = FACTOR_BASES.every((basis) => state.factorCurveSeries.includes(basis));
  const showingOnlyFitted = state.factorCurveSeries.length === 1 && state.factorCurveSeries[0] === "fitted";
  return `
    <details class="curve-options shared-fitting-options" ${state.workbenchDisclosures.curveOptions ? "open" : ""} ontoggle="setWorkbenchDisclosure('curveOptions', this.open)">
      <summary><span>Compare fittings</span><small>${state.factorCurveSeries.length} shown across both graphs</small></summary>
      <div class="curve-series-controls">
        <button class="fitting-preset ${showingAll ? "active" : ""}" aria-pressed="${showingAll}" onclick="showAllFactorCurves()">Show all</button>
        <button class="fitting-preset ${showingOnlyFitted ? "active" : ""}" aria-pressed="${showingOnlyFitted}" onclick="showOnlyFittedCurve()">Only fitted</button>
        ${definitions.map(([basis, label]) => `<label class="fitting-chip" style="--series-color:${candidateColor(basis)}"><input type="checkbox" ${state.factorCurveSeries.includes(basis) ? "checked" : ""} onchange="toggleFactorCurveSeries('${basis}')"><i></i><span>${safe(label)}</span></label>`).join("")}
      </div>
    </details>
  `;
}

function toggleFactorCurveSeries(basis) {
  state.factorCurveSeries = state.factorCurveSeries.includes(basis) ? state.factorCurveSeries.filter((item) => item !== basis) : [...state.factorCurveSeries, basis];
  renderTriangles();
}
function showAllFactorCurves() { state.factorCurveSeries = [...FACTOR_BASES]; renderTriangles(); }
function showOnlyFittedCurve() { state.factorCurveSeries = ["fitted"]; renderTriangles(); }
function setFactorCurveMode(mode) { state.factorCurveMode = mode === "smooth" ? "smooth" : "raw"; renderTriangles(); }

function renderFactors() {
  renderTriangles();
}

function reviewSuggestions() {
  return state.factorSuggestions?.suggestions || [];
}

function renderFactorReviewQueue() {
  const suggestions = reviewSuggestions();
  if (!state.factorAnalysis?.analysis_id) {
    return `
      <section class="review-queue empty-analysis">
        <div>
          <p class="section-label">AI review queue</p>
          <h3>Deterministic factor evidence has not been generated</h3>
          <p class="empty">Generate leave-one-out influence evidence before asking an AI or senior actuary to review link ratios.</p>
        </div>
        <button onclick="refreshFactorAnalysis()">Generate Analysis</button>
      </section>
    `;
  }
  return `
    <section class="review-queue">
      <div class="surface-header">
        <div>
          <p class="section-label">AI review queue</p>
          <h3>Evidence for actuarial judgment</h3>
          <p class="empty">Deterministic screening only. Suggestions do not select factors, stage changes, or enter the report without governed approval.</p>
        </div>
        <div class="state-chip-stack">
          <span class="pill">${safe(state.factorAnalysis.analysis_id)}</span>
          <span class="${badgeClass("active")}">${suggestions.length} review items</span>
        </div>
      </div>
      <div class="review-queue-list">
        ${suggestions.map((item) => renderFactorSuggestion(item)).join("") || '<p class="empty">No deterministic review prompts were raised.</p>'}
      </div>
    </section>
  `;
}

function renderFactorSuggestion(item) {
  const disposition = state.suggestionDispositions[item.suggestion_id];
  const evidence = item.evidence || {};
  return `
    <article class="review-suggestion ${disposition ? `is-${safe(disposition)}` : ""}">
      <div class="suggestion-rank">${evidence.influence_rank ? `#${safe(evidence.influence_rank)}` : "DATA"}</div>
      <div>
        <div class="suggestion-title-row">
          <strong>${safe(item.title)}</strong>
          <span class="${badgeClass(item.priority)}">${safe(item.priority)}</span>
          ${disposition ? `<span class="${badgeClass(disposition === "reviewed" ? "complete" : "superseded")}">${safe(disposition)}</span>` : ""}
        </div>
        <p>${safe(item.summary)}</p>
        <div class="suggestion-evidence">
          ${evidence.link_ratio !== undefined ? `<span>Link ratio <strong>${fmtFactor(evidence.link_ratio)}</strong></span>` : ""}
          ${evidence.delta_ibnr !== undefined ? `<span>Exclusion delta IBNR <strong>${fmt(evidence.delta_ibnr)}</strong></span>` : ""}
          ${evidence.observation_count !== undefined ? `<span>Observations <strong>${safe(evidence.observation_count)}</strong></span>` : ""}
          ${evidence.candidate_spread_pct !== undefined ? `<span>Candidate spread <strong>${percentText(evidence.candidate_spread_pct)}</strong></span>` : ""}
        </div>
      </div>
      <div class="suggestion-actions">
        <button onclick="inspectFactorSuggestion('${safe(item.suggestion_id)}')">Inspect</button>
        <button class="${disposition === "reviewed" ? "active" : ""}" onclick="setSuggestionDisposition('${safe(item.suggestion_id)}', 'reviewed')">Reviewed</button>
        <button class="${disposition === "dismissed" ? "active" : ""}" onclick="setSuggestionDisposition('${safe(item.suggestion_id)}', 'dismissed')">Dismiss</button>
      </div>
    </article>
  `;
}

async function refreshFactorAnalysis() {
  if (!state.runId) return;
  const run = encodeURIComponent(state.runId);
  try {
    const result = await api(`/api/runs/${run}/factor-analysis/refresh`, { method: "POST" });
    state.factorAnalysis = result.analysis;
    state.factorSuggestions = result.review_suggestions;
    showToast("Deterministic factor analysis generated.");
    await loadArtifacts();
    render();
  } catch (error) {
    showToast(error.message);
  }
}

async function inspectFactorSuggestion(suggestionId) {
  const suggestion = reviewSuggestions().find((item) => item.suggestion_id === suggestionId);
  if (!suggestion) return;
  const target = suggestion.target || {};
  let row = (state.factors?.factors || []).find((item) => String(item.development_age) === String(target.development_age));
  if (!row && target.from_dev !== undefined) {
    row = (state.factors?.factors || []).find((item) => String(item.from_dev) === String(target.from_dev));
  }
  if (row) {
    state.selectedDevelopmentAge = String(row.from_dev);
    await loadFactorDetail(row.from_dev, false);
  }
  if (target.point_id) selectFactorPoint(target.point_id, false);
  state.activeTab = "triangles";
  render();
  document.querySelector(".factor-point-layout")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function setSuggestionDisposition(suggestionId, disposition) {
  if (state.suggestionDispositions[suggestionId] === disposition) {
    delete state.suggestionDispositions[suggestionId];
  } else {
    state.suggestionDispositions[suggestionId] = disposition;
  }
  state.selectionSetPreview = null;
  renderFactors();
}

function renderSelectedDevelopmentControls(row) {
  if (!row) return '<p class="empty">No development age selected.</p>';
  const availableFittings = (row.candidate_cards || []).filter((card) => card.available && !card.input_required);
  const displayedCount = displayedFactorBases(row).length;
  return `
    <section class="factor-focus">
      <div class="surface-header">
        <div>
          <p class="section-label">Selected development age</p>
          <h3>${safe(row.development_age || "not available")}</h3>
        </div>
        <span class="pill">${availableFittings.length} available fittings</span>
      </div>
      <details class="focus-disclosure" ${state.workbenchDisclosures.fittings ? "open" : ""} ontoggle="setWorkbenchDisclosure('fittings', this.open)">
        <summary><span>Fitting choices</span><small>${displayedCount} shown on graph · ${availableFittings.length} available</small></summary>
        <div class="factor-grid">
          ${availableFittings.map((card) => FactorCandidateCard(row, card)).join("") || '<p class="empty">Candidate averages are not available.</p>'}
        </div>
      </details>
    </section>
  `;
}

function renderManualOverride(row) {
  const draft = draftForRow(row);
  const manualActive = draft?.selected_basis === "manual_override";
  const previewed = Boolean(state.selectionSetPreview && manualActive);
  return `
    <details class="manual-override-panel ${manualActive ? "active" : ""}" ${state.workbenchDisclosures.manual ? "open" : ""} ontoggle="setWorkbenchDisclosure('manual', this.open)">
      <summary>
        <span>Manual override</span>
        <small>${manualActive ? `staged ${fmtFactor(draft.selected_factor)}` : "drag the orange line or enter a value"}</small>
      </summary>
      <div class="manual-override-content">
        <div>
          <p class="section-label">Manual override candidate</p>
          <h3>${manualActive ? fmtFactor(draft.selected_factor) : fmtFactor(row.selected_factor)}</h3>
          <div class="manual-status-grid">
            <span>Base ${fmtFactor(row.selected_factor)}</span>
            <span>Manual ${manualActive ? fmtFactor(draft.selected_factor) : "not staged"}</span>
            <span>Delta vs base ${previewed ? "review preview" : "preview required"}</span>
          </div>
          <p class="blocker-summary">${state.workflowMode === "explore" ? "EXPLORE allows manual override preview without formal rationale. Promote deliberately before report use." : "Manual override requires rationale, preview, committed selection set, and immutable approval decision."}</p>
        </div>
        <div class="manual-grid">
          <div class="form-row">
            <label for="manualFactorInput">Selected factor</label>
            <input id="manualFactorInput" value="${manualActive ? safe(draft.selected_factor) : ""}" placeholder="positive factor" />
          </div>
          <div class="form-row">
            <label for="manualRationaleInput">Manual ${state.workflowMode === "explore" ? "note" : "rationale"}</label>
            <input id="manualRationaleInput" value="${manualActive ? safe(draft.rationale || "") : ""}" placeholder="${state.workflowMode === "explore" ? "optional while exploring" : "required"}" />
          </div>
          <button onclick="stageManualOverride('${safe(row.from_dev)}')">Stage Manual</button>
        </div>
      </div>
    </details>
  `;
}

function renderTailWorkbench() {
  const baseTail = state.artifacts["fit.json"]?.parameters?.tail || "none";
  const draft = state.selectionDraft.tail;
  const constantActive = draft?.type === "constant";
  return `
    <section class="surface tail-workbench">
      <div class="surface-header">
        <div>
          <p class="section-label">Tail assumption</p>
          <h3>${draft ? safe(draft.type === "constant" ? `Constant ${draft.factor || "not set"}` : "No tail") : safe(`Base: ${baseTail}`)}</h3>
        </div>
        <span class="${badgeClass(draft ? "staged" : "active")}">${draft ? "staged / preview required" : "base fit"}</span>
      </div>
      <div class="manual-grid">
        <button ${baseTail === "none" ? "disabled" : ""} onclick="stageTailType('none')">No Tail</button>
        <button onclick="stageTailType('constant')">Constant Tail</button>
        <div class="form-row">
          <label for="tailFactorInput">Tail factor</label>
          <input id="tailFactorInput" type="number" min="1" step="0.001" value="${constantActive ? safe(draft.factor || "") : ""}" ${constantActive ? "" : "disabled"} oninput="setTailDraft('factor', this.value)" placeholder="1.010" />
        </div>
        <div class="form-row">
          <label for="tailRationaleInput">Tail rationale</label>
          <input id="tailRationaleInput" value="${safe(draft?.rationale || "")}" ${draft ? "" : "disabled"} oninput="setTailDraft('rationale', this.value)" placeholder="required for governed preview" />
        </div>
        <button ${draft ? "" : "disabled"} onclick="clearTailDraft()">Clear</button>
      </div>
      <p class="empty">Constant tails are rerun by the deterministic backend. Log-linear tail smoothing remains unavailable until it has a governed reproducible implementation.</p>
    </section>
  `;
}

function stageTailType(type) {
  state.selectionDraft.tail = {
    type,
    factor: type === "constant" ? (state.selectionDraft.tail?.factor || "1.010") : null,
    rationale: state.selectionDraft.tail?.rationale || ""
  };
  state.selectionSetPreview = null;
  scheduleLivePreview();
  render();
}

function setTailDraft(field, value) {
  if (!state.selectionDraft.tail) return;
  state.selectionDraft.tail[field] = value;
  state.selectionSetPreview = null;
  if (field === "factor") scheduleLivePreview();
  refreshCommitButtonState();
}

function clearTailDraft() {
  state.selectionDraft.tail = null;
  state.selectionSetPreview = null;
  scheduleLivePreview();
  render();
}

function renderFactorPointPlot(row) {
  const detail = state.factorDetail;
  if (!detail?.available || String(detail.from_dev) !== String(row.from_dev)) {
    return '<p class="empty">Factor point plot is loading or unavailable for the selected development age.</p>';
  }
  const period = analysisPeriodForRow(row);
  const points = period?.points || detail.points || [];
  const displayedBases = displayedFactorBases(row);
  const fallbackCandidates = state.factorScale === "linear"
    ? (detail.candidate_lines || []).map((line) => ({ ...line, linear_y_pct: line.y_pct }))
    : [];
  const candidates = (period?.candidates || fallbackCandidates).filter((line) => line.available && displayedBases.includes(line.basis));
  const scale = state.factorScale;
  const yField = scale === "log" ? "log_y_pct" : "linear_y_pct";
  const previewOverlay = (state.selectionSetPreview?.factor_overlay || []).find((item) => String(item.from_dev) === String(row.from_dev));
  const previewY = previewOverlay?.[scale === "log" ? "selected_log_y_pct" : "selected_linear_y_pct"];
  const dragOverride = state.dragOverrides[String(row.from_dev)];
  const fittedLine = (period?.candidates || fallbackCandidates).find((line) => line.basis === "fitted");
  const dragY = dragOverride?.selected_graph?.[scale === "log" ? "log_y_pct" : "linear_y_pct"] ?? fittedLine?.[yField];
  const plot = period?.plot || {};
  const topLabel = scale === "log" ? plot.log_max : plot.linear_max;
  const bottomLabel = scale === "log" ? plot.log_min : plot.linear_min;
  return `
    <div class="factor-point-layout ${state.selectedFactorPoint && state.factorPointPanelOpen ? "has-detail" : ""}">
      <div class="factor-point-main">
        <div class="surface-header">
          <div>
            <p class="section-label">Observed link ratios and selected basis</p>
            <h3>Development Age ${safe(row.development_age)}</h3>
          </div>
          <div class="scale-selector" aria-label="Factor plot scale">
            <button class="${scale === "linear" ? "active" : ""}" onclick="setFactorScale('linear')">Linear</button>
            <button class="${scale === "log" ? "active" : ""}" onclick="setFactorScale('log')">Log</button>
          </div>
        </div>
        <div class="factor-chart-shell">
          <svg class="factor-analysis-chart" viewBox="0 0 1000 360" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Link ratios, candidate factors and governed preview overlay">
            <line class="chart-axis" x1="74" y1="28" x2="74" y2="312"></line>
            <line class="chart-axis" x1="74" y1="312" x2="954" y2="312"></line>
            ${[0, 25, 50, 75, 100].map((pct) => `<line class="chart-grid" x1="74" y1="${28 + pct * 2.84}" x2="954" y2="${28 + pct * 2.84}"></line>`).join("")}
            <text class="chart-axis-label" x="8" y="34">${fmtFactor(topLabel)}</text>
            <text class="chart-axis-label" x="8" y="316">${fmtFactor(bottomLabel)}</text>
            ${candidates.map((line) => {
              const y = line[yField];
              if (y === null || y === undefined) return "";
              const active = draftForRow(row)
                ? draftForRow(row).selected_basis === line.basis
                : line.basis === "fitted";
              return `
                <g class="candidate-line-control ${active ? "active" : ""}" style="--candidate-color:${candidateColor(line.basis)}">
                  <line x1="74" y1="${28 + Number(y) * 2.84}" x2="954" y2="${28 + Number(y) * 2.84}"></line>
                  <title>${safe(line.label)} ${fmtFactor(line.value)}</title>
                </g>
              `;
            }).join("")}
            ${dragY !== null && dragY !== undefined ? `
              <g class="manual-drag-control ${dragOverride ? "staged" : ""}">
                <line class="manual-drag-hit" x1="74" y1="${28 + Number(dragY) * 2.84}" x2="954" y2="${28 + Number(dragY) * 2.84}" onpointerdown="beginFactorDrag(event, '${safe(row.from_dev)}', 'selected_age', '${safe(scale)}')"></line>
                <line class="manual-factor-line" x1="74" y1="${28 + Number(dragY) * 2.84}" x2="954" y2="${28 + Number(dragY) * 2.84}"></line>
                <circle cx="90" cy="${28 + Number(dragY) * 2.84}" r="9" role="slider" tabindex="0" aria-label="Drag manual factor line to stage a manual override" onpointerdown="beginFactorDrag(event, '${safe(row.from_dev)}', 'selected_age', '${safe(scale)}')"></circle>
                <text x="104" y="${18 + Number(dragY) * 2.84}" text-anchor="start">${dragOverride ? `MANUAL ${fmtFactor(dragOverride.manual_factor)}` : "MANUAL OVERRIDE"}</text>
                <title>Drag the orange line vertically to stage a governed manual override</title>
              </g>
            ` : ""}
            ${previewY !== null && previewY !== undefined ? `
              <g class="preview-factor-line">
                <line x1="74" y1="${28 + Number(previewY) * 2.84}" x2="954" y2="${28 + Number(previewY) * 2.84}"></line>
                <text x="86" y="${20 + Number(previewY) * 2.84}">PREVIEW REFIT ${fmtFactor(previewOverlay.selected_factor)}</text>
              </g>
            ` : ""}
            ${points.map((point) => {
            const staged = isPointExclusionStaged(point);
            const selected = state.selectedFactorPoint?.point_id === point.point_id;
            const y = point[yField] ?? point.y_pct;
            const x = 74 + Number(point.x_pct || 50) * 8.8;
            const cy = 28 + Number(y || 50) * 2.84;
            const influential = point.influence?.high_influence;
            return `
              <g class="factor-svg-point ${point.excluded ? "excluded" : ""} ${staged ? "staged" : ""} ${selected ? "selected" : ""} ${influential ? "influential" : ""}" role="button" tabindex="0" onclick="selectFactorPoint('${safe(point.point_id)}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectFactorPoint('${safe(point.point_id)}')}">
                <circle cx="${x}" cy="${cy}" r="${selected ? 9 : influential ? 7 : 6}"></circle>
                ${point.excluded || staged ? `<text class="exclusion-mark" x="${x}" y="${cy + 4}" text-anchor="middle">×</text>` : ""}
                <text x="${x}" y="334" text-anchor="middle">${safe(point.origin)}</text>
                <title>${safe(point.origin)} · link ratio ${fmtFactor(point.link_ratio)}${staged ? " · exclusion staged" : point.excluded ? " · excluded" : ""}${point.influence?.delta_ibnr !== undefined ? ` · exclusion delta IBNR ${fmt(point.influence.delta_ibnr)}` : ""}</title>
              </g>
            `;
          }).join("")}
          </svg>
        </div>
        <div class="displayed-fitting-strip">
          <span class="section-label">Displayed fittings</span>
          ${candidates.map((line) => `
            <button style="--candidate-color:${candidateColor(line.basis)}" onclick="toggleFactorDisplay('${safe(row.from_dev)}', '${safe(line.basis)}')">
              <i></i><span>${safe(line.label)}</span><strong>${fmtFactor(line.value)}</strong><b>×</b>
            </button>
          `).join("") || '<span class="empty">No fitting lines displayed. Use the comparison controls below the all-development curve.</span>'}
        </div>
        <div class="plot-legend">
          <span><b class="legend-dot included"></b>included</span>
          <span><b class="legend-dot excluded"></b>excluded / staged</span>
          <span><b class="legend-dot influential"></b>high influence</span>
          <span><b class="legend-line"></b>displayed fitting</span>
          <span><b class="legend-line preview"></b>preview refit</span>
        </div>
      </div>
      ${state.selectedFactorPoint && state.factorPointPanelOpen ? `<aside class="factor-point-detail">
        <button class="unpin-point-detail" type="button" onclick="closeFactorPointPanel()" aria-label="Unpin point detail">Unpin ×</button>
        ${renderFactorPointInspector()}
      </aside>` : ""}
    </div>
  `;
}

function analysisPeriodForRow(row) {
  return (state.factorAnalysis?.development_periods || []).find((period) => String(period.from_dev) === String(row.from_dev));
}

function setFactorScale(scale) {
  state.factorScale = scale === "log" ? "log" : "linear";
  renderFactors();
}

async function openPerAgeGraph(fromDev, event) {
  event?.preventDefault();
  event?.stopPropagation();
  state.workbenchDisclosures.perAge = true;
  await selectDevelopmentAge(fromDev);
  window.setTimeout(() => document.querySelector(".factor-focus")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
}

function factorPointDrafts() {
  return state.selectionDraft.exclusions.points || [];
}

function isPointExclusionStaged(point) {
  return Boolean(factorPointDrafts().find((draft) =>
    (point.actions?.point_exclusion?.value && draft.value === point.actions.point_exclusion.value) ||
    (
      String(draft.origin) === String(point.origin) &&
      String(draft.from_dev) === String(point.from_dev)
    )
  ));
}

function selectFactorPoint(pointId, renderAfter = true) {
  const detailPoint = (state.factorDetail?.points || []).find((item) => item.point_id === pointId);
  const analysisPoint = (state.factorAnalysis?.development_periods || [])
    .flatMap((period) => period.points || [])
    .find((item) => item.point_id === pointId);
  state.selectedFactorPoint = detailPoint ? { ...detailPoint, influence: analysisPoint?.influence } : analysisPoint || null;
  state.factorPointPanelOpen = Boolean(state.selectedFactorPoint);
  if (renderAfter) {
    renderFactors();
    renderValidationDrawer();
  }
}

function closeFactorPointPanel() {
  state.factorPointPanelOpen = false;
  renderFactors();
  renderValidationDrawer();
}

function renderFactorPointInspector() {
  const point = state.selectedFactorPoint;
  if (!point) return '<p class="empty">Select a point to inspect origin, link ratio, and supported exclusion actions.</p>';
  const staged = isPointExclusionStaged(point);
  const stagedDraft = factorPointDrafts().find((draft) => draft.value === point.actions?.point_exclusion?.value);
  const rationaleStatus = stagedDraft?.rationale?.trim() ? "present" : "required";
  return `
    <div class="surface-header">
      <h3>Point Detail</h3>
      <span class="${badgeClass(staged ? "staged" : point.excluded ? "blocked" : "active")}">${staged ? "staged exclusion" : point.excluded ? "excluded" : "included"}</span>
    </div>
    <dl class="checklist">
      <div class="check-row"><span></span><strong>Origin</strong><span>${safe(point.origin)}</span></div>
      <div class="check-row"><span></span><strong>Age</strong><span>${safe(point.development_age)}</span></div>
      <div class="check-row"><span></span><strong>Link ratio</strong><span>${fmtFactor(point.link_ratio)}</span></div>
      <div class="check-row"><span></span><strong>Source artifact</strong><span>${safe(point.source_artifact || "fit.json")}</span></div>
      <div class="check-row"><span></span><strong>Included status</strong><span>${point.included && !staged ? "included" : "excluded / staged"}</span></div>
      <div class="check-row"><span></span><strong>Staged action</strong><span>${staged ? "factor_point exclusion" : "none"}</span></div>
      <div class="check-row"><span></span><strong>Rationale</strong><span>${staged ? rationaleStatus : "n/a"}</span></div>
      <div class="check-row"><span></span><strong>Influence rank</strong><span>${safe(point.influence?.rank || "not ranked")}</span></div>
      <div class="check-row"><span></span><strong>Exclusion delta factor</strong><span>${fmtFactor(point.influence?.delta_factor)}</span></div>
      <div class="check-row"><span></span><strong>Exclusion delta IBNR</strong><span>${fmt(point.influence?.delta_ibnr)}</span></div>
    </dl>
    <div class="row-actions" style="margin-top: 14px;">
      <button onclick="stageFactorPointExclusion('${safe(point.point_id)}')">${staged ? "Point staged" : "Stage point exclusion"}</button>
      <button onclick="stageOriginExclusionFromCell('${safe(point.origin)}')">Stage origin</button>
      <button onclick="stageValuationExclusionFromCell('${safe(point.to_dev)}')">Stage valuation</button>
      <button onclick="clearFactorPointExclusion('${safe(point.actions?.point_exclusion?.value)}')">Clear point</button>
    </div>
    <p class="empty" style="margin-top: 10px;">Point exclusions are staged until a governed selection-set preview is committed.</p>
  `;
}

function stageFactorPointExclusion(pointId) {
  const point = (state.factorDetail?.points || []).find((item) => item.point_id === pointId);
  const action = point?.actions?.point_exclusion;
  if (!point || !action?.supported) {
    showToast(action?.reason || "Point exclusion is unavailable for this factor point.");
    return;
  }
  if (!isPointExclusionStaged(point)) {
    state.selectionDraft.exclusions.points.push({
      type: "factor_point",
      value: action.value,
      origin: action.origin,
      from_dev: action.from_dev,
      to_dev: action.to_dev,
      development_age: action.development_age,
      link_ratio: point.link_ratio,
      rationale: ""
    });
  }
  state.selectionSetPreview = null;
  scheduleLivePreview();
  showToast("Factor point exclusion staged.");
  render();
}

function clearFactorPointExclusion(value) {
  state.selectionDraft.exclusions.points = factorPointDrafts().filter((point) => point.value !== value);
  state.selectionSetPreview = null;
  scheduleLivePreview();
  render();
}

function setPointExclusionRationale(value, rationale) {
  const point = factorPointDrafts().find((draft) => draft.value === value);
  if (point) point.rationale = rationale;
  state.selectionSetPreview = null;
  refreshCommitButtonState();
}

function stageManualOverride(fromDev) {
  const row = (state.factors?.factors || []).find((item) => String(item.from_dev) === String(fromDev));
  if (!row) return;
  const rawValue = $("manualFactorInput")?.value.trim() || "";
  const rationale = $("manualRationaleInput")?.value.trim() || "";
  const selectedFactor = Number(rawValue);
  if (!Number.isFinite(selectedFactor) || selectedFactor <= 0) {
    showToast("Manual override must be a positive numeric factor.");
    return;
  }
  if (state.workflowMode === "governed" && !rationale) {
    showToast("Manual override requires rationale.");
    return;
  }
  state.selectionDraft.factors[String(row.from_dev)] = {
    development_age: row.development_age,
    from_dev: row.from_dev,
    to_dev: row.to_dev,
    previous_factor: row.selected_factor,
    selected_factor: selectedFactor,
    selected_basis: "manual_override",
    manual_override: true,
    selection_source: "manual",
    rationale
  };
  delete state.dragOverrides[String(row.from_dev)];
  state.selectionSetPreview = null;
  scheduleLivePreview();
  showToast("Manual override staged.");
  render();
}

let activeFactorDrag = null;

function beginFactorDrag(event, fromDev, graph, scale) {
  event.preventDefault();
  event.stopPropagation();
  const handle = event.currentTarget;
  const svg = handle.ownerSVGElement || handle.closest?.("svg");
  if (!svg) return;
  if (handle.setPointerCapture && event.pointerId !== undefined) handle.setPointerCapture(event.pointerId);
  activeFactorDrag = { fromDev, graph, scale, svg, handle, pointerId: event.pointerId, startClientY: event.clientY };
  document.body.classList.add("factor-dragging");
  window.addEventListener("pointermove", previewFactorDrag);
  window.addEventListener("pointerup", finishFactorDrag, { once: true });
  window.addEventListener("pointercancel", cancelFactorDrag, { once: true });
}

function previewFactorDrag(event) {
  const drag = activeFactorDrag;
  if (!drag || (drag.pointerId !== undefined && event.pointerId !== drag.pointerId)) return;
  const rect = drag.svg.getBoundingClientRect();
  if (rect.height <= 0) return;
  const viewBoxHeight = drag.graph === "selected_age" ? 360 : 310;
  let previewY = ((event.clientY - rect.top) / rect.height) * viewBoxHeight;
  const minY = drag.graph === "selected_age" ? 28 : 35;
  const maxY = drag.graph === "selected_age" ? 312 : 250;
  if (previewY < minY) previewY = minY;
  if (previewY > maxY) previewY = maxY;
  drag.previewY = previewY;

  if (drag.graph === "all_development") {
    drag.handle.setAttribute("cy", String(previewY));
    return;
  }

  drag.svg.querySelectorAll(".manual-drag-hit, .manual-factor-line").forEach((line) => {
    line.setAttribute("y1", String(previewY));
    line.setAttribute("y2", String(previewY));
  });
  const handle = drag.svg.querySelector(".manual-drag-control circle");
  if (handle) handle.setAttribute("cy", String(previewY));
  const label = drag.svg.querySelector(".manual-drag-control text");
  if (label) {
    label.setAttribute("y", String(previewY - 10));
    label.textContent = "MANUAL PREVIEW";
  }
}

function cancelFactorDrag() {
  activeFactorDrag = null;
  document.body.classList.remove("factor-dragging");
  window.removeEventListener("pointermove", previewFactorDrag);
  window.removeEventListener("pointerup", finishFactorDrag);
}

async function finishFactorDrag(event) {
  const drag = activeFactorDrag;
  activeFactorDrag = null;
  document.body.classList.remove("factor-dragging");
  window.removeEventListener("pointermove", previewFactorDrag);
  window.removeEventListener("pointercancel", cancelFactorDrag);
  if (!drag || !state.runId) return;
  if (drag.handle.releasePointerCapture && drag.handle.hasPointerCapture?.(drag.pointerId)) {
    drag.handle.releasePointerCapture(drag.pointerId);
  }
  const dragDistance = event.clientY - drag.startClientY;
  if (dragDistance > -4 && dragDistance < 4) return;
  const rect = drag.svg.getBoundingClientRect();
  try {
    const mapped = await api(`/api/runs/${encodeURIComponent(state.runId)}/chain-ladder/factor-drag`, {
      method: "POST",
      body: JSON.stringify({
        from_dev: drag.fromDev,
        graph: drag.graph,
        scale: drag.scale,
        client_y: event.clientY,
        rect_top: rect.top,
        rect_height: rect.height
      })
    });
    const existing = state.selectionDraft.factors[String(mapped.from_dev)] || {};
    state.dragOverrides[String(mapped.from_dev)] = mapped;
    state.selectionDraft.factors[String(mapped.from_dev)] = {
      development_age: mapped.development_age,
      from_dev: mapped.from_dev,
      to_dev: mapped.to_dev,
      previous_factor: mapped.base_factor,
      selected_factor: mapped.manual_factor,
      selected_basis: "manual_override",
      manual_override: true,
      selection_source: "drag",
      rationale: existing.rationale || ""
    };
    state.selectionSetPreview = null;
    scheduleLivePreview();
    showToast(`Manual override ${fmtFactor(mapped.manual_factor)} staged. Rationale and preview required.`);
    render();
  } catch (error) {
    showToast(error.message);
  }
}

function renderFactorTable(rows) {
  return `
    <section class="surface">
      <div class="surface-header">
        <h3>Development Table</h3>
        <span class="pill">read-only base / draft overlay</span>
      </div>
      <div class="triangle-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Development Age</th>
              <th>Base Fitted</th>
              <th>Draft Selected</th>
              <th>Volume Wtd.</th>
              <th>Simple Avg.</th>
              <th>Last 3</th>
              <th>Last 5</th>
              <th>Trimmed</th>
              <th>Median</th>
              <th>Cumulative</th>
              <th>Basis</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => {
              const draft = draftForRow(row);
              const selected = String(row.from_dev) === String(state.selectedDevelopmentAge);
              return `
                <tr class="${selected ? "selected-factor-row" : ""}">
                  <td><button class="text-button" onclick="selectDevelopmentAge('${safe(row.from_dev)}')">${safe(row.development_age || "not available")}</button></td>
                  <td>${fmtFactor(row.fitted_factor ?? row.selected_factor)}</td>
                  <td>${draft ? fmtFactor(draft.selected_factor) : fmtFactor(row.selected_factor)}</td>
                  <td>${fmtFactor(row.candidate_averages?.volume_weighted)}</td>
                  <td>${fmtFactor(row.candidate_averages?.simple_average)}</td>
                  <td>${fmtFactor(row.candidate_averages?.last_3)}</td>
                  <td>${fmtFactor(row.candidate_averages?.last_5)}</td>
                  <td>${fmtFactor(row.candidate_averages?.trimmed_mean)}</td>
                  <td>${fmtFactor(row.candidate_averages?.median)}</td>
                  <td>${fmtFactor(row.cumulative_development_factor)}</td>
                  <td>${safe(draft ? factorBasisLabel(draft.selected_basis) : row.factor_basis || "not available")}</td>
                  <td><button onclick="selectDevelopmentAge('${safe(row.from_dev)}')">Review</button></td>
                </tr>
              `;
            }).join("") || '<tr><td colspan="12">not available</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

async function selectDevelopmentAge(fromDev) {
  state.selectedDevelopmentAge = String(fromDev);
  state.selectedFactorPoint = null;
  await loadFactorDetail(fromDev);
}

function selectFactorCandidate(fromDev, basis) {
  const row = (state.factors?.factors || []).find((item) => String(item.from_dev) === String(fromDev));
  if (!row) return;
  const card = (row.candidate_cards || []).find((item) => item.basis === basis);
  if (!card?.available) return;
  if (!state.factorCurveSeries.includes(basis)) {
    state.factorCurveSeries = [...state.factorCurveSeries, basis];
  }
  if (basis === "fitted") {
    delete state.selectionDraft.factors[String(row.from_dev)];
    delete state.dragOverrides[String(row.from_dev)];
    state.selectionSetPreview = null;
    scheduleLivePreview();
    showToast("Development age restored to the current fitted basis.");
    render();
    return;
  }
  state.selectionDraft.factors[String(row.from_dev)] = {
    development_age: row.development_age,
    from_dev: row.from_dev,
    to_dev: row.to_dev,
    previous_factor: row.selected_factor,
    selected_factor: card.value,
    selected_basis: basis,
    rationale: state.selectionDraft.factors[String(row.from_dev)]?.rationale || ""
  };
  delete state.dragOverrides[String(row.from_dev)];
  state.selectionSetPreview = null;
  scheduleLivePreview();
  showToast(`${factorBasisLabel(basis)} staged for governed preview.`);
  render();
}

function removeDraftFactor(fromDev) {
  delete state.selectionDraft.factors[String(fromDev)];
  delete state.dragOverrides[String(fromDev)];
  state.selectionSetPreview = null;
  scheduleLivePreview();
  render();
}

function setDraftFactorRationale(fromDev, value) {
  if (state.selectionDraft.factors[String(fromDev)]) {
    state.selectionDraft.factors[String(fromDev)].rationale = value;
  }
  state.selectionSetPreview = null;
  refreshCommitButtonState();
}

function setDraftExclusion(field, value) {
  state.selectionDraft.exclusions[field] = value;
  state.selectionSetPreview = null;
  if (field === "origins" || field === "valuations") scheduleLivePreview();
  refreshCommitButtonState();
}

function setCommitMeta(field, value) {
  state.commitMeta[field] = value;
  if (field === "userId") localStorage.setItem("reserveUserId", value || "");
  if (field === "displayName") localStorage.setItem("reserveDisplayName", value || "");
  refreshCommitButtonState();
}

function setExploreMeta(field, value) {
  state.exploreMeta[field] = value;
}

function syncCommitMetaFromInputs() {
  state.commitMeta.globalRationale = $("v2GlobalRationale")?.value.trim() ?? state.commitMeta.globalRationale;
  state.commitMeta.userId = $("v2FactorUserId")?.value.trim() ?? state.commitMeta.userId;
  state.commitMeta.displayName = $("v2FactorDisplayName")?.value.trim() ?? state.commitMeta.displayName;
  localStorage.setItem("reserveUserId", state.commitMeta.userId || "");
  localStorage.setItem("reserveDisplayName", state.commitMeta.displayName || "");
}

function exclusionsHaveRationale() {
  const exclusions = state.selectionDraft.exclusions;
  if (commaValues(exclusions.origins).length && !String(exclusions.originRationale || "").trim()) return false;
  if (commaValues(exclusions.valuations).length && !String(exclusions.valuationRationale || "").trim()) return false;
  for (const point of factorPointDrafts()) {
    if (!String(point.rationale || "").trim()) return false;
  }
  return true;
}

function tailHasRationale() {
  return !state.selectionDraft.tail || Boolean(String(state.selectionDraft.tail.rationale || "").trim());
}

function factorsHaveRationale() {
  for (const factor of draftFactors()) {
    if (!String(factor.rationale || "").trim()) return false;
  }
  return true;
}

function canCommitSelectionSet() {
  if (!state.selectionSetPreview) return false;
  if (!String(state.commitMeta.globalRationale || "").trim()) return false;
  if (!String(state.commitMeta.userId || "").trim()) return false;
  if (!String(state.commitMeta.displayName || "").trim()) return false;
  if (!factorsHaveRationale()) return false;
  if (!exclusionsHaveRationale()) return false;
  if (!tailHasRationale()) return false;
  return true;
}

function refreshCommitButtonState() {
  const button = $("commitSelectionSetButton");
  if (button) button.disabled = !canCommitSelectionSet();
}

function renderSelectionScenarioPanel() {
  const factors = draftFactors();
  const exclusions = state.selectionDraft.exclusions;
  const governedPreview = state.selectionSetPreview;
  const preview = state.workflowMode === "explore" ? state.explorePreview : governedPreview || state.livePreview;
  const globalRationale = state.commitMeta.globalRationale || governedPreview?.global_rationale || "";
  const userId = state.commitMeta.userId || localStorage.getItem("reserveUserId") || "";
  const displayName = state.commitMeta.displayName || localStorage.getItem("reserveDisplayName") || "";
  const workflow = selectionWorkflowState();
  const blockers = commitBlockers();
  const hasStagedWork = factors.length || factorPointDrafts().length || commaValues(exclusions.origins).length || commaValues(exclusions.valuations).length || state.selectionDraft.tail || preview;
  const selectionOpen = state.workbenchDisclosures.selection;
  return `
    <details class="selection-panel" ${selectionOpen ? "open" : ""} ontoggle="setWorkbenchDisclosure('selection', this.open)">
      <summary>
        <div>
          <p class="section-label">Selection scenario</p>
          <h3>Staged Control Checklist</h3>
          <p class="empty">Selected development age: ${safe(selectedFactorRow(state.factors?.factors || [])?.development_age || "n/a")}</p>
        </div>
        <div class="state-chip-stack">
          <span class="${badgeClass(workflow.key)}">${safe(workflow.label)}</span>
          <small>${safe(hasStagedWork ? workflow.detail : "No governed selection staged")}</small>
        </div>
      </summary>
      <div class="selection-panel-content">
        <div class="workspace-grid">
        <div>
          <h3>Pending Factor Changes</h3>
          <div class="draft-list">
            ${factors.map(renderDraftFactor).join("") || '<p class="empty">No factor changes staged.</p>'}
            ${state.selectionDraft.tail ? `<article class="draft-item"><strong>Tail ${safe(state.selectionDraft.tail.type)}</strong><span>${safe(state.selectionDraft.tail.factor || "none")}</span><span>${safe(state.selectionDraft.tail.rationale || "rationale missing")}</span></article>` : ""}
          </div>
        </div>
        <div class="form-grid">
          <h3>Exclusions</h3>
          <div class="form-row">
            <label for="v2OriginExclusions">Origin years</label>
            <input id="v2OriginExclusions" value="${safe(exclusions.origins || "")}" placeholder="comma-separated" oninput="setDraftExclusion('origins', this.value)" />
          </div>
          <div class="form-row">
            <label for="v2OriginRationale">Origin exclusion rationale</label>
            <textarea id="v2OriginRationale" oninput="setDraftExclusion('originRationale', this.value)">${safe(exclusions.originRationale || "")}</textarea>
          </div>
          <div class="form-row">
            <label for="v2ValuationExclusions">Valuation/development years</label>
            <input id="v2ValuationExclusions" value="${safe(exclusions.valuations || "")}" placeholder="comma-separated" oninput="setDraftExclusion('valuations', this.value)" />
          </div>
          <div class="form-row">
            <label for="v2ValuationRationale">Valuation exclusion rationale</label>
            <textarea id="v2ValuationRationale" oninput="setDraftExclusion('valuationRationale', this.value)">${safe(exclusions.valuationRationale || "")}</textarea>
          </div>
          <h3>Factor Point Exclusions</h3>
          <div class="draft-list">
            ${factorPointDrafts().map(renderPointExclusionDraft).join("") || '<p class="empty">No factor points staged.</p>'}
          </div>
        </div>
        </div>
        ${renderPreviewImpactPanel(preview)}
        <div class="form-grid" style="margin-top: 14px;">
          ${state.workflowMode === "explore" ? renderExploreControls() : renderGovernedControls(governedPreview, globalRationale, userId, displayName, blockers)}
        </div>
      </div>
    </details>
  `;
}

function renderExploreControls() {
  return `
    <div class="two-column">
      <div class="form-row">
        <label for="v2ExploreName">Explore scenario name</label>
        <input id="v2ExploreName" value="${safe(state.exploreMeta.name || "")}" oninput="setExploreMeta('name', this.value)" />
      </div>
      <div class="form-row">
        <label for="v2ExploreNotes">Explore notes</label>
        <input id="v2ExploreNotes" value="${safe(state.exploreMeta.notes || "")}" oninput="setExploreMeta('notes', this.value)" placeholder="optional while exploring" />
      </div>
    </div>
    <div class="row-actions">
      <button onclick="previewExploreScenario()">Preview Explore</button>
      <button onclick="previewExploreScenario()">Save Study</button>
      <button class="primary-button" ${state.explorePreview ? "" : "disabled"} onclick="promoteExploreToGovernedDraft()">Promote to Governed Selection</button>
    </div>
    <p class="empty">Explore freely. Promote deliberately. Only governed selections enter the report pack.</p>
  `;
}

function renderGovernedControls(preview, globalRationale, userId, displayName, blockers) {
  return `
        <div class="form-row">
          <label for="v2GlobalRationale">Global rationale</label>
          <textarea id="v2GlobalRationale" oninput="setCommitMeta('globalRationale', this.value)">${safe(globalRationale)}</textarea>
        </div>
        <div class="two-column">
          <div class="form-row">
            <label for="v2FactorUserId">User id</label>
            <input id="v2FactorUserId" value="${safe(userId)}" oninput="setCommitMeta('userId', this.value)" />
          </div>
          <div class="form-row">
            <label for="v2FactorDisplayName">Display name</label>
            <input id="v2FactorDisplayName" value="${safe(displayName)}" oninput="setCommitMeta('displayName', this.value)" />
          </div>
        </div>
        <div class="commit-prereqs">
          ${renderCommitPrerequisite("Preview exists", Boolean(preview))}
          ${renderCommitPrerequisite("Global rationale", Boolean(String(globalRationale).trim()))}
          ${renderCommitPrerequisite("Factor rationales", factorsHaveRationale())}
          ${renderCommitPrerequisite("Exclusion rationales", exclusionsHaveRationale())}
          ${renderCommitPrerequisite("Tail rationale", tailHasRationale())}
          ${renderCommitPrerequisite("User identity", Boolean(String(userId).trim() && String(displayName).trim()))}
        </div>
        <div class="commit-blockers">
          ${blockers.map((reason) => `<span>${safe(reason)}</span>`).join("") || '<span class="ready">commit enabled</span>'}
        </div>
        <div class="row-actions">
          <button onclick="previewSelectionSet()">Preview Scenario</button>
          <button id="commitSelectionSetButton" class="primary-button" title="${safe(blockers.join(", ") || "ready to commit")}" ${canCommitSelectionSet() ? "" : "disabled"} onclick="commitSelectionSet()">Commit Selection Set</button>
        </div>
  `;
}

function renderCommitPrerequisite(label, complete) {
  return `<span class="${complete ? "ready" : "pending"}">${safe(label)}</span>`;
}

function renderPointExclusionDraft(point) {
  return `
    <article class="draft-item point-draft">
      <div class="surface-header">
        <strong>${safe(point.origin)} / ${safe(point.development_age || point.from_dev)}</strong>
        <span class="${badgeClass(point.rationale?.trim() ? "complete" : "pending")}">${point.rationale?.trim() ? "rationale" : "missing rationale"}</span>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Link ratio</strong><span>${fmtFactor(point.link_ratio)}</span></div>
        <div class="check-row"><span></span><strong>Exclusion type</strong><span>factor point</span></div>
      </div>
      <div class="form-row" style="margin-top: 8px;">
        <label>Point exclusion rationale</label>
        <textarea oninput="setPointExclusionRationale('${safe(point.value)}', this.value)">${safe(point.rationale || "")}</textarea>
      </div>
      <button onclick="clearFactorPointExclusion('${safe(point.value)}')">Clear point</button>
    </article>
  `;
}

function renderDraftFactor(draft) {
  const rationaleStatus = draft.rationale?.trim() ? "present" : "missing";
  return `
    <article class="draft-item">
      <div class="surface-header">
        <strong>${safe(draft.development_age)}</strong>
        <span class="${badgeClass(rationaleStatus === "present" ? "complete" : "pending")}">${safe(rationaleStatus)}</span>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Previous factor</strong><span>${fmtFactor(draft.previous_factor)}</span></div>
        <div class="check-row"><span></span><strong>Selected factor</strong><span>${fmtFactor(draft.selected_factor)}</span></div>
        <div class="check-row"><span></span><strong>Basis</strong><span>${safe(factorBasisLabel(draft.selected_basis))}</span></div>
      </div>
      <div class="form-row" style="margin-top: 8px;">
        <label>Rationale</label>
        <textarea oninput="setDraftFactorRationale('${safe(draft.from_dev)}', this.value)">${safe(draft.rationale || "")}</textarea>
      </div>
      <button onclick="removeDraftFactor('${safe(draft.from_dev)}')">Remove</button>
    </article>
  `;
}

function renderPreviewImpactPanel(preview) {
  if (!preview) {
    return `
      <section class="preview-impact-panel">
        <div class="surface-header">
          <div>
            <p class="section-label">Preview impact</p>
            <h3>No preview available</h3>
          </div>
          <span class="${badgeClass("draft")}">not previewed</span>
        </div>
        <p class="empty">Stage a factor basis, manual override, or exclusion, then request a governed preview to see base-vs-selected impact.</p>
      </section>
    `;
  }
  const comparison = preview.comparison || preview.preview_result?.comparison || {};
  const previewResult = preview.preview_result || {};
  const base = comparison.base || {
    ultimate: previewResult.base_ultimate,
    ibnr: previewResult.base_ibnr
  };
  const candidate = comparison.candidate || {
    ultimate: previewResult.selected_ultimate,
    ibnr: previewResult.selected_ibnr
  };
  const deltas = comparison.deltas || {
    ultimate: previewResult.delta_ultimate,
    ibnr: previewResult.delta_ibnr,
    ibnr_pct: previewResult.delta_ibnr_pct
  };
  const transient = preview.preview_kind === "transient";
  const previewId = transient ? "live deterministic calculation" : preview.preview_scenario_id || preview.explore_scenario_id || "preview";
  return `
    <section class="preview-impact-panel">
      <div class="surface-header">
        <div>
          <p class="section-label">Preview impact</p>
          <h3>Base vs Selected Scenario</h3>
        </div>
        <span class="${badgeClass(transient || preview.mode === "explore" ? "not_governed" : "ready")}">${safe(previewId)}</span>
      </div>
      <div class="preview-metrics">
        <div><span>Base ultimate</span><strong>${fmt(base.ultimate)}</strong></div>
        <div><span>Selected ultimate</span><strong>${fmt(candidate.ultimate)}</strong></div>
        <div><span>Delta ultimate</span><strong>${fmt(deltas.ultimate)}</strong></div>
        <div><span>Base IBNR</span><strong>${fmt(base.ibnr)}</strong></div>
        <div><span>Selected IBNR</span><strong>${fmt(candidate.ibnr)}</strong></div>
        <div><span>Delta IBNR</span><strong>${fmt(deltas.ibnr)}</strong></div>
      </div>
      ${transient ? '<p class="empty">Live values are a transient backend rerun. A governed Preview Scenario is still required before commit.</p>' : ""}
      ${renderOriginImpact(preview)}
    </section>
  `;
}

function renderOriginImpact(preview) {
  const rows = preview?.comparison?.by_origin_ibnr_impact || preview?.preview_result?.by_origin_ibnr_impact || [];
  if (!rows.length) return '<p class="empty">By-origin scenario impact is not available until a preview exists.</p>';
  return `
    <section class="surface">
      <div class="surface-header">
        <h3>By-Origin Impact</h3>
        <span class="pill">${safe(preview.preview_scenario_id || preview.scenario_id)}</span>
      </div>
      <div class="triangle-table-wrap">
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
    </section>
  `;
}

function selectionSetRequest(user, globalRationale) {
  const exclusions = [];
  const draft = state.selectionDraft.exclusions;
  commaValues(draft.origins).forEach((value) => {
    exclusions.push({ type: "origin", value, rationale: draft.originRationale });
  });
  commaValues(draft.valuations).forEach((value) => {
    exclusions.push({ type: "valuation", value, rationale: draft.valuationRationale });
  });
  factorPointDrafts().forEach((point) => {
    exclusions.push({
      type: "factor_point",
      value: point.value,
      origin: point.origin,
      from_dev: point.from_dev,
      to_dev: point.to_dev,
      development_age: point.development_age,
      rationale: point.rationale
    });
  });
  const suggestionDispositions = Object.entries(state.suggestionDispositions).map(([suggestionId, status]) => ({
    suggestion_id: suggestionId,
    status,
    rationale: status === "dismissed" ? "Dismissed after actuarial inspection" : "Reviewed against deterministic evidence"
  }));
  return {
    factor_selections: draftFactors().map((factor) => ({
      development_age: factor.development_age,
      from_dev: factor.from_dev,
      selected_basis: factor.selected_basis,
      selected_factor: factor.selected_factor,
      rationale: factor.rationale
    })),
    exclusions,
    tail_selection: state.selectionDraft.tail ? {
      type: state.selectionDraft.tail.type,
      factor: state.selectionDraft.tail.type === "constant" ? Number(state.selectionDraft.tail.factor) : null,
      rationale: state.selectionDraft.tail.rationale
    } : null,
    global_rationale: globalRationale,
    created_by: user,
    source_explore_scenario_id: state.selectedExploreScenarioId,
    factor_analysis_id: state.factorAnalysis?.analysis_id || null,
    reviewed_suggestion_ids: suggestionDispositions.map((item) => item.suggestion_id),
    suggestion_dispositions: suggestionDispositions
  };
}

function exploreScenarioRequest() {
  const governed = selectionSetRequest({}, state.exploreMeta.notes || "");
  const factorSelections = governed.factor_selections || [];
  return {
    explore_scenario_id: state.selectedExploreScenarioId,
    name: state.exploreMeta.name || "Exploratory scenario",
    notes: state.exploreMeta.notes || "",
    factor_selections: factorSelections.filter((factor) => factor.selected_basis !== "manual_override"),
    manual_overrides: factorSelections.filter((factor) => factor.selected_basis === "manual_override"),
    exclusions: governed.exclusions || []
  };
}

async function previewExploreScenario() {
  if (!state.runId) return null;
  const run = encodeURIComponent(state.runId);
  try {
    state.explorePreview = await api(`/api/runs/${run}/explore/preview`, {
      method: "POST",
      body: JSON.stringify(exploreScenarioRequest())
    });
    state.selectedExploreScenarioId = state.explorePreview.explore_scenario_id;
    state.exploreScenarios = await api(`/api/runs/${run}/explore`);
    state.readiness = await api(`/api/runs/${run}/report-readiness`);
    showToast("Explore scenario saved. Not governed.");
    render();
    return state.explorePreview;
  } catch (error) {
    showToast(error.message);
    return null;
  }
}

async function approveExploreAndContinue() {
  if (!state.runId || state.workflowMode !== "explore") return;
  const button = $("approveExploreButton");
  if (button) {
    button.disabled = true;
    button.classList.add("busy");
  }
  try {
    let scenario = state.explorePreview;
    if (!scenario) scenario = await previewExploreScenario();
    if (!scenario) return;

    const storedUserId = state.commitMeta.userId || localStorage.getItem("reserveUserId") || "";
    const storedDisplayName = state.commitMeta.displayName || localStorage.getItem("reserveDisplayName") || "";
    const userId = storedUserId || window.prompt("User ID required for governed approval:", "")?.trim();
    if (!userId) throw new Error("Approval cancelled: user ID is required.");
    const displayName = storedDisplayName || window.prompt("Display name required for governed approval:", "")?.trim();
    if (!displayName) throw new Error("Approval cancelled: display name is required.");
    const existingRationale = state.exploreMeta.notes || scenario.notes || state.commitMeta.globalRationale || "";
    const globalRationale = existingRationale || window.prompt("Approval rationale:", "Approved explored factor selection for governed reporting.")?.trim();
    if (!globalRationale) throw new Error("Approval cancelled: rationale is required.");

    state.commitMeta = { globalRationale, userId, displayName };
    localStorage.setItem("reserveUserId", userId);
    localStorage.setItem("reserveDisplayName", displayName);
    const activeSelectionApproval = activeDecisionOfType("selection_set_approval");
    const run = encodeURIComponent(state.runId);
    const result = await api(`/api/runs/${run}/explore/${encodeURIComponent(scenario.explore_scenario_id)}/promote`, {
      method: "POST",
      body: JSON.stringify({
        global_rationale: globalRationale,
        created_by: { id: userId, display_name: displayName },
        decision_id: `selection_set_approval_${Date.now().toString(36)}`,
        supersedes_decision_id: activeSelectionApproval?.decision_id || null
      })
    });
    const handoff = await api(`/api/runs/${run}/handoff`);
    state.workflowMode = "governed";
    state.activeTab = "report";
    state.explorePreview = null;
    state.selectionDraft = emptySelectionDraft();
    await refreshRun();
    state.activeTab = "report";
    render();
    const selectionId = result.promotion?.selection_set?.selection_set_id || "selection";
    showToast(`Approved ${selectionId}. AI handoff ready: ${handoff.resume_command || `/review ${state.runId}`}`);
  } catch (error) {
    showToast(error.message);
  } finally {
    const currentButton = $("approveExploreButton");
    if (currentButton) {
      currentButton.disabled = false;
      currentButton.classList.remove("busy");
    }
  }
}

function promoteExploreToGovernedDraft() {
  const scenario = state.explorePreview || (exploreScenarios().find((item) => item.explore_scenario_id === state.selectedExploreScenarioId));
  if (!scenario) {
    showToast("Preview or select an explore scenario first.");
    return;
  }
  state.workflowMode = "governed";
  state.selectedExploreScenarioId = scenario.explore_scenario_id;
  state.commitMeta.globalRationale = state.commitMeta.globalRationale || scenario.notes || "";
  const factors = [...(scenario.factor_selections || []), ...(scenario.manual_overrides || [])];
  factors.forEach((factor) => {
    state.selectionDraft.factors[String(factor.from_dev)] = {
      ...factor,
      rationale: factor.rationale || scenario.notes || ""
    };
  });
  const exclusions = state.selectionDraft.exclusions;
  (scenario.origin_exclusions || []).forEach((item) => {
    exclusions.origins = addCommaValue(exclusions.origins, item.value);
    exclusions.originRationale = exclusions.originRationale || item.rationale || scenario.notes || "";
  });
  (scenario.valuation_exclusions || []).forEach((item) => {
    exclusions.valuations = addCommaValue(exclusions.valuations, item.value);
    exclusions.valuationRationale = exclusions.valuationRationale || item.rationale || scenario.notes || "";
  });
  state.selectionDraft.exclusions.points = (scenario.factor_point_exclusions || []).map((item) => ({
    ...item,
    type: "factor_point",
    rationale: item.rationale || scenario.notes || ""
  }));
  state.selectionSetPreview = null;
  state.explorePreview = null;
  scheduleLivePreview();
  showToast("Explore assumptions copied into GOVERNED draft. Preview and commit are still required.");
  render();
}

async function previewSelectionSet() {
  if (!state.runId) return;
  clearLivePreview();
  syncCommitMetaFromInputs();
  const user = {
    id: state.commitMeta.userId || null,
    display_name: state.commitMeta.displayName || null
  };
  const globalRationale = state.commitMeta.globalRationale || "";
  localStorage.setItem("reserveUserId", user.id || "");
  localStorage.setItem("reserveDisplayName", user.display_name || "");
  const request = selectionSetRequest(user, globalRationale);
  const run = encodeURIComponent(state.runId);
  try {
    state.selectionSetPreview = await api(`/api/runs/${run}/selection-sets/preview`, {
      method: "POST",
      body: JSON.stringify(request)
    });
    state.selectedScenarioId = state.selectionSetPreview.preview_scenario_id;
    showToast("Scenario preview created.");
    await loadArtifacts();
    render();
  } catch (error) {
    showToast(error.message);
  }
}

async function commitSelectionSet() {
  const preview = state.selectionSetPreview;
  if (!preview) return;
  syncCommitMetaFromInputs();
  if (!canCommitSelectionSet()) {
    showToast("Commit requires preview, rationales, and user identity.");
    return;
  }
  const user = {
    id: state.commitMeta.userId || null,
    display_name: state.commitMeta.displayName || null
  };
  const globalRationale = state.commitMeta.globalRationale || preview.global_rationale || "";
  const run = encodeURIComponent(state.runId);
  try {
    const reviewed = Array.from(new Set([...(preview.source_artifacts || []), preview.selection_set_artifact]));
    const approvalDecisionId = `selection_set_approval_${Date.now().toString(36)}`;
    const activeSelectionApproval = activeDecisionOfType("selection_set_approval");
    const committed = await api(`/api/runs/${run}/selection-sets/${encodeURIComponent(preview.selection_set_id)}/commit`, {
      method: "POST",
      body: JSON.stringify({
        global_rationale: globalRationale,
        created_by: user,
        decision: {
          schema_version: "0.1",
          decision_id: approvalDecisionId,
          run_id: state.runId,
          task_id: null,
          decision_type: "selection_set_approval",
          status: "accepted",
          selection_set_id: preview.selection_set_id,
          resulting_scenario_id: preview.preview_scenario_id,
          base_run_id: state.runId,
          rationale: globalRationale,
          user,
          source_artifacts_reviewed: reviewed,
          factor_selections: preview.factor_selections || [],
          exclusions: preview.exclusions || [],
          manual_overrides: preview.manual_overrides || [],
          factor_point_exclusions: preview.factor_point_exclusions || [],
          tail_selection: preview.tail_selection || null,
          selection_set_artifact: preview.selection_set_artifact,
          source_explore_scenario_id: preview.source_explore_scenario_id || state.selectedExploreScenarioId,
          comparison: preview.comparison,
          factor_analysis_id: preview.factor_analysis_id || null,
          reviewed_suggestion_ids: preview.reviewed_suggestion_ids || [],
          suggestion_dispositions: preview.suggestion_dispositions || [],
          commands_or_parameters_affected: [],
          supersedes_decision_id: activeSelectionApproval?.decision_id || null
        }
      })
    });
    showToast(`Committed ${committed.selection_set_id} / ${approvalDecisionId}`);
    state.selectionSetPreview = null;
    state.selectionDraft = emptySelectionDraft();
    clearLivePreview();
    await refreshRun();
  } catch (error) {
    showToast(error.message);
  }
}

function ScenarioCard(scenario) {
  const selected = scenario.scenario_id === state.selectedScenarioId;
  const delta = selected ? state.comparison?.deltas?.ibnr : null;
  return `
    <article class="scenario-card">
      <div class="surface-header">
        <h3>${safe(scenario.scenario_id)}</h3>
        <span class="${badgeClass(scenario.status)}">${safe(scenario.status || "available")}</span>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Type</strong><span>${safe(scenario.scenario_type || "n/a")}</span></div>
        <div class="check-row"><span></span><strong>IBNR</strong><span>${fmt(scenario.key_metrics?.ibnr)}</span></div>
        <div class="check-row"><span></span><strong>Delta IBNR</strong><span>${fmt(delta)}</span></div>
        <div class="check-row"><span></span><strong>Source</strong><span>${safe((scenario.output_artifacts || [scenario.artifact_path || "n/a"])[0] || "n/a")}</span></div>
      </div>
      <button class="${selected ? "primary-button" : ""}" onclick="selectScenario('${safe(scenario.scenario_id)}')">${selected ? "Compared" : "Compare"}</button>
    </article>
  `;
}

function renderScenarios() {
  const list = scenarios();
  const selected = list.find((scenario) => scenario.scenario_id === state.selectedScenarioId);
  $("scenariosPanel").innerHTML = `
    ${screenHeading("Scenario candidates", "Scenario Preview and Selection", "Scenario preview is exploratory. Only committed decisions feed report readiness.", `<span class="pill">${fmt(list.length)} candidates</span>`)}
    <div class="scenario-grid">
      ${list.map(ScenarioCard).join("") || '<p class="empty">No scenario candidates are available.</p>'}
    </div>
    <section class="surface">
      <div class="surface-header">
        <h3>Comparison</h3>
        <span class="pill">${safe(state.selectedScenarioId || "none selected")}</span>
      </div>
      ${renderScenarioComparison(selected)}
    </section>
  `;
}

function renderScenarioComparison(selected) {
  if (!selected || !state.comparison) return '<p class="empty">Select a scenario candidate to compare against the base run.</p>';
  const metrics = Object.entries(state.comparison.compared_metrics || {});
  const deltas = state.comparison.deltas || {};
  return `
    <div class="triangle-table-wrap">
      <table>
        <thead><tr><th>Metric</th><th>Base</th><th>Candidate</th><th>Delta</th></tr></thead>
        <tbody>
          ${metrics.map(([metric, values]) => `
            <tr>
              <td>${safe(metric)}</td>
              <td>${fmt(values.base)}</td>
              <td>${fmt(values.candidate)}</td>
              <td>${fmt(deltas[metric])}</td>
            </tr>
          `).join("") || `
            <tr><td>ultimate</td><td>n/a</td><td>n/a</td><td>${fmt(deltas.ultimate)}</td></tr>
            <tr><td>ibnr</td><td>n/a</td><td>n/a</td><td>${fmt(deltas.ibnr)}</td></tr>
          `}
        </tbody>
      </table>
    </div>
  `;
}

function DecisionLogEntry(decision) {
  const scenarioId = decision.scenario_id || decision.resulting_scenario_id || "none";
  const selections = decision.factor_selections || [];
  const manual = decision.manual_overrides || [];
  const exclusions = decision.exclusions || [];
  const tailSelection = decision.tail_selection || null;
  return `
    <article class="decision-card immutable-log">
      <div class="surface-header">
        <h3>${safe(decision.decision_id)}</h3>
        <div class="state-chip-stack">
          <span class="${badgeClass(decision.active ? "active" : "superseded")}">${decision.active ? "active" : "superseded"}</span>
          <span class="pill">immutable</span>
        </div>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Type</strong><span>${safe(decision.decision_type)}</span></div>
        <div class="check-row"><span></span><strong>Status</strong><span>${safe(decision.status)}</span></div>
        <div class="check-row"><span></span><strong>Selection set</strong><span>${safe(decision.selection_set_id || "none")}</span></div>
        <div class="check-row"><span></span><strong>Scenario</strong><span>${safe(scenarioId)}</span></div>
        <div class="check-row"><span></span><strong>Review snapshot</strong><span>${safe(decision.review_snapshot_id || "none")}</span></div>
        <div class="check-row"><span></span><strong>Source explore</strong><span>${safe(decision.source_explore_scenario_id || "none")}</span></div>
        <div class="check-row"><span></span><strong>User</strong><span>${safe(decision.display_name || decision.user?.display_name || decision.user_id || decision.user?.id || "n/a")}</span></div>
        <div class="check-row"><span></span><strong>Timestamp</strong><span>${safe(decision.timestamp_utc || "n/a")}</span></div>
      </div>
      ${renderDecisionSelectionMetadata(selections, manual, exclusions, tailSelection)}
      <p>${safe(decision.rationale || "No rationale recorded.")}</p>
      <p class="empty">${safe((decision.source_artifacts_reviewed || []).join(", ") || "no reviewed artifacts")}</p>
    </article>
  `;
}

function renderDecisionSelectionMetadata(selections, manual, exclusions, tailSelection) {
  if (!selections.length && !manual.length && !exclusions.length && !tailSelection) {
    return '<p class="empty">No selection-set metadata recorded for this decision.</p>';
  }
  return `
    <div class="decision-metadata">
      <div>
        <p class="section-label">Selected factors</p>
        ${selections.map((factor) => `
          <span>${safe(factor.development_age)} ${fmtFactor(factor.previous_factor)} -> ${fmtFactor(factor.selected_factor)} / ${safe(factorBasisLabel(factor.selected_basis))}</span>
        `).join("") || '<span>none</span>'}
      </div>
      <div>
        <p class="section-label">Manual overrides</p>
        ${manual.map((factor) => `<span>${safe(factor.development_age)} ${fmtFactor(factor.selected_factor)}</span>`).join("") || '<span>none</span>'}
      </div>
      <div>
        <p class="section-label">Exclusions</p>
        ${exclusions.map((item) => `<span>${safe(item.type)} ${safe(item.value)} ${item.development_age ? `/ ${safe(item.development_age)}` : ""}</span>`).join("") || '<span>none</span>'}
      </div>
      <div>
        <p class="section-label">Tail</p>
        <span>${tailSelection ? `${safe(tailSelection.selected_parameter || tailSelection.type)} / ${safe(tailSelection.rationale || "no rationale")}` : "base fit"}</span>
      </div>
    </div>
  `;
}

function renderDecisions() {
  const active = state.decisionJournal?.active_decisions || activeDecisions();
  const superseded = state.decisionJournal?.superseded_decisions || [];
  const tasks = state.tasks?.tasks || [];
  const exploreList = exploreScenarios();
  $("decisionsPanel").innerHTML = `
    ${screenHeading("Decision journal", "Audit Logbook", "Committed decisions are immutable artifacts written through backend validation.", `<span class="pill">${fmt(active.length)} active</span>`)}
    <section class="surface">
      <div class="surface-header">
        <h3>Exploratory Scenarios</h3>
        <span class="${badgeClass("not_governed")}">NOT GOVERNED</span>
      </div>
      <div class="scenario-grid">
        ${exploreList.map(ExploreScenarioCard).join("") || '<p class="empty">No exploratory scenarios saved.</p>'}
      </div>
    </section>
    <section class="surface">
      <div class="surface-header">
        <h3>Pending Review Tasks</h3>
        <button onclick="refreshTasks()">Refresh Tasks</button>
      </div>
      <div class="draft-list">
        ${tasks.map(renderTaskRow).join("") || '<p class="empty">No tasks are available.</p>'}
      </div>
    </section>
    <section class="surface">
      <div class="surface-header">
        <h3>Committed Decisions</h3>
        <span class="pill">active</span>
      </div>
      <div class="decision-grid">
        ${active.map(DecisionLogEntry).join("") || '<p class="empty">No active committed decisions.</p>'}
      </div>
    </section>
    <section class="surface">
      <div class="surface-header">
        <h3>Superseded Decisions</h3>
        <span class="pill">${fmt(superseded.length)}</span>
      </div>
      <div class="decision-grid">
        ${superseded.map(DecisionLogEntry).join("") || '<p class="empty">No superseded decisions.</p>'}
      </div>
    </section>
  `;
}

function ExploreScenarioCard(scenario) {
  const preview = scenario.preview_result || {};
  return `
    <article class="scenario-card explore-card">
      <div class="surface-header">
        <h3>${safe(scenario.name || scenario.explore_scenario_id)}</h3>
        <span class="${badgeClass("not_governed")}">NOT GOVERNED</span>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Explore id</strong><span>${safe(scenario.explore_scenario_id)}</span></div>
        <div class="check-row"><span></span><strong>Selected IBNR</strong><span>${fmt(preview.selected_ibnr)}</span></div>
        <div class="check-row"><span></span><strong>Delta IBNR</strong><span>${fmt(preview.delta_ibnr)}</span></div>
        <div class="check-row"><span></span><strong>Updated</strong><span>${safe(scenario.updated_utc || "n/a")}</span></div>
      </div>
      <button onclick="loadExploreScenario('${safe(scenario.explore_scenario_id)}')">Load Study</button>
    </article>
  `;
}

async function loadExploreScenario(exploreScenarioId) {
  const run = encodeURIComponent(state.runId);
  const scenario = await api(`/api/runs/${run}/explore/${encodeURIComponent(exploreScenarioId)}`);
  state.workflowMode = "explore";
  state.selectedExploreScenarioId = scenario.explore_scenario_id;
  state.explorePreview = scenario;
  state.exploreMeta = { name: scenario.name || "Exploratory scenario", notes: scenario.notes || "" };
  state.selectionDraft.factors = {};
  [...(scenario.factor_selections || []), ...(scenario.manual_overrides || [])].forEach((factor) => {
    state.selectionDraft.factors[String(factor.from_dev)] = dictFactorDraft(factor);
  });
  state.selectionDraft.exclusions = { origins: "", originRationale: "", valuations: "", valuationRationale: "", points: [] };
  state.selectionDraft.tail = null;
  (scenario.origin_exclusions || []).forEach((item) => {
    state.selectionDraft.exclusions.origins = addCommaValue(state.selectionDraft.exclusions.origins, item.value);
    state.selectionDraft.exclusions.originRationale = state.selectionDraft.exclusions.originRationale || item.rationale || "";
  });
  (scenario.valuation_exclusions || []).forEach((item) => {
    state.selectionDraft.exclusions.valuations = addCommaValue(state.selectionDraft.exclusions.valuations, item.value);
    state.selectionDraft.exclusions.valuationRationale = state.selectionDraft.exclusions.valuationRationale || item.rationale || "";
  });
  state.selectionDraft.exclusions.points = scenario.factor_point_exclusions || [];
  state.activeTab = "triangles";
  render();
}

function dictFactorDraft(factor) {
  return { ...factor };
}

function renderTaskRow(task) {
  const selected = state.selectedTask?.task_id === task.task_id;
  return `
    <article class="draft-item ${selected ? "selected-cell" : ""}">
      <div class="surface-header">
        <div>
          <h3>${safe(task.title)}</h3>
          <p>${safe(task.description)}</p>
        </div>
        <span class="${badgeClass(task.status)}">${safe(task.status)}</span>
      </div>
      <p class="empty">${safe(task.task_type)} / ${(task.allowed_decision_types || []).map(safe).join(", ") || "no decision type"}</p>
      <button onclick="selectTask('${safe(task.task_id)}')">Open Review</button>
    </article>
  `;
}

function ReportReadinessGate() {
  const payload = state.readiness;
  if (!payload) return '<p class="empty">Report readiness is unavailable.</p>';
  return `
    <section class="report-gate">
      <div class="surface-header">
        <div>
          <p class="section-label">Control gate</p>
          <h3>${safe(payload.status)}</h3>
        </div>
        <span class="${badgeClass(payload.require_approval_would_pass ? "pass" : "blocked")}">${payload.require_approval_would_pass ? "would pass" : "blocked"}</span>
      </div>
      <div class="readiness-command">
        <span>Guarded command</span>
        <code>${safe(payload.report_command || "")}</code>
      </div>
      <div class="workspace-grid" style="margin-top: 16px;">
        <div>
          <h3>Blockers</h3>
          ${renderBlockerList(payload.blockers || [])}
        </div>
        <div>
          ${renderReportModeChecklist(payload)}
          ${renderGovernanceChecklist()}
        </div>
      </div>
    </section>
  `;
}

function renderReportModeChecklist(payload) {
  return `
    <section class="surface" style="margin-bottom: 16px;">
      <div class="surface-header">
        <h3>Explore vs Governed</h3>
        <span class="pill">${safe(payload.explore_message || "Only governed selections enter reports.")}</span>
      </div>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Exploratory scenarios exist</strong><span>${payload.exploratory_scenarios_exist ? "yes" : "no"}</span></div>
        <div class="check-row"><span></span><strong>Governed selection set exists</strong><span>${payload.governed_selection_set_exists ? "yes" : "no"}</span></div>
        <div class="check-row"><span></span><strong>Governed selection approval exists</strong><span>${payload.governed_selection_approval_exists ? "yes" : "no"}</span></div>
        <div class="check-row"><span></span><strong>Report approval exists</strong><span>${payload.report_approval_exists ? "yes" : "no"}</span></div>
      </div>
    </section>
  `;
}

function renderReport() {
  const payload = state.readiness;
  $("reportPanel").innerHTML = `
    ${screenHeading("Report readiness", payload?.status || "Unavailable", "Final review packs only use committed governed decisions.", `<span class="${badgeClass(payload?.status)}">${safe(payload?.status || "n/a")}</span>`)}
    ${ReportReadinessGate()}
  `;
}

function renderBlockerList(blockers) {
  if (!blockers.length) return '<p class="empty">No blockers.</p>';
  return `
    <div class="blocker-list">
      ${blockers.map((blocker) => `
        <div class="blocker-summary severity-${safe(blocker.severity)}">
          <strong>${safe(blocker.label)}</strong>
          <span>${safe(blocker.code || blocker.severity || "blocker")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function renderArtifacts() {
  const buttons = artifactNames.map((name) => {
    const exists = Boolean(state.artifacts[name]);
    return `<button class="${state.artifactName === name ? "primary-button" : ""}" ${exists ? "" : "disabled"} onclick="selectArtifact('${safe(name)}')">${safe(name)}</button>`;
  }).join("");
  const payload = state.artifacts[state.artifactName];
  $("artifactsPanel").innerHTML = `
    ${screenHeading("Artifacts", "Raw Artifact Browser", "Raw JSON is intentionally confined to this tab.", `<span class="pill">${safe(state.artifactName)}</span>`)}
    <div class="row-actions" style="margin-bottom: 12px;">${buttons}</div>
    <pre class="json-viewer">${payload ? safe(JSON.stringify(payload, null, 2)) : "Artifact not available."}</pre>
  `;
}

function selectArtifact(name) {
  state.artifactName = name;
  renderArtifacts();
}

function ValidationDrawer() {
  const payload = state.readiness;
  const blockers = payload?.blockers || [];
  return `
    <section class="drawer-section guided-action-section">
      <p class="section-label">Next action</p>
      ${renderDrawerAction()}
    </section>
    <section class="drawer-section">
      <div class="surface-header">
        <h3>Report Readiness</h3>
        <span class="${badgeClass(payload?.status)}">${safe(payload?.status || "n/a")}</span>
      </div>
      <strong>${fmt(blockers.length)} blockers</strong>
      ${renderBlockerList(blockers)}
      <div class="readiness-command">
        <span>Guarded command</span>
        <code>${safe(payload?.report_command || "")}</code>
      </div>
    </section>
    <section class="drawer-section">
      <h3>Committed Decisions</h3>
      ${renderDrawerDecisions()}
    </section>
  `;
}

function renderValidationDrawer() {
  $("validationDrawer").innerHTML = ValidationDrawer();
  const form = $("v2DecisionForm");
  if (form && state.selectedTask) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await commitDecision(state.selectedTask);
    });
  }
}

function renderDrawerAction() {
  if (state.selectedTask) return renderDecisionForm(state.selectedTask);
  if (state.selectedFactorPoint) return renderFactorPointInspector();
  if (state.selectedTriangleCell) return renderTriangleCellDetail();
  if (state.activeTab === "triangles") return renderSelectedAgeDrawerSummary();
  return DrawerActionCard();
}

function renderSelectedAgeDrawerSummary() {
  const row = selectedFactorRow(state.factors?.factors || []);
  if (!row) return DrawerActionCard();
  const draft = draftForRow(row);
  const workflow = selectionWorkflowState();
  return `
    <article class="drawer-action-card">
      <div class="row-actions">
        <span class="${badgeClass(workflow.key)}">${safe(workflow.label)}</span>
        <span class="pill">selected age</span>
      </div>
      <p class="section-label">Development age</p>
      <h3>${safe(row.development_age || "n/a")}</h3>
      <div class="checklist">
        <div class="check-row"><span></span><strong>Base factor</strong><span>${fmtFactor(row.selected_factor)}</span></div>
        <div class="check-row"><span></span><strong>Draft factor</strong><span>${draft ? fmtFactor(draft.selected_factor) : "none"}</span></div>
        <div class="check-row"><span></span><strong>Basis</strong><span>${safe(draft ? factorBasisLabel(draft.selected_basis) : row.factor_basis || "base")}</span></div>
        <div class="check-row"><span></span><strong>Point exclusions</strong><span>${fmt(factorPointDrafts().length)}</span></div>
      </div>
      <button class="primary-button" onclick="setTab('triangles')">Review Development</button>
    </article>
  `;
}

function DrawerActionCard() {
  const action = state.readiness?.next_action;
  if (!action) return '<p class="empty">No guided action is available.</p>';
  return `
    <article class="drawer-action-card">
      <div class="row-actions">
        <span class="${badgeClass(action.blocked ? "blocked" : "ready")}">${action.blocked ? "blocked" : "ready"}</span>
        <span class="pill">${safe(action.decision_type || "workflow")}</span>
      </div>
      <p class="section-label">Next action</p>
      <h3>${safe(action.detail || action.label)}</h3>
      <button class="primary-button" onclick="openNextAction()">Open Review</button>
    </article>
  `;
}

function renderDrawerDecisions() {
  const entries = activeDecisions();
  const exploreList = exploreScenarios();
  const exploreMarkup = exploreList.slice(0, 3).map((scenario) => `
    <article class="decision-card explore-card">
      <strong>${safe(scenario.name || scenario.explore_scenario_id)}</strong>
      <p>EXPLORE / NOT GOVERNED</p>
      <p class="empty">${safe(scenario.explore_scenario_id)}</p>
    </article>
  `).join("");
  const decisionMarkup = entries.slice(0, 4).map((decision) => `
    <article class="decision-card">
      <strong>${safe(decision.decision_id)}</strong>
      <p>${safe(decision.decision_type)} / ${safe(decision.status)}</p>
      <p class="empty">${safe(decision.resulting_scenario_id || decision.selection_set_id || "no scenario")}</p>
    </article>
  `).join("");
  if (!entries.length && !exploreList.length) return '<p class="empty">No decisions committed.</p>';
  return `${exploreMarkup}${decisionMarkup}`;
}

function renderDecisionForm(task) {
  const allowed = task.allowed_decision_types || [];
  const sourceArtifacts = Array.from(
    new Set([
      ...(task.source_artifacts || []),
      ...(task.task_type === "scenario_selection" ? ["scenario_index.json"] : [])
    ])
  );
  const scenarioField = allowed.includes("scenario_selection")
    ? `
        <div class="form-row">
          <label for="v2ScenarioId">Resulting scenario id</label>
          <input id="v2ScenarioId" value="${safe(state.selectedScenarioId || "")}" placeholder="required for scenario_selection" />
        </div>
      `
    : "";
  return `
    <article class="decision-card">
      <h3>${safe(task.title)}</h3>
      <p>${safe(task.description)}</p>
      ${task.task_type === "bcl_review" ? renderChainLadderReviewContext() : ""}
      <form id="v2DecisionForm" class="form-grid">
        <div class="form-row">
          <label for="v2DecisionType">Decision type</label>
          <select id="v2DecisionType">
            ${allowed.map((type) => `<option value="${safe(type)}">${safe(type)}</option>`).join("")}
          </select>
        </div>
        <div class="form-row">
          <label for="v2DecisionStatus">Status</label>
          <select id="v2DecisionStatus">
            <option value="accepted">accepted</option>
            <option value="modified">modified</option>
            <option value="rejected">rejected</option>
          </select>
        </div>
        ${scenarioField}
        <div class="form-row">
          <label for="v2Rationale">Rationale / review note</label>
          <textarea id="v2Rationale"></textarea>
        </div>
        <div class="form-row">
          <label for="v2UserId">User id</label>
          <input id="v2UserId" value="${safe(localStorage.getItem("reserveUserId") || "")}" />
        </div>
        <div class="form-row">
          <label for="v2DisplayName">Display name</label>
          <input id="v2DisplayName" value="${safe(localStorage.getItem("reserveDisplayName") || "")}" />
        </div>
        <p class="empty">Reviewed artifacts: ${sourceArtifacts.map(safe).join(", ") || "none"}</p>
        <button class="primary-button" type="submit">Commit Decision</button>
      </form>
    </article>
  `;
}

function renderChainLadderReviewContext() {
  const summary = state.summary;
  if (!summary?.is_chain_ladder) return "";
  const currentTotals = summary.totals || {};
  return `
    <div class="blocker-summary">
      <strong>Chain Ladder Summary</strong>
      <span>${safe(summary.display_method)}</span>
      <span>Input ${safe(summary.input_file || "n/a")}</span>
      <span>Latest ${fmt(currentTotals.latest)} / Ultimate ${fmt(currentTotals.ultimate)} / IBNR ${fmt(currentTotals.ibnr)}</span>
    </div>
  `;
}

async function commitDecision(task) {
  const decisionType = $("v2DecisionType").value;
  const userId = $("v2UserId").value.trim();
  const displayName = $("v2DisplayName").value.trim();
  localStorage.setItem("reserveUserId", userId);
  localStorage.setItem("reserveDisplayName", displayName);
  const sourceArtifacts = Array.from(
    new Set([
      ...(task.source_artifacts || []),
      ...(task.task_type === "scenario_selection" ? ["scenario_index.json"] : [])
    ])
  );
  const priorDecision = activeDecisions().find(
    (decision) => decision.task_id === task.task_id || decision.decision_type === decisionType
  );
  const decision = {
    schema_version: "0.1",
    decision_id: `${decisionType}_${Date.now().toString(36)}`,
    run_id: state.runId,
    task_id: task.task_id,
    decision_type: decisionType,
    status: $("v2DecisionStatus").value,
    rationale: $("v2Rationale").value.trim(),
    user: { id: userId, display_name: displayName },
    source_artifacts_reviewed: sourceArtifacts,
    commands_or_parameters_affected: [],
    resulting_scenario_id: decisionType === "scenario_selection" ? $("v2ScenarioId")?.value.trim() || null : null,
    supersedes_decision_id: priorDecision?.decision_id || null
  };
  const run = encodeURIComponent(state.runId);
  try {
    await api(`/api/runs/${run}/decisions`, {
      method: "POST",
      body: JSON.stringify(decision)
    });
    showToast("Decision committed.");
    state.selectedTask = null;
    await refreshRun();
  } catch (error) {
    showToast(error.message);
  }
}

function boot() {
  window.addEventListener("error", (event) => {
    showToast(`Workbench error: ${event.message || "unknown frontend error"}`);
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason?.message || String(event.reason || "unknown asynchronous error");
    showToast(`Workbench error: ${reason}`);
  });
  $("toggleLeftRail").addEventListener("click", () => toggleRail("left"));
  $("toggleRightRail").addEventListener("click", () => toggleRail("right"));
  window.addEventListener("resize", applyRailState);
  applyRailState();
  document.querySelectorAll(".v2-tabs button").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      setTab(state.activeTab);
    });
  });
  document.querySelectorAll("[data-tab-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      state.activeTab = link.dataset.tabLink;
      render();
    });
  });
  $("runSelect").addEventListener("change", async (event) => {
    await openRun(event.target.value);
  });
  $("refreshRun").addEventListener("click", async () => {
    await refreshRun();
    showToast("Run refreshed.");
  });
  loadRuns().catch((error) => {
    showToast(error.message);
    render();
  });
}

document.addEventListener("DOMContentLoaded", boot);
