# V2.36: batched headers and frame-timed ROM service

The source and distributed binary are V2.36. `bin/snldriver236_bin` is
5,012 bytes and was assembled and tested by the user.
No daemon protocol or configuration change is required for this optimization.
The separate timestamp update to the daemon also remains compatible.

## Change

READ and WRITE requests have the same 12-byte wire header:

```text
$22 | handle.l | command.b | offset.l | count.w
```

V2.33 sends READ with six byte-send calls and a six-byte string send, and
WRITE with twelve byte-send calls before the payload. V2.34 builds the entire
header in temporary stack storage and sends it with one IO.SSTRG-based call.
WRITE payloads retain their existing bulk send and acknowledgment handling.

The four handle bytes occupy an odd wire offset and are copied individually
into scratch; no unaligned word/long access is used. The offset and count
fields are aligned. Scratch and registers are restored on success or failure.
Partial headers resume from the remaining bytes without replay; transport
errors poison the channel as before. Per-channel caches and allocation policy
are unchanged. The wire still contains 12 header bytes, with no padding.

## Timing baseline

User-reported QIMSI/SMSQ/E results before batching, with trace disabled:

| Repetitions | Payload per operation | Write seconds | Write KiB/s | Read seconds | Read KiB/s |
| --- | --- | --- | --- | --- | --- |
| 5 | 256 KiB | 12 | 106.667 | 16 | 80 |
| 20 | 256 KiB | 49 | 104.4898 | 65 | 78.76923 |

The older V2.28 five-operation reference was 11 seconds writing and 15
seconds reading. Whole-second measurements make the shorter runs approximate;
use 20 repetitions for the primary comparison. V2.34 hardware results are recorded below.

## Hardware test

1. Assemble the updated source with Talent/Quanta 2.02 and save separately as
   `snldriver236_bin`. Check the assembled length when reserving loading
   memory. Reset before loading/CALLing it; expect V2.36.
2. Run `snl_channels_bas`, the binary round-trip/guard test, and a short
   SNL-to-SNL COPY/WCOPY check. Expect the same correct contents and headers.
3. Run the same throughput program in the same QIMSI display mode, with
   `n=262144: reps=20` on line 40. Keep the host, serial connection, pacing
   settings and logging settings consistent with the baseline; keep trace off.
   Use a fresh benchmark filename, or delete the old file with QL DELETE.
   Report elapsed seconds/rates and the integrity/guard result. Repeat once.
4. On stock QDOS, assemble and run the binary and multiple-channel smoke tests
   to check serial queued-output handling. The throughput BASIC program itself
   targets SMSQ/E; it is not suitable for the unexpanded 128K QL.

Automated suite: **188 tests pass**. Tests exercise exact wire bytes, one
header string send, handle-byte encoding, register/stack restoration, partial
sends, failure without replay, block boundaries, acknowledgments, and existing
multi-channel behavior. Talent assembly and hardware timing remain required.

## V2.34 hardware throughput — QIMSI/SMSQ/E

The user reported the 20-repetition throughput results:

| Version | Write seconds | Write KiB/s | Read seconds | Read KiB/s |
| --- | --- | --- | --- | --- |
| V2.33 baseline | 49 | 104.4898 | 65 | 78.76923 |
| V2.34 batched headers | 39 | 131.2821 | 60 | 85.3333 |

Write throughput increased **25.6%** (10 seconds less elapsed time); read
throughput increased **8.3%** (5 seconds less). The reported rates correspond
to 20 x 256 KiB = 5120 KiB per direction. The user reported the SMSQ/E assembly, channel and benchmark checks passed.
A repeat timing run has not been reported.

Stock QL with TK2 v2.36: V2.34 failed. The diagnostic and host file comparison
confirmed four bytes with bit 7 spuriously set at offsets 77, 517, 836 and
1142. Source and copy were identical, so the corruption occurred before the
copy. The same channel diagnostic passed with V2.33. The precise timing or
ROM interaction responsible has not been established.

## V2.36 timing correction

Both stock serial and QIMSI use the complete 12-byte header batch. The
proposed V2.35 stock fallback was superseded before hardware validation.

The old `snl_kick` passed D3=1 on every invocation. In the JS ROM transmit
service, D3 is subtracted from the serial port-switch timeout at $2E04. It
represents elapsed scheduler frames, not the number of service calls. Busy
polling therefore consumed the timeout without waiting for real frames.
The ROM resets this timeout after placing a byte in the UART. Premature
port selection changes are a plausible explanation for the observed high
bits; the hardware cause remains unconfirmed.

V2.36 reserves one unused CDB word at `fs_spare+44` for the last frame
counter. OPEN, I/O and CLOSE establish a baseline from SV.POLLM ($30).
Each ROM-service call receives the actual unsigned word difference and
updates that baseline. Repeated calls within a frame pass zero; the ROM
still checks UART busy, CTS, and output queues on every call. QIMSI has no
ROM-service callback and remains unaffected. No delay loop or new cache
allocation is added.

The reference JS ROM source is distributed in
[jsromdis.zip](https://sinclairql.net/djw/qlrom/jsromdis.zip), `system_asm`:
frame IRQ $0900 increments SV.POLLM; the scheduler supplies elapsed frames
in D3 at $0936; TX service $2D14 calls $2D74; $2E04 subtracts D3 from the
port-switch timeout. These addresses document the source only and are not
compiled into the driver.

Tests now execute the actual `snl_kick` wrapper with a simulated ROM callback.
They verify zero elapsed frames across 100 polls, a two-frame increment,
counter wrap, and register preservation even when the callback clobbers all
registers. They also verify batched READ/WRITE on the stock profile.

For the stock retest, assemble V2.36 and load the updated `snl_channels_bas`.
It prints diagnostics revision 4 and uses fresh `mc236_src`/`mc236_dst` names.
Run it several times with fresh names or delete only those two test files
between runs. Retest QIMSI channel and throughput checks after stock passes.

### V2.36 hardware result

The user reported **PASS on stock QL/TK2** for the channel diagnostic after
assembling V2.36. This retains batching on stock serial and is consistent
with the timing correction addressing the V2.34 regression. The subsequent hardware photo shows six consecutive revision-4 PASS results
for SNL-to-SNL COPY and three channels. Stock repeat testing is complete for
this regression. The precise physical mechanism is not independently proven.
QIMSI: the user reported six channel-diagnostic passes, followed by the
20 x 256 KiB benchmark: write **40 seconds / 128 KiB/s**, read **60 seconds /
85.3333 KiB/s**. Versus V2.33 (49/65 seconds), throughput increased **22.5%**
writing and **8.3%** reading. The one-second write difference from V2.34's
39-second result does not establish a regression with whole-second timing.
The stock and QIMSI regression checks for this optimization are complete.
