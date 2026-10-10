"""Chaîne de règlement : « sur quelle blockchain ce contrat s'exécute-t-il ? »

Preuve on-chain : eth_chainId = 1 (on parle bien à Ethereum mainnet) ET eth_getCode(adresse)
non vide au bloc figé (il y a bien du code déployé à cette adresse sur cette chaîne).
Si la chaîne est congestionnée ou s'arrête, les liquidations et rachats ne passent plus :
c'est la dépendance la plus basse de la pile.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..ctx import Ctx
from ..graph import Edge, Node
from . import Discovery


def chain_key(name: str) -> str:
    return f"chain:{name}"


def discover_chain(ctx: Ctx, chain_name: str, chain_id: int, onchain_nodes: list[Node]) -> Discovery:
    ts = ctx.block_timestamp
    block = ctx.w3.eth.get_block(ctx.block)
    key = chain_key(chain_name)
    d = Discovery(nodes=[Node(
        key=key, type="chain", label=chain_name.capitalize(), id_hint=chain_name, address=None, chain=chain_name,
        meta={
            "chain_id": chain_id,
            "snapshot_block": ctx.block,
            "snapshot_block_hash": "0x" + bytes(block["hash"]).hex(),
            "snapshot_timestamp": ts,
            "snapshot_time_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "note": "Toutes les lectures on-chain du graphe sont faites à ce bloc.",
        },
    )])
    for n in onchain_nodes:
        if not n.address:
            continue
        size = len(ctx.code(n.address))
        if size == 0:
            n.meta["warning_no_code"] = f"aucun code à {n.address} au bloc {ctx.block}"
            d.notes.append(f"⚠ {n.label} ({n.address}) n'a pas de code : ce n'est pas un contrat")
            continue
        d.edges.append(Edge(n.key, key, "settled_on", "onchain",
                            f"eth_getCode({n.address}) = {size} octets #{ctx.block} ; eth_chainId = {chain_id}"))
    return d
