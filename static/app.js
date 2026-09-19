"use strict";

// ------------------------------------------------------------------ config

const SUMMARY_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "bedwars_level", label: "Level", digits: 0 },
  { key: "games_played_bedwars", label: "Games", digits: 0 },
  { key: "win_rate", label: "Win rate", pct: true },
  { key: "wlr", label: "WLR", digits: 2 },
  { key: "fkdr", label: "FKDR", digits: 2 },
  { key: "kdr", label: "KDR", digits: 2 },
  { key: "bblr", label: "BBLR", digits: 2 },
];

const PROGRESS_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "snapshot_ts", label: "Snapshot", date: true },
  { key: "games_played_bedwars_delta", label: "Games", digits: 0, signed: true },
  { key: "wins_bedwars_delta", label: "Wins", digits: 0, signed: true },
  { key: "final_kills_bedwars_delta", label: "Final kills", digits: 0, signed: true },
  { key: "final_deaths_bedwars_delta", label: "Final deaths", digits: 0, signed: true },
  { key: "fkdr_period", label: "FKDR (period)", digits: 2 },
  { key: "wlr_period", label: "WLR (period)", digits: 2 },
];

const QUALITY_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "uuid", label: "UUID", text: true },
  { key: "snapshot_ts", label: "Snapshot", date: true },
];

const PALETTE = [
  "#4ade80", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa",
  "#f87171", "#2dd4bf", "#fb923c", "#94a3b8", "#e879f9",
];

const state = {
  data: null,
  config: { server_has_key: false },
  sort: { key: "fkdr", dir: -1 },
};

const charts = {};

// ------------------------------------------------------------------ helpers

const $ = (selector) => document.querySelector(selector);

/** Build an element. Text always goes in via textContent, never innerHTML. */
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  node.append(...children);
  return node;
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmt(value, col) {
  if (value === null || value === undefined) return "n/a";
  if (col.date) return new Date(value).toLocaleString();
  if (col.pct) return `${(value * 100).toFixed(1)}%`;
  if (col.digits !== undefined) {
    const text = Number(value).toFixed(col.digits);
    return col.signed && value > 0 ? `+${text}` : text;
  }
  return String(value);
}

function isNumericColumn(col) {
  return !col.text && !col.date;
}

function setStatus(messages) {
  const box = $("#status");
  box.replaceChildren(
    ...messages.map((m) => el("p", { className: m.kind, textContent: m.text }))
  );
}

// ------------------------------------------------------------------ tables

function renderTable(table, columns, rows, sort, onSort) {
  const headRow = el("tr");
  for (const col of columns) {
    const th = el("th", { scope: "col" });
    if (isNumericColumn(col)) th.classList.add("num");

    if (onSort) {
      const btn = el("button", { type: "button", className: "sort-btn", textContent: col.label });
      if (sort.key === col.key) {
        btn.dataset.dir = sort.dir === 1 ? "asc" : "desc";
        th.setAttribute("aria-sort", sort.dir === 1 ? "ascending" : "descending");
      }
      btn.addEventListener("click", () => onSort(col.key));
      th.append(btn);
    } else {
      th.textContent = col.label;
    }
    headRow.append(th);
  }

  const tbody = el("tbody");
  if (rows.length === 0) {
    tbody.append(
      el("tr", {}, el("td", { colSpan: columns.length, className: "muted", textContent: "No rows yet." }))
    );
  }
  for (const row of rows) {
    const tr = el("tr");
    for (const col of columns) {
      const td = el("td", { textContent: fmt(row[col.key], col) });
      if (isNumericColumn(col)) td.classList.add("num");
      tr.append(td);
    }
    tbody.append(tr);
  }

  table.replaceChildren(el("thead", {}, headRow), tbody);
}

// ------------------------------------------------------------------ charts

function chartOptions(showLegend) {
  const grid = { color: cssVar("--border") };
  const ticks = { color: cssVar("--muted") };
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: showLegend, labels: { color: cssVar("--text") } } },
    scales: { x: { ticks, grid }, y: { ticks, grid, beginAtZero: false } },
  };
}

function drawChart(canvasId, config) {
  if (!window.Chart) return;
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new window.Chart($(canvasId), config);
}

// ------------------------------------------------------------------ leaderboard

