// Draws site/data.js (written by analysis/build_site.py). Headlines and chart titles are fixed in index.html;
// the numbers speak in each chart's insight line, computed from DATA under the current controls. Sections draw
// when visible and redraw when a control they read changes. Colours: style.css tokens.
"use strict";

const D = window.DATA, M = D.meta, F = D.F, NF = F.name.length;
const I = new Map(F.name.map((f, i) => [f, i]));
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmt = (v, d = 0) => v == null ? "" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const sgn = (v, d = 0) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), d);
const iso = (day) => new Date(day * 864e5).toISOString().slice(0, 10);
const short = (d) => D.short[d] || d;
const range = (n) => [...Array(n).keys()];
const sum = (l) => l.reduce((a, b) => a + b, 0);
const argmax = (l, f) => l.reduce((b, x) => (f(x) > f(b) ? x : b), l[0]);
const chip = (r) => r == null ? "" : `<span class="chip-rank ${r === 1 ? "r1" : ""}">${r}</span>`;
const SNAP = `Snapshot ${M.snapshot}, bouts through ${M.through}`;

// Spearman's ρ: Pearson correlation of mid-ranks.
function rho(x, y) {
  const rk = (v) => { const o = range(v.length).sort((a, b) => v[a] - v[b]), r = Array(v.length);
    for (let i = 0; i < o.length;) { let j = i; while (j + 1 < o.length && v[o[j + 1]] === v[o[i]]) j++;
      for (let k = i; k <= j; k++) r[o[k]] = (i + j) / 2; i = j + 1; } return r; };
  const a = rk(x), b = rk(y), n = a.length, ma = sum(a) / n, mb = sum(b) / n;
  const c = sum(a.map((v, i) => (v - ma) * (b[i] - mb)));
  return c / Math.sqrt(sum(a.map((v) => (v - ma) ** 2)) * sum(b.map((v) => (v - mb) ** 2)));
}

// ---- theme: every colour is a CSS token --------------------------------------------------------------------
let T, CAT, AX;
function theme() {
  const c = getComputedStyle(document.documentElement), tok = (k) => c.getPropertyValue("--" + k).trim();
  T = { bg: tok("bg"), surface: tok("surface"), text: tok("text"), text2: tok("text-2"), muted: tok("muted"),
    border: tok("border"), border2: tok("border-strong"), context: tok("context"), accent: tok("accent"),
    negative: tok("negative"), positive: tok("positive"), font: tok("font") };
  CAT = [1, 2, 3, 4, 5, 6].map((i) => tok("c" + i));
  AX = { gridcolor: T.border, zerolinecolor: T.border2, linecolor: T.border2, automargin: true,
    tickfont: { color: T.text2, size: 12 }, title: { font: { color: T.text2, size: 13 } } };
}
theme();
const PART = () => [["Championships", CAT[1]], ["Career skill", CAT[0]], ["Contender résumé", CAT[2]]];
const CFG = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

function plot(id, data, layout = {}) {
  if (!window.Plotly) return;
  const ax = (k) => ({ ...AX, ...layout[k], title: { ...AX.title, ...(layout[k]?.title || {}) } });
  Plotly.react($(id), data, {
    height: 440, paper_bgcolor: T.bg, plot_bgcolor: T.bg, colorway: CAT, showlegend: false, hovermode: "closest",
    font: { family: T.font, color: T.text, size: 13 },
    hoverlabel: { bgcolor: T.bg, bordercolor: T.border2, font: { family: T.font, color: T.text, size: 13 } },
    legend: { bgcolor: "rgba(0,0,0,0)", font: { color: T.text2, size: 12 } },
    ...layout, margin: { t: 12, r: 24, b: 48, l: 56, ...layout.margin }, xaxis: ax("xaxis"), yaxis: ax("yaxis"),
  }, CFG);
}
// An exhibit: a fixed title in the page, a computed insight, the chart and a short caption.
function ex(id, insight, src) {
  $(id + "-i").innerHTML = insight;
  if (src != null) $(id + "-s").innerHTML = src;
}
function empty(id, msg) {
  ex(id, msg, "");
  plot(id, [], { height: 200, xaxis: { visible: false }, yaxis: { visible: false } });
}
const label = (x, y, text, color, o = {}) => ({ x, y, text, showarrow: false, font: { size: 12, color }, ...o });
// End-of-line label heights spread at least 14 px apart; span: data range of the axis, px: plot height.
function dodge(ys, span, px) {
  const g = 14 * span / px, o = range(ys.length).sort((a, b) => ys[a] - ys[b]), out = [...ys];
  o.forEach((k, j) => { if (j && out[k] - out[o[j - 1]] < g) out[k] = out[o[j - 1]] + g; });
  return out;
}

// ---- state and the control bar ---------------------------------------------------------------------------
const S = {
  g: "M", div: "All", top: 30, min: M.min_periods, view: "all_time", q: "",
  sel: ["Jon Jones", "Georges St-Pierre", "Islam Makhachev"].filter((f) => I.has(f)),
  a: M.a, s: M.s, rec: "Jon Jones", streak: null,
  dv: new Set(["Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight", "Featherweight"]),
  k: "10", stSort: "length", stMin: 5, dmMin: 8, cal: "All bouts",
};
const VIEWS = {
  all_time: { rank: "at", val: "score", label: "All-time score", div: "div", name: "All-time" },
  prime: { rank: "pr", val: "plevel", label: "Prime level", div: "div", name: "Prime" },
  current: { rank: "cr", val: "cur", label: "Current score", div: "cdiv", name: "Current" },
};

// Class rows (ratings.division_legacy): the All-time score split by the class it was earned in.
const C = D.classes.map(([f, d, rank, t, k, r]) => ({ f, d, rank, t, k, r }));
const member = new Map();
C.forEach((u) => { if (!member.has(u.f)) member.set(u.f, new Map()); member.get(u.f).set(u.d, u); });
const inClass = (i, d, view = S.view) => view === "current" ? F.cdiv[i] === d : member.get(i)?.has(d);
function pool(view = S.view, useDiv = true, g = S.g, div = S.div, min = S.min) {
  return range(NF).filter((i) => F.g[i] === g && F.n[i] >= min && (!useDiv || div === "All" || inClass(i, div, view)));
}
// A board unit is a whole career (no class chosen) or the part of it earned in one class.
const uscore = (u, a = M.a, s = M.s) => M.scale * (a * u.t + (1 - a) * (s * u.k + (1 - s) * u.r));
const upts = (u, a = M.a, s = M.s) => [M.scale * a * u.t, M.scale * (1 - a) * s * u.k, M.scale * (1 - a) * (1 - s) * u.r];
function units(g, div) {
  return div === "All"
    ? range(NF).filter((i) => F.g[i] === g && F.at[i] != null).map((i) => ({ f: i, d: "All", rank: F.at[i], t: F.T[i], k: F.S[i], r: F.R[i] }))
    : C.filter((u) => F.g[u.f] === g && u.d === div);
}
// A board in one class keeps the board's order, restricted to careers fought mostly in that class (career_division).
function boardRows(view = S.view, useDiv = true, g = S.g, div = S.div, min = S.min) {
  const r = VIEWS[view].rank;
  return range(NF).filter((i) => F.g[i] === g && F.n[i] >= min && F[r][i] != null && (!useDiv || div === "All" || F.div[i] === div))
    .sort((a, b) => F[r][a] - F[r][b]);
}

