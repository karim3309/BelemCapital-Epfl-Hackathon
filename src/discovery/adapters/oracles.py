"""Oracles: WHO tells Morpho what the collateral is worth?  (the most important point of position A)

Morpho calls `oracle.price()` and trusts it blindly. That number is the price
of 1 unit of collateral in units of the lent asset, scaled by 1e(36 + loan_dec − collateral_dec).

A Morpho oracle is often an ASSEMBLY of building blocks. We take it apart recursively:
  - meta-oracle (primary + fallback, switches on deviation) → pricing_mode "hybrid"
  - MorphoChainlinkOracleV2: price = SCALE × vaults × BASE_FEED_1 × BASE_FEED_2 / (QUOTE_FEED_1 × QUOTE_FEED_2)
        ⚠ a slot at address 0x0 counts as 1: it is an implicit FIXED price (e.g. "1 USDe = 1 USDC")
  - Pendle linear-discount feed: price = 1 − discount × time remaining   → "fixed" (ignores the market)
  - Chainlink feed (proven via ENS data.eth)                             → "market"
  - constant / "dummy" feed (only used to adjust decimals)              → "fixed"
  - feed ERC-4626 (convertToAssets)                                        → "internal_rate"
Anything we do not recognise is marked `unresolved`: we NEVER guess a pricing mode.
"""
from __future__ import annotations

from ..ctx import Ctx, checksum, is_zero
from ..graph import Edge, Node
from ..ids import contract_id, slugify
from . import Discovery, Task, jsonable, scaled
from .ens import chainlink_ens_name, resolve

CHAINLINK_ISSUER_KEY = "issuer:chainlink"
CHAINLINK_ENS_DOC = "https://docs.chain.link/data-feeds/ens"
STEAKHOUSE_DOC = "https://steakhouse.financial/docs/products/infrastructure/metaoracle"

ROUND = ("latestRoundData()", ["uint80", "int256", "uint256", "uint256", "uint80"])
META_PROBES = [("primaryOracle()", ["address"]), ("backupOracle()", ["address"]), ("currentOracle()", ["address"])]
MCO_V2_PROBES = [("BASE_FEED_1()", ["address"]), ("QUOTE_FEED_1()", ["address"]),
                 ("SCALE_FACTOR()", ["uint256"]), ("BASE_VAULT()", ["address"])]
MCO_V1_PROBES = [("BASE_FEED_1()", ["address"]), ("QUOTE_FEED_1()", ["address"]),
                 ("SCALE_FACTOR()", ["uint256"]), ("VAULT()", ["address"])]
LINEAR_PROBES = [("PT()", ["address"]), ("maturity()", ["uint256"]), ("baseDiscountPerYear()", ["uint256"]), ROUND]
# ⚠ Pendle TWAP feed probes NOT VERIFIED against a real contract (not present in position A):
#    to be confirmed on Etherscan / Pendle docs before relying on them (see docs/VERIFY.md).
PENDLE_TWAP_PROBES = [("market()", ["address"]), ("twapDuration()", ["uint32"]), ROUND]
CL_PROXY_PROBES = [("aggregator()", ["address"]), ("phaseId()", ["uint16"]), ("description()", ["string"]), ROUND]
CL_COMPATIBLE_PROBES = [ROUND, ("decimals()", ["uint8"])]
# Midas "custom" feed: price PUSHED by an administrator (setRoundData), bounded by min/max/deviation.
# Functions taken from the verified code MGloEuroCustomAggregatorFeed (implementation behind a proxy
# deployed by the address labelled "Midas RWA: Deployer"):
MIDAS_CUSTOM_FEED_SOURCE = "https://etherscan.io/address/0xbFd25A5d18B2E49eb4d486A99d9373440909795a#code"
MIDAS_CUSTOM_FEED_PROBES = [("maxAnswerDeviation()", ["uint256"]), ("minAnswer()", ["int192"]),
                            ("maxAnswer()", ["int192"]), ("lastTimestamp()", ["uint256"]), ROUND]
