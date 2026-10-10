"""ERC-20: the base standard of every token (symbol, decimals, totalSupply, balanceOf).

And the central discovery question: "what IS this token?"
We PROBE it (call characteristic functions and see which ones answer):
  - Pendle PT    : SY(), YT(), expiry()        → a Principal Token
  - Pendle SY    : yieldToken(), assetInfo()   → a Standardized Yield wrapper
  - ERC-4626     : asset(), convertToAssets()  → a share vault (e.g. sUSDe)
  - otherwise    : plain ERC-20 (USDe, USDC...)
Order matters: a Pendle SY also exposes asset(), so Pendle is tested first.
"""
from __future__ import annotations

from eth_utils import to_checksum_address

from ..ctx import Ctx
from ..graph import Node
from ..ids import token_id
from . import jsonable, scaled

PT_PROBES = [("SY()", ["address"]), ("YT()", ["address"]), ("expiry()", ["uint256"])]
SY_PROBES = [("yieldToken()", ["address"]), ("assetInfo()", ["uint8", "address", "uint8"])]
ERC4626_PROBES = [("asset()", ["address"]), ("totalAssets()", ["uint256"])]


def _text(ctx: Ctx, address: str, fn: str) -> str | None:
    """symbol()/name(): normally `string`, but some old tokens return `bytes32`."""
    v = ctx.try_call(address, f"{fn}()", returns=["string"])
    if v is None:
        raw = ctx.try_call(address, f"{fn}()", returns=["bytes32"])
        if raw is not None:
            v = bytes.fromhex(raw[2:]).rstrip(b"\x00").decode("utf-8", "replace")
    return v


def read_token(ctx: Ctx, address: str) -> dict | None:
    """Reads the ERC-20 fields. Returns None if this is not a token (no decimals/symbol)."""
    symbol = _text(ctx, address, "symbol")
    decimals = ctx.try_call(address, "decimals()", returns=["uint8"])
    if symbol is None or decimals is None:
        return None
    total_supply = ctx.try_call(address, "totalSupply()", returns=["uint256"])
    return {
        "address": to_checksum_address(address),
        "symbol": symbol,
        "name": _text(ctx, address, "name") or symbol,
        "decimals": decimals,
        "total_supply": total_supply,
    }


def classify(ctx: Ctx, address: str) -> str:
    if ctx.has_functions(address, PT_PROBES):
        return "pendle_pt"
    if ctx.has_functions(address, SY_PROBES):
        return "pendle_sy"
    if ctx.has_functions(address, ERC4626_PROBES):
        decimals = ctx.try_call(address, "decimals()", returns=["uint8"]) or 18
        if ctx.try_call(address, "convertToAssets(uint256)", [10**decimals], ["uint256"]) is not None:
            return "erc4626"
    return "erc20"


def token_node(info: dict, asset_kind: str, extra_meta: dict | None = None) -> Node:
    meta = {
        "asset_kind": asset_kind,
        "symbol": info["symbol"],
        "decimals": info["decimals"],
        "total_supply": jsonable(info["total_supply"]),
        "total_supply_human": scaled(info["total_supply"], info["decimals"]) if info["total_supply"] is not None else None,
    }
    meta.update(extra_meta or {})
    return Node(
        key=info["address"],
        type="asset",
        label=info["symbol"],
        id_hint=token_id(info["symbol"]),
        address=info["address"],
        meta=meta,
    )
