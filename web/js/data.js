// Chargement des données produites par Python (web/data/) + petits utilitaires d'affichage.
// Le front n'effectue AUCUN calcul de risque : il lit risk_report.json et risk_grid.json.

const FILES = {
  graph: "data/graph.json",
  report: "data/risk_report.json",
  grid: "data/risk_grid.json",
  view: "data/view.json",
};

export async function loadAll() {
  const out = {};
  const missing = [];
  await Promise.all(Object.entries(FILES).map(async ([k, url]) => {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      out[k] = await r.json();
    } catch (e) {
      missing.push(url);
    }
  }));
  if (missing.length) {
    const err = new Error("missing");
    err.missing = missing;
    throw err;
  }
  out.nodeById = Object.fromEntries(out.graph.nodes.map(n => [n.id, n]));
  out.nodeById[out.graph.position.id] = { id: out.graph.position.id, type: "position", label: "Position", meta: {}, address: null };
  out.edgesOut = {};
  out.edgesIn = {};
  for (const e of out.graph.edges) {
    (out.edgesOut[e.from] ||= []).push(e);
    (out.edgesIn[e.to] ||= []).push(e);
  }
  out.paramByName = Object.fromEntries(out.report.params.map(p => [p.name, p]));
  return out;
}

export const edgeKey = e => `${e.from}|${e.type}|${e.to}`;

// Ancêtres d'un nœud = tout ce qui en DÉPEND (on remonte les flèches à l'envers).
export function ancestors(data, id) {
  const seen = new Set();
  const stack = [id];
  while (stack.length) {
    const cur = stack.pop();
    for (const e of data.edgesIn[cur] || []) {
      if (e.type === "settled_on" && cur !== id) continue;
      if (!seen.has(e.from)) { seen.add(e.from); stack.push(e.from); }
    }
  }
  return seen;
}

// Plus court chemin position → nœud (BFS sur les flèches, sans settled_on), renvoie la liste d'arêtes.
export function pathFromPosition(data, target) {
  const root = data.graph.position.id;
  const prev = new Map([[root, null]]);
  const q = [root];
  while (q.length) {
    const cur = q.shift();
    if (cur === target) break;
    for (const e of data.edgesOut[cur] || []) {
      if (e.type === "settled_on" && e.to !== target) continue;
      if (!prev.has(e.to)) { prev.set(e.to, e); q.push(e.to); }
    }
  }
  if (!prev.has(target)) return [];
  const edges = [];
  for (let e = prev.get(target); e; e = prev.get(e.from)) edges.unshift(e);
  return edges;
}

const NF = {};
const nf = d => (NF[d] ||= new Intl.NumberFormat("fr-FR", { maximumFractionDigits: d }));
export const usd = x => (x === null || x === undefined) ? "—" : `${nf(0).format(x)} $`;
export const num = (x, d = 2) => (x === null || x === undefined) ? "—" : nf(d).format(x);
export const pct = (x, d = 1) => (x === null || x === undefined) ? "—" : `${(x * 100).toFixed(d).replace(".", ",")} %`;
// Petite probabilité sur l'horizon → fréquence parlante (même formule que src/risk/fmt.py::every) :
// p sur h jours ≈ un événement qui arrive une fois tous les h / −ln(1 − p) jours. Rien au-delà de 20 %.
export function every(p, days) {
  if (p === null || p === undefined || !(p > 0 && p < 0.2) || !(days > 0)) return "";
  const d = days / -Math.log1p(-p);
  if (d < 21) return `≈ une fois tous les ${Math.round(d)} jours`;
  if (d < 90) return `≈ une fois toutes les ${Math.round(d / 7)} semaines`;
  if (d < 730) return `≈ une fois tous les ${Math.round(d / 30.44)} mois`;
  return `≈ une fois tous les ${nf(0).format(d / 365.25)} ans`;
}
export const prob = (x, d, days) => { const f = every(x, days); return pct(x, d) + (f ? ` (${f})` : ""); };
// Horizon de décision du rapport (jours), pour traduire les probabilités en fréquences.
export const horizonOf = data => data.report.monte_carlo.horizon_days;
export const hours = h => (h === null || h === undefined) ? "durable" : (h < 1 ? `${Math.round(h * 60)} min` : `${num(h, 2)} h`);

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Transforme les URL d'une preuve en liens cliquables (le reste est échappé).
export function linkify(text) {
  return esc(text).replace(/https?:\/\/[^\s)]+/g, m => {
    const clean = m.replace(/[.,;]+$/, "");
    return `<a href="${clean}" target="_blank" rel="noopener noreferrer">${clean}</a>${m.slice(clean.length)}`;
  });
}

export function short(id, n = 22) {
  return id.length > n ? id.slice(0, n - 1) + "…" : id;
}
