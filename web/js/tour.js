// Parcours guidé « Explique-moi » : l'histoire d'Alice (docs/GUIDE_DEBUTANT.md §9), couche par couche.
// C'est ce qu'on montre au jury. Chaque étape met en lumière une partie du squelette.

import { esc, horizonOf, prob, usd } from "./data.js";

export function tourSteps(data) {
  const r = data.report, pos = r.position;
  const out = id => (data.edgesOut[id] || []);
  const redeem = [];
  for (let cur = pos.collateral; cur;) {
    redeem.push(cur);
    cur = out(cur).find(e => e.type === "redeemable_into")?.to;
  }
  const base = redeem[redeem.length - 1];
  const issuer = out(base).find(e => e.type === "issued_by")?.to;
  const offchain = issuer ? out(issuer).filter(e => e.type === "deployed_in").map(e => e.to) : [];
  const oracles = data.graph.nodes.filter(n => n.type === "oracle").map(n => n.id);
  const h = r.headline;
  const s24 = r.scenarios.find(s => s.id === "S-USDe-7-24h");
  const s6 = r.scenarios.find(s => s.id === "S-USDe-7-6h");
  return [
    { title: "La position d'Alice", focus: [data.graph.position.id, pos.market, pos.loan],
      text: `Alice a déposé ${Math.round(pos.collateral_pt).toLocaleString("fr-FR")} PT en gage sur un marché Morpho et emprunté
        ${Math.round(pos.debt_usdc).toLocaleString("fr-FR")} USDC. Vu de loin : un dépôt et un emprunt. Passons-le aux rayons X.` },
    { title: "Le gage : un bon Pendle", focus: [pos.collateral, pos.exit_venue, pos.market],
      text: `Le gage est un PT : un bon qui vaudra 1 USDe à l'échéance. Pour le revendre avant, il faut passer par le
        bureau de change Pendle (le pool) — sa profondeur décide du coût de sortie.` },
    { title: "Ce qu'il y a dans le bon", focus: redeem,
      text: `PT → SY (l'adaptateur Pendle) → sUSDe (la tirelire d'Ethena) → USDe (le dollar synthétique). Chaque flèche est
        prouvée on-chain : on a demandé à chaque contrat ce qu'il contient.` },
    { title: "Derrière l'USDe : le monde réel", focus: [base, issuer, ...offchain].filter(Boolean),
      text: `L'USDe tient grâce à Ethena, ses coffres (custodians) et ses paris inverses sur des exchanges. Rien de cela n'est
        on-chain : ce sont des liens curés, avec la page officielle et la date (traits ambrés).` },
    { title: "L'expert qui estime le gage", focus: [pos.market, ...oracles], node: pos.oracle,
      text: `Morpho croit aveuglément son oracle. Ici, c'est un méta-oracle : un expert « catalogue » (prix fixé par une formule)
        et un expert « marché » (Chainlink). Il ne passe au marché que si l'écart dépasse 0,75 % pendant 16 h.` },
    { title: "La durée compte autant que l'ampleur", scenario: "S-USDe-7-24h",
      text: `USDe à 0,93 $ pendant 6 h : ${s6 ? (s6.outcome.liquidated ? "liquidé" : "rien ne se passe") : "—"}. Même prix pendant 24 h :
        ${s24 ? (s24.outcome.liquidated ? `liquidé, ${usd(s24.outcome.borrower_loss_usd)} perdus` : "pas liquidé") : "—"}.
        Le délai de 16 h est le réglage de risque le plus important de la position.` },
    { title: "La décision, à 3 h du matin", sheet: true,
      text: `Alerte « ${esc(h.title)} ». Sortir coûte ${usd(h.exit_cost_usd)}, certain ; rester coûte ${usd(h.loss_if_incident_usd)}
        si l'incident arrive. Une seule question : « est-ce que je crois à plus de ${prob(h.p_star, 1, horizonOf(data))} de chances que ça arrive ? »` },
  ];
}

export function showTourStep(box, steps, i, api) {
  const s = steps[i];
  box.hidden = false;
  box.innerHTML = `
    <div class="step">ÉTAPE ${i + 1} / ${steps.length}</div>
    <h4>${esc(s.title)}</h4>
    <p>${s.text}</p>
    <div class="nav">
      <button data-tour="close">Fermer</button>
      <span>
        ${i > 0 ? `<button data-tour="prev">← Précédent</button>` : ""}
        ${i < steps.length - 1 ? `<button class="primary" data-tour="next">Suivant →</button>` : `<button class="primary" data-tour="close">Terminer</button>`}
      </span>
    </div>`;
  if (s.scenario) api.showScenario(s.scenario);
  else if (s.sheet) { api.showSheet(); api.highlightTopPath(0); }
  else {
    api.focus(s.focus.filter(Boolean));
    if (s.node) api.showNode(s.node, { keepFocus: true });
  }
  api.scrollTo(s.focus?.[0] || null);
}
