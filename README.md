# sitcp-mpcx-mpc-writer-python-first-trial

Experimental cross-platform Python CLI for inspecting and eventually writing SiTCP / SiTCP-XG MPC data from macOS, Linux, WSL, and Docker without using the official Windows GUI.

The command name is **`mpcx-mpc-writer`**.

The intended normal operation is deliberately simple:

```bash
./mpcx-mpc-writer 192.168.2.169 2F20880E82.mpcx
```

The first argument is the target IP address and the second is the MPC/MPCX file. RBCP UDP port `4660` is used by default, so it normally does not need to be written on the command line.

The important design rule is that **SiTCP versus SiTCP-XG is determined from the 22-byte file payload, not from the filename extension**. An SiTCP-XG file may therefore be named `.mpc`; `.mpcx` is not required for detection.

The current implementation can inspect MPC files, classify the payload using the same two decode paths reconstructed from the official Writer, communicate with SiTCP over RBCP, and verify the known EEPROM mappings on normal SiTCP and SiTCP-XG. High-level MPC programming is still intentionally disabled, so the default `IP FILE` command currently reports the planned target/file and refuses the actual write.

## Where the format information comes from

This project uses three evidence sources and keeps them separate:

1. **Public Bee Beans Technologies documentation** — documents SiTCP/SiTCP-XG, RBCP-accessible internal/EEPROM areas, EEPROM write protection, and operation of the official MPC Writer.
2. **Static analysis of the official `SiTcpMpcWriteXG.exe`** — recovered details not found in the reviewed public manuals, including the exact 22-byte length check, content classifier, RBCP packet handling, and XG record construction.
3. **Read-only tests with matching real MPC files and hardware** — confirmed the normal-SiTCP and SiTCP-XG file-to-EEPROM mappings.

Public references include:

- SiTCP / SiTCP-XG downloads and manuals: https://www.bbtech.co.jp/download-files/sitcp/index_en.html
- SiTCP MPC Writer XG guide: https://www.bbtech.co.jp/download-files/sitcp/SiTCP-MPC-Writer-XG-en.0.1.1.pdf
- Bee Beans Technologies `sitcpy`: https://github.com/BeeBeansTechnologies/sitcpy
- SiTCP Forum: https://sitcp.bbtech.co.jp/

The public MPC Writer guide states that an MPCX file contains the SiTCP-XG global MAC address and license information and is written to EEPROM. However, the reviewed public documentation does **not** describe the complete byte-level 22-byte MPC payload format or the Writer's two-path content classifier. Those details were reconstructed from the Writer and checked against real hardware.

See `REVERSE_ENGINEERING.md` for an evidence-by-evidence table.

## How to use

No `pip install` is required for normal use:

```bash
git clone https://github.com/nobukoba/sitcp-mpcx-mpc-writer-python-first-trial.git
cd sitcp-mpcx-mpc-writer-python-first-trial
chmod +x mpcx-mpc-writer
./mpcx-mpc-writer --help
```

### Write an MPC/MPCX file

The main interface is:

```bash
./mpcx-mpc-writer DEVICE_IP FILE
```

For example:

```bash
./mpcx-mpc-writer 192.168.2.169 2F20880E82.mpcx
```

or, for a normal SiTCP device:

```bash
./mpcx-mpc-writer 192.168.2.161 2F20880E6E.mpc
```

The file extension is not used to decide whether the payload is SiTCP or SiTCP-XG.

**Actual MPC programming is still disabled in the current build.** The command is already reserved as the final write interface so that the user-facing syntax will not need to change when programming is enabled.

### Verify a file against a device

```bash
./mpcx-mpc-writer verify 192.168.2.169 2F20880E82.mpcx
```

or:

```bash
./mpcx-mpc-writer verify 192.168.2.161 2F20880E6E.mpc
```

The command classifies the 22-byte payload and selects the corresponding verified EEPROM mapping. No write is performed.

Normal SiTCP mapping confirmed with a matching real device/file pair:

