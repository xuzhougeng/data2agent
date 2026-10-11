// Chart helpers on top of ECharts (loaded as a global by base.html). One visual system for every page.
export const PALETTE = [
  "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
  "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
];
export const VIRIDIS = ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"];

const dark = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export function ready() {
  return new Promise((resolve) => {
    if (window.echarts) return resolve(window.echarts);
    const t = setInterval(() => { if (window.echarts) { clearInterval(t); resolve(window.echarts); } }, 30);
  });
}

const instances = new WeakMap();
export async function make(el) {
  const echarts = await ready();
  let ch = instances.get(el);
  if (!ch) {
    ch = echarts.init(el, null, { renderer: "canvas" });
    instances.set(el, ch);
    new ResizeObserver(() => ch.resize()).observe(el);
  }
  return ch;
}

export function baseOption(extra = {}) {
  const text = css("--text") || "#222", muted = css("--muted") || "#777", border = css("--border") || "#ddd";
  return {
    textStyle: { fontFamily: css("--font-sans") || "sans-serif", color: text },
    color: PALETTE,
    backgroundColor: "transparent",
    animationDuration: 300,
    grid: { left: 48, right: 20, top: 28, bottom: 40, containLabel: true },
    tooltip: { trigger: "item", backgroundColor: dark() ? "#1f242c" : "#fff", borderColor: border, textStyle: { color: text, fontSize: 12 } },
    xAxis: { axisLine: { lineStyle: { color: border } }, axisLabel: { color: muted }, splitLine: { show: false } },
    yAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: muted }, splitLine: { lineStyle: { color: border, type: "dashed" } } },
    ...extra,
  };
}

export function colorMap(categories) {
  const m = new Map();
  categories.forEach((c, i) => m.set(String(c), PALETTE[i % PALETTE.length]));
  return m;
}

