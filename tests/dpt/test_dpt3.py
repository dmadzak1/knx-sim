from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.dpt.dpt3 import DPT3007, DimmingControl

ALL_16_VALUES = list(itertools.product([False, True], range(8)))


class TestDimmingControl:
    def test_rejects_step_code_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="step_code must be 0..7"):
            DimmingControl(direction=True, step_code=8)
        with pytest.raises(ValueError, match="step_code must be 0..7"):
            DimmingControl(direction=True, step_code=-1)

    def test_is_stop(self) -> None:
        assert DimmingControl(direction=True, step_code=0).is_stop
        assert not DimmingControl(direction=True, step_code=1).is_stop

    def test_step_fraction_stop_is_none(self) -> None:
        assert DimmingControl(direction=True, step_code=0).step_fraction is None

    @pytest.mark.parametrize(
        ("step_code", "expected_fraction"),
        [(1, 1.0), (2, 0.5), (3, 0.25), (4, 0.125), (5, 0.0625), (6, 0.03125), (7, 0.015625)],
    )
    def test_step_fraction(self, step_code: int, expected_fraction: float) -> None:
        value = DimmingControl(direction=True, step_code=step_code)
        assert value.step_fraction == expected_fraction


class TestDPT3007:
    @pytest.mark.parametrize(("direction", "step_code"), ALL_16_VALUES)
    def test_encode_all_16_values(self, direction: bool, step_code: int) -> None:
        raw = DPT3007.encode(DimmingControl(direction=direction, step_code=step_code))
        expected = bytes([(0x08 if direction else 0x00) | step_code])
        assert raw == expected

    @pytest.mark.parametrize(("direction", "step_code"), ALL_16_VALUES)
    def test_round_trip_all_16_values(self, direction: bool, step_code: int) -> None:
        value = DimmingControl(direction=direction, step_code=step_code)
        assert DPT3007.decode(DPT3007.encode(value)) == value

    def test_encode_rejects_wrong_type(self) -> None:
        with pytest.raises(TypeError):
            DPT3007.encode((True, 3))  # type: ignore[arg-type]

    def test_decode_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT3007.decode(b"")
        with pytest.raises(ValueError, match="expects 1 byte"):
            DPT3007.decode(bytes([0, 1]))

    def test_decode_rejects_value_above_4_bits(self) -> None:
        with pytest.raises(ValueError, match="expects a 4-bit value"):
            DPT3007.decode(bytes([0x10]))

    def test_payload_length_is_zero(self) -> None:
        assert DPT3007.payload_length == 0

    @given(st.booleans(), st.integers(min_value=0, max_value=7))
    def test_round_trip_hypothesis(self, direction: bool, step_code: int) -> None:
        value = DimmingControl(direction=direction, step_code=step_code)
        assert DPT3007.decode(DPT3007.encode(value)) == value
