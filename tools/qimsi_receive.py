#!/usr/bin/env python3
"""Receive QIMSI serial data and compare it with a local reference file.

Start this on Linux first, then on the QL:
    COPY_N ram1_speed80_dat TO ser2i

Reception uses the reference length, not a Ctrl-Z marker, so all byte values
are allowed. The output file is retained for inspection, including on failure.
"""

import argparse
import os
from pathlib import Path
import select
import termios
import time
import tty


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--output", type=Path, default=Path("speed_return.dat"))
    args = parser.parse_args()
    try:
        expected = args.reference.read_bytes()
        if not expected:
            parser.error("reference must not be empty")
        fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY)
        try:
            tty.setraw(fd)
            settings = termios.tcgetattr(fd)
            settings[2] &= ~(termios.CRTSCTS | termios.PARENB | termios.CSTOPB)
            settings[2] |= termios.CLOCAL | termios.CREAD
            settings[4] = settings[5] = termios.B9600
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            termios.tcflush(fd, termios.TCIFLUSH)
            # Exclusive creation protects the reference and earlier results.
            with args.output.open("xb") as output:
                print(f"Ready: expecting {len(expected)} bytes on {args.port}.", flush=True)
                print("On QL: COPY_N your_ram_file TO ser2i (no Z suffix).", flush=True)
                received = 0
                started = None
                deadline = time.monotonic() + 60
                while received < len(expected):
                    wait = deadline - time.monotonic()
                    if wait <= 0 or not select.select([fd], [], [], max(0, wait))[0]:
                        parser.exit(1, f"FAIL: timed out after {received}/{len(expected)} bytes.\n")
                    chunk = os.read(fd, min(65536, len(expected) - received))
                    if not chunk:
                        raise OSError("Serial device disconnected")
                    if started is None:
                        started = time.monotonic()
                    output.write(chunk)
                    want = expected[received:received + len(chunk)]
                    if chunk != want:
                        index = next(i for i, (a, b) in enumerate(zip(chunk, want)) if a != b)
                        parser.exit(1, f"FAIL: offset {received + index}: expected "
                                    f"{want[index]}, received {chunk[index]}.\n")
                    received += len(chunk)
                    deadline = time.monotonic() + 10
                elapsed = time.monotonic() - started
                # Catch an accidental Ctrl-Z terminator or other trailing bytes.
                if select.select([fd], [], [], 1)[0]:
                    extra = os.read(fd, 65536)
                    if extra:
                        output.write(extra)
                        parser.exit(1, "FAIL: extra bytes after expected payload; use ser2i without Z.\n")
            print(f"PASS: all {received} bytes match {args.reference}.")
            if elapsed > 0:
                print(f"First-to-last received byte: {elapsed:.3f}s, "
                      f"{received / 1024 / elapsed:.1f} KiB/s "
                      "(approximate; excludes startup latency).")
            print(f"Saved to {args.output}")
        finally:
            os.close(fd)
    except (OSError, termios.error) as exc:
        parser.exit(1, f"Receive failed: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nInterrupted. Stop the QL copy before retrying.\n")


if __name__ == "__main__":
    main()
