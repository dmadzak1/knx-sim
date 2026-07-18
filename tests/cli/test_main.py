"""Tests for the minimal CLI launcher (F-CLI-1, partial, M7 round C).

build()/shutdown() are exercised directly rather than main()/run(): run()
blocks on uvicorn.Server.serve() until a real SIGINT/SIGTERM arrives (see
knx_sim/cli/main.py's docstring), which isn't something to drive from a
test process without risking the test runner's own signal handling.
build() is the exact same startup path run() uses, so these tests give
real confidence in it -- just without the "wait forever for Ctrl+C" part.

Reuses this project's established real-network pattern (a real
uvicorn.Server + real clients on one event loop, see tests/web/test_ws.py
and tests/test_demo_house_e2e.py) since that's exactly what build() itself
produces.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from xknx import XKNX
from xknx.dpt.payload import DPTBinary
from xknx.io import ConnectionConfig, ConnectionType
from xknx.telegram import GroupAddress as XGroupAddress
from xknx.telegram import Telegram as XTelegram
from xknx.telegram.apci import GroupValueWrite

from knx_sim.cemi.address import IndividualAddress
from knx_sim.cli.main import RunningApp, _parse_args, build, shutdown
from knx_sim.config.models import DEFAULT_WEB_PORT

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


async def _serve(running: RunningApp) -> asyncio.Task[None]:
    task = asyncio.create_task(running.web_server.serve())
    await asyncio.sleep(0.3)  # let uvicorn actually bind & start accepting
    return task


class TestParseArgs:
    def test_requires_a_config_argument(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args([])

    def test_accepts_a_config_path(self) -> None:
        args = _parse_args(["examples/demo-house.yaml"])
        assert args.config == "examples/demo-house.yaml"


class TestBuild:
    async def test_wires_devices_from_config(self) -> None:
        running = await build(EXAMPLES_DIR / "minimal.yaml")
        try:
            assert len(running.simulator.devices) == 2
            assert running.simulator.bus.has_device(IndividualAddress(1, 1, 1))
            assert running.simulator.bus.has_device(IndividualAddress(1, 1, 2))
        finally:
            await shutdown(running)

    async def test_starts_the_knxip_server(self) -> None:
        running = await build(EXAMPLES_DIR / "minimal.yaml")
        try:
            # bind_address raises until start() has resolved it -- build()
            # already awaits server.start(), so this must not raise.
            assert running.simulator.server.bind_address
            assert running.simulator.server.active_tunnel_count == 0
        finally:
            await shutdown(running)

    async def test_web_server_binds_to_localhost_on_the_configured_port(self) -> None:
        running = await build(EXAMPLES_DIR / "minimal.yaml")
        try:
            assert running.web_server.config.host == "127.0.0.1"
            assert running.web_server.config.port == DEFAULT_WEB_PORT
        finally:
            await shutdown(running)

    async def test_web_port_is_configurable(self, tmp_path: Path) -> None:
        config_file = tmp_path / "custom-port.yaml"
        config_file.write_text(
            "simulator:\n  web_port: 8099\n"
            "devices:\n"
            "  - type: wall_switch\n"
            "    individual_address: '1.1.1'\n"
            "    control_ga: '1/1/1'\n"
        )
        running = await build(config_file)
        try:
            assert running.web_server.config.port == 8099
        finally:
            await shutdown(running)

    async def test_shutdown_stops_bus_and_server_cleanly(self) -> None:
        running = await build(EXAMPLES_DIR / "minimal.yaml")
        await shutdown(running)  # must not raise or hang


class TestEndToEnd:
    async def test_xknx_write_is_visible_via_the_web_dashboard(self) -> None:
        # Proves the CLI's own wiring, not device/DPT behavior (that's
        # covered exhaustively by tests/test_demo_house_e2e.py): a write
        # from a real xknx tunneling client through the CLI-launched
        # KNXnet/IP server shows up when the CLI-launched web dashboard is
        # asked for device state -- the same "both views stay consistent"
        # property M7's own done-when criterion cares about.
        running = await build(EXAMPLES_DIR / "minimal.yaml")
        web_task = await _serve(running)
        xknx = XKNX(
            connection_config=ConnectionConfig(
                connection_type=ConnectionType.TUNNELING, gateway_ip="127.0.0.1"
            )
        )
        try:
            await xknx.start()
            try:
                xknx.telegrams.put_nowait(
                    XTelegram(
                        destination_address=XGroupAddress("1/1/1"),
                        payload=GroupValueWrite(DPTBinary(1)),
                    )
                )
                await xknx.join()
                await asyncio.sleep(0.2)  # margin over the bus's propagation delay

                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{running.web_server.config.port}"
                ) as client:
                    response = await client.get("/api/devices")
                devices = response.json()
                lamp = next(d for d in devices if d["individual_address"] == "1.1.2")
                assert lamp["group_objects"]["status"]["value"] is True
            finally:
                await xknx.stop()
        finally:
            running.web_server.should_exit = True
            await web_task
            await shutdown(running)
