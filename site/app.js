"use strict";

const DATA = "data/derived/";
const RANK_NAMES = { hot: "综合", real: "真人", ai: "AI", comic: "漫剧" };
const TYPE_NAMES = { real: "真人", ai: "AI", comic: "漫剧", unknown: "未知" };
const WATCH_ERR = {
  not_found: "红果上没找到同名剧，请检查剧名或改用链接",
  ambiguous: "有多部同名剧，请改用链接",
  error: "搜索失败，下次采集会重试",
};
const state = { tab: "rank", rankKey: "hot", q: "", sort: "d_hot", type: "all" };
let status = null;
let ranks = null;
let growth = null;
let growthById = new Map();
const seriesCache = new Map();
let charts = [];

async function getJSON(path) {
  const res = await fetch(DATA + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "onclick") node.addEventListener("click", v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function fmtNum(n) {
  if (n === null || n === undefined) return "—";
  const a = Math.abs(n);
  if (a >= 1e8) return (n / 1e8).toFixed(2).replace(/\.?0+$/, "") + "亿";
  if (a >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, "") + "万";
  return String(Math.round(n));
}

function fmtDelta(n) {
  if (n === null || n === undefined) return "—";
  if (n === 0) return "0";
  return (n > 0 ? "+" : "−") + fmtNum(Math.abs(n));
}

function fmtPct(r) {
  if (r === null || r === undefined) return "—";
  return (r > 0 ? "+" : "") + (r * 100).toFixed(1) + "%";
}

function deltaClass(n) {
  return n > 0 ? "up" : n < 0 ? "down" : "";
}

function beijingToday() {
  return new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
}

function daysBetween(a, b) {
  return Math.round((Date.parse(a) - Date.parse(b)) / 86400e3);
}

function titleButton(id, title) {
  return el("button", { class: "link", onclick: () => openDetail(id) }, title || id);
}

function header(names) {
  return el("thead", {}, el("tr", {}, names.map((h) => el("th", {}, h))));
}

function renderStatus() {
  const box = document.getElementById("status");
  box.textContent = "";
  if (!status || !status.date) {
    box.append("还没有数据");
    return;
  }
  const rankDates = Object.entries(status.rank_dates)
    .map(([k, d]) => `${RANK_NAMES[k]} ${d ? d.slice(5) : "—"}`)
    .join(" · ");
  box.append(
    el("span", {}, "数据日期 ", el("b", {}, status.date)),
    el("span", {}, "官方榜 " + rankDates),
    el("span", {}, `追踪 ${status.tracked} 部`),
  );
  if (status.missing) box.append(el("span", { class: "warn" }, `${status.missing} 部详情缺失`));
  if (status.error_count) {
    const tip = status.errors.map((e) => e.message).join("\n");
    box.append(el("span", { class: "warn", title: tip }, `${status.error_count} 个错误`));
  }
  const lag = daysBetween(beijingToday(), status.date);
  if (lag > 1) box.append(el("span", { class: "bad" }, `数据已 ${lag} 天未更新`));
}

function changeCell(it) {
  if (it.badge === "new") return el("span", { class: "badge new" }, "NEW");
  if (it.badge === "back") return el("span", { class: "badge back" }, "回榜");
  if (it.delta === null || it.delta === undefined) return "—";
  if (it.delta === 0) return el("span", { class: "flat" }, "–");
  return el("span", { class: deltaClass(it.delta) }, (it.delta > 0 ? "↑" : "↓") + Math.abs(it.delta));
}

function renderRank() {
  const r = ranks[state.rankKey];
  const table = document.getElementById("rank-table");
  table.textContent = "";
  table.append(header(["名次", "变化", "剧名", "热度", "热度日增", "收藏（日增）", "评分", "在榜", "标签"]));
  const q = state.q.trim();
  const body = el("tbody");
  for (const it of r.items) {
    const g = growthById.get(it.id) || {};
    const title = g.title || it.title;
    if (q && !title.includes(q)) continue;
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "num" }, it.rank),
        el("td", {}, changeCell(it)),
        el("td", { class: "title" }, titleButton(it.id, title), it.status_tags.map((t) => el("span", { class: "tag hot" }, t))),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num" }, fmtNum(g.fav), " ", el("small", { class: deltaClass(g.d_fav) }, fmtDelta(g.d_fav))),
        el("td", { class: "num" }, g.score ?? "—"),
        el("td", { class: "num" }, it.streak + " 天"),
        el("td", { class: "tags" }, (g.tags || []).slice(0, 3).join(" / ")),
      ),
    );
  }
  table.append(body);

  const dropped = document.getElementById("dropped");
  dropped.textContent = "";
  if (!r.prev_rank_date) dropped.append("第一天的数据，暂无对比");
  else if (!r.dropped.length) dropped.append("无");
  for (const d of r.dropped) {
    dropped.append(el("span", { class: "chip" }, titleButton(d.id, d.title), ` 原第 ${d.last_rank} 名`));
  }
}

