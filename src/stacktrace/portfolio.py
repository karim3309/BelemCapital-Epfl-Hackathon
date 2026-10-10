"""Step 2 — the portfolio of a real holder: address → list of its positions ("pockets").

    PYTHONPATH=src python -m stacktrace.portfolio 0xHolderAddress [--min-usd 1]

Two stages, as everywhere in the project:
  1. LOCATE with the Morpho API: "in which vaults / markets does this address hold something?"
     (knowing it on-chain would mean walking every existing vault: that is an indexer's job);
  2. PROVE on-chain, at the session's pinned block, the amount of each position:
       - vault (ERC-4626) : shares = balanceOf(holder), assets = convertToAssets(shares);
       - Morpho market    : Morpho.position(id, holder) → supplied shares / borrowed shares / collateral,
                            converted to assets with the market totals (accrued interest included).
     If the API and the chain disagree, it is flagged: the chain wins.

The dollar price, however, still comes from the API (USD amount / asset amount, for this position).
It is marked `source: api`; it will be replaced by prices read on-chain (oracles) in a later step.

Vocabulary:
  - share: an ownership ticket of the vault. The vault grows with interest → each share is worth
    more and more of the asset. convertToAssets(shares) says what they are worth NOW.
  - pocket: one position of the portfolio; it is the unit on which STAY / EXIT is decided.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from discovery.config import REPO_ROOT, _check_address
from discovery.console import utf8_console
from discovery.ctx import CallFailed, Ctx, checksum
from discovery.adapters.morpho import ORACLE_PRICE_SCALE, VIRTUAL_ASSETS, VIRTUAL_SHARES, read_market, to_assets_up

OUTPUT_DIR = REPO_ROOT / "output" / "live"
API_ONCHAIN_TOLERANCE = 0.01     # 1%: beyond that, the API ↔ chain gap is flagged

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
    """A portfolio pocket, amount proven on-chain."""
    id: str                      # stable identifier of the position (the input of the next steps)
    kind: str                    # morpho_vault_v2 | morpho_vault_v1 | morpho_market_supply | morpho_market_borrow
    label: str
    protocol: str
    chain: str
    address: str | None          # vault, or Morpho Blue for a market
    market_id: str | None
    asset_symbol: str
    asset_address: str
    amount: float                # in units of the asset (on-chain). Borrow: net value (collateral − debt)
    price_usd: float | None      # price of one unit of asset (API, see price_source)
    value_usd: float | None
    price_source: str
    evidence: list[str] = field(default_factory=list)
    api_amount: float | None = None
    api_gap: float | None = None          # relative gap chain vs API
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


# ----------------------------------------------------------------------------- pure computations
def to_assets_down(shares: int, total_assets: int, total_shares: int) -> int:
    """Supplied shares → assets, rounded DOWN (Morpho Blue's SharesMathLib.toAssetsDown)."""
    return shares * (total_assets + VIRTUAL_ASSETS) // (total_shares + VIRTUAL_SHARES)


def usd_per_unit(amount_usd: float | None, amount_raw, decimals: int) -> float | None:
    """Implied price of one unit of asset according to the API (USD / quantity); None if not computable."""
    try:
        qty = int(amount_raw) / 10**decimals
    except (TypeError, ValueError):
        return None
    return (amount_usd / qty) if (amount_usd and qty) else None


def gap(onchain: float, api: float | None) -> float | None:
    if api is None or onchain == 0:
        return None
    return abs(onchain - api) / abs(onchain)


# ----------------------------------------------------------------------------- on-chain evidence
def prove_vault(ctx: Ctx, holder: str, item: dict, version: str, located: str) -> Holding:
    """ERC-4626 vault (MetaMorpho v1 or Morpho Vault V2): holder's shares → assets, at the pinned block."""
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
        price_source=f"api: assetsUsd / assets of this position ({located})",
        evidence=[ctx.ev(vault, "balanceOf(address)", [holder], shares),
                  ctx.ev(vault, "convertToAssets(uint256)", [shares], assets),
                  ctx.ev(vault, "asset()", [], asset)],
        api_amount=api_amount, api_gap=gap(amount, api_amount),
        details={"shares": str(shares), "assets_raw": str(assets), "decimals": decimals},
    )
    if asset != api_asset:
        h.details["warning"] = f"on-chain asset {asset} ≠ API asset {api_asset}: the chain wins"
    return h


