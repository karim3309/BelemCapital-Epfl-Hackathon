"""Disk cache of ALL network calls (RPC and API) — a strict CLAUDE.md requirement.

Principle:
  - each request is described by a dict (e.g. {"method": "eth_call", "params": [...]});
  - a stable key is derived from it: sha256 of the sorted JSON → same request = same file;
  - the response is written to data/cache/<namespace>/<first 2 hex>/<key>.json,
    TOGETHER WITH the original request (human-readable → it is also evidence).

These files are committed to git: the demo replays everything without network (offline mode).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CacheMissError(RuntimeError):
    """Raised in offline mode when a response is not in the cache."""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def cache_key(payload: dict) -> str:
    # 32 hex (128 bits): unique enough, and keeps paths short on Windows.
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()[:32]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    by_namespace: dict = field(default_factory=dict)

    def bump(self, namespace: str, what: str) -> None:
        setattr(self, what, getattr(self, what) + 1)
        ns = self.by_namespace.setdefault(namespace, {"hits": 0, "misses": 0, "writes": 0})
        ns[what] += 1


class DiskCache:
    def __init__(self, root: Path, offline: bool = False):
        self.root = Path(root)
        self.offline = offline
        self.stats = CacheStats()

    def _path(self, namespace: str, key: str) -> Path:
        path = (self.root / namespace / key[:2] / f"{key}.json").resolve()
        if os.name == "nt" and not str(path).startswith("\\\\?\\"):
            # Windows limits paths to 260 characters (MAX_PATH): a repo cloned into a deep folder
            # would make the cache "invisible". The \\?\ prefix lifts that limit.
            path = Path("\\\\?\\" + str(path))
        return path

    def get(self, namespace: str, payload: dict) -> dict | None:
        """Returns the {"request", "response", "fetched_at"} entry or None."""
        path = self._path(namespace, cache_key(payload))
        if path.exists():
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
            self.stats.bump(namespace, "hits")
            return entry
        self.stats.bump(namespace, "misses")
        if self.offline:
            raise CacheMissError(
                f"[offline] no cache for {namespace} {canonical_json(payload)[:200]} — "
                "run once online (ETH_RPC_URL) to fill it"
            )
        return None

    def put(self, namespace: str, payload: dict, response: Any) -> dict:
        entry = {
            "request": payload,
            "response": response,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = self._path(namespace, cache_key(payload))
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write a temporary file then rename it
        # → never a half-written cache file if the script is interrupted.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:   # LF everywhere (Windows included)
            json.dump(entry, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
        self.stats.bump(namespace, "writes")
        return entry
