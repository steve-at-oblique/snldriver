"""Timestamp formatting across daemon stdout, trace and multiline errors."""
import contextlib
import datetime
import io
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_snl_serial import snl, Port


class LoggingTests(unittest.TestCase):
    def setUp(self):
        real_datetime = datetime.datetime
        frozen = real_datetime(2026, 11, 14, 9, 8, 7, 123456)
        self.clock_patch = patch.object(snl.datetime, "datetime")
        clock = self.clock_patch.start()
        clock.now.return_value = frozen
        clock.side_effect = real_datetime
        self.addCleanup(self.clock_patch.stop)
        self.prefix = "11/14/2026 09:08:07 "

    def test_multiline_stdout_stderr_and_blank_messages(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            snl.log_message("one\ntwo")
            snl.log_message("")
            snl.log_message("error\ncontinuation", file=sys.stderr)
        self.assertEqual(output.getvalue(), self.prefix + "one\n" + self.prefix + "two\n" + self.prefix + "\n")
        self.assertEqual(errors.getvalue(), self.prefix + "error\n" + self.prefix + "continuation\n")

    def test_trace_and_statistics_lines_timestamped_without_changing_serial_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            pool = snl.SessionPool({"1": folder})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                opened = Port(b"\x21\x01\x02\x04test")
                snl.serve_one(opened, pool, trace=True)
                handle = int.from_bytes(opened.output[1:5], "big")
                header = Port(b"\x22" + handle.to_bytes(4, "big") + b"\x15")
                snl.serve_one(header, pool, trace=True)
                pool.close_all()
            self.assertEqual(opened.output[0], 0)
            self.assertEqual(len(opened.output), 9)
            self.assertEqual(len(header.output), 65)
            lines = output.getvalue().splitlines()
            self.assertTrue(lines)
            self.assertTrue(all(line.startswith(self.prefix) for line in lines))
            self.assertIn("SNL OPEN", output.getvalue())
            self.assertIn("RX handle=", output.getvalue())
            self.assertIn("SNL SUMMARY", output.getvalue())

    def test_startup_and_multiline_serial_error_timestamped(self):
        def fail_serial(*args, **kwargs):
            raise OSError("unavailable\ncheck cable")
        serial = SimpleNamespace(Serial=fail_serial, SerialException=OSError)
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {"serial": serial}), \
                patch.object(snl, "load_config", return_value={"drives": {}, "trace": True}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            snl.main()
        self.assertTrue(all(line.startswith(self.prefix) for line in output.getvalue().splitlines()))
        self.assertEqual(errors.getvalue(), self.prefix + "Serial error: unavailable\n" + self.prefix + "check cable\n")
        self.assertIn("SNL protocol v2 daemon", output.getvalue())
