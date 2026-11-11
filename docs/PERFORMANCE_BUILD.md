# V2.28 release: transfers without profiling instrumentation

The current source is V2.28, with 512-byte buffers and no profiling. Assemble
`win1_snldriver228_bin` and expect V2.28. The supplied release binary is
`bin/snldriver228_bin`. The daemon uses a 512-byte limit;
the previously deployed 1024-capable daemon also accepts 512-byte requests.

V2.28 addresses the stock QL's reported first-pass assembler failure while
reading `snl6_SNLdriver_asm`: error $F3, call $02, stage $02, no reply bytes,
serial result $FF. The bulk header receive introduced in V2.24 did not
service legacy serial output while waiting for a reply. IO.SSTRG can finish
queuing the request before all bytes reach Linux. The receive loop now calls
the validated ROM serial task when its callback exists, as the older byte
receive loop already did. QIMSI USB has no such callback and skips the call.

All 116 source-interpreter/daemon tests pass, including a regression where
queued request bytes only reach the daemon as the serial task is serviced.
Hardware regression testing now passes on the stock 128K QL and QIMSI Gold
USB under SMSQ/E. Both systems assembled V2.28 to identical binaries.

Confirmed checks include BASIC load/save and existing-file handling, binary
round trips with memory guards, Monitor and assembler loading, assembling and
saving the driver through SNL, DIR and prefix filtering, empty directories,
and missing files. Stock QL testing also passed daemon-missing command retry.
Stock QDOS reports an existing-file error; SMSQ/E offers the Y/N prompt.
Minerva remains unverified for this release.

The V2.28 throughput benchmark passed on QIMSI Gold USB in Large QL Mode 4:
**write 116.3636 KiB/s, read 85.33 KiB/s**, matching the V2.25 baseline.

V2.27 restored the V2.25 baseline after the V2.26 1024-byte experiment showed
no measured gain. The ordinary tests below still apply.

The diagnostic checkpoint is commit `13a347e` (V2.24). It contains the
profiling implementation, associated tests, BASIC runner, and reconciled
hardware results.

V2.25 retains QIMSI Gold/SMSQ/E support, bulk writes, aligned read-cache
copies, batched READ request/reply headers, and 512-byte payloads. It removes:

- all profiling calls, including disabled-state checks;
- timing/counter routines and their initialization;
- the SNLP image header and exported linkage pointer.

The ordinary entry is again the initialization BSR at offset zero. Load and
CALL it as before. Error diagnostics and readiness timeouts are retained;
they are functional driver behavior, not performance profiling. The daemon,
configuration, wire protocol and ordinary throughput benchmark are unchanged.
The following sections preserve the V2.25 development procedure and results.

## Historical V2.25 hardware test procedure

1. Keep the working V2.24 binary as a diagnostic reference. Assemble the
   current `SNLdriver_asm` with Talent/Quanta 2.02 into a separate binary,
   for example `win1_snl225_bin`.
2. Reset before installing the new binary. Allocate enough reserved memory
   for its actual size, LBYTES it and CALL the load address. Confirm V2.25.
   There is no need to record a load address for profiling.
3. Repeat BASIC LOAD/SAVE/overwrite and `binary_test_bas` with a fresh
   filename, then run the ordinary `snl_throughput_bas`, **not** the profiling
   runner. Require PASS for byte and memory guard checks.
4. Use Large QL Mode 4 initially, daemon trace off, unchanged reply pacing,
   and `CLS #1` before each run. Set `reps=20` on benchmark line 40 and use
   a new disposable filename such as `snl6_bench225_bin`.
5. Report PASS, write/read batch seconds and rates, display mode and reps.
   Then repeat in Large 16-bit mode when convenient. SD need not be retested.

With 20 operations, each timed batch transfers 5120 KiB, so:

    KiB/s = 5120 / batch seconds

V2.24's instrumented read-only run took 61 seconds for twenty loads
(83.93443 KiB/s). The earlier V2.22 ordinary Mode 4 benchmark took 11 seconds
for five writes (116.3636 KiB/s) and 16 seconds for five reads (80 KiB/s).
Report V2.25 numbers as a new measurement; removal of instrumentation does
not establish a speedup until tested on hardware.

## Diagnostic compatibility

`snl_read_profile_bas` is retained as a historical tool for V2.23/V2.24 only.
It must not be used to enable counters in V2.25, which has no SNLP layout.
The program's magic check should reject the uninstrumented image. To recover
the diagnostic source without changing the current working tree:

```sh
git show 13a347e:SNLdriver_asm > /tmp/snl224_asm
```

The five profiling-specific source tests were removed from the active suite
with their instrumentation; they remain in the checkpoint. The remaining
115 tests exercise the filesystem, transport, header batching, memory
alignment, cache behavior, failures, and OS/stack policies. V2.25 hardware results follow; V2.28 validation is recorded above.

## First V2.25 hardware result

User-reported PASS on SNL6 in Large QL Mode 4, with `CLS #1` before the run:

| Operations per batch | Write seconds | Write KiB/s | Read seconds | Read KiB/s |
| --- | --- | --- | --- | --- |
| 5 (consistent with reported rates) | 11 | 116.3636 | 15 | 85.3333 |

The first result used five operations, rather than the suggested twenty.
It establishes a passing uninstrumented hardware baseline. Writes match the
earlier 11-second result; reads improved from the V2.22 ordinary benchmark's
16 seconds to 15 seconds. That one-second difference is small relative to
the timer resolution. V2.24's instrumented twenty-load rate was 83.93443
KiB/s; the difference from 85.3333 KiB/s is too small to establish a precise
profiling overhead across different-length, whole-second runs. No further
run is required merely to accept this initial correctness result. Daemon
settings were not explicitly reconfirmed in this report.
