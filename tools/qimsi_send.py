#!/usr/bin/env python3
"""Send a file to QIMSI USB CDC with configurable pacing.

QL: COPY_N ser2iz TO ram1_received_bas
Linux: python3 tools/qimsi_send.py hello_bas

Text mode normalizes newlines and appends Ctrl-Z. --binary sends exact bytes
without a terminator; the QL must receive a known byte count.

Uses only the Python standard library on Linux. Stop other serial programs
before running. This is a raw text transfer, not the QDOS LBYTES protocol.
"""

import argparse
import math
import os
from pathlib import Path
import termios
import time
import tty


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def delay_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def write_all(fd, data):
    remaining = memoryview(data)
    while remaining:
        sent = os.write(fd, remaining)
        if sent <= 0:
            raise OSError("Serial write made no progress")
        remaining = remaining[sent:]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--binary", action="store_true",
                        help="send exact bytes without newline conversion or Ctrl-Z")
    parser.add_argument("--chunk-size", type=positive_int, default=256)
    parser.add_argument("--delay", type=delay_seconds, default=0.05,
                        help="seconds between chunks (default: 0.05)")
    args = parser.parse_args()
    try:
        data = args.file.read_bytes()
        if not args.binary:
            # QL BASIC expects LF lines. Also handle CR-only text files.
            data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if b"\x1a" in data:
                parser.error("file contains Ctrl-Z; use --binary for raw data")
        print(f"Sending {len(data)} bytes to {args.port}; "
              f"{args.chunk_size} bytes per chunk, {args.delay:g}s delay.")
        if args.binary:
            print("The QL must be ready to receive the exact byte count, without Z.")
        else:
            print("The QL must already be waiting in COPY_N ser2iz TO a new file.")
        fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY)
        try:
            tty.setraw(fd)
            settings = termios.tcgetattr(fd)
            settings[2] &= ~(termios.CRTSCTS | termios.PARENB | termios.CSTOPB)
            settings[2] |= termios.CLOCAL | termios.CREAD
            settings[4] = settings[5] = termios.B9600
            termios.tcsetattr(fd, termios.TCSANOW, settings)
            # QIMSI CDC ignores baud; pacing limits the offered data rate.
            started = time.monotonic()
            for offset in range(0, len(data), args.chunk_size):
                write_all(fd, data[offset:offset + args.chunk_size])
                termios.tcdrain(fd)
                time.sleep(args.delay)
            if not args.binary:
                write_all(fd, b"\x1a")
            termios.tcdrain(fd)
            elapsed = time.monotonic() - started
            time.sleep(1)
        finally:
            os.close(fd)
        ending = "" if args.binary else " and Ctrl-Z"
        print(f"Sent {len(data)} bytes{ending} in {elapsed:.2f}s.")
        print("This is sender timing, not verified receiver throughput. "
              "Wait for the QL prompt and check the received file.")
    except (OSError, termios.error) as exc:
        parser.exit(1, f"Transfer failed: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nTransfer interrupted; cancel the QL receive and retry with a new file.\n")


if __name__ == "__main__":
    main()
