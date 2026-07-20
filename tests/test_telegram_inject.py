from __future__ import annotations

import pytest

from knx_sim.dpt import get_codec
from knx_sim.dpt.dpt3 import DimmingControl
from knx_sim.telegram_inject import encode_payload


def test_encodes_a_boolean_dpt() -> None:
    assert encode_payload("1.001", True) == 1
    assert encode_payload("1.001", False) == 0


def test_encodes_a_float_dpt() -> None:
    assert encode_payload("5.001", 50.0) == bytes([128])


def test_coerces_a_dict_into_dimming_control_for_dpt_3_007() -> None:
    payload = encode_payload("3.007", {"direction": True, "step_code": 3})
    expected = get_codec("3.007").encode(DimmingControl(direction=True, step_code=3))
    assert payload == expected[0]  # payload_length == 0 -> unwrapped to an int


def test_accepts_a_real_dimming_control_instance_directly() -> None:
    payload = encode_payload("3.007", DimmingControl(direction=False, step_code=5))
    assert isinstance(payload, int)


def test_rejects_an_unknown_dpt_id() -> None:
    with pytest.raises(KeyError):
        encode_payload("99.999", True)
