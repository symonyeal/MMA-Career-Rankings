// The notebook's analyses (analysis/build_notebook.py) as a static page. Data: data.js, written by
// analysis/build_site.py. Sections draw lazily when visible and redraw when a control they read changes.
"use strict";

const D = window.DATA, M = D.meta, F = D.F, NF = F.name.length;
const I = new Map(F.name.map((f, i) => [f, i]));

// analysis/viz.py: THEME, CHART_COLORWAY, METHOD_COLOR, HEATMAP_COLORSCALE and the "ufc_dark" template.
const T = {
  bg: "#0b1220", surface: "#161f33", surface_alt: "#111a2b", text: "#f8fafc", text_2: "#cbd5e1",
  muted: "#94a3b8", caption: "#64748b", border: "#2a3650", border_strong: "#3b4a6b", primary: "#38bdf8",
  secondary: "#a78bfa", accent: "#fbbf24", accent_2: "#f472b6", positive: "#34d399", negative: "#f87171",
  neutral: "#94a3b8",
};
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif';
const COLORWAY = ["#38bdf8", "#fbbf24", "#34d399", "#a78bfa", "#fb7185", "#f97316", "#22d3ee", "#a3e635", "#e879f9", "#60a5fa"];
const METHOD_COLOR = ["#fb7185", "#a78bfa", "#34d399", "#fbbf24", "#22d3ee", "#94a3b8", "#64748b"];
const HEAT = [[0, T.surface_alt], [0.45, "#1d4ed8"], [1, T.primary]];
const AX = {
  gridcolor: T.border, zerolinecolor: T.border_strong, linecolor: T.border_strong, tickcolor: T.border_strong,
  tickfont: { color: T.text_2, size: 11 }, title: { font: { color: T.text_2, size: 12 } }, automargin: true,
};
const TPL = { layout: {
  paper_bgcolor: T.bg, plot_bgcolor: T.bg, font: { family: FONT, color: T.text, size: 13 },
  title: { font: { family: FONT, color: T.text, size: 16 } }, colorway: COLORWAY, xaxis: AX, yaxis: AX,
  legend: { bgcolor: "rgba(0,0,0,0)", font: { color: T.text_2, size: 11 } },
  hoverlabel: { bgcolor: T.surface, bordercolor: T.border_strong, font: { family: FONT, color: T.text, size: 12 } },
  margin: { t: 56, r: 36, b: 48, l: 56 },
} };
const CFG = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmt = (v, d = 0) => v == null ? "" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const iso = (day) => new Date(day * 864e5).toISOString().slice(0, 10);
const short = (d) => D.short[d] || d;
const range = (n) => [...Array(n).keys()];
const divColor = (d) => COLORWAY[Math.max(0, D.divisions.indexOf(d)) % COLORWAY.length];
const chip = (r) => r == null ? "" : `<span class="chip-rank ${r <= 3 ? "r" + r : ""}">${r}</span>`;

function plot(id, data, layout = {}) {
  if (!window.Plotly) return;
  if (typeof layout.title === "string") layout = { ...layout, title: { text: layout.title } };  // plotly.js >= 3
  if (innerWidth < 700) {  // phone: drop the gutters reserved for end-of-line labels; axes automargin
    const m = layout.margin || {};
    layout = { ...layout, margin: { ...m, l: Math.min(m.l ?? 56, 48), r: Math.min(m.r ?? 36, 16) },
      title: { ...layout.title, font: { size: 13 } } };
  }
  Plotly.react($(id), data, { height: 460, ...layout, template: TPL }, CFG);
}
function plotFig(id, f, patch = {}) {
  const g = structuredClone(f);
  plot(id, g.data, { ...g.layout, ...patch });
}
function empty(id, msg, height = 300) {
  plot(id, [], { height, xaxis: { visible: false }, yaxis: { visible: false },
    annotations: [{ text: msg, showarrow: false, x: 0.5, y: 0.5, xref: "paper", yref: "paper", font: { color: T.caption, size: 14 } }] });
}

// ---- state and the control room -------------------------------------------------------------------------
const S = {
  g: "M", div: "All", top: 30, min: M.min_periods, view: "all_time", q: "",
  sel: ["Jon Jones", "Georges St-Pierre", "Islam Makhachev"].filter((f) => I.has(f)),
  a: M.a, s: M.s, rob: "Georges St-Pierre", rec: "Jon Jones", streak: null,
  dv: new Set(["Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight", "Featherweight"]),
  k: "10", idx: false, stSort: "length", stMin: 5, dmMin: 8,
};
const VIEWS = {
  all_time: { rank: "at", val: "score", label: "All-time score", div: "div" },
  prime: { rank: "pr", val: "plevel", label: "Prime level", div: "div" },
  current: { rank: "cr", val: "cur", label: "Current rating", div: "cdiv" },
};

// Class rows (ratings.division_legacy): the All-time score split by the class it was earned in. A fighter
// belongs to every class where they earned credit; Current places a fighter in their current class.
const C = D.classes.map(([f, d, rank, t, k, r]) => ({ f, d, rank, t, k, r }));
const member = new Map();
C.forEach((u) => { if (!member.has(u.f)) member.set(u.f, new Map()); member.get(u.f).set(u.d, u); });
const inClass = (i, d, view = S.view) => view === "current" ? F.cdiv[i] === d : member.get(i)?.has(d);
function pool(view = S.view, useDiv = true) {
  return range(NF).filter((i) => F.g[i] === S.g && F.n[i] >= S.min && (!useDiv || S.div === "All" || inClass(i, S.div, view)));
}
// A board unit is a whole career (no class chosen) or the part of it earned in one class.
const uscore = (u, a = M.a, s = M.s) => M.scale * (a * u.t + (1 - a) * (s * u.k + (1 - s) * u.r));
function units(g, div) {
  return div === "All"
    ? range(NF).filter((i) => F.g[i] === g && F.at[i] != null).map((i) => ({ f: i, d: "All", rank: F.at[i], t: F.T[i], k: F.S[i], r: F.R[i] }))
    : C.filter((u) => F.g[u.f] === g && u.d === div);
}
function boardRows(view = S.view, useDiv = true) {
  const r = VIEWS[view].rank;
  return pool(view, useDiv).filter((i) => F[r][i] != null).sort((a, b) => F[r][a] - F[r][b]);
}

const SECTIONS = {}, dirty = new Set(Object.keys(SECTIONS)), visible = new Set();
function mark(...ids) {
  (ids.length ? ids : Object.keys(SECTIONS)).forEach((i) => dirty.add(i));
  flush();
}
function flush() {
  for (const id of [...dirty]) if (visible.has(id)) { dirty.delete(id); SECTIONS[id](); }
}

function seg(id, key, after) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $(id).querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    S[key] = b.dataset.v;
    after();
  });
}
function slider(id, out, key, after, parse = Number) {
  const el = $(id);
  el.value = S[key];
  $(out).textContent = el.value;
  el.addEventListener("input", () => { S[key] = parse(el.value); $(out).textContent = el.value; after(); });
}
function divisionOptions() {
  const have = new Set([...C.filter((u) => F.g[u.f] === S.g).map((u) => u.d), ...F.cdiv.filter((d, i) => F.g[i] === S.g && d)]);
  const order = [...have].sort((a, b) => ((D.divisions.indexOf(a) + 99) % 99) - ((D.divisions.indexOf(b) + 99) % 99) || a.localeCompare(b));
  if (!have.has(S.div)) S.div = "All";
  $("c-div").innerHTML = ["All", ...order].map((d) => `<option ${d === S.div ? "selected" : ""}>${esc(d)}</option>`).join("");
}

