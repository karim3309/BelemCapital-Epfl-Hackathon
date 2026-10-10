# Journal d'audit

Méthode : après chaque tâche, on relit **tout le projet** au regard des consignes (`CLAUDE.md`) et du plan,
on corrige, puis on recommence jusqu'à ce que l'audit ne trouve plus rien d'important.

## Audit 1 : après la première découverte complète
| Constat | Correction |
|---|---|
| Crash sur `latestRoundData` : les types de retour étaient passés comme arguments | helper `latest_round()` + tests de feeds |
| Preuve « `Contract.readTokens()` » : le nom du pool Pendle n'était pas étiqueté | labels `PendleMarket` / `PendleMarketFactory`, et preuve `isValidMarket` générée par `ctx.ev` |
| Position vide détectée **après** des calculs inutiles | contrôle déplacé avant le calcul |
| Une API en panne faisait tomber toute la découverte | les tâches API se dégradent proprement (note ⚠) ; les erreurs on-chain restent fatales |

## Audit 2 : code complet vs consignes
| Constat | Correction |
|---|---|
| **Dette sous-estimée** : Morpho ne met à jour les intérêts qu'à chaque interaction (`lastUpdate` vieux de 45 h) | accumulation via `IRM.borrowRateView` + `wTaylorCompounded`, comme Morpho. Recoupement avec l'API Morpho : 0,0001 % d'écart |
| `meta.tvl_usd` (montré dans l'exemple du contrat) absent | `valuation.py` : prix **uniquement** issus de données prouvées. Recoupement : TVL du pool 3,820 M$ contre 3,820 M$ pour l'API Pendle |
| `ctx` filtrait les erreurs par **nom** de classe ; les signatures avec tuples n'étaient pas gérées | exceptions typées ; analyse des types de 1er niveau (tuples) |
| networkx sous-utilisé (consigne de la stack) | `inspect_graph.py` : arbre, analyse d'impact (`ancestors`), test d'acyclicité |
| **Affirmation non sourcée** sur la règle de bascule du méta-oracle | règle réécrite d'après la doc officielle Steakhouse (URL dans `meta.switch_rule_source`). Pas d'arête `issued_by` vers Steakhouse : la factory n'est pas publiée, donc le lien n'est pas prouvé |
| Proxies vérifiés pour les tokens et les oracles seulement | vérification de **tous** les contrats ; « non détecté » ≠ « immuable » (`upgradeable: null`) |
| Fins de ligne CRLF (Windows) dans le cache | écriture en LF + `.gitattributes` |

## Audit 3 : conformité finale à `CLAUDE.md`
| Exigence | Statut | Où |
|---|---|---|
| Python 3.11, web3.py, requests, networkx | ✅ | `requirements.txt`, `pyproject.toml` |
| Adaptateurs dans `src/discovery/adapters/` (`pendle`, `morpho`, `oracles`, `erc4626`…) + `build_graph.py` + `curated.yaml` | ✅ | arborescence |
| **Tous** les appels RPC et API cachés dans `data/cache/`, démo hors réseau | ✅ cache **au niveau du provider** (aucun contournement possible) ; rejeu hors ligne identique à l'octet ; testé | `rpc.py`, `http.py`, `test_position_a_offline.py` |
| Sortie = `graph.json` au contrat figé | ✅ validateur strict à chaque build et en test | `validate.py` |
| Nœuds autorisés uniquement | ✅ 8 types | `vocab.py` |
| Arêtes autorisées uniquement | ⚠ 6 types + l'extension `lends` ; `collateralized_by` = « est collatéral de » inversé | décision à prendre avec les organisateurs (`NEXT_STEPS.md`, étape 0) |
| Chaque arête : `source` + preuve concrète | ✅ format vérifié par le validateur (adresse + bloc pour onchain, URL pour api/curated) | `validate.py` |
| Aucune adresse ni endpoint de mémoire | ✅ toutes les adresses sont soit **découvertes on-chain**, soit relevées dans une doc officielle avec URL (`config.yaml`, `curated.yaml`). Checklist pour l'équipe | `docs/VERIFY.md` |
| Pédagogie : concepts expliqués, petites tâches testables | ✅ docstrings pédagogiques dans chaque module ; 67 tests unitaires et d'intégration | `docs/POSITION_A.md` |

## Audit 4 : simulation d'un coéquipier (clone neuf, sans `.env`, sans réseau)
| Constat | Correction |
|---|---|
| Dans un dossier profond, le chemin d'un fichier de cache dépassait **260 caractères** (MAX_PATH Windows) : le cache devenait invisible | préfixe `\?\` sous Windows dans `cache.py` ; re-test du clone neuf : 67 tests verts, 0 miss, `graph.json` identique à l'octet |
| `validate` plantait dans une console Windows (encodage cp1252) ; les erreurs attendues s'affichaient en trace brute | `console.utf8_console()` pour les 3 CLI ; messages `✗ OfflineError : …` et code de sortie 2 |

## Audit 5 : moteur de risque (parties 2 et 3) — étapes (a) et (b)
| Constat | Correction |
|---|---|
| Le RPC public ne sert que les ~128 derniers blocs : les nouvelles lectures (simulations Pendle, historique Chainlink) étaient impossibles au bloc figé #26161750 | commande unique `python -m risk.refresh` (découverte + lectures du moteur au MÊME bloc, en 30 s) ; données rafraîchies au bloc #26162087, code de découverte inchangé |
| Dataset de hacks DeFiLlama : endpoint **payant** (`pro-api.llama.fi/api/hacks`, doc officielle), page web bloquée | aucune probabilité « inventée » présentée comme calibrée : les fréquences d'exploit sont des **hypothèses affichées**, la décision repose sur **p\*** (indépendant de ces fréquences), sensibilité ×0,5/×2 dans le rapport |
| Fréquence de depeg USDe calibrée sur l'historique on-chain (1 épisode sous 0,99 $ en ~2,5 ans, 7 min, −2,3 %) mais appliquée à des sévérités bien plus fortes | séparation en `usde_market_depeg` (fréquence, sévérité ET durée calées sur l'historique) et `usde_severe_depeg` (queue de distribution = hypothèse explicite) |
| S-TIME ignorait que le PT converge vers 1 à l'échéance (perte affichée = intérêts) | valorisation du PT « mûrie » au taux implicite de l'AMM → gain de ~855 $ d'ici l'échéance |
| Test des seuils : j'avais écrit seuil = u_now / HF (faux) | le moteur avait raison : après bascule HF = HF₀ × prix USDe, donc seuil = 1/HF₀ = 0,9525 $ (identique à POSITION_A.md) |
| Résumé console : « ok » affiché pour une position liquidable mais non liquidée (exploit Morpho, collatéral nul) | libellé « liquidable » |

