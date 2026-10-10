"""Pendle : découpe un actif à rendement (sUSDe) en PT (le principal) + YT (le rendement).

  SY  (Standardized Yield) : emballage standard autour de sUSDe.        SY.yieldToken() → sUSDe
  PT  (Principal Token)    : vaut 1 « actif comptable » à l'échéance.     PT.SY(), PT.expiry()
  YT  (Yield Token)        : touche le rendement jusqu'à l'échéance.
  Pool (PendleMarket)      : AMM PT ↔ SY, où l'on achète/vend du PT avant l'échéance.

Analogie : une obligation zéro-coupon achetée 0,95 et remboursée 1,00 à l'échéance.

Le PT ne connaît PAS l'adresse de son pool. On le LOCALISE via l'API Pendle, puis on le
PROUVE on-chain : pool.readTokens() doit contenir notre PT, et la factory Pendle doit
confirmer isValidMarket(pool). L'API ne sert qu'à trouver ; la preuve reste on-chain.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..ctx import Ctx, checksum
from ..graph import Edge, Node
from ..ids import slugify
from . import Discovery, Task, jsonable, scaled
from .erc20 import token_node


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def discover_pt(ctx: Ctx, info: dict) -> Discovery:
    pt = info["address"]
    sy = ctx.call(pt, "SY()", returns=["address"])
    yt = ctx.call(pt, "YT()", returns=["address"])
    expiry = ctx.call(pt, "expiry()", returns=["uint256"])
    is_expired = ctx.try_call(pt, "isExpired()", returns=["bool"])
    factory = ctx.try_call(pt, "factory()", returns=["address"])

    meta = {
        "sy": sy,
        "yt": yt,
        "expiry": expiry,
        "expiry_iso": _iso(expiry),
        "is_expired": is_expired,
        "days_to_expiry": round((expiry - ctx.block_timestamp) / 86400, 2),
        "factory": factory,
        "redemption_note": "à l'échéance, 1 PT se rachète contre la valeur de 1 actif comptable du SY (voir SY.assetInfo)",
    }
    d = Discovery()
    d.nodes.append(token_node(info, "pendle_pt", meta))
    d.edges.append(Edge(pt, sy, "redeemable_into", "onchain", ctx.ev(pt, "SY()", result=sy)))
    d.follow.append(Task("token", sy))
    d.follow.append(Task("pendle_market_lookup", pt))
    return d


def discover_sy(ctx: Ctx, info: dict) -> Discovery:
    sy = info["address"]
    yield_token = ctx.call(sy, "yieldToken()", returns=["address"])
    asset_type, accounting_asset, asset_decimals = ctx.call(sy, "assetInfo()", returns=["uint8", "address", "uint8"])
    exchange_rate = ctx.try_call(sy, "exchangeRate()", returns=["uint256"])
    meta = {
        "yield_token": yield_token,
        "accounting_asset": accounting_asset,
        "accounting_asset_type": asset_type,
        "accounting_asset_decimals": asset_decimals,
        "exchange_rate": scaled(exchange_rate, 18) if exchange_rate is not None else None,
        "tokens_in": ctx.try_call(sy, "getTokensIn()", returns=["address[]"]),
        "tokens_out": ctx.try_call(sy, "getTokensOut()", returns=["address[]"]),
        "paused": ctx.try_call(sy, "paused()", returns=["bool"]),
        "owner": ctx.try_call(sy, "owner()", returns=["address"]),
    }
    d = Discovery()
    d.nodes.append(token_node(info, "pendle_sy", meta))
    d.edges.append(Edge(sy, yield_token, "redeemable_into", "onchain",
                        ctx.ev(sy, "yieldToken()", result=yield_token)
                        + f" ; assetInfo() = ({asset_type},{accounting_asset},{asset_decimals})"))
    d.follow.append(Task("token", yield_token))
    return d


def find_market_via_api(ctx: Ctx, pt: str, chain_id: int = 1, page_size: int = 100, max_pages: int = 30):
    """Parcourt GET {pendle_core}/v2/markets/all (paginé) et renvoie (entrée, url, fetched_at) ou None."""
    base = ctx.config.apis["pendle_core"].rstrip("/")
    url = f"{base}/v2/markets/all"
    wanted = f"{chain_id}-{pt.lower()}"
    for page in range(max_pages):
        params = {"skip": page * page_size, "limit": page_size}
        data, fetched_at = ctx.http.get_json(url, params)
        results = data.get("results", [])
        for m in results:
            if str(m.get("pt", "")).lower() == wanted and m.get("chainId", chain_id) == chain_id:
                return m, f"{url}?skip={params['skip']}&limit={page_size}", fetched_at
        if len(results) < page_size:
            break
    return None


def discover_pendle_market(ctx: Ctx, market: str, pt: str, api_entry: dict | None,
                           api_url: str | None, fetched_at: str | None) -> Discovery:
    market = checksum(market)
    ctx.labels[market] = "PendleMarket"
    sy, pt_onchain, yt = ctx.call(market, "readTokens()", returns=["address", "address", "address"])
    if pt_onchain != checksum(pt):
        raise ValueError(f"Le pool {market} ne contient pas le PT {pt} (readTokens → {pt_onchain}) : on refuse l'API")
    factory = ctx.call(market, "factory()", returns=["address"])
    ctx.labels[factory] = "PendleMarketFactory"
    is_valid = ctx.try_call(factory, "isValidMarket(address)", [market], ["bool"])
    expiry = ctx.call(market, "expiry()", returns=["uint256"])
    lp_symbol = ctx.try_call(market, "symbol()", returns=["string"]) or "PENDLE-LPT"

    meta: dict = {
        "venue_kind": "pendle_v2_amm",
        "pair": "PT/SY",
        "sy": sy, "pt": pt_onchain, "yt": yt,
        "factory": factory,
        "factory_is_valid_market": is_valid,
        "expiry": expiry, "expiry_iso": _iso(expiry),
        "lp_total_supply": jsonable(ctx.try_call(market, "totalSupply()", returns=["uint256"])),
    }
    # État interne de l'AMM : réserves PT et SY + dernier taux implicite (ln, échelle 1e18).
    storage = ctx.try_call(market, "_storage()", returns=["int128", "int128", "uint96", "uint16", "uint16", "uint16"])
    if storage is not None:
        total_pt, total_sy, last_ln_rate, _, obs_card, _ = storage
        meta.update({
            "reserve_pt": scaled(total_pt, 18),
            "reserve_sy": scaled(total_sy, 18),
            "implied_apy": round(math.exp(last_ln_rate / 1e18) - 1, 6),
            "twap_observation_cardinality": obs_card,
        })
    if api_entry:
        details = api_entry.get("details") or {}
        meta["api_snapshot"] = {
            "liquidity_usd": details.get("liquidity"),
            "implied_apy": details.get("impliedApy"),
            "fetched_at": fetched_at,
            "url": api_url,
        }

    proof = (ctx.ev(market, "readTokens()", result=(sy, pt_onchain, yt))
             + " ; " + ctx.ev(factory, "isValidMarket(address)", [market], is_valid))
    if api_url:
        proof += f" ; pool localisé via l'API Pendle {api_url} (fetched {fetched_at})"

    d = Discovery()
    d.nodes.append(Node(key=market, type="liquidity_venue", label=f"Pendle pool {lp_symbol}",
                        id_hint=f"pendle_{slugify(lp_symbol)}", address=market, meta=meta))
    d.edges.append(Edge(pt_onchain, market, "deployed_in", "onchain", proof))
    if api_entry and api_url and str(api_entry.get("sy", "")).lower().endswith(sy.lower()):
        # Le SY n'a pas de factory() : c'est l'API officielle de Pendle qui le rattache à Pendle,
        # et on vérifie que c'est bien le même SY que celui lu on-chain dans readTokens().
        d.edges.append(Edge(sy, PENDLE_ISSUER_KEY, "issued_by", "api",
                            f"API Pendle {api_url} (fetched {fetched_at}) : le marché {market} liste sy={sy}, "
                            f"identique à readTokens() on-chain #{ctx.block}"))
    d.notes.append(f"Pendle: pool {market} prouvé on-chain pour le PT {pt_onchain} (isValidMarket={is_valid})")
    return d


PENDLE_ISSUER_KEY = "issuer:pendle"
