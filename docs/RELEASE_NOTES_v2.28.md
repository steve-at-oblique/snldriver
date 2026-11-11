# SNL v2.28

SNL is a Linux-backed file storage driver for the Sinclair QL. Load, save
and run files directly from Linux directories over serial or USB serial,
using familiar QL commands.

## Changes

- Adds QIMSI Gold USB SER2 support under SMSQ/E, alongside stock QL/QDOS.
- Improves throughput with bulk writes, batched READ headers and aligned
  read-cache copies. Uses 512-byte payloads without profiling instrumentation.
- Fixes a stock QL timeout when queued serial request bytes still need
  servicing while waiting for a READ reply.
- Includes ready-to-copy configurations for `/dev/ttyUSB0` (RTS/CTS on) and
  QIMSI `/dev/ttyACM0` (RTS/CTS off).
- Adds Copyright 2026 Steve Jennen and BSD-2-Clause licensing for original
  contributions, retaining existing third-party notices.

## Tested

Functional regression tests passed on a stock 128K QL running QDOS and on
QIMSI Gold USB running SMSQ/E: BASIC load/save and existing-file handling,
binary round trips and memory guards, directory listings and prefixes, empty
directories, missing files, Monitor/assembler loading and assembling the driver
through SNL. Both platforms produced identical driver binaries. Stock QL
also passed retry after starting a missing daemon.

QIMSI Gold USB in Large QL Mode 4: **116.36 KiB/s writing, 85.33 KiB/s
reading**, with integrity checks passing. All 116 automated tests pass.
Minerva remains unverified for this version.

## Installation and limits

Use `bin/snldriver228_bin` with the included `snl_serial` Linux daemon and
select the appropriate JSON configuration as described in the README.
Reset before replacing an installed driver, then LBYTES and CALL it.

SNL supports one open channel across all drives, so SNL-to-SNL copying is
unsupported. Host directories are exposed as flat drives; map host
subdirectories to additional drives as needed.
