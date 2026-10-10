"""Explorer un graph.json dans le terminal (avec networkx) — idéal pour la démo et pour comprendre.

    python -m discovery.inspect_graph                      # arbre des dépendances depuis la position
    python -m discovery.inspect_graph --impact usde        # qui est touché si USDe casse ? par quel chemin ?
    python -m discovery.inspect_graph --evidence           # affiche aussi la preuve de chaque arête

Rappel de la convention : une flèche va du DÉPENDANT vers sa DÉPENDANCE,
donc « qui est touché si X casse » = tous les ANCÊTRES de X dans le graphe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import networkx as nx

from .graph import to_networkx

SOURCE_TAG = {"onchain": "⛓", "api": "🌐", "curated": "📄"}


def _describe(g: nx.MultiDiGraph, node: str) -> str:
    d = g.nodes[node]
    if d.get("type") == "position":
        return f"POSITION (value_usd={d.get('value_usd'):,})"
    meta = d.get("meta", {})
    extra = []
    for key in ("pricing_mode", "effective_pricing_mode", "asset_kind", "oracle_kind", "role"):
        if meta.get(key):
            extra.append(f"{key}={meta[key]}")
    if meta.get("tvl_usd") is not None:
        extra.append(f"tvl=${meta['tvl_usd']:,.0f}")
    return f"{node} [{d.get('type')}] {d.get('label', '')}" + (f"  ({', '.join(extra)})" if extra else "")


def print_tree(g: nx.MultiDiGraph, root: str, show_evidence: bool, max_depth: int) -> None:
    seen: set[str] = set()

    def walk(node: str, prefix: str, depth: int) -> None:
        children = sorted(g.out_edges(node, keys=True, data=True), key=lambda e: (e[2], e[1]))
        for i, (_, child, etype, data) in enumerate(children):
            last = i == len(children) - 1
            branch = "└─" if last else "├─"
            again = " (déjà développé ↑)" if child in seen else ""
            print(f"{prefix}{branch} {etype} {SOURCE_TAG.get(data['source'], '?')} → {_describe(g, child)}{again}")
            if show_evidence:
                print(f"{prefix}{'   ' if last else '│  '}   preuve : {data['evidence'][:160]}")
            if child not in seen and depth < max_depth:
                seen.add(child)
                walk(child, prefix + ("   " if last else "│  "), depth + 1)

    print(_describe(g, root))
    seen.add(root)
    walk(root, "", 1)


def print_impact(g: nx.MultiDiGraph, root: str, target: str) -> None:
    if target not in g:
        print(f"nœud inconnu : {target}. Ids disponibles : {', '.join(sorted(n for n in g if n != root))}")
        return
    impacted = nx.ancestors(g, target)
    print(f"Si « {target} » casse, {len(impacted)} élément(s) en dépendent (directement ou non) :")
    for n in sorted(impacted, key=lambda x: (x != root, x)):
        print("  ·", _describe(g, n))
    if root in impacted or root == target:
        path = nx.shortest_path(g, root, target)
        hops = []
        for a, b in zip(path, path[1:]):
            etype = next(iter(g.get_edge_data(a, b)))
            hops.append(f"{a} --{etype}--> {b}")
        print("\nChemin le plus court depuis la position :\n  " + "\n  ".join(hops))
    else:
        print("\n→ la position n'en dépend pas.")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(description="Explorer un graph.json StackTrace")
    p.add_argument("graph", nargs="?", default="output/graph.json")
    p.add_argument("--impact", help="id d'un nœud : qui est touché s'il casse ?")
    p.add_argument("--evidence", action="store_true", help="afficher la preuve de chaque arête")
    p.add_argument("--depth", type=int, default=20)
    args = p.parse_args(argv)
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    g = to_networkx(graph)
    root = graph["position"]["id"]
    if args.impact:
        print_impact(g, root, args.impact)
    else:
        print_tree(g, root, args.evidence, args.depth)
        print(f"\n{g.number_of_nodes() - 1} nœuds, {g.number_of_edges()} arêtes · "
              f"cycles : {'aucun' if nx.is_directed_acyclic_graph(g) else list(nx.simple_cycles(g))[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
