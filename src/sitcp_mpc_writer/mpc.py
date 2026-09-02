"""MPC/MPCX file inspection reconstructed from SiTcpMpcWriteXG 0.4.1-2.

The official Writer requires exactly 22 bytes and tests two 7-byte decoded
views of the file.  These rules are reconstructed from the x86 binary; fields
that are not yet understood remain opaque.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


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

    size_ok = len(data) == 22
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
