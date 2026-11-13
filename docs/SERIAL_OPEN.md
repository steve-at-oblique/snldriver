SNL serial file driver — protocol v2
===================================

For sQLux mapped-directory files and the existing QL Unzip workflow, see
EMULATOR_FILES.md. The daemon now recognizes 30/44-byte emulator wrappers;
V2.10 adds ROM bulk receiving; see BULK_RECEIVE.md. V2.11 adds DELETE via
OPEN mode $FF; see DELETE.md. V2.13 adds readiness before OPEN/DELETE; see
READINESS.md for the latest build and hardware test instructions.

V2.14 fixes the checkerbox after some messages. The supplied V2.10 binary
declares 38 bytes for its 37-byte banner, including alignment padding in the
length inferred from end labels. Banner/diagnostic length words now contain
explicit text byte counts, excluding padding. Keep their counts in sync when
editing text. Reassembly is needed; no daemon update or protocol change.

V2.15 adds directory OPEN mode 4 and FS.MDINF. See DIRECTORY.md for build
and hardware test instructions. Update both driver and daemon for DIR.

SNLdriver_asm is the canonical, self-contained assembly source. The microdrive
maps, image mounting, checksums, sector conversion, directory scanning and
slave-block routines have been removed. Its constants are included directly;
SNL_symbol_asm is retained as a reference. Original MDI files are references
and are no longer build dependencies. The supplied
MDI_RAM_SYMBOL_TABLE is historical assembly output and is not an input.
SYM output is disabled for assembly through SNL. No external symbol setup is needed:
trap keys and the two remaining ROM vectors are explicit in the source.

Both the driver and snl_serial MUST be updated together. The earlier OPEN
packet (01 drive length name) is obsolete; protocol v2 uses command 11 and
includes the access mode. Restart the daemon when switching versions.

Implemented QDOS calls
----------------------

* OPEN old (0), shared/read-only (1), new (2), overwrite (3); CLOSE.
* DELETE through directory OPEN mode -1 ($FF), without retaining a channel.
* Directory OPEN (4): a buffered, read-only stream of 64-byte QDOS entries.
* FS.MDINF: ten-byte medium label and capped free/total sector counts.
* IO.PEND, IO.FBYTE, IO.FLINE, IO.FSTRG, IO.SBYTE, IO.SSTRG.
* FS.LOAD and FS.SAVE: long byte counts, split into at most 512-byte packets.
* FS.HEADR (14–64 bytes), FS.HEADS (first 14 bytes), FS.CHECK, FS.FLUSH.
* FS.POSAB and FS.POSRE: signed positions clamped to [0, file length].
  EOF is returned at the end limit. Payload position zero excludes metadata.
* Format, rename, truncate, dates, versions and extended information return
  Not Implemented.

The original dd_mdvop/dd_mdvio/dd_mdvcl names remain the registered entries.
Position and file size in the CDB are flat payload byte counts, not MDV
block/byte values. FS.LOAD/SAVE retain the full long D2 count; ordinary
string operations use D2.W. D1 returns the actual byte count, A1 advances
by the transferred amount, and single-byte calls preserve A1. Line reads
include LF and do not consume any following byte; buffer exhaustion without
LF returns Buffer Full, and an unterminated final line returns EOF.

QDOS can clone a shared CDB without calling the driver's OPEN routine. To
avoid sharing a serial ID or inheriting a microdrive position of $40, this
implementation registers successful channels as exclusive and remembers
the requested read-only mode separately. A driver-wide lock permits ONE
open SNL file across all drives at a time. This intentionally does not offer
normal concurrent shared-file semantics. OPEN_IN still enforces read-only
access on both QL and Linux. FS_FILES is incremented by QDOS, decremented
by driver CLOSE. Failed OPENs never decrement it themselves.

Transport calls use immediate-return (timeout zero) TRAP #3 from supervisor
mode. A bounded loop retries only the uncompleted byte, using the QDOS RTC
for a three-second per-byte deadline and a retry-count fallback. A private
supervisor stack in the driver linkage allocation provides room for nested
traps without consuming the caller's documented 64-byte allowance. These
are synchronous operations: a long LOAD/SAVE monopolizes the QL scheduler
while transferring, although interrupts can still run. This is an initial
implementation for target testing, not an asynchronous queued driver.

