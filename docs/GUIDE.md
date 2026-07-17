# KNX Simulator — Beginner's Build Guide (with Claude Code)

This guide takes you from zero to a working DPT codec and cEMI parser (milestones M0–M2 of the spec), assuming no prior experience with KNX internals, Wireshark, or protocol programming. Follow it top to bottom. Every step tells you what to do, why, and — where useful — an exact prompt to give Claude Code.

**How to use Claude Code as a beginner (read this first):**
- Work in small steps. Don't ask it to "build the simulator" — ask for one module, one function, one test at a time. You'll learn more and get better code.
- After every generated file, ask: *"Walk me through this file line by line and explain any concept I might not know."* Do this until it becomes unnecessary.
- Ask for tests **before or together with** implementation, and run them yourself. Green tests are your safety net when you don't yet trust your own protocol knowledge.
- When something confuses you, ask Claude Code to explain it with a concrete byte-level example. Protocol code only clicks with real bytes in front of you.
- Commit to git after every working step. Small commits let you experiment fearlessly.

---

## Part 1 — Concepts you'll meet (plain-language glossary)

Read this now; return to it whenever a term appears.

**Telegram** — a single small message on the KNX bus, e.g. "set group address 1/2/10 to ON". Everything in KNX is telegrams.

**Group address (GA)** — a logical "channel name" like `1/2/10`. Devices subscribe to GAs. Written as three numbers (main/middle/sub).

**Individual address** — a device's "serial number on the bus", like `1.1.23`. Used as the *source* of telegrams. In your simulator, each virtual device gets one.

**DPT (Datapoint Type)** — the rulebook for converting a value (like 21.5 °C or "ON") into bytes and back. DPT 1.001 = 1 bit on/off. DPT 5.001 = one byte meaning 0–100%. DPT 9.001 = two bytes encoding a temperature in a special float format. Your first module is a small library of these converters.

**APCI (service)** — what kind of telegram it is. You only care about three: **GroupValueWrite** ("set this value"), **GroupValueRead** ("what's the value?"), **GroupValueResponse** ("here's the value").

**cEMI frame** — nothing mystical: it's simply *the agreed byte layout of a telegram* when it travels over IP. Think of it like this: a telegram is a struct, and cEMI is the serialization format. A cEMI frame for "switch 1/2/10 ON" is just 11 bytes, something like `29 00 BC E0 11 17 0A 0A 01 00 81`. A "cEMI parser/builder" is a pair of functions: `bytes -> Telegram` and `Telegram -> bytes`. You'll write them in M2, field by field, and it's very learnable.

**KNXnet/IP** — the protocol that wraps cEMI frames in UDP packets so KNX can run over your network. It has three parts you'll implement much later: discovery ("any KNX servers out there?"), routing (broadcast style), tunneling (a 1-to-1 connection with handshake — this is what real tools use).

**xknx** — an open-source Python KNX library. You'll use it two ways: as *reference source code* to learn from, and as an independent *test client* to verify your server (never test your server only with your own code).

**Wireshark** — a free program that records network traffic and shows you every packet, decoded field by field. It has a built-in KNXnet/IP decoder, which means it can show you a real KNX telegram's bytes *with labels*. You don't need it until M2, and even then there's an alternative (below). Treat it as a learning microscope, not a prerequisite.

**pytest / property-based testing** — pytest runs your tests. Property-based testing (the `hypothesis` library) generates hundreds of random inputs to check rules like "decode(encode(x)) == x". Perfect for codec code.

---

## Part 2 — Environment setup (Day 1, ~1 hour)

### Step 2.1 — Install the toolchain
1. **Python 3.11 or newer**: check with `python3 --version`. If missing, install from python.org or your package manager.
2. **git**: `git --version` to check.
3. **Claude Code**: follow the current install instructions at https://docs.claude.com/en/docs/claude-code (ask Claude in this chat if you hit trouble — installation details change).
4. Optional but recommended: **VS Code** as your editor (Claude Code integrates with it).

### Step 2.2 — Create the project
```bash
mkdir knx-sim && cd knx-sim
git init
claude
```
Then give Claude Code this prompt:

