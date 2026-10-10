"""Effet d'un choc sur LA position : santé, liquidation, et qui perd combien.

Rappel (GUIDE_DEBUTANT §7) : prêteur sur gages. On a déposé C PT en gage et on doit D USDC.
  health factor (HF) = C × prix_oracle × LLTV / D      (< 1 → liquidable)

Ce que fait le module, dans l'ordre :
  1. valeur de MARCHÉ avant le choc : capital (« equity ») = C × prix_PT − D × prix_USDC ;
  2. pendant le choc : prix vu par l'oracle (oracle_sim) → nouveau HF ;
  3. si HF < 1 : un liquidateur rembourse la dette et saisit du PT avec un bonus (LIF, formule Morpho
     sourcée). Il ne le fait QUE si c'est rentable après avoir revendu le PT saisi (glissement mesuré) ;
     si le gage ne suffit pas → « dette irrécouvrable » chez les prêteurs ;
  4. à l'horizon : si le choc est fini, les prix sont revenus (seules les pertes RÉALISÉES restent :
     liquidation) ; s'il dure encore, on valorise au prix choqué (perte latente).

Trois cas à retenir (le cadrage les cite) :
  - oracle qui suit le marché + choc → liquidation : l'emprunteur perd (bonus + vente au plus bas) ;
  - oracle FIXE + choc → pas de liquidation : l'emprunteur perd en valeur de marché, et si le gage ne
    couvre plus la dette, ce sont les PRÊTEURS qui portent le trou (dette résiduelle) ;
  - choc COURT + méta-oracle → ni bascule ni liquidation : rien n'est réalisé, les prix reviennent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .exit_cost import ExitModel
from .graphview import GraphView
from .oracle_sim import OracleEval
from .propagate import World
from .fmt import num, pct, usd


def lif(lltv: float, params) -> float:
    """Liquidation Incentive Factor (doc Morpho) : min(M, 1 / (β·LLTV + (1 − β)))."""
    beta, m = params["morpho_lif_beta"], params["morpho_lif_max"]
    return min(m, 1 / (beta * lltv + (1 - beta)))


@dataclass
class Baseline:
    collateral: float          # PT
    debt: float                # USDC (intérêts courus inclus)
    oracle_price: float        # USDC par PT selon l'oracle, au bloc
    lltv: float
    pt_usd: float              # valeur de marché d'un PT (prix spot de l'AMM × USDe/USD)
    loan_usd: float
    borrow_apy: float
    equity_usd: float
    hf: float
    pt_implied_apy: float = 0.0
    pt_days_to_expiry: float = 0.0

    @classmethod
    def build(cls, gv: GraphView, exit_model: ExitModel) -> "Baseline":
        market = gv.meta(gv.market_id())
        pos = market["position"]
        coll, debt = pos["collateral_human"], pos["borrow_human"]
        oracle_price = gv.meta(gv.market_oracle_id())["price"]
        lltv = market["lltv"]
        equity = coll * exit_model.pt_usd - debt * exit_model.loan_usd
        venue = gv.exit_venue_id()
        return cls(collateral=coll, debt=debt, oracle_price=oracle_price, lltv=lltv,
                   pt_usd=exit_model.pt_usd, loan_usd=exit_model.loan_usd,
                   borrow_apy=market.get("borrow_apy") or 0.0, equity_usd=equity,
                   hf=coll * oracle_price * lltv / debt,
                   pt_implied_apy=(gv.meta(venue).get("implied_apy") or 0.0) if venue else 0.0,
                   pt_days_to_expiry=gv.meta(gv.collateral_id()).get("days_to_expiry") or 0.0)

    def pt_usd_at(self, offset_days: float) -> float:
        """Valeur du PT plus tard, sans choc : il « mûrit » au taux implicite et vaut 1 actif à l'échéance."""
        t = min(max(offset_days, 0.0), self.pt_days_to_expiry)
        return self.pt_usd * (1 + self.pt_implied_apy) ** (t / 365)


