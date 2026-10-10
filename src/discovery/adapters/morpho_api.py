"""API Morpho (GraphQL) : QUI prête au marché ? (les vaults qui y allouent des USDC)

Pourquoi l'API ? Pour lister les vaults qui allouent dans un marché on-chain, il faudrait
indexer tous les vaults existants et lire leur config : c'est le travail d'un indexeur.
L'API Morpho le fait déjà. On cite donc l'API comme source (`source: "api"`), et on relit
on-chain ce qui peut l'être (nom, symbole, actif du vault, curateur).

Dépendance : un vault qui prête au marché dépend du marché (si le collatéral fait défaut, le vault
encaisse la dette irrécouvrable) → arête vault --deployed_in--> marché.
Pour l'emprunteur, c'est un lien indirect : si les vaults retirent leurs USDC, l'utilisation
monte et le taux d'emprunt explose (modèle de taux adaptatif).
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
        d.notes.append(f"API Morpho : erreur {data['errors'][0].get('message')} → vaults non découverts")
        return d
    market = (data.get("data") or {}).get("marketById") or {}
    vaults = [("MetaMorpho (v1)", v) for v in market.get("supplyingVaults") or []] + \
             [("Morpho Vault V2", v) for v in market.get("supplyingVaultV2s") or []]
    for version, v in vaults:
        addr = checksum(v["address"])
        # Relecture on-chain : on ne fait pas confiance au nom renvoyé par l'API.
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
                            f"API Morpho {url} marketById({market_id}).{'supplyingVaultV2s' if 'V2' in version else 'supplyingVaults'} "
                            f"contient {addr} (fetched {fetched_at})"))
    if not vaults:
        d.notes.append("API Morpho : aucun vault ne prête à ce marché (prêteurs directs uniquement ?)")
    return d

