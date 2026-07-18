"""Real-network integration tests: a genuine xknx client, over real UDP
multicast on localhost, against our real KnxIpServer.

This is M4's literal acceptance test (docs/SPEC.md M4 "Done when": "xknx
discovers the simulator via SEARCH and switches the virtual lamp over
multicast routing") and NFR-2 ("integration tests use a real xknx client
against a spawned server"). Unlike every other test in this project, these
touch real sockets -- keep this file's scope to exactly what the acceptance
criterion needs.
"""

from __future__ import annotations

import asyncio

from xknx import XKNX
from xknx.dpt.payload import DPTBinary
from xknx.io import ConnectionConfig, ConnectionType
from xknx.io.gateway_scanner import GatewayScanner
from xknx.telegram import GroupAddress as XGroupAddress
from xknx.telegram import Telegram as XTelegram
from xknx.telegram.apci import GroupValueWrite

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.devices.switch import SwitchActuator
from knx_sim.knxip.server import KnxIpServer

CONTROL_GA = GroupAddress(1, 1, 1)
STATUS_GA = GroupAddress(1, 1, 2)
X_CONTROL_GA = XGroupAddress("1/1/1")
X_STATUS_GA = XGroupAddress("1/1/2")


async def test_xknx_discovers_server_via_search() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    server = KnxIpServer(bus, friendly_name="knx-sim-test")
    await server.start()
    try:
        scanner = GatewayScanner(XKNX(), timeout_in_seconds=2.0, stop_on_found=1)
        gateways = await scanner.scan()

        assert len(gateways) == 1
        assert gateways[0].name == "knx-sim-test"
        assert gateways[0].supports_routing is True
    finally:
        await server.stop()
        await bus.stop()


async def test_xknx_routing_client_controls_lamp_and_receives_status() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
    bus.register(lamp)
    server = KnxIpServer(bus)
    await server.start()

    status_received = asyncio.Event()
    received: list[XTelegram] = []

    def on_telegram(telegram: XTelegram) -> None:
        received.append(telegram)
        if telegram.destination_address == X_STATUS_GA:
            status_received.set()

    xknx = XKNX(
        connection_config=ConnectionConfig(
            connection_type=ConnectionType.ROUTING,
            individual_address="15.15.250",
        ),
        telegram_received_cb=on_telegram,
    )
    try:
        await xknx.start()

        xknx.telegrams.put_nowait(
            XTelegram(destination_address=X_CONTROL_GA, payload=GroupValueWrite(DPTBinary(1)))
        )
        await xknx.join()

        async with asyncio.timeout(2.0):
            await status_received.wait()

        assert lamp.group_objects["control"].value is True
        assert lamp.group_objects["status"].value is True

        status_updates = [t for t in received if t.destination_address == X_STATUS_GA]
        assert len(status_updates) == 1
        assert status_updates[0].payload == GroupValueWrite(DPTBinary(1))
    finally:
        await xknx.stop()
        await server.stop()
        await bus.stop()
