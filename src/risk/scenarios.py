"""Scénarios de stress : un incident défini dans risk/scenarios.yaml → son effet complet sur la position.

Pour chaque scénario, le moteur enchaîne toujours les mêmes étapes (c'est ça qui le rend auditable) :
  1. propagate      : le choc remonte le graphe (règle par type d'arête) ;
  2. oracle_sim     : quel prix l'oracle du marché affiche pendant le choc (bascule ou non) ;
  3. position       : nouveau HF, liquidation ou non, perte de l'emprunteur et des prêteurs ;
  4. exit_cost      : coût certain de sortir maintenant (dans l'état de liquidité du scénario) ;
  5. decide         : seuil p*, sortie partielle optimale, verdict et phrase d'explication ;
  6. contagion      : le(s) chemin(s) du graphe par lequel le choc atteint la position, avec preuves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import decide
from .exit_cost import ExitModel
from .graphview import GraphView
from .oracle_sim import evaluate as evaluate_oracle
from .params import ParamError, Params
from .position import Baseline, evaluate_position
from .propagate import Shock, World, contagion_paths, propagate


@dataclass
class Engine:
    gv: GraphView
    inputs: dict
    params: Params
    exit_model: ExitModel
    base: Baseline

    @property
    def horizon_days(self) -> float:
        return self.params["horizon_days"]

    # ------------------------------------------------------------------ cœur
    def run(self, shocks: list[Shock], ts_offset_days: float = 0.0) -> tuple[World, object, dict]:
        world = propagate(self.gv, shocks, self.params)
        oracle = evaluate_oracle(self.gv, self.gv.market_oracle_id(), world, self.params, ts_offset_days * 86400)
        outcome = evaluate_position(self.gv, self.base, world, oracle, self.params, self.exit_model,
                                    self.horizon_days, ts_offset_days)
        return world, oracle, outcome

    def decision(self, loss_usd: float, pool_factor: float, p: float, title: str) -> dict:
        full = self.exit_model.cost(1.0, pool_factor)
        exit_usd = full["total_usd"] if full["feasible"] else None
        pstar = decide.p_star(exit_usd, loss_usd)
        f, _ = decide.best_fraction(self.exit_model, loss_usd, p, pool_factor)
        v = decide.verdict_of(f)
        return {
            "exit_cost_full": full, "p_star": pstar, "p_default": p,
            "verdict": v, "exit_fraction": round(f, 2),
            "sentence": decide.sentence(v, f, pstar, p, loss_usd, exit_usd, title, self.horizon_days),
            "table": decide.decision_table(self.exit_model, loss_usd, pool_factor),
        }


def expand_shocks(gv: GraphView, specs: list[dict]) -> list[Shock]:
    shocks = []
    for s in specs:
        nodes = [s["node"]] if "node" in s else gv.select(s["select"])
        if not nodes:
            raise ParamError(f"scénario : aucun nœud ne correspond à {s}")
        for n in nodes:
            shocks.append(Shock(node=n, kind=s["kind"], severity=float(s.get("severity", 0.0)),
                                duration_hours=s.get("duration_hours"), panic=float(s.get("panic", 0.0))))
    return shocks


def load_scenarios(path: str | Path) -> dict:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for sc in raw["scenarios"]:
        for k in ("id", "title", "why", "p_default", "shocks"):
            if k not in sc:
                raise ParamError(f"scénario {sc.get('id')}: champ `{k}` obligatoire")
        pd = sc["p_default"]
        if not (pd.get("hypothesis") and pd.get("why")):
            raise ParamError(f"scénario {sc['id']}: p_default doit être une hypothèse justifiée")
    return raw


def evaluate_scenario(engine: Engine, sc: dict) -> dict:
    gv = engine.gv
    shocks = expand_shocks(gv, sc["shocks"])
    offset = 0.0
    if sc.get("time_offset") == "to_maturity":
        offset = gv.meta(gv.collateral_id()).get("days_to_expiry") or 0.0
    world, oracle, out = engine.run(shocks, offset)
    pool_factor = min(world.pool_factor.values(), default=1.0)
    dec = engine.decision(out["borrower_loss_usd"], pool_factor, sc["p_default"]["value"], sc["title"])
    paths = []
    for s in shocks:
        for p in contagion_paths(gv, s.node, max_paths=2):
            paths.append({"shocked_node": s.node, **p})
    used = scenario_params_used(sc, shocks, world, oracle, out)
    hyp = [u for u in used if engine.params.items.get(u) and engine.params.items[u].status == "hypothesis"]
    return {
        "id": sc["id"], "family": sc.get("family"), "title": sc["title"], "story": sc.get("story", ""),
        "why": sc["why"], "shocks": [s.to_dict() for s in shocks], "time_offset_days": offset,
        "propagation_trace": world.trace, "asset_multipliers": world.asset_mult,
        "oracle": oracle.to_dict(), "outcome": out, "decision": dec, "contagion_paths": paths,
        "params_used": used,
        "confidence": confidence_label(hyp, sc),
    }


def scenario_params_used(sc: dict, shocks: list[Shock], world: World, oracle, out: dict) -> list[str]:
    used = ["horizon_days", "unwind_gas_units", "second_leg_cost_rate", "carry_pt_implied_apy", "carry_borrow_apy",
            "exit_pendle_leg"]
    if oracle.kind == "morpho_meta_oracle_deviation_timelock":
        used += ["meta_oracle_deviation_formula", "meta_oracle_deviation_threshold",
                 "meta_oracle_challenge_timelock_seconds", "meta_oracle_healing_timelock_seconds", "challenger_delay_hours"]
    if out["liquidatable"]:
        used += ["morpho_lif_beta", "morpho_lif_max", "liquidation_repaid_fraction", "liquidator_requires_profit"]
    kinds = {s.kind for s in shocks}
    if "counterparty_failure" in kinds:
        used += ["custodian_backing_share", "exchange_exposure_share"]
    if any(m < 1 for m in world.asset_mult.values()):
        used.append("pt_extra_amm_discount_under_stress")
    if world.pool_factor:
        used.append("stressed_pool_scaling")
    return list(dict.fromkeys(used))


def confidence_label(hypotheses: list[str], sc: dict) -> dict:
    """Niveau de confiance lisible : combien d'hypothèses entrent dans le chiffre ?"""
    n = len(hypotheses)
    level = "élevée" if n <= 3 else ("moyenne" if n <= 6 else "faible")
    return {"level": level, "hypotheses_in_number": hypotheses,
            "note": ("La taille et la durée du choc sont un CHOIX de scénario ; le reste vient de la chaîne "
                     "ou de docs officielles sauf les hypothèses listées.")}


