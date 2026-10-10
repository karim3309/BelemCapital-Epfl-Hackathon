"""Règles de propagation, méta-oracle, décision : tests unitaires (petits cas faits main)."""
import pytest
import yaml

from risk import decide
from risk.oracle_sim import deviation
from risk.params import ParamError, load_params
from risk.propagate import Shock, World, propagate
from tests.risk.conftest import tiny_params


# ------------------------------------------------------------------ propagation
def test_depeg_flows_up_the_redemption_chain(tiny_graph):
    w = propagate(tiny_graph, [Shock("usde", "market_depeg", 0.10)], tiny_params())
    for a in ("usde", "susde", "sy", "pt"):
        assert w.mult(a) == pytest.approx(0.90)       # redeemable_into : la valeur suit le sous-jacent


def test_custodian_failure_hits_issuer_base_asset_without_double_counting(tiny_graph):
    w = propagate(tiny_graph, [Shock("custody", "counterparty_failure", 1.0)], tiny_params())
    assert w.issuer_health["ethena"] == pytest.approx(1 - 1 / 3)
    assert w.mult("usde") == pytest.approx(2 / 3)
    # sUSDe est aussi émis par Ethena : il hérite via USDe, PAS une deuxième fois
    assert w.mult("susde") == pytest.approx(2 / 3)
    assert w.mult("pt") == pytest.approx(2 / 3)


def test_exchange_failure_is_limited_to_exposure_share_plus_panic(tiny_graph):
    w = propagate(tiny_graph, [Shock("exch", "counterparty_failure", 1.0, panic=0.03)], tiny_params())
    assert w.mult("usde") == pytest.approx((1 - 0.02) * (1 - 0.03))


def test_pendle_exploit_hits_sy_once(tiny_graph):
    w = propagate(tiny_graph, [Shock("pendle", "issuer_failure", 0.5)], tiny_params())
    assert w.mult("sy") == pytest.approx(0.5)
    assert w.mult("pt") == pytest.approx(0.5)          # PT hérite du SY, pas de ×0,5 supplémentaire
    assert w.mult("usde") == 1.0


def test_no_shock_no_change(tiny_graph):
    w = propagate(tiny_graph, [], tiny_params())
    assert w.asset_mult == {} and w.duration_hours == 0.0


def test_unknown_node_or_kind_is_refused(tiny_graph):
    with pytest.raises(ValueError):
        propagate(tiny_graph, [Shock("ghost", "market_depeg", 0.1)], tiny_params())
    with pytest.raises(ValueError):
        Shock("usde", "meteor", 0.1)


# ------------------------------------------------------------------ méta-oracle
def test_deviation_formula_from_steakhouse_doc():
    assert deviation(1.0, 0.99) == pytest.approx(0.01 / 0.995)
    assert deviation(2.0, 2.0) == 0


def test_meta_oracle_short_vs_long_shock(engine):
    from risk.oracle_sim import evaluate
    gv, p = engine.gv, engine.params
    o = gv.market_oracle_id()
    short = propagate(gv, [Shock("usde", "market_depeg", 0.07, duration_hours=6)], p)
    long_ = propagate(gv, [Shock("usde", "market_depeg", 0.07, duration_hours=24)], p)
    e_short, e_long = evaluate(gv, o, short, p), evaluate(gv, o, long_, p)
    assert e_short.challenge_possible and not e_short.switched          # choc court : pas de bascule
    assert e_long.switched and e_long.switch_after_hours == pytest.approx(16)   # 57 600 s lus on-chain
    assert e_long.mode == "market" and e_short.mode == "fixed"
    # healing : retour au primaire 24 h après la fin du choc
    assert any("acceptHealing" in t["event"] and t["t_hours"] == pytest.approx(48) for t in e_long.timeline)


def test_backup_price_after_switch_is_primary_times_usde(engine):
    from risk.oracle_sim import evaluate
    gv, p = engine.gv, engine.params
    w = propagate(gv, [Shock("usde", "market_depeg", 0.10, duration_hours=None)], p)
    e = evaluate(gv, gv.market_oracle_id(), w, p)
    primary, backup = e.children
    assert e.price == pytest.approx(backup.price)
    assert backup.price / backup.price_normal == pytest.approx(0.90, rel=1e-9)


def test_frozen_feed_or_halted_chain_prevents_switch(engine):
    from risk.oracle_sim import evaluate
    gv, p = engine.gv, engine.params
    frozen = propagate(gv, [Shock("usde", "market_depeg", 0.2), Shock("feed_usde_usd", "feed_frozen")], p)
    assert not evaluate(gv, gv.market_oracle_id(), frozen, p).switched
    halted = propagate(gv, [Shock("usde", "market_depeg", 0.2), Shock("ethereum", "chain_halt")], p)
    assert not evaluate(gv, gv.market_oracle_id(), halted, p).switched


# ------------------------------------------------------------------ décision
def test_p_star_reproduces_the_brief_example():
    # Brief : sortie à 11 % de la poche, incident à 60 % → p* ≈ 18 %
    assert decide.p_star(11, 60) == pytest.approx(0.1833, abs=1e-4)
    assert decide.p_star(11, 0) is None and decide.p_star(None, 60) is None


class _LinearExit:
    """Coût de sortie linéaire : la meilleure réponse est tout ou rien."""
    def __init__(self, unit, convex=0.0):
        self.unit, self.convex = unit, convex

    def cost(self, f, pool_factor=1.0):
        return {"feasible": True, "total_usd": self.unit * f + self.convex * f * f}


def test_partial_exit_only_when_slippage_is_convex():
    assert decide.best_fraction(_LinearExit(10), 100, 0.05)[0] == 0.0      # 5 < 10/100… reste
    assert decide.best_fraction(_LinearExit(10), 100, 0.20)[0] == 1.0      # tout sortir
    f, _ = decide.best_fraction(_LinearExit(0, convex=20), 100, 0.20)     # coût marginal croissant
    assert 0 < f < 1 and decide.verdict_of(f) == "PARTIAL"


# ------------------------------------------------------------------ paramètres stricts
def _write(tmp_path, data):
    p = tmp_path / "params.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


@pytest.mark.parametrize("spec,needle", [
    ({"value": 1}, "aucun statut"),
    ({"value": 1, "hypothesis": True}, "justification"),
    ({"value": 1, "source": "https://x.example"}, "as_of"),
    ({"source": "onchain"}, "field"),
    ({"source": "onchain", "field": "inputs:nope"}, "introuvable"),
])
def test_param_without_status_is_refused(tmp_path, engine, spec, needle):
    with pytest.raises(ParamError, match=needle):
        load_params(_write(tmp_path, {"x": spec}), engine.gv, engine.inputs)


def test_every_real_param_has_a_status(engine):
    for prm in engine.params.all_params():
        assert prm.status in ("source", "onchain", "hypothesis")
    assert engine.params["meta_oracle_challenge_timelock_seconds"] == 57600       # lu on-chain


def test_world_defaults():
    w = World()
    assert w.mult("anything") == 1.0
