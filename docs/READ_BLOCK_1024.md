# V2.26 candidate: 1024-byte READ blocks

**Historical experiment, reverted in V2.27.** Current driver and daemon use
512-byte blocks/cache again. Bulk writes, cache copying, batched READ headers
and the removal of profiling are retained.

V2.25 is the hardware-tested, uninstrumented 512-byte baseline: Mode 4 write
116.3636 KiB/s and read 85.3333 KiB/s, with PASS. Keep its binary.

V2.26 doubles READ request size and cache capacity to 1024 bytes. WRITE
packets remain 512 bytes to isolate the read-size change. The driver remains
uninstrumented and keeps one acknowledged exchange at a time. Its linkage
allocation grows from `$700` to `$900`: exactly 512 extra bytes, with the cache
still starting at `$500`. The stack and channel-state layout do not move.

The source constants are `snl_rblk=1024` and `snl_wblk=512`. The daemon's
MAX_BLOCK is raised to 1024; packet formats and protocol version are unchanged.
The updated daemon still supports earlier 512-byte drivers. The new driver
requires the updated daemon: an old daemon will reject the larger READs.
Disk-space reporting continues to use 512-byte sectors; directory records
remain 64 bytes. Larger blocks do not add checksum/retransmission support.

## Deploy both ends

1. Copy the updated **snl_serial** to Linux and restart the daemon. Keep your
   QIMSI configuration, especially `/dev/ttyACM0`, RTS/CTS false, XON/XOFF
   disabled, and your drive mappings. Startup should now include:

   ```text
   Maximum READ/WRITE payload: 1024 bytes
   ```

2. Assemble `SNLdriver_asm` as a separate candidate, for example
   `win1_snl226_bin`. The updated daemon can serve the running V2.25 driver
   while you transfer source or assemble. Preserve the V2.25 binary on WIN1.
3. Reset before replacing the driver. Allocate sufficient reserved memory
   for the actual assembled binary, load and CALL it normally. Confirm V2.26.
   There is no profiler address or SNLP header in this build.

## Correctness before speed

Start in Large QL Mode 4. Repeat BASIC LOAD/LIST, SAVE/overwrite/reload,
then run `binary_test_bas` with a fresh destination filename. Require PASS.
For targeted boundaries, set line 20 to each of `n=1023`, `n=1024`, and
`n=1025`, changing line 30 to a fresh filename each time. The test uses
RESPR and retains its allocations until reset; these three small runs use
only a few KiB. The normal 1537-byte test also crosses the new boundary.

Then run the unchanged ordinary `snl_throughput_bas`, daemon tracing off,
`CLS #1`, and `reps=20`, with a new disposable filename such as
`snl6_bench226_bin`. Report PASS, batch seconds, and write/read rates. This
transfers 5120 KiB per timed batch. Do not use the historical profiler runner.

Twenty 256 KiB loads now need 5120 READ exchanges, versus 10240 at 512 bytes.
The previous profile suggested a possible read target around 100–105 KiB/s,
but this remains an estimate; only hardware measurements establish the gain.
Payload processing still handles the same total bytes. Writes should be
comparable to the baseline because their block size/path is unchanged.

Repeat correctness and throughput in Large 16-bit mode. Also check directory
and prefix listings: the cache now holds sixteen 64-byte directory records.
The larger reply is 1027 bytes including status/count, so repeated integrity
tests in both display modes are important before adopting it as the default.

On a failure, report exact error/diagnostics and keep any partial test files.
To roll back, reset and install your V2.25 binary; the new daemon supports it,
so no Linux downgrade is necessary. There is no automatic block-size
negotiation or runtime fallback in this experiment.

## Local checks

Source-interpreter and wire-level tests cover all byte values, 1023/1024/1025
lengths, >64 KiB transfers, exact EOF, odd/even buffer addresses, cache and
caller guards, fragmented payloads, last-byte truncation, malformed counts,
and partial-packet failures. Existing 512-byte wire tests verify daemon
compatibility; write block boundaries remain 512. Source interpretation
does not validate FPGA/OS receive timing or replace Talent assembly.

## First hardware timing

The user confirmed daemon startup maximum 1024 and driver banner V2.26.
Large QL Mode 4 read result: 15 seconds, 85.3333 KiB/s, consistent with five
256 KiB loads. The user subsequently confirmed PASS and a traced reply length
of 1027 bytes, establishing that the larger payload was active. Write timing
was not supplied.
This matches the first V2.25 512-byte baseline at whole-second precision;
the predicted speedup has not been demonstrated. The estimate assumed much
of the prior header-phase time was fixed per exchange, which the profile
did not establish. Traced 1027-byte replies confirmed 1024 payload bytes.
Payload handling,
receive batching/interrupt behavior and overlapping wait time remain
possible explanations; this result does not identify one of them uniquely.
