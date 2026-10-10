# StackTrace · dépendances et risque d'une position DeFi

> Hackathon **Belem DeFi Risk** (EPFL). Une position DeFi en entrée, une **fiche de risque actionnable** en sortie :
> 1. **Découverte** : le graphe de dépendances, chaque arête **prouvée** (on-chain, API ou source officielle curée) ;
> 2. **Impact** : un moteur qui propage un choc dans ce graphe jusqu'à la position, en $ ;
> 3. **Décision** : STAY / PARTIAL x % / EXIT, avec le seuil de probabilité **p\*** du brief ;
> 4. **Front** (`front/`) : un deck de diapositives qui montre tout ça, poche par poche.
>
> Aucune adresse, aucun lien, aucun paramètre n'est deviné.

## La fiche de risque en 30 secondes (bloc #26162087)
| | |
|---|---|
| Alerte (scénario de démo du cadrage) | **USDe −30 % durable** : l'oracle bascule après 16 h, la position est liquidée, **−53 133 $** (tout le capital) et **−77 723 $ pour les prêteurs** |
| Coût certain de sortie | **854 $**, mesuré on-chain (simulation de vente sur le vrai pool Pendle) |
| Seuil | **p\* = 1,6 %** → « est-ce que je crois à plus de 1,6 % de chances que ça arrive cette semaine ? » |
| Sans alerte (Monte Carlo, 200 000 semaines) | perte attendue ≈ 131 $/7 j, VaR 95 % = 0 $, ES 99 % ≈ 13 k$ → **STAY** |
| Le piège de cette position | la **durée** : USDe à 0,93 $ pendant 6 h = 0 $ de perte ; pendant 24 h = liquidation (−37 k$) |
| Le risque caché | exploit Pendle : l'oracle fixe ne voit rien → **152 k$ de dette irrécouvrable chez les prêteurs** |
| Replay réel | 10/10/2025 : USDe à 0,65 $ sur Binance. Notre oracle tient ; un oracle sur le prix Binance nous liquidait |

