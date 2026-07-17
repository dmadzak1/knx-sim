# CLAUDE.md

This is a KNX bus simulator (`knx-sim`) built for learning embedded/home-automation
protocol programming. Read `docs/PROJECT_CONTEXT.md` first in every session; full
requirements are in `docs/SPEC.md`.

## How to work with the developer
- New to protocol programming, binary formats, and asyncio networking — always
  explain non-obvious code and protocol concepts, ideally with concrete byte-level
  examples.
- Work in small steps: one prompt = one small deliverable + tests + explanation.
  Never generate large multi-module chunks in one pass.
- Prefer small, fully type-annotated functions.
- Every new function needs pytest tests.
- Run ruff and mypy (strict) before declaring work done.
- Never add a dependency without asking first.

## Module layout
`knx_sim/dpt` (datapoint codecs) · `knx_sim/cemi` (frame parser/builder + addresses)
· `knx_sim/bus` (device registry, routing, telegram log) · `knx_sim/knxip`
(discovery, routing, tunneling) · `knx_sim/devices` (Device/GroupObject abstraction)
· `knx_sim/config` (YAML config). `knx_sim/web` and `knx_sim/cli` are added later
(milestone M7).
