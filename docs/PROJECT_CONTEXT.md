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

**Current status: M4 in progress (round A of 2 done).** Update the line below as work progresses.

> STATUS: M4 round A done (KNXnet/IP wire format, F-IP-1/F-IP-2 byte layer). knx_sim/knxip/header.py: Header (6 bytes) + ServiceType enum, deliberately narrow (SEARCH/DESCRIPTION/ROUTING only -- tunneling service types are M5). knx_sim/knxip/hpai.py: HPAI (8 bytes: ip/port/protocol) with route_back property (ip=0.0.0.0 -> NAT "reply to wherever this came from"). knx_sim/knxip/dib.py: DeviceInformationDIB (54 fixed bytes) + SupportedServiceFamiliesDIB -- diverges from xknx's polymorphic DIB-list design on purpose, since we only ever emit these exact two DIBs together (we're the server producing responses, not a client consuming arbitrary external ones). knx_sim/knxip/frame.py: SearchRequest/Response, DescriptionRequest/Response, RoutingIndication (body = raw cEMI bytes, no extra wrapping) + parse_frame() dispatcher. All 5 frame types verified byte-exact against xknx (scripts/compare_knxip_with_xknx.py). Key correctness point locked in for round B: SupportedServiceFamiliesDIB must advertise CORE version=1 (not 2, which xknx's GatewayScanner treats as "expects SEARCH_RESPONSE_EXTENDED instead") and ROUTING only (not TUNNELING, that's M5); loop prevention (F-IP-2) will use bus.has_device(telegram.source) to only re-multicast locally-originated telegrams, never ones that arrived via ROUTING_INDICATION -- this is what prevents a multi-router echo storm, distinct from the simpler IP_MULTICAST_LOOP=0 self-echo case. 270 tests passing, ruff+mypy strict clean. Next action: M4 round B -- knx_sim/knxip/server.py (asyncio UDP socket, multicast join/dispatch) plus the real xknx GatewayScanner + Routing integration test on localhost, which is M4's literal "done when" criterion.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
