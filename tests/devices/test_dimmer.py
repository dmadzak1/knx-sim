from __future__ import annotations

import asyncio

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Telegram
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.dpt.dpt3 import DimmingControl

SWITCH_GA = GroupAddress(1, 1, 1)
RELATIVE_DIM_GA = GroupAddress(1, 1, 2)
BRIGHTNESS_GA = GroupAddress(1, 1, 3)
SWITCH_STATUS_GA = GroupAddress(1, 1, 4)
BRIGHTNESS_STATUS_GA = GroupAddress(1, 1, 5)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


def _make(**kwargs: object) -> DimmerActuator:
    return DimmerActuator(
        IndividualAddress(1, 1, 9),
        SWITCH_GA,
        RELATIVE_DIM_GA,
        BRIGHTNESS_GA,
        SWITCH_STATUS_GA,
        BRIGHTNESS_STATUS_GA,
        **kwargs,  # type: ignore[arg-type]
    )


def _bound(dimmer: DimmerActuator) -> tuple[DimmerActuator, Recorder]:
    recorder = Recorder()
    dimmer.bind(recorder)
    return dimmer, recorder


class TestConstruction:
    def test_group_object_addresses(self) -> None:
        dimmer = _make()
        assert dimmer.group_objects["switch"].group_address == SWITCH_GA
        assert dimmer.group_objects["relative_dim"].group_address == RELATIVE_DIM_GA
        assert dimmer.group_objects["brightness"].group_address == BRIGHTNESS_GA
        assert dimmer.group_objects["switch_status"].group_address == SWITCH_STATUS_GA
        assert dimmer.group_objects["brightness_status"].group_address == BRIGHTNESS_STATUS_GA

    def test_defaults_to_off(self) -> None:
        dimmer = _make()
        assert dimmer.group_objects["switch_status"].value is False
        assert dimmer.group_objects["brightness_status"].value == 0.0

    def test_initial_brightness(self) -> None:
        dimmer = _make(initial_brightness=40.0)
        assert dimmer.group_objects["switch_status"].value is True
        assert dimmer.group_objects["brightness_status"].value == 40.0

    @pytest.mark.parametrize("bad_brightness", [-1.0, 100.1])
    def test_rejects_initial_brightness_out_of_range(self, bad_brightness: float) -> None:
        with pytest.raises(ValueError, match="initial_brightness must be 0..100"):
            _make(initial_brightness=bad_brightness)

    def test_rejects_non_positive_ramp_time(self) -> None:
        with pytest.raises(ValueError, match="ramp_time_full_range must be > 0"):
            _make(ramp_time_full_range=0.0)

    def test_rejects_non_positive_tick_interval(self) -> None:
        with pytest.raises(ValueError, match="ramp_tick_interval must be > 0"):
            _make(ramp_tick_interval=0.0)


class TestSwitch:
    async def test_switch_on_with_no_prior_dimming_goes_to_full(self) -> None:
        dimmer, recorder = _bound(_make())
        control = dimmer.group_objects["switch"]
        control.set(True)
        await dimmer.handle_group_write(control)

        assert dimmer.group_objects["brightness_status"].value == 100.0
        assert dimmer.group_objects["switch_status"].value is True
        assert len(recorder.sent) == 2  # brightness_status + switch_status

    async def test_switch_off_remembers_brightness_for_next_on(self) -> None:
        dimmer, _ = _bound(_make(initial_brightness=35.0))

        switch = dimmer.group_objects["switch"]
        switch.set(False)
        await dimmer.handle_group_write(switch)
        assert dimmer.group_objects["brightness_status"].value == 0.0

        switch.set(True)
        await dimmer.handle_group_write(switch)
        assert dimmer.group_objects["brightness_status"].value == 35.0

    async def test_ignores_writes_to_other_group_objects_by_name_only(self) -> None:
        # handle_group_write dispatches purely on group_object.name; an
        # unrelated name (not one of switch/brightness/relative_dim) is a
        # no-op.
        dimmer, recorder = _bound(_make())
        stray = dimmer.group_objects["switch_status"]
        await dimmer.handle_group_write(stray)
        assert recorder.sent == []


