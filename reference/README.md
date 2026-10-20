# Reference material

These files preserve the project's origins and early experiments. They are
not required to assemble the current self-contained `../SNLdriver_asm`.

- `MDI_symbol_asm` and `MDI_RAM_SYMBOL_TABLE`: supplied original definitions and
  historical assembler output.
- `SNL_symbol_asm`: the extracted constants retained as a reference; the
  canonical driver's inline constants are authoritative.
- `experiments/ser_test.asm`: the original serial proof of concept.
- `bootstrap/loader_v210_bas`: the old version-specific base64 loader; its
  fixed binary length does not apply to current builds.

The original SuperBASIC base64 loader is retained as
`../tests/fixtures/loader_bas` because its exact payload is used in the read-cache
regression tests. The current raw-binary sender is `../tools/qltransfer_bin`.
