// Page controllers. Each page talks to `api` (api.js: static or http implementation) and `charts`.
const V = new URL(import.meta.url).searchParams.get("v") || "";
const api = (await import(`./api.js?v=${V}`)).default;
const charts = await import(`./charts.js?v=${V}`);

const P = window.PORTAL;
const M = P.manifest;
const OBS = M.tables.obs, FEAT = M.tables.features;
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const colLabel = (table, name) => (table.columns.find((c) => c.name === name) || {}).label || name;
const fmt = charts.fmt;

// ---------- shared widgets ----------
function navToggle() {
  const b = $("[data-nav-toggle]"), nav = $(".nav");
  if (b) b.addEventListener("click", () => { const open = nav.classList.toggle("open"); b.setAttribute("aria-expanded", open); });
}

/** Autocomplete on an input: fetches feature matches and calls onPick(row). */
function attachSuggest(input, box, onPick) {
  let items = [], active = -1, timer;
  const render = () => {
    box.innerHTML = items.map((r, i) => `<button role="option" aria-selected="${i === active}" data-i="${i}"><span><b>${esc(r.symbol ?? r[FEAT.id])}</b>${r.symbol && r.symbol !== r[FEAT.id] ? ` <span class="muted small">${esc(r[FEAT.id])}</span>` : ""}</span><span class="muted small">${esc(r.biotype || r.name || "")}</span></button>`).join("");
    box.classList.toggle("open", items.length > 0);
  };
  const pick = (i) => { if (items[i]) { input.value = items[i].symbol ?? items[i][FEAT.id]; box.classList.remove("open"); onPick(items[i]); } };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const t = input.value.trim();
    if (!t) { items = []; render(); return; }
    timer = setTimeout(async () => { items = (await api.features.search(t, 12)).rows; active = -1; render(); }, 120);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); render(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); render(); e.preventDefault(); }
    else if (e.key === "Enter") { e.preventDefault(); if (active >= 0) pick(active); else if (items.length) pick(0); else api.features.get(input.value.trim()).then((r) => r && onPick(r)); }
    else if (e.key === "Escape") { box.classList.remove("open"); }
  });
  box.addEventListener("mousedown", (e) => { const b = e.target.closest("button"); if (b) { e.preventDefault(); pick(+b.dataset.i); } });
  input.addEventListener("blur", () => setTimeout(() => box.classList.remove("open"), 150));
}

/** Table renderer with sortable headers. columns: [{name,label,role,dtype}] */
function renderTable(table, columns, rows, { order, onSort, linkCol, linkHref } = {}) {
  const isNum = (c) => c.dtype === "int" || c.dtype === "float" || c.role === "numeric";
  table.querySelector("thead").innerHTML = `<tr>${columns.map((c) => `<th data-col="${esc(c.name)}" class="${isNum(c) ? "num" : ""} ${order && order.col === c.name ? "sorted" + (order.desc ? " desc" : "") : ""}">${esc(c.label || c.name)}</th>`).join("")}</tr>`;
  table.querySelector("tbody").innerHTML = rows.length
    ? rows.map((r) => `<tr>${columns.map((c) => {
        const v = r[c.name];
        const cell = v == null ? "" : isNum(c) ? fmt(v) : esc(v);
        const body = linkCol === c.name && v != null ? `<a href="${linkHref(v)}">${cell}</a>` : cell;
        return `<td class="${isNum(c) ? "num" : c.role === "id" ? "id" : ""}">${body}</td>`;
      }).join("")}</tr>`).join("")
    : `<tr><td colspan="${columns.length}" class="empty">No rows match.</td></tr>`;
  if (onSort) table.querySelectorAll("th").forEach((th) => th.onclick = () => onSort(th.dataset.col));
}

