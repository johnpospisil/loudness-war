// "How loud is my album?" — static lookup over app/data (built by `python -m lw.app.build`).
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";

const $ = (id) => document.getElementById(id);
const state = { conn: null, dist: null, album: null, scope: "all", metric: "lufs" };
const SVGNS = "http://www.w3.org/2000/svg";
const Y0 = 1980, Y1 = 2022;
const MAX_RESULTS = 200;

const minus = (s) => String(s).replace(/-/g, "−");
const fmt = (v, d = 1) => minus(Number(v).toFixed(d));
const norm = (s) => s.normalize("NFKD").replace(/\p{Mn}/gu, "").toLowerCase()
  .replace(/[^\p{L}\p{N}]+/gu, " ").trim();

function pct(p) {
  if (p == null || Number.isNaN(p)) return null;
  if (p > 99) return "over 99%";
  if (p < 1) return "under 1%";
  return `${Math.round(p)}%`;
}

function windowYears(y) {
  const w = state.dist.win;
  return [Math.max(Y0, y - w), Math.min(Y1, y + w)];
}

function genreName(g, plural = true) {
  if (!g) return null;
  if (g === "other") return plural ? "albums in other genres" : "Other";
  const label = state.dist.genres[g];
  return plural ? `${label.toLowerCase()} albums` : label;
}

