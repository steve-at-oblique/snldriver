# SBYTES / LBYTES hardware test

Use the installed SNL driver (V2.09 or later) and current daemon. No reassembly,
daemon update, or debug logging is needed for this first test. The existing
driver implements FS.SAVE ($49), FS.LOAD ($48), and the header operations
used by the original QDOS BASIC commands.

Use drive1 or drive2 with stock QDOS. Its directory-device name parser
accepts drive numbers 1 through 8 and rejects 0 with Not Found before the
SNL driver receives OPEN. The daemon's configured drive0 cannot be reached
as snl0_ through that parser.

Copy `tests/ql/binary_test_bas` into the Linux drive1 directory. On the QL:

```text
NEW
LOAD snl1_binary_test_bas
RUN
```

The program allocates 1,569 bytes, saves a 1,537-byte pattern to
`snl1_bintest_bin`, replaces the memory contents, loads the file back, and
compares every byte. It also checks 16 guard bytes on each side. The pattern
contains every byte value, including NUL, LF, CR, CTRL-Z, and $FF; its length
crosses three 512-byte boundaries and ends with a one-byte partial block.

Expected output ends with:

```text
Byte mismatches: 0  Guard errors: 0
PASS: binary round trip
```

The test uses stock QL `RESPR`. Its reserved memory remains allocated until
reset; do not use RECHP to free it. Each RUN reserves another 1,569 bytes.
If BASIC stops with an error, record the exact error and line.

SBYTES creates a new file. Before repeating, change line 30 to a fresh name,
for example `snl1_bintest2_bin`. No overwrite or deletion is performed by
this test.

For an independent check, copy `check_binary.py` to Linux and run:

```sh
python3 tools/check_binary.py /home/steve/dev/qldaemon/drive1/bintest_bin
```

Expected: `PASS: 1537 bytes match exactly`. The Linux payload should be
exactly 1,537 bytes; the QDOS header lives separately in `.snl_headers`.

After that passes, optionally change line 20 to `n=66563` and line 30 to
another fresh filename. This verifies lengths above 65,535 on hardware, but
requires about 67 KB of free QL heap. Use `--length 66563` with the Linux
checker for that run.

Local validation: 28 tests pass. The new test executes the assembly transfer
loops through the source interpreter against the Python server, saving,
closing, reopening, and loading 66,563 bytes. Existing wire tests cover header
persistence. This does not substitute for Talent assembly or the hardware
BASIC command test above. No driver or protocol changes were needed.

Executable files and EXEC/EXEC_W remain a separate validation step.
