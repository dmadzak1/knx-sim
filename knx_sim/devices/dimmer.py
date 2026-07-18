"""Dimmer actuator: switch + relative dim + absolute brightness control,
with a continuous ramp for relative dimming (F-DEV-2).

Continuous-ramp model, deliberately simplified: DPT 3.007's step_code
technically encodes step *size* per KNX's own timing table (finer step_code
values imply smaller, slower steps). We instead model any non-zero step as
"start a continuous ramp toward 0%/100% at a constant rate", ignoring which
specific step_code was sent -- the rate comes from a device parameter
(ramp_time_full_range), not from the step_code. This trades protocol-perfect
fidelity for a much simpler, more testable model -- a deliberate choice
(see docs/PROJECT_CONTEXT.md), not an oversight.
"""

from __future__ import annotations

import asyncio

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.models import DeviceConfig
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags
from knx_sim.dpt.dpt3 import DimmingControl

DEFAULT_RAMP_TIME_FULL_RANGE = 3.0
DEFAULT_RAMP_TICK_INTERVAL = 0.2


class DimmerActuator(Device):
    """A dimmer actuator: switch (1.001), relative dim (3.007), absolute
    brightness (5.001) controls; switch/brightness status objects."""

    def __init__(
        self,
        individual_address: IndividualAddress,
        switch_ga: GroupAddress,
        relative_dim_ga: GroupAddress,
        brightness_ga: GroupAddress,
        switch_status_ga: GroupAddress,
        brightness_status_ga: GroupAddress,
        *,
        initial_brightness: float = 0.0,
        ramp_time_full_range: float = DEFAULT_RAMP_TIME_FULL_RANGE,
        ramp_tick_interval: float = DEFAULT_RAMP_TICK_INTERVAL,
    ) -> None:
        if not 0.0 <= initial_brightness <= 100.0:
            raise ValueError(f"initial_brightness must be 0..100, got {initial_brightness}")
        if ramp_time_full_range <= 0:
            raise ValueError(f"ramp_time_full_range must be > 0, got {ramp_time_full_range}")
        if ramp_tick_interval <= 0:
            raise ValueError(f"ramp_tick_interval must be > 0, got {ramp_tick_interval}")

        is_on = initial_brightness > 0.0
        switch = GroupObject(
            name="switch",
            group_address=switch_ga,
            dpt_id="1.001",
            flags=GroupObjectFlags(communication=True, write=True),
            value=is_on,
        )
        relative_dim = GroupObject(
            name="relative_dim",
            group_address=relative_dim_ga,
            dpt_id="3.007",
            flags=GroupObjectFlags(communication=True, write=True),
            value=DimmingControl(direction=True, step_code=0),
        )
        brightness = GroupObject(
            name="brightness",
            group_address=brightness_ga,
            dpt_id="5.001",
            flags=GroupObjectFlags(communication=True, write=True),
            value=initial_brightness,
        )
        switch_status = GroupObject(
            name="switch_status",
            group_address=switch_status_ga,
            dpt_id="1.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=is_on,
        )
        brightness_status = GroupObject(
            name="brightness_status",
            group_address=brightness_status_ga,
            dpt_id="5.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=initial_brightness,
        )
        super().__init__(
            individual_address,
            [switch, relative_dim, brightness, switch_status, brightness_status],
        )

        self._brightness = initial_brightness
        self._last_on_brightness = initial_brightness if is_on else 100.0
        self._ramp_time_full_range = ramp_time_full_range
        self._ramp_tick_interval = ramp_tick_interval
        self._ramp_task: asyncio.Task[None] | None = None

    @classmethod
    def from_config(cls, config: DeviceConfig) -> DimmerActuator:
        return cls(
            IndividualAddress.from_string(config.individual_address),
            GroupAddress.from_string(config.require("switch_ga")),
            GroupAddress.from_string(config.require("relative_dim_ga")),
            GroupAddress.from_string(config.require("brightness_ga")),
            GroupAddress.from_string(config.require("switch_status_ga")),
            GroupAddress.from_string(config.require("brightness_status_ga")),
            initial_brightness=float(config.get("initial_brightness", 0.0)),
            ramp_time_full_range=float(
                config.get("ramp_time_full_range", DEFAULT_RAMP_TIME_FULL_RANGE)
            ),
            ramp_tick_interval=float(
                config.get("ramp_tick_interval", DEFAULT_RAMP_TICK_INTERVAL)
            ),
        )

    async def handle_group_write(self, group_object: GroupObject) -> None:
        if group_object.name == "switch":
            await self._cancel_ramp()
            self._brightness = self._last_on_brightness if group_object.value else 0.0
            await self._publish_brightness()
        elif group_object.name == "brightness":
            await self._cancel_ramp()
            self._brightness = float(group_object.value)
            await self._publish_brightness()
        elif group_object.name == "relative_dim":
            control: DimmingControl = group_object.value
            if control.is_stop:
                await self._cancel_ramp()
            else:
                await self._start_ramp(control.direction)

    async def stop(self) -> None:
        await self._cancel_ramp()

    async def _start_ramp(self, direction: bool) -> None:
        await self._cancel_ramp()
        self._ramp_task = asyncio.create_task(self._run_ramp(direction))

    async def _cancel_ramp(self) -> None:
        if self._ramp_task is not None:
            self._ramp_task.cancel()
            try:
                await self._ramp_task
            except asyncio.CancelledError:
                pass
            self._ramp_task = None

    async def _run_ramp(self, direction: bool) -> None:
        rate_per_second = 100.0 / self._ramp_time_full_range
        while True:
            await asyncio.sleep(self._ramp_tick_interval)
            delta = rate_per_second * self._ramp_tick_interval
            if direction:
                self._brightness = min(100.0, self._brightness + delta)
            else:
                self._brightness = max(0.0, self._brightness - delta)
            await self._publish_brightness()
            if self._brightness in (0.0, 100.0):
                self._ramp_task = None
                return

    async def _publish_brightness(self) -> None:
        if self._brightness > 0.0:
            self._last_on_brightness = self._brightness

        brightness_go = self.group_objects["brightness_status"]
        if brightness_go.set(self._brightness) and brightness_go.flags.transmit:
            await self.transmit(brightness_go)

        switch_go = self.group_objects["switch_status"]
        if switch_go.set(self._brightness > 0.0) and switch_go.flags.transmit:
            await self.transmit(switch_go)
