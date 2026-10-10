"""Simulateur d'oracle : quel prix Morpho verra-t-il PENDANT le choc ?

Rappel (GUIDE_DEBUTANT §8) : l'oracle est l'expert qui estime le gage. Morpho le croit aveuglément.
On rejoue l'arbre d'oracles découvert dans graph.json, brique par brique :

  - feed « market » (Chainlink)       : il voit le choc → valeur × multiplicateur de l'actif mesuré ;
                                        sauf s'il est en panne (prix faux) ou figé (ne voit rien) ;
  - feed « fixed » (décote linéaire)  : il ne voit RIEN du marché ; seule l'horloge le fait bouger
                                        (prix = 1 − décote × temps restant) ;
  - feed constant (« Dummy »)          : toujours la même valeur ;
  - MorphoChainlinkOracleV2           : prix = SCALE × feeds de base / feeds de cotation, donc on
                                        multiplie le prix normal par la variation de chaque brique ;
  - MÉTA-ORACLE (Steakhouse)          : deux experts et un arbitre. Écart = |primaire − secours| /
                                        moyenne. Si l'écart dépasse le seuil, n'importe qui appelle
                                        challenge() ; si l'écart tient encore après le délai
                                        (challengeTimelock, lu on-chain : 16 h), on BASCULE sur le secours.
    → la DURÉE du choc compte autant que son ampleur : c'est le cœur de notre analyse.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .graphview import GraphView
from .propagate import World

YEAR = 365 * 86400


@dataclass
class OracleEval:
    node: str
    kind: str
    price_normal: float
    price: float                       # prix vu par Morpho pendant le choc (après décision de bascule)
    mode: str                          # mode de prix EFFECTIF pendant le choc
    switched: bool = False
    switch_after_hours: float | None = None
    deviation: float | None = None
    challenge_possible: bool = False
    timeline: list[dict] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    children: list["OracleEval"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "children"}
        d["children"] = [c.to_dict() for c in self.children]
        return d


def _linear_answer(meta: dict, ts: float) -> float:
    left = max(meta["maturity"] - ts, 0)
    return 1 - meta["base_discount_per_year"] * left / YEAR


def _feed(gv: GraphView, fid: str, world: World, ts_offset: float) -> tuple[float, float, str, list[str]]:
    """(valeur normale, valeur choquée, mode, trace) d'un feed, en unités « humaines »."""
    meta, kind = gv.meta(fid), gv.meta(fid).get("oracle_kind")
    now = gv.snapshot()["timestamp"]
    if kind == "pendle_linear_discount_feed":
        normal = _linear_answer(meta, now + ts_offset)
        return normal, normal, "fixed", [f"{fid} : formule de décote, insensible au marché ({normal:.6f})"]
    if kind == "constant_feed":
        return meta["answer"], meta["answer"], "fixed", [f"{fid} : constant ({meta['answer']})"]
    normal = meta.get("answer") or 1.0
    override = world.feed_override.get(fid)
    if override and override[0] == "frozen":
        return normal, normal, "market", [f"{fid} : FIGÉ, ne voit pas le choc"]
    if meta.get("pricing_mode") == "market":
        asset = gv.feed_priced_asset(fid)
        m = world.mult(asset) if asset else 1.0
        shocked = normal * m
        trace = [f"{fid} suit le marché de {asset} : {normal:.5f} → {shocked:.5f}"]
        if override and override[0] == "fault":
            shocked = normal * override[1]
            trace.append(f"{fid} en PANNE : rapporte {shocked:.5f} quel que soit le marché")
        return normal, shocked, "market", trace
    return normal, normal, meta.get("pricing_mode", "unknown"), [f"{fid} : mode {meta.get('pricing_mode')} — pas de transmission prouvée"]


