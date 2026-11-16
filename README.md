# SNL — Serial Network Link for the Sinclair QL

SNL lets a Sinclair QL load, save and run files directly from folders on
another computer over serial or USB serial. Use familiar QL commands while
the host's Python daemon handles storage. Files are immediately available
from both computers, without copying them into an SD-card container.

The current release is **v2.39**. The supplied
[snldriver239_bin](bin/snldriver239_bin) is 5,296 bytes.

## Features

- BASIC LOAD/SAVE, binary LBYTES/SBYTES, executable loading and DELETE.
- Multiple open channels, including SNL-to-SNL COPY/WCOPY, Unzip and
  assembly with include files. Each channel has its own 512-byte buffer.
- Bulk reads and writes, read-ahead caching and batched request headers.
- Level-2 subdirectories, directory creation, directory listings and prefix
  filtering, such as `DIR snl6_s`.
- Rename and truncate.
- QDOS file headers, file dates/timestamps, file-version query/set and
  extended medium information. QL Unzip can restore archived file dates.
- Case-insensitive filename lookup that preserves the stored spelling.
- Up to eight drive mappings, each pointing to a host folder. Mounted
  network shares can be used just like local folders.
- Recovery from a missed daemon startup: start the daemon and retry the
  failed command.
- Timestamped daemon output and optional OPEN/CLOSE statistics showing
  current and peak channel counts.

The QL can load its monitor and assembler through SNL, assemble the SNL
source, and save the resulting binary directly onto the host or a shared
network folder.

Measured QIMSI Gold USB throughput is approximately **128 KiB/s writing**
and **85.3 KiB/s reading**. See [throughput measurements](docs/THROUGHPUT.md)
for the benchmark conditions and detailed results.

## Supported systems

The driver has been hardware-tested on:

| QL system | Connection | Notes |
| --- | --- | --- |
| Stock 128K QL with QDOS | Built-in SER2 | Toolkit II adds commands used by the extended file-operation tests. |
| QIMSI Gold with SMSQ/E | USB serial | Uses the native USB serial driver. |
| QIMSI Gold with Minerva4Q68 | USB serial | Uses direct transmit and automatically configures the receive buffer; no manual SER_BUFF command is needed. |

Minerva4Q68 support targets its Minerva 1.98-based build with native SER2
USB support, on QIMSI Gold firmware v1.20 or newer. Other Minerva
configurations remain unverified. See the [Minerva guide](docs/QIMSI_MINERVA_TEST.md)
for the supported configuration and hardware results.

Possible hosts include Windows PCs, Linux PCs and Raspberry Pi systems
running Linux. Host-side hardware testing has used Linux; Windows and
Raspberry Pi operation still require validation. Windows RENAME of an open
file is a known compatibility concern.

## Host setup

Install Python 3 and pyserial. Run the daemon from the repository root so it
finds `snl_config.json`. Choose the configuration for your connection, then
edit its serial port and drive paths:

| Connection | Linux / Raspberry Pi OS example | Windows example | Configuration | RTS/CTS |
| --- | --- | --- | --- | --- |
| Stock QL SER2 through a USB-to-serial adapter | `/dev/ttyUSB0` | `COM3` | `snl_configUSB0.json` | Enabled |
| QIMSI Gold USB serial | `/dev/ttyACM0` | `COM3` | `snl_configACM0.json` | Disabled |

These port names are examples. Use the device assigned to your adapter;
on Windows, check Device Manager for its COM port. Windows may require a
USB device driver.

### Linux and Raspberry Pi OS

Install pyserial using your Python environment or system package manager.
Choose one configuration:

```sh
# Stock QL serial adapter:
cp snl_configUSB0.json snl_config.json

# Or QIMSI Gold USB:
cp snl_configACM0.json snl_config.json
```

Create the mapped directories and start the daemon:

```sh
mkdir -p drive1 drive2 drive3 drive4 drive5 drive6
python3 -u snl_serial
```

### Windows (PowerShell)

Install pyserial:

```powershell
py -m pip install pyserial
```

Choose one configuration:

```powershell
# Stock QL serial adapter:
Copy-Item snl_configUSB0.json snl_config.json

# Or QIMSI Gold USB:
Copy-Item snl_configACM0.json snl_config.json
```

Edit `serial_port` to the assigned port, such as `COM3`. Create the mapped
directories and start the daemon:

```powershell
New-Item -ItemType Directory -Force -Path drive1,drive2,drive3,drive4,drive5,drive6
py -u snl_serial
```

If your installation uses `python` instead of `py`, substitute that command.

### Drive mappings and network shares

The example configurations map `snl1_` through `snl6_` to folders `drive1`
through `drive6`. Add entries for additional drives, up to `snl8_`. Each
mapped directory must exist before it is used.

Relative paths are resolved from the directory where you start the daemon.
A leading `~` is not expanded. For absolute Windows paths in JSON, use
forward slashes (`C:/QL/drive1`) or escape backslashes (`C:\\QL\\drive1`).

A network share must be accessible through a filesystem path on the host;
SNL does not interpret `smb://` URLs. For example, if a share is mounted at
`/mnt/documents`, an entry can map its QL folder directly:

