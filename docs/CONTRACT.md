# `graph.json` contract: guide for consuming teams

File: [`output/graph.json`](../output/graph.json). It is validated at every build by `src/discovery/validate.py`.
The vocabulary (types, sources, pricing modes) is **frozen** in `src/discovery/vocab.py`.

## Structure (strict: no other key)
```json
{
  "position": {"id": "morpho:<marketId>:<user>", "value_usd": 409816.56},
  "nodes": [{"id": "...", "type": "...", "label": "...", "address": "0x… | null", "chain": "ethereum | null", "meta": {}}],
  "edges": [{"from": "...", "to": "...", "type": "...", "weight": 1.0, "source": "onchain|api|curated", "evidence": "..."}]
}
```

## The 4 rules to know
1. **Direction:** `from` = the one that depends, `to` = its dependency. A failure propagates **from `to` to `from`**. For "who is hit if X breaks", take the **ancestors** of X (`networkx.ancestors`).
2. **The root is not a node:** it is `position.id`. It only appears as the `from` of the `deployed_in` edge to the market.
3. **`weight` ∈ [0, 1]** = share of the `from`'s exposure that goes through the edge. It is 1.0 when the link is total, and also when the share is unknown (conservative upper bound, mentioned in `evidence`).
4. **A `null` value means "not proven"**, never "zero". Example: `tvl_usd: null` = no provable price.

## Node types and `meta` useful for risk
| type | key `meta` fields (not exhaustive) |
|---|---|
| `lending_market` | `market_id`, `lltv`, `utilization`, `borrow_apy`, `total_supply_human`, `total_borrow_human`, `available_liquidity_human`, `tvl_usd`, **`position`** (`collateral_human`, `borrow_human`, `ltv`, `health_factor`, `oracle_drop_to_liquidation`, `net_value_usd`) |
| `oracle` | `oracle_kind`, **`pricing_mode`** (`market`/`fixed`/`internal_rate`/`hybrid`/`unknown`), `price`. For a meta-oracle: `primary_oracle`, `backup_oracle`, `current_role`, `effective_pricing_mode`, `deviation_threshold`, `challenge_timelock_seconds`, `switch_rule`. For MorphoChainlinkOracleV2: `components`, `implicit_unit_slots`, `price_recomputed_matches`. For a feed: `answer`, `age_seconds`, `priced_asset` |
| `asset` | `asset_kind` (`pendle_pt`/`pendle_sy`/`erc4626_vault`/`erc20`), `symbol`, `decimals`, `total_supply_human`, `price_usd`, `price_usd_source`, `tvl_usd`. PT: `expiry_iso`, `days_to_expiry`. ERC-4626: `share_to_asset_rate`, `cooldown_seconds`. SY: `accounting_asset` |
| `liquidity_venue` | `reserve_pt`, `reserve_sy`, `implied_apy`, `tvl_usd`, `pt_price_implied_by_amm`, `pt_price_morpho_oracle`, `oracle_vs_amm_gap` |
| `vault` | `vault_version`, `asset`, `curator`, `owner`, `tvl_usd` |
| `issuer` / `offchain_counterparty` | `role` (`custodian_off_exchange_settlement`, `hedging_venue`), `evidence_url`, `as_of` |
| `chain` | `chain_id`, **`snapshot_block`**, `snapshot_time_iso` (all reads are made at this block) |
| any contract | `proxy`: `{detected, standard, implementation, upgradeable}`. `upgradeable: null` = not proven |

## Edge types
| type | from → to | reading |
|---|---|---|
| `deployed_in` | position/vault/asset/issuer → market/pool/counterparty | "my funds are placed in" |
| `collateralized_by` | market → asset | "I am secured by" |
| `lends` | market → asset | "I lend this asset" (extension pending validation) |
| `priced_by` | market/oracle → oracle/pool/asset | "my value is computed by" |
| `redeemable_into` | asset → asset | "I can be exchanged for" |
| `issued_by` | asset/oracle/pool/market/vault → issuer | "I am issued / controlled by" |
| `settled_on` | contract → chain | "I run on" |

## Loading the graph
```python
import json
from discovery.graph import to_networkx
import networkx as nx

graph = json.load(open("output/graph.json", encoding="utf-8"))
g = to_networkx(graph)                       # MultiDiGraph, edge key = type
impacted = nx.ancestors(g, "usde")           # everything that depends on USDe
oracles = [n for n, d in g.nodes(data=True) if d.get("type") == "oracle"]
```

## Example of evidence per source
- `onchain`: `PT-sUSDE-26NOV2026.SY() = 0xBF98… @ 0xB195… #26162087` (contract, function, result, address, block).
- `api`: `Morpho API https://api.morpho.org/graphql marketById(…).supplyingVaultV2s contains 0x55C1… (fetched 2026-10-10T…)`
- `curated`: `USDe Token = 0x4c9E… according to https://docs.ethena.fi/solution-design/key-addresses (as of 2026-10-10)`
