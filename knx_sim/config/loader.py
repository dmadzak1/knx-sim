"""Turn a YAML installation file into ready-to-start simulator objects
(F-CFG-1, F-CFG-2).

Two steps, kept separate: load_installation_file() parses + validates YAML
into an InstallationConfig (pure data, no I/O beyond reading the file);
build_simulator() wires that config into an actual Bus + KnxIpServer +
Device instances via the registry's from_config() classmethods. Neither
function starts anything (no bus.start()/server.start()) -- that stays the
caller's responsibility, matching how every existing Bus/KnxIpServer test
and (later) the M7/M8 CLI manage their own async lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import IndividualAddress
from knx_sim.config.models import DeviceConfig, InstallationConfig
from knx_sim.config.registry import build_device
from knx_sim.devices.device import Device
from knx_sim.knxip.server import KnxIpServer


def load_installation_file(path: str | Path) -> InstallationConfig:
    """Read and validate a YAML installation file."""
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    try:
        return InstallationConfig.model_validate(raw or {})
    except ValidationError as exc:
        raise ValueError(f"invalid installation config at {path}:\n{exc}") from exc


@dataclass
class Simulator:
    """A fully wired, not-yet-started simulator: bus, KNXnet/IP server, and
    every device registered onto the bus.

    device_configs pairs each built Device back to the DeviceConfig it came
    from, keyed by individual address -- Device itself only knows its
    group objects (a bus/protocol concern), not display metadata like
    name/room/type (a config concern), and the web dashboard (M7) needs
    both.
    """

    bus: Bus
    server: KnxIpServer
    devices: list[Device]
    device_configs: dict[IndividualAddress, DeviceConfig]


def build_simulator(config: InstallationConfig) -> Simulator:
    """Build a Bus + KnxIpServer + Devices from a validated InstallationConfig."""
    bus = Bus(delay_seconds=config.simulator.delay_seconds)
    devices = [build_device(device_config) for device_config in config.devices]
    for device in devices:
        bus.register(device)
    server = KnxIpServer(
        bus,
        bind_address=config.simulator.bind_address,
        port=config.simulator.port,
        individual_address=IndividualAddress.from_string(config.simulator.individual_address),
        friendly_name=config.simulator.name,
        max_tunnels=config.simulator.max_tunnels,
    )
    device_configs = {
        device.individual_address: device_config
        for device, device_config in zip(devices, config.devices, strict=True)
    }
    return Simulator(bus=bus, server=server, devices=devices, device_configs=device_configs)
