# V2.29 candidate: versions, extended information and dates

The source now identifies itself as V2.29. The distributed
`bin/snldriver228_bin` remains the distributed V2.28 release. V2.29 hardware
results reported by the user are recorded below; no V2.29 binary has been
added to this repository.

## Hardware results — 2026-11-12

User-reported results from the hardware session following this plan:

- Metadata program: initial version 1, explicitly set version 42, reopened
  version 42. Explicit update date retained after CLOSE/reopen.
- DIR: normal file listing and positive extended space counts, reported as
  330833752 free / 981235568 total sectors. No daemon trace was supplied;
  Empty-drive DIR also passed, showing available host filesystem sectors.
  The prefix-filtered check was not individually reported.
- Unzip: all files inflated with no SNL errors when the ZIP was on a different
  device from the SNL destination. An extracted file's date, read on the QL
  using `DATE$(FUPDT(#3))`, matched its archive date viewed on Linux.
- Step 5 reported PASS: binary round trip/guards and BASIC SAVE/NEW/LOAD/LIST
  regression checks. Separate stock-QDOS repetition was not confirmed.

The exact hardware/OS for this session was not explicitly restated. These
results do not establish a separate stock-QDOS or Minerva regression pass.
Automated suite: 131 tests passed before hardware testing.

## Tonight's short hardware test

Start with QIMSI/SMSQ/E, where the date/version BASIC extensions are available.
Use fresh disposable filenames and an empty extraction destination. Retain the
V2.28 binary for rollback. Do not install over an already installed driver.

1. Update Linux `snl_serial`. Assemble `SNLdriver_asm` with Talent/Quanta 2.02
   using the usual workflow; save the candidate as `snldriver229_bin`.
   Reset, load and CALL that candidate. Expect the V2.29 banner. Start the
   matching updated daemon with `trace` enabled in its JSON configuration.
2. Copy `tests/ql/snl_metadata_bas` to the configured Linux drive1 directory.
   On the QL: `NEW`, `LOAD snl1_snl_metadata_bas`, `RUN`. The program creates
   `snl1_meta229_test`; change line 30 to a fresh name before repeating.
   Expected initial version: **1**. The initial date should match the Linux
   host's local time, even if the QL clock is wrong. After explicit changes
   and CLOSE/reopen, expect version **42** and update date **1700000000**.
   Record any error and its line. If an extension is unavailable on an older
   Toolkit, use SMSQ/E for this phase rather than treating it as a driver error.
3. Run `DIR snl1_`, including an empty mapped drive and a prefix-filtered DIR.
   Expect normal listings and nonnegative space counts. Confirm a successful
   `EXTENDED INFO` request in the daemon trace; a DIR implementation that
   only uses `MEDIUM INFO` does not test XINF. On SMSQ/E, compare the displayed
   capacity with the host filesystem; basic stock DIR remains capped at
   32767 sectors. Preserve the trace if the displayed units look wrong.
4. Repeat the previously working QL Unzip extraction, using an archive with a
   known file date and a fresh destination. Keep the ZIP on win/SD rather
   than SNL: extraction needs an input and output channel simultaneously.
   Expect successful `FILE DATE`
   requests and no `SNL unsupported I/O $4C` diagnostic. Inspect the extracted
   file's `FUPDT`/directory date and compare with the archive date. CLOSE/reopen
   must retain that date. Run/load the extracted program to check its header
   and payload still work. A timezone difference in archive conversion should
   be recorded separately from failure to persist the requested date.
5. Run `tests/ql/binary_test_bas` with a fresh output name, and a BASIC
   SAVE/NEW/LOAD/LIST round trip. Expect zero binary mismatches/guard errors.
   SAVE's file date should match host local time. Repeat the assembly,
   LOAD/SAVE, DIR and binary smoke checks on stock QDOS if time permits.

Stop on an assembly error or crash and record the exact message/line. Hardware
assembly and testing remain necessary; the automated interpreter does not
validate instruction encoding, ROM behavior or physical serial timing.

## Implemented semantics

- QDOS update date at header `$34`, version word at `$38`, backup date at `$3C`.
- New/overwritten files start with the daemon's local wall-clock update date,
  encoded as seconds since 1961-01-01. No Linux mtime is read or changed for
  QDOS metadata operations. Ordinary payload writes naturally affect Linux
  mtime, but that value is not authoritative.
- Modified files receive an automatic date/version update on FLUSH/CLOSE.
  Repeated flushes without another modification do not increment the version.
  Explicit update dates and explicit/preserved versions suppress automatic
  replacement for the rest of that open session.
- DATE: D1=-1 reads; D1=0 uses host current time; other values set the date.
  D2.B=0 selects update, 2 selects backup. Other selectors return Bad Parameter.
  Backup dates may be changed through a read-only file channel; update dates
  require write access. Files without metadata report zero dates/version.
- VERS: D1=-1 reads; D1=0 preserves; 1..65535 sets. Out-of-range values return
  Bad Parameter. Automatic increment wraps at 16 bits.
- Existing emulator wrappers remain authoritative for their embedded type and
  data-space attributes. Additional dates/version use a sidecar marked
  `wrapper_metadata: true`; unmarked legacy sidecars cannot override wrappers.
  Preserve these sidecars in backups too.
- XINF returns the documented 64-byte layout, 512-byte allocation units,
  unsigned 32-bit capacity/free counts (saturated at their maximum), QDOS
  logical header size 64, and a host-disk medium type. A1 and D1 are preserved.
  Read-only describes the configured medium's host access, not OPEN_IN mode.

XINF success is traditionally used as a level-2 capability probe. SNL still
has no rename, truncate or subdirectory creation. Applications must tolerate
Not Implemented for those operations; test actual callers before assuming
full level-2 compatibility. Format remains unsupported.

## Wire additions

All multi-byte values are big endian. Existing commands remain unchanged.

| Request | Success reply |
| --- | --- |
| `$19`, key.l, selector.b (DATE) | status.b, date.l |
| `$1C`, key.l (VERS) | status.b, version.l |
| `$1D`, zero.l (XINF) | status.b, information[64] |

Errors return status only. The driver drains XINF into scratch and publishes
the buffer only after a complete reply. `$1A` is intentionally unused because
an existing bootstrap path can leave a stray CTRL-Z on the link.
Use the updated daemon with the new driver: old daemons do not reply to these
new commands. The updated daemon remains compatible with V2.28.

Contract reference: [QDOS/SMS Reference Manual, file I/O operations and directory headers](https://kilgus.net/smsqe/QDOS%20SMS%20Reference%20Manual.pdf).