A transport failure marks the CDB unusable and returns Transmit Error for
Not Complete. Further I/O cannot replay a partially sent request. CLOSE
still releases the file CDB and the one-file lock; the installed driver
retains the serial transport channel. Other transport errors
are returned unchanged on the failing call. The wire protocol has no
framing, sequence numbers or checksum: restart the daemon/link after a
partial-packet failure before opening another file. Automatic recovery from
arbitrary dropped bytes is not implemented. V2.13's token-matched readiness
probe prevents file requests when the daemon is absent, allowing that startup
mistake to be retried after starting it without resetting the QL.

Wire protocol
-------------

All numeric fields are big endian. Status is a signed QDOS error byte
(00 success, F9 Not Found, F8 Exists, F6 EOF, EC Read Only, etc.). Counts
are unsigned words, offsets and lengths are nonnegative signed longs
(maximum file size 0x7fffffff). READ/WRITE count must be at most 512.

V2.13 precedes each OPEN/DELETE with the ASCII readiness exchange documented
in READINESS.md. Normal binary commands are sent only after a matching reply.

| Command | QL request after command byte | Linux reply |
| --- | --- | --- |
| 11 OPEN | drive:u8, mode:u8, name_length:u8, ASCII name | status; on success only, size:u32 |
| 11 DELETE (mode FF) | drive:u8, FF, name_length:u8, ASCII name | status only, including success |
| 12 READ | offset:u32, count:u16 | status, actual:u16, actual data bytes |
| 13 WRITE | offset:u32, count:u16, data | status, actual:u16 |
| 04 CLOSE | none | status |
| 15 READ HEADER | none | status; on success only, 64 header bytes |
| 16 SET HEADER | 14 header bytes | status |
| 17 FLUSH | none | status |
| 18 MEDIUM INFO | none | status; on success only, free:u16, total:u16, label:10 bytes |

OPEN mode 4 permits an empty name for the full directory or a flat filename
prefix for filtering. Its successful size is the directory snapshot byte count;
normal READ/position/EOF/CLOSE calls consume it. Directory writes are Read Only.
Sector counts in MEDIUM INFO use 512-byte sectors, capped at 32767 for the
stock ROM's signed-word display; this does not limit actual file storage.

READ/WRITE replies ALWAYS include the count, even on an error. A short
READ returns EOF plus any available data. A short WRITE returns Drive Full
plus its actual count. Requests include absolute positions so byte, string
and bulk operations use the same host file. A fully received successful
READ must satisfy its requested count; inconsistent replies poison the CDB.

Linux storage
-------------

New SNL files contain payload bytes. QDOS header metadata is stored in
.snl_headers/<filename>.json. Existing emulator-wrapped files are also
supported as described in EMULATOR_FILES.md. Keep the metadata directory when
copying executable files whose type/data-space metadata matters. New and
overwrite reset metadata. Missing metadata on an existing Linux file gives
a default data-file header. Header length is always the actual payload
length; the daemon supplies the QDOS name and first 14 bytes of metadata.
Header updates use atomic replacement; FLUSH/CLOSE fsync writable payloads.

Flat ASCII filenames of 1–36 bytes are supported. Underscores are literal
filename characters. Separators, traversal and paths escaping the drive
are rejected. Filenames use Linux case sensitivity. Parent drive directories
must already exist. Only one file session exists on the daemon; a fresh
valid OPEN closes a stale session left after a QL port close.

Run and verify
--------------

On Linux, install pyserial and create a test directory. Example snl_config.json:

```json
{"serial_port":"/dev/ttyUSB0","baud_rate":9600,"drives":{"1":"./drive1"}}
```

Run `python3 snl_serial`. Set the QL serial baud rate to match (9600 by
default); the QL uses SER2H as in reference/experiments/ser_test.asm. The server disables software
flow control so binary bytes 11/13 are preserved. Retain your proven cable
and handshake setup.

Build SNLdriver_asm with Talent/Quanta 2.02; no include file is needed. Load the
binary into resident memory as for your existing driver. Installation displays `SNL Device driver V2.15 serial debug` on success
and retains allocation/link errors. Installation failure displays its error
byte instead of a success banner. The private stack is owned by job zero along with the linkage block.

Suggested QL checks, using a disposable mapped directory:

1. Enter a short BASIC program, SAVE snl1_trial_bas, NEW, then LOAD
   snl1_trial_bas and LIST. Verify the program and the Linux payload file.
2. SAVE to the same name again: check the expected Exists behavior; use
   your normal overwrite command/OPEN_OVER test when replacing a file.
