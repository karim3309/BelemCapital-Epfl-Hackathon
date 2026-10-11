"""Valuation: `meta.price_usd` and `meta.tvl_usd` (field shown in the JSON contract example).

We take NO price "from memory" nor from a price API: we only reuse what
discovery has already PROVEN on-chain, and each price says where it comes from (`price_usd_source`):
  - lent asset (USDC)          : Chainlink feed resolved via ENS (usdc-usd.data.eth)
  - asset with an X / USD feed : the Chainlink feed found in the oracle (e.g. USDe / USD)
  - ERC-4626 vault (sUSDe)     : internal rate convertToAssets × price of the underlying
  - Pendle SY                  : exchangeRate × price of the accounting asset
  - collateral (PT)            : Morpho oracle price × USD price of the lent asset
If a price cannot be proven, `price_usd` and `tvl_usd` are null (never an invented 0).

Risk bonus: we compare the PT price given by the oracle (formula) with the price implied by the
Pendle AMM (market): a gap = the oracle does not follow the market.
"""
from __future__ import annotations

import math

from .graph import Edge, GraphBuilder, Node

SECONDS_PER_YEAR = 365 * 86400


def _assets(g: GraphBuilder) -> dict[str, Node]:
    return {n.address: n for n in g.nodes.values() if n.type == "asset" and n.address}


def link_market_feeds(g: GraphBuilder, block: int) -> int:
    """Draws the edge  feed --priced_by--> asset  for every Chainlink "SYMBOL / USD" feed whose SYMBOL is an asset of
    the graph (both read on-chain: description() of the feed, symbol() of the token).

    Why: the feed measures the MARKET price of that asset. Without the edge, "who is hit if USDe breaks?"
    (ancestors of usde) never reaches the oracle that depends on USDe's price, although it is the heart of the
    depeg story. Matching is done on the symbol, and the evidence says so. Returns the number of edges added.
    """
    by_symbol = {n.meta.get("symbol"): n for n in g.nodes.values() if n.type == "asset" and n.address}
    added = 0
    for n in list(g.nodes.values()):
        if n.type != "oracle" or n.meta.get("oracle_kind") != "chainlink_aggregator_proxy" or not n.address:
            continue
        desc = n.meta.get("description") or ""
        base, _, quote = desc.partition("/")
        asset = by_symbol.get(base.strip())
        if quote.strip() != "USD" or asset is None:
            continue
        n.meta.setdefault("priced_asset", asset.address)
        ens = (f" ; ENS {n.meta['ens_name']} → this feed (official Chainlink)" if n.meta.get("ens_resolves_to_this_feed")
               else "")
        g.add_edge(Edge(n.key, asset.key, "priced_by", "onchain",
                        f"{n.label}.description() = \"{desc}\" @ {n.address} #{block} ; "
                        f"{asset.label}.symbol() = \"{asset.meta.get('symbol')}\" @ {asset.address} #{block}{ens} — "
                        "the feed measures the market price of this asset (matched on the symbol)"))
        added += 1
    return added


