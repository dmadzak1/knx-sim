"""Per-channel tunneling state machine and channel registry (M5, F-IP-3).

Pure state and decision logic -- no asyncio, no direct clock access. This
mirrors the GroupObject/Device split from M3: TunnelChannel holds state and
answers "what should happen" questions (is this sequence number valid? is
this channel stale?) without performing any I/O or owning any timers itself.
The actual asyncio timers (120s heartbeat staleness, 1s ACK-wait-and-retry)
and the real send/receive plumbing are owned by KnxIpServer, which calls
into these pure methods to make its decisions -- kept as a separate round
specifically so this state machine is testable without spinning up real
sockets or waiting on real wall-clock time.

State machine: CONNECTING -> CONNECTED -> DISCONNECTING (see
docs/PROJECT_CONTEXT.md / SPEC.md F-IP-3 for the full narrative). A channel
in DISCONNECTING is removed from the registry once teardown completes;
there is no further state after that -- the channel object is simply
discarded.

Sequence-counter discipline mirrors xknx's own client-side logic exactly
(read directly from xknx/io/tunnel.py's UDPTunnel._tunnelling_request_received
and _Tunnel.send_cemi/_increase_sequence_number), just from the server's
side of the same protocol:
- Inbound (client -> server): sequence_counter == expected -> ACCEPT
  (process, then advance); == expected-1 mod 256 -> REPEAT (the client's
  retransmission because our ACK was lost -- re-ACK but don't reprocess);
  anything else -> INVALID (protocol violation; the caller disconnects).
- Outbound (server -> client): we track the sequence number for the frame
  we're about to send / already sent; it only advances after that frame is
  successfully ACKed. A failed/timed-out ACK means the caller retries with
  the *same* sequence number, not a new one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from knx_sim.cemi.address import IndividualAddress

_SEQUENCE_MODULUS = 256


class ChannelState(Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


_VALID_TRANSITIONS: dict[ChannelState, frozenset[ChannelState]] = {
    ChannelState.CONNECTING: frozenset({ChannelState.CONNECTED, ChannelState.DISCONNECTING}),
    ChannelState.CONNECTED: frozenset({ChannelState.DISCONNECTING}),
    ChannelState.DISCONNECTING: frozenset(),
}


class SequenceResult(Enum):
    ACCEPT = "accept"  # matches expected -- process it
    REPEAT = "repeat"  # client's retransmission of the last frame -- re-ACK, discard
    INVALID = "invalid"  # protocol violation -- caller should disconnect


@dataclass
class TunnelChannel:
    """One tunnel connection's state: identity, endpoints, FSM state, and
    the two independent sequence-counter directions."""

    channel_id: int
    individual_address: IndividualAddress
    control_endpoint: tuple[str, int]
    data_endpoint: tuple[str, int]
    created_at: float
    state: ChannelState = ChannelState.CONNECTING
    outbound_sequence: int = 0
    inbound_sequence: int = 0
    last_heartbeat: float = field(init=False)

    def __post_init__(self) -> None:
        if not 1 <= self.channel_id <= 255:
            raise ValueError(f"channel_id must be 1..255, got {self.channel_id}")
        self.last_heartbeat = self.created_at

    # --- FSM ---

    def transition_to(self, new_state: ChannelState) -> None:
        if new_state not in _VALID_TRANSITIONS[self.state]:
            raise ValueError(f"Cannot transition from {self.state.name} to {new_state.name}")
        self.state = new_state

    # --- inbound sequence (client -> server) ---

    def check_inbound_sequence(self, sequence_counter: int) -> SequenceResult:
        if sequence_counter == self.inbound_sequence:
            return SequenceResult.ACCEPT
        if sequence_counter == (self.inbound_sequence - 1) % _SEQUENCE_MODULUS:
            return SequenceResult.REPEAT
        return SequenceResult.INVALID

    def advance_inbound_sequence(self) -> None:
        self.inbound_sequence = (self.inbound_sequence + 1) % _SEQUENCE_MODULUS

    # --- outbound sequence (server -> client) ---

    def is_expected_ack(self, sequence_counter: int) -> bool:
        return sequence_counter == self.outbound_sequence

    def advance_outbound_sequence(self) -> None:
        self.outbound_sequence = (self.outbound_sequence + 1) % _SEQUENCE_MODULUS

    # --- heartbeat staleness ---

    def record_heartbeat(self, now: float) -> None:
        self.last_heartbeat = now

    def is_stale(self, now: float, timeout: float = 120.0) -> bool:
        return (now - self.last_heartbeat) >= timeout


class TunnelCapacityError(Exception):
    """Raised when accepting a new tunnel would exceed max_channels."""


class TunnelRegistry:
    """Allocates channel ids (1..255, reused after disconnect) and
    individual addresses (15.15.<channel_id>, the conventional KNXnet/IP
    interface range) for connected tunnels, and enforces a capacity cap."""

    def __init__(self, max_channels: int = 4) -> None:
        if not 1 <= max_channels <= 255:
            raise ValueError(f"max_channels must be 1..255, got {max_channels}")
        self._max_channels = max_channels
        self._channels: dict[int, TunnelChannel] = {}

    @property
    def max_channels(self) -> int:
        return self._max_channels

    def __len__(self) -> int:
        return len(self._channels)

    def create_channel(
        self,
        control_endpoint: tuple[str, int],
        data_endpoint: tuple[str, int],
        now: float,
    ) -> TunnelChannel:
        if len(self._channels) >= self._max_channels:
            raise TunnelCapacityError(f"max concurrent tunnels ({self._max_channels}) reached")
        channel_id = self._allocate_channel_id()
        channel = TunnelChannel(
            channel_id=channel_id,
            individual_address=IndividualAddress(15, 15, channel_id),
            control_endpoint=control_endpoint,
            data_endpoint=data_endpoint,
            created_at=now,
        )
        self._channels[channel_id] = channel
        return channel

    def get(self, channel_id: int) -> TunnelChannel | None:
        return self._channels.get(channel_id)

    def remove(self, channel_id: int) -> None:
        self._channels.pop(channel_id, None)

    def all_channels(self) -> tuple[TunnelChannel, ...]:
        return tuple(self._channels.values())

    def _allocate_channel_id(self) -> int:
        for candidate in range(1, 256):
            if candidate not in self._channels:
                return candidate
        raise AssertionError(  # pragma: no cover
            "unreachable: max_channels <= 255 caps concurrent channels below the id space"
        )
