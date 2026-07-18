from __future__ import annotations

import asyncio

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Telegram
from knx_sim.devices.presence import PresenceSensor

PRESENCE_GA = GroupAddress(1, 1, 1)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


def _make(**kwargs: object) -> PresenceSensor:
    return PresenceSensor(IndividualAddress(1, 1, 9), PRESENCE_GA, **kwargs)  # type: ignore[arg-type]


def _bound(sensor: PresenceSensor) -> tuple[PresenceSensor, Recorder]:
    recorder = Recorder()
    sensor.bind(recorder)
    return sensor, recorder


class TestConstruction:
    def test_group_object_address(self) -> None:
        sensor = _make()
        assert sensor.group_objects["presence"].group_address == PRESENCE_GA

    def test_defaults_to_not_occupied(self) -> None:
        sensor = _make()
        assert sensor.group_objects["presence"].value is False

    def test_rejects_non_positive_hold_time(self) -> None:
        with pytest.raises(ValueError, match="hold_time must be > 0"):
            _make(hold_time=0.0)

    def test_rejects_non_positive_random_activity_min_interval(self) -> None:
        with pytest.raises(ValueError, match="random_activity_min_interval must be > 0"):
            _make(random_activity_min_interval=0.0)

    def test_rejects_max_interval_below_min(self) -> None:
        with pytest.raises(ValueError, match="random_activity_max_interval must be >="):
            _make(random_activity_min_interval=10.0, random_activity_max_interval=5.0)


class TestTrigger:
    async def test_sets_presence_and_transmits(self) -> None:
        sensor, recorder = _bound(_make(hold_time=10.0))
        try:
            await sensor.trigger()

            assert sensor.group_objects["presence"].value is True
            assert len(recorder.sent) == 1
            assert recorder.sent[0].destination == PRESENCE_GA
            assert recorder.sent[0].payload == 1
        finally:
            # hold_time=10.0 leaves a long-pending hold-timer task -- must
            # be cancelled explicitly or it outlives the test (and hangs
            # pytest-asyncio's loop teardown waiting on it).
            await sensor.stop()

    async def test_auto_clears_after_hold_time(self) -> None:
        sensor, recorder = _bound(_make(hold_time=0.05))
        await sensor.trigger()
        assert sensor.group_objects["presence"].value is True

        await asyncio.sleep(0.1)

        assert sensor.group_objects["presence"].value is False
        assert len(recorder.sent) == 2  # True, then False

    async def test_repeated_trigger_extends_the_hold_window(self) -> None:
        sensor, recorder = _bound(_make(hold_time=0.08))
        await sensor.trigger()
        await asyncio.sleep(0.05)
        await sensor.trigger()  # re-extends before the first window would clear
        await asyncio.sleep(0.05)

        # still within the *second* trigger's window
        assert sensor.group_objects["presence"].value is True
        # only 1 transmit: the second trigger() found presence already True
        # (a no-op value-wise) but still restarted the hold timer -- that's
        # exactly what this test is checking.
        assert len(recorder.sent) == 1

        await asyncio.sleep(0.06)
        assert sensor.group_objects["presence"].value is False

    async def test_trigger_while_already_present_still_restarts_timer(self) -> None:
        sensor, recorder = _bound(_make(hold_time=0.06))
        await sensor.trigger()
        assert len(recorder.sent) == 1  # value changed False -> True

        await asyncio.sleep(0.03)
        await sensor.trigger()  # already True -- no new transmit, but timer restarts
        assert len(recorder.sent) == 1

        await asyncio.sleep(0.04)  # would have cleared without the restart
        assert sensor.group_objects["presence"].value is True

        await asyncio.sleep(0.05)  # let the (restarted) timer finish naturally
        assert sensor.group_objects["presence"].value is False


class TestRandomActivity:
    async def test_disabled_by_default_no_activity(self) -> None:
        sensor, recorder = _bound(_make())
        await sensor.start()
        try:
            await asyncio.sleep(0.05)
            assert recorder.sent == []
        finally:
            await sensor.stop()

    async def test_enabled_triggers_within_configured_interval(self) -> None:
        sensor, recorder = _bound(
            _make(
                random_activity=True,
                random_activity_min_interval=0.01,
                random_activity_max_interval=0.02,
                hold_time=10.0,
            )
        )
        await sensor.start()
        try:
            await asyncio.sleep(0.1)
            assert sensor.group_objects["presence"].value is True
            assert len(recorder.sent) >= 1
        finally:
            await sensor.stop()


class TestDeviceStop:
    async def test_stop_cancels_hold_timer_cleanly(self) -> None:
        sensor, _ = _bound(_make(hold_time=10.0))
        await sensor.trigger()
        await sensor.stop()  # must not raise or hang

    async def test_stop_cancels_random_activity_cleanly(self) -> None:
        sensor, _ = _bound(
            _make(
                random_activity=True,
                random_activity_min_interval=0.01,
                random_activity_max_interval=0.02,
            )
        )
        await sensor.start()
        await asyncio.sleep(0.03)
        await sensor.stop()  # must not raise or hang

    async def test_stop_with_no_active_state_is_a_no_op(self) -> None:
        sensor, _ = _bound(_make())
        await sensor.stop()  # must not raise
