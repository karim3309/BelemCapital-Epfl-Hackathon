"""Decision: stay (STAY), partly exit (PARTIAL x%), or fully exit (EXIT) — and WHY.

The rule of the brief / framing note (§4.4):
    Exit if   p × Loss  >  C_exit        ⇔        p  >  p* = C_exit / Loss
  - p      = probability that the incident materialises over the horizon (the MANAGER judges it);
  - Loss   = loss of the pocket if the incident happens (computed by the engine, in $);
  - C_exit = certain cost of exiting now (exit_cost.py, measured on-chain).

Analogy: insuring your car or not. If the premium (C_exit) costs more than "accident risk ×
damage amount", you do not insure. p* is the accident risk above which insurance
pays off. The manager has only one question left: "do I believe in more than p*?"

Partial exit: we unwind a FRACTION f (sell f of the PT and repay f of the debt; leverage
stays the same, so the loss if the incident happens is proportional to 1 − f). Slippage
grows faster than size: we look for the f minimising  C_exit(f) + p × Loss × (1 − f).
"""
from __future__ import annotations

from .exit_cost import ExitModel
from .fmt import pct, prob, usd

P_GRID = [round(i / 100, 2) for i in range(0, 101)]
F_STEP = 0.05


def p_star(exit_cost_usd: float | None, loss_usd: float) -> float | None:
    """Probability threshold; None if nothing to lose (staying is always better) or exit impossible."""
    if exit_cost_usd is None or loss_usd <= 0:
        return None
    return exit_cost_usd / loss_usd


def best_fraction(exit_model: ExitModel, loss_usd: float, p: float, pool_factor: float = 1.0) -> tuple[float, float]:
    """(optimal fraction to exit, total expected cost) for a probability p."""
    best_f, best_j = 0.0, p * max(loss_usd, 0.0)
    n = int(round(1 / F_STEP))
    for i in range(1, n + 1):
        f = i * F_STEP
        c = exit_model.cost(f, pool_factor)
        if not c["feasible"]:
            break
        j = c["total_usd"] + p * max(loss_usd, 0.0) * (1 - f)
        if j < best_j - 1e-9:
            best_f, best_j = f, j
    return best_f, best_j


def verdict_of(f: float) -> str:
    if f <= 0:
        return "STAY"
    if f >= 0.999:
        return "EXIT"
    return "PARTIAL"


def decision_table(exit_model: ExitModel, loss_usd: float, pool_factor: float = 1.0) -> list[dict]:
    """For each p from 0 to 100%: optimal fraction and verdict (the front only READS this table)."""
    out = []
    for p in P_GRID:
        f, j = best_fraction(exit_model, loss_usd, p, pool_factor)
        out.append({"p": p, "exit_fraction": round(f, 2), "verdict": verdict_of(f), "expected_cost_usd": round(j, 2)})
    return out


def sentence(verdict: str, f: float, pstar: float | None, p: float, loss_usd: float, exit_usd: float | None,
             title: str, horizon_days: float = 7.0) -> str:
    if loss_usd <= 0:
        return f"STAY — \"{title}\" costs the position nothing over the horizon: no reason to pay to exit."
    if exit_usd is None:
        return (f"Full exit IMPOSSIBLE — the pool cannot absorb the sale; \"{title}\" would cost "
                f"{usd(loss_usd)}. Reduce the size to the maximum absorbable.")
    ps = prob(pstar, 1, horizon_days) if pstar is not None else "—"
    if verdict == "STAY":
        return (f"STAY — exiting costs {usd(exit_usd)}; \"{title}\" would cost {usd(loss_usd)}. "
                f"Exit only if you believe there is more than a {ps} chance it happens (you estimate {prob(p, 0, horizon_days)}).")
    if verdict == "EXIT":
        return (f"EXIT — you estimate a {prob(p, 0, horizon_days)} chance, above the threshold p* = {ps}: the expected loss "
                f"({usd(p * loss_usd)}) exceeds the certain exit cost ({usd(exit_usd)}).")
    return (f"PARTIAL {pct(f, 0)} — beyond {pct(f, 0)}, marginal slippage costs more than the loss avoided; "
            f"threshold p* (full exit) = {ps}, you estimate {prob(p, 0, horizon_days)}.")
