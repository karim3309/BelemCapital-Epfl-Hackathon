"""Morpho Blue: a SINGLE contract ("singleton") hosting thousands of isolated lending markets.

A market = 5 frozen parameters (MarketParams):
    loanToken (USDC) · collateralToken (PT-sUSDe) · oracle · irm (rate model) · lltv
and its identifier is the fingerprint of those parameters:  marketId = keccak256(abi.encode(params)).
→ By recomputing that hash, we PROVE the parameters read are those of the requested market.

Reads used (Morpho Blue contract):
    idToMarketParams(id) → (loanToken, collateralToken, oracle, irm, lltv)
    market(id)           → (totalSupplyAssets, totalSupplyShares, totalBorrowAssets, totalBorrowShares, lastUpdate, fee)
    position(id, user)   → (supplyShares, borrowShares, collateral)
Liquidation: possible as soon as  debt > collateral × oracle_price / 1e36 × lltv.

Trap: Morpho only updates interest on each interaction (`lastUpdate`). In between,
the stored debt LAGS. Like Morpho, we accrue interest "virtually":
    interest = totalBorrowAssets × wTaylorCompounded(rate_per_second, seconds_elapsed)
with rate_per_second = IRM.borrowRateView(MarketParams, Market).
"""
from __future__ import annotations

import math

from eth_abi import encode
from eth_utils import keccak

from ..ctx import Ctx, checksum, is_zero
from ..graph import POSITION_KEY, Edge, Node
from ..ids import morpho_market_id
from . import Discovery, Task, jsonable, scaled
from .ens import resolve
from .erc20 import read_token

PARAMS_TYPES = ["address", "address", "address", "address", "uint256"]
VIRTUAL_SHARES = 10**6   # SharesMathLib constants (Morpho Blue): protect against share inflation
VIRTUAL_ASSETS = 1
ORACLE_PRICE_SCALE = 10**36
WAD = 10**18
SECONDS_PER_YEAR = 365 * 86400
BORROW_RATE_VIEW = ("borrowRateView((address,address,address,address,uint256),"
                    "(uint128,uint128,uint128,uint128,uint128,uint128))")


def market_key(market_id: str) -> str:
    return f"morpho_market:{market_id.lower()}"


