"""ENS (Ethereum Name Service) : l'annuaire on-chain « nom → adresse ».

Pourquoi ici ? Chainlink enregistre ses feeds officiels sous le domaine `data.eth`
(doc : https://docs.chain.link/data-feeds/ens). Si `usde-usd.data.eth` résout ON-CHAIN vers
l'adresse du feed qu'utilise notre oracle, on a une preuve on-chain que c'est bien un feed Chainlink.

Résolution (sans dépendre du module ENS de web3.py) :
  node     = namehash(nom)                (hash récursif des labels, EIP-137)
  resolver = Registry.resolver(node)
  adresse  = Resolver.addr(node)
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
    """Renvoie (adresse ou None, preuve)."""
    registry = ctx.config.contracts["ens_registry"]
    node = namehash(name)
    resolver = ctx.try_call(registry, "resolver(bytes32)", [node], ["address"])
    if resolver is None or is_zero(resolver):
        return None, f"ENS {name} : aucun resolver @ {registry} #{ctx.block}"
    addr = ctx.try_call(resolver, "addr(bytes32)", [node], ["address"])
    if addr is None or is_zero(addr):
        return None, f"ENS {name} : pas d'adresse @ resolver {resolver} #{ctx.block}"
    return addr, f"ENS {name} → {addr} (Registry {registry} → resolver {resolver}) #{ctx.block}"


def chainlink_ens_name(description: str) -> str:
    """'USDe / USD' → 'usde-usd.data.eth' (convention de nommage Chainlink)."""
    parts = [p.strip().lower() for p in description.split("/")]
    return "-".join(parts) + ".data.eth"
