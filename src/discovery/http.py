"""Appels HTTP (APIs Morpho / Pendle) passant par le cache disque data/cache/http/.

Différence avec le RPC : une API ne sait pas répondre « au bloc N ». La réponse cachée
porte donc sa date (`fetched_at`) et c'est elle qu'on cite comme preuve.
On n'utilise une API que pour LOCALISER quelque chose ; dès que possible, on re-prouve on-chain.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .cache import DiskCache

log = logging.getLogger(__name__)


class CachedHttp:
    def __init__(self, cache: DiskCache, timeout: int = 120, max_retries: int = 3):
        self.cache = cache
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "StackTrace-discovery/0.1 (hackathon Belem DeFi Risk)"

    def get_json(self, url: str, params: dict | None = None) -> tuple[Any, str]:
        """Renvoie (json, fetched_at)."""
        payload = {"method": "GET", "url": url, "params": params or {}}
        return self._cached(payload, lambda: self.session.get(url, params=params, timeout=self.timeout))

    def post_json(self, url: str, body: dict) -> tuple[Any, str]:
        payload = {"method": "POST", "url": url, "body": body}
        return self._cached(payload, lambda: self.session.post(url, json=body, timeout=self.timeout))

    def _cached(self, payload: dict, do_request) -> tuple[Any, str]:
        entry = self.cache.get("http", payload)  # lève CacheMissError en offline
        if entry is None:
            data = self._with_retries(do_request)
            entry = self.cache.put("http", payload, data)
        return entry["response"], entry["fetched_at"]

    def _with_retries(self, do_request) -> Any:
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                r = do_request()
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.exceptions.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                return r.json()
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                    requests.exceptions.HTTPError) as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                retriable = status is None or status == 429 or status >= 500
                if not retriable or attempt >= self.max_retries:
                    raise
                log.warning("API transitoire (%s), nouvel essai dans %.0fs", e, delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")
