from __future__ import annotations

import asyncio

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Telegram
from knx_sim.devices.blind import BlindActuator

MOVE_GA = GroupAddress(1, 1, 1)
STOP_GA = GroupAddress(1, 1, 2)
POSITION_GA = GroupAddress(1, 1, 3)
POSITION_STATUS_GA = GroupAddress(1, 1, 4)
MOVING_STATUS_GA = GroupAddress(1, 1, 5)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


def _make(**kwargs: object) -> BlindActuator:
    return BlindActuator(
        IndividualAddress(1, 1, 9),
        MOVE_GA,
        STOP_GA,
        POSITION_GA,
        POSITION_STATUS_GA,
        MOVING_STATUS_GA,
        **kwargs,  # type: ignore[arg-type]
    )


def _bound(blind: BlindActuator) -> tuple[BlindActuator, Recorder]:
    recorder = Recorder()
    blind.bind(recorder)
    return blind, recorder


class TestConstruction:
    def test_group_object_addresses(self) -> None:
        blind = _make()
        assert blind.group_objects["move"].group_address == MOVE_GA
        assert blind.group_objects["stop"].group_address == STOP_GA
        assert blind.group_objects["position"].group_address == POSITION_GA
        assert blind.group_objects["position_status"].group_address == POSITION_STATUS_GA
        assert blind.group_objects["moving_status"].group_address == MOVING_STATUS_GA

    def test_defaults_to_open_and_not_moving(self) -> None:
        blind = _make()
        assert blind.group_objects["position_status"].value == 0.0
        assert blind.group_objects["moving_status"].value is False

    def test_initial_position(self) -> None:
        blind = _make(initial_position=70.0)
        assert blind.group_objects["position_status"].value == 70.0

    @pytest.mark.parametrize("bad_position", [-1.0, 100.1])
    def test_rejects_initial_position_out_of_range(self, bad_position: float) -> None:
        with pytest.raises(ValueError, match="initial_position must be 0..100"):
            _make(initial_position=bad_position)

    def test_rejects_non_positive_travel_time(self) -> None:
        with pytest.raises(ValueError, match="travel_time_full_range must be > 0"):
            _make(travel_time_full_range=0.0)

    def test_rejects_non_positive_tick_interval(self) -> None:
        with pytest.raises(ValueError, match="travel_tick_interval must be > 0"):
            _make(travel_tick_interval=0.0)


class TestMove:
    async def test_move_down_increases_position_over_time(self) -> None:
        blind, recorder = _bound(
            _make(travel_time_full_range=0.2, travel_tick_interval=0.02)
        )
        move = blind.group_objects["move"]
        move.set(True)  # True = Down
        await blind.handle_group_write(move)

        assert blind.group_objects["moving_status"].value is True
        await asyncio.sleep(0.1)

        assert blind.group_objects["position_status"].value > 0.0
        assert any(t.destination == POSITION_STATUS_GA for t in recorder.sent)
        assert any(t.destination == MOVING_STATUS_GA for t in recorder.sent)

    async def test_move_up_decreases_position_over_time(self) -> None:
        blind, _ = _bound(
            _make(
                initial_position=100.0, travel_time_full_range=0.2, travel_tick_interval=0.02
            )
        )
        move = blind.group_objects["move"]
        move.set(False)  # False = Up
        await blind.handle_group_write(move)

        await asyncio.sleep(0.1)
        assert blind.group_objects["position_status"].value < 100.0

    async def test_move_stops_automatically_at_fully_closed(self) -> None:
        blind, _ = _bound(
            _make(
                initial_position=90.0, travel_time_full_range=0.1, travel_tick_interval=0.02
            )
        )
        move = blind.group_objects["move"]
        move.set(True)
        await blind.handle_group_write(move)

        await asyncio.sleep(0.3)

        assert blind.group_objects["position_status"].value == 100.0
        assert blind.group_objects["moving_status"].value is False

    async def test_move_stops_automatically_at_fully_open(self) -> None:
        blind, _ = _bound(
            _make(initial_position=10.0, travel_time_full_range=0.1, travel_tick_interval=0.02)
        )
        move = blind.group_objects["move"]
        move.set(False)
        await blind.handle_group_write(move)

        await asyncio.sleep(0.3)

        assert blind.group_objects["position_status"].value == 0.0
        assert blind.group_objects["moving_status"].value is False


class TestStop:
    async def test_stop_cancels_movement(self) -> None:
        blind, _ = _bound(
            _make(travel_time_full_range=10.0, travel_tick_interval=0.02)
        )
        move = blind.group_objects["move"]
        move.set(True)
        await blind.handle_group_write(move)
        await asyncio.sleep(0.06)

        stop = blind.group_objects["stop"]
        await blind.handle_group_write(stop)

        position_at_stop = blind.group_objects["position_status"].value
        assert blind.group_objects["moving_status"].value is False
        await asyncio.sleep(0.1)
        assert blind.group_objects["position_status"].value == position_at_stop

    async def test_stop_with_no_active_movement_is_a_no_op(self) -> None:
        blind, recorder = _bound(_make())
        stop = blind.group_objects["stop"]
        await blind.handle_group_write(stop)
        assert recorder.sent == []


class TestAbsolutePosition:
    async def test_travels_toward_target_and_stops_exactly_there(self) -> None:
        blind, _ = _bound(
            _make(travel_time_full_range=0.2, travel_tick_interval=0.02)
        )
        position = blind.group_objects["position"]
        position.set(30.0)
        await blind.handle_group_write(position)

        await asyncio.sleep(0.3)  # well past when it should reach 30%

        assert blind.group_objects["position_status"].value == 30.0
        assert blind.group_objects["moving_status"].value is False

    async def test_moving_up_toward_a_lower_target(self) -> None:
        blind, _ = _bound(
            _make(
                initial_position=80.0, travel_time_full_range=0.2, travel_tick_interval=0.02
            )
        )
        position = blind.group_objects["position"]
        position.set(20.0)
        await blind.handle_group_write(position)

        await asyncio.sleep(0.3)

        assert blind.group_objects["position_status"].value == 20.0

    async def test_already_at_target_does_not_start_travel(self) -> None:
        blind, recorder = _bound(_make(initial_position=50.0))
        position = blind.group_objects["position"]
        position.set(50.0)
        await blind.handle_group_write(position)
        assert recorder.sent == []


class TestDeviceStop:
    async def test_stop_cancels_active_travel_cleanly(self) -> None:
        blind, _ = _bound(_make(travel_time_full_range=10.0, travel_tick_interval=0.02))
        move = blind.group_objects["move"]
        move.set(True)
        await blind.handle_group_write(move)
        await asyncio.sleep(0.05)

        await blind.stop()  # must not raise or hang

    async def test_stop_with_no_active_travel_is_a_no_op(self) -> None:
        blind, _ = _bound(_make())
        await blind.stop()  # must not raise
