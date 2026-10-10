"""ERC-4626: the standard for "share vaults" (tokenized vaults).

Analogy: a shared piggy bank. You deposit the asset (`asset()`, e.g. USDe) and receive shares
(e.g. sUSDe). When the vault earns yield, each share is worth more of the asset:
`convertToAssets(1 share)` goes up. That rate is an INTERNAL (accounting) RATE, not a market price.

Dependency: the share only has value through the underlying asset → `redeemable_into` edge.
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
    # Ethena-specific (sUSDe) but probed generically: withdrawal cooldown.
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
        + f"; convertToAssets(1e{dec}) = {rate} (internal rate)",
    ))
    d.follow.append(Task("token", underlying))
    return d
