"""Datapoint Type (DPT) codec base class and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class DPTBase(ABC):
    """Base class for a KNX Datapoint Type codec.

    A concrete subclass converts one specific DPT (e.g. "1.001") between a
    Python value and its KNX wire representation.
    """

    dpt_id: ClassVar[str]
    """The DPT identifier this codec implements, e.g. "1.001"."""

    payload_length: ClassVar[int]
    """Number of bytes this DPT occupies as a *separate* cEMI payload.

    KNX packs any DPT of 6 bits or fewer inside the APCI byte itself instead
    of appending payload bytes after it. Those DPTs report payload_length=0;
    encode() still returns a bytes object holding the normalized value, which
    the cEMI layer (built in M2) merges into the APCI byte rather than
    appending as separate payload.
    """

    @classmethod
    @abstractmethod
    def encode(cls, value: Any) -> bytes:
        """Convert a Python value to its KNX wire bytes."""

    @classmethod
    @abstractmethod
    def decode(cls, data: bytes) -> Any:
        """Convert KNX wire bytes back to a Python value."""


_REGISTRY: dict[str, type[DPTBase]] = {}


def register(codec: type[DPTBase]) -> type[DPTBase]:
    """Class decorator that adds a DPT codec to the global registry."""
    if codec.dpt_id in _REGISTRY:
        raise ValueError(f"DPT {codec.dpt_id!r} is already registered")
    _REGISTRY[codec.dpt_id] = codec
    return codec


def get_codec(dpt_id: str) -> type[DPTBase]:
    """Look up a registered DPT codec by id, e.g. "1.001"."""
    try:
        return _REGISTRY[dpt_id]
    except KeyError:
        raise KeyError(
            f"No DPT codec registered for {dpt_id!r}. Known: {sorted(_REGISTRY)}"
        ) from None
