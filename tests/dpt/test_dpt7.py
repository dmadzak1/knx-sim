from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt7 import DPT7001


class TestDPT7001:
    def test_encode_known_values(self) -> None:
        assert DPT7001.encode(0) == bytes([0x00, 0x00])
        assert DPT7001.encode(1) == bytes([0x00, 0x01])
        assert DPT7001.encode(256) == bytes([0x01, 0x00])
        assert DPT7001.encode(65535) == bytes([0xFF, 0xFF])

    def test_decode_known_values(self) -> None:
        assert DPT7001.decode(bytes([0x00, 0x00])) == 0
        assert DPT7001.decode(bytes([0x00, 0x01])) == 1
        assert DPT7001.decode(bytes([0x01, 0x00])) == 256
        assert DPT7001.decode(bytes([0xFF, 0xFF])) == 65535

    def test_encode_rejects_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="expects 0..65535"):
            DPT7001.encode(-1)
        with pytest.raises(ValueError, match="expects 0..65535"):
            DPT7001.encode(65536)

    def test_encode_rejects_non_int(self) -> None:
        with pytest.raises(TypeError):
            DPT7001.encode(1.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            DPT7001.encode(True)

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 2 bytes"):
            DPT7001.decode(bytes([0]))
        with pytest.raises(ValueError, match="expects 2 bytes"):
            DPT7001.decode(bytes([0, 0, 0]))

    def test_payload_length_is_two(self) -> None:
        assert DPT7001.payload_length == 2

    @given(st.integers(min_value=0, max_value=65535))
    def test_round_trip_exact(self, value: int) -> None:
        assert DPT7001.decode(DPT7001.encode(value)) == value
