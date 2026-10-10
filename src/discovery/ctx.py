"""The "context" given to every adapter: the ONLY gateway to the blockchain and to the APIs.

An adapter never imports web3 directly: it calls `ctx.call(...)`.
Benefits: everything is cached, everything is read at the same pinned block, and each read
produces a textual piece of evidence (`ctx.ev(...)`) that goes into `evidence`.

How does a contract call (eth_call) work?
  1. the "selector" = first 4 bytes of keccak256("symbol()") → identifies the function;
  2. the ABI-encoded arguments are appended (32 bytes per simple argument);
  3. the node runs the function read-only, at the requested block, and returns bytes;
  4. those bytes are decoded according to the return types (e.g. ["string"]).
If the function does not exist, the contract "reverts" → `try_call` returns None.
That is how we PROBE an unknown contract to find out what it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address
from web3 import Web3

from .cache import CacheMissError
from .config import Config
from .http import CachedHttp
from .rpc import OfflineError, RpcError

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class CallFailed(RuntimeError):
    pass


def checksum(address: str) -> str:
    return to_checksum_address(address)


def is_zero(address: str | None) -> bool:
    return address is None or int(address, 16) == 0


def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def _arg_types(signature: str) -> list[str]:
    """'f(address,(uint128,uint128))' → ['address', '(uint128,uint128)'] (top-level commas only)."""
    inner = signature[signature.index("(") + 1: signature.rindex(")")]
    types, depth, current = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            types.append(current.strip())
            current = ""
            continue
        depth += (ch == "(") - (ch == ")")
        current += ch
    if current.strip():
        types.append(current.strip())
    return types


def _normalize(types: Sequence[str], values: Sequence[Any]) -> list[Any]:
    out = []
    for t, v in zip(types, values):
        if t == "address":
            out.append(checksum(v))
        elif t == "address[]":
            out.append([checksum(x) for x in v])
        elif t.startswith("bytes") and isinstance(v, (bytes, bytearray)):
            out.append("0x" + bytes(v).hex())
        else:
            out.append(v)
    return out


def fmt_value(v: Any) -> str:
    if isinstance(v, (bytes, bytearray)):
        return "0x" + bytes(v).hex()
    if isinstance(v, (list, tuple)):
        return "(" + ",".join(fmt_value(x) for x in v) + ")"
    if isinstance(v, str) and len(v) > 80:
        return v[:77] + "..."
    return str(v)


@dataclass
class Ctx:
    w3: Web3
    block: int
    http: CachedHttp
    config: Config
    labels: dict[str, str] = field(default_factory=dict)   # checksum address → readable name
    _ts: int | None = None

    # ------------------------------------------------------------------ calls
    def call(self, address: str, signature: str, args: Iterable[Any] = (),
             returns: Sequence[str] = ("uint256",)) -> Any:
        """Calls a read-only function at the pinned block. Raises CallFailed on revert/empty."""
        args = list(args)
        types = _arg_types(signature)
        data = selector(signature) + (encode(types, args) if types else b"")
        try:
            raw = self.w3.eth.call({"to": checksum(address), "data": "0x" + data.hex()},
                                   block_identifier=self.block)
        except (CacheMissError, OfflineError, RpcError):
            raise                      # infrastructure problem: NEVER confused with a revert
        except Exception as e:         # revert, missing function... (ContractLogicError, etc.)
            raise CallFailed(f"{signature} @ {address}: {e}") from e
        if not raw:
            # Calling a function on an address without code (EOA) returns "0x": that is NOT an answer.
            raise CallFailed(f"{signature} @ {address}: empty response")
        try:
            values = _normalize(returns, decode(list(returns), bytes(raw)))
        except Exception as e:
            raise CallFailed(f"{signature} @ {address}: cannot decode as {returns}") from e
        return values[0] if len(values) == 1 else tuple(values)

    def try_call(self, address: str, signature: str, args: Iterable[Any] = (),
                 returns: Sequence[str] = ("uint256",)) -> Any | None:
        try:
            return self.call(address, signature, args, returns)
        except CallFailed:
            return None

    def has_functions(self, address: str, probes: Sequence[tuple[str, Sequence[str]]]) -> bool:
        """True if ALL probed functions answer (probe = (signature, return types))."""
        return all(self.try_call(address, sig, (), ret) is not None for sig, ret in probes)

    def code(self, address: str) -> bytes:
        return bytes(self.w3.eth.get_code(checksum(address), block_identifier=self.block))

    def storage_at(self, address: str, slot: int) -> bytes:
        return bytes(self.w3.eth.get_storage_at(checksum(address), slot, block_identifier=self.block))

    @property
    def block_timestamp(self) -> int:
        if self._ts is None:
            self._ts = int(self.w3.eth.get_block(self.block)["timestamp"])
        return self._ts

    # ------------------------------------------------------------------ evidence
    def label(self, address: str) -> str:
        return self.labels.get(checksum(address), "Contract")

    def ev(self, address: str, signature: str, args: Iterable[Any] = (), result: Any = None) -> str:
        """Readable on-chain evidence: `Label.function(args) = result @ 0xAddress #block`."""
        name = signature[: signature.index("(")]
        arg_s = ",".join(fmt_value(a) for a in args)
        res = f" = {fmt_value(result)}" if result is not None else ""
        return f"{self.label(address)}.{name}({arg_s}){res} @ {checksum(address)} #{self.block}"