```json
"8": "/mnt/documents/ql"
```

A drive mapping may also point to a symbolic link to that mounted folder.
The daemon resolves the link when it loads the mapping. Use a host account
that can access the share. Files saved there from a Mac or PC are immediately
available through SNL, and files saved by the QL are available on the share.

### Serial settings and logging

For built-in QL serial, use **9600 baud, eight data bits, no parity, two stop
bits and RTS/CTS hardware flow control**. The cable must carry the handshake
signals. QIMSI USB uses RTS/CTS off; the example baud and stop-bit settings
do not determine its USB transfer speed.

The daemon reserves its serial device. Stop it before using that same device
for bootstrapping or another program. Restart it after configuration changes.

`channel_stats` defaults to true and reports OPEN/CLOSE events plus current
and peak channel counts. Set `trace` to true for detailed protocol diagnostics.
Every output line carries the host-local date and time as
`MM/DD/YYYY HH:MM:SS`. Ctrl-C closes sessions and prints a summary.

## QL installation and use

Load the supplied binary into reserved memory and install it with CALL:

```basic
base=RESPR(6000)
LBYTES win1_snldriver239_bin,base
CALL base
```

Substitute the device where you stored the binary. These lines can also go
in your SuperBASIC BOOT program. With Toolkit II, you can instead use:

```basic
LRESPR win1_snldriver239_bin
```

For direct serial delivery of the binary, see the
[binary bootstrap guide](docs/BINARY_BOOTSTRAP.md). Its host transfer tool is
`python3 tools/qltransfer_bin your_binary` (`py` on Windows). Reserve space
for the actual binary length plus at least 14 bytes when using serial LBYTES.

Reset before replacing an installed driver; SNL owns SER2 until reset.
Start the daemon before accessing files. If it was not started, start it and
retry the failed command without reinstalling SNL.

Examples:

```basic
DIR snl3_
DIR snl6_s
LOAD snl3_program_bas
SAVE snl3_newprogram_bas
LBYTES snl1_data_bin,base
COPY snl1_program_bas TO snl2_program_bas
DELETE snl3_newprogram_bas
EXEC snl1_monitor
```

Directories use QDOS underscore notation, for example `snl1_games_`.
Toolkit II provides commands such as MAKE_DIR and directory navigation on
stock QDOS. See [directory usage](docs/LEVEL2_DIRECTORIES.md).

Dots are literal filename characters; SNL does not translate dots to
underscores. Quote filenames where required by SuperBASIC syntax.

## Files, headers and backups

SNL stores ordinary payload files on the host. Their QDOS metadata is kept
in a hidden `.snl_headers` directory alongside them. Include that directory
in backups, and move or rename the corresponding metadata when manually
moving or renaming files on the host.

The daemon also understands 30- and 44-byte emulator wrappers, allowing
files extracted by QL Unzip in sQLux to be used by the physical QL.

Use normal QDOS/Toolkit II COPY or WCOPY to preserve headers when moving
files between QL devices and SNL. COPY_N omits headers. QL Zip/Unzip can
preserve executable metadata when transferring archives through other
operating systems.

## Current limitations

- FORMAT is not implemented; storage is managed by the host filesystem.
- QDOS paths are limited to 36 characters after the device prefix.
- Stock DIR space counts are capped at 32,767 sectors; extended counts are
  capped at 4,294,967,295 sectors. These are reporting limits, not storage quotas.
- A daemon or connection failure during a transfer reports an error. There is
  no automatic replay or recovery of an interrupted binary exchange.
- Application memory requirements still apply. Unzip and assembly with
  include files exhausted memory in some stock 128K QL tests.
- Running SNL inside an emulator requires a suitable serial mapping and
  compatible ROM/driver behavior; current release validation targets physical
  hardware.

## Source, tests and documentation

```text
bin/              Release binary
SNLdriver_asm      Self-contained QL assembly source
snl_serial         Python serial filesystem daemon
snl_config.json    Serial settings and drive mappings
tools/             Host transfer and verification utilities
tests/             Automated regression tests
  ql/              BASIC programs for hardware tests
  fixtures/        Sample test input
docs/              Usage, protocol, hardware results and development notes
reference/         Original sources and superseded experiments
```

The source assembles with Talent/Quanta Assembler 2.02. Constants are included
in `SNLdriver_asm`; no separate include file is needed. SYM output is disabled.
Retained reference sources are not build inputs.

Run the automated suite from the repository root:

```sh
python3 -B -m unittest discover -s tests -t . -q
```

On Windows, substitute `py` for `python3`. Some filesystem tests, such as
symlink tests, may require platform-specific permissions. The tests exercise
the daemon and an interpreter of the assembly source, including transport
errors, register/stack handling and alignment. They complement Talent
assembly and hardware testing.

The [documentation index](docs/README.md) links to usage guides, test results,
protocol details and historical development notes. Source attribution and
redistribution notices remain in the assembly source; original reference
material is under `reference/`.

Local drive contents, Python caches and optional `build/`/`dist/` staging
folders are ignored by Git.
