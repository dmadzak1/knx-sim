from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt5 import DPT5001, DPT5004


class TestDPT5001:
    def test_encode_zero(self) -> None:
        assert DPT5001.encode(0.0) == bytes([0])

    def test_encode_hundred(self) -> None:
        assert DPT5001.encode(100.0) == bytes([255])

    def test_encode_fifty_rounds_to_nearest(self) -> None:
        # 50% * 255 / 100 = 127.5, rounds to 128.
        assert DPT5001.encode(50.0) == bytes([128])

    def test_decode_zero(self) -> None:
        assert DPT5001.decode(bytes([0])) == 0.0

    def test_decode_max(self) -> None:
        assert DPT5001.decode(bytes([255])) == 100.0

    def test_decode_mid_byte(self) -> None:
        assert DPT5001.decode(bytes([128])) == pytest.approx(50.196, abs=0.001)

    def test_encode_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="expects 0..100"):
            DPT5001.encode(-0.1)
        with pytest.raises(ValueError, match="expects 0..100"):
            DPT5001.encode(100.1)

    def test_encode_rejects_non_number(self) -> None:
        with pytest.raises(TypeError):
            DPT5001.encode("50")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DPT5001.encode(True)

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT5001.decode(b"")
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT5001.decode(bytes([0, 1]))

    def test_payload_length_is_one(self) -> None:
        assert DPT5001.payload_length == 1

    @given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    def test_round_trip_within_resolution(self, value: float) -> None:
        # Resolution is 100/255 ~= 0.392%; rounding introduces at most half
        # a step of error.
        assert abs(DPT5001.decode(DPT5001.encode(value)) - value) <= 0.2


class TestDPT5004:
    def test_encode_decode_identity(self) -> None:
        for value in (0, 1, 128, 255):
            assert DPT5004.decode(DPT5004.encode(value)) == value

    def test_encode_known_bytes(self) -> None:
        assert DPT5004.encode(0) == bytes([0])
        assert DPT5004.encode(255) == bytes([255])

    def test_encode_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="expects 0..255"):
            DPT5004.encode(-1)
        with pytest.raises(ValueError, match="expects 0..255"):
            DPT5004.encode(256)

    def test_encode_rejects_non_int(self) -> None:
        with pytest.raises(TypeError):
            DPT5004.encode(1.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DPT5004.encode(True)

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT5004.decode(b"")
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT5004.decode(bytes([0, 1]))

    def test_payload_length_is_one(self) -> None:
        assert DPT5004.payload_length == 1

    @given(st.integers(min_value=0, max_value=255))
    def test_round_trip_exact(self, value: int) -> None:
        # No scaling involved, so this round-trips exactly.
        assert DPT5004.decode(DPT5004.encode(value)) == value
