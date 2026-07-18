from __future__ import annotations

import pytest

from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.header import Header, ServiceType


class TestHeader:
    def test_to_knx_known_bytes(self) -> None:
        header = Header(service_type=ServiceType.SEARCH_REQUEST, total_length=14)
        assert header.to_knx() == bytes([0x06, 0x10, 0x02, 0x01, 0x00, 0x0E])

    def test_round_trip(self) -> None:
        header = Header(service_type=ServiceType.ROUTING_INDICATION, total_length=17)
        assert Header.from_knx(header.to_knx()) == header

    def test_rejects_total_length_below_header_length(self) -> None:
        with pytest.raises(ValueError, match="total_length must be at least 6"):
            Header(service_type=ServiceType.SEARCH_REQUEST, total_length=3)

    def test_from_knx_rejects_too_short(self) -> None:
        with pytest.raises(ParseError, match="too short"):
            Header.from_knx(bytes([0x06, 0x10, 0x02]))

    def test_from_knx_rejects_wrong_header_length_byte(self) -> None:
        with pytest.raises(ParseError, match="Unexpected header length byte"):
            Header.from_knx(bytes([0x07, 0x10, 0x02, 0x01, 0x00, 0x0E]))

    def test_from_knx_rejects_wrong_protocol_version(self) -> None:
        with pytest.raises(ParseError, match="Unsupported protocol version"):
            Header.from_knx(bytes([0x06, 0x11, 0x02, 0x01, 0x00, 0x0E]))

    def test_from_knx_rejects_unknown_service_type(self) -> None:
        with pytest.raises(ParseError, match="Unsupported KNXnet/IP service type"):
            Header.from_knx(bytes([0x06, 0x10, 0xFF, 0xFF, 0x00, 0x0E]))
