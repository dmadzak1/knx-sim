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

**Current status: M6 and M7 both complete. M8 (scenarios, docs, polish) in progress (round A of 5 done).** Update the line below as work progresses.

> STATUS: M6 (device library + YAML config) and M7 (web dashboard) are both fully complete -- see git log for the "M6 round A-D" and "M7 round A-E" commit messages for full round-by-round detail if ever needed. Short version: knx_sim/config/loader.py's load_installation_file()/build_simulator() turn a YAML file into a wired Bus+KnxIpServer+Device list; knx_sim/web/app.py's create_app(simulator) is the FastAPI backend (REST + /ws + static frontend serving) satisfying F-WEB-1..5; frontend/ is a Vite+React+Tailwind dashboard (device cards, GA activity, injector, telegram monitor) built around one shared WebSocket connection. Also: InstallationConfig.group_addresses (ETS-style project-wide GA name registry, post-M7 user request) flows through the REST/WS API and the frontend. One notable fixed bug worth remembering if similar symptoms ever recur: Bus._deliver() (knx_sim/bus/router.py) used to only call handle_group_write on an actual value *change*, which silently broke any control meant to be re-triggerable with the same value (blind stop/move, dimmer switch after a brightness-only change) -- fixed by always delivering a write that passes the flag gate, since devices already gate their own transmits via GroupObject.set()'s return value independently.
>
> **M8 design locked in** (see commit "M8 design: ..."): `knx-sim monitor` (F-CLI-2) will be WebSocket-based, not xknx-as-runtime-dependency or our own tunneling client. Scenario scripts (F-CLI-3) are YAML-only for v1. License is MIT. 5 rounds: A) F-CLI-1 CLI restructuring (done, this entry); B) F-CLI-2 `knx-sim monitor`; C) F-CLI-3 scenario format + runner; D) README/docs/license; E) CI + polish + tag v1.0.
>
> **M8 round A done**: `[project.scripts]` entry point (pyproject.toml) makes `knx-sim` a real installed command (`python -m knx_sim.cli` still works too). knx_sim/cli/main.py restructured with argparse subparsers -- only `run` exists so far (`monitor` is round B's job to add from scratch, not stubbed here). `run <config.yaml>` flags: `--log-level` (DEBUG/INFO/WARNING/ERROR/CRITICAL), `--web-port` (overrides the YAML's simulator.web_port), `--no-web`/`--no-routing`/`--no-tunneling`. None of these are InstallationConfig/YAML fields -- they're CLI-only, threaded as keyword args through build()/build_simulator() (both gained `enable_routing`/`enable_tunneling` params; build() also gained `web_port_override`/`enable_web`). RunningApp.web_server is now `uvicorn.Server | None`; when None (--no-web), run() blocks on a bare `asyncio.Event().wait()` instead of `web_server.serve()` -- Ctrl+C still works the same way (raises KeyboardInterrupt into whichever of the two is awaited, caught in main()).
>
> Bigger finding: KnxIpServer (knx_sim/knxip/server.py) had never supported disabling routing or tunneling independently -- both were bundled unconditionally into one socket. Added `enable_routing`/`enable_tunneling` constructor params: disabling routing skips both outbound multicast relay and inbound ROUTING_INDICATION processing; disabling tunneling rejects every CONNECT_REQUEST with `E_CONNECTION_TYPE` instead of ever creating a channel; both are reflected in the advertised SupportedServiceFamiliesDIB (so a real client's discovery scan sees the actual capability, not just a silent server-side restriction). Discovery itself (F-IP-1) is never gated by either flag -- a client should always be able to find and query the server, and discovery's own multicast socket membership is what routing needs anyway. Tested end-to-end with real xknx clients in tests/test_knxip_integration.py (routing) and tests/test_knxip_tunnel_integration.py (tunneling), matching this project's established convention of testing KnxIpServer via real-network integration tests rather than isolated unit tests -- there's still no tests/knxip/test_server.py, and that's intentional, not an oversight.
>
> 527 tests passing, ruff+mypy strict clean. Verified manually against a real running `knx-sim` command (not just tests): `--web-port` override, `--no-routing` banner reflection, all confirmed working.
>
> Flagged to the user as something I can't do myself: NFR-5's "quickstart GIF" needs an actual screen recording, which has to be a manual follow-up on their end.
>
> Next action: M8 round B -- `knx-sim monitor` (F-CLI-2), WebSocket-based per the design decision above.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
