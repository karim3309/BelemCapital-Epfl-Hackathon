"""Moteur de risque v2 : « si ce nœud casse, combien perd MA poche ? » — puis loi des pertes (Monte Carlo).

Les incidents ne sont pas écrits à la main : ils sont GÉNÉRÉS à partir du graphe de la poche, par type de
nœud (collatéral, feed, émetteur, protocole, curateur, actif de la poche). Pour chacun, une fonction de
perte transforme une sévérité s ∈ [0, 1] en dollars perdus par la poche, avec des règles écrites en clair :

POCHE « DÉPÔT EN VAULT » (on est prêteur) — on ne perd que la DETTE IRRÉCOUVRABLE des emprunteurs :
  pour chaque emprunteur i d'un marché :  dette Dᵢ, collatéral Vᵢ (au prix oracle), le collatéral chute de d
    - oracle qui SUIT le marché + chute progressive → liquidé à temps (HF = 1) → aucune perte pour le prêteur ;
    - choc brutal, OU oracle qui ne suit pas (taux interne, prix posé par un admin) → pas de liquidation à temps :
          perteᵢ = max(0, Dᵢ − Vᵢ·(1 − d)·(1 − glissement de revente))
  la perte du marché est répartie entre ses prêteurs : poche = part_du_détenteur × Σ (fourni_vault / fourni_total) × perte
  + feed faussé VERS LE HAUT de u : un attaquant dépose du collatéral et emprunte la liquidité disponible L ;
    il gagne (et les prêteurs perdent) si (1 + u) × LLTV > 1 :  perte = L × (1 − 1 / ((1 + u)·LLTV))
  + depeg de l'actif de la poche (EURCV, USDC…) : perte = valeur × d ; faille du protocole / du curateur : valeur × s.

POCHE « EMPRUNT » (on est emprunteur) — capital propre E = collatéral × prix − dette :
  - chute d du collatéral : perte de valeur collatéral × d ; si l'oracle suit et que HF·(1 − d) < 1 → liquidation :
    + pénalité ρ·D·(LIF − 1)  (LIF = formule officielle Morpho) ;   perte plafonnée à E
  - feed faussé VERS LE BAS de x (le vrai prix ne bouge pas) : si HF·(1 − x) < 1 → liquidation à tort :
    perte = ρ·D·(LIF/(1 − x) − 1)  (le liquidateur saisit du collatéral sous-évalué).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .market_data import G, Market
from .params import Params

GRID = np.linspace(0.0, 1.0, 41)        # sévérités relatives (0 = bas de la plage, 1 = haut)


def lif(lltv: float, p: Params) -> float:
    """Liquidation Incentive Factor (doc Morpho) : min(M, 1 / (β·LLTV + (1 − β)))."""
    return min(p["morpho_lif_max"], 1 / (p["morpho_lif_beta"] * lltv + (1 - p["morpho_lif_beta"])))


@dataclass
class Event:
    id: str
    title: str
    family: str                  # clé de params events.<family>
    target: str                  # id du nœud touché (pour le chemin de contagion)
    annual_rate: float
    sev_lo: float
    sev_hi: float
    loss_fn: Callable[[float], float]   # sévérité absolue → perte en $ de la poche
    rule: str                    # règle de transmission, en clair
    weight: float = 1.0          # part de λ (ex. 0,5 pour « vers le haut » d'un feed 50/50)
    losses: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def severities(self) -> np.ndarray:
        return self.sev_lo + GRID * (self.sev_hi - self.sev_lo)

    def tabulate(self) -> None:
        self.losses = np.array([max(0.0, self.loss_fn(s)) for s in self.severities()])

    @property
    def lgi_usd(self) -> float:
        """Perte moyenne SI l'incident arrive (sévérité uniforme dans la plage)."""
        return float(self.losses.mean())

    def p_horizon(self, days: float) -> float:
        return 1 - math.exp(-self.annual_rate * self.weight * days / 365)


# ----------------------------------------------------------------------------- poche « vault »
@dataclass
class VaultPocket:
    label: str
    value_usd: float
    value_units: float
    unit_usd: float              # prix d'une unité d'actif de la poche (EURCV, USDC…)
    holder_share: float          # part du vault détenue par le détenteur
    asset_id: str
    markets: list[Market]
    exit_fraction_now: float     # part de la poche retirable tout de suite (liquidité)
    force_penalty: float
    vault_id: str
    curator_id: str | None


