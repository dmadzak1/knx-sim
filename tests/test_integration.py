"""Cross-module integration tests spanning bus + devices.

The test below is M3's stated acceptance criterion (docs/SPEC.md M3, and
docs/GUIDE.md Part 5): press the virtual wall switch, assert the lamp turns
on, and assert a status telegram shows up in the bus's telegram log.
"""

from __future__ import annotations

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.devices.switch import SwitchActuator, WallSwitch

CONTROL_GA = GroupAddress(1, 1, 1)
STATUS_GA = GroupAddress(1, 1, 2)


async def test_pressing_switch_turns_on_lamp_and_logs_status() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    try:
        wall_switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA)
        lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
        bus.register(wall_switch)
        bus.register(lamp)

        await wall_switch.press()
        await bus.join()

        assert lamp.group_objects["control"].value is True
        assert lamp.group_objects["status"].value is True

        status_entries = [e for e in bus.telegram_log if e.telegram.destination == STATUS_GA]
        assert len(status_entries) == 1
        assert status_entries[0].telegram.service is Service.GROUP_WRITE
        assert status_entries[0].decoded_value is True

        control_entries = [e for e in bus.telegram_log if e.telegram.destination == CONTROL_GA]
        assert len(control_entries) == 1
        assert control_entries[0].decoded_value is True
    finally:
        await bus.stop()


async def test_pressing_switch_again_turns_off_lamp() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    try:
        wall_switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA, initial_value=True)
        lamp = SwitchActuator(
            IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA, initial_value=True
        )
        bus.register(wall_switch)
        bus.register(lamp)

        await wall_switch.press()  # True -> False
        await bus.join()

        assert lamp.group_objects["control"].value is False
        assert lamp.group_objects["status"].value is False
    finally:
        await bus.stop()


async def test_reading_status_ga_gets_current_value() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    try:
        wall_switch = WallSwitch(IndividualAddress(1, 1, 1), CONTROL_GA)
        lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
        bus.register(wall_switch)
        bus.register(lamp)

        await wall_switch.press()
        await bus.join()

        # A third party (e.g. a test-only stand-in for an xknx client) reads
        # the status GA and should see the lamp's current value.
        await bus.inject(
            Telegram(
                source=IndividualAddress(9, 9, 9),
                destination=STATUS_GA,
                service=Service.GROUP_READ,
                payload=None,
            )
        )
        await bus.join()

        responses = [
            e.telegram
            for e in bus.telegram_log
            if e.telegram.service is Service.GROUP_RESPONSE
        ]
        assert len(responses) == 1
        assert responses[0].source == lamp.individual_address
        assert responses[0].payload == 1
    finally:
        await bus.stop()
