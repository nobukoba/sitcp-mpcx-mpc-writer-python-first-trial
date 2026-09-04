# Implementation notes: SiTCP / SiTCP-XG MPC compatibility

This document records the technical information needed to independently implement and verify interoperability with SiTCP / SiTCP-XG MPC data and EEPROM programming.

The project is intended to use **legitimately obtained MPC/MPCX data with authorized hardware**. It does not generate, modify, derive, or bypass SiTCP license data. The license payload is treated as opaque data.

## Sources and verification method

The implementation was developed from a combination of:

1. **Public Bee Beans Technologies documentation and software** describing SiTCP/SiTCP-XG, RBCP, EEPROM access, write protection, and the MPC Writer workflow.
2. **Compatibility analysis of the behavior of the official Windows MPC Writer**, used where the reviewed public documentation did not provide sufficient byte-level detail for an interoperable implementation.
3. **Verification with legitimately obtained MPC/MPCX files and matching hardware**, including read-back comparisons.

These categories are kept separate below so that publicly documented behavior can be distinguished from compatibility observations.

## Public references

- SiTCP / SiTCP-XG downloads and manuals: https://www.bbtech.co.jp/download-files/sitcp/index_en.html
- SiTCP MPC Writer XG guide: https://www.bbtech.co.jp/download-files/sitcp/SiTCP-MPC-Writer-XG-en.0.1.1.pdf
- Bee Beans Technologies `sitcpy`: https://github.com/BeeBeansTechnologies/sitcpy
- SiTCP Forum: https://sitcp.bbtech.co.jp/

The public SiTCP-XG documentation establishes, among other things:

- `0xFFFF0000..0xFFFFFFFF` is reserved for SiTCP-XG internal use.
- EEPROM is accessible at `0xFFFFFC00..0xFFFFFCFF`.
- `0xFFFFFC10..0xFFFFFC4F` contains initial values corresponding to SiTCP-XG register space `0xFFFFFF10..0xFFFFFF4F`.
- writing `0x00` to `0xFFFFFCFF` releases EEPROM write protection.
- EEPROM can be read without releasing write protection.

The public MPC Writer XG guide states that an MPCX file contains the SiTCP-XG global MAC address and license information and that the Writer programs this information into EEPROM.

## RBCP transport

The implementation uses standard RBCP request framing:

```text
write: ff 80 ID LEN ADDR[31:0] DATA...
read:  ff c0 ID LEN ADDR[31:0]
```

The default UDP port used by this project is `4660`.

EEPROM programming is enabled by writing:

```text
0xFFFFFCFF <- 0x00
```

and disabled again with:

```text
0xFFFFFCFF <- 0xFF
```

The implementation always restores write protection after a programming attempt.

## MPC/MPCX payload handling

Files used with the tested Writer/device combinations contain a **22-byte payload**. The filename extension is not sufficient to determine the required EEPROM layout, so this implementation classifies the payload from its contents.

For interoperability, the observed classifier can be reproduced as follows:

```text
payload length = 22 bytes

candidate A = payload[6:13]
  subtract 0x34 from each non-zero byte

candidate B = payload[0:7]
  subtract 0x2c from each non-zero byte

if candidate A passes the expected seven-character validation:
    use type 2
else if candidate B passes the expected seven-character validation:
    use type 1
else:
    reject the payload
```

For the matching files used during verification, the decoded tag is `"Other  "`.

This content-based behavior is why an SiTCP-XG payload can still be recognized when its filename uses `.mpc` rather than `.mpcx`.

The semantic meaning of the opaque license bytes is deliberately not interpreted by this project.

## SiTCP-XG EEPROM layout

For the tested SiTCP-XG payload/device pair, the 22-byte file is programmed as a 24-byte record:

```text
payload[0:16]   -> EEPROM 0xFFFFFC00..0xFFFFFC0F
existing bytes  -> EEPROM 0xFFFFFC10..0xFFFFFC11
payload[16:22]  -> EEPROM 0xFFFFFC12..0xFFFFFC17
```

Therefore an implementation should:

1. read and preserve `0xFFFFFC10..0xFFFFFC11` from the target;
2. construct the 24-byte record shown above;
3. program it to `0xFFFFFC00..0xFFFFFC17`;
4. read it back and verify it byte-for-byte.

The two preserved bytes are target-dependent and must not be replaced with fixed constants.

## Normal SiTCP EEPROM layout

For the tested normal-SiTCP payload/device pair:

```text
payload[0:6]   -> EEPROM 0xFFFFFC12..0xFFFFFC17
payload[6:22]  -> EEPROM 0xFFFFFC40..0xFFFFFC4F
```

The rest of the relevant EEPROM image should be preserved. This is a different programming path from the SiTCP-XG 24-byte record.

## Clear operation

The compatible clear operation covers 128 bytes beginning at `0xFFFFFC00`, using `0xFF` values:

```text
0xFFFFFC00..0xFFFFFC7F <- 0xFF
```

The implementation performs this in 16-byte RBCP transactions and restores EEPROM write protection afterwards.

Clearing is destructive and should require explicit user confirmation.

## Programming sequence

The writer implemented in this repository follows this sequence:

```text
validate/classify 22-byte payload
        |
        v
read EEPROM bytes that must be preserved
        |
        v
enable EEPROM writes (FCFF <- 00)
        |
        v
write in 16-byte RBCP transactions
        |
        v
disable EEPROM writes (FCFF <- FF)
        |
        v
read back and verify byte-for-byte
```

Write requests are intentionally not automatically retried. With UDP, loss of an acknowledgement does not establish that the EEPROM write itself failed; blindly repeating an EEPROM write could therefore be undesirable.

## Evidence status

| Item | Public documentation | Compatibility observation | Hardware/file verification |
| --- | --- | --- | --- |
| RBCP access | yes | yes | yes |
| EEPROM `0xFFFFFC00..FF` | yes | yes | yes |
| `FCFF=00` releases write protection | yes | yes | consistent |
| MPC payload length of 22 bytes | not found in reviewed manuals | yes | yes for tested files |
| content-based payload classifier | not found in reviewed manuals | yes | yes for tested files |
| XG 16 + preserved 2 + 6 mapping | not found in reviewed manuals | yes | yes |
| normal SiTCP 6 + 16 mapping | not found in reviewed manuals | compatible behavior established | yes |
| filename extension determines type | no | no | no |

“Not found” means only that the information was not found in the public material reviewed for this project; it is not a claim that no public specification exists.

## Scope and limitations

The following are intentionally outside the scope of this implementation:

- generating SiTCP license data;
- modifying or deriving license contents;
- bypassing license checks or authorization;
- interpreting the semantic meaning of individual license bytes.

Areas that may still benefit from independent verification include:

- exact meaning of the preserved XG bytes at `0xFFFFFC10..0xFFFFFC11`;
- device-side SiTCP versus SiTCP-XG detection independent of the input file;
- EEPROM initialization behavior across additional supported device variants.

Contributions that confirm behavior from public documentation or additional authorized hardware are welcome.