```text
file[0:6]   -> EEPROM 0xFFFFFC12..0xFFFFFC17
file[6:22]  -> EEPROM 0xFFFFFC40..0xFFFFFC4F
```

SiTCP-XG mapping confirmed with a matching real device/file pair and static analysis of the official Writer:

```text
file[0:16]  -> EEPROM 0xFFFFFC00..0xFFFFFC0F
FC10..FC11  -> preserved current device bytes
file[16:22] -> EEPROM 0xFFFFFC12..0xFFFFFC17
```

A successful verification ends with:

```text
file matches EEPROM : YES
NO WRITE PERFORMED
```

### Read MPC-related EEPROM data

```bash
./mpcx-mpc-writer read 192.168.2.169
```

`read` replaces the older development-style `eeprom-read` command name.

### Inspect a file without hardware

```bash
./mpcx-mpc-writer inspect 2F20880E82.mpcx
```

The classifier reproduces the official Writer's two decode paths:

```text
writer type 1 -> SiTCP-XG payload
writer type 2 -> normal SiTCP payload
```

### Check RBCP connectivity

```bash
./mpcx-mpc-writer probe 192.168.10.10 \
  --address 0x00000000
```

### Expert raw RBCP access

```bash
./mpcx-mpc-writer rbcp-read 192.168.10.10 \
  --address 0x00000000 \
  --length 16
```

```bash
./mpcx-mpc-writer rbcp-write 192.168.10.10 \
  --address 0x12345678 \
  --hex-data "01 02 03 04"
```

These are development/debug commands rather than the normal MPC Writer interface.

### Clear the MPC EEPROM area

**This command is destructive.**

The reconstructed official sequence enables EEPROM writing with `0xFFFFFCFF <- 0x00`, writes `0xFF` over `0xFFFFFC00..0xFFFFFC7F` in 16-byte blocks, and disables writing with `0xFFFFFCFF <- 0xFF`.

```bash
./mpcx-mpc-writer clear 192.168.10.10 --yes-really-clear
```

Do not run this on a device whose MPC/EEPROM contents must be preserved.

### Non-default RBCP port

Port `4660` is used automatically. Specify `--port` only when the target uses another RBCP port:

```bash
./mpcx-mpc-writer verify 192.168.2.169 2F20880E82.mpcx --port 5000
```

## Command summary

```text
mpcx-mpc-writer IP FILE              write MPC/MPCX (currently safety-disabled)
mpcx-mpc-writer verify IP FILE       compare file with target EEPROM
mpcx-mpc-writer read IP              read MPC-related EEPROM area
mpcx-mpc-writer inspect FILE         inspect/classify file only
```

Advanced/debug commands remain available as `probe`, `rbcp-read`, `rbcp-write`, `mpcx-plan`, and `clear`.

## Optional virtual-environment installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
mpcx-mpc-writer --help
```

Do not use `sudo pip install` or `--break-system-packages` for this repository.

## Docker

```bash
docker build -t sitcp-mpcx-mpc-writer-python-first-trial .
```

Inspect a local file:

```bash
docker run --rm \
  -v "$PWD:/work" \
  sitcp-mpcx-mpc-writer-python-first-trial \
  inspect /work/device.mpc
```

Docker Desktop networking on macOS differs from native Linux host networking. For initial hardware tests on a Mac, running the Python CLI directly on macOS is the simplest path.

## Repository layout

```text
.
├── mpcx-mpc-writer
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

## For Developers

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The project intentionally has no third-party runtime Python dependencies.

Keep the high-level workflow safe:

```text
classify file payload
    ↓
detect/check target device compatibility
    ↓
read and preserve current EEPROM state
    ↓
construct exact EEPROM writes
    ↓
explicit write operation
    ↓
read-back verification
    ↓
disable EEPROM write access
```

Do not enable the high-level write operation until the remaining compatibility and write-sequence checks are verified.

The official executable, proprietary libraries, and user-specific MPC files are **not** included in this repository.