# WstETHPriceFeed (Compound): wstETH price = stETH/ETH feed (market) × wstETH internal rate.
# Functions taken from the verified code (constructor: stETHtoETHPriceFeed_, wstETH_, decimals_):
WSTETH_FEED_SOURCE = "https://etherscan.io/address/0x4F67e4d9BD67eFa28236013288737D39AeF48e79#code"
WSTETH_FEED_PROBES = [("stETHtoETHPriceFeed()", ["address"]), ("wstETH()", ["address"]), ROUND]
# "Exchange rate / net asset value" adapters: they read a token's INTERNAL RATE, not a market.
# Names and functions taken from Etherscan verified codes (see *_SOURCE).
WEETH_RATE_SOURCE = "https://etherscan.io/address/0x4270E1817576bbA4b640466bE79A408Ef128F828#code"   # WeEthToEthExchangeRateAdapter
WEETH_RATE_PROBES = [("WEETH()", ["address"]), ROUND]
NAV_ADAPTER_SOURCE = "https://etherscan.io/address/0x9dD65b6d956E31F4dc093372D975275986695827#code"  # NetAssetValueChainlinkAdapter
NAV_ADAPTER_PROBES = [("token()", ["address"]), ("description()", ["string"]), ROUND]
# RedStone (push, Chainlink interface): getDataFeedId / getPriceFeedAdapter (verified implementations
# "EthereumPriceFeed…FundamentalWithoutRoundsV1"). An "…_FUNDAMENTAL" id = fundamental value (NAV / issuer
# rate), not a market price (data categories: https://docs.redstone.finance/docs/data/data-types/).
REDSTONE_SOURCE = "https://etherscan.io/address/0x7219beBd4929Dc52961fFe8bd41a6bE22b6060d6#code"
REDSTONE_PROBES = [("getDataFeedId()", ["bytes32"]), ("getPriceFeedAdapter()", ["address"]), ROUND]
# Rate wrapper that delegates to another oracle via oracle() (e.g. EthPlusPriceAdapter).
ORACLE_WRAPPER_SOURCE = "https://etherscan.io/address/0xf87d2F4d42856f0B6Eae140Aaf78bF0F777e9936#code"
ORACLE_WRAPPER_PROBES = [("oracle()", ["address"]), ROUND]
# Reserve Protocol: RTokenAsset (price of a basket of collaterals) — Etherscan verified code.
RTOKEN_ASSET_SOURCE = "https://etherscan.io/address/0x3f11C47E7ed54b24D7EFC222FD406d8E1F49Fb69#code"
RTOKEN_ASSET_PROBES = [("basketHandler()", ["address"]), ("backingManager()", ["address"]), ("erc20()", ["address"])]
# Chainlink classifies "Exchange Rate" feeds as ON-CHAIN data computed by the issuer, not a market price.
CHAINLINK_EXCHANGE_RATE_DOC = "https://docs.chain.link/data-feeds/data-sources"

KIND_LABEL = {
    "morpho_meta_oracle_deviation_timelock": "MetaOracleDeviationTimelock",
    "morpho_chainlink_oracle_v2": "MorphoChainlinkOracleV2",
    "morpho_chainlink_oracle_v1": "MorphoChainlinkOracle",
    "pendle_linear_discount_feed": "PendleLinearDiscountFeed",
    "pendle_twap_feed": "PendleTwapFeed",
    "chainlink_aggregator_proxy": "ChainlinkFeed",
    "constant_feed": "ConstantFeed",
    "midas_custom_aggregator_feed": "MidasCustomAggregatorFeed",
    "wsteth_price_feed": "WstETHPriceFeed",
    "weeth_exchange_rate_adapter": "WeEthToEthExchangeRateAdapter",
    "nav_chainlink_adapter": "NetAssetValueChainlinkAdapter",
    "redstone_price_feed": "RedStonePriceFeed",
    "oracle_wrapper": "OracleWrapper",
    "reserve_rtoken_asset": "RTokenAsset",
    "chainlink_compatible_unknown": "UnknownChainlinkCompatibleFeed",
    "unknown_morpho_oracle": "UnknownOracle",
    "unknown": "UnknownContract",
}
STATIC_MODE = {
    "morpho_meta_oracle_deviation_timelock": "hybrid",
    "pendle_linear_discount_feed": "fixed",
    "pendle_twap_feed": "market",
    "chainlink_aggregator_proxy": "market",
    "constant_feed": "fixed",
    "midas_custom_aggregator_feed": "fixed",   # value set by an admin: does NOT follow the market
    "weeth_exchange_rate_adapter": "internal_rate",
    "nav_chainlink_adapter": "internal_rate",
    "reserve_rtoken_asset": "unknown",         # price of a basket: not taken apart yet → we do not guess
    "chainlink_compatible_unknown": "unknown",
    "unknown_morpho_oracle": "unknown",
    "unknown": "unknown",
}


