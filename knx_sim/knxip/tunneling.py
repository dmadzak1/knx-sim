"""KNXnet/IP tunneling frames (M5, F-IP-3): CONNECT, CONNECTIONSTATE,
DISCONNECT, and TUNNELLING request/response pairs, plus their small CRI/CRD
sub-structures.

Scope is deliberately narrow, matching the rest of this project: only Basic
CRI/CRD (4 bytes each) for a plain data-link-layer tunnel connection --
confirmed (by reading xknx/io/tunnel.py and request_response/connect.py)
that this is exactly what xknx's default UDP tunnel client sends. Extended
CRI/CRD (KNXnet/IP Tunnelling v2, client-requested individual addresses)
are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip._wire import unwrap_frame, wrap_frame
from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.header import ServiceType
from knx_sim.knxip.hpai import HPAI, HPAI_LENGTH

_CRI_LENGTH = 4
_CRD_LENGTH = 4
_CONNECT_RESPONSE_FIXED_LENGTH = 2  # channel id + status, before HPAI/CRD
_STATUS_LENGTH = 2  # channel id + status, no HPAI (ConnectionState/Disconnect responses)
_CHANNEL_HEADER_LENGTH = 2  # channel id + reserved byte (ConnectionState/Disconnect requests)
_TUNNELLING_HEADER_LENGTH = 4  # length byte + channel id + sequence + reserved
_TUNNELLING_ACK_LENGTH = 4


class ErrorCode(Enum):
    """KNXnet/IP status/error codes this simulator uses or must recognize."""

    E_NO_ERROR = 0x00
    E_SEQUENCE_NUMBER = 0x04
    E_CONNECTION_ID = 0x21
    E_CONNECTION_TYPE = 0x22
    E_CONNECTION_OPTION = 0x23
    E_NO_MORE_CONNECTIONS = 0x24
    E_DATA_CONNECTION = 0x26
    E_TUNNELLING_LAYER = 0x29


class ConnectRequestType(Enum):
    TUNNEL_CONNECTION = 0x04


class TunnellingLayer(Enum):
    DATA_LINK_LAYER = 0x02


@dataclass(frozen=True)
class ConnectRequestInformation:
    """Basic CRI (4 bytes): connection_type + knx_layer + reserved."""

    connection_type: ConnectRequestType = ConnectRequestType.TUNNEL_CONNECTION
    knx_layer: TunnellingLayer = TunnellingLayer.DATA_LINK_LAYER

    def to_knx(self) -> bytes:
        return bytes([_CRI_LENGTH, self.connection_type.value, self.knx_layer.value, 0x00])

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectRequestInformation:
        if len(data) < _CRI_LENGTH:
            raise ParseError(f"CRI too short: {len(data)} bytes, need {_CRI_LENGTH}")
        if data[0] != _CRI_LENGTH:
            raise ParseError(
                f"Unsupported CRI length: {data[0]} (only Basic CRI, length 4, is supported)"
            )
        try:
            connection_type = ConnectRequestType(data[1])
        except ValueError:
            raise ParseError(f"Unsupported connection type: {data[1]:#04x}") from None
        try:
            knx_layer = TunnellingLayer(data[2])
        except ValueError:
            raise ParseError(f"Unsupported tunnelling layer: {data[2]:#04x}") from None
        return cls(connection_type=connection_type, knx_layer=knx_layer)


@dataclass(frozen=True)
class ConnectResponseData:
    """Basic CRD (4 bytes): request_type + the individual address we assigned."""

    individual_address: IndividualAddress
    request_type: ConnectRequestType = ConnectRequestType.TUNNEL_CONNECTION

    def to_knx(self) -> bytes:
        return (
            bytes([_CRD_LENGTH, self.request_type.value]) + self.individual_address.to_knx()
        )

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectResponseData:
        if len(data) < _CRD_LENGTH:
            raise ParseError(f"CRD too short: {len(data)} bytes, need {_CRD_LENGTH}")
        if data[0] != _CRD_LENGTH:
            raise ParseError(
                f"Unsupported CRD length: {data[0]} (only Basic CRD, length 4, is supported)"
            )
        try:
            request_type = ConnectRequestType(data[1])
        except ValueError:
            raise ParseError(f"Unsupported connection type: {data[1]:#04x}") from None
        individual_address = IndividualAddress.from_knx(data[2:4])
        return cls(individual_address=individual_address, request_type=request_type)


@dataclass(frozen=True)
class ConnectRequest:
    control_endpoint: HPAI
    data_endpoint: HPAI
    cri: ConnectRequestInformation = ConnectRequestInformation()

    def to_knx(self) -> bytes:
        body = self.control_endpoint.to_knx() + self.data_endpoint.to_knx() + self.cri.to_knx()
        return wrap_frame(ServiceType.CONNECT_REQUEST, body)

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectRequest:
        body = unwrap_frame(data, ServiceType.CONNECT_REQUEST)
        control_endpoint = HPAI.from_knx(body)
        data_endpoint = HPAI.from_knx(body[HPAI_LENGTH:])
        cri = ConnectRequestInformation.from_knx(body[HPAI_LENGTH * 2 :])
        return cls(control_endpoint=control_endpoint, data_endpoint=data_endpoint, cri=cri)


@dataclass(frozen=True)
class ConnectResponse:
    """status_code == E_NO_ERROR is the only case with a data_endpoint/crd;
    other status codes carry just the channel id (0 for a rejected request
    that never got a channel) and status."""

    communication_channel_id: int
    status_code: ErrorCode
    data_endpoint: HPAI = HPAI()
    crd: ConnectResponseData | None = None

    def to_knx(self) -> bytes:
        body = bytes([self.communication_channel_id, self.status_code.value])
        if self.status_code is ErrorCode.E_NO_ERROR:
            assert self.crd is not None, "crd is required when status_code is E_NO_ERROR"
            body += self.data_endpoint.to_knx() + self.crd.to_knx()
        return wrap_frame(ServiceType.CONNECT_RESPONSE, body)

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectResponse:
        body = unwrap_frame(data, ServiceType.CONNECT_RESPONSE)
        if len(body) < _CONNECT_RESPONSE_FIXED_LENGTH:
            raise ParseError(f"ConnectResponse too short: {len(body)} bytes")
        communication_channel_id = body[0]
        try:
            status_code = ErrorCode(body[1])
        except ValueError:
            raise ParseError(f"Unsupported status code: {body[1]:#04x}") from None
        if status_code is not ErrorCode.E_NO_ERROR:
            return cls(communication_channel_id=communication_channel_id, status_code=status_code)
        data_endpoint = HPAI.from_knx(body[_CONNECT_RESPONSE_FIXED_LENGTH:])
        crd = ConnectResponseData.from_knx(body[_CONNECT_RESPONSE_FIXED_LENGTH + HPAI_LENGTH :])
        return cls(
            communication_channel_id=communication_channel_id,
            status_code=status_code,
            data_endpoint=data_endpoint,
            crd=crd,
        )


@dataclass(frozen=True)
class ConnectionStateRequest:
    communication_channel_id: int
    control_endpoint: HPAI

    def to_knx(self) -> bytes:
        body = bytes([self.communication_channel_id, 0x00]) + self.control_endpoint.to_knx()
        return wrap_frame(ServiceType.CONNECTIONSTATE_REQUEST, body)

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectionStateRequest:
        body = unwrap_frame(data, ServiceType.CONNECTIONSTATE_REQUEST)
        if len(body) < _CHANNEL_HEADER_LENGTH:
            raise ParseError(f"ConnectionStateRequest too short: {len(body)} bytes")
        control_endpoint = HPAI.from_knx(body[_CHANNEL_HEADER_LENGTH:])
        return cls(communication_channel_id=body[0], control_endpoint=control_endpoint)


@dataclass(frozen=True)
class ConnectionStateResponse:
    communication_channel_id: int
    status_code: ErrorCode = ErrorCode.E_NO_ERROR

    def to_knx(self) -> bytes:
        body = bytes([self.communication_channel_id, self.status_code.value])
        return wrap_frame(ServiceType.CONNECTIONSTATE_RESPONSE, body)

    @classmethod
    def from_knx(cls, data: bytes) -> ConnectionStateResponse:
        body = unwrap_frame(data, ServiceType.CONNECTIONSTATE_RESPONSE)
        if len(body) < _STATUS_LENGTH:
            raise ParseError(f"ConnectionStateResponse too short: {len(body)} bytes")
        try:
            status_code = ErrorCode(body[1])
        except ValueError:
            raise ParseError(f"Unsupported status code: {body[1]:#04x}") from None
        return cls(communication_channel_id=body[0], status_code=status_code)


@dataclass(frozen=True)
class DisconnectRequest:
    communication_channel_id: int
    control_endpoint: HPAI

    def to_knx(self) -> bytes:
        body = bytes([self.communication_channel_id, 0x00]) + self.control_endpoint.to_knx()
        return wrap_frame(ServiceType.DISCONNECT_REQUEST, body)

    @classmethod
    def from_knx(cls, data: bytes) -> DisconnectRequest:
        body = unwrap_frame(data, ServiceType.DISCONNECT_REQUEST)
        if len(body) < _CHANNEL_HEADER_LENGTH:
            raise ParseError(f"DisconnectRequest too short: {len(body)} bytes")
        control_endpoint = HPAI.from_knx(body[_CHANNEL_HEADER_LENGTH:])
        return cls(communication_channel_id=body[0], control_endpoint=control_endpoint)


@dataclass(frozen=True)
class DisconnectResponse:
    communication_channel_id: int
    status_code: ErrorCode = ErrorCode.E_NO_ERROR

    def to_knx(self) -> bytes:
        body = bytes([self.communication_channel_id, self.status_code.value])
        return wrap_frame(ServiceType.DISCONNECT_RESPONSE, body)

    @classmethod
    def from_knx(cls, data: bytes) -> DisconnectResponse:
        body = unwrap_frame(data, ServiceType.DISCONNECT_RESPONSE)
        if len(body) < _STATUS_LENGTH:
            raise ParseError(f"DisconnectResponse too short: {len(body)} bytes")
        try:
            status_code = ErrorCode(body[1])
        except ValueError:
            raise ParseError(f"Unsupported status code: {body[1]:#04x}") from None
        return cls(communication_channel_id=body[0], status_code=status_code)


@dataclass(frozen=True)
class TunnellingRequest:
    communication_channel_id: int
    sequence_counter: int
    raw_cemi: bytes

    def __post_init__(self) -> None:
        if not 0 <= self.communication_channel_id <= 255:
            raise ValueError(
                f"communication_channel_id must be 0..255, got {self.communication_channel_id}"
            )
        if not 0 <= self.sequence_counter <= 255:
            raise ValueError(f"sequence_counter must be 0..255, got {self.sequence_counter}")

    def to_knx(self) -> bytes:
        body = (
            bytes(
                [
                    _TUNNELLING_HEADER_LENGTH,
                    self.communication_channel_id,
                    self.sequence_counter,
                    0x00,
                ]
            )
            + self.raw_cemi
        )
        return wrap_frame(ServiceType.TUNNELLING_REQUEST, body)

    @classmethod
    def from_knx(cls, data: bytes) -> TunnellingRequest:
        body = unwrap_frame(data, ServiceType.TUNNELLING_REQUEST)
        if len(body) < _TUNNELLING_HEADER_LENGTH:
            raise ParseError(f"TunnellingRequest too short: {len(body)} bytes")
        if body[0] != _TUNNELLING_HEADER_LENGTH:
            raise ParseError(f"Unexpected TunnellingRequest header length: {body[0]}")
        return cls(
            communication_channel_id=body[1],
            sequence_counter=body[2],
            raw_cemi=bytes(body[_TUNNELLING_HEADER_LENGTH:]),
        )


@dataclass(frozen=True)
class TunnellingAck:
    communication_channel_id: int
    sequence_counter: int
    status_code: ErrorCode = ErrorCode.E_NO_ERROR

    def __post_init__(self) -> None:
        if not 0 <= self.communication_channel_id <= 255:
            raise ValueError(
                f"communication_channel_id must be 0..255, got {self.communication_channel_id}"
            )
        if not 0 <= self.sequence_counter <= 255:
            raise ValueError(f"sequence_counter must be 0..255, got {self.sequence_counter}")

    def to_knx(self) -> bytes:
        body = bytes(
            [
                _TUNNELLING_ACK_LENGTH,
                self.communication_channel_id,
                self.sequence_counter,
                self.status_code.value,
            ]
        )
        return wrap_frame(ServiceType.TUNNELLING_ACK, body)

    @classmethod
    def from_knx(cls, data: bytes) -> TunnellingAck:
        body = unwrap_frame(data, ServiceType.TUNNELLING_ACK)
        if len(body) < _TUNNELLING_ACK_LENGTH:
            raise ParseError(f"TunnellingAck too short: {len(body)} bytes")
        if body[0] != _TUNNELLING_ACK_LENGTH:
            raise ParseError(f"Unexpected TunnellingAck length: {body[0]}")
        try:
            status_code = ErrorCode(body[3])
        except ValueError:
            raise ParseError(f"Unsupported status code: {body[3]:#04x}") from None
        return cls(
            communication_channel_id=body[1], sequence_counter=body[2], status_code=status_code
        )
