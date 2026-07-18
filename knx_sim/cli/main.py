"""Minimal CLI launcher (F-CLI-1, partial): `python -m knx_sim.cli <config.yaml>`
boots the whole simulator -- bus, KNXnet/IP server, and web dashboard --
from a single YAML file and runs until interrupted.

Deliberately minimal for M7: no flags, no log-level control, no disabling
individual subsystems (that's M8's full F-CLI-1 scope). Just enough to
satisfy M7's own done-when criterion: watch telegrams stream live while
operating devices from both the web UI and an external xknx client.

build()/shutdown() are split out from run() so tests can drive the exact
same startup path a real invocation uses (load config -> build_simulator
-> start bus+KnxIpServer -> construct the web app's uvicorn.Server) without
needing run()'s infinite serve()-until-interrupted loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from knx_sim.config.loader import Simulator, build_simulator, load_installation_file
from knx_sim.web.app import create_app

# The web dashboard always binds to 127.0.0.1 (F-WEB-5): it has no
# authentication, so it must never be reachable beyond localhost by
# default, independent of whatever the KNXnet/IP side's bind_address is
# (that one *does* need to be a real reachable interface for xknx/ETS to
# connect to).
WEB_BIND_ADDRESS = "127.0.0.1"

logger = logging.getLogger("knx_sim.cli")


@dataclass
class RunningApp:
    """Everything build() started: the simulator (bus + KNXnet/IP server,
    both already running) and the web dashboard's not-yet-serving
    uvicorn.Server."""

    simulator: Simulator
    web_server: uvicorn.Server


async def build(config_path: str | Path) -> RunningApp:
    """Load config_path and start the bus, KNXnet/IP server, and web app --
    everything except actually serving the web app (that's run()'s job, so
    tests can drive web_server.serve() themselves instead)."""
    installation = load_installation_file(config_path)
    simulator = build_simulator(installation)

    simulator.bus.start()
    await simulator.server.start()

    app = create_app(simulator)
    web_config = uvicorn.Config(
        app,
        host=WEB_BIND_ADDRESS,
        port=installation.simulator.web_port,
        log_level="warning",
    )
    web_server = uvicorn.Server(web_config)

    logger.info(
        "%s: KNXnet/IP on %s:%d, web dashboard on http://%s:%d (Ctrl+C to stop)",
        installation.simulator.name,
        simulator.server.bind_address,
        installation.simulator.port,
        WEB_BIND_ADDRESS,
        installation.simulator.web_port,
    )
    return RunningApp(simulator=simulator, web_server=web_server)


async def shutdown(running: RunningApp) -> None:
    """Stop the KNXnet/IP server, then the bus (which also stops every
    registered device) -- the web dashboard's uvicorn.Server is expected to
    have already stopped serving by the time this is called."""
    await running.simulator.server.stop()
    await running.simulator.bus.stop()


async def run(config_path: str | Path) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    running = await build(config_path)
    try:
        # uvicorn.Server.serve() installs its own SIGINT/SIGTERM handlers
        # and returns normally once one arrives (see uvicorn.server's
        # capture_signals()) -- no KeyboardInterrupt to catch here.
        await running.web_server.serve()
    finally:
        await shutdown(running)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="knx-sim", description="Run a knx-sim virtual installation from a YAML config."
    )
    parser.add_argument("config", help="Path to a YAML installation config (see examples/).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        asyncio.run(run(args.config))
    except KeyboardInterrupt:
        # uvicorn.Server.serve() already handles the first Ctrl+C
        # gracefully and returns normally; this only catches the signal
        # capture_signals() re-raises after restoring the default handler
        # on its way out, or a second Ctrl+C during shutdown.
        pass
