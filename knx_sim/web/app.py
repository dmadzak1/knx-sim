"""FastAPI backend for the dashboard (F-WEB-1, F-WEB-2, F-WEB-4): REST
endpoints for device state / the telegram log / manual injection, plus a
WebSocket stream of live telegrams.

create_app() takes an already-built Simulator (see knx_sim/config/loader.py)
rather than constructing one itself -- the web layer is just another
consumer of a running Bus, same as KnxIpServer, not the thing that owns
simulator lifecycle (that's the CLI's job, M7 round C).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from knx_sim.bus.router import TelegramLogEntry
from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.config.loader import Simulator
from knx_sim.dpt import get_codec
from knx_sim.dpt.dpt3 import DimmingControl
from knx_sim.web.schemas import (
    DeviceState,
    GroupObjectFlagsResponse,
    GroupObjectState,
    InjectRequest,
    InjectResponse,
    TelegramResponse,
)

# Bounded so a slow/stuck WebSocket client can never grow memory without
# limit; on_telegram() below drops rather than blocks when full, since
# Bus._process() awaits every monitor callback sequentially before
# delivering to devices -- a stuck send must never stall bus processing.
WS_QUEUE_MAXSIZE = 1000

# The individual address attributed to telegrams injected via the web UI
# (F-WEB-4) when the request doesn't specify its own source -- distinct
# from KnxIpServer's own default self-address (15.15.0) and from typical
# xknx test-client addresses, so injected telegrams are identifiable in
# the log as coming from the dashboard rather than a real device.
WEB_UI_INDIVIDUAL_ADDRESS = IndividualAddress(15, 15, 200)

_SERVICE_TO_API = {
    Service.GROUP_READ: "read",
    Service.GROUP_RESPONSE: "response",
    Service.GROUP_WRITE: "write",
}
_API_TO_SERVICE = {api: wire for wire, api in _SERVICE_TO_API.items()}


def _serialize_value(value: Any) -> Any:
    """Convert a decoded DPT value to something JSON-native.

    Every DPT decodes to bool/float/int already except 3.007, whose
    DimmingControl dataclass needs converting by hand.
    """
    if isinstance(value, DimmingControl):
        return {"direction": value.direction, "step_code": value.step_code}
    return value


def _coerce_value_for_encode(dpt_id: str, value: Any) -> Any:
    """The inverse of _serialize_value, for injected telegrams: turn a JSON
    {"direction": ..., "step_code": ...} object back into a DimmingControl
    for DPT 3.007. Every other DPT's JSON value already matches what its
    codec expects."""
    if dpt_id == "3.007" and isinstance(value, dict):
        return DimmingControl(**value)
    return value


def _telegram_response(entry: TelegramLogEntry) -> TelegramResponse:
    return TelegramResponse(
        timestamp=entry.timestamp,
        source=str(entry.telegram.source),
        destination=str(entry.telegram.destination),
        service=_SERVICE_TO_API[entry.telegram.service],
        dpt_id=entry.dpt_id,
        value=_serialize_value(entry.decoded_value),
    )


def create_app(simulator: Simulator) -> FastAPI:
    app = FastAPI(title="knx-sim dashboard")
    bus = simulator.bus

    @app.get("/api/devices")
    def list_devices() -> list[DeviceState]:
        result = []
        for device in simulator.devices:
            device_config = simulator.device_configs[device.individual_address]
            group_objects = {
                name: GroupObjectState(
                    group_address=str(group_object.group_address),
                    dpt_id=group_object.dpt_id,
                    value=_serialize_value(group_object.value),
                    flags=GroupObjectFlagsResponse(
                        communication=group_object.flags.communication,
                        read=group_object.flags.read,
                        write=group_object.flags.write,
                        transmit=group_object.flags.transmit,
                        update=group_object.flags.update,
                    ),
                )
                for name, group_object in device.group_objects.items()
            }
            result.append(
                DeviceState(
                    individual_address=str(device.individual_address),
                    name=device_config.name,
                    room=device_config.room,
                    type=device_config.type,
                    group_objects=group_objects,
                )
            )
        return result

    @app.get("/api/telegrams")
    def list_telegrams(
        group_address: str | None = None,
        service: str | None = None,
        since: float | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
    ) -> list[TelegramResponse]:
        ga_filter = None
        if group_address is not None:
            try:
                ga_filter = GroupAddress.from_string(group_address)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None

        service_filter = None
        if service is not None:
            service_filter = _API_TO_SERVICE.get(service)
            if service_filter is None:
                raise HTTPException(
                    422, f"unknown service {service!r}; expected read/write/response"
                )

        entries = [
            entry
            for entry in bus.telegram_log
            if (ga_filter is None or entry.telegram.destination == ga_filter)
            and (service_filter is None or entry.telegram.service is service_filter)
            and (since is None or entry.timestamp >= since)
        ]
        entries = entries[-limit:]
        return [_telegram_response(entry) for entry in entries]

    @app.post("/api/inject")
    async def inject_telegram(request: InjectRequest) -> InjectResponse:
        try:
            destination = GroupAddress.from_string(request.destination)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

        service = _API_TO_SERVICE.get(request.service)
        if service is None:
            raise HTTPException(
                422, f"unknown service {request.service!r}; expected read/write/response"
            )

        if request.source is not None:
            try:
                source = IndividualAddress.from_string(request.source)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        else:
            source = WEB_UI_INDIVIDUAL_ADDRESS

        payload: int | bytes | None = None
        if service is not Service.GROUP_READ:
            if request.dpt_id is None:
                raise HTTPException(422, "dpt_id is required for write/response services")
            try:
                codec = get_codec(request.dpt_id)
                encoded = codec.encode(_coerce_value_for_encode(request.dpt_id, request.value))
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from None
            payload = encoded[0] if codec.payload_length == 0 else encoded

        telegram = Telegram(
            source=source, destination=destination, service=service, payload=payload
        )
        await bus.inject(telegram)
        return InjectResponse()

    @app.websocket("/ws")
    async def telegram_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=WS_QUEUE_MAXSIZE)

        async def on_telegram(telegram: Telegram) -> None:
            # Bus._process() appends to its log before awaiting any monitor
            # callback and never yields control in between (see
            # knx_sim/bus/router.py), so telegram_log[-1] is guaranteed to
            # be *this* telegram's entry for the entire duration of this
            # callback -- no need to re-decode the payload ourselves.
            entry = bus.telegram_log[-1]
            try:
                queue.put_nowait(_telegram_response(entry).model_dump(mode="json"))
            except asyncio.QueueFull:
                pass  # client is falling behind; drop rather than block the bus

        bus.subscribe(on_telegram)

        async def sender() -> None:
            while True:
                data = await queue.get()
                await websocket.send_json({"type": "telegram", "data": data})

        async def receiver() -> None:
            # This stream is server->client only; the client never sends
            # anything meaningful. This loop exists purely to detect
            # disconnection -- Starlette raises WebSocketDisconnect from
            # receive() when the client goes away, which a send-only loop
            # would otherwise never notice, leaving the connection (and
            # this handler's task) alive forever and deadlocking graceful
            # shutdown.
            while True:
                await websocket.receive_text()

        send_task = asyncio.create_task(sender())
        receive_task = asyncio.create_task(receiver())
        try:
            done, pending = await asyncio.wait(
                [send_task, receive_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for task in done:
                exc = task.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        finally:
            bus.unsubscribe(on_telegram)

    return app
