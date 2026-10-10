"""Settlement chain: "which blockchain does this contract run on?"

On-chain evidence: eth_chainId = 1 (we are talking to Ethereum mainnet) AND eth_getCode(address)
is non-empty at the pinned block (there really is code deployed at this address on this chain).
If the chain is congested or halts, liquidations and redemptions stop going through:
it is the lowest dependency in the stack.
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
            "note": "Every on-chain read of the graph is made at this block.",
        },
    )])
    for n in onchain_nodes:
        if not n.address:
            continue
        size = len(ctx.code(n.address))
        if size == 0:
            n.meta["warning_no_code"] = f"no code at {n.address} at block {ctx.block}"
            d.notes.append(f"⚠ {n.label} ({n.address}) has no code: it is not a contract")
            continue
        d.edges.append(Edge(n.key, key, "settled_on", "onchain",
                            f"eth_getCode({n.address}) = {size} bytes #{ctx.block}; eth_chainId = {chain_id}"))
    return d
