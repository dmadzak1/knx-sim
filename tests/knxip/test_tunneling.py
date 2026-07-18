from __future__ import annotations

import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.frame import parse_frame
from knx_sim.knxip.hpai import HPAI
from knx_sim.knxip.tunneling import (
    ConnectionStateRequest,
    ConnectionStateResponse,
    ConnectRequest,
    ConnectRequestInformation,
    ConnectRequestType,
    ConnectResponse,
    ConnectResponseData,
    DisconnectRequest,
    DisconnectResponse,
    ErrorCode,
    TunnellingAck,
    TunnellingLayer,
    TunnellingRequest,
)

_CLIENT_HPAI = HPAI("192.168.1.5", 54321)
_SERVER_HPAI = HPAI("192.168.1.10", 3671)
_ASSIGNED_IA = IndividualAddress(15, 15, 1)


class TestConnectRequestInformation:
    def test_round_trip(self) -> None:
        cri = ConnectRequestInformation()
        assert ConnectRequestInformation.from_knx(cri.to_knx()) == cri

    def test_to_knx_known_bytes(self) -> None:
        cri = ConnectRequestInformation(
            connection_type=ConnectRequestType.TUNNEL_CONNECTION,
            knx_layer=TunnellingLayer.DATA_LINK_LAYER,
        )
        assert cri.to_knx() == bytes([0x04, 0x04, 0x02, 0x00])

    def test_rejects_unsupported_length(self) -> None:
        with pytest.raises(ParseError, match="only Basic CRI"):
            ConnectRequestInformation.from_knx(bytes([0x06, 0x04, 0x02, 0x00, 0x0F, 0x01]))

    def test_rejects_unsupported_connection_type(self) -> None:
        with pytest.raises(ParseError, match="Unsupported connection type"):
            ConnectRequestInformation.from_knx(bytes([0x04, 0x03, 0x02, 0x00]))

    def test_rejects_unsupported_layer(self) -> None:
        with pytest.raises(ParseError, match="Unsupported tunnelling layer"):
            ConnectRequestInformation.from_knx(bytes([0x04, 0x04, 0x99, 0x00]))


class TestConnectResponseData:
    def test_round_trip(self) -> None:
        crd = ConnectResponseData(individual_address=_ASSIGNED_IA)
        assert ConnectResponseData.from_knx(crd.to_knx()) == crd

    def test_to_knx_known_bytes(self) -> None:
        crd = ConnectResponseData(individual_address=IndividualAddress(15, 15, 1))
        assert crd.to_knx() == bytes([0x04, 0x04, 0xFF, 0x01])


class TestConnectRequest:
    def test_round_trip(self) -> None:
        frame = ConnectRequest(control_endpoint=_CLIENT_HPAI, data_endpoint=_CLIENT_HPAI)
        assert ConnectRequest.from_knx(frame.to_knx()) == frame

    def test_parse_frame_dispatches(self) -> None:
        frame = ConnectRequest(control_endpoint=_CLIENT_HPAI, data_endpoint=_CLIENT_HPAI)
        assert parse_frame(frame.to_knx()) == frame


class TestConnectResponse:
    def test_round_trip_success(self) -> None:
        frame = ConnectResponse(
            communication_channel_id=1,
            status_code=ErrorCode.E_NO_ERROR,
            data_endpoint=_SERVER_HPAI,
            crd=ConnectResponseData(individual_address=_ASSIGNED_IA),
        )
        assert ConnectResponse.from_knx(frame.to_knx()) == frame

    def test_round_trip_error_has_no_hpai_or_crd(self) -> None:
        frame = ConnectResponse(
            communication_channel_id=0, status_code=ErrorCode.E_NO_MORE_CONNECTIONS
        )
        raw = frame.to_knx()
        # header(6) + channel(1) + status(1), no HPAI/CRD appended
        assert len(raw) == 8
        assert ConnectResponse.from_knx(raw) == frame

    def test_to_knx_requires_crd_on_success(self) -> None:
        frame = ConnectResponse(communication_channel_id=1, status_code=ErrorCode.E_NO_ERROR)
        with pytest.raises(AssertionError):
            frame.to_knx()


class TestConnectionStateRequest:
    def test_round_trip(self) -> None:
        frame = ConnectionStateRequest(communication_channel_id=1, control_endpoint=_CLIENT_HPAI)
        assert ConnectionStateRequest.from_knx(frame.to_knx()) == frame


class TestConnectionStateResponse:
    def test_round_trip(self) -> None:
        frame = ConnectionStateResponse(communication_channel_id=1)
        assert ConnectionStateResponse.from_knx(frame.to_knx()) == frame

    def test_round_trip_error(self) -> None:
        frame = ConnectionStateResponse(
            communication_channel_id=1, status_code=ErrorCode.E_CONNECTION_ID
        )
        assert ConnectionStateResponse.from_knx(frame.to_knx()) == frame


class TestDisconnectRequest:
    def test_round_trip(self) -> None:
        frame = DisconnectRequest(communication_channel_id=1, control_endpoint=_CLIENT_HPAI)
        assert DisconnectRequest.from_knx(frame.to_knx()) == frame


class TestDisconnectResponse:
    def test_round_trip(self) -> None:
        frame = DisconnectResponse(communication_channel_id=1)
        assert DisconnectResponse.from_knx(frame.to_knx()) == frame


class TestTunnellingRequest:
    def test_round_trip(self) -> None:
        frame = TunnellingRequest(
            communication_channel_id=1, sequence_counter=5, raw_cemi=bytes([0x29, 0x00])
        )
        assert TunnellingRequest.from_knx(frame.to_knx()) == frame

    def test_to_knx_known_bytes(self) -> None:
        frame = TunnellingRequest(
            communication_channel_id=1, sequence_counter=0, raw_cemi=bytes([0xAA, 0xBB])
        )
        body = frame.to_knx()[6:]  # skip the 6-byte KNXnet/IP header
        assert body == bytes([0x04, 0x01, 0x00, 0x00, 0xAA, 0xBB])

    @pytest.mark.parametrize("bad_channel", [-1, 256])
    def test_rejects_channel_id_out_of_range(self, bad_channel: int) -> None:
        with pytest.raises(ValueError, match="communication_channel_id must be 0..255"):
            TunnellingRequest(
                communication_channel_id=bad_channel, sequence_counter=0, raw_cemi=b""
            )

    @pytest.mark.parametrize("bad_seq", [-1, 256])
    def test_rejects_sequence_counter_out_of_range(self, bad_seq: int) -> None:
        with pytest.raises(ValueError, match="sequence_counter must be 0..255"):
            TunnellingRequest(communication_channel_id=1, sequence_counter=bad_seq, raw_cemi=b"")


class TestTunnellingAck:
    def test_round_trip(self) -> None:
        frame = TunnellingAck(communication_channel_id=1, sequence_counter=5)
        assert TunnellingAck.from_knx(frame.to_knx()) == frame

    def test_round_trip_error_status(self) -> None:
        frame = TunnellingAck(
            communication_channel_id=1,
            sequence_counter=5,
            status_code=ErrorCode.E_SEQUENCE_NUMBER,
        )
        assert TunnellingAck.from_knx(frame.to_knx()) == frame

    def test_to_knx_known_bytes(self) -> None:
        frame = TunnellingAck(communication_channel_id=1, sequence_counter=5)
        body = frame.to_knx()[6:]
        assert body == bytes([0x04, 0x01, 0x05, 0x00])
