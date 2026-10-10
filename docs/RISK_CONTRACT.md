# Contrat `risk_report.json` / `risk_grid.json` (sorties du moteur de risque)

Produits par `python -m risk.run` à partir de `output/graph.json` (contrat de la découverte, voir
[`CONTRACT.md`](CONTRACT.md)) et de `output/risk_inputs.json`. Ils sont validés à chaque exécution par
`src/risk/validate_report.py`. Le cadrage nommait ce fichier `risk_report.json` ; c'est ce nom qui est retenu.

**Unités :** montants en **USD** (`*_usd`) ou en **USDC** (`*_usdc`) ; fractions entre 0 et 1 (`0.016` = 1,6 %) ;
durées en heures (`*_hours`, `null` = durable) ; `hf` = health factor (< 1 = liquidable).
**Convention :** `borrower_loss_usd` > 0 = perte de l'emprunteur (négatif = gain) ; `lender_loss_usd` ≥ 0.

## `risk_report.json`

| Clé | Contenu |
|---|---|
| `contract_version` | 1 |
| `snapshot` | `{block, timestamp, time_iso}` : le bloc de la photo (le même que graph.json) |
| `position` | état de départ : `collateral_pt`, `debt_usdc`, `pt_market_usd` (prix de marché d'un PT), `oracle_price`, `gross_value_usd`, `equity_usd` (**poche V** = capital net), `health_factor`, `ltv`, `lltv`, `lif` (bonus de liquidation Morpho), `borrow_apy`, `oracle_drop_to_liquidation`, ids des nœuds clés (`market`, `collateral`, `loan`, `oracle`, `exit_venue`) |
| `headline` | **la fiche de risque** : `scenario` (alerte principale), `verdict` (STAY/PARTIAL/EXIT), `exit_fraction`, `p_star`, `p_default`, `loss_if_incident_usd`, `loss_if_incident_pct_equity`, `lender_loss_usd`, `exit_cost_usd`, `exit_cost_pct_equity`, `sentence`, `three_am_question` |
| `baseline` | verdict « sans alerte » (perte attendue Monte Carlo vs coût de sortie) + phrase |
| `exit_cost.full` | coût de sortie totale : `slippage_rate` / `slippage_usd` (mesuré on-chain), `second_leg_usd`, `gas_usd`, `carry_usd`, `total_usd`, `feasible` |
| `exit_cost.curves` | `{"1.0": [...], "0.5": [...], "0.1": [...]}` : coût pour chaque fraction 0 → 100 % (pas de 5 %), selon que le pool a sa liquidité entière, ÷2 ou ÷10 |
| `exit_cost.simulations_evidence` | preuves des simulations RouterStatic (contrat.fonction(args) = résultat @ adresse #bloc) |
| `monte_carlo` | `samples`, `seed`, `horizon_days`, `p_any_event`, `p_loss`, `p_liquidation`, `expected_loss_usd`, `var95_usd`, `var99_usd`, `es99_usd`, `expected_lender_loss_usd`, `conditional_loss_usd`, `events[]` (λ, probabilité sur l'horizon, contribution à la perte attendue), `top_paths[]` (3 chemins les plus coûteux, arêtes de graph.json avec preuves) |
| `scenarios[]` | un objet par scénario de stress (voir ci-dessous) |
| `replays[]` | incidents réels rejoués : `chainlink_path` (on-chain), `meta_oracle` (écart max, temps au-dessus du seuil, bascule ?), `designs[]` (3 designs d'oracle : HF min, liquidé ?, perte), `offchain_source` (URL + date) |
| `sensitivity[]` | tornade : pour chaque hypothèse, valeurs basse/haute → `el_low/high` (perte attendue), `headline_loss_low/high`, `headline_p_star_low/high` ; trié par impact (`el_swing`) |
| `calibration` | statistiques de l'historique Chainlink USDe/USD (pire écart, épisodes sous chaque seuil, fréquence annuelle) |
| `params[]` | **tous** les paramètres : `name`, `value`, `status` (`source` / `onchain` / `hypothesis`), `source` + `as_of`, ou `field`, ou `why`, et `range` |
| `confidence` | niveau de confiance de p* et de la perte attendue, en clair |

### Un scénario (`scenarios[]`)
| Clé | Contenu |
|---|---|
| `id`, `family`, `title`, `story`, `why` | identité et justification du scénario |
| `shocks[]` | `{node, kind, severity, duration_hours, panic}` : le choc appliqué (nœud de graph.json) |
| `propagation_trace[]` | les règles appliquées, en français |
| `asset_multipliers` | `{id_actif: multiplicateur de valeur}` (0,9 = −10 %) |
| `oracle` | `price_normal` → `price`, `mode` effectif, `switched`, `switch_after_hours`, `deviation`, `challenge_possible`, `timeline[]` (challenge, bascule, retour) |
| `outcome` | `hf_before/after`, `liquidatable`, `liquidated`, `liquidation_profitable`, `seized_pt`, `repaid_usdc`, `bad_debt_usdc`, `equity_before/after_usd`, `borrower_loss_usd`, `lender_loss_usd`, `lgi` (perte / poche), `who_loses`, `recovered_before_horizon`, `trace[]` |
| `decision` | `p_star`, `p_default`, `verdict`, `exit_fraction`, `sentence`, `exit_cost_full`, `table[]` (pour p = 0 → 1 par pas de 0,01 : fraction optimale et verdict) |
| `contagion_paths[]` | chemins position → nœud choqué ; chaque arête = celle de graph.json + `rule` (règle de transmission) |
| `params_used[]`, `confidence` | paramètres mobilisés et niveau de confiance |

## `risk_grid.json` (curseur du front)
| Clé | Contenu |
|---|---|
| `usde_node`, `usde_price_now` | l'actif choqué et son prix au bloc |
| `prices[]`, `durations_hours[]` | axes de la grille (`null` = durable) |
| `p_grid[]` | probabilités 0 → 1 (pas 0,01) |
| `cells[i][j]` | case (prix i, durée j) : `oracle_state` (`primary` / `challenge` / `switched`), `oracle_price`, `deviation`, `hf`, `liquidated`, `liquidatable`, `borrower_loss_usd`, `lender_loss_usd`, `who_loses`, `p_star`, `verdict_default`, `fraction_by_p[]` (fraction optimale pour chaque p de `p_grid`), `status` (« LIQUIDÉ » / « prêteurs exposés » / « pas liquidé »), `sentence` |

## Garanties (vérifiées par le validateur)
- aucun NaN ni infini ; VaR95 ≤ VaR99 ; verdicts dans {STAY, PARTIAL, EXIT} ; p* ≥ 0 ;
- chaque paramètre a un statut ; une hypothèse a toujours un `why` ; une source documentaire a une URL https et une date ;
- chaque arête d'un chemin de contagion **existe dans graph.json avec la même preuve** (rien d'inventé ou de modifié en route) ;
- la grille est complète (dimensions cohérentes, une fraction pour chaque p).
