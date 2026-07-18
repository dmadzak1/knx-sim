"""Device: an individually-addressed collection of GroupObjects.

Devices are constructed standalone (e.g. by config loading or tests) before
any bus exists, so the ability to send telegrams is injected later via
bind() rather than passed to __init__. Subclasses override handle_group_write
and handle_group_read to react to bus events; the bus/router is what decides
*when* to call them (see knx_sim/bus, not yet implemented).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from knx_sim.cemi.address import IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.devices.group_object import GroupObject

SendFn = Callable[[Telegram], Awaitable[None]]


class Device:
    """Base class for a virtual KNX device.

    Concrete device types (SwitchActuator, DimmerActuator, ...) subclass
    this and override handle_group_write for device-specific reactions.
    The base handle_group_read already satisfies F-DEV-8 ("all devices
    answer GroupValueRead on status objects") for every device with no
    subclass code needed.
    """

    def __init__(
        self, individual_address: IndividualAddress, group_objects: Iterable[GroupObject]
    ) -> None:
        self.individual_address = individual_address
        self.group_objects: dict[str, GroupObject] = {go.name: go for go in group_objects}
        self._send: SendFn | None = None

    def bind(self, send: SendFn) -> None:
        """Called by the bus when registering this device."""
        self._send = send

    async def send(self, telegram: Telegram) -> None:
        """Send a telegram onto the bus. Requires bind() to have been called."""
        if self._send is None:
            raise RuntimeError(f"{self!r} is not registered with a bus yet")
        await self._send(telegram)

    async def respond(self, group_object: GroupObject) -> None:
        """Send a GroupValueResponse carrying group_object's current value.

        This is specifically the answer to a GroupValueRead -- see
        handle_group_read.
        """
        telegram = Telegram(
            source=self.individual_address,
            destination=group_object.group_address,
            service=Service.GROUP_RESPONSE,
            payload=group_object.to_payload(),
        )
        await self.send(telegram)

    async def transmit(self, group_object: GroupObject) -> None:
        """Spontaneously send group_object's current value via GroupValueWrite.

        This is the Transmit (T) flag's behavior: a device announcing its
        own value change, as opposed to answering a Read. Callers are
        expected to check group_object.flags.transmit themselves, matching
        how handle_group_read checks flags.read before calling respond().
        """
        telegram = Telegram(
            source=self.individual_address,
            destination=group_object.group_address,
            service=Service.GROUP_WRITE,
            payload=group_object.to_payload(),
        )
        await self.send(telegram)

    async def handle_group_write(self, group_object: GroupObject) -> None:
        """Called after an incoming GroupValueWrite changed group_object's
        value. Override to react (e.g. mirror to a status object). Default:
        no reaction."""

    async def handle_group_read(self, group_object: GroupObject) -> None:
        """Called for an incoming GroupValueRead on group_object. Default:
        respond with the current value if the Read flag is set."""
        if group_object.flags.read:
            await self.respond(group_object)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.individual_address})"