> Create a Python project skeleton for a KNX bus simulator. Use pyproject.toml with setuptools, package name `knx_sim`, Python >=3.11. Create empty packages: knx_sim/dpt, knx_sim/cemi, knx_sim/bus, knx_sim/knxip, knx_sim/devices, knx_sim/config, plus a tests/ directory mirroring that layout. Add dev dependencies: pytest, pytest-asyncio, hypothesis, ruff, mypy. Add a ruff and mypy (strict) config, a .gitignore for Python, and a README stub. Also create a virtual environment setup note in the README. Don't implement any logic yet.

Then:
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest      # should report "no tests ran" — that's success for now
git add -A && git commit -m "Project skeleton"
```

### Step 2.3 — Set up CLAUDE.md (important!)
Claude Code reads a `CLAUDE.md` file in the repo root as standing instructions. Ask Claude Code:

> Create a CLAUDE.md for this project. It should state: this is a KNX bus simulator built for learning; I am new to protocol programming, so always explain non-obvious code; prefer small, fully type-annotated functions; every new function needs pytest tests; run ruff and mypy before declaring work done; never add dependencies without asking; follow the module layout dpt/cemi/bus/knxip/devices/config.

Also copy the project specification (knx-simulator-spec.md from our earlier conversation) into the repo as `docs/SPEC.md` — Claude Code will then always have the full requirements available. Commit.

---

## Part 3 — Milestone M1: the DPT codec (your first real code)

Goal: functions that convert Python values to KNX bytes and back. Pure logic, no networking — the perfect first module.

### Step 3.1 — Start with the easiest DPT (1.001, on/off)
Prompt for Claude Code:

> In knx_sim/dpt, implement DPT 1.001 (boolean switch). Design a small base class DPTBase with encode(value) -> bytes and decode(data: bytes) -> value, plus a registry mapping DPT ids like "1.001" to codec classes. Important KNX detail: DPT values of 6 bits or fewer are transmitted inside the APCI byte, not as separate payload bytes — so the codec should expose a `payload_length` (0 for small DPTs) and encode 1.001 as a single value 0 or 1 that the cEMI layer will later merge into the APCI byte. Write pytest tests including edge cases and a hypothesis round-trip test. Explain the design to me when done.

Run `pytest`, read the explanation, ask follow-up questions until the "6-bit values live inside the APCI byte" idea makes sense — it's the one genuinely weird thing here, and it matters in M2.

### Step 3.2 — DPT 5.001 (percentage) and 5.004
Prompt:

> Add DPT 5.001: one byte 0–255 linearly mapped to 0–100%. encode(50.0) -> bytes([128]) (rounding to nearest). decode must round-trip within the resolution (100/255 ≈ 0.4%). Also DPT 5.004 (raw 0–255). Hypothesis tests: for all v in [0,100], abs(decode(encode(v)) - v) <= 0.2.

### Step 3.3 — DPT 3.007 (relative dimming)
Prompt:

> Add DPT 3.007: 4-bit control value — 1 direction bit (increase/decrease) plus a 3-bit step code where 0 means "stop" and 1..7 mean a step of 1/(2^(code-1)) of full range. Model it as a small dataclass (direction: bool, step_code: int). It's a sub-6-bit DPT, so payload_length is 0. Tests for all 16 possible values.

### Step 3.4 — DPT 9.001 (temperature) — the boss fight
This 2-byte float format is the trickiest: 1 sign bit, 4 exponent bits, 11 mantissa bits (two's complement), value = 0.01 × mantissa × 2^exponent. Prompt:

> Implement DPT 9.001 (KNX 16-bit float, format S EEEE MMMMMMMMMMM, value = 0.01 * M * 2^E with M in two's complement over the combined sign+mantissa). Range approx -671088.64..670760.96, resolution varies with exponent. Choose the smallest exponent that fits the value. Then walk me through encoding 21.5 °C by hand, bit by bit, so I understand the format. Tests: known pairs (0 -> 0x0000, 21.5, -10, 100.0), plus hypothesis round-trip within the format's resolution at that magnitude.

Don't skip the "walk me through by hand" part — after this DPT, no binary format in this project will scare you.

### Step 3.5 — Verify against xknx (independent check)
```bash
pip install xknx
```
Prompt:

> Write a throwaway script scripts/compare_with_xknx.py that, for DPTs 1.001, 5.001, 9.001, encodes a table of sample values with both our codec and xknx's DPT classes and prints any byte-level differences. Fix our codec where we disagree with xknx.

When the script prints zero differences: `git commit -m "M1: DPT codec"`. **Milestone 1 done.** You now own a real, verified piece of the KNX protocol.

---

## Part 4 — Milestone M2: cEMI frames (telegrams as bytes)

### Step 4.1 — Learn the layout with one concrete telegram
Before writing code, ask Claude Code (or Claude in chat):

> Show me the exact byte layout of a cEMI L_Data.ind frame for "GroupValueWrite ON from individual address 1.1.23 to group address 1/2/10", annotating every byte: message code, additional info length, control field 1 bits, control field 2 bits, source address encoding (4+4+8 bits), group address encoding (5+3+8 bits), NPDU length, TPCI/APCI bits, and where the 1-bit payload sits inside the APCI byte. 

Keep that annotated example in `docs/notes/cemi.md`. It's your Rosetta Stone.

### Step 4.2 — Address types
Prompt:

> Implement IndividualAddress and GroupAddress classes in knx_sim/cemi/address.py: parse from strings ("1.1.23", "1/2/10"), format back, convert to/from their 16-bit wire encoding, validate ranges, support equality and hashing (they'll be dict keys). Full tests.

### Step 4.3 — The frame parser/builder
Prompt:

> Implement knx_sim/cemi/frame.py: a Telegram dataclass (source, destination, service: GroupValueRead/Write/Response, priority, hop_count, payload as decoded-DPT-agnostic raw bits/bytes) and functions parse_cemi(data: bytes) -> Telegram and build_cemi(t: Telegram, msg_code) -> bytes for L_Data.req/ind/con. Handle the small-payload case (<=6 bits merged into the APCI byte) and the separate-bytes case. Raise a typed ParseError with a helpful message on malformed input. Round-trip tests plus tests against these known-good frames: [paste 2–3 annotated frames from step 4.1].

### Step 4.4 — Get real captured telegrams (two options)

**Option A — no Wireshark needed:** xknx's GitHub repository contains extensive test fixtures with real frame bytes (look in its tests for KNX/IP frames), and its documentation includes example frames. Prompt:

> Find frame test vectors in the installed xknx package's source (site-packages/xknx) or write a script that uses xknx itself to build KNXnet/IP tunneling frames for a few telegrams, extract the raw cEMI bytes from them, and save them as fixtures in tests/fixtures/cemi/. Then make our parser tests consume those fixtures.

**Option B — learn Wireshark (recommended eventually, ~1 evening):**
1. Install Wireshark from wireshark.org.
2. You need real KNX/IP traffic on your machine. Easiest source: run two small xknx scripts against each other, or install `knxd` (a software KNX daemon) via Docker and point xknx at it.
3. In Wireshark, capture on the loopback interface, filter with `udp.port == 3671` (display filter: `knxnetip`).
4. Click any packet: Wireshark shows every field of the KNXnet/IP header and the cEMI frame inside, decoded and labeled. Compare with your `docs/notes/cemi.md` — this is where the protocol becomes tangible.
5. Right-click a packet → export bytes → save as a test fixture.

When your parser round-trips all fixtures byte-for-byte: `git commit -m "M2: cEMI"`. **Milestone 2 done** — and the two hardest *conceptual* modules are behind you. Everything after this is ordinary async Python.

---

## Part 5 — What comes next (pointers, not full steps)

- **M3 (virtual bus + first devices):** pure Python, no networking. Prompt Claude Code module by module: GroupObject, Device base, the bus router, then a switch + lamp with an integration test "press switch → lamp status telegram appears". This milestone is where the project starts feeling alive.
- **M4/M5 (KNXnet/IP):** before implementing, ask Claude Code to *explain the tunneling handshake as a sequence diagram* and to *design the connection state machine in a markdown doc* — implement only after you understand the diagram. Test against `pip install xknx` from day one of M5.
- Keep the rhythm: one prompt = one small deliverable + tests + explanation + commit.

## Part 6 — When you get stuck

- Parser disagrees with a fixture → ask Claude Code to print both byte sequences side by side with field annotations and find the first differing bit.
- Confusing spec detail → ask for the answer *with a worked byte example*, not prose.
- Tunneling bugs later → Wireshark on loopback with filter `knxnetip` shows you exactly what each side sent; this is where the Option B investment pays off.
- And bring design questions back to Claude in chat anytime — planning conversations are easier here; implementation belongs in Claude Code.
