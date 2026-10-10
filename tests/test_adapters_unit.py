"""T3/T5/T6/T7/T8 — adaptateurs testés avec un faux contexte (aucun réseau)."""
import pytest
from eth_abi import encode
from eth_utils import keccak

from discovery.adapters.erc20 import classify, read_token
from discovery.adapters.morpho import PARAMS_TYPES, read_market, to_assets_up
from discovery.adapters.oracles import ROUND, classify_oracle, discover_oracle
from tests.fakes import FakeCtx, addr

TS = 1_700_000_000


# ------------------------------------------------------------------ ERC-20 / classification
def test_read_token_and_bytes32_symbol_fallback():
    t = addr(1)
    ctx = FakeCtx({
        (t, "symbol()", ()): "USDC",
        (t, "decimals()", ()): 6,
        (t, "totalSupply()", ()): 10**12,
        (t, "name()", ()): "USD Coin",
    })
    info = read_token(ctx, t)
    assert info["symbol"] == "USDC" and info["decimals"] == 6 and info["name"] == "USD Coin"

    old = addr(2)   # vieux token : symbol() renvoie un bytes32 (ex. MKR)
    ctx2 = FakeCtx({(old, "symbol()", ()): "0x" + b"MKR".ljust(32, b"\x00").hex(), (old, "decimals()", ()): 18})
    # la 1re tentative (décodage en `string`) doit échouer, comme sur un vrai vieux token
    real_call = ctx2.call

    def call(address, signature, args=(), returns=("uint256",)):
        if signature == "symbol()" and list(returns) == ["string"]:
            from discovery.ctx import CallFailed
            raise CallFailed("pas une string")
        return real_call(address, signature, args, returns)
    ctx2.call = call
    assert read_token(ctx2, old)["symbol"] == "MKR"


def test_not_a_token_returns_none():
    assert read_token(FakeCtx(), addr(3)) is None


def test_classification_order_pendle_before_erc4626():
    pt, sy, vault, plain = addr(10), addr(11), addr(12), addr(13)
    ctx = FakeCtx({
        (pt, "SY()", ()): sy, (pt, "YT()", ()): addr(14), (pt, "expiry()", ()): TS + 86400,
        # un SY Pendle expose AUSSI asset() : il ne doit pas être pris pour un ERC-4626
        (sy, "yieldToken()", ()): vault, (sy, "assetInfo()", ()): (0, plain, 18), (sy, "asset()", ()): plain,
        (sy, "totalAssets()", ()): 1,
        (vault, "asset()", ()): plain, (vault, "totalAssets()", ()): 5, (vault, "decimals()", ()): 18,
        (vault, "convertToAssets(uint256)", (10**18,)): 12 * 10**17,
    })
    assert classify(ctx, pt) == "pendle_pt"
    assert classify(ctx, sy) == "pendle_sy"
    assert classify(ctx, vault) == "erc4626"
    assert classify(ctx, plain) == "erc20"


# ------------------------------------------------------------------ Morpho
def test_to_assets_up_rounds_up_like_morpho():
    # 1 part sur un marché vide : (1 × (0+1)) / (0+1e6) → arrondi vers le haut = 1
    assert to_assets_up(1, 0, 0) == 1
    assert to_assets_up(10**6, 10**6 - 1, 10**6 - 10**6) == 10**6
    assert to_assets_up(0, 123, 456) == 0


def _market_ctx(params, mid_hex):
    morpho = addr(100)
    mid = bytes.fromhex(mid_hex[2:])
    return FakeCtx({
        (morpho, "idToMarketParams(bytes32)", (mid,)): params,
        (morpho, "market(bytes32)", (mid,)): (1000, 1000 * 10**6, 900, 900 * 10**6, TS, 0),
    }, contracts={"morpho_blue": morpho})


def test_market_id_is_recomputed_and_checked():
    params = (addr(1), addr(2), addr(3), addr(4), 915 * 10**15)
    good_id = "0x" + keccak(encode(PARAMS_TYPES, list(params))).hex()
    m = read_market(_market_ctx(params, good_id), good_id)
    assert m["oracle"] == addr(3) and m["lltv"] == 915 * 10**15

    wrong_id = "0x" + "11" * 32
    with pytest.raises(ValueError, match="keccak256"):
        read_market(_market_ctx(params, wrong_id), wrong_id)


def test_unknown_market_is_refused():
    zero = "0x" + "00" * 20
    mid = "0x" + "22" * 32
    with pytest.raises(ValueError, match="n'existe pas"):
        read_market(_market_ctx((zero, zero, zero, zero, 0), mid), mid)


# ------------------------------------------------------------------ Oracles
def _linear_feed(feed, pt, answer):
    return {
        (feed, "PT()", ()): pt, (feed, "maturity()", ()): TS + 365 * 86400 // 10,
        (feed, "baseDiscountPerYear()", ()): 6 * 10**16,
        (feed, "latestRoundData()", ()): (0, answer, 0, 0, 0), (feed, "decimals()", ()): 18,
        (pt, "symbol()", ()): "PT-X",
    }


def _mco(oracle, base1, base2=None, quote1=None, scale=10**6, price=None):
    z = "0x" + "00" * 20
    return {
        (oracle, "BASE_FEED_1()", ()): base1, (oracle, "BASE_FEED_2()", ()): base2 or z,
        (oracle, "QUOTE_FEED_1()", ()): quote1 or z, (oracle, "QUOTE_FEED_2()", ()): z,
        (oracle, "BASE_VAULT()", ()): z, (oracle, "QUOTE_VAULT()", ()): z,
        (oracle, "BASE_VAULT_CONVERSION_SAMPLE()", ()): 1, (oracle, "QUOTE_VAULT_CONVERSION_SAMPLE()", ()): 1,
        (oracle, "SCALE_FACTOR()", ()): scale, (oracle, "price()", ()): price,
    }


