"""Console telegram monitor (F-CLI-2): `knx-sim monitor` connects to a
running instance's /ws and prints decoded telegrams live -- the same
WebSocket stream the web dashboard's own telegram monitor consumes (M7
round B), just rendered to the terminal instead of a browser.

Deliberately WebSocket-based rather than embedding xknx as a runtime
tunneling client or building our own client-side tunneling state machine
(both considered during M8's design round) -- simplest, reuses
already-tested infrastructure, and the SPEC itself explicitly allows
"its own tunneling client or the WebSocket". A real network client
(not the ASGI in-process transport the rest of the test suite mostly
uses), so this connects to an actual running knx-sim process, not
something spun up in-process -- it has no other way to reach one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

RECONNECT_DELAY_SECONDS = 2.0


def _format_time(timestamp: float) -> str:
    dt = datetime.fromtimestamp(timestamp)  # local time, matching the web dashboard's display
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def format_telegram(data: dict[str, Any]) -> str:
    dpt_id = data.get("dpt_id") or "-"
    line = (
        f"{_format_time(float(data['timestamp']))}  {data['source']} -> {data['destination']}   "
        f"{data['service']:<8} {dpt_id:<6} {data['value']}"
    )
    name = data.get("destination_name")
    if name:
        line += f"   ({name})"
    return line


async def monitor(host: str, port: int) -> None:
    """Connect to ws://host:port/ws and print every telegram, reconnecting
    with a fixed delay on any drop (the server might not be up yet, or
    might restart) -- runs until cancelled/interrupted."""
    url = f"ws://{host}:{port}/ws"
    # flush=True on every print: stdout is block-buffered (not
    # line-buffered) whenever it isn't a real terminal -- piped to a file,
    # `less`, `grep`, etc. -- which would otherwise make a *live* monitor
    # print nothing at all until the buffer happens to fill or the process
    # exits, defeating the entire point of the tool. Confirmed empirically:
    # identical output appeared instantly under `python -u` but never
    # arrived at all within several seconds without it.
    print(f"Connecting to {url} ... (Ctrl+C to stop)", flush=True)
    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"Connected to {url}", flush=True)
                async for raw in ws:
                    message = json.loads(raw)
                    if message.get("type") == "telegram":
                        print(format_telegram(message["data"]), flush=True)
        except (ConnectionClosed, OSError) as exc:
            print(
                f"Connection lost ({exc}); reconnecting in {RECONNECT_DELAY_SECONDS:.0f}s...",
                flush=True,
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