def latest_round(ctx: Ctx, address: str) -> tuple:
    """(roundId, answer, startedAt, updatedAt, answeredInRound) — Chainlink's AggregatorV3 interface."""
    return ctx.call(address, ROUND[0], returns=ROUND[1])


# ======================================================================= classification
def classify_oracle(ctx: Ctx, address: str) -> str:
    if ctx.has_functions(address, META_PROBES):
        return "morpho_meta_oracle_deviation_timelock"
    if ctx.has_functions(address, MCO_V2_PROBES):
        return "morpho_chainlink_oracle_v2"
    if ctx.has_functions(address, MCO_V1_PROBES):
        return "morpho_chainlink_oracle_v1"
    if ctx.has_functions(address, LINEAR_PROBES):
        return "pendle_linear_discount_feed"
    if ctx.has_functions(address, PENDLE_TWAP_PROBES):
        return "pendle_twap_feed"
    if ctx.has_functions(address, CL_PROXY_PROBES):
        return "chainlink_aggregator_proxy"
    if ctx.has_functions(address, MIDAS_CUSTOM_FEED_PROBES):
        return "midas_custom_aggregator_feed"
    if ctx.has_functions(address, WSTETH_FEED_PROBES):
        return "wsteth_price_feed"
    if ctx.has_functions(address, WEETH_RATE_PROBES):
        return "weeth_exchange_rate_adapter"
    if ctx.has_functions(address, REDSTONE_PROBES):
        return "redstone_price_feed"
    if ctx.has_functions(address, ORACLE_WRAPPER_PROBES):
        return "oracle_wrapper"
    if ctx.has_functions(address, NAV_ADAPTER_PROBES) and \
            "asset value" in (ctx.try_call(address, "description()", returns=["string"]) or "").lower():
        return "nav_chainlink_adapter"
    if ctx.has_functions(address, CL_COMPATIBLE_PROBES):
        return "constant_feed" if _looks_constant(ctx, address) else "chainlink_compatible_unknown"
    if ctx.has_functions(address, RTOKEN_ASSET_PROBES):
        return "reserve_rtoken_asset"
    if ctx.try_call(address, "price()", returns=["uint256"]) is not None:
        return "unknown_morpho_oracle"
    return "unknown"


def _looks_constant(ctx: Ctx, address: str) -> bool:
    """A real feed stores "rounds" updated by operators. A constant feed returns
    roundId ≤ 1 and updatedAt = current block timestamp (computed on the fly, nothing is stored)."""
    round_id, _, _, updated_at, _ = latest_round(ctx, address)
    return round_id <= 1 and updated_at == ctx.block_timestamp


def mode_of(ctx: Ctx, address: str, kind: str | None = None) -> str:
    kind = kind or classify_oracle(ctx, address)
    if kind in ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1"):
        return _mco_components(ctx, address, kind)[1]
    if kind == "wsteth_price_feed":        # stETH/ETH market feed × wstETH internal rate
        return _combine([mode_of(ctx, ctx.call(address, "stETHtoETHPriceFeed()", returns=["address"])), "internal_rate"])
    if kind == "chainlink_aggregator_proxy":
        return _chainlink_mode(ctx.try_call(address, "description()", returns=["string"]))
    if kind == "redstone_price_feed":
        return _redstone_mode(ctx.try_call(address, "description()", returns=["string"]))
    if kind == "oracle_wrapper":           # the rate comes from the inner oracle
        return mode_of(ctx, ctx.call(address, "oracle()", returns=["address"]))
    return STATIC_MODE[kind]


def _chainlink_mode(desc: str | None) -> str:
    """A Chainlink "… Exchange Rate …" feed = rate computed on-chain by the issuer (Chainlink docs), not a market."""
    return "internal_rate" if "exchange rate" in (desc or "").lower() else "market"


def _redstone_mode(desc: str | None) -> str:
    return "internal_rate" if "FUNDAMENTAL" in (desc or "").upper() else "market"