function renderSurge() {
  const key = state.sort;
  const note = document.getElementById("surge-note");
  if (!growth.prev_date) {
    note.textContent = "增速需要至少两天的数据，明天开始显示。";
  } else {
    note.textContent =
      `对比 ${growth.prev_date} → ${growth.date}` + (growth.gap > 1 ? `（间隔 ${growth.gap} 天，已换算成日均）` : "");
  }
  const rows = growth.items
    .filter((g) => g[key] !== null && g[key] !== undefined && (state.type === "all" || g.type === state.type))
    .sort((a, b) => b[key] - a[key])
    .slice(0, 50);
  const table = document.getElementById("surge-table");
  table.textContent = "";
  table.append(header(["#", "剧名", "类型", "热度", "热度日增", "增长率", "收藏日增", "7 日热度增量"]));
  const body = el("tbody");
  rows.forEach((g, i) => {
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "num" }, i + 1),
        el("td", { class: "title" }, titleButton(g.id, g.title), g.watch ? el("span", { class: "tag" }, "观察") : null),
        el("td", {}, TYPE_NAMES[g.type] || g.type),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num " + deltaClass(g.r_hot) }, fmtPct(g.r_hot)),
        el("td", { class: "num " + deltaClass(g.d_fav) }, fmtDelta(g.d_fav)),
        el("td", { class: "num " + deltaClass(g.d7_hot) }, fmtDelta(g.d7_hot)),
      ),
    );
  });
  table.append(body);
}

function sparkline(values) {
  const v = values.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return document.createTextNode("数据不足");
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 80 24");
  svg.setAttribute("class", "sparkline");
  const min = Math.min(...v);
  const span = Math.max(...v) - min || 1;
  const points = v.map((x, i) => `${(i / (v.length - 1)) * 78 + 1},${23 - ((x - min) / span) * 22}`).join(" ");
  const line = document.createElementNS(NS, "polyline");
  line.setAttribute("points", points);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "currentColor");
  line.setAttribute("stroke-width", "1.5");
  svg.append(line);
  return svg;
}

function loadSeries(id) {
  if (!seriesCache.has(id)) {
    seriesCache.set(
      id,
      getJSON(`series/${id}.json`).catch((e) => {
        seriesCache.delete(id);
        throw e;
      }),
    );
  }
  return seriesCache.get(id);
}

