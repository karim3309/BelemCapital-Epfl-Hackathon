"""Point d'entrée du moteur de risque : graph.json + risk_inputs.json → risk_report.json + risk_grid.json.

    PYTHONPATH=src python -m risk.run            # 100 % hors ligne (aucun appel réseau)

Ce que produit le rapport (c'est la « fiche de risque » du cadrage §4.5) :
  - le verdict principal STAY / PARTIAL x % / EXIT, en une phrase, avec le seuil p* ;
  - la perte attendue, la VaR 95 %, le coût de sortie ($ et % du capital) ;
  - les 3 chemins de contagion les plus coûteux (avec les preuves des arêtes) ;
  - tous les scénarios de stress, le replay d'incidents réels, la sensibilité aux hypothèses ;
  - la liste des paramètres avec leur statut (sourcé / on-chain / hypothèse) et un niveau de confiance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from discovery.config import REPO_ROOT
from discovery.console import utf8_console

from .calibrate import calibrate
from .exit_cost import ExitModel
from .graphview import GraphView
from .montecarlo import run_mc
from .params import load_params
from .position import Baseline, lif
from .replay import run_replays
from .scenarios import Engine, evaluate_scenario, evaluate_usde_grid, load_scenarios
from .fmt import pct, usd

GRAPH = REPO_ROOT / "output" / "graph.json"
INPUTS = REPO_ROOT / "output" / "risk_inputs.json"
PARAMS = REPO_ROOT / "risk" / "params.yaml"
SCENARIOS = REPO_ROOT / "risk" / "scenarios.yaml"
REPLAYS = REPO_ROOT / "risk" / "replays.yaml"
REPORT = REPO_ROOT / "output" / "risk_report.json"
GRID = REPO_ROOT / "output" / "risk_grid.json"
HEADLINE = "S-USDe-30"


def build_engine(graph_path: Path = GRAPH, inputs_path: Path = INPUTS, params_path: Path = PARAMS) -> Engine:
    gv = GraphView.load(graph_path)
    inputs = json.loads(Path(inputs_path).read_text(encoding="utf-8"))
    if inputs.get("snapshot_block") != gv.snapshot()["block"]:
        raise ValueError(f"risk_inputs.json (bloc {inputs.get('snapshot_block')}) ≠ graph.json (bloc "
                         f"{gv.snapshot()['block']}) : relancez `python -m risk.refresh`")
    calibrate(inputs, gv.snapshot()["timestamp"])
    params = load_params(params_path, gv, inputs)
    exit_model = ExitModel.build(gv, inputs, params)
    return Engine(gv=gv, inputs=inputs, params=params, exit_model=exit_model, base=Baseline.build(gv, exit_model))


def sensitivity(engine: Engine, headline: dict, sc_def: dict, mc_samples: int) -> list[dict]:
    """Tornade : on fait varier chaque hypothèse dans sa plage et on regarde ce qui bouge."""
    from .scenarios import evaluate_scenario as ev_sc
    base_el = run_mc(engine, samples=mc_samples, with_paths=False)["expected_loss_usd"]
    rows = []
    hypo = [p for p in engine.params.items.values()
            if p.status == "hypothesis" and p.range and isinstance(p.value, (int, float)) and not isinstance(p.value, bool)]
    for prm in hypo:
        lo, hi = prm.range
        res = {"param": prm.name, "base": prm.value, "low": lo, "high": hi}
        for tag, val in (("low", lo), ("high", hi)):
            eng = Engine(gv=engine.gv, inputs=engine.inputs, params=engine.params.with_overrides({prm.name: val}),
                         exit_model=None, base=engine.base)
            eng.exit_model = ExitModel.build(engine.gv, engine.inputs, eng.params)
            sc = ev_sc(eng, sc_def)
            res[f"headline_loss_{tag}"] = sc["outcome"]["borrower_loss_usd"]
            res[f"headline_p_star_{tag}"] = sc["decision"]["p_star"]
            res[f"el_{tag}"] = run_mc(eng, samples=mc_samples, with_paths=False)["expected_loss_usd"]
        rows.append(res)
    for name in engine.params.events:          # fréquences annuelles ×0,5 / ×2
        if engine.params.events[name]["annual_rate"].status != "hypothesis":
            continue
        res = {"param": f"{name}.annual_rate", "base": engine.params.events[name]["annual_rate"].value,
               "low": "×0,5", "high": "×2",
               "headline_loss_low": headline["outcome"]["borrower_loss_usd"],
               "headline_loss_high": headline["outcome"]["borrower_loss_usd"],
               "headline_p_star_low": headline["decision"]["p_star"], "headline_p_star_high": headline["decision"]["p_star"]}
        res["el_low"] = run_mc(engine, samples=mc_samples, rate_scale={name: 0.5}, with_paths=False)["expected_loss_usd"]
        res["el_high"] = run_mc(engine, samples=mc_samples, rate_scale={name: 2.0}, with_paths=False)["expected_loss_usd"]
        rows.append(res)
    for r in rows:
        r["el_base"] = base_el
        r["el_swing"] = abs(r["el_high"] - r["el_low"])
    rows.sort(key=lambda r: -r["el_swing"])
    return rows


def build_report(engine: Engine, mc_samples: int | None = None, sens_samples: int = 40000) -> tuple[dict, dict]:
    gv = engine.gv
    sc_raw = load_scenarios(SCENARIOS)
    scenarios = [evaluate_scenario(engine, sc) for sc in sc_raw["scenarios"]]
    by_id = {s["id"]: s for s in scenarios}
    headline = by_id[HEADLINE]
    headline_def = next(s for s in sc_raw["scenarios"] if s["id"] == HEADLINE)
    mc = run_mc(engine, samples=mc_samples)
    grid = evaluate_usde_grid(engine, sc_raw["usde_grid"])
    replays = run_replays(engine, REPLAYS)
    sens = sensitivity(engine, headline, headline_def, sens_samples)

    exit_full = engine.exit_model.cost(1.0)
    eq = engine.base.equity_usd
    baseline_loss = mc["expected_loss_usd"]
    base_verdict = "STAY" if baseline_loss < (exit_full["total_usd"] or 0) else "EXIT"
    market = gv.meta(gv.market_id())
    report = {
        "contract_version": 1,
        "generated_from": {"graph": "output/graph.json", "inputs": "output/risk_inputs.json",
                           "params": "risk/params.yaml", "scenarios": "risk/scenarios.yaml",
                           "replays": "risk/replays.yaml"},
        "snapshot": gv.snapshot(),
        "position": {
            "id": gv.position_id, "market": gv.market_id(), "collateral": gv.collateral_id(), "loan": gv.loan_id(),
            "oracle": gv.market_oracle_id(), "exit_venue": gv.exit_venue_id(),
            "collateral_pt": engine.base.collateral, "debt_usdc": engine.base.debt,
            "pt_market_usd": engine.base.pt_usd, "oracle_price": engine.base.oracle_price,
            "gross_value_usd": engine.base.collateral * engine.base.pt_usd,
            "equity_usd": eq, "value_usd_contract": gv.raw["position"]["value_usd"],
            "health_factor": engine.base.hf, "ltv": market["position"]["ltv"], "lltv": engine.base.lltv,
            "lif": lif(engine.base.lltv, engine.params), "borrow_apy": engine.base.borrow_apy,
            "oracle_drop_to_liquidation": 1 - 1 / engine.base.hf,
            "pocket_definition": "V = capital net (valeur de marché du collatéral − dette) : c'est ce que le manager récupère en sortant",
        },
        "headline": {
            "scenario": HEADLINE, "title": headline["title"],
            "verdict": headline["decision"]["verdict"], "exit_fraction": headline["decision"]["exit_fraction"],
            "p_star": headline["decision"]["p_star"], "p_default": headline["decision"]["p_default"],
            "loss_if_incident_usd": headline["outcome"]["borrower_loss_usd"],
            "loss_if_incident_pct_equity": headline["outcome"]["lgi"],
            "lender_loss_usd": headline["outcome"]["lender_loss_usd"],
            "exit_cost_usd": exit_full["total_usd"], "exit_cost_pct_equity": (exit_full["total_usd"] or 0) / eq,
            "sentence": headline["decision"]["sentence"],
            "three_am_question": (f"Est-ce que je crois à plus de {pct(headline['decision']['p_star'], 1)} de chances que "
                                  f"« {headline['title']} » se produise d'ici {engine.horizon_days:g} jours ?"
                                  if headline["decision"]["p_star"] is not None else None),
        },
        "baseline": {
            "verdict": base_verdict,
            "sentence": (f"{base_verdict} — sans alerte, la perte attendue sur {engine.horizon_days:g} jours "
                         f"({usd(baseline_loss)}) est {'inférieure' if base_verdict == 'STAY' else 'supérieure'} "
                         f"au coût certain de sortie ({usd(exit_full['total_usd'])})."),
        },
        "exit_cost": {
            "full": exit_full,
            "curves": {str(k): engine.exit_model.curve(k) for k in (1.0, 0.5, 0.1)},
            "max_feasible_pt": engine.exit_model.max_feasible_pt,
            "first_reverted_pt": engine.exit_model.min_reverted_pt,
            "simulations_evidence": engine.exit_model.evidence,
            "method": ("PT → SY simulé on-chain (Pendle RouterStatic.swapExactPtForSyStatic) ; coût = écart au prix "
                       "spot de l'AMM ; + conversion vers USDC (hypothèse) + gas (on-chain) + rendement abandonné"),
        },
        "monte_carlo": mc,
        "scenarios": scenarios,
        "replays": replays,
        "sensitivity": sens,
        "calibration": engine.inputs["calibration"],
        "params": [p.to_dict() for p in engine.params.all_params()],
        "confidence": {
            "p_star": "moyenne à élevée : coût de sortie mesuré on-chain, perte calculée sur le graphe prouvé ; "
                      "seules la taille/durée du choc et quelques paramètres de transmission sont des hypothèses",
            "expected_loss_and_var": "faible : la plupart des fréquences annuelles sont des hypothèses d'ordre de "
                                     "grandeur (le dataset de hacks DeFiLlama est payant) — voir la sensibilité",
        },
    }
    return report, grid


def _fmt_pct(x):
    return "—" if x is None else f"{pct(x, 1)}"


def print_summary(report: dict, elapsed: float) -> None:
    h, pos, mc = report["headline"], report["position"], report["monte_carlo"]
    print(f"\n=== StackTrace · fiche de risque · bloc #{report['snapshot']['block']} ===")
    print(f"position : HF {pos['health_factor']:.3f} · capital net {usd(pos['equity_usd'])} · "
          f"liquidable si l'oracle baisse de {pct(pos['oracle_drop_to_liquidation'], 2)}")
    print(f"sortie   : {usd(h['exit_cost_usd'])} ({pct(h['exit_cost_pct_equity'], 2)} du capital)")
    print(f"alerte   : {h['title']} → perte {usd(h['loss_if_incident_usd'])} ; p* = {_fmt_pct(h['p_star'])}")
    print(f"verdict  : {h['sentence']}")
    print(f"sans alerte ({mc['horizon_days']:g} j, {mc['samples']:,} tirages) : perte attendue {usd(mc['expected_loss_usd'])} · "
          f"VaR95 {usd(mc['var95_usd'])} · VaR99 {usd(mc['var99_usd'])} → {report['baseline']['verdict']}")
    print("scénarios :")
    for s in report["scenarios"]:
        o, d = s["outcome"], s["decision"]
        print(f"   · {s['id']:<18} HF {o['hf_before']:.3f}→{o['hf_after']:.3f} "
              f"{'LIQUIDÉ' if o['liquidated'] else ('liquidable' if o['liquidatable'] else 'ok'):<10} emprunteur −{o['borrower_loss_usd']:>10,.0f} $  "
              f"prêteurs −{o['lender_loss_usd']:>9,.0f} $  p*={_fmt_pct(d['p_star']):>7}  {d['verdict']}")
    for r in report["replays"]:
        if r.get("available"):
            print(f"replay   : {r['title']}")
            for d in r["designs"]:
                print(f"   · {d['design']:<52} HF min {d['min_hf']:.3f} {'LIQUIDÉ' if d['liquidated'] else 'ok'}")
    print(f"({elapsed:.1f} s)")


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description="Moteur de risque StackTrace")
    ap.add_argument("--samples", type=int, default=None, help="tirages Monte Carlo (défaut : params.yaml)")
    ap.add_argument("--offline", action="store_true", help="(sans effet : le moteur n'appelle jamais le réseau)")
    args = ap.parse_args(argv)
    t0 = time.time()
    engine = build_engine()
    report, grid = build_report(engine, mc_samples=args.samples)
    from .validate_report import validate_report
    errors = validate_report(report, grid, engine.gv)
    if errors:
        print(f"✗ {len(errors)} erreur(s) dans le rapport :", *errors, sep="\n  - ")
        return 1
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    GRID.write_text(json.dumps(grid, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    print_summary(report, time.time() - t0)
    print(f"✓ {REPORT.relative_to(REPO_ROOT)} et {GRID.relative_to(REPO_ROOT)} valides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
