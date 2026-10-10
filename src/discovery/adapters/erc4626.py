"""ERC-4626 : le standard des « coffres à parts » (tokenized vaults).

Analogie : une tirelire collective. On dépose l'actif (`asset()`, ex. USDe) et on reçoit des parts
(ex. sUSDe). Quand le coffre gagne des revenus, chaque part vaut plus d'actif :
`convertToAssets(1 part)` monte. Ce taux est un TAUX INTERNE (comptable), pas un prix de marché.

Dépendance : la part n'a de valeur que par l'actif sous-jacent → arête `redeemable_into`.
"""
from __future__ import annotations

from ..ctx import Ctx
from ..graph import Edge
from . import Discovery, Task, jsonable, scaled
from .erc20 import token_node


def discover_erc4626(ctx: Ctx, info: dict) -> Discovery:
    address, dec = info["address"], info["decimals"]
    underlying = ctx.call(address, "asset()", returns=["address"])
    one_share = 10**dec
    rate = ctx.call(address, "convertToAssets(uint256)", [one_share], ["uint256"])
    total_assets = ctx.call(address, "totalAssets()", returns=["uint256"])
    under_dec = ctx.try_call(underlying, "decimals()", returns=["uint8"]) or dec

    meta = {
        "underlying": underlying,
        "share_to_asset_rate": scaled(rate, under_dec),
        "pricing_mode_of_rate": "internal_rate",
        "total_assets": jsonable(total_assets),
        "total_assets_human": scaled(total_assets, under_dec),
    }
    # Spécifique Ethena (sUSDe) mais sondé génériquement : délai de retrait.
    cooldown = ctx.try_call(address, "cooldownDuration()", returns=["uint24"])
    if cooldown is not None:
        meta["cooldown_seconds"] = cooldown
    owner = ctx.try_call(address, "owner()", returns=["address"])
    if owner is not None:
        meta["owner"] = owner

    d = Discovery()
    d.nodes.append(token_node(info, "erc4626_vault", meta))
    d.edges.append(Edge(
        from_key=address, to_key=underlying, type="redeemable_into", source="onchain",
        evidence=ctx.ev(address, "asset()", result=underlying)
        + f" ; convertToAssets(1e{dec}) = {rate} (taux interne)",
    ))
    d.follow.append(Task("token", underlying))
    return d