def evaluate_usde_grid(engine: Engine, grid: dict) -> dict:
    """Grille prix USDe × durée pour le curseur du front (toutes les cellules calculées en Python)."""
    gv = engine.gv
    usde = gv.feed_priced_asset(next(n["id"] for n in gv.of_type("oracle")
                                     if n["meta"].get("oracle_kind") == "chainlink_aggregator_proxy"))
    usde_now = gv.meta(usde).get("price_usd") or 1.0
    p = grid["p_default"]["value"]
    cells = []
    for price in grid["prices"]:
        row = []
        for dur in grid["durations_hours"]:
            sev = max(0.0, min(1.0, 1 - price / usde_now))
            shocks = [Shock(node=usde, kind="market_depeg", severity=sev, duration_hours=dur)] if sev > 0 else []
            world, oracle, out = engine.run(shocks)
            dec = engine.decision(out["borrower_loss_usd"], 1.0, p, f"USDe à {price} $ pendant {dur or '∞'} h")
            state = ("switched" if oracle.switched else "challenge" if oracle.challenge_possible else "primary")
            row.append({
                "usde_price": price, "duration_hours": dur, "severity": round(sev, 6),
                "oracle_state": state, "oracle_price": oracle.price, "deviation": oracle.deviation,
                "hf": out["hf_after"], "liquidated": out["liquidated"], "liquidatable": out["liquidatable"],
                "borrower_loss_usd": round(out["borrower_loss_usd"], 2),
                "lender_loss_usd": round(out["lender_loss_usd"], 2),
                "who_loses": out["who_loses"], "p_star": dec["p_star"],
                "verdict_default": dec["verdict"], "exit_fraction_default": dec["exit_fraction"],
                "fraction_by_p": [t["exit_fraction"] for t in dec["table"]],
                "sentence": dec["sentence"],
                "status": ("LIQUIDÉ" if out["liquidated"] else
                           "prêteurs exposés" if out["lender_loss_usd"] > 1 else "pas liquidé"),
            })
        cells.append(row)
    return {"usde_node": usde, "usde_price_now": usde_now, "prices": grid["prices"],
            "durations_hours": grid["durations_hours"], "p_grid": decide.P_GRID, "cells": cells,
            "why": grid["why"]}
