"""Generic contract inspection: is it a proxy? If so, pointing to which implementation?

Why this is RISK information: an "upgradeable" proxy can have its code replaced
by its admin. An EIP-1167 clone, on the other hand, is frozen (it always delegates to the same code).

Standard storage slots are COMPUTED here from their definition
(no copied magic constant):
  - EIP-1967 : slot = keccak256("eip1967.proxy.implementation") - 1
  - legacy OpenZeppelin/ZeppelinOS (used by USDC): slot = keccak256("org.zeppelinos.proxy.implementation")
"""
from __future__ import annotations

from eth_utils import keccak, to_checksum_address

from ..ctx import Ctx

EIP1167_PREFIX = bytes.fromhex("363d3d373d3d3d363d73")
EIP1167_SUFFIX = bytes.fromhex("5af43d82803e903d91602b57fd5bf3")

EIP1967_IMPL_SLOT = int.from_bytes(keccak(text="eip1967.proxy.implementation"), "big") - 1
EIP1967_BEACON_SLOT = int.from_bytes(keccak(text="eip1967.proxy.beacon"), "big") - 1
ZEPPELINOS_IMPL_SLOT = int.from_bytes(keccak(text="org.zeppelinos.proxy.implementation"), "big")


def proxy_info(ctx: Ctx, address: str) -> dict | None:
    code = ctx.code(address)
    if len(code) == 45 and code.startswith(EIP1167_PREFIX) and code.endswith(EIP1167_SUFFIX):
        impl = to_checksum_address(code[10:30])
        return {"detected": True, "standard": "EIP-1167 (minimal clone, not upgradeable)", "implementation": impl,
                "upgradeable": False,
                "evidence": f"eth_getCode({to_checksum_address(address)}) = clone EIP-1167 → {impl} #{ctx.block}"}
    for name, slot in (("EIP-1967", EIP1967_IMPL_SLOT), ("EIP-1967 beacon", EIP1967_BEACON_SLOT),
                       ("ZeppelinOS (legacy)", ZEPPELINOS_IMPL_SLOT)):
        raw = ctx.storage_at(address, slot)
        if int.from_bytes(raw, "big") != 0:
            impl = to_checksum_address(raw[-20:])
            return {"detected": True, "standard": f"{name} (upgradeable)", "implementation": impl, "upgradeable": True,
                    "evidence": f"eth_getStorageAt({to_checksum_address(address)}, slot {name}) = {impl} #{ctx.block}"}
    return None


NOT_DETECTED = {
    "detected": False,
    "upgradeable": None,
    "note": "no EIP-1167 / EIP-1967 / ZeppelinOS proxy detected — other schemes exist: not proven immutable",
}

