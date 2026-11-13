# Binary serial bootstrap without base64

`tools/qltransfer_bin` is a separate Linux sender for the original QDOS serial
LBYTES protocol. The existing `tools/qltransfer` text sender remains available;
the old base64 loaders are retained as fixtures/reference material. The binary
bootstrap has been used on physical QL hardware during this project.

For the 4,592-byte V2.30 SNL driver, stop the daemon and reset the QL,
then type on the QL:

```text
BAUD 9600
base=RESPR(8192)
LBYTES ser2h,base
```

The 8192-byte allocation is sufficient only if the actual binary is no larger
than that; increase it for larger builds. LBYTES uses its first 14 destination
bytes as temporary header storage, so allocations must also be at least 14.

While the QL is waiting in LBYTES, run on Linux:

```sh
python3 tools/qltransfer_bin bin/snldriver230_bin
```

Use the filename of the driver binary you actually want to install. When the
QL returns to its BASIC cursor, type:

```text
CALL base
```

That entry offset is zero for the raw SNL binaries we have checked. Start the
SNL daemon before accessing any SNL files. Do not run this bootstrap with an
SNL driver already installed and owning SER2.

## Format

Wire bytes: FF marker, 14-byte QDOS header, then exact-length binary data.
The header's first four bytes contain the big-endian binary length. The
remaining ten bytes are zero for this LBYTES/bootstrap use. No base64, text
conversion, newline, or CTRL-Z terminator is sent. Use SER2H, not SER2HZ.
Both ends use 9600 baud, eight data bits, no parity, two stop bits and hardware
flow control. The Python sender requires the same pyserial package as the daemon.

The JS ROM IO.SERIO FS.HEADR path checks/consumes FF and reads the following
14 bytes; SuperBASIC LBYTES then requests the length stored in that header.
This avoids the BASIC base64 decode loop and adds only 15 bytes to the payload.
The protocol itself has no checksum; the existing base64 approach also has no
end-to-end checksum. Actual correctness/timing must be verified on hardware.

The sender's write timeout scales with file size and baud rate, with a minimum
of 30 seconds. The original ten-second limit was too short for tk2_bin: 16,411
wire bytes at 9600 baud, 8N2 require at least 18.8 seconds. After a partial
transfer timeout, do not CALL the incomplete binary; reset and start a fresh
receive before sending it again.
