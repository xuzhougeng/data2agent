// Static-target data API: DuckDB-WASM in the browser over the package's Parquet files.
// Implements the same named functions as api.http.js (see api-contract.json).
import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";

const P = window.PORTAL;
const M = P.manifest;
const BASE = (M.deploy && M.deploy.data_base_url) || "data/";
const BUFFER_MAX = 32 * 1024 * 1024; // ponytail: files under this are fetched whole; larger ones are range-read over HTTP

let db, conn, initPromise;
const registered = new Set();
const views = new Set();

function urlFor(rel) {
  const tail = rel.startsWith("data/") ? rel.slice(5) : rel;
  return new URL(BASE + tail, document.baseURI).href;
}
function vname(rel) { return rel.replace(/[^A-Za-z0-9_.]/g, "_"); }

async function init() {
  if (!initPromise) {
    initPromise = (async () => {
      const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
      const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
      db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
      await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
      conn = await db.connect();
      if (P.duckdb_ext_local) {
        // extensions vendored into the package: no runtime dependency on extensions.duckdb.org
        const repo = new URL("assets/duckdb-ext", document.baseURI).href;
        try { await conn.query(`SET custom_extension_repository = '${repo}'`); } catch (e) { console.warn("custom_extension_repository failed", e); }
      }
    })();
  }
  return initPromise;
}

async function register(rel) {
  if (registered.has(rel)) return vname(rel);
  await init();
  const bytes = (M.files[rel] || {}).bytes || 0;
  const name = vname(rel);
  if (bytes && bytes <= BUFFER_MAX) {
    const res = await fetch(urlFor(rel));
    if (!res.ok) throw new Error(`fetch ${rel}: ${res.status}`);
    await db.registerFileBuffer(name, new Uint8Array(await res.arrayBuffer()));
  } else {
    await db.registerFileURL(name, urlFor(rel), duckdb.DuckDBDataProtocol.HTTP, false);
  }
  registered.add(rel);
  return name;
}

function sourceFor(entry) {
  if (entry.shards) return Promise.all(entry.shards.map((s) => register(s.path))).then((names) => `read_parquet([${names.map((n) => `'${n}'`).join(",")}])`);
  return register(entry.path).then((n) => `read_parquet('${n}')`);
}

const VIEW_DEFS = {};
for (const [k, t] of Object.entries(M.tables)) VIEW_DEFS[k] = t;
(M.matrices || []).forEach((x, i) => { VIEW_DEFS[i === 0 ? "matrix" : `matrix_${x.name}`] = x; });
(M.embeddings || []).forEach((e) => { VIEW_DEFS[`emb_${e.name}`] = e; });
(M.results || []).forEach((r) => { VIEW_DEFS[`res_${r.name}`] = r; });
(M.aggregates || []).forEach((g) => { VIEW_DEFS[`agg_${g.name}`] = g; });
(M.figures || []).forEach((f) => f.panels.forEach((p) => { VIEW_DEFS[`fig_${p.id}`] = p; }));
const matrixView = (name) => { const i = (M.matrices || []).findIndex((x) => x.name === name); return i <= 0 ? "matrix" : `matrix_${name}`; };

async function ensure(...names) {
  await init();
  for (const n of names) {
    if (views.has(n)) continue;
    const def = VIEW_DEFS[n];
    if (!def) throw new Error(`unknown table ${n}`);
    const src = await sourceFor(def);
    await conn.query(`create or replace view "${n}" as select * from ${src}`);
    views.add(n);
  }
}

function fix(v) {
  if (typeof v === "bigint") return Number(v);
  if (v && typeof v === "object" && typeof v.toString === "function" && !(v instanceof Date)) return Number.isNaN(Number(v)) ? v.toString() : Number(v);
  return v;
}
async function rows(sql) {
  const res = await conn.query(sql);
  const cols = res.schema.fields.map((f) => f.name);
  const out = [];
  for (const batch of res.batches) {
    for (let i = 0; i < batch.numRows; i++) {
      const row = {};
      for (let c = 0; c < cols.length; c++) row[cols[c]] = fix(batch.getChildAt(c).get(i));
      out.push(row);
    }
  }
  return { columns: cols, rows: out };
}

