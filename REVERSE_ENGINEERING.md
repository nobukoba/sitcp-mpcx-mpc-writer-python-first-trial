# Reverse engineering notes: SiTcpMpcWriteXG.exe 0.4.1-2-gc782

Static analysis target: official 32-bit Windows/Qt5 executable.

## Confirmed RBCP functions

- `0x409960`: RBCP write routine.
  - argument 1: 32-bit register address
  - argument 2: data pointer
  - argument 3: byte length
  - packet header: `ff 80 ID LEN ADDR[31:0]`
- `0x409e50`: RBCP read routine.
  - packet header: `ff c0 ID LEN ADDR[31:0]`

## EEPROM write enable

Helper at `0x40a060` writes one byte to:

- address: `0xFFFFFCFF`
- enable: `0x00`
- disable: `0xFF`

The control is therefore active-low in this writer.

## Clear MPC(X)

The clear path calls write-enable, fills a 128-byte temporary buffer with
`0xFF`, then writes it in eight 16-byte RBCP writes:

- `0xFFFFFC00..0xFFFFFC0F`
- `0xFFFFFC10..0xFFFFFC1F`
- ...
- `0xFFFFFC70..0xFFFFFC7F`

It then disables EEPROM writes again. This corresponds to the GUI's
`Clear MPCX` / successful-clear path.

## Extension area

The writer explicitly reads and writes 64 bytes at:

- base: `0xFFFFFC10`
- size: `0x40`

The write path constructs a 64-byte structure and writes the whole block after
enabling EEPROM writes.

## MPC/MPCX 22-byte loader

Reverse engineering of `SiTcpMpcWriteXG.exe` identified the loader around
VA `0x401ba0` and format classifier around VA `0x4015e0`.

- The selected MPC/MPCX file must be exactly `0x16` (22) bytes.
- Candidate A is `raw[6:13]`, with `0x34` subtracted from every non-zero byte.
- Candidate B is `raw[0:7]`, with `0x2c` subtracted from every non-zero byte.
- A candidate is accepted when each of its seven bytes is alphanumeric,
  `'-'`, NUL, or the Writer's space-equivalent case caused by its `0xDF` mask.
- If candidate A is valid, the Writer stores internal type `2`.
- Otherwise, if candidate B is valid, the Writer stores internal type `1`.
- Otherwise the file is rejected as invalid.

For the supplied XG MPCX examples, candidate B decodes to ASCII `"Other  "`,
so the official Writer classifies them as internal type `1`.

## Confirmed SiTCP-XG MPCX EEPROM mapping (2026-09-03)

Static analysis and a matching real SiTCP-XG device/file pair confirm the
24-byte record written at `0xFFFFFC00` for the XG/type-1 path.

Matching MPCX file (22 bytes):

```
7b a0 94 91 9e 4c 4c 2d 2c 45 2f 37 d0 79 da b0
7c f0 98 01 1f 70
```

Observed target EEPROM:

```
FFFFFC00..07: 7b a0 94 91 9e 4c 4c 2d
FFFFFC08..0F: 2c 45 2f 37 d0 79 da b0
FFFFFC10..17: 17 00 7c f0 98 01 1f 70
```

Therefore:

```
MPCX[0:16]   -> FFFFFC00..FFFFFC0F
FC10..FC11   -> preserved target/device bytes
MPCX[16:22]  -> FFFFFC12..FFFFFC17
```

The final 6 bytes of the MPCX are the MAC address for the observed device.

This also matches the assembly around `0x408f81` / `0x409019`. The Writer
constructs the `0xFFFFFC00` write buffer by copying:

- four dwords into record bytes 0..15,
- then leaving a two-byte gap at record bytes 16..17,
- then one dword plus one word into record bytes 18..23.

The write length is `0x18` (24 bytes) on the corresponding path.
Crucially, the assembly does **not** fill the two-byte gap from the 22-byte
MPCX payload. Thus the observed `17 00` at `FC10..FC11` must not be treated as
fixed MPCX constants. They are existing/device-state bytes preserved in the
24-byte record.

A safe `mpcx-plan` CLI command has been added which reads `FC10..FC11`, builds
the reconstructed 24-byte record, prints it, and performs no write.

## Confirmed standard SiTCP MPC mapping from a matching device/file pair

For the supplied 22-byte `.mpc` sample and matching standard SiTCP device:

- `.mpc[0:6]` matches EEPROM `0xFFFFFC12..0xFFFFFC17` (MAC address).
- `.mpc[6:22]` matches EEPROM `0xFFFFFC40..0xFFFFFC4F`.

This standard-SiTCP layout is different from the XG/type-1 24-byte record and
must remain a separate implementation path.

## Still under reconstruction

- exact meaning of the preserved XG bytes at `0xFFFFFC10..0xFFFFFC11`
- compatibility checks between file and device
- exact conditions selecting the 24-byte versus 80-byte high-level write path
- EEPROM initialization from current RAM/default RAM values
- extension-area initialization behavior for all device variants
- high-level verification/readback behavior after programming

Do not enable the high-level programming command until those remaining checks
are reproduced or independently verified.
