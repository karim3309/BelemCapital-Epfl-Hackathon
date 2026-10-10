"""Le moteur sur la VRAIE position A (graphe + lectures on-chain commités) : cohérence et seuils."""
import json

import pytest

from risk.position import lif
from risk.propagate import Shock
from risk.run import GRID, REPORT, build_report


def loss(engine, u_drop, hours):
    _, oracle, out = engine.run([Shock("usde", "market_depeg", u_drop, duration_hours=hours)] if u_drop else [])
    return oracle, out


def test_no_shock_leaves_everything_unchanged(engine):
    oracle, out = loss(engine, 0, None)
    assert out["hf_after"] == pytest.approx(out["hf_before"])
    assert out["borrower_loss_usd"] == pytest.approx(0, abs=1e-6) and not out["liquidated"]


def test_hf_after_switch_equals_hf_times_backup_over_primary(engine):
    oracle, out = loss(engine, 0.03, None)
    primary, backup = oracle.children
    assert out["hf_after"] == pytest.approx(out["hf_before"] * backup.price / primary.price, rel=1e-9)


def _bisect(fn, lo, hi, n=40):
    for _ in range(n):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fn(mid) else (lo, mid)
    return (lo + hi) / 2


def test_thresholds_of_position_a_emerge_from_the_engine(engine):
    """POSITION_A.md : challenge possible dès USDe < ~0,9925 $ ; liquidable sous ~0,9525 $ après 16 h."""
    u_now = engine.gv.meta("usde")["price_usd"]
    # plus petite baisse qui ouvre un challenge
    d_challenge = _bisect(lambda d: not loss(engine, d, None)[0].challenge_possible, 0.0, 0.05)
    u_challenge = u_now * (1 - d_challenge)
    assert u_challenge == pytest.approx(0.99253, abs=2e-4)
    # plus petite baisse durable qui liquide
    d_liq = _bisect(lambda d: not loss(engine, d, None)[1]["liquidatable"], 0.0, 0.2)
    # après bascule, HF = HF0 × prix de l'USDe (le secours = primaire × USDe/USD) → seuil = 1 / HF0
    assert u_now * (1 - d_liq) == pytest.approx(1 / engine.base.hf, rel=1e-6)
    assert u_now * (1 - d_liq) == pytest.approx(0.9525, abs=2e-3)
    # même baisse, mais 15 h : pas de bascule, pas de liquidation
    assert not loss(engine, d_liq + 0.01, 15)[1]["liquidated"]


def test_liquidation_incentive_matches_morpho_formula(engine):
    assert lif(0.915, engine.params) == pytest.approx(1 / (0.3 * 0.915 + 0.7))
    assert lif(0.5, engine.params) == pytest.approx(1.15)      # plafonné à M


def test_fixed_oracle_leaves_the_hole_to_lenders(engine):
    _, _, out = engine.run([Shock("pendle", "issuer_failure", 0.5)])
    assert not out["liquidatable"]                       # l'oracle fixe ne voit pas l'exploit
    assert out["lender_loss_usd"] > 100_000              # le trou est chez les prêteurs


def test_exit_cost_is_measured_and_increasing(engine):
    curve = engine.exit_model.curve(1.0)
    totals = [c["total_usd"] for c in curve]
    assert totals == sorted(totals) and totals[0] == 0
    assert 0 < curve[-1]["slippage_rate"] < 0.01           # simulation on-chain RouterStatic
    assert engine.exit_model.cost(1.0, pool_factor=0.1)["feasible"] is False   # pool ÷10 : impossible


def test_oct_2025_replay(engine):
    from risk.replay import run_replays
    from risk.run import REPLAYS
    oct25 = next(r for r in run_replays(engine, REPLAYS) if r["id"] == "R-OCT2025")
    real, chainlink, binance = oct25["designs"]
    assert not real["liquidated"] and not chainlink["liquidated"]
    assert binance["liquidated"]                          # un oracle sur le prix Binance nous liquidait
    assert oct25["chainlink_min"] > 0.99                  # on-chain, l'USDe est resté proche de 1 $


def test_committed_report_is_up_to_date(engine):
    report, grid = build_report(engine)
    committed = json.loads(REPORT.read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(report, ensure_ascii=False, default=str))
    assert fresh == committed, "output/risk_report.json n'est plus à jour : relancez python -m risk.run"
    assert json.loads(json.dumps(grid, default=str)) == json.loads(GRID.read_text(encoding="utf-8"))
