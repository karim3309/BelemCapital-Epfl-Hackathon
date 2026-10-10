"""Mise en forme française des nombres dans les phrases du rapport (« 5 313 $ », « 1,6 % »)."""
from __future__ import annotations


def usd(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:,.0f}".replace(",", " ") + " $"


def num(x: float | None, d: int = 0) -> str:
    if x is None:
        return "—"
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def pct(x: float | None, d: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{d}f}".replace(".", ",") + " %"
