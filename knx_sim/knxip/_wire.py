"""Shared header-wrap/unwrap helpers used by every KNXnet/IP frame type.

Package-internal: frame.py and tunneling.py both depend on this; it depends
on neither, avoiding a circular import between them.
"""

from __future__ import annotations

from knx_sim.knxip.errors import ParseError
from knx_sim.knxip.header import HEADER_LENGTH, Header, ServiceType


def wrap_frame(service_type: ServiceType, body: bytes) -> bytes:
    header = Header(service_type=service_type, total_length=HEADER_LENGTH + len(body))
    return header.to_knx() + body


def unwrap_frame(data: bytes, expected: ServiceType) -> bytes:
    header = Header.from_knx(data)
    if header.service_type is not expected:
        raise ParseError(f"Expected {expected.name}, got {header.service_type.name}")
    if len(data) < header.total_length:
        raise ParseError(
            f"Incomplete frame: header declares {header.total_length} bytes, got {len(data)}"
        )
    return data[HEADER_LENGTH : header.total_length]
