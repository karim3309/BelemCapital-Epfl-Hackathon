"""Shock propagation through the graph: "if THIS node breaks, what happens to the others?"

Picture: dominoes. An arrow A → B means "A depends on B". When B falls, the jolt
travels up to A, then to whatever depends on A… up to the position. Each arrow TYPE has its
own rule, written in plain words below (RULES) and applied mechanically:

  redeemable_into  (PT → SY → sUSDe → USDe) : the value follows what it can be exchanged for.
  issued_by        (USDe → Ethena)          : if the issuer loses part of its reserves, its "base"
                                              token loses the same share (no double counting:
                                              sUSDe inherits the loss through USDe, not a 2nd time).
  deployed_in      (Ethena → exchange)      : if a counterparty defaults, the issuer loses the share of
                                              its reserves exposed to it (displayed parameter).
  deployed_in      (PT → Pendle pool)       : a pool draining does not change the PT's value, but the
                                              cost to EXIT (and the profitability of liquidations).
  priced_by        (market → oracle → feed) : a "market" feed passes on the market price, a "fixed"
                                              feed passes on nothing, a meta-oracle chooses according
                                              to its switch rule (see oracle_sim.py).
  collateralized_by / lends                 : the market absorbs the change of the collateral / of the debt
                                              (see position.py).

The result is a "shocked world" (World): for each asset, a value multiplier
(1.00 = unchanged; 0.90 = −10%), plus the state of feeds, pools and protocols.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graphview import GraphView
from .fmt import pct

RULES = {
    "deployed_in": "funds placed in \"{to}\" suffer its failure (or its liquidity, for a pool)",
    "collateralized_by": "the market is secured by \"{to}\": if its value drops, the borrowers' health drops",
    "lends": "the market lends \"{to}\": the debt is denominated in this asset",
    "priced_by": "\"{from_}\" takes its price from \"{to}\": the shock only passes if \"{to}\" follows the market",
    "redeemable_into": "\"{from_}\" can be exchanged for \"{to}\": its value follows that of \"{to}\"",
    "issued_by": "\"{from_}\" is issued by \"{to}\": a loss of the issuer's reserves devalues it",
    "settled_on": "\"{from_}\" runs on \"{to}\": a chain halt blocks liquidations and exits",
}

SHOCK_KINDS = {"market_depeg", "counterparty_failure", "issuer_failure", "protocol_exploit",
               "feed_fault", "feed_frozen", "liquidity_drain", "chain_halt"}


@dataclass
class Shock:
    node: str                          # id of the targeted node in graph.json
    kind: str                          # see SHOCK_KINDS
    severity: float = 0.0              # loss (0..1); feed_fault: gap of the reported price; liquidity_drain: liquidity lost
    duration_hours: float | None = None   # None = permanent (beyond the horizon)
    panic: float = 0.0                 # extra panic discount (counterparty failure)
    label: str = ""

    def __post_init__(self):
        if self.kind not in SHOCK_KINDS:
            raise ValueError(f"unknown shock type: {self.kind}")
        if not 0 <= self.severity <= 1:
            raise ValueError("severity must be in [0, 1]")

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class World:
    asset_mult: dict[str, float] = field(default_factory=dict)
    issuer_health: dict[str, float] = field(default_factory=dict)
    feed_override: dict[str, tuple] = field(default_factory=dict)   # id → ("fault", mult) | ("frozen", None)
    pool_factor: dict[str, float] = field(default_factory=dict)
    protocol_loss: dict[str, float] = field(default_factory=dict)   # protocol issuer → share lost
    chain_halted: bool = False
    duration_hours: float | None = 0.0    # shock duration (None = permanent)
    trace: list[str] = field(default_factory=list)                  # rules applied, in plain words

    def mult(self, asset_id: str) -> float:
        return self.asset_mult.get(asset_id, 1.0)


def counterparty_share(role: str | None, params) -> tuple[float, str]:
    if role == "custodian_off_exchange_settlement":
        return params["custodian_backing_share"], "custodian_backing_share"
    if role == "hedging_venue":
        return params["exchange_exposure_share"], "exchange_exposure_share"
    return 1.0, "full exposure (unknown role)"


def _combined_duration(shocks: list[Shock]) -> float | None:
    if not shocks:
        return 0.0
    if any(s.duration_hours is None for s in shocks):
        return None
    return max(s.duration_hours for s in shocks)


def propagate(gv: GraphView, shocks: list[Shock], params) -> World:
    w = World(duration_hours=_combined_duration(shocks))
    own_mult: dict[str, float] = {}
    issuer_own: dict[str, float] = {}
    cp_loss: dict[str, float] = {}
    panic: dict[str, float] = {}

    # 1) DIRECT effect of each shock on its node
    for s in shocks:
        if s.node not in gv.nodes:
            raise ValueError(f"shock on a node missing from the graph: {s.node}")
        if s.kind == "market_depeg":
            own_mult[s.node] = own_mult.get(s.node, 1.0) * (1 - s.severity)
            w.trace.append(f"{s.node} loses {pct(s.severity, 1)} of its market value (direct shock)")
        elif s.kind == "counterparty_failure":
            cp_loss[s.node] = max(cp_loss.get(s.node, 0.0), s.severity)
            for issuer in gv.sources(s.node, "deployed_in"):
                panic[issuer] = max(panic.get(issuer, 0.0), s.panic)
            w.trace.append(f"{s.node} defaults: {pct(s.severity, 0)} of the funds placed there are lost")
        elif s.kind == "issuer_failure":
            issuer_own[s.node] = issuer_own.get(s.node, 1.0) * (1 - s.severity)
            w.trace.append(f"issuer {s.node} loses {pct(s.severity, 0)} of its value (exploit / failure)")
        elif s.kind == "protocol_exploit":
            w.protocol_loss[s.node] = max(w.protocol_loss.get(s.node, 0.0), s.severity)
            w.trace.append(f"exploit of protocol {s.node}: {pct(s.severity, 0)} of the deposited funds lost")
        elif s.kind == "feed_fault":
            w.feed_override[s.node] = ("fault", 1 - s.severity)
            w.trace.append(f"feed {s.node} reports a WRONG price, {pct(s.severity, 0)} below the true price")
        elif s.kind == "feed_frozen":
            w.feed_override[s.node] = ("frozen", None)
            w.trace.append(f"feed {s.node} is FROZEN: it no longer sees the market")
        elif s.kind == "liquidity_drain":
            w.pool_factor[s.node] = min(w.pool_factor.get(s.node, 1.0), 1 - s.severity)
            w.trace.append(f"pool {s.node} loses {pct(s.severity, 0)} of its liquidity")
        elif s.kind == "chain_halt":
            w.chain_halted = True
            w.trace.append(f"chain {s.node} is halted: neither liquidation nor exit is possible")

    # 2) health of the ISSUERS (reserves exposed to off-chain counterparties)
    for issuer in [n["id"] for n in gv.of_type("issuer")]:
        h = issuer_own.get(issuer, 1.0)
        for cp in gv.targets(issuer, "deployed_in"):
            if cp in cp_loss:
                share, pname = counterparty_share(gv.meta(cp).get("role"), params)
                h *= 1 - share * cp_loss[cp]
                w.trace.append(RULES["deployed_in"].format(to=cp)
                               + f" → {issuer} loses {pct(share * cp_loss[cp], 2)} of its reserves (exposed share: {pname} = {share:g})")
        if panic.get(issuer):
            h *= 1 - panic[issuer]
            w.trace.append(f"panic on {issuer}'s tokens: extra discount of {pct(panic[issuer], 1)}")
        if h != 1.0:
            w.issuer_health[issuer] = h

    # 3) value of the ASSETS, from dependencies to dependents (reverse topological order)
    assets = [n["id"] for n in gv.of_type("asset")]
    dag = nx.DiGraph()
    dag.add_nodes_from(assets)
    for a in assets:
        for b in gv.targets(a, "redeemable_into"):
            dag.add_edge(a, b)
    order = list(reversed(list(nx.topological_sort(dag))))
    for a in order:
        m = own_mult.get(a, 1.0)
        for b in gv.targets(a, "redeemable_into"):
            if w.mult(b) != 1.0:
                w.trace.append(RULES["redeemable_into"].format(from_=a, to=b) + f" → ×{w.mult(b):.4f}")
            m *= w.mult(b)
        # no double counting: an issuer already present lower in the redemption chain is ignored here
        downstream_issuers = {i for d in nx.descendants(dag, a) for i in gv.targets(d, "issued_by")}
        for issuer in gv.targets(a, "issued_by"):
            if issuer in w.issuer_health and issuer not in downstream_issuers:
                w.trace.append(RULES["issued_by"].format(from_=a, to=issuer) + f" → ×{w.issuer_health[issuer]:.4f}")
                m *= w.issuer_health[issuer]
        if m != 1.0:
            w.asset_mult[a] = m
    return w


def contagion_paths(gv: GraphView, node: str, max_paths: int = 3) -> list[dict]:
    """Paths position → shocked node, each edge with its evidence and its transmission rule."""
    out = []
    for path in gv.paths_from_position(node, max_paths=max_paths):
        out.append({
            "nodes": [path[0]["from"]] + [e["to"] for e in path],
            "edges": [{**e, "rule": RULES[e["type"]].format(from_=e["from"], to=e["to"])} for e in path],
        })
    return out
