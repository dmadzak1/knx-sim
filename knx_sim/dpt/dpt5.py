"""DPT 5.x — 1-byte unsigned values (U8)."""

from __future__ import annotations

from knx_sim.dpt.base import DPTBase, register


@register
class DPT5001(DPTBase):
    """DPT 5.001 — Scaling: 0..100%, linearly mapped onto a byte 0..255."""

    dpt_id = "5.001"
    payload_length = 1

    _MAX_PERCENT = 100.0
    _MAX_RAW = 255

    @classmethod
    def encode(cls, value: float) -> bytes:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"DPT 5.001 expects a number, got {type(value).__name__}")
        if not 0.0 <= value <= cls._MAX_PERCENT:
            raise ValueError(f"DPT 5.001 expects 0..100, got {value}")
        raw = round(value * cls._MAX_RAW / cls._MAX_PERCENT)
        return bytes([raw])

    @classmethod
    def decode(cls, data: bytes) -> float:
        if len(data) != 1:
            raise ValueError(f"DPT 5.001 expects 1 byte, got {len(data)}")
        return data[0] * cls._MAX_PERCENT / cls._MAX_RAW


@register
class DPT5004(DPTBase):
    """DPT 5.004 — Percent_U8: raw byte 0..255, 1:1 (no scaling)."""

    dpt_id = "5.004"
    payload_length = 1

    @classmethod
    def encode(cls, value: int) -> bytes:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"DPT 5.004 expects an int, got {type(value).__name__}")
        if not 0 <= value <= 255:
            raise ValueError(f"DPT 5.004 expects 0..255, got {value}")
        return bytes([value])

    @classmethod
    def decode(cls, data: bytes) -> int:
        if len(data) != 1:
            raise ValueError(f"DPT 5.004 expects 1 byte, got {len(data)}")
        return data[0]
