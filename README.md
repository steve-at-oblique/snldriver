# SNL — serial filesystem for the Sinclair QL

SNL is a host-backed file storage driver for the Sinclair QL. It lets your QL
use another computer as external file storage over a serial or USB serial
connection. Possible hosts include Windows PCs, Linux PCs, and Raspberry Pi
systems running Linux. Load, save and run files directly from host directories
using familiar QL commands. SNL uses SER2 on the QL and a Python daemon on
the host computer. Hardware testing so far has used a Linux host; Windows
and Raspberry Pi host setups have not yet been validated for this release.

**V2.31** adds Level-2 directories.
See the [directory hardware test plan](docs/LEVEL2_DIRECTORIES.md).
The supplied binary is the hardware-tested V2.31 release.

The release binary is [snldriver231_bin](bin/snldriver231_bin), assembled with
Talent/Quanta Assembler 2.02 from the V2.31 source. Functional regression
tests passed on a stock 128K QL running QDOS and on QIMSI Gold USB running
SMSQ/E. Assembly on both systems produced identical binaries. Minerva remains
unverified for this release.

V2.28 includes bulk transfers, aligned read-cache copies and batched READ
headers, with 512-byte payloads and no profiling instrumentation. It also fixes
the stock QL timeout caused by queued READ request bytes needing ROM serial
servicing while waiting for a reply. The 1024-byte buffer experiment was
reverted after it showed no measured benefit.

QIMSI Gold USB throughput testing in Large QL Mode 4 passed at **116.36 KiB/s
writing** and **85.33 KiB/s reading**. See the
[performance guide](docs/PERFORMANCE_BUILD.md) and
[QIMSI test history](docs/QIMSI_SMSQE_TEST.md) for test details.

Verified operations include BASIC LOAD/SAVE, binary LBYTES/SBYTES, executable
loading, DIR, DELETE, and the QL Monitor/assembler and Toolkit II overwrite
workflows. The QL can assemble SNL itself and save its new binary through SNL.

## Repository layout

```text
bin/              Release binary (snldriver231_bin)
SNLdriver_asm      Self-contained QL assembly source
snl_serial         Python serial filesystem daemon
snl_config.json    Shareable configuration with relative drive paths
tools/             Host transfer and verification utilities
tests/             Python regression tests
  ql/              BASIC programs for hardware tests
  fixtures/        Sample input used by regression tests
docs/              Protocol, installation, tests and development notes
reference/         Original sources and superseded experiments
```

The assembly constants are already in `SNLdriver_asm`. No separate include
file is needed, and SYM output is disabled so assembly can use one SNL file
at a time. Retained reference sources are not build inputs.

## Host setup

Install Python 3 and pyserial on the host. Run the daemon from the repository
root so it finds `snl_config.json`. Choose the included configuration for
your interface, then edit its serial port and drive paths for your computer:

| Connection | Linux / Raspberry Pi OS example | Windows example | Configuration | RTS/CTS |
| --- | --- | --- | --- | --- |
| Stock QL SER2 through a USB-to-serial adapter | `/dev/ttyUSB0` | `COM3` | `snl_configUSB0.json` | Enabled |
| QIMSI Gold USB serial (QL SER2 under SMSQ/E) | `/dev/ttyACM0` | `COM3` | `snl_configACM0.json` | Disabled |

The port names are examples. On Windows, check Device Manager for the assigned
COM port. On Linux, including Raspberry Pi OS, use the device assigned to
your adapter. Windows may require an appropriate driver for the USB device.

### Linux and Raspberry Pi OS

For a stock QL with a USB-to-serial adapter:

```sh
cp snl_configUSB0.json snl_config.json
```

For QIMSI Gold USB:

```sh
cp snl_configACM0.json snl_config.json
```

Create the mapped directories and start the daemon:

```sh
mkdir -p drive1 drive2 drive3 drive4 drive5 drive6
python3 snl_serial
```

### Windows (PowerShell)

Install pyserial using your Python installation, for example:

```powershell
py -m pip install pyserial
```

Copy the configuration for your interface, using one of:

```powershell
Copy-Item snl_configUSB0.json snl_config.json
# Or, for QIMSI Gold USB:
Copy-Item snl_configACM0.json snl_config.json
```

Edit `serial_port` in `snl_config.json` to the assigned port, such as `COM3`.
Then create the mapped directories and start the daemon:

```powershell
New-Item -ItemType Directory -Force -Path drive1,drive2,drive3,drive4,drive5,drive6
py snl_serial
```

If your Python installation uses `python` rather than `py`, substitute that
command. Windows operation, including file operations on open channels such
as RENAME, still requires platform testing.

### Drive mappings

