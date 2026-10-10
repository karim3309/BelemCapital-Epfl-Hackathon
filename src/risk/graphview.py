"""Lecture pratique de graph.json pour le moteur de risque.

Le moteur ne code JAMAIS en dur « le nœud usde » : il cherche les nœuds par leur rôle dans le graphe
(« le collatéral du marché », « l'oracle du marché », « le feed qui mesure le prix de tel actif »...).
Ainsi, le jour où la découverte produit le graphe d'une autre position, le moteur s'adapte.

Rappel de convention : une arête va du DÉPENDANT (`from`) vers sa DÉPENDANCE (`to`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import networkx as nx


@dataclass
class GraphView:
    raw: dict
    nodes: dict[str, dict] = field(default_factory=dict)
    out_edges: dict[str, list[dict]] = field(default_factory=dict)
    in_edges: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "GraphView":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, graph: dict) -> "GraphView":
        gv = cls(raw=graph)
        for n in graph["nodes"]:
            gv.nodes[n["id"]] = n
        for e in graph["edges"]:
            gv.out_edges.setdefault(e["from"], []).append(e)
            gv.in_edges.setdefault(e["to"], []).append(e)
        return gv

    # ------------------------------------------------------------------ accès
    @property
    def position_id(self) -> str:
        return self.raw["position"]["id"]

    def node(self, nid: str) -> dict:
        return self.nodes[nid]

    def meta(self, nid: str) -> dict:
        return self.nodes[nid]["meta"]

    def of_type(self, type_: str) -> list[dict]:
        return [n for n in self.raw["nodes"] if n["type"] == type_]

    def by_address(self, address: str | None) -> dict | None:
        if not address:
            return None
        for n in self.raw["nodes"]:
            if n["address"] and n["address"].lower() == address.lower():
                return n
        return None

    def targets(self, nid: str, edge_type: str) -> list[str]:
        return [e["to"] for e in self.out_edges.get(nid, []) if e["type"] == edge_type]

    def sources(self, nid: str, edge_type: str) -> list[str]:
        return [e["from"] for e in self.in_edges.get(nid, []) if e["type"] == edge_type]

    def edge(self, a: str, b: str, edge_type: str | None = None) -> dict | None:
        for e in self.out_edges.get(a, []):
            if e["to"] == b and (edge_type is None or e["type"] == edge_type):
                return e
        return None

    def select(self, selector: dict) -> list[str]:
        """Sélecteur de params.yaml : {id: x} ou {type: t, role/oracle_kind/asset_kind: v}."""
        if "id" in selector:
            return [selector["id"]] if selector["id"] in self.nodes else []
        out = []
        for n in self.raw["nodes"]:
            if n["type"] != selector.get("type"):
                continue
            if all(n["meta"].get(k) == v for k, v in selector.items() if k != "type"):
                out.append(n["id"])
        return out

    # ------------------------------------------------------------------ rôles de la position
    def market_id(self) -> str:
        return self.targets(self.position_id, "deployed_in")[0]

    def collateral_id(self) -> str:
        return self.targets(self.market_id(), "collateralized_by")[0]

    def loan_id(self) -> str:
        return self.targets(self.market_id(), "lends")[0]

    def market_oracle_id(self) -> str:
        return self.targets(self.market_id(), "priced_by")[0]

    def exit_venue_id(self) -> str | None:
        venues = self.targets(self.collateral_id(), "deployed_in")
        return venues[0] if venues else None

    def feed_priced_asset(self, feed_id: str) -> str | None:
        """Actif dont un feed mesure le prix de marché (meta.priced_asset = adresse)."""
        node = self.by_address(self.meta(feed_id).get("priced_asset"))
        return node["id"] if node else None

    def snapshot(self) -> dict:
        chain = self.of_type("chain")[0]["meta"]
        return {"block": chain["snapshot_block"], "timestamp": chain["snapshot_timestamp"],
                "time_iso": chain["snapshot_time_iso"]}

    # ------------------------------------------------------------------ networkx
    def nx(self) -> nx.MultiDiGraph:
        from discovery.graph import to_networkx
        return to_networkx(self.raw)

    def paths_from_position(self, target: str, max_paths: int = 3, cutoff: int = 12) -> list[list[dict]]:
        """Chemins de contagion : de la position jusqu'au nœud choqué, arêtes réelles avec leurs preuves."""
        g = nx.DiGraph()
        for e in self.raw["edges"]:
            if e["type"] != "settled_on":          # la chaîne est sous tout : on ne l'utilise pas comme chemin
                g.add_edge(e["from"], e["to"])
        root = self.position_id
        if target not in g or root not in g:
            return []
        paths = sorted(nx.all_simple_paths(g, root, target, cutoff=cutoff), key=len)[:max_paths]
        out = []
        for p in paths:
            out.append([self.edge(a, b) for a, b in zip(p, p[1:])])
        return out


def iter_unique(xs: Iterable[Any]) -> list[Any]:
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
