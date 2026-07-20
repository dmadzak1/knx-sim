"""Tests for the CLI (F-CLI-1, M8 round A).

build()/shutdown() are exercised directly rather than run(): run() blocks
on either uvicorn.Server.serve() or a bare asyncio.Event().wait() until a
real SIGINT/SIGTERM arrives (see knx_sim/cli/main.py's docstring), neither
of which is something to drive from a test process without risking the
test runner's own signal handling. build() is the exact same startup path
run() uses, so these tests give real confidence in it -- just without the
"wait forever for Ctrl+C" part.

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
    assert running.web_server is not None
    task = asyncio.create_task(running.web_server.serve())
    await asyncio.sleep(0.3)  # let uvicorn actually bind & start accepting
    return task


class TestParseArgs:
    def test_requires_a_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args([])

    def test_run_requires_a_config_argument(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args(["run"])

    def test_run_accepts_a_config_path(self) -> None:
        args = _parse_args(["run", "examples/demo-house.yaml"])
        assert args.command == "run"
        assert args.config == "examples/demo-house.yaml"

    def test_run_defaults(self) -> None:
        args = _parse_args(["run", "x.yaml"])
        assert args.log_level == "INFO"
        assert args.web_port is None
        assert args.no_web is False
        assert args.no_routing is False
        assert args.no_tunneling is False

    def test_run_accepts_all_flags(self) -> None:
        args = _parse_args(
            [
                "run",
                "x.yaml",
                "--log-level",
                "DEBUG",
                "--web-port",
                "9000",
                "--no-web",
                "--no-routing",
                "--no-tunneling",
            ]
        )
        assert args.log_level == "DEBUG"
        assert args.web_port == 9000
        assert args.no_web is True
        assert args.no_routing is True
        assert args.no_tunneling is True

    def test_run_rejects_an_unknown_log_level(self) -> None:
        with pytest.raises(SystemExit):
            _parse_args(["run", "x.yaml", "--log-level", "VERBOSE"])


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
            assert running.web_server is not None
            assert running.web_server.config.host == "127.0.0.1"
            assert running.web_server.config.port == DEFAULT_WEB_PORT
        finally:
            await shutdown(running)

    async def test_web_port_is_configurable_via_yaml(self, tmp_path: Path) -> None:
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
            assert running.web_server is not None
            assert running.web_server.config.port == 8099
        finally:
            await shutdown(running)

    async def test_web_port_override_takes_priority_over_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "custom-port.yaml"
        config_file.write_text(
            "simulator:\n  web_port: 8099\n"
            "devices:\n"
            "  - type: wall_switch\n"
            "    individual_address: '1.1.1'\n"
            "    control_ga: '1/1/1'\n"
        )
        running = await build(config_file, web_port_override=8199)
        try:
            assert running.web_server is not None
            assert running.web_server.config.port == 8199
        finally:
            await shutdown(running)

    async def test_no_web_disables_the_web_server(self) -> None:
        running = await build(EXAMPLES_DIR / "minimal.yaml", enable_web=False)
        try:
            assert running.web_server is None
        finally:
            await shutdown(running)

    async def test_no_routing_and_no_tunneling_are_threaded_through(self) -> None:
        running = await build(
            EXAMPLES_DIR / "minimal.yaml", enable_routing=False, enable_tunneling=False
        )
        try:
            # KnxIpServer's own behavior under these flags is exercised
            # end-to-end with real xknx clients in
            # tests/test_knxip_integration.py and
            # tests/test_knxip_tunnel_integration.py -- this just confirms
            # build() actually passes the flags down rather than dropping
            # them.
            assert running.simulator.server._enable_routing is False
            assert running.simulator.server._enable_tunneling is False
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
        assert running.web_server is not None
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