def prove_market(ctx: Ctx, holder: str, item: dict, located: str) -> list[Holding]:
    """Direct position on a Morpho Blue market: a "supply" pocket and/or a "borrow" pocket."""
    mk = item["market"]
    m = read_market(ctx, mk["marketId"])          # parameters + id recomputation + accrued interest
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
            label=f"Supply {loan['symbol']} · market {pair}", protocol="morpho", chain="ethereum",
            address=m["morpho"], market_id=m["market_id"], asset_symbol=loan["symbol"], asset_address=m["loan_token"],
            amount=amount, price_usd=loan_price, value_usd=amount * loan_price if loan_price else None,
            price_source=f"api : supplyAssetsUsd / supplyAssets ({located})", evidence=[proof],
            api_amount=api_amount, api_gap=gap(amount, api_amount),
            details={"supply_shares": str(supply_sh), "lltv": m["lltv"] / 1e18}))

    if borrow_sh or collateral:
        debt = to_assets_up(borrow_sh, m["expected_total_borrow_assets"], m["total_borrow_shares"])
        price_raw = ctx.call(m["oracle"], "price()", returns=["uint256"])
        coll_in_loan = collateral * price_raw // ORACLE_PRICE_SCALE
        net = (coll_in_loan - debt) / 10**loan_dec       # equity, in lent asset, at the oracle price
        hf = (coll_in_loan * m["lltv"] / 10**18 / debt) if debt else None
        # Dollar cross-check: the API values the collateral at ITS market price, we at the price of
        # the market's oracle (the one deciding liquidations) → a small gap is normal and informative.
        api_net_usd = ((st.get("collateralUsd") or 0) - (st.get("borrowAssetsUsd") or 0)) \
            if st.get("collateralUsd") is not None else None
        out.append(Holding(
            id=f"morpho_market_borrow:{m['market_id']}", kind="morpho_market_borrow",
            label=f"Borrow {loan['symbol']} against {coll.get('symbol', '?')} · market {pair}", protocol="morpho",
            chain="ethereum", address=m["morpho"], market_id=m["market_id"], asset_symbol=loan["symbol"],
            asset_address=m["loan_token"], amount=net, price_usd=loan_price,
            value_usd=net * loan_price if loan_price else None,
            price_source=f"api: price of {loan['symbol']} ({located}); collateral valued at the market's oracle price",
            evidence=[proof, ctx.ev(m["oracle"], "price()", [], price_raw)],
            api_amount=(api_net_usd / loan_price) if (api_net_usd is not None and loan_price) else None,
            api_gap=gap(net, api_net_usd / loan_price) if (api_net_usd is not None and loan_price) else None,
            details={"collateral_raw": str(collateral), "debt_raw": str(debt), "oracle_price_raw": str(price_raw),
                     "collateral_value_in_loan": coll_in_loan / 10**loan_dec, "debt": debt / 10**loan_dec,
                     "health_factor": round(hf, 4) if hf else None, "lltv": m["lltv"] / 1e18,
                     "value_definition": "equity = collateral × oracle price − debt (accrued interest included)"}))
    return out


# ----------------------------------------------------------------------------- whole vaults (curator view)
# A CURATOR (RockawayX, Belem…) decides where a vault's money goes. Its question is not "should this depositor
# leave?" but "can a market of MY vault make my depositors lose money, and should I pull the vault out of it?".
# So the pocket is the WHOLE vault: amount = totalAssets(), every depositor together. Two extra inputs:
#   "vault:0x…"   one vault, analysed as a whole;
#   "book:<key>"  every vault of a curator book listed in config.yaml (curator_books), with its source.
VAULT_PREFIX, BOOK_PREFIX = "vault:", "book:"
VAULT_PRICE_QUERIES = (   # tried in order: the first answer with a price wins (the API schema may evolve)
    ("asset.priceUsd",
     "query P($a: String!, $c: Int!) { vaultV2ByAddress(address: $a, chainId: $c) { asset { priceUsd } } }"),
    ("totalAssetsUsd / totalAssets",
     "query P($a: String!, $c: Int!) { vaultV2ByAddress(address: $a, chainId: $c) { totalAssets totalAssetsUsd } }"),
)


def vault_price_usd(ctx: Ctx, vault: str, decimals: int, chain_id: int = 1) -> tuple[float | None, str]:
    """USD price of one unit of the vault's asset, from the Morpho API (marked `api`), or (None, why)."""
    url = ctx.config.apis.get("morpho_graphql")
    if not url or ctx.http is None:
        return None, "no Morpho API configured"
    for how, query in VAULT_PRICE_QUERIES:
        try:
            data, fetched = ctx.http.post_json(url, {"query": query, "variables": {"a": vault, "c": chain_id}})
        except Exception as e:                      # network error: say it, never guess a price
            return None, f"Morpho API unreachable ({type(e).__name__})"
        v = (data.get("data") or {}).get("vaultV2ByAddress") or {}
        if data.get("errors") or not v:
            continue
        price = ((v.get("asset") or {}).get("priceUsd") if how.startswith("asset")
                 else usd_per_unit(v.get("totalAssetsUsd"), v.get("totalAssets"), decimals))
        if price:
            return float(price), f"api: vaultV2ByAddress {how} ({url}, fetched {fetched})"
    return None, "the Morpho API gave no USD price for this vault"


