"""Explore a graph.json in the terminal (with networkx) — ideal for the demo and for understanding.

    python -m discovery.inspect_graph                      # dependency tree from the position
    python -m discovery.inspect_graph --impact usde        # who is hit if USDe breaks? through which path?
    python -m discovery.inspect_graph --evidence           # also prints the evidence of every edge

Reminder of the convention: an arrow goes from the DEPENDENT to its DEPENDENCY,
so "who is hit if X breaks" = all the ANCESTORS of X in the graph.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import networkx as nx

from .console import utf8_console
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
            again = " (already expanded ↑)" if child in seen else ""
            print(f"{prefix}{branch} {etype} {SOURCE_TAG.get(data['source'], '?')} → {_describe(g, child)}{again}")
            if show_evidence:
                print(f"{prefix}{'   ' if last else '│  '}   evidence: {data['evidence'][:160]}")
            if child not in seen and depth < max_depth:
                seen.add(child)
                walk(child, prefix + ("   " if last else "│  "), depth + 1)

    print(_describe(g, root))
    seen.add(root)
    walk(root, "", 1)


def print_impact(g: nx.MultiDiGraph, root: str, target: str) -> None:
    if target not in g:
        print(f"unknown node: {target}. Available ids: {', '.join(sorted(n for n in g if n != root))}")
        return
    impacted = nx.ancestors(g, target)
    print(f"If \"{target}\" breaks, {len(impacted)} element(s) depend on it (directly or not):")
    for n in sorted(impacted, key=lambda x: (x != root, x)):
        print("  ·", _describe(g, n))
    if root in impacted or root == target:
        path = nx.shortest_path(g, root, target)
        hops = []
        for a, b in zip(path, path[1:]):
            etype = next(iter(g.get_edge_data(a, b)))
            hops.append(f"{a} --{etype}--> {b}")
        print("\nShortest path from the position:\n  " + "\n  ".join(hops))
    else:
        print("\n→ the position does not depend on it.")


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    p = argparse.ArgumentParser(description="Explore a StackTrace graph.json")
    p.add_argument("graph", nargs="?", default="output/graph.json")
    p.add_argument("--impact", help="node id: who is hit if it breaks?")
    p.add_argument("--evidence", action="store_true", help="print the evidence of every edge")
    p.add_argument("--depth", type=int, default=20)
    args = p.parse_args(argv)
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    g = to_networkx(graph)
    root = graph["position"]["id"]
    if args.impact:
        print_impact(g, root, args.impact)
    else:
        print_tree(g, root, args.evidence, args.depth)
        print(f"\n{g.number_of_nodes() - 1} nodes, {g.number_of_edges()} edges · "
              f"cycles: {'none' if nx.is_directed_acyclic_graph(g) else list(nx.simple_cycles(g))[:3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
