"""Execute profile selection from the driver; guard SMSQ/E channel storage.

These checks do not emulate SMSQ/E interrupts or replace hardware testing.
"""
from types import SimpleNamespace
import unittest

from tests.test_snl_buffer import CacheCPU, ROOT


class QimsiProfileTests(unittest.TestCase):
    def cpu(self):
        cpu = CacheCPU(SimpleNamespace(mode=1, file_size=lambda: 0))
        source = (ROOT / "SNLdriver_asm").read_bytes().decode("latin1")
        start = source.index("ini_prof cmpi.l")
        end = source.index("; ---", start)
        cpu.code, cpu.labels = [], {}
        for line in source[start:end].splitlines():
            line = line.split(";", 1)[0].rstrip()
            if not line:
                continue
            if not line[0].isspace():
                label, line = line.split(None, 1)
                cpu.labels[label.lower()] = len(cpu.code)
            fields = line.strip().lower().split(None, 1)
            op = fields[0].split(".")
            cpu.code.append((op[0], op[1] if len(op) > 1 else "w",
                             fields[1].split(",") if len(fields) > 1 else []))
        cpu.reg.update(a0=0x1000, a4=0x10000)
        return cpu

    def profile(self, signature, machine):
        cpu = self.cpu()
        cpu.mem[0x1000:0x1004] = signature
        cpu.mem[0x10A7] = machine
        return cpu, cpu.run("ini_prof")[0]

    def test_smsqe_qimsi_selects_usb_and_private_stack(self):
        for machine in (21, 21 | 0x80, 21 | 0x40):
            with self.subTest(machine=machine):
                cpu, status = self.profile(b"SMSQ", machine)
                self.assertEqual(status, 0)
                self.assertEqual(cpu.mem[0x10061], 255)
                self.assertEqual(cpu.mem[0x10060], 0)
                self.assertEqual(cpu.reg["a0"], 0x1000)
                self.assertEqual(cpu.reg["a4"], 0x10000)

    def test_other_smsqe_machines_are_rejected(self):
        for machine in (0, 10, 18, 20, 30):
            with self.subTest(machine=machine):
                cpu, status = self.profile(b"SMSQ", machine)
                self.assertEqual(status, -19)
                self.assertEqual(cpu.mem[0x10061], 0)

    def test_legacy_os_does_not_read_machine_byte_as_smsqe(self):
        for signature in (bytes.fromhex("d2540000"), b"MINV"):
            cpu, status = self.profile(signature, 21)
            self.assertEqual(status, 0)
            self.assertEqual(cpu.mem[0x10061], 0)

    def test_private_fields_fit_common_spare_area_without_overlap(self):
        symbols = self.cpu().symbols
        widths = {"snl_chid": 4, "snl_pdb": 4, "snl_dead": 1,
                  "snl_mode": 1, "snl_rx": 2, "snl_last": 2,
                  "snl_phas": 1, "snl_cnt": 2, "snl_call": 1,
                  "snl_serp": 4, "snl_txp": 4, "snl_buf": 4,
                  "snl_base": 4, "snl_len": 2, "snl_err": 2}
        used = set()
        for name, width in widths.items():
            offset = symbols[name]
            self.assertGreaterEqual(offset, 0x70, name)
            self.assertLessEqual(offset + width, 0xA0, name)
            if width > 1:
                self.assertEqual(offset % 2, 0, name)
            slots = set(range(offset, offset + width))
            self.assertFalse(used & slots, name)
            used |= slots


if __name__ == "__main__":
    unittest.main()
