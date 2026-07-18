from __future__ import annotations

import pytest

from knx_sim.cemi.address import GroupAddress
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags


def _make(dpt_id: str, value: object, **flag_kwargs: bool) -> GroupObject:
    return GroupObject(
        name="test",
        group_address=GroupAddress(1, 2, 3),
        dpt_id=dpt_id,
        flags=GroupObjectFlags(**flag_kwargs),
        value=value,
    )


class TestConstruction:
    def test_unknown_dpt_id_raises(self) -> None:
        with pytest.raises(KeyError, match="No DPT codec registered"):
            _make("99.999", value=None)

    def test_flags_default_to_false(self) -> None:
        flags = GroupObjectFlags()
        assert not (flags.communication or flags.read or flags.write or flags.transmit)
        assert not flags.update


class TestSet:
    def test_set_reports_change(self) -> None:
        go = _make("1.001", value=False)
        assert go.set(True) is True
        assert go.value is True

    def test_set_reports_no_change(self) -> None:
        go = _make("1.001", value=False)
        assert go.set(False) is False
        assert go.value is False


class TestPayloadInlineDpt:
    def test_to_payload_returns_int(self) -> None:
        go = _make("1.001", value=True)
        payload = go.to_payload()
        assert payload == 1
        assert isinstance(payload, int)

    def test_apply_payload_from_int(self) -> None:
        go = _make("1.001", value=False)
        changed = go.apply_payload(1)
        assert changed is True
        assert go.value is True

    def test_round_trip(self) -> None:
        go = _make("1.001", value=True)
        other = _make("1.001", value=False)
        other.apply_payload(go.to_payload())
        assert other.value == go.value


class TestPayloadAppendedDpt:
    def test_to_payload_returns_bytes(self) -> None:
        go = _make("9.001", value=21.5)
        payload = go.to_payload()
        assert payload == bytes([0x0C, 0x33])
        assert isinstance(payload, bytes)

    def test_apply_payload_from_bytes(self) -> None:
        go = _make("9.001", value=0.0)
        changed = go.apply_payload(bytes([0x0C, 0x33]))
        assert changed is True
        assert go.value == 21.5

    def test_round_trip(self) -> None:
        go = _make("9.001", value=-10.0)
        other = _make("9.001", value=0.0)
        other.apply_payload(go.to_payload())
        assert other.value == go.value
