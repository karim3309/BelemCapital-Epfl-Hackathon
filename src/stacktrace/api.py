"""API HTTP du backend StackTrace v2 (pour le front) — FastAPI, lecture seule, données réelles en ligne.

    PYTHONPATH=src python -m stacktrace.api                  # http://127.0.0.1:8000  (doc interactive : /docs)

Routes (contrat détaillé + exemples : docs/API.md) :
    GET  /health                                         diagnostic RPC + APIs, bloc courant
    GET  /holders/{holder}/pockets                       les poches du détenteur (montants prouvés on-chain)
    GET  /holders/{holder}/pockets/{pocket}/graph        graphe de dépendances prouvé (contrat graph.json)
    GET  /holders/{holder}/pockets/{pocket}/risk         verdict STAY/EXIT, perte attendue, sortie, p*, incidents
    POST /holders/{holder}/pockets/{pocket}/incident     mode incident {incident, severity?, p?} → décision
    GET  /holders/{holder}/book                          tout le portefeuille + dépendances partagées

`{pocket}` = id de la poche (ex. morpho_vault_v2:0xD6d4…) OU son numéro dans la liste (1, 2, …).

Fonctionnement :
  - une SESSION en ligne partagée (RPC + bloc figé) ; renouvelée quand son bloc a plus de SESSION_TTL_S secondes ;
  - tous les résultats sont mis en cache POUR CE BLOC : rappeler une route est instantané, et toutes les réponses
    d'un même bloc sont cohérentes entre elles (chaque réponse indique son `block`) ;
  - les calculs sont faits un par un (verrou) : une analyse complète prend du temps (centaines d'appels RPC).
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
from .portfolio import Holding, Portfolio, scan_holder
from .session import Session, SessionError, mask_url, open_session

SESSION_TTL_S = 120
API_VERSION = "2.0"

app = FastAPI(title="StackTrace API", version=API_VERSION,
              description="Dépendances prouvées d'une position DeFi, impact d'un incident, décision STAY / EXIT.")
# Lecture seule, aucune donnée privée : on autorise le front (dev local) à appeler l'API depuis le navigateur.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class _State:
    def __init__(self):
        self.lock = threading.RLock()
        self.session: Session | None = None
        self.opened_at = 0.0
        self.cache: dict[tuple, Any] = {}

    def get_session(self, fresh: bool = False) -> Session:
        if fresh or self.session is None or time.time() - self.opened_at > SESSION_TTL_S:
            try:
                self.session = open_session()
            except SessionError as e:
                raise HTTPException(503, detail=f"RPC indisponible : {e}") from e
            self.opened_at = time.time()
            self.cache.clear()                 # nouveau bloc → nouveaux résultats
        return self.session

    def memo(self, key: tuple, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]


STATE = _State()


def _json(x: Any) -> Any:
    """Convertit les nombres numpy & co. en types JSON standard."""
    return json.loads(json.dumps(x, default=float, ensure_ascii=False))


def _meta(s: Session) -> dict:
    return {"block": s.block, "block_timestamp": s.block_timestamp, "chain_id": s.chain_id}


def _portfolio(s: Session, holder: str) -> Portfolio:
    try:
        return STATE.memo(("portfolio", s.block, holder.lower()), lambda: scan_holder(s.ctx, holder, s.chain_id))
    except ValueError as e:
        raise HTTPException(400, detail=f"adresse invalide : {e}") from e


def _pocket(p: Portfolio, key: str) -> Holding:
    if key.isdigit() and 1 <= int(key) <= len(p.holdings):
        return p.holdings[int(key) - 1]
    for h in p.holdings:
        if h.id.lower() == key.lower():
            return h
    raise HTTPException(404, detail={"error": f"poche « {key} » introuvable",
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
    with STATE.lock:
        s = STATE.get_session(fresh=True)
    out = {"status": "ok", "version": API_VERSION, **_meta(s), "rpc_host": mask_url(s.config.rpc_url),
           "block_age_s": round(time.time() - s.block_timestamp), "apis": {}}
    checks = {"morpho": lambda u: requests.post(u, json={"query": "{ __typename }"}, timeout=15),
              "pendle": lambda u: requests.get(f"{u}/v2/markets/all", params={"skip": 0, "limit": 1}, timeout=15)}
    for name, key in (("morpho", "morpho_graphql"), ("pendle", "pendle_core")):
        try:
            out["apis"][name] = "ok" if checks[name](s.config.apis[key]).ok else "erreur"
        except Exception as e:
            out["apis"][name] = f"injoignable ({type(e).__name__})"
    if out["apis"].get("morpho") != "ok":
        out["status"] = "degraded"
    return out


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
            # si l'analyse de risque a déjà construit ce graphe, on le réutilise
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
    incident: str = Field(..., description="id (ou début d'id) d'un incident listé par /risk → incidents[].id")
    severity: float | None = Field(None, ge=0, le=1, description="sévérité 0–1 (défaut : milieu de la plage)")
    p: float | None = Field(None, ge=0, le=1, description="probabilité estimée par le manager (défaut : hypothèse)")
    horizon: float | None = Field(None, gt=0, le=365)


@app.post("/holders/{holder}/pockets/{pocket}/incident")
def incident(holder: str, pocket: str, body: IncidentIn) -> dict:
    with STATE.lock:
        s = STATE.get_session()
        r, h = _report(s, holder, pocket, body.horizon)
        try:
            inc = incident_decision(r, load_params(), body.incident, body.severity, body.p)
        except UnknownIncident:
            raise HTTPException(404, detail={"error": f"incident « {body.incident} » inconnu",
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


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
