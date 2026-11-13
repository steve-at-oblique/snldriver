"""Metadata protocol contracts, persistence and host-clock policy."""
import datetime
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_snl_serial as fixtures
snl = fixtures.snl


class MetadataTests(unittest.TestCase):
    setUp = fixtures.SerialTests.setUp
    tearDown = fixtures.SerialTests.tearDown
    request = fixtures.SerialTests.request
    open = fixtures.SerialTests.open
    write = fixtures.SerialTests.write
    emulator_file = fixtures.SerialTests.emulator_file

    def date(self, value=0xFFFFFFFF, selector=0):
        return self.request(b"\x19" + struct.pack(">IB", value, selector))

    def version(self, value=0xFFFFFFFF):
        return self.request(b"\x1c" + struct.pack(">I", value))

    def value(self, number):
        return b"\x00" + struct.pack(">I", number)

    def test_host_clock_uses_local_qdos_epoch(self):
        real_datetime = datetime.datetime
        expected = int((real_datetime(2026, 11, 12, 20, 22)
                        - real_datetime(1961, 1, 1)).total_seconds())
        with patch.object(snl.datetime, "datetime") as clock:
            clock.now.return_value = real_datetime(2026, 11, 12, 20, 22)
            clock.side_effect = real_datetime
            self.assertEqual(snl.qdos_now(), expected)

    def test_automatic_date_version_and_repeated_flush(self):
        with patch.object(snl, "qdos_now", return_value=123456789):
            self.open()
            self.write(0, b"hello")
            self.request(b"\x17")
            self.assertEqual(self.date(), self.value(123456789))
            self.assertEqual(self.version(), self.value(1))
            self.request(b"\x17")
            self.assertEqual(self.version(), self.value(1))
        self.request(b"\x04")
        self.open(mode=1)
        self.assertEqual(self.date(), self.value(123456789))
        self.assertEqual(self.version(), self.value(1))
        self.assertEqual((self.root / "test_bas").read_bytes(), b"hello")

    def test_explicit_metadata_survives_later_writes_flush_close(self):
        self.open()
        self.assertEqual(self.date(1700000000), self.value(1700000000))
        self.assertEqual(self.date(1600000000, 2), self.value(1600000000))
        self.assertEqual(self.version(42), self.value(42))
        self.write(0, b"payload")
        self.request(b"\x17")
        self.request(b"\x04")
        self.open(mode=1)
        self.assertEqual(self.date(), self.value(1700000000))
        self.assertEqual(self.date(selector=2), self.value(1600000000))
        self.assertEqual(self.version(), self.value(42))
        h = self.request(b"\x15")[1:]
        self.assertEqual(h[52:58], struct.pack(">IH", 1700000000, 42))
        self.assertEqual(h[60:64], struct.pack(">I", 1600000000))

    def test_preserve_version_zero_and_invalid_keys(self):
        self.open()
        self.assertEqual(self.version(0), self.value(0))
        self.write(0, b"x")
        self.request(b"\x17")
        self.assertEqual(self.version(), self.value(0))
        self.assertEqual(self.version(65536), snl.status(snl.BP))
        self.assertEqual(self.date(0, 1), snl.status(snl.BP))
        with patch.object(snl, "qdos_now", return_value=1900000000):
            self.assertEqual(self.date(0), self.value(1900000000))
        # Errors consumed complete frames; the following query is aligned.
        self.assertEqual(self.version(65535), self.value(65535))

    def test_readonly_backup_allowed_update_and_version_rejected(self):
        self.open()
        self.request(b"\x04")
        self.open(mode=1)
        mtime = (self.root / "test_bas").stat().st_mtime_ns
        self.assertEqual(self.date(123), snl.status(snl.RO))
        self.assertEqual(self.version(2), snl.status(snl.RO))
        self.assertEqual(self.date(456, 2), self.value(456))
        self.assertEqual(self.version(0), self.version())
        self.assertEqual((self.root / "test_bas").stat().st_mtime_ns, mtime)
        self.request(b"\x04")
        self.open(mode=1)
        self.assertEqual(self.date(selector=2), self.value(456))

    def test_missing_metadata_dates_are_unset_and_no_linux_fallback(self):
        (self.root / "test_bas").write_bytes(b"outside")
        self.open(mode=1)
        self.assertEqual(self.date(), self.value(0))
        self.assertEqual(self.version(), self.value(0))
        self.assertFalse((self.root / ".snl_headers").exists())

    def test_wrappers_preserve_payload_and_attributes_with_metadata(self):
        for size in (30, 44):
            with self.subTest(size=size):
                self.session.close()
                wrapper, payload = self.emulator_file(size)
                self.open(mode=0)
                self.assertEqual(self.date(1900000000), self.value(1900000000))
                self.assertEqual(self.version(9), self.value(9))
                self.request(b"\x04")
                self.assertEqual((self.root / "test_bas").read_bytes(), wrapper + payload)
                self.open(mode=1)
                self.assertEqual(self.date(), self.value(1900000000))
                self.assertEqual(self.version(), self.value(9))
                self.assertEqual(self.request(b"\x15")[5:15], wrapper[20:30])

    def test_extended_info_layout_and_32bit_sector_counts(self):
        self.open(name=b"", mode=4)
        usage = SimpleNamespace(total=10**12, free=10**11)
        with patch.object(snl.shutil, "disk_usage", return_value=usage):
            reply = self.request(b"\x1d" + bytes(4))
        self.assertEqual(len(reply), 65)
        info = reply[1:]
        self.assertEqual(info[:6], b"\x00\x04SNL1")
        self.assertEqual(info[22:29], b"\x00\x03SNL\x00\x01")
        self.assertEqual(struct.unpack_from(">HIII", info, 30),
                         (512, usage.total // 512, usage.free // 512, 64))
        self.assertEqual(info[44], 1)
        self.assertEqual(info[47], 2)
        self.assertEqual(info[49:], b"\xff" * 15)
        self.assertEqual(self.request(b"\x1d\x00\x00\x00\x01"), snl.status(snl.BP))
        self.assertEqual(self.date(), snl.status(snl.BP))
        self.assertEqual(self.version(), snl.status(snl.BP))

    def test_update_after_reopen_increments_version_and_uses_new_clock(self):
        self.open()
        self.version(41)
        self.date(1700000000)
        self.request(b"\x04")
        self.open(mode=0)
        with patch.object(snl, "qdos_now", return_value=1800000000):
            self.write(0, b"new")
            self.request(b"\x17")
        self.assertEqual(self.version(), self.value(42))
        self.assertEqual(self.date(), self.value(1800000000))
        self.version(65535)
        self.request(b"\x04")
        self.open(mode=0)
        self.write(0, b"wrap")
        self.request(b"\x17")
        self.assertEqual(self.version(), self.value(0))

    def test_extended_info_saturates_and_reports_medium_readonly(self):
        self.open()
        usage = SimpleNamespace(total=2**60, free=2**59)
        with patch.object(snl.shutil, "disk_usage", return_value=usage), \
                patch.object(snl.os, "access", return_value=False):
            info = self.request(b"\x1d" + bytes(4))[1:]
        self.assertEqual(info[29], 1)
        self.assertEqual(info[32:40], b"\xff" * 8)

    def test_metadata_persistence_error_does_not_claim_success(self):
        self.open()
        before = self.session.header[:]
        with patch.object(self.session, "save_header", side_effect=PermissionError):
            self.assertEqual(self.date(123), snl.status(snl.RO))
            self.assertEqual(self.version(42), snl.status(snl.RO))
        self.assertEqual(self.session.header, before)
        self.assertFalse(self.session.date_fixed)
        self.assertFalse(self.session.version_fixed)
