# V2.19 serial compatibility candidate

Historical development notes: references below to `bin/snl_bin` describe the
old V2.15 distribution. The current release binary is `bin/snldriver228_bin`.

The source is a test candidate. The distributed `bin/snl_bin` remains the
tested V2.15 binary. Assemble `SNLdriver_asm` with the Talent/Quanta assembler
and save a separate candidate binary; do not replace the release binary yet.

Installation now recognizes three paths:

- Original QDOS: retain the existing guarded serial scheduler callback.
- Minerva: recognize the live scheduler entry matching the 14-byte
  `ip_sched` sequence in the supplied Minerva 1.98a1 ROM. The callback address
  comes from the scheduler list, not a fixed ROM address.
- sQLux: validate the opened serial driver's I/O and close entry addresses
  (`$1C020` and `$1C022`), their emulator opcodes (`$AAAA`, `$AAAC`), and its
  open-entry opcode (`$AAAB`). Host serial writes need no ROM callback.

Unrecognized paths still fail installation. This does not establish support
for all Minerva releases or third-party serial replacements.

V2.16 installed in sQLux but crashed after the readiness request, before
OPEN. Inspection of Minerva's `M/mt/trap.asm` and `M/ss/base.asm` identified
a stack convention SNL had violated: Minerva derives its system-variable
base by masking the low word of the supervisor stack address with `$8000`.
Moving the supervisor stack to an arbitrary heap allocation breaks that
calculation. V2.17 recognizes the supplied ROM's TRAP #1 prologue and keeps
Minerva's larger system stack active for OPEN, I/O, and CLOSE. Original QDOS
keeps its private-stack path. This is a candidate correction; the crash
diagnosis and stack capacity still require emulator/hardware validation.

User testing confirmed V2.17 can list the directory in sQLux/Minerva. The
caller also probes optional extended medium information (`FS.XINF`, `$4F`).
V2.18 retains Not Implemented for that query but suppresses its diagnostic,
allowing the caller's working fallback without console clutter. LOAD/SAVE,
binary round trips, and physical hardware regression testing remain pending.

V2.19 also quietly returns Not Implemented for optional file-version
query/set (`FS.VERS`, `$4E`), which Toolkit II COPY probes. QDOS header
read/write support remains intact; this does not implement or preserve the
version field through that optional operation.

References: sQLux `QL_driver.c`, `QLserio.c`, and `xcodes.h` at
https://github.com/SinclairQL/sQLux ; Minerva 1.98 source `M/ip/int.asm` at
https://sinclairql.net/djw/qlrom/m198src.zip .

## First test: sQLux and a virtual serial pair

1. Stop the daemon and reset/restart sQLux; do not install over an existing
   SNL driver. Keep socat running with `/tmp/snl-ql` and `/tmp/snl-host`.
2. Configure sQLux `SER2 = /tmp/snl-ql`. Configure the daemon to use
   `/tmp/snl-host`, with `rtscts` false. This setting is for the virtual pair;
   retain hardware flow control for the physical QL cable.
3. Load and call the newly assembled candidate. Installation should succeed
   without the daemon running and show V2.19.
4. Start the daemon, then try `DIR snl1_`, LOAD of a known BASIC file, and
   LIST. Save under a new test name, NEW, reload it, and verify its contents.
5. Run the existing binary round-trip test. Check the result with
   `tools/check_binary.py`.
6. Check DELETE and overwrite using expendable test files. Test recovery
   after starting with the daemon absent.

The virtual pair does not validate physical timing, baud rate, or RTS/CTS.
The existing automated tests cover filesystem and transfer behavior, not
installation machine code or emulator trap execution.

## Physical regression tests

Test the candidate on the original QL ROM before release, retaining a copy
of V2.15. Then repeat on the Tetroid/Minerva system when available. Record
the Minerva version: the supplied 1.98a1 ROM is the only Minerva image whose
callback signature has been checked so far.
