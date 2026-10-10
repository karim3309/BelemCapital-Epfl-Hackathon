"""Records every API response of one holder, for the front's offline (recorded) mode.

    PYTHONPATH=src python -m stacktrace.record book:rockawayx          # a curator book (config.yaml)
    PYTHONPATH=src python -m stacktrace.record vault:0x…               # one whole vault
    PYTHONPATH=src python -m stacktrace.record 0x4F87…0545             # a holder address

It calls the REAL API routes (in-process, same code as `python -m stacktrace.api`), at one pinned block,
and writes the answers as they are into docs/api_examples/recordings/<holder>/:
    pockets.json, book.json, risk_<n>.json and graph_<n>.json for every pocket, incident.json (one example).
The front picks up every folder there by itself: the demo then replays them with no network.
Needs ETH_RPC_URL in .env (live mode). A full book takes a few minutes the first time.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from fastapi.testclient import TestClient

from discovery.config import REPO_ROOT
from discovery.console import utf8_console

from .api import app
from .portfolio import file_slug

RECORDINGS = REPO_ROOT / "docs" / "api_examples" / "recordings"
INCIDENT_EXAMPLE_P = 0.2      # the manager's probability used for the one recorded incident (shown as such)


def _save(folder, name: str, data: dict) -> None:
    (folder / name).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def record(holder: str) -> int:
    client = TestClient(app)
    t0 = time.time()
    r = client.get(f"/holders/{holder}/pockets")
    if r.status_code != 200:
        print(f"✗ /pockets → {r.status_code}: {r.text[:300]}")
        return 1
    pockets = r.json()
    folder = RECORDINGS / file_slug(pockets["holder"])
    folder.mkdir(parents=True, exist_ok=True)
    _save(folder, "pockets.json", pockets)
    print(f"block #{pockets['block']} · {len(pockets['holdings'])} pocket(s) · {len(pockets['ignored'])} left out")
    for i in pockets["ignored"]:
        print(f"   - left out: {i.get('label') or i.get('id')}: {i['reason']}")

    book = client.get(f"/holders/{holder}/book")          # runs every risk analysis (then cached per block)
    if book.status_code == 200:
        _save(folder, "book.json", book.json())
        print(f"✓ book ({time.time() - t0:.0f} s)")
    else:
        print(f"⚠ /book → {book.status_code}: {book.text[:200]}")

    incident_done = False
    for h in pockets["holdings"]:
        n = h["index"]
        for route in ("risk", "graph"):
            resp = client.get(f"/holders/{holder}/pockets/{n}/{route}")
            if resp.status_code == 200:
                _save(folder, f"{route}_{n}.json", resp.json())
            else:
                print(f"⚠ pocket {n} /{route} → {resp.status_code}: {resp.text[:200]}")
        risk_file = folder / f"risk_{n}.json"
        if not incident_done and risk_file.exists():
            risk = json.loads(risk_file.read_text(encoding="utf-8"))
            top = next((x for x in risk["incidents"] if x["loss_if_incident_usd"] > 0), None)
            if top:
                inc = client.post(f"/holders/{holder}/pockets/{n}/incident",
                                  json={"incident": top["id"], "p": INCIDENT_EXAMPLE_P})
                if inc.status_code == 200:
                    _save(folder, "incident.json", inc.json())
                    incident_done = True
        print(f"✓ pocket {n}: {h['label']} ({time.time() - t0:.0f} s)")

    shown = folder.relative_to(REPO_ROOT) if folder.is_relative_to(REPO_ROOT) else folder
    print(f"\n→ {shown}  — commit it: the front replays it offline.")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description="Records every API response of a holder for the offline demo.")
    ap.add_argument("holder", help="book:<key> (config.yaml), vault:0x… or a holder address 0x…")
    return record(ap.parse_args(argv).holder)


if __name__ == "__main__":
    sys.exit(main())
