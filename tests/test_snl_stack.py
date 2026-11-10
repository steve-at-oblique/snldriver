"""Exercise actual entry wrappers and their caller-stack restore frame.

The filesystem body is replaced by a probe. These tests check register and
stack behavior; they do not emulate Minerva interrupts or assemble opcodes.
"""
from types import SimpleNamespace
import unittest

from tests.test_snl_buffer import CacheCPU, ROOT


class StackPolicyTests(unittest.TestCase):
    def cpu(self):
        cpu = CacheCPU(SimpleNamespace(mode=1, file_size=lambda: 0))
        source = (ROOT / "SNLdriver_asm").read_bytes().decode("latin1")
        wrappers = []
        for entry, body in (("dd_mdvop", "op_main"),
                            ("dd_mdvio", "io_main"),
                            ("dd_mdvcl", "cl_main")):
            start = source.index(entry + " move.l")
            end = source.index(body + " ", start)
            wrappers.append(source[start:end])
            wrappers.append(body + " move.l a7,d1\n         bra stk_exit\n")
        start = source.index("snl_exit move.l")
        end = source.index("; ---", start)
        wrappers.append(source[start:end].replace("snl_exit", "stk_exit"))
        cpu.code, cpu.labels = [], {}
        for line in "".join(wrappers).splitlines():
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
        return cpu

    def test_all_entries_restore_stack_and_a2_under_both_policies(self):
        for entry in ("dd_mdvop", "dd_mdvio", "dd_mdvcl"):
            for minerva in (False, True):
                with self.subTest(entry=entry, minerva=minerva):
                    cpu = self.cpu()
                    linkage, stack_top = 0x10000, 0x2FF00
                    cpu.reg.update(a0=0x2000, a2=0x123456, a3=linkage, d0=7)
                    cpu.put("4(a0)", linkage + 0x18, 4)
                    cpu.mem[linkage + 0x60] = 255 if minerva else 0
                    cpu.run(entry, stack_top=stack_top)
                    self.assertEqual(cpu.reg["a7"], stack_top)
                    self.assertEqual(cpu.reg["a2"], 0x123456)
                    self.assertEqual(cpu.reg["d0"], 7)
                    expected = stack_top - 12 if minerva else linkage + 0x4FC
                    self.assertEqual(cpu.reg["d1"], expected)
                    if minerva:
                        self.assertEqual(cpu.reg["d1"] & 0xFFFF8000, 0x28000)


if __name__ == "__main__":
    unittest.main()
