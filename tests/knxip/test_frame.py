from __future__ import annotations

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import MessageCode, Service, Telegram, build_cemi
from knx_sim.knxip.dib import (
    DeviceInformationDIB,
    ServiceFamily,
    SupportedServiceFamiliesDIB,
    SupportedServiceFamily,
)
from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.frame import (
    DescriptionRequest,
    DescriptionResponse,
    RoutingIndication,
    SearchRequest,
    SearchResponse,
    parse_frame,
)
from knx_sim.knxip.hpai import HPAI

_DEVICE_INFO = DeviceInformationDIB(individual_address=IndividualAddress(15, 15, 0), name="knx-sim")
_SUPP_SVC = SupportedServiceFamiliesDIB(
    families=(
        SupportedServiceFamily(ServiceFamily.CORE, 1),
        SupportedServiceFamily(ServiceFamily.ROUTING, 1),
    )
)


class TestSearchRequest:
    def test_round_trip(self) -> None:
        frame = SearchRequest(discovery_endpoint=HPAI("192.168.1.5", 54321))
        assert SearchRequest.from_knx(frame.to_knx()) == frame

    def test_parse_frame_dispatches(self) -> None:
        frame = SearchRequest(discovery_endpoint=HPAI("192.168.1.5", 54321))
        assert parse_frame(frame.to_knx()) == frame


class TestSearchResponse:
    def test_round_trip(self) -> None:
        frame = SearchResponse(
            control_endpoint=HPAI("192.168.1.5", 3671),
            device_info=_DEVICE_INFO,
            supported_services=_SUPP_SVC,
        )
        assert SearchResponse.from_knx(frame.to_knx()) == frame

    def test_parse_frame_dispatches(self) -> None:
        frame = SearchResponse(
            control_endpoint=HPAI("192.168.1.5", 3671),
            device_info=_DEVICE_INFO,
            supported_services=_SUPP_SVC,
        )
        assert parse_frame(frame.to_knx()) == frame


class TestDescriptionRequest:
    def test_round_trip(self) -> None:
        frame = DescriptionRequest(control_endpoint=HPAI("192.168.1.5", 54321))
        assert DescriptionRequest.from_knx(frame.to_knx()) == frame


class TestDescriptionResponse:
    def test_round_trip(self) -> None:
        frame = DescriptionResponse(device_info=_DEVICE_INFO, supported_services=_SUPP_SVC)
        assert DescriptionResponse.from_knx(frame.to_knx()) == frame


class TestRoutingIndication:
    def test_round_trip(self) -> None:
        cemi = build_cemi(
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GroupAddress(1, 2, 3),
                service=Service.GROUP_WRITE,
                payload=1,
            ),
            MessageCode.L_DATA_IND,
        )
        frame = RoutingIndication(raw_cemi=cemi)
        assert RoutingIndication.from_knx(frame.to_knx()) == frame

    def test_raw_cemi_is_the_entire_body(self) -> None:
        frame = RoutingIndication(raw_cemi=bytes([1, 2, 3]))
        # header(6) + 3 body bytes
        assert frame.to_knx() == bytes([0x06, 0x10, 0x05, 0x30, 0x00, 0x09, 1, 2, 3])


class TestParseFrame:
    def test_wrong_service_type_raises(self) -> None:
        request_bytes = SearchRequest(discovery_endpoint=HPAI()).to_knx()
        with pytest.raises(ParseError, match="Expected SEARCH_RESPONSE"):
            SearchResponse.from_knx(request_bytes)

    def test_rejects_incomplete_frame(self) -> None:
        frame = SearchRequest(discovery_endpoint=HPAI()).to_knx()
        with pytest.raises(ParseError, match="Incomplete frame"):
            parse_frame(frame[:-2])
