"""The KNXnet/IP server: discovery (F-IP-1) and multicast routing (F-IP-2)
over a single UDP socket. Tunneling (M5) extends this same class later.

One socket handles everything: it's bound to the KNXnet/IP port and joined
to the discovery multicast group, so it receives multicast SEARCH_REQUEST
and ROUTING_INDICATION traffic as well as any unicast DESCRIPTION_REQUEST
sent directly to us -- and the same socket sends unicast replies and
multicasts outgoing ROUTING_INDICATIONs.

Loop prevention (F-IP-2) is one mechanism, bus.has_device(telegram.source),
applied on both directions:
- Outbound: only re-multicast a bus telegram if it originated from one of
  our own registered devices -- never re-relay one that arrived from the
  network. Without this, two simulators/routers on the same network would
  bounce every telegram back and forth forever, since each would see the
  other's relay as "new" and re-relay it again.
- Inbound: ignore a received ROUTING_INDICATION whose cEMI source is one of
  our own devices -- it's either our own multicast echoing back (see below)
  or a nonsensical claim; either way we shouldn't re-inject it.

Note IP_MULTICAST_LOOP is deliberately left at its default (enabled), not
disabled: on Windows, disabling it empirically suppresses *all* local
multicast delivery to the socket, not just self-originated packets (unlike
the documented POSIX per-sending-socket semantics) -- it would have broken
receiving from every other local sender too, including a real xknx client
under test on the same machine. The has_device() check above handles the
self-echo case correctly regardless.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import sys

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

logger = logging.getLogger(__name__)

DEFAULT_MULTICAST_GROUP = "224.0.23.12"
DEFAULT_PORT = 3671
DEFAULT_INDIVIDUAL_ADDRESS = IndividualAddress(15, 15, 0)


class KnxIpServer(asyncio.DatagramProtocol):
    """KNXnet/IP server bridging a Bus to the network (F-IP-1, F-IP-2, F-IP-5)."""

    def __init__(
        self,
        bus: Bus,
        *,
        bind_address: str | None = None,
        port: int = DEFAULT_PORT,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        individual_address: IndividualAddress = DEFAULT_INDIVIDUAL_ADDRESS,
        friendly_name: str = "knx-sim",
    ) -> None:
        """bind_address: the local interface to join the multicast group on
        and advertise as our control endpoint. None (default) auto-detects
        a working interface -- notably, on Windows "127.0.0.1" does NOT
        work as a multicast interface at all (confirmed empirically), so a
        hardcoded loopback default would silently break discovery/routing
        there. F-IP-5.
        """
        self._bus = bus
        self._bind_address = bind_address
        self._port = port
        self._multicast_group = multicast_group
        self._individual_address = individual_address
        self._friendly_name = friendly_name
        self._transport: asyncio.DatagramTransport | None = None

    # --- lifecycle ---

    async def start(self) -> None:
        if self._bind_address is None:
            self._bind_address = await self._detect_local_ip()
        sock = self._create_socket()
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(lambda: self, sock=sock)
        self._transport = transport
        self._bus.subscribe(self._on_bus_telegram)

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
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @property
    def _local_ip(self) -> str:
        """The resolved bind address. Only valid after start() has run."""
        assert self._bind_address is not None, "server must be started first"
        return self._bind_address

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
                    control_endpoint=HPAI(self._local_ip, self._port),
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
        # SearchResponse/DescriptionResponse arriving here would be someone
        # else's reply, not a request -- nothing for a server to do with it.

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
        dest = (
            source_addr
            if reply_endpoint.route_back
            else (reply_endpoint.ip_addr, reply_endpoint.port)
        )
        self._send(response.to_knx(), dest)

    # --- outgoing (bus -> network) ---

    async def _on_bus_telegram(self, telegram: Telegram) -> None:
        if not self._bus.has_device(telegram.source):
            return  # arrived from the network; don't re-relay (F-IP-2)
        cemi = build_cemi(telegram, MessageCode.L_DATA_IND)
        routing_indication = RoutingIndication(raw_cemi=cemi)
        self._send(routing_indication.to_knx(), (self._multicast_group, self._port))

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
        # don't implement). ROUTING only, not TUNNELING -- that's M5;
        # claiming it now would make xknx attempt tunneling and fail.
        return SupportedServiceFamiliesDIB(
            families=(
                SupportedServiceFamily(ServiceFamily.CORE, 1),
                SupportedServiceFamily(ServiceFamily.ROUTING, 1),
            )
        )
