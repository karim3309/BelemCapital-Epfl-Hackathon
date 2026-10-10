// Le « squelette » : graph.json dessiné en couches horizontales (comme des vertèbres), en SVG natif.
// La profondeur de dépendance se lit de haut (la position) en bas (Ethereum).
// Style des arêtes = type de PREUVE : on-chain (trait plein lumineux), API (pointillés), curée (ambre fin).

import { edgeKey, short } from "./data.js";

const NS = "http://www.w3.org/2000/svg";
const GLYPH = {
  position: "◎", lending_market: "⛁", vault: "▣", oracle: "⌖", asset: "◈",
  liquidity_venue: "≋", issuer: "◉", offchain_counterparty: "⌂", chain: "⛓",
};
const MODE_FR = { fixed: "prix fixe", market: "prix de marché", internal_rate: "taux interne", hybrid: "hybride (arbitre)", unknown: "inconnu" };
const MODE_COLOR = {
  fixed: "var(--mode-fixed)", market: "var(--mode-market)", internal_rate: "var(--mode-internal)",
  hybrid: "var(--mode-hybrid)", unknown: "var(--mode-unknown)",
};

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function subLabel(node, data) {
  const m = node.meta || {};
  if (node.type === "position") return `valeur ${Math.round(data.graph.position.value_usd).toLocaleString("fr-FR")} $`;
  if (node.type === "lending_market") return `HF ${(m.position?.health_factor ?? 0).toFixed(3).replace(".", ",")} · LLTV ${(m.lltv * 100).toFixed(1).replace(".", ",")}%`;
  if (node.type === "oracle") return MODE_FR[m.pricing_mode] || "?";
  if (node.type === "asset") return m.price_usd != null ? `${m.price_usd.toFixed(4).replace(".", ",")} $` : (m.asset_kind || "");
  if (node.type === "liquidity_venue") return m.tvl_usd != null ? `TVL ${(m.tvl_usd / 1e6).toFixed(2).replace(".", ",")} M$` : "pool";
  if (node.type === "vault") return m.tvl_usd != null ? `TVL ${(m.tvl_usd / 1e6).toFixed(1).replace(".", ",")} M$` : "vault";
  if (node.type === "offchain_counterparty") return (m.role || "").includes("custodian") ? "custodian" : "exchange (hedges)";
  if (node.type === "issuer") return "émetteur";
  if (node.type === "chain") return `bloc #${m.snapshot_block}`;
  return node.type;
}

export class Skeleton {
  constructor(svg, wrap, data, onNodeClick) {
    this.svg = svg;
    this.wrap = wrap;
    this.data = data;
    this.onNodeClick = onNodeClick;
    this.nodeEls = new Map();
    this.edgeEls = new Map();
    this.revealEls = [];
  }

  layout() {
    const W = Math.max(this.wrap.clientWidth, 320);
    const narrow = W < 700;
    const nodeW = narrow ? 156 : Math.min(190, Math.max(156, W / 6.5));
    const nodeH = narrow ? 40 : 44;
    const gapX = narrow ? 10 : 18;
    const marginX = narrow ? 12 : 24;
    const perRow = Math.max(1, Math.floor((W - 2 * marginX + gapX) / (nodeW + gapX)));
    const layers = this.data.view.layers;
    const byLayer = new Map();
    for (const [id, l] of Object.entries(layers)) {
      if (!this.data.nodeById[id]) continue;
      if (!byLayer.has(l)) byLayer.set(l, []);
      byLayer.get(l).push(id);
    }
    const order = { lending_market: 0, vault: 1, asset: 0, liquidity_venue: 2 };
    this.pos = new Map();
    this.bands = [];
    let y = 26;
    for (const l of [...byLayer.keys()].sort((a, b) => a - b)) {
      const ids = byLayer.get(l).sort((a, b) => {
        const na = this.data.nodeById[a], nb = this.data.nodeById[b];
        return ((order[na.type] ?? 1) - (order[nb.type] ?? 1)) || a.localeCompare(b);
      });
      const top = y;
      y += 18;                                            // titre de la couche
      for (let i = 0; i < ids.length; i += perRow) {
        const row = ids.slice(i, i + perRow);
        const rowW = row.length * nodeW + (row.length - 1) * gapX;
        let x = (W - rowW) / 2;
        for (const id of row) {
          this.pos.set(id, { x, y, w: nodeW, h: nodeH, layer: l });
          x += nodeW + gapX;
        }
        y += nodeH + 12;
      }
      this.bands.push({ layer: l, top, bottom: y, title: this.data.view.layer_titles[l] });
      y += 16;
    }
    this.W = W;
    this.H = y + 30;
  }

