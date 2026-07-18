"""The virtual bus: device registry, group-address routing, propagation
delay, and the rolling telegram log.

The bus models a single shared serial medium (matching real TP1): exactly
one telegram is "on the wire" at a time, each incurring a fixed propagation
delay before being routed. A telegram that triggers a device reaction (e.g.
a status mirror) re-enters the same queue as a new, independently-delayed
telegram -- this is what makes multi-hop behavior (switch write -> lamp
reacts -> status telegram appears) fall out naturally, with no special
casing needed.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Priority, Service, Telegram
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject
from knx_sim.dpt import get_codec

DEFAULT_DELAY_SECONDS = 0.02
DEFAULT_LOG_SIZE = 5000

# Scheduling urgency for the priority queue -- distinct from Priority's own
# enum values, which are the cEMI Control Field 1 wire bits from M2 (System=0,
# Normal=1, Urgent=2, Low=3), NOT the urgency order. Urgent must be served
# before Normal even though its wire bit value is numerically higher.
_PRIORITY_RANK: dict[Priority, int] = {
    Priority.SYSTEM: 0,
    Priority.URGENT: 1,
    Priority.NORMAL: 2,
    Priority.LOW: 3,
}

MonitorCallback = Callable[[Telegram], Awaitable[None]]


@dataclass(frozen=True)
class TelegramLogEntry:
    """One rolling telegram-log record (F-BUS-5)."""

    timestamp: float
    telegram: Telegram
    dpt_id: str | None
    decoded_value: Any | None


class Bus:
    """The virtual KNX bus: routes telegrams between registered devices."""

    def __init__(
        self,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        log_size: int = DEFAULT_LOG_SIZE,
    ) -> None:
        self._delay_seconds = delay_seconds
        self._devices: dict[IndividualAddress, Device] = {}
        self._subscribers: dict[GroupAddress, list[tuple[Device, GroupObject]]] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, int, Telegram]] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._log: deque[TelegramLogEntry] = deque(maxlen=log_size)
        self._monitors: list[MonitorCallback] = []
        self._task: asyncio.Task[None] | None = None

    def register(self, device: Device) -> None:
        """Register a device: binds its send capability and indexes its
        group objects for routing (F-BUS-1)."""
        if device.individual_address in self._devices:
            raise ValueError(
                f"individual address {device.individual_address} already registered"
            )
        device.bind(self.inject)
        self._devices[device.individual_address] = device
        for group_object in device.group_objects.values():
            self._subscribers.setdefault(group_object.group_address, []).append(
                (device, group_object)
            )

    def subscribe(self, callback: MonitorCallback) -> None:
        """Register a monitor callback invoked for every processed telegram (F-BUS-6)."""
        self._monitors.append(callback)

    def unsubscribe(self, callback: MonitorCallback) -> None:
        self._monitors.remove(callback)

    async def inject(self, telegram: Telegram) -> None:
        """Put a telegram on the bus (F-BUS-7).

        This is what Device.send() is bound to on registration, and it's
        also how external callers (web UI manual control, scenario runner)
        put a telegram on the bus programmatically.
        """
        await self._queue.put((_PRIORITY_RANK[telegram.priority], next(self._seq), telegram))

    @property
    def telegram_log(self) -> tuple[TelegramLogEntry, ...]:
        return tuple(self._log)

    def start(self) -> None:
        """Start the background telegram-processing loop."""
        if self._task is not None:
            raise RuntimeError("bus is already started")
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the background loop."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def join(self) -> None:
        """Wait until every currently-queued telegram -- and anything it
        cascades into -- has finished processing."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            _, _, telegram = await self._queue.get()
            try:
                await asyncio.sleep(self._delay_seconds)
                await self._process(telegram)
            finally:
                self._queue.task_done()

    async def _process(self, telegram: Telegram) -> None:
        self._log.append(self._make_log_entry(telegram))
        for callback in self._monitors:
            await callback(telegram)

        for device, group_object in self._subscribers.get(telegram.destination, []):
            if device.individual_address == telegram.source:
                continue  # never deliver a telegram back to its own sender
            if not group_object.flags.communication:
                continue
            await self._deliver(telegram, device, group_object)

    async def _deliver(
        self, telegram: Telegram, device: Device, group_object: GroupObject
    ) -> None:
        if telegram.service is Service.GROUP_WRITE:
            assert telegram.payload is not None  # guaranteed by Telegram.__post_init__
            if group_object.flags.write and group_object.apply_payload(telegram.payload):
                await device.handle_group_write(group_object)
        elif telegram.service is Service.GROUP_RESPONSE:
            assert telegram.payload is not None
            if group_object.flags.update and group_object.apply_payload(telegram.payload):
                await device.handle_group_write(group_object)
        elif telegram.service is Service.GROUP_READ:
            if group_object.flags.read:
                await device.handle_group_read(group_object)

    def _make_log_entry(self, telegram: Telegram) -> TelegramLogEntry:
        subscribers = self._subscribers.get(telegram.destination, [])
        dpt_id = subscribers[0][1].dpt_id if subscribers else None
        decoded_value: Any | None = None
        if dpt_id is not None and telegram.payload is not None:
            codec = get_codec(dpt_id)
            payload = telegram.payload
            raw = bytes([payload]) if isinstance(payload, int) else payload
            decoded_value = codec.decode(raw)
        return TelegramLogEntry(
            timestamp=time.time(),
            telegram=telegram,
            dpt_id=dpt_id,
            decoded_value=decoded_value,
        )
