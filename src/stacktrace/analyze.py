"""Étape 5 — pour un détenteur réel : chaque poche → graphe → incidents → pertes → coût de sortie → STAY / EXIT.

    PYTHONPATH=src python -m stacktrace.analyze 0xDétenteur                       # tout le portefeuille
    PYTHONPATH=src python -m stacktrace.analyze 0xDétenteur --pocket "Belem RWA"  # une poche
    PYTHONPATH=src python -m stacktrace.analyze 0xDétenteur --pocket "Belem RWA" --list-incidents
    PYTHONPATH=src python -m stacktrace.analyze 0xDétenteur --pocket "Belem RWA" --incident rwa_credit_event:mgloeuro --severity 0.3 --p 0.2

LA RÈGLE DE DÉCISION (brief Belem + cadrage §4.4)
    Rester coûte une perte INCERTAINE, sortir coûte un montant CERTAIN.
    On choisit la fraction f à sortir maintenant qui minimise   coût_sortie(f) + perte_attendue × (1 − f)
    avec f ≤ f_max (ce qui est sortable tout de suite).  f* > 0 → EXIT (f*),  sinon STAY.
    Pour un incident donné :  p* = coût_sortie / perte_si_incident  — « sortez si vous croyez à plus de p* ».
    p* ne dépend PAS de nos probabilités (hypothèses) : seulement de la perte et du coût, qui sont mesurés.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict

import numpy as np

from discovery.config import REPO_ROOT
from discovery.console import utf8_console
from risk.fmt import every

from .exit_cost import ExitModel, borrow_exit, vault_exit
from .graph_build import build_position_graph, pick
from .market_data import G, load_markets
from .params import load_params
from .portfolio import OUTPUT_DIR, Holding, scan_holder
from .risk_engine import BorrowPocket, Event, VaultPocket, borrow_events, monte_carlo, vault_events

F_STEP = 0.05


# ----------------------------------------------------------------------------- décision
def best_fraction(exit_m: ExitModel, loss_usd: float) -> tuple[float, float]:
    grid = sorted(set([round(x, 4) for x in np.arange(0, exit_m.f_max + 1e-9, F_STEP)] + [round(exit_m.f_max, 4)]))
    best = (0.0, loss_usd)
    for f in grid:
        j = exit_m.cost(f) + loss_usd * (1 - f)
        if j < best[1] - 1e-6:
            best = (f, j)
    return best


def p_star(exit_m: ExitModel, lgi_usd: float) -> float | None:
    """Probabilité au-delà de laquelle sortir (f_max) coûte moins que rester."""
    f = exit_m.f_max
    if f <= 0 or lgi_usd <= 0:
        return None
    return min(exit_m.cost(f) / (f * lgi_usd), 1.0)


def usd(x: float) -> str:
    return f"{x:,.0f} $".replace(",", " ")


def pct(x: float | None, d: int = 1) -> str:
    return "—" if x is None else f"{x * 100:.{d}f} %".replace(".", ",")


def prob(x: float | None, d: int, days: float) -> str:
    """Probabilité sur l'horizon + fréquence parlante : « 0,10 % (≈ une fois tous les 20 ans) »."""
    freq = every(x, days)
    return pct(x, d) + (f" ({freq})" if freq else "")


def soit(x: float | None, days: float) -> str:
    """Fréquence à glisser DANS une parenthèse : « , soit ≈ une fois tous les 20 ans »."""
    freq = every(x, days)
    return f", soit {freq}" if freq else ""


def verdict_sentence(v: str, f: float, f_max: float, el: float, exit_cost: float, top: dict | None,
                     days: float = 7.0) -> str:
    """Compare ce que la sortie ÉVITE (perte attendue × part sortable) à ce qu'elle COÛTE."""
    if v == "STAY":
        avoided = el * f_max
        scope = "" if f_max >= 0.999 else f" (seuls {pct(f_max, 0)} sont sortables maintenant)"
        s = (f"STAY — sortir{scope} éviterait {usd(avoided)} de perte attendue sur l'horizon, "
             f"mais coûterait {usd(exit_cost)}.")
        if top and top.get("p_star") is not None and top["p_star"] < 1:
            s += (f" Sortez si vous estimez à plus de {prob(top['p_star'], 1, days)} le risque « {top['title']} » "
                  f"(notre estimation : {pct(top['p_horizon'], 2)}{soit(top['p_horizon'], days)}).")
        elif top and top.get("p_star") is not None:
            s += f" Même certain, « {top['title']} » coûterait moins que la sortie : rester est toujours mieux."
        elif f_max <= 0:
            s += " Sortie impossible par le marché maintenant (aucune liquidité / glissement excessif)."
        return s
    part = "" if f >= 0.999 else f" {pct(f, 0)} de la poche (maximum sortable maintenant : {pct(f_max, 0)})"
    return (f"EXIT{part} — la perte attendue évitée ({usd(el * f)}) dépasse le coût de sortie ({usd(exit_cost)})"
            + (f" ; risque principal : « {top['title']} »." if top else "."))


