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

**Current status: M6 and M7 both complete. M8 (scenarios, docs, polish) in progress (round B of 5 done).** Update the line below as work progresses.

> STATUS: M6 (device library + YAML config) and M7 (web dashboard) are both fully complete -- see git log for the "M6 round A-D" and "M7 round A-E" commit messages for full round-by-round detail if ever needed. Short version: knx_sim/config/loader.py's load_installation_file()/build_simulator() turn a YAML file into a wired Bus+KnxIpServer+Device list; knx_sim/web/app.py's create_app(simulator) is the FastAPI backend (REST + /ws + static frontend serving) satisfying F-WEB-1..5; frontend/ is a Vite+React+Tailwind dashboard built around one shared WebSocket connection. InstallationConfig.group_addresses (ETS-style project-wide GA name registry, post-M7 user request) flows through the REST/WS API and the frontend. One fixed bug worth remembering if similar symptoms ever recur: Bus._deliver() used to only call handle_group_write on an actual value *change*, silently breaking any control meant to be re-triggerable with the same value -- fixed by always delivering a write that passes the flag gate, since devices already gate their own transmits via GroupObject.set()'s return value independently.
>
> **M8 design locked in** (see commit "M8 design: ..."): `knx-sim monitor` (F-CLI-2) is WebSocket-based, not xknx-as-runtime-dependency or our own tunneling client. Scenario scripts (F-CLI-3) are YAML-only for v1. License is MIT. 5 rounds: A) F-CLI-1 CLI restructuring (done); B) F-CLI-2 `knx-sim monitor` (done, this entry); C) F-CLI-3 scenario format + runner; D) README/docs/license; E) CI + polish + tag v1.0.
>
> **Round A recap**: `[project.scripts]` makes `knx-sim` a real installed command. knx_sim/cli/main.py has argparse subparsers; `run <config.yaml>` gained `--log-level`/`--web-port`/`--no-web`/`--no-routing`/`--no-tunneling` (all CLI-only, threaded as kwargs through build()/build_simulator(), not YAML fields). RunningApp.web_server is now `uvicorn.Server | None`. Bigger finding: KnxIpServer had never actually supported disabling routing/tunneling independently -- added real `enable_routing`/`enable_tunneling` params affecting relay, inbound processing, *and* the discovery-advertised SupportedServiceFamiliesDIB; tested end-to-end with real xknx clients (no tests/knxip/test_server.py -- intentional, matches this project's established KnxIpServer-via-real-network-tests convention).
>
> **Round B done**: knx_sim/cli/monitor.py's `monitor(host, port)` connects to `ws://host:port/ws` (the exact same stream the web dashboard's telegram monitor consumes) and prints each decoded telegram to the console, auto-reconnecting on drop with a fixed 2s delay (a real use case: starting `knx-sim monitor` before `knx-sim run`, or the server briefly restarting). `format_telegram()` is a pure function producing e.g. `20:14:03.221  1.1.2 -> 1/1/1   write    1.001  True   (Living Room Light A1)` -- pulled out separately from monitor() so it's unit-testable without a live connection. Wired into main.py as the `monitor` subcommand (`--host`/`--port`, defaulting to 127.0.0.1/8080). `websockets` promoted from a dev-only to a direct runtime dependency in pyproject.toml -- doesn't change what actually gets installed (already transitively pulled in via uvicorn[standard]), just makes explicit what monitor.py now directly relies on.
>
> **Real bug found via manual verification, not caught by any test**: every `print()` in monitor.py appeared to produce *no output at all* when run as the real installed `knx-sim monitor` command (as opposed to `python -u -m knx_sim.cli monitor`), confirmed empirically by comparing the two invocations side by side. Root cause: Python stdout is block-buffered (not line-buffered) whenever it isn't a real interactive terminal -- true for piped/redirected output, and apparently also for how this sandboxed shell captured the console script's output -- so a long-running live-print tool can sit for a long time with the buffer never flushing. Fixed with `flush=True` on every print() call in the monitor -- the correct fix is in the tool itself (works regardless of invocation method or where stdout is redirected), not something to push onto the user via `-u`/`PYTHONUNBUFFERED`. Worth remembering for any *other* long-running CLI tool that prints incrementally rather than returning a batch result.
>
> 532 tests passing, ruff+mypy strict clean. Manually verified against two real separate `knx-sim` processes (`run` + `monitor`): connect, live telegram printing (including GA names), and the reconnect-before-server-exists path all confirmed working via direct testing, not just the automated suite.
>
> Flagged to the user as something I can't do myself: NFR-5's "quickstart GIF" needs an actual screen recording, which has to be a manual follow-up on their end.
>
> Next action: M8 round C -- F-CLI-3 YAML scenario format + a runner usable both from the CLI and programmatically (so scenarios double as regression tests, e.g. "blind reaches 50% ±2% after position command") + example scenario file(s).

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
