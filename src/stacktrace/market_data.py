"""Risk data of a pocket, taken from ITS proven graph + a few extra reads.

For each Morpho market the pocket is exposed to, we assemble:
  - the totals (supplied, borrowed, available liquidity) — already proven on-chain in the graph;
  - the oracle price, re-read on-chain (`price()`, at the pinned block);
  - the oracle PROFILE on the collateral side: does it follow the collateral's MARKET price, or an internal rate /
    an admin-set price? (that is what decides whether a drop gets liquidated in time);
  - the list of BORROWERS (debt, collateral): located by the Morpho API, rescaled to the on-chain
    total. Why not the aggregate? A borrower at 85% LTV and another at 10% do not have the same
    bad debt as an average at 47%: the loss is computed borrower by borrower.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from discovery.ctx import Ctx

BORROWERS_QUERY = """query Borrowers($m: [String!], $c: [Int!]) {
  marketPositions(first: 300, orderBy: BorrowShares, orderDirection: Desc,
                  where: { marketUniqueKey_in: $m, chainId_in: $c, borrowShares_gte: 1 }) {
    items { user { address } state { borrowAssets collateral } }
  }
}"""
MCO_KINDS = ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1")
TRACKING_MODES = ("market", "hybrid")


@dataclass
class Feed:
    node_id: str
    kind: str
    mode: str
    role: str                     # "base" (feed ↑ ⇒ collateral price ↑) or "quote" (feed ↑ ⇒ price ↓)
    label: str
    bounds: tuple[float, float] | None = None   # (max drop, max rise) relative, if the feed is bounded on-chain


@dataclass
class Market:
    market_id: str
    node_id: str
    label: str
    collateral_id: str
    collateral_symbol: str
    loan_symbol: str
    lltv: float
    supply: float                 # in units of the lent asset
    borrow: float
    liquidity: float
    supply_apy: float | None
    collateral_mode: str          # pricing mode of the oracle on the COLLATERAL SIDE
    collateral_class: str         # volatile | pendle_pt | rwa_or_synthetic
    oracle_id: str
    feeds: list[Feed]
    price: float                  # oracle price: lent units per unit of collateral
    debts: np.ndarray = field(default_factory=lambda: np.zeros(0))       # debt of each borrower
    coll_values: np.ndarray = field(default_factory=lambda: np.zeros(0)) # collateral × oracle price (lent units)
    borrowers_source: str = ""
    our_supply: float = 0.0       # what the pocket's VAULT supplies to this market

    @property
    def tracks_market(self) -> bool:
        return self.collateral_mode in TRACKING_MODES


# ----------------------------------------------------------------------------- graph reading
class G:
    """Convenient access to a pocket's graph.json (dict)."""

    def __init__(self, graph: dict):
        self.raw = graph
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.edges = graph["edges"]
        self.by_address = {n["address"]: n["id"] for n in graph["nodes"] if n.get("address") and n["type"] != "lending_market"}

    def out(self, nid: str, etype: str | None = None) -> list[dict]:
        return [e for e in self.edges if e["from"] == nid and (etype is None or e["type"] == etype)]

    def into(self, nid: str, etype: str | None = None) -> list[dict]:
        return [e for e in self.edges if e["to"] == nid and (etype is None or e["type"] == etype)]

    def meta(self, nid: str) -> dict:
        return self.nodes[nid]["meta"]

    def first(self, ntype: str) -> dict | None:
        return next((n for n in self.raw["nodes"] if n["type"] == ntype), None)

    def path_to(self, target: str) -> list[dict]:
        """Shortest path position → target (list of edges): the CONTAGION PATH."""
        start = self.raw["position"]["id"]
        prev, q = {start: None}, [start]
        while q:
            u = q.pop(0)
            if u == target:
                break
            for e in self.out(u):
                if e["to"] not in prev:
                    prev[e["to"]] = e
                    q.append(e["to"])
        if target not in prev:
            return []
        path, cur = [], target
        while prev[cur]:
            path.insert(0, prev[cur])
            cur = prev[cur]["from"]
        return path


def collateral_side_mode(base_modes: list[str]) -> str:
    """The collateral price FOLLOWS its market only if ALL its collateral-side components follow a market.
    E.g. PST priced = PST internal rate × USDC/USD (market) → the collateral itself is NOT tracked at market."""
    if not base_modes:
        return "fixed"
    for m in ("unknown", "fixed", "internal_rate"):
        if m in base_modes:
            return m
    return "market"


