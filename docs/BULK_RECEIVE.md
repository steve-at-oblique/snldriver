# V2.10 bulk serial receive

The banner identifies this build as `SNL Device driver V2.10 serial debug`.
Reassemble and reset/install as usual. Keep the current Linux daemon and
config, with trace off and both reply delays zero. No protocol changes.

The current canonical source is `SNLdriver_asm`, with the constants included
and SYM output disabled. This permits assembly through SNL's current single
open-file implementation; no include file is required.

## What changed

`snl_bget` calls the existing serial driver's IO.FSTRG entry with the remaining
length, initially up to 512 for a READ payload or 64 for a file header. Each
invocation starts D1 at zero and uses the returned count to advance to the
next batch. Partial returns, including ERR.NC with some bytes, are accepted.
Status/count protocol fields still use the proven byte helpers. Sending is
unchanged.

The payload loop does not call the transmit task: reaching this point already
requires Linux to have received the request and sent a reply. The receive
loop times out after three seconds without progress, also retaining a finite
retry bound for a stopped RTC. Other serial errors poison the channel, as
before; partial exchanges cannot be safely replayed.

The 512-byte cache is published only after the whole reported payload arrives.
Header replies are received into 64 bytes of temporary private-stack storage,
then copied to the caller's requested 14–64 byte area. This drains all wire
bytes without overwriting a short header buffer. Failed header receives return
zero delivered bytes and leave the caller's memory untouched.

The outer SNL file operation, serial channel ownership, hardware flow control,
ROM transmit task signature check, cache size and memory allocation are
unchanged. The original byte-based helper remains for protocol fields.

## Hardware checks

1. Assemble/install V2.10 and confirm the banner. Test a short BASIC LOAD/LIST.
2. Run `binary_test_bas` with a fresh output filename; expect zero byte and
   memory guard errors. This exercises SBYTES/LBYTES and file headers.
3. Run `EXEC snl1_monitor` (using the drive where you keep it) to check the
   executable header and binary loading path.
4. Time the same Abacus LBYTES operation as before. Its actual payload is
   51,644 bytes; the host file includes a 30-byte emulator wrapper. Reserve
   memory once, using your actual drive and filename:

```text
p=RESPR(51674)
LBYTES snl3_abacus,p
```

Start timing at Enter on LBYTES and stop when BASIC returns. Reuse the same p
for repeat LBYTES timings. The baseline is 96 seconds, about 538 payload
bytes/second. At 9600 baud, 8N2, payload plus 101 READ request/reply headers
needs about 60.3 seconds on the wire. No new hardware speed is claimed yet.

If receiving fails, preserve the on-screen stage/count/serial diagnostics and
the V2.10 banner. A partial packet may require restarting the daemon and
resetting/reinstalling the driver before another attempt.

## Local validation

48 tests pass. The source interpreter now executes the bulk receiver and the
header-copy path, stubbing the ROM IO.FSTRG entry and RTC. Tests cover empty
polls, fragmented progress, error after partial data, bad counts, idle timeout,
stopped-clock retry bounds, preserved registers, zero-length receive, short
header buffers, and no publication of partial payload/header data. Existing
server, cache, write, and emulator-wrapper regressions still pass.

The reference JS ROM disassembly's IO.SERIO/IO.FSTRG path returns the completed
count in D1 and advances A1 on partial reads. No ROM code addresses have been
added to the driver. These are source-level checks, not Talent machine-code
assembly or physical serial timing tests.
