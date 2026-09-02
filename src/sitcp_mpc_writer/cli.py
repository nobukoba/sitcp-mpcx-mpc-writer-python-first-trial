from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .eeprom import clear_mpc_area, read_extension
from .mpc import build_mpcx_eeprom_record, inspect_file
from .rbcp import RbcpClient, RbcpError, RbcpTimeout


def _int_auto(value: str) -> int:
    return int(value, 0)


def _read_with_retry(client, address, length, attempts=3):
    last = None
    for _ in range(attempts):
        try:
            return client.read(address, length)
        except RbcpTimeout as exc:
            last = exc
    raise last


def _read_chunked(client, address, length, chunk_size=8):
    out = bytearray()
    for offset in range(0, length, chunk_size):
        out.extend(
            _read_with_retry(
                client,
                address + offset,
                min(chunk_size, length - offset),
            )
        )
    return bytes(out)


def _read_preserved_mpcx_bytes(client):
    try:
        return _read_with_retry(client, 0xFFFFFC10, 2)
    except RbcpTimeout:
        return _read_with_retry(client, 0xFFFFFC10, 1) + _read_with_retry(
            client, 0xFFFFFC11, 1
        )


def cmd_inspect(args):
    info = inspect_file(args.file, args.preview)
    print(
        f"file    : {info.path}\n"
        f"kind    : {info.kind}\n"
        f"size    : {info.size} bytes\n"
        f"sha256  : {info.sha256}\n"
        f"preview : {info.preview_hex}"
    )
    print(
        f"writer-size-valid : {info.writer_size_valid}\n"
        f"writer-type       : {info.writer_type}\n"
        f"decoded-tag       : {info.decoded_tag}\n"
        f"decoded-tag-hex   : {info.decoded_tag_hex}\n"
        f"alternate-decoded: {info.alternate_decoded_hex}"
    )
    return 0


def cmd_rbcp_read(args):
    data = RbcpClient(args.ip, args.port, args.timeout).read(args.address, args.length)
    print(data.hex(" "))
    return 0


def cmd_rbcp_write(args):
    data = bytes.fromhex(args.hex_data.replace("0x", "").replace(",", " "))
    RbcpClient(args.ip, args.port, args.timeout).write(args.address, data)
    print(f"wrote {len(data)} byte(s) to 0x{args.address:08x}")
    return 0


def cmd_probe(args):
    data = RbcpClient(args.ip, args.port, args.timeout).read(args.address, args.length)
    print(
        f"RBCP reachable: {args.ip}:{args.port}\n"
        f"read 0x{args.address:08x}+{args.length}: {data.hex(' ')}"
    )
    return 0


def cmd_verify(args):
    path = Path(args.file)
    data = path.read_bytes()
    info = inspect_file(path)
    if len(data) != 22 or info.writer_type not in (1, 2):
        print(
            f"ERROR: invalid/unknown 22-byte MPC payload (writer type {info.writer_type})",
            file=sys.stderr,
        )
        return 2

    client = RbcpClient(args.ip, args.port, args.timeout)
    print(
        f"target              : {args.ip}:{args.port}\n"
        f"file                : {path}\n"
        f"writer type         : {info.writer_type}\n"
        f"payload type        : {'SiTCP-XG' if info.writer_type == 1 else 'normal SiTCP'}"
    )

    if info.writer_type == 1:
        preserved = _read_preserved_mpcx_bytes(client)
        expected = build_mpcx_eeprom_record(data, preserved)
        actual = _read_chunked(client, 0xFFFFFC00, 24, 8)
        matched = expected == actual
        print(
            f"preserve FC10..11   : {preserved.hex(' ')}\n"
            f"file MAC            : {data[16:22].hex(':')}\n"
            f"expected FC00..FC17 : {expected.hex(' ')}\n"
            f"EEPROM FC00..FC17   : {actual.hex(' ')}"
        )
    else:
        mac = _read_chunked(client, 0xFFFFFC12, 6, 6)
        block = _read_chunked(client, 0xFFFFFC40, 16, 8)
        mac_ok = data[:6] == mac
        block_ok = data[6:] == block
        matched = mac_ok and block_ok
        print(
            f"file MAC            : {data[:6].hex(':')}\n"
            f"EEPROM FC12..FC17   : {mac.hex(':')}\n"
            f"MAC match           : {'YES' if mac_ok else 'NO'}\n"
            f"file MPC block      : {data[6:].hex(' ')}\n"
            f"EEPROM FC40..FC4F   : {block.hex(' ')}\n"
            f"MPC block match     : {'YES' if block_ok else 'NO'}"
        )

    print(
        f"file matches EEPROM : {'YES' if matched else 'NO'}\n"
        "NO WRITE PERFORMED"
    )
    return 0 if matched else 6


