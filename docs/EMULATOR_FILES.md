# Using sQLux Unzip with SNL

Update `snl_serial` on Linux and restart the daemon. Keep the existing config,
with debug off, and the currently working V2.09 QL driver. There is no new
protocol or assembly change.

Filename lookup is case-insensitive: `Assembler`, `assembler`, and `ASSEMBLER`
refer to the same file. Existing host spelling is preserved, including on
overwrite and in returned file headers; new files retain the requested spelling.
Sidecars use the actual host filename. Lookup scans the directory on each OPEN,
so files extracted by sQLux become visible without restarting the daemon.
If Linux contains two names differing only by case, SNL returns Bad Name for
that ambiguous name; rename one on Linux to give each a distinct QDOS name.

Map a sQLux directory device to the same host directory that the daemon serves
as drive1. Run the original QL Unzip inside sQLux and extract the original QL
ZIP archive to that mapped drive. Once extraction finishes, open the resulting
files from the physical QL as `snl1_filename`.

First hardware check: put the ORIGINAL supplied `monitor` in the Linux drive1
directory (not the converted `monitor_snl/monitor`). Then try:

```text
EXEC snl1_monitor
```

The daemon now recognizes its emulator wrapper automatically. Expected payload
length is 20,940 bytes, executable type 1, data space 1,024 bytes. No manually
created `.snl_headers/monitor.json` is needed; an embedded wrapper takes
precedence over an old sidecar. The original Unzip is also recognized, but
still needs expanded memory, so run that on sQLux.

## Storage behavior

Existing emulator files with the 18-byte signature `]!QDOS File Header` and a
30- or 44-byte wrapper are supported. SNL reports payload-only lengths, maps
payload offset zero past the wrapper, and exposes the ten metadata bytes as
QDOS header bytes 4 through 13. Embedded wrapper sizes are big-endian words.
Recognized but truncated/unsupported wrappers return Bad Name rather than
being treated as executable code.

Reading does not modify the file or create a sidecar. Updating an existing
wrapped file preserves its wrapper; setting its QDOS header updates the
wrapper's metadata in place. The extra 14 bytes of a 44-byte wrapper are
preserved, not interpreted as QDOS metadata. Overwriting a file through SNL
creates a plain file and resets metadata, as before.

New files created by SNL still use plain payloads plus `.snl_headers` metadata.
This change enables sQLux-extracted files to be used by SNL; it does not teach
sQLux to read SNL sidecars. For executable files created by SNL, continue to
preserve those sidecars. Legacy `.-UQLX-` metadata and XTcc trailers are not
added by this change.

Finish extraction and close the files in sQLux before opening them through
SNL. The two applications do not coordinate concurrent writes. Keep names
within SNL's existing 36-character flat-file naming support; nested directory
support remains separate work.

## Reference and verification

Checked against sQLux's
[FillQemulator and QHSetHeader](https://github.com/SinclairQL/sQLux/blob/master/uxfile.c).
The implementation hides the wrapper without rewriting or converting the
source file. ZIP extraction and QDOS metadata restoration remain the job of
the existing QL Unzip.

Run local regressions with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -q
```

Tests cover both wrapper lengths, payload offsets and EOF, read-only access,
metadata updates, writable payload extension, stale sidecars, overwrite,
malformed wrappers, and the QL assembly's buffered read path.
