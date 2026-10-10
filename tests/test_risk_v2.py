"""Étape 5 — règles du moteur de risque v2, testées sur des cas calculables à la main (aucun réseau)."""
import numpy as np
import pytest

from stacktrace.analyze import best_fraction, p_star
from stacktrace.exit_cost import ExitModel
from stacktrace.market_data import Market, collateral_side_mode
from stacktrace.params import ParamsError, load_params
from stacktrace.risk_engine import BorrowPocket, borrow_loss_drop, lif, oracle_up_attack, vault_market_loss

P = load_params()


def market(debts, colls, lltv=0.86, liquidity=0.0, mode="market"):
    return Market("0x" + "11" * 32, "m", "M", "c", "C", "L", lltv, supply=sum(debts) + liquidity, borrow=sum(debts),
                  liquidity=liquidity, supply_apy=0.03, collateral_mode=mode, collateral_class="volatile",
                  oracle_id="o", feeds=[], price=1.0, debts=np.array(debts, float), coll_values=np.array(colls, float))


# ------------------------------------------------------------------ prêteur : dette irrécouvrable
def test_bad_debt_is_computed_borrower_by_borrower():
    # deux emprunteurs : l'un à 85 % de LTV, l'autre à 10 %. Chute de 20 %, oracle qui ne suit pas, sans glissement.
    mk = market([85, 10], [100, 100])
    # emprunteur 1 : 85 − 100·0,8 = 5 de perte ; emprunteur 2 : rien. L'agrégat (95 vs 160) n'en verrait aucune.
    assert vault_market_loss(mk, 0.20, tracks=False, speed="jump", slip=0.0) == pytest.approx(5.0)


def test_market_oracle_and_gradual_drop_means_no_lender_loss():
    mk = market([85], [100])
    assert vault_market_loss(mk, 0.30, tracks=True, speed="gradual", slip=0.02) == 0.0
    assert vault_market_loss(mk, 0.30, tracks=True, speed="jump", slip=0.0) == pytest.approx(15.0)


def test_inflated_oracle_attack_needs_price_above_one_over_lltv():
    mk = market([0], [0], lltv=0.77, liquidity=1000)
    assert oracle_up_attack(mk, 0.10) == 0.0                     # 1,10 × 0,77 < 1 : l'attaque ne rapporte rien
    assert oracle_up_attack(mk, 0.50) == pytest.approx(1000 * (1 - 1 / (1.5 * 0.77)))


# ------------------------------------------------------------------ emprunteur
def test_lif_matches_morpho_formula():
    assert lif(0.86, P) == pytest.approx(1 / (0.3 * 0.86 + 0.7))
    assert lif(0.0, P) == P["morpho_lif_max"]                   # plafonné à M


def test_borrower_volatile_drop_counts_only_liquidation():
    bp = BorrowPocket("b", 0, 1.0, market([60], [100]), collateral_value=100, debt=60, hf=100 * 0.86 / 60)
    assert borrow_loss_drop(bp, 0.20, tracks=True, p=P, beta=True) == 0.0          # HF 1,43 → 1,15 : pas liquidé
    penalty = 60 * (lif(0.86, P) - 1)
    assert borrow_loss_drop(bp, 0.40, tracks=True, p=P, beta=True) == pytest.approx(penalty)
    assert borrow_loss_drop(bp, 0.20, tracks=False, p=P, beta=False) == pytest.approx(20.0)   # perte propre (RWA)
    assert borrow_loss_drop(bp, 0.90, tracks=False, p=P, beta=False) == pytest.approx(40.0)   # plafonné au capital


# ------------------------------------------------------------------ oracle côté collatéral
def test_collateral_tracks_market_only_if_all_base_components_do():
    assert collateral_side_mode(["market", "market"]) == "market"
    assert collateral_side_mode(["internal_rate", "market"]) == "internal_rate"   # PST × USDC/USD
    assert collateral_side_mode(["fixed"]) == "fixed"                              # feed Midas
    assert collateral_side_mode([]) == "fixed"


# ------------------------------------------------------------------ décision
def exit_model(f_max, costs_at_one, gas=0.0):
    m = ExitModel("vault", 1000.0, f_max, gas)
    m._f, m._cost = [0.0, 1.0], [0.0, costs_at_one]
    return m


def test_decision_compares_avoided_loss_with_exit_cost():
    m = exit_model(1.0, 10.0)
    assert best_fraction(m, 5.0)[0] == 0.0          # perte attendue 5 < coût 10 → STAY
    assert best_fraction(m, 50.0)[0] == 1.0         # 50 > 10 → EXIT total


def test_exit_is_capped_by_available_liquidity():
    m = exit_model(0.22, 1.0)
    f, _ = best_fraction(m, 500.0)
    assert f == pytest.approx(0.22)


def test_p_star_is_cost_over_loss_and_none_when_exit_impossible():
    m = exit_model(1.0, 10.0)
    assert p_star(m, 1000.0) == pytest.approx(0.01)
    assert p_star(exit_model(0.0, 10.0), 1000.0) is None


# ------------------------------------------------------------------ paramètres
def test_params_without_status_are_refused(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("events: {}\nhorizon_days: {value: 7}\n", encoding="utf-8")
    with pytest.raises(ParamsError):
        load_params(f)
