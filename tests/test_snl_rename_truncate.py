"""Rename/truncate wire behavior and payload/metadata consistency."""
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_snl_serial as fixtures
snl = fixtures.snl


class RenameTruncateTests(unittest.TestCase):
    setUp = fixtures.SerialTests.setUp
    tearDown = fixtures.SerialTests.tearDown
    request = fixtures.SerialTests.request
    open = fixtures.SerialTests.open
    write = fixtures.SerialTests.write
    read = fixtures.SerialTests.read
    emulator_file = fixtures.SerialTests.emulator_file

    def rename(self, name):
        return self.request(bytes((0x1E, len(name))) + name)

    def truncate(self, offset):
        return self.request(b"\x1f" + struct.pack(">I", offset))

    def test_rename_moves_metadata_and_keeps_channel_usable(self):
        self.open()
        self.write(0, b"payload")
        self.session.file_date(1700000000, 0)
        self.session.file_version(42)
        self.assertEqual(self.rename(b"SNL1_Renamed"), b"\x00")
        self.assertFalse((self.root / "test_bas").exists())
        self.assertFalse((self.root / ".snl_headers/test_bas.json").exists())
        self.assertTrue((self.root / ".snl_headers/Renamed.json").exists())
        self.assertEqual(self.read(0, 7), b"\x00\x00\x07payload")
        self.assertEqual(self.session.read_header()[14:23], b"\x00\x07Renamed")
        self.write(7, b"!")
        self.request(b"\x04")
        self.open(b"renamed", mode=1)
        self.assertEqual(self.session.file_date(0xFFFFFFFF, 0), 1700000000)
        self.assertEqual(self.session.file_version(0xFFFFFFFF), 42)
        self.assertEqual((self.root / "Renamed").read_bytes(), b"payload!")

    def test_case_only_and_identical_rename_without_sidecar(self):
        (self.root / "test_bas").write_bytes(b"outside")
        self.open(mode=0)
        self.assertEqual(self.rename(b"snl1_test_bas"), b"\x00")
        self.assertEqual(self.rename(b"snl1_TEST_bas"), b"\x00")
        self.assertIn("TEST_bas", [p.name for p in self.root.iterdir()])
        self.request(b"\x04")
        self.assertFalse((self.root / ".snl_headers").exists())

    def test_collisions_and_invalid_names_leave_original_untouched(self):
        self.open()
        self.write(0, b"source")
        (self.root / "Occupied").write_bytes(b"destination")
        for name in (b"snl1_occupied", b"snl1_OCCUPIED"):
            self.assertEqual(self.rename(name), snl.status(snl.EX))
        (self.root / ".snl_headers/orphan.json").write_text("old")
        self.assertEqual(self.rename(b"snl1_ORPHAN"), snl.status(snl.EX))
        for name in (b"win1_new", b"snl2_new", b"snl1_", b"snl1_../bad",
                     b"snl1_.snl_private", b"snl1_" + b"a" * 37):
            self.assertEqual(self.rename(name), snl.status(snl.BN), name)
        self.assertEqual(self.session.path.name, "test_bas")
        self.assertEqual((self.root / "test_bas").read_bytes(), b"source")
        self.assertEqual((self.root / "Occupied").read_bytes(), b"destination")
        self.assertEqual(self.rename(b"snl1_ok"), b"\x00")

    def test_sidecar_failure_rolls_payload_back(self):
        self.open()
        old = self.session.path
        original = Path.rename
        def fail_sidecar(path, target):
            if path.suffix == ".json":
                raise PermissionError("injected metadata failure")
            return original(path, target)
        with patch.object(Path, "rename", fail_sidecar):
            self.assertEqual(self.rename(b"snl1_new"), snl.status(snl.RO))
        self.assertEqual(self.session.path, old)
        self.assertTrue(old.exists())
        self.assertTrue(self.session.meta_path().exists())
        self.assertFalse((self.root / "new").exists())

    def test_payload_rename_failure_leaves_metadata_and_session(self):
        self.open()
        old = self.session.path
        with patch.object(Path, "rename", side_effect=PermissionError):
            self.assertEqual(self.rename(b"snl1_new"), snl.status(snl.RO))
        self.assertEqual(self.session.path, old)
        self.assertTrue(old.exists())
        self.assertTrue(self.session.meta_path().exists())

    def test_truncate_os_error_does_not_mark_file_modified(self):
        self.open()
        self.write(0, b"original")
        self.request(b"\x17")
        with patch.object(self.session, "file") as file:
            with patch.object(self.session, "file_size", return_value=8):
                file.truncate.side_effect = PermissionError
                self.assertEqual(self.truncate(3), snl.status(snl.RO))
        self.assertFalse(self.session.modified)
        self.assertEqual((self.root / "test_bas").read_bytes(), b"original")

    def test_readonly_directory_and_closed_channel_rejections(self):
        self.open()
        self.request(b"\x04")
        self.open(mode=1)
        self.assertEqual(self.rename(b"snl1_new"), snl.status(snl.RO))
        self.assertEqual(self.truncate(0), snl.status(snl.RO))
        self.request(b"\x04")
        self.open(b"", mode=4)
        self.assertEqual(self.rename(b"snl1_new"), snl.status(snl.RO))
        self.assertEqual(self.truncate(0), snl.status(snl.RO))
        self.request(b"\x04")
        self.assertEqual(self.rename(b"snl1_new"), snl.status(-6))
        self.assertEqual(self.truncate(0), snl.status(-6))

    def test_truncate_middle_end_zero_and_append(self):
        self.open()
        self.write(0, b"abcdefgh")
        self.assertEqual(self.truncate(9), snl.status(snl.BP))
        self.assertEqual(self.truncate(8), b"\x00")
        self.assertEqual(self.truncate(3), b"\x00")
        self.assertEqual(self.read(0, 8), snl.status(snl.EF) + b"\x00\x03abc")
        self.write(3, b"XY")
        self.request(b"\x04")
        self.open(mode=0)
        self.assertEqual(self.session.file_size(), 5)
        self.assertEqual(self.truncate(0), b"\x00")
        self.assertEqual(self.read(0, 1), snl.status(snl.EF) + b"\x00\x00")
        self.write(0, b"new")
        self.request(b"\x04")
        self.assertEqual((self.root / "test_bas").read_bytes(), b"new")

    def test_wrapped_file_rename_truncate_preserve_wrapper(self):
        for length in (30, 44):
            with self.subTest(length=length):
                self.session.close()
                wrapper, payload = self.emulator_file(length)
                self.open(mode=0)
                self.session.file_version(42)
                new = f"wrapped{length}".encode()
                self.assertEqual(self.rename(b"snl1_" + new), b"\x00")
                self.assertEqual(self.truncate(2), b"\x00")
                self.request(b"\x04")
                self.assertEqual((self.root / new.decode()).read_bytes(), wrapper + payload[:2])
                self.open(new, mode=1)
                self.assertEqual(self.session.file_size(), 2)
                self.assertEqual(self.session.file_version(0xFFFFFFFF), 42)
                self.assertEqual(self.session.read_header()[4:14], wrapper[20:30])

    def test_symlink_destination_and_metadata_are_rejected(self):
        self.open()
        (self.root / "link").symlink_to(self.root / "test_bas")
        self.assertEqual(self.rename(b"snl1_link"), snl.status(snl.BN))
        self.session.meta_path().unlink()
        self.session.meta_path().symlink_to(self.root / "test_bas")
        self.assertEqual(self.rename(b"snl1_new"), snl.status(snl.BN))
        self.session.meta_path().unlink()
