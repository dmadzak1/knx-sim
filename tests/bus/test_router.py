from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Priority, Service, Telegram
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags


def _go(
    name: str,
    ga: GroupAddress,
    *,
    dpt_id: str = "1.001",
    value: object = False,
    communication: bool = True,
    read: bool = False,
    write: bool = False,
    update: bool = False,
    transmit: bool = False,
) -> GroupObject:
    return GroupObject(
        name=name,
        group_address=ga,
        dpt_id=dpt_id,
        flags=GroupObjectFlags(
            communication=communication, read=read, write=write, update=update, transmit=transmit
        ),
        value=value,
    )


GA = GroupAddress(1, 2, 3)


@pytest.fixture
async def bus() -> AsyncGenerator[Bus]:
    b = Bus(delay_seconds=0.0)
    b.start()
    yield b
    await b.stop()


class TestRegister:
    async def test_duplicate_individual_address_raises(self, bus: Bus) -> None:
        addr = IndividualAddress(1, 1, 1)
        bus.register(Device(addr, [_go("a", GA, write=True)]))
        with pytest.raises(ValueError, match="already registered"):
            bus.register(Device(addr, [_go("b", GA, write=True)]))

    async def test_device_can_send_after_registration(self, bus: Bus) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)])
        bus.register(device)
        telegram = Telegram(
            source=device.individual_address,
            destination=GA,
            service=Service.GROUP_WRITE,
            payload=1,
        )
        await device.send(telegram)  # must not raise
        await bus.join()

    async def test_has_device(self, bus: Bus) -> None:
        registered = IndividualAddress(1, 1, 1)
        unregistered = IndividualAddress(9, 9, 9)
        bus.register(Device(registered, [_go("a", GA, write=True)]))

        assert bus.has_device(registered) is True
        assert bus.has_device(unregistered) is False


class TestDeviceLifecycle:
    async def test_register_starts_the_device(self, bus: Bus) -> None:
        started = asyncio.Event()

        class Tracked(Device):
            async def start(self) -> None:
                started.set()

        # register() schedules start() as an independent background task
        # (not through the bus's telegram queue), so bus.join() wouldn't
        # synchronize with it -- wait on the event directly instead.
        bus.register(Tracked(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)]))
        async with asyncio.timeout(1.0):
            await started.wait()

    async def test_bus_stop_stops_registered_devices(self) -> None:
        stopped = []

        class Tracked(Device):
            async def stop(self) -> None:
                stopped.append(self)

        b = Bus(delay_seconds=0.0)
        b.start()
        b.register(Tracked(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)]))
        await b.stop()
        assert len(stopped) == 1


class TestWriteRouting:
    async def test_delivered_to_write_flagged_subscriber(self, bus: Bus) -> None:
        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, write=True, value=False)
        receiver = Device(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert receiver_go.value is True

    async def test_not_delivered_without_write_flag(self, bus: Bus) -> None:
        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, write=False, value=False)
        receiver = Device(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert receiver_go.value is False

    async def test_not_delivered_without_communication_flag(self, bus: Bus) -> None:
        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, write=True, communication=False, value=False)
        receiver = Device(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert receiver_go.value is False

    async def test_not_delivered_back_to_sender(self, bus: Bus) -> None:
        addr = IndividualAddress(1, 1, 1)
        own_go = _go("status", GA, write=True, value=False)
        device = Device(addr, [own_go])
        bus.register(device)

        await bus.inject(
            Telegram(source=addr, destination=GA, service=Service.GROUP_WRITE, payload=1)
        )
        await bus.join()

        assert own_go.value is False  # never delivered to its own sender

    async def test_handle_group_write_called_only_on_change(self, bus: Bus) -> None:
        calls: list[GroupObject] = []

        class Recorder(Device):
            async def handle_group_write(self, group_object: GroupObject) -> None:
                calls.append(group_object)

        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, write=True, value=True)  # already True
        receiver = Recorder(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,  # same value (True) -- no change
            )
        )
        await bus.join()
        assert calls == []

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=0,  # now it changes
            )
        )
        await bus.join()
        assert calls == [receiver_go]


class TestResponseRouting:
    async def test_delivered_to_update_flagged_subscriber(self, bus: Bus) -> None:
        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, update=True, value=False)
        receiver = Device(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_RESPONSE,
                payload=1,
            )
        )
        await bus.join()

        assert receiver_go.value is True

    async def test_not_delivered_without_update_flag(self, bus: Bus) -> None:
        sender = Device(IndividualAddress(1, 1, 1), [])
        receiver_go = _go("status", GA, update=False, write=True, value=False)
        receiver = Device(IndividualAddress(1, 1, 2), [receiver_go])
        bus.register(sender)
        bus.register(receiver)

        await bus.inject(
            Telegram(
                source=sender.individual_address,
                destination=GA,
                service=Service.GROUP_RESPONSE,
                payload=1,
            )
        )
        await bus.join()

        assert receiver_go.value is False