  render() {
    this.layout();
    const svg = this.svg;
    svg.innerHTML = "";
    svg.setAttribute("viewBox", `0 0 ${this.W} ${this.H}`);
    svg.setAttribute("height", this.H);
    const defs = el("defs", {}, svg);
    defs.innerHTML = `
      <filter id="glow-soft" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
      <filter id="glow-red" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>`;
    this.revealEls = [];
    const gBands = el("g", {}, svg);
    for (const b of this.bands) {
      const g = el("g", { class: "reveal", "data-y": b.top }, gBands);
      el("rect", { class: "layer-band", x: 6, y: b.top, width: this.W - 12, height: b.bottom - b.top, rx: 10 }, g);
      const t = el("text", { class: "layer-title", x: 18, y: b.top + 13 }, g);
      t.textContent = b.title;
      const n = el("text", { class: "layer-index", x: this.W - 30, y: b.top + 13 }, g);
      n.textContent = `L${String(b.layer).padStart(2, "0")}`;
      this.revealEls.push(g);
    }
    const gEdges = el("g", { filter: "url(#glow-soft)" }, svg);   // un seul filtre pour toutes les arêtes
    const gNodes = el("g", {}, svg);
    this.edgeEls.clear();
    for (const e of this.data.graph.edges) this.drawEdge(gEdges, e);
    this.nodeEls.clear();
    for (const [id, p] of this.pos) this.drawNode(gNodes, id, p);
  }

  drawEdge(parent, e) {
    const a = this.pos.get(e.from), b = this.pos.get(e.to);
    if (!a || !b) return;
    let d;
    const ax = a.x + a.w / 2, bx = b.x + b.w / 2;
    if (Math.abs(a.y - b.y) < 4) {                       // même rangée : arc par-dessous
      const y0 = a.y + a.h, dy = 28;
      d = `M${ax},${y0} C${ax},${y0 + dy} ${bx},${y0 + dy} ${bx},${b.y + b.h}`;
    } else {
      const down = b.y > a.y;
      const y1 = down ? a.y + a.h : a.y, y2 = down ? b.y : b.y + b.h;
      const my = (y1 + y2) / 2;
      d = `M${ax},${y1} C${ax},${my} ${bx},${my} ${bx},${y2}`;
    }
    const cls = e.type === "settled_on" ? "edge settled_on" : `edge ${e.source}`;
    const g = el("g", { class: "reveal", "data-y": Math.min(a.y, b.y) }, parent);
    const path = el("path", { d, class: cls }, g);
    const title = el("title", {}, path);
    title.textContent = `${e.from} —${e.type}→ ${e.to} [${e.source}]`;
    if (e.source === "curated" && e.type !== "settled_on") {
      const t = el("text", { class: "doc-icon", x: (ax + bx) / 2 - 4, y: (a.y + b.y) / 2 + a.h / 2 }, g);
      t.textContent = "▤";
    }
    this.edgeEls.set(edgeKey(e), path);
    this.revealEls.push(g);
  }

