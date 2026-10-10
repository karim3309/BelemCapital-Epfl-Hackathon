# API StackTrace v2 : contrat pour le front

L'API est en **lecture seule**. Elle travaille sur des **données réelles et en direct** (Ethereum mainnet) et renvoie du JSON.
Des **réponses réelles** sont enregistrées dans [`docs/api_examples/`](api_examples/) : le front peut se construire dessus tout de suite, sans lancer le backend.

## Lancer l'API

```powershell
$env:PYTHONPATH="src"; .venv313\Scripts\python -m stacktrace.api
```

L'API répond sur `http://127.0.0.1:8000`. La documentation interactive est sur `http://127.0.0.1:8000/docs`.
Elle a besoin de `ETH_RPC_URL` dans `.env`. CORS est ouvert : le front peut l'appeler depuis le navigateur.

## Ce qu'il faut savoir avant d'appeler

- **Chaque réponse porte le `block`** auquel elle a été calculée. Toutes les réponses d'un même bloc sont cohérentes entre elles.
- **Le bloc est renouvelé toutes les 2 minutes.** Pendant ce temps, les résultats sont en cache, et un nouvel appel est instantané.
- **La première analyse est lente**, car elle fait des centaines d'appels RPC. Prévoyez un état « chargement » :

  | Route | 1er appel | Appels suivants (même bloc) |
  |---|---|---|
  | `/pockets` | ~5 s | instantané |
  | `/risk` d'une poche | ~10 à 30 s | instantané |
  | `/incident` | instantané si `/risk` a déjà été appelé | instantané |
  | `/book` (11 poches) | ~1 min 30 | instantané |

- **Les requêtes sont traitées une par une** côté serveur. Inutile d'en lancer dix en parallèle.
- **`{pocket}`** : l'`id` de la poche (`morpho_vault_v2:0xD6d4…`) **ou** son numéro `index` (1, 2, …) dans la liste `/pockets`.

## Routes

### `GET /health`
Diagnostic : bloc courant, âge du bloc, état des APIs Morpho et Pendle. `status` vaut `ok` ou `degraded`. → [exemple](api_examples/health.json)

### `GET /holders/{holder}/pockets?min_usd=1`
Les poches du détenteur. Elles sont localisées par l'API Morpho, puis **chaque montant est prouvé on-chain**. → [exemple](api_examples/pockets.json)

Champs utiles de `holdings[]` :
- `index`, `id`, `kind`, `label` ;
- `kind` vaut `morpho_vault_v2`, `morpho_market_borrow` ou `morpho_market_supply` ;
- `amount`, `asset_symbol`, `value_usd`, `share_of_book` (part du portefeuille) ;
- `evidence[]` : les preuves on-chain, à afficher en infobulle ;
- `api_gap` : écart entre la chaîne et l'API (`< 1 %` attendu).

### `GET /holders/{holder}/pockets/{pocket}/graph`
Le graphe de dépendances prouvé de la poche, au **format `graph.json` habituel** (voir [CONTRACT.md](CONTRACT.md)) : `graph.position`, `graph.nodes[]`, `graph.edges[]`.
Chaque arête a sa `source` (`onchain`, `api` ou `curated`) et sa preuve (`evidence`). → [exemple](api_examples/graph_vault.json)

Champs à mettre en avant :
- nœud `vault` : `meta.allocations[]` (part de chaque marché) et `meta.exit_liquidity` (ce qui est retirable maintenant) ;
- nœud `oracle` : `meta.pricing_mode`, qui vaut `market`, `fixed`, `internal_rate`, `hybrid` ou `unknown`. **C'est l'information de risque n° 1** : un oracle qui n'est pas `market` ne suit pas le marché ;
- nœud `issuer` avec `meta.role = vault_curator` : le curateur (RockawayX, Bitwise…).

### `GET /holders/{holder}/pockets/{pocket}/risk?horizon=7`
L'analyse complète d'une poche. → exemples : [vault](api_examples/risk_vault.json), [emprunt](api_examples/risk_borrow.json)

| Champ | Contenu |
|---|---|
| `decision.verdict` | **`STAY` ou `EXIT`** |
| `decision.exit_fraction` | part de la poche à sortir (0 → 1) |
| `decision.sentence` | la phrase à afficher au manager |
| `monte_carlo` | `expected_loss_usd` (perte attendue sur l'horizon), `var95_usd`, `var99_usd`, `var999_usd`, `p_any_loss` |
| `exit` | `f_max_now` (part sortable **maintenant**), `cost_full_usd`, `cost_full_pct`, et le détail (devis DEX, pénalité, gas…) |
| `markets[]` | pour chaque marché : `collateral_pricing`, `utilization`, `liquidity`, nombre d'emprunteurs |
| `incidents[]` | **triés par perte attendue** : `id`, `title`, `loss_if_incident_usd`, `p_horizon`, `p_star` (seuil de sortie), `rule` (la règle de calcul en clair), `contagion_path` (texte) |

### `POST /holders/{holder}/pockets/{pocket}/incident`
Le **mode incident** : « que faire si cet incident arrive ? ». → [exemple](api_examples/incident.json)

```json
{ "incident": "rwa_credit_event:mgloeuro", "severity": 0.3, "p": 0.2, "horizon": 7 }
```

- `incident` : un `incidents[].id` de `/risk`. Un début d'id suffit.
- `severity` (0 → 1) : ampleur du choc. Optionnel ; par défaut, le milieu de la plage.
- `p` (0 → 1) : la probabilité estimée **par le manager**. Optionnel.

La réponse contient `incident_mode` :
- `verdict`, `exit_fraction`, `loss_if_incident_usd` / `_pct` et **`p_star`** (« sortez si vous croyez à plus de p\* ») ;
- `sentence` : la phrase à afficher ;
- `contagion_edges[]` : les arêtes du graphe entre la position et le nœud touché, **à surligner sur le graphe**.

Elle contient aussi `baseline_decision`, la décision hors incident.

### `GET /holders/{holder}/book?horizon=7`
Tout le portefeuille. → [exemple](api_examples/book.json)

- `pockets[]` : une ligne par poche, avec verdict, perte attendue, coût de sortie, part sortable, phrase et risque principal ;
- `shared_dependencies[]` : **les dépendances communes à plusieurs poches**, c'est-à-dire la concentration cachée (par exemple Chainlink ETH/USD dans 4 poches) ;
- `skipped[]` : les poches non prises en charge, avec la raison.

## Erreurs

| Code | Quand | Contenu de `detail` |
|---|---|---|
| 404 | poche inconnue | `{error, pockets: [{index, id, label}]}`. [exemple](api_examples/error_404_pocket.json) |
| 404 | incident inconnu | `{error, incidents: [ids…]}` |
| 422 | paramètre invalide (ex. `severity` > 1), ou type de poche pas encore pris en charge | message FastAPI ou texte |
| 400 | adresse invalide | texte |
| 503 | RPC indisponible (`.env` vide, nœud en panne) | texte |
