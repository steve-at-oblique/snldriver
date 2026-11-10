# V2.21 candidate: bulk serial writes

V2.20 passed the first QIMSI Gold/SMSQ/E hardware tests. The write baseline
was 10.49 KiB/s in Large QL Mode 4 and 6.77 KiB/s in Large 16-bit mode.
Reads measured 58.18 and 37.65 KiB/s respectively. See
[the benchmark record](THROUGHPUT.md).

V2.21 changes only the QL-side payload transmission path. It still uses the
same SNL v2 wire protocol, daemon, configuration and 512-byte acknowledged
WRITE packets. Request headers continue to use the existing byte helpers.
Read, directory and timestamp behavior are unchanged.

## Implementation

`snl_bput` queues each payload using direct serial `IO.SSTRG` calls rather
than calling the serial byte helper for every byte. It resets the per-call
count and requests only the remaining bytes after partial progress. Both
partial success and partial ERR.NC are handled. Registers are protected
against the serial driver's permitted clobbering.

The caller's A1 is restored even though the underlying serial call advances
its own pointer. File position, byte count and caller buffer advance only
after the existing host acknowledgement, never merely because serial data
was queued. Earlier acknowledged blocks remain counted if a later block fails.

The validated legacy ROM transmit service is called before and after each
queue attempt, including partial batches. It remains a no-op for QIMSI USB
and sQLux, whose output drivers activate transmission themselves. This does
not establish hardware regression coverage for the original QL or Minerva.

The helper uses a three-second idle timeout, resets the deadline on progress,
and has a finite zero-progress retry budget even if the RTC stops. A serial
error or invalid count poisons the channel. It does not replay a partly sent
packet, nor acknowledge bytes that the host has not confirmed.

The direct-call convention was checked against the official SMSQ/E 3.43
`smsq/spp/io.asm`, `iod/iob/iox.asm` and `iod/iob/pmul.asm` sources. Source
interpreter tests exercise the new assembly against the real Python Session
and packet handler, with register clobbering, fragmented acceptance, errors,
timeouts, block boundaries, lost acknowledgements and >64 KiB round trips.
These checks do not replace Talent assembly or real IRQ/USB testing.

## Hardware test

1. Keep the hardware-tested V2.20 binary. Assemble the updated `SNLdriver_asm`
   with Talent/Quanta 2.02 and save a separate candidate, for example
   `win1_snl221_bin`. The distributed `bin/snl_bin` is not replaced here.
2. Reset before replacing the installed driver. Reserve enough memory for the
   actual candidate binary, load it and CALL it as described in
   [the QIMSI guide](QIMSI_SMSQE_TEST.md). Expect the V2.21 banner.
3. Use the existing daemon and QIMSI configuration. First repeat BASIC
   LOAD/SAVE/overwrite and `tests/ql/binary_test_bas`, with a fresh binary
   test filename. Require PASS before timing. Check recovery if the daemon
   is absent before OPEN; interrupted packets are not automatically replayed.
4. Set daemon `trace` false and restart it. Use `CLS #1` before each run.
   Run the unchanged `tests/ql/snl_throughput_bas` with `reps=5`, first in
   Large QL Mode 4, then in Large 16-bit mode. Use a fresh test filename.
   Record the V2.21 banner, mode, read/write seconds and rates, and PASS.
5. Compare with the V2.20 results. There is no need to rerun the SD benchmarks
   for this write-path change. If a timed batch is below ten seconds, increase
   repetitions for a better estimate with the whole-second timer.

Do not use raw serial tools while SNL owns SER2. On failure, record the QL
error and SNL transfer-stage/count/serial diagnostics before resetting.
The new payload path sets transfer stage 4 for diagnostics.