def test_mco_with_single_linear_feed_is_fixed_and_lists_implicit_slots():
    oracle, feed, pt = addr(20), addr(21), addr(22)
    answer = 994 * 10**15
    expected_price = 10**6 * answer
    ctx = FakeCtx({**_mco(oracle, feed, price=expected_price), **_linear_feed(feed, pt, answer)}, timestamp=TS)
    assert classify_oracle(ctx, feed) == "pendle_linear_discount_feed"
    d = discover_oracle(ctx, oracle, scale_decimals=24)
    meta = d.nodes[0].meta
    assert meta["oracle_kind"] == "morpho_chainlink_oracle_v2"
    assert meta["pricing_mode"] == "fixed"                         # aucun composant de marché
    assert meta["price_recomputed_matches"] is True                # la composition est PROUVÉE
    assert "QUOTE_FEED_1" in meta["implicit_unit_slots"]           # USDC supposé = 1 en dur
    assert [e.to_key for e in d.edges] == [feed]


def test_mco_with_chainlink_feed_is_market_and_detects_wrong_price():
    oracle, linear, cl, pt = addr(30), addr(31), addr(32), addr(33)
    cl_answer = 99_000_000   # 0,99 $ en 8 décimales
    responses = {
        **_mco(oracle, linear, base2=cl, scale=10**10, price=12345),   # price() faux exprès
        **_linear_feed(linear, pt, 10**18),
        (cl, "aggregator()", ()): addr(34), (cl, "phaseId()", ()): 2, (cl, "description()", ()): "USDe / USD",
        (cl, "latestRoundData()", ()): (77, cl_answer, TS, TS - 60, 77), (cl, "decimals()", ()): 8,
    }
    ctx = FakeCtx(responses, timestamp=TS, contracts={"ens_registry": addr(99)})
    d = discover_oracle(ctx, oracle, scale_decimals=24)
    meta = d.nodes[0].meta
    assert meta["pricing_mode"] == "market"
    assert meta["price_recomputed_matches"] is False               # on ne masque JAMAIS une incohérence
    assert classify_oracle(ctx, cl) == "chainlink_aggregator_proxy"


def test_constant_feed_detection():
    feed = addr(40)
    ctx = FakeCtx({(feed, "latestRoundData()", ()): (1, 10**12, TS, TS, 1), (feed, "decimals()", ()): 12,
                   (feed, "description()", ()): "Dummy feed"}, timestamp=TS)
    assert classify_oracle(ctx, feed) == "constant_feed"
    stale = FakeCtx({(feed, "latestRoundData()", ()): (1, 10**12, TS, TS - 999, 1), (feed, "decimals()", ()): 12},
                    timestamp=TS)
    assert classify_oracle(stale, feed) == "chainlink_compatible_unknown"   # pas assez de preuve → inconnu


def test_unknown_oracle_is_marked_unresolved_not_guessed():
    o = addr(50)
    ctx = FakeCtx({(o, "price()", ()): 10**24})
    d = discover_oracle(ctx, o, scale_decimals=24)
    meta = d.nodes[0].meta
    assert meta["oracle_kind"] == "unknown_morpho_oracle"
    assert meta["pricing_mode"] == "unknown" and meta["unresolved"] is True
    assert d.edges == []


def test_round_constant_is_aggregator_v3_signature():
    assert ROUND[0] == "latestRoundData()" and len(ROUND[1]) == 5


# ------------------------------------------------------------------ Position Morpho
def _position_setup(collateral, borrow_shares):
    from discovery.adapters.morpho import discover_position  # noqa: F401  (import local pour la lisibilité)
    morpho, loan, coll, oracle, user = addr(100), addr(101), addr(102), addr(103), addr(104)
    mid_hex = "0x" + "33" * 32
    mid = bytes.fromhex(mid_hex[2:])
    m = {"morpho": morpho, "market_id": mid_hex, "mid": mid, "loan_token": loan, "collateral_token": coll,
         "oracle": oracle, "lltv": 915 * 10**15,
         "expected_total_borrow_assets": 900 * 10**6, "total_borrow_shares": 900 * 10**6 * 10**6}
    ctx = FakeCtx({
        (loan, "decimals()", ()): 6, (coll, "decimals()", ()): 18,
        (oracle, "price()", ()): 99 * 10**22,                       # 1 collatéral = 0,99 USDC (échelle 1e24)
        (morpho, "position(bytes32,address)", (mid, user)): (0, borrow_shares, collateral),
    })
    return ctx, m, user


def test_position_health_metrics():
    from discovery.adapters.morpho import discover_position
    ctx, m, user = _position_setup(collateral=1000 * 10**18, borrow_shares=800 * 10**6 * 10**6)
    d, meta, value_usd = discover_position(ctx, m, user, None)
    assert meta["collateral_value_in_loan_token"] == 990.0
    assert abs(meta["borrow_human"] - 800.0) < 1e-3
    assert abs(meta["health_factor"] - 990 * 0.915 / 800) < 1e-4
    assert abs(value_usd - 990.0) < 1e-6
    assert d.edges[0].type == "deployed_in" and "position(" in d.edges[0].evidence


def test_empty_position_is_refused_and_hypothetical_is_allowed():
    from discovery.adapters.morpho import discover_position
    ctx, m, user = _position_setup(collateral=0, borrow_shares=0)
    with pytest.raises(ValueError, match="aucune position"):
        discover_position(ctx, m, user, None)
    d, meta, value_usd = discover_position(ctx, m, None, 1_000_000)
    assert meta["hypothetical"] is True and value_usd == 1_000_000
