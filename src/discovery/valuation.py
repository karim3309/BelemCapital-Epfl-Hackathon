"""Valorisation : `meta.price_usd` et `meta.tvl_usd` (champ montré dans l'exemple du contrat JSON).

On ne prend AUCUN prix « de mémoire » ni d'API de prix : on réutilise uniquement ce que la
découverte a déjà PROUVÉ on-chain, et chaque prix dit d'où il vient (`price_usd_source`) :
  - actif prêté (USDC)        : feed Chainlink résolu par ENS (usdc-usd.data.eth)
  - actif avec feed X / USD   : le feed Chainlink découvert dans l'oracle (ex. USDe / USD)
  - coffre ERC-4626 (sUSDe)   : taux interne convertToAssets × prix du sous-jacent
  - SY Pendle                 : exchangeRate × prix de l'actif comptable
  - collatéral (PT)           : prix de l'oracle Morpho × prix USD de l'actif prêté
Si un prix n'est pas prouvable, `price_usd` et `tvl_usd` valent null (jamais 0 inventé).

Bonus risque : on compare le prix du PT donné par l'oracle (formule) au prix implicite de l'AMM
Pendle (marché) : un écart = l'oracle ne suit pas le marché.
"""
from __future__ import annotations

import math

from .graph import GraphBuilder, Node

SECONDS_PER_YEAR = 365 * 86400


def _assets(g: GraphBuilder) -> dict[str, Node]:
    return {n.address: n for n in g.nodes.values() if n.type == "asset" and n.address}


def value_graph(g: GraphBuilder, market_key: str, loan_usd: float, loan_usd_source: str, block_ts: int) -> None:
    market = g.nodes[market_key]
    assets = _assets(g)
    prices: dict[str, tuple[float, str]] = {market.meta["loan_token"]: (loan_usd, loan_usd_source)}

    # 1. feeds Chainlink « SYMBOLE / USD » trouvés dans l'oracle
    by_symbol = {n.meta.get("symbol"): a for a, n in assets.items()}
    for n in g.nodes.values():
        if n.type == "oracle" and n.meta.get("oracle_kind") == "chainlink_aggregator_proxy":
            base, _, quote = (n.meta.get("description") or "").partition("/")
            if quote.strip() == "USD" and base.strip() in by_symbol and n.meta.get("answer") is not None:
                n.meta["priced_asset"] = by_symbol[base.strip()]       # le feed mesure le prix de marché de cet actif
                prices.setdefault(by_symbol[base.strip()], (n.meta["answer"], f"Chainlink {n.meta['description']} ({n.address})"))

    # 2. collatéral : prix de l'oracle du marché (en actif prêté) × prix USD de l'actif prêté
    oracle = g.nodes.get(market.meta["oracle"])
    if oracle is not None and oracle.meta.get("price") is not None:
        mode = oracle.meta.get("effective_pricing_mode", oracle.meta.get("pricing_mode"))
        prices.setdefault(market.meta["collateral_token"],
                          (oracle.meta["price"] * loan_usd, f"oracle Morpho {oracle.address} (mode {mode}) × prix USD de l'actif prêté"))

    # 3. propagation : ERC-4626 et SY dérivent leur prix de leur sous-jacent (itératif)
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

    # 4. écriture price_usd / tvl_usd
    for a, n in assets.items():
        p = prices.get(a)
        n.meta["price_usd"] = round(p[0], 8) if p else None
        n.meta["price_usd_source"] = p[1] if p else "aucun prix prouvable on-chain"
        supply = n.meta.get("total_supply_human")
        n.meta["tvl_usd"] = round(supply * p[0], 2) if p and supply is not None else None
        n.meta["tvl_usd_definition"] = "totalSupply × price_usd"
    loan = prices[market.meta["loan_token"]][0]
    market.meta["tvl_usd"] = round(market.meta["total_supply_human"] * loan, 2)
    market.meta["tvl_usd_definition"] = "total fourni (intérêts inclus) × prix USD de l'actif prêté"
    for n in g.nodes.values():
        if n.type == "vault" and n.meta.get("asset") in prices and n.meta.get("total_assets") is not None:
            dec = assets[n.meta["asset"]].meta["decimals"] if n.meta["asset"] in assets else None
            if dec is not None:
                n.meta["tvl_usd"] = round(int(n.meta["total_assets"]) / 10**dec * prices[n.meta["asset"]][0], 2)
                n.meta["tvl_usd_definition"] = "totalAssets × prix USD de l'actif du vault"
        if n.type == "liquidity_venue" and "reserve_pt" in n.meta:
            pt, sy = prices.get(n.meta["pt"]), prices.get(n.meta["sy"])
            n.meta["tvl_usd"] = round(n.meta["reserve_pt"] * pt[0] + n.meta["reserve_sy"] * sy[0], 2) if pt and sy else None
            n.meta["tvl_usd_definition"] = "réserve PT × prix PT + réserve SY × prix SY"
            _compare_pt_prices(g, n, market, block_ts)


def _compare_pt_prices(g: GraphBuilder, pool: Node, market: Node, block_ts: int) -> None:
    """Prix du PT selon l'AMM (taux implicite) vs selon l'oracle Morpho."""
    pt = g.nodes.get(pool.meta["pt"])
    oracle = g.nodes.get(market.meta["oracle"])
    if pt is None or "implied_apy" not in pool.meta or oracle is None or oracle.meta.get("price") is None:
        return
    years = max(pt.meta["expiry"] - block_ts, 0) / SECONDS_PER_YEAR
    amm_price = math.exp(-math.log1p(pool.meta["implied_apy"]) * years)    # en actif comptable (USDe)
    pool.meta["pt_price_implied_by_amm"] = round(amm_price, 8)
    pool.meta["pt_price_implied_by_amm_unit"] = "actif comptable du SY (USDe), = (1 + implied_apy)^(−années restantes)"
    pool.meta["pt_price_morpho_oracle"] = round(oracle.meta["price"], 8)
    pool.meta["oracle_vs_amm_gap"] = round(oracle.meta["price"] / amm_price - 1, 6)