const SECTIONS = {}, dirty = new Set(), visible = new Set();
function mark(...ids) {
  (ids.length ? ids : Object.keys(SECTIONS)).forEach((i) => dirty.add(i));
  flush();
}
function flush() {
  for (const id of [...dirty]) if (visible.has(id)) {
    dirty.delete(id);
    try { SECTIONS[id](); } catch (e) { reportError(e); }   // one failing section must not stop the rest
  }
}
function seg(id, key, after) {
  $(id).querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.classList.contains("on"))));
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $(id).querySelectorAll("button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    S[key] = b.dataset.v;
    after();
  });
}
function slider(id, out, key, after) {
  const el = $(id);
  el.value = S[key];
  $(out).textContent = el.value;
  el.addEventListener("input", () => { S[key] = Number(el.value); $(out).textContent = el.value; after(); });
}
function divisionOptions() {
  const have = new Set([...C.filter((u) => F.g[u.f] === S.g).map((u) => u.d), ...[F.div, F.cdiv].flatMap((v) => v.filter((d, i) => F.g[i] === S.g && d))]);
  const order = [...have].sort((a, b) => ((D.divisions.indexOf(a) + 99) % 99) - ((D.divisions.indexOf(b) + 99) % 99) || a.localeCompare(b));
  if (!have.has(S.div)) S.div = "All";
  const html = ["All", ...order].map((d) => `<option value="${esc(d)}" ${d === S.div ? "selected" : ""}>${d === "All" ? "All classes" : esc(d)}</option>`).join("");
  $("c-div").innerHTML = $("c-class").innerHTML = html;
}
if (!window.Plotly) document.querySelector(".hero").insertAdjacentHTML("beforeend",
  `<p class="callout">Charts need plotly.js from cdn.jsdelivr.net, which did not load. Tables still work.</p>`);

// ---- helpers shared by sections -----------------------------------------------------------------
// Year leaders of a strength frame (rows [class, year, rating, n]).
function leaders(R) {
  const ys = [...new Set(R.map((r) => r[1]))].sort((a, b) => a - b);
  const L = ys.map((y) => argmax(R.filter((r) => r[1] === y), (r) => r[2]));
  return { ys, L };
}
const streakSort = { length: (r) => [r[1], r[8] ?? 0, r[6]], quality: (r) => [r[8] ?? 0, r[1], r[6]], title_wins: (r) => [r[6], r[1], r[8] ?? 0] };
function streaks(g, div, min, key) {
  return D.streaks.filter((r) => r[11] === g && r[1] >= min && (div === "All" || r[5].includes(div)))
    .sort((a, b) => { const x = streakSort[key](a), y = streakSort[key](b); return y[0] - x[0] || y[1] - x[1] || y[2] - x[2]; });
}
// Reigns of a lineage figure: one bar trace per reign, customdata [fighter, won against, start, defences, years].
const reigns = (f) => f.data.map((t) => ({ f: t.customdata[0][0], opp: t.customdata[0][1], start: t.customdata[0][2],
  def: t.customdata[0][3], yrs: t.customdata[0][4], x: t.x[0], text: t.text[0] }));
function calRows(seg) {
  return D.calib.filter((r) => r[0] === seg).map(([, b, p, y, n]) => ({ b, p, y, n, se: Math.sqrt(p * (1 - p) / n) }));
}
const overconfident = (R) => sum(R.filter((r) => r.p > 0.5).map((r) => r.n * (r.p - r.y))) > 0;  // favourites win less than forecast

// ---- hero facts (published boards, men) ---------------------------------------------------------------------
function facts() {
  const one = (v) => esc(F.name[boardRows(v, false, "M", "All", M.min_periods)[0]]);
  $("facts").innerHTML = [[one("all_time"), "#1 All-time"], [one("prime"), "#1 Prime"], [one("current"), "#1 Current"],
    [fmt(M.rated_bouts), `rated bouts through ${M.through}`]].map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("");
}

