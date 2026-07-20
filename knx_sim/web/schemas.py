"""Pydantic response/request models for the dashboard's REST API (F-WEB-1,
F-WEB-4).

value fields are typed Any: most DPTs decode to bool/float/int (already
JSON-native), the one exception being DPT 3.007's DimmingControl dataclass,
which app.py converts to a plain {"direction": ..., "step_code": ...} dict
before it ever reaches one of these models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GroupObjectFlagsResponse(BaseModel):
    communication: bool
    read: bool
    write: bool
    transmit: bool
    update: bool


class GroupObjectState(BaseModel):
    group_address: str
    name: str | None  # from the installation's group_addresses registry, if named
    dpt_id: str
    value: Any
    flags: GroupObjectFlagsResponse


class DeviceState(BaseModel):
    individual_address: str
    name: str | None
    room: str | None
    type: str
    group_objects: dict[str, GroupObjectState]


class TelegramResponse(BaseModel):
    timestamp: float
    source: str
    destination: str
    destination_name: str | None  # from the group_addresses registry, if named
    service: str
    dpt_id: str | None
    value: Any


class InjectRequest(BaseModel):
    destination: str
    service: str = "write"
    dpt_id: str | None = None
    value: Any = None
    source: str | None = None


class InjectResponse(BaseModel):
    status: str = "ok"


class GroupAddressNameEntry(BaseModel):
    address: str
    name: str
