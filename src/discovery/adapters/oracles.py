"""Oracles : QUI dit à Morpho combien vaut le collatéral ?  (le point le plus important de la position A)

Morpho appelle `oracle.price()` et lui fait aveuglément confiance. Ce nombre est le prix
d'1 unité de collatéral en unités de l'actif prêté, à l'échelle 1e(36 + déc_prêt − déc_collatéral).

Un oracle Morpho est souvent un ASSEMBLEUR de briques. On le démonte récursivement :
  - méta-oracle (primaire + secours, bascule si écart)   → pricing_mode "hybrid"
  - MorphoChainlinkOracleV2 : prix = SCALE × vaults × BASE_FEED_1 × BASE_FEED_2 / (QUOTE_FEED_1 × QUOTE_FEED_2)
        ⚠ un slot à l'adresse 0x0 vaut 1 : c'est un prix FIXÉ implicite (ex. « 1 USDe = 1 USDC »)
  - feed Pendle à décote linéaire : prix = 1 − décote × temps restant  → "fixed" (ignore le marché)
  - feed Chainlink (prouvé via ENS data.eth)                              → "market"
  - feed constant / « dummy » (sert juste à ajuster des décimales)        → "fixed"
  - feed ERC-4626 (convertToAssets)                                        → "internal_rate"
Tout ce qu'on ne reconnaît pas est marqué `unresolved` : on ne devine JAMAIS un mode de prix.
"""
from __future__ import annotations

from ..ctx import Ctx, checksum, is_zero
from ..graph import Edge, Node
from ..ids import contract_id, slugify
from . import Discovery, Task, jsonable, scaled
from .contracts import proxy_info
from .ens import chainlink_ens_name, resolve

CHAINLINK_ISSUER_KEY = "issuer:chainlink"
CHAINLINK_ENS_DOC = "https://docs.chain.link/data-feeds/ens"
STEAKHOUSE_DOC = "https://steakhouse.financial/docs/products/infrastructure/metaoracle"

ROUND = ("latestRoundData()", ["uint80", "int256", "uint256", "uint256", "uint80"])
META_PROBES = [("primaryOracle()", ["address"]), ("backupOracle()", ["address"]), ("currentOracle()", ["address"])]
MCO_V2_PROBES = [("BASE_FEED_1()", ["address"]), ("QUOTE_FEED_1()", ["address"]),
                 ("SCALE_FACTOR()", ["uint256"]), ("BASE_VAULT()", ["address"])]
MCO_V1_PROBES = [("BASE_FEED_1()", ["address"]), ("QUOTE_FEED_1()", ["address"]),
                 ("SCALE_FACTOR()", ["uint256"]), ("VAULT()", ["address"])]
LINEAR_PROBES = [("PT()", ["address"]), ("maturity()", ["uint256"]), ("baseDiscountPerYear()", ["uint256"]), ROUND]
# ⚠ Sondes du feed Pendle TWAP NON VÉRIFIÉES sur un contrat réel (pas présent dans la position A) :
#    à confirmer sur Etherscan / doc Pendle avant de s'y fier (voir docs/VERIFY.md).
PENDLE_TWAP_PROBES = [("market()", ["address"]), ("twapDuration()", ["uint32"]), ROUND]
CL_PROXY_PROBES = [("aggregator()", ["address"]), ("phaseId()", ["uint16"]), ("description()", ["string"]), ROUND]
CL_COMPATIBLE_PROBES = [ROUND, ("decimals()", ["uint8"])]

KIND_LABEL = {
    "morpho_meta_oracle_deviation_timelock": "MetaOracleDeviationTimelock",
    "morpho_chainlink_oracle_v2": "MorphoChainlinkOracleV2",
    "morpho_chainlink_oracle_v1": "MorphoChainlinkOracle",
    "pendle_linear_discount_feed": "PendleLinearDiscountFeed",
    "pendle_twap_feed": "PendleTwapFeed",
    "chainlink_aggregator_proxy": "ChainlinkFeed",
    "constant_feed": "ConstantFeed",
    "chainlink_compatible_unknown": "UnknownChainlinkCompatibleFeed",
    "unknown_morpho_oracle": "UnknownOracle",
    "unknown": "UnknownContract",
}
STATIC_MODE = {
    "morpho_meta_oracle_deviation_timelock": "hybrid",
    "pendle_linear_discount_feed": "fixed",
    "pendle_twap_feed": "market",
    "chainlink_aggregator_proxy": "market",
    "constant_feed": "fixed",
    "chainlink_compatible_unknown": "unknown",
    "unknown_morpho_oracle": "unknown",
    "unknown": "unknown",
}


