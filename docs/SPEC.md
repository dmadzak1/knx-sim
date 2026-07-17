# KNX Virtual Bus Simulator — Project Specification

## 1. Project summary

A software simulator of a complete KNX installation: a virtual bus that routes KNX telegrams between simulated devices (switches, dimmers, blinds, thermostats, sensors), exposed to the outside world via KNXnet/IP so that real KNX tooling (ETS, xknx, Home Assistant, knxd-based tools) can connect to it as if it were physical hardware. A web dashboard provides live visualization and control.

**Working name:** `knx-sim` (pick your own)
**Primary language:** Python 3.11+ (asyncio)
**Target users:** KNX integrators testing configurations without hardware, developers testing KNX client software, and learners exploring the protocol.

## 2. Goals and non-goals

### Goals
- Faithful simulation of KNX group communication (GroupValueWrite / Read / Response) at the application layer.
- Standards-compliant KNXnet/IP server: discovery, routing (multicast), and tunneling, interoperable with real third-party clients (xknx as the reference client; ETS connectivity as a stretch validation).
- A library of realistic virtual device types with correct DPT usage, status feedback objects, and time-based behavior (dimming ramps, temperature drift, cyclic transmission).
- Declarative YAML configuration of an entire virtual installation.
- Live web dashboard: telegram monitor, device states, manual control.
- Clean, tested, documented codebase suitable as a portfolio piece.

### Non-goals (explicitly out of scope for v1)
- KNX TP1 physical/link-layer simulation (bit timing, collisions, ACK frames on the twisted pair). Only a simplified propagation-delay model.
- Device management/configuration services (ETS device programming via individual addressing: DeviceDescriptorRead, memory write, load procedures). ETS connecting for *group monitoring* is in scope; *programming* virtual devices from ETS is not.
- KNX Secure (Data Secure / IP Secure).
- KNX RF, PL110, or TP1 media specifics beyond the delay model.
- Persistence of historical telemetry (a time-series DB). Only an in-memory rolling telegram log.

## 3. System architecture

Five modules, each independently testable:

1. **`dpt/`** — Datapoint Type codec library (pure functions, no I/O).
2. **`cemi/`** — cEMI frame parser/builder (pure functions, no I/O).
3. **`bus/`** — virtual bus core: device registry, group-address routing, telegram log, simulated propagation delay.
4. **`knxip/`** — KNXnet/IP server: UDP endpoints, discovery, routing, tunneling connection management.
5. **`devices/`** — virtual device implementations built on a common GroupObject abstraction.

Supporting components: **`config/`** (YAML loader + validation), **`web/`** (FastAPI + WebSocket dashboard backend, static frontend), **`cli/`** (entry point, scenario runner).

Data flow: a client telegram arrives via `knxip`, is decoded by `cemi`, injected into `bus`, routed to subscribed `devices`, which may emit response telegrams that travel back out through `knxip` and simultaneously to the `web` telegram feed.

## 4. Functional requirements

### 4.1 DPT codec (`dpt/`)
- F-DPT-1: Encode and decode the following DPTs with exact KNX binary formats:
  - DPT 1.xxx (1-bit: switch, up/down, enable) — 1.001, 1.008, 1.009
  - DPT 3.007 (4-bit dimming control: direction + step code)
  - DPT 5.xxx (8-bit unsigned: 5.001 percentage 0–100%, 5.004 percent 0–255)
  - DPT 9.xxx (16-bit float: 9.001 temperature °C, 9.004 lux, 9.007 humidity)
  - DPT 7.xxx (16-bit unsigned counter)
  - DPT 14.xxx (32-bit IEEE 754 float)
  - DPT 232.600 (RGB color) — optional, needed only for RGB device
- F-DPT-2: Round-trip property: `decode(encode(x)) == x` within DPT resolution for all valid values; property-based tests (hypothesis) required.
- F-DPT-3: Reject out-of-range values with a typed exception; never emit malformed payloads.
- F-DPT-4: Correctly handle the "small payload" optimization: DPTs of ≤6 bits are packed into the APCI byte itself, not a separate octet.

