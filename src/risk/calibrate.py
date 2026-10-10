"""Calibration on the REAL history: how many times did USDe depeg, and by how much?

Source: every "round" of the Chainlink USDe/USD feed read on-chain (output/risk_inputs.json).
A round = a price update by Chainlink (when the price moves enough, or at regular intervals).

Analogy: re-reading a patient's temperature log over 2 years to know how many times they
had a fever, for how long, and what the worst was.

Frequency estimation method:
  - an "episode" = a continuous period where the price is below a threshold (e.g. $0.99);
  - annual frequency = number of episodes / years observed;
  - if NO episode was seen: we use the "rule of 3" (3 / years), the 95% upper bound of an
    event rate never observed — more honest than claiming "zero probability".
"""
from __future__ import annotations

from datetime import datetime, timezone

YEAR = 365 * 86400
THRESHOLDS = (0.995, 0.99, 0.98, 0.95)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def episodes(rounds: list[dict], threshold: float, end_ts: int) -> list[dict]:
    """Continuous periods below the threshold: start, end (next round above), low."""
    out, cur = [], None
    for r in rounds:
        below = r["answer"] < threshold
        if below and cur is None:
            cur = {"start": r["updated_at"], "low": r["answer"], "low_at": r["updated_at"]}
        elif below:
            if r["answer"] < cur["low"]:
                cur.update(low=r["answer"], low_at=r["updated_at"])
        elif cur is not None:
            cur["end"] = r["updated_at"]
            out.append(cur)
            cur = None
    if cur is not None:
        cur["end"] = end_ts
        out.append(cur)
    for e in out:
        e["duration_minutes"] = round((e["end"] - e["start"]) / 60, 1)
        e["start_iso"], e["low_at_iso"] = _iso(e["start"]), _iso(e["low_at"])
    return out


def calibrate_feed(history: dict, snapshot_ts: int) -> dict:
    rounds = history["rounds"]
    if not rounds:
        return {"available": False}
    first, last = rounds[0]["updated_at"], rounds[-1]["updated_at"]
    years = (snapshot_ts - first) / YEAR
    worst = min(rounds, key=lambda r: r["answer"])
    stats = {
        "available": True, "feed": history["feed"], "description": history["description"],
        "rounds": len(rounds), "first_iso": _iso(first), "last_iso": _iso(last),
        "years_observed": round(years, 3),
        "worst_price": worst["answer"], "worst_at_iso": _iso(worst["updated_at"]),
        "max_drawdown": round(1 - worst["answer"], 6),
        "by_threshold": {},
        "evidence": history["evidence"],
    }
    for thr in THRESHOLDS:
        eps = episodes(rounds, thr, snapshot_ts)
        n = len(eps)
        rate = n / years if n else 3 / years
        stats["by_threshold"][f"{thr}"] = {
            "episodes": n,
            "annual_rate": round(rate, 4),
            "rate_method": "episodes / years" if n else "no episode: rule of 3 (95% upper bound)",
            "longest_minutes": max((e["duration_minutes"] for e in eps), default=0),
            "list": eps[:10],
        }
    return stats


def calibrate(inputs: dict, snapshot_ts: int) -> dict:
    """Adds inputs['calibration'] (used by params.yaml via `inputs:calibration...`)."""
    feeds = {fid: calibrate_feed(h, snapshot_ts) for fid, h in inputs.get("chainlink_history", {}).items()}
    usde = next((v for v in feeds.values() if v.get("available") and "USDe" in (v.get("description") or "")), None)
    cal = {"feeds": feeds}
    if usde:
        cal["usde_depeg_annual_rate_099"] = usde["by_threshold"]["0.99"]["annual_rate"]
        cal["usde_worst_drawdown"] = usde["max_drawdown"]
    inputs["calibration"] = cal
    return cal
