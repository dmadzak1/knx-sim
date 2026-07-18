"""Tests for the dashboard's WebSocket telegram stream (F-WEB-2).

Uses a real uvicorn server + the real `websockets` client library, all on
one event loop -- matching this project's established real-network
integration-test convention (see tests/test_knxip_integration.py) rather
than FastAPI's synchronous TestClient. TestClient's WebSocket support runs
the ASGI app in a separate thread with its own event loop (an anyio
"blocking portal"), which would put Bus's internals (created wherever
build_simulator() runs, since Bus.register() needs a running loop for
asyncio.create_task) on a different loop than the one actually handling
requests -- untested and unnecessary risk when a real server+client on a
single loop is simple and proven to work.

Also confirmed empirically while building this: a send-only WebSocket
handler (no concurrent receive loop) never notices client disconnection,
which then deadlocks graceful server shutdown waiting for the handler to
finish -- this is *why* app.py's /ws endpoint runs a receiver() task
purely to detect disconnects, not just a nice-to-have.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import uvicorn
import websockets

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.config.loader import Simulator, build_simulator, load_installation_file
from knx_sim.web.app import create_app

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
WS_PORT = 18901
WS_URL = f"ws://127.0.0.1:{WS_PORT}/ws"


@pytest.fixture
async def running_dashboard() -> AsyncIterator[Simulator]:
    config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
    simulator = build_simulator(config)
    simulator.bus.start()

    app = create_app(simulator)
    server_config = uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="warning")
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.3)  # let the server bind & start accepting
    try:
        yield simulator
    finally:
        server.should_exit = True
        await server_task
        await simulator.bus.stop()


async def test_streams_a_telegram_after_injection(running_dashboard: Simulator) -> None:
    async with websockets.connect(WS_URL) as client:
        await asyncio.sleep(0.2)  # let the handler reach bus.subscribe()
        await running_dashboard.bus.inject(
            Telegram(
                source=IndividualAddress(1, 1, 9),
                destination=GroupAddress(1, 1, 1),
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        raw = await asyncio.wait_for(client.recv(), timeout=2.0)
        message = json.loads(raw)

    assert message["type"] == "telegram"
    assert message["data"]["destination"] == "1/1/1"
    assert message["data"]["service"] == "write"
    assert message["data"]["dpt_id"] == "1.001"
    assert message["data"]["value"] is True


async def test_streams_every_resulting_telegram(running_dashboard: Simulator) -> None:
    # The injected write to the wall switch's shared control GA also
    # triggers the lamp's status mirror -- both should appear on the stream.
    async with websockets.connect(WS_URL) as client:
        await asyncio.sleep(0.2)
        await running_dashboard.bus.inject(
            Telegram(
                source=IndividualAddress(1, 1, 9),
                destination=GroupAddress(1, 1, 1),
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        first = json.loads(await asyncio.wait_for(client.recv(), timeout=2.0))
        second = json.loads(await asyncio.wait_for(client.recv(), timeout=2.0))

    destinations = {first["data"]["destination"], second["data"]["destination"]}
    assert destinations == {"1/1/1", "1/1/2"}


async def test_multiple_clients_all_receive(running_dashboard: Simulator) -> None:
    async with websockets.connect(WS_URL) as client_a, websockets.connect(WS_URL) as client_b:
        await asyncio.sleep(0.2)
        await running_dashboard.bus.inject(
            Telegram(
                source=IndividualAddress(1, 1, 9),
                destination=GroupAddress(1, 1, 1),
                service=Service.GROUP_WRITE,
                payload=1,
            )
        )
        message_a = json.loads(await asyncio.wait_for(client_a.recv(), timeout=2.0))
        message_b = json.loads(await asyncio.wait_for(client_b.recv(), timeout=2.0))

    assert message_a["data"]["destination"] == "1/1/1"
    assert message_b["data"]["destination"] == "1/1/1"


async def test_disconnecting_client_unsubscribes_from_the_bus(
    running_dashboard: Simulator,
) -> None:
    async with websockets.connect(WS_URL):
        await asyncio.sleep(0.2)
        assert len(running_dashboard.bus._monitors) == 1

    await asyncio.sleep(0.2)  # let the server notice the disconnect and clean up
    assert len(running_dashboard.bus._monitors) == 0
