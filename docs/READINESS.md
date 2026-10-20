# V2.13 readiness handshake

Update `snl_serial` on Linux and assemble/install the V2.13 driver. The daemon
prints `Readiness handshake: enabled` on startup. Both sides must be updated;
an older daemon cannot answer the probe. Keep trace off and reply delays zero.

Use `SNLdriver_asm`, the combined source without INCLUDE/SYM file opens.
After assembling, use the
new binary's actual length in the bootstrap loader. Reset and install as usual;
do not install over a driver already owning SER2. The banner reads
`SNL Device driver V2.13 serial debug`.

## Expected behavior

Before OPEN or DELETE, SNL sends a readiness probe. Only a complete reply with
the current token allows the file request to be sent. With the daemon absent,
the call returns a transmit error after a few seconds. The temporary CDB and
lock are not retained. Start the daemon and repeat the same command; a QL reset
should no longer be needed for this missed-startup case.

Stale bytes, partial reply prefixes and old readiness replies are discarded
while looking for the current matching response. The daemon also recognizes a
fresh probe after an interrupted probe and closes any stale host file session
before answering. The probe itself never opens, writes or deletes a file.

SNL checks its existing one-file lock before probing. A second operation while
a QL SNL channel is active still returns In Use; it cannot reset the host file
under the active channel.

This addresses absent-daemon startup and delayed readiness replies. It does
not implement general recovery from an interrupted binary READ/WRITE packet
or automatically retry writes/deletes with uncertain outcomes. Those still
require the existing recovery procedure. No file operation is replayed here.

## Cost and format

Probe: `~SNL?` + 16 ASCII A..P nibbles + LF (22 bytes).
Reply: `~SNL!` + the same 16 nibbles + LF (22 bytes).

The token contains the installation RTC epoch followed by an incrementing
32-bit attempt counter. Both use eight big-endian printable nibbles. Probe
bytes avoid the binary command range, so an old daemon or one starting in
the middle of a probe can discard its tail without treating it as a file
command. The daemon restarts probe parsing upon another tilde.

At 9600 baud, 8N2, the 44 bytes require about 50 milliseconds on the wire,
plus processing time. This is once per file OPEN/DELETE, not per read/write
block. The larger token deliberately distinguishes attempts as well as driver
installations. The driver allows a bounded interval of roughly three seconds
for matching and also limits retries if the RTC stops.

The two token longs use linkage offsets $58 and $5C, inside the already-cleared
first $60 bytes. Stack allocation and the 512-byte cache remain unchanged.
No hard-coded callable address or special user recovery command is required.

## Hardware test

1. Install V2.13 and confirm an ordinary LOAD works with the updated daemon.
2. With no SNL file open, stop the Linux daemon. Try `LOAD snl3_boot` or another
   known existing BASIC file. Expect a transmit error after a few seconds.
3. Start the daemon and repeat that LOAD without resetting the QL or reinstalling
   SNL. The file should load normally. Repeat the stopped-daemon test if useful.
4. Confirm SAVE/DELETE and the monitor's overwrite prompt still work using a
   disposable filename.
5. Optionally repeat the Abacus LBYTES timing. The previous V2.10/V2.12 baseline
   is about 68 seconds; this adds only one handshake before opening the file.

## Local validation

72 tests pass. Source-level driver tests exercise the actual token encoder,
matcher and nonblocking ROM receive wrapper, with ROM/RTC boundaries simulated.
They cover absent daemon followed by startup and retry with an old reply
queued, wrong tokens, noise and partial prefixes, repeated failed attempts,
stale host sessions, active-channel protection, and stopped-clock bounds.
Server tests cover the echo, interrupted probes, malformed probes, and startup
in a probe's tail. Existing bulk-transfer, delete, metadata and case tests pass.

Hardware IRQ timing and Talent machine-code assembly remain to be tested on
the QL; no new hardware timing result is claimed.
