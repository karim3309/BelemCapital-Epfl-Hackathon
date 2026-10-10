"""One-command diagnostic: does everything the backend needs answer, LIVE?

    PYTHONPATH=src python -m stacktrace.doctor

Checks, in order:
  1. ETH_RPC_URL is set in .env (only the host is shown, never the key);
  2. the RPC answers, on the right chain (chainId = 1 = Ethereum mainnet), and how fast;
  3. the latest block is recent (a lagging node would give a stale snapshot);
  4. the node is an "archive" node (it can answer for an old block → incident replays possible);
  5. the Morpho and Pendle APIs answer (they are used to LOCATE; we then re-prove on-chain).
Exit code 0 if everything essential is OK, 1 otherwise.
"""
from __future__ import annotations

import sys
import time

import requests

from discovery.console import utf8_console

from .session import SessionError, mask_url, open_session

ARCHIVE_LOOKBACK_BLOCKS = 216_000      # ≈ 30 days at 12 s/block
MAX_BLOCK_AGE_S = 120                  # beyond that, the node is probably lagging


def _api_check(name: str, fn) -> tuple[bool, str]:
    t = time.time()
    try:
        detail = fn()
        return True, f"{name}: OK ({(time.time() - t) * 1000:.0f} ms){detail}"
    except Exception as e:
        return False, f"{name}: FAILED ({type(e).__name__}: {str(e)[:120]})"


def run() -> int:
    utf8_console()
    lines: list[tuple[str, str]] = []           # (status, text)
    vital_ok = True

    try:
        t = time.time()
        s = open_session("latest")
        latency = (time.time() - t) * 1000
    except SessionError as e:
        print(f"✗ {e}")
        return 1

    lines.append(("✓", f"ETH_RPC_URL found · host {mask_url(s.config.rpc_url)}"))
    lines.append(("✓", f"RPC on chainId {s.chain_id} (Ethereum mainnet) · session opened in {latency:.0f} ms"))
    age = time.time() - s.block_timestamp
    fresh = age < MAX_BLOCK_AGE_S
    lines.append(("✓" if fresh else "!", f"block pinned for the analysis: #{s.block} · age {age:.0f} s"
                  + ("" if fresh else " → the node seems to be lagging")))

    old = s.block - ARCHIVE_LOOKBACK_BLOCKS
    try:
        s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=old)
        lines.append(("✓", f"archive node: read at block #{old} (~30 d) OK → incident replays possible"))
    except Exception:
        lines.append(("!", "NON-archive node: only the recent state is readable (no historical replay)"))

    morpho_url = s.config.apis.get("morpho_graphql")
    pendle_url = s.config.apis.get("pendle_core")

    def morpho():
        r = requests.post(morpho_url, json={"query": "{ __typename }"}, timeout=20)
        r.raise_for_status()
        if r.json().get("data", {}).get("__typename") != "Query":
            raise RuntimeError("unexpected response")
        return ""

    def pendle():
        r = requests.get(f"{pendle_url}/v2/markets/all", params={"skip": 0, "limit": 1}, timeout=20)
        r.raise_for_status()
        return ""

    for name, url, fn in (("Morpho API", morpho_url, morpho), ("Pendle API", pendle_url, pendle)):
        if not url:
            lines.append(("!", f"{name}: URL missing from config.yaml (apis section)"))
            continue
        ok, txt = _api_check(name, fn)
        lines.append(("✓" if ok else "✗", txt))
        vital_ok &= ok if name == "Morpho API" else True   # Morpho is essential (position scan)

    print("=== StackTrace · live diagnostic ===")
    for status, txt in lines:
        print(f"  {status} {txt}")
    print(f"  · network RPC calls during the test: {s.network_calls}")
    print("→ ready" if vital_ok else "→ NOT ready: fix the ✗ lines above")
    return 0 if vital_ok else 1


if __name__ == "__main__":
    sys.exit(run())
