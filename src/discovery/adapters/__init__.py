"""Discovery adapters: one file per protocol / standard.

Shared contract (this is what lets 3 people work in parallel without stepping on each other):
    a function `discover_xxx(ctx, target, ...) -> Discovery`
  - reads the blockchain ONLY through `ctx` (so cached, at the pinned block, with evidence);
  - changes nothing: it RETURNS nodes, edges, and `follow` tasks
    (the next targets to explore). build_graph.py does the assembly.
  - if it does not recognise a contract, it says so (meta.unresolved=True) instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..graph import Edge, Node


@dataclass(frozen=True)
class Task:
    kind: str                      # "token" | "oracle" | "pendle_market_lookup" | "vaults_lookup" | ...
    target: str                    # address (checksum) or identifier
    hint: tuple = ()               # extra info (hashable)


@dataclass
class Discovery:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    follow: list[Task] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # remarks for the console report

    def extend(self, other: "Discovery") -> "Discovery":
        self.nodes += other.nodes
        self.edges += other.edges
        self.follow += other.follow
        self.notes += other.notes
        return self


def scaled(value: int, decimals: int) -> float:
    """On-chain integer → readable number (e.g. 1_000_000 with 6 decimals → 1.0)."""
    return value / 10 ** decimals


def jsonable(v: Any) -> Any:
    """Very large integers (uint256) are stored as strings in meta so JSON does not lose precision."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int) and abs(v) > 2**53:
        return str(v)
    return v
