"""Root adapter: a deposit in a Morpho Vault V2 → the vault, its adapters, its markets.

How a Morpho Vault V2 is built (official source code, see SOURCES):
  - the VAULT receives deposits (ERC-4626: you get shares);
  - it does not invest itself: it goes through ADAPTERS (vault.adapters(i)), one per "kind of placement";
  - a "Morpho market" adapter places the money into N Morpho Blue markets (adapter.marketIds(j));
  - the CURATOR (vault.curator()) picks the adapters and the caps; "allocators" split the funds.
  - to exit, a depositor withdraws what is liquid; if there is not enough, they can FORCE the withdrawal
    from an adapter (forceDeallocate) by paying a penalty (vault.forceDeallocatePenalty(adapter)),
    but only within what each market has available (the rest is lent out).

What we prove on-chain, at the pinned block:
  holder    --deployed_in--> vault             balanceOf + convertToAssets
  vault     --deployed_in--> market (weight)   adapters(i) → marketIds(j) → expectedSupplyAssets(id)
  vault     --issued_by-->   curator          curator()   (identity of the address: NOT proven → to curate)
then each market is handed to the existing Morpho adapter (collateral, lent asset, oracle…).
"""
from __future__ import annotations

from eth_abi import encode
from eth_utils import keccak

from discovery.adapters import Discovery, scaled
from discovery.adapters.morpho import PARAMS_TYPES, discover_market, market_key, read_market
from discovery.ctx import Ctx, checksum
from discovery.graph import POSITION_KEY, Edge, Node
from discovery.ids import addr6, slugify

from .portfolio import to_assets_down

SOURCES = {
    "vault": "https://github.com/morpho-org/vault-v2/blob/main/src/interfaces/IVaultV2.sol",
    "market_adapter_v2": "https://github.com/morpho-org/vault-v2/blob/main/src/adapters/interfaces/IMorphoMarketV1AdapterV2.sol",
    "market_adapter_v1": "https://github.com/morpho-org/vault-v2/blob/2025-09-15/src/adapters/interfaces/IMorphoMarketV1Adapter.sol",
}
WAD = 10**18
DUST_SHARE = 1e-6       # allocation < 0.0001% of the vault: listed in a note, no node


def _adapter_markets(ctx: Ctx, adapter: str) -> tuple[str, list[tuple[str, int, str]]]:
    """(adapter type, [(marketId, assets supplied, evidence)]) — probes both official versions."""
    n = ctx.try_call(adapter, "marketIdsLength()")
    if n is not None:                                   # MorphoMarketV1AdapterV2 (current version)
        out = []
        for j in range(n):
            mid = ctx.call(adapter, "marketIds(uint256)", [j], ["bytes32"])
            supplied = ctx.call(adapter, "expectedSupplyAssets(bytes32)", [bytes.fromhex(mid[2:])])
            out.append((mid, supplied, f"{ctx.ev(adapter, 'marketIds(uint256)', [j], mid)} ; "
                                       f"{ctx.ev(adapter, 'expectedSupplyAssets(bytes32)', [mid], supplied)}"))
        return "morpho_market_v1_adapter_v2", out
    n = ctx.try_call(adapter, "marketParamsListLength()")
    if n is not None:                                   # MorphoMarketV1Adapter (version 2025-09)
        out = []
        for j in range(n):
            params = ctx.call(adapter, "marketParamsList(uint256)", [j], PARAMS_TYPES)
            mid = "0x" + keccak(encode(PARAMS_TYPES, list(params))).hex()
            m = read_market(ctx, mid)
            sup_sh, _, _ = ctx.call(m["morpho"], "position(bytes32,address)", [m["mid"], adapter],
                                    ["uint256", "uint128", "uint128"])
            supplied = to_assets_down(sup_sh, m["expected_total_supply_assets"], m["total_supply_shares"])
            out.append((mid, supplied, f"{ctx.ev(adapter, 'marketParamsList(uint256)', [j])} → id {mid} ; "
                                       f"{ctx.ev(m['morpho'], 'position(bytes32,address)', [m['mid'], adapter], sup_sh)}"))
        return "morpho_market_v1_adapter", out
    return "unknown", []


