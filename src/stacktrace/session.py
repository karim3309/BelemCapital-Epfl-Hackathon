"""Session EN LIGNE : une connexion RPC + UN bloc figé pour toute une analyse.

Pourquoi figer un bloc alors qu'on travaille en direct ?
  La blockchain avance d'un bloc toutes les ~12 s. Si on lisait le vault au bloc N et ses marchés
  au bloc N+3, les chiffres ne seraient plus cohérents entre eux. On lit donc « latest » UNE fois au
  démarrage, puis toutes les lectures de l'analyse se font à ce bloc-là : c'est une photo instantanée
  de la chaîne, et chaque preuve peut citer « … @ 0xAdresse #bloc ».

Le cache (data/cache_live/) n'est plus là pour la démo hors ligne : il évite de relire deux fois la même
chose pendant une analyse et garde une trace lisible de chaque réponse. Il est ignoré par git.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from web3 import Web3

from discovery.cache import DiskCache
from discovery.config import REPO_ROOT, Config, load_config
from discovery.ctx import Ctx
from discovery.http import CachedHttp
from discovery.rpc import CachedHTTPProvider, check_chain, make_web3, resolve_snapshot_block

LIVE_CACHE_DIR = REPO_ROOT / "data" / "cache_live"


class SessionError(RuntimeError):
    pass


class BlockScopedHttp(CachedHttp):
    """APIs en ligne : la réponse cachée est rattachée au BLOC de l'analyse.

    Une API ne sait pas répondre « au bloc N » : sans ce rattachement, la première réponse resterait
    dans le cache pour toujours (données périmées). Ici, une nouvelle analyse (nouveau bloc) refait
    l'appel, et deux lectures dans la même analyse renvoient la même réponse (cohérence).
    """

    def __init__(self, cache: DiskCache, block: int, **kw):
        super().__init__(cache, **kw)
        self.block = block

    def _cached(self, payload: dict, do_request):
        return super()._cached({**payload, "analysis_block": self.block}, do_request)


def mask_url(url: str | None) -> str:
    """Affiche l'hôte d'une URL RPC sans jamais montrer la clé (souvent dans le chemin)."""
    if not url:
        return "—"
    host = urlparse(url).hostname or ""
    return (host[:4] + "…" + host[-12:]) if len(host) > 18 else host


@dataclass
class Session:
    config: Config
    w3: Web3
    cache: DiskCache
    chain_id: int
    block: int              # le bloc figé de cette analyse
    block_timestamp: int    # son horodatage (secondes UNIX)
    ctx: Ctx                # la porte d'accès des adaptateurs (ctx.call, ctx.http, preuves)

    @property
    def provider(self) -> CachedHTTPProvider:
        return self.w3.provider  # type: ignore[return-value]

    @property
    def network_calls(self) -> int:
        return self.provider.network_calls

    def describe(self) -> str:
        t = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(self.block_timestamp))
        return f"chaîne {self.chain_id} · bloc #{self.block} ({t}) · RPC {mask_url(self.config.rpc_url)}"


def open_session(block: int | str = "latest") -> Session:
    """Ouvre une session en ligne. `block` = "latest" (par défaut) ou un numéro (rejeu d'un état passé).

    Lève SessionError avec un message clair si le RPC manque ou ne répond pas.
    """
    config = load_config(offline=False)
    if not config.rpc_url:
        raise SessionError("ETH_RPC_URL est vide : ouvrez le fichier .env à la racine du repo et collez-y "
                           "l'URL de votre endpoint Ethereum mainnet (QuickNode, Alchemy…).")
    cache = DiskCache(LIVE_CACHE_DIR, offline=False)
    w3 = make_web3(config.rpc_url, cache)
    try:
        chain_id = check_chain(w3, config.expected_chain_id)
        pinned = resolve_snapshot_block(w3, block, offline=False)
        ts = int(w3.eth.get_block(pinned)["timestamp"])
    except Exception as e:  # message pédagogique plutôt qu'une trace web3 illisible
        raise SessionError(f"Le RPC ({mask_url(config.rpc_url)}) ne répond pas correctement : {e}") from e
    ctx = Ctx(w3=w3, block=pinned, http=BlockScopedHttp(cache, pinned), config=config)
    return Session(config=config, w3=w3, cache=cache, chain_id=chain_id, block=pinned, block_timestamp=ts, ctx=ctx)
