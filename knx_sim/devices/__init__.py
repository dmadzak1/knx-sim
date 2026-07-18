"""Device/GroupObject abstraction and the virtual device library."""

from knx_sim.devices.device import Device
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags
from knx_sim.devices.switch import SwitchActuator, WallSwitch

__all__ = [
    "Device",
    "DimmerActuator",
    "GroupObject",
    "GroupObjectFlags",
    "SwitchActuator",
    "WallSwitch",
]