Le détail est dans [docs/PARTS_2_3.md](docs/PARTS_2_3.md) (brief → ce qu'on a fait → où) et le format dans
[docs/RISK_CONTRACT.md](docs/RISK_CONTRACT.md).

## Résultat : la position A

Un **PT-sUSDE-26NOV2026** (Pendle) est déposé en collatéral sur un marché **Morpho Blue**, et de l'**USDC** est emprunté en face.
Les chiffres ci-dessous sont lus au bloc **#26162087** (2026-10-10 12:39 UTC). La démo se rejoue **sans réseau**.

| | |
|---|---|
| Graphe | **28 nœuds, 45 arêtes** : 29 prouvées on-chain, 2 par API, 14 curées (URL + date) |
| Position | 413 030 PT en collatéral, dette 357 217 USDC (intérêts inclus), LTV 87,2 % / LLTV 91,5 % |
| Santé | health factor **1,050** : liquidable si le prix de l'oracle baisse de **4,75 %** |
| Oracle | **méta-oracle** Steakhouse. Le primaire est une décote linéaire seule (**fixe**). Le secours ajoute Chainlink USDe/USD (**marché**). Bascule si l'écart dépasse 0,75 % pendant 16 h |
| Liquidité de sortie | pool Pendle de 3,82 M$ pour 7,76 M$ prêtés sur le marché |

```
POSITION (value_usd=409 819,73)
└─ deployed_in ⛓ → morpho_market_5613b170 [lending_market] Morpho Blue PT-sUSDE-26NOV2026 / USDC (LLTV 91.5%)
   ├─ collateralized_by ⛓ → pt_susde_26nov2026 [asset]
   │  ├─ deployed_in ⛓ → pendle_plp_susde_26nov2026 [liquidity_venue]   (pool AMM, TVL 3,8 M$)
   │  ├─ issued_by 📄 → pendle
   │  └─ redeemable_into ⛓ → sy_susde → redeemable_into ⛓ → susde → redeemable_into ⛓ → usde
   │                                                    └─ issued_by 📄 → ethena_labs ─ deployed_in 📄 → copper, ceffu,
   │                                                                                     fireblocks, binance, bybit, okx…
   ├─ lends ⛓ → usdc ─ issued_by 📄 → circle
   └─ priced_by ⛓ → oracle_meta_f8b29e (hybrid, effectif : fixed)
      ├─ priced_by ⛓ → oracle_morpho_v2_8fca98 (fixed)  ─ priced_by ⛓ → feed décote linéaire PT (6 %/an)
      └─ priced_by ⛓ → oracle_morpho_v2_e2f4cf (market) ─ priced_by ⛓ → feed décote linéaire PT
                                                         ├─ priced_by ⛓ → feed_usde_usd ─ issued_by ⛓ (ENS) → chainlink
                                                         └─ priced_by ⛓ → feed constant « Dummy » (USDC = 1)
⛓ onchain · 🌐 api · 📄 curated          (+ chaque contrat --settled_on--> ethereum)
```

Pour l'explication complète, couche par couche, et les scénarios de depeg chiffrés : [docs/POSITION_A.md](docs/POSITION_A.md).

## Moteur de risque de la position A (hors ligne)
```bash
PYTHONPATH=src python -m risk.run
```
`risk.run` lit `output/graph.json` et `output/risk_inputs.json` (hors ligne) et écrit `output/risk_report.json` et
`output/risk_grid.json`. **Ne supprimez pas `output/`** : ce sont les entrées du moteur et des tests.

Pour **rafraîchir toute la photo** (découverte + lectures du moteur, au même bloc), en ligne : `PYTHONPATH=src python -m risk.refresh`.

## Backend v2 : n'importe quel détenteur réel, en ligne → STAY / EXIT

La v2 part de **l'adresse d'un détenteur réel** (ex. le vault Belem RWA EURCV du tableau Dune RockawayX). Elle trouve
toutes ses poches, construit le graphe prouvé de chacune, chiffre l'impact des incidents, mesure le coût de sortie et
rend un verdict **STAY / EXIT** avec le seuil **p\***. Une API HTTP est fournie pour le front.
→ [docs/BACKEND_V2.md](docs/BACKEND_V2.md) (pipeline, modèle, limites) · [docs/API.md](docs/API.md) (contrat de l'API + exemples réels)

## Front en diapositives : le backend v2 à l'écran (`front/`)

Un deck de 7 diapositives qui suit les questions de Léa à 3 h du matin : le portefeuille, **le verdict STAY / EXIT** de
chaque poche (en très grand), par quel chemin je suis exposée (graphe prouvé, preuve de chaque arête au clic), combien je
peux perdre, combien coûte la sortie, et le mode incident (« croyez-vous à plus de p\* ? »), puis la concentration cachée
du portefeuille. ← → change de poche, ↑ ↓ change de question. Le front **ne calcule aucun risque** : il lit l'API.

```bash
cd front && npm install && npm run dev        # http://localhost:5173
```

- **Sans backend** : il démarre sur les réponses réelles enregistrées dans `docs/api_examples/` (mainnet, bloc #26162868).
  Aucun réseau requis.
- **En direct** : lancez l'API (`PYTHONPATH=src python -m stacktrace.api`, avec `ETH_RPC_URL` dans `.env`) ; le front la
  détecte et propose de passer en direct. Ou `http://localhost:5173/?source=live`.

Détails, architecture et serveur de rejeu : [front/README.md](front/README.md).

## Démarrage rapide

Il faut Python **3.11**. Avec Anaconda, par exemple : `conda create -p .venv311 python=3.11 pip`, puis utilisez `.venv311/python`.

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

Les tests (découverte + moteur de risque + backend v2 + API) tournent en ~10 s, sans réseau, et incluent la position A rejouée depuis le cache.

**Démo hors ligne** (aucun appel réseau, tout vient de `data/cache/`). Sous PowerShell :

```powershell
$env:PYTHONPATH="src"; python -m discovery.build_graph --offline
```

Sous bash :

```bash
PYTHONPATH=src python -m discovery.build_graph --offline
```

Explorer le graphe :

```bash
PYTHONPATH=src python -m discovery.inspect_graph
```

```bash
PYTHONPATH=src python -m discovery.inspect_graph --impact usde
```

```bash
PYTHONPATH=src python -m discovery.validate output/graph.json
```

`--impact` répond à « qui est touché si USDe casse, et par quel chemin ? ». `--evidence` affiche la preuve de chaque arête.
Avec `pip install -e .`, `PYTHONPATH=src` devient inutile.
Sous Windows, si vous clonez dans un dossier très profond, lancez d'abord `git config --global core.longpaths true`.

### Rafraîchir les données (en ligne)
1. `cp .env.example .env`, puis mettez votre `ETH_RPC_URL` (Ethereum mainnet).
2. Dans `config.yaml`, mettez `snapshot_block: latest`, puis lancez `python -m discovery.build_graph`.
3. Recopiez le numéro de bloc affiché dans `config.yaml` pour figer. Relancez `--offline`, puis commitez `data/cache/` et `output/graph.json`.

> Un RPC public non-archive ne répond qu'aux ~128 derniers blocs. Pour figer un bloc ancien, il faut un RPC **archive**.

## Architecture

```
config.yaml            entrées de la découverte (marketId, user, contrats d'entrée), chacune avec sa source
curated.yaml           le hors-chaîne vérifiable (émetteurs, custodians, exchanges), chaque ligne avec URL + date
src/discovery/
  vocab.py             vocabulaire FIGÉ (types de nœuds/arêtes, sources, modes de prix, formes autorisées)
  config.py            chargement + garde-fous (refuse les adresses placeholder)
  cache.py  rpc.py     cache disque branché AU NIVEAU DU PROVIDER web3 → aucun appel ne peut l'éviter
  http.py              APIs (Morpho GraphQL, Pendle) via le même cache
  ctx.py               la seule porte vers la chaîne : call / try_call (sondes) / preuve textuelle
  graph.py  ids.py     modèle de graphe, ids déterministes, export au contrat JSON
  validate.py          validateur strict du contrat (structure + rigueur des preuves + connexité)
  valuation.py         price_usd / tvl_usd à partir des seuls prix prouvés on-chain
  build_graph.py       orchestrateur : racine Morpho → exploration en largeur → passes finales
  inspect_graph.py     arbre + analyse d'impact (networkx)
  adapters/
    morpho.py          marché (hash des params recalculé), position, intérêts courus, santé
    morpho_api.py      vaults qui prêtent au marché (API Morpho, relus on-chain)
    oracles.py         méta-oracle, MorphoChainlinkOracleV2 (prix recalculé), décote linéaire, Chainlink, feed constant
    pendle.py          PT → SY → yieldToken ; pool localisé par API puis PROUVÉ on-chain
    erc20.py erc4626.py  classification par sondage, coffres à parts
    ens.py             résolution ENS (prouve qu'un feed est un feed officiel Chainlink)
    contracts.py       détection des proxies (EIP-1167, EIP-1967, ZeppelinOS)
    chain.py           settled_on (eth_chainId + eth_getCode)
    curated.py         chargeur strict de curated.yaml
src/risk/              MOTEUR DE RISQUE (parties 2 et 3) — ne lit que graph.json + risk_inputs.json
  collect.py refresh.py   lectures on-chain du moteur (devis de vente Pendle, historique Chainlink, gas) au même bloc
  params.py               chargeur STRICT de risk/params.yaml (statut sourcé / on-chain / hypothèse obligatoire)
  calibrate.py            historique Chainlink USDe/USD → fréquence et ampleur des depegs
  propagate.py            une règle de transmission par type d'arête (dominos)
  oracle_sim.py           ce que l'oracle affiche pendant le choc (méta-oracle : seuil + minuterie 16 h)
  position.py             santé, liquidation (bonus Morpho sourcé), pertes emprunteur / prêteurs
  exit_cost.py decide.py  coût de sortie mesuré, seuil p*, sortie partielle, verdict
  montecarlo.py           200 000 semaines simulées → perte attendue, VaR, chemins les plus coûteux
  replay.py               incidents réels rejoués (10/10/2025, 21/02/2025)
  run.py                  rapport + grille + validateur
risk/                  params.yaml, scenarios.yaml, replays.yaml (tout chiffre a un statut)
front/                 front en diapositives (React), lit l'API v2 ou ses réponses enregistrées
data/cache/            réponses RPC/API figées (commitées : la démo survit à une coupure réseau)
output/                graph.json (découverte), risk_inputs.json, risk_report.json, risk_grid.json
```

## Garanties anti-hallucination
- **Bloc figé** : toutes les lectures se font au même bloc, notées dans chaque preuve (`#26162087`).
- **Recalculs** : l'ID du marché est recalculé (`keccak256(MarketParams)`). Le prix de chaque `MorphoChainlinkOracleV2` est recalculé à partir de ses briques, de même que la formule de décote linéaire et les intérêts courus (écart de 0,0001 % avec l'API Morpho).
- **Provenance on-chain** :
  - les sous-oracles sont confirmés par la factory officielle (`isMorphoChainlinkOracleV2`) ;
  - le pool Pendle par sa factory (`isValidMarket`) ;
  - le feed USDe/USD par ENS (`usde-usd.data.eth`).
- **Inconnu = signalé** : un contrat non reconnu devient `meta.unresolved = true`, jamais deviné.
- **Curé = sourcé** : `curated.yaml` refuse toute ligne sans URL https ni date.
- **Validateur** : le contrat JSON est vérifié à chaque build (structure, vocabulaire, formes d'arêtes, preuves, connexité).

## Documentation
| Fichier | Pour qui / quoi |
|---|---|
| [docs/PARTS_2_3.md](docs/PARTS_2_3.md) | parties 2 et 3 : brief → ce qu'on a fait → où c'est |
| [docs/RISK_CONTRACT.md](docs/RISK_CONTRACT.md) | format de `risk_report.json` / `risk_grid.json` |
| [docs/DEMO.md](docs/DEMO.md) | **script de démo de 5 minutes** (PowerShell et bash) |
| [front/README.md](front/README.md) | le front en diapositives (lancement, sources de données, architecture) |
| [docs/GUIDE_DEBUTANT.md](docs/GUIDE_DEBUTANT.md) | **commencer ici** : tout expliqué en partant de zéro |
| [CLAUDE.md](CLAUDE.md) | règles du projet + **vocabulaire figé** + conventions |
| [docs/CONTRACT.md](docs/CONTRACT.md) | **pour les autres équipes** : comment lire `graph.json` |
| [docs/POSITION_A.md](docs/POSITION_A.md) | ce qu'on a découvert sur la position A, expliqué simplement |
| [docs/VERIFY.md](docs/VERIFY.md) | **checklist à cocher par l'équipe** (adresses, fonctions, endpoints) |
| [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) | la suite, la répartition à 3, et les **prompts prêts à lancer** |
| [docs/AUDIT.md](docs/AUDIT.md) | journal des audits et limites connues |
| [docs/AUDIT_BRIEF.md](docs/AUDIT_BRIEF.md) | **audit face au brief Belem et au barème** : notes estimées, failles, plan d'action priorisé |
