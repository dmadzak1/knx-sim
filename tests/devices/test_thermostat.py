from __future__ import annotations

import asyncio

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.cemi.frame import Telegram
from knx_sim.devices.thermostat import Thermostat

TEMPERATURE_GA = GroupAddress(1, 1, 1)
SETPOINT_GA = GroupAddress(1, 1, 2)
HEATING_DEMAND_GA = GroupAddress(1, 1, 3)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Telegram] = []

    async def __call__(self, telegram: Telegram) -> None:
        self.sent.append(telegram)


def _make(**kwargs: object) -> Thermostat:
    return Thermostat(
        IndividualAddress(1, 1, 9),
        TEMPERATURE_GA,
        SETPOINT_GA,
        HEATING_DEMAND_GA,
        **kwargs,  # type: ignore[arg-type]
    )


def _bound(thermostat: Thermostat) -> tuple[Thermostat, Recorder]:
    recorder = Recorder()
    thermostat.bind(recorder)
    return thermostat, recorder


class TestConstruction:
    def test_group_object_addresses(self) -> None:
        thermostat = _make()
        assert thermostat.group_objects["temperature"].group_address == TEMPERATURE_GA
        assert thermostat.group_objects["setpoint"].group_address == SETPOINT_GA
        assert thermostat.group_objects["heating_demand"].group_address == HEATING_DEMAND_GA

    def test_initial_values(self) -> None:
        thermostat = _make(initial_temperature=19.5, initial_setpoint=22.0)
        assert thermostat.group_objects["temperature"].value == 19.5
        assert thermostat.group_objects["setpoint"].value == 22.0
        assert thermostat.group_objects["heating_demand"].value is False

    def test_setpoint_is_read_and_write(self) -> None:
        thermostat = _make()
        assert thermostat.group_objects["setpoint"].flags.read is True
        assert thermostat.group_objects["setpoint"].flags.write is True

    def test_rejects_non_positive_tick_interval(self) -> None:
        with pytest.raises(ValueError, match="tick_interval must be > 0"):
            _make(tick_interval=0.0)

    def test_rejects_non_positive_cyclic_period(self) -> None:
        with pytest.raises(ValueError, match="cyclic_period must be > 0"):
            _make(cyclic_period=0.0)

    @pytest.mark.parametrize("bad_fraction", [-0.1, 1.1])
    def test_rejects_drift_fraction_out_of_range(self, bad_fraction: float) -> None:
        with pytest.raises(ValueError, match="drift_fraction must be 0..1"):
            _make(drift_fraction=bad_fraction)

    def test_rejects_negative_hysteresis(self) -> None:
        with pytest.raises(ValueError, match="hysteresis must be >= 0"):
            _make(hysteresis=-0.1)

    def test_rejects_negative_significant_change(self) -> None:
        with pytest.raises(ValueError, match="significant_change must be >= 0"):
            _make(significant_change=-0.1)