  drawNode(parent, id, p) {
    const node = this.data.nodeById[id];
    const isRoot = node.type === "position";
    const g = el("g", { class: `node type-${node.type} reveal${isRoot ? " root" : ""}`, transform: `translate(${p.x},${p.y})`,
      tabindex: 0, role: "button", "aria-label": `${this.data.view.display?.[id] || node.label} (${node.type})`, "data-y": p.y }, parent);
    el("rect", { class: "body", width: p.w, height: p.h, rx: 9 }, g);
    const glyph = el("text", { class: "glyph", x: 9, y: p.h / 2 + 4 }, g);
    glyph.textContent = GLYPH[node.type] || "•";
    const label = el("text", { class: "label", x: 25, y: 17 }, g);
    const room = p.w - 30 - (node.type === "oracle" ? 14 : 0);          // place pour la pastille du mode de prix
    label.textContent = short(isRoot ? "POSITION A" : (this.data.view.display?.[id] || node.label), Math.floor(room / 6.6));
    const sub = el("text", { class: "sub", x: 25, y: p.h - 9 }, g);
    sub.textContent = short(subLabel(node, this.data), Math.floor((p.w - 30) / 5.8));
    if (node.type === "oracle" && node.meta?.pricing_mode) {
      el("circle", { class: "mode-ring", cx: p.w - 10, cy: 10, r: 4.5, stroke: MODE_COLOR[node.meta.pricing_mode] || MODE_COLOR.unknown }, g);
    }
    const t = el("title", {}, g);
    t.textContent = `${node.label} — ${node.type}${node.meta?.pricing_mode ? " · prix " + node.meta.pricing_mode : ""}`;
    const click = () => this.onNodeClick(id);
    g.addEventListener("click", click);
    g.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); click(); } });
    this.nodeEls.set(id, g);
    this.revealEls.push(g);
  }

  // ------------------------------------------------------------------ états visuels
  clear() {
    for (const g of this.nodeEls.values()) g.classList.remove("faded", "hit", "origin", "selected", "pulse");
    for (const p of this.edgeEls.values()) p.classList.remove("faded", "hl", "fracture");
  }

  select(id) {
    for (const g of this.nodeEls.values()) g.classList.remove("selected");
    this.nodeEls.get(id)?.classList.add("selected");
  }

  highlight(edges, nodes = [], { fade = true } = {}) {
    this.clear();
    const keep = new Set(nodes);
    edges.forEach(e => { keep.add(e.from); keep.add(e.to); });
    if (fade) {
      for (const [id, g] of this.nodeEls) if (!keep.has(id)) g.classList.add("faded");
      for (const p of this.edgeEls.values()) p.classList.add("faded");
    }
    edges.forEach(e => { const p = this.edgeEls.get(edgeKey(e)); if (p) { p.classList.remove("faded"); p.classList.add("hl"); } });
  }

  fracture(edges, hitNodes = [], origins = []) {
    this.clear();
    const keep = new Set([...hitNodes, ...origins]);
    edges.forEach(e => { keep.add(e.from); keep.add(e.to); });
    for (const [id, g] of this.nodeEls) if (!keep.has(id)) g.classList.add("faded");
    for (const p of this.edgeEls.values()) p.classList.add("faded");
    edges.forEach(e => { const p = this.edgeEls.get(edgeKey(e)); if (p) { p.classList.remove("faded"); p.classList.add("fracture"); } });
    hitNodes.forEach(id => this.nodeEls.get(id)?.classList.add("hit"));
    origins.forEach(id => { this.nodeEls.get(id)?.classList.add("origin", "pulse"); });
  }

  focus(ids) {
    this.clear();
    const keep = new Set(ids);
    for (const [id, g] of this.nodeEls) if (!keep.has(id)) g.classList.add("faded");
    for (const [k, p] of this.edgeEls) {
      const [a, , b] = k.split("|");
      if (keep.has(a) && keep.has(b)) p.classList.add("hl"); else p.classList.add("faded");
    }
  }

  scrollTo(id) {
    const p = this.pos.get(id);
    if (p) this.wrap.scrollTo({ top: Math.max(0, p.y - 120), behavior: "smooth" });
  }
}