Both example configurations map `snl1_` through `snl6_` to `drive1` through
`drive6`. Add entries and create their directories before using additional
drives such as `snl7_`.

Relative drive paths are resolved from the directory where you start the
daemon. A leading `~` is not expanded automatically. For absolute Windows
paths in JSON, use forward slashes (`C:/QL/drive1`) or escape backslashes
(`C:\\QL\\drive1`).

For the stock QL's physical serial connection, use 9600 baud, eight data bits,
no parity, two stop bits, and RTS/CTS hardware flow control. Match the tested
QL cable wiring, including the handshake lines. QIMSI USB uses RTS/CTS off;
the example retains the baud and stop-bit settings, but these do not set its
USB transfer speed. Adjust `serial_port` whenever the host assigns a different
port name.

The daemon reserves its host serial device; stop it before switching
configurations or using the same device for bootstrapping.

Restart the daemon after config changes.

## QL installation and use

Use `bin/snldriver231_bin` (4,698 bytes) with the matching updated daemon.
The self-contained source assembles with Talent/Quanta 2.02.
Load it into reserved memory and install it with CALL, not EXEC. See the
[binary serial bootstrap guide](docs/BINARY_BOOTSTRAP.md) for a direct LBYTES
transfer using `python3 tools/qltransfer_bin your_binary` on the host
(use `py` in place of `python3` on Windows). Allocate
enough memory for the actual binary, with at least 14 bytes for serial LBYTES.
The SNL entry offset is zero for the raw binaries checked during development.

Reset before replacing an installed driver; SNL owns SER2 until reset.
After installation, start the daemon before accessing files. A missed daemon
startup is recoverable: start it and retry the failed command without resetting.

Examples:

```text
DIR snl3_
LOAD snl3_program_bas
SAVE snl3_newprogram_bas
DELETE snl3_newprogram_bas
EXEC snl1_monitor
```

Filename lookup ignores case while preserving the stored spelling. Dots are
literal filename characters; SNL does not translate dots to underscores.
Use quoted filenames where needed by SuperBASIC syntax.

## Files and backups

New SNL files contain payload bytes; their QDOS metadata is stored in a hidden
`.snl_headers` directory. Preserve that directory with host-side backups and
move/rename the corresponding metadata when moving/renaming files manually.
The daemon also understands 30- and 44-byte emulator wrappers, allowing files
extracted by QL Unzip in sQLux to be used by the physical QL.

Use normal QDOS/Toolkit II COPY to preserve headers when transferring a file
between Microdrive and SNL. COPY_N omits headers. Individual file copying has
been used on hardware; WCOPY failed during testing and remains unverified.

## Current limits

- One open SNL channel across all drives; SNL-to-SNL copying is unsupported.
- Real subdirectories are supported; see [directory behavior and hardware
  results](docs/LEVEL2_DIRECTORIES.md).
- No format. QDOS paths remain limited to 36 characters after the device
  prefix. V2.30 adds rename and truncate;
  all seven hardware test steps passed under SMSQ/E and on stock QDOS with
  Toolkit II. See [V2.30 results](docs/RENAME_TRUNCATE.md).
  V2.29 metadata hardware results are recorded
  in [the test notes](docs/METADATA_TEST.md).
- Stock DIR space counts are capped at 32767 sectors for display; this is not
  a storage quota.
- Readiness handles missed daemon startup, not arbitrary interrupted binary
  transfers or automatic replay of writes/deletes.
- Physical hardware is tested. Running the driver inside an emulator is
  unverified and requires a usable serial mapping plus ROM compatibility.

## Verification and documentation

From the repository root:

```sh
python3 -B -m unittest discover -s tests -t . -q
```

On Windows, substitute `py` for `python3`. Some tests exercise filesystem
behaviors such as symlinks and may need platform-specific permissions.

The automated tests cover the daemon and an interpreter of the actual assembly source,
including transport errors, register/stack handling and alignment. The five
profiling-specific tests are retained with V2.24 in the diagnostic checkpoint.
They do not replace Talent assembly or physical serial testing. V2.31 has been
assembled and tested on the stock 128K QL and QIMSI Gold USB under SMSQ/E;
both assemblies produced identical binaries. Hardware coverage includes BASIC
load/save, existing-file handling, binary integrity and memory guards,
directories and prefix filtering, empty directories, missing files, executable
loading and assembling the driver through SNL. Stock QL testing also confirmed
recovery after starting a missing daemon. Minerva is unverified for V2.31.

Start with the [documentation index](docs/README.md) for hardware tests,
bootstrap instructions, protocol details and historical development notes.
Original source attribution and redistribution notices remain in the assembly
source; original reference material is under `reference/`.

The local drive folders, Python caches and optional `build/`/`dist/` staging
folders are ignored by Git. No local drive contents are part of this project.
