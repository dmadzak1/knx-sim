"""Device-type registry: maps a DeviceConfig's "type" string to the Device
subclass that knows how to build itself from one (F-CFG-1).

Each device owns its own from_config() classmethod (see e.g.
knx_sim/devices/switch.py), so this module only needs a flat lookup table --
adding a new device type to the library means adding one line here, not
touching a central parser.
"""

from __future__ import annotations

from collections.abc import Callable

from knx_sim.config.models import DeviceConfig
from knx_sim.devices.blind import BlindActuator
from knx_sim.devices.device import Device
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.devices.presence import PresenceSensor
from knx_sim.devices.switch import SwitchActuator, WallSwitch
from knx_sim.devices.thermostat import Thermostat

DeviceFactory = Callable[[DeviceConfig], Device]

DEVICE_TYPES: dict[str, DeviceFactory] = {
    "switch": SwitchActuator.from_config,
    "wall_switch": WallSwitch.from_config,
    "dimmer": DimmerActuator.from_config,
    "blind": BlindActuator.from_config,
    "thermostat": Thermostat.from_config,
    "presence": PresenceSensor.from_config,
}


def build_device(config: DeviceConfig) -> Device:
    """Build the Device described by config, via its type's from_config()."""
    try:
        factory = DEVICE_TYPES[config.type]
    except KeyError:
        known = ", ".join(sorted(DEVICE_TYPES))
        raise ValueError(
            f"unknown device type {config.type!r} for device "
            f"{config.name or config.individual_address!r} -- known types: {known}"
        ) from None
    return factory(config)
