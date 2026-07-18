"""KNXnet/IP frames this simulator supports: discovery/routing (M4) plus
tunneling (M5, in knx_sim/knxip/tunneling.py) -- this module re-exports the
tunneling frame classes and holds the combined parse_frame() dispatcher so
callers have one entry point regardless of service type. A
ROUTING_INDICATION's body is just raw cEMI bytes -- no extra wrapping -- so
it slots directly onto knx_sim.cemi.build_cemi/parse_cemi.
"""

from __future__ import annotations

from dataclasses import dataclass

from knx_sim.knxip._wire import unwrap_frame, wrap_frame
from knx_sim.knxip.dib import DEVICE_INFO_LENGTH, DeviceInformationDIB, SupportedServiceFamiliesDIB
from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.header import Header, ServiceType
from knx_sim.knxip.hpai import HPAI, HPAI_LENGTH
from knx_sim.knxip.tunneling import (
    ConnectionStateRequest,
    ConnectionStateResponse,
    ConnectRequest,
    ConnectResponse,
    DisconnectRequest,
    DisconnectResponse,
    TunnellingAck,
    TunnellingRequest,
)


@dataclass(frozen=True)
class SearchRequest:
    discovery_endpoint: HPAI

    def to_knx(self) -> bytes:
        return wrap_frame(ServiceType.SEARCH_REQUEST, self.discovery_endpoint.to_knx())

    @classmethod
    def from_knx(cls, data: bytes) -> SearchRequest:
        body = unwrap_frame(data, ServiceType.SEARCH_REQUEST)
        return cls(discovery_endpoint=HPAI.from_knx(body))


@dataclass(frozen=True)
class SearchResponse:
    control_endpoint: HPAI
    device_info: DeviceInformationDIB
    supported_services: SupportedServiceFamiliesDIB

    def to_knx(self) -> bytes:
        body = (
            self.control_endpoint.to_knx()
            + self.device_info.to_knx()
            + self.supported_services.to_knx()
        )
        return wrap_frame(ServiceType.SEARCH_RESPONSE, body)

    @classmethod
    def from_knx(cls, data: bytes) -> SearchResponse:
        body = unwrap_frame(data, ServiceType.SEARCH_RESPONSE)
        control_endpoint = HPAI.from_knx(body)
        device_info = DeviceInformationDIB.from_knx(body[HPAI_LENGTH:])
        supported_services = SupportedServiceFamiliesDIB.from_knx(
            body[HPAI_LENGTH + DEVICE_INFO_LENGTH :]
        )
        return cls(
            control_endpoint=control_endpoint,
            device_info=device_info,
            supported_services=supported_services,
        )


@dataclass(frozen=True)
class DescriptionRequest:
    control_endpoint: HPAI

    def to_knx(self) -> bytes:
        return wrap_frame(ServiceType.DESCRIPTION_REQUEST, self.control_endpoint.to_knx())

    @classmethod
    def from_knx(cls, data: bytes) -> DescriptionRequest:
        body = unwrap_frame(data, ServiceType.DESCRIPTION_REQUEST)
        return cls(control_endpoint=HPAI.from_knx(body))


@dataclass(frozen=True)
class DescriptionResponse:
    device_info: DeviceInformationDIB
    supported_services: SupportedServiceFamiliesDIB

    def to_knx(self) -> bytes:
        body = self.device_info.to_knx() + self.supported_services.to_knx()
        return wrap_frame(ServiceType.DESCRIPTION_RESPONSE, body)

    @classmethod
    def from_knx(cls, data: bytes) -> DescriptionResponse:
        body = unwrap_frame(data, ServiceType.DESCRIPTION_RESPONSE)
        device_info = DeviceInformationDIB.from_knx(body)
        supported_services = SupportedServiceFamiliesDIB.from_knx(body[DEVICE_INFO_LENGTH:])
        return cls(device_info=device_info, supported_services=supported_services)


@dataclass(frozen=True)
class RoutingIndication:
    raw_cemi: bytes

    def to_knx(self) -> bytes:
        return wrap_frame(ServiceType.ROUTING_INDICATION, self.raw_cemi)

    @classmethod
    def from_knx(cls, data: bytes) -> RoutingIndication:
        body = unwrap_frame(data, ServiceType.ROUTING_INDICATION)
        return cls(raw_cemi=bytes(body))


AnyFrame = (
    SearchRequest
    | SearchResponse
    | DescriptionRequest
    | DescriptionResponse
    | RoutingIndication
    | ConnectRequest
    | ConnectResponse
    | ConnectionStateRequest
    | ConnectionStateResponse
    | DisconnectRequest
    | DisconnectResponse
    | TunnellingRequest
    | TunnellingAck
)

_FRAME_CLASSES: dict[ServiceType, type[AnyFrame]] = {
    ServiceType.SEARCH_REQUEST: SearchRequest,
    ServiceType.SEARCH_RESPONSE: SearchResponse,
    ServiceType.DESCRIPTION_REQUEST: DescriptionRequest,
    ServiceType.DESCRIPTION_RESPONSE: DescriptionResponse,
    ServiceType.ROUTING_INDICATION: RoutingIndication,
    ServiceType.CONNECT_REQUEST: ConnectRequest,
    ServiceType.CONNECT_RESPONSE: ConnectResponse,
    ServiceType.CONNECTIONSTATE_REQUEST: ConnectionStateRequest,
    ServiceType.CONNECTIONSTATE_RESPONSE: ConnectionStateResponse,
    ServiceType.DISCONNECT_REQUEST: DisconnectRequest,
    ServiceType.DISCONNECT_RESPONSE: DisconnectResponse,
    ServiceType.TUNNELLING_REQUEST: TunnellingRequest,
    ServiceType.TUNNELLING_ACK: TunnellingAck,
}


def parse_frame(data: bytes) -> AnyFrame:
    """Parse any supported KNXnet/IP frame, dispatching on its service type."""
    header = Header.from_knx(data)
    try:
        frame_cls = _FRAME_CLASSES[header.service_type]
    except KeyError:
        raise ParseError(
            f"Unsupported KNXnet/IP service type: {header.service_type.name}"
        ) from None
    return frame_cls.from_knx(data)
