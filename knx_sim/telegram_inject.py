"""Shared helper for turning a decoded value into an injectable
GroupValueWrite payload -- used by both the web dashboard's manual
injector (F-WEB-4, knx_sim/web/app.py) and the scenario runner's `write`
action (F-CLI-3, knx_sim/scenario.py), so the one non-trivial piece of
logic here doesn't drift between two copies: DPT 3.007's DimmingControl
needs a plain {"direction": ..., "step_code": ...} value (a JSON dict from
the web API, or a YAML mapping from a scenario file) coerced back into a
dataclass before encoding -- every other DPT's value already matches what
its codec expects.
"""

from __future__ import annotations

from typing import Any

from knx_sim.dpt import get_codec
from knx_sim.dpt.dpt3 import DimmingControl


def encode_payload(dpt_id: str, value: Any) -> int | bytes:
    """Encode value for dpt_id into the int|bytes shape Telegram.payload
    expects (see knx_sim/cemi/frame.py's Telegram docstring)."""
    if dpt_id == "3.007" and isinstance(value, dict):
        value = DimmingControl(**value)
    codec = get_codec(dpt_id)
    encoded = codec.encode(value)
    return encoded[0] if codec.payload_length == 0 else encoded