def cmd_mpcx_plan(args):
    path = Path(args.file)
    data = path.read_bytes()
    info = inspect_file(path)
    if len(data) != 22 or info.writer_type != 1:
        print("ERROR: payload is not classified as SiTCP-XG", file=sys.stderr)
        return 2
    client = RbcpClient(args.ip, args.port, args.timeout)
    preserved = _read_preserved_mpcx_bytes(client)
    record = build_mpcx_eeprom_record(data, preserved)
    print(
        f"target            : {args.ip}:{args.port}\n"
        f"file              : {path}\n"
        f"preserve FC10-11  : {preserved.hex(' ')}\n"
        f"EEPROM record     : {record.hex(' ')}\n"
        "NO WRITE PERFORMED"
    )
    return 0


def cmd_read(args):
    data = read_extension(RbcpClient(args.ip, args.port, args.timeout))
    print(data.hex(" "))
    return 0


def cmd_clear(args):
    if not args.yes_really_clear:
        print(
            "REFUSED: clear is destructive; add --yes-really-clear",
            file=sys.stderr,
        )
        return 5
    clear_mpc_area(RbcpClient(args.ip, args.port, args.timeout))
    print("cleared MPC EEPROM area 0xfffffc00..0xfffffc7f")
    return 0


def cmd_write(args):
    path = Path(args.file)
    info = inspect_file(path)
    print(
        f"target       : {args.ip}:{args.port}\n"
        f"file         : {path}\n"
        f"payload type : {info.kind}"
    )
    print(
        "REFUSED: MPC programming is not enabled in this build.",
        file=sys.stderr,
    )
    return 4


def _add_ip(parser, timeout=True):
    parser.add_argument("ip", help="target SiTCP/SiTCP-XG IP address")
    parser.add_argument(
        "--port",
        type=int,
        default=4660,
        help="RBCP UDP port (default: 4660)",
    )
    if timeout:
        parser.add_argument("--timeout", type=float, default=1.0)


def build_writer_parser():
    parser = argparse.ArgumentParser(
        prog="mpcmpcx-writer",
        description="Write an MPC/MPCX file to a target SiTCP/SiTCP-XG device.",
    )
    _add_ip(parser, timeout=False)
    parser.add_argument("file", help="MPC/MPCX file")
    parser.set_defaults(func=cmd_write)
    return parser


def build_reader_parser():
    parser = argparse.ArgumentParser(
        prog="mpcmpcx-reader",
        description="Read the MPC-related EEPROM area from a SiTCP/SiTCP-XG device.",
    )
    _add_ip(parser)
    parser.set_defaults(func=cmd_read)
    return parser


def build_command_parser():
    parser = argparse.ArgumentParser(
        prog="mpcmpcx-command",
        description="Advanced MPC/MPCX inspection, verification, and RBCP commands.",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    q = subparsers.add_parser("inspect", help="inspect an MPC/MPCX file")
    q.add_argument("file")
    q.add_argument("--preview", type=int, default=32)
    q.set_defaults(func=cmd_inspect)

    q = subparsers.add_parser("verify", help="compare an MPC/MPCX file with target EEPROM")
    _add_ip(q)
    q.add_argument("file")
    q.set_defaults(func=cmd_verify)

    q = subparsers.add_parser("read", help="read the MPC-related EEPROM area")
    _add_ip(q)
    q.set_defaults(func=cmd_read)

    q = subparsers.add_parser("probe", help="test RBCP connectivity")
    _add_ip(q)
    q.add_argument("--address", type=_int_auto, required=True)
    q.add_argument("--length", type=int, default=1)
    q.set_defaults(func=cmd_probe)

    q = subparsers.add_parser("rbcp-read", help="expert raw RBCP read")
    _add_ip(q)
    q.add_argument("--address", type=_int_auto, required=True)
    q.add_argument("--length", type=int, required=True)
    q.set_defaults(func=cmd_rbcp_read)

    q = subparsers.add_parser("rbcp-write", help="expert raw RBCP write")
    _add_ip(q)
    q.add_argument("--address", type=_int_auto, required=True)
    q.add_argument("--hex-data", required=True)
    q.set_defaults(func=cmd_rbcp_write)

    q = subparsers.add_parser(
        "mpcx-plan",
        help="legacy/development XG plan command; classification is content-based",
    )
    _add_ip(q)
    q.add_argument("file")
    q.set_defaults(func=cmd_mpcx_plan)

    q = subparsers.add_parser("clear", help="destructively clear MPC EEPROM area")
    _add_ip(q)
    q.add_argument("--yes-really-clear", action="store_true")
    q.set_defaults(func=cmd_clear)

    return parser


def _run(parser, argv=None):
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RbcpError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def main_writer(argv=None):
    return _run(build_writer_parser(), argv)


def main_reader(argv=None):
    return _run(build_reader_parser(), argv)


def main_command(argv=None):
    return _run(build_command_parser(), argv)


def main(argv=None):
    return main_command(argv)


if __name__ == "__main__":
    raise SystemExit(main_command())