def _combine(modes: list[str]) -> str:
    if not modes:
        return "fixed"          # no component: price entirely hard-coded
    if "unknown" in modes:
        return "unknown"
    if "market" in modes or "hybrid" in modes:
        return "market"
    if "internal_rate" in modes:
        return "internal_rate"
    return "fixed"


# ======================================================================= discovery
def discover_oracle(ctx: Ctx, address: str, scale_decimals: int | None = None) -> Discovery:
    """scale_decimals = 36 + loan_dec − collateral_dec (provided by the Morpho market to read price())."""
    address = checksum(address)
    kind = classify_oracle(ctx, address)
    ctx.labels[address] = KIND_LABEL[kind]
    handler = {
        "morpho_meta_oracle_deviation_timelock": _meta_oracle,
        "morpho_chainlink_oracle_v2": _mco,
        "morpho_chainlink_oracle_v1": _mco,
        "pendle_linear_discount_feed": _linear_discount,
        "pendle_twap_feed": _pendle_twap,
        "chainlink_aggregator_proxy": _chainlink_proxy,
        "constant_feed": _constant_feed,
        "midas_custom_aggregator_feed": _midas_custom_feed,
        "wsteth_price_feed": _wsteth_feed,
        "weeth_exchange_rate_adapter": _token_rate_adapter,
        "nav_chainlink_adapter": _token_rate_adapter,
        "redstone_price_feed": _redstone_feed,
        "oracle_wrapper": _oracle_wrapper,
        "reserve_rtoken_asset": _rtoken_asset,
    }.get(kind, _unknown)
    return handler(ctx, address, kind, scale_decimals)


def _node(address: str, kind: str, id_hint: str, label: str, meta: dict) -> Node:
    return Node(key=address, type="oracle", label=label, id_hint=id_hint, address=address,
                meta={"oracle_kind": kind, **meta})


def _morpho_price(ctx: Ctx, address: str, scale_decimals: int | None) -> dict:
    raw = ctx.try_call(address, "price()", returns=["uint256"])
    out = {"price_raw": jsonable(raw)}
    if raw is not None and scale_decimals is not None:
        out["price"] = scaled(raw, scale_decimals)
        out["price_scale"] = f"1e{scale_decimals}"
    return out


