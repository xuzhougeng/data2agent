// Hosted-target data API: same named functions as api.static.js, forwarded to the portal's /api/* (see api-contract.json).
const P = window.PORTAL;
const M = P.manifest;
const BASE = ((M.deploy && M.deploy.api_base_url) || "api").replace(/\/$/, "");

async function get(path, params = {}) {
  const u = new URL(BASE + path, document.baseURI);
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    u.searchParams.set(k, typeof v === "object" ? JSON.stringify(v) : String(v));
  }
  const r = await fetch(u);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `${r.status} ${r.statusText}`);
  return r.json();
}
async function post(path, body) {
  const r = await fetch(new URL(BASE + path, document.baseURI), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `${r.status} ${r.statusText}`);
  return r.json();
}

const api = {
  ready: async () => {},
  manifest: M,
  obs: {
    count: (filters) => get("/obs/count", { filters }),
    list: ({ filters, limit = 50, offset = 0, order } = {}) => get("/obs", { filters, limit, offset, order }),
    facets: (filters, cols) => get("/obs/facets", { filters, cols: cols.join(",") }),
    get: (id) => get(`/obs/${encodeURIComponent(id)}`),
  },
  features: {
    search: (text, limit = 20, table) => get("/features/search", { q: text, limit, table }),
    get: (id, table) => get(`/features/${encodeURIComponent(id)}`, { table }),
    where: (table, col, value, limit = 20) => get("/features/where", { table, col, value, limit }),
  },
  matrix: {
    feature: (featureId, { withGroup = true, matrix } = {}) => get(`/matrix/feature/${encodeURIComponent(featureId)}`, { group: withGroup ? 1 : 0, matrix }),
  },
  figure: {
    rows: (panelId, limit = 50000) => get(`/figure/${encodeURIComponent(panelId)}`, { limit }),
  },
  embedding: {
    points: (name, colorCol) => get(`/embedding/${encodeURIComponent(name)}`, { color: colorCol }),
  },
  agg: {
    featureGroup: (featureId, name) => get(`/agg/feature_group/${encodeURIComponent(featureId)}`, { name }),
  },
  results: {
    def(name) { return (M.results || []).find((r) => r.name === name); },
    count: (name, filters) => get(`/results/${encodeURIComponent(name)}/count`, { filters }),
    list: (name, { filters, limit = 50, offset = 0, order } = {}) => get(`/results/${encodeURIComponent(name)}`, { filters, limit, offset, order }),
    facets: (name, filters, cols) => get(`/results/${encodeURIComponent(name)}/facets`, { filters, cols: cols.join(",") }),
    all: (name, filters, limit = 20000) => get(`/results/${encodeURIComponent(name)}/all`, { filters, limit }),
    forFeature: (featureId, table) => get(`/feature_results/${encodeURIComponent(featureId)}`, { table }),
  },
  sql: (query, limit = 1000) => post("/sql", { query, limit }),
};

window.API = api;
export default api;
