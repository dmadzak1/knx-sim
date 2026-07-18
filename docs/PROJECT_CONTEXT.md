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

**Current status: M4 done.** Update the line below as work progresses.

> STATUS: M4 done (F-IP-1, F-IP-2, F-IP-5). Wire format (round A): knx_sim/knxip/{header,hpai,dib,frame}.py -- Header/HPAI/DIB/5 frame types, all verified byte-exact against xknx (scripts/compare_knxip_with_xknx.py). knx_sim/knxip/server.py (round B): KnxIpServer, one UDP socket handling discovery + routing together (bound to the KNXnet/IP port, joined to the multicast group). Two Windows-specific networking gotchas discovered empirically and worth remembering for any future socket work on this project: (1) "127.0.0.1" does NOT work as a multicast interface (IP_MULTICAST_IF/IP_ADD_MEMBERSHIP) on Windows -- the server auto-detects a real local IP instead (same trick as xknx's own get_default_local_ip: connect a UDP socket to the target and read back getsockname()), bind_address defaults to None triggering this; (2) IP_MULTICAST_LOOP=0 on the receiving socket suppresses ALL local multicast delivery on Windows (not just self-originated packets, unlike documented POSIX semantics) -- left at its default (enabled) instead. Loop prevention (F-IP-2) is therefore handled entirely by Bus.has_device(telegram.source), applied on both directions: outbound (only relay locally-originated telegrams) and inbound (ignore a ROUTING_INDICATION claiming to be from one of our own devices -- covers both genuine self-echo and any nonsensical external claim). SupportedServiceFamiliesDIB advertises CORE v1 + ROUTING only (not TUNNELING -- that's M5). tests/test_knxip_integration.py is the real acceptance test: a genuine xknx GatewayScanner discovers the server via SEARCH, and a genuine xknx Routing-mode client switches a SwitchActuator and receives its spontaneous status telegram, all over real UDP multicast on localhost. 273 tests passing, ruff+mypy strict clean. Next action: M5 -- tunneling (F-IP-3), the hardest milestone and the core deliverable (CONNECT/TUNNELING_REQUEST/ACK, per-channel sequence counters, CONNECTIONSTATE heartbeat, ≥4 concurrent tunnels, explicit state machine); no guide steps beyond this point, design together as needed.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
