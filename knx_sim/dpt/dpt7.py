"""DPT 7.x — 2-byte unsigned values (U16), big-endian."""

from __future__ import annotations

from knx_sim.dpt.base import DPTBase, register


class DPT7Base(DPTBase):
    """Shared codec for all DPT 7.x (2-byte unsigned integer) subtypes."""

    payload_length = 2

    @classmethod
    def encode(cls, value: int) -> bytes:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{cls.dpt_id} expects an int, got {type(value).__name__}")
        if not 0 <= value <= 65535:
            raise ValueError(f"{cls.dpt_id} expects 0..65535, got {value}")
        return value.to_bytes(2, "big")

    @classmethod
    def decode(cls, data: bytes) -> int:
        if len(data) != 2:
            raise ValueError(f"{cls.dpt_id} expects 2 bytes, got {len(data)}")
        return int.from_bytes(data, "big")


@register
class DPT7001(DPT7Base):
    """DPT 7.001 — 2-byte unsigned pulse counter."""

    dpt_id = "7.001"
