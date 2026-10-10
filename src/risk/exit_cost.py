"""Exit cost C_exit: how much does it cost to exit NOW, for certain?

Exiting a leveraged position = "unwinding": repay the USDC debt and sell the PT.
The certain cost of that exit has 4 parts (brief: "real slippage + gas + forgone yield"):

  1. slippage on the Pendle pool (PT → SY): MEASURED on-chain. We asked Pendle's RouterStatic
     for a quote at several sale sizes (risk_inputs.json). Cost = gap between what we receive
     and the pool's "spot" price (the AMM's implied price). It includes the pool fees.
     Analogy: the currency exchange office lowers its rate as you sell bigger amounts.
  2. sUSDe/USDe → USDC conversion to repay the debt: pools not discovered → displayed hypothesis.
  3. gas: gas units (hypothesis) × block base fee (on-chain) × ETH price (Chainlink, on-chain).
  4. forgone yield over the horizon: PT fixed yield − cost of the debt (on-chain).

"Stressed" pool (k times less liquidity): selling Q in that pool ≈ selling Q/k in the current pool
(first-order approximation of an AMM, displayed as a hypothesis). Beyond the largest sale
simulated without a revert, the exit is declared IMPOSSIBLE (the pool cannot absorb it).
"""
from __future__ import annotations

from dataclasses import dataclass

from .graphview import GraphView


@dataclass
class ExitModel:
    points: list[tuple[float, float]]      # (PT quantity, relative cost vs spot)
    max_feasible_pt: float
    min_reverted_pt: float | None
    collateral_pt: float
    debt: float
    pt_usd: float
    loan_usd: float
    gas_usd: float
    carry_per_year_usd: float
    params: object
    evidence: list[str]

    @classmethod
    def build(cls, gv: GraphView, inputs: dict, params) -> "ExitModel":
        sims = inputs.get("exit_simulations", {})
        venue = gv.exit_venue_id()
        pos = gv.meta(gv.market_id())["position"]
        pool = gv.meta(venue) if venue else {}
        coll = gv.meta(gv.collateral_id())
        sy_node = gv.node(gv.targets(gv.collateral_id(), "redeemable_into")[0])
        sy_rate = sy_node["meta"].get("exchange_rate")            # accounting asset (USDe) per SY
        fair = pool.get("pt_price_implied_by_amm")                 # PT spot price in USDe
        points, evidence, max_ok, min_rev = [], [], 0.0, None
        for p in sims.get("points", []):
            if p.get("reverted"):
                min_rev = p["pt_in"] if min_rev is None else min(min_rev, p["pt_in"])
                evidence.append(p["evidence"])
                continue
            received_usde = p["sy_out"] * sy_rate
            cost = max(0.0, 1 - received_usde / (p["pt_in"] * fair))
            points.append((p["pt_in"], cost))
            max_ok = max(max_ok, p["pt_in"])
            evidence.append(p["evidence"])
        points.sort()
        accounting = gv.by_address(sy_node["meta"].get("accounting_asset"))
        usde_usd = accounting["meta"].get("price_usd") if accounting else None
        pt_usd = fair * usde_usd if (fair and usde_usd) else coll.get("price_usd")
        loan_usd = gv.meta(gv.loan_id()).get("price_usd") or 1.0
        gas = inputs.get("gas", {})
        gas_usd = params["unwind_gas_units"] * gas.get("base_fee_gwei", 0) * 1e-9 * gas.get("eth_usd", 0)
        carry = (pos["collateral_human"] * pt_usd * params["carry_pt_implied_apy"]
                 - pos["borrow_human"] * loan_usd * params["carry_borrow_apy"])
        return cls(points=points, max_feasible_pt=max_ok, min_reverted_pt=min_rev,
                   collateral_pt=pos["collateral_human"], debt=pos["borrow_human"],
                   pt_usd=pt_usd, loan_usd=loan_usd, gas_usd=gas_usd, carry_per_year_usd=carry,
                   params=params, evidence=evidence)

    # ------------------------------------------------------------------ slippage
    def slippage_rate(self, pt_amount: float, pool_factor: float = 1.0) -> float | None:
        """Relative cost of selling `pt_amount` PT; None = impossible (pool too small)."""
        if pt_amount <= 0:
            return 0.0
        q = pt_amount / max(pool_factor, 1e-9)
        if q > self.max_feasible_pt or not self.points:
            return None
        pts = [(0.0, self.points[0][1])] + self.points
        for (q0, c0), (q1, c1) in zip(pts, pts[1:]):
            if q0 <= q <= q1:
                return c0 + (c1 - c0) * (q - q0) / (q1 - q0) if q1 > q0 else c1
        return self.points[-1][1]

    # ------------------------------------------------------------------ total cost
    def cost(self, fraction: float, pool_factor: float = 1.0, horizon_days: float | None = None) -> dict:
        horizon_days = self.params["horizon_days"] if horizon_days is None else horizon_days
        q = fraction * self.collateral_pt
        notional = q * self.pt_usd
        slip = self.slippage_rate(q, pool_factor)
        if fraction <= 0:
            return {"fraction": 0.0, "feasible": True, "pt_sold": 0.0, "notional_usd": 0.0, "slippage_rate": 0.0,
                    "slippage_usd": 0.0, "second_leg_usd": 0.0, "gas_usd": 0.0, "carry_usd": 0.0, "total_usd": 0.0}
        if slip is None:
            return {"fraction": fraction, "feasible": False, "pt_sold": q, "notional_usd": notional,
                    "slippage_rate": None, "slippage_usd": None, "second_leg_usd": None,
                    "gas_usd": self.gas_usd, "carry_usd": None, "total_usd": None,
                    "why_infeasible": "sale larger than what the pool can absorb (the on-chain simulation reverts)"}
        slippage_usd = slip * notional
        second = self.params["second_leg_cost_rate"] * (notional - slippage_usd)
        carry = fraction * self.carry_per_year_usd * horizon_days / 365
        total = slippage_usd + second + self.gas_usd + carry
        return {"fraction": fraction, "feasible": True, "pt_sold": q, "notional_usd": notional,
                "slippage_rate": slip, "slippage_usd": slippage_usd, "second_leg_usd": second,
                "gas_usd": self.gas_usd, "carry_usd": carry, "total_usd": total}

    def curve(self, pool_factor: float = 1.0, step: float = 0.05) -> list[dict]:
        n = int(round(1 / step))
        return [self.cost(i * step, pool_factor) for i in range(n + 1)]