### 4.2 cEMI frames (`cemi/`)
- F-CEMI-1: Parse and serialize cEMI L_Data.req / L_Data.ind / L_Data.con messages: message code, additional-info length, control field 1 (frame type, repeat, broadcast, priority, ack, confirm), control field 2 (address type, hop count, extended frame format), source individual address, destination address (individual or group), NPDU length, TPCI/APCI, payload.
- F-CEMI-2: Support APCI services: GroupValueRead (0x000), GroupValueResponse (0x040), GroupValueWrite (0x080).
- F-CEMI-3: Address types with parsing/formatting: individual `a.l.d` (4+4+8 bits) and group 3-level `m/i/s` (5+3+8 bits).
- F-CEMI-4: Test fixtures include at least 10 real telegrams captured from Wireshark (knxd or public captures), byte-for-byte.

### 4.3 Virtual bus core (`bus/`)
- F-BUS-1: Devices register with an individual address and a set of group objects (group address + DPT + flags: communication, read, write, transmit, update).
- F-BUS-2: Telegram routing: a GroupValueWrite to group address G is delivered to every group object subscribed to G except the sender's.
- F-BUS-3: GroupValueRead handling: delivered to devices whose group object on G has the Read flag set; that device responds with GroupValueResponse carrying its current value.
- F-BUS-4: Simulated propagation delay: configurable fixed delay per telegram (default ~20 ms, mimicking TP1 at 9600 bit/s); telegrams on the bus are serialized (one at a time), FIFO with priority ordering (system > urgent > normal > low).
- F-BUS-5: Rolling in-memory telegram log (default last 5,000 telegrams) with timestamp, source, destination, service, raw payload, decoded value, and resolved DPT.
- F-BUS-6: Bus is observable: components (web feed, KNXnet/IP layer, loggers) can subscribe to all telegrams (monitor mode).
- F-BUS-7: Injection API: any component can put a telegram on the bus programmatically (used by web UI manual control and the scenario runner).

### 4.4 KNXnet/IP server (`knxip/`)
- F-IP-1: **Discovery**: respond to SEARCH_REQUEST on multicast 224.0.23.12:3671 with SEARCH_RESPONSE (HPAI, device info DIB with friendly name and KNX medium, supported-services DIB). Support DESCRIPTION_REQUEST/RESPONSE.
- F-IP-2: **Routing**: join the multicast group; wrap/unwrap ROUTING_INDICATION frames; every bus telegram is multicast out and every received multicast telegram is injected into the bus. Loop prevention via source-address filtering.
- F-IP-3: **Tunneling** (the critical feature):
  - CONNECT_REQUEST → CONNECT_RESPONSE with assigned channel ID and tunnel individual address; support at least 4 concurrent tunnels.
  - TUNNELING_REQUEST/TUNNELING_ACK with per-channel sequence counters in both directions; out-of-sequence handling per spec (repeat of last-acked seq → re-ACK and discard; anything else → drop connection per spec, or log-and-tolerate in "lenient mode").
  - CONNECTIONSTATE_REQUEST heartbeat; drop channels not refreshed within 120 s.
  - DISCONNECT_REQUEST/RESPONSE from either side.
- F-IP-4: Interoperability acceptance: xknx (as an unmodified pip-installed client) can connect via tunneling, switch a virtual light, read a virtual temperature, and receive spontaneous status telegrams. This is the v1 acceptance test.
- F-IP-5: Configurable bind address/port so multiple simulator instances can coexist.

### 4.5 Virtual devices (`devices/`)
Common abstraction: F-DEV-0: a `Device` base class owning `GroupObject`s; group objects handle DPT encode/decode, transmit-on-change, and cyclic transmission timers.