// ---- 1. rankings --------------------------------------------------------------------------------------------
SECTIONS.rankings = () => { $("board-s").textContent = boardTable(); };
function boardTable() {
  const all = boardRows(), rows = all.filter((i) => !S.q || F.name[i].toLowerCase().includes(S.q)).slice(0, S.top);
  const V = VIEWS[S.view], vmax = Math.max(...rows.map((i) => F[V.val][i]));
  const bar = (v, d) => `<td class="num bar"><i style="width:${(100 * v / (vmax || 1)).toFixed(1)}%"></i><span>${fmt(v, d)}</span></td>`;
  const now = (i) => F.cdiv[i] && F.cdiv[i] !== F.div[i] ? ` <span class="dim">→ now ${esc(short(F.cdiv[i]))}</span>` : "";
  const name = (i) => `<td class="name"><button class="namebtn" data-f="${esc(F.name[i])}">${esc(F.name[i])}</button></td>`;
  const cls = S.div !== "All", pos = new Map(all.map((i, k) => [i, k + 1]));
  const cols = {
    all_time: [["#", (i) => `<td>${chip(cls ? pos.get(i) : F.at[i])}</td>`], ["Fighter", name], ["Division", (i) => `<td>${esc(F.div[i])}${now(i)}</td>`],
      ["Score", (i) => bar(F.score[i], 1)], ["Prime", (i) => `<td class="num">${fmt(F.plevel[i])}</td>`],
      ["Prime rank", (i) => `<td class="num">${F.pr[i] ?? ""}</td>`], ["Elite wins", (i) => `<td class="num">${F.pwins[i] ?? ""}</td>`],
      ["Rated bouts", (i) => `<td class="num dim">${F.n[i]}</td>`], ["Last bout", (i) => `<td class="dim">${F.last[i] ?? ""}</td>`],
      ["All-time #", (i) => `<td class="num dim">${F.at[i] ?? ""}</td>`]],
    prime: [["#", (i) => `<td>${chip(cls ? pos.get(i) : F.pr[i])}</td>`], ["Fighter", name], ["Division", (i) => `<td>${esc(F.div[i])}</td>`],
      ["Prime", (i) => bar(F.plevel[i], 0)], ["Elite wins", (i) => `<td class="num">${F.pwins[i] ?? ""}</td>`],
      ["Best decade", (i) => `<td class="dim">${F.p0[i] ?? ""}–${F.p1[i] ?? ""}</td>`], ["Prime #", (i) => `<td class="num dim">${F.pr[i] ?? ""}</td>`],
      ["All-time rank", (i) => `<td class="num dim">${F.at[i] ?? ""}</td>`]],
    current: [["#", (i) => `<td>${chip(cls ? pos.get(i) : F.cr[i])}</td>`], ["Fighter", name],
      ["Division", (i) => `<td>${cls ? esc(F.div[i]) + now(i) : esc(F.cdiv[i])}</td>`],
      ["Score", (i) => bar(F.cur[i], 0)], ["UFC bouts", (i) => `<td class="num">${F.ufc[i] ?? ""}</td>`],
      ["Last bout", (i) => `<td class="dim">${F.last[i] ?? ""}</td>`], ["Current #", (i) => `<td class="num dim">${F.cr[i] ?? ""}</td>`],
      ["All-time rank", (i) => `<td class="num dim">${F.at[i] ?? ""}</td>`]],
  }[S.view].filter(([h]) => cls || !/^(All-time|Prime|Current) #$/.test(h));
  $("board").innerHTML = rows.length
    ? `<table><thead><tr>${cols.map(([h]) => `<th class="${/^(#|Fighter|Division|Best|Last)/.test(h) ? "" : "num"}">${h}</th>`).join("")}</tr></thead><tbody>` +
      rows.map((i) => `<tr>${cols.map(([, c]) => c(i)).join("")}</tr>`).join("") + "</tbody></table>"
    : `<p class="note" style="padding:10px 14px">No ranked fighters match the current filters.</p>`;
  return `Showing ${rows.length} of ${all.length}${cls ? ` whose UFC career was mostly at ${S.div}` : ""}.`;
}
$("board").addEventListener("click", (e) => {
  const b = e.target.closest(".namebtn");
  if (b) addFighter(b.dataset.f, true);
});
seg("c-view", "view", () => mark("rankings"));
$("c-search").addEventListener("input", (e) => { S.q = e.target.value.trim().toLowerCase(); mark("rankings"); });

// ---- 2. score anatomy and the exchange rates ---------------------------------------------------------------
const rerank = (U, a, s) => new Map([...U].sort((x, y) => uscore(y, a, s) - uscore(x, a, s)).map((u, r) => [u, r + 1]));
const published = () => Math.abs(S.a - M.a) < 1e-9 && Math.abs(S.s - M.s) < 1e-9;
SECTIONS.anatomy = () => {
  const { a, s } = S, U = units(S.g, S.div), R = rerank(U, a, s), K = Math.min(20, S.top), cls = S.div !== "All";
  const order = U.filter((u) => F.n[u.f] >= S.min).sort((x, y) => R.get(x) - R.get(y)), shown = order.slice(0, K).reverse();
  if (!shown.length) return empty("anat-chart", "No ranked fighters match the current filters.");
  const lab = shown.map((u) => { const d = u.rank - R.get(u);
    return `${F.name[u.f]}  #${R.get(u)}` + (d ? ` (${d > 0 ? "▲" : "▼"}${Math.abs(d)})` : ""); });
  const tot = shown.map((u) => uscore(u, a, s));
  const why = [(i) => `${F.tw[i]} qualifying title wins`, (i) => `${F.cy[i]} contributing career years`, (i) => `${F.cw[i]} contender wins`];
  const w = [a, (1 - a) * s, (1 - a) * (1 - s)];
  const data = PART().map(([name, color], j) => ({
    type: "bar", orientation: "h", name: `${name} · ${fmt(100 * w[j], 1)}%`, x: shown.map((u) => upts(u, a, s)[j]), y: lab, marker: { color },
    customdata: shown.map((u, k) => [fmt(tot[k], 1), cls ? `${fmt(100 * uscore(u) / F.score[u.f])}% of the All-time score earned at ${short(u.d)}` : why[j](u.f)]),
    hovertemplate: `<b>%{y}</b><br>${name}: %{x:.1f} points<br>total %{customdata[0]}<br>%{customdata[1]}<extra></extra>`,
  }));
  data.push({ type: "scatter", mode: "text", x: tot, y: lab, text: tot.map((v) => "  " + fmt(v)), textposition: "middle right",
    textfont: { color: T.text, size: 12 }, hoverinfo: "skip", showlegend: false, cliponaxis: false });
  plot("anat-chart", data, {
    barmode: "stack", height: Math.max(420, 28 * shown.length + 120), showlegend: true,
    xaxis: { title: { text: cls ? `Points earned in UFC bouts at ${S.div}` : "Points in the All-time score" }, rangemode: "tozero", range: [0, Math.max(...tot) * 1.14] },
    legend: { orientation: "h", y: 1.0, yanchor: "bottom", x: 0, traceorder: "normal" }, margin: { t: 40, r: 16 },
  });
  const [n1, n2] = order;
  const lead = n2 ? ` by ${fmt(uscore(n1, a, s) - uscore(n2, a, s))} points` : "";
  ex("anat-chart", (published() ? "" : `At a = ${fmt(a, 3)}, s = ${fmt(s, 3)}: `) + `${esc(F.name[n1.f])} leads${n2 ? ` ${esc(F.name[n2.f])}` : ""}${lead}.`,
    `Top ${shown.length} of ${order.length} ranked. ▲▼ places moved from the published order.`);

  // Published top 100 against the new order: overlap at the top and Spearman's ρ.
  const P = [...U].sort((x, y) => x.rank - y.rank).slice(0, 100), r = rho(P.map((u) => u.rank), P.map((u) => R.get(u)));
  const top10 = P.slice(0, 10).filter((u) => R.get(u) <= 10).length;
  const mv = P.slice(0, 50).map((u) => [u.f, u.rank - R.get(u)]).sort((x, y) => y[1] - x[1]);
  const who = (l) => l.map(([i, d]) => `${esc(F.name[i])} ${sgn(d)}`).join(", ");
  $("anat-summary").innerHTML = published()
    ? ""
    : `${top10} of the top 10 stay · ρ = ${fmt(r, 2)} vs the published top 100 · up: ${who(mv.slice(0, 3).filter((x) => x[1] > 0)) || "none"}
       · down: ${who(mv.slice(-3).reverse().filter((x) => x[1] < 0)) || "none"}`;
};
function setRates(a, s) {
  S.a = a; S.s = s;
  $("w-a").value = a; $("w-s").value = s; $("o-a").textContent = fmt(a, 3); $("o-s").textContent = fmt(s, 3);
  mark("anatomy");
}
["a", "s"].forEach((k) => $("w-" + k).addEventListener("input", (e) => setRates(k === "a" ? +e.target.value : S.a, k === "s" ? +e.target.value : S.s)));
$("w-reset").addEventListener("click", () => setRates(M.a, M.s));

// ---- 4. fighters: arcs and tale of the tape -----------------------------------------------------------------
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
  if (go) $("fighters").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
}
const RES = { W: "Win", L: "Loss", D: "Draw", N: "No result" };
// Best five-year stretch: rolling mean over (t − W, t] with at least minN bouts (viz.trajectory_chart).
function bestStretch(t) {
  const [W, minN] = M.peak;
  let lo = 0, s = 0, best = null;
  t.day.forEach((d, j) => {
    s += t.mu[j];
    while (t.day[lo] <= d - W) s -= t.mu[lo++];
    const n = j - lo + 1;
    if (n >= minN && (!best || s / n > best[1])) best = [j, s / n];
  });
  return best;
}
const contender = () => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: M.contender, y1: M.contender, line: { color: T.muted, dash: "dash", width: 1 } });
SECTIONS.fighters = () => {
  const colors = S.sel.map((_, k) => CAT[k]);
  $("sel-chips").innerHTML = S.sel.map((f, k) => `<span class="chip"><i style="background:${colors[k]}"></i>${esc(f)}<button data-f="${esc(f)}" aria-label="Remove ${esc(f)}">×</button></span>`).join("");
  if (!S.sel.length) { empty("arc-chart", "Add a fighter to draw their career."); $("cards").innerHTML = ""; return; }
  const data = [], ann = [], peaks = [], ends = [];
  S.sel.forEach((f, k) => {
    const t = decode(f), c = colors[k];
    if (!t) return;
    const x = t.day.map(iso), txt = t.day.map((_, j) => `${RES[t.r[j]]} vs ${t.o[j] >= 0 ? D.N[t.o[j]] : "?"}${t.m[j] !== "-" ? " · " + M.methods[+t.m[j]] : ""}`);
    data.push({ type: "scatter", mode: "lines", x, y: t.mu, line: { color: c, width: 2 }, text: txt,
      hovertemplate: `<b>${esc(f)}</b><br>%{x|%Y-%m-%d}<br>rating %{y:.0f}<br>%{text}<extra></extra>` });
    const J = (o) => range(x.length).filter((j) => t.r[j] === o);
    data.push({ type: "scatter", mode: "markers", x: J("W").map((j) => x[j]), y: J("W").map((j) => t.mu[j]), hoverinfo: "skip",
      marker: { size: 6, color: c } });
    data.push({ type: "scatter", mode: "markers", x: J("L").map((j) => x[j]), y: J("L").map((j) => t.mu[j]), hoverinfo: "skip",
      marker: { size: 9, symbol: "x-thin", color: T.negative, line: { width: 2, color: T.negative } } });
    const b = bestStretch(t);
    if (b) ann.push({ x: x[b[0]], y: t.mu[b[0]], text: fmt(b[1]), showarrow: true, arrowhead: 0, arrowcolor: c, ax: 0, ay: -26, font: { color: c, size: 12 } });
    const e = t.day.length - 1, top = t.mu.indexOf(Math.max(...t.mu));
    ends.push([x[e], t.mu[e], f.split(" ").at(-1), c]);
    peaks.push([f, t.mu[top], x[top]]);
  });
  const days = S.sel.flatMap((f) => decode(f)?.day ?? []), mu = S.sel.flatMap((f) => decode(f)?.mu ?? []), near = Math.min(...mu) < M.contender + 150;  // draw the line only near the data
  const lo = near ? Math.min(M.contender, ...mu) : Math.min(...mu), ey = dodge(ends.map((q) => q[1]), Math.max(...mu) - lo || 1, 430);
  plot("arc-chart", data, {
    height: 500, annotations: [...ann, ...ends.map(([x, , text, c], k) => label(x, ey[k], text, c, { xanchor: "left", xshift: 6 })),
      ...(near ? [label(1, M.contender, `contender line ${fmt(M.contender)}`, T.muted, { xref: "paper", xanchor: "right", yanchor: "bottom" })] : [])],
    shapes: near ? [contender()] : [], yaxis: { title: { text: "Era-adjusted rating" } }, margin: { r: 90 },
    xaxis: { title: { text: "Event date" }, type: "date", range: [iso(Math.min(...days) - 180), iso(Math.max(...days) + 180)] },
  });
  const p = argmax(peaks, (q) => q[1]);
  ex("arc-chart", peaks.length > 1 ? `Highest peak: ${esc(p[0])}, ${fmt(p[1])} (${p[2].slice(0, 4)}).` : `Peak ${fmt(p[1])} (${p[2].slice(0, 4)}).`,
    `Dot: win · red ×: loss · number: best ${M.peak[2]} mean.`);
  $("cards").innerHTML = S.sel.map((f, k) => card(I.get(f), colors[k])).join("");
};
function card(i, c) {
  const pts = [M.scale * M.a * F.T[i], M.scale * (1 - M.a) * M.s * F.S[i], M.scale * (1 - M.a) * (1 - M.s) * F.R[i]];
  const tot = sum(pts) || 1, row = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
  const rk = (r, v) => (r != null ? `#${r} · ` : "<span class='dim'>not ranked</span> · ") + v;
  return `<div class="card" style="--c:${c}"><h4>${esc(F.name[i])}</h4>
    <div class="sub">${esc(F.div[i])}${F.cdiv[i] && F.cdiv[i] !== F.div[i] ? ` · now ${esc(F.cdiv[i])}` : ""} · ${F.w[i]}–${F.l[i]}${F.d[i] ? "–" + F.d[i] : ""}</div>
    <dl>${row("All-time", rk(F.at[i], fmt(F.score[i], 1)))}
      ${row("Prime", rk(F.pr[i], F.plevel[i] != null ? `${fmt(F.plevel[i])} · ${F.pwins[i]} elite wins` : "—"))}
      ${row("Best decade", F.p0[i] != null ? `${F.p0[i]}–${F.p1[i]}` : "—")}
      ${row("Current", rk(F.cr[i], fmt(F.cur[i])))}
      ${row("Peak rating", fmt(F.peak[i]))}
      ${row("Career mass", `${fmt(F.mass[i])} · ${F.cy[i]} of ${F.ay[i]} years`)}
      ${row("Dominance", F.dom[i] != null ? `${fmt(F.dom[i], 1)} over ${F.domw[i]} wins` : "—")}
      ${row("By class", [...(member.get(i) ?? [])].sort((x, y) => uscore(y[1]) - uscore(x[1]))
        .map(([d, u]) => `${short(d)} #${u.rank} · ${fmt(100 * uscore(u) / F.score[i])}%`).join("<br>") || "—")}
      ${row("Rated bouts", `${F.n[i]} · last ${F.last[i] ?? "—"}`)}</dl>
    <div class="stack">${pts.map((p, j) => `<span style="width:${(100 * p / tot).toFixed(1)}%;background:${PART()[j][1]}"></span>`).join("")}</div>
    <small>All-time points: championships ${fmt(pts[0])} · skill ${fmt(pts[1])} · résumé ${fmt(pts[2])}</small></div>`;
}
$("sel-chips").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b) { S.sel = S.sel.filter((f) => f !== b.dataset.f); mark("fighters"); }
});
$("sel-add").addEventListener("change", (e) => { addFighter(e.target.value); e.target.value = ""; });

// ---- 5. careers: the year-by-year receipt -------------------------------------------------
function receiptChart() {
  const r = D.receipt[S.rec], i = I.get(S.rec);
  if (!r) return empty("rec-chart", "No rated years for this fighter.");
  const y = r.map((x) => x[0]), e = r.map((x) => x[3]), m = sum(e) || 1, top3 = sum([...e].sort((a, b) => b - a).slice(0, 3));
  const on = e.map((v) => v >= 1);
  plot("rec-chart", [{ type: "bar", x: y, y: e, marker: { color: on.map((b) => (b ? T.accent : T.context)) },
    customdata: r.map((x) => [x[1], x[2]]),
    hovertemplate: "%{x}<br>credited %{y:.0f}<br>yearly mean rating %{customdata[0]:.0f}<br>that year's bar %{customdata[1]:.0f}<extra></extra>" }],
  { height: 380, xaxis: { title: { text: "Year" }, dtick: y.length > 14 ? 2 : 1 }, yaxis: { title: { text: "Credited excess over the bar" }, rangemode: "tozero" } });
  ex("rec-chart", `${esc(S.rec)}: ${on.filter(Boolean).length} of ${y.length} years above the bar; career mass ${fmt(F.mass[i])}.`,
    `The bars sum to the published career mass.`);
}
SECTIONS.careers = receiptChart;
$("rec-pick").value = S.rec;
$("rec-pick").addEventListener("change", (e) => { if (I.has(e.target.value)) { S.rec = e.target.value; receiptChart(); } });

// ---- 6. risers and fallers ---------------------------------------------------------------------------------
const movYears = Object.keys(D.movers).sort((a, b) => b - a);
$("mov-year").innerHTML = movYears.map((y) => `<option>${y}</option>`).join("");
SECTIONS.movers = () => {
  const y = $("mov-year").value, t = D.movers[y].data[0];
  if (!t || !t.x?.length) return empty("mov-chart", `No measurable rating moves in ${y}.`);
  const k = range(t.x.length), hi = argmax(k, (j) => t.x[j]), lo = argmax(k, (j) => -t.x[j]);
  plot("mov-chart", [{ type: "bar", orientation: "h", x: t.x, y: t.y, marker: { color: t.x.map((v) => (v >= 0 ? T.accent : T.negative)) },
    text: t.x.map((v) => sgn(v)), textposition: "outside", cliponaxis: false, textfont: { size: 12, color: T.text2 }, customdata: t.customdata,
    hovertemplate: "<b>%{y}</b><br>%{x:+.0f} over %{customdata[1]} bouts<br>%{customdata[0]}<extra></extra>" }],
  { height: Math.max(420, 22 * t.x.length + 90), xaxis: { title: { text: "Change in base WHR skill over the year" }, zeroline: true, zerolinecolor: T.text2 },
    yaxis: { automargin: true }, margin: { r: 48, l: 8 } });
  ex("mov-chart", `${y}: ${esc(t.y[hi])} ${sgn(t.x[hi])}; ${esc(t.y[lo])} ${sgn(t.x[lo])}.`, `Board fighters, both genders.`);
};
$("mov-year").addEventListener("change", () => mark("movers"));

// ---- 7. win streaks ----------------------------------------------------------------------------------------
// row: fighter, length, start day, end day, division, divisions, title wins, finishes, avg opp, ongoing, ended by, gender
let stRows = [];
SECTIONS.streaks = () => {
  stRows = streaks(S.g, S.div, S.stMin, S.stSort).slice(0, S.top);
  const mx = Math.max(1, ...stRows.map((r) => r[1]));
  $("st-table").innerHTML = stRows.length ? `<table><thead><tr><th>#</th><th>Fighter</th><th class="num">Streak</th><th>Division</th><th>Span</th>
    <th class="num">Avg opp</th><th class="num">Titles</th><th class="num">Finishes</th><th>Status</th></tr></thead><tbody>` +
    stRows.map((r, k) => `<tr class="pickable ${S.streak === r ? "sel" : ""}" data-k="${k}"><td>${chip(k + 1)}</td><td class="name">${esc(r[0])}</td>
      <td class="num bar"><i style="width:${(100 * r[1] / mx).toFixed(0)}%"></i><span>${r[1]}</span></td>
      <td>${esc(r[4] ?? "—")}</td><td class="dim">${iso(r[2]).slice(0, 4)}–${iso(r[3]).slice(0, 4)}</td><td class="num dim">${fmt(r[8])}</td>
      <td class="num dim">${r[6]}</td><td class="num dim">${r[7]}</td><td class="${r[9] ? "ok" : "dim"}">${esc(r[10])}</td></tr>`).join("") + "</tbody></table>"
    : `<p class="note" style="padding:10px 14px">No streaks match the current filters.</p>`;
  if (!stRows.includes(S.streak)) S.streak = stRows[0] ?? null;
  streakChart();
};
// Each streak placed by its length and the strength of who it beat; the table's rows, the selected one marked.
function streakChart() {
  const R = stRows.filter((r) => r[8] != null);
  if (!R.length) return empty("st-chart", "No streaks match the current filters.");
  const long = argmax(R, (r) => r[1]), hard = argmax(R, (r) => r[8]);
  const named = new Set([long, hard, S.streak, ...[...R].sort((a, b) => b[1] - a[1]).slice(0, 4)].filter((r) => r && r[8] != null));
  plot("st-chart", [{ type: "scatter", mode: "markers", x: R.map((r) => r[1]), y: R.map((r) => r[8]),
    marker: { size: R.map((r) => (r === S.streak ? 13 : 9)), color: R.map((r) => (r === S.streak ? T.accent : T.context)), line: { color: T.bg, width: 1 } },
    customdata: R.map((r) => [r[0], iso(r[2]).slice(0, 4), iso(r[3]).slice(0, 4), r[6], r[10]]),
    hovertemplate: "<b>%{customdata[0]}</b><br>%{x} straight UFC wins, %{customdata[1]}–%{customdata[2]}<br>average opponent %{y:.0f}<br>%{customdata[3]} title wins · %{customdata[4]}<extra></extra>" }],
  { height: 440, annotations: [...named].map((r) => label(r[1], r[8], r[0].split(" ").at(-1), r === S.streak ? T.accent : T.text2, { yshift: 13 })),
    xaxis: { title: { text: "Streak length (UFC wins)" }, dtick: 1 }, yaxis: { title: { text: "Average opponent rating (Glicko-2 today)" } } });
  ex("st-chart", long === hard ? `${esc(long[0])}: longest (${long[1]}) and toughest (${fmt(hard[8])}).`
    : `Longest: ${esc(long[0])}, ${long[1]}. Toughest: ${esc(hard[0])}, ${fmt(hard[8])}.`, `Opponent rating: Glicko-2 today.`);
}
$("st-table").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-k]");
  if (!tr) return;
  S.streak = stRows[+tr.dataset.k];
  $("st-table").querySelectorAll("tr").forEach((x) => x.classList.toggle("sel", x === tr));
  streakChart();
});
$("st-sort").addEventListener("change", (e) => { S.stSort = e.target.value; mark("streaks"); });

// ---- 7b. upsets --------------------------------------------------------------------------------------------
// row: date, winner, loser, winner's no-vig chance, method, title fight, weight class
SECTIONS.upsets = () => {
  const U = [...D.upsets].reverse(), V = D.market, yr = (r) => r[0].slice(0, 4);
  const y = U.map((r) => `${r[1]} over ${r[2].split(" ").at(-1)} (${yr(r)})`), lo = U.at(-1), titles = U.filter((r) => r[5]).length;
  plot("up-chart", [{ type: "bar", orientation: "h", x: U.map((r) => r[3]), y, marker: { color: U.map((r) => (r[5] ? T.accent : T.context)) },
    text: U.map((r) => fmt(100 * r[3]) + "%"), textposition: "outside", cliponaxis: false, textfont: { size: 12, color: T.text2 },
    customdata: U.map((r) => [r[2], r[0], r[4] ?? "", r[6] ?? "", r[5] ? "title fight" : ""]),
    hovertemplate: "<b>%{y}</b><br>beat %{customdata[0]}, %{customdata[1]}<br>%{customdata[3]} · %{customdata[2]} %{customdata[4]}<br>market chance %{x:.1%}<extra></extra>" }],
  { height: Math.max(420, 26 * U.length + 90), xaxis: { title: { text: "Winner's chance in the betting market" }, tickformat: ".0%", rangemode: "tozero" },
    yaxis: { automargin: true }, margin: { l: 8, r: 48 } });
  ex("up-chart", `Favourites won ${fmt(100 * V.fav)}% of ${fmt(V.odds_bouts)} UFC bouts with odds, ${V.years[0]}–${V.years[1]}. The longest shot to win: ${esc(lo[1])} over ${esc(lo[2])}, ${fmt(100 * lo[3])}% (${yr(lo)}); ${titles} of these ${U.length} were title fights.`,
    `Accent: title fight. Draws and no contests excluded.`);
};

// ---- 8. weight classes -------------------------------------------------------------------------------------
const dvYears = [...new Set(D.strength["10"].map((r) => r[1]))].sort((a, b) => a - b);
const DV = { y0: Math.max(2000, dvYears[0]), y1: dvYears[dvYears.length - 1] };
$("dv-y0").value = DV.y0; $("dv-y1").value = DV.y1;
$("dv-year").min = Math.min(...Object.keys(D.year_top)); $("dv-year").max = Math.max(...Object.keys(D.year_top));
$("dv-year").value = $("o-dv-year").textContent = $("dv-year").max;
$("dv-chips").innerHTML = D.divisions.map((d) => `<button type="button" class="chip ${S.dv.has(d) ? "on" : ""}" data-d="${esc(d)}" aria-pressed="${S.dv.has(d)}" aria-label="${esc(d)}">${esc(short(d))}</button>`).join("");
SECTIONS.divisions = () => {
  const sel = D.divisions.filter((d) => S.dv.has(d)), y0 = Math.min(DV.y0, DV.y1), y1 = Math.max(DV.y0, DV.y1);
  const rows = D.strength[S.k].filter((r) => S.dv.has(r[0]) && r[1] >= y0 && r[1] <= y1);
  if (!rows.length) empty("dv-heat", "Select at least one class with enough rated fighters.");
  else {
    const { ys, L } = leaders(rows), top = new Map(L.map((r) => [r[1], r[2]])), cell = new Map(rows.map((r) => [r[0] + "|" + r[1], r]));
    const ds = sel.filter((d) => rows.some((r) => r[0] === d)).reverse(), cnt = {};
    const z = ds.map((d) => ys.map((y) => { const r = cell.get(d + "|" + y); return r ? 100 * r[2] / top.get(y) : null; }));
    L.forEach((r) => { cnt[r[0]] = (cnt[r[0]] || 0) + 1; });
    const Z = z.flat().filter((v) => v != null).sort((a, b) => a - b), zmin = Math.floor(Z[Math.floor(0.1 * (Z.length - 1))]);  // colour floor: 10th percentile
    const most = argmax(Object.keys(cnt), (d) => cnt[d]);
    plot("dv-heat", [{ type: "heatmap", x: ys, y: ds.map(short), z, zmin, zmax: 100, colorscale: "Viridis", xgap: 1, ygap: 1,
      colorbar: { title: { text: "index", font: { color: T.text2 } }, tickfont: { color: T.text2, size: 12 }, outlinewidth: 0 },
      customdata: ds.map((d) => ys.map((y) => { const r = cell.get(d + "|" + y); return r ? [r[2], r[3]] : [null, null]; })),
      hovertemplate: "%{x} · %{y}<br>index %{z:.1f}<br>top-end rating %{customdata[0]:.0f} · %{customdata[1]} fighters<extra></extra>" }],
    { height: Math.max(300, 34 * ds.length + 90), xaxis: { title: { text: "Year" } } });
    ex("dv-heat", `${esc(L.at(-1)[0])} leads in ${ys.at(-1)}; ${esc(most)} led most often, ${cnt[most]} of ${ys.length} years.`,
      `100 = that year's strongest class, by the mean of its top ${S.k}. Colour floor ${zmin}.`);
  }
  yearTop();
  methodMix(y0, y1);
};
function yearTop() {
  const yr = $("dv-year").value, keep = new Set([...S.dv].map(short));
  const nm = (y) => y.replace(/^\d+\.\s*/, "").split("·")[0].trim(), full = (c) => D.divisions.find((d) => short(d) === c) || c;
  // one row per class: its top five (rank-1 first), ordered by their mean, strongest at the top
  const R = D.year_top[yr].data.filter((t) => keep.has(t.name))
    .map((t) => ({ c: t.name, x: t.x, f: t.y.map(nm), m: sum(t.x) / t.x.length })).sort((a, b) => a.m - b.m);
  if (!R.length) return empty("dv-year-chart", `No rated fighters in the selected classes in ${yr}.`);
  const top = R.at(-1), best = argmax(R, (r) => Math.max(...r.x)), each = (g) => R.flatMap((r) => r.x.map((_, k) => g(r, k)));
  plot("dv-year-chart", [
    { type: "scatter", mode: "markers", x: each((r, k) => r.x[k]), y: each((r) => r.c),
      marker: { size: 11, color: each((r) => (r === top ? T.accent : T.context)), line: { color: T.bg, width: 1 } },
      customdata: each((r, k) => `${k + 1}. ${r.f[k]}`), hovertemplate: "%{customdata} · %{y}<br>end-of-year rating %{x:.0f}<extra></extra>" },
    { type: "scatter", mode: "markers", x: R.map((r) => r.m), y: R.map((r) => r.c), marker: { symbol: "line-ns-open", size: 18, color: T.text2, line: { width: 2 } },
      hovertemplate: "%{y}: top-five mean %{x:.0f}<extra></extra>" },
  ], { height: Math.max(260, 48 * R.length + 80), xaxis: { title: { text: "End-of-year rating" } },
    yaxis: { categoryorder: "array", categoryarray: R.map((r) => r.c) },
    annotations: R.map((r) => label(Math.max(...r.x), r.c, esc(r.f[0]), r === top ? T.accent : T.text2, { xanchor: "right", yshift: 14 })) });
  ex("dv-year-chart", `${yr}: ${esc(full(top.c))} has the strongest top five (mean ${fmt(top.m)}); ${esc(best.f[0])} rated highest, ${fmt(Math.max(...best.x))}.`,
    `Dots: the top five by end-of-year rating, #1 named; tick: their mean.`);
}
function methodMix(y0, y1) {
  const mix = {};
  D.mix.forEach(([y, d, b, n]) => { if (y < y0 || y > y1 || !S.dv.has(d)) return; (mix[y] ||= { Decision: 0, "KO/TKO": 0, Submission: 0 })[b] += n; });
  const ys = Object.keys(mix).map(Number).sort((a, b) => a - b), tot = ys.map((y) => sum(Object.values(mix[y])));
  if (!ys.length) return empty("dv-mix", "No bouts in the selected classes and years.");
  const P = { Decision: CAT[0], "KO/TKO": CAT[1], Submission: CAT[2] }, sh = (b, k) => mix[ys[k]][b] / tot[k];
  plot("dv-mix", Object.keys(P).map((b) => ({ type: "scatter", mode: "lines", stackgroup: "one", x: ys, y: ys.map((_, k) => sh(b, k)),
    line: { width: 0.5, color: P[b] }, fillcolor: P[b], customdata: tot, hovertemplate: `<b>${b}</b><br>%{x}: %{y:.0%} of %{customdata} bouts<extra></extra>` })), {
    height: 400, annotations: Object.keys(P).map((b, j) => { const k = ys.length - 1, below = sum(Object.keys(P).slice(0, j).map((c) => sh(c, k)));
      return label(ys[k], below + sh(b, k) / 2, b, P[b], { xanchor: "left", xshift: 6 }); }),
    yaxis: { range: [0, 1], tickformat: ".0%", title: { text: "Share of bouts" } }, xaxis: { title: { text: "Year" }, range: [ys[0], ys.at(-1)] }, margin: { r: 96 } });
  const w = Math.min(5, ys.length), dec = (K) => 100 * sum(K.map((k) => mix[ys[k]].Decision)) / sum(K.map((k) => tot[k]));
  const K0 = range(w), K1 = range(w).map((k) => ys.length - w + k);
  ex("dv-mix", `Decisions: ${fmt(dec(K0))}% in ${ys[0]}–${ys[w - 1]}, ${fmt(dec(K1))}% in ${ys[ys.length - w]}–${ys.at(-1)}.`, `${fmt(sum(tot))} UFC bouts.`);
}
$("dv-chips").addEventListener("click", (e) => {
  const c = e.target.closest(".chip");
  if (!c) return;
  S.dv.has(c.dataset.d) ? S.dv.delete(c.dataset.d) : S.dv.add(c.dataset.d);
  c.classList.toggle("on");
  c.setAttribute("aria-pressed", String(S.dv.has(c.dataset.d)));
  mark("divisions");
});
["y0", "y1"].forEach((k) => $("dv-" + k).addEventListener("change", (e) => { DV[k] = +e.target.value; mark("divisions"); }));
$("dv-k").addEventListener("change", (e) => { S.k = e.target.value; mark("divisions"); });
$("dv-year").addEventListener("input", (e) => { $("o-dv-year").textContent = e.target.value; yearTop(); });

