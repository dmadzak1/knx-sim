"""Real-network integration tests for tunneling (M5, F-IP-3/F-IP-4).

The connect/control/status and multi-client tests use a genuine,
unmodified xknx tunneling client -- this is F-IP-4's literal acceptance
test. The heartbeat cleanup test uses a raw hand-crafted connection
instead (via our own byte-verified wire format classes, see
tests/knxip/test_tunneling.py) since it specifically needs a client that
goes silent without a graceful disconnect -- not something xknx's own
client API exposes cleanly without reaching into its private internals.
"""

from __future__ import annotations

import asyncio
import socket

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
from knx_sim.knxip.frame import parse_frame
from knx_sim.knxip.hpai import HPAI
from knx_sim.knxip.server import DEFAULT_PORT, KnxIpServer
from knx_sim.knxip.tunneling import ConnectRequest, ConnectRequestInformation, ConnectResponse
from knx_sim.knxip.tunneling import ErrorCode as TunnelingErrorCode

CONTROL_GA = GroupAddress(1, 1, 1)
STATUS_GA = GroupAddress(1, 1, 2)
X_CONTROL_GA = XGroupAddress("1/1/1")
X_STATUS_GA = XGroupAddress("1/1/2")


async def test_xknx_tunnel_client_controls_lamp_and_receives_status() -> None:
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
            connection_type=ConnectionType.TUNNELING, gateway_ip="127.0.0.1"
        ),
        telegram_received_cb=on_telegram,
    )
    try:
        await xknx.start()
        assert server.active_tunnel_count == 1

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


async def test_two_xknx_tunnel_clients_concurrently() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    lamp = SwitchActuator(IndividualAddress(1, 1, 2), CONTROL_GA, STATUS_GA)
    bus.register(lamp)
    server = KnxIpServer(bus)
    await server.start()

    status_a = asyncio.Event()
    status_b = asyncio.Event()

    def on_a(telegram: XTelegram) -> None:
        if telegram.destination_address == X_STATUS_GA:
            status_a.set()

    def on_b(telegram: XTelegram) -> None:
        if telegram.destination_address == X_STATUS_GA:
            status_b.set()

    xknx_a = XKNX(
        connection_config=ConnectionConfig(
            connection_type=ConnectionType.TUNNELING, gateway_ip="127.0.0.1"
        ),
        telegram_received_cb=on_a,
    )
    xknx_b = XKNX(
        connection_config=ConnectionConfig(
            connection_type=ConnectionType.TUNNELING, gateway_ip="127.0.0.1"
        ),
        telegram_received_cb=on_b,
    )
    try:
        await xknx_a.start()
        await xknx_b.start()
        assert server.active_tunnel_count == 2

        # Client A writes; both clients (a full bus participant each) should
        # observe the lamp's resulting status telegram -- not just A.
        xknx_a.telegrams.put_nowait(
            XTelegram(destination_address=X_CONTROL_GA, payload=GroupValueWrite(DPTBinary(1)))
        )
        await xknx_a.join()

        async with asyncio.timeout(2.0):
            await status_a.wait()
        async with asyncio.timeout(2.0):
            await status_b.wait()

        assert lamp.group_objects["status"].value is True
    finally:
        await xknx_a.stop()
        await xknx_b.stop()
        await server.stop()
        await bus.stop()


async def test_heartbeat_cleanup_after_client_goes_silent() -> None:
    # Tiny timeouts so the test doesn't wait on the real 120s spec value.
    bus = Bus(delay_seconds=0.0)
    bus.start()
    server = KnxIpServer(bus, heartbeat_timeout=0.2, heartbeat_check_interval=0.05)
    await server.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", 0))
    loop = asyncio.get_running_loop()
    try:
        local_hpai = HPAI(*sock.getsockname())
        connect_request = ConnectRequest(
            control_endpoint=local_hpai,
            data_endpoint=local_hpai,
            cri=ConnectRequestInformation(),
        )
        sock.sendto(connect_request.to_knx(), ("127.0.0.1", DEFAULT_PORT))

        data = await asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=2.0)
        response = parse_frame(data)
        assert isinstance(response, ConnectResponse)
        assert response.status_code is TunnelingErrorCode.E_NO_ERROR
        assert server.active_tunnel_count == 1

        # Go silent: never send a ConnectionStateRequest heartbeat, as a
        # killed client process never would either.
        await asyncio.sleep(0.5)  # well past heartbeat_timeout + check_interval

        assert server.active_tunnel_count == 0
    finally:
        sock.close()
        await server.stop()
        await bus.stop()


async def test_tunneling_disabled_rejects_connect_request() -> None:
    # F-CLI-1's `--no-tunneling`: reject every CONNECT_REQUEST with
    # E_CONNECTION_TYPE instead of ever creating a channel.
    bus = Bus(delay_seconds=0.0)
    bus.start()
    server = KnxIpServer(bus, enable_tunneling=False)
    await server.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", 0))
    loop = asyncio.get_running_loop()
    try:
        local_hpai = HPAI(*sock.getsockname())
        connect_request = ConnectRequest(
            control_endpoint=local_hpai,
            data_endpoint=local_hpai,
            cri=ConnectRequestInformation(),
        )
        sock.sendto(connect_request.to_knx(), ("127.0.0.1", DEFAULT_PORT))

        data = await asyncio.wait_for(loop.sock_recv(sock, 1024), timeout=2.0)
        response = parse_frame(data)
        assert isinstance(response, ConnectResponse)
        assert response.status_code is TunnelingErrorCode.E_CONNECTION_TYPE
        assert server.active_tunnel_count == 0
    finally:
        sock.close()
        await server.stop()
        await bus.stop()


async def test_discovery_reflects_tunneling_disabled() -> None:
    bus = Bus(delay_seconds=0.0)
    bus.start()
    server = KnxIpServer(bus, friendly_name="knx-sim-no-tunneling", enable_tunneling=False)
    await server.start()
    try:
        scanner = GatewayScanner(XKNX(), timeout_in_seconds=2.0, stop_on_found=1)
        gateways = await scanner.scan()

        assert len(gateways) == 1
        assert gateways[0].supports_tunnelling is False
    finally:
        await server.stop()
        await bus.stop()