# ---- primary / fallback meta-oracle --------------------------------------------------
def _meta_oracle(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    primary = ctx.call(a, "primaryOracle()", returns=["address"])
    backup = ctx.call(a, "backupOracle()", returns=["address"])
    current = ctx.call(a, "currentOracle()", returns=["address"])
    thr = ctx.try_call(a, "deviationThreshold()", returns=["uint256"])
    meta = {
        "pricing_mode": "hybrid",
        "primary_oracle": primary,
        "backup_oracle": backup,
        "current_oracle": current,
        "current_role": "primary" if current == primary else ("backup" if current == backup else "other"),
        "effective_pricing_mode": mode_of(ctx, current),
        "primary_pricing_mode": mode_of(ctx, primary),
        "backup_pricing_mode": mode_of(ctx, backup),
        "deviation_threshold": scaled(thr, 18) if thr is not None else None,
        "current_deviation": scaled(v, 18) if (v := ctx.try_call(a, "getDeviation()", returns=["uint256"])) is not None else None,
        "challenge_timelock_seconds": ctx.try_call(a, "challengeTimelockDuration()", returns=["uint256"]),
        "healing_timelock_seconds": ctx.try_call(a, "healingTimelockDuration()", returns=["uint256"]),
        "is_challenged": ctx.try_call(a, "isChallenged()", returns=["bool"]),
        "is_healing": ctx.try_call(a, "isHealing()", returns=["bool"]),
        "switch_rule": ("Deviation = |primary − fallback| / average. If it exceeds deviation_threshold, anyone "
                        "can call challenge(); if the deviation still holds after challenge_timelock_seconds, "
                        "acceptChallenge() switches to the FALLBACK. Back to the primary via heal() then "
                        "acceptHealing() after healing_timelock_seconds of reconvergence. Permissionless functions."),
        "switch_rule_source": STEAKHOUSE_DOC,
        "design_note": ("MetaOracleDeviationTimelock contract designed by Steakhouse Financial (docs above), deployed "
                        "as EIP-1167 clones by a factory. Link between THIS address and the official factory: "
                        "not proven on-chain (factory address not published in the docs) → no issued_by edge."),
        **_morpho_price(ctx, a, scale),
    }
    if scale is not None:
        for role, fn in (("primary", "primaryPrice()"), ("backup", "backupPrice()")):
            raw = ctx.try_call(a, fn, returns=["uint256"])
            meta[f"{role}_price"] = scaled(raw, scale) if raw is not None else None
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_meta", a), "Primary/fallback meta-oracle (deviation timelock)", meta)])
    d.edges.append(Edge(a, primary, "priced_by", "onchain", ctx.ev(a, "primaryOracle()", result=primary)
                        + f" ; currentOracle() = {current}"))
    d.edges.append(Edge(a, backup, "priced_by", "onchain", ctx.ev(a, "backupOracle()", result=backup)
                        + f"; switch threshold deviationThreshold() = {thr}"))
    hint = (("scale_decimals", scale),) if scale is not None else ()
    d.follow += [Task("oracle", primary, hint), Task("oracle", backup, hint)]
    return d


# ---- MorphoChainlinkOracle V1/V2 ----------------------------------------------------
def _mco_components(ctx: Ctx, a: str, kind: str) -> tuple[dict, str]:
    if kind == "morpho_chainlink_oracle_v2":
        vault_slots = [("BASE_VAULT", "BASE_VAULT_CONVERSION_SAMPLE"), ("QUOTE_VAULT", "QUOTE_VAULT_CONVERSION_SAMPLE")]
    else:
        vault_slots = [("VAULT", "VAULT_CONVERSION_SAMPLE")]
    slots: dict[str, dict] = {}
    for vault, sample in vault_slots:
        addr = ctx.call(a, f"{vault}()", returns=["address"])
        slots[vault] = {"address": None if is_zero(addr) else addr,
                        "sample": ctx.try_call(a, f"{sample}()", returns=["uint256"]),
                        "role": "base" if vault in ("BASE_VAULT", "VAULT") else "quote", "is_vault": True}
    for feed in ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2"):
        addr = ctx.call(a, f"{feed}()", returns=["address"])
        slots[feed] = {"address": None if is_zero(addr) else addr,
                       "role": "base" if feed.startswith("BASE") else "quote", "is_vault": False}
    modes = []
    for s in slots.values():
        if s["address"] is None:
            continue
        s["pricing_mode"] = "internal_rate" if s["is_vault"] else mode_of(ctx, s["address"])
        modes.append(s["pricing_mode"])
    return slots, _combine(modes)


def _mco(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    slots, mode = _mco_components(ctx, a, kind)
    scale_factor = ctx.call(a, "SCALE_FACTOR()", returns=["uint256"])
    meta = {"pricing_mode": mode, "scale_factor": jsonable(scale_factor), **_morpho_price(ctx, a, scale)}

    # Recompute the price from the building blocks: if we land on price(), the composition is PROVEN.
    num, den = scale_factor, 1
    for name, s in slots.items():
        if s["address"] is None:
            continue
        if s["is_vault"]:
            value = ctx.call(s["address"], "convertToAssets(uint256)", [s["sample"]], ["uint256"])
        else:
            value = latest_round(ctx, s["address"])[1]
            if value < 0:
                raise ValueError(f"feed {s['address']} returns a negative price")
        s["value"] = jsonable(value)
        if s["role"] == "base":
            num *= value
        else:
            den *= value
    recomputed = num // den   # same rounding as mulDiv (integer division, rounding down)
    if kind == "morpho_chainlink_oracle_v2":
        # MorphoChainlinkOracleV2 : SCALE_FACTOR × baseVault.convertToAssets(sample) × feeds / (quote...)
        meta["formula"] = "SCALE_FACTOR × BASE_VAULT × BASE_FEED_1 × BASE_FEED_2 / (QUOTE_VAULT × QUOTE_FEED_1 × QUOTE_FEED_2), empty slot = 1"
    raw_price = ctx.try_call(a, "price()", returns=["uint256"])
    meta["price_recomputed_raw"] = jsonable(recomputed)
    meta["price_recomputed_matches"] = raw_price == recomputed
    meta["components"] = {k: {kk: vv for kk, vv in v.items() if kk != "is_vault"} for k, v in slots.items()}
    meta["implicit_unit_slots"] = [k for k, v in slots.items() if v["address"] is None]
    meta["implicit_unit_note"] = ("Each slot listed here counts as 1 in the formula: the matching conversion "
                                  "is FIXED (e.g. no QUOTE_FEED = the lent asset is assumed to be worth 1 unit of "
                                  "the base feeds' currency).")

    factory = ctx.config.contracts.get("morpho_chainlink_oracle_v2_factory")
    if factory and kind == "morpho_chainlink_oracle_v2":
        ok = ctx.try_call(factory, "isMorphoChainlinkOracleV2(address)", [a], ["bool"])
        meta["created_by_official_factory"] = ok
        meta["factory_evidence"] = f"MorphoChainlinkOracleV2Factory.isMorphoChainlinkOracleV2({a}) = {ok} @ {factory} #{ctx.block}"

    label = f"{KIND_LABEL[kind]} ({mode})"
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_morpho_v2" if kind.endswith("v2") else "oracle_morpho_v1", a), label, meta)])
    for name, s in slots.items():
        if s["address"] is None:
            continue
        d.edges.append(Edge(a, s["address"], "priced_by", "onchain",
                            ctx.ev(a, f"{name}()", result=s["address"]) + f"; value read = {s.get('value')}"))
        d.follow.append(Task("token" if s["is_vault"] else "oracle", s["address"]))
    return d


# ---- feeds ----------------------------------------------------------------------------
def _round(ctx: Ctx, a: str) -> dict:
    round_id, answer, _, updated_at, _ = latest_round(ctx, a)
    dec = ctx.try_call(a, "decimals()", returns=["uint8"])
    return {"answer_raw": jsonable(answer), "decimals": dec,
            "answer": scaled(answer, dec) if dec is not None else None,
            "round_id": jsonable(round_id), "updated_at": updated_at,
            "age_seconds": ctx.block_timestamp - updated_at if updated_at else None}


def _linear_discount(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    pt = ctx.call(a, "PT()", returns=["address"])
    maturity = ctx.call(a, "maturity()", returns=["uint256"])
    discount = ctx.call(a, "baseDiscountPerYear()", returns=["uint256"])
    r = _round(ctx, a)
    seconds_left = max(maturity - ctx.block_timestamp, 0)
    expected = 1 - scaled(discount, 18) * seconds_left / (365 * 86400)
    meta = {
        "pricing_mode": "fixed",
        "priced_asset": pt,
        "maturity": maturity,
        "base_discount_per_year": scaled(discount, 18),
        "formula": "PT_price = 1 − baseDiscountPerYear × (maturity − now) / 1 year  (looks at NO market)",
        "formula_expected": round(expected, 12),
        "formula_matches": r["answer"] is not None and abs(r["answer"] - expected) < 1e-9,
        **r,
    }
    sym = ctx.try_call(pt, "symbol()", returns=["string"]) or "pt"
    d = Discovery(nodes=[_node(a, kind, f"feed_{slugify(sym)}_linear_discount", f"Pendle linear discount ({sym})", meta)])
    d.notes.append(f"Feed {a}: PT price FIXED by formula (discount {scaled(discount, 18):.2%}/year) → no link to the market")
    return d


def _pendle_twap(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    market = ctx.call(a, "market()", returns=["address"])
    twap = ctx.call(a, "twapDuration()", returns=["uint32"])
    meta = {"pricing_mode": "market", "market": market, "twap_duration_seconds": twap, **_round(ctx, a),
            "warning": "probes for this feed type not verified against a real contract (see docs/VERIFY.md)"}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_pendle_twap", a), "Feed TWAP Pendle", meta)])
    d.edges.append(Edge(a, market, "priced_by", "onchain", ctx.ev(a, "market()", result=market)))
    d.follow.append(Task("pendle_market", market))
    return d


def _chainlink_proxy(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    desc = ctx.call(a, "description()", returns=["string"])
    ctx.labels[a] = f"ChainlinkFeed[{desc}]"
    meta = {
        "pricing_mode": _chainlink_mode(desc),
        "description": desc,
        "aggregator": ctx.call(a, "aggregator()", returns=["address"]),
        "phase_id": ctx.call(a, "phaseId()", returns=["uint16"]),
        "version": ctx.try_call(a, "version()", returns=["uint256"]),
        "owner": ctx.try_call(a, "owner()", returns=["address"]),
        **_round(ctx, a),
    }
    if meta["pricing_mode"] == "internal_rate":
        meta["pricing_basis"] = (f"\"Exchange Rate\" feed: on-chain data computed by the issuer, not a "
                                 f"market price ({CHAINLINK_EXCHANGE_RATE_DOC})")
    ens_name = chainlink_ens_name(desc)
    resolved, ens_proof = resolve(ctx, ens_name)
    meta["ens_name"] = ens_name
    meta["ens_resolves_to_this_feed"] = resolved == a
    d = Discovery(nodes=[_node(a, kind, f"feed_{slugify(desc)}", f"Chainlink {desc}", meta)])
    if resolved == a:
        d.edges.append(Edge(a, CHAINLINK_ISSUER_KEY, "issued_by", "onchain",
                            f"{ens_proof}; the data.eth domain is the Chainlink feeds' domain ({CHAINLINK_ENS_DOC})"))
    else:
        d.notes.append(f"Feed {a} ({desc}): ENS {ens_name} does not point to it → issuer NOT proven")
    return d


def _constant_feed(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    r = _round(ctx, a)
    desc = ctx.try_call(a, "description()", returns=["string"])
    meta = {"pricing_mode": "fixed", "description": desc, **r,
            "why_constant": (f"latestRoundData() returns roundId={r['round_id']} and updatedAt = timestamp of block "
                             f"#{ctx.block}: the value is computed on the fly, no operator updates it")}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_constant", a), f"Constant feed ({desc or 'no description'})", meta)])
    d.notes.append(f"Feed {a}: CONSTANT ({r['answer']}) — \"{desc}\"")
    return d


def _midas_custom_feed(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    """Price pushed by hand by a Midas administrator (NAV of a tokenised fund). It ONLY moves when
    the admin publishes: in a crisis, the market can collapse without the oracle seeing it."""
    r = _round(ctx, a)
    dec = r["decimals"]
    desc = ctx.try_call(a, "description()", returns=["string"])
    lo, hi = ctx.call(a, "minAnswer()", returns=["int192"]), ctx.call(a, "maxAnswer()", returns=["int192"])
    meta = {
        "pricing_mode": "fixed", "description": desc, **r,
        "pricing_detail": "value published by an administrator via setRoundData(int256) / setRoundDataSafe(int256) "
                          "— follows no market; only changes when the admin publishes",
        "min_answer": scaled(lo, dec) if dec is not None else jsonable(lo),
        "max_answer": scaled(hi, dec) if dec is not None else jsonable(hi),
        "max_answer_deviation_raw": jsonable(ctx.call(a, "maxAnswerDeviation()", returns=["uint256"])),
        "access_control": ctx.try_call(a, "accessControl()", returns=["address"]),
        "verified_source": MIDAS_CUSTOM_FEED_SOURCE,
        "issuer_hint": "deployed by the address labelled \"Midas RWA: Deployer\" on Etherscan — issuer to curate "
                       "(curated.yaml) with an official Midas source",
    }
    label = f"Midas feed (admin-set price){' ' + desc if desc else ''}"
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_midas", a), label, meta)])
    age_d = (r["age_seconds"] or 0) / 86400
    d.notes.append(f"Feed {a}: price SET BY A Midas ADMIN ({r['answer']}), last updated {age_d:.1f} days ago")
    return d


def _wsteth_feed(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    """wstETH in ETH = (stETH in ETH, market feed) × (stETH per wstETH, the token's internal rate)."""
    feed = ctx.call(a, "stETHtoETHPriceFeed()", returns=["address"])
    wsteth = ctx.call(a, "wstETH()", returns=["address"])
    meta = {"pricing_mode": mode_of(ctx, a, kind), "description": ctx.try_call(a, "description()", returns=["string"]),
            **_round(ctx, a), "formula": "price = stETHtoETHPriceFeed × wstETH (internal rate, stETH per wstETH)",
            "verified_source": WSTETH_FEED_SOURCE}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_wsteth", a), "Feed wstETH/ETH (Compound)", meta)])
    d.edges += [Edge(a, feed, "priced_by", "onchain", ctx.ev(a, "stETHtoETHPriceFeed()", result=feed)),
                Edge(a, wsteth, "priced_by", "onchain", ctx.ev(a, "wstETH()", result=wsteth) + " (token internal rate)")]
    d.follow += [Task("oracle", feed), Task("token", wsteth)]
    return d


def _token_rate_adapter(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    """Adapter reading a token's INTERNAL RATE (weETH → ETH, net asset value…): it does not see the market."""
    getter, source = ("WEETH()", WEETH_RATE_SOURCE) if kind == "weeth_exchange_rate_adapter" else ("token()", NAV_ADAPTER_SOURCE)
    token = ctx.call(a, getter, returns=["address"])
    r = _round(ctx, a)
    desc = ctx.try_call(a, "description()", returns=["string"])
    meta = {"pricing_mode": "internal_rate", "description": desc, **r, "priced_asset": token, "verified_source": source,
            "pricing_basis": "token accounting rate (computed by its contract), not a market price"}
    if r.get("updated_at") == 0:
        meta["note"] = "updatedAt = 0: value computed on the fly at each read (no stored \"round\")"
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_rate", a), f"Internal rate ({desc or kind})", meta)])
    d.edges.append(Edge(a, token, "priced_by", "onchain", ctx.ev(a, getter, result=token) + " (token internal rate)"))
    d.follow.append(Task("token", token))
    return d


def _redstone_feed(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    desc = ctx.try_call(a, "description()", returns=["string"])
    feed_id = ctx.call(a, "getDataFeedId()", returns=["bytes32"])
    meta = {"pricing_mode": _redstone_mode(desc), "description": desc, **_round(ctx, a),
            "data_feed_id": bytes.fromhex(feed_id[2:]).rstrip(b"\x00").decode("ascii", "replace"),
            "price_feed_adapter": ctx.call(a, "getPriceFeedAdapter()", returns=["address"]),
            "verified_source": REDSTONE_SOURCE}
    if meta["pricing_mode"] == "internal_rate":
        meta["pricing_basis"] = "RedStone id \"…_FUNDAMENTAL\": published fundamental value (NAV / rate), not a market price"
    return Discovery(nodes=[_node(a, kind, contract_id("feed_redstone", a), f"RedStone {desc or meta['data_feed_id']}", meta)])


def _oracle_wrapper(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    inner = ctx.call(a, "oracle()", returns=["address"])
    desc = ctx.try_call(a, "description()", returns=["string"])
    meta = {"pricing_mode": mode_of(ctx, a, kind), "description": desc, **_round(ctx, a), "inner_oracle": inner,
            "verified_source": ORACLE_WRAPPER_SOURCE}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_wrapper", a), f"Adapter ({desc or 'oracle()'})", meta)])
    d.edges.append(Edge(a, inner, "priced_by", "onchain", ctx.ev(a, "oracle()", result=inner)))
    d.follow.append(Task("oracle", inner))
    return d


def _rtoken_asset(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    """Reserve Protocol: price of an RToken (basket of collaterals). Its sub-oracles are not taken apart yet."""
    token = ctx.call(a, "erc20()", returns=["address"])
    low_high = ctx.try_call(a, "price()", returns=["uint192", "uint192"])
    meta = {"pricing_mode": "unknown", "unresolved": True, "verified_source": RTOKEN_ASSET_SOURCE,
            "price_low_high_raw": [str(x) for x in low_high] if low_high else None,
            "basket_handler": ctx.call(a, "basketHandler()", returns=["address"]),
            "next_step": "take the basket apart (basketHandler) and each collateral's oracles to learn the pricing mode"}
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_rtoken", a), "Reserve RTokenAsset (basket price)", meta)])
    d.edges.append(Edge(a, token, "priced_by", "onchain", ctx.ev(a, "erc20()", result=token)))
    d.follow.append(Task("token", token))
    d.notes.append(f"⚠ Oracle {a} = RTokenAsset (Reserve): basket not taken apart → pricing mode unknown")
    return d


def _unknown(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    meta = {"pricing_mode": "unknown", "unresolved": True,
            "next_step": "unrecognised contract: read its verified source code on Etherscan and add a handler"}
    meta.update(_morpho_price(ctx, a, scale))
    if kind == "chainlink_compatible_unknown":
        meta.update(_round(ctx, a))
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_unknown", a), f"Unrecognised oracle {a[:10]}", meta)])
    d.notes.append(f"⚠ Oracle {a} not recognised ({kind}) → marked unresolved, to analyse by hand")
    return d
