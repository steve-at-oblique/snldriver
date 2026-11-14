"""Multi-channel protocol, open-file policy, lifecycle and daemon statistics."""
import contextlib
import io
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_snl_serial import snl, Port
from tests.test_snl_buffer import CacheCPU


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pool = snl.SessionPool({"1": self.root}, statistics=False)
        self.pool.next_handle = 100

    def tearDown(self):
        self.pool.statistics = False
        self.pool.close_all()
        self.tmp.cleanup()

    def request(self, packet, pool=None):
        port = Port(packet)
        snl.serve_one(port, pool or self.pool)
        self.assertFalse(port.data)
        return bytes(port.output)

    def open(self, name, mode=2):
        response = self.request(bytes((0x21, 1, mode, len(name))) + name)
        self.assertEqual(response[0], 0, response)
        self.assertEqual(len(response), 9)
        return struct.unpack(">II", response[1:])

    def call(self, handle, cmd, body=b""):
        return self.request(b"\x22" + struct.pack(">IB", handle, cmd) + body)

    def write(self, handle, offset, data):
        return self.call(handle, 0x13, struct.pack(">IH", offset, len(data)) + data)

    def read(self, handle, offset, count):
        return self.call(handle, 0x12, struct.pack(">IH", offset, count))

    def test_interleaved_files_have_independent_positions_headers_and_lifetime(self):
        first, _ = self.open(b"first")
        second, _ = self.open(b"second")
        self.assertNotEqual(first, second)
        self.assertEqual(self.pool.peak, 2)
        self.assertEqual(self.write(first, 0, b"ABC"), b"\x00\x00\x03")
        self.assertEqual(self.write(second, 0, b"xyz"), b"\x00\x00\x03")
        self.assertEqual(self.read(first, 1, 2), b"\x00\x00\x02BC")
        self.assertEqual(self.read(second, 0, 3), b"\x00\x00\x03xyz")
        self.assertEqual(self.call(first, 0x1C, struct.pack(">I", 42)), b"\x00\x00\x00\x00\x2a")
        self.assertEqual(self.call(second, 0x1C, bytes(4)), b"\x00" + bytes(4))
        self.assertEqual(self.call(first, 0x04), b"\x00")
        self.assertEqual(self.write(second, 3, b"!"), b"\x00\x00\x01")
        self.assertEqual(self.call(second, 0x04), b"\x00")
        self.assertEqual((self.pool.opens, self.pool.closes, len(self.pool.sessions)), (2, 2, 0))
        self.assertEqual((self.root / "first").read_bytes(), b"ABC")
        self.assertEqual((self.root / "second").read_bytes(), b"xyz!")

    def test_directory_snapshot_can_remain_open_while_copying_files(self):
        (self.root / "source").write_bytes(bytes(range(256)) * 5)
        directory, _ = self.open(b"", 4)
        source, size = self.open(b"source", 1)
        dest, _ = self.open(b"destination")
        for offset in range(0, size, 512):
            payload = self.read(source, offset, min(512, size-offset))[3:]
            self.assertEqual(self.write(dest, offset, payload)[0], 0)
        self.assertEqual(self.pool.peak, 3)
        self.assertEqual(self.call(source, 0x04), b"\x00")
        self.assertEqual(self.call(dest, 0x04), b"\x00")
        self.assertEqual(len(self.pool.sessions), 1)
        self.assertEqual(self.read(directory, 0, 64)[0], 0)
        self.assertEqual((self.root / "source").read_bytes(), (self.root / "destination").read_bytes())

    def test_unknown_handle_consumes_write_and_rename_frames(self):
        unknown = 999
        self.assertEqual(self.write(unknown, 0, b"payload"), snl.status(-6) + bytes(2))
        self.assertEqual(self.read(unknown, 0, 20), snl.status(-6) + bytes(2))
        for cmd, body in ((4, b""), (0x15, b""), (0x16, bytes(14)),
                          (0x19, bytes(5)), (0x1C, bytes(4)), (0x1D, bytes(4)),
                          (0x1E, b"\x08snl1_new"), (0x1F, bytes(4)), (0x20, bytes(4))):
            self.assertEqual(self.call(unknown, cmd, body), snl.status(-6))
        valid, _ = self.open(b"after_errors")
        self.assertEqual(self.write(valid, 0, b"ok"), b"\x00\x00\x02")

    def test_readiness_same_installation_preserves_channels_new_installation_closes(self):
        self.request(b"~SNL?" + b"A" * 16 + b"\n")
        handle, _ = self.open(b"open_file")
        self.request(b"~SNL?" + b"A" * 8 + b"B" * 8 + b"\n")
        self.assertIn(handle, self.pool.sessions)
        self.request(b"~SNL?" + b"C" * 8 + b"A" * 8 + b"\n")
        self.assertFalse(self.pool.sessions)
        self.assertEqual(self.call(handle, 0x17), snl.status(-6))

    def test_reset_counter_closes_stale_channels_even_with_same_clock_epoch(self):
        self.request(b"~SNL?" + b"A" * 8 + b"B" * 8 + b"\n")
        self.open(b"stale")
        self.request(b"~SNL?" + b"A" * 8 + b"A" * 7 + b"B\n")
        self.assertFalse(self.pool.sessions)

    def test_restarted_daemon_returns_unknown_handle(self):
        handle, _ = self.open(b"before_restart")
        self.pool.close_all()
        other = snl.SessionPool({"1": self.root}, statistics=False)
        other.next_handle = 200
        try:
            packet = b"\x22" + struct.pack(">IB", handle, 0x12) + struct.pack(">IH", 0, 5)
            self.assertEqual(self.request(packet, other), snl.status(-6) + bytes(2))
        finally:
            other.close_all()

    def test_shared_readers_allowed_exclusive_conflicts_and_delete_rejected(self):
        (self.root / "file").write_bytes(b"data")
        self.open(b"file", 1)
        self.open(b"FILE", 1)
        for mode in (0, 2, 3, 255):
            response = self.request(bytes((0x21, 1, mode, 4)) + b"file")
            self.assertEqual(response, snl.status(snl.IU))
        self.assertEqual((self.root / "file").read_bytes(), b"data")
        self.assertEqual(self.pool.rejected, 4)

    def test_directory_conversion_does_not_move_another_open_file(self):
        self.open(b"group_file")
        directory, _ = self.open(b"group")
        self.assertEqual(self.call(directory, 0x20, bytes(4)), snl.status(snl.IU))
        self.assertTrue((self.root / "group").is_file())

    def test_statistics_log_peak_and_summary_without_payload(self):
        output = io.StringIO()
        self.pool.statistics = True
        with contextlib.redirect_stdout(output):
            first, _ = self.open(b"first")
            second, _ = self.open(b"second")
            self.write(first, 0, b"SECRET_PAYLOAD")
            self.call(first, 4)
            self.pool.close_all()
        log = output.getvalue()
        self.assertIn("SNL OPEN", log)
        self.assertIn("active=2 peak=2", log)
        self.assertIn("SNL CLOSE", log)
        self.assertIn("SNL SUMMARY", log)
        self.assertIn("opens=2 closes=2 rejected=0 active=0 peak=2", log)
        self.assertNotIn("SECRET_PAYLOAD", log)

    def test_shutdown_continues_closing_after_flush_error(self):
        first, _ = self.open(b"first")
        second, _ = self.open(b"second")
        first_session = self.pool.sessions[first]
        second_session = self.pool.sessions[second]
        with patch.object(first_session, "flush", side_effect=PermissionError):
            self.pool.close_all()
        self.assertIsNone(first_session.file)
        self.assertIsNone(second_session.file)
        self.assertFalse(self.pool.sessions)

    def test_legacy_client_still_works_with_updated_daemon(self):
        self.assertEqual(self.request(b"\x11\x01\x02\x03old"), b"\x00" + bytes(4))
        self.assertEqual(self.request(b"\x13" + struct.pack(">IH", 0, 3) + b"old"), b"\x00\x00\x03")
        self.assertEqual(self.request(b"\x04"), b"\x00")


class DriverChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fixture = snl.Session({"1": self.root})
        self.fixture.open(1, 2, b"fixture")
        self.cpu = CacheCPU(self.fixture)
        self.fixture.close()
        self.cpu.pool.sessions.clear()

    def tearDown(self):
        self.cpu.pool.close_all()
        self.tmp.cleanup()

    def open_cdb(self, cdb, name, mode):
        cpu = self.cpu
        cpu.reg.update(a0=cdb, a1=0x1000, a3=0xA000, a5=cdb)
        cpu.mem[cdb+4:cdb+8] = (0xA018).to_bytes(4, "big")
        cpu.field("fs_acces", mode, 1)
        cpu.field("fs_fname", len(name), 2)
        offset = cdb + cpu.symbols["fs_fname"] + 2
        cpu.mem[offset:offset+len(name)] = name
        cpu.mem[0x1014] = 1
        cpu.mem[0xA050:0xA054] = (0x800).to_bytes(4, "big")
        self.assertEqual(cpu.run("op_main")[0], 0)

    def test_two_driver_cdbs_own_buffers_handles_positions_and_eof(self):
        payload = bytes(range(256)) * 5
        (self.root / "source").write_bytes(payload)
        self.open_cdb(0x2000, b"source", 1)
        first_buffer = self.cpu.field("snl_buf")
        first_handle = self.cpu.field("snl_hand")
        self.open_cdb(0x3000, b"copy", 2)
        self.assertNotEqual(first_buffer, self.cpu.field("snl_buf"))
        self.assertNotEqual(first_handle, self.cpu.field("snl_hand"))
        for offset in range(0, len(payload), 200):
            count = min(200, len(payload)-offset)
            self.cpu.reg["a5"] = 0x2000
            status, block = self.cpu.transfer(count)
            self.assertEqual(status, 0)
            self.cpu.reg["a5"] = 0x3000
            self.assertEqual(self.cpu.transfer(count, action=1, data=block)[0], 0)
        for cdb in (0x2000, 0x3000):
            self.cpu.reg["a5"] = cdb
            self.assertEqual(self.cpu.field("fs_nblok"), len(payload))
            self.assertEqual(self.cpu.field("fs_eblok"), len(payload))
        self.assertEqual((self.root / "copy").read_bytes(), payload)
        self.assertEqual(self.cpu.pool.peak, 2)
        self.assertEqual(len(self.cpu.allocated), 2)

    def test_failed_open_frees_its_buffer_without_closing_other_channel(self):
        self.open_cdb(0x2000, b"working", 2)
        handle = self.cpu.field("snl_hand")
        count_before = len(self.cpu.allocated)
        cpu = self.cpu
        cpu.reg.update(a0=0x3000, a1=0x1000, a3=0xA000, a5=0x3000)
        cpu.field("fs_acces", 1, 1)
        cpu.field("fs_fname", 7, 2)
        offset = 0x3000 + cpu.symbols["fs_fname"] + 2
        cpu.mem[offset:offset+7] = b"missing"
        self.assertEqual(cpu.run("op_main")[0], snl.NF)
        self.assertEqual(len(cpu.allocated), count_before)
        self.assertEqual(cpu.field("snl_buf"), 0)
        self.assertIn(handle, cpu.pool.sessions)

    def test_close_releases_only_its_handle_buffer_and_count(self):
        self.open_cdb(0x2000, b"first", 2)
        first_buffer = self.cpu.field("snl_buf")
        first_handle = self.cpu.field("snl_hand")
        self.open_cdb(0x3000, b"second", 2)
        second_buffer = self.cpu.field("snl_buf")
        second_handle = self.cpu.field("snl_hand")
        self.cpu.reg.update(a0=0x2000, a5=0x2000)
        self.assertEqual(self.cpu.run("cl_main")[0], 0)
        self.assertNotIn(first_handle, self.cpu.pool.sessions)
        self.assertIn(second_handle, self.cpu.pool.sessions)
        self.assertIn(first_buffer, self.cpu.freed)
        self.assertNotIn(second_buffer, self.cpu.freed)
        self.assertEqual(int.from_bytes(self.cpu.mem[0xA048:0xA04A], "big"), 1)
        self.cpu.reg["a5"] = 0x3000
        self.assertEqual(self.cpu.transfer(3, action=1, data=b"yes")[0], 0)
        self.cpu.reg.update(a0=0x3000)
        self.assertEqual(self.cpu.run("cl_main")[0], 0)
        self.assertFalse(self.cpu.pool.sessions)
        self.assertFalse(self.cpu.allocated)

    def test_memory_allocation_failure_sends_no_open_and_keeps_count(self):
        cpu = self.cpu
        cpu.reg.update(a0=0x2000, a1=0x1000, a3=0xA000, a5=0x2000)
        cpu.field("fs_acces", 2, 1)
        cpu.field("fs_fname", 3, 2)
        offset = 0x2000 + cpu.symbols["fs_fname"] + 2
        cpu.mem[offset:offset+3] = b"new"
        cpu.mem[0x1014] = 1
        cpu.alloc_error = -3
        self.assertEqual(cpu.run("op_main")[0], -3)
        self.assertFalse(cpu.requests)
        self.assertFalse(cpu.allocated)
        self.assertFalse(cpu.pool.sessions)
        self.assertEqual(cpu.field("snl_buf"), 0)

    def test_driver_reports_unknown_handle_after_daemon_restart(self):
        self.open_cdb(0x2000, b"working", 2)
        self.cpu.pool.close_all()
        self.cpu.pool = snl.SessionPool({"1": self.root}, statistics=False)
        self.assertEqual(self.cpu.transfer(3, action=1, data=b"bad")[0], -6)
        self.assertEqual(self.cpu.field("fs_nblok"), 0)
        self.assertEqual((self.root / "working").read_bytes(), b"")

    def test_directory_channel_keeps_qdos_directory_access_mode(self):
        (self.root / "source").write_bytes(b"data")
        self.open_cdb(0x2000, b"source", 4)
        self.assertEqual(self.cpu.field("fs_acces", width=1), 4)
        self.assertEqual(self.cpu.field("snl_mode", width=1), 4)
        self.open_cdb(0x3000, b"source", 1)
        self.assertEqual(self.cpu.pool.peak, 2)
        self.assertEqual(self.cpu.transfer(4), (0, b"data"))

    def test_directory_scan_cdb_name_cannot_lock_matching_destination_file(self):
        name = b"destination"
        self.open_cdb(0x2000, name, 4)
        offset = 0x2000 + self.cpu.symbols["fs_fname"]
        length = int.from_bytes(self.cpu.mem[offset:offset+2], "big")
        tag = bytes(self.cpu.mem[offset+2:offset+2+length])
        self.assertEqual(length, 14)
        self.assertTrue(tag.startswith(b".SNL_D"))
        self.assertNotEqual(tag.lower(), name.lower())
        session = self.cpu.pool.sessions[self.cpu.field("snl_hand")]
        self.assertEqual(session.name, name)
        self.open_cdb(0x3000, name, 4)
        offset2 = 0x3000 + self.cpu.symbols["fs_fname"]
        tag2 = bytes(self.cpu.mem[offset2+2:offset2+16])
        self.assertNotEqual(tag, tag2)
        self.open_cdb(0x4000, name, 2)
        self.assertEqual(self.cpu.transfer(4, action=1, data=b"copy")[0], 0)
        self.assertEqual((self.root / "destination").read_bytes(), b"copy")
