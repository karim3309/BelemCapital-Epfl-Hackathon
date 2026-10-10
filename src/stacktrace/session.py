"""LIVE session: an RPC connection + ONE pinned block for a whole analysis.

Why pin a block when working live?
  The blockchain moves one block every ~12 s. If we read the vault at block N and its markets
  at block N+3, the numbers would no longer be consistent. So we read "latest" ONCE at
  startup, then every read of the analysis is made at that block: it is a snapshot
  of the chain, and each piece of evidence can cite "… @ 0xAddress #block".

The cache (data/cache_live/) is no longer there for the offline demo: it avoids reading the same thing
twice during an analysis and keeps a readable trace of each response. It is ignored by git.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from web3 import Web3

from discovery.cache import DiskCache
from discovery.config import REPO_ROOT, Config, load_config
from discovery.ctx import Ctx
from discovery.http import CachedHttp
from discovery.rpc import CachedHTTPProvider, check_chain, make_web3, resolve_snapshot_block

LIVE_CACHE_DIR = REPO_ROOT / "data" / "cache_live"


class SessionError(RuntimeError):
    pass


class BlockScopedHttp(CachedHttp):
    """Live APIs: the cached response is tied to the analysis BLOCK.

    An API cannot answer "at block N": without that link, the first response would stay
    in the cache forever (stale data). Here, a new analysis (new block) makes the
    call again, and two reads within the same analysis return the same response (consistency).
    """

    def __init__(self, cache: DiskCache, block: int, **kw):
        super().__init__(cache, **kw)
        self.block = block

    def _cached(self, payload: dict, do_request):
        return super()._cached({**payload, "analysis_block": self.block}, do_request)


def mask_url(url: str | None) -> str:
    """Shows the host of an RPC URL without ever showing the key (often in the path)."""
    if not url:
        return "—"
    host = urlparse(url).hostname or ""
    return (host[:4] + "…" + host[-12:]) if len(host) > 18 else host


@dataclass
class Session:
    config: Config
    w3: Web3
    cache: DiskCache
    chain_id: int
    block: int              # the pinned block of this analysis
    block_timestamp: int    # its timestamp (UNIX seconds)
    ctx: Ctx                # the adapters' gateway (ctx.call, ctx.http, evidence)

    @property
    def provider(self) -> CachedHTTPProvider:
        return self.w3.provider  # type: ignore[return-value]

    @property
    def network_calls(self) -> int:
        return self.provider.network_calls

    def describe(self) -> str:
        t = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(self.block_timestamp))
        return f"chain {self.chain_id} · block #{self.block} ({t}) · RPC {mask_url(self.config.rpc_url)}"


def open_session(block: int | str = "latest") -> Session:
    """Opens a live session. `block` = "latest" (default) or a number (replay of a past state).

    Raises SessionError with a clear message if the RPC is missing or does not answer.
    """
    config = load_config(offline=False)
    if not config.rpc_url:
        raise SessionError("ETH_RPC_URL is empty: open the .env file at the repo root and paste in "
                           "the URL of your Ethereum mainnet endpoint (QuickNode, Alchemy…).")
    cache = DiskCache(LIVE_CACHE_DIR, offline=False)
    w3 = make_web3(config.rpc_url, cache)
    try:
        chain_id = check_chain(w3, config.expected_chain_id)
        pinned = resolve_snapshot_block(w3, block, offline=False)
        ts = int(w3.eth.get_block(pinned)["timestamp"])
    except Exception as e:  # an explanatory message rather than an unreadable web3 traceback
        raise SessionError(f"The RPC ({mask_url(config.rpc_url)}) is not answering correctly: {e}") from e
    ctx = Ctx(w3=w3, block=pinned, http=BlockScopedHttp(cache, pinned), config=config)
    return Session(config=config, w3=w3, cache=cache, chain_id=chain_id, block=pinned, block_timestamp=ts, ctx=ctx)
