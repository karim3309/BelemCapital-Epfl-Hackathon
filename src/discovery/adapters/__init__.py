"""Adaptateurs de découverte : un fichier par protocole / standard.

Contrat commun (c'est lui qui permet de travailler à 3 sans se marcher dessus) :
    une fonction `discover_xxx(ctx, cible, ...) -> Discovery`
  - lit la blockchain UNIQUEMENT via `ctx` (donc caché, au bloc figé, avec preuve) ;
  - ne modifie rien : elle RENVOIE des nœuds, des arêtes, et des tâches `follow`
    (les prochaines cibles à explorer). C'est build_graph.py qui assemble.
  - si elle ne reconnaît pas un contrat, elle le dit (meta.unresolved=True) au lieu de deviner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..graph import Edge, Node


@dataclass(frozen=True)
class Task:
    kind: str                      # "token" | "oracle" | "pendle_market_lookup" | "vaults_lookup" | ...
    target: str                    # adresse (checksum) ou identifiant
    hint: tuple = ()               # infos complémentaires (hashable)


@dataclass
class Discovery:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    follow: list[Task] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # remarques pour le rapport console

    def extend(self, other: "Discovery") -> "Discovery":
        self.nodes += other.nodes
        self.edges += other.edges
        self.follow += other.follow
        self.notes += other.notes
        return self


def scaled(value: int, decimals: int) -> float:
    """Entier on-chain → nombre lisible (ex. 1_000_000 avec 6 décimales → 1.0)."""
    return value / 10 ** decimals


def jsonable(v: Any) -> Any:
    """Les très grands entiers (uint256) sont stockés en chaîne dans meta pour ne pas perdre de précision en JSON."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int) and abs(v) > 2**53:
        return str(v)
    return v
