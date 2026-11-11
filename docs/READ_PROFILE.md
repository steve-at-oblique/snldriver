# V2.23 diagnostic build: read-phase profiling

Historical guide for V2.23/V2.24. The diagnostic implementation is preserved
in local commit `13a347e`; current V2.25 source removes the instrumentation
and SNLP interface. Use [the performance-build guide](PERFORMANCE_BUILD.md)
for the current source and ordinary benchmark.

This is an instrumented V2.22, not a speed optimization. Keep the working
V2.22 binary. Request size, wire protocol, daemon and cache behavior remain
unchanged. Profiling is off until explicitly enabled by the BASIC runner.
No diagnostics are printed during timed loads.

## Build and run

1. Assemble `SNLdriver_asm` and save a separate binary, for example
   `win1_snl223_bin`. Reset before installing it.
2. Install from WIN1 using enough memory for its actual size (8192 below
   is valid only if the binary fits):

   ```text
   snlbase=RESPR(8192)
   LBYTES win1_snl223_bin,snlbase
   CALL snlbase
   PRINT HEX$(snlbase,32)
   ```

   Confirm the V2.23 banner. **Write down the hexadecimal address printed by
   PRINT HEX$(snlbase,32)**: loading the BASIC runner can clear that variable.
   Plain PRINT may round a large address when displaying scientific notation.
3. Start the unchanged daemon with tracing off and the same pacing settings
   as before. Use Large QL Mode 4 and `CLS #1` for the first run.
4. Put `tests/ql/snl_read_profile_bas` in the directory mapped to an SNL drive.
   On QL, for example:

   ```text
   LOAD snl6_snl_read_profile_bas
   RUN
   ```

5. Enter the hexadecimal driver load address from step 2 without a `$` prefix
   or quotes, then the name of an
   existing 262144-byte file created by `snl_throughput_bas`. This is a
   **read-only test of that file**; it does not create or overwrite it.
6. The program performs twenty loads, then checks the final all-byte pattern
   and guards. Send back PASS/FAIL and all timing/counter lines. At the prior
   80 KiB/s rate, the timed part takes about 64 seconds, plus verification.

The allocation is released on normal completion or a detected data mismatch.
If an I/O error or interruption stops the runner, type `POKE l+100,0` to
disable profiling; reclaim its ALCHP allocation once with `RECHP p` if it
was allocated and has not already been released. Do not use raw serial tools
while SNL owns SER2.

## What is measured

The profiler accumulates SMSQ/E `sys_pict` polling ticks at 50 Hz. It uses no
nested timing trap and no hardware-specific timer register. Each short phase
handles the 16-bit tick wrap modulo 65536. Twenty loads provide enough samples
to identify the dominant phase, but the timer is still coarse: very short
phases may get few or no ticks. Treat small differences as approximate.

- **REQUEST:** sending the seven-byte READ request using the existing byte
  helpers. USB transmission and Linux processing may overlap this phase.
- **REPLY HEADER:** obtaining the status byte and two-byte payload count,
  including any waiting for Linux/USB. This is not purely CPU time.
- **PAYLOAD RECEIVE:** draining the payload through the serial driver, including
  receive waits and interrupts while this phase is active.
- **CACHE COPY:** copying each validated cache span to the caller's buffer.

Phase attribution is elapsed time, not exclusive CPU profiling. Interrupt
work is charged to whichever phase was active, and the overhead of sampling
is not fully excluded. Wall time also includes OPEN/CLOSE, file headers,
other bookkeeping and gaps outside these phases. The whole-second wall timer
and per-phase rounding can make the residual imprecise or slightly negative.

For twenty exact 256 KiB loads, successful counters should normally show:

- 10240 refills (512 blocks per load);
- 5242880 payload bytes received;
- 5242880 bytes copied;
- 10240 copied segments.

Serial payload receive calls may exceed refills if a block arrives in multiple
batches. Empty-call count reveals polling without progress. File-header reads
are deliberately excluded from these payload counters. Unexpected extra
requests should be investigated rather than interpreted as throughput.

## Diagnostic interface

Entry offset zero remains callable. The image begins with a fixed four-byte
word-displacement BRA, followed by `SNLP` magic at offset 4 and an installed-linkage pointer
at offset 8. The pointer is published only after successful registration.
The runner checks the magic, pointer and QIMSI profile before enabling it.

Linkage fields (all offsets hexadecimal): `$64` enable byte, `$66` active
phase word (`-1` means idle), `$68` last tick word; `$70/$74/$78/$7C` phase
tick totals; `$80` refills, `$84` payload bytes, `$88` copied bytes, `$8C`
payload receive calls, `$90` empty calls, `$94` copied segments. Clear/reset
only when no SNL operation is active. These fields lie below the private
stack starting at `$100`; the read cache remains at `$500`.

The runner is specific to this diagnostic layout. These are experimental
diagnostic fields, not an application ABI or new wire protocol.

Talent/Quanta 2.02 rejects the `BRA.W boot` spelling. The four-byte branch
is therefore emitted explicitly as `DC.W $6000` followed by `DC.W boot-*`.
The displacement is relative to the extension word at offset 2, preserving
the fixed header layout without relying on assembler branch-size selection.

## First hardware result

Transcribed from the user's IMG_9807.png. V2.23 returned PASS for final data
and guards on twenty loads of `snl6_bench4_bin`:

| Measurement | Ticks | Seconds |
| --- | --- | --- |
| Request | 333 | 6.66 |
| Reply header | 1130 | 22.60 |
| Payload receive | 1744 | 34.88 |
| Cache copy | 64 | 1.28 |
| Accounted phases | 3271 | 65.42 |

Wall time was 66 seconds, read throughput 77.57576 KiB/s, and wall minus
accounted phases 0.58 seconds. Counters: 10240 refills, 5242880 payload bytes
received, 5242880 bytes copied, 10240 payload receive calls, zero empty calls,
and 10240 copied segments. All match the expected work. The screenshot does
not separately identify display mode or daemon settings.

Cache copying was approximately 2% of wall time; further tuning that loop
alone cannot produce a large overall gain. Payload receive accounted for
about 53%, reply-header handling/waiting 34%, and request sending 10%.
Every payload was accepted in one call, so repeated empty/partial payload
polling is not the dominant cause in this run. These are elapsed phases:
the profile does not distinguish serial-driver CPU work from interrupt work
or identify how much of reply-header time was waiting for Linux/USB.
