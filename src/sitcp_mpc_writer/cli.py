from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .mpc import inspect_file, build_mpcx_eeprom_record
from .rbcp import RbcpClient, RbcpError, RbcpTimeout
from .eeprom import read_extension, clear_mpc_area


def _int_auto(value: str) -> int:
    return int(value, 0)


def _read_with_retry(c: RbcpClient, address: int, length: int, attempts: int = 3) -> bytes:
    """Retry a read-only RBCP transaction after transient UDP timeouts.

    Reads are safe to repeat.  Writes are intentionally not retried here because
    a lost ACK does not prove that the target failed to perform the write.
    """
    last_error: RbcpTimeout | None = None
    for _ in range(attempts):
        try:
            return c.read(address, length)
        except RbcpTimeout as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _read_preserved_mpcx_bytes(c: RbcpClient) -> bytes:
    """Read FC10-11 robustly for the reconstructed XG 24-byte record.

    Prefer one 2-byte request.  If that repeatedly times out, fall back to two
    independent one-byte reads; real XG hardware has shown occasional timeout
    sensitivity depending on EEPROM read length/transaction timing.
    """
    try:
        return _read_with_retry(c, 0xFFFFFC10, 2)
    except RbcpTimeout:
        return (
            _read_with_retry(c, 0xFFFFFC10, 1)
            + _read_with_retry(c, 0xFFFFFC11, 1)
        )


def cmd_inspect(args: argparse.Namespace) -> int:
    info = inspect_file(args.file, args.preview)
    print(f"file    : {info.path}")
    print(f"kind    : {info.kind}")
    print(f"size    : {info.size} bytes")
    print(f"sha256  : {info.sha256}")
    print(f"preview : {info.preview_hex}")
    print(f"writer-size-valid : {info.writer_size_valid}")
    print(f"writer-type       : {info.writer_type}")
    print(f"decoded-tag       : {info.decoded_tag}")
    print(f"decoded-tag-hex   : {info.decoded_tag_hex}")
    print(f"alternate-decoded: {info.alternate_decoded_hex}")
    return 0


def cmd_rbcp_read(args: argparse.Namespace) -> int:
    c = RbcpClient(args.ip, args.port, args.timeout)
    data = c.read(args.address, args.length)
    print(data.hex(" "))
    return 0


def cmd_rbcp_write(args: argparse.Namespace) -> int:
    data = bytes.fromhex(args.hex_data.replace("0x", "").replace(",", " "))
    c = RbcpClient(args.ip, args.port, args.timeout)
    c.write(args.address, data)
    print(f"wrote {len(data)} byte(s) to 0x{args.address:08x}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    c = RbcpClient(args.ip, args.port, args.timeout)
    data = c.read(args.address, args.length)
    print(f"RBCP reachable: {args.ip}:{args.port}")
    print(f"read 0x{args.address:08x}+{args.length}: {data.hex(' ')}")
    return 0


def cmd_mpcx_plan(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = path.read_bytes()
    if path.suffix.lower() != ".mpcx":
        print("ERROR: mpcx-plan expects a .mpcx file", file=sys.stderr)
        return 2
    if len(data) != 22:
        print(f"ERROR: MPCX must be exactly 22 bytes, got {len(data)}", file=sys.stderr)
        return 2

    c = RbcpClient(args.ip, args.port, args.timeout)
    preserved = _read_preserved_mpcx_bytes(c)
    record = build_mpcx_eeprom_record(data, preserved)

    target_mac = record[18:24]
    print(f"MPCX file        : {path}")
    print(f"preserve FC10-11 : {preserved.hex(' ')}")
    print(f"MPCX[0:16]       : {data[:16].hex(' ')}")
    print(f"MPCX MAC         : {target_mac.hex(':')}")
    print(f"EEPROM record    : {record.hex(' ')}")
    print("EEPROM target    : 0xfffffc00..0xfffffc17 (24 bytes)")
    print("NO WRITE PERFORMED")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    info = inspect_file(args.file)
    print(f"file OK : {info.path} ({info.kind}, {info.size} bytes)")
    print(f"sha256  : {info.sha256}")
    print("device compatibility check: NOT IMPLEMENTED")
    return 3


def cmd_write_mpc(args: argparse.Namespace) -> int:
    print("REFUSED: MPC/MPCX EEPROM programming is not enabled in this build.", file=sys.stderr)
    print(
        "Use mpcx-plan to inspect the reconstructed 24-byte SiTCP-XG record without writing.",
        file=sys.stderr,
    )
    return 4


def cmd_eeprom_read(args: argparse.Namespace) -> int:
    c = RbcpClient(args.ip, args.port, args.timeout)
    data = read_extension(c)
    print(data.hex(" "))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    if not args.yes_really_clear:
        print("REFUSED: clear is destructive; add --yes-really-clear", file=sys.stderr)
        return 5
    c = RbcpClient(args.ip, args.port, args.timeout)
    clear_mpc_area(c)
    print("cleared MPC EEPROM area 0xfffffc00..0xfffffc7f")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sitcp-mpc-writer")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("inspect", help="inspect an MPC/MPCX file without writing")
    q.add_argument("file")
    q.add_argument("--preview", type=int, default=32)
    q.set_defaults(func=cmd_inspect)

    q = sub.add_parser("probe", help="verify RBCP connectivity with a harmless read")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--address", type=_int_auto, required=True,
                   help="known safe readable register address, e.g. 0x00000000")
    q.add_argument("--length", type=int, default=1)
    q.add_argument("--timeout", type=float, default=1.0)
    q.set_defaults(func=cmd_probe)

    q = sub.add_parser("rbcp-read", help="raw RBCP read")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--address", type=_int_auto, required=True)
    q.add_argument("--length", type=int, required=True)
    q.add_argument("--timeout", type=float, default=1.0)
    q.set_defaults(func=cmd_rbcp_read)

    q = sub.add_parser("rbcp-write", help="raw RBCP write (expert use)")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--address", type=_int_auto, required=True)
    q.add_argument("--hex-data", required=True)
    q.add_argument("--timeout", type=float, default=1.0)
    q.set_defaults(func=cmd_rbcp_write)

    q = sub.add_parser("eeprom-read", help="read the 64-byte EEPROM extension area reconstructed from official Writer XG")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--timeout", type=float, default=1.0)
    q.set_defaults(func=cmd_eeprom_read)

    q = sub.add_parser("mpcx-plan", help="build the reconstructed 24-byte SiTCP-XG EEPROM record without writing")
    q.add_argument("file")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--timeout", type=float, default=1.0)
    q.set_defaults(func=cmd_mpcx_plan)

    q = sub.add_parser("clear", help="DESTRUCTIVE: reproduce official Clear MPC(X) EEPROM erase sequence")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.add_argument("--timeout", type=float, default=1.0)
    q.add_argument("--yes-really-clear", action="store_true")
    q.set_defaults(func=cmd_clear)

    q = sub.add_parser("check", help="file check; device compatibility pending")
    q.add_argument("file")
    q.add_argument("--ip")
    q.add_argument("--port", type=int, default=4660)
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("write", help="MPC/MPCX write (currently safety-disabled)")
    q.add_argument("file")
    q.add_argument("--ip", required=True)
    q.add_argument("--port", type=int, default=4660)
    q.set_defaults(func=cmd_write_mpc)
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except RbcpError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
