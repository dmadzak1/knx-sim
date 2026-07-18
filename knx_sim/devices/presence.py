"""Presence/motion sensor: DPT 1.018 occupancy, with a hold timer and
optional random-activity mode (F-DEV-5).

Modeled after how real PIR sensors actually behave, not a plain toggle:
trigger() sets presence and (re)starts a hold_time countdown that clears
presence back to False if no further trigger() arrives in time -- repeated
motion keeps re-extending the window, matching a real sensor's "stay lit
while movement continues" behavior. trigger() is also the hook a scenario
script or the web UI (M7/M8) would call to simulate a person walking by.
"""

from __future__ import annotations

import asyncio
import random

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.models import DeviceConfig
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags

DEFAULT_HOLD_TIME = 30.0
DEFAULT_RANDOM_ACTIVITY_MIN_INTERVAL = 10.0
DEFAULT_RANDOM_ACTIVITY_MAX_INTERVAL = 120.0


class PresenceSensor(Device):
    """A presence/motion sensor: presence (1.018, status)."""

    def __init__(
        self,
        individual_address: IndividualAddress,
        presence_ga: GroupAddress,
        *,
        hold_time: float = DEFAULT_HOLD_TIME,
        random_activity: bool = False,
        random_activity_min_interval: float = DEFAULT_RANDOM_ACTIVITY_MIN_INTERVAL,
        random_activity_max_interval: float = DEFAULT_RANDOM_ACTIVITY_MAX_INTERVAL,
    ) -> None:
        if hold_time <= 0:
            raise ValueError(f"hold_time must be > 0, got {hold_time}")
        if random_activity_min_interval <= 0:
            raise ValueError(
                f"random_activity_min_interval must be > 0, got {random_activity_min_interval}"
            )
        if random_activity_max_interval < random_activity_min_interval:
            raise ValueError(
                "random_activity_max_interval must be >= random_activity_min_interval, "
                f"got {random_activity_max_interval} < {random_activity_min_interval}"
            )

        presence = GroupObject(
            name="presence",
            group_address=presence_ga,
            dpt_id="1.018",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=False,
        )
        super().__init__(individual_address, [presence])

        self._hold_time = hold_time
        self._random_activity = random_activity
        self._random_activity_min_interval = random_activity_min_interval
        self._random_activity_max_interval = random_activity_max_interval
        self._hold_task: asyncio.Task[None] | None = None
        self._random_task: asyncio.Task[None] | None = None

    @classmethod
    def from_config(cls, config: DeviceConfig) -> PresenceSensor:
        return cls(
            IndividualAddress.from_string(config.individual_address),
            GroupAddress.from_string(config.require("presence_ga")),
            hold_time=float(config.get("hold_time", DEFAULT_HOLD_TIME)),
            random_activity=bool(config.get("random_activity", False)),
            random_activity_min_interval=float(
                config.get(
                    "random_activity_min_interval", DEFAULT_RANDOM_ACTIVITY_MIN_INTERVAL
                )
            ),
            random_activity_max_interval=float(
                config.get(
                    "random_activity_max_interval", DEFAULT_RANDOM_ACTIVITY_MAX_INTERVAL
                )
            ),
        )

    async def trigger(self) -> None:
        """Simulate a motion event: set presence and (re)start the hold timer."""
        presence = self.group_objects["presence"]
        if presence.set(True) and presence.flags.transmit:
            await self.transmit(presence)
        self._restart_hold_timer()

    async def start(self) -> None:
        if self._random_activity:
            self._random_task = asyncio.create_task(self._run_random_activity())

    async def stop(self) -> None:
        self._cancel_hold_timer()
        if self._random_task is not None:
            self._random_task.cancel()
            try:
                await self._random_task
            except asyncio.CancelledError:
                pass
            self._random_task = None

    def _restart_hold_timer(self) -> None:
        self._cancel_hold_timer()
        self._hold_task = asyncio.create_task(self._hold_and_clear())

    def _cancel_hold_timer(self) -> None:
        # Fire-and-forget: intentionally not awaited. trigger() runs inside
        # _run_random_activity (a long-lived background task); if stop()
        # cancels that task while it's suspended awaiting a hold_task it is
        # cancelling itself here, asyncio delivers the *outer* cancellation
        # at that same await point, and a broad `except CancelledError` here
        # would swallow it -- silently defeating stop()'s cancellation and
        # hanging its `await self._random_task`. Not awaiting sidesteps the
        # ambiguity entirely; there's no cleanup after hold_and_clear's sole
        # await point that we'd miss by not waiting for it to unwind.
        if self._hold_task is not None:
            self._hold_task.cancel()
            self._hold_task = None

    async def _hold_and_clear(self) -> None:
        await asyncio.sleep(self._hold_time)
        presence = self.group_objects["presence"]
        if presence.set(False) and presence.flags.transmit:
            await self.transmit(presence)
        self._hold_task = None

    async def _run_random_activity(self) -> None:
        while True:
            wait = random.uniform(
                self._random_activity_min_interval, self._random_activity_max_interval
            )
            await asyncio.sleep(wait)
            await self.trigger()
