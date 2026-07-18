"""DPT 1.x — 1-bit values (B1)."""

from __future__ import annotations

from knx_sim.dpt.base import DPTBase, register


class DPT1BitBase(DPTBase):
    """Shared codec for all DPT 1.x (1-bit boolean) subtypes."""

    payload_length = 0

    @classmethod
    def encode(cls, value: bool) -> bytes:
        if not isinstance(value, bool):
            raise TypeError(f"{cls.dpt_id} expects a bool, got {type(value).__name__}")
        return bytes([1 if value else 0])

    @classmethod
    def decode(cls, data: bytes) -> bool:
        if len(data) != 1:
            raise ValueError(f"{cls.dpt_id} expects 1 byte, got {len(data)}")
        if data[0] not in (0, 1):
            raise ValueError(f"{cls.dpt_id} expects byte value 0 or 1, got {data[0]}")
        return bool(data[0])


@register
class DPT1001(DPT1BitBase):
    """DPT 1.001 — Switch (False = Off, True = On)."""

    dpt_id = "1.001"


@register
class DPT1008(DPT1BitBase):
    """DPT 1.008 — Up/Down (False = Up, True = Down)."""

    dpt_id = "1.008"


@register
class DPT1009(DPT1BitBase):
    """DPT 1.009 — Open/Close (False = Open, True = Close)."""

    dpt_id = "1.009"


@register
class DPT1010(DPT1BitBase):
    """DPT 1.010 — Start/Stop (False = Stop, True = Start)."""

    dpt_id = "1.010"


@register
class DPT1018(DPT1BitBase):
    """DPT 1.018 — Occupancy (False = Not Occupied, True = Occupied)."""

    dpt_id = "1.018"
