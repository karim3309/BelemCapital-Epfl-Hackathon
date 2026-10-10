"""Portfolio scan tests (step 2) — WITHOUT network: FakeCtx + fake API.

The test marked `online` re-reads the real mainnet (STACKTRACE_ONLINE_TESTS=1).
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
    # 1e6 virtual shares / 1 virtual asset: an empty market converts 1e6 shares into 1 asset
    assert pf.to_assets_down(10**6, 0, 0) == 1
    assert pf.to_assets_down(10**6, 10, 10**6) == 5          # 10**6 × 11 / (2·10**6) = 5.5 → rounded down


def test_usd_per_unit_from_api_ratio():
    assert pf.usd_per_unit(2_000.0, 1_000 * 10**6, 6) == pytest.approx(2.0)
    assert pf.usd_per_unit(None, 10, 6) is None and pf.usd_per_unit(1.0, 0, 6) is None


def test_prove_vault_reads_the_chain_not_the_api():
    ctx = vault_ctx(assets=1_000_000 * 10**6)
    # the API announces 990,000: the chain says 1,000,000 → we keep the chain and measure the gap
    h = pf.prove_vault(ctx, HOLDER, api_item(990_000 * 10**6, 990_000.0), "v2", "API test")
    assert h.amount == 1_000_000
    assert h.price_usd == pytest.approx(1.0)
    assert h.value_usd == pytest.approx(1_000_000)
    assert h.api_gap == pytest.approx(0.01)
    assert any("balanceOf" in e and "#100" in e for e in h.evidence)     # evidence dated at the pinned block


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
    assert p0.holdings == [] and p0.ignored and "empty" in p0.ignored[0]["reason"]


def test_scan_unknown_holder_is_not_an_error():
    ctx = vault_ctx()
    ctx.http = FakeHttp({"errors": [{"message": "No results matching given parameters"}]})
    p = pf.scan_holder(ctx, HOLDER)
    assert p.holdings == [] and "no position" in p.notes[-1]


@pytest.mark.skipif(os.getenv("STACKTRACE_ONLINE_TESTS") != "1", reason="network test (STACKTRACE_ONLINE_TESTS=1)")
def test_scan_real_holder_live():
    from stacktrace.session import open_session
    s = open_session()
    # Main depositor of the "Belem RWA EURCV" vault (Morpho API, vault listed on the RockawayX Dune dashboard)
    p = pf.scan_holder(s.ctx, "0x4F87De7d21aeF48090958f7342E1F69Dff790545", s.chain_id)
    assert p.holdings, "at least one pocket expected"
    assert all(h.evidence for h in p.holdings)
    vaults = [h for h in p.holdings if h.kind.startswith("morpho_vault")]
    assert all(h.api_gap is None or h.api_gap < 0.01 for h in vaults)


# ------------------------------------------------------------------ whole vaults and curator books (curator view)
class PriceHttp:
    """Fake Morpho API: answers the vault price query (or nothing, to test the "no price" path)."""
    def __init__(self, price):
        self.price = price

    def post_json(self, url, body):
        if self.price is None:
            return {"errors": [{"message": "no price"}]}, "2026-10-10T00:00:00+00:00"
        return {"data": {"vaultV2ByAddress": {"asset": {"priceUsd": self.price}}}}, "2026-10-10T00:00:00+00:00"


def whole_vault_ctx(price=1.17, books=None):
    ctx = FakeCtx({
        (VAULT, "adaptersLength()", ()): 1, (VAULT, "name()", ()): "Vault Test EURCV",
        (VAULT, "asset()", ()): USDC, (USDC, "decimals()", ()): 6, (USDC, "symbol()", ()): "EURCV",
        (VAULT, "totalAssets()", ()): 2_000_000 * 10**6,
    })
    ctx.config = SimpleNamespace(apis={"morpho_graphql": "https://api.test/graphql"}, contracts={},
                                 raw={"curator_books": books or {}})
    ctx.http = PriceHttp(price)
    return ctx


def test_whole_vault_amount_is_total_assets_and_price_is_marked_api():
    h = pf.prove_whole_vault(whole_vault_ctx(), VAULT)
    assert h.amount == 2_000_000 and h.value_usd == pytest.approx(2_340_000)
    assert h.details["whole_vault"] and h.price_source.startswith("api:")
    assert any("totalAssets()" in e for e in h.evidence)


def test_vault_prefix_scans_one_whole_vault():
    p = pf.scan_holder(whole_vault_ctx(), f"vault:{VAULT.lower()}")
    assert p.holder == f"vault:{VAULT}" and len(p.holdings) == 1 and p.holdings[0].share_of_book == 1.0


def test_book_prefix_reads_the_config_list():
    ctx = whole_vault_ctx(books={"test": {"label": "Test curator", "source": "https://example.org",
                                          "vaults": [{"name": "Vault Test EURCV", "address": VAULT}]}})
    p = pf.scan_holder(ctx, "book:TEST")
    assert p.holder == "book:test" and [h.label for h in p.holdings] == ["Vault Test EURCV"]
    assert "Test curator" in p.located_by
    with pytest.raises(ValueError, match="unknown book"):
        pf.scan_holder(ctx, "book:nope")


def test_vault_without_usd_price_is_left_out_not_guessed():
    p = pf.scan_holder(whole_vault_ctx(price=None), f"vault:{VAULT}")
    assert p.holdings == [] and "no USD price" in p.ignored[0]["reason"]


def test_non_vault_address_is_ignored_with_the_reason():
    ctx = whole_vault_ctx()
    del ctx.responses[(VAULT, "adaptersLength()", ())]
    p = pf.scan_holder(ctx, f"vault:{VAULT}")
    assert p.holdings == [] and "not a Morpho Vault V2" in p.ignored[0]["reason"]


def test_file_slug_has_no_colon():
    assert pf.file_slug("book:RockawayX") == "book_rockawayx"
