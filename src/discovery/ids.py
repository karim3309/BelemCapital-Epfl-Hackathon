"""Node `id` convention: a DETERMINISTIC snake_case slug (same input → same id, on every machine).

  - token          → normalised symbol()           "PT-sUSDE-26NOV2026" → "pt_susde_26nov2026"
  - Morpho market  → morpho_market_<8 hex of ID>  "morpho_market_5613b170"
  - feed Chainlink → feed_<description>            "USDe / USD"         → "feed_usde_usd"
  - other contract → <kind>_<6 hex of the address>  "oracle_meta_f8b29e"
  - off-chain      → entity name                  "ethena_labs", "copper"
  - chain          → name                           "ethereum"
On collision, graph.py appends "_<6 hex of the address>" (or a numeric suffix).
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
    """Format required by the contract: morpho:<marketId>:<user>."""
    return f"morpho:{market_id.lower()}:{user}"
