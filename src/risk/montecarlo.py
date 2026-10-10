"""Monte Carlo: "over the next 7 days, how much can I lose, on average and in the worst cases?"

Idea: we replay the week 200,000 times. Each time, each root event of params.yaml
(USDe depeg, failure of an exchange or a custodian, Pendle/Morpho exploit, feed outage,
liquidity flight, USDC depeg) happens or not according to its annual frequency λ:
    probability over the horizon = 1 − exp(−λ × horizon)          (Poisson law)
with a severity and a duration drawn within their range. The drawn events become shocks, which
go through EXACTLY the same engine as the scenarios (propagation → oracle → position).

Correlation "through common parents" (framing note): two events hitting the same node
(e.g. two of Ethena's exchanges) add up on that node (USDe), then on everything depending on it.

Outputs: expected loss (mean), VaR 95% / 99% (loss exceeded in only 5% / 1% of
weeks), ES 99% (mean of the worst 1% of weeks), and the costliest contagion paths.

⚠ The frequencies λ are mostly HYPOTHESES (status displayed). That is why the decision
relies first on p* (which does not depend on them); the Monte Carlo gives the order of magnitude and the sensitivity.
"""
from __future__ import annotations

import math

import numpy as np

from .propagate import Shock, contagion_paths
from .scenarios import Engine

EVENT_TO_SHOCK = {
    "market_depeg": "market_depeg", "counterparty_failure": "counterparty_failure",
    "issuer_failure": "issuer_failure", "protocol_exploit": "protocol_exploit",
    "feed_fault": "feed_fault", "liquidity_drain": "liquidity_drain",
}


def _range(v) -> tuple[float, float]:
    if isinstance(v, (list, tuple)):
        return float(v[0]), float(v[1])
    return float(v), float(v)


def event_pairs(engine: Engine, horizon_days: float, rate_scale: dict | None = None) -> list[dict]:
    rate_scale = rate_scale or {}
    out = []
    for name, ev in engine.params.events.items():
        lam = float(ev["annual_rate"].value) * rate_scale.get(name, 1.0)
        prob = 1 - math.exp(-lam * horizon_days / 365)
        for t in engine.gv.select(ev["target"]):
            out.append({"event": name, "target": t, "kind": ev["kind"], "annual_rate": lam, "prob": prob,
                        "severity": _range(ev["severity"].value),
                        "duration": _range(ev["duration_hours"].value),
                        "panic": _range(ev["panic_depeg"].value) if "panic_depeg" in ev else (0.0, 0.0)})
    return out


def run_mc(engine: Engine, samples: int | None = None, seed: int | None = None,
           rate_scale: dict | None = None, with_paths: bool = True) -> dict:
    p = engine.params
    n = int(samples or p["mc_samples"])
    rng = np.random.default_rng(int(seed if seed is not None else p["mc_seed"]))
    horizon = p["horizon_days"]
    pairs = event_pairs(engine, horizon, rate_scale)
    k = len(pairs)
    probs = np.array([x["prob"] for x in pairs])
    occur = rng.random((n, k)) < probs
    u_sev, u_dur, u_pan = rng.random((n, k)), rng.random((n, k)), rng.random((n, k))

    borrower = np.zeros(n)
    lender = np.zeros(n)
    contrib = np.zeros(k)
    liquidations = 0
    rows = np.nonzero(occur.any(axis=1))[0]
    for i in rows:
        active = np.nonzero(occur[i])[0]
        shocks = []
        for j in active:
            x = pairs[j]
            lo, hi = x["severity"]
            dlo, dhi = x["duration"]
            plo, phi = x["panic"]
            dur = dlo + (dhi - dlo) * u_dur[i, j]
            shocks.append(Shock(node=x["target"], kind=EVENT_TO_SHOCK[x["kind"]],
                                severity=lo + (hi - lo) * u_sev[i, j],
                                duration_hours=None if dur >= horizon * 24 else dur,
                                panic=plo + (phi - plo) * u_pan[i, j]))
        _, _, out = engine.run(shocks)
        borrower[i] = out["borrower_loss_usd"]
        lender[i] = out["lender_loss_usd"]
        liquidations += int(out["liquidated"])
        if borrower[i] > 0:
            contrib[active] += borrower[i] / len(active)     # split equally between simultaneous events

    def var(x, q):
        return float(np.quantile(x, q))

    tail = np.sort(borrower)[-max(1, n // 100):]
    res = {
        "samples": n, "seed": int(seed if seed is not None else p["mc_seed"]), "horizon_days": horizon,
        "p_any_event": float(occur.any(axis=1).mean()),
        "p_loss": float((borrower > 1).mean()),
        "p_liquidation": liquidations / n,
        "expected_loss_usd": float(borrower.mean()),
        "expected_loss_pct_equity": float(borrower.mean() / engine.base.equity_usd),
        "var95_usd": var(borrower, 0.95), "var99_usd": var(borrower, 0.99),
        "es99_usd": float(tail.mean()),
        "expected_lender_loss_usd": float(lender.mean()),
        "conditional_loss_usd": float(borrower[borrower > 1].mean()) if (borrower > 1).any() else 0.0,
        "events": [{**{k2: v for k2, v in x.items()}, "expected_loss_usd": float(contrib[j] / n)}
                   for j, x in enumerate(pairs)],
    }
    res["events"].sort(key=lambda e: -e["expected_loss_usd"])
    if with_paths:
        top = []
        for e in res["events"][:3]:
            paths = contagion_paths(engine.gv, e["target"], max_paths=1)
            top.append({"event": e["event"], "target": e["target"], "expected_loss_usd": e["expected_loss_usd"],
                        "share": e["expected_loss_usd"] / res["expected_loss_usd"] if res["expected_loss_usd"] else 0,
                        "path": paths[0] if paths else None})
        res["top_paths"] = top
    return res
