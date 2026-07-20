"""Tests for YAML scenario scripts (F-CLI-3, M8 round C).

The last test in this file is the SPEC's own literal example of a
scenario used as a regression test (docs/SPEC.md's testing strategy:
"blind reaches 50% ±2% after position command") -- built through the
real pipeline (a real installation YAML + a real scenario YAML, loaded
and run exactly as `knx-sim run --scenario` would), not by hand-wiring a
BlindActuator directly, to actually demonstrate F-CLI-3's own stated
purpose end to end.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.config.loader import Simulator, build_simulator, load_installation_file
from knx_sim.devices.presence import PresenceSensor
from knx_sim.devices.switch import WallSwitch
from knx_sim.scenario import load_scenario_file, run_scenario, run_scenario_file

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class TestLoadScenarioFile:
    def test_parses_steps(self, tmp_path: Path) -> None:
        scenario_file = _write(
            tmp_path,
            "scenario.yaml",
            "- at: 2.0\n  device: hallway_switch\n  action: press\n"
            "- at: 10.0\n  device: kitchen_presence\n  action: trigger\n",
        )
        steps = load_scenario_file(scenario_file)
        assert len(steps) == 2
        assert steps[0].at == 2.0
        assert steps[0].device == "hallway_switch"
        assert steps[0].action == "press"
        assert steps[1].device == "kitchen_presence"
        assert steps[1].action == "trigger"

    def test_empty_file_is_an_empty_scenario(self, tmp_path: Path) -> None:
        scenario_file = _write(tmp_path, "empty.yaml", "")
        assert load_scenario_file(scenario_file) == []

    def test_raises_a_helpful_error_on_invalid_yaml(self, tmp_path: Path) -> None:
        scenario_file = _write(
            tmp_path, "bad.yaml", "- device: hallway_switch\n  action: press\n"  # missing 'at'
        )
        with pytest.raises(ValueError, match="invalid scenario file"):
            load_scenario_file(scenario_file)


async def _build_test_installation(tmp_path: Path) -> Simulator:
    config_file = _write(
        tmp_path,
        "install.yaml",
        "devices:\n"
        "  - type: wall_switch\n"
        "    individual_address: '1.1.1'\n"
        "    name: hallway_switch\n"
        "    control_ga: '1/1/1'\n"
        "  - type: presence\n"
        "    individual_address: '1.1.2'\n"
        "    name: kitchen_presence\n"
        "    presence_ga: '1/1/2'\n"
        "    hold_time: 5.0\n"
        "  - type: thermostat\n"
        "    individual_address: '1.1.3'\n"
        "    name: living_room_thermostat\n"
        "    temperature_ga: '1/1/10'\n"
        "    setpoint_ga: '1/1/11'\n"
        "    heating_demand_ga: '1/1/12'\n",
    )
    config = load_installation_file(config_file)
    simulator = build_simulator(config)
    simulator.bus.start()
    return simulator


class TestRunScenario:
    async def test_press_action(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            wall_switch = next(d for d in simulator.devices if isinstance(d, WallSwitch))
            steps = load_scenario_file(
                _write(tmp_path, "s1.yaml", "- at: 0\n  device: hallway_switch\n  action: press\n")
            )
            await run_scenario(simulator, steps)
            assert wall_switch.group_objects["control"].value is True
        finally:
            await simulator.bus.stop()

    async def test_trigger_action(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        presence = next(d for d in simulator.devices if isinstance(d, PresenceSensor))
        try:
            await run_scenario_file(
                simulator,
                _write(
                    tmp_path, "s2.yaml", "- at: 0\n  device: kitchen_presence\n  action: trigger\n"
                ),
            )
            assert presence.group_objects["presence"].value is True
        finally:
            await presence.stop()
            await simulator.bus.stop()

    async def test_write_action(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            await run_scenario_file(
                simulator,
                _write(
                    tmp_path,
                    "s3.yaml",
                    "- at: 0\n"
                    "  device: living_room_thermostat\n"
                    "  action: write\n"
                    "  group_object: setpoint\n"
                    "  value: 23.5\n",
                ),
            )
            device = next(
                d for d in simulator.devices if d.individual_address == IndividualAddress(1, 1, 3)
            )
            assert device.group_objects["setpoint"].value == 23.5
        finally:
            await simulator.bus.stop()

    async def test_steps_execute_in_at_order_regardless_of_file_order(
        self, tmp_path: Path
    ) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            # The file lists the *later* step first; if execution followed
            # file order rather than `at` order, the final value would be
            # 10.0 (whichever is written last in the file) instead of 20.0
            # (whichever has the later `at`).
            await run_scenario_file(
                simulator,
                _write(
                    tmp_path,
                    "s4.yaml",
                    "- at: 0.3\n  device: living_room_thermostat\n  action: write\n"
                    "  group_object: setpoint\n  value: 20.0\n"
                    "- at: 0.0\n  device: living_room_thermostat\n  action: write\n"
                    "  group_object: setpoint\n  value: 10.0\n",
                ),
            )
            device = next(
                d for d in simulator.devices if d.individual_address == IndividualAddress(1, 1, 3)
            )
            assert device.group_objects["setpoint"].value == 20.0
        finally:
            await simulator.bus.stop()

    async def test_unknown_device_raises_a_helpful_error(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            with pytest.raises(ValueError, match="no device named 'nonexistent'"):
                await run_scenario_file(
                    simulator,
                    _write(
                        tmp_path, "s5.yaml", "- at: 0\n  device: nonexistent\n  action: press\n"
                    ),
                )
        finally:
            await simulator.bus.stop()

    async def test_unknown_action_raises_a_helpful_error(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            with pytest.raises(ValueError, match="no action 'dance'"):
                await run_scenario_file(
                    simulator,
                    _write(
                        tmp_path, "s6.yaml", "- at: 0\n  device: hallway_switch\n  action: dance\n"
                    ),
                )
        finally:
            await simulator.bus.stop()

    async def test_write_without_group_object_raises_a_helpful_error(self, tmp_path: Path) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            with pytest.raises(ValueError, match="needs group_object"):
                await run_scenario_file(
                    simulator,
                    _write(
                        tmp_path,
                        "s7.yaml",
                        "- at: 0\n  device: living_room_thermostat\n  action: write\n  value: 5\n",
                    ),
                )
        finally:
            await simulator.bus.stop()

    async def test_write_unknown_group_object_raises_a_helpful_error(
        self, tmp_path: Path
    ) -> None:
        simulator = await _build_test_installation(tmp_path)
        try:
            with pytest.raises(ValueError, match="no group object named 'nonexistent'"):
                await run_scenario_file(
                    simulator,
                    _write(
                        tmp_path,
                        "s8.yaml",
                        "- at: 0\n"
                        "  device: living_room_thermostat\n"
                        "  action: write\n"
                        "  group_object: nonexistent\n"
                        "  value: 5\n",
                    ),
                )
        finally:
            await simulator.bus.stop()


async def test_the_bundled_demo_scenario_references_are_all_valid() -> None:
    # examples/demo-scenario.yaml is meant to run over ~18 real seconds
    # against examples/demo-house.yaml -- too slow for a unit test, and not
    # the point here anyway. This just proves every device/action/
    # group_object it references actually exists in demo-house.yaml (a
    # typo in either file would otherwise only surface when someone
    # actually runs the demo), by replaying the same steps with `at`
    # collapsed to 0.
    installation = load_installation_file(EXAMPLES_DIR / "demo-house.yaml")
    simulator = build_simulator(installation)
    simulator.bus.start()
    try:
        steps = load_scenario_file(EXAMPLES_DIR / "demo-scenario.yaml")
        fast_steps = [step.model_copy(update={"at": 0.0}) for step in steps]
        await run_scenario(simulator, fast_steps)
    finally:
        await simulator.bus.stop()


async def test_blind_reaches_50_percent_after_position_command_scenario(tmp_path: Path) -> None:
    # The SPEC's own literal example (docs/SPEC.md's testing strategy)
    # of a scenario doubling as a behavioral regression test, run through
    # the real pipeline end to end: a real installation YAML + a real
    # scenario YAML. travel_time_full_range is shortened so the test
    # doesn't wait on the real 20s default.
    config_file = _write(
        tmp_path,
        "install.yaml",
        "devices:\n"
        "  - type: blind\n"
        "    individual_address: '1.1.1'\n"
        "    name: living_room_blind\n"
        "    move_ga: '1/1/1'\n"
        "    stop_ga: '1/1/2'\n"
        "    position_ga: '1/1/3'\n"
        "    position_status_ga: '1/1/4'\n"
        "    moving_status_ga: '1/1/5'\n"
        "    travel_time_full_range: 1.0\n",
    )
    scenario_file = _write(
        tmp_path,
        "scenario.yaml",
        "- at: 0\n  device: living_room_blind\n  action: write\n"
        "  group_object: position\n  value: 50.0\n",
    )

    config = load_installation_file(config_file)
    simulator = build_simulator(config)
    simulator.bus.start()
    try:
        await run_scenario_file(simulator, scenario_file)
        # travel_time_full_range=1.0s for the full 0..100 range -> ~0.5s
        # to reach position 50; give it a comfortable margin.
        await asyncio.sleep(0.8)

        blind = simulator.devices[0]
        position = blind.group_objects["position_status"].value
        assert 48.0 <= position <= 52.0
    finally:
        await simulator.bus.stop()
