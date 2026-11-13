# V2.30: RENAME and TRUNCATE

Current source adds IOF.RNAM ($4A) and IOF.TRNC ($4B). Use the matching
updated daemon and the distributed `bin/snldriver230_bin` (4,592 bytes).
Assembly and hardware validation passed on stock QDOS and SMSQ/E, as
recorded below. V2.29 metadata results remain in
[the metadata test notes](METADATA_TEST.md).

## Hardware results — 2026-11-13

The user reported **all seven test-plan steps PASS under SMSQ/E**:

1. Talent assembly, installation and V2.30 banner.
2. SuperBASIC smoke test: rename, metadata preservation, cached-read
   truncation, append, reopen, and truncation to zero.
3. Directory listing and payload/sidecar relocation checks.
4. Collision rejection (including case-insensitive matching), original
   contents preserved, and successful rename after the rejected operation.
5. Read-only truncation rejected, file unchanged.
6. Renamed executable copy still runs with its attributes intact.
7. Binary round-trip/guard and BASIC SAVE/NEW/LOAD/LIST regression checks.

The user also reported **steps 2–7 PASS on a stock QL running QDOS with
Toolkit II**, followed by **step 1 PASS** after assembling on that machine.
The stock-QDOS test variant avoids the SMSQ/E-only metadata setters.
All seven steps have therefore passed on both reported platforms.
The user confirmed that Linux `cmp -b` passed for the stock-QL and
SMSQ/E builds: the two assembled driver binaries are byte-for-byte identical. The V2.30 binary is distributed in `bin/snldriver230_bin`.
Automated suite: **147 tests passed**.

## Hardware test plan

Start on QIMSI/SMSQ/E, then repeat the applicable smoke checks on stock
QDOS with Toolkit II. Report PASS or the first error/line; no full output
transcription is needed.

1. Assemble `SNLdriver_asm` with Talent/Quanta 2.02 and save a separate
   `snldriver230_bin`. Reset before loading/calling it; expect V2.30.
   Update/restart the Linux daemon. Keep the previous working binary.
2. Put `tests/ql/snl_rename_truncate_bas` in Linux drive1. On the QL:

   ```basic
   NEW
   LOAD snl1_snl_rename_truncate_bas
   RUN
   ```

   This creates `snl1_rt230_old` and renames it to `snl1_rt230_new`.
   Both must be unused beforehand; change line 20 before repeating.
   Expect **PASS: rename, metadata, truncate and append**. It checks:
   payload length; version/date preservation across rename; reading to
   prime the cache; truncate at current position; append and reopen;
   truncate to zero and write again. Final payload is one byte, ASCII Z.
   The test uses SMSQ/E date/version setters as did the V2.29 test.
   For **stock QDOS with Toolkit II**, use
   `tests/ql/snl_rename_truncate_qdos_bas` instead. This avoids SET_FVERS,
   SET_FUPDT and FVERS, and compares the automatic update date before/after
   rename using Toolkit II FUPDT. Its disposable names contain `rt230q`.
   The original SMSQ/E test stopped at line 50 (SET_FVERS) with Bad Name
   in the user's stock-QDOS/Toolkit II session; this did not yet exercise
   rename or truncate.
3. `DIR snl1_rt230_`: only the new name should appear. On Linux, the old
   payload and old sidecar must be gone. The new payload and
   `.snl_headers/rt230_new.json` must exist. Open through the new name on
   the QL and confirm the final contents/length (the test does this too).
4. Collision check, using two new disposable names:

   ```basic
   OPEN_NEW #3,snl1_rt230_a: PRINT #3,"A": CLOSE #3
   OPEN_NEW #3,snl1_rt230_b: PRINT #3,"B": CLOSE #3
   RENAME snl1_rt230_a TO snl1_rt230_b
   ```

   Expect **Already Exists**. Both files must retain their original contents.
   Repeat the rename using `SNL1_RT230_B` as destination; still expect
   Already Exists. Then rename A to a fresh name: that must succeed,
   confirming the failed rename did not leave a channel open.
5. Read-only check: `OPEN_IN #3,snl1_rt230_new`, then `TRUNCATE #3`.
   Expect **Read Only**; `CLOSE #3`. Reopen and verify it is still one byte.
6. Rename a disposable copy of an executable previously extracted by QL
   Unzip, then EXEC it using the new name. This checks wrapped-file attributes
   and metadata relocation on hardware. Use win/SD as the copy source;
   SNL-to-SNL COPY still needs two channels and remains unsupported.
7. Run the binary round-trip/guard test with a fresh name and a BASIC
   SAVE/NEW/LOAD/LIST round trip. Optionally repeat V2.29 metadata checks.

Case-only rename is supported by the SNL operation. Some Toolkit RENAME
commands may reject it before invoking the driver, so an Already Exists
response from that BASIC command alone does not establish a driver failure.
Do not use a directory-containing ZIP as a directory-support test: SNL
remains flat. Use `-j` for flattening, watching for filename collisions.

## Behavior

RENAME operates on an open exclusive file. Its QDOS string must include
`snlN_` and a 1..36-byte filename. Device matching ignores case, and the
new drive must match the open channel. Cross-drive moves return Bad Name.
The driver updates its channel filename after acknowledgment. File position,
read cache, payload contents, date and version are retained.

The daemon checks payload and sidecar collisions before renaming. It renames
the payload and its sidecar (when present), then updates the session path/name.
A metadata rename failure attempts to roll the payload back and returns an
error. This is not a crash-atomic pair of renames; host-side writers should
not rename/create the same names concurrently. Symlinks are rejected.

TRUNCATE shortens the open exclusive file at its current payload position.
It cannot extend a file. A no-op at EOF succeeds. The driver updates EOF and
invalidates the read cache only after success. Subsequent writes can append
at the cut point. For emulator-wrapped files, the wrapper is retained and
only the payload tail is removed. A real size change marks the file modified,
using existing date/version rules on FLUSH/CLOSE.

Shared/read-only and directory channels return Read Only for both operations.
Format, real subdirectories and multiple simultaneous channels remain unsupported.

## Wire additions

| Request | Reply |
| --- | --- |
| `$1E`, length.b, full_device_qualified_name[length] | status.b |
| `$1F`, payload_position.l | status.b |

Positions are unsigned big-endian values. Errors also return status only.
Existing commands are unchanged. Old daemons do not answer new commands;
install the matching daemon before testing V2.30.

Contract references: [QDOS/SMS Reference Manual](https://kilgus.net/smsqe/QDOS%20SMS%20Reference%20Manual.pdf),
[Toolkit II manual](https://www.lingula.org.uk/~steve/share/ToolKit-II-Manual.pdf).
