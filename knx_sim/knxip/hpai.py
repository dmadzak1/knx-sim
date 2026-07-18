"""HPAI: Host Protocol Address Information.

An 8-byte (IP address, port, host protocol) triple used throughout
KNXnet/IP to say "send responses here". Layout: length(1)=0x08,
host_protocol(1), ip(4), port(2, big endian).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum

from knx_sim.knxip.errors import ParseError

HPAI_LENGTH = 0x08


class HostProtocol(Enum):
    IPV4_UDP = 0x01


@dataclass(frozen=True)
class HPAI:
    ip_addr: str = "0.0.0.0"
    port: int = 0
    protocol: HostProtocol = HostProtocol.IPV4_UDP

    def __post_init__(self) -> None:
        ipaddress.IPv4Address(self.ip_addr)  # raises ValueError if malformed
        if not 0 <= self.port <= 65535:
            raise ValueError(f"HPAI port must be 0..65535, got {self.port}")

    @property
    def route_back(self) -> bool:
        """True if this HPAI means "reply to wherever this packet actually
        came from" instead of a self-declared address (NAT traversal)."""
        return self.ip_addr == "0.0.0.0"

    def to_knx(self) -> bytes:
        ip_bytes = ipaddress.IPv4Address(self.ip_addr).packed
        return (
            bytes([HPAI_LENGTH, self.protocol.value]) + ip_bytes + self.port.to_bytes(2, "big")
        )

    @classmethod
    def from_knx(cls, data: bytes) -> HPAI:
        if len(data) < HPAI_LENGTH:
            raise ParseError(f"HPAI too short: {len(data)} bytes, need at least 8")
        if data[0] != HPAI_LENGTH:
            raise ParseError(f"Unexpected HPAI length byte: {data[0]:#04x}, expected 0x08")
        try:
            protocol = HostProtocol(data[1])
        except ValueError:
            raise ParseError(f"Unsupported host protocol code: {data[1]:#04x}") from None
        ip_addr = str(ipaddress.IPv4Address(bytes(data[2:6])))
        port = int.from_bytes(data[6:8], "big")
        return cls(ip_addr=ip_addr, port=port, protocol=protocol)