def discover_vault_v2(ctx: Ctx, vault: str, holder: str) -> Discovery:
    """holder == vault means the WHOLE vault (curator view): the position is all its depositors together."""
    vault, holder = checksum(vault), checksum(holder)
    whole = holder == vault
    name = ctx.call(vault, "name()", returns=["string"])
    ctx.labels[vault] = name
    asset = ctx.call(vault, "asset()", returns=["address"])
    dec = ctx.call(asset, "decimals()", returns=["uint8"])
    symbol = ctx.try_call(asset, "symbol()", returns=["string"]) or "?"
    total = ctx.call(vault, "totalAssets()")
    if whole:
        shares, held = ctx.call(vault, "totalSupply()"), total
        position_evidence = (f"{ctx.ev(vault, 'totalAssets()', [], total)} — whole vault: the position is all its "
                             "depositors together (curator view)")
    else:
        shares = ctx.call(vault, "balanceOf(address)", [holder])
        held = ctx.call(vault, "convertToAssets(uint256)", [shares]) if shares else 0
        if not shares:
            raise ValueError(f"{holder} has no share of vault {name} at block {ctx.block}")
        position_evidence = (f"{ctx.ev(vault, 'balanceOf(address)', [holder], shares)} ; "
                             f"{ctx.ev(vault, 'convertToAssets(uint256)', [shares], held)}")
    curator = ctx.call(vault, "curator()", returns=["address"])
    owner = ctx.try_call(vault, "owner()", returns=["address"])
    liquidity_adapter = ctx.try_call(vault, "liquidityAdapter()", returns=["address"])
    idle = ctx.call(asset, "balanceOf(address)", [vault])          # unallocated assets, withdrawable right away
    # "Liquidity source" market: a normal withdrawal draws from it WITHOUT a penalty (vault.liquidityData() =
    # abi.encode(MarketParams) for a Morpho market adapter). Beyond that, forceDeallocate is needed (penalty).
    liq_market = None
    raw_ld = ctx.try_call(vault, "liquidityData()", returns=["bytes"])
    if raw_ld and len(bytes.fromhex(raw_ld[2:])) == 160:
        liq_market = "0x" + keccak(bytes.fromhex(raw_ld[2:])).hex()

    d = Discovery()
    vkey = vault
    d.edges.append(Edge(POSITION_KEY, vkey, "deployed_in", "onchain", position_evidence))

    adapters_meta, allocations = [], []
    withdrawable = idle
    penalty_free = idle
    for i in range(ctx.call(vault, "adaptersLength()")):
        adapter = ctx.call(vault, "adapters(uint256)", [i], ["address"])
        ctx.labels[adapter] = "VaultV2Adapter"
        parent = ctx.try_call(adapter, "parentVault()", returns=["address"])
        penalty = ctx.try_call(vault, "forceDeallocatePenalty(address)", [adapter])
        kind, markets = _adapter_markets(ctx, adapter) if parent == vault else ("parent_mismatch", [])
        adapters_meta.append({
            "address": adapter, "kind": kind, "parent_vault_ok": parent == vault,
            "force_deallocate_penalty": scaled(penalty, 18) if penalty is not None else None,
            "is_liquidity_adapter": adapter == liquidity_adapter,
            "evidence": ctx.ev(vault, "adapters(uint256)", [i], adapter),
        })
        if kind in ("unknown", "parent_mismatch"):
            d.notes.append(f"⚠ adapter {adapter} of vault {name} not recognised ({kind}): its placements are NOT in the graph")
            continue
        for mid, supplied, proof in markets:
            share = supplied / total if total else 0.0
            if share < DUST_SHARE:
                d.notes.append(f"market {mid[:10]}…: negligible allocation ({scaled(supplied, dec):,.2f} {symbol}), ignored")
                continue
            m = read_market(ctx, mid)
            liquidity = max(m["expected_total_supply_assets"] - m["expected_total_borrow_assets"], 0)
            out_now = min(supplied, liquidity)
            withdrawable += out_now
            if liq_market and mid.lower() == liq_market.lower() and adapter == liquidity_adapter:
                penalty_free += out_now
            allocations.append({
                "market_id": mid, "adapter": adapter, "supplied": scaled(supplied, dec), "share_of_vault": round(share, 6),
                "market_utilization": round(m["expected_total_borrow_assets"] / m["expected_total_supply_assets"], 6)
                if m["expected_total_supply_assets"] else None,
                "market_available_liquidity": scaled(liquidity, dec), "withdrawable_now": scaled(out_now, dec),
            })
            d.edges.append(Edge(vkey, market_key(mid), "deployed_in", "onchain",
                                f"{adapters_meta[-1]['evidence']}; {proof}; vault share = {share:.4%} "
                                f"(÷ totalAssets {total})", weight=min(share, 1.0)))
            md = discover_market(ctx, m)
            md.follow = [t for t in md.follow if t.kind != "vaults_lookup"]   # co-lenders are not our dependencies
            d.extend(md)

    placed = sum(a["supplied"] for a in allocations)
    total_h = scaled(total, dec)
    held_h = scaled(held, dec)
    gap = total_h - placed - scaled(idle, dec)
    if total_h and abs(gap) / total_h > 0.001:
        d.notes.append(f"⚠ {name}: totalAssets {total_h:,.2f} ≠ placed {placed:,.2f} + idle {scaled(idle, dec):,.2f} "
                       f"(gap {gap:,.2f} {symbol}) — interest not yet accounted or placement not discovered")
    w_h = scaled(withdrawable, dec)
    d.nodes.append(Node(key=vkey, type="vault", label=name, id_hint=f"vault_{name}", address=vault, meta={
        "vault_version": "Morpho Vault V2", "source_interface": SOURCES["vault"],
        "asset": asset, "asset_symbol": symbol, "asset_decimals": dec,
        "total_assets": str(total), "total_assets_human": total_h, "idle_assets_human": scaled(idle, dec),
        "curator": curator, "owner": owner, "liquidity_adapter": liquidity_adapter,
        "adapters": adapters_meta, "allocations": allocations,
        "holder": holder, "holder_shares": str(shares), "holder_assets_human": held_h, "whole_vault": whole,
        "holder_share_of_vault": round(held / total, 6) if total else None,
        "liquidity_market_id": liq_market,
        "exit_liquidity": {
            "withdrawable_now_human": w_h,
            "penalty_free_human": scaled(penalty_free, dec),
            "covers_holder_share_penalty_free": round(min(scaled(penalty_free, dec) / held_h, 1.0), 6) if held_h else None,
            "penalty_free_definition": "idle + liquidity of the \"liquidity source\" market (liquidityData): normal withdrawal without penalty",
            "definition": "idle + Σ min(supplied by the vault, available market liquidity) — what all the "
                          "depositors together can withdraw now (forceDeallocate, penalty above)",
            "covers_holder_share": round(min(w_h / held_h, 1.0), 6) if held_h else None,
        },
    }))

    ident = curator_identity(ctx, vault, curator)
    ckey = f"issuer:curator_{slugify(ident['name'])}" if ident else f"issuer:curator_{addr6(curator)}"
    meta = {"role": "vault_curator", "curator_address": curator}
    if ident:
        meta.update({"identity_source": ident["source"], "verified_by_morpho": ident["verified"],
                     "website": ident["website"],
                     "note": "Curator address proven on-chain (curator()); the NAME comes from the Morpho API, which "
                             "links this address to the entity."})
        label = f"{ident['name']} (curator)"
    else:
        meta.update({"unresolved": True, "note": "Address read on-chain; identity NOT found (Morpho API silent): "
                                                 "to add to curated.yaml with an official source."})
        label = f"Curator {curator[:6]}…{curator[-4:]}"
    d.nodes.append(Node(key=ckey, type="issuer", label=label, id_hint=ckey.split(":")[1], address=None, chain=None, meta=meta))
    evidence = ctx.ev(vault, "curator()", [], curator)
    if ident:
        evidence += f"; identity: {ident['source']}"
    d.edges.append(Edge(vkey, ckey, "issued_by", "onchain", evidence))
    return d


CURATOR_QUERY = """query Curators($a: String!, $c: Int!) {
  vaultV2ByAddress(address: $a, chainId: $c) { curators { items { name verified addresses { address } socials { type url } } } }
}"""


def curator_identity(ctx: Ctx, vault: str, curator: str) -> dict | None:
    """Name of the curator entity according to the Morpho API, IF the address read on-chain is among its declared addresses."""
    url = ctx.config.apis.get("morpho_graphql")
    if not url or ctx.http is None:
        return None
    try:
        data, fetched_at = ctx.http.post_json(url, {"query": CURATOR_QUERY, "variables": {"a": vault, "c": 1}})
    except Exception:
        return None
    items = ((((data.get("data") or {}).get("vaultV2ByAddress") or {}).get("curators") or {}).get("items")) or []
    for it in items:
        if curator.lower() in {x["address"].lower() for x in it.get("addresses") or []}:
            site = next((s["url"] for s in it.get("socials") or [] if s.get("type") == "url"), None)
            return {"name": it["name"], "verified": bool(it.get("verified")), "website": site,
                    "source": f"API Morpho {url} vaultV2ByAddress({vault}).curators (fetched {fetched_at})"}
    return None
