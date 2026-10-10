// Le dock du bas : cartes de scénarios (mode squelette) ou curseurs (mode scénario).
// Les curseurs ne font que CHOISIR une case de risk_grid.json (pré-calculée par Python).

import { esc, hours, num, pct, usd } from "./data.js";
import { verdictTag } from "./panels.js";

export function renderCards(box, data, activeId) {
  const cards = data.report.scenarios.map(s => `
    <button class="card${s.id === activeId ? " active" : ""}" data-scenario="${esc(s.id)}" title="${esc(s.story)}">
      <div class="cid">${esc(s.id)}</div>
      <div class="ct">${esc(s.title)}</div>
      <div class="cm"><span>${s.outcome.liquidated ? "LIQUIDÉ" : s.outcome.lender_loss_usd > 1 ? "prêteurs −" + usd(s.outcome.lender_loss_usd) : "HF " + s.outcome.hf_after.toFixed(3)}</span>
        <span>${verdictTag(s.decision.verdict)}</span></div>
      <div class="cm"><span>perte ${usd(s.outcome.borrower_loss_usd)}</span><span>p* ${pct(s.decision.p_star)}</span></div>
    </button>`).join("");
  box.innerHTML = `
    <div class="dock-hint">Scénarios de stress calculés par le moteur — cliquez pour voir la fracture se propager.
      <button class="btn-link" data-action="sheet">Fiche de risque</button> ·
      <button class="btn-link" data-action="replay" data-id="R-OCT2025">Replay 10 octobre 2025</button></div>
    <div class="cards">${cards}</div>`;
}

export function renderSliders(box, data, state) {
  const g = data.grid;
  const priceIdx = state.priceIdx, durIdx = state.durIdx, pIdx = state.pIdx;
  box.innerHTML = `
    <div class="dock-hint">Faites varier le prix de l'USDe et la durée du choc : le squelette, l'arbitre du méta-oracle et le verdict
      se mettent à jour à partir de <code>risk_grid.json</code>.</div>
    <div class="dock-row">
      <div class="slider">
        <label for="s-price">Prix de l'USDe</label>
        <input id="s-price" type="range" min="0" max="${g.prices.length - 1}" step="1" value="${priceIdx}">
        <output id="o-price">${num(g.prices[priceIdx], 4)} $</output>
      </div>
      <div class="slider">
        <label for="s-dur">Durée du choc</label>
        <input id="s-dur" type="range" min="0" max="${g.durations_hours.length - 1}" step="1" value="${durIdx}">
        <output id="o-dur">${hours(g.durations_hours[durIdx])}</output>
      </div>
      <div class="slider">
        <label for="s-p">Votre probabilité que ça arrive</label>
        <input id="s-p" type="range" min="0" max="${g.p_grid.length - 1}" step="1" value="${pIdx}">
        <output id="o-p">${pct(g.p_grid[pIdx], 0)}</output>
      </div>
    </div>`;
}

export function renderImpactHint(box) {
  box.innerHTML = `<div class="dock-hint">Mode impact : cliquez n'importe quel nœud du squelette (ex. Binance, Copper, Chainlink…)
    pour voir tout ce qui en dépend et le chemin par lequel la fracture atteint la position.</div>`;
}
