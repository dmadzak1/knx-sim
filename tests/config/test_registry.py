from __future__ import annotations

import pytest

from knx_sim.cemi.address import GroupAddress, IndividualAddress
from knx_sim.config.models import DeviceConfig
from knx_sim.config.registry import DEVICE_TYPES, build_device
from knx_sim.devices.blind import BlindActuator
from knx_sim.devices.dimmer import DimmerActuator
from knx_sim.devices.presence import PresenceSensor
from knx_sim.devices.switch import SwitchActuator, WallSwitch
from knx_sim.devices.thermostat import Thermostat

# DeviceConfig's extra (device-specific) fields only exist at runtime via
# extra="allow" -- mypy's view of pydantic's synthesized __init__ only
# knows the declared fields, so every config with extra fields below is
# built via model_validate(dict) rather than keyword arguments, matching
# how production code (the YAML loader) always builds these.


def test_all_device_types_registered() -> None:
    assert set(DEVICE_TYPES) == {
        "switch",
        "wall_switch",
        "dimmer",
        "blind",
        "thermostat",
        "presence",
    }


def test_unknown_type_raises_helpful_error() -> None:
    config = DeviceConfig(type="teleporter", individual_address="1.1.1")
    with pytest.raises(ValueError, match="unknown device type 'teleporter'"):
        build_device(config)


class TestBuildSwitch:
    def test_builds_switch_actuator(self) -> None:
        config = DeviceConfig.model_validate(
            {
                "type": "switch",
                "individual_address": "1.1.1",
                "control_ga": "1/1/1",
                "status_ga": "1/1/2",
                "initial_value": True,
            }
        )
        device = build_device(config)
        assert isinstance(device, SwitchActuator)
        assert device.individual_address == IndividualAddress(1, 1, 1)
        assert device.group_objects["control"].group_address == GroupAddress(1, 1, 1)
        assert device.group_objects["status"].group_address == GroupAddress(1, 1, 2)
        assert device.group_objects["status"].value is True

    def test_missing_required_field_raises(self) -> None:
        config = DeviceConfig.model_validate(
            {"type": "switch", "individual_address": "1.1.1", "control_ga": "1/1/1"}
        )
        with pytest.raises(ValueError, match="missing required field 'status_ga'"):
            build_device(config)


class TestBuildWallSwitch:
    def test_builds_wall_switch(self) -> None:
        config = DeviceConfig.model_validate(
            {"type": "wall_switch", "individual_address": "1.1.9", "control_ga": "1/1/1"}
        )
        device = build_device(config)
        assert isinstance(device, WallSwitch)
        assert device.group_objects["control"].group_address == GroupAddress(1, 1, 1)


class TestBuildDimmer:
    def test_builds_dimmer_actuator(self) -> None:
        config = DeviceConfig.model_validate(
            {
                "type": "dimmer",
                "individual_address": "1.1.2",
                "switch_ga": "1/1/10",
                "relative_dim_ga": "1/1/11",
                "brightness_ga": "1/1/12",
                "switch_status_ga": "1/1/13",
                "brightness_status_ga": "1/1/14",
                "initial_brightness": 50.0,
                "ramp_time_full_range": 4.0,
            }
        )
        device = build_device(config)
        assert isinstance(device, DimmerActuator)
        assert device.group_objects["brightness_status"].value == 50.0
        assert device.group_objects["switch_status"].value is True


class TestBuildBlind:
    def test_builds_blind_actuator(self) -> None:
        config = DeviceConfig.model_validate(
            {
                "type": "blind",
                "individual_address": "1.1.3",
                "move_ga": "1/2/1",
                "stop_ga": "1/2/2",
                "position_ga": "1/2/3",
                "position_status_ga": "1/2/4",
                "moving_status_ga": "1/2/5",
                "initial_position": 25.0,
            }
        )
        device = build_device(config)
        assert isinstance(device, BlindActuator)
        assert device.group_objects["position_status"].value == 25.0


class TestBuildThermostat:
    def test_builds_thermostat(self) -> None:
        config = DeviceConfig.model_validate(
            {
                "type": "thermostat",
                "individual_address": "1.1.4",
                "temperature_ga": "1/3/1",
                "setpoint_ga": "1/3/2",
                "heating_demand_ga": "1/3/3",
                "initial_temperature": 19.5,
                "initial_setpoint": 22.0,
            }
        )
        device = build_device(config)
        assert isinstance(device, Thermostat)
        assert device.group_objects["temperature"].value == 19.5
        assert device.group_objects["setpoint"].value == 22.0


class TestBuildPresence:
    def test_builds_presence_sensor(self) -> None:
        config = DeviceConfig.model_validate(
            {
                "type": "presence",
                "individual_address": "1.1.5",
                "presence_ga": "1/4/1",
                "hold_time": 45.0,
                "random_activity": True,
            }
        )
        device = build_device(config)
        assert isinstance(device, PresenceSensor)
        assert device.group_objects["presence"].group_address == GroupAddress(1, 4, 1)
