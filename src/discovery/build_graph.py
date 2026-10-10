"""Script principal : (marketId, user) → graph.json prouvé.

    python -m discovery.build_graph                 # en ligne (remplit le cache si besoin)
    python -m discovery.build_graph --offline       # démo : 100 % depuis data/cache/, zéro réseau

Déroulé :
  1. connexion RPC (via le cache) + vérification chainId + bloc figé ;
  2. racine : le marché Morpho (paramètres prouvés par recalcul du hash) et la position ;
  3. exploration en largeur : chaque adaptateur renvoie des nœuds, des arêtes et les prochaines
     cibles (`follow`) — token, oracle, pool Pendle, vaults... jusqu'à épuisement ;
  4. passes finales : valorisation (price_usd / tvl_usd), émetteurs (curated.yaml),
     relations hors chaîne, chaîne de règlement ;
  5. validation stricte du contrat JSON, puis écriture de output/graph.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .adapters import Discovery, Task
from .adapters.chain import discover_chain
from .adapters.contracts import proxy_info
from .adapters.curated import Curated, load_curated
from .adapters.erc4626 import discover_erc4626
from .adapters.erc20 import classify, read_token, token_node
from .adapters.morpho import discover_market, discover_position, loan_token_usd_price, market_key, read_market
from .adapters.morpho_api import discover_supplying_vaults
from .adapters.oracles import discover_oracle
from .adapters.pendle import discover_pendle_market, discover_pt, discover_sy, find_market_via_api
from .cache import DiskCache
from .config import Config, load_config
from .ctx import ZERO_ADDRESS, Ctx, checksum
from .graph import GraphBuilder
from .http import CachedHttp
from .ids import position_id
from .rpc import check_chain, make_web3, resolve_snapshot_block
from .validate import validate
from .valuation import value_graph

log = logging.getLogger("stacktrace")

API_TASKS = {"pendle_market_lookup", "vaults_lookup"}


@dataclass
class Report:
    block: int = 0
    notes: list[str] = field(default_factory=list)
    tasks_done: int = 0


# =========================================================================== dispatch
def discover_token(ctx: Ctx, address: str) -> Discovery:
    info = read_token(ctx, address)
    if info is None:
        raise ValueError(f"{address} n'est pas un ERC-20 lisible (symbol/decimals absents)")
    ctx.labels[info["address"]] = info["symbol"]
    kind = classify(ctx, address)
    if kind == "pendle_pt":
        d = discover_pt(ctx, info)
    elif kind == "pendle_sy":
        d = discover_sy(ctx, info)
    elif kind == "erc4626":
        d = discover_erc4626(ctx, info)
    else:
        d = Discovery(nodes=[token_node(info, "erc20")])
    proxy = proxy_info(ctx, address)
    if proxy:
        d.nodes[0].meta["proxy"] = proxy
    return d


def run_task(ctx: Ctx, task: Task) -> Discovery:
    hint = dict(task.hint)
    if task.kind == "token":
        return discover_token(ctx, task.target)
    if task.kind == "oracle":
        return discover_oracle(ctx, task.target, hint.get("scale_decimals"))
    if task.kind == "pendle_market_lookup":
        found = find_market_via_api(ctx, task.target)
        if not found:
            return Discovery(notes=[f"Aucun pool Pendle trouvé via l'API pour le PT {task.target}"])
        entry, url, fetched_at = found
        market = checksum(entry["address"])
        return discover_pendle_market(ctx, market, task.target, entry, url, fetched_at)
    if task.kind == "pendle_market":
        _, pt, _ = ctx.call(task.target, "readTokens()", returns=["address", "address", "address"])
        return discover_pendle_market(ctx, task.target, pt, None, None, None)
    if task.kind == "vaults_lookup":
        if not ctx.config.include_vaults:
            return Discovery(notes=["vaults ignorés (discovery.include_vaults = false)"])
        return discover_supplying_vaults(ctx, task.target, ctx.config.expected_chain_id)
    raise ValueError(f"tâche inconnue : {task.kind}")


def apply(g: GraphBuilder, d: Discovery, queue: deque, report: Report) -> None:
    for n in d.nodes:
        g.add_node(n)
    for e in d.edges:
        g.add_edge(e)
    queue.extend(d.follow)
    report.notes.extend(d.notes)


# =========================================================================== passes finales
def add_issuers_and_offchain(g: GraphBuilder, curated: Curated, block: int, labels: dict) -> None:
    # 1. issued_by pour chaque contrat connu (par adresse ou par factory)
    for n in list(g.nodes.values()):
        if not n.address:
            continue
        edge = curated.issuer_edge(n.key, n.address, n.meta.get("factory"), block, labels.get(n.address, n.label))
        if edge:
            g.add_edge(edge)
    # 2. on matérialise les entités curées RÉFÉRENCÉES, puis leurs relations (récursivement)
    pending = deque(e.to_key for e in g.edges.values() if e.to_key.startswith(("issuer:", "offchain:")))
    while pending:
        key = pending.popleft()
        if g.has(key):
            continue
        node = curated.node_for_key(key)
        if node is None:
            raise ValueError(f"entité {key} référencée mais absente de curated.yaml")
        g.add_node(node)
        for e in curated.relation_edges(key.partition(":")[2]):
            g.add_edge(e)
            pending.append(e.to_key)


def build(config: Config) -> tuple[dict, Report, DiskCache]:
    report = Report()
    cache = DiskCache(config.cache_dir, offline=config.offline)
    w3 = make_web3(config.rpc_url, cache)
    chain_id = check_chain(w3, config.expected_chain_id)
    block = resolve_snapshot_block(w3, config.snapshot_block, config.offline)
    report.block = block
    ctx = Ctx(w3=w3, block=block, http=CachedHttp(cache), config=config)
    curated = load_curated(config.curated_file)
    g = GraphBuilder()
    queue: deque[Task] = deque()

    # --- racine : marché + position
    m = read_market(ctx, config.market_id)
    apply(g, discover_market(ctx, m), queue, report)
    pos_d, pos_meta, value_usd = discover_position(ctx, m, config.user, config.value_usd_override)
    apply(g, pos_d, queue, report)
    g.nodes[market_key(config.market_id)].meta["position"] = pos_meta

    # --- exploration en largeur
    seen: set[tuple[str, str]] = set()
    while queue:
        task = queue.popleft()
        sig = (task.kind, task.target.lower())
        if sig in seen:
            continue
        seen.add(sig)
        if len(g.nodes) > config.max_nodes:
            raise RuntimeError(f"plus de {config.max_nodes} nœuds : boucle probable, on arrête")
        log.info("→ %s %s", task.kind, task.target)
        try:
            d = run_task(ctx, task)
        except requests.RequestException as e:
            if task.kind not in API_TASKS:
                raise
            # Une API indisponible ne doit pas faire tomber la découverte on-chain : on le DIT.
            d = Discovery(notes=[f"⚠ {task.kind} {task.target} non découvert (API indisponible : {e})"])
        apply(g, d, queue, report)
        report.tasks_done += 1

    # --- passes finales
    usd, usd_source = loan_token_usd_price(ctx)
    value_graph(g, market_key(config.market_id), usd, usd_source, ctx.block_timestamp)
    add_issuers_and_offchain(g, curated, block, ctx.labels)
    onchain = [n for n in g.nodes.values() if n.address]
    apply(g, discover_chain(ctx, config.chain_name, chain_id, onchain), queue, report)

    pid = position_id(config.market_id, config.user or ZERO_ADDRESS)
    graph = g.to_contract(pid, value_usd)
    return graph, report, cache


# =========================================================================== CLI
def _print_summary(graph: dict, report: Report, cache: DiskCache, errors: list[str], out: Path) -> None:
    from collections import Counter
    print(f"\n=== StackTrace · découverte au bloc #{report.block} ===")
    print(f"position : {graph['position']['id']}  (value_usd = {graph['position']['value_usd']:,})")
    print("nœuds    :", dict(Counter(n["type"] for n in graph["nodes"])))
    print("arêtes   :", dict(Counter(e["type"] for e in graph["edges"])))
    print("sources  :", dict(Counter(e["source"] for e in graph["edges"])))
    s = cache.stats
    print(f"cache    : {s.hits} hits, {s.misses} misses, {s.writes} écritures {s.by_namespace}")
    if report.notes:
        print("notes    :")
        for n in report.notes:
            print("   ·", n)
    if errors:
        print(f"✗ {len(errors)} erreur(s) de validation :")
        for e in errors:
            print("   -", e)
    else:
        print(f"✓ contrat JSON valide → {out}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")   # accents et ✓ dans la console Windows
        except AttributeError:
            pass
    p = argparse.ArgumentParser(description="StackTrace — découverte du graphe de dépendances")
    p.add_argument("--config", default=None, help="chemin de config.yaml")
    p.add_argument("--offline", action="store_true", help="aucun appel réseau : tout depuis data/cache/")
    p.add_argument("--out", default=None, help="fichier de sortie (défaut : discovery.output_file)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    config = load_config(args.config, offline=True if args.offline else None)
    graph, report, cache = build(config)
    errors = validate(graph)
    out = Path(args.out) if args.out else config.output_file
    if not errors:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    _print_summary(graph, report, cache, errors, out)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
