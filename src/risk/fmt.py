"""English number formatting for the report sentences ("$5,313", "1.6%")."""
from __future__ import annotations

import math

# Above 20% over the horizon, "1 chance in 5" speaks for itself: no frequency is added.
EVERY_MAX_P = 0.2


def usd(x: float | None) -> str:
    if x is None:
        return "—"
    return ("-" if x < 0 else "") + f"${abs(x):,.0f}"


def num(x: float | None, d: int = 0) -> str:
    if x is None:
        return "—"
    return f"{x:,.{d}f}"


def pct(x: float | None, d: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{d}f}%"


def every(p: float | None, horizon_days: float) -> str:
    """Turns a small probability over the horizon into an average frequency: "≈ once every 19 years".

    A probability p over a horizon of h days matches (Poisson law) an event happening on average
    once every  h / −ln(1 − p)  days. E.g.: 0.10% over 7 days ≈ once every 19 years.
    Empty string if p is zero, missing or already telling (≥ 20%).
    """
    if p is None or not 0 < p < EVERY_MAX_P or horizon_days <= 0:
        return ""
    days = horizon_days / -math.log1p(-p)
    if days < 21:
        return f"≈ once every {round(days)} days"
    if days < 90:
        return f"≈ once every {round(days / 7)} weeks"
    if days < 730:
        return f"≈ once every {round(days / 30.44)} months"
    return f"≈ once every {num(days / 365.25)} years"


def prob(p: float | None, d: int, horizon_days: float) -> str:
    """Readable probability: "0.10% (≈ once every 19 years)"."""
    freq = every(p, horizon_days)
    return pct(p, d) + (f" ({freq})" if freq else "")
