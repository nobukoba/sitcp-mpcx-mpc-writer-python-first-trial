# sitcp-mpcx-mpc-writer-python-first-trial

Experimental cross-platform Python CLI for inspecting and eventually writing SiTCP / SiTCP-XG MPC/MPCX data from macOS, Linux, and Docker without using the official Windows GUI.

The current implementation can inspect MPC/MPCX files, communicate with SiTCP over RBCP, read the reconstructed EEPROM extension area, and reproduce the official `Clear MPC(X)` sequence. Full MPC/MPCX programming is still intentionally disabled until the remaining file-to-EEPROM mapping is verified.

## How to use

Clone the repository and install it into a Python virtual environment:

```bash
git clone https://github.com/nobukoba/sitcp-mpcx-mpc-writer-python-first-trial.git
cd sitcp-mpcx-mpc-writer-python-first-trial

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Check that the command is available:

```bash
sitcp-mpc-writer --help
```

### Inspect an MPC/MPCX file

This does not access the FPGA or EEPROM.

```bash
sitcp-mpc-writer inspect ./device.mpcx
```

The official SiTCP MPC Writer XG 0.4.1-2 loader has been reconstructed far enough to verify that MPC/MPCX files handled by that path are 22 bytes and to reproduce its 7-byte tag decoding/type detection.

### Check RBCP connectivity

The default RBCP UDP port used by SiTCP is `4660`.

For a device in ForceDefault mode, the default IP address is typically `192.168.10.10`.

Use a register address that is known to be safe to read in the FPGA design:

```bash
sitcp-mpc-writer probe \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x00000000 \
  --length 1
```

### Read raw RBCP data

```bash
sitcp-mpc-writer rbcp-read \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x00000000 \
  --length 16
```

### Read the reconstructed EEPROM extension area

Static analysis of the official SiTCP MPC Writer XG 0.4.1-2 shows a 64-byte read beginning at RBCP address `0xFFFFFC10`.

```bash
sitcp-mpc-writer eeprom-read \
  --ip 192.168.10.10 \
  --port 4660
```

### Clear the MPC EEPROM area

**This command is destructive.**

The reconstructed official sequence is:

1. write `0x00` to `0xFFFFFCFF` to enable EEPROM writing;
2. write `0xFF` to `0xFFFFFC00` through `0xFFFFFC7F` in 16-byte blocks;
3. write `0xFF` to `0xFFFFFCFF` to disable EEPROM writing again.

The Python CLI requires an explicit confirmation option:

```bash
sitcp-mpc-writer clear \
  --ip 192.168.10.10 \
  --port 4660 \
  --yes-really-clear
```

Do not run this on a device whose MPC/EEPROM contents must be preserved.

### Raw RBCP write

A raw write command is provided for expert testing:

```bash
sitcp-mpc-writer rbcp-write \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x12345678 \
  --hex-data "01 02 03 04"
```

This is not the MPC/MPCX programming command. The user is responsible for choosing a safe address and data value.

## MPC/MPCX writing status

The intended final command is:

```bash
sitcp-mpc-writer write ./device.mpcx \
  --ip 192.168.10.10 \
  --port 4660
```

At present this command is deliberately disabled.

The following parts have already been reconstructed from the official Windows writer:

- RBCP packet format and UDP communication;
- EEPROM write-enable register `0xFFFFFCFF`;
- active-low write-enable values: `0x00` = enabled, `0xFF` = disabled;
- MPC clear area `0xFFFFFC00` to `0xFFFFFC7F`;
- 16-byte block writes used by `Clear MPC(X)`;
- 64-byte EEPROM access beginning at `0xFFFFFC10`;
- 22-byte MPC/MPCX file length check;
- two 7-byte decode paths used by the official writer to classify MPC/MPCX data.

Still under investigation:

- complete meaning of all 22 MPC/MPCX bytes;
- exact mapping from the 22-byte file to the EEPROM image;
- SiTCP versus SiTCP-XG compatibility checks;
- EEPROM initialization using current RAM/default values;
- extension-area initialization and verification;
- complete `Write MPC(X)` sequence.

These parts are not guessed because an incorrect implementation can overwrite EEPROM configuration or license information.

## Docker

Build the image locally:

```bash
docker build -t sitcp-mpcx-mpc-writer-python-first-trial .
```

Inspect a local MPC/MPCX file:

```bash
docker run --rm \
  -v "$PWD:/work" \
  sitcp-mpcx-mpc-writer-python-first-trial \
  inspect /work/device.mpcx
```

On Linux, direct access to a SiTCP device on the host network can normally be tested with:

```bash
docker run --rm \
  --network host \
  sitcp-mpcx-mpc-writer-python-first-trial \
  probe \
  --ip 192.168.10.10 \
  --port 4660 \
  --address 0x00000000 \
  --length 1
```

Docker Desktop networking on macOS differs from native Linux host networking. For initial hardware tests on a Mac, running the Python CLI directly on macOS is the simplest path.

## Repository layout

```text
.
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

Run the current tests with:

```bash
python -m unittest discover -s tests -v
```

The project intentionally has no third-party runtime Python dependencies. RBCP communication uses the Python standard library.

When extending the writer, keep the workflow safe:

```text
inspect file
    ↓
check device / MPC compatibility
    ↓
read and preserve current EEPROM state
    ↓
construct the exact EEPROM image
    ↓
explicit write operation
    ↓
read-back verification
    ↓
disable EEPROM write access
```

Do not enable the high-level `write` command until the complete mapping and sequence are verified.

### Reverse-engineering reference

The current implementation was developed by comparing public SiTCP/SiTCP-XG documentation with static analysis of the official Windows `SiTcpMpcWriteXG.exe` version `0.4.1-2`.

The official executable, proprietary libraries, and user-specific MPC/MPCX files are **not** included in this repository.

See `REVERSE_ENGINEERING.md` for the reconstructed technical details.