class TestAbsoluteBrightness:
    async def test_sets_brightness_directly(self) -> None:
        dimmer, recorder = _bound(_make())
        brightness = dimmer.group_objects["brightness"]
        brightness.set(66.0)
        await dimmer.handle_group_write(brightness)

        assert dimmer.group_objects["brightness_status"].value == 66.0
        assert dimmer.group_objects["switch_status"].value is True
        assert len(recorder.sent) == 2

    async def test_setting_to_zero_turns_switch_status_off(self) -> None:
        dimmer, _ = _bound(_make(initial_brightness=50.0))
        brightness = dimmer.group_objects["brightness"]
        brightness.set(0.0)
        await dimmer.handle_group_write(brightness)

        assert dimmer.group_objects["switch_status"].value is False

    async def test_cancels_active_ramp(self) -> None:
        dimmer, _ = _bound(_make(ramp_time_full_range=10.0, ramp_tick_interval=0.02))
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=3))
        await dimmer.handle_group_write(relative_dim)
        await asyncio.sleep(0.05)

        brightness = dimmer.group_objects["brightness"]
        brightness.set(20.0)
        await dimmer.handle_group_write(brightness)

        level_after_set = dimmer.group_objects["brightness_status"].value
        await asyncio.sleep(0.1)
        assert dimmer.group_objects["brightness_status"].value == level_after_set == 20.0


class TestRelativeDim:
    async def test_increase_raises_brightness_over_time(self) -> None:
        dimmer, recorder = _bound(
            _make(ramp_time_full_range=0.2, ramp_tick_interval=0.02)
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=1))
        await dimmer.handle_group_write(relative_dim)

        await asyncio.sleep(0.1)

        stop = DimmingControl(direction=True, step_code=0)
        relative_dim.set(stop)
        await dimmer.handle_group_write(relative_dim)

        assert dimmer.group_objects["brightness_status"].value > 0.0
        assert any(t.destination == BRIGHTNESS_STATUS_GA for t in recorder.sent)

    async def test_decrease_lowers_brightness_over_time(self) -> None:
        dimmer, _ = _bound(
            _make(
                initial_brightness=100.0, ramp_time_full_range=0.2, ramp_tick_interval=0.02
            )
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=False, step_code=1))
        await dimmer.handle_group_write(relative_dim)

        await asyncio.sleep(0.1)

        relative_dim.set(DimmingControl(direction=False, step_code=0))
        await dimmer.handle_group_write(relative_dim)

        assert dimmer.group_objects["brightness_status"].value < 100.0

    async def test_stop_before_any_movement_is_a_no_op(self) -> None:
        dimmer, recorder = _bound(_make())
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=0))
        await dimmer.handle_group_write(relative_dim)
        assert recorder.sent == []

    async def test_ramp_stops_automatically_at_full_brightness(self) -> None:
        dimmer, _ = _bound(
            _make(
                initial_brightness=95.0, ramp_time_full_range=0.1, ramp_tick_interval=0.02
            )
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=1))
        await dimmer.handle_group_write(relative_dim)

        await asyncio.sleep(0.3)  # well past when it should hit 100% and stop

        assert dimmer.group_objects["brightness_status"].value == 100.0
        # a further wait shouldn't change anything -- the ramp task ended itself
        value_at_100 = dimmer.group_objects["brightness_status"].value
        await asyncio.sleep(0.1)
        assert dimmer.group_objects["brightness_status"].value == value_at_100

    async def test_ramp_stops_automatically_at_zero_brightness(self) -> None:
        dimmer, _ = _bound(
            _make(initial_brightness=5.0, ramp_time_full_range=0.1, ramp_tick_interval=0.02)
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=False, step_code=1))
        await dimmer.handle_group_write(relative_dim)

        await asyncio.sleep(0.3)

        assert dimmer.group_objects["brightness_status"].value == 0.0
        assert dimmer.group_objects["switch_status"].value is False

    async def test_switching_off_cancels_an_active_ramp(self) -> None:
        dimmer, _ = _bound(
            _make(
                initial_brightness=50.0, ramp_time_full_range=10.0, ramp_tick_interval=0.02
            )
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=1))
        await dimmer.handle_group_write(relative_dim)
        await asyncio.sleep(0.05)

        switch = dimmer.group_objects["switch"]
        switch.set(False)
        await dimmer.handle_group_write(switch)
        assert dimmer.group_objects["brightness_status"].value == 0.0

        # if the ramp weren't cancelled, this sleep would let it keep moving
        await asyncio.sleep(0.1)
        assert dimmer.group_objects["brightness_status"].value == 0.0


class TestDeviceStop:
    async def test_stop_cancels_active_ramp_cleanly(self) -> None:
        dimmer, _ = _bound(
            _make(ramp_time_full_range=10.0, ramp_tick_interval=0.02)
        )
        relative_dim = dimmer.group_objects["relative_dim"]
        relative_dim.set(DimmingControl(direction=True, step_code=1))
        await dimmer.handle_group_write(relative_dim)
        await asyncio.sleep(0.05)

        await dimmer.stop()  # must not raise or hang

    async def test_stop_with_no_active_ramp_is_a_no_op(self) -> None:
        dimmer, _ = _bound(_make())
        await dimmer.stop()  # must not raise
