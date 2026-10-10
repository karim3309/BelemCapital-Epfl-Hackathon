"""Rafraîchir TOUTE la photo en une commande : découverte + lectures du moteur de risque, au même bloc.

Pourquoi une commande dédiée ? Un RPC public (non « archive ») ne sait répondre qu'aux ~128 derniers
blocs (~25 min). Le graphe et les lectures du moteur de risque doivent être faits au MÊME bloc,
donc dans la foulée. Ensuite tout est en cache : on rejoue hors ligne autant qu'on veut.

    PYTHONPATH=src python -m risk.refresh      # nécessite ETH_RPC_URL dans .env
puis
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
        print("✗ graphe invalide :", *errors, sep="\n  - ")
        return 1
    config.output_file.write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8", newline="\n")
    pin_block(report.block)
    print(f"✓ graphe découvert au bloc #{report.block} ({len(graph['nodes'])} nœuds) — config.yaml figé")
    data = collect_mod.collect(offline=False)
    collect_mod.OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                                  encoding="utf-8", newline="\n")
    print(f"✓ lectures du moteur de risque au même bloc → {collect_mod.OUTPUT}")
    print("Ensuite : python -m risk.run --offline  (puis commitez data/cache, output/, config.yaml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
