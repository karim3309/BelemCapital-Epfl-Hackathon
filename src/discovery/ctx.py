"""Le « contexte » donné à chaque adaptateur : la SEULE porte d'accès à la blockchain et aux APIs.

Un adaptateur n'importe jamais web3 directement : il appelle `ctx.call(...)`.
Avantages : tout est caché, tout est lu au même bloc figé, et chaque lecture
produit une preuve textuelle (`ctx.ev(...)`) qu'on met dans `evidence`.

Comment marche un appel de contrat (eth_call) ?
  1. le « sélecteur » = 4 premiers octets de keccak256("symbol()")  → identifie la fonction ;
  2. on y colle les arguments encodés en ABI (32 octets par argument simple) ;
  3. le nœud exécute la fonction en lecture seule, au bloc demandé, et renvoie des octets ;
  4. on décode ces octets selon les types de retour (ex. ["string"]).
Si la fonction n'existe pas, le contrat « revert » → `try_call` renvoie None.
C'est ainsi qu'on SONDE un contrat inconnu pour savoir ce qu'il est.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address
from web3 import Web3

from .config import Config
from .http import CachedHttp

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
    inner = signature[signature.index("(") + 1: signature.rindex(")")]
    return [t.strip() for t in inner.split(",") if t.strip()]


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
    labels: dict[str, str] = field(default_factory=dict)   # adresse checksum → nom lisible
    _ts: int | None = None

    # ------------------------------------------------------------------ appels
    def call(self, address: str, signature: str, args: Iterable[Any] = (),
             returns: Sequence[str] = ("uint256",)) -> Any:
        """Appelle une fonction en lecture au bloc figé. Lève CallFailed si revert/vide."""
        args = list(args)
        types = _arg_types(signature)
        data = selector(signature) + (encode(types, args) if types else b"")
        try:
            raw = self.w3.eth.call({"to": checksum(address), "data": "0x" + data.hex()},
                                   block_identifier=self.block)
        except Exception as e:  # revert, fonction absente...
            if type(e).__name__ in ("CacheMissError", "OfflineError", "RpcError"):
                raise
            raise CallFailed(f"{signature} @ {address}: {e}") from e
        if not raw:
            # Appeler une fonction sur une adresse sans code (EOA) renvoie "0x" : ce n'est PAS une réponse.
            raise CallFailed(f"{signature} @ {address}: réponse vide")
        try:
            values = _normalize(returns, decode(list(returns), bytes(raw)))
        except Exception as e:
            raise CallFailed(f"{signature} @ {address}: décodage impossible en {returns}") from e
        return values[0] if len(values) == 1 else tuple(values)

    def try_call(self, address: str, signature: str, args: Iterable[Any] = (),
                 returns: Sequence[str] = ("uint256",)) -> Any | None:
        try:
            return self.call(address, signature, args, returns)
        except CallFailed:
            return None

    def has_functions(self, address: str, probes: Sequence[tuple[str, Sequence[str]]]) -> bool:
        """True si TOUTES les fonctions sondées répondent (sonde = (signature, types de retour))."""
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

    # ------------------------------------------------------------------ preuves
    def label(self, address: str) -> str:
        return self.labels.get(checksum(address), "Contract")

    def ev(self, address: str, signature: str, args: Iterable[Any] = (), result: Any = None) -> str:
        """Preuve on-chain lisible : `Label.fonction(args) = résultat @ 0xAdresse #bloc`."""
        name = signature[: signature.index("(")]
        arg_s = ",".join(fmt_value(a) for a in args)
        res = f" = {fmt_value(result)}" if result is not None else ""
        return f"{self.label(address)}.{name}({arg_s}){res} @ {checksum(address)} #{self.block}"
