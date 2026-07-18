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

**Current status: M6 in progress (round B of 4 done).** Update the line below as work progresses.

> STATUS: M6 round B done (BlindActuator + Thermostat). Design decisions locked in for the whole milestone: pydantic + PyYAML approved as new runtime dependencies (not yet installed -- that's round D); DPT 3.007 relative dimming modeled as a constant-rate continuous ramp rather than the real per-step-code timing table, deliberate simplification; staging is 4 rounds -- A) lifecycle+DPTs+Dimmer (done), B) BlindActuator+Thermostat (done, this entry), C) PresenceSensor+pydantic config models+device registry, D) YAML loading/validation+example configs+e2e test. Round A recap: Device.start()/stop() hooks, Bus.register()/stop() wiring, DPT 1.010 (Start/Stop)/1.018 (Occupancy), DimmerActuator. This round: knx_sim/devices/blind.py -- BlindActuator generalizes the dimmer's ramp into _run_travel(direction, target): a move command travels to a bound (0/100), an absolute position command travels to that specific target, same loop either way; position convention 0=open/up, 100=closed/down. knx_sim/devices/thermostat.py -- Thermostat needs no handle_group_write override at all (setpoint is a combined read/write object; the bus already applies incoming writes to the GroupObject's value before calling any handler, so the periodic physics tick just reads the current value on its next iteration -- worth remembering as the pattern for any future device whose only reaction to a write is "use the new value next tick"). Physics is deliberately simple per-tick deltas (drift_fraction of the ambient gap, plus heating_rate_per_tick when heating demanded), asymmetric hysteresis around setpoint to avoid chatter, temperature transmits on cyclic backstop or significant change whichever comes first. 424 tests passing (all real-timing ramp/physics tests verified stable across repeated runs), ruff+mypy strict clean. Next action: M6 round C -- PresenceSensor (F-DEV-5: DPT 1.018 occupancy, both a trigger() method for scenarios/tests and an optional built-in random-activity background task) + pydantic config models (SimulatorConfig/DeviceConfig/InstallationConfig) + a device-type registry mapping config "type" strings to Device subclasses, each via its own from_config() classmethod so device-specific config parsing stays local to that device rather than centralized in a loader.

## Working conventions
- Fully type-annotated, mypy --strict clean, ruff formatted, coverage target ≥85% on dpt/cemi/bus.
- Commit after every working step with a short imperative message.
- Keep protocol explanations the developer requests in `docs/notes/` (e.g. `docs/notes/cemi.md` holds the annotated example telegram) — they double as project documentation.
- When a fixture and our code disagree, print both byte sequences side by side with field annotations and locate the first differing bit before changing anything.
