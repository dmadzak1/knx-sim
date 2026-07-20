"""Tests for `knx-sim monitor` (F-CLI-2, M8 round B).

monitor() runs forever until cancelled, so these drive it as a background
task against a real running instance (via cli.main.build(), the same
startup path `knx-sim run` uses) and capture its printed output with
pytest's capsys -- matching this project's established real-network
testing convention (see tests/cli/test_main.py) rather than mocking the
WebSocket connection.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.cli.main import RunningApp, build, shutdown
from knx_sim.cli.monitor import format_telegram, monitor

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


class TestFormatTelegram:
    def test_includes_core_fields(self) -> None:
        line = format_telegram(
            {
                "timestamp": 1_700_000_000.123,
                "source": "1.1.2",
                "destination": "1/1/1",
                "destination_name": None,
                "service": "write",
                "dpt_id": "1.001",
                "value": True,
            }
        )
        assert "1.1.2 -> 1/1/1" in line
        assert "write" in line
        assert "1.001" in line
        assert "True" in line

    def test_appends_the_group_address_name_when_present(self) -> None:
        line = format_telegram(
            {
                "timestamp": 1_700_000_000.123,
                "source": "1.1.2",
                "destination": "1/1/2",
                "destination_name": "Living Room Light A1 Status",
                "service": "write",
                "dpt_id": "1.001",
                "value": True,
            }
        )
        assert "(Living Room Light A1 Status)" in line

    def test_omits_the_name_parenthetical_when_unnamed(self) -> None:
        line = format_telegram(
            {
                "timestamp": 1_700_000_000.123,
                "source": "1.1.2",
                "destination": "1/1/1",
                "destination_name": None,
                "service": "write",
                "dpt_id": "1.001",
                "value": True,
            }
        )
        assert "(" not in line


async def _start(config_path: Path) -> tuple[RunningApp, asyncio.Task[None]]:
    running = await build(config_path)
    assert running.web_server is not None
    web_task = asyncio.create_task(running.web_server.serve())
    await asyncio.sleep(0.3)  # let uvicorn actually bind & start accepting
    return running, web_task


async def _stop(running: RunningApp, web_task: asyncio.Task[None]) -> None:
    assert running.web_server is not None
    running.web_server.should_exit = True
    await web_task
    await shutdown(running)


class TestMonitor:
    async def test_prints_telegrams_from_a_running_instance(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        running, web_task = await _start(EXAMPLES_DIR / "minimal.yaml")
        assert running.web_server is not None
        monitor_task = asyncio.create_task(
            monitor("127.0.0.1", running.web_server.config.port)
        )
        await asyncio.sleep(0.3)  # let monitor connect and subscribe
        try:
            await running.simulator.bus.inject(
                Telegram(
                    source=IndividualAddress(9, 9, 9),
                    destination=GroupAddress(1, 1, 1),
                    service=Service.GROUP_WRITE,
                    payload=1,
                )
            )
            await asyncio.sleep(0.3)

            output = capsys.readouterr().out
            assert "1/1/1" in output
            assert "write" in output
        finally:
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
            await _stop(running, web_task)

    async def test_retries_until_the_server_is_up(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Starting `knx-sim monitor` before `knx-sim run` is a real use
        # case (or the server briefly restarting) -- monitor() shouldn't
        # give up on the first failed connection attempt. Pin the port in
        # advance (web_port_override) so the same monitor_task, pointed at
        # it from the start, can outlive the server not existing yet.
        port = 18999
        monitor_task = asyncio.create_task(monitor("127.0.0.1", port))
        await asyncio.sleep(0.3)  # let the first (failed) attempt happen and start retrying

        running = await build(EXAMPLES_DIR / "minimal.yaml", web_port_override=port)
        assert running.web_server is not None
        web_task = asyncio.create_task(running.web_server.serve())
        try:
            await asyncio.sleep(2.5)  # past RECONNECT_DELAY_SECONDS -- the retry should land
            output = capsys.readouterr().out
            assert f"Connected to ws://127.0.0.1:{port}" in output
        finally:
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
            await _stop(running, web_task)
