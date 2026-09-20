"use strict";

// ------------------------------------------------------------------ config

const SUMMARY_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "bedwars_level", label: "Level", digits: 0 },
  { key: "games_played_bedwars", label: "Games", digits: 0 },
  { key: "wins_bedwars", label: "Wins", digits: 0 },
  { key: "losses_bedwars", label: "Losses", digits: 0 },
  { key: "win_rate", label: "Win rate", pct: true },
  { key: "wlr", label: "WLR", digits: 2 },
  { key: "final_kills_bedwars", label: "Final kills", digits: 0 },
  { key: "final_deaths_bedwars", label: "Final deaths", digits: 0 },
  { key: "fkdr", label: "FKDR", digits: 2 },
  { key: "kills_bedwars", label: "Kills", digits: 0 },
  { key: "deaths_bedwars", label: "Deaths", digits: 0 },
  { key: "kdr", label: "KDR", digits: 2 },
  { key: "beds_broken_bedwars", label: "Beds broken", digits: 0 },
  { key: "beds_lost_bedwars", label: "Beds lost", digits: 0 },
  { key: "bblr", label: "BBLR", digits: 2 },
];

const PROGRESS_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "snapshot_ts", label: "Snapshot", date: true },
  { key: "games_played_bedwars_delta", label: "Games", digits: 0, signed: true },
  { key: "wins_bedwars_delta", label: "Wins", digits: 0, signed: true },
  { key: "losses_bedwars_delta", label: "Losses", digits: 0, signed: true },
  { key: "final_kills_bedwars_delta", label: "Final kills", digits: 0, signed: true },
  { key: "final_deaths_bedwars_delta", label: "Final deaths", digits: 0, signed: true },
  { key: "kills_bedwars_delta", label: "Kills", digits: 0, signed: true },
  { key: "deaths_bedwars_delta", label: "Deaths", digits: 0, signed: true },
  { key: "beds_broken_bedwars_delta", label: "Beds broken", digits: 0, signed: true },
  { key: "beds_lost_bedwars_delta", label: "Beds lost", digits: 0, signed: true },
  { key: "fkdr_period", label: "FKDR (period)", digits: 2 },
  { key: "wlr_period", label: "WLR (period)", digits: 2 },
];

const QUALITY_COLUMNS = [
  { key: "username", label: "Player", text: true },
  { key: "uuid", label: "UUID", text: true },
  { key: "snapshot_ts", label: "Snapshot", date: true },
];

const PALETTE = [
  "#f5f5f5", "#b0b0b0", "#8a8a8a", "#d6d6d6", "#707070",
  "#c2c2c2", "#e8e8e8", "#7c7c7c", "#9e9e9e", "#5e5e5e",
];
// Line dashes keep players apart when several lines are similar shades of gray.
const DASHES = [[], [6, 4], [2, 3], [10, 4, 2, 4], [], [6, 4], [2, 3], [10, 4, 2, 4], [], [6, 4]];

const MODE_LABELS = { overall: "Overall", solo: "Solo", doubles: "Doubles", trios: "3s", fours: "4s" };

const state = {
  data: null,
  mode: "overall",
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

/** The summary, history and progress rows for the selected game mode. */
function view() {
  return state.data.modes[state.mode];
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
  return [...view().summary].sort((a, b) => {
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
  $("#mode-label").textContent = MODE_LABELS[state.mode];
  renderTable($("#summary-table"), SUMMARY_COLUMNS, sortedSummary(), state.sort, onSort);
  renderBarChart();
}

function renderBarChart() {
  const key = $("#bar-metric").value;
  const col = SUMMARY_COLUMNS.find((c) => c.key === key);
  const rows = [...view().summary]
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
  const history = view().history;

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
    borderDash: DASHES[i % DASHES.length],
    backgroundColor: PALETTE[i % PALETTE.length],
    spanGaps: true,
    tension: 0.25,
  }));

  drawChart("#line-chart", {
    type: "line",
    data: { labels: stamps.map((s) => new Date(s).toLocaleString()), datasets },
    options: chartOptions(true),
  });

  renderTable($("#progress-table"), PROGRESS_COLUMNS, view().progress, null, null);
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

function setMode(mode) {
  state.mode = mode;
  for (const btn of document.querySelectorAll(".mode-btn")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.mode === mode));
  }
  if (state.data && !state.data.empty) render();
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
  const save = $("#save-toggle").checked;
  const button = $("#fetch-btn");

  if (!key) {
    setStatus([{ kind: "error", text: "Enter your Hypixel API key first." }]);
    $("#api-key").focus();
    return;
  }

  button.disabled = true;
  setStatus([{ kind: "info", text: "Fetching from Hypixel..." }]);

  try {
    const headers = { "Content-Type": "application/json", "X-Hypixel-Key": key };

    const res = await fetch(save ? "/api/fetch" : "/api/live", {
      method: "POST",
      headers,
      body: JSON.stringify({ usernames: names }),
    });
    const body = await res.json();
    if (!res.ok) {
      const detail = (body.skipped || []).map((s) => `${s.name}: ${s.reason}`).join("; ");
      throw new Error([body.error || `Request failed (${res.status}).`, detail].filter(Boolean).join(" "));
    }

    const messages = [];
    if (save) {
      if (body.saved.length) messages.push({ kind: "success", text: `Saved: ${body.saved.join(", ")}` });
    } else {
      messages.push({
        kind: "info",
        text: `Live view for ${body.fetched.join(", ")}. Nothing was saved, so a refresh clears this.`,
      });
    }
    for (const s of body.skipped) messages.push({ kind: "warning", text: `Skipped ${s.name}: ${s.reason}` });
    setStatus(messages);

    if (save) {
      await loadDashboard();
    } else {
      state.data = body.dashboard;   // in memory only
      render();
    }
  } catch (err) {
    setStatus([{ kind: "error", text: err.message }]);
  } finally {
    button.disabled = false;
  }
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
  for (const btn of document.querySelectorAll(".mode-btn")) {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  }

  try {
    await loadDashboard();
  } catch (err) {
    setStatus([{ kind: "error", text: err.message }]);
  }
}

init();
