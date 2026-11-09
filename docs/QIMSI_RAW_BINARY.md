# QIMSI USB raw binary round trip

This tests the serial transport before adapting SNL to SMSQ/E. It requires
SMSQ/E with working QIMSI USB SER2 support and Python 3 on Linux. Stop the
SNL daemon and other serial tools first. Python tools use the standard library.

The fixture is 4096 bytes: values 0 through 255 repeated sixteen times. It
includes NUL, CR, LF, Ctrl-Z, XON and XOFF. Both ends disable flow control and
use raw data. There is no header or EOF marker: the length is known in advance.

## Install the BASIC receiver

On QL:

```text
COPY_N ser2iz TO ram1_rawtest_bas
```

On Linux, from the repository directory:

```sh
python3 tools/qimsi_send.py tests/ql/qimsi_binary_receive_bas
```

This transfers the BASIC source in the sender's normal text mode.

## Linux to QL

Create the fixture on Linux (refuses to overwrite an existing file):

```sh
python3 tools/qimsi_binary_fixture.py
```

On QL:

```text
LOAD ram1_rawtest_bas
RUN
```

Enter a new destination filename, such as `ram1_raw_bin`. When it says Ready,
run on Linux within 60 seconds:

```sh
python3 tools/qimsi_send.py qimsi_binary.dat --binary --chunk-size 16
```

The QL stops on the first mismatch or timeout, closes the files, and prints
FAIL. A successful receive prints PASS and leaves the exact data in the RAM
file. The first byte has offset zero. On failure, the output is partial; use
a fresh filename for the next run. After an interruption, let the sender
finish or stop it, then reopen the QL receive before retrying.

The small chunks and default 0.05-second delay deliberately offer only about
320 bytes/second (roughly 13 seconds for this file). The BASIC receiver checks
and saves each byte individually. This is an all-byte integrity test, **not**
a test of the maximum speed of the OS driver or the existing COPY_N path.

## QL to Linux

Start Linux first:

```sh
python3 tools/qimsi_receive.py qimsi_binary.dat --output binary_return.dat
```

When Linux says Ready, on QL:

```text
COPY_N ram1_raw_bin TO ser2idr
```

`I` ignores flow control, `D` disables output translation, and `R` selects
raw carriage-return handling. Do not add `Z`: Ctrl-Z is ordinary payload.

Linux checks every returned byte and reports PASS or the first mismatch.
It allows 60 seconds for the first data and 10 seconds of inactivity thereafter,
and checks for trailing data for one second after the expected length arrives.
The returned file is retained; choose a new output name on subsequent runs.
An independent comparison is also possible:

```sh
cmp qimsi_binary.dat binary_return.dat
```

No output from `cmp` means identical files. Exact-count framing cannot detect
arbitrarily delayed extra bytes, and this test has no retransmission protocol.
