// StackTrace — Rayon X : point d'entrée. Relie les données, le squelette, les panneaux et les modes.
import { ancestors, edgeKey, esc, hours, loadAll, num, pathFromPosition } from "./data.js";
import { renderCards, renderImpactHint, renderSliders } from "./dock.js";
import { decrypt, filmNoise, scan } from "./effects.js";
import { cellSheet, impactSheet, nodeSheet, paramsSheet, renderVitals, replaySheet, riskSheet, scenarioSheet } from "./panels.js";
import { Skeleton } from "./skeleton.js";
import { showTourStep, tourSteps } from "./tour.js";

const $ = sel => document.querySelector(sel);
const state = { mode: "explore", scenarioId: null, priceIdx: 0, durIdx: 0, pIdx: 10, tourIdx: null };
let data, sk, steps;

function legend() {
  $("#legend").innerHTML = `
    <span><i></i>preuve on-chain</span><span><i class="api"></i>API</span><span><i class="curated"></i>curé ▤</span>
    <span><i class="fracture"></i>fracture</span>
    <span><b style="background:var(--mode-fixed)"></b>prix fixé</span><span><b style="background:var(--mode-market)"></b>prix de marché</span>
    <span><b style="background:var(--mode-internal)"></b>taux interne</span><span><b style="background:var(--mode-hybrid)"></b>hybride</span>`;
}

function panel(html) {
  const p = $("#panel");
  p.innerHTML = html;
  p.scrollTop = 0;
}

// ------------------------------------------------------------------ actions
function showSheet() { panel(riskSheet(data)); }

function showNode(id, { keepFocus = false } = {}) {
  sk.select(id);
  if (!keepFocus && state.mode === "explore") {
    const edges = [...(data.edgesOut[id] || []), ...(data.edgesIn[id] || [])].filter(e => e.type !== "settled_on");
    sk.highlight(edges, [id]);
    sk.select(id);
  }
  panel(nodeSheet(data, id));
}

function showScenario(id) {
  const sc = data.report.scenarios.find(s => s.id === id);
  if (!sc) return;
  state.scenarioId = id;
  const edges = [];
  const seen = new Set();
  for (const p of sc.contagion_paths) for (const e of p.edges) if (!seen.has(edgeKey(e))) { seen.add(edgeKey(e)); edges.push(e); }
  const hit = Object.entries(sc.asset_multipliers).filter(([, m]) => m < 1).map(([k]) => k);
  if (sc.oracle.switched) hit.push(sc.oracle.node, ...sc.oracle.children.map(c => c.node));
  if (sc.outcome.liquidated || sc.outcome.lender_loss_usd > 1 || sc.outcome.borrower_loss_usd > 1) hit.push(data.report.position.market);
  const origins = sc.shocks.map(s => s.node);
  if (sc.outcome.borrower_loss_usd > 1 || sc.outcome.lender_loss_usd > 1 || sc.outcome.liquidatable) sk.fracture(edges, hit, origins);
  else sk.highlight(edges, origins);
  panel(scenarioSheet(data, sc));
  document.querySelectorAll(".card").forEach(c => c.classList.toggle("active", c.dataset.scenario === id));
}

function showReplay(id) {
  const rp = data.report.replays.find(r => r.id === id && r.available);
  if (!rp) return;
  const path = pathFromPosition(data, data.view.usde_node || "usde");
  sk.highlight(path, [data.view.usde_node]);
  panel(replaySheet(data, rp));
}

function showImpact(id) {
  const anc = ancestors(data, id);
  const path = pathFromPosition(data, id);
  sk.fracture(path, [...anc].filter(x => x !== id), [id]);
  sk.select(id);
  panel(impactSheet(data, id, anc, path));
}

function highlightTopPath(i) {
  const t = data.report.monte_carlo.top_paths?.[i];
  if (t?.path) sk.fracture(t.path.edges, t.path.nodes.slice(1, -1), [t.target]);
}

function updateCell() {
  const cell = data.grid.cells[state.priceIdx][state.durIdx];
  $("#o-price") && ($("#o-price").textContent = `${num(data.grid.prices[state.priceIdx], 4)} $`);
  const paths = data.view.usde_paths || [];
  const edges = [];
  const seen = new Set();
  for (const p of paths) for (const e of p.edges) if (!seen.has(edgeKey(e))) { seen.add(edgeKey(e)); edges.push(e); }
  const usde = data.view.usde_node;
  if (cell.severity <= 0) sk.clear();
  else if (cell.borrower_loss_usd > 1 || cell.lender_loss_usd > 1 || cell.liquidatable) {
    const hit = new Set(paths.flatMap(p => p.nodes).filter(n => n !== usde));
    sk.fracture(edges, [...hit], [usde]);
  } else sk.highlight(edges, [usde]);
  panel(cellSheet(data, cell, state.pIdx));
}

