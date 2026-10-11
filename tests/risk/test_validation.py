"""Counterfactual replays on real price paths: the view served to the front, and the copy recorded offline."""
import json

from fastapi.testclient import TestClient

from risk.validation import OUT, load
from stacktrace import api


def test_recorded_validation_is_up_to_date():
    recorded = json.loads(OUT.read_text(encoding="utf-8"))
    assert recorded == json.loads(json.dumps(load(), ensure_ascii=False)), \
        "docs/api_examples/validation.json is stale: run python -m risk.validation"


def test_oct_2025_replay_shows_that_the_oracle_source_decides():
    oct25 = next(r for r in load()["replays"] if r["id"] == "R-OCT2025")
    by_design = {d["design"]: d for d in oct25["designs"]}
    assert not by_design["Real meta-oracle (fixed primary + Chainlink fallback)"]["liquidated"]
    assert not by_design["Market oracle on Chainlink USDe/USD"]["liquidated"]
    assert any(d["liquidated"] for name, d in by_design.items() if "Binance" in name)
    assert oct25["offchain"]["evidence_url"].startswith("https://")
    assert "opposite outcomes" in oct25["takeaway"]


def test_validation_route_needs_no_rpc(monkeypatch):
    def no_rpc():
        raise AssertionError("/validation must not open an RPC session")
    monkeypatch.setattr(api, "open_session", no_rpc)
    api.STATE.__init__()
    r = TestClient(api.app).get("/validation")
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["replays"]] == ["R-OCT2025", "R-FEB2025"]
