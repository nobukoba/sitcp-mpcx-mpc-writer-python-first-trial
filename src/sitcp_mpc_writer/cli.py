from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .eeprom import clear_mpc_area, program_mpc_payload
from .mpc import (
    build_mpcx_eeprom_record,
    detect_eeprom_payload_type,
    inspect_file,
    payload_type_name,
)
from .rbcp import RbcpClient, RbcpError, RbcpTimeout


FIELD_WIDTH = 20
DEFAULT_TIMEOUT = 3.0
EEPROM_BASE = 0xFFFFFC00
EEPROM_READ_SIZE = 0x50


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
        out.extend(_read_with_retry(client, address + offset, min(chunk_size, length - offset)))
    return bytes(out)


def _read_preserved_mpcx_bytes(client):
    try:
        return _read_with_retry(client, 0xFFFFFC10, 2)
    except RbcpTimeout:
        return _read_with_retry(client, 0xFFFFFC10, 1) + _read_with_retry(client, 0xFFFFFC11, 1)


def _read_detection_image(client):
    return _read_chunked(client, EEPROM_BASE, EEPROM_READ_SIZE, 8)


def _format_ipv4(data: bytes) -> str:
    return ".".join(str(value) for value in data)


def _format_eeprom_rows(data: bytes, base: int, row_size: int = 16) -> str:
    rows = []
    for offset in range(0, len(data), row_size):
        rows.append(f"{base + offset:08X}: {data[offset:offset + row_size].hex(' ')}")
    return "\n".join(rows)


def _print_fields(*rows):
    for key, value in rows:
        print(f"{key:<{FIELD_WIDTH}}: {value}")


def _print_raw(title: str, data: bytes, base: int, row_size: int = 16):
    print(f"{title}:")
    print(_format_eeprom_rows(data, base, row_size))


def cmd_inspect(args):
    info = inspect_file(args.file, args.preview)
    _print_fields(
        ("command", "inspect"),
        ("file", info.path),
        ("payload type", payload_type_name(info.writer_type)),
        ("size", f"{info.size} bytes"),
        ("writer type", info.writer_type),
        ("writer size valid", info.writer_size_valid),
        ("decoded tag", info.decoded_tag),
        ("decoded tag hex", info.decoded_tag_hex),
        ("alternate decoded", info.alternate_decoded_hex),
        ("sha256", info.sha256),
        ("preview", info.preview_hex),
    )
    return 0


def cmd_rbcp_read(args):
    data = RbcpClient(args.ip, args.port, args.timeout).read(args.address, args.length)
    _print_fields(
        ("command", "rbcp-read"),
        ("target", f"{args.ip}:{args.port}"),
        ("address", f"0x{args.address:08x}"),
        ("length", f"{args.length} byte(s)"),
        ("data", data.hex(" ")),
    )
    return 0


def cmd_rbcp_write(args):
    data = bytes.fromhex(args.hex_data.replace("0x", "").replace(",", " "))
    RbcpClient(args.ip, args.port, args.timeout).write(args.address, data)
    _print_fields(
        ("command", "rbcp-write"),
        ("target", f"{args.ip}:{args.port}"),
        ("address", f"0x{args.address:08x}"),
        ("length", f"{len(data)} byte(s)"),
        ("data", data.hex(" ")),
        ("status", "WRITE OK"),
    )
    return 0


def cmd_probe(args):
    data = RbcpClient(args.ip, args.port, args.timeout).read(args.address, args.length)
    _print_fields(
        ("command", "probe"),
        ("target", f"{args.ip}:{args.port}"),
        ("address", f"0x{args.address:08x}"),
        ("length", f"{args.length} byte(s)"),
        ("data", data.hex(" ")),
        ("status", "RBCP REACHABLE"),
    )
    return 0


