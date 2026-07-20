"""Tests for serving the built frontend as static files (round E).

FRONTEND_DIST is a module-level constant computed once at import time, so
these tests monkeypatch knx_sim.web.app.FRONTEND_DIST directly rather than
depending on whether `npm run build` has actually been run in this
checkout -- keeps the test suite meaningful (and CI-safe) regardless of
frontend build state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

import knx_sim.web.app as web_app
from knx_sim.config.loader import Simulator, build_simulator, load_installation_file
from knx_sim.web.app import create_app

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
async def simulator() -> AsyncIterator[Simulator]:
    config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
    sim = build_simulator(config)
    sim.bus.start()
    yield sim
    await sim.bus.stop()


class TestFrontendBuilt:
    async def test_serves_index_html_at_root(
        self, simulator: Simulator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html><body>knx-sim dashboard</body></html>")
        monkeypatch.setattr(web_app, "FRONTEND_DIST", dist)

        app = create_app(simulator)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert "knx-sim dashboard" in response.text

    async def test_api_routes_still_take_priority_over_the_mount(
        self, simulator: Simulator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html></html>")
        monkeypatch.setattr(web_app, "FRONTEND_DIST", dist)

        app = create_app(simulator)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/devices")

        assert response.status_code == 200
        assert response.json() != []


class TestFrontendNotBuilt:
    async def test_api_still_works_without_a_frontend_build(
        self, simulator: Simulator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(web_app, "FRONTEND_DIST", tmp_path / "does-not-exist")

        app = create_app(simulator)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/devices")

        assert response.status_code == 200

    async def test_root_is_not_found_without_a_frontend_build(
        self, simulator: Simulator, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(web_app, "FRONTEND_DIST", tmp_path / "does-not-exist")

        app = create_app(simulator)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 404