def vault_market_loss(mk: Market, drop: float, tracks: bool, speed: str, slip: float) -> float:
    """Dette irrécouvrable du marché (unités prêtées) si le collatéral perd `drop`."""
    if drop <= 0 or not len(mk.debts):
        return 0.0
    if tracks and speed == "gradual":
        return 0.0                                   # liquidé à HF = 1, collatéral D/LLTV > D : prêteurs remboursés
    recovered = mk.coll_values * (1 - drop) * (1 - slip)
    return float(np.maximum(mk.debts - recovered, 0).sum())


def oracle_up_attack(mk: Market, up: float) -> float:
    k = (1 + up) * mk.lltv
    return mk.liquidity * (1 - 1 / k) if k > 1 else 0.0


def _drops(g: G, target: str, s: float) -> dict[str, float]:
    """Choc de valeur sur un actif → remonte aux actifs qui en dépendent (rachetable en, pondéré)."""
    drops, todo = {target: s}, [target]
    while todo:
        cur = todo.pop()
        for e in g.into(cur, "redeemable_into"):
            v = drops[cur] * e["weight"]
            if v > drops.get(e["from"], 0):
                drops[e["from"]] = v
                todo.append(e["from"])
    return drops


def vault_events(g: G, vp: VaultPocket, p: Params) -> list[Event]:
    ev: list[Event] = []
    E = lambda fam, k: p[f"events.{fam}.{k}"]
    slip = lambda mk: p[f"liquidation_slippage.{mk.collateral_class}"]
    to_usd = vp.holder_share * vp.unit_usd

    def market_share(mk: Market) -> float:
        return mk.our_supply / mk.supply if mk.supply else 0.0

    # 1. chute de chaque collatéral (la famille dépend de la façon dont l'oracle le price)
    seen = set()
    for mk in vp.markets:
        if mk.collateral_id in seen:
            continue
        seen.add(mk.collateral_id)
        fam = "volatile_crash" if mk.collateral_class == "volatile" else "rwa_credit_event"
        speed = vp_speed(p, fam)
        tracks_override = p.raw["events"][fam].get("oracle_tracks")

        def loss(s, cid=mk.collateral_id, fam=fam, speed=speed, tro=tracks_override):
            drops = _drops(g, cid, s)
            tot = 0.0
            for m in vp.markets:
                d = drops.get(m.collateral_id, 0.0)
                tracks = m.tracks_market if tro is None else (tro and m.tracks_market)
                tot += market_share(m) * vault_market_loss(m, d, tracks, speed, slip(m))
            return tot * to_usd
        lo, hi = E(fam, "severity")
        rule = ("chute progressive d'un collatéral pricé au marché : les emprunteurs sont liquidés à temps (HF = 1), "
                "le prêteur ne perd rien — sauf choc brutal" if fam == "volatile_crash" else
                "choc brutal sur un collatéral dont l'oracle NE suit PAS le marché (taux interne / prix posé) : pas de "
                "liquidation à temps → dette irrécouvrable max(0, D − V·(1−d)·(1−glissement)), emprunteur par emprunteur")
        ev.append(Event(f"{fam}:{mk.collateral_id}", f"Chute du collatéral {mk.collateral_symbol}", fam,
                        mk.collateral_id, E(fam, "annual_rate"), lo, hi, loss, rule))

    # 2. feeds de prix : faux vers le haut (attaque de la liquidité) — vers le bas ne coûte rien au prêteur
    feeds = {}
    for mk in vp.markets:
        for f in mk.feeds:
            feeds.setdefault(f.node_id, (f, []))[1].append(mk)
    for fid, (f, mks) in feeds.items():
        if f.mode == "fixed" and f.bounds is None:
            continue                                   # constante / formule : rien à fausser
        fam = ("admin_feed_compromise" if f.kind == "midas_custom_aggregator_feed"
               else "internal_rate_fault" if f.mode == "internal_rate" else "oracle_fault")
        if f.bounds:                                   # bornes on-chain : l'admin ne peut pas aller au-delà
            lo = hi = f.bounds[1] if f.role == "base" else f.bounds[0]
            weight = 1.0
        else:
            lo, hi = E(fam, "severity")
            weight = 0.5                               # 50 % vers le haut (cas qui coûte au prêteur)

        def loss(s, mks=mks):
            return sum(market_share(m) * oracle_up_attack(m, s) for m in mks) * to_usd
        ev.append(Event(f"{fam}:{fid}", f"Feed {f.label} faussé (prix du collatéral surévalué)", fam, fid,
                        E(fam, "annual_rate"), lo, hi, loss,
                        "un attaquant emprunte la liquidité disponible L contre du collatéral surévalué : "
                        "perte = L·(1 − 1/((1+u)·LLTV)) si (1+u)·LLTV > 1", weight=weight))

    # 3. l'actif de la poche lui-même (EURCV, USDC…) et ses émetteurs
    lo, hi = E("stable_depeg", "severity")
    ev.append(Event(f"stable_depeg:{vp.asset_id}", f"Depeg de {g.nodes[vp.asset_id]['label']} (actif de la poche)",
                    "stable_depeg", vp.asset_id, E("stable_depeg", "annual_rate"), lo, hi,
                    lambda s: vp.value_usd * s, "la poche est libellée dans cet actif : perte = valeur × d"))
    ev += issuer_events(g, p, vp.asset_id, lambda s: vp.value_usd * s, vault=vp)

    # 4. protocole et curateur
    lo, hi = E("protocol_exploit", "severity")
    mid = next((e["to"] for e in g.out(vp.markets[0].node_id, "issued_by")), vp.markets[0].node_id) if vp.markets else vp.vault_id
    ev.append(Event("protocol_exploit:morpho", "Faille du protocole Morpho Blue", "protocol_exploit", mid,
                    E("protocol_exploit", "annual_rate"), lo, hi, lambda s: vp.value_usd * s,
                    "tous les fonds déposés sont exposés : perte = valeur × s"))
    if vp.curator_id:
        lo, hi = E("curator_failure", "severity")
        ev.append(Event(f"curator_failure:{vp.curator_id}", f"Défaillance du curateur ({g.nodes[vp.curator_id]['label']})",
                        "curator_failure", vp.curator_id, E("curator_failure", "annual_rate"), lo, hi,
                        lambda s: vp.value_usd * s, "mauvaise allocation bornée par les plafonds : perte = valeur × s"))
    return ev


