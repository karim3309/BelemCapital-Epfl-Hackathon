// Panneaux : constantes vitales, fiche de risque, fiche de l'os (nœud), scénario, impact, replay.
// Tout le texte chiffré vient de risk_report.json / risk_grid.json / graph.json (aucun calcul ici).

import { esc, every, horizonOf, hours, linkify, num, pct, prob, usd } from "./data.js";

const STATUS_LABEL = { source: "sourcé", onchain: "on-chain", hypothesis: "hypothèse" };
const SRC_LABEL = { onchain: "on-chain", api: "API", curated: "curé" };

export const verdictTag = v => `<span class="verdict-tag verdict-${v}">${v}</span>`;
const badge = (cls, txt) => `<span class="badge ${cls}">${esc(txt)}</span>`;
const MODE_FR = { fixed: "prix fixe", market: "prix de marché", internal_rate: "taux interne", hybrid: "hybride", unknown: "inconnu" };
const modeBadge = m => m ? badge(`mode-${m}`, MODE_FR[m] || m) : "";
const statusBadge = s => badge(`source-${s}`, STATUS_LABEL[s] || s);

function kv(rows) {
  return `<dl class="kv">${rows.filter(r => r[1] !== undefined && r[1] !== null && r[1] !== "")
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
}

function proof(e, data, { withRule = true } = {}) {
  const rule = data.view.rules[e.type]?.replaceAll("{to}", e.to).replaceAll("{from_}", e.from) || "";
  return `<div class="proof">
    <div class="head">${badge(e.source, SRC_LABEL[e.source] || e.source)}
      <span class="mono">${esc(e.from)} → <b>${esc(e.type)}</b> → ${esc(e.to)}</span>
      ${e.weight !== 1 ? `<span class="mono">poids ${e.weight}</span>` : ""}</div>
    ${withRule && rule ? `<div class="rule">${esc(rule)}</div>` : ""}
    <div class="ev">${linkify(e.evidence)}</div>
  </div>`;
}

function pathBlock(path, data, label = "") {
  if (!path) return "";
  return `<div>${label}${path.edges.map(e => proof(e, data)).join("")}</div>`;
}

// ------------------------------------------------------------------ constantes vitales
export function renderVitals(box, data) {
  const pos = data.report.position, h = data.report.headline, b = data.report.baseline, snap = data.report.snapshot;
  const hfClass = pos.health_factor < 1.1 ? "warn" : "good";
  const cells = [
    ["Health factor", num(pos.health_factor, 3), `liquidable sous 1,000`, hfClass],
    ["LTV / LLTV", `${num(pos.ltv * 100, 1)} / ${num(pos.lltv * 100, 1)} %`, "dette ÷ gage / limite", ""],
    ["Marge avant liquidation", pct(pos.oracle_drop_to_liquidation, 2), "baisse du prix oracle", "warn"],
    ["Gage (valeur de marché)", usd(pos.gross_value_usd), `${num(pos.collateral_pt, 0)} PT`, ""],
    ["Dette", usd(pos.debt_usdc * 1), "USDC, intérêts inclus", ""],
    ["Capital net (poche V)", usd(pos.equity_usd), "ce qu'on récupère en sortant", ""],
    ["Coût de sortie", usd(h.exit_cost_usd), `${pct(h.exit_cost_pct_equity)} du capital · mesuré on-chain`, ""],
    ["Sans alerte", verdictTag(b.verdict), "perte attendue < coût de sortie", "good"],
    ["Photo", `#${snap.block}`, snap.time_iso.replace("T", " ").slice(0, 16) + " UTC", ""],
  ];
  box.innerHTML = cells.map(([k, v, s, c]) =>
    `<div class="vital ${c}"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s)}</div></div>`).join("");
}

