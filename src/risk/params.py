"""STRICT loader of risk/params.yaml: no number without a status.

Three possible statuses (the front shows them with 3 different badges):
  - "sourced"     : `source: https://...` + `as_of` → read in official docs;
  - "on-chain"    : `source: onchain` + `field`      → read in graph.json / risk_inputs.json;
  - "hypothesis"  : `hypothesis: true` + `why`       → our team's own, stated choice.

Analogy: a receipt where each line must say where the price comes from. A line without
provenance = the receipt is refused (ParamError), the computation does not start.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .graphview import GraphView

STATUSES = ("source", "onchain", "hypothesis")


class ParamError(ValueError):
    pass


@dataclass
class Param:
    name: str
    value: Any
    status: str                       # source | onchain | hypothesis
    source: str | None = None         # URL (status=source) or "onchain"
    as_of: str | None = None
    field: str | None = None          # path of the on-chain value
    why: str | None = None            # justification (status=hypothesis)
    note: str | None = None
    range: list | None = None         # values tested in sensitivity

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _status_of(where: str, spec: dict) -> str:
    if spec.get("hypothesis") is True:
        if not str(spec.get("why", "")).strip():
            raise ParamError(f"{where}: hypothesis without justification (`why`)")
        return "hypothesis"
    src = spec.get("source")
    if src == "onchain":
        if not spec.get("field"):
            raise ParamError(f"{where}: onchain source without `field`")
        return "onchain"
    if isinstance(src, str) and src.startswith("https://"):
        try:
            date.fromisoformat(str(spec.get("as_of")))
        except ValueError as e:
            raise ParamError(f"{where}: documentary source without an `as_of` date") from e
        return "source"
    raise ParamError(f"{where}: no status (neither source https+as_of, nor source onchain+field, nor hypothesis+why)")


# ----------------------------------------------------------------------------- on-chain resolution
_SEL_RE = re.compile(r"^(?P<type>[a-z_]+)(\[(?P<k>[a-z_]+)=(?P<v>[^\]]+)\])?\.meta\.(?P<key>[a-z_0-9]+)$")


def resolve_field(path: str, graph: GraphView, inputs: dict) -> Any:
    """'graph:oracle[oracle_kind=x].meta.y' → value in graph.json; 'inputs:a.b' → risk_inputs.json."""
    scope, _, rest = path.partition(":")
    if scope == "inputs":
        cur: Any = inputs
        for part in rest.split("."):
            if not isinstance(cur, dict) or part not in cur:
                raise ParamError(f"on-chain field not found in risk_inputs.json: {path}")
            cur = cur[part]
        return cur
    if scope == "graph":
        m = _SEL_RE.match(rest)
        if not m:
            raise ParamError(f"invalid graph selector: {path}")
        for n in graph.of_type(m["type"]):
            if m["k"] and str(n["meta"].get(m["k"])) != m["v"]:
                continue
            if m["key"] in n["meta"]:
                return n["meta"][m["key"]]
        raise ParamError(f"on-chain field not found in graph.json: {path}")
    raise ParamError(f"unknown scope (graph: or inputs:): {path}")


def _make(where: str, name: str, spec: dict, graph: GraphView, inputs: dict) -> Param:
    status = _status_of(where, spec)
    value = spec.get("value")
    if status == "onchain":
        value = resolve_field(spec["field"], graph, inputs) if value is None else value
    elif value is None:
        raise ParamError(f"{where}: `value` missing")
    return Param(name=name, value=value, status=status,
                 source=spec.get("source"), as_of=str(spec["as_of"]) if spec.get("as_of") else None,
                 field=spec.get("field"), why=spec.get("why"), note=spec.get("note") or spec.get("method"),
                 range=spec.get("range"))


@dataclass
class Params:
    items: dict[str, Param] = field(default_factory=dict)
    events: dict[str, dict] = field(default_factory=dict)   # name → {target, kind, annual_rate: Param, ...}

    def __getitem__(self, name: str) -> Any:
        return self.items[name].value

    def get(self, name: str, default: Any = None) -> Any:
        return self.items[name].value if name in self.items else default

    def with_overrides(self, overrides: dict[str, Any]) -> "Params":
        """Copy with some values changed (sensitivity analysis)."""
        items = {k: Param(**{**v.__dict__}) for k, v in self.items.items()}
        for k, v in overrides.items():
            items[k].value = v
        return Params(items=items, events=self.events)

    def all_params(self) -> list[Param]:
        out = list(self.items.values())
        for ev_name, ev in self.events.items():
            for k in ("annual_rate", "severity", "duration_hours", "panic_depeg"):
                if k in ev:
                    out.append(ev[k])
        return out


EVENT_FIELDS = ("annual_rate", "severity", "duration_hours", "panic_depeg")


def load_params(path: str | Path, graph: GraphView, inputs: dict) -> Params:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    p = Params()
    for name, spec in raw.items():
        if name in ("version",):
            continue
        if name == "events":
            for ev_name, ev in spec.items():
                if "target" not in ev or "kind" not in ev:
                    raise ParamError(f"events.{ev_name}: `target` and `kind` are required")
                out = {"name": ev_name, "target": ev["target"], "kind": ev["kind"]}
                for k in EVENT_FIELDS:
                    if k in ev:
                        out[k] = _make(f"events.{ev_name}.{k}", f"{ev_name}.{k}", ev[k], graph, inputs)
                for k in ("annual_rate", "severity", "duration_hours"):
                    if k not in out:
                        raise ParamError(f"events.{ev_name}: `{k}` missing")
                p.events[ev_name] = out
            continue
        if name == "monte_carlo":
            for k, v in spec.items():
                p.items[f"mc_{k}"] = _make(f"monte_carlo.{k}", f"mc_{k}", v, graph, inputs)
            continue
        if not isinstance(spec, dict):
            raise ParamError(f"{name}: must be an object with a status")
        p.items[name] = _make(name, name, spec, graph, inputs)
    return p
