"""Adaptateur racine : un dépôt dans un Morpho Vault V2 → le vault, ses adapters, ses marchés.

Comment est construit un Morpho Vault V2 (code source officiel, voir SOURCES) :
  - le VAULT reçoit les dépôts (ERC-4626 : on reçoit des parts) ;
  - il n'investit pas lui-même : il passe par des ADAPTERS (vault.adapters(i)), un par « type de placement » ;
  - un adapter « marché Morpho » place l'argent dans N marchés Morpho Blue (adapter.marketIds(j)) ;
  - le CURATEUR (vault.curator()) choisit les adapters et les plafonds ; des « allocateurs » répartissent.
  - pour sortir, un déposant retire ce qui est liquide ; s'il n'y en a pas assez, il peut FORCER le retrait
    d'un adapter (forceDeallocate) en payant une pénalité (vault.forceDeallocatePenalty(adapter)),
    mais seulement dans la limite de ce que chaque marché a de disponible (le reste est prêté).

Ce que l'on prouve on-chain, au bloc figé :
  détenteur --deployed_in--> vault           balanceOf + convertToAssets
  vault     --deployed_in--> marché (poids)  adapters(i) → marketIds(j) → expectedSupplyAssets(id)
  vault     --issued_by-->   curateur        curator()   (identité de l'adresse : NON prouvée → à curer)
puis chaque marché est confié à l'adaptateur Morpho existant (collatéral, actif prêté, oracle…).
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
DUST_SHARE = 1e-6       # allocation < 0,0001 % du vault : listée en note, pas de nœud


def _adapter_markets(ctx: Ctx, adapter: str) -> tuple[str, list[tuple[str, int, str]]]:
    """(type d'adapter, [(marketId, actifs fournis, preuve)]) — sonde les deux versions officielles."""
    n = ctx.try_call(adapter, "marketIdsLength()")
    if n is not None:                                   # MorphoMarketV1AdapterV2 (version actuelle)
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
    vault, holder = checksum(vault), checksum(holder)
    name = ctx.call(vault, "name()", returns=["string"])
    ctx.labels[vault] = name
    asset = ctx.call(vault, "asset()", returns=["address"])
    dec = ctx.call(asset, "decimals()", returns=["uint8"])
    symbol = ctx.try_call(asset, "symbol()", returns=["string"]) or "?"
    total = ctx.call(vault, "totalAssets()")
    shares = ctx.call(vault, "balanceOf(address)", [holder])
    held = ctx.call(vault, "convertToAssets(uint256)", [shares]) if shares else 0
    if not shares:
        raise ValueError(f"{holder} n'a aucune part du vault {name} au bloc {ctx.block}")
    curator = ctx.call(vault, "curator()", returns=["address"])
    owner = ctx.try_call(vault, "owner()", returns=["address"])
    liquidity_adapter = ctx.try_call(vault, "liquidityAdapter()", returns=["address"])
    idle = ctx.call(asset, "balanceOf(address)", [vault])          # actifs non placés, retirables tout de suite
    # Marché « source de liquidité » : un retrait normal y puise SANS pénalité (vault.liquidityData() =
    # abi.encode(MarketParams) pour un adapter marché Morpho). Au-delà, il faut forceDeallocate (pénalité).
    liq_market = None
    raw_ld = ctx.try_call(vault, "liquidityData()", returns=["bytes"])
    if raw_ld and len(bytes.fromhex(raw_ld[2:])) == 160:
        liq_market = "0x" + keccak(bytes.fromhex(raw_ld[2:])).hex()

    d = Discovery()
    vkey = vault
    d.edges.append(Edge(POSITION_KEY, vkey, "deployed_in", "onchain",
                        f"{ctx.ev(vault, 'balanceOf(address)', [holder], shares)} ; "
                        f"{ctx.ev(vault, 'convertToAssets(uint256)', [shares], held)}"))

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
            d.notes.append(f"⚠ adapter {adapter} du vault {name} non reconnu ({kind}) : ses placements ne sont PAS dans le graphe")
            continue
        for mid, supplied, proof in markets:
            share = supplied / total if total else 0.0
            if share < DUST_SHARE:
                d.notes.append(f"marché {mid[:10]}… : allocation négligeable ({scaled(supplied, dec):,.2f} {symbol}), ignoré")
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
                                f"{adapters_meta[-1]['evidence']} ; {proof} ; part du vault = {share:.4%} "
                                f"(÷ totalAssets {total})", weight=min(share, 1.0)))
            md = discover_market(ctx, m)
            md.follow = [t for t in md.follow if t.kind != "vaults_lookup"]   # les co-prêteurs ne sont pas nos dépendances
            d.extend(md)

    placed = sum(a["supplied"] for a in allocations)
    total_h = scaled(total, dec)
    held_h = scaled(held, dec)
    gap = total_h - placed - scaled(idle, dec)
    if total_h and abs(gap) / total_h > 0.001:
        d.notes.append(f"⚠ {name} : totalAssets {total_h:,.2f} ≠ placé {placed:,.2f} + idle {scaled(idle, dec):,.2f} "
                       f"(écart {gap:,.2f} {symbol}) — intérêts non encore comptabilisés ou placement non découvert")
    w_h = scaled(withdrawable, dec)
    d.nodes.append(Node(key=vkey, type="vault", label=name, id_hint=f"vault_{name}", address=vault, meta={
        "vault_version": "Morpho Vault V2", "source_interface": SOURCES["vault"],
        "asset": asset, "asset_symbol": symbol, "asset_decimals": dec,
        "total_assets": str(total), "total_assets_human": total_h, "idle_assets_human": scaled(idle, dec),
        "curator": curator, "owner": owner, "liquidity_adapter": liquidity_adapter,
        "adapters": adapters_meta, "allocations": allocations,
        "holder": holder, "holder_shares": str(shares), "holder_assets_human": held_h,
        "holder_share_of_vault": round(held / total, 6) if total else None,
        "liquidity_market_id": liq_market,
        "exit_liquidity": {
            "withdrawable_now_human": w_h,
            "penalty_free_human": scaled(penalty_free, dec),
            "covers_holder_share_penalty_free": round(min(scaled(penalty_free, dec) / held_h, 1.0), 6) if held_h else None,
            "penalty_free_definition": "idle + liquidité du marché « source de liquidité » (liquidityData) : retrait normal sans pénalité",
            "definition": "idle + Σ min(fourni par le vault, liquidité disponible du marché) — ce que l'ensemble des "
                          "déposants peut retirer maintenant (forceDeallocate, pénalité ci-dessus)",
            "covers_holder_share": round(min(w_h / held_h, 1.0), 6) if held_h else None,
        },
    }))

    ident = curator_identity(ctx, vault, curator)
    ckey = f"issuer:curator_{slugify(ident['name'])}" if ident else f"issuer:curator_{addr6(curator)}"
    meta = {"role": "vault_curator", "curator_address": curator}
    if ident:
        meta.update({"identity_source": ident["source"], "verified_by_morpho": ident["verified"],
                     "website": ident["website"],
                     "note": "Adresse du curateur prouvée on-chain (curator()) ; le NOM vient de l'API Morpho, qui "
                             "relie cette adresse à l'entité."})
        label = f"{ident['name']} (curateur)"
    else:
        meta.update({"unresolved": True, "note": "Adresse lue on-chain ; identité NON trouvée (API Morpho muette) : "
                                                 "à ajouter dans curated.yaml avec une source officielle."})
        label = f"Curateur {curator[:6]}…{curator[-4:]}"
    d.nodes.append(Node(key=ckey, type="issuer", label=label, id_hint=ckey.split(":")[1], address=None, chain=None, meta=meta))
    evidence = ctx.ev(vault, "curator()", [], curator)
    if ident:
        evidence += f" ; identité : {ident['source']}"
    d.edges.append(Edge(vkey, ckey, "issued_by", "onchain", evidence))
    return d


CURATOR_QUERY = """query Curators($a: String!, $c: Int!) {
  vaultV2ByAddress(address: $a, chainId: $c) { curators { items { name verified addresses { address } socials { type url } } } }
}"""


def curator_identity(ctx: Ctx, vault: str, curator: str) -> dict | None:
    """Nom de l'entité curatrice selon l'API Morpho, SI l'adresse lue on-chain figure dans ses adresses déclarées."""
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
