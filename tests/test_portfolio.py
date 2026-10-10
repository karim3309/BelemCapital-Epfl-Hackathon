"""Tests du scan de portefeuille (étape 2) — SANS réseau : FakeCtx + fausse API.

Le test marqué `online` relit le vrai mainnet (STACKTRACE_ONLINE_TESTS=1).
"""
import os
from types import SimpleNamespace

import pytest

from stacktrace import portfolio as pf
from tests.fakes import FakeCtx, addr

HOLDER, VAULT, USDC = addr(1), addr(2), addr(3)


class FakeHttp:
    def __init__(self, data):
        self.data = data

    def post_json(self, url, body):
        return self.data, "2026-10-10T00:00:00+00:00"


def vault_ctx(shares=10**18, assets=1_000_000 * 10**6):
    ctx = FakeCtx({
        (VAULT, "balanceOf(address)", (HOLDER,)): shares,
        (VAULT, "convertToAssets(uint256)", (shares,)): assets,
        (VAULT, "asset()", ()): USDC,
        (USDC, "decimals()", ()): 6,
        (VAULT, "name()", ()): "Vault Test USDC",
    })
    ctx.config = SimpleNamespace(apis={"morpho_graphql": "https://api.test/graphql"}, contracts={})
    return ctx


def api_item(assets_raw, assets_usd):
    return {"shares": "1", "assets": str(assets_raw), "assetsUsd": assets_usd,
            "vault": {"address": VAULT, "name": "Vault Test USDC", "symbol": "vT",
                      "asset": {"address": USDC, "symbol": "USDC", "decimals": 6}}}


def test_to_assets_down_matches_morpho_sharesmath():
    # 1e6 parts virtuelles / 1 actif virtuel : un marché vide convertit 1e6 parts en 1 actif
    assert pf.to_assets_down(10**6, 0, 0) == 1
    assert pf.to_assets_down(10**6, 10, 10**6) == 5          # 10**6 × 11 / (2·10**6) = 5,5 → arrondi vers le bas


def test_usd_per_unit_from_api_ratio():
    assert pf.usd_per_unit(2_000.0, 1_000 * 10**6, 6) == pytest.approx(2.0)
    assert pf.usd_per_unit(None, 10, 6) is None and pf.usd_per_unit(1.0, 0, 6) is None


def test_prove_vault_reads_the_chain_not_the_api():
    ctx = vault_ctx(assets=1_000_000 * 10**6)
    # l'API annonce 990 000 : la chaîne dit 1 000 000 → on garde la chaîne et on mesure l'écart
    h = pf.prove_vault(ctx, HOLDER, api_item(990_000 * 10**6, 990_000.0), "v2", "API test")
    assert h.amount == 1_000_000
    assert h.price_usd == pytest.approx(1.0)
    assert h.value_usd == pytest.approx(1_000_000)
    assert h.api_gap == pytest.approx(0.01)
    assert any("balanceOf" in e and "#100" in e for e in h.evidence)     # preuve datée au bloc figé


def test_scan_filters_empty_positions_and_computes_book_shares():
    ctx = vault_ctx()
    ctx.http = FakeHttp({"data": {"userByAddress": {
        "vaultV2Positions": [api_item(1_000_000 * 10**6, 1_000_000.0)], "vaultPositions": [], "marketPositions": []}}})
    p = pf.scan_holder(ctx, HOLDER)
    assert len(p.holdings) == 1 and p.holdings[0].share_of_book == 1.0
    assert p.total_value_usd == pytest.approx(1_000_000)

    empty = vault_ctx(shares=0)
    empty.http = ctx.http
    p0 = pf.scan_holder(empty, HOLDER)
    assert p0.holdings == [] and p0.ignored and "vide" in p0.ignored[0]["reason"]


def test_scan_unknown_holder_is_not_an_error():
    ctx = vault_ctx()
    ctx.http = FakeHttp({"errors": [{"message": "No results matching given parameters"}]})
    p = pf.scan_holder(ctx, HOLDER)
    assert p.holdings == [] and "aucune position" in p.notes[-1]


@pytest.mark.skipif(os.getenv("STACKTRACE_ONLINE_TESTS") != "1", reason="test réseau (STACKTRACE_ONLINE_TESTS=1)")
def test_scan_real_holder_live():
    from stacktrace.session import open_session
    s = open_session()
    # Déposant principal du vault « Belem RWA EURCV » (API Morpho, vault listé sur le dashboard Dune RockawayX)
    p = pf.scan_holder(s.ctx, "0x4F87De7d21aeF48090958f7342E1F69Dff790545", s.chain_id)
    assert p.holdings, "au moins une poche attendue"
    assert all(h.evidence for h in p.holdings)
    vaults = [h for h in p.holdings if h.kind.startswith("morpho_vault")]
    assert all(h.api_gap is None or h.api_gap < 0.01 for h in vaults)