/** Scatter of points [{x,y,color}] where color is a category label. One series per category so legend toggles work. */
export async function scatterCategorical(el, points, { categories, title, square = false, symbolSize, onLegend } = {}) {
  const ch = await make(el);
  const cats = categories || [...new Set(points.map((p) => String(p.color)))].sort();
  const cmap = colorMap(cats);
  const by = new Map(cats.map((c) => [c, []]));
  for (const p of points) (by.get(String(p.color)) || by.set(String(p.color), []).get(String(p.color))).push([p.x, p.y, p.obs_id]);
  const n = points.length;
  const size = symbolSize || (n > 100000 ? 2 : n > 30000 ? 3 : n > 5000 ? 4 : 6);
  const opt = baseOption({
    title: title ? { text: title, left: "center", textStyle: { fontSize: 13, fontWeight: 500 } } : undefined,
    legend: { show: false },
    tooltip: { trigger: "item", formatter: (p) => `${p.seriesName}<br><span class="mono">${p.data[2]}</span>` },
    xAxis: { type: "value", scale: true, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    grid: { left: 10, right: 10, top: title ? 36 : 10, bottom: 10 },
    toolbox: { show: false },
    series: [...by.entries()].map(([name, data]) => ({
      name, type: "scatter", data, symbolSize: size, large: data.length > 5000, largeThreshold: 5000,
      itemStyle: { color: cmap.get(name), opacity: 0.85 }, emphasis: { focus: "series" },
    })),
  });
  ch.setOption(opt, true);
  if (onLegend) ch.on("legendselectchanged", onLegend);
  return { chart: ch, categories: cats, cmap };
}

/** Scatter colored by a continuous value [{x,y,v}]. Zeros drawn first in light gray so expressing cells sit on top. */
export async function scatterContinuous(el, points, { title, label = "value", square = false } = {}) {
  const ch = await make(el);
  const zeros = [], nz = [];
  let max = 0;
  for (const p of points) { if (p.v > 0) { nz.push([p.x, p.y, p.v, p.obs_id]); if (p.v > max) max = p.v; } else zeros.push([p.x, p.y, 0, p.obs_id]); }
  nz.sort((a, b) => a[2] - b[2]);
  const n = points.length;
  const size = n > 100000 ? 2 : n > 30000 ? 3 : n > 5000 ? 4 : 6;
  ch.setOption(baseOption({
    title: title ? { text: title, left: "center", textStyle: { fontSize: 13, fontWeight: 500 } } : undefined,
    tooltip: { formatter: (p) => `<span class="mono">${p.data[3]}</span><br>${label}: ${(+p.data[2]).toFixed(3)}` },
    visualMap: { min: 0, max: max || 1, dimension: 2, right: 8, top: "middle", calculable: false, precision: 1, text: [max.toFixed(1), "0"], textStyle: { color: css("--muted") }, inRange: { color: VIRIDIS }, seriesIndex: 1 },
    xAxis: { type: "value", scale: true, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { show: false }, splitLine: { show: false } },
    grid: { left: 10, right: 70, top: title ? 36 : 10, bottom: 10 },
    series: [
      { name: "not detected", type: "scatter", data: zeros, symbolSize: size, large: true, itemStyle: { color: dark() ? "#2f3741" : "#e5e7eb" } },
      { name: label, type: "scatter", data: nz, symbolSize: size, large: nz.length > 5000 },
    ],
  }), true);
  return ch;
}

/** Bar chart of [{label, value}] (horizontal when many categories). */
export async function bar(el, items, { horizontal, color, valueLabel = "n", colors, sort = false } = {}) {
  const ch = await make(el);
  const data = sort ? [...items].sort((a, b) => b.value - a.value) : items;
  const h = horizontal ?? data.length > 6;
  const cat = { type: "category", data: data.map((d) => d.label), axisLabel: { interval: 0, rotate: h ? 0 : (data.length > 8 ? 30 : 0), width: h ? 170 : undefined, overflow: "truncate", fontSize: 11 }, inverse: h };
  const val = { type: "value", name: valueLabel, nameLocation: "middle", nameGap: h ? 24 : 40, nameTextStyle: { color: css("--muted") } };
  ch.setOption(baseOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (ps) => `${ps[0].name}<br>${valueLabel}: <b>${fmt(ps[0].value)}</b>` },
    grid: { left: h ? 8 : 48, right: 24, top: 16, bottom: h ? 30 : 56, containLabel: true },
    xAxis: h ? { ...baseOption().xAxis, ...val } : { ...baseOption().xAxis, ...cat },
    yAxis: h ? { ...baseOption().yAxis, ...cat } : { ...baseOption().yAxis, ...val },
    series: [{ type: "bar", data: data.map((d, i) => ({ value: d.value, itemStyle: { color: (colors && colors.get(String(d.label))) || color || PALETTE[0], borderRadius: 3 } })), barMaxWidth: 28 }],
  }), true);
  return ch;
}

