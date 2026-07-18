from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt14 import DPT14056


class TestDPT14056:
    def test_encode_known_values(self) -> None:
        assert DPT14056.encode(0.0) == bytes.fromhex("00000000")
        assert DPT14056.encode(1.0) == bytes.fromhex("3f800000")
        assert DPT14056.encode(-1.0) == bytes.fromhex("bf800000")

    def test_decode_known_values(self) -> None:
        assert DPT14056.decode(bytes.fromhex("00000000")) == 0.0
        assert DPT14056.decode(bytes.fromhex("3f800000")) == 1.0
        assert DPT14056.decode(bytes.fromhex("bf800000")) == -1.0

    def test_encode_rejects_magnitude_too_large_for_float32(self) -> None:
        with pytest.raises(ValueError, match="does not fit"):
            DPT14056.encode(1e40)

    def test_encode_rejects_non_number(self) -> None:
        with pytest.raises(TypeError):
            DPT14056.encode("1.0")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DPT14056.encode(True)

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 4 bytes"):
            DPT14056.decode(bytes([0, 0, 0]))
        with pytest.raises(ValueError, match="expects 4 bytes"):
            DPT14056.decode(bytes([0, 0, 0, 0, 0]))

    def test_nan_and_infinity_round_trip(self) -> None:
        # Unlike DPT 9.x, plain IEEE 754 handles these natively -- not
        # rejected, matching xknx's DPT4ByteFloat behaviour.
        assert DPT14056.decode(DPT14056.encode(float("inf"))) == float("inf")
        assert math.isnan(DPT14056.decode(DPT14056.encode(float("nan"))))

    def test_payload_length_is_four(self) -> None:
        assert DPT14056.payload_length == 4

    @given(st.floats(width=32, allow_nan=False, allow_infinity=False))
    def test_round_trip_exact_for_float32_values(self, value: float) -> None:
        # hypothesis' width=32 strategy only generates values exactly
        # representable in float32, so the round-trip is exact -- no
        # precision-loss tolerance needed.
        assert DPT14056.decode(DPT14056.encode(value)) == value
