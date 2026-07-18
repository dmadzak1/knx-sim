from __future__ import annotations

import pytest

from knx_sim.cemi.address import IndividualAddress
from knx_sim.knxip.tunnel_channel import ChannelState, SequenceResult, TunnelChannel

CONTROL_EP = ("192.168.1.5", 54321)
DATA_EP = ("192.168.1.5", 54321)


def _make(channel_id: int = 1, now: float = 1000.0) -> TunnelChannel:
    return TunnelChannel(
        channel_id=channel_id,
        individual_address=IndividualAddress(15, 15, channel_id),
        control_endpoint=CONTROL_EP,
        data_endpoint=DATA_EP,
        created_at=now,
    )


class TestConstruction:
    def test_starts_in_connecting_state(self) -> None:
        channel = _make()
        assert channel.state is ChannelState.CONNECTING

    def test_starts_with_zero_sequence_counters(self) -> None:
        channel = _make()
        assert channel.outbound_sequence == 0
        assert channel.inbound_sequence == 0

    def test_last_heartbeat_defaults_to_created_at(self) -> None:
        channel = _make(now=1234.5)
        assert channel.last_heartbeat == 1234.5

    @pytest.mark.parametrize("bad_id", [0, -1, 256])
    def test_rejects_channel_id_out_of_range(self, bad_id: int) -> None:
        with pytest.raises(ValueError, match="channel_id must be 1..255"):
            TunnelChannel(
                channel_id=bad_id,
                individual_address=IndividualAddress(15, 15, 1),
                control_endpoint=CONTROL_EP,
                data_endpoint=DATA_EP,
                created_at=0.0,
            )


class TestStateMachine:
    def test_connecting_to_connected(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.CONNECTED)
        assert channel.state is ChannelState.CONNECTED

    def test_connecting_to_disconnecting(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.DISCONNECTING)
        assert channel.state is ChannelState.DISCONNECTING

    def test_connected_to_disconnecting(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.CONNECTED)
        channel.transition_to(ChannelState.DISCONNECTING)
        assert channel.state is ChannelState.DISCONNECTING

    def test_cannot_go_back_to_connecting(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.CONNECTED)
        with pytest.raises(ValueError, match="Cannot transition from CONNECTED to CONNECTING"):
            channel.transition_to(ChannelState.CONNECTING)

    def test_disconnecting_is_terminal(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.DISCONNECTING)
        with pytest.raises(ValueError, match="Cannot transition from DISCONNECTING"):
            channel.transition_to(ChannelState.CONNECTED)

    def test_same_state_transition_is_rejected(self) -> None:
        channel = _make()
        channel.transition_to(ChannelState.CONNECTED)
        with pytest.raises(ValueError, match="Cannot transition from CONNECTED to CONNECTED"):
            channel.transition_to(ChannelState.CONNECTED)


class TestInboundSequence:
    def test_accepts_expected_sequence(self) -> None:
        channel = _make()
        assert channel.check_inbound_sequence(0) is SequenceResult.ACCEPT

    def test_repeat_of_last_accepted_frame(self) -> None:
        channel = _make()
        channel.advance_inbound_sequence()  # now expecting 1
        assert channel.check_inbound_sequence(0) is SequenceResult.REPEAT

    def test_invalid_out_of_order_sequence(self) -> None:
        channel = _make()
        assert channel.check_inbound_sequence(5) is SequenceResult.INVALID

    def test_advance_increments_expected_sequence(self) -> None:
        channel = _make()
        channel.advance_inbound_sequence()
        assert channel.inbound_sequence == 1
        assert channel.check_inbound_sequence(1) is SequenceResult.ACCEPT

    def test_wraps_at_256(self) -> None:
        channel = _make()
        channel.inbound_sequence = 255
        channel.advance_inbound_sequence()
        assert channel.inbound_sequence == 0

    def test_repeat_check_wraps_correctly_at_zero(self) -> None:
        channel = _make()
        # expected == 0 -> "repeat of the previous frame" is seq 255 (wrap)
        assert channel.check_inbound_sequence(255) is SequenceResult.REPEAT


class TestOutboundSequence:
    def test_is_expected_ack(self) -> None:
        channel = _make()
        assert channel.is_expected_ack(0) is True
        assert channel.is_expected_ack(1) is False

    def test_advance_increments(self) -> None:
        channel = _make()
        channel.advance_outbound_sequence()
        assert channel.outbound_sequence == 1
        assert channel.is_expected_ack(1) is True

    def test_wraps_at_256(self) -> None:
        channel = _make()
        channel.outbound_sequence = 255
        channel.advance_outbound_sequence()
        assert channel.outbound_sequence == 0


class TestHeartbeat:
    def test_not_stale_before_timeout(self) -> None:
        channel = _make(now=1000.0)
        assert channel.is_stale(now=1000.0 + 119.9, timeout=120.0) is False

    def test_stale_at_timeout_boundary(self) -> None:
        channel = _make(now=1000.0)
        assert channel.is_stale(now=1000.0 + 120.0, timeout=120.0) is True

    def test_record_heartbeat_resets_staleness(self) -> None:
        channel = _make(now=1000.0)
        channel.record_heartbeat(now=1090.0)
        assert channel.is_stale(now=1090.0 + 119.9, timeout=120.0) is False