// ------------------------------------------------------------------ modes
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-btn[data-mode]").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
  sk.clear();
  const dock = $("#dock");
  if (mode === "scenario") {
    renderSliders(dock, data, state);
    updateCell();
  } else if (mode === "impact") {
    renderImpactHint(dock);
    panel(`<h2>Mode impact</h2><p class="explain">Cliquez un nœud : on calcule à partir de <code>graph.json</code> tout ce qui en
      dépend (ses « ancêtres »), et on dessine le chemin de la fracture jusqu'à la position.</p>`);
  } else {
    renderCards(dock, data, state.scenarioId);
    showSheet();
  }
}

function onNodeClick(id) {
  if (state.mode === "impact") showImpact(id);
  else showNode(id);
}

// ------------------------------------------------------------------ délégation d'évènements
function wire() {
  document.querySelectorAll(".mode-btn[data-mode]").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
  document.body.addEventListener("click", ev => {
    const a = ev.target.closest("[data-action]");
    if (a) {
      const id = a.dataset.id;
      ({
        sheet: showSheet, "all-params": () => panel(paramsSheet(data)),
        scenario: () => { if (state.mode !== "explore") setMode("explore"); showScenario(id); },
        replay: () => showReplay(id), impact: () => { setMode("impact"); showImpact(id); },
        "path-mc": () => highlightTopPath(Number(a.dataset.index)),
      }[a.dataset.action] || (() => {}))();
      return;
    }
    const card = ev.target.closest("[data-scenario]");
    if (card) showScenario(card.dataset.scenario);
    const t = ev.target.closest("[data-tour]");
    if (t) {
      const k = t.dataset.tour;
      if (k === "close") { $("#tour").hidden = true; state.tourIdx = null; sk.clear(); return; }
      state.tourIdx += k === "next" ? 1 : -1;
      showTourStep($("#tour"), steps, state.tourIdx, tourApi);
    }
  });
  document.body.addEventListener("input", ev => {
    if (ev.target.id === "s-price") { state.priceIdx = Number(ev.target.value); updateCell(); }
    if (ev.target.id === "s-dur") { state.durIdx = Number(ev.target.value); $("#o-dur").textContent = durLabel(); updateCell(); }
    if (ev.target.id === "s-p") { state.pIdx = Number(ev.target.value); $("#o-p").textContent = `${Math.round(data.grid.p_grid[state.pIdx] * 100)} %`; updateCell(); }
  });
  $("#tour-btn").addEventListener("click", () => {
    if (state.mode !== "explore") setMode("explore");
    state.tourIdx = 0;
    showTourStep($("#tour"), steps, 0, tourApi);
  });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { sk.render(); sk.revealEls.forEach(e => e.classList.add("on")); if (state.mode === "scenario") updateCell(); }, 180);
  });
}

function durLabel() {
  return hours(data.grid.durations_hours[state.durIdx]);
}

const tourApi = {
  showScenario, showSheet, highlightTopPath,
  showNode: (id, o) => showNode(id, o),
  focus: ids => sk.focus(ids),
  scrollTo: id => id && sk.scrollTo(id),
};

// ------------------------------------------------------------------ démarrage
async function start() {
  filmNoise($("#film-noise"));
  decrypt($(".brand-name"));
  try {
    data = await loadAll();
  } catch (e) {
    const err = $("#error");
    err.hidden = false;
    err.innerHTML = `<b>Données introuvables</b><br>${esc((e.missing || [String(e)]).join(", "))}<br><br>
      Lancez d'abord :<br><code>PYTHONPATH=src python -m risk.run</code><br><code>PYTHONPATH=src python -m risk.export_web</code><br>
      puis servez le dossier : <code>python -m http.server 8000 -d web</code> (ouvrir index.html directement ne marche pas).`;
    return;
  }
  const snap = data.report.snapshot;
  $("#patient").innerHTML = `patient <b>${esc(data.graph.position.id.slice(0, 22))}…</b> · bloc <b>#${snap.block}</b> · ${esc(snap.time_iso.slice(0, 16).replace("T", " "))} UTC`;
  $("#film-block").textContent = `#${snap.block}`;
  // curseurs par défaut : USDe 0,93 $ pendant 24 h (le cas du prompt)
  state.priceIdx = Math.max(0, data.grid.prices.indexOf(0.93));
  state.durIdx = Math.max(0, data.grid.durations_hours.indexOf(24));
  state.pIdx = data.grid.p_grid.indexOf(0.1);
  steps = tourSteps(data);
  renderVitals($("#vitals"), data);
  legend();
  sk = new Skeleton($("#skeleton"), $("#svg-wrap"), data, onNodeClick);
  sk.render();
  wire();
  setMode("explore");
  scan($("#scanline"), sk.revealEls);
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("mode")) setMode(hash.get("mode"));
  if (hash.get("scenario")) showScenario(hash.get("scenario"));
  if (hash.get("node")) (state.mode === "impact" ? showImpact : showNode)(hash.get("node"));
  if (hash.get("replay")) showReplay(hash.get("replay"));
}

start();