function renderWatch() {
  const table = document.getElementById("watch-table");
  table.textContent = "";
  const entries = status.watchlist || [];
  if (!entries.length) {
    table.append(el("tbody", {}, el("tr", {}, el("td", {}, "观察列表为空"))));
    return;
  }
  table.append(header(["条目", "剧名", "热度", "热度日增", "收藏", "收藏日增", "近 7 天热度"]));
  const body = el("tbody");
  table.append(body);
  for (const w of entries) {
    if (w.status !== "ok") {
      const why = WATCH_ERR[w.status] + (w.candidates ? "：" + w.candidates.join("、") : "");
      body.append(el("tr", {}, el("td", {}, w.entry), el("td", { class: "warn", colspan: "6" }, why)));
      continue;
    }
    const g = growthById.get(w.id) || {};
    const spark = el("td", { class: "spark" });
    body.append(
      el(
        "tr",
        {},
        el("td", {}, w.entry),
        el("td", { class: "title" }, titleButton(w.id, g.title || w.id)),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num" }, fmtNum(g.fav)),
        el("td", { class: "num " + deltaClass(g.d_fav) }, fmtDelta(g.d_fav)),
        spark,
      ),
    );
    loadSeries(w.id)
      .then((s) => spark.append(sparkline(s.points.slice(-7).map((p) => p.hot))))
      .catch(() => spark.append("—"));
  }
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

async function openDetail(id) {
  const dlg = document.getElementById("detail");
  const info = document.getElementById("d-info");
  document.getElementById("d-title").textContent = (growthById.get(id) || {}).title || id;
  document.getElementById("d-link").href = `https://hongguoduanju.com/detail?series_id=${encodeURIComponent(id)}`;
  info.textContent = "加载中…";
  charts.forEach((c) => c.destroy());
  charts = [];
  history.replaceState(null, "", "#s=" + encodeURIComponent(id));
  if (!dlg.open) dlg.showModal();

  let s;
  try {
    s = await loadSeries(id);
  } catch (e) {
    info.textContent = "历史数据加载失败";
    return;
  }
  document.getElementById("d-title").textContent = s.title || id;
  const firstDay = s.first_visible ? new Date(s.first_visible * 1000 + 8 * 3600e3).toISOString().slice(0, 10) : "—";
  info.textContent = "";
  info.append(
    ...[
      `${s.eps ?? "—"} 集`,
      `上线 ${firstDay}`,
      `评分 ${s.score ?? "—"}`,
      `${fmtNum(s.rating_cnt)} 人评分`,
      `${fmtNum(s.review_cnt)} 条评论`,
      (s.tags || []).join(" / "),
    ].map((t) => el("span", {}, t)),
  );
  if (!window.Chart) {
    info.append(el("span", { class: "warn" }, "图表库加载失败"));
    return;
  }
  const labels = s.points.map((p) => p.date.slice(5));
  const fg = cssVar("--muted");
  const grid = cssVar("--line");
  const base = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { color: fg } } },
  };
  const axisX = { ticks: { color: fg }, grid: { color: grid } };
  charts.push(
    new Chart(document.getElementById("d-metrics"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "热度", data: s.points.map((p) => p.hot), yAxisID: "y", borderColor: cssVar("--c1"), tension: 0.2 },
          { label: "收藏", data: s.points.map((p) => p.fav), yAxisID: "y1", borderColor: cssVar("--c2"), tension: 0.2 },
          { label: "点赞", data: s.points.map((p) => p.like), yAxisID: "y1", borderColor: cssVar("--c3"), tension: 0.2 },
        ],
      },
      options: {
        ...base,
        scales: {
          x: axisX,
          y: { position: "left", ticks: { color: fg, callback: (v) => fmtNum(v) }, grid: { color: grid } },
          y1: { position: "right", ticks: { color: fg, callback: (v) => fmtNum(v) }, grid: { drawOnChartArea: false } },
        },
      },
    }),
  );
  const keys = Object.keys(RANK_NAMES).filter((k) => s.points.some((p) => p.ranks[k] !== undefined));
  charts.push(
    new Chart(document.getElementById("d-ranks"), {
      type: "line",
      data: {
        labels,
        datasets: keys.map((k, i) => ({
          label: RANK_NAMES[k] + "榜名次",
          data: s.points.map((p) => p.ranks[k] ?? null),
          borderColor: cssVar(`--c${i + 1}`),
          spanGaps: false,
          tension: 0.2,
        })),
      },
      options: {
        ...base,
        scales: { x: axisX, y: { reverse: true, min: 1, ticks: { color: fg, precision: 0 }, grid: { color: grid } } },
      },
    }),
  );
}

function setActive(container, attr, value) {
  for (const b of container.querySelectorAll("button")) b.classList.toggle("active", b.dataset[attr] === value);
}

function showTab(tab) {
  state.tab = tab;
  setActive(document.getElementById("tabs"), "tab", tab);
  for (const t of ["rank", "surge", "watch"]) document.getElementById("view-" + t).hidden = t !== tab;
  if (tab === "rank") renderRank();
  else if (tab === "surge") renderSurge();
  else renderWatch();
}

function onSeg(id, attr, apply) {
  document.getElementById(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    apply(b.dataset[attr]);
    setActive(e.currentTarget, attr, b.dataset[attr]);
  });
}

function wire() {
  onSeg("tabs", "tab", showTab);
  onSeg("rank-keys", "key", (v) => {
    state.rankKey = v;
    renderRank();
  });
  onSeg("surge-sort", "sort", (v) => {
    state.sort = v;
    renderSurge();
  });
  onSeg("surge-type", "type", (v) => {
    state.type = v;
    renderSurge();
  });
  document.getElementById("rank-q").addEventListener("input", (e) => {
    state.q = e.target.value;
    renderRank();
  });
  const dlg = document.getElementById("detail");
  document.getElementById("d-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close();
  });
  dlg.addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
}

async function init() {
  wire();
  try {
    [status, ranks, growth] = await Promise.all([
      getJSON("status.json"),
      getJSON("ranks_latest.json"),
      getJSON("growth_latest.json"),
    ]);
  } catch (e) {
    document.getElementById("status").textContent = "数据加载失败：" + e.message;
    return;
  }
  growthById = new Map(growth.items.map((g) => [g.id, g]));
  renderStatus();
  showTab("rank");
  const m = location.hash.match(/^#s=(\d+)$/);
  if (m) openDetail(m[1]);
}

init();
