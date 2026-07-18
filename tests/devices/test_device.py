from __future__ import annotations

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags


class Recorder:
    """Async send-callable test double that records every Telegram sent."""

    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


def _switch_go(name: str = "switch", *, read: bool = False, value: bool = False) -> GroupObject:
    return GroupObject(
        name=name,
        group_address=GroupAddress(1, 2, 3),
        dpt_id="1.001",
        flags=GroupObjectFlags(communication=True, read=read, transmit=True),
        value=value,
    )


class TestSend:
    async def test_send_without_bind_raises(self) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_switch_go()])
        telegram = Telegram(
            source=device.individual_address,
            destination=GroupAddress(1, 2, 3),
            service=Service.GROUP_WRITE,
            payload=1,
        )
        with pytest.raises(RuntimeError, match="not registered with a bus"):
            await device.send(telegram)

    async def test_send_after_bind_invokes_callback(self) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_switch_go()])
        recorder = Recorder()
        device.bind(recorder)
        telegram = Telegram(
            source=device.individual_address,
            destination=GroupAddress(1, 2, 3),
            service=Service.GROUP_WRITE,
            payload=1,
        )
        await device.send(telegram)
        assert recorder.sent == [telegram]


class TestRespond:
    async def test_respond_builds_group_response(self) -> None:
        go = _switch_go(value=True)
        device = Device(IndividualAddress(1, 1, 1), [go])
        recorder = Recorder()
        device.bind(recorder)

        await device.respond(go)

        assert len(recorder.sent) == 1
        sent = recorder.sent[0]
        assert sent.source == device.individual_address
        assert sent.destination == go.group_address
        assert sent.service is Service.GROUP_RESPONSE
        assert sent.payload == 1  # DPT 1.001 True -> inline int 1


class TestDefaultHandleGroupRead:
    async def test_responds_when_read_flag_set(self) -> None:
        go = _switch_go(read=True, value=True)
        device = Device(IndividualAddress(1, 1, 1), [go])
        recorder = Recorder()
        device.bind(recorder)

        await device.handle_group_read(go)

        assert len(recorder.sent) == 1
        assert recorder.sent[0].service is Service.GROUP_RESPONSE

    async def test_does_nothing_when_read_flag_not_set(self) -> None:
        go = _switch_go(read=False)
        device = Device(IndividualAddress(1, 1, 1), [go])
        recorder = Recorder()
        device.bind(recorder)

        await device.handle_group_read(go)

        assert recorder.sent == []


class TestDefaultHandleGroupWrite:
    async def test_default_is_a_no_op(self) -> None:
        go = _switch_go()
        device = Device(IndividualAddress(1, 1, 1), [go])
        recorder = Recorder()
        device.bind(recorder)

        await device.handle_group_write(go)  # must not raise

        assert recorder.sent == []


class TestLifecycleHooks:
    async def test_default_start_and_stop_are_no_ops(self) -> None:
        device = Device(IndividualAddress(1, 1, 1), [_switch_go()])
        await device.start()  # must not raise
        await device.stop()  # must not raise

    async def test_subclass_can_override_start_and_stop(self) -> None:
        events: list[str] = []

        class Tracked(Device):
            async def start(self) -> None:
                events.append("started")

            async def stop(self) -> None:
                events.append("stopped")

        device = Tracked(IndividualAddress(1, 1, 1), [_switch_go()])
        await device.start()
        await device.stop()
        assert events == ["started", "stopped"]


class TestSubclassing:
    async def test_subclass_can_override_handle_group_write(self) -> None:
        control = _switch_go("control")
        status = _switch_go("status", read=True)

        class Mirror(Device):
            async def handle_group_write(self, group_object: GroupObject) -> None:
                if group_object.name == "control":
                    status_go = self.group_objects["status"]
                    status_go.set(group_object.value)
                    await self.respond(status_go)

        device = Mirror(IndividualAddress(1, 1, 1), [control, status])
        recorder = Recorder()
        device.bind(recorder)

        control.set(True)
        await device.handle_group_write(control)

        assert status.value is True
        assert len(recorder.sent) == 1
        assert recorder.sent[0].destination == status.group_address
