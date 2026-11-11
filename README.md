# SNL — serial filesystem for the Sinclair QL

SNL is a Linux-backed file storage driver for the Sinclair QL. It lets your QL
use a Linux computer as external file storage over a serial or USB serial
connection. Load, save and run files directly from Linux directories using
familiar QL commands. SNL uses SER2 on the QL and a Python daemon on Linux.

The release binary is [snldriver228_bin](bin/snldriver228_bin), assembled with
Talent/Quanta Assembler 2.02 from `SNLdriver_asm` (V2.28). Functional regression
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
bin/              Release binary (snldriver228_bin)
SNLdriver_asm      Self-contained QL assembly source
snl_serial         Linux serial filesystem daemon
snl_config.json    Shareable configuration with relative drive paths
tools/             Linux transfer and verification utilities
tests/             Python regression tests
  ql/              BASIC programs for hardware tests
  fixtures/        Sample input used by regression tests
docs/              Protocol, installation, tests and development notes
reference/         Original sources and superseded experiments
```

The assembly constants are already in `SNLdriver_asm`. No separate include
file is needed, and SYM output is disabled so assembly can use one SNL file
at a time. Retained reference sources are not build inputs.

## Linux setup

Install Python 3 and pyserial. From the repository root, choose the included
configuration for your interface and copy it over `snl_config.json`:

| Connection | Linux device | Configuration | RTS/CTS |
| --- | --- | --- | --- |
| Stock QL SER2 through a USB-to-serial adapter | `/dev/ttyUSB0` | `snl_configUSB0.json` | Enabled |
| QIMSI Gold USB serial (QL SER2 under SMSQ/E) | `/dev/ttyACM0` | `snl_configACM0.json` | Disabled |

For a stock QL with a USB-to-serial adapter:

```sh
cp snl_configUSB0.json snl_config.json
```

For QIMSI Gold USB:

```sh
cp snl_configACM0.json snl_config.json
```

Both example configurations map `snl1_` through `snl6_` to `drive1` through
`drive6`. Create those directories and start the daemon:

```sh
mkdir -p drive1 drive2 drive3 drive4 drive5 drive6
python3 snl_serial
```

Edit `snl_config.json` for your serial-device path and mapped directories.
Relative drive paths are resolved from the directory where you start the
daemon. The checked-in configuration contains relative paths and is intended
to be shared. A leading `~` is not expanded automatically.

For the stock QL's physical serial connection, use 9600 baud, eight data bits,
no parity, two stop bits, and RTS/CTS hardware flow control. Match the tested
QL cable wiring, including the handshake lines. QIMSI USB uses RTS/CTS off;
the example retains the baud and stop-bit settings, but these do not set its
USB transfer speed. Linux device numbers can vary, so adjust `serial_port`
if your interface appears under a different name.

The daemon reserves its host serial device; stop it before switching
configurations or using the same device for bootstrapping.

Restart the daemon after config changes.

## QL installation and use

Use `bin/snldriver228_bin`, or assemble `SNLdriver_asm` with Talent/Quanta 2.02
and save the raw binary.
Load it into reserved memory and install it with CALL, not EXEC. See the
[binary serial bootstrap guide](docs/BINARY_BOOTSTRAP.md) for a direct LBYTES
transfer using `python3 tools/qltransfer_bin your_binary` on Linux. Allocate
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
`.snl_headers` directory. Preserve that directory with Linux-side backups and
move/rename the corresponding metadata when moving/renaming files manually.
The daemon also understands 30- and 44-byte emulator wrappers, allowing files
extracted by QL Unzip in sQLux to be used by the physical QL.

Use normal QDOS/Toolkit II COPY to preserve headers when transferring a file
between Microdrive and SNL. COPY_N omits headers. Individual file copying has
been used on hardware; WCOPY failed during testing and remains unverified.

## Current limits

- One open SNL channel across all drives; SNL-to-SNL copying is unsupported.
- Flat drive directories; DIR can filter a filename prefix but cannot traverse
  subdirectories. Map a host subdirectory as another drive instead.
- No format, rename, truncate, or extended filesystem calls.
- Stock DIR space counts are capped at 32767 sectors for display; this is not
  a storage quota.
- Readiness handles missed daemon startup, not arbitrary interrupted binary
  transfers or automatic replay of writes/deletes.
- Physical hardware is tested. Running the driver inside an emulator is
  unverified and requires a usable serial mapping plus ROM compatibility.

## Verification and documentation

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -q
```

The 116 tests cover the daemon and an interpreter of the actual assembly source,
including transport errors, register/stack handling and alignment. The five
profiling-specific tests are retained with V2.24 in the diagnostic checkpoint.
They do not replace Talent assembly or physical serial testing. V2.28 has been
assembled and tested on the stock 128K QL and QIMSI Gold USB under SMSQ/E;
both assemblies produced identical binaries. Hardware coverage includes BASIC
load/save, existing-file handling, binary integrity and memory guards,
directories and prefix filtering, empty directories, missing files, executable
loading and assembling the driver through SNL. Stock QL testing also confirmed
recovery after starting a missing daemon. Minerva is unverified for V2.28.

Start with the [documentation index](docs/README.md) for hardware tests,
bootstrap instructions, protocol details and historical development notes.
Original source attribution and redistribution notices remain in the assembly
source; original reference material is under `reference/`.

The local drive folders, Python caches and optional `build/`/`dist/` staging
folders are ignored by Git. No local drive contents are part of this project.