def latest_round(ctx: Ctx, address: str) -> tuple:
    """(roundId, answer, startedAt, updatedAt, answeredInRound) — interface AggregatorV3 de Chainlink."""
    return ctx.call(address, ROUND[0], returns=ROUND[1])


# ======================================================================= classification
def classify_oracle(ctx: Ctx, address: str) -> str:
    if ctx.has_functions(address, META_PROBES):
        return "morpho_meta_oracle_deviation_timelock"
    if ctx.has_functions(address, MCO_V2_PROBES):
        return "morpho_chainlink_oracle_v2"
    if ctx.has_functions(address, MCO_V1_PROBES):
        return "morpho_chainlink_oracle_v1"
    if ctx.has_functions(address, LINEAR_PROBES):
        return "pendle_linear_discount_feed"
    if ctx.has_functions(address, PENDLE_TWAP_PROBES):
        return "pendle_twap_feed"
    if ctx.has_functions(address, CL_PROXY_PROBES):
        return "chainlink_aggregator_proxy"
    if ctx.has_functions(address, CL_COMPATIBLE_PROBES):
        return "constant_feed" if _looks_constant(ctx, address) else "chainlink_compatible_unknown"
    if ctx.try_call(address, "price()", returns=["uint256"]) is not None:
        return "unknown_morpho_oracle"
    return "unknown"


def _looks_constant(ctx: Ctx, address: str) -> bool:
    """Un vrai feed stocke des « rounds » mis à jour par des opérateurs. Un feed constant renvoie
    roundId ≤ 1 et un updatedAt = horodatage du bloc courant (calculé à la volée, rien n'est stocké)."""
    round_id, _, _, updated_at, _ = latest_round(ctx, address)
    return round_id <= 1 and updated_at == ctx.block_timestamp


def mode_of(ctx: Ctx, address: str, kind: str | None = None) -> str:
    kind = kind or classify_oracle(ctx, address)
    if kind in ("morpho_chainlink_oracle_v2", "morpho_chainlink_oracle_v1"):
        return _mco_components(ctx, address, kind)[1]
    return STATIC_MODE[kind]


def _combine(modes: list[str]) -> str:
    if not modes:
        return "fixed"          # aucun composant : prix entièrement codé en dur
    if "unknown" in modes:
        return "unknown"
    if "market" in modes or "hybrid" in modes:
        return "market"
    if "internal_rate" in modes:
        return "internal_rate"
    return "fixed"


# ======================================================================= découverte
def discover_oracle(ctx: Ctx, address: str, scale_decimals: int | None = None) -> Discovery:
    """scale_decimals = 36 + déc_prêt − déc_collatéral (fourni par le marché Morpho pour lire price())."""
    address = checksum(address)
    kind = classify_oracle(ctx, address)
    ctx.labels[address] = KIND_LABEL[kind]
    handler = {
        "morpho_meta_oracle_deviation_timelock": _meta_oracle,
        "morpho_chainlink_oracle_v2": _mco,
        "morpho_chainlink_oracle_v1": _mco,
        "pendle_linear_discount_feed": _linear_discount,
        "pendle_twap_feed": _pendle_twap,
        "chainlink_aggregator_proxy": _chainlink_proxy,
        "constant_feed": _constant_feed,
    }.get(kind, _unknown)
    d = handler(ctx, address, kind, scale_decimals)
    node = d.nodes[0]
    proxy = proxy_info(ctx, address)
    if proxy:
        node.meta["proxy"] = proxy
    return d


def _node(address: str, kind: str, id_hint: str, label: str, meta: dict) -> Node:
    return Node(key=address, type="oracle", label=label, id_hint=id_hint, address=address,
                meta={"oracle_kind": kind, **meta})


def _morpho_price(ctx: Ctx, address: str, scale_decimals: int | None) -> dict:
    raw = ctx.try_call(address, "price()", returns=["uint256"])
    out = {"price_raw": jsonable(raw)}
    if raw is not None and scale_decimals is not None:
        out["price"] = scaled(raw, scale_decimals)
        out["price_scale"] = f"1e{scale_decimals}"
    return out


