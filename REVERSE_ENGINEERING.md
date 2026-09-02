# Reverse engineering notes: SiTcpMpcWriteXG.exe 0.4.1-2-gc782

This document deliberately separates three kinds of evidence:

1. **Public official documentation** from Bee Beans Technologies.
2. **Static analysis of the official Windows Writer** (`SiTcpMpcWriteXG.exe`).
3. **Read-only verification against matching real MPC files and hardware**.

This distinction is important: the public manuals document the SiTCP/SiTCP-XG EEPROM and Writer operation, but do not document the complete 22-byte MPC payload format or the Writer's payload classifier.

## Public official documentation

Useful public sources include:

- Bee Beans Technologies SiTCP/SiTCP-XG download page:
  https://www.bbtech.co.jp/download-files/sitcp/index_en.html
- SiTCP-XG manual (public versions are available from the download site).
- SiTCP MPC Writer XG user guide:
  https://www.bbtech.co.jp/download-files/sitcp/SiTCP-MPC-Writer-XG-en.0.1.1.pdf
- Official `sitcpy` Python repository:
  https://github.com/BeeBeansTechnologies/sitcpy
- SiTCP Forum:
  https://sitcp.bbtech.co.jp/

The public SiTCP-XG documentation establishes, among other things:

- `0xFFFF0000..0xFFFFFFFF` is reserved for SiTCP-XG internal use.
- EEPROM is accessible at `0xFFFFFC00..0xFFFFFCFF`.
- `0xFFFFFC10..0xFFFFFC4F` contains initial values corresponding to SiTCP-XG register space `0xFFFFFF10..0xFFFFFF4F`.
- writing `0x00` to `0xFFFFFCFF` releases EEPROM write protection.
- EEPROM can be read without releasing write protection.

The public MPC Writer XG guide states that the MPCX file contains the SiTCP-XG global MAC address and license information and that the Writer programs this information into EEPROM. It documents the GUI workflow, but not the byte-level 22-byte file format used by the implementation.

### Search for a public MPC/MPCX byte-level specification

As of 2026-09-03, the public Bee Beans download material and publicly searchable SiTCP Forum material were reviewed specifically for a description of the MPC/MPCX payload format. The reviewed public material contains useful information about EEPROM access, MAC/license programming, SiTCP/SiTCP-XG configuration, and the MPC Writer workflow, but **no public byte-level specification was found for the 22-byte MPC/MPCX payload or for the Writer's Type-1/Type-2 classifier**.

In particular, no reviewed public source was found that documents all of the following implementation details:

```text
payload length = 22 bytes

Type 1 classifier:
  decode payload[0:7] with the Writer's 0x2c transformation

Type 2 classifier:
  decode payload[6:13] with the Writer's 0x34 transformation

SiTCP-XG mapping:
  payload[0:16]  -> FC00..FC0F
  preserve       -> FC10..FC11
  payload[16:22] -> FC12..FC17

normal SiTCP mapping:
  payload[0:6]   -> FC12..FC17
  payload[6:22]  -> FC40..FC4F
```

This is a statement about the public material reviewed, not a claim that no such document can exist anywhere. The byte-level information used by this project should therefore be attributed to Writer analysis and hardware/file verification unless a public specification is subsequently identified.

## Confirmed RBCP functions from Writer static analysis

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

The active-low write-enable behavior is consistent with the public SiTCP-XG documentation.

## Clear MPC(X)

Static analysis of the Writer's clear path shows that it enables EEPROM writing, fills a 128-byte temporary buffer with `0xFF`, and writes it in eight 16-byte RBCP writes:

- `0xFFFFFC00..0xFFFFFC0F`
- `0xFFFFFC10..0xFFFFFC1F`
- ...
- `0xFFFFFC70..0xFFFFFC7F`

It then disables EEPROM writes again.

## Extension area

The Writer explicitly accesses 64 bytes beginning at:

- base: `0xFFFFFC10`
- size: `0x40`

