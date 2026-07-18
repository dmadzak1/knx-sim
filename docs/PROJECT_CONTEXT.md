# PROJECT_CONTEXT — KNX Virtual Bus Simulator (`knx-sim`)

Read this first in every session. Full requirements live in `docs/SPEC.md`; the step-by-step beginner plan lives in `docs/GUIDE.md`.

## What we are building
A software simulator of a complete KNX home-automation installation: a virtual bus routing KNX telegrams between simulated devices (switches, dimmers, blinds, thermostats, sensors), exposed via a standards-compliant KNXnet/IP server (discovery, multicast routing, and tunneling on UDP 3671) so that real, unmodified KNX tools — xknx above all — can connect and operate the virtual house. A FastAPI + WebSocket web dashboard adds live telegram monitoring and manual control. No physical hardware is involved at any point.

## Why (context for design decisions)
The developer is learning embedded/home-automation protocols without access to hardware and wants a strong portfolio project. Educational value and code clarity outrank cleverness and performance. The single most important success criterion (v1 acceptance test): **a pip-installed, unmodified xknx client can tunnel in, switch a virtual light, read a virtual temperature, and receive spontaneous status telegrams.**

## The developer (how to work with them)
- New to protocol programming, binary formats, Wireshark, and asyncio networking. Experienced enough to code, but learning KNX from scratch.
- Always explain non-obvious code and protocol concepts, ideally with concrete byte-level examples.
- Work in small steps: one prompt = one small deliverable + tests + explanation. Never generate large multi-module chunks in one pass.
- Every new function gets pytest tests; run ruff + mypy (strict) before declaring work done.
- Ask before adding any dependency.

## Decided architecture (do not re-litigate without discussion)
- **Language/stack:** Python 3.11+, single process, single asyncio event loop. UDP via asyncio DatagramProtocol. Web layer: FastAPI + WebSockets (added late, milestone M7). Config: YAML validated with pydantic. Tests: pytest + pytest-asyncio + hypothesis.
- **Modules:** `knx_sim/dpt` (datapoint codecs, pure functions) · `knx_sim/cemi` (cEMI frame parser/builder + address types, pure functions) · `knx_sim/bus` (device registry, group-address routing, telegram log, ~20 ms simulated propagation delay, FIFO with priority) · `knx_sim/knxip` (discovery, routing, tunneling with explicit per-channel state machine) · `knx_sim/devices` (Device/GroupObject abstraction + device library) · `knx_sim/config` · `knx_sim/web` · `knx_sim/cli`.
- **Reference/verification strategy:** xknx is both a source-code reference and the independent test client — never validate the server only against our own client code. Byte-exact test fixtures come from Wireshark captures or frames produced by xknx itself.
- **Key protocol details already agreed:** DPTs of ≤6 bits are carried inside the APCI byte (codec exposes payload_length = 0 for these); DPT 9 uses the KNX 16-bit float (S EEEE MMMMMMMMMMM, value = 0.01·M·2^E); group addresses are 3-level (5/3/8 bits), individual addresses 4/4/8 bits; supported APCI services are GroupValueRead/Write/Response only.

## Explicit non-goals for v1 (out of scope — do not implement)
TP1 physical-layer simulation (bit timing, collisions, ACKs) beyond the fixed delay model; ETS device *programming* (memory writes, load procedures — ETS group monitoring is fine); KNX Secure; RF/PL110 media; historical telemetry persistence; authentication on the web UI (localhost tool, bind 127.0.0.1).

## Milestones and current status
M0 bootstrap → M1 DPT codec (1.001/1.008/1.009, 3.007, 5.001/5.004, 9.x, 7.x, 14.x) → M2 cEMI frames + addresses → M3 in-process bus + switch/lamp devices → M4 KNXnet/IP discovery + routing → M5 tunneling (hardest, the core deliverable: CONNECT/TUNNELING_REQUEST/ACK, sequence counters, CONNECTIONSTATE heartbeat, ≥4 concurrent tunnels) → M6 device library + YAML config → M7 web dashboard → M8 scenarios, docs, polish.

**Current status: M5 in progress (round B of 3 done).** Update the line below as work progresses.

> STATUS: M5 round B done (F-IP-3 state machine). Round A (wire format) done previously: knx_sim/knxip/tunneling.py -- ConnectRequest/Response, ConnectionStateRequest/Response, DisconnectRequest/Response, TunnellingRequest/Ack, Basic CRI/CRD only (Extended/Tunnelling-v2 out of scope), all verified byte-exact against xknx. wrap_frame/unwrap_frame extracted to knx_sim/knxip/_wire.py to avoid a frame.py<->tunneling.py circular import. Round B (this round): knx_sim/knxip/tunnel_channel.py -- TunnelChannel (pure state, no asyncio, no internal clock access -- mirrors the GroupObject/Device split from M3) with CONNECTING->CONNECTED->DISCONNECTING FSM (transition_to() validates against an explicit allowed-transitions map); independent inbound/outbound sequence-counter tracking, where the inbound ACCEPT/REPEAT/INVALID logic is a direct mirror of xknx's own client-side UDPTunnel._tunnelling_request_received (read from xknx/io/tunnel.py) applied from the server's side of the same protocol -- REPEAT means "client's retransmission because our ACK was lost, re-ACK but don't reprocess", INVALID means disconnect (strict mode only per developer's explicit choice; SPEC.md's optional lenient mode is deferred until a concrete need shows up); heartbeat staleness via is_stale(now, timeout) with externally-injected 'now', keeping it pure-testable without real 120s waits. TunnelRegistry: channel-id allocation (1..255, lowest-free-id reuse after disconnect), individual address = 15.15.<channel_id> (conventional KNXnet/IP interface range), capacity cap (default 4, matching F-IP-3's stated minimum, configurable higher) raising TunnelCapacityError when full. 340 tests passing, ruff+mypy strict clean. Next action: M5 round C -- wire TunnelChannel/TunnelRegistry into KnxIpServer (real asyncio: the 120s heartbeat timer, the 1s ACK-wait-and-retry-once-then-disconnect timer for our own outbound TunnellingRequests, per-channel relay of every bus telegram except back to its own originating channel -- distinct from routing's global has_device()-only relay rule), then the real multi-client xknx tunneling acceptance test (F-IP-4: connect, control a device, receive spontaneous status, two clients at once, kill-a-client heartbeat cleanup within 120s).

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
