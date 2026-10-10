"""T4 — modèle de graphe, ids et validateur du contrat JSON."""
import copy

import pytest

from discovery.graph import POSITION_KEY, Edge, GraphBuilder, Node
from discovery.ids import morpho_market_id, position_id, slugify, token_id
from discovery.validate import validate
from tests.fakes import addr

MID = "0x" + "ab" * 32
USER = addr(9)


@pytest.mark.parametrize("raw,expected", [
    ("PT-sUSDE-26NOV2026", "pt_susde_26nov2026"),
    ("sUSDe", "susde"),
    ("USDe / USD", "usde_usd"),
    ("  --  ", "node"),
])
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_id_helpers():
    assert token_id("SY-sUSDE") == "sy_susde"
    assert morpho_market_id("0x5613b170ded2") == "morpho_market_5613b170"
    assert position_id(MID, USER) == f"morpho:{MID}:{USER}"


def _tiny_graph() -> GraphBuilder:
    g = GraphBuilder()
    mkey = f"morpho_market:{MID}"
    g.add_node(Node(mkey, "lending_market", "Marché", "morpho_market_abababab", address=addr(0xBEEFCAFE)))
    g.add_node(Node(addr(2), "asset", "PT-X", "pt_x", address=addr(2)))
    g.add_node(Node("chain:ethereum", "chain", "Ethereum", "ethereum"))
    g.add_edge(Edge(POSITION_KEY, mkey, "deployed_in", "onchain", f"Morpho.position() @ {addr(1)} #100"))
    g.add_edge(Edge(mkey, addr(2), "collateralized_by", "onchain", f"Morpho.idToMarketParams() @ {addr(1)} #100"))
    g.add_edge(Edge(addr(2), "chain:ethereum", "settled_on", "onchain", f"eth_getCode({addr(2)}) = 10 octets #100"))
    return g


def _valid() -> dict:
    return _tiny_graph().to_contract(position_id(MID, USER), 1000)


def test_valid_graph_passes():
    graph = _valid()
    assert validate(graph) == []
    assert set(graph) == {"position", "nodes", "edges"}
    assert {n["id"] for n in graph["nodes"]} == {"morpho_market_abababab", "pt_x", "ethereum"}


def test_id_collisions_get_address_suffix():
    g = GraphBuilder()
    g.add_node(Node(addr(1), "asset", "X", "same", address=addr(1)))
    g.add_node(Node(addr(2), "asset", "X", "same", address=addr(2)))
    assert sorted(g.assign_ids().values()) == ["same", "same_000000"]


def test_node_and_edge_guards():
    with pytest.raises(ValueError):
        Node("k", "token", "x", "x")                       # type hors vocabulaire
    with pytest.raises(ValueError):
        Edge("a", "b", "depends_on", "onchain", "preuve")  # type d'arête hors vocabulaire
    with pytest.raises(ValueError):
        Edge("a", "b", "priced_by", "memory", "preuve")    # source inventée
    with pytest.raises(ValueError):
        Edge("a", "b", "priced_by", "onchain", "  ")       # pas de preuve
    g = GraphBuilder()
    g.add_node(Node("a", "asset", "a", "a", address=addr(1)))
    with pytest.raises(ValueError):
        g.add_node(Node("a", "oracle", "a", "a", address=addr(1)))   # même clé, autre type


def test_dangling_edge_is_refused_at_export():
    g = _tiny_graph()
    g.add_edge(Edge(addr(2), "issuer:ghost", "issued_by", "curated", "https://example.org"))
    with pytest.raises(ValueError, match="inexistant"):
        g.to_contract(position_id(MID, USER), 1)


def _mutate(fn):
    graph = copy.deepcopy(_valid())
    fn(graph)
    return validate(graph)


@pytest.mark.parametrize("mutation,needle", [
    (lambda g: g.pop("edges"), "premier niveau"),
    (lambda g: g["position"].update(id="morpho:bad"), "position.id"),
    (lambda g: g["nodes"][0].update(type="token"), "hors vocabulaire"),
    (lambda g: g["nodes"][0].update(address=g["nodes"][0]["address"].lower()), "checksum"),
    (lambda g: g["edges"][0].update(source="memory"), "source"),
    (lambda g: g["edges"][0].update(evidence="trust me"), "preuve"),
    (lambda g: g["edges"][0].update(to="nowhere"), "inexistant"),
    (lambda g: g["edges"][0].update(weight=2), "weight"),
    (lambda g: g["edges"].append(dict(g["edges"][0])), "dupliquée"),
    (lambda g: g["nodes"][0]["meta"].update(pricing_mode="vibes"), "pricing_mode"),
    (lambda g: g["nodes"][0]["meta"].update(note="adresse 0x..."), "placeholder"),
])
def test_validator_catches(mutation, needle):
    errors = _mutate(mutation)
    assert errors and any(needle in e for e in errors), errors


def test_validator_rejects_forbidden_shape():
    def bad(g):
        # un actif ne peut pas être « collateralized_by » : seul un marché de prêt l'est
        g["edges"].append({"from": "pt_x", "to": "ethereum", "type": "collateralized_by", "weight": 1.0,
                           "source": "onchain", "evidence": f"x @ {addr(2)} #100"})
    assert any("forme interdite" in e for e in _mutate(bad))


def test_validator_rejects_orphans():
    def orphan(g):
        g["nodes"].append({"id": "lonely", "type": "issuer", "label": "Seul", "address": None,
                           "chain": None, "meta": {}})
    assert any("non reliés" in e for e in _mutate(orphan))


def test_offchain_evidence_needs_url():
    def no_url(g):
        g["edges"][1]["source"] = "curated"
    assert any("sans URL" in e for e in _mutate(no_url))