// ---------- data ----------
async function init() {
  const [dist, buf] = await Promise.all([
    fetch("data/dist.json?v=bc99e0cd60").then((r) => r.json()),
    fetch("data/albums.parquet?v=46d987d708").then((r) => {
      if (!r.ok) throw new Error(`albums.parquet: HTTP ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  state.dist = dist;
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }),
  );
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);
  await db.registerFileBuffer("albums.parquet", new Uint8Array(buf));
  state.conn = await db.connect();
  await state.conn.query("create table albums as select * from 'albums.parquet'");
  $("n-albums").textContent = dist.n_albums.toLocaleString("en-GB");
  $("min-tracks").textContent = dist.min_tracks;
}

const COLS = `mbid, title, artist, type, year, genre, n_tracks, lufs, lra, lufs_min, lufs_max,
  pct_lufs, pct_lufs_genre, pct_lra, pct_lra_genre`;

async function rows(sql, params) {
  const stmt = await state.conn.prepare(sql);
  const res = await stmt.query(...params);
  await stmt.close();
  return res.toArray().map((r) => {
    const o = r.toJSON();
    for (const k of Object.keys(o)) if (typeof o[k] === "bigint") o[k] = Number(o[k]);
    return o;
  });
}

async function search(q) {
  const words = norm(q).split(" ").filter(Boolean).slice(0, 6);
  if (!words.length) return [];
  const where = words.map(() => "(title_key || ' ' || artist_key) like ?").join(" and ");
  const full = norm(q);
  // keep the MAX_RESULTS most relevant matches, then list them in release-year order
  const list = await rows(
    `select ${COLS}, count(*) over () as n_total from albums where ${where}
     order by (title_key = ?) desc, (artist_key = ?) desc, n_sub desc limit ${MAX_RESULTS}`,
    [...words.map((w) => `%${w}%`), full, full],
  );
  return list.sort((a, b) => a.year - b.year || a.title.localeCompare(b.title));
}

// ---------- rendering ----------
// Charts are drawn at the container's real pixel width, so text stays 12 px on phones.
const width = (svg) => Math.max(280, Math.round(svg.parentElement.clientWidth || 720));
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

function renderResults(list, q) {
  const ol = $("results");
  ol.replaceChildren();
  if (!list.length) {
    $("status").textContent = `No albums match "${q}". Try fewer words, or the artist's name on its own.`;
    return;
  }
  const total = list[0].n_total;
  $("status").textContent = total > list.length
    ? `${total.toLocaleString("en-GB")} matches. Showing the ${list.length} most-submitted, oldest first. Add a word to narrow it down.`
    : list.length === 1 ? "1 match." : `${list.length} matches, oldest first.`;
  for (const a of list) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<span class="r-title"></span><span class="r-lufs"></span><span class="r-sub"></span>`;
    b.querySelector(".r-title").textContent = a.title;
    b.querySelector(".r-sub").textContent = `${a.artist}, ${a.year}`;
    b.querySelector(".r-lufs").textContent = `${fmt(a.lufs)} LUFS`;
    b.addEventListener("click", () => select(a, true));
    li.appendChild(b);
    ol.appendChild(li);
  }
}

function select(a, scroll) {
  state.album = a;
  if (!a.genre && state.scope === "genre") state.scope = "all";
  history.replaceState(null, "", `#${a.mbid}`);
  $("album").hidden = false;
  $("a-title").textContent = a.title;
  const type = a.type && a.type !== "Other" ? a.type : "Release";
  const g = a.genre ? `, ${genreName(a.genre, false)}` : "";
  $("a-meta").textContent = `${a.artist}, ${a.year}. ${type}${g}. ${a.n_tracks} tracks measured, from ${fmt(a.lufs_min)} to ${fmt(a.lufs_max)} LUFS.`;
  $("a-lufs").textContent = fmt(a.lufs);
  $("a-lra").textContent = fmt(a.lra);
  const [w0, w1] = windowYears(a.year);
  const years = `albums released ${w0}–${w1}`;
  const gl = genreName(a.genre);
  $("a-lufs-text").textContent = `Louder than ${pct(a.pct_lufs)} of ${years}` +
    (gl && a.pct_lufs_genre != null ? `, and ${pct(a.pct_lufs_genre)} of ${gl} from those years.` : ".");
  $("a-lra-text").textContent = `More dynamic than ${pct(a.pct_lra)} of ${years}` +
    (gl && a.pct_lra_genre != null ? `, and ${pct(a.pct_lra_genre)} of ${gl}.` : ".") +
    " Loudness range is the coarser estimate.";
  $("t-genre").disabled = !a.genre;
  $("t-genre").textContent = a.genre ? genreName(a.genre, false) : "Same genre";
  $("a-mb").href = `https://musicbrainz.org/release-group/${a.mbid}`;
  $("a-share").href = `#${a.mbid}`;
  draw();
  if (scroll) $("album").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

function syncToggles() {
  document.querySelectorAll("[data-scope]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.scope === state.scope)));
  document.querySelectorAll("[data-metric]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.metric === state.metric)));
}

function draw() {
  syncToggles();
  drawMeter();
  drawTrend();
}

function drawMeter() {
  const a = state.album, d = state.dist, m = state.metric;
  const bins = d[`${m}_bins`];
  const [w0, w1] = windowYears(a.year);
  const key = state.scope === "genre" && a.genre ? a.genre : "all";
  const counts = new Array(bins.length - 1).fill(0);
  for (let y = w0; y <= w1; y++) {
    const h = d.hist[`${y}|${key}`];
    if (h) h[m].forEach((c, i) => { counts[i] += c; });
  }
  const n = counts.reduce((s, c) => s + c, 0);
  const who = key === "all" ? "all genres" : genreName(a.genre);
  $("m-caption").textContent = m === "lufs"
    ? `Median loudness of ${n.toLocaleString("en-GB")} albums released ${w0}–${w1}, ${who}`
    : `Median loudness range of ${n.toLocaleString("en-GB")} albums released ${w0}–${w1}, ${who}`;

  const svg = $("m-svg");
  const W = width(svg), H = 190, L = 8, R = 8, T = 30, B = 40;
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const lo = bins[0], hi = bins[bins.length - 1];
  const x = (v) => L + ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * (W - L - R);
  const max = Math.max(...counts, 1);
  const yb = (c) => T + (H - T - B) * (1 - c / max);
  const val = a[m];
  const step = m === "lufs" ? 5 : W < 500 ? 4 : 2;
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
    el("line", { x1: x(t), x2: x(t), y1: T, y2: H - B, class: "grid" }, svg);
    el("text", { x: x(t), y: H - B + 18, "text-anchor": "middle" }, svg).textContent = minus(t);
  }
  counts.forEach((c, i) => {
    const mine = val >= bins[i] && val < bins[i + 1];
    el("rect", {
      x: x(bins[i]) + 0.5, width: Math.max(x(bins[i + 1]) - x(bins[i]) - 1, 0.5),
      y: yb(c), height: H - B - yb(c), class: mine ? "bar mine" : "bar",
    }, svg);
  });
  el("line", { x1: L, x2: W - R, y1: H - B, y2: H - B, class: "axis", stroke: "#8a8984" }, svg);
  const xl = m === "lufs" ? "est. LUFS (quieter ← → louder)"
    : W < 500 ? "est. LU (compressed ← → dynamic)" : "est. LU loudness range (more compressed ← → more dynamic)";
  el("text", { x: W / 2, y: H - 6, "text-anchor": "middle" }, svg).textContent = xl;
  const xv = x(val);
  el("line", { x1: xv, x2: xv, y1: T - 8, y2: H - B, class: "needle" }, svg);
  const anchor = xv > W - 90 ? "end" : xv < 90 ? "start" : "middle";
  el("text", { x: xv, y: T - 14, "text-anchor": anchor, class: "needle-label" }, svg)
    .textContent = `This album ${fmt(val)}`;
}

function drawTrend() {
  const a = state.album, m = state.metric, s = state.dist.hero[m];
  const svg = $("t-svg");
  const W = width(svg), H = W < 500 ? 220 : 260, L = 40, R = 12, T = 12, B = 30;
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const vals = [...s.p10, ...s.p90, a[m]];
  const lo = Math.floor(Math.min(...vals)) - 0.5, hi = Math.ceil(Math.max(...vals)) + 0.5;
  const x = (y) => L + ((y - (Y0 - 0.5)) / (Y1 - Y0 + 1)) * (W - L - R);
  const y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  el("rect", { x: x(2015.95), y: T, width: x(Y1 + 0.5) - x(2015.95), height: H - T - B, class: "era" }, svg);
  el("text", { x: x(Y1 + 0.5) - 4, y: T + 14, "text-anchor": "end" }, svg).textContent =
    W < 500 ? "Normalised" : "Normalisation era";
  const step = hi - lo > 12 ? 4 : 2;
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
    el("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: "grid" }, svg);
    el("text", { x: L - 6, y: y(t) + 4, "text-anchor": "end" }, svg).textContent = minus(t);
  }
  for (let t = 1980; t <= 2020; t += W < 500 ? 20 : 10) {
    el("text", { x: x(t), y: H - 8, "text-anchor": "middle" }, svg).textContent = t;
  }
  const band = s.year.map((yr, i) => `${x(yr)},${y(s.p90[i])}`)
    .concat(s.year.map((yr, i) => `${x(yr)},${y(s.p10[i])}`).reverse());
  el("polygon", { points: band.join(" "), class: "band" }, svg);
  el("polyline", { points: s.year.map((yr, i) => `${x(yr)},${y(s.median[i])}`).join(" "), class: "line" }, svg);
  el("circle", { cx: x(a.year), cy: y(a[m]), r: 7, class: "dot" }, svg);
  const lab = el("text", { x: x(a.year) + (a.year > 2010 ? -12 : 12), y: y(a[m]) - 10,
    "text-anchor": a.year > 2010 ? "end" : "start", class: "needle-label" }, svg);
  lab.textContent = a.title.length > 40 ? `${a.title.slice(0, 38)}…` : a.title;
}

// ---------- wiring ----------
document.querySelectorAll("[data-scope]").forEach((b) => b.addEventListener("click", () => {
  if (b.disabled) return;
  state.scope = b.dataset.scope;
  draw();
}));
document.querySelectorAll("[data-metric]").forEach((b) => b.addEventListener("click", () => {
  state.metric = b.dataset.metric;
  draw();
}));

$("search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) { $("status").textContent = "Type an album title or an artist's name."; return; }
  $("status").textContent = "Searching…";
  $("results").replaceChildren();
  try {
    renderResults(await search(q), q);
  } catch (err) {
    $("status").textContent = `Search failed: ${err.message}`;
  }
});

async function fromHash() {
  const id = location.hash.slice(1);
  if (!/^[0-9a-f-]{36}$/.test(id)) return;
  const r = await rows(`select ${COLS} from albums where mbid = ?`, [id]);
  if (r.length) select(r[0], false);
  else $("status").textContent = "That album isn't in the catalogue.";
}
window.addEventListener("hashchange", fromHash);
let resizeFrame = 0;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => { if (state.album) draw(); });
});

init().then(async () => {
  $("q").disabled = false;
  document.querySelector("#search button").disabled = false;
  $("status").textContent = "";
  $("q").focus();
  await fromHash();
}).catch((err) => {
  $("status").textContent = `The catalogue didn't load (${err.message}). Reload the page to try again.`;
});
