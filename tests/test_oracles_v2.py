"""Étape 4 — nouveaux types d'oracle rencontrés dans le portefeuille réel (FakeCtx, aucun réseau)."""
from discovery.adapters.oracles import classify_oracle, discover_oracle
from tests.fakes import FakeCtx, addr

TS = 1_700_000_000
R = "latestRoundData()"


def test_weeth_rate_adapter_is_internal_rate_and_points_to_token():
    a, weeth = addr(40), addr(41)
    ctx = FakeCtx({(a, "WEETH()", ()): weeth, (a, R, ()): (0, 11 * 10**17, 0, 0, 0), (a, "decimals()", ()): 18,
                   (a, "description()", ()): "weETH/ETH exchange rate"}, timestamp=TS)
    assert classify_oracle(ctx, a) == "weeth_exchange_rate_adapter"
    d = discover_oracle(ctx, a)
    assert d.nodes[0].meta["pricing_mode"] == "internal_rate"
    assert [(e.to_key, e.type) for e in d.edges] == [(weeth, "priced_by")]
    assert "updatedAt = 0" in d.nodes[0].meta["note"]


def test_nav_adapter_needs_the_nav_description():
    a, tok = addr(42), addr(43)
    base = {(a, "token()", ()): tok, (a, R, ()): (0, 10**18, 0, 0, 0), (a, "decimals()", ()): 18}
    nav = FakeCtx({**base, (a, "description()", ()): "Net Asset Value in USD"}, timestamp=TS)
    assert classify_oracle(nav, a) == "nav_chainlink_adapter"
    other = FakeCtx({**base, (a, "description()", ()): "Something else"}, timestamp=TS)
    assert classify_oracle(other, a) != "nav_chainlink_adapter"          # token() seul ne suffit pas


def test_redstone_fundamental_vs_market():
    a = addr(44)
    common = {(a, "getDataFeedId()", ()): "0x" + b"strUSD_FUNDAMENTAL".ljust(32, b"\x00").hex(),
              (a, "getPriceFeedAdapter()", ()): addr(45), (a, R, ()): (1, 103 * 10**6, 0, TS, 1), (a, "decimals()", ()): 8}
    fund = FakeCtx({**common, (a, "description()", ()): "RedStone Price Feed for strUSD_FUNDAMENTAL"}, timestamp=TS)
    n = discover_oracle(fund, a).nodes[0]
    assert n.meta["pricing_mode"] == "internal_rate" and n.meta["data_feed_id"] == "strUSD_FUNDAMENTAL"
    mkt = FakeCtx({**common, (a, "description()", ()): "RedStone Price Feed for ETH"}, timestamp=TS)
    assert discover_oracle(mkt, a).nodes[0].meta["pricing_mode"] == "market"


def test_chainlink_exchange_rate_feed_is_not_a_market_price():
    a = addr(46)
    ctx = FakeCtx({(a, "aggregator()", ()): addr(47), (a, "phaseId()", ()): 1,
                   (a, "description()", ()): "PST-USDC Exchange Rate (Calculated)",
                   (a, R, ()): (7, 113 * 10**4, 0, TS, 7), (a, "decimals()", ()): 6},
                  timestamp=TS, contracts={"ens_registry": addr(48)})   # ENS : aucun nom → émetteur non prouvé
    assert classify_oracle(ctx, a) == "chainlink_aggregator_proxy"
    n = discover_oracle(ctx, a).nodes[0]
    assert n.meta["pricing_mode"] == "internal_rate" and "docs.chain.link" in n.meta["pricing_basis"]