// ---- 9. title lineage ----------------------------------------------------------------------------------------
$("tl-div").innerHTML = Object.keys(D.lineage).map((d) => `<option ${d === "Lightweight" ? "selected" : ""}>${esc(d)}</option>`).join("");
SECTIONS.lineage = () => {
  const d = $("tl-div").value, R = reigns(D.lineage[d][$("tl-int").checked ? 1 : 0]);
  if (!R.length) return empty("tl-chart", `No title wins recorded at ${d}.`);
  const done = R.length > 1 ? R.slice(0, -1) : R, top = done.reduce((b, r) => (r.yrs > b.yrs ? r : b));
  plot("tl-chart", R.map((r, k) => ({ type: "bar", orientation: "h", x: [r.x], base: [r.start], y: ["belt"], text: [r.text],
    textposition: "inside", insidetextanchor: "middle", textangle: 0, textfont: { size: 12, color: r === top ? T.bg : T.text },
    marker: { color: r === top ? T.accent : k % 2 ? T.context : T.border2, line: { color: T.bg, width: 1 } },
    customdata: [[r.f, r.opp, r.start, r.def, r.yrs]],
    hovertemplate: "<b>%{customdata[0]}</b><br>won %{customdata[2]} against %{customdata[1]}<br>%{customdata[3]} defences · %{customdata[4]} years<extra></extra>" })),
  { height: 200, barmode: "overlay", uniformtext: { minsize: 12, mode: "hide" }, xaxis: { type: "date" }, yaxis: { visible: false }, margin: { t: 8, b: 32, l: 8, r: 8 } });
  ex("tl-chart", `Longest: ${esc(top.f)}, ${fmt(top.yrs, 1)} years, ${top.def} defence${top.def === 1 ? "" : "s"}.`,
    `A reign runs to the next title change, so a vacated belt counts until refilled.`);
};
$("tl-div").addEventListener("change", () => mark("lineage"));
$("tl-int").addEventListener("change", () => mark("lineage"));

