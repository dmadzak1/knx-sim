# knx-sim

A software simulator of a complete KNX home-automation installation: a
virtual bus that routes KNX telegrams between simulated devices
(switches, dimmers, blinds, thermostats, sensors), exposed via a
standards-compliant KNXnet/IP server (discovery, multicast routing, and
tunneling) so that real, unmodified KNX tools — [xknx][xknx] above all —
can connect and operate the virtual house, no physical hardware
required. A web dashboard adds live telegram monitoring and manual
control on top.

[xknx]: https://github.com/XKNX/xknx

<!-- TODO: quickstart recording (NFR-5) -- record a short terminal + browser
     walkthrough (run demo-house.yaml, watch telegrams stream, control a
     device from the web UI while an xknx script also operates it) and
     drop the GIF/link here. -->

## Features

- **DPT codec library** — exact KNX binary formats (1.001 switch,
  3.007 dimming, 5.001/5.004 8-bit values, 9.001/9.004/9.007 16-bit
  float, 7.x counters, 14.x IEEE 754 floats), round-trip tested with
  hypothesis.
- **cEMI frame parsing** and 3-level group / individual addressing,
  verified byte-for-byte against real captures and xknx's own encoder.
- **A virtual bus** with realistic behavior: FIFO-with-priority
  delivery, a simulated ~20ms propagation delay, and a rolling
  in-memory telegram log.
- **A standards-compliant KNXnet/IP server**: SEARCH/DESCRIPTION
  discovery, multicast routing, and tunneling (≥4 concurrent clients,
  sequence-counter discipline, CONNECTIONSTATE heartbeat) — an
  unmodified xknx client can't tell it apart from real hardware.
- **A device library** with real time-based behavior: dimmer ramps,
  blind travel with live position, thermostat room physics, presence
  sensors, cyclically-transmitting sensors — all configured from one
  YAML file.
- **A web dashboard** (FastAPI + WebSocket + React): live telegram
  monitor, device cards grouped by room, a group-address activity view,
  and a manual telegram injector.
- **`knx-sim monitor`**, a console telegram viewer, and YAML **scenario
  scripts** for repeatable demos that double as regression tests.

See [`docs/SPEC.md`](docs/SPEC.md) for the full requirements this
implements, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how
the pieces above fit together.

## Quickstart

```bash
git clone https://github.com/dmadzak1/knx-sim.git
cd knx-sim
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the bundled demo house (two rooms, one of every device type — see
[`examples/demo-house.yaml`](examples/demo-house.yaml)):

```bash
knx-sim run examples/demo-house.yaml
```

This starts the KNXnet/IP server on UDP 3671 (routing + tunneling both
on) and the web dashboard at <http://127.0.0.1:8080>. Open the
dashboard to watch telegrams and control devices by hand, or connect a
real xknx client:

```python
import asyncio
from xknx import XKNX
from xknx.devices import Switch

async def main() -> None:
    async with XKNX() as xknx:
        switch = Switch(xknx, name="Living Room Light", group_address="1/1/1")
        await switch.set_on()
        await asyncio.sleep(1)

asyncio.run(main())
```

(`XKNX()` with no arguments auto-discovers the simulator over multicast
routing, the same way it would find a real KNX/IP router on your LAN.
You may see xknx log a `L_DATA_CON ... confirmation timed out` warning —
that's xknx waiting on a local data-link confirmation no KNXnet/IP
router actually sends over the network either; it's benign, and the
write still lands, as `knx-sim run`'s web dashboard or telegram log will
confirm.)

Other things worth trying:

```bash
# Console telegram viewer -- connects to an already-running instance
knx-sim monitor

# Play a scripted 6-step tour of the demo house (presses, dims, moves a
# blind, sets a thermostat, triggers presence -- see examples/demo-scenario.yaml)
knx-sim run examples/demo-house.yaml --scenario examples/demo-scenario.yaml

# All `run` flags
knx-sim run --help
```

## Writing your own installation

An installation is one YAML file: simulator-wide settings, then a list
of devices with their type, individual address, and group-address
wiring. See [`examples/minimal.yaml`](examples/minimal.yaml) (one
switch, one lamp) for the smallest possible file, and
[`examples/demo-house.yaml`](examples/demo-house.yaml) for every
supported device type wired up across two rooms.

## Protocol notes

Written while building this, as a from-scratch learning artifact rather
than a paraphrase of the KNX spec — each one derives a real, worked
byte sequence and cross-checks it against xknx's own implementation:

- [`docs/notes/cemi.md`](docs/notes/cemi.md) — cEMI frame layout
  (control fields, addressing, TPCI/APCI packing), one telegram
  decoded byte by byte.
- [`docs/notes/dpt9.md`](docs/notes/dpt9.md) — the KNX 16-bit float
  format (sign/exponent/mantissa), worked positive and negative
  examples.
- [`docs/notes/knxip.md`](docs/notes/knxip.md) — KNXnet/IP discovery,
  routing, and tunneling: worked frames for every service, the
  sequence-counter accept/repeat/reject rules, and the tunnel
  connection lifecycle.

## Development

```bash
ruff check .
mypy knx_sim/ tests/
pytest
```

The frontend (`frontend/`, Vite + React + Tailwind) has its own dev
loop:

```bash
cd frontend
npm install
npm run dev      # dev server with hot reload against a running knx-sim backend
npm run build    # production build -> frontend/dist, served by knx-sim itself
```

## Non-goals

TP1 physical-layer simulation (bit timing, collisions, ACK frames)
beyond the fixed-delay model; ETS device *programming* (memory writes,
load procedures — ETS group monitoring is fully supported); KNX
Secure; RF/PL110 media; historical telemetry persistence; web UI
authentication (a localhost tool, bound to 127.0.0.1 by default). See
`docs/SPEC.md` §2 for the complete list.

## License

MIT — see [`LICENSE`](LICENSE).
