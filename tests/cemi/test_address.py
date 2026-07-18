from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from knx_sim.cemi.address import GroupAddress, IndividualAddress


class TestIndividualAddress:
    def test_from_string(self) -> None:
        addr = IndividualAddress.from_string("1.1.23")
        assert addr == IndividualAddress(area=1, line=1, device=23)

    def test_str_round_trip(self) -> None:
        assert str(IndividualAddress.from_string("1.1.23")) == "1.1.23"

    def test_from_string_rejects_wrong_shape(self) -> None:
        with pytest.raises(ValueError, match="expected 'area.line.device'"):
            IndividualAddress.from_string("1.1")
        with pytest.raises(ValueError, match="expected 'area.line.device'"):
            IndividualAddress.from_string("1.1.1.1")

    def test_from_string_rejects_non_integer_parts(self) -> None:
        with pytest.raises(ValueError, match="must be integers"):
            IndividualAddress.from_string("a.b.c")

    @pytest.mark.parametrize(
        ("area", "line", "device"),
        [(-1, 0, 0), (16, 0, 0), (0, -1, 0), (0, 16, 0), (0, 0, -1), (0, 0, 256)],
    )
    def test_rejects_out_of_range(self, area: int, line: int, device: int) -> None:
        with pytest.raises(ValueError):
            IndividualAddress(area=area, line=line, device=device)

    def test_known_wire_encoding(self) -> None:
        # Matches the worked example in docs/notes/cemi.md: 1.1.23 -> 0x11 0x17.
        addr = IndividualAddress(area=1, line=1, device=23)
        assert addr.to_knx() == bytes([0x11, 0x17])

    def test_known_wire_decoding(self) -> None:
        addr = IndividualAddress.from_knx(bytes([0x11, 0x17]))
        assert addr == IndividualAddress(area=1, line=1, device=23)

    def test_from_knx_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 2 bytes"):
            IndividualAddress.from_knx(bytes([0x11]))

    def test_equality_and_hashing(self) -> None:
        a = IndividualAddress(area=1, line=1, device=23)
        b = IndividualAddress(area=1, line=1, device=23)
        c = IndividualAddress(area=1, line=1, device=24)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
        registry = {a: "lamp"}
        assert registry[b] == "lamp"  # b hashes/equals the same as a

    @given(
        st.integers(min_value=0, max_value=15),
        st.integers(min_value=0, max_value=15),
        st.integers(min_value=0, max_value=255),
    )
    def test_wire_round_trip(self, area: int, line: int, device: int) -> None:
        addr = IndividualAddress(area=area, line=line, device=device)
        assert IndividualAddress.from_knx(addr.to_knx()) == addr

    @given(
        st.integers(min_value=0, max_value=15),
        st.integers(min_value=0, max_value=15),
        st.integers(min_value=0, max_value=255),
    )
    def test_string_round_trip(self, area: int, line: int, device: int) -> None:
        addr = IndividualAddress(area=area, line=line, device=device)
        assert IndividualAddress.from_string(str(addr)) == addr


class TestGroupAddress:
    def test_from_string(self) -> None:
        addr = GroupAddress.from_string("1/2/10")
        assert addr == GroupAddress(main=1, middle=2, sub=10)

    def test_str_round_trip(self) -> None:
        assert str(GroupAddress.from_string("1/2/10")) == "1/2/10"

    def test_from_string_rejects_wrong_shape(self) -> None:
        with pytest.raises(ValueError, match="expected 'main/middle/sub'"):
            GroupAddress.from_string("1/2")
        with pytest.raises(ValueError, match="expected 'main/middle/sub'"):
            GroupAddress.from_string("1/2/3/4")

    def test_from_string_rejects_non_integer_parts(self) -> None:
        with pytest.raises(ValueError, match="must be integers"):
            GroupAddress.from_string("a/b/c")

    @pytest.mark.parametrize(
        ("main", "middle", "sub"),
        [(-1, 0, 0), (32, 0, 0), (0, -1, 0), (0, 8, 0), (0, 0, -1), (0, 0, 256)],
    )
    def test_rejects_out_of_range(self, main: int, middle: int, sub: int) -> None:
        with pytest.raises(ValueError):
            GroupAddress(main=main, middle=middle, sub=sub)

    def test_known_wire_encoding(self) -> None:
        # Matches the worked example in docs/notes/cemi.md: 1/2/10 -> 0x0A 0x0A.
        addr = GroupAddress(main=1, middle=2, sub=10)
        assert addr.to_knx() == bytes([0x0A, 0x0A])

    def test_known_wire_decoding(self) -> None:
        addr = GroupAddress.from_knx(bytes([0x0A, 0x0A]))
        assert addr == GroupAddress(main=1, middle=2, sub=10)

    def test_from_knx_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="expects 2 bytes"):
            GroupAddress.from_knx(bytes([0x0A]))

    def test_equality_and_hashing(self) -> None:
        a = GroupAddress(main=1, middle=2, sub=10)
        b = GroupAddress(main=1, middle=2, sub=10)
        c = GroupAddress(main=1, middle=2, sub=11)
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
        registry = {a: "living room light"}
        assert registry[b] == "living room light"

    @given(
        st.integers(min_value=0, max_value=31),
        st.integers(min_value=0, max_value=7),
        st.integers(min_value=0, max_value=255),
    )
    def test_wire_round_trip(self, main: int, middle: int, sub: int) -> None:
        addr = GroupAddress(main=main, middle=middle, sub=sub)
        assert GroupAddress.from_knx(addr.to_knx()) == addr

    @given(
        st.integers(min_value=0, max_value=31),
        st.integers(min_value=0, max_value=7),
        st.integers(min_value=0, max_value=255),
    )
    def test_string_round_trip(self, main: int, middle: int, sub: int) -> None:
        addr = GroupAddress(main=main, middle=middle, sub=sub)
        assert GroupAddress.from_string(str(addr)) == addr


def test_individual_and_group_address_not_equal() -> None:
    # Same underlying 16-bit value, different address kind -- must not compare equal.
    individual = IndividualAddress(area=0, line=1, device=2)
    group = GroupAddress(main=0, middle=1, sub=2)
    assert individual != group  # type: ignore[comparison-overlap]
