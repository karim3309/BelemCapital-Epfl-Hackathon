"""Convention d'`id` des nœuds : un slug snake_case DÉTERMINISTE (même entrée → même id, sur toutes les machines).

  - token          → symbol() normalisé            "PT-sUSDE-26NOV2026" → "pt_susde_26nov2026"
  - marché Morpho  → morpho_market_<8 hex de l'ID> "morpho_market_5613b170"
  - feed Chainlink → feed_<description>            "USDe / USD"         → "feed_usde_usd"
  - autre contrat  → <kind>_<6 hex de l'adresse>   "oracle_meta_f8b29e"
  - hors chaîne    → nom de l'entité              "ethena_labs", "copper"
  - chaîne         → nom                            "ethereum"
En cas de collision, graph.py ajoute "_<6 hex de l'adresse>" (ou un suffixe numérique).
"""
from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _NON_ALNUM.sub("_", text.strip().lower()).strip("_")
    return slug or "node"


def addr6(address: str) -> str:
    return address.lower().removeprefix("0x")[:6]


def token_id(symbol: str) -> str:
    return slugify(symbol)


def contract_id(kind: str, address: str) -> str:
    return f"{slugify(kind)}_{addr6(address)}"


def morpho_market_id(market_id: str) -> str:
    return f"morpho_market_{market_id.lower().removeprefix('0x')[:8]}"


def position_id(market_id: str, user: str) -> str:
    """Format imposé par le contrat : morpho:<marketId>:<user>."""
    return f"morpho:{market_id.lower()}:{user}"
