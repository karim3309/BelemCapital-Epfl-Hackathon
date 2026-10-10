"""Étape 3 — le graphe de dépendances PROUVÉ d'une poche choisie dans le portefeuille d'un détenteur.

    PYTHONPATH=src python -m stacktrace.graph_build 0xDétenteur "Belem RWA"     (morceau du nom de la poche)
    PYTHONPATH=src python -m stacktrace.graph_build 0xDétenteur 3                (n° de la poche dans la liste)

Déroulé (même moteur que discovery/build_graph.py, mais la racine dépend du TYPE de poche) :
  1. session en ligne (bloc figé) + scan du portefeuille → on retrouve la poche demandée ;
  2. racine selon le type :
       morpho_vault_v2      → vault → adapters → marchés                (stacktrace/vault_v2.py)
       morpho_market_borrow → marché + position (collatéral, dette, santé) (adaptateur existant)
       morpho_market_supply → marché + position de prêt
  3. exploration en largeur des dépendances (tokens, oracles, Pendle…) avec les adaptateurs existants ;
  4. passes finales : émetteurs et hors-chaîne (curated.yaml), proxies, chaîne de règlement ;
  5. validation stricte du contrat JSON → output/live/graph_<poche>.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, deque

import requests

from discovery.adapters import Discovery
from discovery.adapters.chain import discover_chain
from discovery.adapters.contracts import NOT_DETECTED, proxy_info
from discovery.adapters.curated import load_curated
from discovery.adapters.morpho import discover_market, discover_position, market_key, read_market
from discovery.build_graph import API_TASKS, Report, add_issuers_and_offchain, apply, run_task
from discovery.config import REPO_ROOT
from discovery.console import utf8_console
from discovery.graph import POSITION_KEY, Edge, GraphBuilder
from discovery.ids import position_id, slugify
from discovery.validate import validate
from discovery.vocab import ALLOWED_EDGE_SHAPES

from .portfolio import OUTPUT_DIR, Holding, scan_holder
from .session import Session
from .vault_v2 import discover_vault_v2

log = logging.getLogger("stacktrace")
SETTLED_ON_TYPES = ALLOWED_EDGE_SHAPES["settled_on"][0]
SKIPPED_TASKS = {"vaults_lookup"}       # les autres prêteurs d'un marché ne sont pas des dépendances de NOTRE poche


def root_discovery(s: Session, h: Holding, holder: str) -> tuple[Discovery, str]:
    """Racine du graphe selon le type de poche → (découverte, id de position du contrat JSON)."""
    ctx = s.ctx
    if h.kind == "morpho_vault_v2":
        return discover_vault_v2(ctx, h.address, holder), f"morpho_vault_v2:{h.address}:{holder}"
    if h.kind in ("morpho_market_borrow", "morpho_market_supply"):
        m = read_market(ctx, h.market_id)
        d = discover_market(ctx, m)
        d.follow = [t for t in d.follow if t.kind not in SKIPPED_TASKS]
        if h.kind == "morpho_market_borrow":
            pos_d, pos_meta, _ = discover_position(ctx, m, holder, None)
            d.extend(pos_d)
            d.nodes[0].meta["position"] = pos_meta
        else:
            d.edges.append(Edge(POSITION_KEY, market_key(m["market_id"]), "deployed_in", "onchain", h.evidence[0]))
        return d, position_id(m["market_id"], holder)
    raise NotImplementedError(f"type de poche {h.kind!r} pas encore pris en charge (étape suivante)")


def build_position_graph(s: Session, h: Holding, holder: str) -> tuple[dict, Report]:
    ctx, report = s.ctx, Report(block=s.block)
    g, queue = GraphBuilder(), deque()
    d, pid = root_discovery(s, h, holder)
    apply(g, d, queue, report)

    seen: set[tuple[str, str]] = set()
    while queue:
        task = queue.popleft()
        sig = (task.kind, task.target.lower())
        if sig in seen or task.kind in SKIPPED_TASKS:
            continue
        seen.add(sig)
        if len(g.nodes) > s.config.max_nodes:
            raise RuntimeError(f"plus de {s.config.max_nodes} nœuds : boucle probable, on arrête")
        try:
            found = run_task(ctx, task)
        except requests.RequestException as e:
            if task.kind not in API_TASKS:
                raise
            found = Discovery(notes=[f"⚠ {task.kind} {task.target} non découvert (API indisponible : {e})"])
        except ValueError as e:          # contrat illisible : on le DIT, on ne devine pas
            found = Discovery(notes=[f"⚠ {task.kind} {task.target} non découvert : {e}"])
        apply(g, found, queue, report)
        report.tasks_done += 1

    add_issuers_and_offchain(g, load_curated(s.config.curated_file), s.block, ctx.labels)
    onchain = [n for n in g.nodes.values() if n.address and n.type in SETTLED_ON_TYPES]
    for n in onchain:
        n.meta.setdefault("proxy", proxy_info(ctx, n.address) or dict(NOT_DETECTED))
    apply(g, discover_chain(ctx, s.config.chain_name, s.chain_id, onchain), queue, report)

    graph = g.to_contract(pid, h.value_usd or 0.0)
    errors = validate(graph)
    if errors:
        raise ValueError("contrat JSON invalide :\n  - " + "\n  - ".join(errors[:15]))
    return graph, report


def pick(holdings: list[Holding], selector: str) -> Holding:
    if selector.isdigit() and 1 <= int(selector) <= len(holdings):
        return holdings[int(selector) - 1]
    sel = selector.lower()
    hits = [h for h in holdings if sel in h.label.lower() or h.id.lower().startswith(sel)]
    if len(hits) != 1:
        names = "\n".join(f"  {i}. {h.label}" for i, h in enumerate(holdings, 1))
        raise SystemExit(f"« {selector} » désigne {len(hits)} poche(s). Choisissez un numéro ou un nom plus précis :\n{names}")
    return hits[0]


def _summary(graph: dict, report: Report, h: Holding) -> None:
    nodes, edges = graph["nodes"], graph["edges"]
    print(f"\n=== Graphe de la poche « {h.label} » ({h.kind}) ===")
    print(f"    {len(nodes)} nœuds {dict(Counter(n['type'] for n in nodes))}")
    print(f"    {len(edges)} arêtes · sources {dict(Counter(e['source'] for e in edges))}")
    vault = next((n for n in nodes if n["type"] == "vault" and n["meta"].get("allocations")), None)
    if vault:
        m = vault["meta"]
        sym = m["asset_symbol"]
        print(f"\n  Vault {vault['label']} : {m['total_assets_human']:,.0f} {sym} · détenteur = {m['holder_share_of_vault']:.1%} du vault")
        print(f"  {'marché (id)':14s} {'collatéral':>18s} {'fourni':>16s} {'part':>7s} {'util.':>6s} {'retirable':>14s}")
        markets = {n["meta"].get("market_id"): n for n in nodes if n["type"] == "lending_market"}
        for a in sorted(m["allocations"], key=lambda a: -a["supplied"]):
            mk = markets.get(a["market_id"])
            coll = mk["label"].split(" / ")[0].replace("Morpho Blue ", "") if mk else "?"
            print(f"  {a['market_id'][:12]:14s} {coll:>18s} {a['supplied']:>16,.0f} {a['share_of_vault']:>7.1%} "
                  f"{(a['market_utilization'] or 0):>6.0%} {a['withdrawable_now']:>14,.0f}")
        ex = m["exit_liquidity"]
        pen = [a["force_deallocate_penalty"] for a in m["adapters"]]
        print(f"\n  Sortie : retirable maintenant ≈ {ex['withdrawable_now_human']:,.0f} {sym} pour TOUS les déposants "
              f"→ couvre {ex['covers_holder_share']:.1%} de la poche · pénalité de retrait forcé {pen}")
    unresolved = [n for n in nodes if n["meta"].get("unresolved")]
    if unresolved:
        print(f"\n  ⚠ {len(unresolved)} nœud(s) non résolu(s) (on ne devine pas) :")
        for n in unresolved:
            print(f"     - {n['id']} [{n['type']}] {n['label']}")
    if report.notes:
        print("\n  Notes :")
        for note in report.notes:
            print(f"   · {note}")


def main(argv: list[str] | None = None) -> int:
    from .session import SessionError, open_session
    utf8_console()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    ap = argparse.ArgumentParser(description="Graphe de dépendances prouvé d'une poche d'un détenteur.")
    ap.add_argument("holder")
    ap.add_argument("position", help="numéro de la poche (liste de stacktrace.portfolio) ou morceau de son nom")
    args = ap.parse_args(argv)
    try:
        s = open_session()
    except SessionError as e:
        print(f"✗ {e}")
        return 1
    p = scan_holder(s.ctx, args.holder, s.chain_id)
    h = pick(p.holdings, args.position)
    print(f"{s.describe()}\nPoche : {h.label} ({h.value_usd or 0:,.0f} $)")
    graph, report = build_position_graph(s, h, p.holder)
    _summary(graph, report, h)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"graph_{slugify(h.label)[:40]}.json"
    out.write_text(json.dumps(graph, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ contrat JSON valide → {out.relative_to(REPO_ROOT)}  ({s.network_calls} appels RPC réseau)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
