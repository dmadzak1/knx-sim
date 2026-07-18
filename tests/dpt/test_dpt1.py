from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt1 import DPT1001


def test_encode_true() -> None:
    assert DPT1001.encode(True) == bytes([1])


def test_encode_false() -> None:
    assert DPT1001.encode(False) == bytes([0])


def test_decode_zero_is_false() -> None:
    assert DPT1001.decode(bytes([0])) is False


def test_decode_one_is_true() -> None:
    assert DPT1001.decode(bytes([1])) is True


def test_encode_rejects_non_bool() -> None:
    with pytest.raises(TypeError):
        DPT1001.encode(1)  # type: ignore[arg-type]


def test_decode_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="expects 1 byte"):
        DPT1001.decode(b"")
    with pytest.raises(ValueError, match="expects 1 byte"):
        DPT1001.decode(bytes([0, 1]))


def test_decode_rejects_invalid_byte_value() -> None:
    with pytest.raises(ValueError, match="expects byte value 0 or 1"):
        DPT1001.decode(bytes([2]))


def test_payload_length_is_zero() -> None:
    # DPT 1.001 is <= 6 bits, so it's merged into the APCI byte, not a
    # separate cEMI payload.
    assert DPT1001.payload_length == 0


@given(st.booleans())
def test_round_trip(value: bool) -> None:
    assert DPT1001.decode(DPT1001.encode(value)) == value