def prove_whole_vault(ctx: Ctx, vault: str, chain_id: int = 1) -> Holding:
    """A Morpho Vault V2 taken as a whole: amount = totalAssets() at the pinned block."""
    vault = checksum(vault)
    if ctx.try_call(vault, "adaptersLength()") is None:
        raise ValueError(f"{vault} is not a Morpho Vault V2 (no adaptersLength())")
    name = ctx.call(vault, "name()", returns=["string"])
    ctx.labels[vault] = name
    asset = ctx.call(vault, "asset()", returns=["address"])
    decimals = ctx.call(asset, "decimals()", returns=["uint8"])
    symbol = ctx.try_call(asset, "symbol()", returns=["string"]) or "?"
    total = ctx.call(vault, "totalAssets()")
    price, price_source = vault_price_usd(ctx, vault, decimals, chain_id)
    amount = total / 10**decimals
    return Holding(
        id=f"morpho_vault_v2:{vault}", kind="morpho_vault_v2", label=name, protocol="morpho", chain="ethereum",
        address=vault, market_id=None, asset_symbol=symbol, asset_address=asset, amount=amount, price_usd=price,
        value_usd=amount * price if price is not None else None, price_source=price_source,
        evidence=[ctx.ev(vault, "totalAssets()", [], total), ctx.ev(vault, "asset()", [], asset)],
        details={"whole_vault": True, "decimals": decimals, "total_assets_raw": str(total),
                 "perspective": "curator: the pocket is the whole vault, i.e. all its depositors"})


def curator_book(config, key: str) -> tuple[dict, list[str]]:
    """(book entry, checked vault addresses) of config.yaml → curator_books.<key>."""
    books = (getattr(config, "raw", None) or {}).get("curator_books") or {}
    if key not in books:
        raise ValueError(f"unknown book {key!r} (known: {', '.join(books) or 'none'}; see config.yaml curator_books)")
    book = books[key]
    return book, [_check_address(f"curator_books.{key}.vaults[{i}]", v.get("address"))
                  for i, v in enumerate(book.get("vaults") or [])]


def scan_vaults(ctx: Ctx, key: str, vaults: list[str], located: str, chain_id: int = 1,
                min_usd: float = 1.0) -> Portfolio:
    """A list of whole vaults → a portfolio whose pockets are the vaults (the curator's book)."""
    holdings, ignored = [], []
    notes = [f"Vaults listed by {located}; amounts PROVEN on-chain (totalAssets) at block #{ctx.block}."]
    for v in vaults:
        try:
            h = prove_whole_vault(ctx, v, chain_id)
        except (CallFailed, ValueError) as e:
            ignored.append({"id": f"morpho_vault_v2:{v}", "reason": f"on-chain proof impossible: {e}"})
            continue
        if h.value_usd is None:
            ignored.append({"id": h.id, "label": h.label, "reason": f"no USD price ({h.price_source}): "
                            "a loss in dollars cannot be computed, so the vault is left out rather than guessed"})
        elif h.amount == 0 or abs(h.value_usd) < min_usd:
            ignored.append({"id": h.id, "label": h.label, "reason": f"empty or < ${min_usd}", "value_usd": h.value_usd})
        else:
            holdings.append(h)
    return _finish(Portfolio(key, "ethereum", ctx.block, ctx.block_timestamp, located, holdings, ignored, notes))


def _finish(p: Portfolio) -> Portfolio:
    """Sorts the pockets by value and computes each one's share of the book."""
    p.holdings.sort(key=lambda h: -(h.value_usd or 0))
    total = sum(h.value_usd or 0 for h in p.holdings)
    for h in p.holdings:
        h.share_of_book = round((h.value_usd or 0) / total, 6) if total else None
        if h.api_gap is not None and h.api_gap > API_ONCHAIN_TOLERANCE:
            p.notes.append(f"⚠ {h.label}: the chain says {h.amount:,.2f} {h.asset_symbol}, the API {h.api_amount:,.2f} "
                           f"(gap {h.api_gap:.1%}) — the chain wins.")
    if any(h.value_usd is None for h in p.holdings):
        p.notes.append("⚠ some pockets have no USD price (API silent): excluded from the total.")
    return p


