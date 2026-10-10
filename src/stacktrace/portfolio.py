"""Étape 2 — le portefeuille d'un détenteur réel : adresse → liste de ses positions (« poches »).

    PYTHONPATH=src python -m stacktrace.portfolio 0xAdresseDuDétenteur [--min-usd 1]

Deux temps, comme partout dans le projet :
  1. LOCALISER avec l'API Morpho : « dans quels vaults / marchés cette adresse a-t-elle quelque chose ? »
     (pour le savoir on-chain il faudrait parcourir tous les vaults existants : c'est le travail d'un indexeur) ;
  2. PROUVER on-chain, au bloc figé de la session, le montant de chaque position :
       - vault (ERC-4626) : parts = balanceOf(détenteur), actifs = convertToAssets(parts) ;
       - marché Morpho     : Morpho.position(id, détenteur) → parts prêtées / parts empruntées / collatéral,
                             converties en actifs avec les totaux du marché (intérêts courus inclus).
     Si l'API et la chaîne ne sont pas d'accord, on le signale : c'est la chaîne qui fait foi.

Le prix en dollars, lui, vient encore de l'API (montant USD / montant en actif, pour cette position).
Il est marqué `source: api` ; on le remplacera par des prix lus on-chain (oracles) dans une étape suivante.

Vocabulaire :
  - part (share) : un ticket de propriété du vault. Le vault grossit avec les intérêts → chaque part vaut
    de plus en plus d'actif. convertToAssets(parts) dit combien elles valent MAINTENANT.
  - poche : une position du portefeuille ; c'est l'unité sur laquelle on décidera STAY / EXIT.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from discovery.config import REPO_ROOT
from discovery.console import utf8_console
from discovery.ctx import CallFailed, Ctx, checksum
from discovery.adapters.morpho import ORACLE_PRICE_SCALE, VIRTUAL_ASSETS, VIRTUAL_SHARES, read_market, to_assets_up

OUTPUT_DIR = REPO_ROOT / "output" / "live"
API_ONCHAIN_TOLERANCE = 0.01     # 1 % : au-delà, l'écart API ↔ chaîne est signalé

QUERY = """query Holder($a: String!, $c: Int!) {
  userByAddress(address: $a, chainId: $c) {
    address
    vaultV2Positions { shares assets assetsUsd vault { address name symbol asset { address symbol decimals } } }
    vaultPositions { state { shares assets assetsUsd } vault { address name symbol asset { address symbol decimals } } }
    marketPositions {
      market { marketId lltv loanAsset { address symbol decimals } collateralAsset { address symbol decimals } }
      state { supplyShares supplyAssets supplyAssetsUsd borrowShares borrowAssets borrowAssetsUsd collateral collateralUsd }
    }
  }
}"""


@dataclass
class Holding:
    """Une poche du portefeuille, montant prouvé on-chain."""
    id: str                      # identifiant stable de la position (sert d'entrée aux étapes suivantes)
    kind: str                    # morpho_vault_v2 | morpho_vault_v1 | morpho_market_supply | morpho_market_borrow
    label: str
    protocol: str
    chain: str
    address: str | None          # vault, ou Morpho Blue pour un marché
    market_id: str | None
    asset_symbol: str
    asset_address: str
    amount: float                # en unités de l'actif (on-chain). Emprunt : valeur nette (collatéral − dette)
    price_usd: float | None      # prix d'une unité d'actif (API, voir price_source)
    value_usd: float | None
    price_source: str
    evidence: list[str] = field(default_factory=list)
    api_amount: float | None = None
    api_gap: float | None = None          # écart relatif chaîne vs API
    details: dict = field(default_factory=dict)
    share_of_book: float | None = None


@dataclass
class Portfolio:
    holder: str
    chain: str
    block: int
    block_time: int
    located_by: str
    holdings: list[Holding]
    ignored: list[dict]
    notes: list[str]

    @property
    def total_value_usd(self) -> float:
        return sum(h.value_usd or 0 for h in self.holdings)

    def to_json(self) -> dict:
        return {"holder": self.holder, "chain": self.chain, "block": self.block, "block_time": self.block_time,
                "located_by": self.located_by, "total_value_usd": round(self.total_value_usd, 2),
                "holdings": [asdict(h) for h in self.holdings], "ignored": self.ignored, "notes": self.notes}


# ----------------------------------------------------------------------------- calculs purs
def to_assets_down(shares: int, total_assets: int, total_shares: int) -> int:
    """Parts prêtées → actifs, arrondi vers le BAS (SharesMathLib.toAssetsDown de Morpho Blue)."""
    return shares * (total_assets + VIRTUAL_ASSETS) // (total_shares + VIRTUAL_SHARES)


def usd_per_unit(amount_usd: float | None, amount_raw, decimals: int) -> float | None:
    """Prix implicite d'une unité d'actif d'après l'API (USD / quantité) ; None si non calculable."""
    try:
        qty = int(amount_raw) / 10**decimals
    except (TypeError, ValueError):
        return None
    return (amount_usd / qty) if (amount_usd and qty) else None


def gap(onchain: float, api: float | None) -> float | None:
    if api is None or onchain == 0:
        return None
    return abs(onchain - api) / abs(onchain)


# ----------------------------------------------------------------------------- preuves on-chain
def prove_vault(ctx: Ctx, holder: str, item: dict, version: str, located: str) -> Holding:
    """Vault ERC-4626 (MetaMorpho v1 ou Morpho Vault V2) : parts du détenteur → actifs, au bloc figé."""
    v = item["vault"]
    vault = checksum(v["address"])
    ctx.labels[vault] = v.get("name") or "Vault"
    shares = ctx.call(vault, "balanceOf(address)", [holder])
    assets = ctx.call(vault, "convertToAssets(uint256)", [shares]) if shares else 0
    asset = ctx.call(vault, "asset()", returns=["address"])
    decimals = ctx.call(asset, "decimals()", returns=["uint8"])
    name = ctx.try_call(vault, "name()", returns=["string"]) or v.get("name") or vault
    api_asset = checksum(v["asset"]["address"])
    st = item if version == "v2" else item["state"]
    price = usd_per_unit(st.get("assetsUsd"), st.get("assets"), decimals)
    amount = assets / 10**decimals
    api_amount = int(st["assets"]) / 10**decimals if st.get("assets") is not None else None
    h = Holding(
        id=f"morpho_vault_{version}:{vault}", kind=f"morpho_vault_{version}", label=name, protocol="morpho",
        chain="ethereum", address=vault, market_id=None, asset_symbol=v["asset"]["symbol"], asset_address=asset,
        amount=amount, price_usd=price, value_usd=amount * price if price is not None else None,
        price_source=f"api : assetsUsd / assets de cette position ({located})",
        evidence=[ctx.ev(vault, "balanceOf(address)", [holder], shares),
                  ctx.ev(vault, "convertToAssets(uint256)", [shares], assets),
                  ctx.ev(vault, "asset()", [], asset)],
        api_amount=api_amount, api_gap=gap(amount, api_amount),
        details={"shares": str(shares), "assets_raw": str(assets), "decimals": decimals},
    )
    if asset != api_asset:
        h.details["warning"] = f"actif on-chain {asset} ≠ actif API {api_asset} : la chaîne fait foi"
    return h


def prove_market(ctx: Ctx, holder: str, item: dict, located: str) -> list[Holding]:
    """Position directe sur un marché Morpho Blue : une poche « prêt » et/ou une poche « emprunt »."""
    mk = item["market"]
    m = read_market(ctx, mk["marketId"])          # paramètres + recalcul de l'id + intérêts courus
    supply_sh, borrow_sh, collateral = ctx.call(
        m["morpho"], "position(bytes32,address)", [m["mid"], holder], ["uint256", "uint128", "uint128"])
    proof = ctx.ev(m["morpho"], "position(bytes32,address)", [m["mid"], holder], (supply_sh, borrow_sh, collateral))
    loan, coll = mk["loanAsset"], mk.get("collateralAsset") or {}
    loan_dec = ctx.call(m["loan_token"], "decimals()", returns=["uint8"])
    st = item["state"]
    loan_price = (usd_per_unit(st.get("supplyAssetsUsd"), st.get("supplyAssets"), loan_dec)
                  or usd_per_unit(st.get("borrowAssetsUsd"), st.get("borrowAssets"), loan_dec))
    pair = f"{coll.get('symbol', '—')}/{loan['symbol']}"
    out: list[Holding] = []

    if supply_sh:
        supplied = to_assets_down(supply_sh, m["expected_total_supply_assets"], m["total_supply_shares"])
        amount = supplied / 10**loan_dec
        api_amount = int(st["supplyAssets"]) / 10**loan_dec if st.get("supplyAssets") is not None else None
        out.append(Holding(
            id=f"morpho_market_supply:{m['market_id']}", kind="morpho_market_supply",
            label=f"Prêt {loan['symbol']} · marché {pair}", protocol="morpho", chain="ethereum",
            address=m["morpho"], market_id=m["market_id"], asset_symbol=loan["symbol"], asset_address=m["loan_token"],
            amount=amount, price_usd=loan_price, value_usd=amount * loan_price if loan_price else None,
            price_source=f"api : supplyAssetsUsd / supplyAssets ({located})", evidence=[proof],
            api_amount=api_amount, api_gap=gap(amount, api_amount),
            details={"supply_shares": str(supply_sh), "lltv": m["lltv"] / 1e18}))

    if borrow_sh or collateral:
        debt = to_assets_up(borrow_sh, m["expected_total_borrow_assets"], m["total_borrow_shares"])
        price_raw = ctx.call(m["oracle"], "price()", returns=["uint256"])
        coll_in_loan = collateral * price_raw // ORACLE_PRICE_SCALE
        net = (coll_in_loan - debt) / 10**loan_dec       # capital propre, en actif prêté, au prix de l'oracle
        hf = (coll_in_loan * m["lltv"] / 10**18 / debt) if debt else None
        # Contrôle croisé en dollars : l'API valorise le collatéral à SON prix de marché, nous au prix de
        # l'oracle du marché (celui qui décide des liquidations) → un petit écart est normal et informatif.
        api_net_usd = ((st.get("collateralUsd") or 0) - (st.get("borrowAssetsUsd") or 0)) \
            if st.get("collateralUsd") is not None else None
        out.append(Holding(
            id=f"morpho_market_borrow:{m['market_id']}", kind="morpho_market_borrow",
            label=f"Emprunt {loan['symbol']} contre {coll.get('symbol', '?')} · marché {pair}", protocol="morpho",
            chain="ethereum", address=m["morpho"], market_id=m["market_id"], asset_symbol=loan["symbol"],
            asset_address=m["loan_token"], amount=net, price_usd=loan_price,
            value_usd=net * loan_price if loan_price else None,
            price_source=f"api : prix de {loan['symbol']} ({located}) ; collatéral valorisé au prix de l'oracle du marché",
            evidence=[proof, ctx.ev(m["oracle"], "price()", [], price_raw)],
            api_amount=(api_net_usd / loan_price) if (api_net_usd is not None and loan_price) else None,
            api_gap=gap(net, api_net_usd / loan_price) if (api_net_usd is not None and loan_price) else None,
            details={"collateral_raw": str(collateral), "debt_raw": str(debt), "oracle_price_raw": str(price_raw),
                     "collateral_value_in_loan": coll_in_loan / 10**loan_dec, "debt": debt / 10**loan_dec,
                     "health_factor": round(hf, 4) if hf else None, "lltv": m["lltv"] / 1e18,
                     "value_definition": "capital propre = collatéral × prix oracle − dette (intérêts courus inclus)"}))
    return out


# ----------------------------------------------------------------------------- orchestration
def scan_holder(ctx: Ctx, holder: str, chain_id: int = 1, min_usd: float = 1.0) -> Portfolio:
    holder = checksum(holder)
    url = ctx.config.apis["morpho_graphql"]
    data, fetched_at = ctx.http.post_json(url, {"query": QUERY, "variables": {"a": holder, "c": chain_id}})
    located = f"API Morpho {url} userByAddress (fetched {fetched_at})"
    notes = [f"Positions LOCALISÉES par {located} ; montants PROUVÉS on-chain au bloc #{ctx.block}."]
    if data.get("errors"):
        msg = data["errors"][0].get("message", "")
        if "No results" in msg or "not found" in msg.lower():
            return Portfolio(holder, "ethereum", ctx.block, ctx.block_timestamp, located, [], [],
                             notes + ["L'API Morpho ne connaît aucune position pour cette adresse."])
        raise RuntimeError(f"API Morpho : {msg}")
    user = (data.get("data") or {}).get("userByAddress") or {}

    candidates: list[tuple[str, dict]] = (
        [("v2", x) for x in user.get("vaultV2Positions") or []]
        + [("v1", x) for x in user.get("vaultPositions") or []]
        + [("market", x) for x in user.get("marketPositions") or []])

    holdings, ignored = [], []
    for kind, item in candidates:
        try:
            found = prove_market(ctx, holder, item, located) if kind == "market" else \
                [prove_vault(ctx, holder, item, kind, located)]
        except (CallFailed, ValueError) as e:
            ignored.append({"kind": kind, "reason": f"preuve on-chain impossible : {e}", "api_item": item})
            continue
        for h in found:
            if h.amount == 0 or (h.value_usd is not None and abs(h.value_usd) < min_usd):
                ignored.append({"id": h.id, "label": h.label, "reason": f"vide ou < {min_usd} $",
                                "value_usd": h.value_usd})
            else:
                holdings.append(h)

    holdings.sort(key=lambda h: -(h.value_usd or 0))
    total = sum(h.value_usd or 0 for h in holdings)
    for h in holdings:
        h.share_of_book = round((h.value_usd or 0) / total, 6) if total else None
        if h.api_gap is not None and h.api_gap > API_ONCHAIN_TOLERANCE:
            notes.append(f"⚠ {h.label} : la chaîne dit {h.amount:,.2f} {h.asset_symbol}, l'API {h.api_amount:,.2f} "
                         f"(écart {h.api_gap:.1%}) — la chaîne fait foi.")
    if any(h.value_usd is None for h in holdings):
        notes.append("⚠ certaines poches n'ont pas de prix USD (API muette) : exclues du total.")
    return Portfolio(holder, "ethereum", ctx.block, ctx.block_timestamp, located, holdings, ignored, notes)


# ----------------------------------------------------------------------------- CLI
def _print(p: Portfolio, session_desc: str) -> None:
    print(f"=== Portefeuille de {p.holder} ===")
    print(f"    {session_desc}")
    print(f"    {len(p.holdings)} poche(s) · total {p.total_value_usd:,.0f} $ · {len(p.ignored)} position(s) vide(s)/ignorée(s)\n")
    print(f"  {'poche':52s} {'montant (on-chain)':>26s} {'valeur $':>14s} {'part':>7s}  API≈chaîne")
    for h in p.holdings:
        amt = f"{h.amount:,.2f} {h.asset_symbol}"
        val = f"{h.value_usd:,.0f}" if h.value_usd is not None else "—"
        ok = "—" if h.api_gap is None else ("✓" if h.api_gap <= API_ONCHAIN_TOLERANCE else f"⚠ {h.api_gap:.1%}")
        print(f"  {h.label[:52]:52s} {amt:>26s} {val:>14s} {h.share_of_book or 0:>7.1%}  {ok}")
        if h.kind == "morpho_market_borrow":
            d = h.details
            print(f"      ↳ collatéral {d['collateral_value_in_loan']:,.0f} − dette {d['debt']:,.0f} {h.asset_symbol} · HF {d['health_factor']}")
    print()
    for n in p.notes:
        print(f"  · {n}")


def main(argv: list[str] | None = None) -> int:
    from .session import SessionError, open_session
    utf8_console()
    ap = argparse.ArgumentParser(description="Liste les positions (poches) d'un détenteur, prouvées on-chain.")
    ap.add_argument("holder", help="adresse du détenteur (0x…)")
    ap.add_argument("--min-usd", type=float, default=1.0, help="ignore les poches plus petites (défaut 1 $)")
    args = ap.parse_args(argv)
    try:
        s = open_session()
    except SessionError as e:
        print(f"✗ {e}")
        return 1
    p = scan_holder(s.ctx, args.holder, s.chain_id, args.min_usd)
    _print(p, s.describe())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"portfolio_{p.holder.lower()}.json"
    out.write_text(json.dumps(p.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)}  ({s.network_calls} appels RPC réseau)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
