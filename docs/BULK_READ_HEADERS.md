# V2.24 candidate: bulk READ request and reply headers

This changes only the READ refill header path from the V2.23 profiling build.
It retains 512-byte payloads, the existing daemon/wire protocol, write path,
read-cache copy loop, diagnostic header layout and 50 Hz profiler.

## Implementation and checks

The request is assembled in eight bytes of stack scratch. Its seven wire
bytes start at scratch+1: command at +1, the four-byte offset at +2, and the
two-byte count at +6. This keeps the word/long stores aligned on the 68000.
Only seven bytes are transmitted through `snl_bput`; the padding is not sent.

The same scratch space receives the three-byte status/count header through
`snl_bget`. The signed status is checked with the same valid-error bounds as
the byte status helper. The unaligned count at wire bytes 1 and 2 is decoded
bytewise, not with a word read. Existing count limits, short-EOF behavior and
deferred errors remain. Every exit reclaims the scratch, including failures.

Tests execute the source against the Python packet handler, checking exact
request bytes, partial request acceptance, fragmented and truncated headers,
invalid statuses/counts, underlying driver errors, register clobbering, memory
alignment, cache integrity and stack balance. These remain source-level tests;
Talent assembly and hardware testing are required.

## Hardware comparison

1. Keep working V2.22/V2.23 binaries. Assemble `SNLdriver_asm` as a separate
   candidate, for example `win1_snl224_bin`.
2. Reset, allocate sufficient memory, load and CALL the candidate. Confirm
   the V2.24 banner and print/write down `HEX$(base,32)` using the actual load
   address variable, exactly as in the prior profiling run.
3. Use the same Linux daemon and settings, Large QL Mode 4, tracing off,
   and `CLS #1` before running.
4. Run your existing `snl_read_profile_bas` with the **new** driver's load
   address and the same existing 256 KiB benchmark file. No BASIC program
   update is required: V2.23 and V2.24 share the SNLP header and statistics
   offsets. An older prompt may still say V2.23; enter the V2.24 address.
5. Report PASS/FAIL, wall seconds, all four phase timings, and counters.
   The work remains 20 loads, 10240 refills, and 5242880 payload bytes.

V2.23 baseline from the screenshot:

| Phase | Ticks | Seconds |
| --- | --- | --- |
| Request | 333 | 6.66 |
| Reply header | 1130 | 22.60 |
| Payload receive | 1744 | 34.88 |
| Cache copy | 64 | 1.28 |

Wall time was 66 seconds, 77.57576 KiB/s; data and guards passed. Look at total
wall time as well as individual phases: changing the request timing may move
waiting between phases, and 50 Hz sampling is approximate. No speedup is
claimed before measurement. Payload receive counters exclude the three-byte
reply-header calls, as before. Once profiling passes, repeat BASIC LOAD and
the binary round-trip test to check application-level behavior.

## First hardware report

V2.24 passed final payload and guard verification on twenty loads: wall time
61 seconds, read throughput 83.93443 KiB/s, versus V2.23's 66 seconds and
77.57576 KiB/s (about 8.2% higher throughput).

Reported phases: request 76 ticks (1.52 seconds), reply header 1089 ticks
(21.78 seconds), payload 1747 ticks (34.94 seconds), cache copy 69 ticks
(1.38 seconds). Accounted phase time was 59.62 seconds, residual 1.38 seconds.
The user corrected the initial request-count transcription from 26 to 76
ticks, confirming the 1.52-second request time and phase sum.

Counters were reported as 10240 refills, 5242880 received bytes, 5242880
copied bytes, 10240 payload receive calls, zero empty calls, and 10240 copied
segments. The user corrected the initial copied-segment transcription from
10249 to 10240; all work counters now match the expected twenty loads.
Display mode and daemon settings were not separately reconfirmed in this
report. Payload receive time remains essentially unchanged from V2.23;
bulk header handling did not remove the dominant payload-receive cost.
