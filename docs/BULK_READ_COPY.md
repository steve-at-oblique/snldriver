# V2.22 candidate: bulk read-cache copy

Historical development notes: references below to `bin/snl_bin` describe the
old V2.15 distribution. The current release binary is `bin/snldriver228_bin`.

V2.21 passed the QIMSI Gold/SMSQ/E binary benchmark in Large QL Mode 4:
five 256 KiB overwrites took 11 seconds (116.36 KiB/s), while five loads took
23 seconds (55.65 KiB/s). Those are the comparison figures for this change.

## Change

SNL already receives payloads into its 512-byte cache with bulk serial I/O.
Previously it copied each cached byte into the application buffer individually,
rechecking the cache and updating file position/counts for every byte.

V2.22 copies the smaller of the remaining cache span and requested length in
one segment and updates the position/counts once per segment. With even source
and destination addresses it uses a longword copy loop and a byte tail. If both
addresses are odd it peels one byte to align them; if their parity differs it
uses a simple byte copy loop for that segment. This avoids address errors on
the original 68000 as well as the QIMSI FPGA processor.

IO.FLINE still scans bytes and stops immediately after LF, leaving the rest
cached. Cache refills, seeking, EOF/error deferral and partial-packet handling
are unchanged. Caller buffers receive only validated cache data. V2.21's bulk
write path, the daemon, configuration and wire protocol are unchanged.

Source-interpreter coverage includes every source/destination parity, tiny
copies and longword tails, 512-byte crossings, reads over 64 KiB, switching
between ordinary and line reads, memory guards, deferred errors, and transport
failure after earlier valid data. The interpreter now rejects unaligned
word/long accesses, and an instruction-count check confirms the aligned cache
copy avoids per-byte bookkeeping. This is not a cycle-accurate benchmark or
a replacement for assembly/hardware tests.

## Hardware test

1. Keep the working V2.21 binary. Assemble `SNLdriver_asm` with Talent/Quanta
   2.02 and save a separate candidate, for example `win1_snl222_bin`.
2. Reset before replacing the installed driver, then load and CALL the
   candidate with enough reserved memory for its actual binary size. Expect
   `SNL Device driver V2.22 serial debug`.
3. Check BASIC LOAD/LIST/RUN first: line reads are deliberately separate from
   the new ordinary-read path. Repeat SAVE/overwrite/reload, then run
   `tests/ql/binary_test_bas` with a fresh test filename. Require PASS.
4. Set daemon tracing off, use `CLS #1`, then run the unchanged
   `tests/ql/snl_throughput_bas` in Large QL Mode 4 with `reps=5` and a new
   SNL filename. Record read/write seconds, rates and PASS. If a batch takes
   less than ten seconds, increase repetitions for a more accurate estimate.
5. After passing, repeat in Large 16-bit mode and check directory/prefix
   listing and existing application loads. SD benchmarks need not be rerun.

No raw serial tool may run while SNL owns SER2. Original QL and Minerva
regression remain necessary before releasing a combined binary. The existing
distributed `bin/snl_bin` is not replaced by this source candidate.
