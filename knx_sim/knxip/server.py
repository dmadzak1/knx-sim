"""The KNXnet/IP server: discovery (F-IP-1), multicast routing (F-IP-2), and
tunneling (F-IP-3) over a single UDP socket.

One socket handles everything: it's bound to the KNXnet/IP port and joined
to the discovery multicast group, so it receives multicast SEARCH_REQUEST
and ROUTING_INDICATION traffic, unicast DESCRIPTION_REQUEST and all
tunneling requests sent directly to us -- and the same socket sends unicast
replies, multicasts outgoing ROUTING_INDICATIONs, and sends/receives
per-channel TUNNELLING_REQUEST/ACK frames.

Loop prevention (F-IP-2) is one mechanism, bus.has_device(telegram.source),
applied on both directions:
- Outbound: only re-multicast a bus telegram if it originated from one of
  our own registered devices -- never re-relay one that arrived from the
  network. Without this, two simulators/routers on the same network would
  bounce every telegram back and forth forever, since each would see the
  other's relay as "new" and re-relay it again.
- Inbound: ignore a received ROUTING_INDICATION whose cEMI source is one of
  our own devices -- it's either our own multicast echoing back or a
  nonsensical claim; either way we shouldn't re-inject it.

Note IP_MULTICAST_LOOP is deliberately left at its default (enabled), not
disabled: on Windows, disabling it empirically suppresses *all* local
multicast delivery to the socket, not just self-originated packets (unlike
the documented POSIX per-sending-socket semantics) -- it would have broken
receiving from every other local sender too, including a real xknx client
under test on the same machine. The has_device() check above handles the
self-echo case correctly regardless.

Tunneling relay is a *different* rule from routing's: a tunnel client
expects to see essentially everything on the bus, like a real device would
(or an ETS bus monitor) -- not just locally-originated telegrams. So every
bus telegram is relayed to every CONNECTED channel except the one channel
whose own individual_address matches telegram.source (so a client never
gets echoed its own just-sent write back). See TunnelChannel/TunnelRegistry
in knx_sim/knxip/tunnel_channel.py for the state machine this relies on --
this module owns the actual asyncio timers (heartbeat staleness, ACK
wait-and-retry) and socket I/O that state machine was deliberately built
without.

Another Windows unicast quirk, distinct from M4's multicast-loopback one:
when a client connects to us via 127.0.0.1, its own OS socket ends up bound
to loopback too (xknx's find_local_ip matches the gateway's scope) -- and a
socket bound to 127.0.0.1 on Windows cannot subsequently send to a
*different* real interface address. So whatever address we advertise back
to a client for future communication (CONNECT_RESPONSE's data_endpoint,
SEARCH_RESPONSE's control_endpoint) must match the scope the client is
already talking to us on: loopback if they reached us via loopback, our
real detected interface IP otherwise. See _advertised_ip().
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import sys
import time

from knx_sim.bus.router import Bus
from knx_sim.cemi.address import IndividualAddress
from knx_sim.cemi.frame import MessageCode, Telegram, build_cemi, parse_cemi
from knx_sim.cemi.frame import ParseError as CemiParseError
from knx_sim.knxip.dib import (
    DeviceInformationDIB,
    ServiceFamily,
    SupportedServiceFamiliesDIB,
    SupportedServiceFamily,
)
from knx_sim.knxip.errors import ParseError as KnxIpParseError
from knx_sim.knxip.frame import (
    DescriptionRequest,
    DescriptionResponse,
    RoutingIndication,
    SearchRequest,
    SearchResponse,
    parse_frame,
)
from knx_sim.knxip.hpai import HPAI
from knx_sim.knxip.tunnel_channel import (
    ChannelState,
    SequenceResult,
    TunnelCapacityError,
    TunnelChannel,
    TunnelRegistry,
)
from knx_sim.knxip.tunneling import (
    ConnectionStateRequest,
    ConnectionStateResponse,
    ConnectRequest,
    ConnectResponse,
    ConnectResponseData,
    DisconnectRequest,
    DisconnectResponse,
    ErrorCode,
    TunnellingAck,
    TunnellingRequest,
)

logger = logging.getLogger(__name__)

DEFAULT_MULTICAST_GROUP = "224.0.23.12"
DEFAULT_PORT = 3671
DEFAULT_INDIVIDUAL_ADDRESS = IndividualAddress(15, 15, 0)
DEFAULT_MAX_TUNNELS = 4
DEFAULT_HEARTBEAT_TIMEOUT = 120.0
DEFAULT_HEARTBEAT_CHECK_INTERVAL = 10.0
DEFAULT_ACK_TIMEOUT = 1.0


class KnxIpServer(asyncio.DatagramProtocol):
    """KNXnet/IP server bridging a Bus to the network (F-IP-1..3, F-IP-5)."""

    def __init__(
        self,
        bus: Bus,
        *,
        bind_address: str | None = None,
        port: int = DEFAULT_PORT,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        individual_address: IndividualAddress = DEFAULT_INDIVIDUAL_ADDRESS,
        friendly_name: str = "knx-sim",
        max_tunnels: int = DEFAULT_MAX_TUNNELS,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
        heartbeat_check_interval: float = DEFAULT_HEARTBEAT_CHECK_INTERVAL,
        ack_timeout: float = DEFAULT_ACK_TIMEOUT,
    ) -> None:
        """bind_address: the local interface to join the multicast group on
        and advertise as our control endpoint. None (default) auto-detects
        a working interface -- notably, on Windows "127.0.0.1" does NOT
        work as a multicast interface at all (confirmed empirically), so a
        hardcoded loopback default would silently break discovery/routing
        there. F-IP-5.

        heartbeat_timeout/heartbeat_check_interval/ack_timeout default to
        the real spec values (120s / 10s / 1s) but are constructor
        parameters specifically so tests can use tiny values instead of
        actually waiting on real wall-clock time.
        """
        self._bus = bus
        self._bind_address = bind_address
        self._port = port
        self._multicast_group = multicast_group
        self._individual_address = individual_address
        self._friendly_name = friendly_name
        self._transport: asyncio.DatagramTransport | None = None

        self._tunnels = TunnelRegistry(max_channels=max_tunnels)
        self._heartbeat_timeout = heartbeat_timeout
        self._heartbeat_check_interval = heartbeat_check_interval
        self._ack_timeout = ack_timeout
        self._pending_tunnel_acks: dict[tuple[int, int], asyncio.Future[ErrorCode]] = {}
        self._channel_send_locks: dict[int, asyncio.Lock] = {}
        self._heartbeat_task: asyncio.Task[None] | None = None

    # --- lifecycle ---

    async def start(self) -> None:
        if self._bind_address is None:
            self._bind_address = await self._detect_local_ip()
        sock = self._create_socket()
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(lambda: self, sock=sock)
        self._transport = transport
        self._bus.subscribe(self._on_bus_telegram)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _detect_local_ip(self) -> str:
        """Auto-detect a local interface IP by asking the OS which one it
        would use to reach the multicast group -- same trick xknx's own
        client uses (xknx.io.util.get_default_local_ip)."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.setblocking(False)
            loop = asyncio.get_running_loop()
            await loop.sock_connect(probe, (self._multicast_group, self._port))
            local_ip: str = probe.getsockname()[0]
            return local_ip

    async def stop(self) -> None:
        self._bus.unsubscribe(self._on_bus_telegram)
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        for channel in self._tunnels.all_channels():
            await self._terminate_channel(channel)
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @property
    def _local_ip(self) -> str:
        """The resolved bind address. Only valid after start() has run."""
        assert self._bind_address is not None, "server must be started first"
        return self._bind_address

    @property
    def active_tunnel_count(self) -> int:
        return len(self._tunnels)

    def _advertised_ip(self, peer_ip: str) -> str:
        """The IP we should tell a given peer to use for future
        communication with us -- see the module docstring's note on the
        Windows loopback-bind reachability quirk."""
        if ipaddress.ip_address(peer_ip).is_loopback:
            return "127.0.0.1"
        return self._local_ip

    def _create_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)

        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self._local_ip)
        )
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(self._multicast_group) + socket.inet_aton(self._local_ip),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        if sys.platform == "win32":
            # '' == INADDR_ANY; binding to the multicast address directly
            # doesn't work reliably on Windows.
            sock.bind(("", self._port))
        else:
            sock.bind((self._multicast_group, self._port))

        return sock

    # --- asyncio.DatagramProtocol callbacks (synchronous) ---

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.create_task(self._handle_datagram(data, addr))

    def error_received(self, exc: Exception) -> None:
        logger.debug("UDP error: %s", exc)

    # --- incoming ---

    async def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            frame = parse_frame(data)
        except KnxIpParseError as exc:
            logger.debug("Ignoring unparsable KNXnet/IP frame from %s: %s", addr, exc)
            return

        if isinstance(frame, SearchRequest):
            self._reply(
                SearchResponse(
                    control_endpoint=HPAI(self._advertised_ip(addr[0]), self._port),
                    device_info=self._device_info_dib(),
                    supported_services=self._supported_services_dib(),
                ),
                frame.discovery_endpoint,
                addr,
            )
        elif isinstance(frame, DescriptionRequest):
            self._reply(
                DescriptionResponse(
                    device_info=self._device_info_dib(),
                    supported_services=self._supported_services_dib(),
                ),
                frame.control_endpoint,
                addr,
            )
        elif isinstance(frame, RoutingIndication):
            await self._handle_routing_indication(frame)
        elif isinstance(frame, ConnectRequest):
            self._handle_connect_request(frame, addr)
        elif isinstance(frame, ConnectionStateRequest):
            self._handle_connectionstate_request(frame, addr)
        elif isinstance(frame, DisconnectRequest):
            self._handle_disconnect_request(frame, addr)
        elif isinstance(frame, TunnellingRequest):
            await self._handle_tunnelling_request(frame)
        elif isinstance(frame, TunnellingAck):
            self._handle_tunnelling_ack(frame)
        # SearchResponse/DescriptionResponse/ConnectResponse/
        # ConnectionStateResponse/DisconnectResponse arriving here would be
        # someone else's reply, not a request -- nothing for a server to do
        # with it (we never send the requests they'd be answering).

    async def _handle_routing_indication(self, frame: RoutingIndication) -> None:
        try:
            _, telegram = parse_cemi(frame.raw_cemi)
        except CemiParseError as exc:
            logger.debug("Ignoring unparsable cEMI in ROUTING_INDICATION: %s", exc)
            return
        if self._bus.has_device(telegram.source):
            return  # our own multicast echoing back, or a nonsensical claim
        await self._bus.inject(telegram)

    def _reply(
        self,
        response: SearchResponse | DescriptionResponse,
        reply_endpoint: HPAI,
        source_addr: tuple[str, int],
    ) -> None:
        dest = _resolve_reply_addr(reply_endpoint, source_addr)
        self._send(response.to_knx(), dest)

    # --- tunneling: CONNECT / CONNECTIONSTATE / DISCONNECT ---

    def _handle_connect_request(self, frame: ConnectRequest, addr: tuple[str, int]) -> None:
        # frame.cri already guarantees TUNNEL_CONNECTION + DATA_LINK_LAYER --
        # ConnectRequestInformation.from_knx() rejects anything else as a
        # ParseError before this handler ever runs, since our CRI enums only
        # define those single values (Basic CRI only; see tunneling.py).
        control_endpoint = _resolve_reply_addr(frame.control_endpoint, addr)
        data_endpoint = _resolve_reply_addr(frame.data_endpoint, addr)

        try:
            channel = self._tunnels.create_channel(
                control_endpoint, data_endpoint, now=time.monotonic()
            )
        except TunnelCapacityError:
            self._send(
                ConnectResponse(
                    communication_channel_id=0, status_code=ErrorCode.E_NO_MORE_CONNECTIONS
                ).to_knx(),
                addr,
            )
            return

        response = ConnectResponse(
            communication_channel_id=channel.channel_id,
            status_code=ErrorCode.E_NO_ERROR,
            data_endpoint=HPAI(self._advertised_ip(addr[0]), self._port),
            crd=ConnectResponseData(individual_address=channel.individual_address),
        )
        self._send(response.to_knx(), control_endpoint)
        channel.transition_to(ChannelState.CONNECTED)

    def _handle_connectionstate_request(
        self, frame: ConnectionStateRequest, addr: tuple[str, int]
    ) -> None:
        channel = self._tunnels.get(frame.communication_channel_id)
        if channel is None:
            status_code = ErrorCode.E_CONNECTION_ID
        else:
            channel.record_heartbeat(time.monotonic())
            status_code = ErrorCode.E_NO_ERROR
        response = ConnectionStateResponse(frame.communication_channel_id, status_code)
        self._send(response.to_knx(), _resolve_reply_addr(frame.control_endpoint, addr))

    def _handle_disconnect_request(self, frame: DisconnectRequest, addr: tuple[str, int]) -> None:
        channel = self._tunnels.get(frame.communication_channel_id)
        if channel is None:
            status_code = ErrorCode.E_CONNECTION_ID
        else:
            if channel.state is not ChannelState.DISCONNECTING:
                channel.transition_to(ChannelState.DISCONNECTING)
            self._tunnels.remove(channel.channel_id)
            status_code = ErrorCode.E_NO_ERROR
        response = DisconnectResponse(frame.communication_channel_id, status_code)
        self._send(response.to_knx(), _resolve_reply_addr(frame.control_endpoint, addr))

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_check_interval)
            now = time.monotonic()
            for channel in self._tunnels.all_channels():
                if channel.is_stale(now, timeout=self._heartbeat_timeout):
                    logger.debug("Tunnel channel %s heartbeat timed out", channel.channel_id)
                    await self._terminate_channel(channel)

    async def _terminate_channel(self, channel: TunnelChannel) -> None:
        """Best-effort, fire-and-forget teardown: tell the client, but don't
        wait for a DisconnectResponse (mirrors how xknx's own client handles
        an unplanned disconnect -- see _Tunnel._tunnel_lost in
        xknx/io/tunnel.py)."""
        if channel.state is not ChannelState.DISCONNECTING:
            channel.transition_to(ChannelState.DISCONNECTING)
        disconnect_request = DisconnectRequest(
            communication_channel_id=channel.channel_id,
            control_endpoint=HPAI(self._advertised_ip(channel.control_endpoint[0]), self._port),
        )
        self._send(disconnect_request.to_knx(), channel.control_endpoint)
        self._tunnels.remove(channel.channel_id)

    # --- tunneling: TUNNELLING_REQUEST/ACK (client -> server) ---

    async def _handle_tunnelling_request(self, frame: TunnellingRequest) -> None:
        channel = self._tunnels.get(frame.communication_channel_id)
        if channel is None:
            logger.debug(
                "Ignoring TunnellingRequest for unknown channel %s",
                frame.communication_channel_id,
            )
            return

        result = channel.check_inbound_sequence(frame.sequence_counter)
        if result is SequenceResult.ACCEPT:
            channel.advance_inbound_sequence()
            self._send_tunnelling_ack(channel, frame.sequence_counter, ErrorCode.E_NO_ERROR)
            try:
                _, telegram = parse_cemi(frame.raw_cemi)
            except CemiParseError as exc:
                logger.debug("Ignoring unparsable cEMI in TunnellingRequest: %s", exc)
                return
            await self._bus.inject(telegram)
        elif result is SequenceResult.REPEAT:
            # the client's retransmission because our ACK was lost -- re-ACK
            # but don't reprocess.
            self._send_tunnelling_ack(channel, frame.sequence_counter, ErrorCode.E_NO_ERROR)
        else:
            logger.debug(
                "Channel %s sent an out-of-sequence TunnellingRequest; disconnecting",
                channel.channel_id,
            )
            await self._terminate_channel(channel)

    def _send_tunnelling_ack(
        self, channel: TunnelChannel, sequence_counter: int, status_code: ErrorCode
    ) -> None:
        ack = TunnellingAck(channel.channel_id, sequence_counter, status_code)
        self._send(ack.to_knx(), channel.data_endpoint)

    def _handle_tunnelling_ack(self, frame: TunnellingAck) -> None:
        key = (frame.communication_channel_id, frame.sequence_counter)
        future = self._pending_tunnel_acks.get(key)
        if future is not None and not future.done():
            future.set_result(frame.status_code)

    # --- outgoing (bus -> network) ---

    async def _on_bus_telegram(self, telegram: Telegram) -> None:
        await self._relay_via_routing(telegram)
        await self._relay_via_tunnels(telegram)

    async def _relay_via_routing(self, telegram: Telegram) -> None:
        if not self._bus.has_device(telegram.source):
            return  # arrived from the network; don't re-relay (F-IP-2)
        cemi = build_cemi(telegram, MessageCode.L_DATA_IND)
        routing_indication = RoutingIndication(raw_cemi=cemi)
        self._send(routing_indication.to_knx(), (self._multicast_group, self._port))

    async def _relay_via_tunnels(self, telegram: Telegram) -> None:
        cemi = build_cemi(telegram, MessageCode.L_DATA_IND)
        for channel in self._tunnels.all_channels():
            if channel.state is not ChannelState.CONNECTED:
                continue
            if channel.individual_address == telegram.source:
                continue  # never echo a telegram back to its own channel
            # Channels relay concurrently with each other, but sends *within*
            # one channel must be serialized -- spec requires a confirmation
            # be awaited before the next telegram is sent on that channel,
            # and two bus telegrams processed back-to-back could otherwise
            # race on the same channel's outbound_sequence counter.
            asyncio.create_task(self._send_tunnelling_request_serialized(channel, cemi))

    async def _send_tunnelling_request_serialized(
        self, channel: TunnelChannel, raw_cemi: bytes
    ) -> None:
        lock = self._channel_send_locks.setdefault(channel.channel_id, asyncio.Lock())
        async with lock:
            if self._tunnels.get(channel.channel_id) is None:
                return  # channel was torn down while this was queued
            await self._send_tunnelling_request_with_retry(channel, raw_cemi)

    async def _send_tunnelling_request_with_retry(
        self, channel: TunnelChannel, raw_cemi: bytes
    ) -> None:
        """Send with retry, per spec: on timeout/error, retry once with the
        *same* sequence number; if that also fails, terminate the channel.

        Callers must hold this channel's send lock (see
        _send_tunnelling_request_serialized) -- this method itself doesn't
        serialize against concurrent calls for the same channel.
        """
        for _attempt in range(2):
            if self._tunnels.get(channel.channel_id) is None:
                return  # channel was torn down while we were retrying
            sequence_counter = channel.outbound_sequence
            status_code = await self._send_tunnelling_request_and_wait(
                channel, sequence_counter, raw_cemi
            )
            if status_code is ErrorCode.E_NO_ERROR:
                channel.advance_outbound_sequence()
                return
        await self._terminate_channel(channel)

    async def _send_tunnelling_request_and_wait(
        self, channel: TunnelChannel, sequence_counter: int, raw_cemi: bytes
    ) -> ErrorCode | None:
        key = (channel.channel_id, sequence_counter)
        future: asyncio.Future[ErrorCode] = asyncio.get_running_loop().create_future()
        self._pending_tunnel_acks[key] = future
        try:
            request = TunnellingRequest(channel.channel_id, sequence_counter, raw_cemi)
            self._send(request.to_knx(), channel.data_endpoint)
            try:
                return await asyncio.wait_for(future, timeout=self._ack_timeout)
            except TimeoutError:
                return None
        finally:
            self._pending_tunnel_acks.pop(key, None)

    def _send(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport is None:
            return
        self._transport.sendto(data, addr)

    # --- self-description ---

    def _device_info_dib(self) -> DeviceInformationDIB:
        return DeviceInformationDIB(
            individual_address=self._individual_address,
            name=self._friendly_name,
            multicast_address=self._multicast_group,
        )

    def _supported_services_dib(self) -> SupportedServiceFamiliesDIB:
        # CORE version 1, not 2: xknx's GatewayScanner skips a plain
        # SEARCH_RESPONSE from anything claiming Core v2, expecting
        # SEARCH_RESPONSE_EXTENDED instead (KNX IP Secure territory we
        # don't implement).
        return SupportedServiceFamiliesDIB(
            families=(
                SupportedServiceFamily(ServiceFamily.CORE, 1),
                SupportedServiceFamily(ServiceFamily.ROUTING, 1),
                SupportedServiceFamily(ServiceFamily.TUNNELING, 1),
            )
        )


def _resolve_reply_addr(endpoint: HPAI, source_addr: tuple[str, int]) -> tuple[str, int]:
    """route_back (endpoint.ip_addr == 0.0.0.0) means "reply to wherever
    this packet actually came from" (NAT traversal) instead of the
    self-declared address in the endpoint HPAI."""
    return source_addr if endpoint.route_back else (endpoint.ip_addr, endpoint.port)