def evaluate(gv: GraphView, oid: str, world: World, params, ts_offset: float = 0.0) -> OracleEval:
    meta = gv.meta(oid)
    kind = meta.get("oracle_kind", "unknown")

    if kind == "morpho_meta_oracle_deviation_timelock":
        return _meta(gv, oid, world, params, ts_offset)

    if kind in ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1"):
        ratio, modes, trace, children = 1.0, [], [], []
        now = gv.snapshot()["timestamp"]
        for slot, comp in meta.get("components", {}).items():
            if not comp.get("address") or comp.get("pricing_mode") == "internal_rate":
                continue      # slot vide (= 1) ou taux interne : insensible au choc de marché
            node = gv.by_address(comp["address"])
            if node is None:
                continue
            normal_now = gv.meta(node["id"]).get("answer")
            normal, shocked, mode, t = _feed(gv, node["id"], world, ts_offset)
            # variation par rapport à la valeur LUE au bloc (le prix normal de l'oracle y correspond)
            if normal_now:
                factor = shocked / normal_now
                ratio *= factor if comp["role"] == "base" else 1 / factor
            modes.append(mode)
            trace += t
            children.append(OracleEval(node=node["id"], kind=gv.meta(node["id"]).get("oracle_kind"),
                                       price_normal=normal, price=shocked, mode=mode, trace=t))
        base = meta["price"]
        # prix « normal » à la date décalée (S-TIME) : seule la décote linéaire bouge avec l'horloge
        time_ratio = 1.0
        for c in children:
            if c.kind == "pendle_linear_discount_feed":
                time_ratio *= _linear_answer(gv.meta(c.node), now + ts_offset) / gv.meta(c.node)["answer"]
        price_normal = base * time_ratio
        mode = "market" if "market" in modes else ("fixed" if modes else "fixed")
        return OracleEval(node=oid, kind=kind, price_normal=price_normal, price=base * ratio,
                          mode=mode, trace=trace, children=children)

    # Oracle non reconnu : on ne devine pas
    price = meta.get("price") or meta.get("answer") or 0.0
    return OracleEval(node=oid, kind=kind, price_normal=price, price=price, mode="unknown",
                      trace=[f"{oid} non reconnu : prix supposé inchangé (à analyser)"])


def deviation(a: float, b: float) -> float:
    """Formule de la doc Steakhouse : |primaire − secours| / moyenne(primaire, secours)."""
    return abs(a - b) / ((a + b) / 2) if a + b else 0.0


def _meta(gv: GraphView, oid: str, world: World, params, ts_offset: float) -> OracleEval:
    meta = gv.meta(oid)
    primary = evaluate(gv, gv.by_address(meta["primary_oracle"])["id"], world, params, ts_offset)
    backup = evaluate(gv, gv.by_address(meta["backup_oracle"])["id"], world, params, ts_offset)
    thr = params["meta_oracle_deviation_threshold"]
    challenge_h = params["meta_oracle_challenge_timelock_seconds"] / 3600
    healing_h = params["meta_oracle_healing_timelock_seconds"] / 3600
    delay_h = params["challenger_delay_hours"]
    dev = deviation(primary.price, backup.price)
    possible = dev > thr
    duration = world.duration_hours
    needed = delay_h + challenge_h
    lasts = duration is None or duration >= needed
    start_backup = meta.get("current_role") == "backup"

    tl = [{"t_hours": 0, "event": f"choc : écart primaire/secours = {dev:.2%} (seuil {thr:.2%})",
           "role": "backup" if start_backup else "primary"}]
    trace = [f"écart = |{primary.price:.6f} − {backup.price:.6f}| / moyenne = {dev:.3%} ; seuil = {thr:.3%}"]
    switched = start_backup
    if not start_backup and possible and world.chain_halted:
        trace.append("chaîne à l'arrêt : personne ne peut appeler challenge() → pas de bascule")
    elif not start_backup and possible:
        tl.append({"t_hours": delay_h, "event": "challenge() appelé (fonction sans permission)", "role": "primary"})
        if lasts:
            switched = True
            tl.append({"t_hours": needed, "event": f"acceptChallenge() après {challenge_h:.0f} h → BASCULE sur le secours",
                       "role": "backup"})
            trace.append(f"l'écart dure ≥ {needed:.0f} h → bascule sur le secours ({backup.mode})")
        else:
            tl.append({"t_hours": duration, "event": "fin du choc avant la fin du délai → revokeChallenge(), pas de bascule",
                       "role": "primary"})
            trace.append(f"le choc dure {duration:g} h < {needed:.0f} h → PAS de bascule, le prix reste {primary.mode}")
    else:
        trace.append("écart sous le seuil → pas de challenge possible, le primaire reste en place")
    if switched and duration is not None and not start_backup:
        tl.append({"t_hours": duration, "event": "fin du choc : les prix reconvergent → heal()", "role": "backup"})
        tl.append({"t_hours": duration + healing_h, "event": f"acceptHealing() après {healing_h:.0f} h → retour au primaire",
                   "role": "primary"})

    chosen = backup if switched else primary
    return OracleEval(node=oid, kind="morpho_meta_oracle_deviation_timelock",
                      price_normal=primary.price_normal if not start_backup else backup.price_normal,
                      price=chosen.price, mode=chosen.mode, switched=switched and not start_backup,
                      switch_after_hours=needed if (switched and not start_backup) else None,
                      deviation=dev, challenge_possible=possible, timeline=tl,
                      trace=trace + primary.trace + backup.trace, children=[primary, backup])