This is consistent with the public SiTCP-XG register/EEPROM mapping.

## MPC/MPCX 22-byte loader — recovered from the Writer

Static analysis of `SiTcpMpcWriteXG.exe` identified the loader around VA `0x401ba0` and format classifier around VA `0x4015e0`.

- The selected MPC/MPCX payload must be exactly `0x16` (22) bytes.
- Candidate A is `raw[6:13]`, with `0x34` subtracted from every non-zero byte.
- Candidate B is `raw[0:7]`, with `0x2c` subtracted from every non-zero byte.
- A candidate is accepted when each of its seven bytes satisfies the Writer's character validation.
- If candidate A is valid, the Writer stores internal type `2`.
- Otherwise, if candidate B is valid, the Writer stores internal type `1`.
- Otherwise the file is rejected as invalid.

For the matching files tested here, the decoded tag is `"Other  "`.

**This classifier and the 22-byte byte-level format were not obtained from the public manuals. They were recovered from the official Writer and then checked against real files/hardware.**

The filename extension is therefore not authoritative. An SiTCP-XG payload can be classified from its contents even when the file is named `*.mpc` rather than `*.mpcx`.

## Verified SiTCP-XG mapping — static analysis + matching hardware/file pair

A matching 22-byte XG payload and SiTCP-XG device establish the following mapping:

```text
file[0:16]   -> EEPROM 0xFFFFFC00..0xFFFFFC0F
FC10..FC11   -> preserved current target/device bytes
file[16:22]  -> EEPROM 0xFFFFFC12..0xFFFFFC17
```

The final six payload bytes matched the target MAC address.

The observed 24-byte EEPROM record was:

```text
FFFFFC00..0F: payload[0:16]
FFFFFC10..11: existing device bytes
FFFFFC12..17: payload[16:22]
```

This independently matches the assembly around `0x408f81` / `0x409019`: the Writer copies 16 payload bytes, leaves a two-byte gap, and then copies the remaining six payload bytes. The corresponding write length is `0x18` (24 bytes).

The observed two bytes at `FC10..FC11` must **not** be treated as fixed constants; the assembly shows that they are preserved rather than supplied by the 22-byte payload.

## Verified normal SiTCP mapping — matching hardware/file pair

A matching 22-byte normal-SiTCP payload and device establish:

```text
file[0:6]   -> EEPROM 0xFFFFFC12..0xFFFFFC17  (MAC address)
file[6:22]  -> EEPROM 0xFFFFFC40..0xFFFFFC4F
```

Both regions matched the real target exactly in read-only verification.

This layout is different from the XG/type-1 24-byte record and must remain a separate implementation path.

## Evidence status summary

| Item | Public docs/forum reviewed | Writer analysis | Real hardware/file verification |
| --- | --- | --- | --- |
| RBCP access exists | yes | yes | yes |
| EEPROM `0xFFFFFC00..FF` | yes | yes | yes |
| `FCFF=00` releases write protection | yes | yes | not required for read-only verification |
| MPC payload is exactly 22 bytes | not found | yes | yes, tested files |
| content-based type classifier | not found | yes | yes, matches known SiTCP/XG files |
| XG 16 + preserved 2 + 6 mapping | not found | yes | yes |
| normal SiTCP 6 + 16 mapping | not found in reviewed material | implementation path investigated | yes |
| filename extension determines generation | no | no | no; do not use it |

## Still under reconstruction

- exact semantic meaning of every license byte
- exact meaning of the preserved XG bytes at `0xFFFFFC10..0xFFFFFC11`
- robust device-side SiTCP versus SiTCP-XG detection independent of the file
- exact conditions selecting the 24-byte versus 80-byte high-level Writer path
- EEPROM initialization from current/default RAM values
- extension-area initialization behavior for all supported device variants
- complete high-level write/read-back behavior after programming

Do not enable the high-level programming command until the remaining compatibility and write-sequence checks are reproduced or independently verified.
