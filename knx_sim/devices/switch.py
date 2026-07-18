"""Switch actuator and wall switch: the simplest device pair (F-DEV-1, F-DEV-6).

A WallSwitch's control GA is wired to a SwitchActuator's control GA at
config time (same GroupAddress on both) -- that's how they get linked on
the bus; neither device holds a direct reference to the other.
"""

from __future__ import annotations

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags

_SWITCH_DPT = "1.001"


class SwitchActuator(Device):
    """A switch actuator (relay): DPT 1.001 on a control GA, with status
    mirrored to a separate status GA (F-DEV-1)."""

    def __init__(
        self,
        individual_address: IndividualAddress,
        control_ga: GroupAddress,
        status_ga: GroupAddress,
        *,
        initial_value: bool = False,
    ) -> None:
        control = GroupObject(
            name="control",
            group_address=control_ga,
            dpt_id=_SWITCH_DPT,
            flags=GroupObjectFlags(communication=True, write=True),
            value=initial_value,
        )
        status = GroupObject(
            name="status",
            group_address=status_ga,
            dpt_id=_SWITCH_DPT,
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=initial_value,
        )
        super().__init__(individual_address, [control, status])

    async def handle_group_write(self, group_object: GroupObject) -> None:
        if group_object.name != "control":
            return
        status = self.group_objects["status"]
        if status.set(group_object.value) and status.flags.transmit:
            await self.transmit(status)


class WallSwitch(Device):
    """A wall switch (sensor): a purely stimulus device with no bus-facing
    Read/Write behavior of its own -- it only ever sends (F-DEV-6).

    press() is the "physical button press" simulated by the web UI or a
    scenario script.
    """

    def __init__(
        self,
        individual_address: IndividualAddress,
        control_ga: GroupAddress,
        *,
        initial_value: bool = False,
    ) -> None:
        control = GroupObject(
            name="control",
            group_address=control_ga,
            dpt_id=_SWITCH_DPT,
            flags=GroupObjectFlags(communication=True, transmit=True),
            value=initial_value,
        )
        super().__init__(individual_address, [control])

    async def press(self) -> None:
        """Toggle the control value and transmit it, as a physical press would."""
        control = self.group_objects["control"]
        control.set(not control.value)
        await self.transmit(control)
