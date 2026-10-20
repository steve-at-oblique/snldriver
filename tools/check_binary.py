"""Check the Linux payload saved by binary_test_bas, without dependencies."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--length", type=int, default=1537)
    args = parser.parse_args()
    if args.length < 0:
        parser.error("length must be nonnegative")
    actual = args.file.read_bytes()
    expected = bytes(i % 256 for i in range(args.length))
    if actual == expected:
        print(f"PASS: {len(actual)} bytes match exactly")
        return 0
    print(f"FAIL: expected {len(expected)} bytes, found {len(actual)}")
    for offset, (got, want) in enumerate(zip(actual, expected)):
        if got != want:
            print(f"First mismatch at offset {offset}: got {got:02x}, expected {want:02x}")
            break
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
