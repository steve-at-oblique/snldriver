# SNL and SD filesystem throughput on SMSQ/E

Use `tests/ql/snl_throughput_bas` after the correctness tests pass. No driver
reassembly is required. This program targets SMSQ/E's ALCHP/RECHP, POKE$ and
SBYTES_O facilities; it is not a stock-ROM QL benchmark.

## Run

1. Set `"trace": false` in Linux `snl_config.json` and restart the daemon.
   Leave reply pacing at its current setting and record that setting. Close
   other programs that produce substantial I/O or console output.
2. Copy the BASIC source into a Linux directory mapped to an SNL drive.
   For a mapping of drive 6 to `./drive6`, for example:

   ```sh
   cp tests/ql/snl_throughput_bas drive6/snl_throughput_bas
   ```

3. On QL:

   ```text
   LOAD snl6_snl_throughput_bas
   RUN
   ```

4. At the prompt enter a new disposable filename such as `snl6_bench1_bin`.
   The initial SBYTES deliberately refuses an existing file. The timed saves
   then overwrite only the file just created. Do not select a valuable filename.
5. Wait through preparation, timing, and the final byte comparison. Record
   PASS, WRITE seconds/KiB/s, READ seconds/KiB/s, and display mode.
6. RUN again with `win1_bench1_bin` for an SD-card comparison. The file consumes
   256 KiB on each device. Repeat in the other display mode, using fresh names.

## Meaning of the numbers

The program prepares a 262144-byte pattern containing all 256 byte values.
It creates one file outside the measured interval, then times five overwrite
saves and five loads, separately. Each batch transfers 1280 KiB of payload:

    KiB/s = 1280 / batch seconds

The timing includes BASIC command/loop overhead, filesystem OPEN/CLOSE,
header operations and, for SNL writes, the daemon's durability work. It excludes
pattern generation, payload clearing, byte verification and screen printing.
It measures useful application-level throughput, not USB bus bandwidth.

The timer is DATE, with whole-second resolution. A batch measurement may be
off by roughly one second. If a batch takes less than ten seconds, increase
`reps` on line 40 (for example to 20) and repeat for a better estimate. Do not
change the clock during a run. Actual rates may be below earlier pacing targets.

The final loaded buffer is checked byte-for-byte and sixteen guard bytes on
each side are checked. The five repeated loads are not individually verified;
this complements the separate integrity tests. The timed reads follow writes
to the same file, so caching can affect results: report these as repeated-file
reads, not cold-storage benchmarks. Test files are retained for inspection.

ALCHP memory is reclaimed on PASS or a detected data/guard failure. If BASIC
stops with an I/O error or you interrupt it after allocation, reclaim it once
with `RECHP p` while the benchmark's variable `p` is still valid, before RUN
again. Never RECHP it a second time after normal completion.

For an independent check of the SNL payload on Linux:

```sh
python3 tools/check_binary.py drive6/bench1_bin --length 262144
```

Use the actual configured host directory and filename. This checks the payload;
QDOS metadata is stored separately in `.snl_headers`.

Suggested result table:

| Device | Display mode | Operations per batch | Write seconds | Write KiB/s | Read seconds | Read KiB/s | Verification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SNL USB | Large QL Mode 4 | 5 | 122 | 10.4918 | 22 | 58.18182 | Timings reported |
| SD WIN1 | Large QL Mode 4 | 200 | 34 | 1505.882 | 11 | 4654.545 | Timings reported |
| SNL USB | Large 16-bit | 5 | 189 | 6.772407 | 34 | 37.64706 | Initial run PASS; cleared-screen rerun timings reported |
| SD WIN1 | Large 16-bit | 200 | 42 | 1219.048 | 16 | 3200 | Earlier 20-operation run passed; new run timings reported |

First user-reported SNL timing on 2026-11-10: five 256 KiB operations per
batch in Large 16-bit mode. The user confirmed daemon tracing was off and
both initial SNL and SD benchmarks finished with PASS. The initial SD WIN1
run used twenty operations per batch (5120 KiB), taking five seconds to write
and one second to read; that read interval was too short for a precise rate.
The subsequent 200-operation SD run transferred 51200 KiB per batch, taking
42 seconds to write and 16 seconds to read, as shown above. SNL used five
operations per batch (1280 KiB). Pacing settings were not explicitly confirmed.
These are repeated-file reads, which can benefit from filesystem caching.
The user clarified that the longer SD run followed `CLS #1`, then repeated
SNL6 with the same screen clearing: writes remained 189 seconds and reads
changed from 35 to 34 seconds. That read difference is within the approximate
one-second timing resolution; no material screen-clearing benefit is established.
Benchmark status printing is outside the timed batches, so its normal scrolling
is excluded from the measured intervals.
The user standardized subsequent comparisons on `CLS #1` before running and
reported the Large QL Mode 4 SNL6 result above. Compared with the cleared-screen
Large 16-bit SNL run, writes are about 1.55 times faster (189/122) and reads
about 1.55 times faster (34/22). Display mode affects both directions similarly;
the write/read asymmetry remains in both modes.
The subsequent WIN1 Large QL Mode 4 result used 200 operations per batch
(51200 KiB, consistent with the reported rates). Its writes took 34 seconds
and reads 11 seconds. Relative to Large 16-bit mode, SD writes are about
24% faster and reads about 45% faster. In Mode 4, SD is about 144 times
faster than SNL for overwrites and 80 times faster for repeated-file reads.
V2.20 writes invoked the serial
byte helper for every payload byte, while reads use bulk serial receive.
This is a candidate explanation for the asymmetry, not a measured profile.

## V2.21 bulk-write result — 2026-11-10

The user assembled the candidate on the QL using the running SNL driver,
copied the candidate binary to WIN1, reset, then installed from WIN1.
Standalone BASIC smoke tests were skipped for this iteration.

| Device | Display mode | Operations per batch | Write seconds | Write KiB/s | Read seconds | Read KiB/s |
| --- | --- | --- | --- | --- | --- | --- |
| SNL6, V2.21 | Large QL Mode 4 | 5 (consistent with rates) | 11 | 116.3636 | 23 | 55.65217 |

The user subsequently confirmed the benchmark finished with PASS in Large
QL Mode 4. The trace setting was not explicitly reconfirmed for this run.
Relative to the V2.20 Mode 4 baseline, writes improved
about 11.1 times (122/11). Read time changed from 22 to 23 seconds, within
the uncertainty of comparing whole-second measurements; no read regression
is established. Reads still copy cached payload to the caller one byte at a
time, checking cache position and updating counters for each byte. Bulk
serial reception alone does not remove that CPU overhead.

## V2.22 bulk read-cache copy result

The user reported PASS in Large QL Mode 4 with five 256 KiB operations per
batch: writes remained 11 seconds (116.3636 KiB/s), while reads took 16 seconds
(80 KiB/s), about 44% faster than V2.21's 23-second read batch. V2.23 adds
optional phase profiling to this V2.22 path; its results must be identified
as instrumented measurements rather than another optimization benchmark.
