"""Oracle simulator: what price will Morpho see DURING the shock?

Reminder (BEGINNER_GUIDE §8): the oracle is the appraiser valuing the collateral. Morpho trusts it blindly.
We replay the oracle tree discovered in graph.json, block by block:

  - "market" feed (Chainlink)         : it sees the shock → value × multiplier of the measured asset;
                                        unless it is broken (wrong price) or frozen (sees nothing);
  - "fixed" feed (linear discount)    : it sees NOTHING of the market; only the clock moves it
                                        (price = 1 − discount × time remaining);
  - constant feed ("Dummy")           : always the same value;
  - MorphoChainlinkOracleV2           : price = SCALE × base feeds / quote feeds, so we
                                        multiply the normal price by the change of each block;
  - META-ORACLE (Steakhouse)          : two appraisers and a referee. Deviation = |primary − fallback| /
                                        average. If the deviation exceeds the threshold, anyone calls
                                        challenge(); if the deviation still holds after the delay
                                        (challengeTimelock, read on-chain: 16 h), it SWITCHES to the fallback.
    → the DURATION of the shock matters as much as its size: this is the heart of our analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .graphview import GraphView
from .propagate import World
from .fmt import pct

YEAR = 365 * 86400


@dataclass
class OracleEval:
    node: str
    kind: str
    price_normal: float
    price: float                       # price seen by Morpho during the shock (after the switch decision)
    mode: str                          # EFFECTIVE pricing mode during the shock
    switched: bool = False
    switch_after_hours: float | None = None
    deviation: float | None = None
    challenge_possible: bool = False
    timeline: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    children: list["OracleEval"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "children"}
        d["children"] = [c.to_dict() for c in self.children]
        return d


def _linear_answer(meta: dict, ts: float) -> float:
    left = max(meta["maturity"] - ts, 0)
    return 1 - meta["base_discount_per_year"] * left / YEAR


def _feed(gv: GraphView, fid: str, world: World, ts_offset: float) -> tuple[float, float, str, list[str]]:
    """(normal value, shocked value, mode, trace) of a feed, in "human" units."""
    meta, kind = gv.meta(fid), gv.meta(fid).get("oracle_kind")
    now = gv.snapshot()["timestamp"]
    if kind == "pendle_linear_discount_feed":
        normal = _linear_answer(meta, now + ts_offset)
        return normal, normal, "fixed", [f"{fid}: discount formula, blind to the market ({normal:.6f})"]
    if kind == "constant_feed":
        return meta["answer"], meta["answer"], "fixed", [f"{fid} : constant ({meta['answer']})"]
    normal = meta.get("answer") or 1.0
    override = world.feed_override.get(fid)
    if override and override[0] == "frozen":
        return normal, normal, "market", [f"{fid}: FROZEN, does not see the shock"]
    if meta.get("pricing_mode") == "market":
        asset = gv.feed_priced_asset(fid)
        m = world.mult(asset) if asset else 1.0
        shocked = normal * m
        trace = [f"{fid} follows the {asset} market: {normal:.5f} → {shocked:.5f}"]
        if override and override[0] == "fault":
            shocked = normal * override[1]
            trace.append(f"{fid} BROKEN: reports {shocked:.5f} whatever the market")
        return normal, shocked, "market", trace
    return normal, normal, meta.get("pricing_mode", "unknown"), [f"{fid}: mode {meta.get('pricing_mode')} — no proven transmission"]


def evaluate(gv: GraphView, oid: str, world: World, params, ts_offset: float = 0.0) -> OracleEval:
    meta = gv.meta(oid)
    kind = meta.get("oracle_kind", "unknown")

    if kind == "morpho_meta_oracle_deviation_timelock":
        return _meta(gv, oid, world, params, ts_offset)

    if kind in ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1"):
        ratio, modes, trace, children = 1.0, [], [], []
        now = gv.snapshot()["timestamp"]
        for slot, comp in meta.get("components", {}).items():
            if not comp.get("address") or comp.get("pricing_mode") == "internal_rate":
                continue      # empty slot (= 1) or internal rate: blind to the market shock
            node = gv.by_address(comp["address"])
            if node is None:
                continue
            normal_now = gv.meta(node["id"]).get("answer")
            normal, shocked, mode, t = _feed(gv, node["id"], world, ts_offset)
            # change relative to the value READ at the block (the oracle's normal price matches it)
            if normal_now:
                factor = shocked / normal_now
                ratio *= factor if comp["role"] == "base" else 1 / factor
            modes.append(mode)
            trace += t
            children.append(OracleEval(node=node["id"], kind=gv.meta(node["id"]).get("oracle_kind"),
                                       price_normal=normal, price=shocked, mode=mode, trace=t))
        base = meta["price"]
        # "normal" price at the shifted date (S-TIME): only the linear discount moves with the clock
        time_ratio = 1.0
        for c in children:
            if c.kind == "pendle_linear_discount_feed":
                time_ratio *= _linear_answer(gv.meta(c.node), now + ts_offset) / gv.meta(c.node)["answer"]
        price_normal = base * time_ratio
        mode = "market" if "market" in modes else ("fixed" if modes else "fixed")
        return OracleEval(node=oid, kind=kind, price_normal=price_normal, price=base * ratio,
                          mode=mode, trace=trace, children=children)

    # Unrecognised oracle: we do not guess
    price = meta.get("price") or meta.get("answer") or 0.0
    return OracleEval(node=oid, kind=kind, price_normal=price, price=price, mode="unknown",
                      trace=[f"{oid} not recognised: price assumed unchanged (to analyse)"])


def deviation(a: float, b: float) -> float:
    """Formula from the Steakhouse docs: |primary − fallback| / average(primary, fallback)."""
    return abs(a - b) / ((a + b) / 2) if a + b else 0.0


def _meta(gv: GraphView, oid: str, world: World, params, ts_offset: float) -> OracleEval:
    meta = gv.meta(oid)
    primary = evaluate(gv, gv.by_address(meta["primary_oracle"])["id"], world, params, ts_offset)
    backup = evaluate(gv, gv.by_address(meta["backup_oracle"])["id"], world, params, ts_offset)
    thr = params["meta_oracle_deviation_threshold"]
    challenge_h = params["meta_oracle_challenge_timelock_seconds"] / 3600
    healing_h = params["meta_oracle_healing_timelock_seconds"] / 3600
    delay_h = params["challenger_delay_hours"]
    dev = deviation(primary.price, backup.price)
    possible = dev > thr
    duration = world.duration_hours
    needed = delay_h + challenge_h
    lasts = duration is None or duration >= needed
    start_backup = meta.get("current_role") == "backup"

    tl = [{"t_hours": 0, "event": f"shock: primary/fallback deviation = {pct(dev, 2)} (threshold {pct(thr, 2)})",
           "role": "backup" if start_backup else "primary"}]
    trace = [f"deviation = |{primary.price:.6f} − {backup.price:.6f}| / average = {pct(dev, 3)}; threshold = {pct(thr, 3)}"]
    switched = start_backup
    if not start_backup and possible and world.chain_halted:
        trace.append("chain halted: nobody can call challenge() → no switch")
    elif not start_backup and possible:
        tl.append({"t_hours": delay_h, "event": "challenge() called (permissionless function)", "role": "primary"})
        if lasts:
            switched = True
            tl.append({"t_hours": needed, "event": f"acceptChallenge() after {challenge_h:.0f} h → SWITCH to the fallback",
                       "role": "backup"})
            trace.append(f"the deviation lasts ≥ {needed:.0f} h → switch to the fallback ({backup.mode})")
        else:
            tl.append({"t_hours": duration, "event": "shock ends before the delay is over → revokeChallenge(), no switch",
                       "role": "primary"})
            trace.append(f"the shock lasts {duration:g} h < {needed:.0f} h → NO switch, the price stays {primary.mode}")
    else:
        trace.append("deviation below the threshold → no challenge possible, the primary stays in place")
    if switched and duration is not None and not start_backup:
        tl.append({"t_hours": duration, "event": "end of the shock: prices reconverge → heal()", "role": "backup"})
        tl.append({"t_hours": duration + healing_h, "event": f"acceptHealing() after {healing_h:.0f} h → back to the primary",
                   "role": "primary"})

    chosen = backup if switched else primary
    return OracleEval(node=oid, kind="morpho_meta_oracle_deviation_timelock",
                      price_normal=primary.price_normal if not start_backup else backup.price_normal,
                      price=chosen.price, mode=chosen.mode, switched=switched and not start_backup,
                      switch_after_hours=needed if (switched and not start_backup) else None,
                      deviation=dev, challenge_possible=possible, timeline=tl,
                      trace=trace + primary.trace + backup.trace, children=[primary, backup])
