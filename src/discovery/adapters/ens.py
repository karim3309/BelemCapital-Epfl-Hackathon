"""ENS (Ethereum Name Service): the on-chain "name → address" directory.

Why here? Chainlink registers its official feeds under the `data.eth` domain
(docs: https://docs.chain.link/data-feeds/ens). If `usde-usd.data.eth` resolves ON-CHAIN to
the address of the feed our oracle uses, we have on-chain proof that it really is a Chainlink feed.

Resolution (without depending on web3.py's ENS module):
  node     = namehash(name)               (recursive hash of the labels, EIP-137)
  resolver = Registry.resolver(node)
  address  = Resolver.addr(node)
"""
from __future__ import annotations

from eth_utils import keccak

from ..ctx import Ctx, is_zero


def namehash(name: str) -> bytes:
    node = b"\x00" * 32
    if name:
        for label in reversed(name.split(".")):
            node = keccak(node + keccak(text=label))
    return node


def resolve(ctx: Ctx, name: str) -> tuple[str | None, str]:
    """Returns (address or None, evidence)."""
    registry = ctx.config.contracts["ens_registry"]
    node = namehash(name)
    resolver = ctx.try_call(registry, "resolver(bytes32)", [node], ["address"])
    if resolver is None or is_zero(resolver):
        return None, f"ENS {name}: no resolver @ {registry} #{ctx.block}"
    addr = ctx.try_call(resolver, "addr(bytes32)", [node], ["address"])
    if addr is None or is_zero(addr):
        return None, f"ENS {name}: no address @ resolver {resolver} #{ctx.block}"
    return addr, f"ENS {name} → {addr} (Registry {registry} → resolver {resolver}) #{ctx.block}"


def chainlink_ens_name(description: str) -> str:
    """'USDe / USD' → 'usde-usd.data.eth' (Chainlink naming convention)."""
    parts = [p.strip().lower() for p in description.split("/")]
    return "-".join(parts) + ".data.eth"