if (!window.Plotly) document.querySelector(".hero").insertAdjacentHTML("beforeend",
  `<p class="callout">Charts need plotly.js from cdn.jsdelivr.net, which did not load. Tables still work.</p>`);

// ---- hero -----------------------------------------------------------------------------------------------
$("facts").innerHTML = [
  [M.through, "data through"], [fmt(M.rated_bouts), "rated bouts"], [fmt(M.fighters), "rated fighters"],
  [fmt(M.established), `on the boards (${M.min_periods}+ rated bouts)`], [fmt(M.contender), "contender line"],
].map(([v, l]) => `<div class="fact"><b>${v}</b><span>${l}</span></div>`).join("");
$("foot").textContent = `Snapshot ${M.snapshot}. Rankings are the published boards; see README.md and RANKINGS.md.`;
$("names").innerHTML = F.name.map((f) => `<option value="${esc(f)}">`).join("");

// ---- 1. rankings ----------------------------------------------------------------------------------------
SECTIONS.rankings = () => {
  if (S.view === "all_time" && S.div !== "All") return classTable();
  const rows = boardRows().filter((i) => !S.q || F.name[i].toLowerCase().includes(S.q)).slice(0, S.top);
  const V = VIEWS[S.view], vmax = Math.max(...rows.map((i) => F[V.val][i])), vmin = Math.min(...rows.map((i) => F[V.val][i]));
  const bar = (v, d) => `<td class="num bar"><i style="width:${(100 * (v - vmin * 0.98) / (vmax - vmin * 0.98 || 1)).toFixed(1)}%"></i><span>${fmt(v, d)}</span></td>`;
  const now = (i) => F.cdiv[i] && F.cdiv[i] !== F.div[i] ? ` <span class="dim">→ now ${esc(short(F.cdiv[i]))}</span>` : "";
  const name = (i) => `<td class="name"><button class="namebtn" data-f="${esc(F.name[i])}">${esc(F.name[i])}</button></td>`;
  const cls = S.div !== "All";  // Prime and Current within a class: the published order restricted, renumbered
  const pos = new Map(rows.map((i, k) => [i, k + 1]));
  const cols = {
    all_time: [["#", (i) => `<td>${chip(F.at[i])}</td>`], ["Fighter", name], ["Division", (i) => `<td>${esc(F.div[i])}${now(i)}</td>`],
      ["Score", (i) => bar(F.score[i], 1)], ["Prime", (i) => `<td class="num">${fmt(F.plevel[i])}</td>`],
      ["Prime rank", (i) => `<td class="num">${F.pr[i] ?? ""}</td>`], ["Elite wins", (i) => `<td class="num">${F.pwins[i] ?? ""}</td>`],
      ["Rated bouts", (i) => `<td class="num dim">${F.n[i]}</td>`], ["Last bout", (i) => `<td class="dim">${F.last[i] ?? ""}</td>`]],
    prime: [["#", (i) => `<td>${chip(cls ? pos.get(i) : F.pr[i])}</td>`], ["Fighter", name], ["Division", (i) => `<td>${esc(F.div[i])}</td>`],
      ["Prime", (i) => bar(F.plevel[i], 0)], ["Elite wins", (i) => `<td class="num">${F.pwins[i] ?? ""}</td>`],
      ["Best decade", (i) => `<td class="dim">${F.p0[i] ?? ""}–${F.p1[i] ?? ""}</td>`], ["Prime #", (i) => `<td class="num dim">${F.pr[i] ?? ""}</td>`],
      ["All-time rank", (i) => `<td class="num dim">${F.at[i] ?? ""}</td>`]],
    current: [["#", (i) => `<td>${chip(cls ? pos.get(i) : F.cr[i])}</td>`], ["Fighter", name], ["Division", (i) => `<td>${esc(F.cdiv[i])}</td>`],
      ["Rating", (i) => bar(F.cur[i], 0)], ["UFC bouts", (i) => `<td class="num">${F.ufc[i] ?? ""}</td>`],
      ["Last bout", (i) => `<td class="dim">${F.last[i] ?? ""}</td>`], ["Current #", (i) => `<td class="num dim">${F.cr[i] ?? ""}</td>`],
      ["All-time rank", (i) => `<td class="num dim">${F.at[i] ?? ""}</td>`]],
  }[S.view].filter(([h]) => cls || !/^(Prime|Current) #$/.test(h));
  $("board").innerHTML = rows.length
    ? `<table><thead><tr>${cols.map(([h]) => `<th class="${/^(#|Fighter|Division|Best|Last)/.test(h) ? "" : "num"}">${h}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((i) => `<tr>${cols.map(([, c]) => c(i)).join("")}</tr>`).join("") + "</tbody></table>"
    : `<p class="note" style="padding:10px 14px">No ranked fighters match the current filters.</p>`;
};
function classTable() {
  const U = units(S.g, S.div).filter((u) => F.n[u.f] >= S.min && (!S.q || F.name[u.f].toLowerCase().includes(S.q)))
    .sort((x, y) => x.rank - y.rank).slice(0, S.top);
  if (!U.length) { $("board").innerHTML = `<p class="note" style="padding:10px 14px">No ranked fighters in this class.</p>`; return; }
  const v = U.map((u) => uscore(u)), vmax = Math.max(...v);
  const pts = (u) => [M.scale * M.a * u.t, M.scale * (1 - M.a) * M.s * u.k, M.scale * (1 - M.a) * (1 - M.s) * u.r];
  const other = (u) => [...member.get(u.f)].filter(([d]) => d !== u.d).map(([d, w]) => `${short(d)} #${w.rank}`).join(", ");
  $("board").innerHTML = `<table><thead><tr><th>#</th><th>Fighter</th><th class="num">Class score</th><th class="num">Share of All-time</th>
    <th class="num">Championships</th><th class="num">Career skill</th><th class="num">Résumé</th><th class="num">All-time #</th><th>Also ranked</th></tr></thead><tbody>` +
    U.map((u, k) => { const p = pts(u); return `<tr><td>${chip(u.rank)}</td>
      <td class="name"><button class="namebtn" data-f="${esc(F.name[u.f])}">${esc(F.name[u.f])}</button></td>
      <td class="num bar"><i style="width:${(100 * v[k] / vmax).toFixed(1)}%"></i><span>${fmt(v[k], 1)}</span></td>
      <td class="num">${fmt(100 * v[k] / F.score[u.f])}%</td><td class="num dim">${fmt(p[0])}</td><td class="num dim">${fmt(p[1])}</td>
      <td class="num dim">${fmt(p[2])}</td><td class="num dim">${F.at[u.f] ?? ""}</td><td class="dim">${esc(other(u))}</td></tr>`; }).join("") +
    "</tbody></table>";
}
$("board").addEventListener("click", (e) => {
  const b = e.target.closest(".namebtn");
  if (b) addFighter(b.dataset.f, true);
});
seg("c-view", "view", () => mark("rankings", "placement", "divisions"));
$("c-search").addEventListener("input", (e) => { S.q = e.target.value.trim().toLowerCase(); mark("rankings"); });

// ---- 2. score anatomy and the exchange rates -----------------------------------------------------------
function rerank(U, a, s) {
  return new Map([...U].sort((x, y) => uscore(y, a, s) - uscore(x, a, s)).map((u, r) => [u, r + 1]));
}
SECTIONS.anatomy = () => {
  const { a, s } = S, U = units(S.g, S.div), R = rerank(U, a, s), K = Math.min(20, S.top), cls = S.div !== "All";
  const shown = U.filter((u) => F.n[u.f] >= S.min).sort((x, y) => R.get(x) - R.get(y)).slice(0, K).reverse();
  const lab = shown.map((u) => {
    const d = u.rank - R.get(u);
    return `#${R.get(u)}  ${F.name[u.f]}` + (d ? `  (${d > 0 ? "▲" : "▼"}${Math.abs(d)})` : "");
  });
  const ev = (txt) => (u) => (cls ? `${fmt(100 * uscore(u) / F.score[u.f])}% of the All-time score earned at ${short(u.d)}` : txt(u.f));
  const parts = [
    [`Championships · ${fmt(100 * a, 1)}%`, (u) => M.scale * a * u.t, T.accent, ev((i) => `${F.tw[i]} qualifying title wins`)],
    [`Career skill · ${fmt(100 * (1 - a) * s, 1)}%`, (u) => M.scale * (1 - a) * s * u.k, T.primary, ev((i) => `${F.cy[i]} contributing career years`)],
    [`Contender résumé · ${fmt(100 * (1 - a) * (1 - s), 1)}%`, (u) => M.scale * (1 - a) * (1 - s) * u.r, T.positive, ev((i) => `${F.cw[i]} contender wins`)],
  ];
  const tot = shown.map((u) => uscore(u, a, s));
  const data = parts.map(([name, f, color, ev]) => ({
    type: "bar", orientation: "h", name, x: shown.map(f), y: lab, marker: { color },
    customdata: shown.map((u, j) => [fmt(tot[j], 1), ev(u)]),
    hovertemplate: `<b>%{y}</b><br>${name}: %{x:.1f} points<br>${cls ? "Class" : "All-time"} total: %{customdata[0]}<br>%{customdata[1]}<extra></extra>`,
  }));
  data.push({ type: "scatter", mode: "text", x: tot, y: lab, text: tot.map((v) => "  " + fmt(v)), textposition: "middle right",
    textfont: { color: T.text, size: 11 }, hoverinfo: "skip", showlegend: false, cliponaxis: false });
  plot("anat-chart", data, {
    title: (cls ? `${S.div}: ` : "All-time: ") + (published() ? "why the leaders rank here" : "the board at the chosen exchange rates (▲▼ against published)"),
    barmode: "stack", height: Math.max(470, 31 * shown.length + 185), hovermode: "closest",
    xaxis: { title: { text: cls ? `Weighted points earned at ${S.div}` : "Weighted points in the All-time score" }, rangemode: "tozero", range: [0, Math.max(...tot, 1) * 1.16] },
    legend: { orientation: "h", y: -0.16, x: 0, traceorder: "normal" }, margin: { t: 68, r: 84, b: 100, l: 60 },
  });

  // Published top 100 against the new order: overlap at the top and Spearman's rho.
  const P = [...U].sort((x, y) => x.rank - y.rank).slice(0, 100);
  const q = [...P].sort((x, y) => R.get(x) - R.get(y)), pos = new Map(q.map((u, r) => [u, r + 1]));
  const n = P.length, rho = n > 1 ? 1 - 6 * P.reduce((t, u, r) => t + (r + 1 - pos.get(u)) ** 2, 0) / (n * (n * n - 1)) : 1;
  const top10 = P.slice(0, 10).filter((u) => R.get(u) <= 10).length;
  const mv = P.slice(0, 50).map((u) => [u.f, u.rank - R.get(u)]).sort((x, y) => y[1] - x[1]);
  const who = (l) => l.map(([i, d]) => `${esc(F.name[i])} ${d > 0 ? "+" : ""}${d}`).join(", ");
  const num1 = F.name[[...R].find(([, r]) => r === 1)[0].f];
  $("anat-summary").innerHTML = published()
    ? `At the published rates (a = ${M.a}, s = ${M.s}). Move a slider to see how much of the order is the exchange rate.`
    : `At a = ${fmt(a, 3)}, s = ${fmt(s, 3)}: #1 is <b>${esc(num1)}</b>; ${top10} of the published top 10 stay in the top 10;
       Spearman's ρ over the published top 100 is <b>${fmt(rho, 3)}</b>.
       Largest moves in the published top 50 — up: ${who(mv.slice(0, 3).filter((x) => x[1] > 0)) || "none"};
       down: ${who(mv.slice(-3).reverse().filter((x) => x[1] < 0)) || "none"}.`;
  robustness();
};
const published = () => Math.abs(S.a - M.a) < 1e-9 && Math.abs(S.s - M.s) < 1e-9;
function robustness() {
  const f = I.get(S.rob);
  if (f == null || F.at[f] == null) return empty("rob-chart", "Pick a fighter ranked on an All-time board.");
  const E = units(F.g[f], "All"), me = E.find((u) => u.f === f), G = range(21).map((k) => k / 20);
  const z = G.map((s) => G.map((a) => { const v = uscore(me, a, s); return 1 + E.filter((u) => uscore(u, a, s) > v).length; }));
  const zmax = Math.max(10, Math.min(Math.max(...z.flat()), 3 * F.at[f]));
  plot("rob-chart", [
    { type: "heatmap", x: G, y: G, z, zmin: 1, zmax, colorscale: HEAT, reversescale: true,
      texttemplate: "%{z}", textfont: { size: 9, color: T.text }, colorbar: { title: { text: "rank" } },
      hovertemplate: "a = %{x:.2f}, s = %{y:.2f}<br>rank %{z}<extra></extra>" },
    { type: "scatter", mode: "markers", x: [M.a], y: [M.s], hoverinfo: "skip", showlegend: false,
      marker: { size: 18, symbol: "circle-open", color: T.accent, line: { width: 3 } } },
  ], {
    title: `${S.rob}: All-time rank across exchange rates (published #${F.at[f]})`, height: 520,
    xaxis: { title: { text: "championships weight a" }, dtick: 0.1 }, yaxis: { title: { text: "career-skill share s" }, dtick: 0.1 },
    margin: { t: 60, r: 20, b: 56, l: 64 },
  });
  if (!$("rob-chart").bound) {
    $("rob-chart").bound = true;
    $("rob-chart").on("plotly_click", (ev) => { const p = ev.points[0]; if (p.data.type === "heatmap") setRates(p.x, p.y); });
  }
}
function setRates(a, s) {
  S.a = a; S.s = s;
  $("w-a").value = a; $("w-s").value = s; $("o-a").textContent = fmt(a, 3); $("o-s").textContent = fmt(s, 3);
  mark("anatomy");
}
["a", "s"].forEach((k) => $("w-" + k).addEventListener("input", (e) => setRates(k === "a" ? +e.target.value : S.a, k === "s" ? +e.target.value : S.s)));
$("w-reset").addEventListener("click", () => setRates(M.a, M.s));
$("rob-pick").value = S.rob;
$("rob-pick").addEventListener("change", (e) => { if (I.has(e.target.value)) { S.rob = e.target.value; robustness(); } });

// ---- 3. résumé vs rating ---------------------------------------------------------------------------------
SECTIONS.placement = () => {
  const cu = S.view === "all_time" && S.div !== "All" ? new Map(units(S.g, S.div).map((u) => [u.f, u])) : null;
  const V = cu ? { ...VIEWS.all_time, label: `${S.div} class score` } : VIEWS[S.view];
  const val = (i) => (cu ? uscore(cu.get(i)) : F[V.val][i]);
  const rows = cu ? [...cu.values()].filter((u) => F.n[u.f] >= S.min).sort((x, y) => x.rank - y.rank).map((u) => u.f).slice(0, S.top)
    : boardRows().slice(0, S.top);
  if (!rows.length) return empty("place-chart", "No ranked fighters match the current filters.");
  const by = new Map();
  rows.forEach((i, r) => { const d = F[V.div][i] || "Unknown"; if (!by.has(d)) by.set(d, []); by.get(d).push([i, r + 1]); });
  const mean = (l) => l.reduce((t, [i]) => t + val(i), 0) / l.length;
  const data = [...by].sort((x, y) => mean(y[1]) - mean(x[1])).map(([d, l]) => ({
    type: "scatter", mode: "markers", name: d, x: l.map(([i]) => F.n[i]), y: l.map(([i]) => val(i)),
    marker: { size: l.map(([, r]) => (r <= 10 ? 16 : 9)), color: divColor(d), opacity: 0.82, line: { color: "white", width: 0.8 } },
    customdata: l.map(([i, r]) => [r, F.name[i], F.last[i]]),
    hovertemplate: `<b>#%{customdata[0]} %{customdata[1]}</b><br>${d}<br>rated bouts=%{x}<br>${V.label}=%{y:.1f}<br>last bout=%{customdata[2]}<extra></extra>`,
  }));
  const ann = rows.slice(0, 10).map((i, r) => ({ x: F.n[i], y: val(i), text: String(r + 1), showarrow: false,
    font: { size: 10, color: r ? T.text : T.bg }, bgcolor: r ? T.surface : T.accent, bordercolor: T.border_strong, borderpad: 2 }))
    .concat(rows.slice(0, 6).map((i, r) => ({ x: F.n[i], y: val(i), text: F.name[i], showarrow: false, xanchor: "left",
      xshift: 14, yshift: r % 2 ? -10 : 10, font: { size: 11, color: T.text } })));
  plot("place-chart", data, {
    title: `Top ${rows.length} placement — ${V.label}`, height: 560, annotations: ann,
    xaxis: { title: { text: "Rated bouts" }, rangemode: "tozero" }, yaxis: { title: { text: V.label } },
    legend: { orientation: "h", y: -0.2 }, margin: { l: 70, r: 40, t: 70, b: 110 },
  });
};

// ---- 4. fighters: arcs and tale of the tape -------------------------------------------------------------
function decode(name) {
  const t = D.traj[name];
  if (!t) return null;
  let d = t[0];
  return { day: t[1].map((x) => (d += x)), mu: t[2], m: t[3], r: t[4], o: t[5] };
}
function addFighter(f, go = false) {
  if (!I.has(f)) return;
  if (!S.sel.includes(f)) S.sel = [...S.sel, f].slice(-6);
  mark("fighters");
  if (go) $("fighters").scrollIntoView({ behavior: "smooth" });
}
const RES = { W: "Win", L: "Loss", D: "Draw", N: "" };
function arcTraces(names, colors) {
  const data = [], ann = [];
  const [W, minN, label] = M.peak;
  names.forEach((f, k) => {
    const t = decode(f);
    if (!t) return;
    const c = colors[k], x = t.day.map(iso);
    const txt = t.day.map((_, j) => `${RES[t.r[j]]} vs ${t.o[j] >= 0 ? D.N[t.o[j]] : "?"}${t.m[j] !== "-" ? " · " + M.methods[+t.m[j]] : ""}`);
    data.push({ type: "scatter", mode: "lines", name: f, x, y: t.mu, line: { color: c, width: 2 }, text: txt,
      hovertemplate: `<b>${esc(f)}</b><br>%{x|%Y-%m-%d}<br>rating %{y:.0f}<br>%{text}<extra></extra>` });
    const g = {};
    t.m.split("").forEach((m, j) => { (g[m] ||= []).push(j); });
    Object.entries(g).forEach(([m, J]) => data.push({
      type: "scatter", mode: "markers", x: J.map((j) => x[j]), y: J.map((j) => t.mu[j]), showlegend: false, hoverinfo: "skip",
      marker: { size: 7, color: m === "-" ? T.caption : METHOD_COLOR[+m], line: { color: c, width: 1.5 } },
    }));
    // Best 5-year stretch: rolling mean over (t − W, t] with at least minN bouts (viz.trajectory_chart).
    let lo = 0, sum = 0, best = null;
    t.day.forEach((d, j) => {
      sum += t.mu[j];
      while (t.day[lo] <= d - W) sum -= t.mu[lo++];
      const n = j - lo + 1;
      if (n >= minN && (!best || sum / n > best[1])) best = [j, sum / n];
    });
    if (best) ann.push({ x: x[best[0]], y: t.mu[best[0]], text: `${label} ${fmt(best[1])}`, showarrow: true, arrowhead: 2, ax: 0, ay: -30, font: { color: c, size: 10 } });
    const e = t.day.length - 1;
    ann.push({ x: x[e], y: t.mu[e], text: f, showarrow: false, xanchor: "left", xshift: 8, font: { color: c, size: 11 } });
  });
  return { data, ann };
}
const contender = () => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: M.contender, y1: M.contender, line: { color: T.muted, dash: "dash", width: 1 } });
SECTIONS.fighters = () => {
  const colors = S.sel.map((_, k) => COLORWAY[k % COLORWAY.length]);
  $("sel-chips").innerHTML = S.sel.map((f, k) => `<span class="chip"><i style="background:${colors[k]}"></i>${esc(f)}<button data-f="${esc(f)}" aria-label="remove">×</button></span>`).join("");
  if (!S.sel.length) { empty("arc-chart", "Add a fighter to draw their career."); $("cards").innerHTML = ""; return; }
  const { data, ann } = arcTraces(S.sel, colors);
  plot("arc-chart", data, {
    title: "Base WHR skill, fight by fight", height: 540, hovermode: "closest", annotations: ann,
    shapes: S.sel.some((f) => Math.min(...(decode(f)?.mu ?? [Infinity])) < M.contender + 150) ? [contender()] : [],
    xaxis: { title: { text: "Event date" }, type: "date" }, yaxis: { title: { text: "Rating" } },
    legend: { orientation: "h", y: 1.1, x: 0, yanchor: "bottom" }, margin: { r: 150, t: 80 },
  });
  $("cards").innerHTML = S.sel.map((f, k) => card(I.get(f), colors[k])).join("");
};
function card(i, c) {
  const pts = [M.scale * M.a * F.T[i], M.scale * (1 - M.a) * M.s * F.S[i], M.scale * (1 - M.a) * (1 - M.s) * F.R[i]];
  const tot = pts.reduce((x, y) => x + y, 0) || 1;
  const row = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
  const rk = (r, v) => (r != null ? `#${r} · ` : "<span class='dim'>not ranked</span> · ") + v;
  return `<div class="card" style="--c:${c}"><h4>${esc(F.name[i])}</h4>
    <div class="sub">${esc(F.div[i])}${F.cdiv[i] && F.cdiv[i] !== F.div[i] ? ` · now ${esc(F.cdiv[i])}` : ""} · ${F.w[i]}–${F.l[i]}${F.d[i] ? "–" + F.d[i] : ""}</div>
    <dl>${row("All-time", rk(F.at[i], fmt(F.score[i], 1)))}
      ${row("Prime", rk(F.pr[i], F.plevel[i] != null ? `${fmt(F.plevel[i])} · ${F.pwins[i]} elite wins` : "—"))}
      ${row("Best decade", F.p0[i] != null ? `${F.p0[i]}–${F.p1[i]}` : "—")}
      ${row("Current", rk(F.cr[i], fmt(F.cur[i])))}
      ${row("Peak rating", fmt(F.peak[i]))}
      ${row("Career mass", `${fmt(F.mass[i])} · ${F.cy[i]} of ${F.ay[i]} years`)}
      ${row("Dominance", F.dom[i] != null ? `${fmt(F.dom[i], 2)} over ${F.domw[i]} wins` : "—")}
      ${row("By class", [...(member.get(i) ?? [])].sort((x, y) => uscore(y[1]) - uscore(x[1]))
        .map(([d, u]) => `${short(d)} #${u.rank} · ${fmt(100 * uscore(u) / F.score[i])}%`).join("<br>") || "—")}
      ${row("Rated bouts", `${F.n[i]} · last ${F.last[i] ?? "—"}`)}</dl>
    <div class="stack">${pts.map((p, j) => `<span style="width:${(100 * p / tot).toFixed(1)}%;background:${[T.accent, T.primary, T.positive][j]}"></span>`).join("")}</div>
    <small>All-time points: championships ${fmt(pts[0])} · skill ${fmt(pts[1])} · résumé ${fmt(pts[2])}</small></div>`;
}
$("sel-chips").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b) { S.sel = S.sel.filter((f) => f !== b.dataset.f); mark("fighters"); }
});
$("sel-add").addEventListener("change", (e) => { addFighter(e.target.value); e.target.value = ""; });

// ---- 5. careers: receipt, shape, ladder, all-time vs prime ---------------------------------------------
function receiptChart() {
  const r = D.receipt[S.rec], i = I.get(S.rec);
  if (!r) return empty("rec-chart", "No rated years for this fighter.");
  const y = r.map((x) => x[0]);
  plot("rec-chart", [
    { type: "bar", name: "credited excess", x: y, y: r.map((x) => x[3]), base: r.map((x) => x[2]), marker: { color: T.primary, opacity: 0.85 },
      hovertemplate: "year %{x}<br>credited %{y:.0f} rating points<extra></extra>" },
    { type: "scatter", mode: "lines", name: "that year's bar", x: y, y: r.map((x) => x[2]), line: { color: T.accent, width: 2, dash: "dash" },
      hovertemplate: "year %{x}<br>bar %{y:.0f}<extra></extra>" },
    { type: "scatter", mode: "lines+markers", name: "rating that year", x: y, y: r.map((x) => x[1]), line: { color: T.text, width: 2 },
      marker: { size: 7 }, hovertemplate: "year %{x}<br>rating %{y:.0f}<extra></extra>" },
  ], { title: `Where ${S.rec} earned it — career mass ${fmt(F.mass[i])}`, height: 430, barmode: "overlay",
    xaxis: { title: { text: "year" }, dtick: y.length > 14 ? 2 : 1 }, yaxis: { title: { text: "rating" } },
    legend: { orientation: "h", y: 1.12, x: 0 } });
}
SECTIONS.careers = () => {
  receiptChart();
  // Height or duration (viz.career_shape_scatter).
  const P = pool("all_time").filter((i) => F.mass[i] > 0).sort((x, y) => F.mass[y] - F.mass[x]).slice(0, Math.max(20, S.top));
  if (P.length) {
    const ms = P.map((i) => F.mass[i]), yrs = P.map((i) => F.ay[i]), mn = Math.min(...ms), sp = Math.max(...ms) - mn || 1;
    const qs = [0.25, 0.5, 0.75, 0.95].map((q) => [...ms].sort((a, b) => a - b)[Math.round(q * (ms.length - 1))]);
    const g = range(60).map((k) => Math.max(1, Math.min(...yrs) - 0.5) + k * (Math.max(...yrs) - Math.min(...yrs) + 1) / 59);
    plot("shape-chart", [
      ...qs.map((L) => ({ type: "scatter", mode: "lines", x: g, y: g.map((x) => L / x), hoverinfo: "skip", showlegend: false,
        line: { color: T.border_strong, width: 1, dash: "dot" } })),
      { type: "scatter", mode: "markers+text", x: yrs, y: P.map((i) => F.mass[i] / F.ay[i]),
        text: P.map((i, r) => (r < 12 ? F.name[i] : "")), textposition: "top center", textfont: { size: 10, color: T.muted },
        marker: { size: ms.map((m) => 8 + 14 * (m - mn) / sp), color: ms, colorscale: [[0, T.caption], [1, T.accent]], showscale: true,
          colorbar: { title: { text: "career<br>mass" } }, line: { color: T.bg, width: 1 } },
        customdata: P.map((i) => [F.name[i], F.mass[i], F.n[i]]), showlegend: false,
        hovertemplate: "<b>%{customdata[0]}</b><br>active years %{x}<br>mean yearly excess %{y:.0f}<br>career mass %{customdata[1]:.0f}<br>rated bouts %{customdata[2]}<extra></extra>" },
    ], { title: "What built the score: years above the field vs distance above it", height: 560,
      xaxis: { title: { text: "active years (each contributes once)" } }, yaxis: { title: { text: "mean yearly excess over the bar" }, rangemode: "tozero" } });
  } else empty("shape-chart", "No careers match the current filters.");
  plotFig("ladder-chart", D.ladder, { height: 560, legend: { font: { size: 10 } }, xaxis: { ...D.ladder.layout.xaxis, type: "category" } });
  legacyPrime();
};
function legacyPrime() {
  const P = pool("all_time").filter((i) => F.n[i] >= Math.max(8, S.min) && F.prime[i] != null && F.score[i] != null)
    .sort((x, y) => F.score[y] - F.score[x]).slice(0, Math.max(20, 2 * S.top));
  if (P.length < 3) return empty("lp-chart", "Too few fighters match the current filters.");
  const x = P.map((i) => F.prime[i]), y = P.map((i) => F.score[i]), n = P.length;
  const mx = x.reduce((a, b) => a + b) / n, my = y.reduce((a, b) => a + b) / n;
  const b1 = x.reduce((t, xi, k) => t + (xi - mx) * (y[k] - my), 0) / x.reduce((t, xi) => t + (xi - mx) ** 2, 0), b0 = my - b1 * mx;
  const res = P.map((i, k) => [i, y[k] - (b0 + b1 * x[k])]).sort((u, v) => v[1] - u[1]);
  const by = new Map();
  P.forEach((i) => { const d = F.div[i] || "—"; if (!by.has(d)) by.set(d, []); by.get(d).push(i); });
  const xs = [Math.min(...x), Math.max(...x)];
  const lab = [...res.slice(0, 4), ...res.slice(-4)].map(([i, r]) => ({ x: F.prime[i], y: F.score[i], text: F.name[i],
    showarrow: true, arrowhead: 0, ax: 0, ay: r > 0 ? -22 : 22, font: { size: 10, color: r > 0 ? T.positive : T.accent_2 }, arrowcolor: T.border_strong }));
  plot("lp-chart", [
    { type: "scatter", mode: "lines", x: xs, y: xs.map((v) => b0 + b1 * v), line: { color: T.muted, dash: "dash" }, hoverinfo: "skip", showlegend: false },
    ...[...by].map(([d, l]) => ({ type: "scatter", mode: "markers", name: short(d), x: l.map((i) => F.prime[i]), y: l.map((i) => F.score[i]),
      marker: { size: 11, opacity: 0.8, color: divColor(d), line: { color: T.bg, width: 0.6 } },
      customdata: l.map((i) => [F.name[i], F.n[i], res.find((r) => r[0] === i)[1] >= 0 ? "More All-time than typical for this Prime" : "More Prime than typical for this All-time"]),
      hovertemplate: "<b>%{customdata[0]}</b><br>Prime score=%{x:.0f}<br>All-time score=%{y:.1f}<br>%{customdata[1]} rated bouts<br><b>%{customdata[2]}</b><extra></extra>" })),
  ], { title: "All-time vs Prime — longevity beyond the best decade", height: 580, annotations: lab, hovermode: "closest",
    xaxis: { title: { text: "Prime score · best 10 years, at least 13 appearances" } }, yaxis: { title: { text: "All-time score" } },
    legend: { orientation: "h", y: -0.2 } });
}
$("rec-pick").value = S.rec;
$("rec-pick").addEventListener("change", (e) => { if (I.has(e.target.value)) { S.rec = e.target.value; receiptChart(); } });

// ---- 6. risers and fallers -------------------------------------------------------------------------------
const movYears = Object.keys(D.movers).sort((a, b) => b - a);
$("mov-year").innerHTML = movYears.map((y) => `<option>${y}</option>`).join("");
SECTIONS.movers = () => plotFig("mov-chart", D.movers[$("mov-year").value]);
$("mov-year").addEventListener("change", () => mark("movers"));

// ---- 7. win streaks --------------------------------------------------------------------------------------
// row: fighter, length, start day, end day, division, divisions, title wins, finishes, avg opp, ongoing, ended by, gender
let stRows = [];
SECTIONS.streaks = () => {
  const key = { length: (r) => [r[1], r[8] ?? 0, r[6]], quality: (r) => [r[8] ?? 0, r[1], r[6]], title_wins: (r) => [r[6], r[1], r[8] ?? 0] }[S.stSort];
  stRows = D.streaks.filter((r) => r[11] === S.g && r[1] >= S.stMin && (S.div === "All" || r[5].includes(S.div)))
    .sort((a, b) => { const x = key(a), y = key(b); return y[0] - x[0] || y[1] - x[1] || y[2] - x[2]; }).slice(0, S.top);
  const mx = Math.max(1, ...stRows.map((r) => r[1]));
  $("st-table").innerHTML = stRows.length ? `<table><thead><tr><th>#</th><th>Fighter</th><th class="num">Streak</th><th>Division</th><th>Span</th>
    <th class="num">Avg opp</th><th class="num">Titles</th><th class="num">Finishes</th><th>Status</th></tr></thead><tbody>` +
    stRows.map((r, k) => `<tr class="pickable ${S.streak === r ? "sel" : ""}" data-k="${k}"><td>${chip(k + 1)}</td><td class="name">${esc(r[0])}</td>
      <td class="num bar"><i style="width:${(100 * r[1] / mx).toFixed(0)}%;background:rgba(251,191,36,.3)"></i><span>${r[1]}</span></td>
      <td>${esc(r[4] ?? "—")}</td><td class="dim">${iso(r[2]).slice(0, 4)}–${iso(r[3]).slice(0, 4)}</td><td class="num dim">${fmt(r[8])}</td>
      <td class="num dim">${r[6]}</td><td class="num dim">${r[7]}</td><td class="${r[9] ? "ok" : "dim"}">${esc(r[10])}</td></tr>`).join("") + "</tbody></table>"
    : `<p class="note" style="padding:10px 14px">No streaks match the current filters.</p>`;
  if (!stRows.includes(S.streak)) S.streak = stRows[0] ?? null;
  streakChart();
};
function streakChart() {
  const r = S.streak;
  if (!r) return empty("st-chart", "No streak selected.");
  const t = decode(r[0]);
  if (!t) return empty("st-chart", `${r[0]} has fewer than ${M.min_periods} rated bouts, so no rating timeline is published.`);
  const x = t.day.map(iso), oc = { W: T.positive, L: T.negative, D: T.neutral, N: T.caption };
  const data = [{ type: "scatter", mode: "lines", x, y: t.mu, name: `${r[0]} rating`, line: { color: T.primary, width: 2.5, shape: "spline", smoothing: 0.4 }, hoverinfo: "skip" }];
  ["W", "L", "D"].forEach((o) => {
    const J = range(x.length).filter((j) => t.r[j] === o);
    if (J.length) data.push({ type: "scatter", mode: "markers", name: RES[o], x: J.map((j) => x[j]), y: J.map((j) => t.mu[j]),
      marker: { size: 10, color: oc[o], line: { color: T.bg, width: 1.5 } }, text: J.map((j) => D.N[t.o[j]] ?? "?"),
      hovertemplate: `<b>${esc(r[0])} — ${RES[o]}</b> vs %{text}<br>%{x|%b %d, %Y}<br>rating %{y:.0f}<extra></extra>` });
  });
  plot("st-chart", data, { title: `${r[0]}: rating timeline`, height: 440, hovermode: "closest",
    shapes: [{ type: "rect", xref: "x", yref: "paper", x0: iso(r[2]), x1: iso(r[3]), y0: 0, y1: 1, fillcolor: "rgba(251,191,36,0.14)", line: { width: 0 }, layer: "below" }],
    annotations: [{ x: iso(Math.round((r[2] + r[3]) / 2)), y: 1, yref: "paper", yanchor: "bottom", showarrow: false, text: `${r[1]}-fight win streak`, font: { color: T.accent, size: 12 } }],
    xaxis: { title: { text: "Date" }, type: "date" }, yaxis: { title: { text: "Base WHR skill" } }, legend: { orientation: "h", y: 1.1, x: 0, yanchor: "bottom" } });
}
$("st-table").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-k]");
  if (!tr) return;
  S.streak = stRows[+tr.dataset.k];
  $("st-table").querySelectorAll("tr").forEach((x) => x.classList.toggle("sel", x === tr));
  streakChart();
});
$("st-sort").addEventListener("change", (e) => { S.stSort = e.target.value; mark("streaks"); });

// ---- 8. weight classes -----------------------------------------------------------------------------------
const dvYears = [...new Set(D.strength["10"].map((r) => r[1]))].sort((a, b) => a - b);
const DV = { y0: Math.max(2000, dvYears[0]), y1: dvYears[dvYears.length - 1] };
$("dv-y0").value = DV.y0; $("dv-y1").value = DV.y1;
$("dv-year").min = Math.min(...Object.keys(D.year_top)); $("dv-year").max = Math.max(...Object.keys(D.year_top));
$("dv-year").value = $("o-dv-year").textContent = $("dv-year").max;
$("dv-chips").innerHTML = D.divisions.map((d) => `<span class="chip ${S.dv.has(d) ? "on" : ""}" data-d="${esc(d)}">${esc(short(d))}</span>`).join("");
SECTIONS.divisions = () => {
  const sel = D.divisions.filter((d) => S.dv.has(d)), y0 = Math.min(DV.y0, DV.y1), y1 = Math.max(DV.y0, DV.y1);
  const rows = D.strength[S.k].filter((r) => S.dv.has(r[0]) && r[1] >= y0 && r[1] <= y1);
  const ymax = {};
  rows.forEach((r) => { ymax[r[1]] = Math.max(ymax[r[1]] ?? -Infinity, r[2]); });
  const val = (r) => (S.idx ? 100 * r[2] / ymax[r[1]] : r[2]);
  if (!rows.length) { ["dv-time", "dv-heat"].forEach((id) => empty(id, "Select at least one class with enough rated fighters.")); }
  else {
    const last = Math.max(...rows.map((r) => r[1])), lead = rows.filter((r) => r[1] === last).sort((a, b) => b[2] - a[2])[0];
    const data = sel.map((d) => { const l = rows.filter((r) => r[0] === d); return l.length && {
      type: "scatter", mode: "lines+markers", name: d, x: l.map((r) => r[1]), y: l.map(val), line: { color: divColor(d), width: 2.5 }, marker: { size: 6 },
      customdata: l.map((r) => [r[2], r[3]]), hovertemplate: `<b>${esc(d)}</b> ${S.idx ? "index %{y:.1f} · " : ""}rating %{customdata[0]:.1f} · %{customdata[1]} fighters<extra></extra>` }; }).filter(Boolean);
    const ends = data.map((t) => ({ x: t.x.at(-1), y: t.y.at(-1), text: short(t.name), showarrow: false, xanchor: "left", xshift: 8, font: { color: t.line.color, size: 11 } }));
    plot("dv-time", data, { title: { text: `Division strength — top ${S.k} per class, ${y0}–${y1}<br><sup>Leader in ${last}: ${lead[0]} (${fmt(lead[2], 1)})</sup>` },
      height: 540, hovermode: "x unified", annotations: ends, xaxis: { title: { text: "Year" } },
      yaxis: { title: { text: S.idx ? "Strength index (strongest selected class = 100)" : "Base WHR skill" } },
      legend: { orientation: "h", y: -0.18 }, margin: { r: 70 } });
    const years = [...new Set(rows.map((r) => r[1]))].sort((a, b) => a - b), cell = new Map(rows.map((r) => [r[0] + "|" + r[1], r]));
    const ds = sel.filter((d) => rows.some((r) => r[0] === d)).reverse();
    const z = ds.map((d) => years.map((y) => { const r = cell.get(d + "|" + y); return r ? 100 * r[2] / ymax[y] : null; }));
    const zmin = Math.max(80, Math.min(...z.flat().filter((v) => v != null)));
    plot("dv-heat", [{ type: "heatmap", x: years, y: ds.map(short), z, zmin, zmax: 100, colorscale: HEAT, colorbar: { title: { text: "Strength index" } },
      customdata: ds.map((d) => years.map((y) => cell.get(d + "|" + y)?.[2] ?? null)),
      hovertemplate: "%{x} · %{y}<br>strength index %{z:.1f}<br>top-end rating %{customdata:.1f}<extra></extra>" }],
      { title: `Top-end division strength by year (top ${S.k})`, height: Math.max(300, 34 * ds.length + 120), xaxis: { title: { text: "Year" } } });
  }
  yearTop();
  // Board share by career class (viz.top100_division_density_chart) on the chosen board.
  const B = boardRows(S.view, false).slice(0, 100), dv = VIEWS[S.view].div, cnt = {}, pts = S.view === "all_time";
  B.forEach((i) => {
    if (pts) [...(member.get(i) ?? [])].forEach(([d, u]) => { cnt[d] = (cnt[d] || 0) + uscore(u); });
    else { const d = F[dv][i] || "Unknown"; cnt[d] = (cnt[d] || 0) + 1; }
  });
  const den = Object.values(cnt).reduce((x, y) => x + y, 0), sh = Object.entries(cnt).sort((a, b) => a[1] - b[1]);
  plot("dv-share", [{ type: "bar", orientation: "h", x: sh.map(([, n]) => 100 * n / den), y: sh.map(([d]) => d), marker: { color: T.primary },
    text: sh.map(([, n]) => `${fmt(100 * n / den, 1)}%`), textposition: "outside", cliponaxis: false,
    customdata: sh.map(([, n]) => fmt(n)), hovertemplate: `<b>%{y}</b><br>%{customdata} ${pts ? "All-time points" : "fighters"}<extra></extra>` }],
    { title: pts ? `Where the All-time top ${B.length} earned their points, by class` : `Class share inside the ${VIEWS[S.view].label.split(" ")[0]} top ${B.length}`,
      height: Math.max(380, 30 * sh.length + 120),
      xaxis: { ticksuffix: "%", title: { text: "Share" } }, showlegend: false, margin: { r: 60 } });
  // Parity (viz.division_entropy_chart) and finishes (viz.method_mix_timeline_chart).
  const E = D.entropy.filter((r) => S.dv.has(r[1]) && r[0] >= y0 && r[0] <= y1), ent = [];
  sel.forEach((d) => { const l = E.filter((r) => r[1] === d); if (!l.length) return;
    ent.push({ type: "scatter", mode: "lines+markers", name: short(d), x: l.map((r) => r[0]), y: l.map((r) => r[2]), line: { color: divColor(d) }, marker: { size: 5 },
      hovertemplate: `<b>${esc(d)}</b> %{x}<br>crowdedness %{y:.2f}<extra></extra>` },
    { type: "scatter", mode: "lines", name: short(d), x: l.map((r) => r[0]), y: l.map((r) => r[3]), xaxis: "x", yaxis: "y2", showlegend: false, line: { color: divColor(d) },
      hovertemplate: `<b>${esc(d)}</b> %{x}<br>average top-10 rating %{y:.0f}<extra></extra>` }); });
  if (ent.length) plot("dv-ent", ent, { title: "How deep each class is, and how strong its top", height: 680,
    yaxis: { domain: [0.56, 1], range: [0, 1.02], title: { text: "Crowdedness (0–1)" } },
    yaxis2: { ...AX, domain: [0, 0.44], title: { text: "Average top-10 rating" } }, xaxis: { anchor: "y2", title: { text: "Year" } },
    legend: { orientation: "h", y: 1.08, x: 0 } });
  else empty("dv-ent", "No parity rows for the selected classes.");
  const mix = {};
  D.mix.forEach(([y, d, b, n]) => { if (y < y0 || y > y1 || !S.dv.has(d)) return; (mix[y] ||= { "KO/TKO": 0, Submission: 0, Decision: 0 })[b] += n; });
  const ys = Object.keys(mix).map(Number).sort((a, b) => a - b), tot = ys.map((y) => Object.values(mix[y]).reduce((a, b) => a + b, 0));
  const MC = { "KO/TKO": [T.negative, "rgba(248,113,113,0.55)"], Submission: [T.secondary, "rgba(167,139,250,0.55)"], Decision: [T.primary, "rgba(56,189,248,0.55)"] };
  plot("dv-mix", Object.keys(MC).map((b) => ({ type: "scatter", mode: "lines", stackgroup: "one", name: b, x: ys, y: ys.map((y, k) => mix[y][b] / tot[k]),
    line: { width: 0.5, color: MC[b][0] }, fillcolor: MC[b][1], customdata: tot,
    hovertemplate: `<b>${b}</b><br>%{x}: %{y:.0%} of %{customdata} bouts<extra></extra>` })),
  { title: "How fights end over time (bouts with a recorded weight class)", height: 440,
    yaxis: { range: [0, 1], tickformat: ".0%", title: { text: "Share of fights" } }, xaxis: { title: { text: "Year" } }, legend: { orientation: "h", y: 1.12, x: 0 } });
};
function yearTop() {
  const f = structuredClone(D.year_top[$("dv-year").value]), keep = new Set([...S.dv].map(short));
  f.data = f.data.filter((t) => keep.has(t.name));
  f.data.forEach((t) => { t.marker = { color: divColor(D.divisions.find((d) => short(d) === t.name)) }; t.cliponaxis = false; });
  if (!f.data.length) return empty("dv-year-chart", "No rated fighters in the selected classes that year.");
  const ys = f.data.flatMap((t) => t.y), xs = f.data.flatMap((t) => t.x);
  plot("dv-year-chart", f.data, { ...f.layout, height: Math.max(380, 30 * ys.length + 110),
    xaxis: { ...f.layout.xaxis, range: [Math.min(...xs) - 60, Math.max(...xs) + 60], title: { text: "Base WHR skill, end of year" } },
    yaxis: { categoryorder: "array", categoryarray: [...ys].reverse(), automargin: true }, margin: { l: 40, r: 60, t: 70, b: 80 } });
}
$("dv-chips").addEventListener("click", (e) => {
  const c = e.target.closest(".chip");
  if (!c) return;
  S.dv.has(c.dataset.d) ? S.dv.delete(c.dataset.d) : S.dv.add(c.dataset.d);
  c.classList.toggle("on");
  mark("divisions");
});
["y0", "y1"].forEach((k) => $("dv-" + k).addEventListener("change", (e) => { DV[k] = +e.target.value; mark("divisions"); }));
$("dv-k").addEventListener("change", (e) => { S.k = e.target.value; mark("divisions"); });
seg("dv-index", "idx", () => { S.idx = S.idx === "1"; mark("divisions"); });
$("dv-year").addEventListener("input", (e) => { $("o-dv-year").textContent = e.target.value; yearTop(); });

// ---- 9. title lineage ------------------------------------------------------------------------------------
$("tl-div").innerHTML = Object.keys(D.lineage).map((d) => `<option ${d === "Lightweight" ? "selected" : ""}>${esc(d)}</option>`).join("");
SECTIONS.lineage = () => plotFig("tl-chart", D.lineage[$("tl-div").value][$("tl-int").checked ? 1 : 0], { height: 320 });
$("tl-div").addEventListener("change", () => mark("lineage"));
$("tl-int").addEventListener("change", () => mark("lineage"));

// ---- 10. dominance ---------------------------------------------------------------------------------------
SECTIONS.dominance = () => {
  const P = pool("all_time").filter((i) => F.dom[i] != null && F.domw[i] >= S.dmMin).sort((x, y) => F.dom[y] - F.dom[x]).slice(0, S.top).reverse();
  if (!P.length) return empty("dm-chart", "No fighters match the current filters.");
  plot("dm-chart", [{ type: "bar", orientation: "h", x: P.map((i) => F.dom[i]), y: P.map((i) => F.name[i]),
    marker: { color: P.map((_, k) => (k === P.length - 1 ? T.accent : T.primary)) }, text: P.map((i) => fmt(F.dom[i], 2)), textposition: "outside", cliponaxis: false,
    customdata: P.map((i) => [F.domw[i], fmt(F.whr[i])]), hovertemplate: "<b>%{y}</b><br>dominance %{x:.2f}<br>%{customdata[0]} wins<br>rating %{customdata[1]}<extra></extra>" }],
  { title: "Most dominant fighters", height: Math.max(420, 26 * P.length + 120), showlegend: false,
    xaxis: { title: { text: "Dominance score (higher = more one-sided wins)" }, rangemode: "tozero" }, margin: { l: 40, r: 60 } });
};

// ---- 11. integrity policy --------------------------------------------------------------------------------
SECTIONS.policy = () => {
  plotFig("pol-chart", D.integrity.fig);
  const L = D.integrity.ledger.slice(0, Math.max(S.top, 25));
  $("pol-table").innerHTML = `<table><thead><tr><th>Date</th><th>Fighter</th><th>Opponent</th><th>Reason</th><th>Detail</th>
    <th class="num">Result weight</th><th class="num">Discount</th></tr></thead><tbody>` +
    L.map((r) => `<tr><td class="dim">${r[0] ?? ""}</td><td class="name">${esc(r[1])}</td><td>${esc(r[2])}</td><td style="color:${T.accent}">${esc(r[3])}</td>
      <td class="dim" style="white-space:normal;min-width:260px">${esc(r[4])}</td><td class="num">${fmt(r[5], 2)}</td><td class="num down">${fmt(r[6])}%</td></tr>`).join("") + "</tbody></table>";
};

// ---- 12. benchmark ---------------------------------------------------------------------------------------
SECTIONS.benchmark = () => {
  const all = D.bench.slice(0, Math.max(15, S.top)), B = all.filter((r) => r[2] != null).reverse();
  const far = [...B].sort((a, b) => Math.abs(b[3]) - Math.abs(a[3])).slice(0, 3);
  $("bm-summary").innerHTML = `Matched <b>${B.length} of ${all.length}</b> men's All-time leaders to FightMatrix's list.` +
    (far.length ? ` Largest disagreements: ${far.map((r) => `${esc(r[0])} (#${r[1]} here, #${r[2]} there)`).join(", ")}.` : "");
  if (!B.length) return empty("bm-chart", "No matched fighters.");
  plot("bm-chart", [
    { type: "scatter", mode: "lines", x: B.flatMap((r) => [r[1], r[2], null]), y: B.flatMap((r) => [r[0], r[0], null]), line: { color: T.border_strong, width: 2 }, hoverinfo: "skip", showlegend: false },
    { type: "scatter", mode: "markers", name: "Rank Engine", x: B.map((r) => r[1]), y: B.map((r) => r[0]), marker: { color: T.primary, size: 10 },
      customdata: B.map((r) => [r[4], r[3]]), hovertemplate: "<b>%{y}</b><br>Engine rank %{x}<br>Score %{customdata[0]:.1f}<br>Gap %{customdata[1]:+d}<extra></extra>" },
    { type: "scatter", mode: "markers", name: "FightMatrix all-time", x: B.map((r) => r[2]), y: B.map((r) => r[0]), marker: { color: T.accent, size: 10, symbol: "diamond" },
      customdata: B.map((r) => r[5]), hovertemplate: "<b>%{y}</b><br>FightMatrix rank %{x}<br>Points %{customdata:,.0f}<extra></extra>" },
  ], { title: "Where the All-time board disagrees with an external reference", height: Math.max(520, 22 * B.length + 170),
    xaxis: { autorange: "reversed", title: { text: "Rank (1 is best)" } }, yaxis: { automargin: true }, legend: { orientation: "h", y: 1.04, x: 0 } });
};

// ---- wiring ----------------------------------------------------------------------------------------------
seg("c-gender", "g", () => { divisionOptions(); mark(); });
$("c-div").addEventListener("change", (e) => { S.div = e.target.value; mark(); });
slider("c-top", "o-top", "top", () => mark());
slider("c-min", "o-min", "min", () => mark());
slider("st-min", "o-st-min", "stMin", () => mark("streaks"));
slider("dm-min", "o-dm-min", "dmMin", () => mark("dominance"));
$("w-a").value = S.a; $("w-s").value = S.s; $("o-a").textContent = fmt(S.a, 3); $("o-s").textContent = fmt(S.s, 3);
divisionOptions();
const io = new IntersectionObserver((es) => {
  es.forEach((e) => (e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id)));
  flush();
}, { rootMargin: "400px 0px" });
Object.keys(SECTIONS).forEach((id) => { dirty.add(id); io.observe($(id)); });
