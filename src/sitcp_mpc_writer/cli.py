from __future__ import annotations
import argparse
from pathlib import Path
import sys
from .mpc import inspect_file, build_mpcx_eeprom_record
from .rbcp import RbcpClient, RbcpError, RbcpTimeout
from .eeprom import read_extension, clear_mpc_area

def _int_auto(value: str) -> int: return int(value, 0)

def _read_with_retry(c, address, length, attempts=3):
    last=None
    for _ in range(attempts):
        try: return c.read(address,length)
        except RbcpTimeout as exc: last=exc
    raise last

def _read_chunked(c,address,length,chunk_size=8):
    out=bytearray()
    for off in range(0,length,chunk_size):
        out.extend(_read_with_retry(c,address+off,min(chunk_size,length-off)))
    return bytes(out)

def _read_preserved_mpcx_bytes(c):
    try: return _read_with_retry(c,0xFFFFFC10,2)
    except RbcpTimeout:
        return _read_with_retry(c,0xFFFFFC10,1)+_read_with_retry(c,0xFFFFFC11,1)

def cmd_inspect(args):
    i=inspect_file(args.file,args.preview)
    print(f"file    : {i.path}\nkind    : {i.kind}\nsize    : {i.size} bytes\nsha256  : {i.sha256}\npreview : {i.preview_hex}")
    print(f"writer-size-valid : {i.writer_size_valid}\nwriter-type       : {i.writer_type}\ndecoded-tag       : {i.decoded_tag}\ndecoded-tag-hex   : {i.decoded_tag_hex}\nalternate-decoded: {i.alternate_decoded_hex}")
    return 0

def cmd_rbcp_read(a):
    print(RbcpClient(a.ip,a.port,a.timeout).read(a.address,a.length).hex(' ')); return 0

def cmd_rbcp_write(a):
    data=bytes.fromhex(a.hex_data.replace('0x','').replace(',',' ')); RbcpClient(a.ip,a.port,a.timeout).write(a.address,data); print(f"wrote {len(data)} byte(s) to 0x{a.address:08x}"); return 0

def cmd_probe(a):
    d=RbcpClient(a.ip,a.port,a.timeout).read(a.address,a.length); print(f"RBCP reachable: {a.ip}:{a.port}\nread 0x{a.address:08x}+{a.length}: {d.hex(' ')}"); return 0

def cmd_verify(a):
    p=Path(a.file); data=p.read_bytes(); info=inspect_file(p)
    if len(data)!=22 or info.writer_type not in (1,2):
        print(f"ERROR: invalid/unknown 22-byte MPC payload (writer type {info.writer_type})",file=sys.stderr); return 2
    c=RbcpClient(a.ip,a.port,a.timeout)
    print(f"file                : {p}\nwriter type         : {info.writer_type}\ndetected device     : {'SiTCP-XG' if info.writer_type==1 else 'normal SiTCP'}")
    if info.writer_type==1:
        preserved=_read_preserved_mpcx_bytes(c); expected=build_mpcx_eeprom_record(data,preserved)
        actual=_read_chunked(c,0xFFFFFC00,24,8); matched=expected==actual
        print(f"preserve FC10..11   : {preserved.hex(' ')}\nfile MAC            : {data[16:22].hex(':')}\nexpected FC00..FC17 : {expected.hex(' ')}\nEEPROM FC00..FC17   : {actual.hex(' ')}")
    else:
        mac=_read_chunked(c,0xFFFFFC12,6,6); block=_read_chunked(c,0xFFFFFC40,16,8)
        mac_ok=data[:6]==mac; block_ok=data[6:]==block; matched=mac_ok and block_ok
        print(f"file MAC            : {data[:6].hex(':')}\nEEPROM FC12..FC17   : {mac.hex(':')}\nMAC match           : {'YES' if mac_ok else 'NO'}\nfile MPC block      : {data[6:].hex(' ')}\nEEPROM FC40..FC4F   : {block.hex(' ')}\nMPC block match     : {'YES' if block_ok else 'NO'}")
    print(f"file matches EEPROM : {'YES' if matched else 'NO'}\nNO WRITE PERFORMED")
    return 0 if matched else 6

def cmd_mpcx_plan(a):
    p=Path(a.file); data=p.read_bytes(); info=inspect_file(p)
    if len(data)!=22 or info.writer_type!=1: print('ERROR: payload is not classified as SiTCP-XG',file=sys.stderr); return 2
    c=RbcpClient(a.ip,a.port,a.timeout); preserved=_read_preserved_mpcx_bytes(c); record=build_mpcx_eeprom_record(data,preserved)
    print(f"file              : {p}\npreserve FC10-11  : {preserved.hex(' ')}\nEEPROM record     : {record.hex(' ')}\nNO WRITE PERFORMED"); return 0

def cmd_eeprom_read(a): print(read_extension(RbcpClient(a.ip,a.port,a.timeout)).hex(' ')); return 0

def cmd_clear(a):
    if not a.yes_really_clear: print('REFUSED: clear is destructive; add --yes-really-clear',file=sys.stderr); return 5
    clear_mpc_area(RbcpClient(a.ip,a.port,a.timeout)); print('cleared MPC EEPROM area 0xfffffc00..0xfffffc7f'); return 0

def cmd_write(a): print('REFUSED: MPC programming is not enabled in this build.',file=sys.stderr); return 4

def _netargs(q, timeout=True):
    q.add_argument('--ip',required=True); q.add_argument('--port',type=int,default=4660)
    if timeout: q.add_argument('--timeout',type=float,default=1.0)

def build_parser():
    p=argparse.ArgumentParser(prog='sitcp-mpc-writer'); s=p.add_subparsers(dest='cmd',required=True)
    q=s.add_parser('inspect'); q.add_argument('file'); q.add_argument('--preview',type=int,default=32); q.set_defaults(func=cmd_inspect)
    q=s.add_parser('verify',help='auto-detect normal SiTCP vs SiTCP-XG from 22-byte payload and verify EEPROM'); q.add_argument('file'); _netargs(q); q.set_defaults(func=cmd_verify)
    q=s.add_parser('probe'); _netargs(q); q.add_argument('--address',type=_int_auto,required=True); q.add_argument('--length',type=int,default=1); q.set_defaults(func=cmd_probe)
    q=s.add_parser('rbcp-read'); _netargs(q); q.add_argument('--address',type=_int_auto,required=True); q.add_argument('--length',type=int,required=True); q.set_defaults(func=cmd_rbcp_read)
    q=s.add_parser('rbcp-write'); _netargs(q); q.add_argument('--address',type=_int_auto,required=True); q.add_argument('--hex-data',required=True); q.set_defaults(func=cmd_rbcp_write)
    q=s.add_parser('eeprom-read'); _netargs(q); q.set_defaults(func=cmd_eeprom_read)
    q=s.add_parser('mpcx-plan',help='legacy/development XG plan command; classification is content-based'); q.add_argument('file'); _netargs(q); q.set_defaults(func=cmd_mpcx_plan)
    q=s.add_parser('clear'); _netargs(q); q.add_argument('--yes-really-clear',action='store_true'); q.set_defaults(func=cmd_clear)
    q=s.add_parser('write'); q.add_argument('file'); _netargs(q,False); q.set_defaults(func=cmd_write)
    return p

def main():
    a=build_parser().parse_args()
    try: return a.func(a)
    except (RbcpError,ValueError) as exc: print(f"ERROR: {exc}",file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