def oracle_profile(g: G, oracle_id: str) -> tuple[str, list[Feed]]:
    """(collateral-side mode, leaf feeds with their role). For a MorphoChainlinkOracle, only the
    BASE components describe the collateral (the QUOTE ones describe the lent asset)."""
    m = g.meta(oracle_id)
    feeds: list[Feed] = []

    def leaves(nid: str, role: str, seen: set) -> None:
        if nid in seen:
            return
        seen.add(nid)
        node = g.nodes[nid]
        nxt = [e["to"] for e in g.out(nid, "priced_by") if g.nodes[e["to"]]["type"] == "oracle"]
        if node["type"] == "oracle" and node["meta"].get("oracle_kind") not in MCO_KINDS and \
                node["meta"].get("oracle_kind") != "morpho_meta_oracle_deviation_timelock":
            nm = node["meta"]
            bounds = None
            if nm.get("oracle_kind") == "midas_custom_aggregator_feed" and nm.get("answer"):
                bounds = (1 - nm["min_answer"] / nm["answer"], nm["max_answer"] / nm["answer"] - 1)
            feeds.append(Feed(nid, nm.get("oracle_kind", "?"), nm.get("pricing_mode", "unknown"), role, node["label"], bounds))
        for t in nxt:
            leaves(t, role, seen)

    if m.get("oracle_kind") in MCO_KINDS:
        comps = m.get("components") or {}
        base_modes = []
        for slot, c in comps.items():
            if not c.get("address"):
                continue
            nid = g.by_address.get(c["address"])
            role = c.get("role", "base")
            if role == "base":
                base_modes.append(c.get("pricing_mode") or (g.meta(nid).get("pricing_mode") if nid else "unknown"))
            if nid and g.nodes[nid]["type"] == "oracle":
                leaves(nid, role, set())
        return collateral_side_mode(base_modes), feeds
    leaves(oracle_id, "base", set())
    return m.get("pricing_mode", "unknown"), feeds


def collateral_class(g: G, coll_id: str, mode: str) -> str:
    if g.meta(coll_id).get("asset_kind") == "pendle_pt":
        return "pendle_pt"
    return "volatile" if mode in TRACKING_MODES else "rwa_or_synthetic"


# ----------------------------------------------------------------------------- assemblage
def load_markets(ctx: Ctx, g: G) -> list[Market]:
    out = []
    for n in g.raw["nodes"]:
        if n["type"] != "lending_market":
            continue
        m = n["meta"]
        coll_id = next(e["to"] for e in g.out(n["id"], "collateralized_by"))
        loan_id = next(e["to"] for e in g.out(n["id"], "lends"))
        oracle_id = next(e["to"] for e in g.out(n["id"], "priced_by"))
        mode, feeds = oracle_profile(g, oracle_id)
        loan_dec, coll_dec = g.meta(loan_id)["decimals"], g.meta(coll_id)["decimals"]
        price_raw = ctx.call(m["oracle"], "price()", returns=["uint256"])
        price = price_raw / 10**36 * 10**coll_dec / 10**loan_dec       # lent units per unit of collateral
        apy = m.get("borrow_apy")
        supply_apy = apy * (m.get("utilization") or 0) * (1 - (m.get("fee") or 0)) if apy is not None else None
        mk = Market(
            market_id=m["market_id"], node_id=n["id"], label=n["label"], collateral_id=coll_id,
            collateral_symbol=g.nodes[coll_id]["label"], loan_symbol=g.nodes[loan_id]["label"], lltv=m["lltv"],
            supply=m["total_supply_human"], borrow=m["total_borrow_human"], liquidity=max(m["available_liquidity_human"], 0),
            supply_apy=supply_apy, collateral_mode=mode, collateral_class=collateral_class(g, coll_id, mode),
            oracle_id=oracle_id, feeds=feeds, price=price)
        _load_borrowers(ctx, mk, loan_dec, coll_dec, price_raw)
        out.append(mk)
    return out


def _load_borrowers(ctx: Ctx, mk: Market, loan_dec: int, coll_dec: int, price_raw: int) -> None:
    url = ctx.config.apis["morpho_graphql"]
    debts, colls = [], []
    try:
        data, fetched = ctx.http.post_json(url, {"query": BORROWERS_QUERY, "variables": {"m": [mk.market_id], "c": [1]}})
        for it in ((data.get("data") or {}).get("marketPositions") or {}).get("items") or []:
            st = it["state"]
            debts.append(int(st["borrowAssets"] or 0) / 10**loan_dec)
            colls.append(int(st["collateral"] or 0) * price_raw / 10**36 / 10**loan_dec)
        src = f"API Morpho {url} marketPositions (fetched {fetched})"
    except Exception as e:                       # API silent: fall back to the aggregate, and SAY it
        src = f"API unavailable ({type(e).__name__}) → a single aggregated borrower"
    listed = sum(debts)
    residual = mk.borrow - listed
    if residual > 1e-6 * max(mk.borrow, 1):
        # Unlisted borrowers: grouped at the listed ones' average LTV (or at the LLTV, prudently, if none).
        ltv = (listed / sum(colls)) if colls and sum(colls) else mk.lltv
        debts.append(residual)
        colls.append(residual / ltv)
        src += f"; remaining {residual:,.0f} {mk.loan_symbol} aggregated at the average LTV {ltv:.1%}"
    elif listed > mk.borrow and listed:
        k = mk.borrow / listed                 # rescaled to the total PROVEN on-chain (accrued interest)
        debts = [d * k for d in debts]
    mk.debts, mk.coll_values, mk.borrowers_source = np.array(debts), np.array(colls), src
