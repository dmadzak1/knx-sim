"""YAML scenario scripts (F-CLI-3): a declarative list of timed stimuli
("at t=2s press hallway switch; at t=10s presence in kitchen") for
repeatable demos and integration tests.

load_scenario_file()/run_scenario() are usable two ways: from the CLI
(`knx-sim run <config.yaml> --scenario <scenario.yaml>`, so a demo runs
itself while you watch the dashboard) and directly from test code (so a
scenario doubles as a regression test per the SPEC's own testing
strategy, e.g. "blind reaches 50% ±2% after position command" -- a test
just calls run_scenario() against a Simulator it already built, then
asserts on device state afterward).

Two kinds of steps: a named action already defined on the device (e.g.
`press` on a wall_switch, `trigger` on a presence sensor) called by
looking up that method by name -- safe here specifically because the
scenario author is the one naming the method to call, not inferring it;
and a generic `write` action that injects a GroupValueWrite to one of the
device's own group objects (looked up by its config name, e.g.
"brightness"), for actuator-type devices that don't have a stimulus
method of their own -- setting a thermostat's setpoint, for instance.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from knx_sim.cemi.address import IndividualAddress
from knx_sim.cemi.frame import Service, Telegram
from knx_sim.config.loader import Simulator
from knx_sim.devices.device import Device
from knx_sim.telegram_inject import encode_payload

# Distinct from KnxIpServer's own default self-address (15.15.0) and the
# web dashboard's WEB_UI_INDIVIDUAL_ADDRESS (15.15.200), so a scenario's
# "write" telegrams are identifiable in the log as scripted stimuli.
SCENARIO_INDIVIDUAL_ADDRESS = IndividualAddress(15, 15, 201)


class ScenarioStep(BaseModel):
    """One timed stimulus. `at` is seconds elapsed since the scenario
    started (not wall-clock time), so scenario files stay reusable across
    runs. group_object/value only apply to the `write` action."""

    at: float
    device: str
    action: str
    group_object: str | None = None
    value: Any = None


def load_scenario_file(path: str | Path) -> list[ScenarioStep]:
    """Read and validate a YAML scenario file: a plain list of steps."""
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    try:
        return [ScenarioStep.model_validate(item) for item in (raw or [])]
    except ValidationError as exc:
        raise ValueError(f"invalid scenario file at {path}:\n{exc}") from exc


def _find_device(simulator: Simulator, name: str) -> Device:
    for device in simulator.devices:
        if simulator.device_configs[device.individual_address].name == name:
            return device
    raise ValueError(f"no device named {name!r} in this installation")


async def _execute_step(simulator: Simulator, step: ScenarioStep) -> None:
    device = _find_device(simulator, step.device)

    if step.action == "write":
        if step.group_object is None:
            raise ValueError(
                f"scenario step for device {step.device!r} needs group_object for 'write'"
            )
        group_object = device.group_objects.get(step.group_object)
        if group_object is None:
            raise ValueError(
                f"device {step.device!r} has no group object named {step.group_object!r}"
            )
        telegram = Telegram(
            source=SCENARIO_INDIVIDUAL_ADDRESS,
            destination=group_object.group_address,
            service=Service.GROUP_WRITE,
            payload=encode_payload(group_object.dpt_id, step.value),
        )
        await simulator.bus.inject(telegram)
        return

    method = getattr(device, step.action, None)
    if not callable(method):
        raise ValueError(f"device {step.device!r} has no action {step.action!r}")
    await method()


async def run_scenario(simulator: Simulator, steps: list[ScenarioStep]) -> None:
    """Execute every step against simulator, in `at` order, waiting in
    real time between steps as needed. `at` is relative to this call, not
    to when the simulator itself was built/started.

    Each step's telegram(s) are given a chance to fully settle
    (bus.join()) before the next step's wait begins -- both `write` and
    the press()/trigger() actions ultimately just enqueue a telegram
    (bus.inject() returns as soon as it's queued, not once delivered), so
    without this a step's effects might not be visible yet when the next
    step fires, or when run_scenario() itself returns -- surprising for
    F-CLI-3's other stated purpose, using a scenario as a regression test
    that asserts on device state right after it finishes.
    """
    start = time.monotonic()
    for step in sorted(steps, key=lambda s: s.at):
        wait = step.at - (time.monotonic() - start)
        if wait > 0:
            await asyncio.sleep(wait)
        await _execute_step(simulator, step)
        await simulator.bus.join()


async def run_scenario_file(simulator: Simulator, path: str | Path) -> None:
    await run_scenario(simulator, load_scenario_file(path))
