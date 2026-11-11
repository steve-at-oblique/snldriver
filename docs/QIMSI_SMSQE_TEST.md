# V2.20 candidate: SMSQ/E on QIMSI Gold

Historical development notes: references below to `bin/snl_bin` describe the
old V2.15 distribution. The current release binary is `bin/snldriver228_bin`.

The results below describe V2.20. The current development source is the
[V2.27 uninstrumented 512-byte build](PERFORMANCE_BUILD.md); use that guide for the current
candidate filename, expected banner and regression steps.

This source candidate adds automatic selection of the QIMSI Gold USB SER2
transport. Initial hardware tests have passed as recorded below; broader
validation is still required before release.
The existing `bin/snl_bin` has **not** been replaced: assemble the updated
`SNLdriver_asm` into a separate candidate such as `win1_snl220_bin`.

## Hardware results — 2026-11-10

User-reported passes on the physical QIMSI Gold running SMSQ/E over USB SER2:

- BASIC LOAD and SAVE.
- Overwrite with the expected yes/no confirmation.
- `tests/ql/binary_test_bas`: binary save/reload, byte comparison and memory
  guards passed.
- Directory listings and filename-prefix filtering.
- Empty directories and missing-file handling.
- Missing-daemon recovery.
- Executable loading: Monitor and Talent assembler ran; the assembler
  successfully assembled the old SNL source.
- Talent ZIP extraction from `win2_` to `snl6_` completed and the extracted
  Monitor ran. The driver reported unsupported I/O `$4C` (IOF.DATE), so
  timestamp restoration through that operation is not supported. No explicit
  CRC-verification report was supplied.

The user subsequently confirmed all tests passed in Large 16-bit mode
(1024x512), in addition to the earlier Large QL Mode 4 testing. Performance
was reported as subjectively slower in Large 16-bit mode; no SNL throughput
timing has yet been recorded.

Extracting a ZIP from `snl6_` to `snl6_` did not work, consistent with the
existing one-open-SNL-channel limitation across all SNL drives. This is not
a supported extraction path; keep either the archive or destination on a
non-SNL device.

These results complete the first BASIC, binary and directory smoke tests.
The exact SMSQ/E build, serial configuration and assembled
binary checksum were not supplied with this result report. No throughput
measurement is claimed for SNL itself. Broader executable-metadata checks,
deletion, explicitly sized large-file byte comparisons, and original
QL/Minerva regression remain to be checked.

## Selection and compatibility

