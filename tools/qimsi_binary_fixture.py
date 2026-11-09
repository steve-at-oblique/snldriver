#!/usr/bin/env python3
"""Create the 4096-byte all-values fixture for qimsi_binary_receive_bas."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=Path("qimsi_binary.dat"))
    args = parser.parse_args()
    try:
        with args.output.open("xb") as output:
            output.write(bytes(range(256)) * 16)
    except OSError as exc:
        parser.exit(1, f"Cannot create fixture: {exc}\n")
    print(f"Created {args.output}: 4096 bytes, values 0..255 repeated 16 times.")


if __name__ == "__main__":
    main()
