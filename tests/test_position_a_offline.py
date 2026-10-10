"""T12 — "golden" test: position A is replayed 100% from data/cache/ (zero network).

This test guarantees three things for the demo:
  1. the committed cache is enough (no network call, even if the Wi-Fi drops);
  2. the graph complies with the JSON contract;
  3. the graph does contain the expected dependencies of position A (and their evidence).
"""
import json

import pytest

from discovery.build_graph import build
from discovery.config import REPO_ROOT, load_config
from discovery.validate import validate


@pytest.fixture(scope="module")
def result():
    config = load_config(REPO_ROOT / "config.yaml", offline=True)
    if config.snapshot_block == "latest":
        pytest.skip("snapshot_block: latest → pin a block in config.yaml to replay offline")
    graph, report, cache = build(config)
    return config, graph, report, cache


def _node(graph, nid):
    return next(n for n in graph["nodes"] if n["id"] == nid)


def _edges(graph):
    return {(e["from"], e["type"], e["to"]) for e in graph["edges"]}


def test_no_network_and_full_cache_hits(result):
    _, _, _, cache = result
    assert cache.stats.misses == 0 and cache.stats.writes == 0


def test_contract_is_valid(result):
    _, graph, _, _ = result
    assert validate(graph) == []


def test_matches_committed_output(result):
    config, graph, _, _ = result
    committed = json.loads(config.output_file.read_text(encoding="utf-8"))
    assert graph == committed, "output/graph.json is out of date: re-run python -m discovery.build_graph --offline"


def test_expected_dependency_chain(result):
    config, graph, _, _ = result
    market = f"morpho_market_{config.market_id[2:10]}"
    edges = _edges(graph)
    expected = {
        (graph["position"]["id"], "deployed_in", market),
        (market, "collateralized_by", "pt_susde_26nov2026"),
        (market, "lends", "usdc"),
        (market, "priced_by", "oracle_meta_f8b29e"),
        ("pt_susde_26nov2026", "redeemable_into", "sy_susde"),
        ("sy_susde", "redeemable_into", "susde"),
        ("susde", "redeemable_into", "usde"),
        ("usde", "issued_by", "ethena_labs"),
        ("usdc", "issued_by", "circle"),
        ("pt_susde_26nov2026", "deployed_in", "pendle_plp_susde_26nov2026"),
        ("pt_susde_26nov2026", "issued_by", "pendle"),
        ("feed_usde_usd", "issued_by", "chainlink"),
        ("ethena_labs", "deployed_in", "copper"),
        ("pt_susde_26nov2026", "settled_on", "ethereum"),
    }
    missing = expected - edges
    assert not missing, f"missing edges: {missing}"


def test_oracle_story_is_captured(result):
    _, graph, _, _ = result
    meta = _node(graph, "oracle_meta_f8b29e")["meta"]
    assert meta["pricing_mode"] == "hybrid"
    assert meta["primary_pricing_mode"] == "fixed"      # primary: linear discount only (USDe = USDC = 1)
    assert meta["backup_pricing_mode"] == "market"      # backup: × Chainlink USDe/USD
    for oid in ("oracle_morpho_v2_8fca98", "oracle_morpho_v2_e2f4cf"):
        assert _node(graph, oid)["meta"]["price_recomputed_matches"] is True
        assert _node(graph, oid)["meta"]["created_by_official_factory"] is True
    assert _node(graph, "feed_pt_susde_26nov2026_linear_discount")["meta"]["formula_matches"] is True
    assert _node(graph, "feed_usde_usd")["meta"]["ens_resolves_to_this_feed"] is True


def test_every_edge_has_known_source_and_evidence(result):
    _, graph, _, _ = result
    for e in graph["edges"]:
        assert e["source"] in {"onchain", "api", "curated"}
        assert len(e["evidence"]) > 20
