"""On-chain reads of the risk engine → output/risk_inputs.json.

This is the ONLY part of the engine that talks to the blockchain. It reuses the discovery
plumbing (disk cache, pinned block, evidence), and reads at the SAME block as graph.json:

  1. REAL exit cost: we ask Pendle's RouterStatic contract "if I sold Q PT into this
     pool, how much SY would I get?" (simulation function, no transaction).
     Analogy: asking the exchange office for a quote at several amounts, without trading.
  2. History of the Chainlink USDe/USD feed: every "round" (update) since the feed
     was created. Used to calibrate depeg severity AND to replay October 2025.
  3. Gas price: block base fee + ETH/USD price (Chainlink feed found via ENS).

    python -m risk.collect            # online (or offline if everything is already cached)
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from discovery.adapters.ens import resolve
from discovery.cache import DiskCache
from discovery.config import REPO_ROOT, load_config
from discovery.console import utf8_console
from discovery.ctx import CallFailed, Ctx, checksum
from discovery.http import CachedHttp
from discovery.rpc import make_web3

from .graphview import GraphView

SWAP_STATIC = "swapExactPtForSyStatic(address,uint256)"
SWAP_STATIC_SOURCE = ("IPActionMarketCoreStatic.sol, npm package @pendle/core-v2@6.6.1 "
                      "(https://cdn.jsdelivr.net/npm/@pendle/core-v2@6.6.1/contracts/interfaces/IPActionMarketCoreStatic.sol)")
ROUND = ["uint80", "int256", "uint256", "uint256", "uint80"]
# Simulated sizes, as multiples of the position's collateral (1.0 = sell everything).
# Large multiples approximate a smaller pool (see params: stressed_pool_scaling).
SIZE_MULTIPLES = [0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0, 20.0]
OUTPUT = REPO_ROOT / "output" / "risk_inputs.json"


def _make_ctx(block: int, offline: bool | None = None) -> Ctx:
    config = load_config(offline=offline)
    cache = DiskCache(config.cache_dir, offline=config.offline)
    w3 = make_web3(config.rpc_url, cache)
    return Ctx(w3=w3, block=block, http=CachedHttp(cache), config=config)


def collect_exit_simulations(ctx: Ctx, gv: GraphView) -> dict:
    venue = gv.exit_venue_id()
    if venue is None:
        return {"available": False, "reason": "no exit pool in the graph"}
    market = gv.node(venue)["address"]
    router = ctx.config.contracts["pendle_router_static"]
    ctx.labels[checksum(router)] = "PendleRouterStatic"
    pos = gv.meta(gv.market_id())["position"]
    collateral = float(pos["collateral_human"])
    points = []
    for m in SIZE_MULTIPLES:
        pt_in = collateral * m
        raw_in = int(pt_in * 10**18)
        res = ctx.try_call(router, SWAP_STATIC, [market, raw_in], ["uint256", "uint256", "uint256", "uint256"])
        point = {"size_multiple": m, "pt_in": pt_in}
        if res is None:
            point.update({"reverted": True,
                          "evidence": f"PendleRouterStatic.swapExactPtForSyStatic({market},{raw_in}) → revert #{ctx.block}"})
        else:
            sy_out, sy_fee, impact, rate_after = res
            point.update({
                "reverted": False, "sy_out": sy_out / 1e18, "sy_fee": sy_fee / 1e18,
                "price_impact": impact / 1e18, "exchange_rate_after": rate_after / 1e18,
                "evidence": ctx.ev(router, SWAP_STATIC, [market, raw_in], res),
            })
        points.append(point)
    return {
        "available": True, "router_static": checksum(router),
        "router_static_source": ctx.config.contract_sources["pendle_router_static"],
        "function": SWAP_STATIC, "function_source": SWAP_STATIC_SOURCE,
        "market": market, "collateral_pt": collateral, "points": points,
    }


def collect_chainlink_history(ctx: Ctx, gv: GraphView, workers: int = 8) -> dict:
    """Every round of each Chainlink feed in the graph (successive phases of the proxy)."""
    out = {}
    for n in gv.of_type("oracle"):
        if n["meta"].get("oracle_kind") != "chainlink_aggregator_proxy":
            continue
        proxy = n["address"]
        ctx.labels[checksum(proxy)] = f"ChainlinkFeed[{n['meta'].get('description')}]"
        phase_now = ctx.call(proxy, "phaseId()", returns=["uint16"])
        decimals = ctx.call(proxy, "decimals()", returns=["uint8"])
        phases, jobs = [], []
        for ph in range(1, phase_now + 1):
            agg = ctx.try_call(proxy, "phaseAggregators(uint16)", [ph], ["address"])
            if agg is None or int(agg, 16) == 0:
                continue
            last = ctx.try_call(agg, "latestRound()", returns=["uint256"])
            if not last:
                continue
            phases.append({"phase": ph, "aggregator": agg, "rounds": last})
            jobs += [((ph << 64) | r, ph, r) for r in range(1, last + 1)]

        def read(job):
            rid, ph, r = job
            try:
                res = ctx.call(proxy, "getRoundData(uint80)", [rid], ROUND)
            except CallFailed:
                return None
            return {"phase": ph, "round": r, "answer": res[1] / 10**decimals, "updated_at": res[3]}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            rounds = [x for x in pool.map(read, jobs) if x and x["updated_at"]]
        rounds.sort(key=lambda x: (x["updated_at"], x["phase"], x["round"]))
        out[n["id"]] = {
            "feed": proxy, "description": n["meta"].get("description"), "decimals": decimals,
            "phases": phases, "rounds": rounds,
            "evidence": f"ChainlinkFeed.getRoundData(phase<<64|round) for {len(rounds)} rounds @ {proxy} #{ctx.block}",
        }
    return out


def collect_gas(ctx: Ctx) -> dict:
    block = ctx.w3.eth.get_block(ctx.block)
    base_fee = int(block.get("baseFeePerGas", 0)) / 1e9
    gas = {"base_fee_gwei": base_fee,
           "base_fee_evidence": f"eth_getBlockByNumber({ctx.block}).baseFeePerGas = {base_fee:.4f} gwei"}
    name = ctx.config.raw.get("usd_reference", {}).get("gas_token_usd_feed_ens")
    if name:
        feed, proof = resolve(ctx, name)
        if feed:
            _, answer, _, _, _ = ctx.call(feed, "latestRoundData()", returns=ROUND)
            dec = ctx.call(feed, "decimals()", returns=["uint8"])
            gas["eth_usd"] = answer / 10**dec
            gas["eth_usd_evidence"] = f"{proof}; latestRoundData().answer = {answer} (dec. {dec})"
    return gas


def collect(graph_path: Path | None = None, offline: bool | None = None) -> dict:
    gv = GraphView.load(graph_path or REPO_ROOT / "output" / "graph.json")
    snap = gv.snapshot()
    ctx = _make_ctx(snap["block"], offline)
    data = {
        "snapshot_block": snap["block"],
        "snapshot_time_iso": snap["time_iso"],
        "position_id": gv.position_id,
        "exit_simulations": collect_exit_simulations(ctx, gv),
        "chainlink_history": collect_chainlink_history(ctx, gv),
        "gas": collect_gas(ctx),
    }
    return data


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description="On-chain reads of the risk engine")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    data = collect(offline=True if args.offline else None)
    OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    sims = data["exit_simulations"].get("points", [])
    hist = sum(len(v["rounds"]) for v in data["chainlink_history"].values())
    print(f"✓ {OUTPUT}: {len(sims)} sale simulations, {hist} Chainlink rounds, block #{data['snapshot_block']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
