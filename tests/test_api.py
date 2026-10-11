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


def test_books_lists_the_curator_books_of_the_config():
    r = TestClient(api.app).get("/books")
    assert r.status_code == 200
    rockawayx = next(b for b in r.json()["books"] if b["holder"] == "book:rockawayx")
    assert rockawayx["vaults"] >= 1 and "dune.com" in rockawayx["source"]


def test_recorder_writes_every_route_of_a_holder(client, monkeypatch, tmp_path):
    from stacktrace import record
    monkeypatch.setattr(record, "RECORDINGS", tmp_path)
    monkeypatch.setattr(api, "incident_decision", lambda report, p, incident, severity=None, p_incident=None:
                        {"verdict": "STAY", "p_star": 0.5, "incident": incident, "p_used": p_incident})
    assert record.record(HOLDER) == 0
    folder = tmp_path / HOLDER.lower()
    names = sorted(f.name for f in folder.iterdir())
    assert names == ["book.json", "graph_1.json", "graph_2.json", "incident.json", "pockets.json",
                     "risk_1.json", "risk_2.json"]
    import json
    assert json.loads((folder / "incident.json").read_text())["incident_mode"]["p_used"] == record.INCIDENT_EXAMPLE_P


def test_health_keeps_the_results_already_computed(client):
    c, calls = client
    c.get(f"/holders/{HOLDER}/pockets/1/risk")
    c.get("/health")                                     # used to force a new session and empty the cache
    c.get(f"/holders/{HOLDER}/pockets/1/risk")
    assert calls["analyze"] == 1


def test_hold_block_keeps_the_session_beyond_the_ttl(client, monkeypatch):
    c, calls = client
    monkeypatch.setattr(api, "SESSION_TTL_S", None)
    c.get(f"/holders/{HOLDER}/pockets/1/risk")
    api.STATE.opened_at -= 3600                          # one hour later
    c.get(f"/holders/{HOLDER}/pockets/1/risk")
    assert calls["analyze"] == 1 and c.get("/health").json()["block_held"] is True


def test_warmup_calls_every_route_of_the_deck(client, monkeypatch):
    from stacktrace import warmup
    c, calls = client
    seen = []

    def fake_get(url, timeout=None):
        path = url.replace("http://127.0.0.1:8000", "")
        seen.append(path)
        return c.get(path)
    monkeypatch.setattr(warmup.requests, "get", fake_get)
    assert warmup.warmup(HOLDER) == 0
    assert any(p.endswith("/book") for p in seen) and sum(p.endswith("/graph") for p in seen) == 2
    assert calls["analyze"] == 2                         # each pocket analysed once, then served from the cache


# ------------------------------------------------------------------ audit 2026-10-11: robustness before the live demo
def test_one_failing_pocket_is_skipped_not_a_500_for_the_whole_book(client, monkeypatch):
    c, _ = client
    real = api.analyze_pocket

    def flaky(s, h, holder, p, days, *a, **k):
        if h.label == "Pocket 2":
            raise RuntimeError("429 Client Error: Too Many Requests for url: https://x.rpc-provider.example/SECRETKEY/")
        return real(s, h, holder, p, days, *a, **k)
    monkeypatch.setattr(api, "analyze_pocket", flaky)
    r = c.get(f"/holders/{HOLDER}/book")
    assert r.status_code == 200
    d = r.json()
    assert [p["label"] for p in d["pockets"]] == ["Pocket 1"]
    assert d["skipped"][0]["label"] == "Pocket 2" and "SECRETKEY" not in d["skipped"][0]["reason"]


def test_invalid_holder_is_400(client, monkeypatch):
    c, _ = client

    def bad(ctx, holder, chain_id, min_usd=1.0):
        raise ValueError(f"not an address: {holder!r}")
    monkeypatch.setattr(api, "scan_holder", bad)
    assert c.get("/holders/0xNOT_AN_ADDRESS/pockets").status_code == 400


def test_graph_never_serves_another_holders_graph(client, monkeypatch):
    c, _ = client
    c.get(f"/holders/{HOLDER}/pockets/1/risk")                       # graph of HOLDER cached by the analysis
    other = "0x" + "cd" * 20
    built = []
    monkeypatch.setattr(api, "build_position_graph",
                        lambda s, h, holder: built.append(holder) or ({"position": {"id": holder}, "nodes": [], "edges": []}, None))
    monkeypatch.setattr(api, "scan_holder", lambda ctx, holder, chain_id, min_usd=1.0: Portfolio(
        other, "ethereum", 123, 1_700_000_000, "test", [holding(1)], [], []))
    r = c.get(f"/holders/{other}/pockets/1/graph").json()
    assert built == [other] and r["graph"]["position"]["id"] == other


def test_cached_answers_do_not_wait_for_a_running_computation(client):
    import threading
    c, _ = client
    c.get(f"/holders/{HOLDER}/pockets/1/risk")                       # cached
    busy, release = threading.Event(), threading.Event()

    def long_job():                                                  # simulates a cold /book holding the lock
        with api.STATE.lock:
            busy.set()
            release.wait(5)
    t = threading.Thread(target=long_job)
    t.start()
    busy.wait(2)
    try:
        assert c.get(f"/holders/{HOLDER}/pockets/1/risk").status_code == 200
        assert c.get(f"/holders/{HOLDER}/pockets/1/graph").status_code == 200
        assert c.get("/health").json()["block"] == 123                # the front's "API reachable?" check too
    finally:
        release.set()
        t.join()


def test_unexpected_error_is_a_json_500_without_the_key(client, monkeypatch):
    c, _ = client

    def boom(*a, **k):
        raise RuntimeError("HTTPSConnectionPool(host='x.rpc-provider.example', port=443): Max retries exceeded with url: /SECRETKEY/")
    monkeypatch.setattr(api, "analyze_pocket", boom)
    r = TestClient(api.app, raise_server_exceptions=False).get(f"/holders/{HOLDER}/pockets/1/risk")
    assert r.status_code == 500 and "SECRETKEY" not in r.text