def to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    """Converts debt shares to assets, rounded UP (like Morpho, in the protocol's favour)."""
    num = shares * (total_assets + VIRTUAL_ASSETS)
    den = total_shares + VIRTUAL_SHARES
    return -(-num // den)


def w_taylor_compounded(x: int, n: int) -> int:
    """e^(x·n) − 1 approximated to order 3 (Morpho Blue's MathLib.wTaylorCompounded), in WAD."""
    first = x * n
    second = first * first // (2 * WAD)
    third = second * first // (3 * WAD)
    return first + second + third


def accrue_interest(ctx: Ctx, m: dict) -> dict:
    """Adds to `m` the interest-UP-TO-DATE totals at the pinned block (like MorphoBalancesLib.expectedMarketBalances)."""
    elapsed = max(ctx.block_timestamp - m["last_update"], 0)
    rate = None
    if not is_zero(m["irm"]):
        params = (m["loan_token"], m["collateral_token"], m["oracle"], m["irm"], m["lltv"])
        rate = ctx.try_call(m["irm"], BORROW_RATE_VIEW, [params, m["state"]], ["uint256"])
    interest = m["total_borrow_assets"] * w_taylor_compounded(rate, elapsed) // WAD if rate and elapsed else 0
    m.update({
        "borrow_rate_per_second": rate,
        "seconds_since_last_update": elapsed,
        "accrued_interest": interest,
        "expected_total_borrow_assets": m["total_borrow_assets"] + interest,
        "expected_total_supply_assets": m["total_supply_assets"] + interest,
    })
    return m


def read_market(ctx: Ctx, market_id: str) -> dict:
    morpho = ctx.config.contracts["morpho_blue"]
    ctx.labels[checksum(morpho)] = "Morpho"
    mid = bytes.fromhex(market_id.removeprefix("0x"))
    params = ctx.call(morpho, "idToMarketParams(bytes32)", [mid], PARAMS_TYPES)
    loan, collateral, oracle, irm, lltv = params
    if int(loan, 16) == 0:
        raise ValueError(f"Market {market_id} does not exist on Morpho Blue (idToMarketParams empty)")
    recomputed = "0x" + keccak(encode(PARAMS_TYPES, [loan, collateral, oracle, irm, lltv])).hex()
    if recomputed != market_id.lower():
        raise ValueError(f"keccak256(MarketParams) = {recomputed} ≠ {market_id}: inconsistent parameters")
    state = ctx.call(morpho, "market(bytes32)", [mid], ["uint128"] * 6)
    m = {
        "morpho": checksum(morpho), "market_id": market_id.lower(), "mid": mid,
        "loan_token": loan, "collateral_token": collateral, "oracle": oracle, "irm": irm, "lltv": lltv,
        "state": tuple(state),
        "total_supply_assets": state[0], "total_supply_shares": state[1],
        "total_borrow_assets": state[2], "total_borrow_shares": state[3],
        "last_update": state[4], "fee": state[5],
        "id_recomputed": recomputed,
    }
    return accrue_interest(ctx, m)


def discover_market(ctx: Ctx, m: dict) -> Discovery:
    loan = read_token(ctx, m["loan_token"])
    coll = read_token(ctx, m["collateral_token"])
    if loan is None or coll is None:
        raise ValueError("loanToken / collateralToken is not a readable ERC-20")
    lltv = scaled(m["lltv"], 18)
    supply, borrow = m["expected_total_supply_assets"], m["expected_total_borrow_assets"]
    rate = m["borrow_rate_per_second"]
    official_irm = ctx.config.contracts.get("morpho_adaptive_curve_irm")
    meta = {
        "protocol": "morpho_blue",
        "market_id": m["market_id"],
        "market_id_check": f"keccak256(abi.encode(MarketParams)) = {m['id_recomputed']} (identical to the requested ID)",
        "loan_token": m["loan_token"],
        "collateral_token": m["collateral_token"],
        "oracle": m["oracle"],
        "irm": m["irm"],
        "irm_is_official_adaptive_curve": (checksum(official_irm) == m["irm"]) if official_irm else None,
        "lltv": lltv,
        "total_supply_assets": jsonable(supply),
        "total_borrow_assets": jsonable(borrow),
        "total_supply_human": scaled(supply, loan["decimals"]),
        "total_borrow_human": scaled(borrow, loan["decimals"]),
        "available_liquidity_human": scaled(supply - borrow, loan["decimals"]),
        "utilization": round(borrow / supply, 6) if supply else None,
        "totals_include_accrued_interest": True,
        "accrued_interest_human": scaled(m["accrued_interest"], loan["decimals"]),
        "seconds_since_last_update": m["seconds_since_last_update"],
        "borrow_rate_per_second": jsonable(rate),
        "borrow_apy": round(math.exp(rate * SECONDS_PER_YEAR / WAD) - 1, 6) if rate else None,
        "borrow_rate_evidence": (ctx.ev(m["irm"], BORROW_RATE_VIEW.split("(")[0] + "(MarketParams,Market)", (), rate)
                                 if rate is not None else "borrowRateView unavailable"),
        "fee": scaled(m["fee"], 18),
        "last_update": m["last_update"],
        "oracle_price_scale_decimals": 36 + loan["decimals"] - coll["decimals"],
    }
    key = market_key(m["market_id"])
    label = f"Morpho Blue {coll['symbol']} / {loan['symbol']} (LLTV {lltv:.1%})"
    ev_params = ctx.ev(m["morpho"], "idToMarketParams(bytes32)", [m["mid"]])
    d = Discovery(nodes=[Node(key=key, type="lending_market", label=label,
                              id_hint=morpho_market_id(m["market_id"]), address=m["morpho"], meta=meta)])
    d.edges += [
        Edge(key, coll["address"], "collateralized_by", "onchain", f"{ev_params} → collateralToken = {coll['address']}"),
        Edge(key, loan["address"], "lends", "onchain", f"{ev_params} → loanToken = {loan['address']}"),
        Edge(key, m["oracle"], "priced_by", "onchain", f"{ev_params} → oracle = {m['oracle']}"),
    ]
    scale = meta["oracle_price_scale_decimals"]
    d.follow += [
        Task("token", coll["address"]),
        Task("token", loan["address"]),
        Task("oracle", m["oracle"], (("scale_decimals", scale),)),
        Task("vaults_lookup", m["market_id"]),
    ]
    return d


def loan_token_usd_price(ctx: Ctx) -> tuple[float, str]:
    """USD price of the lent asset via the Chainlink feed resolved through ENS (e.g. usdc-usd.data.eth)."""
    name = ctx.config.loan_usd_feed_ens
    if name:
        feed, proof = resolve(ctx, name)
        if feed:
            _, answer, _, _, _ = ctx.call(feed, "latestRoundData()", returns=["uint80", "int256", "uint256", "uint256", "uint80"])
            dec = ctx.call(feed, "decimals()", returns=["uint8"])
            return scaled(answer, dec), f"{proof}; latestRoundData().answer = {answer} (dec. {dec})"
    return 1.0, "no USD feed configured: lent asset assumed = 1 USD"


def discover_position(ctx: Ctx, m: dict, user: str | None, value_usd_override: float | None) -> tuple[Discovery, dict, float]:
    """Reads the position (collateral, debt) and computes its health. Returns (Discovery, position_meta, value_usd)."""
    key = market_key(m["market_id"])
    loan_dec = ctx.call(m["loan_token"], "decimals()", returns=["uint8"])
    coll_dec = ctx.call(m["collateral_token"], "decimals()", returns=["uint8"])
    price_raw = ctx.call(m["oracle"], "price()", returns=["uint256"])
    usd, usd_proof = loan_token_usd_price(ctx)
    lltv = m["lltv"]

    if user is None:
        meta = {"hypothetical": True, "note": "no user configured: hypothetical position (value_usd from config)"}
        edge = Edge(POSITION_KEY, key, "deployed_in", "onchain",
                    ctx.ev(m["morpho"], "idToMarketParams(bytes32)", [m["mid"]]) + " (hypothetical position)")
        return Discovery(edges=[edge]), meta, float(value_usd_override or 0)

    supply_shares, borrow_shares, collateral = ctx.call(
        m["morpho"], "position(bytes32,address)", [m["mid"], user], ["uint256", "uint128", "uint128"])
    if collateral == 0 and borrow_shares == 0 and supply_shares == 0:
        raise ValueError(f"User {user} has no position on market {m['market_id']} at block {ctx.block}")
    borrow = to_assets_up(borrow_shares, m["expected_total_borrow_assets"], m["total_borrow_shares"])
    coll_value = collateral * price_raw // ORACLE_PRICE_SCALE             # in units of the lent asset
    max_borrow = coll_value * lltv // 10**18
    hf = (max_borrow / borrow) if borrow else None
    meta = {
        "user": user,
        "collateral": jsonable(collateral),
        "collateral_human": scaled(collateral, coll_dec),
        "borrow_shares": jsonable(borrow_shares),
        "borrow_assets": jsonable(borrow),
        "borrow_human": scaled(borrow, loan_dec),
        "supply_shares": jsonable(supply_shares),
        "oracle_price_raw": jsonable(price_raw),
        "collateral_value_in_loan_token": scaled(coll_value, loan_dec),
        "ltv": round(borrow / coll_value, 6) if coll_value else None,
        "lltv": scaled(lltv, 18),
        "health_factor": round(hf, 6) if hf else None,
        "oracle_drop_to_liquidation": round(1 - 1 / hf, 6) if hf else None,
        "loan_token_usd": usd,
        "loan_token_usd_evidence": usd_proof,
    }
    value_usd = float(value_usd_override) if value_usd_override else scaled(coll_value, loan_dec) * usd
    meta["value_usd_definition"] = ("collateral value at the Morpho oracle price × USD price of the lent asset"
                                    if not value_usd_override else "forced by config.yaml (value_usd_override)")
    meta["net_value_usd"] = round(value_usd - scaled(borrow, loan_dec) * usd, 2)
    edge = Edge(POSITION_KEY, key, "deployed_in", "onchain",
                ctx.ev(m["morpho"], "position(bytes32,address)", [m["mid"], user],
                       (supply_shares, borrow_shares, collateral)))
    return Discovery(edges=[edge]), meta, value_usd
