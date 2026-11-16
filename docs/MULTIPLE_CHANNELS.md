# V2.33: multiple channels and daemon statistics

The current distributed release is `bin/snldriver238_bin` (5,296 bytes), with
the matching updated daemon. The original V2.33 hardware results and test
plan are recorded below; see [V2.36 validation](BATCHED_CHANNEL_HEADERS.md)
for header batching, stock ROM timing, and performance results.
[V2.38 validation](QIMSI_MINERVA_TEST.md) adds Minerva4Q68 USB support. V2.32 was the
initial multi-channel candidate; V2.33 corrects directory-scan identities for
SNL-to-SNL WCOPY.

## Hardware test plan

Start on QIMSI/SMSQ/E, then repeat the applicable tests on stock QDOS with
Toolkit II v2.36. Keep the V2.31 binary available. Use the updated daemon
with V2.33; the old daemon does not understand handled requests.

1. Assemble `SNLdriver_asm` with Talent/Quanta 2.02 and save a separate
   `snldriver233_bin`. Reset before loading/CALLing it. Expect V2.33.
2. Start the updated daemon. `channel_stats` defaults to true; detailed byte
   tracing is not needed for these measurements. On Linux, save output with:

   ```sh
   python3 -u snl_serial | tee snl_channels.log
   ```

   This keeps the ordinary console output and creates a log. Use Ctrl-C for
   normal shutdown; expect CLOSE events and a SUMMARY showing active=0.
3. Copy `tests/ql/snl_channels_bas` into drive1, then on the QL:

   ```basic
   NEW
   LOAD snl1_snl_channels_bas
   RUN
   ```

   Expect **PASS: SNL-to-SNL COPY and three channels**. The test creates
   `mc233_src` and `mc233_dst` (1,537-byte patterns), copies between SNL
   channels while a directory channel remains open, and compares both files
   through independent read channels. Expect a peak of at least **3** in
   the log. DELETE both test files through the QL before repeating, or change
   their names. QL DELETE removes their sidecars as well.
4. Try ordinary SNL-to-SNL COPY and WCOPY to/from another device, then
   SNL-to-SNL WCOPY with several disposable files. Inspect prompts: WCOPY
   applies Toolkit wildcard naming rules. Check copied content, headers and
   that every OPEN eventually has a CLOSE. Record the observed peak.
5. Run QL Unzip with the archive **on SNL** and a fresh SNL extraction
   destination. This formerly failed under the one-channel restriction.
   Include subdirectories and verify extracted contents/date preservation.
   Record peak channels. Do not overwrite the archive with output names.
6. Run the Quanta/Talent monitor and assemble a small source with INCLUDE
   files, keeping source, include files and output on SNL where possible.
   Record success and peak channels; compare output with a known-good build.
7. Repeat directory, rename/truncate, metadata and binary/BASIC regression
   checks. Test startup recovery: stop the daemon with no open SNL files,
   attempt DIR, start it, then retry DIR without resetting the QL.
8. Optionally interrupt a disposable copy by stopping the daemon. The copy
   should report failure; do not expect automatic resume. Close/reopen the
   files or retry the operation once the daemon is running. A mid-packet
   interruption may require QL/transport reset; stream resynchronization is
   outside this change. Incomplete destination files should be discarded.

Only the real measurements establish whether two or three channels cover
normal workloads. There is no new arbitrary two/three-channel cap; each open
channel consumes its normal QDOS CDB plus a separate 512-byte read buffer.

## Statistics

With `channel_stats: true` in `snl_config.json`, events look like:

```text
11/14/2026 09:08:07 SNL OPEN handle=100 drive=1 mode=1 file='source_zip' active=1 peak=1
11/14/2026 09:08:07 SNL OPEN handle=101 drive=1 mode=2 file='output_bas' active=2 peak=2
11/14/2026 09:08:07 SNL CLOSE handle=101 file='output_bas' active=1 peak=2
11/14/2026 09:08:07 SNL CLOSE handle=100 file='source_zip' active=0 peak=2
11/14/2026 09:08:07 SNL SUMMARY reason='shutdown' opens=2 closes=2 rejected=0 active=0 peak=2
```

Every daemon console line is prefixed with host-local `MM/DD/YYYY HH:MM:SS`,
including startup, statistics, trace output, and reported serial errors.
Timestamps have one-second precision.