def evaluate_position(gv: GraphView, base: Baseline, world: World, oracle: OracleEval, params,
                      exit_model: ExitModel, horizon_days: float, ts_offset_days: float = 0.0) -> dict:
    horizon_h = horizon_days * 24
    coll_id, loan_id = gv.collateral_id(), gv.loan_id()
    trace: list[str] = []

    # -- prix de marché pendant le choc
    extra = params["pt_extra_amm_discount_under_stress"] if world.mult(coll_id) < 1 else 0.0
    pt_usd_now = base.pt_usd_at(ts_offset_days)          # S-TIME : le PT converge vers 1 à l'échéance
    pt_usd_shock = pt_usd_now * world.mult(coll_id) * (1 - extra)
    loan_usd_shock = base.loan_usd * world.mult(loan_id)

    # -- dette à la date évaluée (S-TIME : la dette grossit au taux d'emprunt)
    debt = base.debt * math.exp(base.borrow_apy * ts_offset_days / 365) if ts_offset_days else base.debt

    # -- exploit du protocole de prêt : une part du collatéral disparaît
    lost = max((world.protocol_loss.get(i, 0.0) for i in gv.targets(gv.market_id(), "issued_by")), default=0.0)
    coll = base.collateral * (1 - lost)
    if lost:
        trace.append(f"exploit du marché : {pct(lost, 0)} du collatéral perdu")

    hf_before = base.hf
    hf_shock = coll * oracle.price * base.lltv / debt
    trace.append(f"HF {hf_before:.4f} → {hf_shock:.4f} (prix oracle {oracle.price_normal:.6f} → {oracle.price:.6f}, mode {oracle.mode})")

    # -- liquidation ?
    liquidated, liq_profitable, liq_time_h = False, None, None
    seized = repaid = bad_debt = 0.0
    factor = lif(base.lltv, params)
    pool_factor = min(world.pool_factor.values(), default=1.0)
    if hf_shock < 1 and not world.chain_halted:
        liq_time_h = oracle.switch_after_hours or 0.0
        repay = debt * params["liquidation_repaid_fraction"]
        seize = min(coll, repay * factor / oracle.price)
        repay_eff = seize * oracle.price / factor if seize < repay * factor / oracle.price else repay
        slip = exit_model.slippage_rate(seize, pool_factor)
        proceeds = seize * pt_usd_shock * (1 - slip) if slip is not None else 0.0
        profit = proceeds - repay_eff * loan_usd_shock
        liq_profitable = profit > 0
        trace.append(f"liquidable (HF < 1) : bonus LIF = {factor:.4f} ; liquidateur rembourse {num(repay_eff)} USDC, "
                     f"saisit {num(seize)} PT, revente {'impossible' if slip is None else f'à −{pct(slip, 2)}'} "
                     f"→ profit {usd(profit)}")
        if liq_profitable or not params["liquidator_requires_profit"]:
            liquidated = True
            seized, repaid = seize, repay_eff
            if seize >= coll and repay_eff < debt:
                bad_debt = debt - repay_eff          # gage épuisé : le reste est irrécouvrable
                trace.append(f"gage épuisé : {num(bad_debt)} USDC de dette irrécouvrable chez les prêteurs")
        else:
            trace.append("liquidation NON rentable → personne ne liquide : la dette reste exposée")
    elif hf_shock < 1 and world.chain_halted:
        trace.append("liquidable mais la chaîne est à l'arrêt : liquidation retardée")

    # -- valorisation à l'horizon
    recovered = world.duration_hours is not None and world.duration_hours < horizon_h
    pt_final = pt_usd_now if recovered else pt_usd_shock
    loan_final = base.loan_usd if recovered else loan_usd_shock
    if recovered:
        trace.append(f"le choc ({world.duration_hours:g} h) se termine avant l'horizon ({horizon_h:.0f} h) : prix revenus")
    coll_left = coll - seized
    debt_left = 0.0 if bad_debt else debt - repaid
    final = coll_left * pt_final - debt_left * loan_final
    lender_exposure = 0.0
    if final < 0:
        lender_exposure = -final
        trace.append(f"le gage ne couvre plus la dette : l'emprunteur abandonne, prêteurs exposés à {usd(lender_exposure)}")
        final = 0.0
    borrower_loss = base.equity_usd - final
    lender_loss = bad_debt * loan_final + lender_exposure
    who = []
    if borrower_loss > 1:
        who.append("emprunteur")
    if lender_loss > 1:
        who.append("prêteurs")
    return {
        "hf_before": hf_before, "hf_after": hf_shock,
        "oracle_price_before": oracle.price_normal, "oracle_price_after": oracle.price,
        "oracle_mode": oracle.mode, "oracle_switched": oracle.switched,
        "liquidatable": hf_shock < 1, "liquidated": liquidated, "liquidation_profitable": liq_profitable,
        "liquidation_after_hours": liq_time_h, "lif": factor,
        "seized_pt": seized, "repaid_usdc": repaid, "bad_debt_usdc": bad_debt,
        "pt_usd_before": base.pt_usd, "pt_usd_shock": pt_usd_shock,
        "equity_before_usd": base.equity_usd, "equity_after_usd": final,
        "borrower_loss_usd": borrower_loss, "lender_loss_usd": lender_loss,
        "lgi": max(borrower_loss, 0.0) / base.equity_usd if base.equity_usd > 0 else None,
        "who_loses": who or ["personne"], "recovered_before_horizon": recovered,
        "trace": trace,
    }
