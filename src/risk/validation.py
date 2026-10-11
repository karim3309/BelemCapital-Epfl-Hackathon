"""Counterfactual replays on real price paths: TODAY's position put through crises that REALLY happened.

    PYTHONPATH=src python -m risk.validation        # 100 % offline → docs/api_examples/validation.json

A stress test asks "what if USDe lost 30 %?". A counterfactual replay asks something else: take a real price path
(its depth AND its duration) and run it through the same engine, applied to the position AS IT IS TODAY.
It is NOT a back-test: it does not compare the model with what really happened to this position (which may not have
existed on that date). It shows how today's design (oracle, health factor) would cope with a shock of that shape.

The replays themselves are computed by `risk.run` (src/risk/replay.py) at the frozen block of position A and stored in
output/risk_report.json. This module only reshapes them for the front and states the takeaway of each replay in plain
words: the front computes nothing. The API serves the same view at GET /validation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from discovery.config import REPO_ROOT
from discovery.console import utf8_console

from .fmt import usd
from .run import REPORT

OUT = REPO_ROOT / "docs" / "api_examples" / "validation.json"

DESIGN_KEYS = ("design", "min_hf", "liquidated", "borrower_loss_usd", "why")
META_KEYS = ("threshold", "max_deviation", "longest_above_threshold_minutes", "needed_minutes", "challenge_possible",
             "switched")


def takeaway(designs: list[dict]) -> str:
    """One sentence: same real shock, which oracle designs survive it and which one gets liquidated."""
    hit = [d for d in designs if d["liquidated"]]
    safe = [d for d in designs if not d["liquidated"]]
    if hit and safe:
        losses = " ; ".join(f"{d['design']}: liquidated, {usd(d['borrower_loss_usd'] or 0)} lost" for d in hit)
        return (f"Same real crisis, opposite outcomes: {len(safe)} oracle design(s) hold, but {losses}. "
                "The source of the oracle decides who gets liquidated.")
    if hit:
        return "Every oracle design is liquidated: the position would not have survived this crisis."
    if not designs:
        return ""
    lowest = min(d["min_hf"] for d in designs)
    return (f"No oracle design is liquidated: the real shock stayed below what the position can absorb "
            f"(lowest health factor {lowest:.3f}, liquidation below 1).")


def build(report: dict) -> dict:
    pos = report["position"]
    replays = []
    for r in report.get("replays", []):
        if not r.get("available"):
            replays.append({"id": r["id"], "title": r["title"], "available": False})
            continue
        designs = [{k: d.get(k) for k in DESIGN_KEYS} for d in r["designs"]]
        replays.append({
            "id": r["id"], "title": r["title"], "story": r["story"], "available": True,
            "window": r["window"],
            "onchain": {"feed": r["feed"], "min_price": r["chainlink_min"], "min_time": r["chainlink_min_iso"],
                        "path": r["chainlink_path"], "evidence": r["evidence"]},
            "offchain": r.get("offchain_source"),
            "meta_oracle": {k: r["meta_oracle"].get(k) for k in META_KEYS},
            "designs": designs,
            "takeaway": takeaway(designs),
        })
    return {
        "snapshot": report["snapshot"],
        "position": {"id": pos["id"], "label": "PT-sUSDe collateral on Morpho Blue, USDC borrowed (position A)",
                     "health_factor": pos["health_factor"], "equity_usd": pos["equity_usd"],
                     "oracle_drop_to_liquidation": pos["oracle_drop_to_liquidation"]},
        "method": ("Counterfactual, not a back-test: TODAY's position put through real past price paths, with the "
                   "same engine as the stress scenarios. On-chain path: every round of the Chainlink USDe/USD feed, "
                   "read at the frozen block. Off-chain price (exchange order book): curated, with its source and "
                   "date."),
        "replays": replays,
    }


def load(path: Path = REPORT) -> dict:
    return build(json.loads(Path(path).read_text(encoding="utf-8")))


def main() -> int:
    utf8_console()
    view = load()
    OUT.write_text(json.dumps(view, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for r in view["replays"]:
        print(f"· {r['title']}\n  {r.get('takeaway', 'not available')}")
    print(f"✓ {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
