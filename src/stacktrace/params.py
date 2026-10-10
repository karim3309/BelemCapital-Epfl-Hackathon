"""Chargeur STRICT de risk/params_v2.yaml : aucun chiffre sans statut (source officielle ou hypothèse assumée).

Chaque feuille « paramètre » doit avoir `value` ET soit (`source` https + `as_of`), soit (`hypothesis: true` + `why`).
On garde le statut à côté de la valeur : le rapport final liste toutes les hypothèses utilisées.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from discovery.config import REPO_ROOT

PARAMS_FILE = REPO_ROOT / "risk" / "params_v2.yaml"


class ParamsError(ValueError):
    pass


@dataclass
class Param:
    path: str
    value: Any
    status: str                 # "source" | "hypothesis"
    why: str
    range: list | None = None


@dataclass
class Params:
    raw: dict
    items: dict[str, Param] = field(default_factory=dict)

    def __getitem__(self, path: str) -> Any:
        return self.items[path].value

    def get(self, path: str, default=None):
        return self.items[path].value if path in self.items else default

    def override(self, path: str, value: Any) -> "Params":
        """Copie avec une valeur remplacée (analyse de sensibilité)."""
        new = Params(self.raw, dict(self.items))
        p = self.items[path]
        new.items[path] = Param(p.path, value, p.status, p.why, p.range)
        return new

    def listing(self) -> list[dict]:
        return [{"param": p.path, "value": p.value, "status": p.status, "why": p.why, "range": p.range}
                for p in self.items.values()]


def _is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node


def _check(path: str, leaf: dict) -> Param:
    if leaf.get("hypothesis") is True:
        if not str(leaf.get("why", "")).strip():
            raise ParamsError(f"{path} : hypothèse sans `why`")
        return Param(path, leaf["value"], "hypothesis", leaf["why"], leaf.get("range"))
    src = str(leaf.get("source", ""))
    if src.startswith("https://") and leaf.get("as_of"):
        return Param(path, leaf["value"], "source", f"{src} (relevé le {leaf['as_of']})", leaf.get("range"))
    raise ParamsError(f"{path} : ni `source` https + `as_of`, ni `hypothesis: true` + `why` → refusé")


def load_params(path: Path = PARAMS_FILE) -> Params:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    p = Params(raw)

    def walk(node: Any, prefix: str) -> None:
        if _is_leaf(node):
            p.items[prefix] = _check(prefix, node)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("version", "applies_to", "speed", "oracle_tracks", "oracle_tracks_why"):
                    continue                     # descriptions / options qualitatives, pas des chiffres
                walk(v, f"{prefix}.{k}" if prefix else k)

    walk(raw, "")
    for name, ev in (raw.get("events") or {}).items():
        if ev.get("speed") not in ("gradual", "jump"):
            raise ParamsError(f"events.{name}.speed doit valoir gradual ou jump")
    return p
