"""Blind/shutter actuator: move up/down, stop, and absolute position
control, with simulated travel time (F-DEV-3).

Same continuous-motion model as DimmerActuator's ramp, generalized slightly:
a move command travels to a bound (0% or 100%), an absolute position command
travels to that specific target -- both share one _run_travel(direction,
target) loop, since "travel to a bound" is just the special case where
target happens to be 0.0 or 100.0.

Position convention: 0% = fully open/up, 100% = fully closed/down, matching
DPT 1.008's Up/Down (False=Up, True=Down) and typical KNX blind actuators.
"""

from __future__ import annotations

import asyncio

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.models import DeviceConfig
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags

DEFAULT_TRAVEL_TIME_FULL_RANGE = 20.0
DEFAULT_TRAVEL_TICK_INTERVAL = 0.2


class BlindActuator(Device):
    """A blind/shutter actuator: move (1.008), stop (1.010), absolute
    position (5.001) controls; position/moving status objects."""

    def __init__(
        self,
        individual_address: IndividualAddress,
        move_ga: GroupAddress,
        stop_ga: GroupAddress,
        position_ga: GroupAddress,
        position_status_ga: GroupAddress,
        moving_status_ga: GroupAddress,
        *,
        initial_position: float = 0.0,
        travel_time_full_range: float = DEFAULT_TRAVEL_TIME_FULL_RANGE,
        travel_tick_interval: float = DEFAULT_TRAVEL_TICK_INTERVAL,
    ) -> None:
        if not 0.0 <= initial_position <= 100.0:
            raise ValueError(f"initial_position must be 0..100, got {initial_position}")
        if travel_time_full_range <= 0:
            raise ValueError(f"travel_time_full_range must be > 0, got {travel_time_full_range}")
        if travel_tick_interval <= 0:
            raise ValueError(f"travel_tick_interval must be > 0, got {travel_tick_interval}")

        move = GroupObject(
            name="move",
            group_address=move_ga,
            dpt_id="1.008",
            flags=GroupObjectFlags(communication=True, write=True),
            value=False,
        )
        stop = GroupObject(
            name="stop",
            group_address=stop_ga,
            dpt_id="1.010",
            flags=GroupObjectFlags(communication=True, write=True),
            value=False,
        )
        position = GroupObject(
            name="position",
            group_address=position_ga,
            dpt_id="5.001",
            flags=GroupObjectFlags(communication=True, write=True),
            value=initial_position,
        )
        position_status = GroupObject(
            name="position_status",
            group_address=position_status_ga,
            dpt_id="5.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=initial_position,
        )
        moving_status = GroupObject(
            name="moving_status",
            group_address=moving_status_ga,
            dpt_id="1.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=False,
        )
        super().__init__(
            individual_address, [move, stop, position, position_status, moving_status]
        )

        self._position = initial_position
        self._travel_time_full_range = travel_time_full_range
        self._travel_tick_interval = travel_tick_interval
        self._travel_task: asyncio.Task[None] | None = None

    @classmethod
    def from_config(cls, config: DeviceConfig) -> BlindActuator:
        return cls(
            IndividualAddress.from_string(config.individual_address),
            GroupAddress.from_string(config.require("move_ga")),
            GroupAddress.from_string(config.require("stop_ga")),
            GroupAddress.from_string(config.require("position_ga")),
            GroupAddress.from_string(config.require("position_status_ga")),
            GroupAddress.from_string(config.require("moving_status_ga")),
            initial_position=float(config.get("initial_position", 0.0)),
            travel_time_full_range=float(
                config.get("travel_time_full_range", DEFAULT_TRAVEL_TIME_FULL_RANGE)
            ),
            travel_tick_interval=float(
                config.get("travel_tick_interval", DEFAULT_TRAVEL_TICK_INTERVAL)
            ),
        )

    async def handle_group_write(self, group_object: GroupObject) -> None:
        if group_object.name == "move":
            direction = bool(group_object.value)
            await self._start_travel(direction, target=100.0 if direction else 0.0)
        elif group_object.name == "stop":
            await self._cancel_travel()
        elif group_object.name == "position":
            target = float(group_object.value)
            await self._start_travel(direction=target > self._position, target=target)

    async def stop(self) -> None:
        await self._cancel_travel()

    async def _start_travel(self, direction: bool, target: float) -> None:
        await self._cancel_travel()
        if self._position == target:
            return
        await self._set_moving(True)
        self._travel_task = asyncio.create_task(self._run_travel(direction, target))

    async def _cancel_travel(self) -> None:
        if self._travel_task is not None:
            self._travel_task.cancel()
            try:
                await self._travel_task
            except asyncio.CancelledError:
                pass
            self._travel_task = None
            await self._set_moving(False)

    async def _run_travel(self, direction: bool, target: float) -> None:
        rate_per_second = 100.0 / self._travel_time_full_range
        while True:
            await asyncio.sleep(self._travel_tick_interval)
            delta = rate_per_second * self._travel_tick_interval
            if direction:
                self._position = min(target, self._position + delta)
            else:
                self._position = max(target, self._position - delta)
            await self._publish_position()
            if self._position == target:
                self._travel_task = None
                await self._set_moving(False)
                return

    async def _publish_position(self) -> None:
        position_go = self.group_objects["position_status"]
        if position_go.set(self._position) and position_go.flags.transmit:
            await self.transmit(position_go)

    async def _set_moving(self, moving: bool) -> None:
        moving_go = self.group_objects["moving_status"]
        if moving_go.set(moving) and moving_go.flags.transmit:
            await self.transmit(moving_go)
