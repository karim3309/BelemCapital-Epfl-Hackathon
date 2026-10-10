"""HTTP API of the StackTrace v2 backend (for the front) — FastAPI, read-only, real live data.

    PYTHONPATH=src python -m stacktrace.api                  # http://127.0.0.1:8000  (doc interactive : /docs)
    PYTHONPATH=src python -m stacktrace.api --hold-block     # demo: one block until restart (warm up, then present)

Routes (detailed contract + examples: docs/API.md):
    GET  /health                                         RPC + APIs diagnostic, current block
    GET  /holders/{holder}/pockets                       the holder's pockets (amounts proven on-chain)
    GET  /holders/{holder}/pockets/{pocket}/graph        proven dependency graph (graph.json contract)
    GET  /holders/{holder}/pockets/{pocket}/risk         STAY/EXIT verdict, expected loss, exit, p*, incidents
    POST /holders/{holder}/pockets/{pocket}/incident     incident mode {incident, severity?, p?} → decision
    GET  /holders/{holder}/book                          the whole portfolio + shared dependencies
    GET  /books                                          curator books of config.yaml (use holder = book:<key>)

`{holder}` = an address (0x…), OR "vault:0x…" (one whole vault, curator view), OR "book:<key>" (every vault of a
curator book listed in config.yaml → curator_books).

`{pocket}` = the pocket's id (e.g. morpho_vault_v2:0xD6d4…) OR its number in the list (1, 2, …).

How it works:
  - one shared live SESSION (RPC + pinned block); renewed when its block is older than SESSION_TTL_S seconds,
    or NEVER with --hold-block (demo: everything computed during the warm-up stays instant until restart);
  - every result is cached FOR THAT BLOCK: calling a route again is instant, and all responses
    of the same block are consistent with each other (each response states its `block`);
  - computations run one at a time (lock): a full analysis takes time (hundreds of RPC calls).
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .analyze import UnknownIncident, analyze_pocket, incident_decision, public, shared_dependencies
from .graph_build import build_position_graph
from .params import load_params
from .portfolio import BOOK_PREFIX, Holding, Portfolio, curator_book, scan_holder
from .session import Session, SessionError, mask_url, open_session

SESSION_TTL_S: float | None = 120     # None = hold the block until restart (--hold-block)
API_VERSION = "2.0"

app = FastAPI(title="StackTrace API", version=API_VERSION,
              description="Proven dependencies of a DeFi position, impact of an incident, STAY / EXIT decision.")
# Read-only, no private data: the front (local dev) is allowed to call the API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class _State:
    def __init__(self):
        self.lock = threading.RLock()
        self.session: Session | None = None
        self.opened_at = 0.0
        self.cache: dict[tuple, Any] = {}

    def get_session(self, fresh: bool = False) -> Session:
        expired = SESSION_TTL_S is not None and time.time() - self.opened_at > SESSION_TTL_S
        if fresh or self.session is None or expired:
            try:
                self.session = open_session()
            except SessionError as e:
                raise HTTPException(503, detail=f"RPC unavailable: {e}") from e
            self.opened_at = time.time()
            self.cache.clear()                 # new block → new results
        return self.session

    def memo(self, key: tuple, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]


STATE = _State()


def _json(x: Any) -> Any:
    """Converts numpy & co. numbers into standard JSON types."""
    return json.loads(json.dumps(x, default=float, ensure_ascii=False))


def _meta(s: Session) -> dict:
    return {"block": s.block, "block_timestamp": s.block_timestamp, "chain_id": s.chain_id}


def _portfolio(s: Session, holder: str) -> Portfolio:
    try:
        return STATE.memo(("portfolio", s.block, holder.lower()), lambda: scan_holder(s.ctx, holder, s.chain_id))
    except ValueError as e:
        raise HTTPException(400, detail=f"invalid holder (address, vault:0x… or book:<key>): {e}") from e


def _pocket(p: Portfolio, key: str) -> Holding:
    if key.isdigit() and 1 <= int(key) <= len(p.holdings):
        return p.holdings[int(key) - 1]
    for h in p.holdings:
        if h.id.lower() == key.lower():
            return h
    raise HTTPException(404, detail={"error": f"pocket \"{key}\" not found",
                                     "pockets": [{"index": i, "id": h.id, "label": h.label}
                                                 for i, h in enumerate(p.holdings, 1)]})


def _report(s: Session, holder: str, pocket: str, horizon: float | None) -> tuple[dict, Holding]:
    p = load_params()
    days = horizon or p["horizon_days"]
    port = _portfolio(s, holder)
    h = _pocket(port, pocket)

    def run():
        try:
            return analyze_pocket(s, h, port.holder, p, days)
        except NotImplementedError as e:
            raise HTTPException(422, detail=str(e)) from e
    return STATE.memo(("risk", s.block, port.holder, h.id, days), run), h


# ----------------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    # The CURRENT session (no forced renewal): a health check must not throw away the results already computed.
    with STATE.lock:
        s = STATE.get_session()
    out = {"status": "ok", "version": API_VERSION, **_meta(s), "rpc_host": mask_url(s.config.rpc_url),
           "block_age_s": round(time.time() - s.block_timestamp), "block_held": SESSION_TTL_S is None, "apis": {}}
    checks = {"morpho": lambda u: requests.post(u, json={"query": "{ __typename }"}, timeout=15),
              "pendle": lambda u: requests.get(f"{u}/v2/markets/all", params={"skip": 0, "limit": 1}, timeout=15)}
    for name, key in (("morpho", "morpho_graphql"), ("pendle", "pendle_core")):
        try:
            out["apis"][name] = "ok" if checks[name](s.config.apis[key]).ok else "error"
        except Exception as e:
            out["apis"][name] = f"unreachable ({type(e).__name__})"
    if out["apis"].get("morpho") != "ok":
        out["status"] = "degraded"
    return out


@app.get("/books")
def books() -> dict:
    """Curator books listed in config.yaml: each one is analysed with holder = "book:<key>"."""
    from discovery.config import load_config
    cfg = load_config(offline=True)
    out = []
    for key, b in (cfg.raw.get("curator_books") or {}).items():
        _, vaults = curator_book(cfg, key)
        out.append({"holder": f"{BOOK_PREFIX}{key}", "label": b.get("label", key), "vaults": len(vaults),
                    "source": " ".join(str(b.get("source", "")).split())})
    return {"books": out}


@app.get("/holders/{holder}/pockets")
def pockets(holder: str, min_usd: float = Query(1.0, ge=0)) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        port = STATE.memo(("portfolio", s.block, holder.lower(), min_usd),
                          lambda: scan_holder(s.ctx, holder, s.chain_id, min_usd))
        data = port.to_json()
        for i, h in enumerate(data["holdings"], 1):
            h["index"] = i
        return _json({**_meta(s), **data})


@app.get("/holders/{holder}/pockets/{pocket}/graph")
def graph(holder: str, pocket: str) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        port = _portfolio(s, holder)
        h = _pocket(port, pocket)

        def build():
            # if the risk analysis already built this graph, reuse it
            for k, v in STATE.cache.items():
                if k[0] == "risk" and k[1] == s.block and k[3] == h.id:
                    return v["_graph"]
            try:
                return build_position_graph(s, h, port.holder)[0]
            except NotImplementedError as e:
                raise HTTPException(422, detail=str(e)) from e
        return _json({**_meta(s), "pocket": {"id": h.id, "label": h.label, "kind": h.kind},
                      "graph": STATE.memo(("graph", s.block, port.holder, h.id), build)})


@app.get("/holders/{holder}/pockets/{pocket}/risk")
def risk(holder: str, pocket: str, horizon: float | None = Query(None, gt=0, le=365)) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        r, _ = _report(s, holder, pocket, horizon)
        return _json({**_meta(s), **public(r)})


class IncidentIn(BaseModel):
    incident: str = Field(..., description="id (or start of id) of an incident listed by /risk → incidents[].id")
    severity: float | None = Field(None, ge=0, le=1, description="severity 0–1 (default: middle of the range)")
    p: float | None = Field(None, ge=0, le=1, description="probability estimated by the manager (default: hypothesis)")
    horizon: float | None = Field(None, gt=0, le=365)


@app.post("/holders/{holder}/pockets/{pocket}/incident")
def incident(holder: str, pocket: str, body: IncidentIn) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        r, h = _report(s, holder, pocket, body.horizon)
        try:
            inc = incident_decision(r, load_params(), body.incident, body.severity, body.p)
        except UnknownIncident:
            raise HTTPException(404, detail={"error": f"incident \"{body.incident}\" unknown",
                                             "incidents": [x["id"] for x in r["incidents"]]})
        return _json({**_meta(s), "pocket": r["pocket"], "baseline_decision": r["decision"], "incident_mode": inc})


@app.get("/holders/{holder}/book")
def book(holder: str, horizon: float | None = Query(None, gt=0, le=365)) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        port = _portfolio(s, holder)
        reports, skipped = [], []
        for h in port.holdings:
            try:
                reports.append(_report(s, holder, h.id, horizon)[0])
            except HTTPException as e:
                skipped.append({"id": h.id, "label": h.label, "reason": e.detail})
        summary = [{"index": i, "id": r["pocket"]["id"], "label": r["pocket"]["label"], "kind": r["pocket"]["kind"],
                    "value_usd": r["pocket"]["value_usd"], "share_of_book": r["pocket"]["share_of_book"],
                    "verdict": r["decision"]["verdict"], "exit_fraction": r["decision"]["exit_fraction"],
                    "expected_loss_usd": r["monte_carlo"]["expected_loss_usd"], "exit_cost_usd": r["exit"]["cost_full_usd"],
                    "exit_fraction_now": r["exit"]["f_max_now"], "sentence": r["decision"]["sentence"],
                    "top_risk": next((x for x in r["incidents"] if x["loss_if_incident_usd"] > 0), None)}
                   for i, r in enumerate(reports, 1)]
        return _json({**_meta(s), "holder": port.holder,
                      "total_value_usd": sum(r["pocket"]["value_usd"] or 0 for r in reports),
                      "expected_loss_usd": sum(r["monte_carlo"]["expected_loss_usd"] for r in reports),
                      "pockets": summary, "skipped": skipped, "shared_dependencies": shared_dependencies(reports)})


def main(argv: list[str] | None = None) -> None:
    import argparse

    import uvicorn
    global SESSION_TTL_S
    ap = argparse.ArgumentParser(description="StackTrace API (live, read-only).")
    ap.add_argument("--hold-block", action="store_true",
                    help="keep the same block until restart: warm up before a demo, then every screen is instant")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    if a.hold_block:
        SESSION_TTL_S = None
        print("Block held until restart (--hold-block): warm it up with  python -m stacktrace.warmup book:rockawayx")
    uvicorn.run(app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
