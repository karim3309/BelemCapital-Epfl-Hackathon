"""Ethereum RPC connection, with the disk cache plugged in AT THE PROVIDER LEVEL.

Why at the provider level? Because EVERYTHING web3.py does (eth_call, eth_getCode,
reading a block...) goes through `make_request`. Intercepting it here means no call can
"forget" the cache: it is a structural guarantee, not a discipline.

Cache rule:
  - static methods (eth_chainId)                     → always cached;
  - methods read AT A SPECIFIC BLOCK (eth_call, ...) → cached (the result never changes again);
  - any call at "latest"/"pending"                   → never cached (the result moves),
    and FORBIDDEN in offline mode. "latest" is resolved once at startup, then pinned.
  - a `revert` is a deterministic result → it is cached too (function probes rely on it).
"""
from __future__ import annotations

import itertools
import logging
import time
from typing import Any

import requests
from web3 import Web3
from web3.providers.rpc import HTTPProvider

from .cache import CacheMissError, DiskCache

log = logging.getLogger(__name__)

STATIC_METHODS = {"eth_chainId", "net_version"}
# method → index of the "block" parameter
BLOCK_PARAM_INDEX = {
    "eth_call": 1,
    "eth_getCode": 1,
    "eth_getStorageAt": 2,
    "eth_getBalance": 1,
    "eth_getBlockByNumber": 0,
}
MOVING_TAGS = {"latest", "pending", "safe", "finalized", "earliest"}


class OfflineError(RuntimeError):
    pass


class RpcError(RuntimeError):
    pass


def _is_revert(error: dict) -> bool:
    msg = str(error.get("message", "")).lower()
    return "revert" in msg or error.get("code") == 3


def _is_pinned(method: str, params: Any) -> bool:
    if method in STATIC_METHODS:
        return True
    idx = BLOCK_PARAM_INDEX.get(method)
    if idx is None or not isinstance(params, (list, tuple)) or len(params) <= idx:
        return False
    block = params[idx]
    return isinstance(block, str) and block.startswith("0x") and block not in MOVING_TAGS


class CachedHTTPProvider(HTTPProvider):
    """HTTPProvider that reads/writes data/cache/rpc/ before touching the network."""

    _ids = itertools.count(1)

    def __init__(self, endpoint_uri: str | None, cache: DiskCache, max_retries: int = 4, **kwargs):
        # Offline without a URL, use a dummy URL: it will never be called.
        super().__init__(endpoint_uri or "http://offline.invalid", request_kwargs={"timeout": 30}, **kwargs)
        self.has_endpoint = endpoint_uri is not None
        self.cache = cache
        self.max_retries = max_retries
        self.network_calls = 0

    def make_request(self, method, params):  # type: ignore[override]
        params = list(params) if isinstance(params, tuple) else params
        if _is_pinned(method, params):
            payload = {"method": method, "params": params}
            entry = self.cache.get("rpc", payload)  # raises CacheMissError when offline
            if entry is not None:
                return {"jsonrpc": "2.0", "id": next(self._ids), **entry["response"]}
            response = self._network(method, params)
            if "result" in response:
                self.cache.put("rpc", payload, {"result": response["result"]})
            elif _is_revert(response.get("error", {})):
                self.cache.put("rpc", payload, {"error": response["error"]})
            else:
                raise RpcError(self._explain(method, params, response.get("error")))
            return response
        if self.cache.offline:
            raise OfflineError(f"[offline] unpinned call not allowed: {method} {params} (the block must be a number)")
        return self._network(method, params)

    def _network(self, method, params):
        if not self.has_endpoint:
            raise OfflineError("No ETH_RPC_URL set (.env) — cannot fill the cache")
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                self.network_calls += 1
                response = super().make_request(method, params)
                err = response.get("error") if isinstance(response, dict) else None
                if err and not _is_revert(err) and self._is_transient(err) and attempt < self.max_retries:
                    raise _Transient(str(err))
                return response
            except (_Transient, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                log.warning("Transient RPC error (%s), retrying in %.0fs", e, delay)
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status not in (429, 500, 502, 503, 504) or attempt >= self.max_retries:
                    raise RpcError(self._explain(method, params, {"message": str(e)})) from e
                log.warning("RPC HTTP %s, retrying in %.0fs", status, delay)
            time.sleep(delay)
            delay *= 2
        raise RpcError(f"RPC unreachable after {self.max_retries} attempts: {method}")

    @staticmethod
    def _is_transient(err: dict) -> bool:
        msg = str(err.get("message", "")).lower()
        return any(s in msg for s in ("rate limit", "too many", "timeout", "busy", "capacity"))

    @staticmethod
    def _explain(method, params, error) -> str:
        msg = str((error or {}).get("message", error))
        hint = ""
        if any(s in msg.lower() for s in ("header not found", "missing trie node", "historical", "archive", "403")):
            hint = (" → this block is too old for this RPC (non-archive node). "
                    "Use an archive RPC, or snapshot_block: latest.")
        return f"RPC error on {method} {str(params)[:160]}: {msg}{hint}"


class _Transient(Exception):
    pass


def make_web3(rpc_url: str | None, cache: DiskCache) -> Web3:
    provider = CachedHTTPProvider(rpc_url, cache)
    return Web3(provider)


def resolve_snapshot_block(w3: Web3, snapshot: int | str, offline: bool) -> int:
    """Turns "latest" into a block number. Once per run."""
    if isinstance(snapshot, int):
        return snapshot
    if offline:
        raise OfflineError("snapshot_block: latest is impossible offline — pin a block number in config.yaml")
    # Step back 2 blocks to avoid a block not yet propagated to every node.
    return int(w3.eth.block_number) - 2


def check_chain(w3: Web3, expected_chain_id: int) -> int:
    chain_id = int(w3.eth.chain_id)
    if chain_id != expected_chain_id:
        raise RpcError(f"Wrong chain: chainId={chain_id}, expected {expected_chain_id}")
    return chain_id


__all__ = ["CachedHTTPProvider", "make_web3", "resolve_snapshot_block", "check_chain",
           "OfflineError", "RpcError", "CacheMissError"]
