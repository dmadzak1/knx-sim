# DPT 9.x — the 16-bit KNX float format

Wire format, 16 bits total:

```
S EEEE MMMMMMMMMMM
```

- `S` (1 bit): sign
- `E` (4 bits): exponent, 0..15
- `M` (11 bits): mantissa

`S` and `M` together form a **12-bit two's complement integer**, also called `M`
below. The decoded value is:

```
value = 0.01 * M * 2^E
```

Encoding picks the **smallest** `E` for which `M = round(value / (0.01 * 2^E))`
fits in `[-2048, 2047]`. This makes the encoding unambiguous — for any legal
value there is exactly one valid `(S, E, M)` combination the encoder will
produce, even though decoding would accept others.

## Worked example: 21.5 °C

1. Try `E=0`: `M = round(21.5 / 0.01) = 2150`. Out of range (max 2047).
2. Try `E=1`: `M = round(21.5 / 0.02) = 1075`. Fits.
3. `M = 1075` is positive, so its 12-bit two's complement form is just its
   binary representation: `1075 = 0x433 = 100 0011 0011` (11 bits, since it's
   positive the sign bit is `0`, and the 11-bit mantissa is `1075` itself:
   `1000 0110 011`).
4. Assemble: sign `0`, exponent `0001`, mantissa `10000110011`.
5. Split into bytes:
   - byte1 = `S EEEE M10 M9 M8` = `0 0001 100` = `0x0C`
   - byte2 = `M7 M6 M5 M4 M3 M2 M1 M0` = `00110011` = `0x33`

**21.5 °C → `0x0C 0x33`.**

Reversing: sign=0, E=1, M=1075 → `0.01 * 1075 * 2 = 21.5`. ✓

## Worked example: -10.0 °C (where two's complement matters)

1. `E=0`: `M = round(-10.0 / 0.01) = -1000`. Fits (`-2048 <= -1000 <= 2047`).
2. 12-bit two's complement of `-1000` is `4096 - 1000 = 3096` =
   `1100 0001 1000`.
3. Top bit (sign) = `1`; remaining 11 bits (mantissa) = `1000 0011000`.
4. byte1 = `1 0000 100` = `0x84`; byte2 = `00011000` = `0x18`.

**-10.0 °C → `0x84 0x18`.**

Reversing: mantissa bits recombine to unsigned `3096`; because the sign bit
is set, subtract `2^12 = 4096` → `-1000`. `0.01 * -1000 * 2^0 = -10.0`. ✓
This is the general rule for reading any fixed-width two's complement field:
if the sign bit is set, the value is `unsigned_reading - 2^width`.

## Range

With `E=15` (the largest exponent) and the full mantissa range:

- max: `M=2047` → `0.01 * 2047 * 32768 = 670760.96`
- min: `M=-2048` → `0.01 * -2048 * 32768 = -671088.64`

## Implementation

See `knx_sim/dpt/dpt9.py` (`DPT9Base`, shared by all DPT 9.x subtypes) and
`tests/dpt/test_dpt9.py` (known-pair tests for `0.0`, `21.5`, `-10.0`,
`100.0`, plus a hypothesis round-trip test tolerant to the resolution the
picked exponent implies).