def vp_speed(p: Params, fam: str) -> str:
    return p.raw["events"][fam]["speed"]


def issuer_events(g: G, p: Params, asset_id: str, loss: Callable[[float], float], vault=None) -> list[Event]:
    out = []
    lo, hi = p["events.issuer_failure.severity"]
    for e in g.out(asset_id, "issued_by"):
        iss = g.nodes[e["to"]]
        if iss["meta"].get("role") == "vault_curator":
            continue
        out.append(Event(f"issuer_failure:{e['to']}", f"Défaillance de l'émetteur {iss['label']} ({g.nodes[asset_id]['label']})",
                         "issuer_failure", e["to"], p["events.issuer_failure.annual_rate"], lo, hi, loss,
                         "l'actif émis perd s de sa valeur"))
    return out


# ----------------------------------------------------------------------------- poche « emprunt »
@dataclass
class BorrowPocket:
    label: str
    value_usd: float             # capital propre en $
    unit_usd: float              # prix de l'actif prêté
    market: Market
    collateral_value: float      # en unités prêtées (prix oracle)
    debt: float
    hf: float

    @property
    def equity(self) -> float:
        return max(self.collateral_value - self.debt, 0.0)


def borrow_loss_drop(bp: BorrowPocket, d: float, tracks: bool, p: Params, beta: bool = False) -> float:
    """beta=True : chute d'un actif volatil = exposition de marché choisie → seule la LIQUIDATION compte
    (paramètre borrow_market_beta_excluded) ; beta=False : perte de valeur propre au collatéral (RWA, depeg)."""
    loss = 0.0 if (beta and p["borrow_market_beta_excluded"]) else bp.collateral_value * d
    if tracks and bp.hf * (1 - d) < 1:
        loss += p["liquidation_repaid_fraction"] * bp.debt * (lif(bp.market.lltv, p) - 1)
    return min(loss, bp.equity) * bp.unit_usd


