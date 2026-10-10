"""Fake context to test the adapters WITHOUT a blockchain.

We describe by hand what each contract "would answer":
    responses[(address, "symbol()", ())] = "USDC"
Any function not described "reverts" (CallFailed), exactly like a real contract
that does not have that function. This is what lets us test the PROBING logic.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from discovery.ctx import CallFailed, Ctx, checksum


def addr(n: int) -> str:
    """Deterministic dummy address: addr(1) = 0x000...0001 (checksum)."""
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
            raise CallFailed(f"simulated revert: {signature} @ {address}")
        return self.responses[key]

    def code(self, address: str) -> bytes:
        return self.codes.get(checksum(address), b"\x60\x80")   # default: "there is code"

    def storage_at(self, address: str, slot: int) -> bytes:
        return bytes(32)                                    # default: not a proxy

    @property
    def block_timestamp(self) -> int:
        return self._fake_ts
