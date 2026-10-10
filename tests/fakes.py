"""Faux contexte pour tester les adaptateurs SANS blockchain.

On décrit à la main ce que « répondrait » chaque contrat :
    responses[(adresse, "symbol()", ())] = "USDC"
Toute fonction non décrite fait un « revert » (CallFailed), exactement comme un vrai contrat
qui n'a pas cette fonction. C'est ce qui permet de tester la logique de SONDAGE.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from discovery.ctx import CallFailed, Ctx, checksum


def addr(n: int) -> str:
    """Adresse factice déterministe : addr(1) = 0x000...0001 (checksum)."""
    return checksum("0x" + f"{n:040x}")


class FakeCtx(Ctx):
    def __init__(self, responses: dict | None = None, codes: dict | None = None,
                 block: int = 100, timestamp: int = 1_700_000_000, contracts: dict | None = None):
        super().__init__(w3=None, block=block, http=None,
                         config=SimpleNamespace(contracts=contracts or {}, apis={}, loan_usd_feed_ens=None))
        self.responses = {(checksum(a), sig, tuple(args)): v for (a, sig, args), v in (responses or {}).items()}
        self.codes = {checksum(a): c for a, c in (codes or {}).items()}
        self._fake_ts = timestamp
        self.calls: list[tuple] = []

    def call(self, address: str, signature: str, args=(), returns=("uint256",)) -> Any:
        key = (checksum(address), signature, tuple(args))
        self.calls.append(key)
        if key not in self.responses:
            raise CallFailed(f"revert simulé : {signature} @ {address}")
        return self.responses[key]

    def code(self, address: str) -> bytes:
        return self.codes.get(checksum(address), b"\x60\x80")   # par défaut : « il y a du code »

    def storage_at(self, address: str, slot: int) -> bytes:
        return bytes(32)                                    # par défaut : pas un proxy

    @property
    def block_timestamp(self) -> int:
        return self._fake_ts
