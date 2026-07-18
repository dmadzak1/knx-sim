"""Declarative YAML installation config: pydantic models + device registry.

Note: knx_sim.config.registry (DEVICE_TYPES, build_device) and
knx_sim.config.loader (load_installation_file, build_simulator, Simulator)
are deliberately NOT re-exported here -- both import every Device subclass
(loader via registry), and each Device subclass imports
knx_sim.config.models; re-exporting either from this package's __init__
would close a circular import (importing knx_sim.config.models forces this
__init__ to run first). Import them directly, e.g.
`from knx_sim.config.loader import build_simulator, load_installation_file`.
"""

from knx_sim.config.models import DeviceConfig, InstallationConfig, SimulatorConfig

__all__ = [
    "DeviceConfig",
    "InstallationConfig",
    "SimulatorConfig",
]
