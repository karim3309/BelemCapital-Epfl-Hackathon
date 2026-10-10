# Contrat `graph.json` : guide pour les équipes consommatrices

Fichier : [`output/graph.json`](../output/graph.json). Il est validé à chaque build par `src/discovery/validate.py`.
Le vocabulaire (types, sources, modes de prix) est **figé** dans `src/discovery/vocab.py`.

## Structure (stricte : aucune autre clé)
```json
{
  "position": {"id": "morpho:<marketId>:<user>", "value_usd": 409816.56},
  "nodes": [{"id": "...", "type": "...", "label": "...", "address": "0x… | null", "chain": "ethereum | null", "meta": {}}],
  "edges": [{"from": "...", "to": "...", "type": "...", "weight": 1.0, "source": "onchain|api|curated", "evidence": "..."}]
}
```

## Les 4 règles à connaître
1. **Direction :** `from` = celui qui dépend, `to` = sa dépendance. Une panne se propage **de `to` vers `from`**. Pour « qui est touché si X casse », prenez les **ancêtres** de X (`networkx.ancestors`).
2. **La racine n'est pas un nœud :** c'est `position.id`. Elle apparaît uniquement comme `from` de l'arête `deployed_in` vers le marché.
3. **`weight` ∈ [0, 1]** = part de l'exposition du `from` qui passe par l'arête. Il vaut 1.0 quand le lien est total, et aussi quand la part est inconnue (borne haute conservatrice, mentionnée dans `evidence`).
4. **Une valeur `null` signifie « non prouvé »**, jamais « zéro ». Exemple : `tvl_usd: null` = aucun prix prouvable.

## Types de nœuds et `meta` utiles au risque
| type | `meta` clés (non exhaustif) |
|---|---|
| `lending_market` | `market_id`, `lltv`, `utilization`, `borrow_apy`, `total_supply_human`, `total_borrow_human`, `available_liquidity_human`, `tvl_usd`, **`position`** (`collateral_human`, `borrow_human`, `ltv`, `health_factor`, `oracle_drop_to_liquidation`, `net_value_usd`) |
| `oracle` | `oracle_kind`, **`pricing_mode`** (`market`/`fixed`/`internal_rate`/`hybrid`/`unknown`), `price`. Pour un méta-oracle : `primary_oracle`, `backup_oracle`, `current_role`, `effective_pricing_mode`, `deviation_threshold`, `challenge_timelock_seconds`, `switch_rule`. Pour MorphoChainlinkOracleV2 : `components`, `implicit_unit_slots`, `price_recomputed_matches`. Pour un feed : `answer`, `age_seconds`, `priced_asset` |
| `asset` | `asset_kind` (`pendle_pt`/`pendle_sy`/`erc4626_vault`/`erc20`), `symbol`, `decimals`, `total_supply_human`, `price_usd`, `price_usd_source`, `tvl_usd`. PT : `expiry_iso`, `days_to_expiry`. ERC-4626 : `share_to_asset_rate`, `cooldown_seconds`. SY : `accounting_asset` |
| `liquidity_venue` | `reserve_pt`, `reserve_sy`, `implied_apy`, `tvl_usd`, `pt_price_implied_by_amm`, `pt_price_morpho_oracle`, `oracle_vs_amm_gap` |
| `vault` | `vault_version`, `asset`, `curator`, `owner`, `tvl_usd` |
| `issuer` / `offchain_counterparty` | `role` (`custodian_off_exchange_settlement`, `hedging_venue`), `evidence_url`, `as_of` |
| `chain` | `chain_id`, **`snapshot_block`**, `snapshot_time_iso` (toutes les lectures sont faites à ce bloc) |
| tout contrat | `proxy` : `{detected, standard, implementation, upgradeable}`. `upgradeable: null` = non prouvé |

## Types d'arêtes
| type | from → to | lecture |
|---|---|---|
| `deployed_in` | position/vault/asset/issuer → marché/pool/contrepartie | « mes fonds sont placés dans » |
| `collateralized_by` | marché → actif | « je suis garanti par » |
| `lends` | marché → actif | « je prête cet actif » (extension en attente de validation) |
| `priced_by` | marché/oracle → oracle/pool/actif | « ma valeur est calculée par » |
| `redeemable_into` | actif → actif | « je peux être échangé contre » |
| `issued_by` | actif/oracle/pool/marché/vault → émetteur | « je suis émis / contrôlé par » |
| `settled_on` | contrat → chaîne | « je m'exécute sur » |

## Charger le graphe
```python
import json
from discovery.graph import to_networkx
import networkx as nx

graph = json.load(open("output/graph.json", encoding="utf-8"))
g = to_networkx(graph)                       # MultiDiGraph, clé d'arête = type
impacted = nx.ancestors(g, "usde")           # tout ce qui dépend de l'USDe
oracles = [n for n, d in g.nodes(data=True) if d.get("type") == "oracle"]
```

## Exemple de preuve par source
- `onchain` : `PT-sUSDE-26NOV2026.SY() = 0xBF98… @ 0xB195… #26161750` (contrat, fonction, résultat, adresse, bloc).
- `api` : `API Morpho https://api.morpho.org/graphql marketById(…).supplyingVaultV2s contient 0x55C1… (fetched 2026-10-10T…)`
- `curated` : `USDe Token = 0x4c9E… selon https://docs.ethena.fi/solution-design/key-addresses (relevé le 2026-10-10)`
