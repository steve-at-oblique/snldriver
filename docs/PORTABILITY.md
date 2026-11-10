# One-binary compatibility target

This is the pre-implementation audit. The V2.20 source candidate now implements
the SMSQ/E QIMSI Gold/SER2 path and shared channel-state relocation described
below. See [the hardware test guide](QIMSI_SMSQE_TEST.md) for its actual scope
and validation status; configurable ports and QL-mode SER4 remain future work.

SNL should retain one source and one distributed binary for the original QL,
Minerva/sQLux, QIMSI in QL mode, and QIMSI in Q68 mode running SMSQ/E.
QIMSI and SMSQ/E support is a development target, not a V2.19 capability.
The working V2.19 source and released binary have not been changed by this
audit.

## Separate the OS from the serial transport

Installation must select two independent policies:

1. OS/channel/stack handling: original QDOS, supported Minerva, or SMSQ/E.
2. Transport: original QL serial, sQLux host serial, Jan Bredenbeek's QIMSI
   SER4, or SMSQ/E's Q68-family serial driver.

Detecting Minerva alone does not identify the serial hardware. Detecting a
SER4 name alone does not establish a particular driver's implementation.
Use the opened driver and supported OS interfaces to validate a profile.
Do not call the original ROM transmit task for independent QIMSI or
SMSQ/E serial transports.

Port selection must be possible without assembling another binary. Keep
SER2H as the original-QL default and provide an explicit installer setting
for other ports. Avoid silently opening unrelated ports to discover where
the user's cable is connected. Automatic OS/profile selection can coexist
with explicit port selection. The installer interface is still to be
implemented and tested.

## Source audit findings

The official SMSQ/E 3.43 source retains a QDOS-compatible filesystem OPEN
path in `smsq/ioa/opfl.asm`. It passes A0 as the channel block, A1 as the
physical definition, and A3 as the driver linkage. Its channel table lookup
in `smsq/io/ckchn.asm` also retains the table-index/tag model used by SNL.
These findings support a shared implementation; they do not prove that
every SNL assumption is safe.

**Channel private storage must move.** SNL currently starts at `$58`.
SMSQ/E `keys/chn` reserves `$58` for the drive-definition pointer, followed
by drive/file and subdirectory fields. Its documented spare area starts at
`$70` and ends at `$A0`. SNL's current 40-byte private state fits at
`$70..$97`, also within original QDOS's spare area. Check all state accesses
and add overlap/bounds checks before changing the base.

**Transmission activation differs.** SMSQ/E's `smsq/spp/io.asm` delegates
to `iob_iox`, which activates output as bytes are queued. The Q68-specific
`q68_oopr` in `smsq/q68/spp/ser.asm` enables transmit interrupts. Jan's
QL-mode SER4 `send` writes directly to the QIMSI FIFO; the independent
FPGA-side processor transmits the data. Neither path uses the original
QL ROM queue-start mechanism.

**Stack handling needs explicit validation.** Minerva's stack-derived
system-variable convention already requires a different policy from the
original QDOS private stack. Audit SMSQ/E trap and interrupt entry/return,
stack capacity, and nested calls before selecting its policy. Do not infer
the policy from a serial device name.

Audit the legacy filesystem CLOSE ownership, physical-definition counters,
utility vectors, optional channel-name callbacks, and driver registration
as part of the same change. Preserve the single-channel restriction and
existing file protocol during this work.

## Serial configuration

- Original QL: retain the tested baud, 8N2, hardware-handshake setup.
- QIMSI QL-mode SER4: configure 8-bit raw data and disable XON/XOFF. The H
  suffix is accepted but ignored by that driver. Baud/buffer configuration
  belongs to its own utility/firmware, not SNL.
- QIMSI/SMSQ/E mode: use the OS's serial devices and configuration. Do not
  load the QL-mode SER4 driver alongside an OS running on the FPGA CPU.
  Determine whether the user intends the UART or USB serial port.

SNL's request/reply protocol bounds the largest normal READ reply to 515
bytes (status, two-byte count, 512-byte payload). This is promising for
QIMSI's buffered connection without hardware flow control, but overruns
and burst behavior require hardware tests. Do not enable XON/XOFF for the
unescaped binary protocol.

The Python daemon's protocol should remain unchanged. Host serial settings
must match the chosen transport; disable RTS/CTS and XON/XOFF for the
QIMSI connection lacking hardware handshaking.

## Implementation and validation sequence

1. Add channel-layout bounds tests, relocate private state into shared spare
   space, and regress on the original QL and sQLux/Minerva.
2. Add installer port selection and a validated QIMSI SER4 profile. Test
   with the simple serial program, then SNL binary round trips.
3. Add the audited SMSQ/E profile, including registration, stacks, serial
   activation, and CLOSE handling. Validate against the actual board's OS
   build and port configuration.
4. Run DIR, BASIC SAVE/LOAD, all-byte-value binary round trips, executable
   header/dataspace preservation, COPY between native and SNL drives,
   overwrite/DELETE, and daemon-absent recovery in each environment.
5. Repeat the original physical QL regression suite with the same binary
   before replacing the release artifact or claiming combined support.

Hardware availability limits validation; source recognition alone is not a
passing compatibility test. Retain V2.19 as a recovery baseline.

## References

- [Official SMSQ/E source distribution](https://www.wlenerz.com/smsqe/):
  audited release 3.43, downloaded to temporary storage only.
- [QIMSI SER4 source and configuration](https://github.com/janbredenbeek/QIMSI-SER4):
  `ser4.asm`, including byte and block I/O and direct FIFO output.
- [Minerva test history](MINERVA_TEST.md).
