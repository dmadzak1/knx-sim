"""DPT 14.x — 4-byte IEEE 754 single-precision float values (F32), big-endian."""

from __future__ import annotations

import struct

from knx_sim.dpt.base import DPTBase, register


class DPT14Base(DPTBase):
    """Shared codec for all DPT 14.x (4-byte IEEE 754 float) subtypes.

    Unlike DPT 9.x, this is a plain IEEE 754 single-precision float on the
    wire (no custom exponent/mantissa scheme), so encode/decode is a direct
    struct.pack/unpack. NaN and +/-Infinity round-trip fine in IEEE 754
    itself, so — matching xknx's behaviour — they aren't rejected here; only
    magnitudes that don't fit in a 32-bit float raise.
    """

    payload_length = 4

    @classmethod
    def encode(cls, value: float) -> bytes:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{cls.dpt_id} expects a number, got {type(value).__name__}")
        try:
            return struct.pack(">f", value)
        except (OverflowError, struct.error) as exc:
            raise ValueError(
                f"{cls.dpt_id} value {value} does not fit in a 32-bit float"
            ) from exc

    @classmethod
    def decode(cls, data: bytes) -> float:
        if len(data) != 4:
            raise ValueError(f"{cls.dpt_id} expects 4 bytes, got {len(data)}")
        try:
            (value,) = struct.unpack(">f", data)
        except struct.error as exc:
            raise ValueError(f"{cls.dpt_id} could not unpack {data!r}") from exc
        return float(value)


@register
class DPT14056(DPT14Base):
    """DPT 14.056 — Power, in watts."""

    dpt_id = "14.056"