class TestDrift:
    async def test_temperature_drifts_toward_ambient(self) -> None:
        thermostat, _ = _bound(
            _make(
                initial_temperature=25.0,
                ambient_temperature=18.0,
                drift_fraction=0.5,
                heating_rate_per_tick=0.0,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.1)
            assert thermostat.group_objects["temperature"].value < 25.0
        finally:
            await thermostat.stop()

    async def test_no_drift_when_already_at_ambient(self) -> None:
        thermostat, _ = _bound(
            _make(
                initial_temperature=18.0,
                initial_setpoint=18.0,  # within the default hysteresis band -- no heating
                ambient_temperature=18.0,
                drift_fraction=0.5,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.1)
            assert thermostat.group_objects["temperature"].value == 18.0
        finally:
            await thermostat.stop()


class TestHeatingHysteresis:
    async def test_heating_turns_on_below_setpoint_minus_hysteresis(self) -> None:
        thermostat, recorder = _bound(
            _make(
                initial_temperature=15.0,
                initial_setpoint=20.0,
                hysteresis=0.5,
                ambient_temperature=15.0,
                drift_fraction=0.0,
                heating_rate_per_tick=0.1,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.05)
            assert thermostat.group_objects["heating_demand"].value is True
            assert any(t.destination == HEATING_DEMAND_GA for t in recorder.sent)
        finally:
            await thermostat.stop()

    async def test_heating_turns_off_above_setpoint_plus_hysteresis(self) -> None:
        thermostat, _ = _bound(
            _make(
                initial_temperature=15.0,
                initial_setpoint=15.2,
                hysteresis=0.1,
                ambient_temperature=30.0,
                drift_fraction=0.0,
                heating_rate_per_tick=1.0,  # heats up fast, well past setpoint+hysteresis
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.03)  # one tick: heating should engage
            assert thermostat.group_objects["heating_demand"].value is True

            await asyncio.sleep(0.1)  # further ticks: should overshoot and turn off
            assert thermostat.group_objects["heating_demand"].value is False
        finally:
            await thermostat.stop()

    async def test_no_heating_within_hysteresis_band(self) -> None:
        thermostat, _ = _bound(
            _make(
                initial_temperature=20.0,
                initial_setpoint=20.2,
                hysteresis=0.5,
                ambient_temperature=20.0,
                drift_fraction=0.0,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.08)
            assert thermostat.group_objects["heating_demand"].value is False
        finally:
            await thermostat.stop()


class TestSetpointWrite:
    async def test_write_updates_value_used_by_next_tick(self) -> None:
        thermostat, _ = _bound(
            _make(
                initial_temperature=18.0,
                initial_setpoint=18.0,
                hysteresis=0.2,
                ambient_temperature=18.0,
                drift_fraction=0.0,
                heating_rate_per_tick=0.0,
                tick_interval=0.02,
            )
        )
        setpoint = thermostat.group_objects["setpoint"]
        setpoint.set(25.0)  # now well above temperature + hysteresis

        await thermostat.start()
        try:
            await asyncio.sleep(0.05)
            assert thermostat.group_objects["heating_demand"].value is True
        finally:
            await thermostat.stop()


class TestTemperatureTransmission:
    async def test_transmits_on_significant_change(self) -> None:
        thermostat, recorder = _bound(
            _make(
                initial_temperature=25.0,
                ambient_temperature=15.0,
                drift_fraction=0.5,
                significant_change=0.5,
                cyclic_period=1000.0,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.05)
            assert any(t.destination == TEMPERATURE_GA for t in recorder.sent)
        finally:
            await thermostat.stop()

    async def test_transmits_cyclically_even_without_significant_change(self) -> None:
        thermostat, recorder = _bound(
            _make(
                initial_temperature=18.0,
                ambient_temperature=18.0,  # no drift at all
                drift_fraction=0.5,
                significant_change=1000.0,  # never "significant"
                cyclic_period=0.05,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.15)
            assert any(t.destination == TEMPERATURE_GA for t in recorder.sent)
        finally:
            await thermostat.stop()

    async def test_no_transmit_before_significant_change_or_cyclic_due(self) -> None:
        thermostat, recorder = _bound(
            _make(
                initial_temperature=18.0,
                initial_setpoint=18.0,  # within the default hysteresis band -- no heating
                ambient_temperature=18.0,
                drift_fraction=0.5,
                significant_change=1000.0,
                cyclic_period=1000.0,
                tick_interval=0.02,
            )
        )
        await thermostat.start()
        try:
            await asyncio.sleep(0.08)
            assert recorder.sent == []
        finally:
            await thermostat.stop()


class TestDeviceStop:
    async def test_stop_cancels_physics_task_cleanly(self) -> None:
        thermostat, _ = _bound(_make(tick_interval=0.02))
        await thermostat.start()
        await asyncio.sleep(0.03)
        await thermostat.stop()  # must not raise or hang

    async def test_stop_without_start_is_a_no_op(self) -> None:
        thermostat, _ = _bound(_make())
        await thermostat.stop()  # must not raise
