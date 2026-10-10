"""Chargement de config.yaml + .env, avec garde-fous anti-hallucination.

On refuse de démarrer si une adresse est un placeholder ("0x...", "TO_VERIFY", "à vérifier")
ou n'a pas le bon format : mieux vaut planter que découvrir un graphe faux.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_MARKET_ID_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_PLACEHOLDERS = ("0x...", "to_verify", "todo", "à vérifier", "a verifier")


class ConfigError(ValueError):
    pass


def _check_address(name: str, value: Any) -> str:
    if not isinstance(value, str) or any(p in value.lower() for p in _PLACEHOLDERS):
        raise ConfigError(f"{name}: adresse manquante ou placeholder ({value!r}) — vérifiez-la sur Etherscan")
    if not _ADDRESS_RE.match(value):
        raise ConfigError(f"{name}: format d'adresse invalide ({value!r})")
    return value


@dataclass
class Config:
    raw: dict
    path: Path
    chain_name: str
    expected_chain_id: int
    snapshot_block: int | str          # int, ou "latest" (résolu au démarrage)
    rpc_url: str | None
    offline: bool
    market_id: str
    user: str | None
    value_usd_override: float | None
    contracts: dict[str, str]          # nom → adresse
    contract_sources: dict[str, str]   # nom → URL de la source
    loan_usd_feed_ens: str | None
    apis: dict[str, str]
    api_sources: dict[str, str]
    max_nodes: int
    include_vaults: bool
    curated_file: Path
    output_file: Path
    cache_dir: Path
    extra: dict = field(default_factory=dict)


def load_config(path: str | Path | None = None, *, offline: bool | None = None) -> Config:
    path = Path(path) if path else REPO_ROOT / "config.yaml"
    load_dotenv(REPO_ROOT / ".env")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    pos = raw["position"]
    if pos.get("protocol") != "morpho":
        raise ConfigError("Seul le protocole 'morpho' est supporté comme racine pour l'instant")
    market_id = str(pos["market_id"])
    if not _MARKET_ID_RE.match(market_id):
        raise ConfigError(f"position.market_id invalide : {market_id!r} (attendu 0x + 64 hex)")
    user = pos.get("user")
    if user is not None:
        user = _check_address("position.user", user)

    contracts, sources = {}, {}
    for name, entry in raw["contracts"].items():
        contracts[name] = _check_address(f"contracts.{name}.address", entry.get("address"))
        sources[name] = entry.get("source", "")
        if not sources[name].startswith("http"):
            raise ConfigError(f"contracts.{name}: une `source` (URL) est obligatoire")

    snap = raw.get("snapshot_block", "latest")
    if not (snap == "latest" or isinstance(snap, int)):
        raise ConfigError("snapshot_block doit être un entier ou 'latest'")

    if offline is None:
        offline = os.getenv("STACKTRACE_OFFLINE", "0").strip() in ("1", "true", "yes")

    disc = raw.get("discovery", {})
    rpc_env = raw.get("rpc", {}).get("url_env", "ETH_RPC_URL")
    return Config(
        raw=raw,
        path=path,
        chain_name=raw["chain"]["name"],
        expected_chain_id=int(raw["chain"]["expected_chain_id"]),
        snapshot_block=snap,
        rpc_url=os.getenv(rpc_env) or None,
        offline=offline,
        market_id=market_id.lower(),
        user=user,
        value_usd_override=pos.get("value_usd_override"),
        contracts=contracts,
        contract_sources=sources,
        loan_usd_feed_ens=(raw.get("usd_reference") or {}).get("loan_token_usd_feed_ens"),
        apis={k: v["url"] for k, v in raw.get("apis", {}).items()},
        api_sources={k: v.get("source", "") for k, v in raw.get("apis", {}).items()},
        max_nodes=int(disc.get("max_nodes", 200)),
        include_vaults=bool(disc.get("include_vaults", True)),
        curated_file=REPO_ROOT / disc.get("curated_file", "curated.yaml"),
        output_file=REPO_ROOT / disc.get("output_file", "output/graph.json"),
        cache_dir=REPO_ROOT / disc.get("cache_dir", "data/cache"),
    )
