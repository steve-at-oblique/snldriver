# V2.11 DELETE

V2.12 keeps DELETE and makes expected host errors such as Not Found and
Exists quiet during OPEN/DELETE. Reply-byte/serial diagnostics remain enabled
for broken exchanges. Use the V2.12 banner to identify the updated source.

Update `snl_serial` on Linux and restart the daemon. Assemble/install V2.11
after a QL reset using the usual bootstrap process; start the daemon before
accessing SNL. The new banner is `SNL Device driver V2.11 serial debug`.
The previous loader's binary length must be updated to match the newly
assembled file; do not reuse V2.10's 3,080-byte length for this build.

The canonical `SNLdriver_asm` includes the constants and disables SYM output
for building on the QL with SNL's single-open-file limitation. No separate
include file is required.

## Hardware test

Use a disposable BASIC file with a fresh name:

```text
SAVE snl3_deltest_bas
DELETE snl3_DELTEST_BAS
SAVE snl3_deltest_bas
```

The delete should succeed despite the different case; the second SAVE should
create a new file. Check on Linux that both the original payload and its
`.snl_headers/deltest_bas.json` were removed when DELETE ran. To test a missing
file, delete it twice: the second DELETE should report Not Found.

Next try the monitor's existing-file replacement workflow with a disposable
binary, accepting its Y/N replacement prompt. DELETE now supplies the standard
QDOS operation that was missing; if the monitor requests another unsupported
operation, record its exact message and the SNL diagnostic call number.

Ordinary SAVE still requests a new file and returns Exists if it is already
there. Use DELETE then SAVE, or the application's replacement confirmation.
This change does not silently turn new-file requests into overwrites.

## Implementation

QDOS IO.DELET invokes the directory OPEN routine with fs_acces=$FF. The driver
sends the existing $11 frame with mode $FF and reads a single status byte.
It does not read an OPEN size, register a channel, take the one-file lock, or
change the PDB file count. QDOS unlinks/frees the temporary DELETE CDB on
return. The behavior was checked against the JS ROM directory dispatcher.

The daemon resolves the same case-insensitive name as OPEN and removes its
payload and matching sidecar. Embedded emulator headers require no separate
metadata deletion. Missing files return Not Found; active sessions return In
Use. Directories, symlinks, ambiguous case collisions, reserved names and paths
outside the drive are rejected. The driver retains its current restriction
against issuing another operation while any SNL file is open.

An old daemon returns Not Implemented for mode $FF; it must be updated to use
DELETE. Normal OPEN/READ/WRITE frames and V2.10's bulk-receive behavior remain
compatible.

## Validation

57 local tests pass, including the actual source-level driver DELETE path,
status-only response consumption, unchanged file counts/lock on DELETE,
subsequent successful OPEN, deletion and recreation, metadata removal,
case-insensitive names, busy/missing files, emulator-wrapped files, and failed
or unsafe deletions. Source interpretation does not replace Talent assembly
or a hardware test.
