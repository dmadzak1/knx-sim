from __future__ import annotations

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.devices.switch import SwitchActuator, WallSwitch

CONTROL_GA = GroupAddress(1, 1, 1)
STATUS_GA = GroupAddress(1, 1, 2)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


class TestSwitchActuator:
    def test_group_objects_and_initial_value(self) -> None:
        lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
        assert lamp.group_objects["control"].group_address == CONTROL_GA
        assert lamp.group_objects["status"].group_address == STATUS_GA
        assert lamp.group_objects["control"].value is False
        assert lamp.group_objects["status"].value is False

    def test_initial_value_override(self) -> None:
        lamp = SwitchActuator(
            IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA, initial_value=True
        )
        assert lamp.group_objects["control"].value is True
        assert lamp.group_objects["status"].value is True

    async def test_control_write_mirrors_to_status_and_transmits(self) -> None:
        lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
        recorder = Recorder()
        lamp.bind(recorder)

        control = lamp.group_objects["control"]
        control.set(True)
        await lamp.handle_group_write(control)

        assert lamp.group_objects["status"].value is True
        assert len(recorder.sent) == 1
        sent = recorder.sent[0]
        assert sent.destination == STATUS_GA
        assert sent.service is Service.GROUP_WRITE
        assert sent.payload == 1

    async def test_ignores_writes_to_other_group_objects(self) -> None:
        lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
        recorder = Recorder()
        lamp.bind(recorder)

        await lamp.handle_group_write(lamp.group_objects["status"])

        assert recorder.sent == []

    async def test_no_retransmit_when_status_already_matches(self) -> None:
        lamp = SwitchActuator(
            IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA, initial_value=True
        )
        recorder = Recorder()
        lamp.bind(recorder)

        control = lamp.group_objects["control"]
        control.set(True)  # already True -- no-op
        await lamp.handle_group_write(control)

        assert recorder.sent == []


class TestWallSwitch:
    def test_group_object(self) -> None:
        switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA)
        assert switch.group_objects["control"].group_address == CONTROL_GA
        assert switch.group_objects["control"].value is False

    async def test_press_toggles_and_transmits(self) -> None:
        switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA)
        recorder = Recorder()
        switch.bind(recorder)

        await switch.press()

        assert switch.group_objects["control"].value is True
        assert len(recorder.sent) == 1
        sent = recorder.sent[0]
        assert sent.destination == CONTROL_GA
        assert sent.service is Service.GROUP_WRITE
        assert sent.payload == 1

    async def test_second_press_toggles_back(self) -> None:
        switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA)
        recorder = Recorder()
        switch.bind(recorder)

        await switch.press()
        await switch.press()

        assert switch.group_objects["control"].value is False
        assert len(recorder.sent) == 2
        assert recorder.sent[1].payload == 0
