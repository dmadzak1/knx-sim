"""DPT 1.x — 1-bit values (B1)."""

from __future__ import annotations

from knx_sim.dpt.base import DPTBase, register


@register
class DPT1001(DPTBase):
    """DPT 1.001 — Switch (False = Off, True = On)."""

    dpt_id = "1.001"
    payload_length = 0

    @classmethod
    def encode(cls, value: bool) -> bytes:
        if not isinstance(value, bool):
            raise TypeError(f"DPT 1.001 expects a bool, got {type(value).__name__}")
        return bytes([1 if value else 0])

    @classmethod
    def decode(cls, data: bytes) -> bool:
        if len(data) != 1:
            raise ValueError(f"DPT 1.001 expects 1 byte, got {len(data)}")
        if data[0] not in (0, 1):
            raise ValueError(f"DPT 1.001 expects byte value 0 or 1, got {data[0]}")
        return bool(data[0])
