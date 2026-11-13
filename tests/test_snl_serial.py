"""Wire-level tests using fragmented serial I/O and real temporary host files."""
import contextlib
import io
import importlib.machinery
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("snl", str(ROOT / "snl_serial"))
spec = importlib.util.spec_from_loader(loader.name, loader)
snl = importlib.util.module_from_spec(spec)
loader.exec_module(snl)


class Port:
    def __init__(self, data):
        self.data = bytearray(data)
        self.output = bytearray()

    def read(self, n):
        n = min(n, 3)  # serial reads need not return an entire packet
        out = bytes(self.data[:n])
        del self.data[:n]
        return out

    def write(self, data):
        n = min(len(data), 5)  # exercise short serial writes too
        self.output.extend(data[:n])
        return n


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.session = snl.Session({"1": self.root})

    def tearDown(self):
        self.session.close()
        self.tmp.cleanup()

    def request(self, packet):
        port = Port(packet)
        snl.serve_one(port, self.session)
        self.assertEqual(port.data, b"")
        return bytes(port.output)

    def open(self, name=b"test_bas", mode=2, drive=1):
        return self.request(bytes((0x11, drive, mode, len(name))) + name)

    def write(self, offset, data):
        return self.request(b"\x13" + struct.pack(">IH", offset, len(data)) + data)

    def read(self, offset, count):
        return self.request(b"\x12" + struct.pack(">IH", offset, count))

    def test_binary_save_load_and_header_roundtrip(self):
        payload = bytes(range(256)) * 300  # >64K: catches 16-bit LOAD/SAVE truncation on host
        self.assertEqual(self.open(), b"\x00" + bytes(4))
        header = struct.pack(">I", 12345) + bytes((0, 1)) + struct.pack(">II", 4096, 0)
        self.assertEqual(self.request(b"\x16" + header), b"\x00")
        for offset in range(0, len(payload), 512):
            block = payload[offset:offset + 512]
            self.assertEqual(self.write(offset, block), b"\x00" + struct.pack(">H", len(block)))
        self.assertEqual(self.request(b"\x17"), b"\x00")
        self.assertEqual(self.request(b"\x04"), b"\x00")
        self.assertEqual((self.root / "test_bas").read_bytes(), payload)
        self.assertEqual(self.open(mode=1), b"\x00" + struct.pack(">I", len(payload)))
        read_header = self.request(b"\x15")
        self.assertEqual(len(read_header), 65)
        self.assertEqual(read_header[1:5], struct.pack(">I", len(payload)))
        self.assertEqual(read_header[5:15], header[4:14])
        self.assertEqual(read_header[15:25], b"\x00\x08test_bas")
        result = bytearray()
        for offset in range(0, len(payload), 512):
            reply = self.read(offset, 512)
            self.assertEqual(reply[:3], b"\x00\x02\x00")
            result.extend(reply[3:])
        self.assertEqual(result, payload)
        self.assertEqual(self.read(len(payload), 1), b"\xf6\x00\x00")

    def test_access_modes_and_errors(self):
        self.assertEqual(self.open(mode=0), snl.status(snl.NF))
        self.assertEqual(self.open(drive=2), snl.status(snl.NF))
        self.assertEqual(self.open(), b"\x00" + bytes(4))
        self.assertEqual(self.write(0, b"abc"), b"\x00\x00\x03")
        self.assertEqual(self.open(), snl.status(snl.EX))
        self.assertEqual(self.open(mode=1), b"\x00\x00\x00\x00\x03")
        self.assertEqual(self.write(0, b"x"), snl.status(snl.RO) + bytes(2))
        self.assertEqual(self.request(b"\x16" + bytes(14)), snl.status(snl.RO))
        self.assertEqual(self.open(mode=3), b"\x00" + bytes(4))
        self.assertEqual((self.root / "test_bas").read_bytes(), b"")
        self.assertEqual(self.open(mode=5), snl.status(snl.NI))

    def test_delete_removes_payload_and_metadata_then_save_can_reuse_name(self):
        self.open(name=b"Mixed_Bin")
        self.write(0, b"old")
        self.request(b"\x16" + bytes(5) + b"\x01" + bytes(8))
        self.request(b"\x04")
        self.assertEqual(self.open(name=b"MIXED_BIN", mode=255), b"\x00")
        self.assertFalse((self.root / "Mixed_Bin").exists())
        self.assertFalse((self.root / ".snl_headers" / "Mixed_Bin.json").exists())
        self.assertIsNone(self.session.file)
        self.assertEqual(self.open(name=b"Mixed_Bin"), bytes(5))
        self.assertEqual(self.write(0, b"replacement"), b"\x00\x00\x0b")
        self.request(b"\x04")
        self.open(name=b"mixed_bin", mode=1)
        self.assertEqual(self.request(b"\x15")[6], 0)

    def test_delete_missing_file_and_busy_session(self):
        self.assertEqual(self.open(mode=255), snl.status(snl.NF))
        self.open()
        self.write(0, b"keep")
        self.assertEqual(self.open(mode=255), snl.status(snl.IU))
        self.assertEqual(self.read(0, 4), b"\x00\x00\x04keep")
        self.request(b"\x04")
        self.assertEqual(self.open(mode=255), b"\x00")
        self.assertEqual(self.open(mode=255), snl.status(snl.NF))

    def test_delete_emulator_file_needs_no_sidecar(self):
        self.emulator_file()
        self.assertEqual(self.open(name=b"TEST_BAS", mode=255), b"\x00")
        self.assertFalse((self.root / "test_bas").exists())
        self.assertFalse((self.root / ".snl_headers").exists())

    def test_delete_refuses_directories_paths_and_symlink_metadata(self):
        (self.root / "folder").mkdir()
        for name in (b"folder", b"../escape", b".SNL_HEADERS"):
            self.assertEqual(self.open(name=name, mode=255), snl.status(snl.BN))
        (self.root / "test_bas").write_bytes(b"keep")
        (self.root / ".snl_headers").mkdir()
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere) / "metadata"
            outside.write_bytes(b"keep too")
            (self.root / ".snl_headers" / "test_bas.json").symlink_to(outside)
            self.assertEqual(self.open(mode=255), snl.status(snl.BN))
            self.assertEqual(outside.read_bytes(), b"keep too")
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")

    def test_delete_failure_preserves_payload(self):
        (self.root / "test_bas").write_bytes(b"keep")
        with patch.object(Path, "unlink", side_effect=PermissionError):
            self.assertEqual(self.open(mode=255), snl.status(snl.RO))
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")

    def test_delete_reply_does_not_leave_bytes_before_next_open(self):
        (self.root / "test_bas").write_bytes(b"old")
        port = Port(b"\x11\x01\xff\x08test_bas\x11\x01\x02\x08test_bas")
        snl.serve_one(port, self.session)
        snl.serve_one(port, self.session)
        self.assertEqual(port.output, bytes(6))
        self.assertFalse(port.data)

    def test_ready_echoes_token_without_opening_a_file(self):
        token = b"ABCDEFGHIJKLMNOP"
        port = Port(b"~SNL?" + token + b"\n")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            snl.serve_one(port, self.session)
        self.assertEqual(port.output, b"~SNL!" + token + b"\n")
        self.assertFalse(port.data)
        self.assertIsNone(self.session.file)
        self.assertFalse(list(self.root.iterdir()))
        self.assertEqual(output.getvalue(), "")

    def test_ready_closes_stale_host_session(self):
        self.open()
        self.write(0, b"keep")
        token = b"A" * 16
        self.assertEqual(self.request(b"~SNL?" + token + b"\n"), b"~SNL!" + token + b"\n")
        self.assertIsNone(self.session.file)
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")

    def test_ready_restarts_after_an_interrupted_probe(self):
        token = b"P" * 16
        port = Port(b"~SNL?AAA~SNL?" + token + b"\n")
        snl.serve_one(port, self.session)
        self.assertEqual(port.output, b"~SNL!" + token + b"\n")
        self.assertFalse(port.data)

    def test_ready_rejects_malformed_probes_without_response(self):
        for packet in (b"~BAD?" + b"A" * 16 + b"\n", b"~SNL?ABC\n",
                       b"~SNL?" + b"Q" * 16 + b"\n",
                       b"~SNL?" + b"A" * 17 + b"\n"):
            port = Port(packet)
            while port.data:
                snl.serve_one(port, self.session)
            self.assertFalse(port.output)
            self.assertIsNone(self.session.file)

    def test_ready_tail_then_fresh_probe_and_open(self):
        token = b"B" * 16
        port = Port(b"L?AAAA\n~SNL?" + token + b"\n\x11\x01\x02\x08test_bas")
        while port.data:
            snl.serve_one(port, self.session)
        self.assertEqual(port.output, b"~SNL!" + token + b"\n" + bytes(5))

    def test_directory_records_preserve_names_metadata_and_wrapped_sizes(self):
        self.open(name=b"Mixed_Bin")
        metadata = bytes.fromhex("00010000100000000000")
        self.request(b"\x16" + bytes(4) + metadata)
        self.write(0, b"abc")
        self.request(b"\x04")
        wrapper, payload = self.emulator_file()
        (self.root / "test_bas").rename(self.root / "Assembler")
        (self.root / "empty").write_bytes(b"")
        (self.root / "subdirectory").mkdir()
        (self.root / ".DS_Store").write_bytes(b"hidden")
        (self.root / ("x" * 37)).write_bytes(b"long")
        (self.root / "link").symlink_to(self.root / "empty")
        self.assertEqual(self.open(name=b"", mode=4), b"\x00" + struct.pack(">I", 192))
        reply = self.read(0, 512)
        self.assertEqual(reply[:3], b"\xf6\x00\xc0")
        records = [reply[3+i:3+i+64] for i in range(0, 192, 64)]
        names = [r[16:16+int.from_bytes(r[14:16], "big")] for r in records]
        self.assertEqual(names, [b"Assembler", b"empty", b"Mixed_Bin"])
        self.assertEqual([int.from_bytes(r[:4], "big") for r in records], [len(payload)+64, 64, 67])
        self.assertEqual(records[0][4:14], wrapper[20:30])
        self.assertEqual(records[2][4:14], metadata)
        self.assertEqual(self.request(b"\x15")[6], 255)
        self.assertEqual(self.read(192, 64), b"\xf6\x00\x00")
        self.assertEqual(self.request(b"\x04"), b"\x00")

    def test_directory_snapshot_spans_blocks_and_refreshes_on_reopen(self):
        for i in range(11):
            (self.root / f"File_{i:02}").write_bytes(bytes(i))
        self.assertEqual(self.open(name=b"", mode=4), b"\x00" + struct.pack(">I", 704))
        (self.root / "Later").write_bytes(b"new")
        first, last = self.read(0, 512), self.read(512, 512)
        self.assertEqual(first[:3], b"\x00\x02\x00")
        self.assertEqual(last[:3], b"\xf6\x00\xc0")
        self.assertEqual(len(first[3:]+last[3:]), 704)
        self.assertNotIn(b"Later", first+last)
        self.request(b"\x04")
        self.assertEqual(self.open(name=b"", mode=4), b"\x00" + struct.pack(">I", 768))

    def test_empty_directory_and_case_insensitive_prefix(self):
        self.assertEqual(self.open(name=b"", mode=4), bytes(5))
        self.assertEqual(self.read(0, 64), b"\xf6\x00\x00")
        self.request(b"\x04")
        for name in ("Source_A", "source_b", "Other"):
            (self.root / name).write_bytes(b"text")
        self.assertEqual(self.open(name=b"SOURCE_", mode=4), b"\x00\x00\x00\x00\x80")
        records = self.read(0, 128)[3:]
        self.assertEqual(records[16:24], b"Source_A")
        self.assertEqual(records[80:88], b"source_b")

    def test_directory_is_read_only_and_can_be_flushed_and_closed(self):
        self.open(name=b"", mode=4)
        self.assertEqual(self.write(0, b"x"), snl.status(snl.RO) + bytes(2))
        self.assertEqual(self.request(b"\x16" + bytes(14)), snl.status(snl.RO))
        self.assertEqual(self.request(b"\x17"), b"\x00")
        self.assertEqual(self.open(name=b"missing", mode=255), snl.status(snl.IU))
        self.assertEqual(self.request(b"\x04"), b"\x00")
        self.assertFalse(list(self.root.iterdir()))

    def test_medium_info_returns_10_byte_label_and_sector_counts(self):
        self.session.drives["3"] = self.root
        self.open(name=b"", mode=4, drive=3)
        with patch.object(snl.shutil, "disk_usage", return_value=SimpleNamespace(total=8192, free=2048)):
            self.assertEqual(self.request(b"\x18"), b"\x00\x00\x04\x00\x10SNL3      ")
        with patch.object(snl.shutil, "disk_usage", return_value=SimpleNamespace(total=10**12, free=10**11)):
            self.assertEqual(self.request(b"\x18")[1:5], b"\x7f\xff" * 2)
        self.request(b"\x04")
        self.assertEqual(self.request(b"\x18"), snl.status(-6))

    def test_directory_rejects_bad_prefix_and_missing_drive(self):
        for name in (b"../", b"a/b", b"a\\b", b"\xff", b".SNL_HEADERS", b"x" * 37):
            self.assertEqual(self.open(name=name, mode=4), snl.status(snl.BN))
        self.assertEqual(self.open(name=b"", mode=4, drive=2), snl.status(snl.NF))

    def test_directory_rejects_ambiguous_linux_names(self):
        (self.root / "Assembler").write_bytes(b"keep")
        entries = [self.root / "Assembler", self.root / "assembler"]
        with patch.object(Path, "iterdir", return_value=entries):
            self.assertEqual(self.open(name=b"", mode=4), snl.status(snl.BN))
        self.assertEqual((self.root / "Assembler").read_bytes(), b"keep")

    def test_case_insensitive_open_preserves_name_and_sidecar(self):
        self.assertEqual(self.open(name=b"Assembler"), bytes(5))
        metadata = bytes.fromhex("00010000040000000000")
        self.request(b"\x16" + bytes(4) + metadata)
        self.write(0, b"code")
        self.request(b"\x04")
        for name in (b"assembler", b"ASSEMBLER", b"aSsEmBlEr"):
            self.assertEqual(self.open(name=name, mode=1), b"\x00\x00\x00\x00\x04")
            h = self.request(b"\x15")
            self.assertEqual(h[5:15], metadata)
            self.assertEqual(h[15:26], b"\x00\x09Assembler")
            self.assertEqual(self.read(0, 4), b"\x00\x00\x04code")
        self.assertTrue((self.root / "Assembler").exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".snl_headers", "Assembler"])
        self.assertTrue((self.root / ".snl_headers" / "Assembler.json").exists())

    def test_case_insensitive_create_and_overwrite(self):
        self.open(name=b"Mixed_Bin")
        self.write(0, b"old")
        self.request(b"\x04")
        self.assertEqual(self.open(name=b"mixed_bin"), snl.status(snl.EX))
        self.assertEqual(self.open(name=b"MIXED_BIN", mode=3), bytes(5))
        self.write(0, b"new")
        self.request(b"\x04")
        self.assertEqual((self.root / "Mixed_Bin").read_bytes(), b"new")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".snl_headers", "Mixed_Bin"])

    def test_case_insensitive_emulator_file(self):
        wrapper, payload = self.emulator_file()
        (self.root / "test_bas").rename(self.root / "Assembler")
        self.assertEqual(self.open(name=b"assembler", mode=1), b"\x00" + struct.pack(">I", len(payload)))
        self.assertEqual(self.request(b"\x15")[5:15], wrapper[20:30])
        self.assertEqual(self.read(0, len(payload)), b"\x00" + struct.pack(">H", len(payload)) + payload)

    def test_case_insensitive_reserved_names_and_symlink_checks(self):
        self.assertEqual(self.open(name=b".SNL_HEADERS"), snl.status(snl.BN))
        with tempfile.TemporaryDirectory() as elsewhere:
            (self.root / "Escape").symlink_to(Path(elsewhere) / "payload")
            self.assertEqual(self.open(name=b"ESCAPE", mode=3), snl.status(snl.BN))

    def test_case_collision_is_rejected_without_modifying_files(self):
        (self.root / "Assembler").write_bytes(b"one")
        # Simulate Linux's two directory entries even on a Mac filesystem.
        entries = [self.root / "Assembler", self.root / "assembler"]
        with patch.object(Path, "iterdir", return_value=entries):
            for mode in (0, 1, 2, 3, 255):
                self.assertEqual(self.open(name=b"Assembler", mode=mode), snl.status(snl.BN))
        self.assertEqual((self.root / "Assembler").read_bytes(), b"one")

    def emulator_file(self, length=30, payload=b"\x60\x00\x00\xff\x1a\n"):
        metadata = bytes.fromhex("00010000040000000000")
        wrapper = snl.EMULATOR_MAGIC + struct.pack(">H", length // 2) + metadata
        wrapper += bytes(range(length - 30))
        (self.root / "test_bas").write_bytes(wrapper + payload)
        return wrapper, payload

    def test_emulator_wrappers_hide_prefix_and_report_payload_length(self):
        for length in (30, 44):
            with self.subTest(length=length):
                wrapper, payload = self.emulator_file(length)
                self.assertEqual(self.open(mode=1), b"\x00" + struct.pack(">I", len(payload)))
                h = self.request(b"\x15")
                self.assertEqual(h[1:5], struct.pack(">I", len(payload)))
                self.assertEqual(h[5:15], wrapper[20:30])
                self.assertEqual(self.read(0, 512), b"\xf6" + struct.pack(">H", len(payload)) + payload)
                self.assertEqual(self.read(2, 2), b"\x00\x00\x02" + payload[2:4])
                self.assertEqual(self.read(len(payload), 1), b"\xf6\x00\x00")
                self.request(b"\x04")
                self.assertEqual((self.root / "test_bas").read_bytes(), wrapper + payload)

    def test_emulator_write_and_header_update_preserve_wrapper_and_extension(self):
        wrapper, payload = self.emulator_file(44)
        self.open(mode=0)
        self.assertEqual(self.write(1, b"XY"), b"\x00\x00\x02")
        self.assertEqual(self.write(len(payload), b"MORE"), b"\x00\x00\x04")
        metadata = bytes.fromhex("00010000200000000000")
        self.assertEqual(self.request(b"\x16" + bytes(4) + metadata), b"\x00")
        self.request(b"\x04")
        raw = (self.root / "test_bas").read_bytes()
        expected_payload = payload[:1] + b"XY" + payload[3:] + b"MORE"
        self.assertEqual(raw, wrapper[:20] + metadata + wrapper[30:] + expected_payload)
        self.assertTrue((self.root / ".snl_headers" / "test_bas.json").exists())
        self.assertEqual(self.open(mode=1), b"\x00" + struct.pack(">I", len(expected_payload)))
        self.assertEqual(self.request(b"\x15")[5:15], metadata)

    def test_emulator_wrapper_overrides_stale_sidecar(self):
        self.open()
        self.request(b"\x04")
        wrapper, payload = self.emulator_file()
        # Even a malformed old sidecar must not hide a fresh emulator header.
        (self.root / ".snl_headers" / "test_bas.json").write_text("stale")
        self.assertEqual(self.open(mode=1), b"\x00" + struct.pack(">I", len(payload)))
        self.assertEqual(self.request(b"\x15")[5:15], wrapper[20:30])

    def test_overwrite_emulator_file_starts_plain_and_resets_metadata(self):
        self.emulator_file()
        self.open(mode=0)
        self.assertEqual(self.open(mode=3), bytes(5))
        self.assertEqual(self.write(0, b"plain"), b"\x00\x00\x05")
        self.request(b"\x04")
        self.assertEqual((self.root / "test_bas").read_bytes(), b"plain")
        self.open(mode=1)
        self.assertEqual(self.session.payload_base, 0)
        self.assertEqual(self.request(b"\x15")[5:15], bytes(10))

    def test_invalid_emulator_wrapper_is_rejected_without_open_file(self):
        for raw in (snl.EMULATOR_MAGIC, snl.EMULATOR_MAGIC + b"\x00",
                    snl.EMULATOR_MAGIC + b"\x00\x0f" + bytes(9),
                    snl.EMULATOR_MAGIC + b"\x00\x16" + bytes(10),
                    snl.EMULATOR_MAGIC + b"\xff\xff" + bytes(30)):
            with self.subTest(raw=raw):
                (self.root / "test_bas").write_bytes(raw)
                self.assertEqual(self.open(mode=1), snl.status(snl.BN))
                self.assertIsNone(self.session.file)
                self.assertEqual((self.root / "test_bas").read_bytes(), raw)

    def test_empty_emulator_payload_and_read_only_protection(self):
        wrapper, _ = self.emulator_file(payload=b"")
        self.assertEqual(self.open(mode=1), bytes(5))
        self.assertEqual(self.read(0, 1), b"\xf6\x00\x00")
        self.assertEqual(self.write(0, b"x"), snl.status(snl.RO) + bytes(2))
        self.assertEqual(self.request(b"\x16" + bytes(14)), snl.status(snl.RO))
        self.assertEqual((self.root / "test_bas").read_bytes(), wrapper)

    def test_eof_partial_and_absolute_positions(self):
        self.open()
        self.write(0, b"one\ntwo\n")
        self.assertEqual(self.read(4, 9), b"\xf6\x00\x04two\n")
        self.assertEqual(self.read(0, 4), b"\x00\x00\x04one\n")
        self.assertEqual(self.read(0, 0), b"\x00\x00\x00")
        self.assertEqual(self.write(4, b"T"), b"\x00\x00\x01")
        self.assertEqual(self.read(4, 4), b"\x00\x00\x04Two\n")

    def test_bad_names_and_symlinks(self):
        for name in (b"", b"../escape", b"x/y", b"x\\y", b"a\x00b", b"x" * 37, b"\xff", b".snl_headers"):
            self.assertEqual(self.open(name=name), snl.status(snl.BN), name)
        with tempfile.TemporaryDirectory() as elsewhere:
            (self.root / "escape").symlink_to(Path(elsewhere) / "payload")
            self.assertEqual(self.open(name=b"escape"), snl.status(snl.BN))

    def test_bad_count_is_drained_before_next_command(self):
        self.open()
        packet = b"\x13" + struct.pack(">IH", 0, 513) + bytes(513)
        port = Port(packet + b"\x15")
        snl.serve_one(port, self.session)
        snl.serve_one(port, self.session)
        self.assertEqual(port.output[:3], snl.status(snl.BP) + bytes(2))
        self.assertEqual(len(port.output), 3 + 65)
        self.assertEqual(self.read(0, 513), snl.status(snl.BP) + bytes(2))

    def test_short_host_write_reports_actual_count(self):
        self.open()
        original = self.session.file
        class ShortWriter:
            def seek(self, offset):
                original.seek(offset)
            def write(self, data):
                return original.write(data[:2])
        self.session.file = ShortWriter()
        try:
            self.assertEqual(self.write(0, b"abcdef"), snl.status(snl.DF) + b"\x00\x02")
        finally:
            self.session.file = original
        self.assertEqual((self.root / "test_bas").read_bytes(), b"ab")

    def test_trace_identifies_unknown_command_and_bad_open_mode(self):
        output = io.StringIO()
        unknown = Port(b"\x01")  # obsolete protocol OPEN
        bad_mode = Port(b"\x11\x01\x05\x04test")
        with contextlib.redirect_stdout(output):
            snl.serve_one(unknown, self.session, trace=True)
            snl.serve_one(bad_mode, self.session, trace=True)
        self.assertEqual(unknown.output, b"")
        self.assertEqual(bad_mode.output, snl.status(snl.NI))
        text = output.getvalue()
        self.assertIn("RX command=$01 UNKNOWN", text)
        self.assertIn("DROP unknown command=$01; no reply", text)
        self.assertNotIn("TX command=$01", text)
        self.assertIn("drive=1 mode=5 name_length=4 name=b'test'", text)
        self.assertIn("TX command=$11 status=$ED (-19)", text)

    def test_stray_ctrl_z_before_open_does_not_pollute_reply(self):
        (self.root / "trial_bas").write_bytes(b'10 PRINT "HELLO"\n')
        size = (self.root / "trial_bas").stat().st_size
        port = Port(b"\x1a\x11\x01\x01\x09trial_bas")
        snl.serve_one(port, self.session)
        self.assertEqual(port.output, b"")
        snl.serve_one(port, self.session)
        self.assertEqual(port.output, b"\x00" + struct.pack(">I", size))
        self.assertEqual(port.data, b"")

    def test_paced_open_reply_preserves_bytes_and_flushes_each_byte(self):
        class PacedPort(Port):
            def __init__(self, data):
                super().__init__(data)
                self.flushes = 0
            def flush(self):
                self.flushes += 1
        port = PacedPort(b"\x11\x01\x02\x04test")
        with patch.object(snl.time, "sleep") as sleep:
            snl.serve_one(port, self.session, reply_delay=0.05, byte_delay=0.01)
        self.assertEqual(port.output, bytes(5))
        self.assertEqual(port.flushes, 5)
        self.assertEqual([args.args[0] for args in sleep.call_args_list], [0.05] + [0.01] * 4)

    def test_standalone_link_test_matches_open_reply(self):
        port = Port(b"\x1a~")
        with contextlib.redirect_stdout(io.StringIO()):
            snl.serve_link_test(port)
            self.assertEqual(port.output, b"")
            snl.serve_link_test(port)
        self.assertEqual(port.output, b"\x00\x00\x00\x00\x17")
        self.assertIsNone(self.session.file)

    def test_normal_requests_are_quiet_and_unpaced_by_default(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(snl.time, "sleep") as sleep:
            self.assertEqual(self.open(), bytes(5))
            self.assertEqual(self.write(0, b"hello"), b"\x00\x00\x05")
            self.assertEqual(self.read(0, 5), b"\x00\x00\x05hello")
            self.assertEqual(self.request(b"\x04"), b"\x00")
        self.assertEqual(output.getvalue(), "")
        sleep.assert_not_called()

    def test_ql_serial_format_uses_two_stop_bits(self):
        settings = snl.serial_settings({"baud_rate": 9600})
        self.assertEqual(settings["stopbits"], 2)
        self.assertEqual(settings["bytesize"], 8)
        self.assertEqual(settings["parity"], "N")
        self.assertFalse(settings["xonxoff"])
        self.assertEqual(snl.serial_settings({"stop_bits": 1.5})["stopbits"], 1.5)
        with self.assertRaises(ValueError):
            snl.serial_settings({"stop_bits": 3})

    def test_missing_file_and_truncated_stream(self):
        self.assertEqual(self.read(0, 1), snl.status(-6) + bytes(2))
        self.assertEqual(self.request(b"\x15"), snl.status(-6))
        with self.assertRaises(EOFError):
            self.request(b"\x11\x01\x02\x04ab")
        self.assertFalse((self.root / "ab").exists())


if __name__ == "__main__":
    unittest.main()
