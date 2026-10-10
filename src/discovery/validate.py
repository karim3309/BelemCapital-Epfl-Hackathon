"""Validateur du contrat graph.json — à lancer avant de livrer un graphe aux autres équipes.

    python -m discovery.validate output/graph.json

Il vérifie la STRUCTURE (clés exactes, types autorisés) et la RIGUEUR (chaque arête a une
preuve, une source permise, aucune adresse placeholder, tout est relié à la position).
Renvoie la liste des erreurs (vide = graphe conforme).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import networkx as nx

from .graph import to_networkx
from .vocab import ALLOWED_EDGE_SHAPES, EDGE_TYPES, NODE_TYPES, PRICING_MODES, SOURCES

TOP_KEYS = {"position", "nodes", "edges"}
POSITION_KEYS = {"id", "value_usd"}
NODE_KEYS = {"id", "type", "label", "address", "chain", "meta"}
EDGE_KEYS = {"from", "to", "type", "weight", "source", "evidence"}

POSITION_ID_RE = re.compile(r"^morpho:0x[0-9a-f]{64}:0x[0-9a-fA-F]{40}$")
NODE_ID_RE = re.compile(r"^[a-z0-9_]+$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
PLACEHOLDER_RE = re.compile(r"0x\.\.\.|TO_VERIFY|à vérifier|TODO", re.IGNORECASE)


def _is_checksummed(address: str) -> bool:
    from eth_utils import to_checksum_address
    return to_checksum_address(address) == address


def validate(graph: dict) -> list[str]:
    errors: list[str] = []
    err = errors.append

    if set(graph) != TOP_KEYS:
        err(f"clés de premier niveau {sorted(graph)} ≠ {sorted(TOP_KEYS)}")
        return errors

    pos = graph["position"]
    if set(pos) != POSITION_KEYS:
        err(f"position: clés {sorted(pos)} ≠ {sorted(POSITION_KEYS)}")
    if not POSITION_ID_RE.match(str(pos.get("id", ""))):
        err(f"position.id {pos.get('id')!r} ne suit pas morpho:<marketId>:<user>")
    if not isinstance(pos.get("value_usd"), (int, float)) or pos.get("value_usd", -1) < 0:
        err("position.value_usd doit être un nombre ≥ 0")

    types_by_id: dict[str, str] = {pos.get("id"): "position"}
    for n in graph["nodes"]:
        nid = n.get("id")
        where = f"nœud {nid!r}"
        if set(n) != NODE_KEYS:
            err(f"{where}: clés {sorted(n)} ≠ {sorted(NODE_KEYS)}")
            continue
        if not NODE_ID_RE.match(str(nid)):
            err(f"{where}: id doit être en snake_case [a-z0-9_]")
        if nid in types_by_id:
            err(f"{where}: id dupliqué")
        types_by_id[nid] = n["type"]
        if n["type"] not in NODE_TYPES:
            err(f"{where}: type {n['type']!r} hors vocabulaire")
        if not n["label"]:
            err(f"{where}: label vide")
        if n["address"] is not None:
            if not ADDRESS_RE.match(n["address"]):
                err(f"{where}: adresse invalide {n['address']!r}")
            elif not _is_checksummed(n["address"]):
                err(f"{where}: adresse non checksummée (EIP-55)")
        if n["type"] in ("asset", "oracle", "lending_market", "liquidity_venue", "vault") and not n["address"]:
            err(f"{where}: un nœud on-chain doit avoir une adresse")
        if not isinstance(n["meta"], dict):
            err(f"{where}: meta doit être un objet")
        else:
            pm = n["meta"].get("pricing_mode")
            if pm is not None and pm not in PRICING_MODES:
                err(f"{where}: meta.pricing_mode {pm!r} hors vocabulaire {sorted(PRICING_MODES)}")

    seen_edges = set()
    for e in graph["edges"]:
        where = f"arête {e.get('from')} -{e.get('type')}-> {e.get('to')}"
        if set(e) != EDGE_KEYS:
            err(f"{where}: clés {sorted(e)} ≠ {sorted(EDGE_KEYS)}")
            continue
        sig = (e["from"], e["to"], e["type"])
        if sig in seen_edges:
            err(f"{where}: dupliquée")
        seen_edges.add(sig)
        if e["type"] not in EDGE_TYPES:
            err(f"{where}: type hors vocabulaire")
            continue
        if e["source"] not in SOURCES:
            err(f"{where}: source {e['source']!r} hors {sorted(SOURCES)}")
        for end in ("from", "to"):
            if e[end] not in types_by_id:
                err(f"{where}: `{end}` pointe vers un nœud inexistant")
        if e["from"] in types_by_id and e["to"] in types_by_id:
            allowed_from, allowed_to = ALLOWED_EDGE_SHAPES[e["type"]]
            if types_by_id[e["from"]] not in allowed_from or types_by_id[e["to"]] not in allowed_to:
                err(f"{where}: forme interdite ({types_by_id[e['from']]} -{e['type']}-> {types_by_id[e['to']]})")
        if not isinstance(e["weight"], (int, float)) or not 0 <= e["weight"] <= 1:
            err(f"{where}: weight hors [0,1]")
        ev = e["evidence"]
        if not isinstance(ev, str) or len(ev.strip()) < 10:
            err(f"{where}: preuve absente ou trop courte")
        elif e["source"] == "onchain" and not re.search(r"0x[0-9a-fA-F]{40}.*#\d+", ev):
            err(f"{where}: preuve on-chain sans 'adresse #bloc'")
        elif e["source"] in ("api", "curated") and "http" not in ev:
            err(f"{where}: preuve {e['source']} sans URL")

    blob = json.dumps(graph, ensure_ascii=False)
    if PLACEHOLDER_RE.search(blob):
        err(f"placeholder trouvé dans le graphe : {PLACEHOLDER_RE.search(blob).group(0)!r}")

    # Tout doit être relié à la position (connexité faible : un vault pointe VERS le marché).
    if not errors:
        g = to_networkx(graph)
        comp = nx.node_connected_component(g.to_undirected(as_view=True), pos["id"])
        orphans = sorted(set(g.nodes) - comp)
        if orphans:
            err(f"nœuds non reliés à la position : {orphans}")
    return errors


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("output/graph.json")
    graph = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(graph)
    if errors:
        print(f"✗ {path} : {len(errors)} erreur(s)")
        for e in errors:
            print("  -", e)
        return 1
    print(f"✓ {path} conforme au contrat : {len(graph['nodes'])} nœuds, {len(graph['edges'])} arêtes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
