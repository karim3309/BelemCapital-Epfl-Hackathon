"""Cache disque de TOUS les appels réseau (RPC et API) — contrainte stricte de CLAUDE.md.

Principe :
  - chaque requête est décrite par un dictionnaire (ex. {"method": "eth_call", "params": [...]}) ;
  - on en tire une clé stable : sha256 du JSON trié  → même requête = même fichier ;
  - la réponse est écrite dans data/cache/<namespace>/<2 premiers hex>/<clé>.json,
    AVEC la requête d'origine (lisible par un humain → c'est aussi une preuve).

Ces fichiers sont commités dans git : la démo rejoue tout sans réseau (mode offline).
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
    """Levée en mode offline quand une réponse n'est pas dans le cache."""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def cache_key(payload: dict) -> str:
    # 32 hex (128 bits) : largement unique, et garde les chemins courts sous Windows.
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
        return self.root / namespace / key[:2] / f"{key}.json"

    def get(self, namespace: str, payload: dict) -> dict | None:
        """Renvoie l'entrée {"request", "response", "fetched_at"} ou None."""
        path = self._path(namespace, cache_key(payload))
        if path.exists():
            with open(path, encoding="utf-8") as f:
                entry = json.load(f)
            self.stats.bump(namespace, "hits")
            return entry
        self.stats.bump(namespace, "misses")
        if self.offline:
            raise CacheMissError(
                f"[offline] pas de cache pour {namespace} {canonical_json(payload)[:200]} — "
                "relancez une fois en ligne (ETH_RPC_URL) pour le remplir"
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
        # Écriture atomique : on écrit un fichier temporaire puis on le renomme
        # → jamais de fichier de cache à moitié écrit si le script est interrompu.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:   # LF partout (Windows compris)
            json.dump(entry, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
        self.stats.bump(namespace, "writes")
        return entry
