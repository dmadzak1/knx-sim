# cEMI L_Data frame — annotated byte layout

Cross-checked against xknx's own implementation (`xknx/cemi/cemi_frame.py`,
`xknx/cemi/const.py`, `xknx/telegram/tpci.py`, `xknx/telegram/apci.py`), not
just the spec/guesswork — the derivation below reconstructs the guide's
example bytes exactly using xknx's actual flag/APCI constants.

## Example: GroupValueWrite ON, from 1.1.23 to 1/2/10

```
29 00 BC E0 11 17 0A 0A 01 00 81
```

| Byte | Value | Field |
|---|---|---|
| 0 | `29` | Message Code (`L_Data.ind`) |
| 1 | `00` | Additional Info Length (0 = none) |
| 2 | `BC` | Control Field 1 |
| 3 | `E0` | Control Field 2 |
| 4–5 | `11 17` | Source Address (individual, 4+4+8 bits) |
| 6–7 | `0A 0A` | Destination Address (group, 5+3+8 bits) |
| 8 | `01` | NPDU Length |
| 9 | `00` | TPCI + top 2 APCI bits |
| 10 | `81` | remaining 2 APCI bits + data |

## Message Code

FROM DATA LINK LAYER TO NETWORK LAYER (received from the bus): `L_Data.ind
= 0x29`. The other two you'll meet: `L_Data.req = 0x11` (send a frame,
network layer → data link layer) and `L_Data.con = 0x2E` (local
confirmation that a frame was sent — does not mean it was received).

## Control Field 1 = `0xBC` = `1011 1100`

| bit | value | field | meaning |
|---|---|---|---|
| 7 | 1 | Frame Type | Standard frame (0 = extended) |
| 6 | 0 | reserved | always 0 |
| 5 | 1 | Repeat | "do not repeat" (this is the original frame) |
| 4 | 1 | Broadcast | normal domain broadcast |
| 3–2 | 11 | Priority | `00`=System, `01`=Normal, `10`=Urgent, `11`=**Low** (default for group telegrams) |
| 1 | 0 | Ack Request | no ack requested |
| 0 | 0 | Confirm | no error (only meaningful on `L_Data.con`) |

## Control Field 2 = `0xE0` = `1110 0000`

| bit | value | field | meaning |
|---|---|---|---|
| 7 | 1 | Destination Address Type | group address (0 = individual address) |
| 6–4 | 110 | Hop Count | `6` — standard starting TTL |
| 3–0 | 0000 | Extended Frame Format | `0` — standard addressing |

## Addresses

- **Source** `11 17` → individual address **1.1.23** (4+4+8 bits): `0001
  0001 00010111` = area 1, line 1, device 23.
- **Destination** `0A 0A` → group address **1/2/10** (5+3+8 bits): first
  byte `00001 010` = main group 1, middle group 2; second byte `00001010`
  = 10 (sub group).

## NPDU Length = `01`

Length of what follows the length byte itself, **minus 1**: i.e. `(total
TPCI+APCI+data byte count) - 1`. Here there are 2 such bytes (09, 0A), so
length = 1. For a DPT with N payload bytes appended separately (e.g. DPT
9.x, N=2), length = `1 + N`.

## TPCI / APCI — bytes 9 and 10

TPCI and APCI are packed together across these two octets; this is the
part that needs care.

- **Byte 9** (`00`): bits 7–6 = TPCI type (`00` = UDT, Unnumbered Data —
  normal for group communication; other values are numbered/control
  variants used for point-to-point connections). Bits 5–2 = sequence
  number (unused here, 0). Bits 1–0 = the **top 2 bits** of a 10-bit APCI
  field (`00` here).
- **Byte 10** (`81` = `1000 0001`): bits 7–6 = the **remaining 2 bits** of
  APCI — `10` = GroupValueWrite (`00`=Read, `01`=Response, `10`=Write).
  Bits 5–0 = where a ≤6-bit DPT value lives directly: `000001` = 1 (ON).

This is the concrete form of the DPT 1.001 rule from M1: `DPT1001.encode(True)`
produces `bytes([1])`, and the cEMI layer ORs that `1` into the low 6 bits
of this byte alongside the `0b10______` GroupValueWrite APCI code.

For DPTs with `payload_length > 0` (e.g. DPT 9.x), bits 5–0 of byte 10 are
unused/0, and the encoded value bytes are appended after byte 10 instead.

## Source

Derived by hand from KNX Application Note 117/08 (KNX IP Communication
Medium) field definitions and independently reconstructed from xknx's
`CEMIFlags`, `TPCI.to_knx()`, and `encode_cmd_and_payload()` — both
approaches produce the exact byte sequence above.