- `active`: currently open handled sessions, including directory snapshots.
- `peak`: highest active count since daemon startup.
- `opens`/`closes`: successful handled opens and session removals.
- `rejected`: failed OPEN or DELETE attempts, including ordinary Not Found
  probes. OPEN REJECTED records the name, mode and QDOS status.
- Modes: 0 exclusive old, 1 shared/read-only, 2 new, 3 overwrite, 4 directory.
- Logs describe filenames and operations; statistics do not print payloads.

Restart the daemon before a workload to measure that workload's own peak.
A QL reset closes stale sessions but does not reset the daemon's cumulative
statistics. Set `channel_stats` false to suppress statistics. `trace` remains
an independent option for detailed protocol diagnostics. Existing V2.31
clients retain their legacy single-session protocol, without handled-session
statistics. Do not mix old and new clients on the same serial connection.

## Driver and daemon changes

OPEN obtains a daemon handle and allocates its own 512-byte cache. Each CDB
retains independent mode, position, EOF and cache state. Failed OPEN frees
its cache. CLOSE removes only its session/cache and leaves the permanent
serial connection and other channels intact. CDB fields owned by SMSQ/E
remain untouched.

The serial transport and private stack remain shared. An entry lock is taken
before switching to that stack and released after the complete driver call.
A busy entry returns Not Complete before sending any bytes, allowing retry;
packets are never interleaved. No background request queue is introduced.

The daemon permits multiple readers of the same ordinary file, but rejects
conflicting exclusive opens and deletion of an open target. Directory snapshots
can coexist with file operations. MAKE_DIR rejects adoption of a prefixed file
that is open on another channel. Internal directory-record scans are not counted
as QL channels.

Readiness no longer closes existing sessions on every OPEN. A changed QL
installation token, or a reset attempt counter, closes stale sessions. The
existing missing-daemon startup retry is retained. Handles increase from a
randomized daemon-start seed and are not reused within a run. After a daemon
restart old handles normally receive Channel Not Open. There is no automatic
reopen, replay, asynchronous cancellation notification or elaborate recovery
from a partially transmitted packet. Graceful daemon shutdown attempts to
flush/close every open session even if another session's flush fails.

## Wire additions

| Request | Success reply |
| --- | --- |
| `$21`, drive.b, mode.b, length.b, name[length] | status.b, handle.l, size.l |
| `$21` with mode `$FF` (DELETE) | status.b only |
| `$22`, handle.l, original_command.b, original_body | Original reply layout |

The readiness token format is unchanged. Multi-byte fields are big endian.
Unknown handles return Channel Not Open (-6); READ/WRITE errors also return
count=0 so the driver can drain the normal response shape. Complete request
bodies are consumed before rejecting an unknown handle. Updated daemons also
accept legacy operations for older drivers.

Automated validation: **179 tests pass**. Coverage includes interleaved driver
CDBs, SNL-to-SNL copy, three simultaneous daemon sessions, failed-OPEN and
CLOSE cache cleanup, entry-lock behavior, stale handles, startup retries,
sharing conflicts, statistics and shutdown cleanup. Instruction encoding,
physical serial timing and ROM behavior still require hardware tests.

## Hardware results — 2026-11-14

- QIMSI/SMSQ/E: all eight test-plan steps passed, including SNL-to-SNL COPY,
  WCOPY, Unzip, assembly with INCLUDE files, regressions and interruption tests.
- Stock QL with Toolkit II: steps 1–4, 7 and 8 passed. Unzip (step 5) and
  assembly with INCLUDE files (step 6) could not complete due to insufficient
  memory on the 128K machine; these are not recorded as driver failures.
- Observed QIMSI/SMSQ/E peaks: WCOPY **3**, assembler with INCLUDE files **2**,
  Unzip **2**. These are workload observations, not channel limits.

WCOPY initially failed before any file OPEN reached the daemon. The QDOS
channel block labeled directory scans as exclusive files. Preserving directory
mode fixed the SNL-to-WIN case. SNL-to-SNL WCOPY also required unique reserved
scan names: a scan's filename filter could otherwise block a matching NEW/OVER
file open in the OS. V2.33 uses `.SNL_D` plus eight printable handle nibbles
for the internal CDB identity; the daemon retains the real filter/header names.
The user confirmed SNL-to-SNL WCOPY passed after installing V2.33.

Each hardware-retest change will receive a distinct candidate version rather
than reusing a version number for several assembled binaries.
