# Documentation

Start with the [project README](../README.md) for the V2.28 release binary,
and tested operations. Current source is the V2.29 metadata candidate. Run commands from the repo root unless a
guide explicitly says otherwise.

## Practical guides

- [V2.29 metadata test plan](METADATA_TEST.md): file versions, extended medium
  information, host-clock dates and QL Unzip timestamp restoration.

- [1024-byte READ experiment](READ_BLOCK_1024.md): historical V2.26 changes
  and results; V2.27 restores the 512-byte driver cache and daemon limit.
- [Uninstrumented performance build](PERFORMANCE_BUILD.md): V2.25 removes
  profiling; V2.24 is preserved in diagnostic checkpoint `13a347e`.
- [Batched READ headers](BULK_READ_HEADERS.md): V2.24 request/reply header
  batching and comparison with the V2.23 profiling baseline.
- [Read-phase profiler](READ_PROFILE.md): V2.23 diagnostic build and a
  read-only runner to distinguish request, receive and cache-copy costs.
- [Bulk read-cache copy candidate](BULK_READ_COPY.md): V2.22 aligned cache
  copying, preserved line-read behavior, and hardware test steps.
- [Bulk write candidate](BULK_WRITE.md): V2.21 payload transmission and
  hardware regression/benchmark steps, compared with the tested V2.20 baseline.
- [Throughput benchmark](THROUGHPUT.md): timed, verified binary reads and
  overwrite saves on SNL and SD under SMSQ/E.
- [QIMSI Gold / SMSQ/E candidate](QIMSI_SMSQE_TEST.md): build V2.20 and test
  BASIC load/save first, followed by binary operations and directory listings.
- [Binary serial bootstrap](BINARY_BOOTSTRAP.md): install SNL or Toolkit II
  using the stock serial LBYTES protocol and `tools/qltransfer_bin`.
- [Binary round-trip test](BINARY_TEST.md): use `tests/ql/binary_test_bas` to
  verify SBYTES/LBYTES and use `tools/check_binary.py` on the Linux payload.
- [Emulator file compatibility](EMULATOR_FILES.md): QL Unzip in sQLux, shared
  directories, emulator wrappers and SNL metadata.
- [Directory support](DIRECTORY.md): DIR behavior, filtering and space counts.

## Protocol and development history

- [Serial implementation and history](SERIAL_OPEN.md): wire protocol, ROM
  investigation, architecture, limitations and the accumulated debugging record.
- [Bulk receiving](BULK_RECEIVE.md): the V2.10 performance change and tests.
- [DELETE](DELETE.md): V2.11 delete and V2.12 quiet filename checks.
- [Readiness handshake](READINESS.md): V2.13 missed-daemon recovery.

Version-specific notes describe the change at that point in development.
Use the current source/banner and actual newly assembled binary length when
installing; old binary sizes and version banners are historical examples.
