# KNXnet/IP — annotated byte layouts (discovery, routing, tunneling)

Cross-checked against xknx's own implementation (`xknx/io/`,
`xknx/knxip/*`), the same way `docs/notes/cemi.md` was: bytes below are
reconstructed from this project's own wire-format code
(`knx_sim/knxip/header.py`, `hpai.py`, `dib.py`, `frame.py`,
`tunneling.py`) and independently cross-checked against how xknx's client
builds and parses the same frames.

Every KNXnet/IP frame shares one 6-byte header, then a service-specific
body:

```
06 10 <service type, 2 bytes> <total length, 2 bytes>
```

`06` = header length (always 6), `10` = protocol version 1.0, service
type selects which body format follows, total length is header + body
combined (so a receiver with only the header yet knows exactly how many
more bytes to read off the socket).

## Discovery: SEARCH_REQUEST / SEARCH_RESPONSE (F-IP-1)

A client that doesn't already know a server's address multicasts a
`SEARCH_REQUEST` to `224.0.23.12:3671` carrying an HPAI (Host Protocol
Address Information — an 8-byte "send your reply here" triple) for its
own discovery endpoint. Every server listening on that multicast group
unicasts back a `SEARCH_RESPONSE` describing itself.

### Worked example: SEARCH_REQUEST from a client at 192.168.1.50:50000

```
06 10 02 01 00 0E 08 01 C0 A8 01 32 C3 50
```

| Bytes | Value | Field |
|---|---|---|
| 0–5 | `06 10 02 01 00 0E` | header: length 6, v1.0, `SEARCH_REQUEST` (`0x0201`), total length 14 |
| 6 | `08` | HPAI length (always 8) |
| 7 | `01` | host protocol: `IPV4_UDP` |
| 8–11 | `C0 A8 01 32` | IP `192.168.1.50` |
| 12–13 | `C3 50` | port `50000` |

### SEARCH_RESPONSE structure

