"""Coût CERTAIN de sortir d'une poche maintenant, pour une fraction f de la poche.

  Dépôt en vault : on retire des actifs. Pas de glissement de prix, mais :
     - on ne peut retirer que ce qui est liquide (idle + liquidité des marchés) → f ≤ f_max ;
     - pénalité de retrait forcé (lue on-chain, souvent 0) ;
     - rendement abandonné sur l'horizon (APY des marchés pondéré par l'allocation) ;
     - gas (prix du bloc × prix ETH Chainlink).
  Emprunt : pour rembourser f × dette, il faut REVENDRE du collatéral contre l'actif prêté. Le glissement est
     MESURÉ par des devis réels de l'agrégateur KyberSwap (API publique, datée), à plusieurs tailles :
         glissement(f) = 1 − sortie(f) / (entrée(f) × taux d'un petit montant de référence)
     Si aucune route n'existe (collatéral illiquide), on prend l'hypothèse de repli, signalée comme NON mesurée.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from discovery.adapters.ens import resolve
from discovery.ctx import Ctx

from .market_data import G
from .params import Params

F_QUOTES = (0.25, 0.5, 1.0)


@dataclass
class ExitModel:
    kind: str
    value_usd: float
    f_max: float                         # fraction sortable MAINTENANT
    gas_usd: float
    detail: dict = field(default_factory=dict)
    _f: list = field(default_factory=list)
    _cost: list = field(default_factory=list)

    def cost(self, f: float) -> float:
        """Coût en $ pour sortir la fraction f (0 si f = 0)."""
        if f <= 0:
            return 0.0
        return self.gas_usd + float(np.interp(f, self._f, self._cost))


def gas_usd(ctx: Ctx, units: int) -> tuple[float, str]:
    block = ctx.w3.eth.get_block(ctx.block)
    base_fee = int(block.get("baseFeePerGas") or 0)
    name = (ctx.config.raw.get("usd_reference") or {}).get("gas_token_usd_feed_ens", "eth-usd.data.eth")
    feed, proof = resolve(ctx, name)
    if not feed:
        return 0.0, "prix ETH introuvable via ENS : gas ignoré"
    _, answer, _, _, _ = ctx.call(feed, "latestRoundData()", returns=["uint80", "int256", "uint256", "uint256", "uint80"])
    dec = ctx.call(feed, "decimals()", returns=["uint8"])
    eth = answer / 10**dec
    usd = units * base_fee / 1e18 * eth
    return usd, f"{units} gas × baseFee {base_fee / 1e9:.2f} gwei (bloc #{ctx.block}) × ETH {eth:,.0f} $ ({proof})"


def vault_exit(ctx: Ctx, p: Params, value_usd: float, f_max: float, apy: float | None, penalty: float, days: float,
               f_free: float = 0.0) -> ExitModel:
    """Retrait normal sans pénalité jusqu'à f_free (marché source de liquidité), puis forceDeallocate avec pénalité."""
    g_usd, g_src = gas_usd(ctx, int(p["exit_gas_units.vault"]))
    carry = (apy or 0.0) * days / 365
    f_free = min(f_free, f_max)
    m = ExitModel("vault", value_usd, f_max, g_usd, detail={
        "withdrawable_now_fraction": f_max, "penalty_free_fraction": f_free, "force_deallocate_penalty": penalty,
        "forgone_yield_rate_over_horizon": carry, "supply_apy_weighted": apy, "gas": g_src,
        "note": "au-delà de f_max, la sortie dépend du remboursement des emprunteurs / de la hausse des taux"})
    m._f = [0.0, f_free, 1.0] if 0 < f_free < 1 else [0.0, 1.0]
    m._cost = [value_usd * f * carry + value_usd * max(0.0, f - f_free) * penalty for f in m._f]
    return m


def borrow_exit(ctx: Ctx, p: Params, g: G, value_usd: float, unit_usd: float, debt: float, price: float,
                coll_id: str, loan_id: str, days: float = 7.0) -> ExitModel:
    g_usd, g_src = gas_usd(ctx, int(p["exit_gas_units.borrow"]))
    coll, loan = g.nodes[coll_id], g.nodes[loan_id]
    cdec = coll["meta"]["decimals"]
    url = p["exit_quote_api"]
    ctx.http.session.headers["X-Client-Id"] = "stacktrace-hackathon"   # identifiant client demandé par la doc KyberSwap

    def quote(units: float) -> tuple[int, int, str]:
        raw = int(units * 10**cdec)
        data, fetched = ctx.http.get_json(url, {"tokenIn": coll["address"], "tokenOut": loan["address"], "amountIn": str(raw)})
        rs = (data.get("data") or {}).get("routeSummary") or {}
        if not rs.get("amountOut"):
            raise ValueError(data.get("message") or "pas de route")
        return raw, int(rs["amountOut"]), fetched

    full_units = debt / price if price else 0.0          # collatéral à vendre pour rembourser TOUTE la dette
    detail = {"quote_api": url, "collateral_to_sell_full": full_units, "gas": g_src}
    fs, costs = [0.0], [0.0]
    try:
        ref_units = min(full_units * 0.01, 20_000 / (price * unit_usd)) if price and unit_usd else full_units * 0.01
        r_in, r_out, fetched = quote(ref_units)
        rate = r_out / r_in
        detail["reference"] = {"collateral_in": ref_units, "rate_out_per_in_raw": rate, "fetched": fetched}
        quotes = []
        for f in F_QUOTES:
            q_in, q_out, _ = quote(full_units * f)
            slip = max(0.0, 1 - q_out / (q_in * rate))
            quotes.append({"fraction": f, "slippage": round(slip, 6)})
            fs.append(f)
            costs.append(slip * f * debt * unit_usd)
        detail["quotes"] = quotes
        detail["measured"] = True
    except Exception as e:
        slip = p["exit_swap_slippage_fallback"]
        detail.update({"measured": False, "fallback_slippage": slip,
                       "why": f"devis impossible ({type(e).__name__}: {str(e)[:120]}) → hypothèse de repli"})
        fs, costs = [0.0, 1.0], [0.0, slip * debt * unit_usd]
    # Part sortable PAR LE MARCHÉ : on s'arrête là où le glissement mesuré dépasse le maximum acceptable
    # (au-delà, vendre détruirait plus de valeur que le risque évité : le pool ne peut pas absorber la vente).
    max_slip = p["exit_max_acceptable_slippage"]
    f_max = 1.0
    if detail.get("measured"):
        ok = [q["fraction"] for q in detail["quotes"] if q["slippage"] <= max_slip]
        f_max = max(ok) if ok else 0.0
        if f_max < 1.0:
            detail["market_capacity_note"] = (f"au-delà de {f_max:.0%} de la dette, le glissement dépasse {max_slip:.0%} : "
                                              "le marché ne peut pas absorber la vente (autre voie : rachat chez l'émetteur, non modélisé)")
    carry = p["borrow_net_carry_annual"] * days / 365          # rendement net abandonné sur l'horizon
    detail["forgone_net_carry_rate_over_horizon"] = carry
    m = ExitModel("borrow", value_usd, f_max, g_usd, detail=detail)
    m._f = fs
    m._cost = [min(c + f * value_usd * carry, value_usd) for f, c in zip(fs, costs)]   # plafonné au capital propre
    return m