// ---- 10. dominance -----------------------------------------------------------------------------------------
SECTIONS.dominance = () => {
  const P = pool("all_time").filter((i) => F.dom[i] != null && F.domw[i] >= S.dmMin).sort((x, y) => F.dom[y] - F.dom[x]).slice(0, S.top).reverse();
  if (!P.length) return empty("dm-chart", "No fighters match the current filters.");
  const top = P.at(-1);
  plot("dm-chart", [{ type: "bar", orientation: "h", x: P.map((i) => F.dom[i]), y: P.map((i) => F.name[i]),
    marker: { color: P.map((i) => (i === top ? T.accent : T.context)) }, text: P.map((i) => fmt(F.dom[i], 1)), textposition: "outside",
    cliponaxis: false, textfont: { size: 12, color: T.text2 }, customdata: P.map((i) => [F.domw[i], fmt(F.whr[i])]),
    hovertemplate: "<b>%{y}</b><br>dominance %{x:.1f}<br>%{customdata[0]} wins<br>rating %{customdata[1]}<extra></extra>" }],
  { height: Math.max(380, 22 * P.length + 80), xaxis: { title: { text: "Mean dominance per win" }, rangemode: "tozero" }, margin: { l: 8, r: 48 } });
  const tie = P.filter((i) => F.dom[i] === F.dom[top]).length;
  ex("dm-chart", `${esc(F.name[top])} leads${tie > 1 ? `, tied with ${tie - 1}` : ""}: ${fmt(F.dom[top], 1)} over ${F.domw[top]} wins.`, `${P.length} fighters with ${S.dmMin}+ wins.`);
};