// ------------------------------------------------------------------ fiche de risque
export function riskSheet(data) {
  const r = data.report, h = r.headline, mc = r.monte_carlo, b = r.baseline;
  const top = (mc.top_paths || []).map((t, i) => `
    <div class="proof">
      <div class="head"><b>#${i + 1}</b> <span class="mono">${esc(t.event)} → ${esc(t.target)}</span>
        <span class="mono">${usd(t.expected_loss_usd)} / ${mc.horizon_days} j (${pct(t.share, 0)})</span></div>
      <button class="btn-link" data-action="path-mc" data-index="${i}">dessiner ce chemin sur le squelette</button>
    </div>`).join("");
  const hyp = r.params.filter(p => p.status === "hypothesis");
  const reps = r.replays.filter(x => x.available).map(x =>
    `<button class="btn-link" data-action="replay" data-id="${esc(x.id)}">${esc(x.title)}</button>`).join("<br>");
  return `
    <h2>Fiche de risque</h2>
    <div class="title">Alerte : ${esc(h.title)}</div>
    <p class="sentence">${verdictTag(h.verdict)} ${esc(h.sentence.replace(/^(STAY|EXIT|PARTIAL)[^—]*—\s*/, ""))}</p>
    <p class="explain"><b>La question de 3 h du matin :</b> ${esc(h.three_am_question || "")}</p>
    <div class="big">p* = ${pct(h.p_star)}</div>${h.p_star != null && every(h.p_star, horizonOf(data)) ? `<p class="explain">${every(h.p_star, horizonOf(data))} : c'est la fréquence d'un événement qui a ${pct(h.p_star)} de chances d'arriver en ${horizonOf(data)} jours.</p>` : ""}
    <p>Sortir coûte <b>${usd(h.exit_cost_usd)}</b> (certain) ; si l'incident arrive, la poche perd <b>${usd(h.loss_if_incident_usd)}</b>
      (${pct(h.loss_if_incident_pct_equity, 0)} du capital) et les prêteurs <b>${usd(h.lender_loss_usd)}</b>.
      Au-dessus de p*, sortir coûte moins cher que rester.</p>
    <button class="btn-link" data-action="scenario" data-id="${esc(h.scenario)}">voir le détail du scénario →</button>

    <h3>Sans alerte, sur ${mc.horizon_days} jours (Monte Carlo, ${num(mc.samples, 0)} tirages)</h3>
    ${kv([["perte attendue", usd(mc.expected_loss_usd)], ["VaR 95 %", usd(mc.var95_usd)], ["VaR 99 %", usd(mc.var99_usd)],
          ["ES 99 % (1 % pires)", usd(mc.es99_usd)], ["P(perte)", prob(mc.p_loss, 2, mc.horizon_days)], ["P(liquidation)", prob(mc.p_liquidation, 2, mc.horizon_days)],
          ["prêteurs (attendu)", usd(mc.expected_lender_loss_usd)], ["verdict", verdictTag(b.verdict)]])}
    <p>${esc(b.sentence)}</p>

    <h3>Les 3 chemins de contagion les plus coûteux</h3>
    ${top}

    <h3>Replays d'incidents réels</h3>
    <p>${reps}</p>

    <h3>Confiance</h3>
    ${kv([["seuil p*", esc(r.confidence.p_star)], ["perte attendue / VaR", esc(r.confidence.expected_loss_and_var)]])}

    <h3>Hypothèses (${hyp.length}) — à challenger</h3>
    <table class="params-table">${hyp.map(p => `<tr><td>${esc(p.name)}</td><td>${statusBadge(p.status)} ${esc(JSON.stringify(p.value))}<br>${esc(p.why || "")}</td></tr>`).join("")}</table>
    <h3>Sensibilité (les 5 hypothèses qui font le plus bouger la perte attendue)</h3>
    <table class="params-table">${r.sensitivity.slice(0, 5).map(s => `<tr><td>${esc(s.param)}</td>
      <td>${esc(String(s.low))} → ${usd(s.el_low)} · ${esc(String(s.high))} → ${usd(s.el_high)}<br>p* : ${prob(s.headline_p_star_low, 1, horizonOf(data))} ↔ ${prob(s.headline_p_star_high, 1, horizonOf(data))}</td></tr>`).join("")}</table>
    <p><button class="btn-link" data-action="all-params">voir les ${r.params.length} paramètres et leur source</button></p>`;
}

export function paramsSheet(data) {
  const rows = data.report.params.map(p => `<tr><td>${esc(p.name)}</td><td>${statusBadge(p.status)}
      ${p.status !== "onchain" || typeof p.value !== "object" ? esc(JSON.stringify(p.value)).slice(0, 120) : "(données on-chain)"}
      <br>${p.source && p.source !== "onchain" ? linkify(p.source) : ""}${p.field ? `<span class="mono">${esc(p.field)}</span>` : ""}
      ${p.why ? "<br>" + esc(p.why) : ""}${p.note ? "<br><i>" + esc(p.note) + "</i>" : ""}</td></tr>`).join("");
  return `<h2>Paramètres du moteur</h2>
    <p>Chaque chiffre a un statut : ${statusBadge("source")} doc officielle (URL + date), ${statusBadge("onchain")} lu dans le graphe
    ou au bloc figé, ${statusBadge("hypothesis")} choix de modélisation assumé (justifié).</p>
    <table class="params-table">${rows}</table>
    <p><button class="btn-link" data-action="sheet">← fiche de risque</button></p>`;
}

// ------------------------------------------------------------------ fiche de l'os (nœud)
export function nodeSheet(data, id) {
  const n = data.nodeById[id];
  if (n.type === "position") {
    return `<h2>Position</h2><div class="title">${esc(id.slice(0, 26))}…</div>
      <p class="explain">La racine : un dépôt de PT en gage sur Morpho et un emprunt d'USDC. Tout ce qui est dessous est ce dont elle dépend.</p>
      ${kv([["value_usd (contrat)", usd(data.graph.position.value_usd)], ["capital net", usd(data.report.position.equity_usd)]])}
      ${(data.edgesOut[id] || []).map(e => proof(e, data)).join("")}`;
  }
  const [typeTitle, typeText] = data.view.type_text[n.type] || [n.type, ""];
  const m = n.meta || {};
  const kindText = data.view.kind_text[m.oracle_kind] || data.view.kind_text[m.asset_kind] || "";
  const rows = [];
  if (n.address) rows.push(["adresse", `<a href="${data.view.etherscan}${n.address}" target="_blank" rel="noopener noreferrer">${n.address.slice(0, 10)}…${n.address.slice(-6)}</a>`]);
  if (m.pricing_mode) rows.push(["mode de prix", modeBadge(m.pricing_mode)]);
  if (m.effective_pricing_mode) rows.push(["mode effectif", modeBadge(m.effective_pricing_mode)]);
  if (m.price != null) rows.push(["prix (oracle)", num(m.price, 6)]);
  if (m.answer != null) rows.push(["valeur du feed", num(m.answer, 6)]);
  if (m.price_usd != null) rows.push(["prix USD", `${num(m.price_usd, 6)} $`]);
  if (m.tvl_usd != null) rows.push(["TVL", usd(m.tvl_usd)]);
  if (m.deviation_threshold != null) rows.push(["seuil de bascule", pct(m.deviation_threshold, 2)]);
  if (m.challenge_timelock_seconds != null) rows.push(["délai de bascule", hours(m.challenge_timelock_seconds / 3600)]);
  if (m.days_to_expiry != null) rows.push(["échéance", `${esc(m.expiry_iso?.slice(0, 10))} (${num(m.days_to_expiry, 1)} j)`]);
  if (m.share_to_asset_rate != null) rows.push(["taux interne", num(m.share_to_asset_rate, 6)]);
  if (m.cooldown_seconds != null) rows.push(["délai de retrait", hours(m.cooldown_seconds / 3600)]);
  if (m.implied_apy != null) rows.push(["taux implicite", pct(m.implied_apy, 2)]);
  if (m.utilization != null) rows.push(["utilisation", pct(m.utilization, 1)]);
  if (m.borrow_apy != null) rows.push(["taux d'emprunt", pct(m.borrow_apy, 2)]);
  if (m.proxy) rows.push(["code modifiable ?", m.proxy.upgradeable === true ? badge("danger", "oui (proxy)") :
    m.proxy.upgradeable === false ? "non (clone figé)" : "non prouvé"]);
  if (m.role) rows.push(["rôle", esc(m.role)]);
  if (m.evidence_url) rows.push(["source", linkify(m.evidence_url) + ` (${esc(m.as_of)})`]);
  if (m.switch_rule) rows.push(["règle de bascule", esc(m.switch_rule)]);
  if (m.note && n.type !== "chain") rows.push(["note", esc(m.note)]);
  if (m.why_constant) rows.push(["pourquoi constant", esc(m.why_constant)]);
  if (m.formula) rows.push(["formule", `<span class="mono">${esc(m.formula)}</span>`]);
  const outs = (data.edgesOut[id] || []).filter(e => e.type !== "settled_on");
  const settled = (data.edgesOut[id] || []).find(e => e.type === "settled_on");
  const ins = data.edgesIn[id] || [];
  const scenarios = data.report.scenarios.filter(s => s.shocks.some(sh => sh.node === id));
  return `
    <h2>${esc(typeTitle)}</h2>
    <div class="title">${esc(n.label)}</div>
    <p class="explain">${esc(typeText)}${kindText ? "<br><br>" + esc(kindText) : ""}</p>
    ${kv(rows)}
    ${scenarios.length ? `<h3>Scénarios qui frappent ce nœud</h3>${scenarios.map(s =>
      `<button class="btn-link" data-action="scenario" data-id="${esc(s.id)}">${esc(s.title)}</button>`).join("<br>")}` : ""}
    <p><button class="btn-link" data-action="impact" data-id="${esc(id)}">⚡ et si ce nœud casse ? (mode impact)</button></p>
    <h3>Ce dont il dépend (${outs.length})</h3>
    ${outs.map(e => proof(e, data)).join("") || "<p>Rien : c'est le fond de la pile.</p>"}
    ${settled ? proof(settled, data, { withRule: false }) : ""}
    <h3>Ce qui dépend de lui (${ins.length})</h3>
    ${ins.slice(0, 12).map(e => proof(e, data, { withRule: false })).join("")}`;
}

// ------------------------------------------------------------------ scénario
export function scenarioSheet(data, sc) {
  const o = sc.outcome, d = sc.decision, or = sc.oracle;
  const status = o.liquidated ? `<span class="status-pill status-liq">LIQUIDÉ</span>` :
    o.lender_loss_usd > 1 ? `<span class="status-pill status-lend">PRÊTEURS EXPOSÉS</span>` :
      `<span class="status-pill status-ok">PAS LIQUIDÉ</span>`;
  const tl = (or.timeline || []).map(t => `<li class="${t.role === "backup" ? "backup" : ""}"><span class="t">t+${hours(t.t_hours)}</span>${esc(t.event)}</li>`).join("");
  const used = (sc.params_used || []).map(n => data.paramByName[n]).filter(Boolean);
  return `
    <h2>Scénario ${esc(sc.id)}</h2>
    <div class="title">${esc(sc.title)}</div>
    <p>${esc(sc.story)}</p>
    <p>${status}</p>
    ${kv([["HF", `${num(o.hf_before, 3)} → <b>${num(o.hf_after, 3)}</b>`],
          ["prix oracle", `${num(o.oracle_price_before, 5)} → ${num(o.oracle_price_after, 5)} ${modeBadge(o.oracle_mode)}`],
          ["méta-oracle", or.switched ? badge("danger", `basculé après ${hours(or.switch_after_hours)}`) :
            or.challenge_possible ? "challenge possible, pas de bascule" : "aucun challenge possible"],
          ["perte emprunteur", `<b>${usd(o.borrower_loss_usd)}</b> (${pct(o.lgi, 0)} du capital)`],
          ["perte prêteurs", usd(o.lender_loss_usd)],
          ["qui perd", esc(o.who_loses.join(", "))]])}
    <h3>Décision</h3>
    <p class="sentence">${verdictTag(d.verdict)} ${esc(d.sentence.replace(/^(STAY|EXIT|PARTIAL)[^—]*—\s*/, ""))}</p>
    ${kv([["seuil p*", prob(d.p_star, 1, horizonOf(data))], ["p (illustration)", prob(d.p_default, 0, horizonOf(data))],
          ["coût de sortie", d.exit_cost_full.feasible ? usd(d.exit_cost_full.total_usd) : badge("danger", "sortie impossible")]])}
    ${tl ? `<h3>Chronologie de l'oracle</h3><ul class="timeline">${tl}</ul>` : ""}
    <h3>Comment le choc se propage (règles appliquées)</h3>
    <ul class="trace">${[...sc.propagation_trace, ...o.trace].map(t => `<li>${esc(t)}</li>`).join("")}</ul>
    <h3>Chemin(s) de contagion prouvés</h3>
    ${sc.contagion_paths.map(p => pathBlock(p, data)).join("") || "<p>Pas de chemin direct (choc sur la chaîne).</p>"}
    <h3>Paramètres utilisés</h3>
    <table class="params-table">${used.map(p => `<tr><td>${esc(p.name)}</td><td>${statusBadge(p.status)} ${esc(p.why || p.note || p.source || "")}</td></tr>`).join("")}</table>
    <p><i>Pourquoi ce scénario :</i> ${esc(sc.why)} · confiance : <b>${esc(sc.confidence.level)}</b></p>`;
}

// ------------------------------------------------------------------ cellule de la grille (mode scénario)
export function cellSheet(data, cell, pIndex) {
  const p = data.grid.p_grid[pIndex];
  const f = cell.fraction_by_p[pIndex];
  const v = f <= 0 ? "STAY" : f >= 0.999 ? "EXIT" : "PARTIAL";
  const status = cell.status === "LIQUIDÉ" ? "status-liq" : cell.status === "prêteurs exposés" ? "status-lend" : "status-ok";
  const arb = ["primary", "challenge", "switched"].map(s => `<span class="${cell.oracle_state === s ? `on ${s}` : ""}">${
    { primary: "expert « catalogue »", challenge: "challenge (écart > 0,75 %)", switched: "basculé sur le marché" }[s]}</span>`).join("");
  return `
    <h2>Scénario interactif</h2>
    <div class="title">USDe à ${num(cell.usde_price, 4)} $ pendant ${hours(cell.duration_hours)}</div>
    <div class="arbiter">${arb}</div>
    <p style="margin-top:12px"><span class="status-pill ${status}">${esc(cell.status.toUpperCase())}</span></p>
    ${kv([["health factor", `<b>${num(cell.hf, 3)}</b>`], ["écart primaire/secours", pct(cell.deviation, 2)],
          ["perte emprunteur", usd(cell.borrower_loss_usd)], ["perte prêteurs", usd(cell.lender_loss_usd)],
          ["seuil p*", prob(cell.p_star, 1, horizonOf(data))], ["votre probabilité", prob(p, 0, horizonOf(data))]])}
    <p class="sentence">${verdictTag(v)} ${v === "PARTIAL" ? `sortir ${pct(f, 0)} de la position` :
      v === "EXIT" ? "sortir entièrement" : "rester"} — ${cell.p_star == null ? "rien à perdre dans ce scénario." :
      p > cell.p_star ? `vous croyez à plus que p* = ${prob(cell.p_star, 1, horizonOf(data))}.` : `vous croyez à moins que p* = ${prob(cell.p_star, 1, horizonOf(data))}.`}</p>
    <p class="explain">Le méta-oracle n'écoute le marché que si l'écart dépasse 0,75 % <b>pendant 16 h</b>.
      Faites glisser la durée de part et d'autre de 16 h : à prix égal, le verdict change.</p>
    <p>Tous ces chiffres viennent de <code>risk_grid.json</code>, calculé par le moteur Python (aucun calcul dans la page).</p>`;
}

// ------------------------------------------------------------------ impact
export function impactSheet(data, id, anc, path) {
  const n = data.nodeById[id];
  const list = [...anc].filter(x => x !== data.graph.position.id).map(x => data.nodeById[x]).filter(Boolean);
  const hitsPosition = anc.has(data.graph.position.id);
  const scenarios = data.report.scenarios.filter(s => s.shocks.some(sh => sh.node === id));
  return `
    <h2>Mode impact</h2>
    <div class="title">Et si « ${esc(n.label)} » casse ?</div>
    <p class="explain">${hitsPosition ? `<b>La position est touchée</b>, par ${path.length} maillon(s) : la fracture remonte le chemin dessiné en magenta.`
      : "La position ne dépend pas de ce nœud."} ${list.length} élément(s) en dépendent au total.</p>
    ${scenarios.length ? `<h3>Combien ? (scénarios chiffrés par le moteur)</h3>${scenarios.map(s =>
      `<div class="proof"><div class="head">${verdictTag(s.decision.verdict)} <b>${esc(s.title)}</b></div>
      perte ${usd(s.outcome.borrower_loss_usd)} · prêteurs ${usd(s.outcome.lender_loss_usd)} · p* ${prob(s.decision.p_star, 1, horizonOf(data))}
      <br><button class="btn-link" data-action="scenario" data-id="${esc(s.id)}">détail →</button></div>`).join("")}`
      : `<p>Pas de scénario chiffré sur ce nœud : le chemin montre l'exposition, pas encore le montant.</p>`}
    <h3>Chemin vers la position (preuves)</h3>
    ${path.map(e => proof(e, data)).join("") || "<p>—</p>"}
    <h3>Tout ce qui en dépend</h3>
    <p class="mono">${list.map(x => esc(x.label)).join(" · ")}</p>`;
}

// ------------------------------------------------------------------ replay
export function replaySheet(data, rp) {
  const pts = rp.chainlink_path;
  const W = 340, H = 140, pad = 26;
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t + 3600;
  const lo = Math.min(0.6, ...pts.map(p => p.price)), hi = 1.01;
  const X = t => pad + (t - t0) / (t1 - t0) * (W - pad - 8);
  const Y = v => 8 + (hi - v) / (hi - lo) * (H - pad - 8);
  let d = "";
  pts.forEach((p, i) => { d += (i ? `H${X(p.t).toFixed(1)}V${Y(p.price).toFixed(1)}` : `M${X(p.t).toFixed(1)},${Y(p.price).toFixed(1)}`); });
  d += `H${X(t1).toFixed(1)}`;
  const off = rp.designs.find(x => x.design.includes("Binance"));
  const binLine = off ? `<line x1="${pad}" x2="${W - 8}" y1="${Y(0.65)}" y2="${Y(0.65)}" stroke="var(--magenta)" stroke-dasharray="4 3"/>
    <text x="${W - 10}" y="${Y(0.65) - 4}" text-anchor="end" fill="var(--magenta)" font-size="10" font-family="monospace">Binance 0,65 $ (~40 min, curé)</text>` : "";
  const thr = rp.meta_oracle.challenge_price;
  const chart = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Prix de l'USDe">
    <line x1="${pad}" x2="${W - 8}" y1="${Y(1)}" y2="${Y(1)}" stroke="rgba(103,232,249,.25)"/>
    <line x1="${pad}" x2="${W - 8}" y1="${Y(thr)}" y2="${Y(thr)}" stroke="var(--amber)" stroke-dasharray="2 3"/>
    <text x="${pad + 2}" y="${Y(thr) + 11}" fill="var(--amber)" font-size="9" font-family="monospace">seuil de challenge ${num(thr, 4)} $</text>
    ${binLine}
    <path d="${d}" fill="none" stroke="var(--cyan)" stroke-width="1.8"/>
    ${(() => { const m = pts.reduce((a, b) => (b.price < a.price ? b : a));
      return `<circle cx="${X(m.t)}" cy="${Y(m.price)}" r="3.5" fill="var(--bone)"/>
        <text x="${Math.min(X(m.t) + 6, W - 120)}" y="${Y(m.price) + 14}" fill="var(--bone)" font-size="9.5" font-family="monospace">min Chainlink ${num(m.price, 4)} $</text>`; })()}
    <text x="${pad}" y="${H - 6}" fill="var(--dim)" font-size="9" font-family="monospace">${esc(rp.window.start.slice(0, 10))}</text>
    <text x="${W - 8}" y="${H - 6}" text-anchor="end" fill="var(--dim)" font-size="9" font-family="monospace">Chainlink USDe/USD on-chain</text>
  </svg>`;
  return `
    <h2>Replay d'incident réel</h2>
    <div class="title">${esc(rp.title)}</div>
    <p>${esc(rp.story)}</p>
    ${chart}
    <p style="font-size:11.5px">Trait cyan : le prix de l'USDe <b>on-chain</b> (feed Chainlink, lu au bloc figé). Pointillé ambre :
      le seuil sous lequel l'arbitre du méta-oracle peut être challengé. Pointillé magenta : le plus bas <b>sur Binance</b>
      (hors chaîne, source curée) — invisible pour Chainlink, qui agrège de nombreuses sources.</p>
    ${kv([["plus bas Chainlink", `${num(rp.chainlink_min, 5)} $ (${esc(rp.chainlink_min_iso.slice(0, 16).replace("T", " "))} UTC)`],
          ["écart max", pct(rp.meta_oracle.max_deviation, 2)],
          ["temps au-dessus du seuil", `${num(rp.meta_oracle.longest_above_threshold_minutes, 1)} min (il en faut ${num(rp.meta_oracle.needed_minutes, 0)})`]])}
    <h3>Trois oracles face à la même journée</h3>
    ${rp.designs.map(x => `<div class="proof"><div class="head">${x.liquidated ? badge("danger", "liquidé") : badge("onchain", "intact")}
      <b>${esc(x.design)}</b></div>HF min ${num(x.min_hf, 3)}${x.borrower_loss_usd ? ` · perte ${usd(x.borrower_loss_usd)}` : ""}
      <div class="rule">${esc(x.why)}</div></div>`).join("")}
    ${rp.offchain_source ? `<p>Source du prix hors chaîne : ${linkify(rp.offchain_source.evidence_url)} (${esc(rp.offchain_source.as_of)}) — « ${esc(rp.offchain_source.says)} »</p>` : ""}
    <p class="ev mono">${esc(rp.evidence)}</p>`;
}
