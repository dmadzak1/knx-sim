"""Declarative YAML installation config: pydantic models + device registry.

Note: knx_sim.config.registry (DEVICE_TYPES, build_device) is deliberately
NOT re-exported here -- it imports every Device subclass, each of which
imports knx_sim.config.models; re-exporting it from this package's __init__
would make that a circular import (importing knx_sim.config.models forces
this __init__ to run first). Import it directly:
`from knx_sim.config.registry import build_device`.
"""

from knx_sim.config.models import DeviceConfig, InstallationConfig, SimulatorConfig

__all__ = [
    "DeviceConfig",
    "InstallationConfig",
    "SimulatorConfig",
]
