"""Minimal RBCP client for SiTCP.

Implemented from the public RBCP packet description and the public sitcpy
implementation by Bee Beans Technologies. This module intentionally contains
no MPC/MPCX EEPROM programming assumptions.
"""
from __future__ import annotations

import socket
import struct


class RbcpError(RuntimeError):
    pass


class RbcpTimeout(RbcpError):
    pass


class RbcpBusError(RbcpError):
    pass


class RbcpClient:
    HEADER_SIZE = 8
    VERSION_TYPE = 0xFF
    CMD_READ = 0xC0
    CMD_WRITE = 0x80

    def __init__(self, host: str, port: int = 4660, timeout: float = 1.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._packet_id = 0

    def _next_id(self) -> int:
        value = self._packet_id
        self._packet_id = (self._packet_id + 1) & 0xFF
        return value

    def _header(self, command: int, address: int, length: int, packet_id: int) -> bytes:
        if not 0 <= address <= 0xFFFFFFFF:
            raise ValueError("address must be 0..0xffffffff")
        if not 0 <= length <= 255:
            raise ValueError("length must be 0..255")
        return struct.pack(
            ">BBBBI",
            self.VERSION_TYPE,
            command,
            packet_id,
            length,
            address,
        )

    def _transaction(self, packet: bytes, packet_id: int) -> bytes:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout)
            sock.sendto(packet, (self.host, self.port))
            try:
                reply, _ = sock.recvfrom(self.HEADER_SIZE + 255)
            except socket.timeout as exc:
                raise RbcpTimeout(
                    f"RBCP timeout from {self.host}:{self.port}"
                ) from exc

        if len(reply) < self.HEADER_SIZE:
            raise RbcpError(f"short RBCP reply: {len(reply)} bytes")
        if reply[0] != self.VERSION_TYPE:
            raise RbcpError(f"unexpected RBCP version/type: 0x{reply[0]:02x}")
        if reply[2] != packet_id:
            raise RbcpError(
                f"packet ID mismatch: expected {packet_id}, received {reply[2]}"
            )
        if reply[1] & 0x01:
            raise RbcpBusError("RBCP bus error returned by target")
        return reply[self.HEADER_SIZE :]

    def read(self, address: int, length: int) -> bytes:
        packet_id = self._next_id()
        header = self._header(self.CMD_READ, address, length, packet_id)
        return self._transaction(header, packet_id)

    def write(self, address: int, data: bytes) -> bytes:
        if len(data) > 255:
            raise ValueError("one RBCP write is limited to 255 bytes")
        packet_id = self._next_id()
        header = self._header(self.CMD_WRITE, address, len(data), packet_id)
        return self._transaction(header + data, packet_id)
