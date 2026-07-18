"""KNX address types: individual addresses ("1.1.23") and group addresses ("1/2/10").

Both are 16-bit wire values, just split differently:
- IndividualAddress: 4 bits area + 4 bits line + 8 bits device.
- GroupAddress: 5 bits main group + 3 bits middle group + 8 bits sub group.

See docs/notes/cemi.md for the worked byte-level derivation this matches.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndividualAddress:
    """A KNX individual address, e.g. "1.1.23" (area.line.device)."""

    area: int  # 0..15 (4 bits)
    line: int  # 0..15 (4 bits)
    device: int  # 0..255 (8 bits)

    def __post_init__(self) -> None:
        if not 0 <= self.area <= 15:
            raise ValueError(f"IndividualAddress area must be 0..15, got {self.area}")
        if not 0 <= self.line <= 15:
            raise ValueError(f"IndividualAddress line must be 0..15, got {self.line}")
        if not 0 <= self.device <= 255:
            raise ValueError(f"IndividualAddress device must be 0..255, got {self.device}")

    @classmethod
    def from_string(cls, value: str) -> IndividualAddress:
        parts = value.split(".")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid individual address {value!r}: expected 'area.line.device'"
            )
        try:
            area, line, device = (int(part) for part in parts)
        except ValueError:
            raise ValueError(
                f"Invalid individual address {value!r}: area/line/device must be integers"
            ) from None
        return cls(area=area, line=line, device=device)

    def __str__(self) -> str:
        return f"{self.area}.{self.line}.{self.device}"

    def to_knx(self) -> bytes:
        raw = (self.area << 12) | (self.line << 8) | self.device
        return raw.to_bytes(2, "big")

    @classmethod
    def from_knx(cls, data: bytes) -> IndividualAddress:
        if len(data) != 2:
            raise ValueError(f"IndividualAddress expects 2 bytes, got {len(data)}")
        raw = int.from_bytes(data, "big")
        return cls(area=(raw >> 12) & 0xF, line=(raw >> 8) & 0xF, device=raw & 0xFF)


@dataclass(frozen=True)
class GroupAddress:
    """A KNX 3-level group address, e.g. "1/2/10" (main/middle/sub)."""

    main: int  # 0..31 (5 bits)
    middle: int  # 0..7 (3 bits)
    sub: int  # 0..255 (8 bits)

    def __post_init__(self) -> None:
        if not 0 <= self.main <= 31:
            raise ValueError(f"GroupAddress main must be 0..31, got {self.main}")
        if not 0 <= self.middle <= 7:
            raise ValueError(f"GroupAddress middle must be 0..7, got {self.middle}")
        if not 0 <= self.sub <= 255:
            raise ValueError(f"GroupAddress sub must be 0..255, got {self.sub}")

    @classmethod
    def from_string(cls, value: str) -> GroupAddress:
        parts = value.split("/")
        if len(parts) != 3:
            raise ValueError(f"Invalid group address {value!r}: expected 'main/middle/sub'")
        try:
            main, middle, sub = (int(part) for part in parts)
        except ValueError:
            raise ValueError(
                f"Invalid group address {value!r}: main/middle/sub must be integers"
            ) from None
        return cls(main=main, middle=middle, sub=sub)

    def __str__(self) -> str:
        return f"{self.main}/{self.middle}/{self.sub}"

    def to_knx(self) -> bytes:
        raw = (self.main << 11) | (self.middle << 8) | self.sub
        return raw.to_bytes(2, "big")

    @classmethod
    def from_knx(cls, data: bytes) -> GroupAddress:
        if len(data) != 2:
            raise ValueError(f"GroupAddress expects 2 bytes, got {len(data)}")
        raw = int.from_bytes(data, "big")
        return cls(main=(raw >> 11) & 0x1F, middle=(raw >> 8) & 0x7, sub=raw & 0xFF)
