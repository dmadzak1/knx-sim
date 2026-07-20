from __future__ import annotations

from pathlib import Path

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.loader import build_simulator, load_installation_file
from knx_sim.devices.switch import SwitchActuator, WallSwitch
from knx_sim.knxip.server import DEFAULT_PORT

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


class TestLoadInstallationFile:
    def test_loads_minimal_yaml(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        assert config.simulator.name == "knx-sim-minimal"
        assert len(config.devices) == 2
        assert {d.type for d in config.devices} == {"wall_switch", "switch"}

    def test_loads_demo_house_yaml(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "demo-house.yaml")
        assert len(config.devices) == 10
        assert len({d.individual_address for d in config.devices}) == 10
        assert {d.type for d in config.devices} == {
            "wall_switch",
            "switch",
            "dimmer",
            "blind",
            "thermostat",
            "presence",
        }
        assert {d.room for d in config.devices} == {"Living Room", "Bedroom"}

    def test_minimal_yaml_devices_have_no_room(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        assert all(d.room is None for d in config.devices)

    def test_raises_helpful_error_on_invalid_config(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(
            "devices:\n  - type: switch\n    individual_address: not-an-address\n"
        )
        with pytest.raises(ValueError, match="invalid installation config"):
            load_installation_file(bad_file)

    def test_raises_on_unknown_device_type_only_at_build_time(self, tmp_path: Path) -> None:
        # Unknown "type" strings pass YAML validation (DeviceConfig.type is
        # just a str) -- the registry only rejects them at build_device()
        # time, so build_simulator() is where this actually surfaces.
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(
            "devices:\n  - type: teleporter\n    individual_address: '1.1.1'\n"
        )
        config = load_installation_file(bad_file)
        with pytest.raises(ValueError, match="unknown device type 'teleporter'"):
            build_simulator(config)


class TestBuildSimulator:
    async def test_wires_devices_onto_the_bus(self) -> None:
        # build_simulator() registers each device on the bus, and
        # Bus.register() schedules device.start() as a background task --
        # that needs a running event loop, hence this test being async.
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        simulator = build_simulator(config)
        try:
            assert len(simulator.devices) == 2
            assert simulator.bus.has_device(IndividualAddress(1, 1, 1))
            assert simulator.bus.has_device(IndividualAddress(1, 1, 2))

            wall_switch = next(d for d in simulator.devices if isinstance(d, WallSwitch))
            lamp = next(d for d in simulator.devices if isinstance(d, SwitchActuator))
            assert wall_switch.group_objects["control"].group_address == GroupAddress(1, 1, 1)
            assert lamp.group_objects["status"].group_address == GroupAddress(1, 1, 2)
        finally:
            await simulator.bus.stop()

    async def test_device_configs_pairs_each_device_with_its_config(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        simulator = build_simulator(config)
        try:
            assert len(simulator.device_configs) == 2
            wall_switch = next(d for d in simulator.devices if isinstance(d, WallSwitch))
            device_config = simulator.device_configs[wall_switch.individual_address]
            assert device_config.name == "hallway_switch"
            assert device_config.type == "wall_switch"
        finally:
            await simulator.bus.stop()

    async def test_server_reflects_simulator_config(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        simulator = build_simulator(config)
        try:
            assert simulator.server._friendly_name == "knx-sim-minimal"
            assert simulator.server._port == DEFAULT_PORT
        finally:
            await simulator.bus.stop()

    async def test_group_address_names_parsed_from_registry(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "demo-house.yaml")
        simulator = build_simulator(config)
        try:
            assert simulator.group_address_names[GroupAddress(1, 1, 1)] == (
                "Living Room Light A1"
            )
            assert len(simulator.group_address_names) == 26
        finally:
            await simulator.bus.stop()

    async def test_minimal_yaml_has_no_group_address_names(self) -> None:
        config = load_installation_file(EXAMPLES_DIR / "minimal.yaml")
        simulator = build_simulator(config)
        try:
            assert simulator.group_address_names == {}
        finally:
            await simulator.bus.stop()
