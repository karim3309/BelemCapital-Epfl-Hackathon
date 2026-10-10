"""Décision : rester (STAY), sortir en partie (PARTIAL x %), ou tout sortir (EXIT) — et POURQUOI.

La règle du brief / cadrage (§4.4) :
    Sortir si   p × Perte  >  C_exit        ⇔        p  >  p* = C_exit / Perte
  - p      = probabilité que l'incident se matérialise sur l'horizon (c'est le MANAGER qui la juge) ;
  - Perte  = perte de la poche si l'incident arrive (calculée par le moteur, en $) ;
  - C_exit = coût certain de sortir maintenant (exit_cost.py, mesuré on-chain).

Analogie : assurer ou pas sa voiture. Si la prime (C_exit) coûte plus que « risque d'accident ×
montant des dégâts », on ne s'assure pas. p* est le risque d'accident à partir duquel l'assurance
devient rentable. Le manager n'a plus qu'une question à se poser : « est-ce que je crois à plus de p* ? »

Sortie partielle : on déboucle une FRACTION f (on vend f du PT et on rembourse f de la dette ; le
levier reste le même, donc la perte en cas d'incident est proportionnelle à 1 − f). Le glissement
croît plus vite que la taille : on cherche le f qui minimise  C_exit(f) + p × Perte × (1 − f).
"""
from __future__ import annotations

from .exit_cost import ExitModel
from .fmt import pct, usd

P_GRID = [round(i / 100, 2) for i in range(0, 101)]
F_STEP = 0.05


def p_star(exit_cost_usd: float | None, loss_usd: float) -> float | None:
    """Seuil de probabilité ; None si rien à perdre (rester est toujours mieux) ou sortie impossible."""
    if exit_cost_usd is None or loss_usd <= 0:
        return None
    return exit_cost_usd / loss_usd


def best_fraction(exit_model: ExitModel, loss_usd: float, p: float, pool_factor: float = 1.0) -> tuple[float, float]:
    """(fraction optimale à sortir, coût total attendu) pour une probabilité p."""
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
    """Pour chaque p de 0 à 100 % : fraction optimale et verdict (le front ne fait que LIRE ce tableau)."""
    out = []
    for p in P_GRID:
        f, j = best_fraction(exit_model, loss_usd, p, pool_factor)
        out.append({"p": p, "exit_fraction": round(f, 2), "verdict": verdict_of(f), "expected_cost_usd": round(j, 2)})
    return out


def sentence(verdict: str, f: float, pstar: float | None, p: float, loss_usd: float, exit_usd: float | None,
             title: str) -> str:
    if loss_usd <= 0:
        return f"STAY — « {title} » ne coûte rien à la position sur l'horizon : aucune raison de payer pour sortir."
    if exit_usd is None:
        return (f"Sortie IMPOSSIBLE en entier — le pool ne peut pas absorber la vente ; « {title} » coûterait "
                f"{usd(loss_usd)}. Réduire la taille au maximum absorbable.")
    ps = f"{pct(pstar, 1)}" if pstar is not None else "—"
    if verdict == "STAY":
        return (f"STAY — sortir coûte {usd(exit_usd)} ; « {title} » coûterait {usd(loss_usd)}. "
                f"Sortez seulement si vous croyez à plus de {ps} de chances que ça arrive (vous estimez {pct(p, 0)}).")
    if verdict == "EXIT":
        return (f"EXIT — vous estimez {pct(p, 0)} de chances, au-dessus du seuil p* = {ps} : la perte attendue "
                f"({usd(p * loss_usd)}) dépasse le coût certain de sortie ({usd(exit_usd)}).")
    return (f"PARTIAL {pct(f, 0)} — au-delà de {pct(f, 0)}, le glissement marginal coûte plus que la perte évitée ; "
            f"seuil p* (sortie totale) = {ps}, vous estimez {pct(p, 0)}.")
