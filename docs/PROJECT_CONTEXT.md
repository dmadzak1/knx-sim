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

**Current status: M6 complete. M7 (web dashboard) in progress (round D of 5 done).** Update the line below as work progresses.

> STATUS: M6 is fully complete (all of F-DEV-2..5/8..9 and F-CFG-1..3 -- see git log for M6 round A-D commit messages if ever needed; short version: knx_sim/config/loader.py's load_installation_file()/build_simulator() turn a YAML file into a wired-but-not-started Bus+KnxIpServer+Device list, examples/minimal.yaml and demo-house.yaml are the two F-CFG-3 example installs, tests/test_demo_house_e2e.py is M6's own real-xknx acceptance test).
>
> M7 design locked in (see commit "M7 design: ..."): CLI launcher built now (not deferred to M8), React+Tailwind+Vite frontend, DeviceConfig.room field, fastapi+uvicorn[standard] approved. 5 rounds: A) FastAPI REST skeleton + DeviceConfig.room (done); B) WebSocket live stream (done); C) minimal CLI launcher (done); D) frontend scaffold + telegram table (this entry); E) device cards + GA view + injector + polish (M7's actual done-when).
>
> Rounds A-C recap (see git log "M7 round A/B/C" commits for full detail): knx_sim/web/app.py's create_app(simulator) builds a FastAPI app around an already-built Simulator. GET /api/devices, GET /api/telegrams (filterable), POST /api/inject (F-WEB-1/F-WEB-4), /ws (F-WEB-2) streaming `{"type": "telegram", "data": {...}}` for every processed telegram. DeviceConfig.room added; Simulator gained device_configs pairing each Device back to its config. knx_sim/cli/ -- `python -m knx_sim.cli <config.yaml>` boots bus+KnxIpServer+web dashboard together; build()/shutdown() split from run() for testability; web dashboard always binds 127.0.0.1 (F-WEB-5) independent of the KNXnet/IP side's bind_address. Two reusable findings from this stretch: (1) a send-only WebSocket handler that never calls websocket.receive() never notices client disconnection, deadlocking graceful shutdown -- needs a concurrent receiver() task whose only job is detecting WebSocketDisconnect. (2) uvicorn.Server.serve() (even called directly, not via uvicorn.run()) already installs its own SIGINT/SIGTERM/SIGBREAK handlers and returns normally once one arrives -- no manual KeyboardInterrupt handling needed around serve() itself.
>
> M7 round D done: frontend/ (new, Node.js needed to be installed by the user mid-round -- wasn't present in the environment) -- Vite + React 19 + TypeScript + Tailwind CSS v4 (via @tailwindcss/vite; v4 needs no separate tailwind.config.js/PostCSS setup, just the Vite plugin + `@import "tailwindcss";` in index.css). vite.config.ts proxies /api and /ws to 127.0.0.1:8080 during `npm run dev`, so the dev server needs no CORS setup and can reload independently of the Python backend. src/hooks/useTelegramStream.ts: GET /api/telegrams for initial history, then live updates over /ws with auto-reconnect (2s fixed delay) on drop; caps the in-memory list at 500 entries (matches the backend's own bounded-queue philosophy, knx_sim/web/app.py's WS_QUEUE_MAXSIZE); `paused` stops appends without tearing down the socket, using a ref to avoid a stale closure over the paused boolean inside the long-lived message handler. src/components/TelegramMonitor.tsx: auto-scroll (scrolls to bottom on new rows, toggleable), pause/resume, client-side filtering by GA substring + service, live connected/disconnected indicator.
>
> Verification: TypeScript compiles clean (`tsc -b`), production build succeeds, oxlint passes. End-to-end proxy correctness confirmed by injecting a telegram through the proxied REST endpoint and observing it arrive over the proxied WebSocket in the exact shape the frontend expects (done via a throwaway `node -e` script, not a formal test -- no frontend test framework set up yet, deliberately deferred; manual + build/lint verification was judged sufficient for this round's scope). User visually confirmed in a real browser: table renders and updates live, pause/resume and filters work. One user observation resolved during review, not a bug: two near-simultaneous identical-looking telegram rows (living_room_thermostat and bedroom_thermostat, ~31ms apart, same value) -- both thermostats in demo-house.yaml use identical default physics parameters and started within milliseconds of each other, so they run in natural lockstep; different source/destination columns confirm these are two genuine independent telegrams, not a streaming dedup bug.
>
> Static-file serving of the production frontend build from FastAPI (so the CLI alone can serve everything without a separate `npm run dev`) is deliberately deferred to round E.
>
> 499 tests passing (Python side unchanged this round), ruff+mypy strict clean across knx_sim/ and tests/. Next action: M7 round E (final) -- device cards grouped by room with controls (toggle/slider/setpoint, calling POST /api/inject), GA activity view (per-GA last value + rate), manual telegram injector form, wiring FastAPI to serve frontend/dist/ in production, and general polish. This is M7's actual done-when: watch telegrams stream live while operating devices from both the web UI and an external xknx client, both views staying consistent.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
