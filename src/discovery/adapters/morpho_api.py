"""Morpho API (GraphQL): WHO lends to the market? (the vaults allocating USDC to it)

Why the API? Listing the vaults that allocate to an on-chain market would require
indexing every existing vault and reading its config: that is an indexer's job.
The Morpho API already does it. So we cite the API as the source (`source: "api"`), and re-read
on-chain whatever can be (vault name, symbol, asset, curator).

Dependency: a vault lending to the market depends on the market (if the collateral defaults, the vault
takes the bad debt) → edge vault --deployed_in--> market.
For the borrower it is an indirect link: if the vaults pull their USDC, utilisation
rises and the borrow rate spikes (adaptive rate model).
"""
from __future__ import annotations

from ..ctx import Ctx, checksum
from ..graph import Edge, Node
from ..ids import slugify
from . import Discovery
from .morpho import market_key

QUERY = """query Vaults($id: String!, $chainId: Int!) {
  marketById(marketId: $id, chainId: $chainId) {
    marketId
    supplyingVaults { address name symbol }
    supplyingVaultV2s { address name symbol }
  }
}"""


def discover_supplying_vaults(ctx: Ctx, market_id: str, chain_id: int = 1) -> Discovery:
    url = ctx.config.apis["morpho_graphql"]
    data, fetched_at = ctx.http.post_json(url, {"query": QUERY, "variables": {"id": market_id, "chainId": chain_id}})
    d = Discovery()
    if data.get("errors"):
        d.notes.append(f"Morpho API: error {data['errors'][0].get('message')} → vaults not discovered")
        return d
    market = (data.get("data") or {}).get("marketById") or {}
    vaults = [("MetaMorpho (v1)", v) for v in market.get("supplyingVaults") or []] + \
             [("Morpho Vault V2", v) for v in market.get("supplyingVaultV2s") or []]
    for version, v in vaults:
        addr = checksum(v["address"])
        # On-chain re-read: we do not trust the name returned by the API.
        name = ctx.try_call(addr, "name()", returns=["string"]) or v.get("name") or addr
        symbol = ctx.try_call(addr, "symbol()", returns=["string"]) or v.get("symbol")
        meta = {
            "vault_version": version,
            "symbol": symbol,
            "asset": ctx.try_call(addr, "asset()", returns=["address"]),
            "curator": ctx.try_call(addr, "curator()", returns=["address"]),
            "owner": ctx.try_call(addr, "owner()", returns=["address"]),
            "total_assets": str(ta) if (ta := ctx.try_call(addr, "totalAssets()", returns=["uint256"])) is not None else None,
            "discovered_via": f"{url} (fetched {fetched_at})",
        }
        d.nodes.append(Node(key=addr, type="vault", label=name, id_hint=f"vault_{slugify(symbol or name)}",
                            address=addr, meta=meta))
        d.edges.append(Edge(addr, market_key(market_id), "deployed_in", "api",
                            f"Morpho API {url} marketById({market_id}).{'supplyingVaultV2s' if 'V2' in version else 'supplyingVaults'} "
                            f"contains {addr} (fetched {fetched_at})"))
    if not vaults:
        d.notes.append("Morpho API: no vault lends to this market (direct lenders only?)")
    return d

