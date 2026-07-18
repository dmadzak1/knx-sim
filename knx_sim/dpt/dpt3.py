"""DPT 3.x — 4-bit control values (B1U3)."""

from __future__ import annotations

from dataclasses import dataclass

from knx_sim.dpt.base import DPTBase, register


@dataclass(frozen=True)
class DimmingControl:
    """A DPT 3.007 control value: a direction plus a step code.

    step_code 0 means "stop"; step_code 1..7 means "step by
    1 / 2**(step_code - 1) of the full range" (1 = a single step spanning
    the whole range, 7 = the finest step).
    """

    direction: bool  # True = increase/up, False = decrease/down
    step_code: int  # 0..7

    def __post_init__(self) -> None:
        if not 0 <= self.step_code <= 7:
            raise ValueError(f"step_code must be 0..7, got {self.step_code}")

    @property
    def is_stop(self) -> bool:
        return self.step_code == 0

    @property
    def step_fraction(self) -> float | None:
        """Fraction of the full range this step covers, or None if stop."""
        if self.step_code == 0:
            return None
        # typeshed types int.__pow__ as returning Any for a non-literal
        # exponent (to cover negative exponents, which yield float); wrap in
        # float() so mypy can confirm the return type here.
        return 1 / float(2 ** (self.step_code - 1))


@register
class DPT3007(DPTBase):
    """DPT 3.007 — Control_Dimming: 1 direction bit + 3-bit step code."""

    dpt_id = "3.007"
    payload_length = 0

    @classmethod
    def encode(cls, value: DimmingControl) -> bytes:
        if not isinstance(value, DimmingControl):
            raise TypeError(f"DPT 3.007 expects a DimmingControl, got {type(value).__name__}")
        raw = (0x08 if value.direction else 0x00) | value.step_code
        return bytes([raw])

    @classmethod
    def decode(cls, data: bytes) -> DimmingControl:
        if len(data) != 1:
            raise ValueError(f"DPT 3.007 expects 1 byte, got {len(data)}")
        raw = data[0]
        if raw > 0x0F:
            raise ValueError(f"DPT 3.007 expects a 4-bit value, got {raw:#04x}")
        return DimmingControl(direction=bool(raw & 0x08), step_code=raw & 0x07)
