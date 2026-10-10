# StackTrace · Module de Découverte

> Hackathon **Belem DeFi Risk** (EPFL). Le module reconstruit automatiquement le **graphe de dépendances**
> d'une position DeFi sur Ethereum mainnet. **Chaque arête est prouvée** : un appel on-chain, une API
> ou une source officielle curée. Aucune adresse ni aucun lien n'est deviné.

## Résultat : la position A

Un **PT-sUSDE-26NOV2026** (Pendle) est déposé en collatéral sur un marché **Morpho Blue**, et de l'**USDC** est emprunté en face.
Les chiffres ci-dessous sont lus au bloc **#26161750** (2026-10-10 11:31 UTC). La démo se rejoue **sans réseau**.

| | |
|---|---|
| Graphe | **28 nœuds, 45 arêtes** : 29 prouvées on-chain, 2 par API, 14 curées (URL + date) |
| Position | 413 030 PT en collatéral, dette 357 215 USDC (intérêts inclus), LTV 87,2 % / LLTV 91,5 % |
| Santé | health factor **1,050** : liquidable si le prix de l'oracle baisse de **4,75 %** |
| Oracle | **méta-oracle** Steakhouse. Le primaire est une décote linéaire seule (**fixe**). Le secours ajoute Chainlink USDe/USD (**marché**). Bascule si l'écart dépasse 0,75 % pendant 16 h |
| Liquidité de sortie | pool Pendle de 3,82 M$ pour 7,76 M$ prêtés sur le marché |

```
POSITION (value_usd=409,816.56)
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

## Démarrage rapide

Il faut Python **3.11**. Avec Anaconda, par exemple : `conda create -p .venv311 python=3.11 pip`, puis utilisez `.venv311/python`.

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

Les 67 tests tournent en ~2 s, sans réseau, et incluent la position A rejouée depuis le cache.

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
data/cache/            réponses RPC/API figées (commitées : la démo survit à une coupure réseau)
output/graph.json      le livrable pour les autres équipes
```

## Garanties anti-hallucination
- **Bloc figé** : toutes les lectures se font au même bloc, notées dans chaque preuve (`#26161750`).
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
| [docs/GUIDE_DEBUTANT.md](docs/GUIDE_DEBUTANT.md) | **commencer ici** : tout expliqué en partant de zéro |
| [CLAUDE.md](CLAUDE.md) | règles du projet + **vocabulaire figé** + conventions |
| [docs/CONTRACT.md](docs/CONTRACT.md) | **pour les autres équipes** : comment lire `graph.json` |
| [docs/POSITION_A.md](docs/POSITION_A.md) | ce qu'on a découvert sur la position A, expliqué simplement |
| [docs/VERIFY.md](docs/VERIFY.md) | **checklist à cocher par l'équipe** (adresses, fonctions, endpoints) |
| [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) | la suite, la répartition à 3, et les **prompts prêts à lancer** |
| [docs/AUDIT.md](docs/AUDIT.md) | journal des audits et limites connues |
