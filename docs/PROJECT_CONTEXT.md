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

**Current status: M5 done.** Update the line below as work progresses.

> STATUS: M5 done (F-IP-3, F-IP-4). Round A (wire format): knx_sim/knxip/tunneling.py -- 8 frame types + Basic CRI/CRD (Extended/Tunnelling-v2 out of scope), verified byte-exact against xknx. Round B (state machine): knx_sim/knxip/tunnel_channel.py -- TunnelChannel (pure state, no asyncio) with CONNECTING->CONNECTED->DISCONNECTING FSM, independent inbound/outbound sequence counters (inbound ACCEPT/REPEAT/INVALID mirrors xknx's own client-side logic exactly, strict-disconnect-on-INVALID only -- lenient mode deferred per developer's choice), is_stale(now, timeout) with externally-injected clock for pure testability; TunnelRegistry allocates channel ids (1..255, reused) and individual addresses (15.15.<channel_id>), caps concurrency (default 4). Round C (this round): wired into knx_sim/knxip/server.py -- real 120s heartbeat loop, 1s ACK-wait-with-one-retry-then-disconnect for our outbound TunnellingRequests, per-channel relay of every bus telegram except back to its own originating channel (a materially different rule from routing's global has_device()-only relay -- a tunnel client is a full bus participant, not a peer router). Two real bugs found only by testing against a genuine xknx client (not caught by unit tests): (1) a second Windows unicast-reachability quirk, distinct from M4's multicast one -- a client connecting via 127.0.0.1 binds its own socket to loopback too, and Windows won't let a loopback-bound socket send to a different real interface address, so the server must advertise an address matching whatever scope the peer is already using (KnxIpServer._advertised_ip()); (2) a race condition where two bus telegrams relayed to the same channel in quick succession (e.g. a control write immediately followed by its own status echo) could race on that channel's outbound_sequence counter -- fixed with a per-channel asyncio.Lock serializing sends within one channel while different channels still relay concurrently. tests/test_knxip_tunnel_integration.py is the real F-IP-4 acceptance test: single client connects/controls/receives status, two concurrent clients both observe the same bus activity, and a client that goes silent (no heartbeat, simulating a killed process) gets cleaned up past the timeout -- verified stable across repeated runs. 343 tests passing, ruff+mypy strict clean. Next action: M6 -- device library (F-DEV-2..5, F-DEV-8..9: dimmer/blind/thermostat/presence-sensor/wall-switch-variants, time-based behavior via asyncio tasks owned by each device) + YAML config (F-CFG-1..3); no guide steps beyond this point, design together as needed.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
