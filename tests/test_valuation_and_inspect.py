"""Intérêts Morpho, valorisation USD et inspecteur networkx."""
import math

from discovery.adapters.morpho import WAD, accrue_interest, w_taylor_compounded
from discovery.graph import POSITION_KEY, Edge, GraphBuilder, Node
from discovery.graph import to_networkx
from discovery.ids import position_id
from discovery.inspect_graph import print_impact
from discovery.valuation import value_graph
from tests.fakes import FakeCtx, addr

TS = 1_700_000_000


def test_taylor_compounding_is_close_to_exp():
    rate = int(0.05 / (365 * 86400) * WAD)          # 5 %/an par seconde
    one_year = 365 * 86400
    approx = w_taylor_compounded(rate, one_year) / WAD
    assert abs(approx - (math.exp(0.05) - 1)) < 1e-4


def test_interest_is_accrued_since_last_update():
    irm = addr(7)
    m = {"irm": irm, "loan_token": addr(1), "collateral_token": addr(2), "oracle": addr(3), "lltv": 9 * 10**17,
         "state": (1000, 0, 1000, 0, TS - 86400, 0), "last_update": TS - 86400,
         "total_borrow_assets": 10**12, "total_supply_assets": 2 * 10**12}
    rate = 10**9                                       # ~3,2 %/an
    sig = ("borrowRateView((address,address,address,address,uint256),"
           "(uint128,uint128,uint128,uint128,uint128,uint128))")
    params = (addr(1), addr(2), addr(3), irm, 9 * 10**17)
    ctx = FakeCtx({(irm, sig, (params, m["state"])): rate}, timestamp=TS)
    accrue_interest(ctx, m)
    assert m["seconds_since_last_update"] == 86400
    assert m["accrued_interest"] == 10**12 * w_taylor_compounded(rate, 86400) // WAD > 0
    assert m["expected_total_borrow_assets"] == 10**12 + m["accrued_interest"]


def _priced_graph():
    g = GraphBuilder()
    usdc, usde, susde, pt = addr(1), addr(2), addr(3), addr(4)
    mkey = "morpho_market:0x" + "cd" * 32
    g.add_node(Node(mkey, "lending_market", "M", "m", address=addr(9), meta={
        "loan_token": usdc, "collateral_token": pt, "oracle": addr(5), "total_supply_human": 1000.0}))
    g.add_node(Node(addr(5), "oracle", "O", "o", address=addr(5), meta={"price": 0.99, "pricing_mode": "fixed"}))
    g.add_node(Node(addr(6), "oracle", "F", "f", address=addr(6), meta={
        "oracle_kind": "chainlink_aggregator_proxy", "description": "USDe / USD", "answer": 0.98}))
    for a, sym, kind, extra in ((usdc, "USDC", "erc20", {}), (usde, "USDe", "erc20", {}),
                                (susde, "sUSDe", "erc4626_vault", {"underlying": usde, "share_to_asset_rate": 1.2}),
                                (pt, "PT-X", "pendle_pt", {})):
        g.add_node(Node(a, "asset", sym, sym.lower(), address=a,
                        meta={"symbol": sym, "asset_kind": kind, "total_supply_human": 10.0, "decimals": 18, **extra}))
    return g, mkey


def test_valuation_uses_only_proven_prices():
    g, mkey = _priced_graph()
    value_graph(g, mkey, 1.0, "Chainlink USDC/USD", TS)
    meta = {n.label: n.meta for n in g.nodes.values()}
    assert meta["USDe"]["price_usd"] == 0.98                    # feed Chainlink découvert
    assert abs(meta["sUSDe"]["price_usd"] - 1.2 * 0.98) < 1e-12  # taux interne × sous-jacent
    assert meta["PT-X"]["price_usd"] == 0.99                     # oracle Morpho × USDC
    assert meta["USDe"]["tvl_usd"] == 9.8
    assert meta["F"]["priced_asset"] == addr(2)
    assert meta["M"]["tvl_usd"] == 1000.0


def test_impact_walks_up_to_the_position(capsys):
    g = GraphBuilder()
    mkey = "morpho_market:0x" + "ab" * 32
    g.add_node(Node(mkey, "lending_market", "M", "morpho_market_abababab", address=addr(9)))
    g.add_node(Node(addr(2), "asset", "PT", "pt", address=addr(2)))
    g.add_node(Node("issuer:acme", "issuer", "Acme", "acme", chain=None))
    g.add_edge(Edge(POSITION_KEY, mkey, "deployed_in", "onchain", f"x @ {addr(9)} #1"))
    g.add_edge(Edge(mkey, addr(2), "collateralized_by", "onchain", f"x @ {addr(9)} #1"))
    g.add_edge(Edge(addr(2), "issuer:acme", "issued_by", "curated", "https://acme.example"))
    graph = g.to_contract(position_id("0x" + "ab" * 32, addr(8)), 1)
    print_impact(to_networkx(graph), graph["position"]["id"], "acme")
    out = capsys.readouterr().out
    assert "3 élément(s)" in out and "pt --issued_by--> acme" in out
