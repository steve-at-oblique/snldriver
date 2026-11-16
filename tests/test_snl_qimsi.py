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
                self.assertEqual(cpu.mem[0x10061], 1)
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

    def minerva(self, machine=21, version=b"1.98"):
        cpu = self.cpu()
        cpu.mem[0x1000:0x1004] = bytes.fromhex("d2540000")
        cpu.mem[0x10A7] = machine
        cpu.reg["d2"] = int.from_bytes(version, "big")
        cpu.mem[0x84:0x88] = (0x1176).to_bytes(4, "big")
        # Minerva4Q68 Q68_ROM.SYS MT.TRAP: native-stack sysvars convention.
        cpu.mem[0x1176:0x1182] = bytes.fromhex("48e701062e0f024780002c47")
        return cpu

    def test_minerva_qimsi_selects_usb_and_native_stack(self):
        for version in (b"1.98", b"1G98"):
            for machine in (21, 21 | 0x80):
                with self.subTest(version=version, machine=machine):
                    cpu = self.minerva(machine, version)
                    self.assertEqual(cpu.run("ini_prof")[0], 0)
                    self.assertEqual(cpu.mem[0x10061], 2)
                    self.assertEqual(cpu.mem[0x10060], 255)
                    self.assertEqual(cpu.reg["a0"], 0x1000)
                    self.assertEqual(cpu.reg["a4"], 0x10000)
                    self.assertEqual(cpu.reg["d2"], int.from_bytes(version, "big"))

    def test_minerva_machine_byte_alone_does_not_select_usb(self):
        for damaged_word in (0, 4, 8):
            cpu = self.minerva()
            cpu.mem[0x1176 + damaged_word] ^= 1
            self.assertEqual(cpu.run("ini_prof")[0], 0)
            self.assertEqual(cpu.mem[0x10061], 0)
        for pointer in (0, 0x1177, 0xC000):
            cpu = self.minerva()
            cpu.mem[0x84:0x88] = pointer.to_bytes(4, "big")
            self.assertEqual(cpu.run("ini_prof")[0], 0)
            self.assertEqual(cpu.mem[0x10061], 0)

    def test_other_minerva_versions_and_machines_keep_legacy_transport(self):
        for machine, version in ((18, b"1.98"), (19, b"1.98"),
                                 (0, b"1.98"), (21, b"1.97")):
            with self.subTest(machine=machine, version=version):
                cpu = self.minerva(machine, version)
                self.assertEqual(cpu.run("ini_prof")[0], 0)
                self.assertEqual(cpu.mem[0x10061], 0)
                self.assertEqual(cpu.mem[0x10060], 255)

    def minerva_serial(self):
        cpu = self.minerva()
        cpu.mem[0x10050:0x10054] = (0x800).to_bytes(4, "big")
        cpu.mem[0x922:0x926] = b"SER2"
        cpu.mem[0x93E:0x942] = (0x1C228).to_bytes(4, "big")
        cpu.mem[0xA00:0xA04] = bytes.fromhex("0c000007")
        return cpu

    def test_minerva_usb_driver_linkage_is_validated(self):
        cpu = self.minerva_serial()
        self.assertEqual(cpu.run("ini_mser")[0], 0)
        self.assertEqual(cpu.reg["a0"], 0x1000)
        self.assertEqual(cpu.reg["a4"], 0x10000)
        self.assertFalse(cpu.requests)

    def test_wrong_minerva_serial_linkage_is_rejected(self):
        for address in (0x922, 0x93E, 0xA00):
            cpu = self.minerva_serial()
            cpu.mem[address] ^= 1
            self.assertEqual(cpu.run("ini_mser")[0], -19)
        for pointer in (0, 0xA01):
            cpu = self.minerva_serial()
            cpu.mem[0x904:0x908] = pointer.to_bytes(4, "big")
            self.assertEqual(cpu.run("ini_mser")[0], -19)

    def test_minerva_buffer_setup_matches_ser_buff_and_preserves_registers(self):
        cpu = self.minerva_serial()
        cpu.mem[0x1044:0x1048] = (0x900).to_bytes(4, "big")
        cpu.reg["sr"] = 0
        saved = {r: cpu.reg[r] for r in ("d1", "d2", "d3", "a0", "a1", "a2", "a3", "a4")}
        writes = []
        original_put = cpu.put
        def watched_put(operand, value, width):
            address = cpu.address(operand, width, update=False) if operand.endswith("(a1)") else -1
            if 0x942 <= address <= 0x948:
                writes.append(cpu.reg["sr"] & 0x2700)
            return original_put(operand, value, width)
        cpu.put = watched_put
        self.assertEqual(cpu.run("ini_mbuf")[0], 0)
        self.assertEqual(bytes(cpu.mem[0x942:0x94A]), bytes.fromhex("1010041004040c0c"))
        self.assertEqual(writes, [0x2700] * 4)
        self.assertEqual(cpu.reg["sr"], 0)
        self.assertEqual({r: cpu.reg[r] for r in saved}, saved)
        self.assertEqual(cpu.reg["a7"], 0x3F000)

    def test_minerva_buffer_setup_rejects_busy_port_without_changes(self):
        for field in (0x936, 0x93A):
            cpu = self.minerva_serial()
            cpu.mem[0x1044:0x1048] = (0x900).to_bytes(4, "big")
            cpu.mem[field:field + 4] = (0x1234).to_bytes(4, "big")
            before = bytes(cpu.mem[0x900:0x950])
            self.assertEqual(cpu.run("ini_mbuf")[0], -9)
            self.assertEqual(bytes(cpu.mem[0x900:0x950]), before)

    def test_minerva_buffer_setup_checks_driver_and_bounds_list_scan(self):
        cpu = self.minerva_serial()
        self.assertEqual(cpu.run("ini_mbuf")[0], -19)  # missing driver
        cpu.mem[0x1044:0x1048] = (0x900).to_bytes(4, "big")
        cpu.mem[0x900:0x904] = (0x900).to_bytes(4, "big")  # cycle
        cpu.mem[0x93E:0x942] = (0x1C208).to_bytes(4, "big")  # physical UART
        before = bytes(cpu.mem[0x900:0x950])
        self.assertEqual(cpu.run("ini_mbuf")[0], -19)
        self.assertEqual(bytes(cpu.mem[0x900:0x950]), before)

    def test_private_fields_fit_common_spare_area_without_overlap(self):
        symbols = self.cpu().symbols
        widths = {"snl_chid": 4, "snl_pdb": 4, "snl_dead": 1,
                  "snl_mode": 1, "snl_rx": 2, "snl_last": 2,
                  "snl_phas": 1, "snl_cnt": 2, "snl_call": 1,
                  "snl_serp": 4, "snl_txp": 4, "snl_buf": 4,
                  "snl_base": 4, "snl_len": 2, "snl_err": 2,
                  "snl_hand": 4, "snl_tick": 2}
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
