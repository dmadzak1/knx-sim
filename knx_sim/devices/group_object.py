"""GroupObject: a device's typed, addressable piece of state.

Pure state -- no asyncio, no bus reference, no I/O. It knows its own group
address, DPT, KNX C/R/W/T/U flags, and current value, and it bridges
between DPT-decoded Python values and the int|bytes payload shape
knx_sim.cemi.Telegram expects (see Telegram's docstring in
knx_sim/cemi/frame.py for why that shape exists).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knx_sim.cemi.address import GroupAddress
from knx_sim.dpt import get_codec


@dataclass(frozen=True)
class GroupObjectFlags:
    """KNX group object flags: Communication, Read, Write, Transmit, Update."""

    communication: bool = False
    read: bool = False
    write: bool = False
    transmit: bool = False
    update: bool = False


@dataclass
class GroupObject:
    """A single group address's worth of typed state on a Device."""

    name: str
    group_address: GroupAddress
    dpt_id: str
    flags: GroupObjectFlags
    value: Any
    cyclic_seconds: float | None = None

    def __post_init__(self) -> None:
        get_codec(self.dpt_id)  # fail fast on an unknown DPT id

    def set(self, value: Any) -> bool:
        """Update the value. Returns True if it actually changed."""
        changed = bool(value != self.value)
        self.value = value
        return changed

    def to_payload(self) -> int | bytes:
        """Encode the current value into Telegram's payload shape."""
        codec = get_codec(self.dpt_id)
        encoded = codec.encode(self.value)
        if codec.payload_length == 0:
            return encoded[0]
        return encoded

    def apply_payload(self, payload: int | bytes) -> bool:
        """Decode a Telegram payload and set it as the current value.

        Returns True if the value actually changed.
        """
        codec = get_codec(self.dpt_id)
        raw = bytes([payload]) if isinstance(payload, int) else payload
        return self.set(codec.decode(raw))
