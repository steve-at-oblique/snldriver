# V2.38: QIMSI Gold USB under Minerva4Q68

The source and supplied `bin/snldriver238_bin` are V2.38. The 5,296-byte
binary was assembled and hardware-tested by the user. No daemon protocol or configuration change is
required. The separately tested daemon shutdown logging fix remains compatible.
V2.37 passed installation/DIR, channel diagnostic revision 5, binary round
trip, and launching the game with manually configured USB buffers. V2.38
automates that configuration; its Minerva recovery, channel and binary
tests passed.

## Supported configuration

QIMSI Gold running Jan Bredenbeek's Minerva4Q68, based on Minerva 1.98,
with its native SER2 USB driver (Minerva4Q68 v1.80 or newer and QIMSI Gold
firmware v1.20 or newer). V2.38 automatically configures the equivalent of
`SER_BUFF 2,1024,4096` before opening SER2. No BASIC setup command is needed.

The default zero-buffer USB receive path hung both a native BASIC probe and
the initial SNL test on the user's machine. Buffered I/O passed; the precise
underlying cause is not established. This targets the default port names. Renamed ports,
other Minerva hardware, Q68 physical UARTs and other SMSQ/E targets are not
newly supported by this change.

V2.36 opened the legacy serial path and searched for the original QL ROM
transmit scheduler task. On this configuration it reported:

```text
SNL ROM TX task unavailable $ED
SNL installation failed $ED
```

Minerva4Q68 has its own serial driver and does not require this callback.

## Implementation

The new profile requires all of:

- The existing audited Minerva MT.TRAP prologue, which derives sysvars from
  the supervisor stack: `48E70106 2E0F0247 80002C47`.
- MT.INF version `1.98` (or the alternate `1G98` image).
- Minerva4Q68's sys_mtyp machine ID 21 (QIMSI Gold).

It sets linkage+$60 for the native Minerva stack and linkage+$61 to 2 for
Minerva USB. SMSQ/E QIMSI uses profile 1 and the existing private stack.
Legacy configurations retain profile 0 and their existing transmit servicing.

Minerva opens `SER2I`, with flow control disabled. Its driver accepts only
4–6 characters; the SMSQ/E-specific `SER2IDR` name is not appropriate here.
Before configuring buffers, and again after OPEN, SNL verifies the driver's SER2 name, USB status-register address
($1C228) stored in its linkage, and the basic-I/O dispatch signature from
q68ser v1.12. A mismatch closes the serial channel and frees installation
memory rather than registering an unsupported transport. Validation reads
linkage/code memory, not hardware registers.

During installation, SNL locates the validated native SER2 driver through
SV.DRLST, using a bounded search. It invokes Minerva's MT.EXTOP to check the
port is unused and set queue sizes plus SER_BUFF's matching thresholds with
interrupts masked. The callback returns with RTE, restoring the original
interrupt state. A busy port returns In Use without modifying its settings.
Queue storage is allocated by the native serial driver's subsequent OPEN;
SNL does not create its own version of Minerva's queue implementation.
SMSQ/E and legacy profiles do not run this setup.

The serial driver already implements byte/string transfers, partial counts,
ERR.NC and direct USB FIFO I/O. SNL therefore uses its existing bulk transmit
and receive helpers with no ROM transmit callback. Per-channel buffers,
request serialization, metadata and the wire protocol remain unchanged.

The native supervisor stack is essential: both Minerva's traps and level-2
interrupts derive the system-variable base from the current stack address.
SNL's entry wrappers already support this policy, including lock acquisition
before entering the body and restoration of the caller's stack.

## Source evidence and automated checks

