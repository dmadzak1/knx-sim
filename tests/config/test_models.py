from __future__ import annotations

import pytest
from pydantic import ValidationError

from knx_sim.config.models import DeviceConfig, InstallationConfig, SimulatorConfig


class TestSimulatorConfig:
    def test_defaults(self) -> None:
        config = SimulatorConfig()
        assert config.name == "knx-sim"
        assert config.bind_address is None
        assert config.port == 3671
        assert config.individual_address == "15.15.0"
        assert config.max_tunnels == 4
        assert config.delay_seconds == 0.02

    def test_rejects_malformed_individual_address(self) -> None:
        with pytest.raises(ValidationError, match="Invalid individual address"):
            SimulatorConfig(individual_address="not-an-address")

    def test_rejects_out_of_range_port(self) -> None:
        with pytest.raises(ValidationError, match="port must be 1..65535"):
            SimulatorConfig(port=70000)

    def test_rejects_zero_max_tunnels(self) -> None:
        with pytest.raises(ValidationError, match="max_tunnels must be >= 1"):
            SimulatorConfig(max_tunnels=0)

    def test_rejects_negative_delay(self) -> None:
        with pytest.raises(ValidationError, match="delay_seconds must be >= 0"):
            SimulatorConfig(delay_seconds=-0.1)


class TestDeviceConfig:
    def test_requires_type_and_individual_address(self) -> None:
        with pytest.raises(ValidationError):
            DeviceConfig()  # type: ignore[call-arg]

    def test_rejects_malformed_individual_address(self) -> None:
        with pytest.raises(ValidationError, match="Invalid individual address"):
            DeviceConfig(type="switch", individual_address="nope")

    def test_extra_fields_are_kept(self) -> None:
        # Extra (device-specific) fields are only known at runtime via
        # extra="allow" -- pydantic's synthesized __init__ that mypy sees
        # only lists the declared fields, so construction from a dict via
        # model_validate() (as the real YAML loader does) rather than
        # keyword arguments, matching how production code always builds
        # these.
        config = DeviceConfig.model_validate(
            {
                "type": "switch",
                "individual_address": "1.1.1",
                "control_ga": "1/1/1",
                "status_ga": "1/1/2",
            }
        )
        assert config.require("control_ga") == "1/1/1"
        assert config.require("status_ga") == "1/1/2"

    def test_require_raises_on_missing_field(self) -> None:
        config = DeviceConfig(type="switch", individual_address="1.1.1")
        with pytest.raises(ValueError, match="missing required field 'control_ga'"):
            config.require("control_ga")

    def test_get_returns_default_when_absent(self) -> None:
        config = DeviceConfig(type="switch", individual_address="1.1.1")
        assert config.get("initial_value", False) is False

    def test_get_returns_value_when_present(self) -> None:
        config = DeviceConfig.model_validate(
            {"type": "switch", "individual_address": "1.1.1", "initial_value": True}
        )
        assert config.get("initial_value", False) is True


class TestInstallationConfig:
    def test_defaults_to_empty(self) -> None:
        config = InstallationConfig()
        assert config.devices == []
        assert config.simulator == SimulatorConfig()

    def test_accepts_multiple_devices_with_distinct_addresses(self) -> None:
        config = InstallationConfig.model_validate(
            {
                "devices": [
                    {"type": "switch", "individual_address": "1.1.1", "control_ga": "1/1/1"},
                    {"type": "switch", "individual_address": "1.1.2", "control_ga": "1/1/2"},
                ]
            }
        )
        assert len(config.devices) == 2

    def test_rejects_duplicate_individual_addresses(self) -> None:
        with pytest.raises(ValidationError, match="duplicate individual_address"):
            InstallationConfig.model_validate(
                {
                    "devices": [
                        {"type": "switch", "individual_address": "1.1.1", "control_ga": "1/1/1"},
                        {"type": "switch", "individual_address": "1.1.1", "control_ga": "1/1/2"},
                    ]
                }
            )