Initialization obtains the system-variable pointer with MT.INF. It checks
the `SMSQ` system identifier and then the machine byte at offset `$A7`, masked
with `$1F` just like the BASIC MACHINE function. Machine 21 (`sys.mqig` in
SMSQ/E 3.43's `keys/sys`) selects QIMSI Gold and opens `SER2IDR`:

- I: no flow control;
- D: no output translation;
- R: raw carriage-return handling;
- no Z suffix: all byte values, including Ctrl-Z, are payload.

Other SMSQ/E machines are rejected with Not Implemented rather than guessed
to be compatible. Existing QDOS and validated Minerva/sQLux paths remain.
This is not a claim of standalone Q68, QIMSI under Minerva, or QL-mode SER4
support. The QIMSI profile requires a working USB-capable SMSQ/E build
(3.43 or later); it does not infer USB availability from MACHINE alone.

Private file-channel fields now occupy `$70..$97`, within the common spare
area ending at `$A0`. SMSQ/E-owned fields `$58..$6F` are left untouched.
The profile uses the existing private stack: Q68 trap/interrupt handlers
obtain sysvars from `sms.sysb`, independently of the stack address. The
validated Minerva path continues to use its native stack.

SMSQ/E's SPP serial I/O activates its own output interrupts. QIMSI skips the
QL ROM scheduler scan and leaves the ROM transmit callback zero. Registration,
channel resolution, file-count ownership, and CLOSE retain the QDOS-compatible
conventions implemented by SMSQ/E's `sms/link`, `ioa/opfl`, `ioa/clos`,
`io/ckchn`, and legacy memory/list utility vectors. SNL remains a legacy
directory driver; optional SMSQ/E channel-name facilities are not advertised.

References: [official SMSQ/E source distribution](https://www.wlenerz.com/smsqe/),
version 3.43; `keys/sys`, `keys/chn`, `keys/iod`, `smsq/init/sys.asm`,
`smsq/sbas/procs/machine.asm`, `smsq/qd/trap1.asm`, `smsq/qd/trap3.asm`,
`smsq/sms/rte.asm`, `smsq/q68/int.asm`, `smsq/spp/io.asm`,
`smsq/q68/spp/ser.asm`, and `iod/iob/iox.asm`.

## Build and install

1. Keep the release binary as recovery media. Assemble the current source
   with Talent/Quanta Assembler 2.02, as before. Save a separate candidate.
   The source is self-contained, uses the 68000 instruction set, and still
   has entry offset zero.
2. Stop raw transfer tools using `/dev/ttyACM0`. Reset the QL before installing
   the candidate; do not CALL it over an already installed SNL driver.
3. On QL, allocate enough reserved memory for the actual assembled binary
   and install it, for example with 8192 bytes **if the binary fits**:

   ```text
   base=RESPR(8192)
   LBYTES win1_snl220_bin,base
   CALL base
   ```

   Expect `SNL Device driver V2.20 serial debug`. Installing does not require
   the Linux daemon. SNL keeps SER2 open until reset; do not use serial COPY
   or transfer tools concurrently afterward.

4. On Linux edit `snl_config.json`, preserving your directory mappings:

   ```json
   {
     "serial_port": "/dev/ttyACM0",
     "baud_rate": 9600,
     "stop_bits": 2,
     "rtscts": false,
     "reply_delay_ms": 0,
     "inter_byte_delay_ms": 0,
     "trace": true,
     "drives": {"1": "./drive1"}
   }
   ```

   Baud is ignored by QIMSI USB. Stop bits need not change from the existing
   setting: this is a USB CDC link rather than a UART connection. The daemon
   already disables XON/XOFF.
   This changes configuration only, not the daemon or wire protocol.

5. Prepare the first BASIC file and start the daemon from the repo root:

   ```sh
   mkdir -p drive1
   cp tests/fixtures/qimsi_hello_bas drive1/qimsi_hello_bas
   python3 snl_serial
   ```

   The `cp` command replaces a file of that name, so use a disposable test
   directory. Trace output will show OPEN/READ/WRITE/CLOSE activity.

## First hardware test: BASIC LOAD and SAVE

On QL:

```text
LOAD snl1_qimsi_hello_bas
LIST
RUN
```

Expect the message and numbers 1 through 5. Then save to a new filename:

```text
SAVE snl1_qimsi_saved_bas
NEW
LOAD snl1_qimsi_saved_bas
LIST
RUN
```

Confirm the listing and output are unchanged. Repeat loading and saving,
including an empty BASIC program if desired. Record the exact QL error,
any SNL diagnostic lines, and Linux trace if an operation fails. Do not
continue with binary or directory tests until BASIC load/save works.

After a successful first pass, check overwrite using a disposable saved
file, and missing-daemon recovery: stop the daemon, attempt a LOAD, then
restart it and retry. A pre-request readiness timeout should be recoverable;
an interrupted file packet is not automatically replayed.

## Subsequent stages

1. Binary SBYTES/LBYTES using `tests/ql/binary_test_bas`, with byte and memory
   guard checks; follow with sizes around 512-byte boundaries and larger files.
2. Directory listings, prefix filters, empty directories, and missing files.
3. Executable headers, deletion, overwrite, repeated/long transfers, and original
   QL/Minerva regression testing before releasing one combined binary.

Use Large QL Mode 4 initially, then repeat in Large 16-bit mode. SNL requests
at most 512 payload bytes per READ (515 total reply bytes) and waits for each
reply before sending the next request. This differs from an unrestricted
256 KiB serial stream. No fixed 80 KiB/s rate is assumed; verify reliability
before tuning throughput. Hardware USB/interrupt timing is not simulated by
the Python source-interpreter tests.
