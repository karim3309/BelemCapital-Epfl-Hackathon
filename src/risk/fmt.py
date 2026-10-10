"""Mise en forme française des nombres dans les phrases du rapport (« 5 313 $ », « 1,6 % »)."""
from __future__ import annotations

import math

# Au-delà de 20 % sur l'horizon, « 1 chance sur 5 » se comprend tout seul : on n'ajoute pas de fréquence.
EVERY_MAX_P = 0.2


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


def every(p: float | None, horizon_days: float) -> str:
    """Traduit une petite probabilité sur l'horizon en fréquence moyenne : « ≈ une fois tous les 19 ans ».

    Une probabilité p sur un horizon de h jours correspond (loi de Poisson) à un événement qui arrive en
    moyenne une fois tous les  h / −ln(1 − p)  jours. Ex. : 0,10 % sur 7 jours ≈ une fois tous les 19 ans.
    Chaîne vide si p est nul, absent ou déjà parlant (≥ 20 %).
    """
    if p is None or not 0 < p < EVERY_MAX_P or horizon_days <= 0:
        return ""
    days = horizon_days / -math.log1p(-p)
    if days < 21:
        return f"≈ une fois tous les {round(days)} jours"
    if days < 90:
        return f"≈ une fois toutes les {round(days / 7)} semaines"
    if days < 730:
        return f"≈ une fois tous les {round(days / 30.44)} mois"
    return f"≈ une fois tous les {num(days / 365.25)} ans"


def prob(p: float | None, d: int, horizon_days: float) -> str:
    """Probabilité lisible : « 0,10 % (≈ une fois tous les 19 ans) »."""
    freq = every(p, horizon_days)
    return pct(p, d) + (f" ({freq})" if freq else "")
