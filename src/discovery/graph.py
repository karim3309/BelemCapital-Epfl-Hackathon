"""Graph model: nodes, edges, de-duplication, id assignment, export to the JSON contract.

During discovery, nodes are referenced by a stable internal KEY:
  - on-chain contract       → its checksum address          "0xB195..."
  - Morpho market           → "morpho_market:<marketId>"     (all markets share the singleton's address)
  - off-chain entity        → "offchain:<slug>"  / issuer → "issuer:<slug>"
  - chain                   → "chain:<name>"
  - racine                  → "position"
The readable JSON `id`s ("pt_susde_26nov2026") are only computed at the end (`to_contract`),
in a single place, which makes collisions impossible to miss.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from .ids import addr6, slugify
from .vocab import EDGE_TYPES, NODE_TYPES, SOURCES

POSITION_KEY = "position"


@dataclass
class Node:
    key: str
    type: str
    label: str
    id_hint: str
    address: str | None = None
    chain: str | None = "ethereum"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in NODE_TYPES:
            raise ValueError(f"unknown node type: {self.type!r} (see vocab.NODE_TYPES)")


@dataclass
class Edge:
    from_key: str
    to_key: str
    type: str
    source: str
    evidence: str
    weight: float = 1.0

    def __post_init__(self):
        if self.type not in EDGE_TYPES:
            raise ValueError(f"unknown edge type: {self.type!r} (see vocab.EDGE_TYPES)")
        if self.source not in SOURCES:
            raise ValueError(f"unknown source: {self.source!r} (onchain | api | curated)")
        if not self.evidence or not self.evidence.strip():
            raise ValueError(f"edge {self.from_key} -{self.type}-> {self.to_key} without evidence")
        if not 0.0 <= float(self.weight) <= 1.0:
            raise ValueError("weight must be in [0, 1]")


class GraphBuilder:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple[str, str, str], Edge] = {}

    # ------------------------------------------------------------- adding
    def add_node(self, node: Node) -> str:
        existing = self.nodes.get(node.key)
        if existing is None:
            self.nodes[node.key] = node
            return node.key
        if existing.type != node.type:
            raise ValueError(f"{node.key} already known as {existing.type}, not {node.type}")
        for k, v in node.meta.items():          # complete, never overwrite
            existing.meta.setdefault(k, v)
        return node.key

    def add_edge(self, edge: Edge) -> None:
        if edge.from_key == edge.to_key:
            raise ValueError(f"self-loop not allowed: {edge.from_key}")
        k = (edge.from_key, edge.to_key, edge.type)
        self.edges.setdefault(k, edge)          # the first evidence wins

    def has(self, key: str) -> bool:
        return key in self.nodes

    # ------------------------------------------------------------- export
    def assign_ids(self) -> dict[str, str]:
        """internal key → final id. Sorted by key → deterministic result."""
        ids: dict[str, str] = {}
        taken: set[str] = set()
        for key in sorted(self.nodes):
            n = self.nodes[key]
            base = slugify(n.id_hint)
            candidate = base
            if candidate in taken and n.address:
                candidate = f"{base}_{addr6(n.address)}"
            i = 2
            while candidate in taken:
                candidate = f"{base}_{i}"
                i += 1
            taken.add(candidate)
            ids[key] = candidate
        return ids

    def to_contract(self, position_id: str, value_usd: float) -> dict:
        ids = self.assign_ids()
        ids[POSITION_KEY] = position_id
        nodes = [
            {
                "id": ids[n.key],
                "type": n.type,
                "label": n.label,
                "address": n.address,
                "chain": n.chain,
                "meta": n.meta,
            }
            for n in self.nodes.values()
        ]
        edges = []
        for e in self.edges.values():
            if e.from_key not in ids or e.to_key not in ids:
                raise ValueError(f"edge to a missing node: {e.from_key} -{e.type}-> {e.to_key}")
            edges.append({
                "from": ids[e.from_key],
                "to": ids[e.to_key],
                "type": e.type,
                "weight": float(e.weight),
                "source": e.source,
                "evidence": e.evidence,
            })
        type_order = ["lending_market", "vault", "oracle", "asset", "liquidity_venue",
                      "issuer", "offchain_counterparty", "chain"]
        nodes.sort(key=lambda n: (type_order.index(n["type"]), n["id"]))
        edges.sort(key=lambda e: (e["from"], e["type"], e["to"]))
        return {
            "position": {"id": position_id, "value_usd": round(float(value_usd), 2)},
            "nodes": nodes,
            "edges": edges,
        }


def to_networkx(graph: dict) -> nx.MultiDiGraph:
    """Loads a graph.json (dict) into networkx — handy for the other teams' analyses."""
    g = nx.MultiDiGraph()
    g.add_node(graph["position"]["id"], type="position", **{"value_usd": graph["position"]["value_usd"]})
    for n in graph["nodes"]:
        g.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in graph["edges"]:
        g.add_edge(e["from"], e["to"], key=e["type"], **{k: v for k, v in e.items() if k not in ("from", "to")})
    return g