## Limites connues (à assumer ou à traiter, voir `NEXT_STEPS.md`)
- **Vocabulaire :** `lends` et la convention de direction sont en attente de validation officielle.
- **`value_usd`** = collatéral au prix de l'oracle (la valeur nette est donnée dans `meta.position.net_value_usd`). Définition à confirmer avec les équipes aval.
- **Poids hors chaîne inconnus :** les arêtes Ethena → custodians / exchanges ont `weight = 1.0` (borne haute, dit dans la preuve). Les listes d'Ethena sont des exemples (« such as »).
- **Méta-oracle :** lien avec la factory Steakhouse non prouvé on-chain.
- **Feed TWAP Pendle :** les sondes (`market()`, `twapDuration()`) n'ont pas été vérifiées sur un vrai contrat (absent de la position A).
- **Proxies :** seuls EIP-1167, EIP-1967 (+ beacon) et ZeppelinOS sont détectés. « Non détecté » ne veut pas dire immuable.
- **RPC non-archive :** rafraîchir les données impose `snapshot_block: latest`, puis de figer le bloc (procédure dans `NEXT_STEPS.md`).
- **Racine :** seules les positions Morpho Blue sont supportées comme point de départ.
- **Fraîcheur :** `age_seconds` des feeds est fourni, mais pas comparé à un heartbeat sourcé.
