"""Validator of output/risk_report.json and output/risk_grid.json (like discovery/validate.py).

It checks that the report is COMPLETE and HONEST:
  - every section of the risk sheet is there, with no NaN or infinity;
  - every parameter has a status (source / onchain / hypothesis);
  - every contagion path is made of edges that EXIST in graph.json, with the same evidence
    (no evidence lost or invented along the way);
  - verdicts in {STAY, PARTIAL, EXIT}, probabilities in [0, 1], p* ≥ 0.
"""
from __future__ import annotations

import json
import math
import sys

from .graphview import GraphView

VERDICTS = {"STAY", "PARTIAL", "EXIT"}
REQUIRED = ("contract_version", "snapshot", "position", "headline", "baseline", "exit_cost", "monte_carlo",
            "scenarios", "replays", "sensitivity", "calibration", "params", "confidence")


def _walk_numbers(obj, path="$"):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            yield path
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_numbers(v, f"{path}[{i}]")


def validate_report(report: dict, grid: dict, gv: GraphView) -> list[str]:
    errors: list[str] = []
    err = errors.append
    for k in REQUIRED:
        if k not in report:
            err(f"missing section: {k}")
    if errors:
        return errors
    for p in _walk_numbers(report):
        err(f"invalid number (NaN/inf): {p}")
    for p in report["params"]:
        st = p.get("status")
        if st not in ("source", "onchain", "hypothesis"):
            err(f"parameter without status: {p.get('name')}")
        if st == "hypothesis" and not p.get("why"):
            err(f"hypothesis without justification: {p['name']}")
        if st == "source" and not (str(p.get("source", "")).startswith("https://") and p.get("as_of")):
            err(f"sourced parameter without URL/date: {p['name']}")
    h = report["headline"]
    if h["verdict"] not in VERDICTS:
        err(f"invalid main verdict: {h['verdict']}")
    if h["p_star"] is not None and h["p_star"] < 0:
        err("negative p*")
    if not h.get("sentence"):
        err("missing explanatory sentence")
    for sc in report["scenarios"]:
        d = sc["decision"]
        if d["verdict"] not in VERDICTS:
            err(f"{sc['id']}: invalid verdict")
        if not 0 <= d["p_default"] <= 1:
            err(f"{sc['id']}: p_default outside [0,1]")
        for path in sc["contagion_paths"]:
            for e in path["edges"]:
                real = gv.edge(e["from"], e["to"], e["type"])
                if real is None:
                    err(f"{sc['id']}: edge missing from graph.json {e['from']} -{e['type']}-> {e['to']}")
                elif real["evidence"] != e["evidence"] or real["source"] != e["source"]:
                    err(f"{sc['id']}: evidence altered on {e['from']} -{e['type']}-> {e['to']}")
    for t in report["monte_carlo"].get("top_paths", []):
        if t.get("path"):
            for e in t["path"]["edges"]:
                if gv.edge(e["from"], e["to"], e["type"]) is None:
                    err(f"top_paths: missing edge {e['from']} -> {e['to']}")
    mc = report["monte_carlo"]
    if not mc["var95_usd"] <= mc["var99_usd"] + 1e-6:
        err("VaR95 > VaR99: inconsistent")
    # grille
    for k in ("prices", "durations_hours", "cells", "p_grid"):
        if k not in grid:
            err(f"risk_grid: missing key {k}")
    if not errors:
        if len(grid["cells"]) != len(grid["prices"]) or any(len(r) != len(grid["durations_hours"]) for r in grid["cells"]):
            err("risk_grid: inconsistent dimensions")
        for row in grid["cells"]:
            for c in row:
                if len(c["fraction_by_p"]) != len(grid["p_grid"]):
                    err("risk_grid: fraction_by_p incomplete")
                    break
    return errors


def main(argv: list[str] | None = None) -> int:
    from discovery.config import REPO_ROOT
    from discovery.console import utf8_console
    utf8_console()
    report = json.loads((REPO_ROOT / "output" / "risk_report.json").read_text(encoding="utf-8"))
    grid = json.loads((REPO_ROOT / "output" / "risk_grid.json").read_text(encoding="utf-8"))
    errors = validate_report(report, grid, GraphView.load(REPO_ROOT / "output" / "graph.json"))
    if errors:
        print(f"✗ {len(errors)} error(s)", *errors, sep="\n  - ")
        return 1
    print("✓ risk_report.json and risk_grid.json are compliant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
