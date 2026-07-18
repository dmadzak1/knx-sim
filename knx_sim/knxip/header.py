"""The 6-byte KNXnet/IP header that precedes every frame's body.

Layout: header_length(1)=0x06, protocol_version(1)=0x10, service_type(2, big
endian), total_length(2, big endian, header+body combined).

ServiceType is deliberately narrow -- only the services M4 implements
(discovery + routing). Tunneling service types (CONNECT_REQUEST, etc.) are
added in M5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from knx_sim.knxip.errors import ParseError

HEADER_LENGTH = 0x06
_PROTOCOL_VERSION = 0x10


class ServiceType(Enum):
    SEARCH_REQUEST = 0x0201
    SEARCH_RESPONSE = 0x0202
    DESCRIPTION_REQUEST = 0x0203
    DESCRIPTION_RESPONSE = 0x0204
    ROUTING_INDICATION = 0x0530


@dataclass(frozen=True)
class Header:
    service_type: ServiceType
    total_length: int

    def __post_init__(self) -> None:
        if self.total_length < HEADER_LENGTH:
            raise ValueError(
                f"total_length must be at least {HEADER_LENGTH}, got {self.total_length}"
            )

    def to_knx(self) -> bytes:
        return (
            bytes([HEADER_LENGTH, _PROTOCOL_VERSION])
            + self.service_type.value.to_bytes(2, "big")
            + self.total_length.to_bytes(2, "big")
        )

    @classmethod
    def from_knx(cls, data: bytes) -> Header:
        if len(data) < HEADER_LENGTH:
            raise ParseError(f"KNXnet/IP header too short: {len(data)} bytes, need at least 6")
        if data[0] != HEADER_LENGTH:
            raise ParseError(f"Unexpected header length byte: {data[0]:#04x}, expected 0x06")
        if data[1] != _PROTOCOL_VERSION:
            raise ParseError(f"Unsupported protocol version: {data[1]:#04x}, expected 0x10")
        try:
            service_type = ServiceType(int.from_bytes(data[2:4], "big"))
        except ValueError:
            raise ParseError(f"Unsupported KNXnet/IP service type: {data[2:4].hex()}") from None
        total_length = int.from_bytes(data[4:6], "big")
        return cls(service_type=service_type, total_length=total_length)