def file_slug(holder: str) -> str:
    """A file-name-safe version of a holder ("book:rockawayx" → "book_rockawayx"; ':' is forbidden on Windows)."""
    return holder.lower().replace(":", "_")


# ----------------------------------------------------------------------------- orchestration
def scan_holder(ctx: Ctx, holder: str, chain_id: int = 1, min_usd: float = 1.0) -> Portfolio:
    """A holder address, or "vault:0x…" (one whole vault), or "book:<key>" (a curator book of config.yaml)."""
    raw = holder.strip()
    if raw.lower().startswith(VAULT_PREFIX):
        vault = checksum(raw[len(VAULT_PREFIX):])
        return scan_vaults(ctx, f"{VAULT_PREFIX}{vault}", [vault], "the request (one whole vault)", chain_id, min_usd)
    if raw.lower().startswith(BOOK_PREFIX):
        key = raw[len(BOOK_PREFIX):].lower()
        book, vaults = curator_book(ctx.config, key)
        source = " ".join(str(book.get("source", "?")).split())
        return scan_vaults(ctx, f"{BOOK_PREFIX}{key}", vaults,
                           f"curator book \"{book.get('label', key)}\" of config.yaml (source: {source})",
                           chain_id, min_usd)
    holder = checksum(raw)
    url = ctx.config.apis["morpho_graphql"]
    data, fetched_at = ctx.http.post_json(url, {"query": QUERY, "variables": {"a": holder, "c": chain_id}})
    located = f"API Morpho {url} userByAddress (fetched {fetched_at})"
    notes = [f"Positions LOCATED by {located}; amounts PROVEN on-chain at block #{ctx.block}."]
    if data.get("errors"):
        msg = data["errors"][0].get("message", "")
        if "No results" in msg or "not found" in msg.lower():
            return Portfolio(holder, "ethereum", ctx.block, ctx.block_timestamp, located, [], [],
                             notes + ["The Morpho API knows no position for this address."])
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
            ignored.append({"kind": kind, "reason": f"on-chain proof impossible: {e}", "api_item": item})
            continue
        for h in found:
            if h.amount == 0 or (h.value_usd is not None and abs(h.value_usd) < min_usd):
                ignored.append({"id": h.id, "label": h.label, "reason": f"empty or < ${min_usd}",
                                "value_usd": h.value_usd})
            else:
                holdings.append(h)

    return _finish(Portfolio(holder, "ethereum", ctx.block, ctx.block_timestamp, located, holdings, ignored, notes))


# ----------------------------------------------------------------------------- CLI
def _print(p: Portfolio, session_desc: str) -> None:
    print(f"=== Portfolio of {p.holder} ===")
    print(f"    {session_desc}")
    print(f"    {len(p.holdings)} pocket(s) · total ${p.total_value_usd:,.0f} · {len(p.ignored)} empty/ignored position(s)\n")
    print(f"  {'pocket':52s} {'amount (on-chain)':>26s} {'value $':>14s} {'share':>7s}  API≈chain")
    for h in p.holdings:
        amt = f"{h.amount:,.2f} {h.asset_symbol}"
        val = f"{h.value_usd:,.0f}" if h.value_usd is not None else "—"
        ok = "—" if h.api_gap is None else ("✓" if h.api_gap <= API_ONCHAIN_TOLERANCE else f"⚠ {h.api_gap:.1%}")
        print(f"  {h.label[:52]:52s} {amt:>26s} {val:>14s} {h.share_of_book or 0:>7.1%}  {ok}")
        if h.kind == "morpho_market_borrow":
            d = h.details
            print(f"      ↳ collateral {d['collateral_value_in_loan']:,.0f} − debt {d['debt']:,.0f} {h.asset_symbol} · HF {d['health_factor']}")
    print()
    for n in p.notes:
        print(f"  · {n}")


def main(argv: list[str] | None = None) -> int:
    from .session import SessionError, open_session
    utf8_console()
    ap = argparse.ArgumentParser(description="Lists a holder's positions (pockets), proven on-chain.")
    ap.add_argument("holder", help="holder address (0x…), vault:0x… (one whole vault) or book:<key> (config.yaml)")
    ap.add_argument("--min-usd", type=float, default=1.0, help="ignore pockets smaller than this (default $1)")
    args = ap.parse_args(argv)
    try:
        s = open_session()
    except SessionError as e:
        print(f"✗ {e}")
        return 1
    p = scan_holder(s.ctx, args.holder, s.chain_id, args.min_usd)
    _print(p, s.describe())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"portfolio_{file_slug(p.holder)}.json"
    out.write_text(json.dumps(p.to_json(), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {out.relative_to(REPO_ROOT)}  ({s.network_calls} network RPC calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
