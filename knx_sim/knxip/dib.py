"""DIB (Description Information Block): self-description structures a
KNXnet/IP server includes in SEARCH_RESPONSE and DESCRIPTION_RESPONSE.

Real KNXnet/IP servers can emit an open-ended set of DIB types, so xknx
models them polymorphically (a DIB base class + a determine_dib() type
dispatcher). We only ever emit exactly two, always together -- device info
and supported services -- since we're the one producing responses, not
consuming arbitrary external servers'. So SearchResponse/DescriptionResponse
(frame.py) just hold these two DIBs as named fields instead of a generic
list; the added polymorphism wouldn't buy us anything in this direction.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import Enum

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip.errors import ParseError

DEVICE_INFO_LENGTH = 54


class DIBTypeCode(Enum):
    DEVICE_INFO = 0x01
    SUPP_SVC_FAMILIES = 0x02


class KNXMedium(Enum):
    TP1 = 0x02
    PL110 = 0x04
    RF = 0x10
    KNX_IP = 0x20


class ServiceFamily(Enum):
    CORE = 0x02
    DEVICE_MANAGEMENT = 0x03
    TUNNELING = 0x04
    ROUTING = 0x05


@dataclass(frozen=True)
class DeviceInformationDIB:
    """54 fixed bytes: length, type code, medium, programming mode,
    individual address, project/installation id (unused, always 0),
    serial number, multicast address, MAC address, a 30-byte latin-1 name."""

    individual_address: IndividualAddress
    name: str
    multicast_address: str = "224.0.23.12"
    serial_number: bytes = b"\x00" * 6
    mac_address: bytes = b"\x00" * 6
    knx_medium: KNXMedium = KNXMedium.TP1
    programming_mode: bool = False

    def __post_init__(self) -> None:
        if len(self.serial_number) != 6:
            raise ValueError(f"serial_number must be 6 bytes, got {len(self.serial_number)}")
        if len(self.mac_address) != 6:
            raise ValueError(f"mac_address must be 6 bytes, got {len(self.mac_address)}")
        if len(self.name.encode("latin-1", errors="replace")) > 30:
            raise ValueError(f"name must fit in 30 latin-1 bytes: {self.name!r}")
        ipaddress.IPv4Address(self.multicast_address)  # raises ValueError if malformed

    def to_knx(self) -> bytes:
        name_bytes = self.name.encode("latin-1", errors="replace").ljust(30, b"\x00")
        return (
            bytes(
                [
                    DEVICE_INFO_LENGTH,
                    DIBTypeCode.DEVICE_INFO.value,
                    self.knx_medium.value,
                    int(self.programming_mode),
                ]
            )
            + self.individual_address.to_knx()
            + bytes(2)  # project/installation identifier: unused, always 0
            + self.serial_number
            + ipaddress.IPv4Address(self.multicast_address).packed
            + self.mac_address
            + name_bytes
        )

    @classmethod
    def from_knx(cls, data: bytes) -> DeviceInformationDIB:
        if len(data) < DEVICE_INFO_LENGTH:
            raise ParseError(
                f"DeviceInformationDIB too short: {len(data)} bytes, need {DEVICE_INFO_LENGTH}"
            )
        if data[0] != DEVICE_INFO_LENGTH:
            raise ParseError(f"Unexpected DIB length byte: {data[0]:#04x}, expected 54")
        try:
            type_code = DIBTypeCode(data[1])
        except ValueError:
            raise ParseError(f"Unsupported DIB type code: {data[1]:#04x}") from None
        if type_code is not DIBTypeCode.DEVICE_INFO:
            raise ParseError(f"Expected DEVICE_INFO DIB, got {type_code.name}")
        try:
            knx_medium = KNXMedium(data[2])
        except ValueError:
            raise ParseError(f"Unsupported KNX medium: {data[2]:#04x}") from None
        programming_mode = bool(data[3])
        individual_address = IndividualAddress.from_knx(data[4:6])
        serial_number = bytes(data[8:14])
        multicast_address = str(ipaddress.IPv4Address(bytes(data[14:18])))
        mac_address = bytes(data[18:24])
        name = data[24:54].decode("latin-1", errors="replace").rstrip("\x00")
        return cls(
            individual_address=individual_address,
            name=name,
            multicast_address=multicast_address,
            serial_number=serial_number,
            mac_address=mac_address,
            knx_medium=knx_medium,
            programming_mode=programming_mode,
        )


@dataclass(frozen=True)
class SupportedServiceFamily:
    family: ServiceFamily
    version: int

    def __post_init__(self) -> None:
        if not 0 <= self.version <= 255:
            raise ValueError(f"version must be 0..255, got {self.version}")

    def to_knx(self) -> bytes:
        return bytes([self.family.value, self.version])


@dataclass(frozen=True)
class SupportedServiceFamiliesDIB:
    families: tuple[SupportedServiceFamily, ...]

    def calculated_length(self) -> int:
        return 2 + 2 * len(self.families)

    def to_knx(self) -> bytes:
        return bytes(
            [self.calculated_length(), DIBTypeCode.SUPP_SVC_FAMILIES.value]
        ) + b"".join(family.to_knx() for family in self.families)

    @classmethod
    def from_knx(cls, data: bytes) -> SupportedServiceFamiliesDIB:
        if len(data) < 2:
            raise ParseError(f"SupportedServiceFamiliesDIB too short: {len(data)} bytes")
        length = data[0]
        if len(data) < length or length % 2:
            raise ParseError(f"Invalid SupportedServiceFamiliesDIB length: {length}")
        try:
            type_code = DIBTypeCode(data[1])
        except ValueError:
            raise ParseError(f"Unsupported DIB type code: {data[1]:#04x}") from None
        if type_code is not DIBTypeCode.SUPP_SVC_FAMILIES:
            raise ParseError(f"Expected SUPP_SVC_FAMILIES DIB, got {type_code.name}")
        families = []
        for pos in range(2, length, 2):
            try:
                family = ServiceFamily(data[pos])
            except ValueError:
                raise ParseError(f"Unsupported service family code: {data[pos]:#04x}") from None
            families.append(SupportedServiceFamily(family=family, version=data[pos + 1]))
        return cls(families=tuple(families))
