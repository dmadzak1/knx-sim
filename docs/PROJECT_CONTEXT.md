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

**Current status: M6 complete. M7 (web dashboard) in progress (round A of 5 done).** Update the line below as work progresses.

> STATUS: M6 is fully complete (all of F-DEV-2..5/8..9 and F-CFG-1..3 -- see git log for M6 round A-D commit messages if the detail is ever needed; the short version: knx_sim/config/loader.py's load_installation_file()/build_simulator() turn a YAML file into a wired-but-not-started Bus+KnxIpServer+Device list, examples/minimal.yaml and demo-house.yaml are the two F-CFG-3 example installs, tests/test_demo_house_e2e.py is M6's own real-xknx acceptance test).
>
> M7 design locked in (see commit "M7 design: ..."): CLI launcher built now (not deferred to M8), React+Tailwind+Vite frontend, DeviceConfig.room field, fastapi+uvicorn[standard] approved. 5 rounds: A) FastAPI REST skeleton + DeviceConfig.room (this entry); B) WebSocket live stream; C) minimal CLI launcher; D) frontend scaffold + telegram table; E) device cards + GA view + injector + polish (M7's actual done-when).
>
> M7 round A done: knx_sim/config/models.py -- DeviceConfig gets a new declared `room: str | None = None` field (display metadata, not a device behavior param, so it's alongside name/type rather than one of the extra="allow" fields). examples/demo-house.yaml's 10 devices tagged Living Room/Bedroom; examples/minimal.yaml deliberately left without room, to exercise the None/"Ungrouped" path. knx_sim/config/loader.py -- Simulator gained `device_configs: dict[IndividualAddress, DeviceConfig]` (built via `zip(devices, config.devices, strict=True)`, safe because build_device() preserves list order) since Device itself only knows its group objects, not name/room/type -- the web layer needs both, and Device deliberately doesn't learn about config-layer concerns to get it. knx_sim/web/ (new package) -- app.py's create_app(simulator) builds a FastAPI app around an already-built Simulator (web is just another Bus consumer, not the thing that owns simulator lifecycle -- that's round C's CLI). Three endpoints: GET /api/devices (per-device state incl. room/type from device_configs), GET /api/telegrams (filterable by group_address/service/since, capped by `limit`, default 200), POST /api/inject (F-WEB-4's backend half -- encodes via the real DPT codec registry, defaults source to a dedicated WEB_UI_INDIVIDUAL_ADDRESS constant (15.15.200) distinct from the server's own address and typical xknx test-client addresses so injected telegrams are identifiable in the log). schemas.py's value fields are typed Any -- every DPT decodes to bool/float/int already except 3.007's DimmingControl dataclass, hand-converted to/from a {"direction", "step_code"} dict at the API boundary (_serialize_value/_coerce_value_for_encode) since pydantic won't auto-serialize an arbitrary stdlib dataclass nested in an Any field.
>
> Testing approach worth remembering for round B: build_simulator() needs a running event loop (Bus.register() schedules device.start() via asyncio.create_task), so these tests use httpx.AsyncClient over httpx.ASGITransport(app=app) inside async test functions rather than FastAPI's synchronous TestClient -- keeps simulator construction and every request on the same event loop, avoiding cross-loop asyncio object errors a separate sync client would hit. Endpoint tests that need a telegram to actually finish processing call `await simulator.bus.start()` in setup and `await simulator.bus.join()` after posting to /api/inject, rather than sleeping -- join() waits on the bus's own queue, not wall-clock time.
>
> Installed this round: fastapi, uvicorn[standard] (runtime deps), httpx (dev dep, for the async test client). 486 tests passing, ruff+mypy strict clean across knx_sim/ and tests/. Next action: M7 round B -- WebSocket endpoint (F-WEB-2) streaming decoded telegrams + device-state changes live, tested via Starlette's WebSocket test client.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
