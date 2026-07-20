"""CLI (F-CLI-1): `knx-sim run <config.yaml>` boots the whole simulator --
bus, KNXnet/IP server, and web dashboard -- from a single YAML file and
runs until interrupted, with flags for log level, web port override, and
disabling web/routing/tunneling individually.

build()/shutdown() are split out from run() so tests can drive the exact
same startup path a real invocation uses (load config -> build_simulator
-> start bus+KnxIpServer -> construct the web app's uvicorn.Server) without
needing run()'s infinite serve()-until-interrupted loop.

`knx-sim monitor` (F-CLI-2) and scenario scripts (F-CLI-3) are separate,
later rounds of M8 -- this module is round A's F-CLI-1 scope only.
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

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_LOG_LEVEL = "INFO"

logger = logging.getLogger("knx_sim.cli")


@dataclass
class RunningApp:
    """Everything build() started: the simulator (bus + KNXnet/IP server,
    both already running) and the web dashboard's not-yet-serving
    uvicorn.Server -- None if the web dashboard was disabled (--no-web)."""

    simulator: Simulator
    web_server: uvicorn.Server | None


async def build(
    config_path: str | Path,
    *,
    web_port_override: int | None = None,
    enable_web: bool = True,
    enable_routing: bool = True,
    enable_tunneling: bool = True,
) -> RunningApp:
    """Load config_path and start the bus, KNXnet/IP server, and (unless
    disabled) web app -- everything except actually serving the web app
    (that's run()'s job, so tests can drive web_server.serve() themselves
    instead)."""
    installation = load_installation_file(config_path)
    simulator = build_simulator(
        installation, enable_routing=enable_routing, enable_tunneling=enable_tunneling
    )

    simulator.bus.start()
    await simulator.server.start()

    web_server: uvicorn.Server | None = None
    web_port = (
        web_port_override if web_port_override is not None else installation.simulator.web_port
    )
    if enable_web:
        app = create_app(simulator)
        web_config = uvicorn.Config(
            app,
            host=WEB_BIND_ADDRESS,
            port=web_port,
            log_level="warning",
        )
        web_server = uvicorn.Server(web_config)

    logger.info(
        "%s: KNXnet/IP on %s:%d (routing %s, tunneling %s), web dashboard %s (Ctrl+C to stop)",
        installation.simulator.name,
        simulator.server.bind_address,
        installation.simulator.port,
        "on" if enable_routing else "off",
        "on" if enable_tunneling else "off",
        f"on http://{WEB_BIND_ADDRESS}:{web_port}" if enable_web else "disabled",
    )
    return RunningApp(simulator=simulator, web_server=web_server)


async def shutdown(running: RunningApp) -> None:
    """Stop the KNXnet/IP server, then the bus (which also stops every
    registered device) -- the web dashboard's uvicorn.Server (if any) is
    expected to have already stopped serving by the time this is called."""
    await running.simulator.server.stop()
    await running.simulator.bus.stop()


async def run(
    config_path: str | Path,
    *,
    log_level: str = DEFAULT_LOG_LEVEL,
    web_port_override: int | None = None,
    enable_web: bool = True,
    enable_routing: bool = True,
    enable_tunneling: bool = True,
) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    running = await build(
        config_path,
        web_port_override=web_port_override,
        enable_web=enable_web,
        enable_routing=enable_routing,
        enable_tunneling=enable_tunneling,
    )
    try:
        if running.web_server is not None:
            # uvicorn.Server.serve() installs its own SIGINT/SIGTERM
            # handlers and returns normally once one arrives (see
            # uvicorn.server's capture_signals()) -- no KeyboardInterrupt
            # to catch here.
            await running.web_server.serve()
        else:
            # No web server to serve()-and-block-on -- wait directly for
            # Ctrl+C instead (main()'s KeyboardInterrupt handler catches
            # it the same way it catches capture_signals()'s re-raise).
            await asyncio.Event().wait()
    finally:
        await shutdown(running)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="knx-sim", description="A software simulator of a KNX home-automation installation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run a knx-sim virtual installation from a YAML config."
    )
    run_parser.add_argument("config", help="Path to a YAML installation config (see examples/).")
    run_parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=LOG_LEVELS,
        help=f"Logging verbosity (default: {DEFAULT_LOG_LEVEL}).",
    )
    run_parser.add_argument(
        "--web-port",
        type=int,
        default=None,
        help="Override the config's web dashboard port.",
    )
    run_parser.add_argument(
        "--no-web", action="store_true", help="Disable the web dashboard entirely."
    )
    run_parser.add_argument(
        "--no-routing", action="store_true", help="Disable KNXnet/IP multicast routing."
    )
    run_parser.add_argument(
        "--no-tunneling", action="store_true", help="Disable KNXnet/IP tunneling."
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "run":
        try:
            asyncio.run(
                run(
                    args.config,
                    log_level=args.log_level,
                    web_port_override=args.web_port,
                    enable_web=not args.no_web,
                    enable_routing=not args.no_routing,
                    enable_tunneling=not args.no_tunneling,
                )
            )
        except KeyboardInterrupt:
            # uvicorn.Server.serve() already handles the first Ctrl+C
            # gracefully and returns normally; this only catches the signal
            # capture_signals() re-raises after restoring the default handler
            # on its way out, a second Ctrl+C during shutdown, or the bare
            # asyncio.Event().wait() used when the web dashboard is disabled.
            pass