def path_text(g: G, target: str) -> str:
    path = g.path_to(target)
    if not path:
        return "(hors du chemin direct)"
    return " → ".join([g.raw["position"]["id"][:18] + "…"] + [f"[{e['type']}] {g.nodes[e['to']]['label']}" for e in path])


# ----------------------------------------------------------------------------- une poche
def analyze_pocket(s, h: Holding, holder: str, p, days: float, incident: str | None = None,
                   severity: float | None = None, p_incident: float | None = None) -> dict:
    graph, _ = build_position_graph(s, h, holder)
    g = G(graph)
    markets = load_markets(s.ctx, g)
    unit_usd = h.price_usd or 1.0

    if h.kind.startswith("morpho_vault"):
        vnode = g.first("vault")
        vm = vnode["meta"]
        alloc = {a["market_id"]: a for a in vm["allocations"]}
        for mk in markets:
            mk.our_supply = alloc.get(mk.market_id, {}).get("supplied", 0.0)
        curator = next((n["id"] for n in graph["nodes"] if n["meta"].get("role") == "vault_curator"), None)
        pocket = VaultPocket(h.label, h.value_usd or 0, h.amount, unit_usd, vm["holder_share_of_vault"],
                             g.by_address[vm["asset"]], markets, vm["exit_liquidity"]["covers_holder_share"] or 0.0,
                             max((a["force_deallocate_penalty"] or 0) for a in vm["adapters"]), vnode["id"], curator)
        events = vault_events(g, pocket, p)
        placed = sum(m.our_supply for m in markets)
        apy = sum(m.our_supply * (m.supply_apy or 0) for m in markets) / placed if placed else None
        exit_m = vault_exit(s.ctx, p, pocket.value_usd, pocket.exit_fraction_now, apy, pocket.force_penalty, days,
                            vm["exit_liquidity"].get("covers_holder_share_penalty_free") or 0.0)
        cap = pocket.value_usd
    else:
        mk = markets[0]
        pos = g.nodes[mk.node_id]["meta"]["position"]
        bp = BorrowPocket(h.label, h.value_usd or 0, unit_usd, mk, pos["collateral_value_in_loan_token"],
                          pos["borrow_human"], pos["health_factor"])
        events = borrow_events(g, bp, p)
        loan_id = next(e["to"] for e in g.out(mk.node_id, "lends"))
        exit_m = borrow_exit(s.ctx, p, g, bp.value_usd, unit_usd, bp.debt, mk.price, mk.collateral_id, loan_id, days)
        cap = bp.equity * unit_usd

    for e in events:
        e.tabulate()
    mc = monte_carlo(events, cap, days, p)
    el = mc["expected_loss_usd"]
    rows = []
    for e in events:
        ph = e.p_horizon(days)
        rows.append({"id": e.id, "title": e.title, "family": e.family, "target": e.target,
                     "annual_rate": e.annual_rate * e.weight, "p_horizon": ph,
                     "severity_range": [e.sev_lo, e.sev_hi], "loss_if_incident_usd": e.lgi_usd,
                     "loss_if_incident_max_usd": float(e.losses.max()), "expected_loss_usd": ph * e.lgi_usd,
                     "p_star": p_star(exit_m, e.lgi_usd), "rule": e.rule, "contagion_path": path_text(g, e.target)})
    rows.sort(key=lambda r: -r["expected_loss_usd"])

    f, _ = best_fraction(exit_m, el)
    verdict = "EXIT" if f > 0 else "STAY"
    top = next((r for r in rows if r["loss_if_incident_usd"] > 0), None)
    report = {
        "pocket": {"id": h.id, "kind": h.kind, "label": h.label, "value_usd": h.value_usd, "share_of_book": h.share_of_book},
        "graph": {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "position_id": graph["position"]["id"]},
        "markets": [{"label": m.label, "collateral_pricing": m.collateral_mode, "collateral_class": m.collateral_class,
                     "lltv": m.lltv, "utilization": (m.borrow / m.supply) if m.supply else None, "liquidity": m.liquidity,
                     "our_supply": m.our_supply, "borrowers": int(len(m.debts)), "borrowers_source": m.borrowers_source}
                    for m in markets],
        "monte_carlo": mc,
        "exit": {"f_max_now": exit_m.f_max, "cost_full_usd": exit_m.cost(max(exit_m.f_max, 1e-9)),
                 "cost_full_pct": exit_m.cost(max(exit_m.f_max, 1e-9)) / (h.value_usd or 1), **exit_m.detail},
        "decision": {"verdict": verdict, "exit_fraction": f,
                     "sentence": verdict_sentence(verdict, f, exit_m.f_max, el,
                                                  exit_m.cost(f if f > 0 else max(exit_m.f_max, 1e-9)), top, days)},
        "incidents": rows,
    }

    report["_graph"], report["_events"], report["_exit"], report["_holding"] = graph, events, exit_m, h
    if incident:
        report["incident_mode"] = incident_decision(report, p, incident, severity, p_incident)
    return report


