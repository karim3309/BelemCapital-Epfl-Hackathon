"""Risk engine v2: "if this node breaks, how much does MY pocket lose?" — then the loss distribution (Monte Carlo).

Incidents are not hand-written: they are GENERATED from the pocket's graph, by node
type (collateral, feed, issuer, protocol, curator, pocket asset). For each one, a loss
function turns a severity s ∈ [0, 1] into dollars lost by the pocket, with rules written in plain words:

"VAULT DEPOSIT" POCKET (we are a lender) — we only lose the borrowers' BAD DEBT:
  for each borrower i of a market: debt Dᵢ, collateral Vᵢ (at the oracle price), the collateral drops by d
    - oracle FOLLOWING the market + gradual drop → liquidated in time (HF = 1) → no loss for the lender;
    - sudden shock, OR an oracle that does not follow (internal rate, admin-set price) → no timely liquidation:
          lossᵢ = max(0, Dᵢ − Vᵢ·(1 − d)·(1 − resale slippage))
  the market's loss is shared among its lenders: pocket = holder_share × Σ (vault_supply / total_supply) × loss
  + feed skewed UPWARDS by u: an attacker deposits collateral and borrows the available liquidity L;
    they win (and lenders lose) if (1 + u) × LLTV > 1:  loss = L × (1 − 1 / ((1 + u)·LLTV))
  + depeg of the pocket's asset (EURCV, USDC…): loss = value × d; protocol / curator failure: value × s.

"BORROW" POCKET (we are a borrower) — equity E = collateral × price − debt:
  - collateral drop d: collateral value loss × d; if the oracle follows and HF·(1 − d) < 1 → liquidation:
    + penalty ρ·D·(LIF − 1)  (LIF = official Morpho formula);   loss capped at E
  - feed skewed DOWNWARDS by x (the true price does not move): if HF·(1 − x) < 1 → wrongful liquidation:
    loss = ρ·D·(LIF/(1 − x) − 1)  (the liquidator seizes undervalued collateral).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .market_data import G, Market
from .params import Params

GRID = np.linspace(0.0, 1.0, 41)        # relative severities (0 = bottom of the range, 1 = top)


def lif(lltv: float, p: Params) -> float:
    """Liquidation Incentive Factor (doc Morpho) : min(M, 1 / (β·LLTV + (1 − β)))."""
    return min(p["morpho_lif_max"], 1 / (p["morpho_lif_beta"] * lltv + (1 - p["morpho_lif_beta"])))


@dataclass
class Event:
    id: str
    title: str
    family: str                  # params key events.<family>
    target: str                  # id of the node hit (for the contagion path)
    annual_rate: float
    sev_lo: float
    sev_hi: float
    loss_fn: Callable[[float], float]   # absolute severity → pocket loss in $
    rule: str                    # transmission rule, in plain words
    weight: float = 1.0          # share of λ (e.g. 0.5 for "upwards" on a 50/50 feed)
    # Loss that REMAINS after exiting (severity → $). None = exiting removes the whole loss.
    # E.g. a depeg of the pocket's own asset (EURCV): withdrawing from the vault still leaves you holding EURCV.
    residual_fn: Callable[[float], float] | None = None
    residual_why: str = ""
    losses: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residuals: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def severities(self) -> np.ndarray:
        return self.sev_lo + GRID * (self.sev_hi - self.sev_lo)

    def tabulate(self) -> None:
        sev = self.severities()
        self.losses = np.array([max(0.0, self.loss_fn(s)) for s in sev])
        res = [max(0.0, self.residual_fn(s)) for s in sev] if self.residual_fn else [0.0] * len(sev)
        self.residuals = np.minimum(np.array(res), self.losses)

    @property
    def avoidable(self) -> np.ndarray:
        """Loss that exiting AVOIDS, per severity of the grid."""
        return self.losses - self.residuals

    @property
    def lgi_usd(self) -> float:
        """Average loss IF the incident happens (uniform severity within the range)."""
        return float(self.losses.mean())

    @property
    def lgi_avoidable_usd(self) -> float:
        """Average loss IF the incident happens that exiting would have avoided."""
        return float(self.avoidable.mean())

    def split(self, severity: float) -> tuple[float, float]:
        """(total loss, avoidable loss) for one severity."""
        total = max(0.0, self.loss_fn(severity))
        residual = min(max(0.0, self.residual_fn(severity)), total) if self.residual_fn else 0.0
        return total, total - residual

    def p_horizon(self, days: float) -> float:
        return 1 - math.exp(-self.annual_rate * self.weight * days / 365)


# ----------------------------------------------------------------------------- "vault" pocket
@dataclass
class VaultPocket:
    label: str
    value_usd: float
    value_units: float
    unit_usd: float              # price of one unit of the pocket's asset (EURCV, USDC…)
    holder_share: float          # share of the vault held by the holder
    asset_id: str | None         # node of the pocket's asset (None if no known market lends it: all-idle vault…)
    markets: list[Market]
    exit_fraction_now: float     # share of the pocket withdrawable right away (liquidity)
    force_penalty: float
    vault_id: str
    curator_id: str | None
    asset_symbol: str = "?"


def vault_market_loss(mk: Market, drop: float, tracks: bool, speed: str, slip: float) -> float:
    """Bad debt of the market (lent units) if the collateral loses `drop`."""
    if drop <= 0 or not len(mk.debts):
        return 0.0
    if tracks and speed == "gradual":
        return 0.0                                   # liquidated at HF = 1, collateral D/LLTV > D: lenders repaid
    recovered = mk.coll_values * (1 - drop) * (1 - slip)
    return float(np.maximum(mk.debts - recovered, 0).sum())


def oracle_up_attack(mk: Market, up: float) -> float:
    k = (1 + up) * mk.lltv
    return mk.liquidity * (1 - 1 / k) if k > 1 else 0.0


def _drops(g: G, target: str, s: float) -> dict[str, float]:
    """Value shock on an asset → travels up to the assets depending on it (redeemable into, weighted)."""
    drops, todo = {target: s}, [target]
    while todo:
        cur = todo.pop()
        for e in g.into(cur, "redeemable_into"):
            v = drops[cur] * e["weight"]
            if v > drops.get(e["from"], 0):
                drops[e["from"]] = v
                todo.append(e["from"])
    return drops


def vault_events(g: G, vp: VaultPocket, p: Params) -> list[Event]:
    ev: list[Event] = []
    E = lambda fam, k: p[f"events.{fam}.{k}"]
    slip = lambda mk: p[f"liquidation_slippage.{mk.collateral_class}"]
    to_usd = vp.holder_share * vp.unit_usd

    def market_share(mk: Market) -> float:
        return mk.our_supply / mk.supply if mk.supply else 0.0

    # 1. drop of each collateral (the family depends on how the oracle prices it)
    seen = set()
    for mk in vp.markets:
        if mk.collateral_id in seen:
            continue
        seen.add(mk.collateral_id)
        fam = "volatile_crash" if mk.collateral_class == "volatile" else "rwa_credit_event"
        speed = vp_speed(p, fam)
        tracks_override = p.raw["events"][fam].get("oracle_tracks")

        def loss(s, cid=mk.collateral_id, fam=fam, speed=speed, tro=tracks_override):
            drops = _drops(g, cid, s)
            tot = 0.0
            for m in vp.markets:
                d = drops.get(m.collateral_id, 0.0)
                tracks = m.tracks_market if tro is None else (tro and m.tracks_market)
                tot += market_share(m) * vault_market_loss(m, d, tracks, speed, slip(m))
            return tot * to_usd
        lo, hi = E(fam, "severity")
        rule = ("gradual drop of a market-priced collateral: borrowers are liquidated in time (HF = 1), "
                "the lender loses nothing — unless a sudden shock" if fam == "volatile_crash" else
                "sudden shock on a collateral whose oracle does NOT follow the market (internal rate / set price): no "
                "timely liquidation → bad debt max(0, D − V·(1−d)·(1−slippage)), borrower by borrower")
        ev.append(Event(f"{fam}:{mk.collateral_id}", f"{mk.collateral_symbol} collateral drop", fam,
                        mk.collateral_id, E(fam, "annual_rate"), lo, hi, loss, rule))

    # 2. price feeds: skewed upwards (liquidity attack) — downwards costs the lender nothing
    feeds = {}
    for mk in vp.markets:
        for f in mk.feeds:
            feeds.setdefault(f.node_id, (f, []))[1].append(mk)
    for fid, (f, mks) in feeds.items():
        if f.mode == "fixed" and f.bounds is None:
            continue                                   # constant / formula: nothing to skew
        fam = ("admin_feed_compromise" if f.kind == "midas_custom_aggregator_feed"
               else "internal_rate_fault" if f.mode == "internal_rate" else "oracle_fault")
        if f.bounds:                                   # on-chain bounds: the admin cannot go beyond
            lo = hi = f.bounds[1] if f.role == "base" else f.bounds[0]
            weight = 1.0
        else:
            lo, hi = E(fam, "severity")
            weight = 0.5                               # 50% upwards (the case that costs the lender)

        def loss(s, mks=mks):
            return sum(market_share(m) * oracle_up_attack(m, s) for m in mks) * to_usd
        ev.append(Event(f"{fam}:{fid}", f"Feed {f.label} skewed (collateral price overstated)", fam, fid,
                        E(fam, "annual_rate"), lo, hi, loss,
                        "an attacker borrows the available liquidity L against overstated collateral: "
                        "loss = L·(1 − 1/((1+u)·LLTV)) if (1+u)·LLTV > 1", weight=weight))

    # 3. the pocket's own asset (EURCV, USDC…) and its issuers
    lo, hi = E("stable_depeg", "severity")
    asset_label = g.nodes[vp.asset_id]["label"] if vp.asset_id else vp.asset_symbol
    keep = "withdrawing from the vault gives back this same asset: exiting does not avoid its depeg"
    ev.append(Event(f"stable_depeg:{vp.asset_id or vp.asset_symbol.lower()}", f"{asset_label} depeg (pocket asset)",
                    "stable_depeg", vp.asset_id or vp.vault_id, E("stable_depeg", "annual_rate"), lo, hi,
                    lambda s: vp.value_usd * s, "the pocket is denominated in this asset: loss = value × d",
                    residual_fn=lambda s: vp.value_usd * s, residual_why=keep))
    if vp.asset_id:
        ev += issuer_events(g, p, vp.asset_id, lambda s: vp.value_usd * s, vault=vp,
                            residual_fn=lambda s: vp.value_usd * s, residual_why=keep)

    # 4. protocol and curator
    lo, hi = E("protocol_exploit", "severity")
    mid = next((e["to"] for e in g.out(vp.markets[0].node_id, "issued_by")), vp.markets[0].node_id) if vp.markets else vp.vault_id
    ev.append(Event("protocol_exploit:morpho", "Morpho Blue protocol exploit", "protocol_exploit", mid,
                    E("protocol_exploit", "annual_rate"), lo, hi, lambda s: vp.value_usd * s,
                    "all deposited funds are exposed: loss = value × s"))
    if vp.curator_id:
        lo, hi = E("curator_failure", "severity")
        ev.append(Event(f"curator_failure:{vp.curator_id}", f"Curator failure ({g.nodes[vp.curator_id]['label']})",
                        "curator_failure", vp.curator_id, E("curator_failure", "annual_rate"), lo, hi,
                        lambda s: vp.value_usd * s, "bad allocation bounded by the caps: loss = value × s"))
    return ev


def vp_speed(p: Params, fam: str) -> str:
    return p.raw["events"][fam]["speed"]


def issuer_events(g: G, p: Params, asset_id: str, loss: Callable[[float], float], vault=None,
                  residual_fn: Callable[[float], float] | None = None, residual_why: str = "") -> list[Event]:
    out = []
    lo, hi = p["events.issuer_failure.severity"]
    for e in g.out(asset_id, "issued_by"):
        iss = g.nodes[e["to"]]
        if iss["meta"].get("role") == "vault_curator":
            continue
        out.append(Event(f"issuer_failure:{e['to']}", f"Issuer failure: {iss['label']} ({g.nodes[asset_id]['label']})",
                         "issuer_failure", e["to"], p["events.issuer_failure.annual_rate"], lo, hi, loss,
                         "the issued asset loses s of its value", residual_fn=residual_fn, residual_why=residual_why))
    return out


# ----------------------------------------------------------------------------- "borrow" pocket
@dataclass
class BorrowPocket:
    label: str
    value_usd: float             # equity in $
    unit_usd: float              # price of the lent asset
    market: Market
    collateral_value: float      # in lent units (oracle price)
    debt: float
    hf: float

    @property
    def equity(self) -> float:
        return max(self.collateral_value - self.debt, 0.0)


def borrow_loss_drop(bp: BorrowPocket, d: float, tracks: bool, p: Params, beta: bool = False) -> float:
    """beta=True: drop of a volatile asset = chosen market exposure → only the LIQUIDATION counts
    (borrow_market_beta_excluded parameter); beta=False: value loss specific to the collateral (RWA, depeg)."""
    loss = 0.0 if (beta and p["borrow_market_beta_excluded"]) else bp.collateral_value * d
    if tracks and bp.hf * (1 - d) < 1:
        loss += p["liquidation_repaid_fraction"] * bp.debt * (lif(bp.market.lltv, p) - 1)
    return min(loss, bp.equity) * bp.unit_usd


def borrow_residual(bp: BorrowPocket, d: float, p: Params, beta: bool = False) -> float:
    """After unwinding (enough collateral sold to repay the debt), the equity is still held IN the collateral token:
    its own value loss stays (E × d); a volatile beta does not count (borrow_market_beta_excluded)."""
    if beta and p["borrow_market_beta_excluded"]:
        return 0.0
    return min(bp.equity * d, bp.equity) * bp.unit_usd


KEEP_COLLATERAL = ("after unwinding, the equity is still held in the collateral token: its own value loss "
                   "(equity × d) is not avoided, only the leverage and the liquidation are")


def borrow_events(g: G, bp: BorrowPocket, p: Params) -> list[Event]:
    mk, E = bp.market, (lambda fam, k: p[f"events.{fam}.{k}"])
    ev = []
    fam = "volatile_crash" if mk.collateral_class == "volatile" else "rwa_credit_event"
    tro = p.raw["events"][fam].get("oracle_tracks")
    tracks = mk.tracks_market if tro is None else (tro and mk.tracks_market)
    lo, hi = E(fam, "severity")
    beta = fam == "volatile_crash"
    rule = ("drop of a volatile asset: chosen market exposure, only the liquidation counts "
            "(penalty ρ·D·(LIF−1) if HF·(1−d) < 1)" if beta and p["borrow_market_beta_excluded"] else
            "value loss specific to the collateral; + liquidation penalty ρ·D·(LIF−1) if the oracle follows and HF·(1−d) < 1")
    ev.append(Event(f"{fam}:{mk.collateral_id}", f"{mk.collateral_symbol} collateral drop", fam, mk.collateral_id,
                    E(fam, "annual_rate"), lo, hi, lambda s: borrow_loss_drop(bp, s, tracks, p, beta), rule,
                    residual_fn=lambda s: borrow_residual(bp, s, p, beta), residual_why=KEEP_COLLATERAL))
    ev += issuer_events(g, p, mk.collateral_id, lambda s: borrow_loss_drop(bp, s, mk.tracks_market, p),
                        residual_fn=lambda s: borrow_residual(bp, s, p), residual_why=KEEP_COLLATERAL)
    rho, L = p["liquidation_repaid_fraction"], lif(mk.lltv, p)
    for f in mk.feeds:
        if f.mode == "fixed" and f.bounds is None:
            continue
        fam_f = ("admin_feed_compromise" if f.kind == "midas_custom_aggregator_feed"
                 else "internal_rate_fault" if f.mode == "internal_rate" else "oracle_fault")
        if f.bounds:
            lo = hi = f.bounds[0] if f.role == "base" else f.bounds[1]
            weight = 1.0
        else:
            lo, hi = E(fam_f, "severity")
            weight = 0.5                                     # 50% downwards (the case that costs the borrower)

        def loss(x):
            if bp.hf * (1 - x) >= 1:
                return 0.0
            return min(rho * bp.debt * (L / (1 - x) - 1), bp.equity) * bp.unit_usd
        ev.append(Event(f"{fam_f}:{f.node_id}", f"Feed {f.label} skewed downwards (wrongful liquidation)", fam_f, f.node_id,
                        E(fam_f, "annual_rate"), lo, hi, loss,
                        "if HF·(1−x) < 1: wrongful liquidation, loss = ρ·D·(LIF/(1−x) − 1)", weight=weight))
    lo, hi = E("protocol_exploit", "severity")
    mid = next((e["to"] for e in g.out(mk.node_id, "issued_by")), mk.node_id)
    ev.append(Event("protocol_exploit:morpho", "Morpho Blue protocol exploit", "protocol_exploit", mid,
                    E("protocol_exploit", "annual_rate"), lo, hi,
                    lambda s: min(bp.collateral_value * s, bp.equity) * bp.unit_usd,
                    "stolen collateral: loss = min(collateral × s, equity)"))
    return ev


# ----------------------------------------------------------------------------- Monte Carlo
def monte_carlo(events: list[Event], cap_usd: float, days: float, p: Params) -> dict:
    """Each incident happens (or not) over the horizon; uniform severity within its range; losses added up,
    capped at the pocket's value. Events assumed independent (stated limit)."""
    n, rng = int(p["monte_carlo.samples"]), np.random.default_rng(int(p["monte_carlo.seed"]))
    total, kept = np.zeros(n), np.zeros(n)
    for e in events:
        if not len(e.losses):
            e.tabulate()
        hit = rng.random(n) < e.p_horizon(days)
        u = rng.random(n)
        total += np.where(hit, np.interp(u, GRID, e.losses), 0.0)
        kept += np.where(hit, np.interp(u, GRID, e.residuals), 0.0)
    total = np.minimum(total, cap_usd)
    kept = np.minimum(kept, total)
    avoidable = total - kept
    return {"samples": n, "horizon_days": days, "expected_loss_usd": float(total.mean()),
            "expected_loss_avoidable_usd": float(avoidable.mean()),
            "expected_loss_unavoidable_usd": float(kept.mean()),
            "avoidable_note": "avoidable = what exiting removes; unavoidable = what stays with the asset you get back "
                              "(e.g. a depeg of the pocket's own asset)",
            "var95_usd": float(np.quantile(total, 0.95)), "var99_usd": float(np.quantile(total, 0.99)),
            "var999_usd": float(np.quantile(total, 0.999)),
            "p_any_loss": float((total > 0).mean()),
            "independence_note": "incidents drawn independently (correlations between nodes not modelled)"}