3. OPEN_IN #3,snl1_trial_bas, INPUT #3,a$, CLOSE #3; check line reading.
4. OPEN_NEW #3,snl1_bytes, PRINT #3,"hello", CLOSE #3, then OPEN_IN and
   INPUT it back. Try a write to OPEN_IN and confirm Read Only.
5. Test LBYTES/SBYTES with binary data (all byte values), a file larger
   than 64 KiB, header type/data-space round trips, exact EOF and short reads.
6. Test a missing file, unmapped drive, second simultaneous open, and
   disconnect during a transfer. After a partial packet restart the daemon
   before retrying. Confirm CLOSE releases the SNL file lock; SER2H remains reserved by SNL.

`python3 -m unittest -v test_snl_serial.py` exercises the receiver with real
temporary files and fragmented serial reads/writes, including a 76,800-byte
binary round trip, access modes, EOF, headers, absolute positions, invalid
paths/counts, partial host writes and truncated packets. These tests do not
execute the assembly. Source labels and branch targets were checked, but
no compatible assembler, QL emulator or physical QL is available here:
Talent 2.02 assembly, ROM compatibility, serial handshake, nested trap/private
stack behavior and end-to-end SuperBASIC LOAD/SAVE remain unverified.

Reference: QDOS/SMS Reference Manual, sections 2.2.3, 7 and 15:
https://www.kilgus.net/smsqe/QDOS%20SMS%20Reference%20Manual.pdf

QL diagnostics (V2.01)
----------------------

The restored success banner identifies the loaded binary. Unsupported local
I/O prints `SNL unsupported I/O $xx`; an unsupported OPEN mode prints
`SNL unsupported OPEN mode $xx`. A Not Implemented response from the Linux
receiver prints `SNL host status $ED`. Messages preserve the I/O operation,
error and buffer registers. They go to the default QDOS console using the
same UT.MTEXT mechanism as the original banner.

After rebuilding, reset/restart the QL before installing the new binary so
an earlier registered driver or physical definition block cannot handle
the test. Confirm the V2.01 banner, retry LOAD, and record the complete SNL
message immediately before the BASIC error. These diagnostics identify the
missing call; they do not yet add an unobserved operation to LOAD's path.

Linux packet diagnostics
------------------------

The daemon now prints its absolute script/config paths and logs command
bytes, OPEN drive/mode/name, READ/WRITE offsets/counts, and reply statuses.
The supplied snl_config.json enables this with `"trace": true`; set false
when finished debugging. No payload contents are logged. Stop the existing
Python process and start the updated snl_serial; changing the file on disk
does not update a running process. Startup must say `SNL protocol v2
diagnostic daemon`. For a QL `SNL host status $ED`, capture RX and TX lines
from OPEN through the first status=$ED to identify the rejected request.

9600-baud receive correction (V2.02)
------------------------------------

Linux now explicitly uses 8N2 (eight data bits, no parity, two stop bits).
The earlier daemon inherited pyserial's one-stop-bit default, which is
unsuitable for a base QL receiving at 9600. Configuration uses `stop_bits: 2`.
Hardware flow control is configurable with `rtscts`; its default remains
false until the actual cable's handshake connections are confirmed.

The daemon logs the exact OPEN reply bytes and its serial format at startup.
The QL banner is V2.02. Failed OPEN exchanges now also print the number of
received reply bytes in hex: $00 means no complete status byte, $01 means
status arrived but no size byte, $02–$04 means a partial size, and $05 means
the whole success reply arrived (a subsequent validation failed). A rejected
OPEN normally has only its one status byte. The counter measures bytes
returned successfully by the QDOS serial driver, not electrical activity.

For the next test, first update/restart Python and retry the current QL binary
with two stop bits. If it still fails, build/install V2.02 and report both
`SNL OPEN reply bytes $xx` and the Linux `OPEN reply wire` line. The new
counter does not change the protocol.

QL stop-bit requirement: original QL Concepts manual, Serial Ports:
https://sinclairql.net/djw/docs/ebooks/olqlug/QL%20Manual%20-%20Concepts.htm

Stray-byte response correction
------------------------------

Unknown command bytes are now logged and discarded without a reply. The
reported sequence `RX $1A`, `TX $ED`, then a successful OPEN caused the QL
to consume the unsolicited $ED as its OPEN status. The source of $1A has
not been established. A regression test feeds $1A followed by a valid OPEN
and verifies that the only response is the successful OPEN status/size.
This handles stray unknown bytes between requests, not arbitrary corrupted
packets. Partial packets still require a link/daemon restart.

