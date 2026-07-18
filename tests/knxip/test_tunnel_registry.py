from __future__ import annotations

import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip.tunnel_channel import ChannelState, TunnelCapacityError, TunnelRegistry

CONTROL_EP = ("192.168.1.5", 54321)
DATA_EP = ("192.168.1.5", 54321)


class TestConstruction:
    @pytest.mark.parametrize("bad_max", [0, -1, 256])
    def test_rejects_max_channels_out_of_range(self, bad_max: int) -> None:
        with pytest.raises(ValueError, match="max_channels must be 1..255"):
            TunnelRegistry(max_channels=bad_max)


class TestCreateChannel:
    def test_assigns_channel_id_starting_at_one(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        channel = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert channel.channel_id == 1

    def test_assigns_individual_address_from_channel_id(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        channel = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert channel.individual_address == IndividualAddress(15, 15, 1)

    def test_second_channel_gets_next_id(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        second = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert second.channel_id == 2

    def test_new_channel_starts_connecting(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        channel = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert channel.state is ChannelState.CONNECTING

    def test_len_reflects_active_channels(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        assert len(registry) == 0
        registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert len(registry) == 1


class TestCapacity:
    def test_raises_when_full(self) -> None:
        registry = TunnelRegistry(max_channels=2)
        registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        with pytest.raises(TunnelCapacityError, match="max concurrent tunnels"):
            registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)

    def test_supports_at_least_four_concurrent_tunnels(self) -> None:
        # F-IP-3: "support at least 4 concurrent tunnels" -- default must
        # satisfy this without extra configuration.
        registry = TunnelRegistry()
        for _ in range(4):
            registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert len(registry) == 4


class TestGetAndRemove:
    def test_get_returns_the_channel(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        created = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert registry.get(created.channel_id) is created

    def test_get_unknown_channel_returns_none(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        assert registry.get(99) is None

    def test_remove_frees_the_slot(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        created = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        registry.remove(created.channel_id)
        assert len(registry) == 0
        assert registry.get(created.channel_id) is None

    def test_remove_unknown_channel_is_a_no_op(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        registry.remove(99)  # must not raise

    def test_removed_channel_id_is_reused(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        first = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        registry.remove(first.channel_id)
        reused = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        assert reused.channel_id == first.channel_id


class TestAllChannels:
    def test_returns_every_registered_channel(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        a = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        b = registry.create_channel(CONTROL_EP, DATA_EP, now=0.0)
        all_channels = registry.all_channels()
        assert len(all_channels) == 2
        assert a in all_channels
        assert b in all_channels

    def test_empty_registry_returns_empty_tuple(self) -> None:
        registry = TunnelRegistry(max_channels=4)
        assert registry.all_channels() == ()