Device library for v1:
- F-DEV-1: **Switch actuator** (relay): receives DPT 1.001 on control GA; sends status on separate status GA.
- F-DEV-2: **Dimmer actuator**: control objects for switch (1.001), relative dim (3.007, with ramp over time), absolute brightness (5.001); status objects for on/off and brightness; configurable ramp speed.
- F-DEV-3: **Blind/shutter actuator**: move up/down (1.008), stop/step (1.007 or 1.010), absolute position (5.001); simulated travel time with live position; position + moving status objects.
- F-DEV-4: **Thermostat/room controller**: sends measured temperature (9.001) cyclically and on significant change; receives setpoint (9.001); simple simulated room physics (drift toward ambient, heating raises temperature when demand active); heating-demand output object (1.001 or 5.001).
- F-DEV-5: **Presence/motion sensor**: sends 1.018 on simulated or scripted presence events; configurable random activity mode.
- F-DEV-6: **Wall switch (sensor)**: purely stimulus device; pressed via web UI or scenario script; emits write telegrams (toggle, dim, blinds).
- F-DEV-7: **Weather station** (stretch within v1 if time allows): temperature, brightness (9.004), wind, rain.
- F-DEV-8: All devices answer GroupValueRead on their status objects (Read flag).
- F-DEV-9: Device behavior parameters (ramp times, cycle periods, physics constants) settable per device in YAML.

### 4.6 Configuration (`config/`)
- F-CFG-1: One YAML file describes the installation: simulator settings (name, bind address, tunnels, delay model), then a list of devices with type, individual address, group-object → group-address mapping, and behavior parameters.
- F-CFG-2: Validation with helpful errors (pydantic): duplicate individual addresses, malformed GAs, unknown device types, DPT/GA conflicts (two objects on one GA with incompatible DPTs → warning).
- F-CFG-3: Ship at least two example installations: `minimal.yaml` (1 switch + 1 lamp) and `demo-house.yaml` (2 rooms, ~10 devices).

### 4.7 Web dashboard (`web/`)
- F-WEB-1: FastAPI backend; REST endpoints: list devices with live state, get telegram log (filterable by GA/service/time), inject telegram (GA + DPT + value).
- F-WEB-2: WebSocket stream of decoded telegrams and device-state changes.
- F-WEB-3: Frontend (single-page; plain JS or a light framework): live telegram monitor table (auto-scroll, pause, filter), device cards grouped by room showing state with controls (toggle, slider, setpoint), group-address activity view (per-GA last value + rate).
- F-WEB-4: Manual telegram injector form (choose GA, DPT, value) for testing.
- F-WEB-5: No authentication in v1 (localhost tool); bind to 127.0.0.1 by default.

### 4.8 CLI and scenario runner (`cli/`)
- F-CLI-1: `knx-sim run <config.yaml>` starts the simulator; flags for log level, web port, disabling web/routing/tunneling individually.
- F-CLI-2: `knx-sim monitor` — console telegram monitor (connects to a running instance via its own tunneling client or the WebSocket).
- F-CLI-3: Scenario scripts: a YAML/Python script of timed stimuli ("at t=2s press hallway switch; at t=10s presence in kitchen") for repeatable demos and integration tests.

## 5. Non-functional requirements
- NFR-1: Python 3.11+, fully type-annotated, mypy --strict clean; ruff for lint/format.
- NFR-2: Test coverage ≥85% on `dpt/`, `cemi/`, `bus/`; integration tests use a real xknx client against a spawned server (pytest-asyncio).
- NFR-3: Sustained throughput of ≥50 telegrams/s with 50 devices without falling behind (trivially achievable; guard with a benchmark test).
- NFR-4: Single-process, single event loop; no external services required to run.
- NFR-5: Documentation: README with quickstart GIF, architecture doc, protocol notes (your own explanation of cEMI/KNXnet/IP — great learning artifact), per-module docstrings.
- NFR-6: CI (GitHub Actions): lint, type-check, tests on push.
- NFR-7: License: MIT or Apache-2.0.

## 6. Project steps (milestones)

Each milestone ends with something demoable. Estimates assume part-time work (evenings/weekends).

### M0 — Bootstrap (1–2 days)
Repo, pyproject.toml, ruff/mypy/pytest config, CI pipeline, package skeleton with the five modules. Read xknx source for `dpt` and `knxip` as orientation. Capture reference telegrams with Wireshark against knxd or find public captures.
**Done when:** CI is green on an empty skeleton.

