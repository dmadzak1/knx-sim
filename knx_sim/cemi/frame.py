"""cEMI L_Data frame parsing and building.

See docs/notes/cemi.md for the annotated byte-level example this module
implements. Scope is deliberately narrow, matching the project's decided
architecture: only L_Data.req/ind/con, only GroupValueRead/Write/Response,
only unnumbered group communication (no transport connections, no
additional-info blocks, no extended/LTE addressing).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from knx_sim.cemi.address import GroupAddress, IndividualAddress


class ParseError(Exception):
    """Raised when a byte sequence is not a valid/supported cEMI frame."""


class MessageCode(Enum):
    """cEMI message codes this simulator supports (L_Data only)."""

    L_DATA_REQ = 0x11  # network layer -> data link layer (send)
    L_DATA_IND = 0x29  # data link layer -> network layer (received from bus)
    L_DATA_CON = 0x2E  # local confirmation that a frame was sent


class Priority(Enum):
    """Control Field 1 bits 3-2."""

    SYSTEM = 0b00
    NORMAL = 0b01
    URGENT = 0b10
    LOW = 0b11


class Service(Enum):
    """Supported APCI services -- the value is APCI bits 7-6 (see cemi.md)."""

    GROUP_READ = 0b00
    GROUP_RESPONSE = 0b01
    GROUP_WRITE = 0b10


@dataclass(frozen=True)
class Telegram:
    """A KNX telegram: a DPT-agnostic view of a cEMI L_Data frame's content.

    `payload` mirrors the cEMI wire shape directly rather than any DPT
    semantics:
    - `None` for GroupValueRead (the service carries no value).
    - `int` (0..63) for a <=6-bit DPT (payload_length == 0) -- merged into
      the low 6 bits of the APCI byte.
    - `bytes` for a DPT with payload_length > 0 -- appended after the APCI
      byte.

    A DPT codec's `encode()` always returns `bytes`; it's the caller's job
    (the bus layer, in M3) to pick the right shape here based on the
    codec's `payload_length`: 0 -> `int.from_bytes(encoded, "big")`,
    otherwise the `bytes` as-is.
    """

    source: IndividualAddress
    destination: GroupAddress
    service: Service
    payload: int | bytes | None
    priority: Priority = Priority.LOW
    hop_count: int = 6

    def __post_init__(self) -> None:
        if not 0 <= self.hop_count <= 7:
            raise ValueError(f"hop_count must be 0..7, got {self.hop_count}")
        if self.service is Service.GROUP_READ:
            if self.payload is not None:
                raise ValueError("GroupValueRead must not carry a payload")
        else:
            if self.payload is None:
                raise ValueError(f"{self.service.name} requires a payload")
            if isinstance(self.payload, int) and not 0 <= self.payload <= 63:
                raise ValueError(f"inline payload must be 0..63, got {self.payload}")
            if isinstance(self.payload, bytes) and len(self.payload) == 0:
                raise ValueError("appended payload must not be empty")


def build_cemi(telegram: Telegram, msg_code: MessageCode) -> bytes:
    """Serialize a Telegram to a cEMI L_Data frame."""
    # Control Field 1: standard frame, do-not-repeat, broadcast, priority,
    # no ack requested, no error. See docs/notes/cemi.md.
    ctrl1 = 0b1011_0000 | (telegram.priority.value << 2)
    # Control Field 2: group-address destination, hop count, standard
    # addressing (not extended/LTE).
    ctrl2 = 0b1000_0000 | (telegram.hop_count << 4)

    if isinstance(telegram.payload, bytes):
        inline_bits = 0
        appended = telegram.payload
    elif isinstance(telegram.payload, int):
        inline_bits = telegram.payload
        appended = b""
    else:
        inline_bits = 0
        appended = b""

    tpci_apci_high = 0x00  # unnumbered data TPCI, APCI bits 9-8 = 00
    apci_low_and_data = (telegram.service.value << 6) | inline_bits
    tpdu = bytes([tpci_apci_high, apci_low_and_data]) + appended
    npdu_length = len(tpdu) - 1

    return (
        bytes([msg_code.value, 0x00])  # message code, additional info length
        + bytes([ctrl1, ctrl2])
        + telegram.source.to_knx()
        + telegram.destination.to_knx()
        + bytes([npdu_length])
        + tpdu
    )


def parse_cemi(data: bytes) -> tuple[MessageCode, Telegram]:
    """Parse a cEMI L_Data frame, returning its message code and Telegram."""
    if len(data) < 9:
        raise ParseError(f"cEMI frame too short: {len(data)} bytes, need at least 9")

    try:
        msg_code = MessageCode(data[0])
    except ValueError:
        raise ParseError(f"Unsupported cEMI message code: {data[0]:#04x}") from None

    add_info_len = data[1]
    if add_info_len != 0:
        raise ParseError(f"Additional info blocks are not supported (length={add_info_len})")

    ctrl1, ctrl2 = data[2], data[3]

    if not ctrl2 & 0x80:
        raise ParseError(
            "Individual-address destinations are not supported (GroupValue services only)"
        )

    priority = Priority((ctrl1 >> 2) & 0b11)
    hop_count = (ctrl2 >> 4) & 0b111

    source = IndividualAddress.from_knx(data[4:6])
    destination = GroupAddress.from_knx(data[6:8])

    npdu_length = data[8]
    tpdu = data[9:]
    if len(tpdu) != npdu_length + 1:
        raise ParseError(
            f"NPDU length mismatch: header says {npdu_length}, "
            f"got {len(tpdu) - 1} bytes of TPDU tail"
        )
    if len(tpdu) < 2:
        raise ParseError(f"TPDU too short: {len(tpdu)} bytes, need at least 2")

    tpci_byte, apci_byte, *data_bytes = tpdu

    if (tpci_byte >> 6) != 0b00:
        raise ParseError(
            f"Unsupported TPCI type: {tpci_byte >> 6:#04b} "
            "(only unnumbered data is supported)"
        )
    if (tpci_byte >> 2) & 0xF:
        raise ParseError("Unexpected sequence number on unnumbered data TPCI")
    if tpci_byte & 0b11:
        raise ParseError(
            "Only GroupValueRead/Write/Response APCI services are supported "
            "(APCI bits 9-8 must be 0)"
        )

    try:
        service = Service((apci_byte >> 6) & 0b11)
    except ValueError:
        raise ParseError(f"Unsupported APCI service: {(apci_byte >> 6) & 0b11:#04b}") from None

    inline_value = apci_byte & 0x3F
    appended = bytes(data_bytes)
    if inline_value and appended:
        raise ParseError("Malformed APCI byte: data present in both inline and appended form")

    if service is Service.GROUP_READ:
        if inline_value or appended:
            raise ParseError("GroupValueRead must not carry a payload")
        payload: int | bytes | None = None
    else:
        payload = appended if appended else inline_value

    telegram = Telegram(
        source=source,
        destination=destination,
        service=service,
        payload=payload,
        priority=priority,
        hop_count=hop_count,
    )
    return msg_code, telegram
