"""MPC/MPCX file and EEPROM classification reconstructed from SiTcpMpcWriteXG 0.4.1-2.

The official Writer requires exactly 22 bytes and classifies the payload from
its contents. The filename extension is not used to decide whether the file
is for normal SiTCP or SiTCP-XG; an XG payload may therefore also be named
*.mpc.

Known EEPROM mappings let us reconstruct both possible 22-byte payloads from
a target EEPROM image and run the same content classifier on them. This is
used for automatic MPC/MPCX target detection without relying on the filename.
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
EEPROM_DETECT_SIZE = 0x50


def _valid_tag(buf: bytes) -> bool:
    if len(buf) != 7:
        return False
    for b in buf:
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


def classify_payload(data: bytes) -> int:
    """Return official Writer type: 1=XG/MPCX, 2=normal SiTCP/MPC, 0=unknown."""
    if len(data) != MPC_FILE_SIZE:
        return 0
    a = _decode_nonzero(data[6:13], 0x34)
    b = _decode_nonzero(data[0:7], 0x2C)
    if _valid_tag(a):
        return 2
    if _valid_tag(b):
        return 1
    return 0


def payload_type_name(writer_type: int) -> str:
    if writer_type == 1:
        return "MPCX (SiTCP-XG)"
    if writer_type == 2:
        return "MPC (normal SiTCP)"
    if writer_type == -1:
        return "ambiguous"
    return "unknown"


def build_mpcx_eeprom_record(mpcx: bytes, preserved_fc10_fc11: bytes) -> bytes:
    if len(mpcx) != MPC_FILE_SIZE:
        raise ValueError(f"MPC/X payload must be exactly {MPC_FILE_SIZE} bytes, got {len(mpcx)}")
    if len(preserved_fc10_fc11) != MPCX_PRESERVED_SIZE:
        raise ValueError("preserved FC10..FC11 field must be exactly 2 bytes")
    return mpcx[:16] + preserved_fc10_fc11 + mpcx[16:]


def reconstruct_xg_payload(eeprom_fc00_fc4f: bytes) -> bytes:
    """Reconstruct the 22-byte XG/MPCX payload from EEPROM FC00..FC4F."""
    if len(eeprom_fc00_fc4f) < EEPROM_DETECT_SIZE:
        raise ValueError("EEPROM image must contain FC00..FC4F (80 bytes)")
    return eeprom_fc00_fc4f[0:16] + eeprom_fc00_fc4f[18:24]


def reconstruct_normal_payload(eeprom_fc00_fc4f: bytes) -> bytes:
    """Reconstruct the 22-byte normal-SiTCP/MPC payload from EEPROM FC00..FC4F."""
    if len(eeprom_fc00_fc4f) < EEPROM_DETECT_SIZE:
        raise ValueError("EEPROM image must contain FC00..FC4F (80 bytes)")
    return eeprom_fc00_fc4f[0x12:0x18] + eeprom_fc00_fc4f[0x40:0x50]


def detect_eeprom_payload_type(eeprom_fc00_fc4f: bytes) -> tuple[int, bytes | None]:
    """Auto-detect target type using reconstructed payloads and the Writer classifier.

    Returns ``(1, xg_payload)`` for MPCX/SiTCP-XG, ``(2, normal_payload)`` for
    MPC/normal SiTCP, ``(0, None)`` if neither mapping classifies, and
    ``(-1, None)`` if both classify and the result is ambiguous.
    """
    xg_payload = reconstruct_xg_payload(eeprom_fc00_fc4f)
    normal_payload = reconstruct_normal_payload(eeprom_fc00_fc4f)
    xg_ok = classify_payload(xg_payload) == 1
    normal_ok = classify_payload(normal_payload) == 2
    if xg_ok and not normal_ok:
        return 1, xg_payload
    if normal_ok and not xg_ok:
        return 2, normal_payload
    if xg_ok and normal_ok:
        return -1, None
    return 0, None


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
    size_ok = len(data) == MPC_FILE_SIZE
    writer_type = classify_payload(data)
    decoded_tag = None
    decoded_tag_hex = None
    alternate = None

    if writer_type:
        a = _decode_nonzero(data[6:13], 0x34)
        b = _decode_nonzero(data[0:7], 0x2C)
        tag, other = (a, b) if writer_type == 2 else (b, a)
        decoded_tag = tag.rstrip(b"\x00").decode("ascii", errors="replace")
        decoded_tag_hex = tag.hex(" ")
        alternate = other.hex(" ")

    if writer_type == 1:
        kind = "SiTCP-XG MPC payload"
    elif writer_type == 2:
        kind = "normal SiTCP MPC payload"
    else:
        kind = "unknown/invalid MPC payload"

    return MpcInfo(
        path=p, kind=kind, size=len(data), sha256=hashlib.sha256(data).hexdigest(),
        preview_hex=data[:preview_bytes].hex(" "), writer_size_valid=size_ok,
        writer_type=writer_type, decoded_tag=decoded_tag,
        decoded_tag_hex=decoded_tag_hex, alternate_decoded_hex=alternate,
    )