const esc = (s) => String(s).replace(/'/g, "''");
const q = (name) => `"${String(name).replace(/"/g, '""')}"`;

function where(filters = {}, idCol = "obs_id", textCols = [idCol]) {
  const parts = [];
  for (const [col, vals] of Object.entries(filters)) {
    if (col === "q") {
      if (vals) parts.push("(" + textCols.map((c) => `cast(${q(c)} as varchar) ilike '%${esc(vals)}%'`).join(" or ") + ")");
    } else if (Array.isArray(vals) && vals.length) {
      parts.push(`cast(${q(col)} as varchar) in (${vals.map((v) => `'${esc(v)}'`).join(",")})`);
    } else if (vals && typeof vals === "object" && (vals.min != null || vals.max != null)) {
      if (vals.min != null) parts.push(`${q(col)} >= ${Number(vals.min)}`);
      if (vals.max != null) parts.push(`${q(col)} <= ${Number(vals.max)}`);
    }
  }
  return parts.length ? "where " + parts.join(" and ") : "";
}

function orderBy(o) {
  if (!o || !o.col) return "";
  return `order by ${q(o.col)} ${o.desc ? "desc" : "asc"} nulls last`;
}

const api = {
  ready: init,
  manifest: M,

  obs: {
    async count(filters) {
      await ensure("obs");
      return (await rows(`select count(*) n from obs ${where(filters)}`)).rows[0].n;
    },
    async list({ filters, limit = 50, offset = 0, order } = {}) {
      await ensure("obs");
      return rows(`select * from obs ${where(filters)} ${orderBy(order)} limit ${+limit} offset ${+offset}`);
    },
    async facets(filters, cols) {
      await ensure("obs");
      const out = {};
      for (const c of cols) {
        const f = { ...filters }; delete f[c]; // counts for a facet ignore its own selection
        out[c] = (await rows(`select cast(${q(c)} as varchar) as "value", count(*) as n from obs ${where(f)} group by 1 order by n desc, 1 limit 60`)).rows;
      }
      return out;
    },
    async get(id) {
      await ensure("obs");
      return (await rows(`select * from obs where ${q(M.tables.obs.id)} = '${esc(id)}' limit 1`)).rows[0] || null;
    },
  },

  // table = feature table name (a modality); default 'features'
  features: {
    async search(text, limit = 20, table = "features") {
      await ensure(table);
      const cols = M.tables[table].columns.filter((c) => c.search).map((c) => c.name);
      if (!cols.length) cols.push(M.tables[table].id);
      const t = esc(text.trim());
      if (!t) return { columns: [], rows: [] };
      const score = cols.map((c) => `case when lower(cast(${q(c)} as varchar)) = lower('${t}') then 0 when cast(${q(c)} as varchar) ilike '${t}%' then 1 else 2 end`).join(" + ");
      const cond = cols.map((c) => `cast(${q(c)} as varchar) ilike '%${t}%'`).join(" or ");
      return rows(`select *, (${score}) _score from ${q(table)} where ${cond} order by _score, length(cast(${q(cols[0])} as varchar)), ${q(cols[0])} limit ${+limit}`);
    },
    async get(id, table = "features") {
      await ensure(table);
      const cols = M.tables[table].columns.filter((c) => c.search).map((c) => c.name);
      const cond = [M.tables[table].id, ...cols].map((c) => `lower(cast(${q(c)} as varchar)) = lower('${esc(id)}')`).join(" or ");
      return (await rows(`select * from ${q(table)} where ${cond} limit 1`)).rows[0] || null;
    },
    async where(table, col, value, limit = 20) {
      await ensure(table);
      return rows(`select * from ${q(table)} where lower(cast(${q(col)} as varchar)) = lower('${esc(value)}') limit ${+limit}`);
    },
  },

  matrix: {
    async feature(featureId, { withGroup = true, matrix } = {}) {
      const v = matrix ? matrixView(matrix) : "matrix";
      await ensure(v, "obs");
      const g = withGroup && P.primary_group ? `, cast(o.${q(P.primary_group)} as varchar) "group"` : "";
      return rows(`select m.obs_id, m."value" as "value"${g} from ${q(v)} m ${g ? `join obs o on o.${q(M.tables.obs.id)} = m.obs_id` : ""} where m.feature_id = '${esc(featureId)}'`);
    },
  },

  figure: {
    async rows(panelId, limit = 50000) {
      await ensure(`fig_${panelId}`);
      return rows(`select * from ${q("fig_" + panelId)} limit ${+limit}`);
    },
  },

  embedding: {
    async points(name, colorCol) {
      await ensure(`emb_${name}`, "obs");
      const c = colorCol ? `, o.${q(colorCol)} as color` : "";
      return rows(`select e.obs_id, e.x, e.y${c} from ${q("emb_" + name)} e join obs o on o.${q(M.tables.obs.id)} = e.obs_id`);
    },
  },

  agg: {
    async featureGroup(featureId, name = "feature_group") {
      const g = (M.aggregates || []).find((a) => a.name === name);
      if (!g) return { columns: [], rows: [] };
      await ensure(`agg_${name}`);
      return rows(`select "group", n, mean, pct from ${q("agg_" + name)} where feature_id = '${esc(featureId)}' order by mean desc`);
    },
  },

  results: {
    def(name) { return (M.results || []).find((r) => r.name === name); },
    async count(name, filters) {
      await ensure(`res_${name}`);
      const d = api.results.def(name);
      return (await rows(`select count(*) n from ${q("res_" + name)} ${where(filters, d.feature_col, [d.feature_col].filter(Boolean))}`)).rows[0].n;
    },
    async list(name, { filters, limit = 50, offset = 0, order } = {}) {
      await ensure(`res_${name}`);
      const d = api.results.def(name);
      return rows(`select * from ${q("res_" + name)} ${where(filters, d.feature_col, [d.feature_col].filter(Boolean))} ${orderBy(order)} limit ${+limit} offset ${+offset}`);
    },
    async facets(name, filters, cols) {
      await ensure(`res_${name}`);
      const d = api.results.def(name);
      const out = {};
      for (const c of cols) {
        const f = { ...filters }; delete f[c];
        out[c] = (await rows(`select cast(${q(c)} as varchar) as "value", count(*) as n from ${q("res_" + name)} ${where(f, d.feature_col, [d.feature_col].filter(Boolean))} group by 1 order by n desc, 1 limit 60`)).rows;
      }
      return out;
    },
    async all(name, filters, limit = 20000) {
      await ensure(`res_${name}`);
      const d = api.results.def(name);
      return rows(`select * from ${q("res_" + name)} ${where(filters, d.feature_col, [d.feature_col].filter(Boolean))} limit ${+limit}`);
    },
    async forFeature(featureId, table = "features") {
      const out = [];
      for (const r of M.results || []) {
        if (!r.feature_col || (r.features || "features") !== table) continue;
        await ensure(`res_${r.name}`);
        const res = await rows(`select * from ${q("res_" + r.name)} where ${q(r.feature_col)} = '${esc(featureId)}' limit 200`);
        res.rows.forEach((row) => out.push({ _table: r.label, ...row }));
      }
      return out;
    },
  },

  async sql(query, limit = 1000) {
    await init();
    const s = String(query).trim().replace(/;+\s*$/, "");
    if (!/^(select|with|describe|show|explain|pragma|summarize)\b/i.test(s)) throw new Error("Only read-only SELECT/WITH queries are allowed.");
    if (/;/.test(s)) throw new Error("One statement at a time.");
    // register every table the query might reference (cheap: names only; files load lazily per view)
    const names = Object.keys(VIEW_DEFS).filter((n) => new RegExp(`\\b${n}\\b`, "i").test(s));
    await ensure(...names);
    return rows(/^(describe|show|explain|pragma|summarize)/i.test(s) ? s : `select * from (${s}) limit ${+limit}`);
  },
};

window.API = api;
export default api;