A server's `SEARCH_RESPONSE` body is three pieces back to back: its own
control-endpoint HPAI (8 bytes, "send DESCRIPTION/CONNECT requests
here"), a fixed 54-byte **Device Information DIB**, and a variable-length
**Supported Service Families DIB**:

| Field | Bytes | Notes |
|---|---|---|
| control endpoint | 8 | same HPAI layout as above |
| DIB length | 1 | `0x36` = 54 |
| DIB type code | 1 | `0x01` = DEVICE_INFO |
| KNX medium | 1 | `0x02` = TP1 (this simulator always claims TP1, the medium it's simulating) |
| programming mode | 1 | `0x00`/`0x01` |
| individual address | 2 | the server's own self-address, e.g. `15.15.0` → `FF 00` |
| project/installation id | 2 | unused, always `00 00` |
| serial number | 6 | unused, always zero |
| multicast address | 4 | `224.0.23.12` → `E0 00 17 0C` |
| MAC address | 6 | unused, always zero |
| device name | 30 | latin-1, null-padded, e.g. `"knx-sim-demo-house"` |
| services DIB length | 1 | `2 + 2 * (number of families)` |
| services DIB type code | 1 | `0x02` = SUPP_SVC_FAMILIES |
| family/version pairs | 2 each | e.g. `(CORE, 0x02, 0x01)`, `(TUNNELING, 0x04, 0x01)`, `(ROUTING, 0x05, 0x01)` — `DEVICE_MANAGEMENT` is deliberately *not* advertised, since programming virtual devices via ETS is out of scope (see SPEC.md non-goals) |

`DESCRIPTION_REQUEST`/`DESCRIPTION_RESPONSE` (unicast, once a client
already has an address) carry exactly the same DeviceInformationDIB +
SupportedServiceFamiliesDIB pair, just without the leading control
endpoint.

## Routing: ROUTING_INDICATION (F-IP-2)

The simplest service by far — the body is *just the raw cEMI frame*,
with zero extra wrapping. Reusing `docs/notes/cemi.md`'s own worked
example (`GroupValueWrite` ON, `1.1.23` → `1/2/10`):

```
06 10 05 30 00 11 29 00 BC E0 11 17 0A 0A 01 00 81
                   \_____________ same 11 bytes as cemi.md _____________/
```

Header says `ROUTING_INDICATION` (`0x0530`), total length `0x0011` = 17
(6 header + 11 cEMI). Every server multicasts every bus telegram this
way, and injects every multicast frame it receives back onto its own
bus — which is exactly why loop prevention (filtering on
`bus.has_device(telegram.source)`, see `knx_sim/knxip/server.py`'s
docstring) has to exist: without it, two simulators on the same network
would each treat the other's relay as "new" and re-relay it forever.

## Tunneling: the stateful part (F-IP-3)

Tunneling is where KNXnet/IP stops being "one frame in, one frame out"
and becomes a real connection with state, sequence numbers, and
timeouts — this is why M5 was the hardest milestone.

### Handshake: CONNECT_REQUEST / CONNECT_RESPONSE

A client opens a tunnel by sending its control and data HPAIs (usually
identical) plus a 4-byte **CRI** (Connection Request Information)
declaring what kind of connection it wants:

```
06 10 02 05 00 1A 08 01 C0 A8 01 32 C3 50 08 01 C0 A8 01 32 C3 51 04 04 02 00
```

| Bytes | Value | Field |
|---|---|---|
| 0–5 | `06 10 02 05 00 1A` | header: `CONNECT_REQUEST` (`0x0205`), total length 26 |
| 6–13 | `08 01 C0 A8 01 32 C3 50` | control endpoint HPAI: `192.168.1.50:50000` |
| 14–21 | `08 01 C0 A8 01 32 C3 51` | data endpoint HPAI: `192.168.1.50:50001` |
| 22 | `04` | CRI length (Basic CRI, always 4) |
| 23 | `04` | connection type: `TUNNEL_CONNECTION` |
| 24 | `02` | KNX layer: `DATA_LINK_LAYER` (Tunnelling Extended/Layer-other variants are out of scope) |
| 25 | `00` | reserved |

The server picks an unused channel ID, assigns the client its own
virtual individual address (F-IP-3), and replies with a 4-byte **CRD**
(Connection Response Data) instead of a CRI:

```
06 10 02 06 00 14 01 00 08 01 C0 A8 01 0A 0E 57 04 04 FF 01
```

| Bytes | Value | Field |
|---|---|---|
| 6 | `01` | assigned communication channel ID |
| 7 | `00` | status code: `E_NO_ERROR` |
| 8–15 | `08 01 C0 A8 01 0A 0E 57` | server's own data endpoint HPAI: `192.168.1.10:3671` |
| 16–19 | `04 04 FF 01` | CRD: length 4, request type `TUNNEL_CONNECTION`, assigned individual address `15.15.1` |

A rejected request (e.g. `E_NO_MORE_CONNECTIONS` if the ≥4-tunnel limit
is already used up) carries *only* channel ID + status — no HPAI/CRD —
since there's no connection to describe.

### TUNNELLING_REQUEST / TUNNELLING_ACK

Once connected, every cEMI frame in either direction travels inside a
`TUNNELLING_REQUEST`, and **must** be acknowledged with a
`TUNNELLING_ACK` referencing the same channel and sequence number:

```
06 10 04 20 00 15 04 01 00 00 29 00 BC E0 11 17 0A 0A 01 00 81
06 10 04 21 00 0A 04 01 00 00
```

| Frame | Bytes | Field |
|---|---|---|
| REQUEST | `04 01 00 00` | length 4, channel 1, sequence 0, reserved |
| REQUEST | `29 00 BC E0 ...` | the raw cEMI frame (same GroupValueWrite as above) |
| ACK | `04 01 00 00` | length 4, channel 1, sequence 0, status `E_NO_ERROR` |

### Sequence-counter discipline

Each direction of each channel keeps its own 0–255 wrapping counter,
independently. This project's rule (matching xknx's client-side logic
in `xknx/io/tunnel.py` exactly, just from the server's side of the same
protocol — see `knx_sim/knxip/tunnel_channel.py`) for an *inbound* frame's
sequence number, compared to what's expected next:

| received == | meaning | action |
|---|---|---|
| expected | new frame | process it, ACK it, advance the counter |
| expected − 1 (mod 256) | the client never saw our last ACK and retransmitted | re-send the same ACK, but don't reprocess the frame |
| anything else | protocol violation | drop the connection |

Outbound is the mirror image: the server tracks the sequence number of
the frame it just sent and waits up to 1s for the matching ACK; a
timeout means retry with the *same* sequence number (it only advances
once actually ACKed), not a new one.

### Connection lifecycle

```
        CONNECT_REQUEST received, channel assigned
                        |
                        v
   CONNECTING  ─────────────────────►  CONNECTED
                                            │
              DISCONNECT_REQUEST (either side),
              or CONNECTIONSTATE heartbeat not
              refreshed within 120s
                                            │
                                            v
                                    DISCONNECTING ──► removed from registry
```

A `CONNECTIONSTATE_REQUEST`/`RESPONSE` pair is the heartbeat: a
connected client is expected to send one periodically (well under 120s),
and a channel that goes quiet longer than that is torn down as if the
client had disconnected without asking — the only way the server can
detect a client that simply vanished (crashed, network partition) rather
than disconnecting cleanly.

## Implementation

See `knx_sim/knxip/header.py`/`hpai.py`/`dib.py` (discovery structures),
`knx_sim/knxip/frame.py` (`RoutingIndication`, the combined
`parse_frame()` dispatcher), `knx_sim/knxip/tunneling.py` (all the
CONNECT/CONNECTIONSTATE/DISCONNECT/TUNNELLING frame classes), and
`knx_sim/knxip/tunnel_channel.py` (the pure `TunnelChannel` state
machine + sequence-number decision logic, deliberately kept free of
asyncio/sockets/timers so it's testable without either). The real
timers and socket I/O built on top of that state machine live in
`knx_sim/knxip/server.py`.