def borrow_events(g: G, bp: BorrowPocket, p: Params) -> list[Event]:
    mk, E = bp.market, (lambda fam, k: p[f"events.{fam}.{k}"])
    ev = []
    fam = "volatile_crash" if mk.collateral_class == "volatile" else "rwa_credit_event"
    tro = p.raw["events"][fam].get("oracle_tracks")
    tracks = mk.tracks_market if tro is None else (tro and mk.tracks_market)
    lo, hi = E(fam, "severity")
    beta = fam == "volatile_crash"
    rule = ("chute d'un actif volatil : exposition de marché choisie, seule la liquidation compte "
            "(pénalité ρ·D·(LIF−1) si HF·(1−d) < 1)" if beta and p["borrow_market_beta_excluded"] else
            "perte de valeur propre au collatéral ; + pénalité de liquidation ρ·D·(LIF−1) si l'oracle suit et HF·(1−d) < 1")
    ev.append(Event(f"{fam}:{mk.collateral_id}", f"Chute du collatéral {mk.collateral_symbol}", fam, mk.collateral_id,
                    E(fam, "annual_rate"), lo, hi, lambda s: borrow_loss_drop(bp, s, tracks, p, beta), rule))
    ev += issuer_events(g, p, mk.collateral_id, lambda s: borrow_loss_drop(bp, s, mk.tracks_market, p))
    rho, L = p["liquidation_repaid_fraction"], lif(mk.lltv, p)
    for f in mk.feeds:
        if f.mode == "fixed" and f.bounds is None:
            continue
        fam_f = ("admin_feed_compromise" if f.kind == "midas_custom_aggregator_feed"
                 else "internal_rate_fault" if f.mode == "internal_rate" else "oracle_fault")
        if f.bounds:
            lo = hi = f.bounds[0] if f.role == "base" else f.bounds[1]
            weight = 1.0
        else:
            lo, hi = E(fam_f, "severity")
            weight = 0.5                                     # 50 % vers le bas (cas qui coûte à l'emprunteur)

        def loss(x):
            if bp.hf * (1 - x) >= 1:
                return 0.0
            return min(rho * bp.debt * (L / (1 - x) - 1), bp.equity) * bp.unit_usd
        ev.append(Event(f"{fam_f}:{f.node_id}", f"Feed {f.label} faussé vers le bas (liquidation à tort)", fam_f, f.node_id,
                        E(fam_f, "annual_rate"), lo, hi, loss,
                        "si HF·(1−x) < 1 : liquidation à tort, perte = ρ·D·(LIF/(1−x) − 1)", weight=weight))
    lo, hi = E("protocol_exploit", "severity")
    mid = next((e["to"] for e in g.out(mk.node_id, "issued_by")), mk.node_id)
    ev.append(Event("protocol_exploit:morpho", "Faille du protocole Morpho Blue", "protocol_exploit", mid,
                    E("protocol_exploit", "annual_rate"), lo, hi,
                    lambda s: min(bp.collateral_value * s, bp.equity) * bp.unit_usd,
                    "collatéral volé : perte = min(collatéral × s, capital propre)"))
    return ev


# ----------------------------------------------------------------------------- Monte Carlo
def monte_carlo(events: list[Event], cap_usd: float, days: float, p: Params) -> dict:
    """Chaque incident survient (ou pas) sur l'horizon ; sévérité uniforme dans sa plage ; pertes additionnées,
    plafonnées à la valeur de la poche. Événements supposés indépendants (limite affichée)."""
    n, rng = int(p["monte_carlo.samples"]), np.random.default_rng(int(p["monte_carlo.seed"]))
    total = np.zeros(n)
    for e in events:
        if not len(e.losses):
            e.tabulate()
        hit = rng.random(n) < e.p_horizon(days)
        u = rng.random(n)
        total += np.where(hit, np.interp(u, GRID, e.losses), 0.0)
    total = np.minimum(total, cap_usd)
    return {"samples": n, "horizon_days": days, "expected_loss_usd": float(total.mean()),
            "var95_usd": float(np.quantile(total, 0.95)), "var99_usd": float(np.quantile(total, 0.99)),
            "var999_usd": float(np.quantile(total, 0.999)),
            "p_any_loss": float((total > 0).mean()),
            "independence_note": "incidents tirés indépendamment (corrélations entre nœuds non modélisées)"}
