# V2.15 DIR

Update `snl_serial` on Linux and restart the daemon. Assemble/install V2.15
after a QL reset using the normal bootstrap process. Both sides must be
updated. Confirm the banner says `SNL Device driver V2.15 serial debug`.

Use `SNLdriver_asm` to assemble on the QL. The constants are included and SYM
output is disabled; no separate include or symbol-output file is needed.
Use the newly assembled binary's actual length in the bootstrap loader.

## Hardware test

```text
DIR snl3_
```

Expect a medium label `SNL3`, free/total sector counts, then the files in drive3
with their original uppercase/lowercase spelling. Try drive1/drive2 too. Files
are sorted alphabetically without regard to case.

An empty drive should display its medium information and no filenames. A
listing longer than eight files checks crossing the 512-byte cache boundary.
For an optional filter, `DIR snl3_source_` lists names starting with `source_`
in any capitalization. This is a flat filename-prefix filter, not a subdirectory
or wildcard implementation.

Then confirm LOAD and the monitor's overwrite workflow still work after DIR
has completed and closed its channel. SAVE and DELETE remain unchanged.

## What is listed

Each visible regular file becomes a standard 64-byte directory record. The
record preserves its actual spelling, executable type/data space and stored
metadata. Embedded emulator wrappers are excluded from program lengths;
directory length fields include QDOS's 64-byte header overhead. Empty files
are included. Existing plain files without metadata are ordinary data files.

Dotfiles (including `.snl_headers`, AppleDouble files and `.DS_Store`), host
subdirectories, symlinks, non-ASCII names, names longer than 36 bytes and names
containing a backslash are omitted. Ambiguous case-colliding names or invalid
metadata on an otherwise visible file cause Bad Name; nothing is deleted or
renamed to resolve them.

The daemon captures a directory snapshot at OPEN. Later host changes appear
on the next DIR, without restarting the daemon. The snapshot is read-only and
uses the existing 512-byte read-ahead cache: eight records per network read.
Only one SNL channel can be open at a time, as before.

## Medium information

Stock SuperBASIC DIR calls FS.MDINF ($45) before fetching entries. The driver
now implements it using daemon command $18. The reply contains status,
16-bit free and total counts, and a ten-byte space-padded label such as `SNL3`.
D1 returns free sectors in the high word and total sectors in the low word;
A1 advances by the ten copied label bytes. Partial labels are not published.

The underlying Linux filesystem supplies free/total space in 512-byte sectors.
Counts are capped at 32767 because stock DIR formats them as signed 16-bit
values. A large Linux volume will commonly show 32767/32767; these are legacy
display limits, not an SNL capacity limit or per-drive storage quota. Mapped
drives sharing one Linux filesystem share its free-space pool.

## Local validation

84 tests pass. The source interpreter executes the stock-DIR sequence: mode-4
OPEN with no filename, FS.MDINF, repeated 64-byte reads, and EOF. Ten records
use two network READs. Additional checks cover empty listings, prefix matching,
case preservation, plain/sidecar/emulator metadata, zero-byte files, hidden
host files, snapshot refresh, read-only enforcement, media labels/counts and
partial-reply protection. Existing readiness, delete, binary and case-insensitive
lookup tests pass. Talent assembly and the real QL's DIR display are the next
verification steps.