// ---- 10b. age and layoffs against the market -----------------------------------------------------------------
// band row: label, fighter appearances, win rate, mean no-vig price, standard error of (won − price)
// Pooled bands k0..k1: [label, n, won, priced, se], se = √Σ(n·se)² / N.
function pooled(R, k0, k1, lab) {
  const B = R.slice(k0, k1 + 1), N = sum(B.map((r) => r[1])), w = (j) => sum(B.map((r) => r[1] * r[j])) / N;
  return [lab, N, w(2), w(3), Math.sqrt(sum(B.map((r) => (r[1] * r[4]) ** 2))) / N];
}
function vsPrice(id, R, xt, lo, hi) {
  const x = R.map((r) => r[0]);
  plot(id, [
    { type: "scatter", mode: "lines", x: x.flatMap((v) => [v, v, null]), y: R.flatMap((r) => [r[3], r[2], null]), line: { color: T.border2, width: 2 }, hoverinfo: "skip", showlegend: false },
    { type: "scatter", mode: "markers", name: "Market price", x, y: R.map((r) => r[3]), marker: { size: 10, symbol: "circle-open", color: T.text2, line: { width: 2 } },
      hovertemplate: "%{x}: priced %{y:.1%}<extra></extra>" },
    { type: "scatter", mode: "markers", name: "Won", x, y: R.map((r) => r[2]), marker: { size: 10, color: R.map((r) => (r[2] < r[3] ? T.negative : T.accent)) },
      error_y: { type: "data", array: R.map((r) => 1.96 * r[4]), color: T.border2, thickness: 1.5, width: 0 },
      customdata: R.map((r) => [r[1], 100 * (r[2] - r[3])]),
      hovertemplate: "%{x}: won %{y:.1%} (%{customdata[1]:+.1f} points)<br>%{customdata[0]:,} fights<extra></extra>" },
  ], { height: 400, showlegend: true, legend: { orientation: "h", y: 1.0, yanchor: "bottom", x: 0 }, margin: { t: 40 },
    xaxis: { title: { text: xt }, type: "category" }, yaxis: { title: { text: "Win rate" }, tickformat: ".0%" } });
  const gap = (r) => `${sgn(100 * (r[2] - r[3]), 1)} points (95% interval ±${fmt(196 * r[4], 1)})`;
  ex(id, `${lo[0]}: won ${fmt(100 * lo[2], 1)}% against a ${fmt(100 * lo[3], 1)}% price, ${gap(lo)}. ${hi[0]}: ${gap(hi)}.`,
    `${fmt(sum(R.map((r) => r[1])))} fighter appearances · bars: 95% intervals on the win rate.`);
}
SECTIONS.age = () => {
  const A = D.age, L = D.layoff;
  vsPrice("age-chart", A, "Age at the fight (years)", pooled(A, 4, A.length - 1, "Fighters 34 and older"), pooled(A, 0, 1, "Under 28"));
  vsPrice("lay-chart", L, "Months since the previous fight", pooled(L, 3, L.length - 1, "After 12 or more months out"), pooled(L, 1, 2, "After 4 to 12 months"));
};