def cmd_verify(args):
    path = Path(args.file)
    data = path.read_bytes()
    info = inspect_file(path)
    if len(data) != 22 or info.writer_type not in (1, 2):
        print(f"ERROR: invalid/unknown 22-byte MPC payload (writer type {info.writer_type})", file=sys.stderr)
        return 2

    client = RbcpClient(args.ip, args.port, args.timeout)
    eeprom = _read_detection_image(client)
    device_type, _ = detect_eeprom_payload_type(eeprom)
    _print_fields(
        ("command", "verify"),
        ("target", f"{args.ip}:{args.port}"),
        ("file", path),
        ("file type", payload_type_name(info.writer_type)),
        ("target type", payload_type_name(device_type)),
        ("writer type", info.writer_type),
    )

    if device_type in (1, 2) and device_type != info.writer_type:
        _print_fields(("match", "NO"), ("status", "TARGET TYPE MISMATCH"))
        return 7

    if info.writer_type == 1:
        preserved = eeprom[0x10:0x12]
        expected = build_mpcx_eeprom_record(data, preserved)
        actual = eeprom[0:24]
        matched = expected == actual
        _print_fields(
            ("preserved FC10..FC11", preserved.hex(" ")),
            ("file MAC", data[16:22].hex(":")),
            ("expected FC00..FC17", expected.hex(" ")),
            ("EEPROM FC00..FC17", actual.hex(" ")),
            ("match", "YES" if matched else "NO"),
            ("status", "VERIFY OK" if matched else "VERIFY FAILED"),
        )
    else:
        mac = eeprom[0x12:0x18]
        block = eeprom[0x40:0x50]
        mac_ok = data[:6] == mac
        block_ok = data[6:] == block
        matched = mac_ok and block_ok
        _print_fields(
            ("file MAC", data[:6].hex(":")),
            ("EEPROM MAC", mac.hex(":")),
            ("MAC match", "YES" if mac_ok else "NO"),
            ("file MPC block", data[6:].hex(" ")),
            ("EEPROM MPC block", block.hex(" ")),
            ("MPC block match", "YES" if block_ok else "NO"),
            ("match", "YES" if matched else "NO"),
            ("status", "VERIFY OK" if matched else "VERIFY FAILED"),
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
    _print_fields(
        ("command", "mpcx-plan"),
        ("target", f"{args.ip}:{args.port}"),
        ("file", path),
        ("payload type", payload_type_name(info.writer_type)),
        ("preserved FC10..FC11", preserved.hex(" ")),
        ("EEPROM record", record.hex(" ")),
        ("status", "NO WRITE PERFORMED"),
    )
    return 0


def cmd_read(args):
    client = RbcpClient(args.ip, args.port, args.timeout)
    eeprom = _read_detection_image(client)
    detected_type, detected_payload = detect_eeprom_payload_type(eeprom)
    data = eeprom[0x10:0x50]
    mac = data[0x02:0x08]
    ip = data[0x08:0x0C]
    tcp_port = int.from_bytes(data[0x0C:0x0E], "big")
    mss = int.from_bytes(data[0x10:0x12], "big")
    udp_port = int.from_bytes(data[0x12:0x14], "big")

    rows = [
        ("command", "read"),
        ("target", f"{args.ip}:{args.port}"),
        ("detected type", payload_type_name(detected_type)),
        ("MAC", mac.hex(":")),
        ("IP", _format_ipv4(ip)),
        ("TCP port", tcp_port),
        ("MSS", mss),
        ("RBCP UDP port", udp_port),
        ("FC10..FC11", data[0:2].hex(" ")),
    ]
    if detected_payload is not None:
        rows.append(("reconstructed payload", detected_payload.hex(" ")))
    if detected_type == 1:
        rows.append(("MPCX FC00..FC0F", eeprom[0:16].hex(" ")))
    elif detected_type == 2:
        rows.append(("MPC FC40..FC4F", eeprom[0x40:0x50].hex(" ")))
    rows.append(("status", "READ OK"))
    _print_fields(*rows)
    _print_raw("raw EEPROM FC00..FC4F", eeprom, EEPROM_BASE)
    return 0


def cmd_clear(args):
    if not args.yes_really_clear:
        print("REFUSED: clear is destructive; add --yes-really-clear", file=sys.stderr)
        return 5
    clear_mpc_area(RbcpClient(args.ip, args.port, args.timeout))
    _print_fields(
        ("command", "clear"),
        ("target", f"{args.ip}:{args.port}"),
        ("EEPROM area", "0xFFFFFC00..0xFFFFFC7F"),
        ("status", "CLEAR OK"),
    )
    return 0


def cmd_write(args):
    path = Path(args.file)
    payload = path.read_bytes()
    info = inspect_file(path)
    if len(payload) != 22 or info.writer_type not in (1, 2):
        print(f"ERROR: invalid/unknown 22-byte MPC payload (writer type {info.writer_type})", file=sys.stderr)
        return 2

    client = RbcpClient(args.ip, args.port, args.timeout)
    eeprom = _read_detection_image(client)
    device_type, _ = detect_eeprom_payload_type(eeprom)

    _print_fields(
        ("command", "write"),
        ("target", f"{args.ip}:{args.port}"),
        ("file", path),
        ("file type", payload_type_name(info.writer_type)),
        ("target type", payload_type_name(device_type)),
        ("writer type", info.writer_type),
        ("file payload", payload.hex(" ")),
    )

    if device_type in (1, 2) and device_type != info.writer_type:
        _print_fields(("status", "REFUSED: TARGET TYPE MISMATCH"))
        return 7
    if device_type not in (1, 2):
        _print_fields(("status", "REFUSED: TARGET TYPE NOT DETECTED"))
        return 7

    _print_fields(("operation", "programming EEPROM"))
    readback = program_mpc_payload(client, payload, info.writer_type)

    if info.writer_type == 1:
        _print_fields(
            ("preserved FC10..FC11", readback[16:18].hex(" ")),
            ("read-back FC00..FC17", readback.hex(" ")),
            ("read-back MAC", readback[18:24].hex(":")),
            ("write", "OK"),
            ("read-back verify", "OK"),
            ("EEPROM write protect", "ENABLED"),
            ("status", "WRITE OK"),
        )
    else:
        _print_fields(
            ("read-back MAC", readback[0x12:0x18].hex(":")),
            ("read-back FC40..FC4F", readback[0x40:0x50].hex(" ")),
            ("write", "OK"),
            ("read-back verify", "OK"),
            ("EEPROM write protect", "ENABLED"),
            ("status", "WRITE OK"),
        )
    return 0


def _add_ip(parser, timeout=True):
    parser.add_argument("ip", help="target SiTCP/SiTCP-XG IP address")
    parser.add_argument("--port", type=int, default=4660, help="RBCP UDP port (default: 4660)")
    if timeout:
        parser.add_argument(
            "--timeout",
            type=float,
            default=DEFAULT_TIMEOUT,
            help=f"RBCP timeout in seconds (default: {DEFAULT_TIMEOUT:g})",
        )


def build_writer_parser():
    parser = argparse.ArgumentParser(
        prog="mpc-mpcx-writer",
        description="Auto-detect MPC/MPCX, write to a compatible target, and verify by read-back.",
    )
    _add_ip(parser)
    parser.add_argument("file", help="MPC/MPCX file")
    parser.set_defaults(func=cmd_write)
    return parser


def build_reader_parser():
    parser = argparse.ArgumentParser(
        prog="mpc-mpcx-reader",
        description="Auto-detect MPC/MPCX and read/decode the target EEPROM.",
    )
    _add_ip(parser)
    parser.set_defaults(func=cmd_read)
    return parser


def build_command_parser():
    parser = argparse.ArgumentParser(
        prog="mpc-mpcx-command",
        description="Advanced MPC/MPCX inspection, verification, and RBCP commands.",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    q = subparsers.add_parser("inspect", help="inspect and auto-classify an MPC/MPCX file")
    q.add_argument("file")
    q.add_argument("--preview", type=int, default=32)
    q.set_defaults(func=cmd_inspect)

    q = subparsers.add_parser("verify", help="auto-detect and compare an MPC/MPCX file with target EEPROM")
    _add_ip(q)
    q.add_argument("file")
    q.set_defaults(func=cmd_verify)

    q = subparsers.add_parser("read", help="auto-detect and decode the MPC-related EEPROM area")
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
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RbcpError, RuntimeError, ValueError) as exc:
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
