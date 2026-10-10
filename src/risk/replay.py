"""Replay of real incidents: position A, as it is today, living through a real day of crisis.

Brief: "on real data". We replay the USDe price path of a crisis day:
  - ON-CHAIN price: the rounds of the Chainlink USDe/USD feed that day (read at the pinned block);
  - OFF-CHAIN price (Binance order book): curated, with its source (risk/replays.yaml).

And we compare three oracle "designs" facing the same day:
  1. OUR real oracle (meta-oracle: fixed primary, Chainlink fallback, switch after 16 h of deviation);
  2. a market oracle plugged into Chainlink (without a meta-oracle);
  3. a market oracle plugged into the Binance price (what Binance did for its own collateral).
The framing note's message (plan B): "the SOURCE and the LOGIC of the oracle matter".
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from .oracle_sim import OracleEval, deviation
from .position import evaluate_position
from .propagate import World
from .scenarios import Engine
from .fmt import num, pct


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def chainlink_path(engine: Engine, start: int, end: int) -> tuple[str, list[tuple[int, float]]]:
    hist = engine.inputs.get("chainlink_history", {})
    fid = next(iter(hist))
    rounds = hist[fid]["rounds"]
    before = [r for r in rounds if r["updated_at"] < start]
    path = [(start, before[-1]["answer"])] if before else []
    path += [(r["updated_at"], r["answer"]) for r in rounds if start <= r["updated_at"] <= end]
    return fid, path


def meta_on_path(engine: Engine, path: list[tuple[int, float]], end: int) -> dict:
    """Primary/fallback deviation over time. Primary = fixed discount; fallback = discount × USDe price:
    deviation = |1 − u| / ((1 + u) / 2), it only depends on the USDe price u."""
    p = engine.params
    thr = p["meta_oracle_deviation_threshold"]
    needed = (p["challenger_delay_hours"] * 3600) + p["meta_oracle_challenge_timelock_seconds"]
    above_start, longest, max_dev, switched = None, 0, 0.0, False
    points = path + [(end, path[-1][1])] if path else []
    for (t, u), (t_next, _) in zip(points, points[1:]):
        dev = deviation(1.0, u)
        max_dev = max(max_dev, dev)
        if dev > thr:
            above_start = t if above_start is None else above_start
            span = t_next - above_start
            longest = max(longest, span)
            if span >= needed:
                switched = True
        else:
            above_start = None
    # USDe price below which the deviation exceeds the threshold: 2(1−u)/(1+u) = threshold  ⇔  u = (2 − threshold)/(2 + threshold)
    return {"max_deviation": max_dev, "threshold": thr, "challenge_price": (2 - thr) / (2 + thr), "longest_above_threshold_minutes": round(longest / 60, 1),
            "needed_minutes": needed / 60, "challenge_possible": max_dev > thr, "switched": switched}


def _liquidation_outcome(engine: Engine, oracle_factor: float, duration_hours: float, market_mult: float = 1.0) -> dict:
    """Effect of an oracle showing `oracle_factor` × normal price, while the on-chain market is worth market_mult."""
    base = engine.base
    world = World(duration_hours=duration_hours)
    if market_mult != 1.0:
        world.asset_mult[engine.gv.collateral_id()] = market_mult
    fake = OracleEval(node="replay", kind="counterfactual", price_normal=base.oracle_price,
                      price=base.oracle_price * oracle_factor, mode="market")
    return evaluate_position(engine.gv, base, world, fake, engine.params, engine.exit_model, engine.horizon_days)


def run_replays(engine: Engine, path: str | Path) -> list[dict]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out = []
    for r in raw["replays"]:
        start, end = _ts(r["window"]["start"]), _ts(r["window"]["end"])
        fid, cl = chainlink_path(engine, start, end)
        if not cl:
            out.append({"id": r["id"], "title": r["title"], "available": False})
            continue
        u_ref = cl[0][1]
        u_min_t, u_min = min(cl[1:] or cl, key=lambda x: x[1])
        meta = meta_on_path(engine, cl, end)
        designs = []
        # 1. our real oracle
        hf_real = engine.base.hf * (u_min / 1.0 if meta["switched"] else 1.0)
        designs.append({"design": "Real meta-oracle (fixed primary + Chainlink fallback)",
                        "min_hf": hf_real, "liquidated": hf_real < 1, "borrower_loss_usd": 0.0 if hf_real >= 1 else None,
                        "why": (f"max deviation {pct(meta['max_deviation'], 2)} vs threshold {pct(meta['threshold'], 2)}; "
                                f"above the threshold for {num(meta['longest_above_threshold_minutes'], 1)} min "
                                f"({num(meta['needed_minutes'])} min needed to switch) → "
                                f"{'SWITCH' if meta['switched'] else 'no switch, fixed price'}")})
        # 2. market oracle on Chainlink
        f_cl = u_min / u_ref
        o2 = _liquidation_outcome(engine, f_cl, 1.0)
        designs.append({"design": "Market oracle on Chainlink USDe/USD", "min_hf": engine.base.hf * f_cl,
                        "liquidated": o2["liquidated"], "borrower_loss_usd": o2["borrower_loss_usd"],
                        "why": f"Chainlink went down to ${num(u_min, 4)} ({datetime.utcfromtimestamp(u_min_t).isoformat()} UTC)"})
        item = {"id": r["id"], "title": r["title"], "story": r["story"].strip(), "available": True,
                "feed": fid, "window": r["window"], "chainlink_path": [{"t": t, "price": u} for t, u in cl],
                "chainlink_min": u_min, "chainlink_min_iso": datetime.utcfromtimestamp(u_min_t).isoformat() + "Z",
                "meta_oracle": meta, "designs": designs,
                "evidence": engine.inputs["chainlink_history"][fid]["evidence"]}
        # 3. market oracle on the exchange price (off-chain, curated)
        off = r.get("offchain_path")
        if off:
            o3 = _liquidation_outcome(engine, off["low"] / u_ref, off["duration_minutes"] / 60)
            designs.append({"design": f"Market oracle on the {off['venue']} price", "min_hf": engine.base.hf * off["low"] / u_ref,
                            "liquidated": o3["liquidated"], "borrower_loss_usd": o3["borrower_loss_usd"],
                            "why": (f"{off['venue']} at ${num(off['low'], 2)} for ~{off['duration_minutes']} min (curated source); "
                                    "on-chain the PT was still worth ~1: the liquidator buys the collateral back at a discount"),
                            "trace": o3["trace"]})
            item["offchain_source"] = {k: off[k] for k in ("evidence_url", "as_of", "says")}
        out.append(item)
    return out