// ---- 11. integrity policy ------------------------------------------------------------------------------------
// debit row: fighter, base rating, base rank, policy rank, debit, PED, DQ, missed-weight results
SECTIONS.policy = () => {
  const G = D.integrity, R = G.debits.slice(0, 15).reverse(), moves = R.map((r) => r[3] - r[2]), w = argmax(range(R.length), (k) => moves[k]);
  const y = R.map((r) => r[0]), why = (r) => [r[5] && `${r[5]} PED`, r[6] && `${r[6]} DQ`, r[7] && `${r[7]} missed weight`].filter(Boolean).join(", ");
  plot("pol-chart", [
    { type: "scatter", mode: "lines", x: R.flatMap((r) => [r[2], r[3], null]), y: R.flatMap((r) => [r[0], r[0], null]), line: { color: T.border2, width: 2 }, hoverinfo: "skip" },
    { type: "scatter", mode: "markers", x: R.map((r) => r[2]), y, marker: { size: 9, color: T.context },
      hovertemplate: "<b>%{y}</b><br>base rank #%{x}<extra></extra>" },
    { type: "scatter", mode: "markers", x: R.map((r) => r[3]), y, marker: { size: 9, color: T.negative },
      customdata: R.map((r) => [r[4], why(r), r[1]]), hovertemplate: "<b>%{y}</b><br>policy rank #%{x}<br>debit −%{customdata[0]:.0f} on base %{customdata[2]:.0f}<br>%{customdata[1]}<extra></extra>" },
  ], { height: Math.max(380, 24 * R.length + 80), xaxis: { title: { text: `Rank among all ${fmt(G.rated)} rated fighters (1 is best)` }, autorange: "reversed" },
    yaxis: { automargin: true }, margin: { l: 8 } });
  ex("pol-chart", `Largest move: ${esc(R[w][0])}, #${R[w][2]} → #${R[w][3]} for −${fmt(R[w][4])}.`, `${fmt(G.n)} fighters debited; the 15 highest-rated shown.`);
  const L = G.ledger.slice(0, Math.max(S.top, 25));
  $("pol-table").innerHTML = `<table><thead><tr><th>Date</th><th>Fighter</th><th>Opponent</th><th>Reason</th><th>Detail</th>
    <th class="num">Result weight</th><th class="num">Discount</th></tr></thead><tbody>` +
    L.map((r) => `<tr><td class="dim">${r[0] ?? ""}</td><td class="name">${esc(r[1])}</td><td>${esc(r[2])}</td><td>${esc(r[3])}</td>
      <td class="dim" style="white-space:normal;min-width:260px">${esc(r[4])}</td><td class="num">${fmt(r[5], 2)}</td><td class="num down">${fmt(r[6])}%</td></tr>`).join("") + "</tbody></table>";
};

