"""Risk engine fixtures: the REAL graph of position A (committed) and a small hand-made graph."""
import pytest

from risk.graphview import GraphView
from risk.run import build_engine


@pytest.fixture(scope="session")
def engine():
    return build_engine()


class P(dict):
    """Minimal parameters for the unit tests (same interface as Params: p['name'])."""


def tiny_params(**over):
    base = {"custodian_backing_share": 1 / 3, "exchange_exposure_share": 0.02,
            "meta_oracle_deviation_threshold": 0.0075, "meta_oracle_challenge_timelock_seconds": 57600,
            "meta_oracle_healing_timelock_seconds": 86400, "challenger_delay_hours": 0}
    base.update(over)
    return P(base)


def _n(id_, type_, meta=None):
    return {"id": id_, "type": type_, "label": id_, "address": None, "chain": "ethereum", "meta": meta or {}}


def _e(a, b, t):
    return {"from": a, "to": b, "type": t, "weight": 1.0, "source": "onchain", "evidence": f"test {a}->{b} @ 0x{'0'*40} #1"}


@pytest.fixture
def tiny_graph():
    """PT → SY → sUSDe → USDe; issuers Pendle / Ethena; Ethena → custodian + exchange."""
    nodes = [_n(x, "asset", {"asset_kind": k}) for x, k in
             (("pt", "pendle_pt"), ("sy", "pendle_sy"), ("susde", "erc4626_vault"), ("usde", "erc20"))]
    nodes += [_n("pendle", "issuer"), _n("ethena", "issuer"),
              _n("custody", "offchain_counterparty", {"role": "custodian_off_exchange_settlement"}),
              _n("exch", "offchain_counterparty", {"role": "hedging_venue"})]
    edges = [_e("pt", "sy", "redeemable_into"), _e("sy", "susde", "redeemable_into"), _e("susde", "usde", "redeemable_into"),
             _e("pt", "pendle", "issued_by"), _e("sy", "pendle", "issued_by"),
             _e("susde", "ethena", "issued_by"), _e("usde", "ethena", "issued_by"),
             _e("ethena", "custody", "deployed_in"), _e("ethena", "exch", "deployed_in")]
    return GraphView.from_dict({"position": {"id": "morpho:0x" + "a" * 64 + ":0x" + "b" * 40, "value_usd": 1},
                                "nodes": nodes, "edges": edges})