def value_graph(g: GraphBuilder, market_key: str, loan_usd: float, loan_usd_source: str, block_ts: int) -> None:
    market = g.nodes[market_key]
    assets = _assets(g)
    prices: dict[str, tuple[float, str]] = {market.meta["loan_token"]: (loan_usd, loan_usd_source)}

    # 1. Chainlink "SYMBOL / USD" feeds found in the oracle
    by_symbol = {n.meta.get("symbol"): a for a, n in assets.items()}
    for n in g.nodes.values():
        if n.type == "oracle" and n.meta.get("oracle_kind") == "chainlink_aggregator_proxy":
            base, _, quote = (n.meta.get("description") or "").partition("/")
            if quote.strip() == "USD" and base.strip() in by_symbol and n.meta.get("answer") is not None:
                n.meta["priced_asset"] = by_symbol[base.strip()]       # the feed measures this asset's market price
                prices.setdefault(by_symbol[base.strip()], (n.meta["answer"], f"Chainlink {n.meta['description']} ({n.address})"))

    # 2. collateral: market oracle price (in lent asset) × USD price of the lent asset
    oracle = g.nodes.get(market.meta["oracle"])
    if oracle is not None and oracle.meta.get("price") is not None:
        mode = oracle.meta.get("effective_pricing_mode", oracle.meta.get("pricing_mode"))
        prices.setdefault(market.meta["collateral_token"],
                          (oracle.meta["price"] * loan_usd, f"Morpho oracle {oracle.address} (mode {mode}) × USD price of the lent asset"))

    # 3. propagation: ERC-4626 and SY derive their price from their underlying (iterative)
    changed = True
    while changed:
        changed = False
        for a, n in assets.items():
            if a in prices:
                continue
            kind = n.meta.get("asset_kind")
            if kind == "erc4626_vault" and n.meta.get("underlying") in prices:
                p, src = prices[n.meta["underlying"]]
                prices[a] = (n.meta["share_to_asset_rate"] * p, f"convertToAssets ({n.meta['share_to_asset_rate']:.6f}) × [{src}]")
                changed = True
            elif kind == "pendle_sy" and n.meta.get("accounting_asset") in prices and n.meta.get("exchange_rate"):
                p, src = prices[n.meta["accounting_asset"]]
                prices[a] = (n.meta["exchange_rate"] * p, f"SY.exchangeRate ({n.meta['exchange_rate']:.6f}) × [{src}]")
                changed = True

    # 4. write price_usd / tvl_usd
    for a, n in assets.items():
        p = prices.get(a)
        n.meta["price_usd"] = round(p[0], 8) if p else None
        n.meta["price_usd_source"] = p[1] if p else "no price provable on-chain"
        supply = n.meta.get("total_supply_human")
        n.meta["tvl_usd"] = round(supply * p[0], 2) if p and supply is not None else None
        n.meta["tvl_usd_definition"] = "totalSupply × price_usd"
    loan = prices[market.meta["loan_token"]][0]
    market.meta["tvl_usd"] = round(market.meta["total_supply_human"] * loan, 2)
    market.meta["tvl_usd_definition"] = "total supplied (interest included) × USD price of the lent asset"
    for n in g.nodes.values():
        if n.type == "vault" and n.meta.get("asset") in prices and n.meta.get("total_assets") is not None:
            dec = assets[n.meta["asset"]].meta["decimals"] if n.meta["asset"] in assets else None
            if dec is not None:
                n.meta["tvl_usd"] = round(int(n.meta["total_assets"]) / 10**dec * prices[n.meta["asset"]][0], 2)
                n.meta["tvl_usd_definition"] = "totalAssets × USD price of the vault's asset"
        if n.type == "liquidity_venue" and "reserve_pt" in n.meta:
            pt, sy = prices.get(n.meta["pt"]), prices.get(n.meta["sy"])
            n.meta["tvl_usd"] = round(n.meta["reserve_pt"] * pt[0] + n.meta["reserve_sy"] * sy[0], 2) if pt and sy else None
            n.meta["tvl_usd_definition"] = "PT reserve × PT price + SY reserve × SY price"
            _compare_pt_prices(g, n, market, block_ts)


def _compare_pt_prices(g: GraphBuilder, pool: Node, market: Node, block_ts: int) -> None:
    """PT price according to the AMM (implied rate) vs according to the Morpho oracle."""
    pt = g.nodes.get(pool.meta["pt"])
    oracle = g.nodes.get(market.meta["oracle"])
    if pt is None or "implied_apy" not in pool.meta or oracle is None or oracle.meta.get("price") is None:
        return
    years = max(pt.meta["expiry"] - block_ts, 0) / SECONDS_PER_YEAR
    amm_price = math.exp(-math.log1p(pool.meta["implied_apy"]) * years)    # in accounting asset (USDe)
    pool.meta["pt_price_implied_by_amm"] = round(amm_price, 8)
    pool.meta["pt_price_implied_by_amm_unit"] = "SY accounting asset (USDe), = (1 + implied_apy)^(−years remaining)"
    pool.meta["pt_price_morpho_oracle"] = round(oracle.meta["price"], 8)
    pool.meta["oracle_vs_amm_gap"] = round(oracle.meta["price"] / amm_price - 1, 6)