Channel-table slot fix (V2.03)
-----------------------------

The driver now opens SER2H during installation, before it registers the
SNL device. The channel is owned by job zero and its ID is stored at $4C in
the linkage block. File OPEN only copies this existing ID into its CDB;
file CLOSE does not close the transport. Installation failure releases
both the serial channel (if opened) and the unregistered linkage block.
SER2H is reserved for SNL until QL reset; stop other serial transfer tools
before installation. There is no driver unload operation yet.

The earlier code nested a serial IO.OPEN inside the SNL directory OPEN.
In the original QDOS JS ROM, trap #2 selects a free channel-table slot at
$32E0, invokes directory OPEN, and only installs the returned CDB into that
slot at $331E. The nested serial OPEN can select the same unfilled slot.
Outer SNL OPEN then overwrites the serial table entry, invalidating its ID.
This explains a successful host OPEN followed by Channel Not Open before
the next packet. The correction removes that nested channel allocation.

Reassemble/install V2.03 after a fresh QL reset, restart the current Linux
daemon, confirm the V2.03 banner, then LOAD snl1_trial_bas once. The next
Linux log should show a READ HEADER or READ request after successful OPEN.
Python has not changed for this fix. Hardware validation is still needed.

ROM disassembly source:
https://sinclairql.net/djw/qlrom/jsromdis.zip

Receive-path diagnostics (V2.04)
-------------------------------

The supplied Linux configuration now requests a 50 ms delay before replies
and 10 ms between reply bytes. Each paced byte is flushed to avoid a USB
write burst. This is a diagnostic setting, not a confirmed fix or a substitute
for correctly wired flow control. It significantly slows large transfers;
set both delay fields to zero later when the receive path is verified.

Try the paced daemon with the current driver first. If OPEN still fails,
V2.04 additionally prints `SNL serial result $xx` after the received-byte
counter: FF is Not Complete (the poll loop timed out or hit its retry bound),
F3 is the underlying serial Transmit Error, and FA is Channel Not Open.
This reports the last serial TRAP result before it is mapped to the public
error. A result of 00 means the last serial operation succeeded and the
failure occurred at protocol validation instead.

Cable confirmation
------------------

The user confirmed a cable carrying CTS, RTS, TX, RX and ground, already
tested at 9600 baud. The supplied config now enables `rtscts: true` so
Linux honors hardware flow control; startup must report rtscts=True.
Two stop bits and the diagnostic reply pacing remain enabled. This aligns
the daemon with the available cable signals; it does not establish that
the remaining receive-path fault is fixed.

First READ diagnostics (V2.05)
-----------------------------

The latest hardware trace shows successful OPEN followed by a successful
one-byte READ reply on Linux, then a QL Xmit Error. V2.05 prints transfer
failures as I/O error, original QDOS call, stage, reply-count high and low
bytes, received-reply byte count, and the underlying serial result. For
READ, stage 01 is request transmission, 02 status reception, 03 count
reception, 04 payload reception, 05 count validation. The reply counter is
reset per transfer packet. The one-byte READ should consume four reply
bytes: status=00, count=00 01, then one payload byte. These diagnostics
preserve all caller registers. No transfer logic was changed in this build.

The Python trace also logs READ/WRITE reply header bytes (status and count)
without logging payload contents. The existing Python can be retained for
the next QL test; update it only if the extra header log is useful.

Binary receive control test (no SNL installation)
------------------------------------------------

For the intermittent zero-byte OPEN timeout, reset the QL and do not install
SNL. On Linux stop the daemon, copy the updated script and run:

    python3 snl_serial --link-test

This mode does not run the file server. It waits for ASCII '~' and returns
exactly the five bytes from the observed successful OPEN reply, using the
same serial settings and configured pacing. Other bytes are ignored.