// ---- 12. calibration ---------------------------------------------------------------------------------------
// The causal rating and the no-vig market on the same bouts; [bin, mean forecast, win rate, n] per source.
// row: label, log loss, Brier, winners picked, log loss minus the market's, 95% interval low, high
function marketChart() {
  const V = D.market, pct = (v) => fmt(100 * v, 1) + "%", row = (l) => V.rows.find((r) => r[0] === l);
  const R = [...V.rows].sort((a, b) => b[1] - a[1]), mk = row("Betting market"), sm = row("Stats model"), both = row("Market + stats model");
  const sgn = (v) => (v >= 0 ? "+" : "−") + fmt(Math.abs(v), 3);
  plot("mk-chart", [{ type: "scatter", mode: "markers", x: R.map((r) => r[1]), y: R.map((r) => r[0]),
    marker: { size: 12, color: R.map((r) => (r === mk ? T.accent : T.text2)) },
    customdata: R.map((r) => [100 * r[3], r === mk ? "" : `<br>${sgn(r[4])} vs market (95%: ${sgn(r[5])} to ${sgn(r[6])})`]),
    hovertemplate: "<b>%{y}</b><br>log loss %{x:.3f}%{customdata[1]}<br>winners picked %{customdata[0]:.1f}%<extra></extra>" }],
  { height: 300, xaxis: { title: { text: "Log loss (lower is better)" }, tickformat: ".3f" }, yaxis: { automargin: true }, margin: { l: 8 } });
  ex("mk-chart", `Nothing beats the market. Its log loss is ${fmt(mk[1], 3)}; the stats model scores ${fmt(sm[1], 3)}, and adding the stats to the price changes it by ${sgn(both[4])} (95% interval ${sgn(both[5])} to ${sgn(both[6])}).`,
    `${fmt(V.n)} UFC bouts with odds, ${V.span[0]} to ${V.span[1]}; each year forecast by a model fitted on earlier years · pre-UFC regional bouts are left out, because they were recorded only for fighters who later lasted in the UFC.`);
  const pts = (R0, name, color, symbol) => { const Q = R0.filter((r) => r[3] >= 50); return { type: "scatter", mode: "markers", name, x: Q.map((r) => r[1]), y: Q.map((r) => r[2]),
    marker: { size: 10, color, symbol, line: { color, width: 2 } }, customdata: Q.map((r) => r[3]),
    hovertemplate: `${name}<br>forecast %{x:.1%}<br>observed %{y:.1%}<br>n = %{customdata:,}<extra></extra>` }; };
  plot("mkc-chart", [
    { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], line: { color: T.muted, dash: "dash", width: 1 }, hoverinfo: "skip", showlegend: false },
    pts(V.cal_market, "Betting market", T.accent, "circle"), pts(V.cal_model, "Stats model", T.text2, "diamond-open"),
  ], { height: 460, showlegend: true, legend: { orientation: "h", y: 1.0, yanchor: "bottom", x: 0 }, margin: { t: 40 },
    xaxis: { title: { text: "Forecast win probability" }, range: [0, 1], tickformat: ".0%" },
    yaxis: { title: { text: "Observed win rate" }, range: [0, 1], tickformat: ".0%" } });
  const b8 = (C) => C.find((r) => r[0] === 8), cm = b8(V.cal_market), cs = b8(V.cal_model);
  ex("mkc-chart", `The market picked the winner in ${pct(mk[3])} of bouts, the stats model in ${pct(sm[3])}. Fighters the market rated near ${pct(cm[1])} won ${pct(cm[2])}; the model's picks near ${pct(cs[1])} won ${pct(cs[2])}.`,
    `Same bouts · both corners · bins under 50 bouts hidden.`);
}
const calSegs = [...new Set(D.calib.map((r) => r[0]))];
$("cal-seg").innerHTML = calSegs.map((s) => `<option>${esc(s)}</option>`).join("");
SECTIONS.checks = () => {
  marketChart();
  const R = calRows(S.cal), n = sum(R.map((r) => r.n)) / 2, dev = Math.max(...R.map((r) => Math.abs(r.y - r.p)));
  const cover = R.filter((r) => Math.abs(r.y - r.p) <= 1.96 * r.se).length;
  plot("cal-chart", [
    { type: "scatter", mode: "lines", x: [0, 1], y: [0, 1], line: { color: T.muted, dash: "dash", width: 1 }, hoverinfo: "skip" },
    { type: "scatter", mode: "markers", x: R.map((r) => r.p), y: R.map((r) => r.y), marker: { size: 9, color: T.accent },
      error_y: { type: "data", array: R.map((r) => 1.96 * r.se), color: T.accent, thickness: 1.5, width: 0 },
      customdata: R.map((r) => [r.n, 100 * (r.y - r.p)]),
      hovertemplate: "forecast %{x:.1%}<br>observed %{y:.1%} (%{customdata[1]:+.1f} points)<br>n = %{customdata[0]:,}<extra></extra>" },
  ], { height: 460, annotations: [label(0.98, 0.9, "forecast = observed", T.muted, { xanchor: "right", yanchor: "top" })],
    xaxis: { title: { text: "Forecast win probability" }, range: [0, 1], tickformat: ".0%" },
    yaxis: { title: { text: "Observed win rate" }, range: [0, 1], tickformat: ".0%" } });
  ex("cal-chart", `Largest gap ${fmt(100 * dev, 1)} points; favourites win slightly ${overconfident(R) ? "less" : "more"} often than forecast.`,
    `${fmt(n)} bouts · bars: 95% intervals · causal Glicko-2.`);
};
$("cal-seg").addEventListener("change", (e) => { S.cal = e.target.value; mark("checks"); });

// ---- 13. benchmark -----------------------------------------------------------------------------------------
// row: fighter, engine rank, FightMatrix rank, gap, score, FightMatrix points
SECTIONS.benchmark = () => {
  const all = D.bench.slice(0, Math.max(15, S.top)), B = all.filter((r) => r[2] != null).reverse();
  if (B.length < 3) return empty("bm-chart", "Too few matched fighters.");
  const far = argmax(B, (r) => Math.abs(r[3]));
  plot("bm-chart", [
    { type: "scatter", mode: "lines", x: B.flatMap((r) => [r[1], r[2], null]), y: B.flatMap((r) => [r[0], r[0], null]),
      line: { color: T.border2, width: 2 }, hoverinfo: "skip" },
    { type: "scatter", mode: "markers", x: B.map((r) => r[2]), y: B.map((r) => r[0]), marker: { color: T.context, size: 9, symbol: "diamond" },
      customdata: B.map((r) => r[5]), hovertemplate: "<b>%{y}</b><br>FightMatrix #%{x}<br>%{customdata:,.0f} points<extra></extra>" },
    { type: "scatter", mode: "markers", x: B.map((r) => r[1]), y: B.map((r) => r[0]), marker: { color: B.map((r) => (r === far ? T.accent : T.text2)), size: 9 },
      customdata: B.map((r) => [r[4], r[3]]), hovertemplate: "<b>%{y}</b><br>Career Rankings #%{x}<br>score %{customdata[0]:.1f}<br>gap %{customdata[1]:+d}<extra></extra>" },
  ], { height: Math.max(420, 22 * B.length + 80), xaxis: { range: [Math.max(...B.flatMap((r) => [r[1], r[2]])) + 1, 0], title: { text: "Rank (1 is best)" } },
    yaxis: { automargin: true }, margin: { l: 8 } });
  ex("bm-chart", `ρ = ${fmt(rho(B.map((r) => r[1]), B.map((r) => r[2])), 2)} over ${B.length} matched; biggest gap ${esc(far[0])}, #${far[1]} here, #${far[2]} there.`,
    `Dot: Career Rankings · diamond: FightMatrix.`);
};

// ---- wiring --------------------------------------------------------------------------------------------------
const phoneLayout = matchMedia('(max-width: 720px)');
const filterPanel = document.querySelector('.filter-panel');
filterPanel.open = !phoneLayout.matches;
phoneLayout.addEventListener('change', e => { filterPanel.open = !e.matches; });
seg("c-gender", "g", () => { divisionOptions(); mark(); });
["c-div", "c-class"].forEach((id) => $(id).addEventListener("change", (e) => {
  S.div = $("c-div").value = $("c-class").value = e.target.value;
  mark();
}));
slider("c-top", "o-top", "top", () => mark());
slider("c-min", "o-min", "min", () => mark());
slider("st-min", "o-st-min", "stMin", () => mark("streaks"));
slider("dm-min", "o-dm-min", "dmMin", () => mark("dominance"));
$("w-a").value = S.a; $("w-s").value = S.s; $("o-a").textContent = fmt(S.a, 3); $("o-s").textContent = fmt(S.s, 3);
$("release-label").textContent = `Published ${M.snapshot}`;
$("foot").textContent = `${SNAP}. The rankings are the published boards; see README.md and RANKINGS.md.`;
$("names").innerHTML = F.name.map((f) => `<option value="${esc(f)}">`).join("");
divisionOptions();
facts();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { theme(); mark(); });
// Keep navigation in step with the section being read.
const navObserver = new IntersectionObserver((entries) => {
  const current = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
  if (!current) return;
  document.querySelectorAll('nav a').forEach(a => {
    if (a.hash === '#' + current.target.id) a.setAttribute('aria-current', 'location');
    else a.removeAttribute('aria-current');
  });
}, { rootMargin: '-15% 0px -65% 0px' });
document.querySelectorAll('main section[id]').forEach(section => navObserver.observe(section));
const headerSize = new ResizeObserver(([entry]) => {
  document.documentElement.style.setProperty('--header-height', `${entry.target.getBoundingClientRect().height}px`);
});
headerSize.observe(document.querySelector('.top'));
// The rankings table is cheap and is the page's purpose, so it always draws; on a phone the
// hero is taller than the screen and the table would otherwise wait for a scroll.
const ALWAYS_DRAWN = new Set(["rankings"]);
const io = new IntersectionObserver((es) => {
  es.forEach((e) => (e.isIntersecting || ALWAYS_DRAWN.has(e.target.id) ? visible.add(e.target.id) : visible.delete(e.target.id)));
  flush();
}, { rootMargin: "400px 0px" });
Object.keys(SECTIONS).forEach((id) => { dirty.add(id); io.observe($(id)); });
