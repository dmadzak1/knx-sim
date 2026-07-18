from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt1 import DPT1001, DPT1008, DPT1009, DPT1BitBase

ONE_BIT_DPTS: list[type[DPT1BitBase]] = [DPT1001, DPT1008, DPT1009]


@pytest.mark.parametrize("dpt", ONE_BIT_DPTS)
class TestSharedOneBitBehaviour:
    def test_encode_true(self, dpt: type[DPT1BitBase]) -> None:
        assert dpt.encode(True) == bytes([1])

    def test_encode_false(self, dpt: type[DPT1BitBase]) -> None:
        assert dpt.encode(False) == bytes([0])

    def test_decode_zero_is_false(self, dpt: type[DPT1BitBase]) -> None:
        assert dpt.decode(bytes([0])) is False

    def test_decode_one_is_true(self, dpt: type[DPT1BitBase]) -> None:
        assert dpt.decode(bytes([1])) is True

    def test_encode_rejects_non_bool(self, dpt: type[DPT1BitBase]) -> None:
        with pytest.raises(TypeError):
            dpt.encode(1)  # type: ignore[arg-type]

    def test_decode_rejects_wrong_length(self, dpt: type[DPT1BitBase]) -> None:
        with pytest.raises(ValueError, match="expects 1 byte"):
            dpt.decode(b"")
        with pytest.raises(ValueError, match="expects 1 byte"):
            dpt.decode(bytes([0, 1]))

    def test_decode_rejects_invalid_byte_value(self, dpt: type[DPT1BitBase]) -> None:
        with pytest.raises(ValueError, match="expects byte value 0 or 1"):
            dpt.decode(bytes([2]))

    def test_payload_length_is_zero(self, dpt: type[DPT1BitBase]) -> None:
        assert dpt.payload_length == 0

    @given(st.booleans())
    def test_round_trip(self, dpt: type[DPT1BitBase], value: bool) -> None:
        assert dpt.decode(dpt.encode(value)) == value


def test_dpt_ids() -> None:
    assert DPT1001.dpt_id == "1.001"
    assert DPT1008.dpt_id == "1.008"
    assert DPT1009.dpt_id == "1.009"