class UnknownIncident(LookupError):
    pass


def incident_decision(report: dict, p, incident: str, severity: float | None = None,
                      p_incident: float | None = None) -> dict:
    """Mode incident : réutilise les incidents et le coût de sortie DÉJÀ calculés (aucun nouvel appel réseau)."""
    events, exit_m, h = report["_events"], report["_exit"], report["_holding"]
    g = G(report["_graph"])
    ev = next((e for e in events if e.id.lower().startswith(incident.lower())), None)
    if ev is None:
        raise UnknownIncident(incident)
    sev = severity if severity is not None else (ev.sev_lo + ev.sev_hi) / 2
    lgi = max(0.0, ev.loss_fn(sev))
    pi = p_incident if p_incident is not None else p["incident_p_default"]
    fi, _ = best_fraction(exit_m, pi * lgi)
    ps = p_star(exit_m, lgi)
    vi = "EXIT" if fi > 0 else "STAY"
    return {
        "incident": ev.id, "title": ev.title, "severity": sev, "loss_if_incident_usd": lgi,
        "loss_if_incident_pct": lgi / (h.value_usd or 1), "p_used": pi,
        "p_source": "manager" if p_incident is not None else "hypothèse par défaut (params_v2.yaml)",
        "p_star": ps, "verdict": vi, "exit_fraction": fi, "rule": ev.rule, "contagion_path": path_text(g, ev.target),
        "contagion_edges": g.path_to(ev.target),
        "sentence": (f"{vi}{'' if fi in (0, 1) else f' {pct(fi, 0)}'} — si « {ev.title} » (sévérité {pct(sev, 0)}) se produit, "
                     f"la poche perd {usd(lgi)} ({pct(lgi / (h.value_usd or 1))}). Sortir maintenant coûte "
                     f"{usd(exit_m.cost(max(exit_m.f_max, 1e-9)))}"
                     + (f" et ne couvre que {pct(exit_m.f_max, 0)} de la poche" if exit_m.f_max < 0.999 else "")
                     + (f". Seuil : sortez si vous croyez à plus de {prob(ps, 1, report['monte_carlo']['horizon_days'])} "
                        "de chances." if ps is not None
                        else ". Sortie impossible maintenant (aucune liquidité).")),
    }


def public(report: dict) -> dict:
    """Le rapport sans les objets internes (clés « _… ») : ce qui part en JSON."""
    return {k: v for k, v in report.items() if not k.startswith("_")}


# ----------------------------------------------------------------------------- portefeuille
def shared_dependencies(reports: list[dict]) -> list[dict]:
    """Dépendances communes à plusieurs poches (même adresse) : la concentration cachée du portefeuille."""
    seen = defaultdict(lambda: {"label": None, "type": None, "pockets": set(), "value_usd": 0.0})
    for r in reports:
        for n in r["_graph"]["nodes"]:
            # un marché Morpho a l'adresse du contrat unique : on l'identifie par son marketId
            key = n["meta"].get("market_id") if n["type"] == "lending_market" else (n.get("address") or n["id"])
            if n["type"] == "chain":
                continue
            d = seen[key]
            d["label"], d["type"] = n["label"], n["type"]
            if r["pocket"]["label"] not in d["pockets"]:
                d["pockets"].add(r["pocket"]["label"])
                d["value_usd"] += r["pocket"]["value_usd"] or 0
    out = [{"dependency": v["label"], "type": v["type"], "pockets": len(v["pockets"]), "exposed_value_usd": v["value_usd"]}
           for v in seen.values() if len(v["pockets"]) >= 2]
    return sorted(out, key=lambda x: -x["exposed_value_usd"])