On the QL run serial_receive_test_bas, or type its commands as a short BASIC
program. INKEY$(#3,150) waits for each byte and reports either its numeric
value or TIMEOUT. Expected output is five lines with values 0, 0, 0, 0, 23.
This exercises the same binary response through normal user-mode QDOS I/O,
without SNL's nested zero-timeout polling. If it passes consistently, the
remaining driver receive loop is the next focus; failure here means the
same response also fails without SNL. Report QL values/timeouts and Linux
LINK TEST lines. Stop this mode before restarting normal file service.

Direct serial-driver calls (V2.06)
---------------------------------

The user-mode binary control test passed with exact values 0,0,0,0,23.
The serial format/cable can therefore carry the observed OPEN response;
the failing supervisor receive path remains the focus.

V2.06 removes nested TRAP #3 from the byte-polling helper. Installation
resolves the retained serial channel ID through SV.CHBAS and stores its
permanent CDB pointer at linkage+$50. File OPEN copies that pointer into
its spare area. The helper calls the serial CDB's own driver I/O entry,
with A0=serial CDB, A3=assumed serial driver base, A6=system variables,
D0=byte operation, D1=byte, D2/D3/D7=0 for initial entry. The call follows
the driver-entry setup in the QDOS JS trap #3 dispatcher. D4-D7/A4-A6 are
protected around each direct call; the outer helper preserves the remaining
registers. This retains the ROM queues, parity handling and interrupt
servers, while bypassing nested channel lookup, channel busy state and
job bookkeeping. The initial RTC deadline and retry bound remain.

This is a change to the driver receive path, not a confirmed hardware fix.
Reassemble/reset/install V2.06. Stop --link-test mode on Linux and restart
normal `python3 snl_serial` with the same working settings. Retry LOAD once
and capture diagnostics and RX/TX messages. No Python changes are needed
for this build. The permanent serial CDB must not be closed independently;
the transport remains reserved until reset.

Starting queued serial output (V2.07)
-------------------------------------

The original QDOS SER byte-write path queues data; it does not itself
start an idle UART. The ROM serial scheduler task does that. While SNL
waits synchronously in supervisor mode, normal scheduling cannot run.
A request can therefore stay queued until SNL returns with a timeout,
then reach Linux too late. A passing user-mode receive control test does
not exercise this queue-start problem.

V2.07 locates the standard ROM serial transmit scheduler callback through
SV.SHLST. It accepts only a base-ROM entry with the exact eight-byte
signature `40E7 007C 0700 51C4` (MOVE SR,-(A7), ORI.W #$0700,SR,
SF D4). No absolute ROM routine address is compiled in. At most 32 list
nodes are examined; unsupported ROMs fail installation explicitly with
`SNL ROM TX task unavailable $ED` and release the serial channel/heap.
This implementation targets the original QDOS ROM task structure; it is
not a general Minerva/SMSQ/E adapter.

The validated callback is saved at linkage+$54 and copied to each file
CDB. The byte helper services output before each attempt and after an
accepted send, with all D/A registers preserved and D3=1 to advance the
idle-port selection countdown. The ROM task itself checks UART busy and
CTS, protects its hardware work, and returns with its saved SR. This does
not run the scheduler or unrelated scheduler tasks. It retains normal
ROM queueing and IRQ reception.

Reassemble/reset/install V2.07, confirm its banner, restart the normal
Linux daemon (not --link-test), and retry LOAD. Python/config changes are
not needed. This corrects a concrete queue-start dependency seen in the
JS ROM source, but still requires validation on the user's actual ROM.
If installation reports the ROM task unavailable, record PRINT VER$ and
do not bypass the signature guard.

Source evidence in the JS ROM disassembly:
* SER byte write at $0BF4 calls queue insertion $3838.
* Serial scheduler task descriptor at $2D00 points to $2D14.
* $2D14 services the output queue through $2D74.
* Frame IRQ $0900 skips the scheduler for supervisor callers.
These addresses document the inspected source only; they are not used by
this driver build.

SAVE screen probe (V2.08)
------------------------

Hardware validation: V2.07 successfully loaded the 23-byte trial_bas and
LIST displayed `10 PRINT "hello worl"`. SAVE roundtrip_bas then opened in
NEW mode, wrote 25 bytes and closed successfully on Linux. Reloading that
saved file remains the next round-trip check.

SAVE additionally issued trap #3 operation $24. This is IOW.CLRR, a screen
clear-right request made by the ROM's common listing routine after writing
a line ($91B8 in the inspected JS ROM). The listing code ignores its return
value. V2.08 restores the original directory driver's handling of unsupported
non-file calls below $40: return err.bp (Bad Parameter) without an unsupported
file-operation message. No screen behavior is emulated and no bytes are
added to the file. Unsupported file calls at $40 and above retain their
Not Implemented diagnostics. Python and the wire protocol are unchanged.

Rebuild V2.08 at your convenience. The file already saved by V2.07 can be
checked immediately with NEW, LOAD snl1_roundtrip_bas, LIST; that check does
not require the new build.

Normal operation after confirmed LOAD/SAVE round trip
-----------------------------------------------------

The user confirmed SAVE created the changed BASIC program and NEW/LOAD/LIST
restored it on the physical QL. The supplied config now sets `trace: false`,
`reply_delay_ms: 0` and `inter_byte_delay_ms: 0`. The diagnostic delays were
50 ms per reply plus 10 ms between bytes; removing them is the main speed
improvement. RTS/CTS and two stop bits remain enabled. Burst replies with
these settings still need the user's next hardware run.

The daemon defaults to trace off. Per-packet output and its message formatting
are skipped unless trace is enabled. Normal startup retains the port/baud,
drive mappings and serial format; serial errors remain visible. Set trace
true and restore delay settings only when diagnosing a problem. Copy both
snl_serial and snl_config.json to Linux and restart the daemon. No QL build
is required. --link-test continues to print its dedicated test messages.

512-byte read-ahead buffer (V2.09)
----------------------------------

The driver now reads payload data into a 512-byte QL-side cache. IO.FBYTE,
IO.FLINE, IO.FSTRG and FS.LOAD all consume this same cache. The Python
protocol and config are unchanged; existing READ requests already support
512-byte blocks. The original direct serial-driver and guarded transmit-task
paths are retained.

The linkage allocation grows from $500 to $700 bytes. Its private stack
still ends at $4FF; the read buffer occupies $500–$6FF, so it cannot overlap
the stack. The one-open-file restriction allows a single shared buffer.
Per-file cache pointer, base offset, valid length and deferred status use
12 more bytes of the CDB spare area (ending at $7F in the $A0-byte CDB).
OPEN clears cache state before use, so a subsequent file cannot see stale
cached contents.

File position advances only when a byte is delivered to the caller, not
when prefetched. Line reads include LF and retain subsequent bytes for the
next call. Seeks within the cached window reuse it; seeks outside refill at
the requested absolute offset. Writes invalidate cached data/status before
sending data. Header operations do not alter the payload cache. Read-only
write rejection leaves a valid cache intact.

A short READ reply carrying EOF is fully received, then its data is served
normally. EOF is deferred until a caller reaches the cached end. Exact-size
reads can therefore succeed even when their prefetch encountered EOF.
Repeated EOF calls reuse the deferred result. A truncated transport reply
never publishes a partial cache; the existing dead-channel guard prevents
its reuse. Error diagnostics now print received-count high/low bytes to
cover replies over 255 bytes.

Verification
~~~~~~~~~~~~

At the V2.09 milestone, the regression suite passed 27 tests. For the current
suite, run `python3 -m unittest discover -s tests -t . -v` from the repository root.
The cache tests interpret the actual snl_xfer/snl_read/snl_fill assembly
source with a small instruction/CCR interpreter and route its generated
packets through the real Python receiver using temporary host files. This
checks transfer logic, register saves, stack balance and wire behavior; it
is not machine-code assembly/emulation and does not validate ROM timing.

Tests cover one-byte and line-by-line reads of the actual 1,714-byte
loader_bas (FOUR 512-byte READ requests in either case), newlines crossing
cache boundaries, line-buffer overflow, empty/exact-block EOF, binary and
>64 KiB reads, seeking, write invalidation, read-only rejection, writing after
cached EOF, malformed counts and interrupted replies. Existing receiver tests
also pass. Talent/Quanta assembly and hardware timing remain to be checked.

Hardware check
~~~~~~~~~~~~~~

1. Reassemble/reset/install V2.09. Keep the current Python daemon and config.
2. Time LOAD snl1_loader_bas, then LIST/RUN as appropriate to confirm contents.
3. For one diagnostic run, set Python config trace=true and restart it.
   For the current 1,714-byte loader, expect READ offsets 0,512,1024,1536,
   each requesting 512 bytes. The last reply is EOF with 178 bytes; the
   driver defers that EOF while delivering those bytes. Restore trace=false.
4. Repeat SAVE/NEW/LOAD/LIST with a new filename to check the write round trip.
5. Check a short file, a line longer than 512 bytes if your ROM accepts one,
   and a binary LBYTES case when convenient.

No performance number is claimed before hardware timing. This removes
per-character protocol round trips; ROM byte handling and the existing
serial polling overhead still apply.

## V2.29 metadata candidate

The current source adds FILE DATE ($19), FILE VERSION ($1C), and EXTENDED
INFO ($1D). See [metadata protocol and hardware tests](METADATA_TEST.md) for
request/reply layouts, date/version semantics and daemon compatibility.
