"""Tests for the dashboard's REST API (F-WEB-1, F-WEB-4).

Uses httpx.AsyncClient over an ASGITransport (no real socket) rather than
FastAPI's synchronous TestClient, because build_simulator() needs a
running event loop (Bus.register() schedules device.start() as a
background task) -- keeping everything on one async test's event loop
avoids the cross-loop asyncio object issues a separate sync TestClient
would introduce.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.config.loader import Simulator, build_simulator, load_installation_file
from knx_sim.web.app import WEB_UI_INDIVIDUAL_ADDRESS, create_app

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
async def minimal_client() -> AsyncIterator[tuple[Simulator, httpx.AsyncClient]]:
    config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
    simulator = build_simulator(config)
    simulator.bus.start()
    app = create_app(simulator)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield simulator, client
    await simulator.bus.stop()


@pytest.fixture
async def demo_house_client() -> AsyncIterator[tuple[Simulator, httpx.AsyncClient]]:
    config = load_installation_file(EXAMPLES_DIR / "demo-house.yaml")
    simulator = build_simulator(config)
    simulator.bus.start()
    app = create_app(simulator)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield simulator, client
    await simulator.bus.stop()


class TestListDevices:
    async def test_returns_every_device_with_state(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.get("/api/devices")
        assert response.status_code == 200
        devices = response.json()
        assert len(devices) == 2

        lamp = next(d for d in devices if d["type"] == "switch")
        assert lamp["individual_address"] == "1.1.2"
        assert lamp["name"] == "hallway_lamp"
        assert lamp["room"] is None
        assert lamp["group_objects"]["control"]["group_address"] == "1/1/1"
        assert lamp["group_objects"]["control"]["dpt_id"] == "1.001"
        assert lamp["group_objects"]["control"]["value"] is False
        assert lamp["group_objects"]["control"]["flags"]["write"] is True

    async def test_includes_room_from_config(
        self, demo_house_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = demo_house_client
        response = await client.get("/api/devices")
        devices = response.json()
        bedroom_devices = [d for d in devices if d["room"] == "Bedroom"]
        assert len(bedroom_devices) == 5


class TestListTelegrams:
    async def test_empty_log_returns_empty_list(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.get("/api/telegrams")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_telegrams_after_injection(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "1.001", "value": True},
        )
        await simulator.bus.join()

        response = await client.get("/api/telegrams")
        telegrams = response.json()
        assert len(telegrams) >= 1
        first = telegrams[0]
        assert first["destination"] == "1/1/1"
        assert first["service"] == "write"
        assert first["dpt_id"] == "1.001"
        assert first["value"] is True

    async def test_filters_by_group_address(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "1.001", "value": True},
        )
        await simulator.bus.join()

        matching = (await client.get("/api/telegrams", params={"group_address": "1/1/1"})).json()
        assert len(matching) >= 1
        assert all(t["destination"] == "1/1/1" for t in matching)

        empty = (await client.get("/api/telegrams", params={"group_address": "9/7/255"})).json()
        assert empty == []

    async def test_filters_by_service(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "1.001", "value": True},
        )
        await simulator.bus.join()

        reads = (await client.get("/api/telegrams", params={"service": "read"})).json()
        assert reads == []
        writes = (await client.get("/api/telegrams", params={"service": "write"})).json()
        assert len(writes) >= 1

    async def test_rejects_unknown_service(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.get("/api/telegrams", params={"service": "teleport"})
        assert response.status_code == 422


class TestInjectTelegram:
    async def test_write_updates_device_state(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        response = await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "1.001", "value": True},
        )
        assert response.status_code == 200
        await simulator.bus.join()

        lamp = next(
            d for d in simulator.devices if d.individual_address == IndividualAddress(1, 1, 2)
        )
        assert lamp.group_objects["control"].value is True
        assert lamp.group_objects["status"].value is True

    async def test_defaults_source_to_web_ui_address(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "1.001", "value": True},
        )
        await simulator.bus.join()

        entry = simulator.bus.telegram_log[0]
        assert entry.telegram.source == WEB_UI_INDIVIDUAL_ADDRESS

    async def test_explicit_source_is_respected(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = minimal_client
        await client.post(
            "/api/inject",
            json={
                "destination": "1/1/1",
                "dpt_id": "1.001",
                "value": True,
                "source": "3.3.3",
            },
        )
        await simulator.bus.join()

        entry = simulator.bus.telegram_log[0]
        assert entry.telegram.source == IndividualAddress(3, 3, 3)

    async def test_read_requires_no_dpt_id_or_value(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.post(
            "/api/inject", json={"destination": "1/1/2", "service": "read"}
        )
        assert response.status_code == 200

    async def test_dimming_control_round_trips_through_dict(
        self, demo_house_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        simulator, client = demo_house_client
        response = await client.post(
            "/api/inject",
            json={
                "destination": "1/1/11",  # living_room_dimmer's relative_dim_ga
                "dpt_id": "3.007",
                "value": {"direction": True, "step_code": 3},
            },
        )
        assert response.status_code == 200
        await simulator.bus.join()

        dimmer = next(
            d for d in simulator.devices if d.individual_address == IndividualAddress(1, 1, 3)
        )
        control = dimmer.group_objects["relative_dim"].value
        assert control.direction is True
        assert control.step_code == 3

    async def test_rejects_malformed_destination(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.post(
            "/api/inject",
            json={"destination": "not-a-ga", "dpt_id": "1.001", "value": True},
        )
        assert response.status_code == 422

    async def test_rejects_write_without_dpt_id(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.post("/api/inject", json={"destination": "1/1/1", "value": True})
        assert response.status_code == 422

    async def test_rejects_unknown_dpt_id(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.post(
            "/api/inject",
            json={"destination": "1/1/1", "dpt_id": "99.999", "value": True},
        )
        assert response.status_code == 422

    async def test_rejects_unknown_service(
        self, minimal_client: tuple[Simulator, httpx.AsyncClient]
    ) -> None:
        _, client = minimal_client
        response = await client.post(
            "/api/inject", json={"destination": "1/1/1", "service": "teleport"}
        )
        assert response.status_code == 422
