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

**Current status: M6 and M7 both complete. M8 (scenarios, docs, polish) in progress (round C of 5 done).** Update the line below as work progresses.

> STATUS: M6 (device library + YAML config) and M7 (web dashboard) are both fully complete -- see git log for the "M6 round A-D" and "M7 round A-E" commit messages for full round-by-round detail if ever needed. Short version: knx_sim/config/loader.py's load_installation_file()/build_simulator() turn a YAML file into a wired Bus+KnxIpServer+Device list; knx_sim/web/app.py's create_app(simulator) is the FastAPI backend (REST + /ws + static frontend serving) satisfying F-WEB-1..5; frontend/ is a Vite+React+Tailwind dashboard built around one shared WebSocket connection. InstallationConfig.group_addresses (ETS-style project-wide GA name registry, post-M7 user request) flows through the REST/WS API and the frontend. One fixed bug worth remembering if similar symptoms ever recur: Bus._deliver() used to only call handle_group_write on an actual value *change*, silently breaking any control meant to be re-triggerable with the same value -- fixed by always delivering a write that passes the flag gate, since devices already gate their own transmits via GroupObject.set()'s return value independently.
>
> **M8 design locked in** (see commit "M8 design: ..."): `knx-sim monitor` (F-CLI-2) is WebSocket-based, not xknx-as-runtime-dependency or our own tunneling client. Scenario scripts (F-CLI-3) are YAML-only for v1. License is MIT. 5 rounds: A) F-CLI-1 CLI restructuring (done); B) F-CLI-2 `knx-sim monitor` (done); C) F-CLI-3 scenario format + runner (done, this entry); D) README/docs/license; E) CI + polish + tag v1.0.
>
> **Round A recap**: `[project.scripts]` makes `knx-sim` a real installed command, with argparse subparsers and `run` flags (`--log-level`/`--web-port`/`--no-web`/`--no-routing`/`--no-tunneling`). Bigger finding: KnxIpServer had never actually supported disabling routing/tunneling independently -- added real `enable_routing`/`enable_tunneling` params affecting relay, inbound processing, *and* the discovery-advertised SupportedServiceFamiliesDIB.
>
> **Round B recap**: knx_sim/cli/monitor.py's `monitor(host, port)` connects to `ws://host:port/ws` (the same stream the web dashboard consumes) and prints each decoded telegram to the console, auto-reconnecting on drop. Real bug found via manual verification (not caught by any test): stdout is block-buffered whenever not a real interactive terminal, so a long-running live-print tool silently produced no output until buffer flush -- fixed with `flush=True` on every print(), the general fix for any long-running incrementally-printing CLI tool. `websockets` promoted to a direct runtime dependency.
>
> **Round C done**: F-CLI-3 YAML scenario scripts. knx_sim/scenario.py's `ScenarioStep` (at/device/action/group_object?/value?) + `load_scenario_file()`/`run_scenario()`/`run_scenario_file()` -- usable both from the CLI (`knx-sim run <config> --scenario <scenario.yaml>`, launched as a background task, failures logged not fatal so a scripted-demo bug can't take down the server) and directly from test code (a scenario doubling as a regression test, per the SPEC's own example: `tests/test_scenario.py::test_blind_reaches_50_percent_after_position_command_scenario` runs a real installation YAML + real scenario YAML end to end and asserts the blind settles at 50% +/-2%). Two kinds of steps: a named action already on the device (`press`, `trigger` -- looked up via `getattr(device, step.action)`, safe here because the scenario author names the exact method) and a generic `write` action that injects a GroupValueWrite to one of the device's own group objects by config name (e.g. a thermostat's `setpoint`) -- the escape hatch for actuator-type devices with no stimulus method of their own. Extracted knx_sim/telegram_inject.py's `encode_payload()` (DPT 3.007 DimmingControl dict-coercion + codec encode) as a shared helper so this logic doesn't drift between the web dashboard's manual injector (knx_sim/web/app.py) and the scenario runner -- refactored app.py to use it, re-verified its 20 existing tests unchanged.
>
> **Real bug found and fixed in the shipped scenario runner (not just a test bug)**: `run_scenario()` originally didn't wait for a step's telegram to actually be delivered before starting the next step's timer -- `bus.inject()` only enqueues, it doesn't wait for processing, so a `write` immediately followed by an assertion (or by the next step) could see a stale value. Fixed by adding `await simulator.bus.join()` after each step. Confirmed safe for devices with independent multi-second background tasks (e.g. a blind's `_run_travel`): `bus.join()` only waits for the initiating write's own delivery/cascade, not unrelated background tasks it kicks off.
>
> examples/demo-scenario.yaml is a 6-step tour of examples/demo-house.yaml (press a switch, dim, move a blind, set a thermostat setpoint, trigger presence, press another switch) runnable via `knx-sim run examples/demo-house.yaml --scenario examples/demo-scenario.yaml`; a dedicated test replays its exact steps with `at` collapsed to 0 so a typo'd device/group_object name in either YAML file is caught by the suite rather than only surfacing when someone runs the real 18-second demo.
>
> 552 tests passing, ruff+mypy strict clean. Manually verified live: ran `knx-sim run examples/demo-house.yaml --scenario examples/demo-scenario.yaml` as the real installed command and polled `/api/devices` over the full ~18s run, confirming all six scripted steps landed (switch presses, dimmer brightness ~75%, blind position ~50%, thermostat setpoint 22.0, presence, second switch) and the scenario logged "finished" cleanly.
>
> Next action: M8 round D -- README overhaul, architecture doc, protocol notes audit, LICENSE file (MIT), docstring audit.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