function sortedSummary() {
  const { key, dir } = state.sort;
  return [...state.data.summary].sort((a, b) => {
    const x = a[key];
    const y = b[key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * dir;
  });
}

function onSort(key) {
  if (state.sort.key === key) {
    state.sort.dir *= -1;
  } else {
    state.sort = { key, dir: key === "username" ? 1 : -1 };
  }
  renderLeaderboard();
}

function renderLeaderboard() {
  renderTable($("#summary-table"), SUMMARY_COLUMNS, sortedSummary(), state.sort, onSort);
  renderBarChart();
}

function renderBarChart() {
  const key = $("#bar-metric").value;
  const col = SUMMARY_COLUMNS.find((c) => c.key === key);
  const rows = [...state.data.summary]
    .filter((r) => r[key] != null)
    .sort((a, b) => b[key] - a[key]);

  drawChart("#bar-chart", {
    type: "bar",
    data: {
      labels: rows.map((r) => r.username),
      datasets: [{
        label: col.label,
        data: rows.map((r) => r[key]),
        backgroundColor: rows.map((_, i) => PALETTE[i % PALETTE.length]),
        borderRadius: 6,
      }],
    },
    options: chartOptions(false),
  });
}

// ------------------------------------------------------------------ history

function renderHistory() {
  const metric = $("#history-metric").value;
  const history = state.data.history;

  const stamps = [...new Set(history.map((r) => r.snapshot_ts))].sort();
  const byPlayer = new Map();
  for (const row of history) {
    if (!byPlayer.has(row.uuid)) byPlayer.set(row.uuid, { name: row.username, points: new Map() });
    const entry = byPlayer.get(row.uuid);
    entry.name = row.username;
    entry.points.set(row.snapshot_ts, row[metric]);
  }

  const enough = [...byPlayer.values()].some((p) => p.points.size >= 2);
  $("#history-hint").hidden = enough;

  const datasets = [...byPlayer.values()].map((player, i) => ({
    label: player.name,
    data: stamps.map((s) => player.points.get(s) ?? null),
    borderColor: PALETTE[i % PALETTE.length],
    backgroundColor: PALETTE[i % PALETTE.length],
    spanGaps: true,
    tension: 0.25,
  }));

  drawChart("#line-chart", {
    type: "line",
    data: { labels: stamps.map((s) => new Date(s).toLocaleString()), datasets },
    options: chartOptions(true),
  });

  renderTable($("#progress-table"), PROGRESS_COLUMNS, state.data.progress, null, null);
}

// ------------------------------------------------------------------ quality

function renderQuality() {
  const q = state.data.quality;
  $("#stat-passed").textContent = q.passed;
  $("#stat-quarantined").textContent = q.quarantined;
  $("#stat-players").textContent = q.players;
  renderTable($("#quality-table"), QUALITY_COLUMNS, q.quarantined_rows, null, null);
}

// ------------------------------------------------------------------ page wiring

function render() {
  const empty = state.data.empty;
  $("#empty-state").hidden = !empty;
  $("#dashboard").hidden = empty;
  if (empty) return;
  renderLeaderboard();
  renderHistory();
  renderQuality();
}

function showTab(name) {
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  }
  for (const panel of document.querySelectorAll(".panel")) {
    panel.hidden = panel.id !== `panel-${name}`;
  }
  // Charts drawn while hidden can size wrong, so redraw when a tab opens.
  if (state.data && !state.data.empty) {
    if (name === "history") renderHistory();
    if (name === "leaderboard") renderBarChart();
  }
}

async function loadDashboard() {
  const res = await fetch("/api/dashboard");
  if (!res.ok) throw new Error(`Could not load data (${res.status}).`);
  state.data = await res.json();
  render();
}

async function onFetch() {
  const names = $("#usernames").value.split(/[\s,]+/).filter(Boolean);
  const key = $("#api-key").value.trim();
  const button = $("#fetch-btn");

  button.disabled = true;
  setStatus([{ kind: "info", text: "Fetching from Hypixel..." }]);

  try {
    const headers = { "Content-Type": "application/json" };
    if (key) headers["X-Hypixel-Key"] = key;

    const res = await fetch("/api/fetch", {
      method: "POST",
      headers,
      body: JSON.stringify({ usernames: names }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || `Request failed (${res.status}).`);

    const messages = [];
    if (body.saved.length) messages.push({ kind: "success", text: `Saved: ${body.saved.join(", ")}` });
    for (const s of body.skipped) messages.push({ kind: "warning", text: `Skipped ${s.name}: ${s.reason}` });
    setStatus(messages);

    await loadDashboard();
  } catch (err) {
    setStatus([{ kind: "error", text: err.message }]);
  } finally {
    button.disabled = false;
  }
}

function updateKeyHint() {
  $("#api-key").placeholder = state.config.server_has_key
    ? "Optional: the server already has a key"
    : "Paste your Hypixel API key";
}

async function init() {
  if (!window.Chart) document.body.classList.add("no-charts");

  for (const col of SUMMARY_COLUMNS.filter(isNumericColumn)) {
    $("#bar-metric").append(el("option", { value: col.key, textContent: col.label }));
  }
  $("#bar-metric").value = "fkdr";

  $("#fetch-btn").addEventListener("click", onFetch);
  $("#bar-metric").addEventListener("change", () => state.data && renderBarChart());
  $("#history-metric").addEventListener("change", () => state.data && renderHistory());
  for (const tab of document.querySelectorAll('[role="tab"]')) {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
  }

  try {
    const res = await fetch("/api/config");
    if (res.ok) state.config = await res.json();
  } catch {
    // Not fatal: the key field simply keeps its default hint.
  }
  updateKeyHint();

  try {
    await loadDashboard();
  } catch (err) {
    setStatus([{ kind: "error", text: err.message }]);
  }
}

init();
