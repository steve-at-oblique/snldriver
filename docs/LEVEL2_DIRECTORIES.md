# V2.31: Level-2 directories

Current source adds real host subdirectories and IOF.MKDR ($4D).
The distributed binary is `bin/snldriver231_bin` (4,698 bytes). All five
steps passed on QIMSI/SMSQ/E; steps 1, 2, 3 and 5 passed on stock QDOS with
TK2 v2.36. Stock-QDOS step 4 was not run because no separate win1_ device
was available. Detailed results and initial test corrections appear below.

## Quick hardware tests

1. Update the daemon, assemble `SNLdriver_asm` to a separate
   `snldriver231_bin`, reset, then load/CALL it. Expect V2.31.
2. Copy `tests/ql/snl_directories_bas` to Linux drive1. On the QL:

   ```basic
   NEW
   LOAD snl1_snl_directories_bas
   RUN
   ```

   Use a fresh directory name in line 20 if a failed run leaves files behind.
   Expect **PASS: directories, adoption, move, truncate, delete**. The two
   DIR calls should show a subdirectory and its file. A normal successful
   run removes its disposable files/directories. Linux should show real
   directories during the run, rather than flattened underscore filenames.
3. Manually create a directory and save/load a BASIC program within it.
   Check DIR at the root and inside it, and Toolkit II DATA_USE/DDOWN/DUP.
   Verify a directory containing a file cannot be deleted; remove its contents
   before deleting it. Repeat a case-insensitive lookup within a subdirectory.
4. Put `qspread302.zip` on win/SD (not SNL). Extract into a fresh SNL
   destination using the usual QL Unzip command **without `-j`**. Keep the
   archive and output on different devices because SNL still supports one
   open channel. Expect real directories, preserved dates and no unsupported
   `$4D` diagnostic. Try running QSpread according to its installation notes.
   Record the first error or filename if extraction fails; paths longer than
   36 characters after `snlN_` remain outside SNL's supported limit.
5. Repeat V2.30 rename/truncate and binary/BASIC smoke checks. Test both
   SMSQ/E and stock QDOS with Toolkit II. Compare assembled binaries on Linux.

## Implementation and compatibility

- A QDOS name such as `snl1_games_chess_bas` can address
  `drive1/games/chess_bas`. Case is preserved and lookup ignores case.
- Exact flat filenames take precedence to preserve existing files. Otherwise
  lookup follows the longest existing directory prefix. Underscores remaining
  in the leaf are literal. Ambiguous Linux names differing only in case are
  rejected. If a flat name shadows a nested path, listing the shadowed entry
  returns Bad Name rather than silently reading the wrong file. Avoid creating
  such aliases manually on Linux.
- Directory OPEN resolves the folder and then applies any remaining filename
  prefix inside it. Listings contain 64-byte QDOS headers with full logical
  names; directory entries have type 255. Symlinks and hidden metadata are
  excluded. Directory snapshots refresh on reopen, as before.
- IOF.MKDR converts an open empty exclusive file to a directory channel.
  A trailing underscore on the placeholder is accepted and removed from the
  host directory name. Existing sibling files/directories with the new prefix
  are moved inside, together with their metadata. Failed moves attempt rollback.
  Nonempty files and invalid keys return Bad Parameter.
- Each directory has its own `.snl_headers` metadata storage. A directory's own
  metadata is stored in its parent's `.snl_headers`. Wrapped-file support is
  retained. RENAME can move ordinary files between directories on one drive.
- DELETE removes empty directories and empty internal metadata storage.
  Nonempty directories return In Use. Directory renaming remains Read Only,
  consistent with the existing SNL directory-channel policy.
- No Level-3 driver rewrite, multiple channels, FORMAT, automatic dot/underscore
  translation, or longer QDOS path format is included.
- MAKE_DIR/prefix adoption and payload/sidecar moves are not crash-atomic.
  Avoid concurrent Linux changes to names being modified by SNL.

## Protocol

Existing requests remain compatible; OPEN/DELETE/RENAME names may now resolve
through subdirectories. New request: `$20`, key.l (zero), with success reply
`status.b`, directory_stream_size.l. Errors contain status only. Longwords
are big endian. The driver changes its channel to directory mode and clears
its position/read cache after a complete successful reply.

Automated suite: **160 tests pass**, including nested paths, case handling,
prefix adoption, metadata moves, rollback, cache/mode changes and short replies.

Reference: [QDOS/SMS Reference Manual, IOF.MKDR and directory headers](https://kilgus.net/smsqe/QDOS%20SMS%20Reference%20Manual.pdf).

Initial hardware run: MAKE_DIR at BASIC line 80 reported Bad Parameter after
creating its empty placeholder. The driver no longer rejects nonzero D1: it
sends the sole supported zero wire key and preserves the caller register.
A hardware retry is required to confirm the cause and correction.

## Hardware progress — 2026-11-13

After removal of the driver D1 check, the user reported steps 1, 2 and 3
PASS on QIMSI running SMSQ/E, including nonempty-directory rejection and
subsequent empty-directory deletion. Step 4 initially failed because the active ACM daemon configuration lacked
its drive-7 mapping: every OPEN, including OPEN_NEW, returned Not Found and
no MAKE DIRECTORY request occurred. After correcting the mapping and rerunning,
the user reported **step 4 PASS**, extracting the archive without `-j`.
Steps 1–4 have therefore passed on QIMSI/SMSQ/E. The V2.30 rename/truncate
regression program also passed after removing stale metadata left by manual
Linux payload deletion (the stale destination sidecar correctly caused Already
Exists). The remaining binary/BASIC checks within step 5 and stock-QDOS
validation remain unconfirmed. QSpread launched from SNL but stopped at a
menu-file configuration error; full application operation is not yet verified.

The user subsequently confirmed **all five V2.31 test-plan steps PASS on
QIMSI/SMSQ/E**, including the binary/BASIC and rename/truncate regressions
in step 5. Stock-QDOS results were subsequently reported below. QSpread launch was observed;
its menu-file configuration still needs application setup.

### Stock QDOS without Toolkit II

The user confirmed root DIR and `DIR snl1_steve_` PASS, with no directory
marker in the original DIR display, and LOAD/SAVE inside directories PASS.
The full directory BASIC program is intended for Toolkit II or SMSQ/E and
was not used as the unextended-QDOS smoke test. Binary round-trip and
stock-QDOS-with-Toolkit-II directory results remain unconfirmed.

Stock-QDOS test-program compatibility: the BASIC fixture now uses
`testroot$`, `testsub$`, `testold$` and `testnew$` rather than short names
that can clash with installed keywords, and separates its setup assignments.
Hardware parsing of the revised fixture remains to be confirmed. TK2 v2.36
from Kilgus was confirmed to provide MAKE_DIR and show directory arrows;
the user’s v2.12 build lacked MAKE_DIR.

### Stock QDOS with Toolkit II v2.36

The user reported **steps 1, 2, 3 and 5 PASS** on the stock QL with TK2
v2.36 and SNL V2.31, including parsing/running the revised BASIC fixture.
Step 4 was **not run**: this machine has no win1_ device for holding the
ZIP separately from SNL output. It is not recorded as a driver failure.
Unzip with directories already passed on QIMSI/SMSQ/E.
