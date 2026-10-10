# Parties 2 et 3 : ce que demande le brief, ce qu'on a fait, où c'est

Sources : le brief Belem (`docs/BelemCapital_EPFL-Hackathon_DeFi-Risk-Dependency-Challenge_EN_v1.pdf`) et la
note de cadrage de l'équipe (`docs/Belem DeFi Risk — Cadrage & Guideline.pdf`).
Barème du brief : **Découverte 30 %** (partie 1, déjà faite) · **Estimation d'impact 30 %** (partie 2) ·
**Utilité de la décision 25 %** (partie 3) · **Démo sur données réelles 15 %**.

---

## Partie 2 : estimation d'impact (« le nombre est-il défendable ? »)

| Ce que demandent le brief et le cadrage | Ce qu'on a fait | Où |
|---|---|---|
| Des scénarios par nœud : exploit, depeg, panne/manipulation d'oracle, gel de liquidité, arrêt de chaîne | **15 scénarios de stress** : depeg USDe (3 variantes), faillite d'exchange (1 ou 3), custodian, feed faux, feed figé, pool ÷2 et ÷10, depeg USDC, exploit Pendle, exploit Morpho, arrêt d'Ethereum, passage du temps. Plus une **grille de 228 cas** (prix USDe × durée) | `risk/scenarios.yaml`, `src/risk/scenarios.py` |
| Une règle de transmission par type d'arête, **écrite en clair** | `redeemable_into` (la valeur suit le sous-jacent), `issued_by` (perte de réserves, sans double comptage), `deployed_in` (part exposée à la contrepartie), `priced_by` (transmis seulement si l'oracle suit le marché), `collateralized_by` / `lends` (effet sur la santé) | `src/risk/propagate.py` (`RULES`) |
| « Collatéral qui chute + oracle qui suit le marché → liquidation, perte = bonus + slippage » | simulateur d'oracle + liquidation avec le **bonus de liquidation officiel de Morpho** (formule sourcée). Le liquidateur n'agit que si c'est rentable **après glissement mesuré on-chain** | `src/risk/oracle_sim.py`, `src/risk/position.py` |
| « Collatéral qui chute + oracle fixe → pas de liquidation → dette résiduelle chez les prêteurs » | calculé et affiché : l'exploit Pendle (SY −50 %) laisse **152 k$** de trou chez les prêteurs, sans aucune liquidation | scénario `S-PENDLE-EXPLOIT` |
| Le méta-oracle (spécifique à notre position) | règle de bascule **sourcée** (doc Steakhouse) et **paramètres lus on-chain** (seuil 0,75 %, délai 16 h, retour 24 h). La durée du choc décide de tout | `oracle_sim._meta` |
| Calibration sur l'historique d'incidents | **historique complet on-chain** du feed Chainlink USDe/USD (960 rounds depuis 04/2024) : pire écart 2,3 % (21/02/2025), 1 épisode sous 0,99 $ en ~2,5 ans. Le dataset de hacks DeFiLlama est **payant** : les fréquences d'exploit sont des **hypothèses affichées** | `src/risk/calibrate.py`, `risk/params.yaml` |
| Monte Carlo avec corrélation via les parents communs → perte attendue, VaR 95 %, chemin le plus coûteux | 200 000 semaines simulées (graine fixe). Les événements qui touchent le même nœud se cumulent sur lui puis sur ses dépendants. Sorties : perte attendue, **VaR 95/99**, ES 99, P(liquidation), **top 3 des chemins** (avec preuves) | `src/risk/montecarlo.py` |
| « Hypothèses visibles et sourcées, sensibilité affichée » | **chaque** paramètre a un statut (sourcé / on-chain / hypothèse), sinon le chargeur refuse. **Tornade de sensibilité** sur chaque hypothèse | `src/risk/params.py`, `report.sensitivity` |
| Pas de « score magique 0-100 » | aucun score : seulement des $, des %, un seuil p* | — |

## Partie 3 : utilité de la décision (« stay or exit, and why »)

| Ce que demandent le brief et le cadrage | Ce qu'on a fait | Où |
|---|---|---|
| Exit si p·LGI·V > C_exit ⇔ p > **p\*** = C_exit / (LGI·V) | p\* calculé pour chaque scénario et chaque case de la grille | `src/risk/decide.py` |
| C_exit = slippage sur la **vraie liquidité** + gas + rendement abandonné | glissement **simulé on-chain** (Pendle RouterStatic `swapExactPtForSyStatic`, 16 tailles), gas (base fee du bloc × ETH/USD Chainlink), rendement abandonné (APY du PT − coût d'emprunt). La conversion vers USDC est une hypothèse affichée | `src/risk/exit_cost.py`, `src/risk/collect.py` |
| **Sortie partielle** : marginal slippage = marginal expected loss | optimisation de la fraction f qui minimise C_exit(f) + p·Perte·(1−f), pour chaque p de 0 à 100 % | `decide.best_fraction`, `decision_table` |
| Verdict STAY / PARTIAL x % / EXIT, en une phrase | pour chaque scénario + un verdict « sans alerte » (Monte Carlo) + un verdict principal (alerte du cadrage : depeg −30 %) | `report.headline`, `report.baseline` |
| Les 3 chemins de contagion les plus coûteux, dessinés sur le graphe | `monte_carlo.top_paths` (arêtes de graph.json avec leurs preuves), dessinés en fracture dans le front | front, mode squelette |
| Liste des hypothèses avec source + niveau de confiance | `report.params`, `report.confidence` (p* : moyenne à élevée ; perte attendue : faible, dit franchement) | fiche de risque |

## Démo sur données réelles (15 %)

| Demandé | Fait |
|---|---|
| Adresses mainnet réelles, appels live avec cache | tout le graphe + les lectures du moteur sont faits au **même bloc** (#26162087), mis en cache, puis rejoués hors ligne (`python -m risk.refresh`, puis `risk.run`) |
| Replay d'un vrai incident | **10 octobre 2025** (plan B du cadrage) : USDe à 0,65 $ sur Binance pendant ~40 min (source curée), on-chain ≥ 0,9929 $ (lu sur Chainlink). Notre oracle tient, un oracle branché sur Binance nous liquidait. Bonus : 21 février 2025 |
| Une app qui tourne | front en diapositives (`front/`), sur l'API v2 ou ses réponses enregistrées |

## Ce qui n'est PAS fait (et pourquoi)
- **Replay xUSD / deUSD (novembre 2025)** : il faudrait retrouver un vault exposé et ses allocations d'avant la crise (blocs historiques, donc un RPC archive). Plan B du cadrage réalisé à la place.
- **Position B (vault Morpho curé) et vue « book 10 poches »** : bonus du cadrage, non commencés (voir `NEXT_STEPS.md`).
- **Probabilités d'exploit calibrées sur DeFiLlama** : dataset payant. Alternatives possibles : rekt.news ou un export manuel sourcé.