function quantiles(arr) {
  const a = Float64Array.from(arr).sort();
  const q = (p) => { const i = (a.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return a[lo] + (a[hi] - a[lo]) * (i - lo); };
  return a.length ? [a[0], q(0.25), q(0.5), q(0.75), a[a.length - 1]] : [0, 0, 0, 0, 0];
}

/** Box plot per group from [{name, values:Float32Array|number[]}]. */
export async function boxByGroup(el, groups, { valueLabel = "value", colors } = {}) {
  const ch = await make(el);
  const names = groups.map((g) => g.name);
  ch.setOption(baseOption({
    tooltip: { trigger: "item", formatter: (p) => p.seriesType === "boxplot" ? `${p.name}<br>median ${fmt(p.data[3])} · IQR ${fmt(p.data[2])}–${fmt(p.data[4])}<br>n = ${groups[p.dataIndex].values.length}` : "" },
    grid: { left: 12, right: 20, top: 16, bottom: 12, containLabel: true },
    xAxis: { ...baseOption().xAxis, type: "category", data: names, axisLabel: { interval: 0, rotate: names.length > 6 ? 30 : 0, color: css("--muted") } },
    yAxis: { ...baseOption().yAxis, type: "value" },
    series: [{ type: "boxplot", data: groups.map((g, i) => ({ value: quantiles(g.values), itemStyle: { color: (colors && colors.get(String(g.name))) || PALETTE[i % PALETTE.length], borderColor: css("--text-2") } })), boxWidth: ["30%", "60%"] }],
  }), true);
  return ch;
}

/** Dot plot for one feature: [{group, mean, pct, n}] → bubble size = fraction expressing, color = mean. */
export async function dotplot(el, rows, { valueLabel = "mean" } = {}) {
  const ch = await make(el);
  const data = [...rows].sort((a, b) => a.mean - b.mean);
  const max = Math.max(...data.map((d) => d.mean), 1e-9);
  ch.setOption(baseOption({
    tooltip: { formatter: (p) => `${p.name}<br>${valueLabel}: <b>${fmt(p.value[0])}</b><br>expressing: <b>${(p.data.pct * 100).toFixed(1)}%</b> of ${p.data.n}` },
    grid: { left: 8, right: 80, top: 20, bottom: 36, containLabel: true },
    xAxis: { ...baseOption().xAxis, type: "value", name: valueLabel, nameLocation: "middle", nameGap: 26, nameTextStyle: { color: css("--muted") }, min: 0 },
    yAxis: { ...baseOption().yAxis, type: "category", data: data.map((d) => d.group), axisLabel: { width: 180, overflow: "truncate", color: css("--text-2") } },
    visualMap: { min: 0, max, dimension: 0, right: 8, top: "middle", calculable: false, text: [fmt(max), "0"], textStyle: { color: css("--muted"), fontSize: 10 }, inRange: { color: VIRIDIS }, itemHeight: 90 },
    series: [{ type: "scatter", data: data.map((d) => ({ name: d.group, value: [d.mean, d.group], pct: d.pct, n: d.n, symbolSize: 6 + 30 * Math.sqrt(d.pct) })), itemStyle: { borderColor: css("--border-strong"), borderWidth: 1 } }],
  }), true);
  return ch;
}

/** Volcano: rows with effect, p, label; highlight by thresholds. */
export async function volcano(el, rows, { effect, p, label, effectLabel = "log2 fold change", pThr = 0.05, fcThr = 1, onClick } = {}) {
  const ch = await make(el);
  const pts = rows.map((r) => {
    const e = +r[effect], pv = Math.max(+r[p] || 1e-300, 1e-300), y = -Math.log10(pv);
    const sig = pv < pThr && Math.abs(e) >= fcThr;
    return { value: [e, y], name: r[label], itemStyle: { color: sig ? (e > 0 ? "#e15759" : "#4e79a7") : (dark() ? "#4b5563" : "#c7cdd4"), opacity: sig ? 0.9 : 0.6 } };
  });
  ch.setOption(baseOption({
    tooltip: { formatter: (q) => `<b>${q.name}</b><br>${effectLabel}: ${fmt(q.value[0])}<br>-log10 p: ${fmt(q.value[1])}` },
    grid: { left: 48, right: 20, top: 20, bottom: 44, containLabel: true },
    xAxis: { ...baseOption().xAxis, type: "value", name: effectLabel, nameLocation: "middle", nameGap: 26, nameTextStyle: { color: css("--muted") } },
    yAxis: { ...baseOption().yAxis, type: "value", name: "-log10 p", nameTextStyle: { color: css("--muted") } },
    series: [{ type: "scatter", data: pts, symbolSize: 5, large: pts.length > 5000, markLine: { silent: true, symbol: "none", lineStyle: { type: "dashed", color: css("--muted") }, data: [{ xAxis: -fcThr }, { xAxis: fcThr }, { yAxis: -Math.log10(pThr) }] } }],
  }), true);
  if (onClick) ch.on("click", (q) => onClick(q.name));
  return ch;
}

export function downloadPNG(chart, name = "chart") {
  const a = document.createElement("a");
  a.href = chart.getDataURL({ pixelRatio: 2, backgroundColor: dark() ? "#171b21" : "#fff" });
  a.download = `${name}.png`;
  a.click();
}

export function fmt(v) {
  if (v == null || Number.isNaN(v)) return "";
  if (Number.isInteger(v)) return v.toLocaleString();
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return v.toExponential(2);
  return (+v).toFixed(a < 1 ? 3 : 2);
}
