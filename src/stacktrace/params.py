"""STRICT loader of risk/params_v2.yaml: no number without a status (official source or stated hypothesis).

Each "parameter" leaf must have `value` AND either (`source` https + `as_of`), or (`hypothesis: true` + `why`).
The status is kept next to the value: the final report lists every hypothesis used.
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
        """Copy with one value replaced (sensitivity analysis)."""
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
            raise ParamsError(f"{path}: hypothesis without `why`")
        return Param(path, leaf["value"], "hypothesis", leaf["why"], leaf.get("range"))
    src = str(leaf.get("source", ""))
    if src.startswith("https://") and leaf.get("as_of"):
        return Param(path, leaf["value"], "source", f"{src} (as of {leaf['as_of']})", leaf.get("range"))
    raise ParamsError(f"{path}: neither `source` https + `as_of`, nor `hypothesis: true` + `why` → refused")


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
                    continue                     # descriptions / qualitative options, not numbers
                walk(v, f"{prefix}.{k}" if prefix else k)

    walk(raw, "")
    for name, ev in (raw.get("events") or {}).items():
        if ev.get("speed") not in ("gradual", "jump"):
            raise ParamsError(f"events.{name}.speed must be gradual or jump")
    return p
