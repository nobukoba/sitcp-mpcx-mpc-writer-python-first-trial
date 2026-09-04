# sitcp-mpcx-mpc-writer-python-first-trial

Experimental cross-platform Python CLI for inspecting, reading, verifying, and writing SiTCP / SiTCP-XG MPC data from macOS, Linux, WSL, and Docker without using the official Windows GUI.

This project is intended only for interoperability with legitimately obtained SiTCP / SiTCP-XG hardware and MPC/MPCX files. It does **not** generate, modify, or bypass SiTCP licenses.

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

`mpc-mpcx-writer` performs EEPROM programming and read-back verification. Write transactions are deliberately **not automatically retried**: a lost UDP ACK does not prove that an EEPROM write failed, so blindly repeating a write is avoided.

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

```bash
./mpc-mpcx-command verify 192.168.2.169 2F20880E82.mpcx
./mpc-mpcx-command inspect 2F20880E82.mpcx
./mpc-mpcx-command probe 192.168.10.10 --address 0x00000000
./mpc-mpcx-command rbcp-read 192.168.10.10 --address 0x00000000 --length 16
./mpc-mpcx-command rbcp-write 192.168.10.10 --address 0x12345678 --hex-data "01 02 03 04"
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

## Basis of the implementation

The implementation was developed for cross-platform interoperability using:

- publicly available Bee Beans Technologies SiTCP / SiTCP-XG documentation and software;
- behavior and compatibility analysis of the official Windows MPC Writer;
- verification with legitimately obtained MPC/MPCX files and corresponding hardware.

Public references include:

- SiTCP / SiTCP-XG downloads and manuals: https://www.bbtech.co.jp/download-files/sitcp/index_en.html
- SiTCP MPC Writer XG guide: https://www.bbtech.co.jp/download-files/sitcp/SiTCP-MPC-Writer-XG-en.0.1.1.pdf
- Bee Beans Technologies `sitcpy`: https://github.com/BeeBeansTechnologies/sitcpy
- SiTCP Forum: https://sitcp.bbtech.co.jp/

The project contains no official executable, proprietary library, or user-specific MPC/MPCX file. Users must obtain any required SiTCP license data through the legitimate Bee Beans Technologies process. This project only transfers already-authorized data to compatible hardware; it does not create license data or circumvent licensing checks.

For byte-level format, EEPROM mapping, RBCP behavior, and information sufficient for an independent compatible implementation, see `IMPLEMENTATION_NOTES.md`.

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
├── IMPLEMENTATION_NOTES.md
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
