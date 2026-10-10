"""Refresh the WHOLE snapshot in one command: discovery + risk-engine reads, at the same block.

Why a dedicated command? A public (non-"archive") RPC can only answer for the last ~128
blocks (~25 min). The graph and the risk-engine reads must be made at the SAME block,
so back to back. After that everything is cached: replay offline as much as you like.

    PYTHONPATH=src python -m risk.refresh      # requires ETH_RPC_URL in .env
then
    PYTHONPATH=src python -m risk.run --offline
"""
from __future__ import annotations

import json
import re
import sys

from discovery.build_graph import build
from discovery.config import REPO_ROOT, load_config
from discovery.console import utf8_console
from discovery.validate import validate

from . import collect as collect_mod


def pin_block(block: int) -> None:
    path = REPO_ROOT / "config.yaml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^snapshot_block: .*$", f"snapshot_block: {block}", text, count=1)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    utf8_console()
    config = load_config(offline=False)
    config.snapshot_block = "latest"
    graph, report, _ = build(config)
    errors = validate(graph)
    if errors:
        print("✗ invalid graph:", *errors, sep="\n  - ")
        return 1
    config.output_file.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8", newline="\n")
    pin_block(report.block)
    print(f"✓ graph discovered at block #{report.block} ({len(graph['nodes'])} nodes) — config.yaml pinned")
    data = collect_mod.collect(offline=False)
    collect_mod.OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                                  encoding="utf-8", newline="\n")
    print(f"✓ risk-engine reads at the same block → {collect_mod.OUTPUT}")
    print("Next: python -m risk.run --offline  (then commit data/cache, output/, config.yaml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