function toCSV(columns, rows) {
  const cell = (v) => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return [columns.join(","), ...rows.map((r) => columns.map((c) => cell(r[c])).join(","))].join("\n");
}
function download(name, text, type = "text/csv") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Facet sidebar + chips bound to a filter state. */
function facetPanel(listEl, chipsEl, cols, state, onChange) {
  const render = (counts) => {
    listEl.innerHTML = cols.map((c, i) => {
      const vals = counts[c.name] || [];
      return `<details class="facet" ${i < 3 ? "open" : ""}><summary>${esc(c.label)}</summary><ul>${vals.map((v) => `<li><label><input type="checkbox" data-col="${esc(c.name)}" value="${esc(v.value)}" ${(state.filters[c.name] || []).includes(v.value) ? "checked" : ""}><span>${esc(v.value ?? "—")}</span><span class="n">${fmt(v.n)}</span></label></li>`).join("")}</ul></details>`;
    }).join("");
    chipsEl.innerHTML = Object.entries(state.filters).flatMap(([col, vals]) => Array.isArray(vals) ? vals.map((v) => `<span class="chip">${esc(colLabel({ columns: cols }, col))}: ${esc(v)} <button data-col="${esc(col)}" data-v="${esc(v)}" aria-label="remove">×</button></span>`) : []).join("");
  };
  listEl.addEventListener("change", (e) => {
    const cb = e.target; if (cb.type !== "checkbox") return;
    const arr = state.filters[cb.dataset.col] || [];
    state.filters[cb.dataset.col] = cb.checked ? [...arr, cb.value] : arr.filter((v) => v !== cb.value);
    if (!state.filters[cb.dataset.col].length) delete state.filters[cb.dataset.col];
    onChange();
  });
  chipsEl.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.filters[b.dataset.col] = (state.filters[b.dataset.col] || []).filter((v) => v !== b.dataset.v);
    if (!state.filters[b.dataset.col].length) delete state.filters[b.dataset.col];
    onChange();
  });
  return render;
}

const facetCols = (table) => table.columns.filter((c) => c.role === "facet" && c.name !== table.id).sort((a, b) => (b.primary_group ? 1 : 0) - (a.primary_group ? 1 : 0));
const visibleCols = (table) => table.columns.filter((c) => c.role !== "hidden");

