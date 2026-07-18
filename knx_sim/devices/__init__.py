"""Device/GroupObject abstraction and the virtual device library."""

from knx_sim.devices.blind import BlindActuator
from knx_sim.devices.device import Device
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags
from knx_sim.devices.presence import PresenceSensor
from knx_sim.devices.switch import SwitchActuator, WallSwitch
from knx_sim.devices.thermostat import Thermostat

__all__ = [
    "BlindActuator",
    "Device",
    "DimmerActuator",
    "GroupObject",
    "GroupObjectFlags",
    "PresenceSensor",
    "SwitchActuator",
    "Thermostat",
    "WallSwitch",
]
