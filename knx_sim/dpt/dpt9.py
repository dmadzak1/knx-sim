"""DPT 9.x — 2-byte KNX float values (F16)."""

from __future__ import annotations

import math

from knx_sim.dpt.base import DPTBase, register

_MIN_VALUE = -671088.64
_MAX_VALUE = 670760.96


class DPT9Base(DPTBase):
    """Shared codec for all DPT 9.x (2-byte KNX float) subtypes.

    Wire format: S EEEE MMMMMMMMMMM (16 bits) — 1 sign bit, 4-bit exponent,
    11-bit mantissa. The sign bit plus the mantissa together form a 12-bit
    two's complement integer M; value = 0.01 * M * 2**E. Encoding picks the
    smallest exponent for which M fits in [-2048, 2047], so each value has
    exactly one valid encoding.
    """

    payload_length = 2

    @classmethod
    def encode(cls, value: float) -> bytes:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{cls.dpt_id} expects a number, got {type(value).__name__}")
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{cls.dpt_id} does not support NaN/Infinity")
        if not _MIN_VALUE <= value <= _MAX_VALUE:
            raise ValueError(f"{cls.dpt_id} expects {_MIN_VALUE}..{_MAX_VALUE}, got {value}")

        for exponent in range(16):
            mantissa = round(value / (0.01 * (2**exponent)))
            if -2048 <= mantissa <= 2047:
                break
        else:  # pragma: no cover - unreachable, the range check above guarantees a fit
            raise ValueError(f"{cls.dpt_id} value {value} does not fit in any exponent")

        raw12 = mantissa & 0x0FFF
        sign_bit = (raw12 >> 11) & 0x01
        mantissa11 = raw12 & 0x7FF

        byte1 = (sign_bit << 7) | (exponent << 3) | (mantissa11 >> 8)
        byte2 = mantissa11 & 0xFF
        return bytes([byte1, byte2])

    @classmethod
    def decode(cls, data: bytes) -> float:
        if len(data) != 2:
            raise ValueError(f"{cls.dpt_id} expects 2 bytes, got {len(data)}")
        byte1, byte2 = data
        sign_bit = (byte1 >> 7) & 0x01
        exponent = (byte1 >> 3) & 0x0F
        mantissa11 = ((byte1 & 0x07) << 8) | byte2
        raw12 = (sign_bit << 11) | mantissa11
        mantissa = raw12 - 4096 if sign_bit else raw12
        # float() wrap works around typeshed typing int**int as Any (to
        # cover negative exponents, which int.__pow__ can't produce here).
        return 0.01 * mantissa * float(2**exponent)


@register
class DPT9001(DPT9Base):
    """DPT 9.001 — Temperature, in degrees Celsius."""

    dpt_id = "9.001"
