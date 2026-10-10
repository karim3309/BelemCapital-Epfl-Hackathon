"""Propagation d'un choc dans le graphe : « si CE nœud casse, qu'arrive-t-il aux autres ? »

Image : des dominos. Une flèche A → B veut dire « A dépend de B ». Quand B tombe, la secousse
remonte vers A, puis vers ce qui dépend de A… jusqu'à la position. Chaque TYPE de flèche a sa
propre règle, écrite en clair ci-dessous (RULES) et appliquée mécaniquement :

  redeemable_into  (PT → SY → sUSDe → USDe) : la valeur suit celle de ce contre quoi on s'échange.
  issued_by        (USDe → Ethena)          : si l'émetteur perd une part de ses réserves, son jeton
                                              « de base » perd la même part (pas de double comptage :
                                              sUSDe hérite de la perte via USDe, pas une 2e fois).
  deployed_in      (Ethena → exchange)      : si une contrepartie fait défaut, l'émetteur perd la part de
                                              ses réserves qui y était exposée (paramètre affiché).
  deployed_in      (PT → pool Pendle)       : un pool qui se vide ne change pas la valeur du PT, mais le
                                              coût pour SORTIR (et la rentabilité des liquidations).
  priced_by        (marché → oracle → feed) : un feed « market » transmet le prix de marché, un feed
                                              « fixed » ne transmet rien, un méta-oracle choisit selon
                                              sa règle de bascule (voir oracle_sim.py).
  collateralized_by / lends                 : le marché encaisse la variation du collatéral / de la dette
                                              (voir position.py).

Le résultat est un « monde choqué » (World) : pour chaque actif, un multiplicateur de valeur
(1,00 = inchangé ; 0,90 = −10 %), plus l'état des feeds, des pools et des protocoles.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from .graphview import GraphView
from .fmt import pct

RULES = {
    "deployed_in": "les fonds placés dans « {to} » subissent sa défaillance (ou sa liquidité, pour un pool)",
    "collateralized_by": "le marché est garanti par « {to} » : si sa valeur baisse, la santé des emprunteurs baisse",
    "lends": "le marché prête « {to} » : la dette est libellée dans cet actif",
    "priced_by": "« {from_} » tire son prix de « {to} » : le choc passe seulement si « {to} » suit le marché",
    "redeemable_into": "« {from_} » s'échange contre « {to} » : sa valeur suit celle de « {to} »",
    "issued_by": "« {from_} » est émis par « {to} » : une perte de réserves de l'émetteur le déprécie",
    "settled_on": "« {from_} » fonctionne sur « {to} » : un arrêt de la chaîne bloque liquidations et sorties",
}

SHOCK_KINDS = {"market_depeg", "counterparty_failure", "issuer_failure", "protocol_exploit",
               "feed_fault", "feed_frozen", "liquidity_drain", "chain_halt"}


@dataclass
class Shock:
    node: str                          # id du nœud ciblé dans graph.json
    kind: str                          # voir SHOCK_KINDS
    severity: float = 0.0              # perte (0..1) ; feed_fault : écart du prix rapporté ; liquidity_drain : liquidité perdue
    duration_hours: float | None = None   # None = permanent (dépasse l'horizon)
    panic: float = 0.0                 # décote de panique additionnelle (défaillance de contrepartie)
    label: str = ""

    def __post_init__(self):
        if self.kind not in SHOCK_KINDS:
            raise ValueError(f"type de choc inconnu : {self.kind}")
        if not 0 <= self.severity <= 1:
            raise ValueError("severity doit être dans [0, 1]")

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class World:
    asset_mult: dict[str, float] = field(default_factory=dict)
    issuer_health: dict[str, float] = field(default_factory=dict)
    feed_override: dict[str, tuple] = field(default_factory=dict)   # id → ("fault", mult) | ("frozen", None)
    pool_factor: dict[str, float] = field(default_factory=dict)
    protocol_loss: dict[str, float] = field(default_factory=dict)   # émetteur de protocole → part perdue
    chain_halted: bool = False
    duration_hours: float | None = 0.0    # durée du choc (None = permanent)
    trace: list[str] = field(default_factory=list)                  # règles appliquées, en clair

    def mult(self, asset_id: str) -> float:
        return self.asset_mult.get(asset_id, 1.0)


def counterparty_share(role: str | None, params) -> tuple[float, str]:
    if role == "custodian_off_exchange_settlement":
        return params["custodian_backing_share"], "custodian_backing_share"
    if role == "hedging_venue":
        return params["exchange_exposure_share"], "exchange_exposure_share"
    return 1.0, "exposition totale (rôle inconnu)"


def _combined_duration(shocks: list[Shock]) -> float | None:
    if not shocks:
        return 0.0
    if any(s.duration_hours is None for s in shocks):
        return None
    return max(s.duration_hours for s in shocks)


def propagate(gv: GraphView, shocks: list[Shock], params) -> World:
    w = World(duration_hours=_combined_duration(shocks))
    own_mult: dict[str, float] = {}
    issuer_own: dict[str, float] = {}
    cp_loss: dict[str, float] = {}
    panic: dict[str, float] = {}

    # 1) effet DIRECT de chaque choc sur son nœud
    for s in shocks:
        if s.node not in gv.nodes:
            raise ValueError(f"choc sur un nœud absent du graphe : {s.node}")
        if s.kind == "market_depeg":
            own_mult[s.node] = own_mult.get(s.node, 1.0) * (1 - s.severity)
            w.trace.append(f"{s.node} perd {pct(s.severity, 1)} de sa valeur de marché (choc direct)")
        elif s.kind == "counterparty_failure":
            cp_loss[s.node] = max(cp_loss.get(s.node, 0.0), s.severity)
            for issuer in gv.sources(s.node, "deployed_in"):
                panic[issuer] = max(panic.get(issuer, 0.0), s.panic)
            w.trace.append(f"{s.node} fait défaut : {pct(s.severity, 0)} des fonds qui y sont placés sont perdus")
        elif s.kind == "issuer_failure":
            issuer_own[s.node] = issuer_own.get(s.node, 1.0) * (1 - s.severity)
            w.trace.append(f"l'émetteur {s.node} perd {pct(s.severity, 0)} de sa valeur (exploit / défaillance)")
        elif s.kind == "protocol_exploit":
            w.protocol_loss[s.node] = max(w.protocol_loss.get(s.node, 0.0), s.severity)
            w.trace.append(f"exploit du protocole {s.node} : {pct(s.severity, 0)} des fonds déposés perdus")
        elif s.kind == "feed_fault":
            w.feed_override[s.node] = ("fault", 1 - s.severity)
            w.trace.append(f"le feed {s.node} rapporte un prix FAUX, {pct(s.severity, 0)} sous le vrai prix")
        elif s.kind == "feed_frozen":
            w.feed_override[s.node] = ("frozen", None)
            w.trace.append(f"le feed {s.node} est FIGÉ : il ne voit plus le marché")
        elif s.kind == "liquidity_drain":
            w.pool_factor[s.node] = min(w.pool_factor.get(s.node, 1.0), 1 - s.severity)
            w.trace.append(f"le pool {s.node} perd {pct(s.severity, 0)} de sa liquidité")
        elif s.kind == "chain_halt":
            w.chain_halted = True
            w.trace.append(f"la chaîne {s.node} est à l'arrêt : ni liquidation ni sortie possibles")

    # 2) santé des ÉMETTEURS (réserves exposées aux contreparties hors chaîne)
    for issuer in [n["id"] for n in gv.of_type("issuer")]:
        h = issuer_own.get(issuer, 1.0)
        for cp in gv.targets(issuer, "deployed_in"):
            if cp in cp_loss:
                share, pname = counterparty_share(gv.meta(cp).get("role"), params)
                h *= 1 - share * cp_loss[cp]
                w.trace.append(RULES["deployed_in"].format(to=cp)
                               + f" → {issuer} perd {pct(share * cp_loss[cp], 2)} de ses réserves (part exposée : {pname} = {share:g})")
        if panic.get(issuer):
            h *= 1 - panic[issuer]
            w.trace.append(f"panique sur les jetons de {issuer} : décote supplémentaire de {pct(panic[issuer], 1)}")
        if h != 1.0:
            w.issuer_health[issuer] = h

    # 3) valeur des ACTIFS, des dépendances vers les dépendants (ordre topologique inversé)
    assets = [n["id"] for n in gv.of_type("asset")]
    dag = nx.DiGraph()
    dag.add_nodes_from(assets)
    for a in assets:
        for b in gv.targets(a, "redeemable_into"):
            dag.add_edge(a, b)
    order = list(reversed(list(nx.topological_sort(dag))))
    for a in order:
        m = own_mult.get(a, 1.0)
        for b in gv.targets(a, "redeemable_into"):
            if w.mult(b) != 1.0:
                w.trace.append(RULES["redeemable_into"].format(from_=a, to=b) + f" → ×{w.mult(b):.4f}")
            m *= w.mult(b)
        # pas de double comptage : un émetteur déjà présent plus bas dans la chaîne de rachat est ignoré ici
        downstream_issuers = {i for d in nx.descendants(dag, a) for i in gv.targets(d, "issued_by")}
        for issuer in gv.targets(a, "issued_by"):
            if issuer in w.issuer_health and issuer not in downstream_issuers:
                w.trace.append(RULES["issued_by"].format(from_=a, to=issuer) + f" → ×{w.issuer_health[issuer]:.4f}")
                m *= w.issuer_health[issuer]
        if m != 1.0:
            w.asset_mult[a] = m
    return w


def contagion_paths(gv: GraphView, node: str, max_paths: int = 3) -> list[dict]:
    """Chemins position → nœud choqué, chaque arête avec sa preuve et sa règle de transmission."""
    out = []
    for path in gv.paths_from_position(node, max_paths=max_paths):
        out.append({
            "nodes": [path[0]["from"]] + [e["to"] for e in path],
            "edges": [{**e, "rule": RULES[e["type"]].format(from_=e["from"], to=e["to"])} for e in path],
        })
    return out
