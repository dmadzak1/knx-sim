"""M6's own acceptance test (docs/SPEC.md M6 "Done when"): demo-house.yaml
boots a 10-device house and a genuine xknx client can operate every device
type.

Loads examples/demo-house.yaml through the real config pipeline (loader +
registry -- no test-only shortcuts), starts a real KnxIpServer over a real
xknx tunneling connection, and drives one representative interaction per
device type: wall_switch (a locally-triggered "physical press", observed by
the external client), switch actuator (write + status), dimmer (write +
switch/brightness status), blind (move + stop), thermostat (setpoint
write), presence sensor (GroupValueRead -> GroupValueResponse, F-DEV-8).

Every group address we assert on is registered as an asyncio.Event *before*
the action that triggers it, avoiding the race of a telegram arriving
before anyone's listening for it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from xknx import XKNX
from xknx.dpt.dpt_9 import DPTTemperature
from xknx.dpt.payload import DPTBinary
from xknx.io import ConnectionConfig, ConnectionType
from xknx.telegram import GroupAddress as XGroupAddress
from xknx.telegram import Telegram as XTelegram
from xknx.telegram.apci import GroupValueRead, GroupValueWrite

from knx_sim.cemi.address import IndividualAddress
from knx_sim.config.loader import build_simulator, load_installation_file
from knx_sim.devices.device import Device
from knx_sim.devices.switch import WallSwitch

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

WATCHED_GAS = ["1/2/1", "1/2/2", "1/1/13", "1/1/24", "1/2/40"]


async def test_demo_house_boots_and_xknx_operates_every_device_type() -> None:
    config = load_installation_file(EXAMPLES_DIR / "demo-house.yaml")
    assert len(config.devices) == 10

    simulator = build_simulator(config)
    simulator.bus.start()
    await simulator.server.start()

    def find(individual_address: str) -> Device:
        ia = IndividualAddress.from_string(individual_address)
        return next(d for d in simulator.devices if d.individual_address == ia)

    events = {XGroupAddress(ga): asyncio.Event() for ga in WATCHED_GAS}

    def on_telegram(telegram: XTelegram) -> None:
        destination = telegram.destination_address
        if not isinstance(destination, XGroupAddress):
            return
        event = events.get(destination)
        if event is not None:
            event.set()

    async def wait_for(ga: str) -> None:
        async with asyncio.timeout(2.0):
            await events[XGroupAddress(ga)].wait()

    xknx = XKNX(
        connection_config=ConnectionConfig(
            connection_type=ConnectionType.TUNNELING, gateway_ip="127.0.0.1"
        ),
        telegram_received_cb=on_telegram,
    )
    try:
        await xknx.start()

        # --- wall_switch (F-DEV-6): a locally-triggered "physical press",
        # not an xknx write -- verifies the external client observes a
        # device-initiated telegram just like any bus participant would.
        wall_switch = find("1.2.1")
        assert isinstance(wall_switch, WallSwitch)
        await wall_switch.press()
        await wait_for("1/2/1")
        assert wall_switch.group_objects["control"].value is True

        # --- switch actuator (F-DEV-1): the bedroom lamp shares its control
        # GA with the wall switch above, so it reacts to the same press.
        lamp = find("1.2.2")
        await wait_for("1/2/2")
        assert lamp.group_objects["status"].value is True

        # --- dimmer (F-DEV-2): switch ON should drive both status objects.
        dimmer = find("1.1.3")
        xknx.telegrams.put_nowait(
            XTelegram(
                destination_address=XGroupAddress("1/1/10"),
                payload=GroupValueWrite(DPTBinary(1)),
            )
        )
        await xknx.join()
        await wait_for("1/1/13")
        assert dimmer.group_objects["switch_status"].value is True
        assert dimmer.group_objects["brightness_status"].value == 100.0

        # --- blind (F-DEV-3): move down starts travel, stop halts it.
        blind = find("1.1.4")
        xknx.telegrams.put_nowait(
            XTelegram(
                destination_address=XGroupAddress("1/1/20"),
                payload=GroupValueWrite(DPTBinary(1)),
            )
        )
        await xknx.join()
        await wait_for("1/1/24")
        assert blind.group_objects["moving_status"].value is True

        # "stop" starts at value=False; the bus only calls
        # handle_group_write on an actual value change (GroupObject.set()'s
        # change detection), so the write must flip it to True to fire --
        # BlindActuator treats any stop write as "halt", regardless of bit.
        events[XGroupAddress("1/1/24")].clear()
        xknx.telegrams.put_nowait(
            XTelegram(
                destination_address=XGroupAddress("1/1/21"),
                payload=GroupValueWrite(DPTBinary(1)),
            )
        )
        await xknx.join()
        await wait_for("1/1/24")
        assert blind.group_objects["moving_status"].value is False

        # --- thermostat (F-DEV-4): setpoint write updates state directly
        # (no handle_group_write override -- the next physics tick would
        # read it, but the write itself produces no status telegram, so
        # there's nothing to wait for beyond the bus's own propagation
        # delay).
        thermostat = find("1.1.5")
        xknx.telegrams.put_nowait(
            XTelegram(
                destination_address=XGroupAddress("1/1/31"),
                payload=GroupValueWrite(DPTTemperature.to_knx(22.5)),
            )
        )
        await xknx.join()
        await asyncio.sleep(0.2)  # margin over the bus's propagation delay
        assert thermostat.group_objects["setpoint"].value == pytest.approx(22.5, abs=0.02)

        # --- presence sensor (F-DEV-5 / F-DEV-8): GroupValueRead is
        # answered with the current (default False) value.
        xknx.telegrams.put_nowait(
            XTelegram(destination_address=XGroupAddress("1/2/40"), payload=GroupValueRead())
        )
        await xknx.join()
        await wait_for("1/2/40")
    finally:
        await xknx.stop()
        await simulator.server.stop()
        await simulator.bus.stop()
