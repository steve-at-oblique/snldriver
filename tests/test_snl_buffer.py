"""Execute read-cache and bulk serial transfer source against the Python server.

This small interpreter covers instructions used by snl_xfer/snl_read/
snl_fill/snl_bget/snl_bput and the header reader. It checks algorithm/register/
CCR behavior, not instruction encoding, ROM compatibility or serial IRQ timing.
Talent assembly and QL testing remain required. Small wire helpers stand in
for serial delivery. String I/O and the clock are stubbed at their boundaries,
with register clobbering, partial
batches and errors. The driver routines execute from SNLdriver_asm.
"""
from pathlib import Path
import re
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_snl_serial import snl, Port

ROOT = Path(__file__).resolve().parents[1]
LOADER_FIXTURE = ROOT / "tests" / "fixtures" / "loader_bas"


class CacheCPU:
    def __init__(self, session):
        self.session = session
        self.reg = {f"{prefix}{i}": 0 for prefix in "da" for i in range(8)}
        self.mem = bytearray(0x40000)
        self.symbols = {}
        for file in ("SNLdriver_asm",):
            for line in (ROOT / file).read_bytes().decode("latin1").splitlines():
                m = re.match(r"^(\w[\w.]*)\s+equ\s+([^;]+)", line, re.I)
                if m and m[2].strip() != "*":
                    expression = m[2].strip().lower()
                    expression = re.sub(r"\$([0-9a-f]+)", r"0x\1", expression)
                    expression = re.sub(r"\b[a-z_][a-z_0-9.]*\b", lambda t: str(self.symbols[t[0]]) if t[0] in self.symbols else t[0], expression)
                    self.symbols[m[1].lower()] = eval(expression, {"__builtins__": {}}, {})
        source = (ROOT / "SNLdriver_asm").read_bytes().decode("latin1")
        source = (source[source.index("op_main "):source.index("; I/O: preserve")]
                  + source[source.index("io_info "):source.index("io_ov    ")]
                  + source[source.index("snl_xfer "):source.index("; CLOSE closes")])
        self.code, self.labels = [], {}
        for line in source.splitlines():
            line = line.split(";", 1)[0].rstrip()
            if not line:
                continue
            if not line[0].isspace():
                label, line = line.split(None, 1)
                self.labels[label.lower()] = len(self.code)
            fields = line.strip().lower().split(None, 1)
            op = fields[0].split(".")
            self.code.append((op[0], op[1] if len(op) > 1 else "w", fields[1].split(",") if len(fields) > 1 else []))
        self.reg.update(a5=0x2000, a1=0x4000, a7=0x3F000)
        self.mem[0x2004:0x2008] = (0xA018).to_bytes(4, "big")
        self.field("snl_buf", 0xC000)
        self.field("snl_serp", 0x800)
        self.mem[0x804:0x808] = (0x900).to_bytes(4, "big")
        self.mem[0x904:0x908] = (0xA00).to_bytes(4, "big")
        self.field("snl_mode", session.mode, 1)
        self.field("fs_nblok", 0)
        self.field("fs_eblok", session.file_size())
        self.wire = bytearray()
        self.reply = bytearray()
        self.requests = []
        self.read_lengths = []
        self.truncate_reply = None
        self.reply_override = None
        self.rom_limit = 512
        self.rom_batches = []
        self.rom_calls = []
        self.read_header_batches = []
        self.read_header_calls = []
        self.queued_tx = bytearray()
        self.defer_tx = False
        self.tx_limit = 512
        self.tx_batches = []
        self.tx_calls = []
        self.clock = 0
        self.clock_step = 0.01
        self.diagnostics = []
        self.daemon_online = True
        self.offline_packets = []
        self.ready_noise = b""
        self.ready_wrong_token = False
        self.kicks = 0
        self.steps = 0
        self.z = self.n = self.c = self.v = False

    def field(self, name, value=None, width=4):
        address = self.reg["a5"] + self.symbols[name]
        if value is not None:
            self.mem[address:address + width] = (value & ((1 << (width * 8)) - 1)).to_bytes(width, "big")
        return int.from_bytes(self.mem[address:address + width], "big")

    def number(self, text):
        text = text.strip()
        if text in self.symbols:
            return self.symbols[text]
        expression = re.fullmatch(r"([a-z_][\w.]*)([+-])(\d+)", text)
        if expression:
            base, sign, amount = expression.groups()
            return self.symbols[base] + int(sign + amount)
        return int(text.replace("$", "0x"), 0)

    def address(self, operand, width, update=True):
        m = re.fullmatch(r"(-)?([\w.$+-]*)\((a[0-7])\)(\+)?", operand)
        if not m:
            raise AssertionError(f"Unsupported addressing: {operand}")
        pre, offset, reg, post = m.groups()
        if pre and offset:
            offset, pre = "-" + offset, None
        amount = 2 if width == 1 and reg == "a7" else width
        if pre:
            self.reg[reg] -= amount
        address = self.reg[reg] + (self.number(offset) if offset else 0)
        if post and update:
            self.reg[reg] += amount
        return address

    def get(self, operand, width):
        if operand.startswith("#"):
            return self.number(operand[1:]) & ((1 << (width * 8)) - 1)
        if operand in self.reg:
            return self.reg[operand] & ((1 << (width * 8)) - 1)
        address = self.address(operand, width)
        assert width == 1 or address % 2 == 0, f"68000 unaligned read: {operand} at {address:#x}"
        return int.from_bytes(self.mem[address:address + width], "big")

    def put(self, operand, value, width):
        mask = (1 << (width * 8)) - 1
        value &= mask
        if operand in self.reg:
            if operand.startswith("a"):
                if width == 2 and value & 0x8000:
                    value |= 0xFFFF0000
                self.reg[operand] = value
            else:
                self.reg[operand] = (self.reg[operand] & ~mask) | value
        else:
            address = self.address(operand, width)
            assert width == 1 or address % 2 == 0, f"68000 unaligned write: {operand} at {address:#x}"
            self.mem[address:address + width] = value.to_bytes(width, "big")

    def flags(self, value, width):
        mask, sign = (1 << (width * 8)) - 1, 1 << (width * 8 - 1)
        self.z, self.n = (value & mask) == 0, bool(value & sign)
        self.c = self.v = False

    def arithmetic(self, left, right, width, subtract):
        mask, sign = (1 << (width * 8)) - 1, 1 << (width * 8 - 1)
        result = left - right if subtract else left + right
        self.flags(result, width)
        self.c = left < right if subtract else result > mask
        self.v = bool(((left ^ right) if subtract else ~(left ^ right)) & (left ^ result) & sign)
        return result & mask

    @staticmethod
    def register_list(text):
        result = []
        for part in text.split("/"):
            if "-" in part:
                start, end = part.split("-")
                result.extend(start[0] + str(i) for i in range(int(start[1]), int(end[1]) + 1))
            else:
                result.append(part)
        return sorted(result, key=lambda r: (r[0] == "a", int(r[1])))

    def transmit(self, data):
        self.wire.extend(data)
        cmd = self.wire[0]
        assert cmd in (0x11, 0x12, 0x13, 0x15, 0x18, 0x19, 0x1C, 0x1D, ord("~")), self.wire.hex()
        if cmd == ord("~"):
            count, length = 0, 22
        elif cmd in (0x19, 0x1C, 0x1D):
            count, length = 0, 6 if cmd == 0x19 else 5
        elif cmd == 0x11:
            if len(self.wire) < 4:
                return
            count, length = 0, 4 + self.wire[3]
        elif cmd in (0x15, 0x18):
            count, length = 0, 1
        else:
            if len(self.wire) < 7:
                return
            count = int.from_bytes(self.wire[5:7], "big")
            length = 7 + (count if cmd == 0x13 else 0)
        if len(self.wire) < length:
            return
        assert len(self.wire) == length
        assert cmd == ord("~") or not self.reply, "New request before previous reply drained"
        packet = bytes(self.wire)
        self.requests.append(packet)
        if cmd == 0x12:
            self.read_lengths.append(count)
        if not self.daemon_online:
            self.offline_packets.append(packet)
            self.wire.clear()
            return
        port = Port(packet)
        snl.serve_one(port, self.session)
        response = port.output
        if cmd == ord("~"):
            if self.ready_wrong_token:
                response = b"~SNL!" + b"P" * 16 + b"\n"
            response = self.ready_noise + response
            self.ready_noise = b""
        elif self.reply_override is not None:
            response = self.reply_override
        if cmd != ord("~") and self.truncate_reply is not None:
            response = response[:self.truncate_reply]
        self.reply.extend(response)
        self.wire.clear()

    def helper(self, name):
        if name.startswith("dbg_"):
            self.diagnostics.append(name)
            return  # diagnostics preserve caller registers
        if name == "snl_kick":
            self.kicks += 1
            if self.queued_tx:
                self.transmit(self.queued_tx[:1])
                del self.queued_tx[:1]
            return
        def receive(n):
            if len(self.reply) < n:
                raise EOFError
            data = self.reply[:n]
            del self.reply[:n]
            self.field("snl_rx", self.field("snl_rx", width=2) + n, 2)
            return int.from_bytes(data, "big")
        try:
            self.reg["d0"] = 0
            if name in ("snl_send", "snl_putl", "snl_putw"):
                width = {"snl_send": 1, "snl_putl": 4, "snl_putw": 2}[name]
                self.transmit((self.reg["d1"] & ((1 << (width * 8)) - 1)).to_bytes(width, "big"))
            elif name == "snl_stat":
                status = receive(1)
                self.reg["d0"] = (status if status < 128 else status - 256) & 0xFFFFFFFF
            elif name in ("snl_recv", "snl_getw", "snl_getl"):
                self.reg["d1"] = receive({"snl_recv": 1, "snl_getw": 2, "snl_getl": 4}[name])
            elif name == "snl_bad":
                self.field("snl_dead", 255, 1)
                self.reg["d0"] = (-13) & 0xFFFFFFFF
            else:
                raise AssertionError(name)
        except EOFError:
            self.field("snl_dead", 255, 1)
            self.reg["d0"] = (-13) & 0xFFFFFFFF
        self.flags(self.reg["d0"], 4)

    def rom_read(self):
        assert self.reg["a4"] == 0xA00
        if self.reg["d0"] == self.symbols["io.sstrg"]:
            return self.rom_write()
        byte_read = self.reg["d0"] == self.symbols["io.fbyte"]
        assert byte_read or self.reg["d0"] == self.symbols["io.fstrg"]
        assert self.reg["d1"] == self.reg["d3"] == self.reg["d7"] == 0
        if byte_read:
            result = 0 if self.reply else -1
            value = self.reply.pop(0) if self.reply else 0
            for reg in self.register_list("d2-d7/a0-a6"):
                self.reg[reg] = 0xDEADBEEF
            self.reg["d0"], self.reg["d1"] = result & 0xFFFFFFFF, value
            self.flags(self.reg["d0"], 4)
            return
        requested = self.reg["d2"]
        # Keep injected payload behavior separate from the new three-byte header.
        is_read_header = self.field("snl_phas", width=1) == 2
        calls = self.read_header_calls if is_read_header else self.rom_calls
        batches = self.read_header_batches if is_read_header else self.rom_batches
        calls.append(requested)
        if batches:
            actual, result = batches.pop(0)
        else:
            actual = min(requested, len(self.reply), self.rom_limit)
            result = 0 if actual == requested else -1
        # Deliberately invalid counts can be injected without writing past RAM.
        copied = min(actual, requested, len(self.reply))
        address = self.reg["a1"]
        self.mem[address:address + copied] = self.reply[:copied]
        del self.reply[:copied]
        self.reg["a1"] += copied
        for reg in self.register_list("d2-d7/a0/a2-a6"):
            self.reg[reg] = 0xDEADBEEF
        self.reg["d0"] = result & 0xFFFFFFFF
        self.reg["d1"] = actual
        self.flags(self.reg["d0"], 4)

    def rom_write(self):
        assert self.reg["d1"] == self.reg["d3"] == self.reg["d7"] == 0
        requested = self.reg["d2"]
        address = self.reg["a1"]
        self.tx_calls.append((address, requested))
        if self.tx_batches:
            actual, result = self.tx_batches.pop(0)
        else:
            actual = min(requested, self.tx_limit)
            result = 0 if actual == requested else -1
        # An invalid count may be injected without reading outside the request.
        copied = max(0, min(actual, requested))
        if copied:
            data = bytes(self.mem[address:address + copied])
            if self.defer_tx:
                self.queued_tx.extend(data)
            else:
                self.transmit(data)
        self.reg["a1"] += copied
        for reg in self.register_list("d2-d7/a0/a2-a6"):
            self.reg[reg] = 0xDEADBEEF
        self.reg["d0"] = result & 0xFFFFFFFF
        self.reg["d1"] = actual & 0xFFFFFFFF
        self.flags(self.reg["d0"], 4)

    def run(self, entry, stack_top=0x3F000):
        self.reg["a7"] = stack_top
        self.reg["a7"] -= 4
        self.put("(a7)", 0xFFFFFFFF, 4)
        pc, steps = self.labels[entry], 0
        while pc != 0xFFFFFFFF:
            steps += 1
            assert steps < 5000000, "Assembly did not terminate"
            op, size, args = self.code[pc]
            self.steps += 1
            pc += 1
            width = {"b": 1, "w": 2, "l": 4}[size]
            if op == "rts":
                pc = self.get("(a7)+", 4)
            elif op == "movem":
                if args[1] == "-(a7)":
                    regs = self.register_list(args[0])
                    self.reg["a7"] -= 4 * len(regs)
                    for i, reg in enumerate(regs):
                        self.put(f"{i * 4}(a7)", self.reg[reg], 4)
                else:
                    assert args[0] == "(a7)+"
                    for reg in self.register_list(args[1]):
                        self.reg[reg] = self.get("(a7)+", 4)
            elif op == "bsr":
                if args[0] in self.labels:
                    self.put("-(a7)", pc, 4)
                    pc = self.labels[args[0]]
                else:
                    self.helper(args[0])
            elif op == "jsr":
                assert args == ["(a4)"]
                self.rom_read()
            elif op == "trap":
                assert args == ["#1"] and self.reg["d0"] == 0x13
                self.reg["d0"] = 0
                self.reg["d1"] = int(self.clock)
                self.clock += self.clock_step
            elif op == "lea":
                self.reg[args[1]] = self.address(args[0], 4, update=False)
            elif op == "st":
                self.put(args[0], 255, 1)
            elif op == "btst":
                # Immediate bit test: longs for data registers, bytes for memory.
                bit_width = 4 if args[1].startswith("d") and args[1] in self.reg else 1
                bit = self.get(args[0], 4) % (bit_width * 8)
                self.z = not bool(self.get(args[1], bit_width) & (1 << bit))
            elif op == "lsr":
                shift = self.get(args[0], width)
                value = self.get(args[1], width)
                result = value >> shift
                self.put(args[1], result, width)
                self.flags(result, width)
                self.c = bool(value & (1 << (shift - 1))) if shift else False
            elif op == "dbra":
                value = (self.get(args[0], 2) - 1) & 0xFFFF
                self.put(args[0], value, 2)
                if value != 0xFFFF:
                    pc = self.labels[args[1]]
            elif op == "andi":
                value = self.get(args[0], width) & self.get(args[1], width)
                self.put(args[1], value, width)
                self.flags(value, width)
            elif op == "rol":
                shift = self.get(args[0], width)
                value = self.get(args[1], width)
                mask = (1 << (width * 8)) - 1
                value = ((value << shift) | (value >> (width * 8 - shift))) & mask
                self.put(args[1], value, width)
                self.flags(value, width)
            elif op.startswith("b"):
                take = {"bra": True, "beq": self.z, "bne": not self.z,
                        "bcs": self.c, "bcc": not self.c, "bhi": not self.c and not self.z,
                        "bls": self.c or self.z, "bvs": self.v, "bmi": self.n,
                        "bge": self.n == self.v, "blt": self.n != self.v}[op]
                if take:
                    if args[0] in ("io_ret", "io_ok", "snl_exit"):
                        if args[0] == "io_ok":
                            self.reg["d0"] = 0
                        pc = self.get("(a7)+", 4)
                    else:
                        pc = self.labels[args[0]]
            elif op in ("move", "moveq"):
                if op == "moveq":
                    width = 4
                value = self.get(args[0], width)
                self.put(args[1], value, width)
                if not args[1].startswith("a"):
                    self.flags(value, width)
            elif op in ("cmp", "cmpi"):
                self.arithmetic(self.get(args[1], width), self.get(args[0], width), width, True)
            elif op == "tst":
                self.flags(self.get(args[0], width), width)
            elif op == "clr":
                self.put(args[0], 0, width)
                self.flags(0, width)
            elif op == "ext":
                value = self.get(args[0], width // 2)
                if value & (1 << (width * 4 - 1)):
                    value -= 1 << (width * 4)
                self.put(args[0], value, width)
                self.flags(value, width)
            elif op in ("add", "addi", "addq", "sub", "subq", "adda", "suba"):
                dst = args[1]
                value, left = self.get(args[0], width), self.get(dst, width)
                if dst.startswith("a"):
                    left = self.reg[dst]
                    if width == 2 and value & 0x8000:
                        value -= 0x10000
                    self.put(dst, left - value if op.startswith("sub") else left + value, 4)
                else:
                    result = self.arithmetic(left, value, width, op.startswith("sub"))
                    self.put(dst, result, width)
            else:
                raise AssertionError(f"Unsupported instruction: {op}.{size} {args}")
        assert self.reg["a7"] == stack_top, "Unbalanced assembly stack"
        result = self.reg["d0"]
        if result & 0x80000000:
            result -= 1 << 32
        return result, b""

    def transfer(self, count, action=0, data=b"", address=0x10000):
        self.reg.update(d5=count, d7=action, a1=address)
        self.mem[address:address + len(data)] = data
        result, _ = self.run("snl_xfer")
        return result, bytes(self.mem[address:address + self.reg["d1"]])


class BufferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.session = snl.Session({"1": self.root})

    def tearDown(self):
        self.session.close()
        self.tmp.cleanup()

    def cpu(self, payload):
        (self.root / "test_bas").write_bytes(payload)
        self.session.open(1, 0, b"test_bas")
        return CacheCPU(self.session)

    def test_metadata_handlers_wire_and_pointer_preservation(self):
        for entry, value, selector, cmd in (("io_vers", 42, 0, 0x1C),
                                            ("io_date", 1800000000, 2, 0x19)):
            with self.subTest(entry=entry):
                cpu = self.cpu(b"abc")
                cpu.reg.update(d1=value, d2=selector, a1=0x10001)
                self.assertEqual(cpu.run(entry)[0], 0)
                self.assertEqual(cpu.reg["d1"], value)
                self.assertEqual(cpu.reg["a1"], 0x10001)
                packet = bytes((cmd,)) + value.to_bytes(4, "big")
                if entry == "io_date":
                    packet += bytes((selector,))
                self.assertEqual(cpu.requests, [packet])
                self.assertFalse(cpu.reply)

    def test_extended_info_preserves_pointers_and_memory_guards(self):
        cpu = self.cpu(b"abc")
        cpu.reg.update(d1=0, a1=0x10001)
        cpu.mem[0x10000:0x10042] = b"Z" * 66
        expected = self.session.extended_info(0)
        self.assertEqual(cpu.run("io_xinf")[0], 0)
        self.assertEqual(cpu.reg["a1"], 0x10001)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.mem[0x10000:0x10042], b"Z" + expected + b"Z")
        self.assertFalse(cpu.reply)

    def test_extended_info_short_response_does_not_publish_partial_data(self):
        for length in (1, 12, 64):
            with self.subTest(length=length):
                cpu = self.cpu(b"abc")
                cpu.truncate_reply = length
                cpu.reg.update(d1=0, a1=0x10000)
                cpu.mem[0x10000:0x10040] = b"Z" * 64
                self.assertEqual(cpu.run("io_xinf")[0], -13)
                self.assertEqual(cpu.reg["a1"], 0x10000)
                self.assertEqual(cpu.reg["d1"], 0)
                self.assertEqual(cpu.mem[0x10000:0x10040], b"Z" * 64)

    def test_metadata_daemon_error_and_short_reply(self):
        cpu = self.cpu(b"abc")
        cpu.reg.update(d1=65536)
        self.assertEqual(cpu.run("io_vers")[0], snl.BP)
        self.assertEqual(cpu.reg["d1"], 65536)
        self.assertFalse(cpu.reply)
        cpu = self.cpu(b"abc")
        cpu.truncate_reply = 3
        cpu.reg.update(d1=0xFFFFFFFF)
        self.assertEqual(cpu.run("io_date")[0], -13)
        self.assertEqual(cpu.reg["a1"], 0x4000)

    def test_loader_character_reads_need_four_requests(self):
        payload = LOADER_FIXTURE.read_bytes()
        cpu = self.cpu(payload)
        result = bytearray()
        for _ in payload:
            code, data = cpu.transfer(1)
            self.assertEqual(code, 0)
            result.extend(data)
        self.assertEqual(result, payload)
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(cpu.read_lengths, [512] * 4)
        self.assertEqual(cpu.field("fs_nblok"), len(payload))
        self.assertEqual(cpu.reply, b"")

    def test_loader_line_reads_need_four_requests(self):
        payload = LOADER_FIXTURE.read_bytes()
        cpu = self.cpu(payload)
        result = bytearray()
        for _ in range(payload.count(b"\n") + 2):
            code, data = cpu.transfer(1024, action=2)
            result.extend(data)
            if code == -10:
                break
            self.assertEqual(code, 0)
            self.assertTrue(data.endswith(b"\n"))
        else:
            self.fail("No EOF after the final BASIC source line")
        self.assertEqual(result, payload)
        self.assertEqual(cpu.read_lengths, [512] * 4)

    def test_lines_leave_following_bytes_cached(self):
        cpu = self.cpu(b"first\nsecond\nthird")
        self.assertEqual(cpu.transfer(100, action=2), (0, b"first\n"))
        self.assertEqual(cpu.transfer(100, action=2), (0, b"second\n"))
        self.assertEqual(cpu.transfer(100, action=2), (-10, b"third"))
        self.assertEqual(cpu.transfer(100, action=2), (-10, b""))
        self.assertEqual(cpu.read_lengths, [512])

    def test_cached_bulk_copy_all_pointer_parities_and_segment_tails(self):
        payload = bytes(range(256)) * 5
        for source_offset in (0, 1):
            for destination in (0x10000, 0x10001):
                for count in (1, 2, 3, 4, 5, 7, 8, 15, 16, 255, 510, 511, 512, 513, 1025):
                    with self.subTest(source_offset=source_offset,
                                      destination=destination, count=count):
                        cpu = self.cpu(payload)
                        # Fill once, then seek to force an even or odd cached source.
                        self.assertEqual(cpu.transfer(1), (0, payload[:1]))
                        cpu.field("fs_nblok", source_offset)
                        cpu.mem[destination - 8:destination + count + 8] = b"Z" * (count + 16)
                        expected = payload[source_offset:source_offset + count]
                        self.assertEqual(cpu.transfer(count, address=destination), (0, expected))
                        self.assertEqual(cpu.reg["a1"], destination + count)
                        self.assertEqual(cpu.reg["d1"], count)
                        self.assertEqual(cpu.field("fs_nblok"), source_offset + count)
                        self.assertEqual(cpu.mem[destination - 8:destination], b"Z" * 8)
                        self.assertEqual(cpu.mem[destination + count:destination + count + 8], b"Z" * 8)
                        self.assertFalse(cpu.reply)

    def test_bulk_copy_then_line_scan_then_bulk_uses_same_cache(self):
        payload = b"abcd\nsecond\n" + bytes(range(256)) * 3
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(3, address=0x10001), (0, b"abc"))
        self.assertEqual(cpu.transfer(100, action=2), (0, b"d\n"))
        self.assertEqual(cpu.transfer(7), (0, b"second\n"))
        self.assertEqual(cpu.transfer(600, address=0x10001), (0, payload[12:612]))
        self.assertEqual(cpu.field("fs_nblok"), 612)
        self.assertEqual(cpu.read_lengths, [512, 512])

    def test_bulk_copy_defers_error_until_cache_end(self):
        cpu = self.cpu(b"abcde")
        cpu.reply_override = b"\xf5\x00\x05abcde"  # data plus disk-full error
        self.assertEqual(cpu.transfer(3), (0, b"abc"))
        self.assertEqual(cpu.transfer(3), (-11, b"de"))
        self.assertEqual(cpu.field("fs_nblok"), 5)
        self.assertEqual(cpu.transfer(1), (-11, b""))
        self.assertEqual(cpu.read_lengths, [512])

    def test_read_request_is_exact_seven_byte_bulk_packet(self):
        payload = bytes(range(256)) * 5
        cpu = self.cpu(payload)
        cpu.field("fs_nblok", 123)
        self.assertEqual(cpu.transfer(100, address=0x10001), (0, payload[123:223]))
        self.assertEqual(cpu.requests, [b"\x12\x00\x00\x00\x7b\x02\x00"])
        self.assertEqual([size for _, size in cpu.tx_calls], [7])
        self.assertEqual(cpu.tx_calls[0][0] % 2, 1)  # intentionally odd wire start
        self.assertEqual(cpu.read_header_calls, [3])
        self.assertEqual(cpu.rom_calls, [512])
        self.assertEqual(cpu.field("snl_rx", width=2), 515)

    def test_legacy_read_services_queued_request_while_waiting_for_header(self):
        payload = bytes(range(256)) * 5
        cpu = self.cpu(payload)
        cpu.defer_tx = True  # IO.SSTRG queues bytes; each ROM service sends one
        cpu.field("snl_txp", 0x1234)
        self.assertEqual(cpu.transfer(len(payload)), (0, payload))
        self.assertEqual(cpu.read_lengths, [512, 512, 512])
        self.assertFalse(cpu.queued_tx)
        self.assertGreater(len(cpu.read_header_calls), 3)
        self.assertEqual(cpu.field("snl_dead", width=1), 0)

    def test_partial_bulk_read_request_is_not_replayed(self):
        cpu = self.cpu(b"abcdef")
        cpu.tx_batches = [(2, -1), (0, -1), (5, 0)]
        self.assertEqual(cpu.transfer(6), (0, b"abcdef"))
        self.assertEqual([size for _, size in cpu.tx_calls], [7, 5, 5])
        self.assertEqual(cpu.requests, [b"\x12\x00\x00\x00\x00\x02\x00"])
        self.assertEqual(cpu.read_header_calls, [3])

    def test_bulk_read_request_failure_keeps_cache_and_caller_unpublished(self):
        cpu = self.cpu(b"abcdef")
        cpu.tx_batches = [(2, -6)]
        cpu.mem[0x10000:0x10006] = b"Z" * 6
        self.assertEqual(cpu.transfer(6), (-6, b""))
        self.assertEqual(cpu.field("snl_dead", width=1), 255)
        self.assertEqual(cpu.field("snl_len", width=2), 0)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.mem[0x10000:0x10006], b"Z" * 6)
        self.assertEqual(bytes(cpu.wire), b"\x12\x00")
        self.assertFalse(cpu.requests)
        self.assertFalse(cpu.read_header_calls)

    def test_fragmented_bulk_read_header_resumes_at_remaining_bytes(self):
        cpu = self.cpu(b"abcdef")
        cpu.read_header_batches = [(0, -1), (1, -1), (1, 0), (1, -1)]
        self.assertEqual(cpu.transfer(6), (0, b"abcdef"))
        self.assertEqual(cpu.read_header_calls, [3, 3, 2, 1])
        self.assertEqual(cpu.rom_calls, [6])
        self.assertEqual(cpu.field("snl_rx", width=2), 9)
        self.assertFalse(cpu.reply)

    def test_truncated_bulk_read_header_never_publishes_payload(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                cpu = self.cpu(b"abcdef")
                cpu.clock_step = 1
                cpu.truncate_reply = count
                cpu.mem[0x10000:0x10006] = b"Z" * 6
                self.assertEqual(cpu.transfer(6), (-13, b""))
                self.assertEqual(cpu.field("snl_rx", width=2), count)
                self.assertEqual(cpu.field("snl_dead", width=1), 255)
                self.assertEqual(cpu.field("snl_len", width=2), 0)
                self.assertEqual(cpu.field("fs_nblok"), 0)
                self.assertEqual(cpu.mem[0x10000:0x10006], b"Z" * 6)
                self.assertFalse(cpu.rom_calls)

    def test_bulk_read_header_driver_error_is_preserved(self):
        cpu = self.cpu(b"abcdef")
        cpu.read_header_batches = [(1, -6)]
        self.assertEqual(cpu.transfer(6), (-6, b""))
        self.assertEqual(cpu.field("snl_rx", width=2), 1)
        self.assertEqual(cpu.field("snl_last", width=2), 0xFFFA)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)
        self.assertFalse(cpu.rom_calls)

    def test_bulk_read_header_validates_status_and_count(self):
        for header in (b"\x01\x00\x00", b"\xff\x00\x00", b"\xeb\x00\x00",
                       b"\x00\x02\x01", b"\x00\x00\x00"):
            with self.subTest(header=header):
                cpu = self.cpu(b"abcdef")
                cpu.reply_override = header
                self.assertEqual(cpu.transfer(6), (-13, b""))
                self.assertEqual(cpu.field("snl_len", width=2), 0)
                self.assertEqual(cpu.field("fs_nblok"), 0)
                self.assertEqual(cpu.field("snl_dead", width=1), 255)
                self.assertFalse(cpu.rom_calls)

    def test_bulk_read_header_valid_host_error_remains_unpoisoned(self):
        cpu = self.cpu(b"abcdef")
        cpu.reply_override = b"\xed\x00\x00"  # Not Implemented, no payload
        self.assertEqual(cpu.transfer(6), (-19, b""))
        self.assertEqual(cpu.field("snl_dead", width=1), 0)
        self.assertEqual(cpu.diagnostics, ["dbg_host"])
        self.assertFalse(cpu.rom_calls)

    def test_bulk_copy_counts_only_complete_packets_before_transport_failure(self):
        cpu = self.cpu(bytes(range(256)) * 5)
        self.assertEqual(cpu.transfer(1), (0, b"\x00"))
        cpu.field("fs_nblok", 0)
        cpu.truncate_reply = 10  # next refill: header plus seven incomplete payload bytes
        cpu.mem[0x10000:0x10401] = b"Z" * 1025
        self.assertEqual(cpu.transfer(1024), (-13, bytes(range(256)) * 2))
        self.assertEqual(cpu.field("fs_nblok"), 512)
        self.assertEqual(cpu.reg["a1"], 0x10200)
        self.assertEqual(cpu.mem[0x10200:0x10401], b"Z" * 513)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_aligned_cache_copy_uses_fewer_than_one_step_per_byte(self):
        payload = bytes(range(256)) * 2
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(1), (0, payload[:1]))
        cpu.field("fs_nblok", 0)
        cpu.steps = 0
        self.assertEqual(cpu.transfer(512), (0, payload))
        self.assertLess(cpu.steps, 512)
        self.assertEqual(cpu.read_lengths, [512])  # no additional serial request

    def test_line_crosses_block_boundary(self):
        payload = b"a" * 511 + b"bc\nnext\n"
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(600, action=2), (0, payload[:514]))
        self.assertEqual(cpu.transfer(100, action=2), (0, b"next\n"))
        self.assertEqual(cpu.read_lengths, [512, 512])

    def test_line_full_does_not_consume_next_character(self):
        cpu = self.cpu(b"abc\n")
        self.assertEqual(cpu.transfer(3, action=2), (-5, b"abc"))
        self.assertEqual(cpu.transfer(1, action=2), (0, b"\n"))
        self.assertEqual(cpu.read_lengths, [512])

    def test_bulk_binary_and_exact_block_eof(self):
        payload = bytes(range(256)) * 4
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(1024), (0, payload))
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(cpu.read_lengths, [512, 512, 512])

    def test_empty_file_and_zero_length_requests(self):
        cpu = self.cpu(b"")
        self.assertEqual(cpu.transfer(0), (0, b""))
        self.assertEqual(cpu.read_lengths, [])
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(cpu.read_lengths, [512])

    def test_seek_reuses_window_or_refills(self):
        payload = bytes(range(256)) * 5
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(5), (0, payload[:5]))
        cpu.field("fs_nblok", 100)
        self.assertEqual(cpu.transfer(3), (0, payload[100:103]))
        self.assertEqual(cpu.read_lengths, [512])
        cpu.field("fs_nblok", 700)
        self.assertEqual(cpu.transfer(3), (0, payload[700:703]))
        cpu.field("fs_nblok", 0)
        self.assertEqual(cpu.transfer(3), (0, payload[:3]))
        offsets = [int.from_bytes(p[1:5], "big") for p in cpu.requests]
        self.assertEqual(offsets, [0, 700, 0])

    def test_write_invalidates_prefetch(self):
        cpu = self.cpu(b"abcdef\n")
        self.assertEqual(cpu.transfer(1), (0, b"a"))
        cpu.field("fs_nblok", 1)
        code, _ = cpu.transfer(2, action=1, data=b"XY")
        self.assertEqual(code, 0)
        self.assertEqual(cpu.field("snl_len", width=2), 0)
        cpu.field("fs_nblok", 0)
        self.assertEqual(cpu.transfer(7), (0, b"aXYdef\n"))
        self.assertEqual([p[0] for p in cpu.requests], [0x12, 0x13, 0x12])

    def test_bulk_read_above_64k_preserves_long_count(self):
        payload = bytes(range(256)) * 260
        cpu = self.cpu(payload)
        self.assertEqual(cpu.transfer(len(payload)), (0, payload))
        self.assertEqual(len(cpu.requests), 130)
        self.assertEqual(cpu.field("fs_nblok"), 66560)

    def test_binary_bulk_save_reopen_load(self):
        # Exercise the actual assembly write/read loops against the host.
        # Includes all byte values, >64K counts, and a partial last block.
        payload = (bytes(range(256)) * 260) + b"\x00\xff\x1a"
        cpu = self.cpu(b"")
        self.assertEqual(cpu.transfer(len(payload), action=1, data=payload)[0], 0)
        self.assertEqual(cpu.reg["d1"], len(payload))
        self.assertEqual(cpu.reg["a1"], 0x10000 + len(payload))
        self.assertEqual(cpu.field("fs_eblok"), len(payload))
        self.session.close()
        self.assertEqual((self.root / "test_bas").read_bytes(), payload)
        self.session.open(1, 1, b"test_bas")
        reader = CacheCPU(self.session)
        self.assertEqual(reader.transfer(len(payload)), (0, payload))
        self.assertEqual(reader.reg["a1"], 0x10000 + len(payload))

    def test_bulk_write_block_boundaries_use_string_io(self):
        for count in (0, 1, 511, 512, 513, 1024, 1537):
            with self.subTest(count=count):
                payload = bytes(i % 256 for i in range(count))
                cpu = self.cpu(b"")
                self.assertEqual(cpu.transfer(count, action=1, data=payload)[0], 0)
                self.assertEqual(cpu.reg["d1"], count)
                self.assertEqual(cpu.reg["a1"], 0x10000 + count)
                self.assertEqual(cpu.field("fs_nblok"), count)
                self.assertEqual(cpu.field("fs_eblok"), count)
                sizes = [min(512, count - offset) for offset in range(0, count, 512)]
                self.assertEqual([size for _, size in cpu.tx_calls], sizes)
                self.assertEqual([int.from_bytes(p[5:7], "big") for p in cpu.requests], sizes)
                self.session.flush()
                self.assertEqual((self.root / "test_bas").read_bytes(), payload)
                self.assertFalse(cpu.wire)
                self.assertFalse(cpu.reply)

    def test_bulk_write_partial_batches_resume_without_duplicate_bytes(self):
        payload = bytes(range(100))
        cpu = self.cpu(b"")
        # Includes ERR.NC with no progress, short success, and a complete NC.
        cpu.tx_batches = [(0, -1), (10, -1), (20, 0), (0, -1), (70, -1)]
        self.assertEqual(cpu.transfer(100, action=1, data=payload)[0], 0)
        self.assertEqual(cpu.tx_calls, [(0x10000, 100), (0x10000, 100),
                                        (0x1000A, 90), (0x1001E, 70),
                                        (0x1001E, 70)])
        self.assertEqual(cpu.requests, [b"\x13\x00\x00\x00\x00\x00\x64" + payload])
        self.assertEqual(cpu.reg["d1"], 100)
        self.assertEqual(cpu.reg["a1"], 0x10064)
        self.assertEqual(cpu.field("snl_dead", width=1), 0)
        self.assertEqual(cpu.kicks, 10)  # legacy service before and after every batch

    def test_bulk_write_partial_error_does_not_advance_unacknowledged_position(self):
        cpu = self.cpu(b"")
        cpu.tx_batches = [(10, -6)]
        self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -6)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.field("fs_eblok"), 0)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)
        self.assertEqual(cpu.field("snl_last", width=2), 0xFFFA)
        self.assertEqual(len(cpu.wire), 17)  # header plus ten queued payload bytes
        self.assertFalse(cpu.requests)
        # An already poisoned transport must not replay this partial packet.
        before = bytes(cpu.wire)
        cpu.reg["d2"] = 100
        self.assertEqual(cpu.run("snl_bput")[0], -13)
        self.assertEqual(bytes(cpu.wire), before)
        self.assertEqual(len(cpu.tx_calls), 1)

    def test_bulk_write_idle_timeout_after_progress(self):
        cpu = self.cpu(b"")
        cpu.clock_step = 1
        cpu.tx_batches = [(10, -1)] + [(0, -1)] * 10
        self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -13)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)
        self.assertFalse(cpu.requests)

    def test_bulk_write_progress_resets_idle_deadline(self):
        cpu = self.cpu(b"")
        cpu.clock_step = 1
        cpu.tx_batches = [(1, -1)] * 20
        payload = bytes(range(20))
        self.assertEqual(cpu.transfer(20, action=1, data=payload)[0], 0)
        self.assertEqual(cpu.reg["d1"], 20)
        self.assertGreater(cpu.clock, 3)
        self.assertEqual(cpu.field("snl_dead", width=1), 0)

    def test_bulk_write_short_host_ack_advances_only_confirmed_bytes(self):
        cpu = self.cpu(b"")
        cpu.reply_override = b"\xf5\x00\x03"  # disk full, three bytes acknowledged
        self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -11)
        self.assertEqual(cpu.reg["d1"], 3)
        self.assertEqual(cpu.reg["a1"], 0x10003)
        self.assertEqual(cpu.field("fs_nblok"), 3)
        self.assertEqual(cpu.field("fs_eblok"), 3)
        self.assertFalse(cpu.reply)

    def test_bulk_write_invalid_host_ack_poisoned_without_overadvance(self):
        for ack in (b"\x00\x00\x65", b"\x00\x00\x03"):
            with self.subTest(ack=ack):
                cpu = self.cpu(b"")
                cpu.reply_override = ack
                self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -13)
                self.assertLessEqual(cpu.reg["d1"], 100)
                self.assertEqual(cpu.reg["a1"], 0x10000 + cpu.reg["d1"])
                self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_write_rejects_invalid_serial_counts(self):
        for count in (101, -1):
            with self.subTest(count=count):
                cpu = self.cpu(b"")
                cpu.tx_batches = [(count, 0)]
                self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -13)
                self.assertEqual(cpu.reg["d1"], 0)
                self.assertEqual(cpu.reg["a1"], 0x10000)
                self.assertEqual(cpu.field("fs_nblok"), 0)
                self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_write_preserves_registers_and_zero_length(self):
        cpu = self.cpu(b"")
        cpu.reg.update(d2=0, a1=0x10000)
        saved = {r: cpu.reg[r] for r in cpu.register_list("d2-d7/a0-a6")}
        self.assertEqual(cpu.run("snl_bput")[0], 0)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual({r: cpu.reg[r] for r in saved}, saved)
        self.assertFalse(cpu.tx_calls)
        self.assertEqual(cpu.kicks, 0)
        # Queue ten bytes after a real packet header, to exercise normal I/O.
        cpu.wire = bytearray(b"\x13\x00\x00\x00\x00\x00\x0a")
        cpu.mem[0x10000:0x1000A] = b"0123456789"
        cpu.reg["d2"] = 10
        saved["d2"] = 10
        self.assertEqual(cpu.run("snl_bput")[0], 0)
        self.assertEqual(cpu.reg["d1"], 10)
        self.assertEqual({r: cpu.reg[r] for r in saved}, saved)
        self.assertEqual(cpu.reg["a1"], 0x10000)

    def test_bulk_write_retry_bound_with_stopped_clock(self):
        cpu = self.cpu(b"")
        cpu.clock_step = 0
        cpu.tx_batches = [(0, -1)] * 10
        cpu.code = [(op, size, ["#2", args[1]] if op == "move" and
                     args == ["#262143", "d7"] else args)
                    for op, size, args in cpu.code]
        self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -13)
        self.assertEqual(len(cpu.tx_calls), 2)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)

    def test_bulk_write_counts_only_acknowledged_previous_blocks(self):
        cpu = self.cpu(b"")
        cpu.tx_batches = [(512, 0), (4, -6)]
        payload = bytes(range(256)) * 4
        self.assertEqual(cpu.transfer(1024, action=1, data=payload)[0], -6)
        self.assertEqual(cpu.reg["d1"], 512)
        self.assertEqual(cpu.reg["a1"], 0x10200)
        self.assertEqual(cpu.field("fs_nblok"), 512)
        self.assertEqual(cpu.field("fs_eblok"), 512)
        self.assertEqual(len(cpu.requests), 1)
        self.assertEqual(len(cpu.wire), 11)

    def test_bulk_write_waits_for_host_ack_before_reporting_success(self):
        cpu = self.cpu(b"")
        cpu.reply_override = b""
        self.assertEqual(cpu.transfer(100, action=1, data=b"X" * 100)[0], -13)
        self.assertEqual(len(cpu.requests), 1)  # host received packet; ACK was lost
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_buffered_load_from_emulator_wrapped_file(self):
        payload = bytes(range(256)) * 6 + b"\xff"
        wrapper = snl.EMULATOR_MAGIC + b"\x00\x0f" + bytes.fromhex("00010000040000000000")
        (self.root / "test_bas").write_bytes(wrapper + payload)
        self.assertEqual(self.session.open(1, 1, b"test_bas"), len(payload))
        cpu = CacheCPU(self.session)
        # Model the length supplied by OPEN, which excludes the wrapper.
        cpu.field("fs_eblok", len(payload))
        self.assertEqual(cpu.transfer(len(payload)), (0, payload))
        self.assertEqual(cpu.transfer(1), (-10, b""))
        self.assertEqual(len(cpu.requests), 4)
        self.assertEqual((self.root / "test_bas").read_bytes(), wrapper + payload)

    def test_read_only_write_keeps_valid_cache(self):
        cpu = self.cpu(b"abcdef")
        self.assertEqual(cpu.transfer(1), (0, b"a"))
        cpu.field("snl_mode", 1, 1)
        self.assertEqual(cpu.transfer(1, action=1, data=b"X")[0], -20)
        self.assertEqual(cpu.field("fs_nblok"), 1)
        self.assertEqual(cpu.transfer(1), (0, b"b"))
        self.assertEqual(len(cpu.requests), 1)

    def test_write_after_cached_eof_can_extend_then_reread(self):
        cpu = self.cpu(b"abc")
        self.assertEqual(cpu.transfer(4), (-10, b"abc"))
        self.assertEqual(cpu.transfer(3, action=1, data=b"XYZ")[0], 0)
        self.assertEqual(cpu.field("fs_eblok"), 6)
        cpu.field("fs_nblok", 0)
        self.assertEqual(cpu.transfer(7), (-10, b"abcXYZ"))

    def test_partial_transport_reply_never_publishes_cache(self):
        cpu = self.cpu(b"abcdef\n")
        cpu.truncate_reply = 6  # header plus three data bytes
        self.assertEqual(cpu.transfer(1), (-13, b""))
        self.assertEqual(cpu.field("snl_len", width=2), 0)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_receive_fragmented_batches_and_empty_polls(self):
        payload = bytes(range(256)) * 2
        cpu = self.cpu(payload)
        cpu.rom_batches = [(0, -1), (10, -1), (20, -1), (0, -1), (482, 0)]
        self.assertEqual(cpu.transfer(512), (0, payload))
        self.assertEqual(cpu.rom_calls, [512, 512, 502, 482, 482])
        self.assertEqual(cpu.field("snl_rx", width=2), 515)
        self.assertEqual(cpu.field("snl_dead", width=1), 0)

    def test_bulk_receive_idle_timeout_after_progress(self):
        cpu = self.cpu(bytes(range(100)))
        cpu.clock_step = 1
        cpu.rom_batches = [(10, -1)] + [(0, -1)] * 10
        self.assertEqual(cpu.transfer(100), (-13, b""))
        self.assertEqual(cpu.field("snl_rx", width=2), 13)
        self.assertEqual(cpu.field("snl_len", width=2), 0)
        self.assertEqual(cpu.field("fs_nblok"), 0)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_receive_propagates_rom_error_after_partial_batch(self):
        cpu = self.cpu(b"abcdef")
        cpu.rom_batches = [(2, -6)]
        self.assertEqual(cpu.transfer(6), (-6, b""))
        self.assertEqual(cpu.field("snl_last", width=2), 0xFFFA)
        self.assertEqual(cpu.field("snl_rx", width=2), 5)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_receive_rejects_excessive_rom_count(self):
        cpu = self.cpu(b"abcdef")
        cpu.rom_batches = [(7, 0)]
        self.assertEqual(cpu.transfer(6), (-13, b""))
        self.assertEqual(cpu.field("snl_len", width=2), 0)

    def test_bulk_receive_preserves_registers_and_handles_zero_length(self):
        cpu = self.cpu(b"abc")
        cpu.reply = bytearray(b"abc")
        cpu.reg.update(d2=3, a1=0x10000)
        saved = {r: cpu.reg[r] for r in cpu.register_list("d2-d7/a0/a2-a6")}
        self.assertEqual(cpu.run("snl_bget")[0], 0)
        self.assertEqual(cpu.reg["d1"], 3)
        self.assertEqual(cpu.reg["a1"], 0x10003)
        self.assertEqual({r: cpu.reg[r] for r in saved}, saved)
        cpu.reg["d2"] = 0
        self.assertEqual(cpu.run("snl_bget")[0], 0)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(len(cpu.rom_calls), 1)

    def test_bulk_receive_retry_bound_with_stopped_clock(self):
        cpu = self.cpu(b"abc")
        cpu.reply = bytearray()
        cpu.clock_step = 0
        # Scale down only the retry budget, executing the real bound logic.
        cpu.code = [(op, size, ["#2", args[1]] if op == "move" and
                     args == ["#262143", "d7"] else args)
                    for op, size, args in cpu.code]
        cpu.reg.update(d2=3, a1=0x10000)
        self.assertEqual(cpu.run("snl_bget")[0], -13)
        self.assertEqual(len(cpu.rom_calls), 2)
        self.assertEqual(cpu.field("snl_dead", width=1), 255)

    def test_bulk_header_drains_64_bytes_for_short_or_full_caller_buffer(self):
        for count in (14, 64):
            with self.subTest(count=count):
                cpu = self.cpu(b"abc")
                expected = self.session.read_header()
                cpu.rom_limit = 10
                cpu.reg.update(d2=count, a1=0x10000)
                cpu.mem[0x10000:0x10041] = b"Z" * 65
                self.assertEqual(cpu.run("io_headr")[0], 0)
                self.assertEqual(cpu.reg["d1"], count)
                self.assertEqual(cpu.reg["a1"], 0x10000 + count)
                self.assertEqual(cpu.mem[0x10000:0x10000 + count], expected[:count])
                self.assertEqual(cpu.mem[0x10000 + count], ord("Z"))
                self.assertFalse(cpu.reply)
                self.assertEqual(cpu.rom_calls, [64, 54, 44, 34, 24, 14, 4])

    def test_bulk_header_failure_does_not_publish_partial_header(self):
        cpu = self.cpu(b"abc")
        cpu.truncate_reply = 11
        cpu.reg.update(d2=14, a1=0x10000)
        cpu.mem[0x10000:0x1000E] = b"Z" * 14
        self.assertEqual(cpu.run("io_headr")[0], -13)
        self.assertEqual(cpu.reg["d1"], 0)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.mem[0x10000:0x1000E], b"Z" * 14)

    def directory_request(self, cpu, mode, name=b"test_bas"):
        cpu.reg.update(a0=0x2000, a1=0x1000, a3=0xA000)
        cpu.field("fs_acces", mode, 1)
        cpu.field("fs_fname", len(name), 2)
        offset = 0x2000 + cpu.symbols["fs_fname"] + 2
        cpu.mem[offset:offset + len(name)] = name
        cpu.mem[0x1014] = 1  # PDB drive number
        cpu.mem[0x1022] = 5  # sentinel: QDOS owns this count on OPEN/DELETE
        cpu.mem[0xA050:0xA054] = (0x800).to_bytes(4, "big")
        return cpu.run("op_main")[0]

    def test_driver_delete_uses_status_only_and_leaves_channel_unregistered(self):
        cpu = self.cpu(b"old")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 255, b"TEST_BAS"), 0)
        self.assertEqual(cpu.requests[-1], b"\x11\x01\xff\x08TEST_BAS")
        self.assertEqual(cpu.requests[0][:5], b"~SNL?")
        self.assertFalse(cpu.reply)
        self.assertEqual(cpu.field("snl_rx", width=2), 1)
        self.assertEqual(cpu.mem[0xA048], 0)
        self.assertEqual(cpu.mem[0x1022], 5)
        self.assertEqual(cpu.field("fs_acces", width=1), 255)
        self.assertFalse((self.root / "test_bas").exists())
        self.assertEqual(self.directory_request(cpu, 2), 0)
        self.assertEqual(cpu.mem[0xA048], 255)  # subsequent real OPEN takes lock
        self.assertEqual(cpu.field("snl_rx", width=2), 5)

    def test_driver_delete_not_found_preserves_status_and_file_count(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 255, b"missing"), -7)
        self.assertEqual(cpu.mem[0xA048], 0)
        self.assertEqual(cpu.mem[0x1022], 5)
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")
        self.assertEqual(cpu.diagnostics, [])

    def test_driver_missing_open_is_quiet(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 1, b"missing"), -7)
        self.assertEqual(cpu.diagnostics, [])

    def test_open_and_data_io_preserve_smsqe_owned_channel_fields(self):
        payload = b'10 PRINT "QIMSI"\n20 STOP\n'
        cpu = self.cpu(payload)
        self.session.close()
        start = cpu.reg["a5"] + 0x58
        sentinel = bytes(range(0x58, 0x70))
        cpu.mem[start:start + len(sentinel)] = sentinel
        self.assertEqual(self.directory_request(cpu, 0), 0)
        self.assertEqual(cpu.transfer(len(payload)), (0, payload))
        self.assertEqual(cpu.mem[start:start + len(sentinel)], sentinel)

    def test_driver_broken_open_retains_transport_diagnostics(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.truncate_reply = 1  # success byte but missing length
        self.assertEqual(self.directory_request(cpu, 1), -13)
        self.assertEqual(cpu.diagnostics, ["dbg_rhi", "dbg_rx", "dbg_ser"])

    def test_driver_delete_with_open_channel_sends_no_request(self):
        cpu = self.cpu(b"keep")
        cpu.mem[0xA048] = 255
        self.assertEqual(self.directory_request(cpu, 255), -9)
        self.assertFalse(cpu.requests)
        self.assertEqual(cpu.mem[0x1022], 5)
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")

    def test_ready_offline_then_start_daemon_and_retry_with_stale_reply(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.daemon_online = False
        self.assertEqual(self.directory_request(cpu, 1), -13)
        self.assertEqual(len(cpu.requests), 1)
        self.assertTrue(cpu.requests[0].startswith(b"~SNL?"))
        self.assertEqual(cpu.mem[0xA048], 0)
        self.assertEqual(cpu.diagnostics, [])
        self.assertEqual(cpu.field("snl_dead", width=1), 0)
        # A delayed reply to the first probe is already in the QL queue.
        delayed = Port(cpu.offline_packets[0])
        snl.serve_one(delayed, self.session)
        cpu.reply.extend(delayed.output)
        cpu.daemon_online = True
        self.assertEqual(self.directory_request(cpu, 1), 0)
        probes = [p for p in cpu.requests if p.startswith(b"~SNL?")]
        self.assertEqual(len(probes), 2)
        self.assertNotEqual(probes[0], probes[1])
        self.assertEqual(cpu.requests[-1], b"\x11\x01\x01\x08test_bas")
        self.assertFalse(cpu.reply)
        self.assertEqual(cpu.field("fs_eblok"), 4)

    def test_ready_discards_noise_and_partial_prefix_before_current_reply(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.ready_noise = b"\x00\x00\xffjunk~SNL!ABC~SNL!" + b"P" * 16 + b"\n"
        self.assertEqual(self.directory_request(cpu, 1), 0)
        self.assertFalse(cpu.reply)
        self.assertEqual(cpu.diagnostics, [])

    def test_ready_wrong_token_cannot_authorize_delete(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.ready_wrong_token = True
        self.assertEqual(self.directory_request(cpu, 255), -13)
        self.assertEqual(len(cpu.requests), 1)
        self.assertTrue(cpu.requests[0].startswith(b"~SNL?"))
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")
        self.assertEqual(cpu.diagnostics, [])

    def test_ready_repeated_offline_attempts_leave_no_file_requests(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.daemon_online = False
        for mode in (1, 2, 255):
            self.assertEqual(self.directory_request(cpu, mode), -13)
        self.assertEqual(len(set(cpu.requests)), 3)
        self.assertTrue(all(p.startswith(b"~SNL?") for p in cpu.requests))
        self.assertEqual(cpu.mem[0xA048], 0)
        self.assertEqual(cpu.mem[0x1022], 5)

    def test_ready_releases_stale_host_session_before_delete(self):
        cpu = self.cpu(b"old")
        # Host has an open session, but QL's linkage says no active channel.
        self.assertEqual(self.directory_request(cpu, 255), 0)
        self.assertIsNone(self.session.file)
        self.assertFalse((self.root / "test_bas").exists())

    def test_ready_sends_nothing_when_an_snl_channel_is_active(self):
        cpu = self.cpu(b"keep")
        cpu.mem[0xA048] = 255
        self.assertEqual(self.directory_request(cpu, 1), -9)
        self.assertFalse(cpu.requests)
        self.assertIsNotNone(self.session.file)

    def test_ready_token_contains_installation_epoch_and_attempt_counter(self):
        cpu = self.cpu(b"keep")
        cpu.mem[0xA058:0xA05C] = bytes.fromhex("12345678")
        self.assertEqual(self.directory_request(cpu, 1), 0)
        self.assertEqual(cpu.requests[0], b"~SNL?BCDEFGHIAAAAAAAB\n")

    def test_ready_retry_bound_when_clock_is_stopped(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        cpu.daemon_online = False
        cpu.clock_step = 0
        cpu.code = [(op, size, ["#2", args[1]] if op == "move" and
                     args == ["#262143", "d7"] else args)
                    for op, size, args in cpu.code]
        self.assertEqual(self.directory_request(cpu, 1), -13)
        self.assertEqual(len(cpu.requests), 1)
        self.assertEqual(cpu.mem[0xA048], 0)

    def test_stock_dir_sequence_open_info_64_byte_reads_and_eof(self):
        cpu = self.cpu(b"")
        self.session.close()
        for i in range(9):
            (self.root / f"Source_{i}").write_bytes(b"code")
        self.assertEqual(self.directory_request(cpu, 4, b""), 0)
        self.assertEqual(cpu.field("fs_eblok"), 640)
        cpu.reg.update(a1=0x10000)
        cpu.mem[0x10000:0x1000B] = b"Z" * 11
        with patch.object(snl.shutil, "disk_usage", return_value=SimpleNamespace(total=8192, free=2048)):
            self.assertEqual(cpu.run("io_info")[0], 0)
        self.assertEqual(cpu.reg["d1"], 0x00040010)
        self.assertEqual(cpu.reg["a1"], 0x1000A)
        self.assertEqual(cpu.mem[0x10000:0x1000B], b"SNL1      Z")
        names = []
        for _ in range(10):
            code, record = cpu.transfer(64)
            self.assertEqual(code, 0)
            self.assertEqual(len(record), 64)
            n = int.from_bytes(record[14:16], "big")
            names.append(record[16:16+n].decode("ascii"))
        self.assertEqual(names, [f"Source_{i}" for i in range(9)] + ["test_bas"])
        self.assertEqual(cpu.transfer(64), (-10, b""))
        reads = [p for p in cpu.requests if p[0] == 0x12]
        self.assertEqual(len(reads), 2)  # eight directory records per cache block
        self.assertEqual(cpu.read_lengths, [512, 512])

    def test_driver_empty_directory_opens_and_returns_eof(self):
        cpu = self.cpu(b"")
        self.session.close()
        (self.root / "test_bas").unlink()
        self.assertEqual(self.directory_request(cpu, 4, b""), 0)
        self.assertEqual(cpu.field("fs_eblok"), 0)
        self.assertEqual(cpu.transfer(64), (-10, b""))

    def test_driver_directory_write_is_rejected_before_sending_any_bytes(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 4, b""), 0)
        before = len(cpu.requests)
        self.assertEqual(cpu.transfer(1, action=1, data=b"x")[0], -20)
        self.assertEqual(len(cpu.requests), before)
        self.assertEqual((self.root / "test_bas").read_bytes(), b"keep")

    def test_driver_medium_info_partial_reply_leaves_caller_buffer_untouched(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 4, b""), 0)
        cpu.truncate_reply = 8
        cpu.reg.update(a1=0x10000)
        cpu.mem[0x10000:0x1000A] = b"Z" * 10
        self.assertEqual(cpu.run("io_info")[0], -13)
        self.assertEqual(cpu.reg["a1"], 0x10000)
        self.assertEqual(cpu.mem[0x10000:0x1000A], b"Z" * 10)

    def test_driver_rejects_empty_name_for_regular_file(self):
        cpu = self.cpu(b"keep")
        self.session.close()
        self.assertEqual(self.directory_request(cpu, 1, b""), -12)
        self.assertFalse(cpu.requests)

    def test_bad_count_or_successful_short_reply_is_rejected(self):
        for reply in (b"\x00\x02\x01", b"\x00\x00\x01x"):
            with self.subTest(reply=reply):
                cpu = self.cpu(b"abc")
                cpu.reply_override = reply
                self.assertEqual(cpu.transfer(1), (-13, b""))
                self.assertEqual(cpu.field("snl_len", width=2), 0)


if __name__ == "__main__":
    unittest.main()
