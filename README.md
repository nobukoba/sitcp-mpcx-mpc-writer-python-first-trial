# sitcp-mpcx-mpc-writer-python-first-trial

Experimental cross-platform Python CLI for inspecting and eventually writing SiTCP / SiTCP-XG MPC data from macOS, Linux, WSL, and Docker without using the official Windows GUI.

The important design rule is that **SiTCP versus SiTCP-XG is determined from the 22-byte file payload, not from the filename extension**. An SiTCP-XG file may therefore be named `.mpc`; `.mpcx` is not required for detection.

The current implementation can inspect MPC files, classify the payload using the same two decode paths reconstructed from the official Writer, communicate with SiTCP over RBCP, verify known EEPROM mappings on normal SiTCP and SiTCP-XG, read the reconstructed EEPROM extension area, and reproduce the official `Clear MPC(X)` sequence. High-level MPC programming is still intentionally disabled.

## How to use

No `pip install` is required for normal use. Clone the repository and run the executable wrapper directly:

```bash
git clone https://github.com/nobukoba/sitcp-mpcx-mpc-writer-python-first-trial.git
cd sitcp-mpcx-mpc-writer-python-first-trial
./sitcp-mpc-writer --help
```

The wrapper runs the package from `src/` with `python3`, so it also avoids the `externally-managed-environment` error produced by Homebrew/Debian-style system Python environments.

## Basic commands

### Inspect a file

This only reads the file and does not access the FPGA or EEPROM.

```bash
./sitcp-mpc-writer inspect ./device.mpc
```

The official SiTCP MPC Writer XG 0.4.1-2 loader has been reconstructed far enough to confirm a 22-byte payload and two 7-byte decode paths used to classify the data.

Current classifier result:

```text
writer type 1 -> SiTCP-XG payload
writer type 2 -> normal SiTCP payload
```

The extension is ignored for this classification. For example, an XG payload named `device.mpc` is still detected as SiTCP-XG.

### Verify a file against a device

Use the same `verify` command for both normal SiTCP and SiTCP-XG:

```bash
./sitcp-mpc-writer verify ./device.mpc \
  --ip 192.168.2.161 \
  --port 4660 \
  --timeout 3
```

or, for an XG device:

```bash
./sitcp-mpc-writer verify ./device.mpcx \
  --ip 192.168.2.169 \
  --port 4660 \
  --timeout 3
```

The command first classifies the 22-byte payload, then selects the verified EEPROM mapping automatically. No write is performed.

For normal SiTCP, the mapping confirmed against a matching real device/file pair is:

```text
file[0:6]   -> EEPROM 0xFFFFFC12..0xFFFFFC17
file[6:22]  -> EEPROM 0xFFFFFC40..0xFFFFFC4F
```

For SiTCP-XG, the mapping confirmed against a matching real device/file pair and static analysis of the official Writer is:

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

### Check RBCP connectivity

The default RBCP UDP port used by SiTCP is `4660`.

For a device in ForceDefault mode, the default IP address is typically `192.168.10.10`.

Use a register address that is known to be safe to read in the FPGA design:

```bash
./sitcp-mpc-writer probe \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x00000000 \
  --length 1
```

### Read raw RBCP data

```bash
./sitcp-mpc-writer rbcp-read \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x00000000 \
  --length 16
```

### Read the reconstructed EEPROM extension area

```bash
./sitcp-mpc-writer eeprom-read \
  --ip 192.168.10.10 \
  --port 4660
```

### Clear the MPC EEPROM area

**This command is destructive.**

The reconstructed official sequence is:

1. write `0x00` to `0xFFFFFCFF` to enable EEPROM writing;
2. write `0xFF` to `0xFFFFFC00` through `0xFFFFFC7F` in 16-byte blocks;
3. write `0xFF` to `0xFFFFFCFF` to disable EEPROM writing again.

The Python CLI requires explicit confirmation:

```bash
./sitcp-mpc-writer clear \
  --ip 192.168.10.10 \
  --port 4660 \
  --yes-really-clear
```

Do not run this on a device whose MPC/EEPROM contents must be preserved.

### Raw RBCP write

A raw write command is provided for expert testing:

```bash
./sitcp-mpc-writer rbcp-write \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x12345678 \
  --hex-data "01 02 03 04"
```

This is not the MPC programming command. The user is responsible for choosing a safe address and value.

## MPC writing status

The intended final interface is deliberately simple and extension-independent:

```bash
./sitcp-mpc-writer inspect FILE
./sitcp-mpc-writer verify FILE --ip DEVICE_IP
./sitcp-mpc-writer write FILE --ip DEVICE_IP
```

`write` is currently disabled.

Before high-level writing is enabled, the implementation will require file-payload classification, device compatibility validation, preservation of fields that the official Writer preserves, explicit write enable, exact mapped writes, read-back verification, and write-disable cleanup.

Read transactions may be retried after UDP timeouts. Writes are intentionally not blindly retried because a lost ACK does not prove that the target-side write failed.

## Optional installation into a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
sitcp-mpc-writer --help
```

Do not use `sudo pip install` or `--break-system-packages` for this repository.

## Docker

Build the image locally:

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

On Linux, direct access to a SiTCP device on the host network can normally be tested with:

```bash
docker run --rm \
  --network host \
  sitcp-mpcx-mpc-writer-python-first-trial \
  verify /work/device.mpc \
  --ip 192.168.10.10
```

Docker Desktop networking on macOS differs from native Linux host networking. For initial hardware tests on a Mac, running the Python CLI directly on macOS is the simplest path.

## Repository layout

```text
.
├── sitcp-mpc-writer
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

`REVERSE_ENGINEERING.md` records addresses, constants, and behavior recovered from the official SiTCP MPC Writer XG binary. Implementation code should only be updated from behavior that has been verified there or against actual hardware/network captures.

## For Developers

Run the tests without installing the package:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The project intentionally has no third-party runtime Python dependencies. RBCP communication uses the Python standard library.

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

Do not enable the high-level `write` command until the remaining write sequence and compatibility checks are verified.

### Reverse-engineering reference

The current implementation was developed by comparing public SiTCP/SiTCP-XG documentation with static analysis of the official Windows `SiTcpMpcWriteXG.exe` version `0.4.1-2` and read-only tests against real hardware.

The official executable, proprietary libraries, and user-specific MPC files are **not** included in this repository.

See `REVERSE_ENGINEERING.md` for the reconstructed technical details.