### M1 — DPT codec (3–5 days)
Implement F-DPT-1..4 with unit + property tests. The DPT 9 float format (sign, 4-bit exponent, 11-bit two's-complement mantissa, value = 0.01·m·2^e) is the trickiest — do it last.
**Done when:** all listed DPTs round-trip; encoders match xknx's output on a sample table.

### M2 — cEMI frames + addressing (3–5 days)
Implement F-CEMI-1..4. Address classes with parsing/formatting and hashing (they'll be dict keys everywhere). Validate against Wireshark fixtures byte-for-byte.
**Done when:** every captured fixture parses, re-serializes identically, and decoded fields match Wireshark's dissection.

### M3 — Virtual bus + first two devices (4–6 days)
Implement F-BUS-1..7, the `Device`/`GroupObject` base (F-DEV-0), switch actuator and wall switch (F-DEV-1, F-DEV-6). Everything in-process: a test presses the virtual switch, asserts the lamp turns on and a status telegram appears in the log.
**Done when:** the switch-controls-lamp integration test passes; console monitor prints decoded telegrams live.

### M4 — KNXnet/IP discovery + routing (4–6 days)
Implement F-IP-1, F-IP-2, F-IP-5 on asyncio UDP. Test with xknx in routing mode on localhost.
**Done when:** xknx discovers the simulator via SEARCH and switches the virtual lamp over multicast routing.

### M5 — Tunneling (7–10 days) — the core deliverable
Implement F-IP-3 as an explicit per-channel state machine (document it — states: CONNECTING, CONNECTED, DISCONNECTING; events; timers). Sequence counters, ACKs, heartbeats, multi-client. Then the F-IP-4 acceptance test.
**Done when:** unmodified xknx connects via tunneling, controls devices, receives spontaneous status telegrams; two clients can be connected at once; killing a client's process leads to heartbeat cleanup within 120 s.

### M6 — Device library + YAML config (5–8 days)
Implement F-DEV-2..5, F-DEV-8..9 and F-CFG-1..3. Time-based behavior (dimming ramps, blind travel, thermostat physics) via asyncio tasks owned by each device.
**Done when:** `knx-sim run demo-house.yaml` boots a 10-device house and an xknx script can operate every device type.

### M7 — Web dashboard (6–10 days)
Implement F-WEB-1..5. Keep the frontend simple first (telegram table + device cards), polish second.
**Done when:** you can watch telegrams stream live while operating devices from both the web UI and an external xknx client, and both views stay consistent.

### M8 — Scenarios, docs, polish (3–5 days)
F-CLI-1..3, README with demo recording, architecture doc, protocol notes, example configs, tag v1.0.
**Done when:** a stranger can clone, `pip install`, run the demo house, and connect xknx by following the README alone.

**Total: roughly 5–8 weeks part-time.**

## 7. Testing strategy
- Unit: pure-function tests for `dpt/` and `cemi/` (property-based where possible).
- Fixture: byte-exact Wireshark capture round-trips.
- Integration: pytest-asyncio spins up the full server; real xknx client drives it (routing and tunneling suites).
- Behavioral: scenario scripts as regression tests (e.g., "blind reaches 50% ±2% after position command").
- Interop (manual, documented): ETS group monitor via tunneling; Home Assistant KNX integration pointed at the simulator.

## 8. Risks and mitigations
- **Tunneling sequence/timeout edge cases** — highest-risk area. Mitigate: model as an explicit state machine, test against xknx early and often, add a "lenient mode" toggle, compare behavior with knxd using Wireshark.
- **ETS interop quirks** (ETS may probe unsupported services) — respond with proper error codes / E_CONNECTION_TYPE where applicable; treat ETS group-monitor support as stretch validation, not a v1 gate.
- **Multicast on the dev machine** (VPNs, Docker, and some OS setups break it) — make routing optional; tunneling is the primary path.
- **Scope creep into device management** — explicitly deferred (see non-goals); log-and-ignore unsupported APCI services.

## 9. Post-v1 roadmap (stretch)
- Floor-plan view with SVG rooms and clickable devices.
- ETS project file (.knxproj) import to auto-generate the YAML installation.
- KNX IP Secure.
- Fault injection: telegram loss, duplication, delay jitter — for testing client robustness.
- knx-sim as a pytest fixture package for other projects' CI.
- Emulated ESP32 firmware device (Wokwi/QEMU/Renode) joining the simulated bus as an external KNXnet/IP node.