# ---- méta-oracle primaire / secours -------------------------------------------------
def _meta_oracle(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    primary = ctx.call(a, "primaryOracle()", returns=["address"])
    backup = ctx.call(a, "backupOracle()", returns=["address"])
    current = ctx.call(a, "currentOracle()", returns=["address"])
    thr = ctx.try_call(a, "deviationThreshold()", returns=["uint256"])
    meta = {
        "pricing_mode": "hybrid",
        "primary_oracle": primary,
        "backup_oracle": backup,
        "current_oracle": current,
        "current_role": "primary" if current == primary else ("backup" if current == backup else "other"),
        "effective_pricing_mode": mode_of(ctx, current),
        "primary_pricing_mode": mode_of(ctx, primary),
        "backup_pricing_mode": mode_of(ctx, backup),
        "deviation_threshold": scaled(thr, 18) if thr is not None else None,
        "current_deviation": scaled(v, 18) if (v := ctx.try_call(a, "getDeviation()", returns=["uint256"])) is not None else None,
        "challenge_timelock_seconds": ctx.try_call(a, "challengeTimelockDuration()", returns=["uint256"]),
        "healing_timelock_seconds": ctx.try_call(a, "healingTimelockDuration()", returns=["uint256"]),
        "is_challenged": ctx.try_call(a, "isChallenged()", returns=["bool"]),
        "is_healing": ctx.try_call(a, "isHealing()", returns=["bool"]),
        "switch_rule": ("Écart = |primaire − secours| / moyenne. S'il dépasse deviation_threshold, n'importe qui "
                        "peut appeler challenge() ; si l'écart tient encore après challenge_timelock_seconds, "
                        "acceptChallenge() bascule sur le SECOURS. Retour au primaire via heal() puis "
                        "acceptHealing() après healing_timelock_seconds de reconvergence. Fonctions sans permission."),
        "switch_rule_source": STEAKHOUSE_DOC,
        "design_note": ("Contrat MetaOracleDeviationTimelock conçu par Steakhouse Financial (doc ci-dessus), déployé "
                        "en clones EIP-1167 par une factory. Lien entre CETTE adresse et la factory officielle : "
                        "non prouvé on-chain (adresse de la factory non publiée dans la doc) → pas d'arête issued_by."),
        **_morpho_price(ctx, a, scale),
    }
    if scale is not None:
        for role, fn in (("primary", "primaryPrice()"), ("backup", "backupPrice()")):
            raw = ctx.try_call(a, fn, returns=["uint256"])
            meta[f"{role}_price"] = scaled(raw, scale) if raw is not None else None
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_meta", a), "Méta-oracle primaire/secours (deviation timelock)", meta)])
    d.edges.append(Edge(a, primary, "priced_by", "onchain", ctx.ev(a, "primaryOracle()", result=primary)
                        + f" ; currentOracle() = {current}"))
    d.edges.append(Edge(a, backup, "priced_by", "onchain", ctx.ev(a, "backupOracle()", result=backup)
                        + f" ; seuil de bascule deviationThreshold() = {thr}"))
    hint = (("scale_decimals", scale),) if scale is not None else ()
    d.follow += [Task("oracle", primary, hint), Task("oracle", backup, hint)]
    return d


# ---- MorphoChainlinkOracle V1/V2 ----------------------------------------------------
def _mco_components(ctx: Ctx, a: str, kind: str) -> tuple[dict, str]:
    if kind == "morpho_chainlink_oracle_v2":
        vault_slots = [("BASE_VAULT", "BASE_VAULT_CONVERSION_SAMPLE"), ("QUOTE_VAULT", "QUOTE_VAULT_CONVERSION_SAMPLE")]
    else:
        vault_slots = [("VAULT", "VAULT_CONVERSION_SAMPLE")]
    slots: dict[str, dict] = {}
    for vault, sample in vault_slots:
        addr = ctx.call(a, f"{vault}()", returns=["address"])
        slots[vault] = {"address": None if is_zero(addr) else addr,
                        "sample": ctx.try_call(a, f"{sample}()", returns=["uint256"]),
                        "role": "base" if vault in ("BASE_VAULT", "VAULT") else "quote", "is_vault": True}
    for feed in ("BASE_FEED_1", "BASE_FEED_2", "QUOTE_FEED_1", "QUOTE_FEED_2"):
        addr = ctx.call(a, f"{feed}()", returns=["address"])
        slots[feed] = {"address": None if is_zero(addr) else addr,
                       "role": "base" if feed.startswith("BASE") else "quote", "is_vault": False}
    modes = []
    for s in slots.values():
        if s["address"] is None:
            continue
        s["pricing_mode"] = "internal_rate" if s["is_vault"] else mode_of(ctx, s["address"])
        modes.append(s["pricing_mode"])
    return slots, _combine(modes)


def _mco(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    slots, mode = _mco_components(ctx, a, kind)
    scale_factor = ctx.call(a, "SCALE_FACTOR()", returns=["uint256"])
    meta = {"pricing_mode": mode, "scale_factor": jsonable(scale_factor), **_morpho_price(ctx, a, scale)}

    # Recalcul du prix à partir des briques : si on retombe sur price(), on a PROUVÉ la composition.
    num, den = scale_factor, 1
    for name, s in slots.items():
        if s["address"] is None:
            continue
        if s["is_vault"]:
            value = ctx.call(s["address"], "convertToAssets(uint256)", [s["sample"]], ["uint256"])
        else:
            value = latest_round(ctx, s["address"])[1]
            if value < 0:
                raise ValueError(f"feed {s['address']} renvoie un prix négatif")
        s["value"] = jsonable(value)
        if s["role"] == "base":
            num *= value
        else:
            den *= value
    recomputed = num // den   # même arrondi que mulDiv (division entière vers le bas)
    if kind == "morpho_chainlink_oracle_v2":
        # MorphoChainlinkOracleV2 : SCALE_FACTOR × baseVault.convertToAssets(sample) × feeds / (quote...)
        meta["formula"] = "SCALE_FACTOR × BASE_VAULT × BASE_FEED_1 × BASE_FEED_2 / (QUOTE_VAULT × QUOTE_FEED_1 × QUOTE_FEED_2), slot vide = 1"
    raw_price = ctx.try_call(a, "price()", returns=["uint256"])
    meta["price_recomputed_raw"] = jsonable(recomputed)
    meta["price_recomputed_matches"] = raw_price == recomputed
    meta["components"] = {k: {kk: vv for kk, vv in v.items() if kk != "is_vault"} for k, v in slots.items()}
    meta["implicit_unit_slots"] = [k for k, v in slots.items() if v["address"] is None]
    meta["implicit_unit_note"] = ("Chaque slot listé ici vaut 1 dans la formule : la conversion correspondante "
                                  "est FIXÉE (ex. aucun QUOTE_FEED = l'actif prêté est supposé valoir 1 unité de "
                                  "la devise des feeds de base).")

    factory = ctx.config.contracts.get("morpho_chainlink_oracle_v2_factory")
    if factory and kind == "morpho_chainlink_oracle_v2":
        ok = ctx.try_call(factory, "isMorphoChainlinkOracleV2(address)", [a], ["bool"])
        meta["created_by_official_factory"] = ok
        meta["factory_evidence"] = f"MorphoChainlinkOracleV2Factory.isMorphoChainlinkOracleV2({a}) = {ok} @ {factory} #{ctx.block}"

    label = f"{KIND_LABEL[kind]} ({mode})"
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_morpho_v2" if kind.endswith("v2") else "oracle_morpho_v1", a), label, meta)])
    for name, s in slots.items():
        if s["address"] is None:
            continue
        d.edges.append(Edge(a, s["address"], "priced_by", "onchain",
                            ctx.ev(a, f"{name}()", result=s["address"]) + f" ; valeur lue = {s.get('value')}"))
        d.follow.append(Task("token" if s["is_vault"] else "oracle", s["address"]))
    return d


# ---- feeds ----------------------------------------------------------------------------
def _round(ctx: Ctx, a: str) -> dict:
    round_id, answer, _, updated_at, _ = latest_round(ctx, a)
    dec = ctx.try_call(a, "decimals()", returns=["uint8"])
    return {"answer_raw": jsonable(answer), "decimals": dec,
            "answer": scaled(answer, dec) if dec is not None else None,
            "round_id": jsonable(round_id), "updated_at": updated_at,
            "age_seconds": ctx.block_timestamp - updated_at if updated_at else None}


def _linear_discount(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    pt = ctx.call(a, "PT()", returns=["address"])
    maturity = ctx.call(a, "maturity()", returns=["uint256"])
    discount = ctx.call(a, "baseDiscountPerYear()", returns=["uint256"])
    r = _round(ctx, a)
    seconds_left = max(maturity - ctx.block_timestamp, 0)
    expected = 1 - scaled(discount, 18) * seconds_left / (365 * 86400)
    meta = {
        "pricing_mode": "fixed",
        "priced_asset": pt,
        "maturity": maturity,
        "base_discount_per_year": scaled(discount, 18),
        "formula": "prix_PT = 1 − baseDiscountPerYear × (maturity − now) / 1 an  (ne regarde AUCUN marché)",
        "formula_expected": round(expected, 12),
        "formula_matches": r["answer"] is not None and abs(r["answer"] - expected) < 1e-9,
        **r,
    }
    sym = ctx.try_call(pt, "symbol()", returns=["string"]) or "pt"
    d = Discovery(nodes=[_node(a, kind, f"feed_{slugify(sym)}_linear_discount", f"Décote linéaire Pendle ({sym})", meta)])
    d.notes.append(f"Feed {a} : prix PT FIXÉ par formule (décote {scaled(discount, 18):.2%}/an) → aucun lien au marché")
    return d


def _pendle_twap(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    market = ctx.call(a, "market()", returns=["address"])
    twap = ctx.call(a, "twapDuration()", returns=["uint32"])
    meta = {"pricing_mode": "market", "market": market, "twap_duration_seconds": twap, **_round(ctx, a),
            "warning": "sondes de ce type de feed non vérifiées sur un contrat réel (voir docs/VERIFY.md)"}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_pendle_twap", a), "Feed TWAP Pendle", meta)])
    d.edges.append(Edge(a, market, "priced_by", "onchain", ctx.ev(a, "market()", result=market)))
    d.follow.append(Task("pendle_market", market))
    return d


def _chainlink_proxy(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    desc = ctx.call(a, "description()", returns=["string"])
    ctx.labels[a] = f"ChainlinkFeed[{desc}]"
    meta = {
        "pricing_mode": "market",
        "description": desc,
        "aggregator": ctx.call(a, "aggregator()", returns=["address"]),
        "phase_id": ctx.call(a, "phaseId()", returns=["uint16"]),
        "version": ctx.try_call(a, "version()", returns=["uint256"]),
        "owner": ctx.try_call(a, "owner()", returns=["address"]),
        **_round(ctx, a),
    }
    ens_name = chainlink_ens_name(desc)
    resolved, ens_proof = resolve(ctx, ens_name)
    meta["ens_name"] = ens_name
    meta["ens_resolves_to_this_feed"] = resolved == a
    d = Discovery(nodes=[_node(a, kind, f"feed_{slugify(desc)}", f"Chainlink {desc}", meta)])
    if resolved == a:
        d.edges.append(Edge(a, CHAINLINK_ISSUER_KEY, "issued_by", "onchain",
                            f"{ens_proof} ; le domaine data.eth est celui des feeds Chainlink ({CHAINLINK_ENS_DOC})"))
    else:
        d.notes.append(f"Feed {a} ({desc}) : ENS {ens_name} ne pointe pas vers lui → émetteur NON prouvé")
    return d


def _constant_feed(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    r = _round(ctx, a)
    desc = ctx.try_call(a, "description()", returns=["string"])
    meta = {"pricing_mode": "fixed", "description": desc, **r,
            "why_constant": (f"latestRoundData() renvoie roundId={r['round_id']} et updatedAt = horodatage du bloc "
                             f"#{ctx.block} : la valeur est calculée à la volée, aucun opérateur ne la met à jour")}
    d = Discovery(nodes=[_node(a, kind, contract_id("feed_constant", a), f"Feed constant ({desc or 'sans description'})", meta)])
    d.notes.append(f"Feed {a} : CONSTANT ({r['answer']}) — « {desc} »")
    return d


def _unknown(ctx: Ctx, a: str, kind: str, scale: int | None) -> Discovery:
    meta = {"pricing_mode": "unknown", "unresolved": True,
            "next_step": "contrat non reconnu : lire son code source vérifié sur Etherscan et ajouter un handler"}
    meta.update(_morpho_price(ctx, a, scale))
    if kind == "chainlink_compatible_unknown":
        meta.update(_round(ctx, a))
    d = Discovery(nodes=[_node(a, kind, contract_id("oracle_unknown", a), f"Oracle non reconnu {a[:10]}", meta)])
    d.notes.append(f"⚠ Oracle {a} non reconnu ({kind}) → marqué unresolved, à analyser à la main")
    return d
