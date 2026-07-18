from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt9 import DPT9001

# Hand-derived in docs/notes/dpt9.md: 21.5 -> E=1, M=1075; -10.0 -> E=0, M=-1000;
# 100.0 -> E=3, M=1250.
KNOWN_PAIRS = [
    (0.0, bytes([0x00, 0x00])),
    (21.5, bytes([0x0C, 0x33])),
    (-10.0, bytes([0x84, 0x18])),
    (100.0, bytes([0x1C, 0xE2])),
]


class TestDPT9001:
    @pytest.mark.parametrize(("value", "expected"), KNOWN_PAIRS)
    def test_encode_known_pairs(self, value: float, expected: bytes) -> None:
        assert DPT9001.encode(value) == expected

    @pytest.mark.parametrize(("value", "encoded"), KNOWN_PAIRS)
    def test_decode_known_pairs(self, value: float, encoded: bytes) -> None:
        assert DPT9001.decode(encoded) == value

    def test_encode_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="expects"):
            DPT9001.encode(670760.97)
        with pytest.raises(ValueError, match="expects"):
            DPT9001.encode(-671088.65)

    def test_encode_rejects_nan_and_infinity(self) -> None:
        with pytest.raises(ValueError, match="NaN/Infinity"):
            DPT9001.encode(float("nan"))
        with pytest.raises(ValueError, match="NaN/Infinity"):
            DPT9001.encode(float("inf"))

    def test_encode_rejects_non_number(self) -> None:
        with pytest.raises(TypeError):
            DPT9001.encode("21.5")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DPT9001.encode(True)

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 2 bytes"):
            DPT9001.decode(bytes([0x00]))
        with pytest.raises(ValueError, match="expects 2 bytes"):
            DPT9001.decode(bytes([0x00, 0x00, 0x00]))

    def test_payload_length_is_two(self) -> None:
        assert DPT9001.payload_length == 2

    @given(
        st.floats(
            min_value=-671088.64, max_value=670760.96, allow_nan=False, allow_infinity=False
        )
    )
    def test_round_trip_within_resolution(self, value: float) -> None:
        encoded = DPT9001.encode(value)
        # Resolution depends on the exponent this particular value picked;
        # error after rounding is at most half a step at that resolution.
        exponent = (encoded[0] >> 3) & 0x0F
        resolution = 0.01 * (2**exponent)
        decoded = DPT9001.decode(encoded)
        assert abs(decoded - value) <= resolution / 2 + 1e-9
