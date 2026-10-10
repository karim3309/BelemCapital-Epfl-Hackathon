"""Diagnostic en une commande : est-ce que tout ce dont le backend a besoin répond, EN DIRECT ?

    PYTHONPATH=src python -m stacktrace.doctor

Vérifie, dans l'ordre :
  1. ETH_RPC_URL est défini dans .env (on n'affiche que l'hôte, jamais la clé) ;
  2. le RPC répond, sur la bonne chaîne (chainId = 1 = Ethereum mainnet), et en combien de temps ;
  3. le dernier bloc est récent (un nœud en retard donnerait une photo périmée) ;
  4. le nœud est « archive » (il sait répondre pour un bloc ancien → rejeux d'incidents possibles) ;
  5. les APIs Morpho et Pendle répondent (elles servent à LOCALISER, on re-prouve ensuite on-chain).
Code de sortie 0 si tout l'indispensable est OK, 1 sinon.
"""
from __future__ import annotations

import sys
import time

import requests

from discovery.console import utf8_console

from .session import SessionError, mask_url, open_session

ARCHIVE_LOOKBACK_BLOCKS = 216_000      # ≈ 30 jours à 12 s/bloc
MAX_BLOCK_AGE_S = 120                  # au-delà, le nœud est probablement en retard


def _api_check(name: str, fn) -> tuple[bool, str]:
    t = time.time()
    try:
        detail = fn()
        return True, f"{name} : OK ({(time.time() - t) * 1000:.0f} ms){detail}"
    except Exception as e:
        return False, f"{name} : ÉCHEC ({type(e).__name__}: {str(e)[:120]})"


def run() -> int:
    utf8_console()
    lines: list[tuple[str, str]] = []           # (statut, texte)
    vital_ok = True

    try:
        t = time.time()
        s = open_session("latest")
        latency = (time.time() - t) * 1000
    except SessionError as e:
        print(f"✗ {e}")
        return 1

    lines.append(("✓", f"ETH_RPC_URL trouvé · hôte {mask_url(s.config.rpc_url)}"))
    lines.append(("✓", f"RPC sur chainId {s.chain_id} (Ethereum mainnet) · ouverture de session {latency:.0f} ms"))
    age = time.time() - s.block_timestamp
    fresh = age < MAX_BLOCK_AGE_S
    lines.append(("✓" if fresh else "!", f"bloc figé pour l'analyse : #{s.block} · âge {age:.0f} s"
                  + ("" if fresh else " → le nœud semble en retard")))

    old = s.block - ARCHIVE_LOOKBACK_BLOCKS
    try:
        s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=old)
        lines.append(("✓", f"nœud archive : lecture au bloc #{old} (~30 j) OK → rejeux d'incidents possibles"))
    except Exception:
        lines.append(("!", "nœud NON archive : seul l'état récent est lisible (pas de rejeu historique)"))

    morpho_url = s.config.apis.get("morpho_graphql")
    pendle_url = s.config.apis.get("pendle_core")

    def morpho():
        r = requests.post(morpho_url, json={"query": "{ __typename }"}, timeout=20)
        r.raise_for_status()
        if r.json().get("data", {}).get("__typename") != "Query":
            raise RuntimeError("réponse inattendue")
        return ""

    def pendle():
        r = requests.get(f"{pendle_url}/v2/markets/all", params={"skip": 0, "limit": 1}, timeout=20)
        r.raise_for_status()
        return ""

    for name, url, fn in (("API Morpho", morpho_url, morpho), ("API Pendle", pendle_url, pendle)):
        if not url:
            lines.append(("!", f"{name} : URL absente de config.yaml (section apis)"))
            continue
        ok, txt = _api_check(name, fn)
        lines.append(("✓" if ok else "✗", txt))
        vital_ok &= ok if name == "API Morpho" else True   # Morpho indispensable (scan des positions)

    print("=== StackTrace · diagnostic en ligne ===")
    for status, txt in lines:
        print(f"  {status} {txt}")
    print(f"  · appels RPC réseau pendant le test : {s.network_calls}")
    print("→ prêt" if vital_ok else "→ PAS prêt : corrigez les lignes ✗ ci-dessus")
    return 0 if vital_ok else 1


if __name__ == "__main__":
    sys.exit(run())
