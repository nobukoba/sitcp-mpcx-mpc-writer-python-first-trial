"""SiTCP/SiTCP-XG EEPROM access helpers.

The EEPROM mappings used here are based on public SiTCP/SiTCP-XG documentation,
static analysis of the official MPC Writer, and read-only checks against matching
real MPC/MPCX files and devices.
"""
from __future__ import annotations

from .rbcp import RbcpClient, RbcpTimeout

EEPROM_BASE = 0xFFFFFC00
EEPROM_MPC_CLEAR_END = 0xFFFFFC80  # exclusive
EEPROM_WRITE_ENABLE = 0xFFFFFCFF
EEPROM_EXTENSION_BASE = 0xFFFFFC10
EEPROM_EXTENSION_SIZE = 0x40
EEPROM_ACCESS_BLOCK_SIZE = 0x10
EEPROM_READ_CHUNK_SIZE = 8
EEPROM_READ_ATTEMPTS = 3


def set_write_enable(client: RbcpClient, enabled: bool) -> None:
    """Enable/disable EEPROM writes using the active-low FCFF control byte."""
    value = b"\x00" if enabled else b"\xff"
    reply = client.write(EEPROM_WRITE_ENABLE, value)
    if len(reply) != 1:
        raise RuntimeError(
            f"unexpected RBCP ACK length for EEPROM write-enable: {len(reply)}"
        )


def _read_once_with_retry(
    client: RbcpClient,
    address: int,
    length: int,
    attempts: int = EEPROM_READ_ATTEMPTS,
) -> bytes:
    last_error = None
    for _ in range(attempts):
        try:
            return client.read(address, length)
        except RbcpTimeout as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _read_exact(
    client: RbcpClient,
    address: int,
    length: int,
    chunk_size: int = EEPROM_READ_CHUNK_SIZE,
) -> bytes:
    out = bytearray()
    for offset in range(0, length, chunk_size):
        size = min(chunk_size, length - offset)
        data = _read_once_with_retry(client, address + offset, size)
        if len(data) != size:
            raise RuntimeError(
                f"short EEPROM read at 0x{address + offset:08x}: expected {size}, got {len(data)}"
            )
        out.extend(data)
    return bytes(out)


def _write_exact(client: RbcpClient, address: int, data: bytes, chunk_size: int = 16) -> None:
    """Write without automatic retries.

    A lost UDP ACK does not prove that an EEPROM write failed, so write
    transactions are deliberately not retried blindly.
    """
    for offset in range(0, len(data), chunk_size):
        block = data[offset : offset + chunk_size]
        reply = client.write(address + offset, block)
        if len(reply) != len(block):
            raise RuntimeError(
                f"short RBCP ACK while writing 0x{address + offset:08x}: "
                f"expected {len(block)}, got {len(reply)}"
            )


def read_extension(client: RbcpClient) -> bytes:
    """Read 0xFFFFFC10..0xFFFFFC4F in conservative 8-byte chunks with retries."""
    return _read_exact(client, EEPROM_EXTENSION_BASE, EEPROM_EXTENSION_SIZE)


def build_program_image(client: RbcpClient, payload: bytes, writer_type: int) -> tuple[int, bytes]:
    """Build the exact EEPROM image to be written while preserving device bytes.

    writer_type 1 (SiTCP-XG):
      payload[0:16]  -> FC00..FC0F
      current FC10..FC11 are preserved
      payload[16:22] -> FC12..FC17

    writer_type 2 (normal SiTCP):
      the current FC00..FC4F image is preserved except for
      payload[0:6]   -> FC12..FC17
      payload[6:22]  -> FC40..FC4F

    The normal-SiTCP path writes an 80-byte FC00..FC4F image, matching the
    reconstructed official Writer behavior while preserving all fields that are
    not present in the 22-byte MPC file.
    """
    if len(payload) != 22:
        raise ValueError(f"MPC/MPCX payload must be exactly 22 bytes, got {len(payload)}")

    if writer_type == 1:
        current = bytearray(_read_exact(client, EEPROM_BASE, 24))
        current[0:16] = payload[0:16]
        current[18:24] = payload[16:22]
        return EEPROM_BASE, bytes(current)

    if writer_type == 2:
        current = bytearray(_read_exact(client, EEPROM_BASE, 0x50))
        current[0x12:0x18] = payload[0:6]
        current[0x40:0x50] = payload[6:22]
        return EEPROM_BASE, bytes(current)

    raise ValueError(f"unsupported MPC writer type: {writer_type}")


def program_mpc_payload(client: RbcpClient, payload: bytes, writer_type: int) -> bytes:
    """Program a validated 22-byte MPC/MPCX payload and verify by read-back.

    EEPROM write access is always disabled again in a ``finally`` block.
    Returns the verified EEPROM image that was written.
    """
    address, image = build_program_image(client, payload, writer_type)

    set_write_enable(client, True)
    try:
        _write_exact(client, address, image, 16)
    finally:
        set_write_enable(client, False)

    actual = _read_exact(client, address, len(image))
    if actual != image:
        mismatch = next(
            (i for i, (expected, got) in enumerate(zip(image, actual)) if expected != got),
            None,
        )
        if mismatch is None:
            mismatch_text = "unknown"
        else:
            mismatch_text = (
                f"0x{address + mismatch:08x}: expected 0x{image[mismatch]:02x}, "
                f"got 0x{actual[mismatch]:02x}"
            )
        raise RuntimeError(f"EEPROM read-back verification failed at {mismatch_text}")

    return actual


def clear_mpc_area(client: RbcpClient) -> None:
    """Reproduce the official writer's destructive MPC clear sequence."""
    set_write_enable(client, True)
    try:
        _write_exact(
            client,
            EEPROM_BASE,
            b"\xff" * (EEPROM_MPC_CLEAR_END - EEPROM_BASE),
            EEPROM_ACCESS_BLOCK_SIZE,
        )
    finally:
        set_write_enable(client, False)