// ---------- pages ----------
const pages = {
  async index() {
    const input = $("#home-search");
    if (input) attachSuggest(input, $("#home-suggest"), (r) => location.href = `feature.html?id=${encodeURIComponent(r[FEAT.id])}`);
    const el = $("#home-composition");
    if (el && P.primary_group) {
      const items = (P.facets[P.primary_group] || []).map((f) => ({ label: f.value, value: f.n }));
      const cmap = charts.colorMap(items.map((i) => i.label));
      charts.bar(el, items, { valueLabel: OBS.label.toLowerCase(), colors: cmap });
    }
  },

  async browse() {
    const state = { filters: {}, page: 0, size: 50, order: null };
    const fcols = facetCols(OBS);
    const cols = visibleCols(OBS);
    const table = $("#browse-table"), count = $("#browse-count"), info = $("#browse-page-info");
    const chartSel = $("#browse-chart-col");
    chartSel.innerHTML = fcols.map((c) => `<option value="${esc(c.name)}" ${c.primary_group ? "selected" : ""}>${esc(c.label)}</option>`).join("");
    const renderFacets = facetPanel($("#browse-facet-list"), $("#browse-chips"), fcols, state, () => { state.page = 0; refresh(); });
    let busy = false;
    async function refresh() {
      if (busy) return; busy = true;
      try {
        const [n, data, counts] = await Promise.all([
          api.obs.count(state.filters),
          api.obs.list({ filters: state.filters, limit: state.size, offset: state.page * state.size, order: state.order }),
          api.obs.facets(state.filters, fcols.map((c) => c.name)),
        ]);
        count.textContent = `${fmt(n)} ${OBS.label.toLowerCase()}${Object.keys(state.filters).length ? " match" : ""}`;
        renderTable(table, cols, data.rows, { order: state.order, onSort: (c) => { state.order = state.order && state.order.col === c ? { col: c, desc: !state.order.desc } : { col: c, desc: false }; refresh(); } });
        renderFacets(counts);
        const from = state.page * state.size + 1, to = Math.min(n, (state.page + 1) * state.size);
        info.textContent = n ? `${fmt(from)}–${fmt(to)} of ${fmt(n)}` : "";
        $("#browse-prev").disabled = state.page === 0; $("#browse-next").disabled = to >= n;
        const cc = chartSel.value;
        const items = (counts[cc] || []).map((f) => ({ label: f.value, value: f.n }));
        charts.bar($("#browse-chart"), items, { valueLabel: OBS.label.toLowerCase(), colors: charts.colorMap(items.map((i) => i.label)) });
      } finally { busy = false; }
    }
    $("#browse-prev").onclick = () => { state.page--; refresh(); };
    $("#browse-next").onclick = () => { state.page++; refresh(); };
    chartSel.onchange = refresh;
    $("#browse-clear").onclick = () => { state.filters = {}; $("#browse-q").value = ""; state.page = 0; refresh(); };
    let t; $("#browse-q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { if (e.target.value) state.filters.q = e.target.value; else delete state.filters.q; state.page = 0; refresh(); }, 200); });
    $("#browse-export").onclick = async () => {
      const data = await api.obs.list({ filters: state.filters, limit: 100000, order: state.order });
      download(`${M.id}-${OBS.label.toLowerCase()}.csv`, toCSV(cols.map((c) => c.name), data.rows));
    };
    refresh();
  },

  async embedding() {
    const nameSel = $("#emb-name"), colorSel = $("#emb-color"), legend = $("#emb-legend"), el = $("#emb-chart");
    const legendTitle = $("#emb-legend-title");
    let current = null, featureId = null, chartRef = null;
    async function draw() {
      el.classList.add("loading");
      try {
        const name = nameSel.value;
        if (featureId) {
          const [pts, expr] = await Promise.all([api.embedding.points(name), api.matrix.feature(featureId, { withGroup: false })]);
          const v = new Map(expr.rows.map((r) => [r.obs_id, r.value]));
          const points = pts.rows.map((r) => ({ x: r.x, y: r.y, obs_id: r.obs_id, v: v.get(r.obs_id) || 0 }));
          chartRef = await charts.scatterContinuous(el, points, { label: M.matrices[0].value.label || "value" });
          legendTitle.textContent = featureId;
          legend.innerHTML = `<p class="muted">${fmt(expr.rows.length)} of ${fmt(points.length)} ${OBS.label.toLowerCase()} with a non-zero value. <a href="feature.html?id=${encodeURIComponent(featureId)}">Open ${esc(featureId)} →</a></p><button class="btn small" id="emb-back">Back to annotation</button>`;
          $("#emb-back").onclick = () => { featureId = null; $("#emb-feature").value = ""; draw(); };
        } else {
          const col = colorSel.value;
          const pts = await api.embedding.points(name, col);
          const colDef = OBS.columns.find((c) => c.name === col);
          if (colDef && colDef.role === "numeric") {
            chartRef = await charts.scatterContinuous(el, pts.rows.map((r) => ({ x: r.x, y: r.y, obs_id: r.obs_id, v: +r.color })), { label: colDef.label });
            legendTitle.textContent = colDef.label; legend.innerHTML = "";
          } else {
            const cats = (P.facets[col] || []).map((f) => f.value);
            const res = await charts.scatterCategorical(el, pts.rows.map((r) => ({ x: r.x, y: r.y, obs_id: r.obs_id, color: r.color })), { categories: cats });
            chartRef = res.chart;
            const counts = Object.fromEntries((P.facets[col] || []).map((f) => [f.value, f.n]));
            legendTitle.textContent = colDef ? colDef.label : col;
            legend.innerHTML = `<div class="legend" style="flex-direction:column;gap:4px">${res.categories.map((c) => `<label style="--c:${res.cmap.get(c)};cursor:pointer"><input type="checkbox" checked data-cat="${esc(c)}" class="sr-only"><span class="sw">${esc(c)}</span> <span class="muted">${fmt(counts[c] || 0)}</span></label>`).join("")}</div>`;
            legend.querySelectorAll("input").forEach((cb) => cb.onchange = () => chartRef.dispatchAction({ type: cb.checked ? "legendSelect" : "legendUnSelect", name: cb.dataset.cat }));
          }
        }
      } finally { el.classList.remove("loading"); }
    }
    nameSel.onchange = draw; colorSel.onchange = () => { featureId = null; $("#emb-feature").value = ""; draw(); };
    attachSuggest($("#emb-feature"), $("#emb-suggest"), (r) => { featureId = r[FEAT.id]; draw(); });
    $("#emb-png").onclick = () => chartRef && charts.downloadPNG(chartRef, `${M.id}-${nameSel.value}`);
    const q = new URLSearchParams(location.search);
    if (q.get("feature")) { featureId = q.get("feature"); $("#emb-feature").value = featureId; }
    draw();
  },

  async feature() {
    const input = $("#feat-search"), detail = $("#feat-detail"), empty = $("#feat-empty");
    const ex = P.example_features || [];
    $("#feat-examples").innerHTML = ex.map((f) => `<a href="feature.html?id=${encodeURIComponent(f)}">${esc(f)}</a>`).join(", ") || "searching above";
    const valueLabel = M.matrices.length ? (M.matrices[0].value.label || M.matrices[0].value.kind) : "value";
    async function show(row) {
      const id = row[FEAT.id];
      history.replaceState(null, "", `feature.html?id=${encodeURIComponent(id)}`);
      document.title = `${row.symbol || id} · ${M.short_title || M.title}`;
      empty.hidden = true; detail.hidden = false;
      $("#feat-title").textContent = row.symbol || id;
      $("#feat-badges").innerHTML = (row.symbol && row.symbol !== id ? `<span class="pill mono">${esc(id)}</span>` : "") + (row.biotype ? `<span class="pill">${esc(row.biotype)}</span>` : "");
      $("#feat-kv").innerHTML = visibleCols(FEAT).filter((c) => c.role !== "id" && row[c.name] != null && row[c.name] !== "").map((c) => `<dt>${esc(c.label)}</dt><dd>${c.role === "link" ? `<a href="${esc(row[c.name])}">${esc(row[c.name])}</a>` : typeof row[c.name] === "number" ? fmt(row[c.name]) : esc(row[c.name])}</dd>`).join("");
      $("#feat-value-label").textContent = valueLabel;
      const [expr, agg] = await Promise.all([api.matrix.feature(id), api.agg.featureGroup(id)]);
      const groupCounts = Object.fromEntries((P.facets[P.primary_group] || []).map((f) => [f.value, f.n]));
      const byGroup = new Map();
      for (const r of expr.rows) (byGroup.get(r.group) || byGroup.set(r.group, []).get(r.group)).push(r.value);
      const idsByGroup = new Map();
      for (const r of expr.rows) (idsByGroup.get(r.group) || idsByGroup.set(r.group, []).get(r.group)).push(r.obs_id);
      const groups = Object.keys(groupCounts).map((g) => { const vals = byGroup.get(g) || []; const zeros = Math.max(0, groupCounts[g] - vals.length); return { name: g, values: vals.concat(new Array(zeros).fill(0)), ids: (idsByGroup.get(g) || []).concat(new Array(zeros).fill("(not detected)")) }; });
      const cmap = charts.colorMap(Object.keys(groupCounts));
      if (M.stats.n_obs <= 200) charts.stripByGroup($("#feat-group-chart"), groups, { valueLabel, colors: cmap });
      else charts.boxByGroup($("#feat-group-chart"), groups, { valueLabel, colors: cmap });
      if (agg.rows.length) charts.dotplot($("#feat-dot-chart"), agg.rows, { valueLabel: `mean ${valueLabel}` });
      else $("#feat-dot-chart").innerHTML = `<div class="empty">No per-group aggregate in this package.</div>`;
      const embSel = $("#feat-emb");
      if (embSel) {
        const drawEmb = async () => {
          const pts = await api.embedding.points(embSel.value);
          const v = new Map(expr.rows.map((r) => [r.obs_id, r.value]));
          charts.scatterContinuous($("#feat-emb-chart"), pts.rows.map((r) => ({ x: r.x, y: r.y, obs_id: r.obs_id, v: v.get(r.obs_id) || 0 })), { label: valueLabel });
        };
        embSel.onchange = drawEmb; drawEmb();
      }
      const rt = $("#feat-results");
      if (rt) {
        const hits = await api.results.forFeature(id);
        const labelOf = (k) => { for (const r of M.results) { const c = r.columns.find((x) => x.name === k); if (c) return c.label || k; } return k; };
        const cols = hits.length ? Object.keys(hits[0]).filter((k) => k !== "feature_id").map((k) => ({ name: k, label: k === "_table" ? "Table" : labelOf(k), dtype: typeof hits[0][k] === "number" ? "float" : "string" })) : [{ name: "_table", label: "Table" }];
        renderTable(rt, cols, hits);
      }
    }
    attachSuggest(input, $("#feat-suggest"), show);
    const q = new URLSearchParams(location.search).get("id");
    if (q) { input.value = q; const r = await api.features.get(q); if (r) show(r); else { empty.textContent = `No ${FEAT.label_singular.toLowerCase()} matches “${q}”.`; } }
  },

  async results() {
    const sel = $("#res-name"), table = $("#res-table"), info = $("#res-page-info"), count = $("#res-count"), desc = $("#res-desc");
    const state = { name: sel.value, filters: {}, page: 0, size: 50, order: null };
    let fcols = [], cols = [], renderFacets;
    function setup() {
      const d = api.results.def(state.name);
      desc.textContent = d.description || "";
      fcols = d.columns.filter((c) => c.role === "facet");
      cols = d.columns;
      state.filters = {}; state.page = 0;
      state.order = d.p_col ? { col: d.p_col, desc: false } : d.score_col ? { col: d.score_col, desc: true } : null;
      renderFacets = facetPanel($("#res-facet-list"), $("#res-chips"), fcols, state, () => { state.page = 0; refresh(); });
      $("#res-chart-title").textContent = d.effect_col && d.p_col ? "Volcano" : d.score_col ? `Top by ${colLabel(d, d.score_col)}` : "Overview";
    }
    async function refresh() {
      const d = api.results.def(state.name);
      const [n, data, counts] = await Promise.all([
        api.results.count(state.name, state.filters),
        api.results.list(state.name, { filters: state.filters, limit: state.size, offset: state.page * state.size, order: state.order }),
        api.results.facets(state.name, state.filters, fcols.map((c) => c.name)),
      ]);
      count.textContent = `${fmt(n)} rows`;
      renderTable(table, cols, data.rows, { order: state.order, onSort: (c) => { state.order = state.order && state.order.col === c ? { col: c, desc: !state.order.desc } : { col: c, desc: true }; refresh(); }, linkCol: d.feature_col, linkHref: (v) => `feature.html?id=${encodeURIComponent(v)}` });
      renderFacets(counts);
      const from = state.page * state.size + 1, to = Math.min(n, (state.page + 1) * state.size);
      info.textContent = n ? `${fmt(from)}–${fmt(to)} of ${fmt(n)}` : "";
      $("#res-prev").disabled = state.page === 0; $("#res-next").disabled = to >= n;
      const all = await api.results.all(state.name, state.filters, 20000);
      const el = $("#res-chart");
      if (d.effect_col && d.p_col) charts.volcano(el, all.rows, { effect: d.effect_col, p: d.p_col, label: d.label_col || d.feature_col, effectLabel: colLabel(d, d.effect_col), onClick: (f) => location.href = `feature.html?id=${encodeURIComponent(f)}` });
      else if (d.score_col) {
        const top = [...all.rows].sort((a, b) => b[d.score_col] - a[d.score_col]).slice(0, 25);
        charts.bar(el, top.map((r) => ({ label: `${r[d.feature_col] || ""}${d.group_col ? " · " + r[d.group_col] : ""}`, value: r[d.score_col] })), { horizontal: true, valueLabel: colLabel(d, d.score_col) });
      } else el.innerHTML = `<div class="empty">No numeric column to chart.</div>`;
    }
    sel.onchange = () => { state.name = sel.value; setup(); refresh(); };
    $("#res-prev").onclick = () => { state.page--; refresh(); };
    $("#res-next").onclick = () => { state.page++; refresh(); };
    $("#res-clear").onclick = () => { state.filters = {}; $("#res-q").value = ""; state.page = 0; refresh(); };
    let t; $("#res-q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { if (e.target.value) state.filters.q = e.target.value; else delete state.filters.q; state.page = 0; refresh(); }, 200); });
    $("#res-export").onclick = async () => { const data = await api.results.all(state.name, state.filters, 500000); download(`${M.id}-${state.name}.csv`, toCSV(cols.map((c) => c.name), data.rows)); };
    setup(); refresh();
  },

  async api() {
    const ta = $("#sql-input"), status = $("#sql-status"), table = $("#sql-table"), csv = $("#sql-csv");
    let last = null;
    async function run() {
      status.textContent = "Running…"; csv.disabled = true;
      const t0 = performance.now();
      try {
        last = await api.sql(ta.value);
        const cols = last.columns.map((c) => ({ name: c, label: c, dtype: typeof (last.rows[0] || {})[c] === "number" ? "float" : "string" }));
        renderTable(table, cols, last.rows);
        status.textContent = `${fmt(last.rows.length)} row${last.rows.length === 1 ? "" : "s"}${last.rows.length >= 1000 ? " (capped)" : ""} · ${((performance.now() - t0) / 1000).toFixed(2)} s`;
        csv.disabled = !last.rows.length;
      } catch (e) {
        status.innerHTML = `<span class="badge-bad">${esc(e.message)}</span>`;
        table.querySelector("thead").innerHTML = ""; table.querySelector("tbody").innerHTML = "";
      }
    }
    $("#sql-run").onclick = run;
    ta.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run(); });
    $("#sql-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-sql]"); if (b) { ta.value = b.dataset.sql; run(); } });
    csv.onclick = () => last && download(`${M.id}-query.csv`, toCSV(last.columns, last.rows));
    run();
  },
};

navToggle();
const page = document.body.dataset.page;
if (pages[page]) pages[page]().catch((e) => { console.error(e); const m = document.querySelector("main"); const d = document.createElement("div"); d.className = "callout"; d.innerHTML = `<b>Could not load data.</b> ${esc(e.message)}`; m.prepend(d); });
