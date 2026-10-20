# Documentation

Start with the [project README](../README.md) for the current V2.15 setup and
supported operations. Run shell commands from the repository root unless a
guide explicitly says otherwise.

## Practical guides

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
