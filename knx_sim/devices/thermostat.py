"""Thermostat / room controller: measured temperature, setpoint, and
heating demand, driven by a periodic simulated-physics tick (F-DEV-4).

Physics model, deliberately simple (per-tick deltas, not continuous
calculus): each tick, temperature drifts toward ambient_temperature by
drift_fraction of the current gap (simple exponential decay), plus
heating_rate_per_tick more if heating is currently demanded. Heating
demand itself uses asymmetric hysteresis around the setpoint (turns on at
setpoint - hysteresis, off at setpoint + hysteresis) so it doesn't chatter
right at the boundary.

setpoint needs no handle_group_write override: it's a combined read/write
object, and the bus already applies an incoming write to its GroupObject
value *before* any handler runs (see Bus._deliver in knx_sim/bus/router.py)
-- the next physics tick simply reads the current value, so there's nothing
extra to react to.

Temperature is published on a cyclic backstop (cyclic_period) *or*
immediately on a significant change (significant_change), whichever comes
first -- matching F-DEV-4's "cyclically and on significant change".
"""

from __future__ import annotations

import asyncio

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.models import DeviceConfig
from knx_sim.devices.device import Device
from knx_sim.devices.group_object import GroupObject, GroupObjectFlags

DEFAULT_TICK_INTERVAL = 5.0
DEFAULT_CYCLIC_PERIOD = 300.0
DEFAULT_SIGNIFICANT_CHANGE = 0.1
DEFAULT_DRIFT_FRACTION = 0.02
DEFAULT_HEATING_RATE_PER_TICK = 0.1
DEFAULT_HYSTERESIS = 0.5


class Thermostat(Device):
    """A thermostat: temperature (9.001, status), setpoint (9.001,
    read/write), heating_demand (1.001, status)."""

    def __init__(
        self,
        individual_address: IndividualAddress,
        temperature_ga: GroupAddress,
        setpoint_ga: GroupAddress,
        heating_demand_ga: GroupAddress,
        *,
        initial_temperature: float = 20.0,
        initial_setpoint: float = 21.0,
        ambient_temperature: float = 18.0,
        drift_fraction: float = DEFAULT_DRIFT_FRACTION,
        heating_rate_per_tick: float = DEFAULT_HEATING_RATE_PER_TICK,
        hysteresis: float = DEFAULT_HYSTERESIS,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        cyclic_period: float = DEFAULT_CYCLIC_PERIOD,
        significant_change: float = DEFAULT_SIGNIFICANT_CHANGE,
    ) -> None:
        if tick_interval <= 0:
            raise ValueError(f"tick_interval must be > 0, got {tick_interval}")
        if cyclic_period <= 0:
            raise ValueError(f"cyclic_period must be > 0, got {cyclic_period}")
        if not 0.0 <= drift_fraction <= 1.0:
            raise ValueError(f"drift_fraction must be 0..1, got {drift_fraction}")
        if hysteresis < 0:
            raise ValueError(f"hysteresis must be >= 0, got {hysteresis}")
        if significant_change < 0:
            raise ValueError(f"significant_change must be >= 0, got {significant_change}")

        temperature = GroupObject(
            name="temperature",
            group_address=temperature_ga,
            dpt_id="9.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=initial_temperature,
        )
        setpoint = GroupObject(
            name="setpoint",
            group_address=setpoint_ga,
            dpt_id="9.001",
            flags=GroupObjectFlags(communication=True, read=True, write=True, transmit=True),
            value=initial_setpoint,
        )
        heating_demand = GroupObject(
            name="heating_demand",
            group_address=heating_demand_ga,
            dpt_id="1.001",
            flags=GroupObjectFlags(communication=True, read=True, transmit=True),
            value=False,
        )
        super().__init__(individual_address, [temperature, setpoint, heating_demand])

        self._temperature = initial_temperature
        self._ambient_temperature = ambient_temperature
        self._drift_fraction = drift_fraction
        self._heating_rate_per_tick = heating_rate_per_tick
        self._hysteresis = hysteresis
        self._tick_interval = tick_interval
        self._cyclic_period = cyclic_period
        self._significant_change = significant_change
        self._tick_task: asyncio.Task[None] | None = None

    @classmethod
    def from_config(cls, config: DeviceConfig) -> Thermostat:
        return cls(
            IndividualAddress.from_string(config.individual_address),
            GroupAddress.from_string(config.require("temperature_ga")),
            GroupAddress.from_string(config.require("setpoint_ga")),
            GroupAddress.from_string(config.require("heating_demand_ga")),
            initial_temperature=float(config.get("initial_temperature", 20.0)),
            initial_setpoint=float(config.get("initial_setpoint", 21.0)),
            ambient_temperature=float(config.get("ambient_temperature", 18.0)),
            drift_fraction=float(config.get("drift_fraction", DEFAULT_DRIFT_FRACTION)),
            heating_rate_per_tick=float(
                config.get("heating_rate_per_tick", DEFAULT_HEATING_RATE_PER_TICK)
            ),
            hysteresis=float(config.get("hysteresis", DEFAULT_HYSTERESIS)),
            tick_interval=float(config.get("tick_interval", DEFAULT_TICK_INTERVAL)),
            cyclic_period=float(config.get("cyclic_period", DEFAULT_CYCLIC_PERIOD)),
            significant_change=float(
                config.get("significant_change", DEFAULT_SIGNIFICANT_CHANGE)
            ),
        )

    async def start(self) -> None:
        self._tick_task = asyncio.create_task(self._run_physics())

    async def stop(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

    async def _run_physics(self) -> None:
        last_transmitted_temperature = self._temperature
        elapsed_since_transmit = 0.0
        while True:
            await asyncio.sleep(self._tick_interval)
            elapsed_since_transmit += self._tick_interval

            heating_demand_go = self.group_objects["heating_demand"]
            setpoint = self.group_objects["setpoint"].value

            delta = (self._ambient_temperature - self._temperature) * self._drift_fraction
            if heating_demand_go.value:
                delta += self._heating_rate_per_tick
            self._temperature += delta

            await self._update_heating_demand(heating_demand_go, setpoint)

            temperature_go = self.group_objects["temperature"]
            temperature_go.set(self._temperature)
            significant = (
                abs(self._temperature - last_transmitted_temperature)
                >= self._significant_change
            )
            cyclic_due = elapsed_since_transmit >= self._cyclic_period
            if (significant or cyclic_due) and temperature_go.flags.transmit:
                await self.transmit(temperature_go)
                last_transmitted_temperature = self._temperature
                elapsed_since_transmit = 0.0

    async def _update_heating_demand(
        self, heating_demand_go: GroupObject, setpoint: float
    ) -> None:
        if not heating_demand_go.value and self._temperature <= setpoint - self._hysteresis:
            new_demand = True
        elif heating_demand_go.value and self._temperature >= setpoint + self._hysteresis:
            new_demand = False
        else:
            return
        if heating_demand_go.set(new_demand) and heating_demand_go.flags.transmit:
            await self.transmit(heating_demand_go)
