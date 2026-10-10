"""API v2 — routes, error codes and cache, WITHOUT network (session, scan and analysis replaced by fakes)."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from stacktrace import api
from stacktrace.analyze import UnknownIncident
from stacktrace.portfolio import Holding, Portfolio

HOLDER = "0x" + "ab" * 20


def holding(i: int, kind="morpho_vault_v2") -> Holding:
    return Holding(id=f"{kind}:0x{i:040x}", kind=kind, label=f"Pocket {i}", protocol="morpho", chain="ethereum",
                   address=f"0x{i:040x}", market_id=None, asset_symbol="USDC", asset_address="0x" + "0" * 40,
                   amount=100.0, price_usd=1.0, value_usd=100.0 * i, price_source="test", share_of_book=0.5)


@pytest.fixture()
def client(monkeypatch):
    calls = {"analyze": 0}
    session = SimpleNamespace(block=123, block_timestamp=1_700_000_000, chain_id=1, ctx=None,
                              config=SimpleNamespace(rpc_url="https://x.test/KEY", apis={}))
    monkeypatch.setattr(api, "open_session", lambda: session)
    monkeypatch.setattr(api, "scan_holder", lambda ctx, holder, chain_id, min_usd=1.0: Portfolio(
        HOLDER, "ethereum", 123, 1_700_000_000, "test", [holding(1), holding(2)], [], []))

    def fake_analyze(s, h, holder, p, days, *a, **k):
        calls["analyze"] += 1
        return {"pocket": {"id": h.id, "label": h.label, "kind": h.kind, "value_usd": h.value_usd, "share_of_book": 0.5},
                "decision": {"verdict": "STAY", "exit_fraction": 0.0, "sentence": "STAY — test"},
                "monte_carlo": {"expected_loss_usd": 1.0}, "exit": {"cost_full_usd": 2.0, "f_max_now": 1.0},
                "incidents": [{"id": "rwa_credit_event:x", "loss_if_incident_usd": 10.0}],
                "_graph": {"position": {"id": "p"}, "nodes": [], "edges": []}, "_events": [], "_exit": None,
                "_holding": h}
    monkeypatch.setattr(api, "analyze_pocket", fake_analyze)
    api.STATE.__init__()                      # fresh state for every test
    return TestClient(api.app), calls


def test_pockets_are_indexed(client):
    c, _ = client
    r = c.get(f"/holders/{HOLDER}/pockets")
    assert r.status_code == 200
    d = r.json()
    assert d["block"] == 123 and [h["index"] for h in d["holdings"]] == [1, 2]


def test_risk_by_index_or_id_and_cached_per_block(client):
    c, calls = client
    assert c.get(f"/holders/{HOLDER}/pockets/1/risk").json()["decision"]["verdict"] == "STAY"
    pid = holding(1).id
    r = c.get(f"/holders/{HOLDER}/pockets/{pid}/risk").json()
    assert r["pocket"]["id"] == pid and "_graph" not in r          # internal objects never exposed
    assert calls["analyze"] == 1                                    # 2nd call: block cache


def test_unknown_pocket_is_404_with_the_list(client):
    c, _ = client
    r = c.get(f"/holders/{HOLDER}/pockets/99/risk")
    assert r.status_code == 404 and len(r.json()["detail"]["pockets"]) == 2


def test_incident_unknown_is_404_and_known_returns_decision(client, monkeypatch):
    c, _ = client

    def fake_incident(report, p, incident, severity=None, p_incident=None):
        if incident != "rwa":
            raise UnknownIncident(incident)
        return {"verdict": "EXIT", "p_star": 0.01, "incident": "rwa_credit_event:x"}
    monkeypatch.setattr(api, "incident_decision", fake_incident)
    bad = c.post(f"/holders/{HOLDER}/pockets/1/incident", json={"incident": "nope"})
    assert bad.status_code == 404 and bad.json()["detail"]["incidents"] == ["rwa_credit_event:x"]
    ok = c.post(f"/holders/{HOLDER}/pockets/1/incident", json={"incident": "rwa", "severity": 0.3, "p": 0.2}).json()
    assert ok["incident_mode"]["verdict"] == "EXIT" and ok["baseline_decision"]["verdict"] == "STAY"


def test_invalid_severity_is_rejected(client):
    c, _ = client
    r = c.post(f"/holders/{HOLDER}/pockets/1/incident", json={"incident": "rwa", "severity": 2})
    assert r.status_code == 422


def test_book_aggregates_all_pockets(client):
    c, _ = client
    d = c.get(f"/holders/{HOLDER}/book").json()
    assert len(d["pockets"]) == 2 and d["total_value_usd"] == 300 and d["expected_loss_usd"] == 2.0


def test_rpc_down_is_503(monkeypatch):
    def boom():
        raise api.SessionError("ETH_RPC_URL is empty")
    monkeypatch.setattr(api, "open_session", boom)
    api.STATE.__init__()
    r = TestClient(api.app).get(f"/holders/{HOLDER}/pockets")
    assert r.status_code == 503 and "RPC" in r.json()["detail"]
