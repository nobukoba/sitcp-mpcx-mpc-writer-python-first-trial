"""SiTCP/SiTCP-XG EEPROM access primitives reconstructed from MPC Writer XG 0.4.1-2.

The constants in this module were obtained by static analysis of the official
SiTcpMpcWriteXG.exe. High-level MPCX programming remains intentionally
incomplete until the file-to-EEPROM field mapping is fully reconstructed.
"""
from __future__ import annotations

from .rbcp import RbcpClient

EEPROM_BASE = 0xFFFFFC00
EEPROM_MPC_CLEAR_END = 0xFFFFFC80  # exclusive
EEPROM_WRITE_ENABLE = 0xFFFFFCFF
EEPROM_EXTENSION_BASE = 0xFFFFFC10
EEPROM_EXTENSION_SIZE = 0x40
EEPROM_ACCESS_BLOCK_SIZE = 0x10


def set_write_enable(client: RbcpClient, enabled: bool) -> None:
    # Official Writer XG 0.4.1-2 uses active-low write enable:
    # enabled=True -> 0x00, enabled=False -> 0xff.
    value = b"\x00" if enabled else b"\xff"
    reply = client.write(EEPROM_WRITE_ENABLE, value)
    if len(reply) != 1:
        raise RuntimeError(f"unexpected RBCP ACK length for EEPROM write-enable: {len(reply)}")


def read_extension(client: RbcpClient) -> bytes:
    """Read 0xFFFFFC10..0xFFFFFC4F in conservative 16-byte chunks.

    Actual hardware testing showed that a one-byte access at 0xFFFFFC10 works,
    while a single 64-byte request can time out. The official writer also uses
    16-byte granularity for several EEPROM operations, so chunking avoids
    assuming that every SiTCP/SiTCP-XG implementation accepts a 64-byte RBCP
    transaction to this internal region.
    """
    blocks = []
    for offset in range(0, EEPROM_EXTENSION_SIZE, EEPROM_ACCESS_BLOCK_SIZE):
        address = EEPROM_EXTENSION_BASE + offset
        data = client.read(address, EEPROM_ACCESS_BLOCK_SIZE)
        if len(data) != EEPROM_ACCESS_BLOCK_SIZE:
            raise RuntimeError(
                f"short EEPROM read at 0x{address:08x}: "
                f"expected {EEPROM_ACCESS_BLOCK_SIZE}, got {len(data)}"
            )
        blocks.append(data)
    return b"".join(blocks)


def clear_mpc_area(client: RbcpClient) -> None:
    """Reproduce the official writer's MPC clear sequence.

    Destructive: erases 0xFFFFFC00..0xFFFFFC7F by writing 0xff in 16-byte chunks.
    Write-enable is restored to disabled in a finally block.
    """
    set_write_enable(client, True)
    try:
        block = b"\xff" * EEPROM_ACCESS_BLOCK_SIZE
        for address in range(EEPROM_BASE, EEPROM_MPC_CLEAR_END, EEPROM_ACCESS_BLOCK_SIZE):
            reply = client.write(address, block)
            if len(reply) != len(block):
                raise RuntimeError(
                    f"short RBCP ACK while clearing 0x{address:08x}: {len(reply)}"
                )
    finally:
        set_write_enable(client, False)
