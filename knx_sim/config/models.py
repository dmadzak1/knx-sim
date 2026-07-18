"""Pydantic models for the YAML installation config (F-CFG-1).

DeviceConfig deliberately only types the fields every device shares (type,
individual_address, name); everything device-specific -- group addresses,
ramp/travel times, hold times, whatever -- is free-form extra YAML keys at
the same top level (model_config extra="allow"), so a device's own
from_config() classmethod is the only place that knows its own field names
(see knx_sim/config/registry.py). require()/get() are typed accessors for
those extra fields: pydantic exposes them dynamically via __getattr__, which
mypy --strict can't see through, so callers go through these instead of
raw attribute access.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knx_sim.cemi.address import IndividualAddress

DEFAULT_SIMULATOR_NAME = "knx-sim"
DEFAULT_PORT = 3671
DEFAULT_MAX_TUNNELS = 4
DEFAULT_DELAY_SECONDS = 0.02


class SimulatorConfig(BaseModel):
    """Top-level simulator settings: name, bind address, tunnels, delay model."""

    name: str = DEFAULT_SIMULATOR_NAME
    bind_address: str | None = None
    port: int = DEFAULT_PORT
    individual_address: str = "15.15.0"
    max_tunnels: int = DEFAULT_MAX_TUNNELS
    delay_seconds: float = DEFAULT_DELAY_SECONDS

    @field_validator("individual_address")
    @classmethod
    def _validate_individual_address(cls, value: str) -> str:
        IndividualAddress.from_string(value)  # raises ValueError on malformed input
        return value

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError(f"port must be 1..65535, got {value}")
        return value

    @field_validator("max_tunnels")
    @classmethod
    def _validate_max_tunnels(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"max_tunnels must be >= 1, got {value}")
        return value

    @field_validator("delay_seconds")
    @classmethod
    def _validate_delay_seconds(cls, value: float) -> float:
        if value < 0:
            raise ValueError(f"delay_seconds must be >= 0, got {value}")
        return value


class DeviceConfig(BaseModel):
    """One device entry: type + individual address + device-specific fields."""

    model_config = ConfigDict(extra="allow")

    type: str
    individual_address: str
    name: str | None = None

    @field_validator("individual_address")
    @classmethod
    def _validate_individual_address(cls, value: str) -> str:
        IndividualAddress.from_string(value)  # raises ValueError on malformed input
        return value

    def require(self, key: str) -> Any:
        """Fetch a device-specific field, raising a helpful error if absent."""
        extra = self.model_extra or {}
        if key not in extra:
            raise ValueError(
                f"device {self.name or self.individual_address!r} (type={self.type!r}) "
                f"is missing required field {key!r}"
            )
        return extra[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Fetch an optional device-specific field, or default if absent."""
        return (self.model_extra or {}).get(key, default)


class InstallationConfig(BaseModel):
    """A whole virtual installation: simulator settings plus its devices."""

    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)
    devices: list[DeviceConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_individual_addresses(self) -> InstallationConfig:
        seen: set[str] = set()
        for device in self.devices:
            if device.individual_address in seen:
                raise ValueError(
                    f"duplicate individual_address {device.individual_address!r} "
                    "-- every device needs a unique address"
                )
            seen.add(device.individual_address)
        return self
