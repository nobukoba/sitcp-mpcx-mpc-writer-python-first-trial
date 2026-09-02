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
enabling EEPROM writes. More field-level mapping is still required before this
is exposed as MPC/MPCX programming.

## Still under reconstruction

- exact `.mpc` / `.mpcx` file field layout
- compatibility checks between file and device
- mapping from parsed MPCX fields into the 64-byte block at `0xFFFFFC10`
- EEPROM initialization from current RAM/default RAM values
- extension-area ranges beyond the confirmed 64-byte access
- verification / retry behavior around the high-level write workflow

Do not infer those fields from offsets until confirmed by additional static or
packet-level analysis.

## MPC/MPCX 22-byte loader (2026-09-02)

Reverse engineering of `SiTcpMpcWriteXG.exe` identified the loader around
VA `0x401ba0` and format classifier around VA `0x4015e0`.

* The selected MPC/MPCX file must be exactly `0x16` (22) bytes.
* Candidate A is `raw[6:13]`, with `0x34` subtracted from every non-zero byte.
* Candidate B is `raw[0:7]`, with `0x2c` subtracted from every non-zero byte.
* A candidate is accepted when each of its seven bytes is alphanumeric,
  `'-'`, or NUL.
* If candidate A is valid, the Writer stores internal type `2`.
* Otherwise, if candidate B is valid, the Writer stores internal type `1`.
* Otherwise the file is rejected as invalid.

For the supplied `SN_2F20880CDE.mpcx`, candidate B decodes to ASCII
`"Other  "`, so the official Writer classifies it as internal type `1`.
The remaining bytes are still treated as opaque until their EEPROM mapping is
fully reconstructed.
