"""Warm-up before a live demo: makes the RUNNING API compute everything the deck will ask for.

    Window 1:  PYTHONPATH=src python -m stacktrace.api --hold-block      (the block stays the same until restart)
    Window 2:  PYTHONPATH=src python -m stacktrace.warmup book:rockawayx

It calls the same routes as the front (pockets, book, then the risk and the graph of every pocket) over HTTP.
The API caches every answer for its block, so once this is done every screen of the deck is instant.
Without --hold-block the API moves to a new block every 2 minutes and the warm-up is lost: keep it on.
"""
from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import quote

import requests

from discovery.console import utf8_console

DEFAULT_API = "http://127.0.0.1:8000"
TIMEOUT_S = 1800          # the first /book of a large curator book can take many minutes


def warmup(holder: str, api: str = DEFAULT_API) -> int:
    base = f"{api.rstrip('/')}/holders/{quote(holder, safe='')}"
    t0 = time.time()

    def get(path: str, what: str) -> dict | None:
        t = time.time()
        try:
            r = requests.get(base + path, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            print(f"✗ {what}: API unreachable ({type(e).__name__}). Is `python -m stacktrace.api --hold-block` running?")
            return None
        if r.status_code != 200:
            print(f"⚠ {what} → HTTP {r.status_code}: {r.text[:200]}")
            return None
        print(f"✓ {what} ({time.time() - t:.0f} s)")
        return r.json()

    health = requests.get(f"{api.rstrip('/')}/health", timeout=60).json()
    if not health.get("block_held"):
        print("⚠ the API does not hold its block: restart it with --hold-block, or this warm-up is lost in 2 minutes")
    pockets = get("/pockets", "pockets")
    if not pockets:
        return 1
    print(f"   block #{pockets['block']} · {len(pockets['holdings'])} pocket(s) · {len(pockets['ignored'])} left out")
    for i in pockets["ignored"]:
        print(f"   - left out: {i.get('label') or i.get('id')}: {i['reason']}")
    get("/book", "book (risk of every pocket)")
    for h in pockets["holdings"]:
        get(f"/pockets/{h['index']}/risk", f"risk  · {h['label']}")
        get(f"/pockets/{h['index']}/graph", f"graph · {h['label']}")
    print(f"\nReady in {time.time() - t0:.0f} s. Leave the API window open; open the deck with ?source=live&holder={holder}")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description="Makes the running API compute everything the deck needs, before a demo.")
    ap.add_argument("holder", nargs="?", default="book:rockawayx", help="book:<key>, vault:0x… or an address (default book:rockawayx)")
    ap.add_argument("--api", default=DEFAULT_API, help=f"API base URL (default {DEFAULT_API})")
    a = ap.parse_args(argv)
    try:
        return warmup(a.holder, a.api)
    except requests.RequestException as e:
        print(f"✗ API unreachable ({type(e).__name__}). Start it first: python -m stacktrace.api --hold-block")
        return 1


if __name__ == "__main__":
    sys.exit(main())
