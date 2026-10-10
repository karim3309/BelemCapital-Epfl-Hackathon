"""Replay d'incidents réels : la position A, telle qu'elle est aujourd'hui, revivant une vraie journée de crise.

Brief : « sur des données réelles ». On rejoue le chemin de prix de l'USDe d'un jour de crise :
  - prix ON-CHAIN : les rounds du feed Chainlink USDe/USD de ce jour-là (lus au bloc figé) ;
  - prix HORS CHAÎNE (carnet d'ordres de Binance) : curé, avec sa source (risk/replays.yaml).

Et on compare trois « designs » d'oracle face à la même journée :
  1. NOTRE oracle réel (méta-oracle : primaire fixe, secours Chainlink, bascule après 16 h d'écart) ;
  2. un oracle de marché branché sur Chainlink (sans méta-oracle) ;
  3. un oracle de marché branché sur le prix de Binance (ce que faisait Binance pour son propre collatéral).
Le message du cadrage (plan B) : « la SOURCE et la LOGIQUE de l'oracle comptent ».
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from .oracle_sim import OracleEval, deviation
from .position import evaluate_position
from .propagate import World
from .scenarios import Engine
from .fmt import pct


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
    """Écart primaire/secours dans le temps. Primaire = décote fixe ; secours = décote × prix USDe :
    écart = |1 − u| / ((1 + u) / 2), il ne dépend que du prix u de l'USDe."""
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
    return {"max_deviation": max_dev, "threshold": thr, "longest_above_threshold_minutes": round(longest / 60, 1),
            "needed_minutes": needed / 60, "challenge_possible": max_dev > thr, "switched": switched}


def _liquidation_outcome(engine: Engine, oracle_factor: float, duration_hours: float, market_mult: float = 1.0) -> dict:
    """Effet d'un oracle qui affiche `oracle_factor` × prix normal, pendant que le marché on-chain vaut market_mult."""
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
        # 1. notre oracle réel
        hf_real = engine.base.hf * (u_min / 1.0 if meta["switched"] else 1.0)
        designs.append({"design": "Méta-oracle réel (primaire fixe + secours Chainlink)",
                        "min_hf": hf_real, "liquidated": hf_real < 1, "borrower_loss_usd": 0.0 if hf_real >= 1 else None,
                        "why": (f"écart max {pct(meta['max_deviation'], 2)} vs seuil {pct(meta['threshold'], 2)} ; "
                                f"au-dessus du seuil pendant {meta['longest_above_threshold_minutes']} min "
                                f"(il faut {meta['needed_minutes']:.0f} min pour basculer) → "
                                f"{'BASCULE' if meta['switched'] else 'pas de bascule, prix fixe'}")})
        # 2. oracle de marché sur Chainlink
        f_cl = u_min / u_ref
        o2 = _liquidation_outcome(engine, f_cl, 1.0)
        designs.append({"design": "Oracle de marché sur Chainlink USDe/USD", "min_hf": engine.base.hf * f_cl,
                        "liquidated": o2["liquidated"], "borrower_loss_usd": o2["borrower_loss_usd"],
                        "why": f"Chainlink est descendu à {u_min:.4f} $ ({datetime.utcfromtimestamp(u_min_t).isoformat()} UTC)"})
        item = {"id": r["id"], "title": r["title"], "story": r["story"].strip(), "available": True,
                "feed": fid, "window": r["window"], "chainlink_path": [{"t": t, "price": u} for t, u in cl],
                "chainlink_min": u_min, "chainlink_min_iso": datetime.utcfromtimestamp(u_min_t).isoformat() + "Z",
                "meta_oracle": meta, "designs": designs,
                "evidence": engine.inputs["chainlink_history"][fid]["evidence"]}
        # 3. oracle de marché sur le prix de l'exchange (hors chaîne, curé)
        off = r.get("offchain_path")
        if off:
            o3 = _liquidation_outcome(engine, off["low"] / u_ref, off["duration_minutes"] / 60)
            designs.append({"design": f"Oracle de marché sur le prix {off['venue']}", "min_hf": engine.base.hf * off["low"] / u_ref,
                            "liquidated": o3["liquidated"], "borrower_loss_usd": o3["borrower_loss_usd"],
                            "why": (f"{off['venue']} à {off['low']} $ pendant ~{off['duration_minutes']} min (source curée) ; "
                                    "on-chain le PT valait toujours ~1 : le liquidateur rachète le gage au rabais"),
                            "trace": o3["trace"]})
            item["offchain_source"] = {k: off[k] for k in ("evidence_url", "as_of", "says")}
        out.append(item)
    return out