def print_pocket(r: dict) -> None:
    pk, mc, ex, dec = r["pocket"], r["monte_carlo"], r["exit"], r["decision"]
    print(f"\n━━━ {pk['label']} · {usd(pk['value_usd'] or 0)} ({pct(pk['share_of_book'])} du portefeuille) ━━━")
    print(f"  graphe {r['graph']['nodes']} nœuds / {r['graph']['edges']} arêtes")
    for m in r["markets"]:
        print(f"  · {m['label'][12:60]:48s} prix collatéral : {m['collateral_pricing']:13s} util. {pct(m['utilization'], 0):>6s} "
              f"{m['borrowers']:>3d} emprunteurs")
    print(f"  Perte attendue ({mc['horizon_days']:.0f} j) : {usd(mc['expected_loss_usd'])} · proba d'une perte : "
          f"{pct(mc['p_any_loss'], 2)} · VaR 99,9 % : {usd(mc['var999_usd'])}"
          f" · coût de sortie : {usd(ex['cost_full_usd'])} ({pct(ex['cost_full_pct'], 2)}) · sortable maintenant : {pct(ex['f_max_now'], 0)}")
    print("  Principaux risques (perte si l'incident arrive · p* = seuil de sortie) :")
    for row in [x for x in r["incidents"] if x["loss_if_incident_usd"] > 0][:4]:
        print(f"    - {row['title'][:62]:62s} {usd(row['loss_if_incident_usd']):>14s}   p* {pct(row['p_star']):>8s}")
    print(f"  ➜ {dec['sentence']}")
    if "incident_mode" in r:
        im = r["incident_mode"]
        print(f"\n  ⚡ INCIDENT : {im['sentence']}\n     chemin : {im['contagion_path']}\n     règle : {im['rule']}")


def main(argv: list[str] | None = None) -> int:
    from .session import SessionError, open_session
    utf8_console()
    logging.basicConfig(level=logging.ERROR)
    ap = argparse.ArgumentParser(description="Risque et décision STAY / EXIT pour les poches d'un détenteur réel.")
    ap.add_argument("holder")
    ap.add_argument("--pocket", help="numéro ou morceau du nom d'une poche (défaut : tout le portefeuille)")
    ap.add_argument("--horizon", type=float, help="horizon en jours (défaut : params_v2.yaml)")
    ap.add_argument("--incident", help="id (ou début d'id) d'un incident en cours, voir --list-incidents")
    ap.add_argument("--severity", type=float, help="sévérité de l'incident (0–1)")
    ap.add_argument("--p", type=float, help="votre probabilité que l'incident se matérialise (0–1)")
    ap.add_argument("--list-incidents", action="store_true")
    a = ap.parse_args(argv)
    try:
        s = open_session()
    except SessionError as e:
        print(f"✗ {e}")
        return 1
    p = load_params()
    days = a.horizon or p["horizon_days"]
    port = scan_holder(s.ctx, a.holder, s.chain_id)
    pockets = [pick(port.holdings, a.pocket)] if a.pocket else port.holdings
    print(f"{s.describe()}\nDétenteur {port.holder} · {len(port.holdings)} poches · {usd(port.total_value_usd)} · horizon {days:.0f} j")

    reports = []
    for h in pockets:
        try:
            r = analyze_pocket(s, h, port.holder, p, days, a.incident, a.severity, a.p)
        except UnknownIncident:
            print(f"incident « {a.incident} » inconnu pour « {h.label} ». Utilisez --list-incidents.")
            return 1
        except NotImplementedError as e:
            print(f"\n━━━ {h.label} : ignorée ({e})")
            continue
        reports.append(r)
        if a.list_incidents:
            print(f"\nIncidents générés pour « {h.label} » :")
            for row in r["incidents"]:
                print(f"  {row['id'][:60]:60s} perte si incident {usd(row['loss_if_incident_usd']):>14s}  ({row['title'][:50]})")
            continue
        print_pocket(r)

    book = None
    if len(reports) > 1:
        book = {"total_value_usd": sum(r["pocket"]["value_usd"] or 0 for r in reports),
                "expected_loss_usd": sum(r["monte_carlo"]["expected_loss_usd"] for r in reports),
                "exits": [r["pocket"]["label"] for r in reports if r["decision"]["verdict"] == "EXIT"],
                "shared_dependencies": shared_dependencies(reports)[:12]}
        print(f"\n━━━ PORTEFEUILLE : perte attendue {usd(book['expected_loss_usd'])} sur {usd(book['total_value_usd'])} · "
              f"EXIT recommandé : {', '.join(book['exits']) or 'aucune poche'}")
        print("  Dépendances partagées par plusieurs poches (concentration cachée) :")
        for d in book["shared_dependencies"][:8]:
            print(f"    - {d['dependency'][:40]:40s} [{d['type']:14s}] {d['pockets']} poches · {usd(d['exposed_value_usd'])} exposés")

    out = OUTPUT_DIR / f"risk_{port.holder.lower()}.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"holder": port.holder, "block": s.block, "horizon_days": days, "book": book,
                               "pockets": [public(r) for r in reports],
                               "assumptions": p.listing()}, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)}  ({s.network_calls} appels RPC réseau)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