Audited against the ready-built 80 KiB Q68_ROM.SYS and sources in
[Minerva4Q68](https://github.com/janbredenbeek/Minerva4Q68):

- `m/mt/trap.asm`, `m/mt/inf.asm`, `m/ss/int2.asm`: trap/IRQ stack convention
  and OS version retrieval. The supplied ROM's trap-1 vector is $1176;
  no fixed trap routine address is compiled into SNL.
- `extrarom/q68hw.asm`: populates sys_mtyp and maps QIMSI Gold to ID 21.
- `extrarom/q68ser.asm`: port-name parsing, linkage layout, direct FIFO
  I/O, string count semantics, and self-starting buffered output.
- `m/inc/q68`: second serial status register at $1C228.
- The project's README documents supported firmware, default SER2 buffers
  (zero/direct I/O), and USB port support.

The automated suite executes profile selection and serial-linkage checks,
rejects altered signatures/wrong ports, checks native/private entry-stack
restoration, and exercises existing byte, bulk and multiple-channel paths.
These checks do not emulate actual Minerva interrupt timing or replace
Talent assembly and hardware validation.

## Build and hardware test

1. Assemble the updated self-contained `SNLdriver_asm` using Talent/Quanta
   2.02. Save the binary separately as `snldriver238_bin`. Do not reuse the
   fixed 5,100-byte reservation: the new source is larger. Reserve memory
   according to the actual assembled file length, for example with TK2:

   ```basic
   base=RESPR(FLEN("win1_snldriver238_bin")+14)
   LBYTES win1_snldriver238_bin,base
   CALL base
   ```

   Enter Minerva4Q68 from a fresh boot and omit the manual SER_BUFF command
   when testing V2.38. Use RESPR(6000) if TK2/FLEN is not available, checking
   the assembled size fits. Load TK2 v2.36 for
   the supplied BASIC diagnostic programs. Expect the V2.38 banner, with
   neither the ROM-task error nor an installation error. Use the same
   `/dev/ttyACM0` daemon settings used for QIMSI/SMSQ/E, with rtscts false.

2. First leave the daemon stopped and try `DIR snl1_`: expect Xmit Error
   with the QL still responsive. Start the daemon and retry DIR: expect it to
   work without reinstalling. Then load a known BASIC file and save/reload a disposable BASIC
   file. This checks initial readiness, directory reception and ordinary
   reads/writes. Repeat DIR on another mapped drive.

3. Run the updated `tests/ql/snl_channels_bas`. It prints diagnostics
   revision 6, uses fresh `mc238_src`/`mc238_dst` names, verifies all 1,537
   bytes in source and copy, and holds three channels open. Expect PASS.

4. Run the existing `tests/ql/binary_test_bas` with a fresh
   `snl1_bintest_bin` name. It generates its own 1,537-byte pattern; expect
   zero byte mismatches and zero guard errors. Try COPY/WCOPY between SNL and WIN and between two SNL drives.

5. Run the existing metadata, rename/truncate and directory tests as
   applicable (see their individual plans). Then extract the desired game's
   QL-created ZIP from SNL to a disposable SNL directory, and try the game.
   No `-j` is needed when preserving its directory structure.

6. Regression-check the same candidate under QIMSI/SMSQ/E (channel diagnostic
   and normal COPY/WCOPY) and stock QDOS/TK2 (installation, DIR and channel
   diagnostic). These configurations must retain their existing behavior.

Report the first failing step and the driver message or daemon rejection.
A serial-open Not Found can indicate that the second port is disabled or
unavailable; an installation $ED after OPEN indicates a profile/linkage
validation failure.

## Initial V2.37 hardware result (unresolved)

The user assembled a 5,174-byte binary and installed it under Minerva4Q68
using RESPR(5400). Installation succeeded, but the first DIR printed a newline
and crashed. With daemon trace enabled, the only request trace was
`SNL READY token=...`; no OPEN was logged. The daemon logs READY after sending
its reply, so this proves transmission of the probe but not successful QL
reception or return from the readiness helper. Allocation size is sufficient.
A native BASIC SER2I readiness exchange without SNL loaded was then used
to separate serial reception from the SNL polling/stack path.

### Native receive comparison

Without SNL loaded, OPEN #3,SER2I followed by a valid readiness PRINT and
INPUT hung in the default direct-I/O configuration. The same native BASIC
program **passed** after adding `SER_BUFF 2,1024,4096` before OPEN. This
isolates a receive-path difference independently of SNL. The initial claim
that the external interrupt handler unconditionally discards direct-mode
bytes was not established: the full entry checks rxint_en first.

The next test retained these buffers, closed the probe channel, installed
V2.37 and retried DIR. The results follow.

### Buffered SNL hardware results

With `SER_BUFF 2,1024,4096` set before installing the same V2.37 binary,
the user confirmed:

- DIR: **PASS**.
- Channel diagnostic revision 5: **PASS**.
- Binary round trip: **PASS**.

No reassembly or daemon protocol change was needed for these passes. The
native buffered probe and the SNL tests establish a working configuration;
they do not independently identify the defect in the default direct path.

## V2.38 automatic-buffer verification

The automated suite (198 tests) checks the actual setup callback, exact
queue lengths including native headers, SER_BUFF-compatible thresholds,
interrupt masking while updating defaults, return-state/register/stack
restoration, rejection of open channels without mutation, and bounded
search on missing/incorrect drivers. Minerva hardware results are recorded below; cross-platform results
are recorded below.

The later missing-daemon hang under V2.37 occurred after a reboot where the
user had omitted SER_BUFF. It is not yet evidence of failed recovery with
buffers configured; the V2.38 hardware plan explicitly tests that case.

### V2.38 Minerva hardware results

The user confirmed all of the following with automatic buffer setup:

- Missing daemon: Xmit Error, QL remains usable; start daemon and retry: **PASS**.
- Channel diagnostic revision 6: **PASS**.
- Binary round trip: **PASS**.

This validates normal transfers and the start-daemon/retry-OPEN workflow
without a manual SER_BUFF command. The earlier V2.37 unbuffered hang is
avoided by the installation-time buffer setup. The stock-QDOS and SMSQ/E regressions below also passed.

### V2.38 cross-platform hardware regressions

Stock QL with Toolkit II: binary round trip, channel diagnostic,
rename, metadata and directories: **all PASS**.

QIMSI Gold with SMSQ/E: installation, DIR, channel diagnostic,
binary round trip and WCOPY: **all PASS**.

Together with the Minerva results, this completes the planned V2.38
hardware validation. The original QDOS and SMSQ/E transport paths retain
their working behavior alongside automatic Minerva USB buffer setup.