class TestReadRouting:
    async def test_read_flagged_subscriber_responds(self, bus: Bus) -> None:
        requester = Device(IndividualAddress(1, 1, 1), [])
        answerer_go = _go("status", GA, read=True, value=True)
        answerer = Device(IndividualAddress(1, 1, 2), [answerer_go])
        bus.register(requester)
        bus.register(answerer)

        received: list[Telegram] = []

        async def monitor(telegram: Telegram) -> None:
            received.append(telegram)

        bus.subscribe(monitor)

        await bus.inject(
            Telegram(
                source=requester.individual_address,
                destination=GA,
                service=Service.GROUP_READ,
                payload=None,
            )
        )
        await bus.join()

        responses = [t for t in received if t.service is Service.GROUP_RESPONSE]
        assert len(responses) == 1
        assert responses[0].source == answerer.individual_address
        assert responses[0].payload == 1

    async def test_not_answered_without_read_flag(self, bus: Bus) -> None:
        requester = Device(IndividualAddress(1, 1, 1), [])
        silent_go = _go("status", GA, read=False, value=True)
        silent = Device(IndividualAddress(1, 1, 2), [silent_go])
        bus.register(requester)
        bus.register(silent)

        received: list[Telegram] = []

        async def monitor(telegram: Telegram) -> None:
            received.append(telegram)

        bus.subscribe(monitor)

        await bus.inject(
            Telegram(
                source=requester.individual_address,
                destination=GA,
                service=Service.GROUP_READ,
                payload=None,
            )
        )
        await bus.join()

        assert len(received) == 1  # only the original read, no response


class TestMonitor:
    async def test_subscribe_receives_every_processed_telegram(self, bus: Bus) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)])
        bus.register(device)

        seen: list[Telegram] = []

        async def monitor(telegram: Telegram) -> None:
            seen.append(telegram)

        bus.subscribe(monitor)

        telegram = Telegram(
            source=IndividualAddress(9, 9, 9),
            destination=GA,
            service=Service.GROUP_WRITE,
            payload=1,
        )
        await bus.inject(telegram)
        await bus.join()

        assert seen == [telegram]

    async def test_unsubscribe_stops_notifications(self, bus: Bus) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)])
        bus.register(device)

        seen: list[Telegram] = []

        async def monitor(telegram: Telegram) -> None:
            seen.append(telegram)

        bus.subscribe(monitor)
        bus.unsubscribe(monitor)

        await bus.inject(
            Telegram(
                source=IndividualAddress(9, 9, 9),
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert seen == []


class TestTelegramLog:
    async def test_processed_telegram_is_logged_with_decoded_value(self, bus: Bus) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_go("a", GA, write=True)])
        bus.register(device)

        await bus.inject(
            Telegram(
                source=IndividualAddress(9, 9, 9),
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert len(bus.telegram_log) == 1
        entry = bus.telegram_log[0]
        assert entry.dpt_id == "1.001"
        assert entry.decoded_value is True

    async def test_unresolvable_dpt_logs_none(self, bus: Bus) -> None:
        # No device subscribed to this GA at all.
        other_ga = GroupAddress(9, 1, 9)
        await bus.inject(
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=other_ga,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        entry = bus.telegram_log[0]
        assert entry.dpt_id is None
        assert entry.decoded_value is None

    async def test_log_is_capped(self) -> None:
        small_bus = Bus(delay_seconds=0.0, log_size=2)
        small_bus.start()
        try:
            for _ in range(5):
                await small_bus.inject(
                    Telegram(
                        source=IndividualAddress(1, 1, 1),
                        destination=GA,
                        service=Service.GROUP_READ,
                        payload=None,
                    )
                )
            await small_bus.join()
            assert len(small_bus.telegram_log) == 2
        finally:
            await small_bus.stop()


class TestPriorityOrdering:
    async def test_higher_priority_processed_first(self) -> None:
        # Don't start the bus yet -- queue several telegrams at different
        # priorities first, then start, so ordering is exercised.
        b = Bus(delay_seconds=0.0)
        order: list[str] = []

        device = Device(IndividualAddress(1, 1, 2), [_go("a", GA, write=True)])
        b.register(device)

        async def monitor(telegram: Telegram) -> None:
            order.append(telegram.priority.name)

        b.subscribe(monitor)

        sender = IndividualAddress(1, 1, 1)
        for priority in (Priority.LOW, Priority.NORMAL, Priority.SYSTEM, Priority.URGENT):
            await b.inject(
                Telegram(
                    source=sender,
                    destination=GA,
                    service=Service.GROUP_WRITE,
                    payload=1,
                    priority=priority,
                )
            )

        b.start()
        await b.join()
        await b.stop()

        assert order == ["SYSTEM", "URGENT", "NORMAL", "LOW"]


class TestMultiHop:
    async def test_write_triggers_cascaded_status_telegram(self, bus: Bus) -> None:
        control = _go("control", GA, write=True, value=False)
        status_ga = GroupAddress(1, 2, 4)
        status = _go("status", status_ga, read=True, value=False)

        class Mirror(Device):
            async def handle_group_write(self, group_object: GroupObject) -> None:
                if group_object.name == "control":
                    status.set(group_object.value)
                    await self.respond(status)

        lamp = Mirror(IndividualAddress(1, 1, 2), [control, status])
        bus.register(lamp)

        seen: list[Telegram] = []

        async def monitor(telegram: Telegram) -> None:
            seen.append(telegram)

        bus.subscribe(monitor)

        await bus.inject(
            Telegram(
                source=IndividualAddress(1, 1, 1),
                destination=GA,
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        await bus.join()

        assert control.value is True
        assert status.value is True
        assert len(seen) == 2  # the original write + the cascaded response
        assert seen[1].destination == status_ga
        assert seen[1].service is Service.GROUP_RESPONSE
