# sitcp-mpcx-mpc-writer-python-first-trial

Experimental cross-platform Python CLI for inspecting, reading, verifying, and writing SiTCP / SiTCP-XG MPC data from macOS, Linux, WSL, and Docker without using the official Windows GUI.

The user-facing commands are split by purpose:

```text
mpc-mpcx-writer  IP FILE
mpc-mpcx-reader  IP
mpc-mpcx-command COMMAND ...
```

RBCP UDP port `4660` is used by default, so it normally does not need to be written on the command line.

The important design rule is that **SiTCP versus SiTCP-XG is determined from the 22-byte file payload, not from the filename extension**. An SiTCP-XG file may therefore be named `.mpc`; `.mpcx` is not required for detection.

## How to use

No `pip install` is required for normal use:

```bash
git clone https://github.com/nobukoba/sitcp-mpcx-mpc-writer-python-first-trial.git
cd sitcp-mpcx-mpc-writer-python-first-trial
chmod +x mpc-mpcx-writer mpc-mpcx-reader mpc-mpcx-command
```

Running any of the three commands without arguments prints its help text.

### Write an MPC/MPCX file

```bash
./mpc-mpcx-writer 192.168.2.169 2F20880E82.mpcx
```

or, for a normal SiTCP device:

```bash
./mpc-mpcx-writer 192.168.2.161 2F20880E6E.mpc
```

The first argument is the target IP address and the second is the MPC/MPCX file. The file extension is not used to decide whether the payload is SiTCP or SiTCP-XG.

`mpc-mpcx-writer` now performs actual EEPROM programming. The sequence is:

```text
classify 22-byte MPC/MPCX payload
    ↓
read current EEPROM bytes that must be preserved
    ↓
enable EEPROM writes (0xFFFFFCFF <- 0x00)
    ↓
write EEPROM in 16-byte RBCP transactions
    ↓
disable EEPROM writes (0xFFFFFCFF <- 0xFF)
    ↓
read back EEPROM and verify byte-for-byte
```

Write transactions are deliberately **not automatically retried**. A lost UDP ACK does not prove that an EEPROM write failed, so blindly repeating a write is avoided.

For SiTCP-XG, the 24-byte EEPROM record is constructed as:

```text
file[0:16]   -> EEPROM 0xFFFFFC00..0xFFFFFC0F
FC10..FC11   -> preserve current EEPROM values
file[16:22]  -> EEPROM 0xFFFFFC12..0xFFFFFC17
```

For normal SiTCP, the current `0xFFFFFC00..0xFFFFFC4F` image is read first and preserved except for:

```text
file[0:6]   -> EEPROM 0xFFFFFC12..0xFFFFFC17
file[6:22]  -> EEPROM 0xFFFFFC40..0xFFFFFC4F
```

A successful write ends with:

```text
WRITE OK
READ-BACK VERIFY OK
EEPROM WRITE DISABLED
```

### Read MPC-related EEPROM data

```bash
./mpc-mpcx-reader 192.168.2.169
```

This is the normal read-only command. No MPC/MPCX file is required.

### Advanced commands

Detailed inspection, verification, and RBCP operations are collected under `mpc-mpcx-command`.

Verify a file against a device without writing:

```bash
./mpc-mpcx-command verify 192.168.2.169 2F20880E82.mpcx
```

Inspect a file without hardware:

```bash
./mpc-mpcx-command inspect 2F20880E82.mpcx
```

Check RBCP connectivity:

```bash
./mpc-mpcx-command probe 192.168.10.10 \
  --address 0x00000000
```

Expert raw RBCP read:

```bash
./mpc-mpcx-command rbcp-read 192.168.10.10 \
  --address 0x00000000 \
  --length 16
```

Expert raw RBCP write:

```bash
./mpc-mpcx-command rbcp-write 192.168.10.10 \
  --address 0x12345678 \
  --hex-data "01 02 03 04"
```

Clear the MPC EEPROM area:

```bash
./mpc-mpcx-command clear 192.168.10.10 --yes-really-clear
```

**`clear` is destructive.**

### Non-default RBCP port / timeout

Port `4660` is used automatically. Specify `--port` only when the target uses another RBCP port. The writer also accepts `--timeout`:

```bash
./mpc-mpcx-writer 192.168.2.169 2F20880E82.mpcx --timeout 3
```

## Where the format information comes from

This project uses three evidence sources and keeps them separate:

1. **Public Bee Beans Technologies documentation** — documents SiTCP/SiTCP-XG, RBCP-accessible internal/EEPROM areas, EEPROM write protection, and operation of the official MPC Writer.
2. **Static analysis of the official `SiTcpMpcWriteXG.exe`** — recovered details not found in the reviewed public manuals, including the exact 22-byte length check, content classifier, RBCP packet handling, and XG record construction.
3. **Tests with matching real MPC files and hardware** — confirmed the normal-SiTCP and SiTCP-XG file-to-EEPROM mappings used here.

Public references include:

- SiTCP / SiTCP-XG downloads and manuals: https://www.bbtech.co.jp/download-files/sitcp/index_en.html
- SiTCP MPC Writer XG guide: https://www.bbtech.co.jp/download-files/sitcp/SiTCP-MPC-Writer-XG-en.0.1.1.pdf
- Bee Beans Technologies `sitcpy`: https://github.com/BeeBeansTechnologies/sitcpy
- SiTCP Forum: https://sitcp.bbtech.co.jp/

The public MPC Writer guide states that an MPCX file contains the SiTCP-XG global MAC address and license information and is written to EEPROM. The reviewed public documentation does not describe the complete byte-level 22-byte MPC payload format or the Writer's two-path content classifier; those details were reconstructed from the Writer and checked against real hardware.

See `REVERSE_ENGINEERING.md` for details.

## Command summary

```text
mpc-mpcx-writer IP FILE                 write MPC/MPCX and verify by read-back
mpc-mpcx-reader IP                      read MPC-related EEPROM area
mpc-mpcx-command verify IP FILE         compare file with target EEPROM
mpc-mpcx-command inspect FILE           inspect/classify a file
mpc-mpcx-command probe IP ...           test RBCP connectivity
mpc-mpcx-command rbcp-read IP ...       expert raw RBCP read
mpc-mpcx-command rbcp-write IP ...      expert raw RBCP write
```

## Optional virtual-environment installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
mpc-mpcx-writer --help
mpc-mpcx-reader --help
mpc-mpcx-command --help
```

The project intentionally has no third-party runtime Python dependencies.

## Docker

```bash
docker build -t sitcp-mpcx-mpc-writer-python-first-trial .
```

Docker Desktop networking on macOS differs from native Linux host networking. For initial hardware tests on a Mac, running the Python CLI directly on macOS is the simplest path.

## Repository layout

```text
.
├── mpc-mpcx-writer
├── mpc-mpcx-reader
├── mpc-mpcx-command
├── Dockerfile
├── README.md
├── REVERSE_ENGINEERING.md
├── pyproject.toml
├── src/
│   └── sitcp_mpc_writer/
│       ├── __init__.py
│       ├── cli.py
│       ├── eeprom.py
│       ├── mpc.py
│       └── rbcp.py
└── tests/
    └── test_rbcp.py
```

The official executable, proprietary libraries, and user-specific MPC files are **not** included in this repository.
