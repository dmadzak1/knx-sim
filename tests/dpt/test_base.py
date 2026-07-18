from __future__ import annotations

import pytest

from knx_sim.dpt.base import DPTBase, get_codec, register
from knx_sim.dpt.dpt1 import DPT1001


def test_get_codec_returns_registered_class() -> None:
    assert get_codec("1.001") is DPT1001


def test_get_codec_unknown_id_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="No DPT codec registered"):
        get_codec("99.999")


def test_register_duplicate_dpt_id_raises() -> None:
    class Dummy(DPTBase):
        dpt_id = "1.001"
        payload_length = 0

        @classmethod
        def encode(cls, value: object) -> bytes:
            return b""

        @classmethod
        def decode(cls, data: bytes) -> object:
            return None

    with pytest.raises(ValueError, match="already registered"):
        register(Dummy)
