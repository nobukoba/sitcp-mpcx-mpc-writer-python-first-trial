"""MPC/MPCX file inspection reconstructed from SiTcpMpcWriteXG 0.4.1-2.

The official Writer requires exactly 22 bytes and tests two 7-byte decoded
views of the file. These rules are reconstructed from the x86 binary.

For SiTCP-XG, static analysis plus a matching real-device EEPROM dump shows
that the 22-byte MPCX payload is written into a 24-byte EEPROM record at
0xFFFFFC00 as follows:

    MPCX[0:16]  -> EEPROM bytes 0..15
    existing EEPROM bytes FC10..FC11 -> record bytes 16..17 (preserved)
    MPCX[16:22] -> EEPROM bytes 18..23

The two bytes at FC10..FC11 are therefore *not* constants from the MPCX file.
The official Writer's assembly leaves the corresponding two-byte gap intact
while copying the 22 MPCX bytes into its 24-byte write buffer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


MPC_FILE_SIZE = 22
MPCX_EEPROM_RECORD_SIZE = 24
MPCX_EEPROM_BASE = 0xFFFFFC00
MPCX_PRESERVED_OFFSET = 16
MPCX_PRESERVED_SIZE = 2


def _valid_tag(buf: bytes) -> bool:
    if len(buf) != 7:
        return False
    for b in buf:
        # The Writer masks with 0xDF before its NUL test, so ASCII space
        # (0x20) is also accepted because it becomes zero.
        if b in (0, 0x20, ord('-')):
            continue
        if ord('0') <= b <= ord('9'):
            continue
        if ord('A') <= (b & 0xDF) <= ord('Z'):
            continue
        return False
    return True


def _decode_nonzero(buf: bytes, delta: int) -> bytes:
    return bytes(((b - delta) & 0xFF) if b else 0 for b in buf)


def build_mpcx_eeprom_record(mpcx: bytes, preserved_fc10_fc11: bytes) -> bytes:
    """Build the reconstructed 24-byte SiTCP-XG EEPROM record.

    This function does not perform any I/O. The two bytes corresponding to
    EEPROM addresses 0xFFFFFC10..0xFFFFFC11 must be read from the target and
    supplied explicitly; they are preserved by the official Writer rather
    than taken from the 22-byte MPCX file.
    """
    if len(mpcx) != MPC_FILE_SIZE:
        raise ValueError(f"MPCX must be exactly {MPC_FILE_SIZE} bytes, got {len(mpcx)}")
    if len(preserved_fc10_fc11) != MPCX_PRESERVED_SIZE:
        raise ValueError(
            "preserved FC10..FC11 field must be exactly 2 bytes, "
            f"got {len(preserved_fc10_fc11)}"
        )
    return mpcx[:16] + preserved_fc10_fc11 + mpcx[16:]


@dataclass(frozen=True)
class MpcInfo:
    path: Path
    kind: str
    size: int
    sha256: str
    preview_hex: str
    writer_size_valid: bool
    writer_type: int
    decoded_tag: str | None
    decoded_tag_hex: str | None
    alternate_decoded_hex: str | None


def inspect_file(path: str | Path, preview_bytes: int = 32) -> MpcInfo:
    p = Path(path)
    data = p.read_bytes()
    suffix = p.suffix.lower()
    if suffix == ".mpcx":
        kind = "MPCX (SiTCP-XG candidate)"
    elif suffix == ".mpc":
        kind = "MPC (SiTCP candidate)"
    else:
        kind = "unknown"

    size_ok = len(data) == MPC_FILE_SIZE
    writer_type = 0
    decoded_tag = None
    decoded_tag_hex = None
    alternate = None

    if size_ok:
        # Reconstructed from function at VA 0x4015e0.
        # Candidate A uses raw[6:13] and subtracts 0x34 from non-zero bytes.
        # Candidate B uses raw[0:7] and subtracts 0x2c from non-zero bytes.
        a = _decode_nonzero(data[6:13], 0x34)
        b = _decode_nonzero(data[0:7], 0x2C)
        if _valid_tag(a):
            writer_type = 2
            tag, other = a, b
        elif _valid_tag(b):
            writer_type = 1
            tag, other = b, a
        else:
            tag, other = None, None

        if tag is not None:
            decoded_tag = tag.rstrip(b"\x00").decode("ascii", errors="replace")
            decoded_tag_hex = tag.hex(" ")
            alternate = other.hex(" ")

    return MpcInfo(
        path=p,
        kind=kind,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        preview_hex=data[:preview_bytes].hex(" "),
        writer_size_valid=size_ok,
        writer_type=writer_type,
        decoded_tag=decoded_tag,
        decoded_tag_hex=decoded_tag_hex,
        alternate_decoded_hex=alternate,
    )
