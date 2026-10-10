"""Chargeur de curated.yaml — la couche « vérifiable mais pas on-chain ».

Exemples : QUI est derrière une adresse (Ethena Labs ? Circle ?), OÙ sont les réserves
d'Ethena (custodians), SUR QUELS exchanges sont ses hedges. Aucun contrat ne le dit :
ça se prouve par une page officielle, avec une URL et une date.

Le chargeur est STRICT : URL obligatoire, date obligatoire, types du vocabulaire figé.
Il vaut mieux un graphe incomplet qu'un graphe avec une affirmation non sourcée.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from eth_utils import to_checksum_address

from ..graph import Edge, Node
from ..vocab import EDGE_TYPES, NODE_TYPES

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class CuratedError(ValueError):
    pass


def entity_key(key: str, type_: str) -> str:
    return f"issuer:{key}" if type_ == "issuer" else f"offchain:{key}"


def _check_common(where: str, entry: dict) -> None:
    url = entry.get("evidence_url", "")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise CuratedError(f"{where}: evidence_url https:// obligatoire")
    try:
        date.fromisoformat(str(entry.get("as_of")))
    except ValueError as e:
        raise CuratedError(f"{where}: as_of doit être une date AAAA-MM-JJ") from e


@dataclass
class Curated:
    entities: dict[str, dict] = field(default_factory=dict)          # key → entrée
    by_address: dict[str, dict] = field(default_factory=dict)        # adresse checksum → entrée (match: address)
    by_factory: dict[str, dict] = field(default_factory=dict)        # adresse checksum → entrée (match: factory)
    relations: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ nœuds / arêtes
    def node(self, key: str) -> Node:
        e = self.entities[key]
        meta = {"evidence_url": e["evidence_url"], "as_of": str(e["as_of"]), "note": e.get("note", "")}
        if e.get("role"):
            meta["role"] = e["role"]
        return Node(key=entity_key(key, e["type"]), type=e["type"], label=e["label"], id_hint=key,
                    address=None, chain=None, meta=meta)

    def node_for_key(self, graph_key: str) -> Node | None:
        """'issuer:ethena_labs' → nœud curé correspondant (ou None si inconnu)."""
        _, _, key = graph_key.partition(":")
        return self.node(key) if key in self.entities else None

    def issuer_edge(self, node_key: str, address: str | None, factory: str | None,
                    block: int, label: str) -> Edge | None:
        """Arête issued_by si l'adresse (ou la factory qui l'a créée) est un contrat connu."""
        if address and (hit := self.by_address.get(to_checksum_address(address))):
            ev = (f"{hit['role']} = {to_checksum_address(address)} selon {hit['evidence_url']} "
                  f"(relevé le {hit['as_of']})")
        elif factory and (hit := self.by_factory.get(to_checksum_address(factory))):
            ev = (f"{label}.factory() = {to_checksum_address(factory)} @ {to_checksum_address(address)} #{block} ; "
                  f"cette factory est « {hit['role']} » selon {hit['evidence_url']} (relevé le {hit['as_of']})")
        else:
            return None
        issuer = self.entities[hit["issuer"]]
        return Edge(node_key, entity_key(hit["issuer"], issuer["type"]), "issued_by", "curated", ev)

    def relation_edges(self, from_key: str) -> list[Edge]:
        out = []
        for r in self.relations:
            if r["from"] != from_key:
                continue
            src, dst = self.entities[r["from"]], self.entities[r["to"]]
            weight_txt = "" if r.get("weight_known", False) else " ; poids inconnu → 1.0 = borne haute conservatrice"
            out.append(Edge(entity_key(r["from"], src["type"]), entity_key(r["to"], dst["type"]), r["type"],
                            "curated", f"{r.get('note', '')} — {r['evidence_url']} (relevé le {r['as_of']}){weight_txt}",
                            weight=float(r.get("weight", 1.0))))
        return out


def load_curated(path: Path) -> Curated:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    c = Curated()
    for i, e in enumerate(raw.get("entities", [])):
        where = f"curated.entities[{i}] ({e.get('key')})"
        if e.get("type") not in NODE_TYPES or e["type"] not in ("issuer", "offchain_counterparty"):
            raise CuratedError(f"{where}: type doit être issuer ou offchain_counterparty")
        if not re.match(r"^[a-z0-9_]+$", str(e.get("key", ""))):
            raise CuratedError(f"{where}: key en snake_case obligatoire")
        if not e.get("label"):
            raise CuratedError(f"{where}: label obligatoire")
        _check_common(where, e)
        if e["key"] in c.entities:
            raise CuratedError(f"{where}: key dupliquée")
        c.entities[e["key"]] = e
    for i, k in enumerate(raw.get("known_contracts", [])):
        where = f"curated.known_contracts[{i}]"
        if not _ADDRESS_RE.match(str(k.get("address", ""))):
            raise CuratedError(f"{where}: adresse invalide")
        if k.get("issuer") not in c.entities:
            raise CuratedError(f"{where}: issuer {k.get('issuer')!r} absent de entities")
        if k.get("match") not in ("address", "factory"):
            raise CuratedError(f"{where}: match doit valoir address ou factory")
        _check_common(where, k)
        target = c.by_address if k["match"] == "address" else c.by_factory
        target[to_checksum_address(k["address"])] = k
    for i, r in enumerate(raw.get("relations", [])):
        where = f"curated.relations[{i}]"
        if r.get("type") not in EDGE_TYPES:
            raise CuratedError(f"{where}: type {r.get('type')!r} hors vocabulaire")
        for end in ("from", "to"):
            if r.get(end) not in c.entities:
                raise CuratedError(f"{where}: {end}={r.get(end)!r} absent de entities")
        if not 0 <= float(r.get("weight", 1.0)) <= 1:
            raise CuratedError(f"{where}: weight hors [0,1]")
        _check_common(where, r)
        c.relations.append(r)
    return c
