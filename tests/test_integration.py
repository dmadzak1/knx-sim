"""Cross-module integration tests spanning bus + devices.

The test below is M3's stated acceptance criterion (docs/SPEC.md M3, and
docs/GUIDE.md Part 5): press the virtual wall switch, assert the lamp turns
on, and assert a status telegram shows up in the bus's telegram log.
"""

from __future__ import annotations

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.devices.blind import BlindActuator
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.devices.switch import SwitchActuator, WallSwitch
from knx_sim.dpt import get_codec

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


async def test_blind_move_command_restarts_travel_after_a_stop() -> None:
    # Regression test: Bus._deliver() used to only deliver a GroupValueWrite
    # to a device when the decoded value actually differed from the group
    # object's cached value. "move" doesn't reset after a stop, so a second
    # "move down" (same True value as the first) would be silently dropped
    # by the bus before BlindActuator ever saw it -- the blind would get
    # stuck un-restartable after its first stop. Fixed by always delivering
    # a write that passes the flag gate, regardless of value change.
    move_ga = GroupAddress(2, 1, 1)
    stop_ga = GroupAddress(2, 1, 2)
    position_ga = GroupAddress(2, 1, 3)
    position_status_ga = GroupAddress(2, 1, 4)
    moving_status_ga = GroupAddress(2, 1, 5)

    bus = Bus(delay_seconds=0.0)
    bus.start()
    try:
        blind = BlindActuator(
            IndividualAddress(2, 1, 9),
            move_ga,
            stop_ga,
            position_ga,
            position_status_ga,
            moving_status_ga,
        )
        bus.register(blind)

        async def move_down() -> None:
            await bus.inject(
                Telegram(
                    source=IndividualAddress(9, 9, 9),
                    destination=move_ga,
                    service=Service.GROUP_WRITE,
                    payload=1,
                )
            )
            await bus.join()

        async def stop() -> None:
            await bus.inject(
                Telegram(
                    source=IndividualAddress(9, 9, 9),
                    destination=stop_ga,
                    service=Service.GROUP_WRITE,
                    payload=1,
                )
            )
            await bus.join()

        await move_down()
        assert blind.group_objects["moving_status"].value is True

        await stop()
        assert blind.group_objects["moving_status"].value is False

        await move_down()  # same True value as the first move_down()
        assert blind.group_objects["moving_status"].value is True
    finally:
        await blind.stop()
        await bus.stop()


async def test_dimmer_switch_write_turns_off_even_if_only_brightness_was_ever_written() -> None:
    # Regression test: writing "brightness" directly (as a slider control
    # would) never touches the separate "switch" group object's own cached
    # value -- it stays at its constructor default. Before the same fix as
    # above, writing to "switch" afterward could be silently dropped by the
    # bus if that write happened to match "switch"'s stale cached value,
    # even though the dimmer was clearly on (non-zero brightness).
    switch_ga = GroupAddress(2, 2, 1)
    relative_dim_ga = GroupAddress(2, 2, 2)
    brightness_ga = GroupAddress(2, 2, 3)
    switch_status_ga = GroupAddress(2, 2, 4)
    brightness_status_ga = GroupAddress(2, 2, 5)

    bus = Bus(delay_seconds=0.0)
    bus.start()
    try:
        dimmer = DimmerActuator(
            IndividualAddress(2, 2, 9),
            switch_ga,
            relative_dim_ga,
            brightness_ga,
            switch_status_ga,
            brightness_status_ga,
        )
        bus.register(dimmer)
        # "switch" starts False (initial_brightness=0.0) and is never
        # written to directly -- only "brightness" is.
        assert dimmer.group_objects["switch"].value is False

        await bus.inject(
            Telegram(
                source=IndividualAddress(9, 9, 9),
                destination=brightness_ga,
                service=Service.GROUP_WRITE,
                payload=get_codec("5.001").encode(50.0),
            )
        )
        await bus.join()
        assert dimmer.group_objects["switch_status"].value is True
        assert dimmer.group_objects["switch"].value is False  # still untouched

        # Now turn off via "switch" -- its own cached value is still False,
        # and we're writing False again, which used to be silently dropped.
        await bus.inject(
            Telegram(
                source=IndividualAddress(9, 9, 9),
                destination=switch_ga,
                service=Service.GROUP_WRITE,
                payload=0,
            )
        )
        await bus.join()

        assert dimmer.group_objects["switch_status"].value is False
        assert dimmer.group_objects["brightness_status"].value == 0.0
    finally:
        await bus.stop()
