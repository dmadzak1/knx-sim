"""The live web dashboard: FastAPI backend (REST + WebSocket) and frontend."""

from knx_sim.web.app import create_app

__all__ = ["create_app"]
