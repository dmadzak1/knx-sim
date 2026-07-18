from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.hpai import HPAI, HostProtocol


class TestHPAI:
    def test_to_knx_known_bytes(self) -> None:
        hpai = HPAI("192.168.1.10", 3671)
        assert hpai.to_knx() == bytes([0x08, 0x01, 192, 168, 1, 10, 0x0E, 0x57])

    def test_round_trip(self) -> None:
        hpai = HPAI("10.0.0.1", 12345)
        assert HPAI.from_knx(hpai.to_knx()) == hpai

    def test_default_is_route_back(self) -> None:
        assert HPAI().route_back is True

    def test_non_zero_address_is_not_route_back(self) -> None:
        assert HPAI("192.168.1.10", 3671).route_back is False

    def test_rejects_invalid_ip(self) -> None:
        with pytest.raises(ValueError):
            HPAI("not-an-ip", 0)

    def test_rejects_port_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="port must be 0..65535"):
            HPAI("0.0.0.0", 65536)

    def test_from_knx_rejects_too_short(self) -> None:
        with pytest.raises(ParseError, match="too short"):
            HPAI.from_knx(bytes([0x08, 0x01, 1, 2, 3]))

    def test_from_knx_rejects_wrong_length_byte(self) -> None:
        with pytest.raises(ParseError, match="Unexpected HPAI length byte"):
            HPAI.from_knx(bytes([0x09, 0x01, 1, 2, 3, 4, 0, 0]))

    def test_from_knx_rejects_unsupported_protocol(self) -> None:
        with pytest.raises(ParseError, match="Unsupported host protocol code"):
            HPAI.from_knx(bytes([0x08, 0xFF, 1, 2, 3, 4, 0, 0]))

    @given(
        st.integers(0, 255),
        st.integers(0, 255),
        st.integers(0, 255),
        st.integers(0, 255),
        st.integers(0, 65535),
    )
    def test_round_trip_hypothesis(self, a: int, b: int, c: int, d: int, port: int) -> None:
        hpai = HPAI(f"{a}.{b}.{c}.{d}", port, HostProtocol.IPV4_UDP)
        assert HPAI.from_knx(hpai.to_knx()) == hpai
