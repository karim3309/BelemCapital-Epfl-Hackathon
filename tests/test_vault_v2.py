"""Step 3 tests — vault V2 and new oracles — WITHOUT network (FakeCtx)."""
from eth_abi import encode
from eth_utils import keccak

from discovery.adapters.morpho import PARAMS_TYPES, market_key
from discovery.adapters.oracles import classify_oracle, discover_oracle
from discovery.graph import POSITION_KEY
from stacktrace.vault_v2 import discover_vault_v2
from tests.fakes import FakeCtx, addr

TS = 1_700_000_000
ROUND = "latestRoundData()"


# ------------------------------------------------------------------ Midas feed (price set by an admin)
def test_midas_custom_feed_is_fixed_and_exposes_bounds():
    f = addr(10)
    ctx = FakeCtx({
        (f, "maxAnswerDeviation()", ()): 10**8, (f, "minAnswer()", ()): 90 * 10**8, (f, "maxAnswer()", ()): 110 * 10**8,
        (f, "lastTimestamp()", ()): TS - 86400, (f, ROUND, ()): (2, 100 * 10**8, 0, TS - 86400, 2),
        (f, "decimals()", ()): 8, (f, "description()", ()): "mX/EUR",
    }, timestamp=TS)
    assert classify_oracle(ctx, f) == "midas_custom_aggregator_feed"
    node = discover_oracle(ctx, f).nodes[0]
    assert node.meta["pricing_mode"] == "fixed"
    assert node.meta["min_answer"] == 90 and node.meta["max_answer"] == 110
    assert node.meta["age_seconds"] == 86400 and "setRoundData" in node.meta["pricing_detail"]


# ------------------------------------------------------------------ wstETH feed (market × internal rate)
def test_wsteth_feed_links_market_feed_and_token():
    f, cl, wst = addr(20), addr(21), addr(22)
    ctx = FakeCtx({
        (f, "stETHtoETHPriceFeed()", ()): cl, (f, "wstETH()", ()): wst,
        (f, ROUND, ()): (1, 12 * 10**7, 0, TS, 1), (f, "decimals()", ()): 8,
        # the stETH/ETH feed is a Chainlink proxy → "market" mode
        (cl, "aggregator()", ()): addr(23), (cl, "phaseId()", ()): 1, (cl, "description()", ()): "STETH / ETH",
        (cl, ROUND, ()): (5, 10**18, 0, TS, 5),
    }, timestamp=TS)
    assert classify_oracle(ctx, f) == "wsteth_price_feed"
    d = discover_oracle(ctx, f)
    assert d.nodes[0].meta["pricing_mode"] == "market"
    assert {(e.to_key, e.type) for e in d.edges} == {(cl, "priced_by"), (wst, "priced_by")}
    assert {t.kind for t in d.follow} == {"oracle", "token"}


# ------------------------------------------------------------------ vault V2 → adapter → market
def _vault_world():
    vault, holder, asset, adapter, coll, oracle, irm, morpho, curator = (addr(i) for i in range(30, 39))
    params = (asset, coll, oracle, irm, 86 * 10**16)
    mid_hex = "0x" + keccak(encode(PARAMS_TYPES, list(params))).hex()
    mid = bytes.fromhex(mid_hex[2:])
    shares = 7 * 10**18
    responses = {
        # vault: 1,000 EURCV in total, of which 100 not placed (idle); the holder has 500
        (vault, "name()", ()): "Vault Test", (vault, "asset()", ()): asset, (vault, "totalAssets()", ()): 1000 * 10**6,
        (vault, "balanceOf(address)", (holder,)): shares, (vault, "convertToAssets(uint256)", (shares,)): 500 * 10**6,
        (vault, "curator()", ()): curator, (vault, "owner()", ()): curator, (vault, "liquidityAdapter()", ()): adapter,
        (vault, "adaptersLength()", ()): 1, (vault, "adapters(uint256)", (0,)): adapter,
        (vault, "forceDeallocatePenalty(address)", (adapter,)): 0,
        (asset, "decimals()", ()): 6, (asset, "symbol()", ()): "EURCV", (asset, "balanceOf(address)", (vault,)): 100 * 10**6,
        # "Morpho market" adapter (current version): 900 EURCV in 1 market
        (adapter, "parentVault()", ()): vault, (adapter, "marketIdsLength()", ()): 1,
        (adapter, "marketIds(uint256)", (0,)): mid_hex, (adapter, "expectedSupplyAssets(bytes32)", (mid,)): 900 * 10**6,
        # market: 1,000 supplied, 900 borrowed → only 100 of liquidity available
        (morpho, "idToMarketParams(bytes32)", (mid,)): params,
        (morpho, "market(bytes32)", (mid,)): (1000 * 10**6, 1000 * 10**12, 900 * 10**6, 900 * 10**12, TS, 0),
        (coll, "symbol()", ()): "WBTC", (coll, "decimals()", ()): 8,
    }
    return FakeCtx(responses, timestamp=TS, contracts={"morpho_blue": morpho}), vault, holder, mid_hex, curator


def test_vault_v2_allocation_weights_and_exit_liquidity():
    ctx, vault, holder, mid_hex, curator = _vault_world()
    d = discover_vault_v2(ctx, vault, holder)
    edges = {(e.from_key, e.to_key, e.type): e for e in d.edges}

    assert (POSITION_KEY, vault, "deployed_in") in edges                 # holder → vault (balanceOf)
    alloc = edges[(vault, market_key(mid_hex), "deployed_in")]          # vault → market, weight = vault's share
    assert abs(alloc.weight - 0.9) < 1e-9 and "expectedSupplyAssets" in alloc.evidence

    v = next(n for n in d.nodes if n.key == vault).meta
    # withdrawable = idle 100 + min(900 supplied, 100 of market liquidity) = 200 → 40% of the pocket (500)
    assert v["exit_liquidity"]["withdrawable_now_human"] == 200
    assert v["exit_liquidity"]["covers_holder_share"] == 0.4
    assert v["holder_share_of_vault"] == 0.5

    cur = next(n for n in d.nodes if n.type == "issuer")
    assert cur.meta["unresolved"] and cur.meta["curator_address"] == curator   # identity NOT guessed
    assert any(e.type == "issued_by" and "curator()" in e.evidence for e in d.edges)
    assert not any(t.kind == "vaults_lookup" for t in d.follow)               # co-lenders excluded


def test_whole_vault_is_the_curator_view():
    """holder == vault: the position is the WHOLE vault (all depositors), read with totalAssets()."""
    ctx, vault, _, mid_hex, _ = _vault_world()
    ctx.responses[(vault, "totalSupply()", ())] = 2 * 10**18
    d = discover_vault_v2(ctx, vault, vault)
    root = next(e for e in d.edges if e.from_key == POSITION_KEY)
    assert root.to_key == vault and "totalAssets()" in root.evidence and "whole vault" in root.evidence

    v = next(n for n in d.nodes if n.key == vault).meta
    assert v["whole_vault"] and v["holder_share_of_vault"] == 1.0
    # the same 200 withdrawable now, but measured against the whole vault (1,000) → 20%
    assert v["exit_liquidity"]["covers_holder_share"] == 0.2
