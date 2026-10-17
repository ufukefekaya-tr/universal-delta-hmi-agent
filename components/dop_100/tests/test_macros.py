# SPDX-License-Identifier: Apache-2.0
"""Neutral byte fixtures exercise record framing, preservation and receipts."""
import gzip
import hashlib
import struct
import unittest

from universal_diascreen_hmi.errors import AgentError
from universal_diascreen_hmi.macros import (HEADER, TAIL, MacroInstruction, MacroProgram,
                                          inspect_compiled, parse_macro, parse_parsed_address)


def record(opcode=bytes.fromhex("0a00011c"), fields=None):
    fields = fields or (b"BITOFF DIA_TAG@{ControlLink}0.Shared.request", b"{ControlLink}0@Shared.request", b"Var2", b"Var3", b"Var4")
    return opcode + b"".join(struct.pack("<I", len(field)) + field for field in fields) + TAIL


def descriptor(name):
    return bytes.fromhex("7300000000000001ff") + struct.pack("<H", len(name)) + name


class MacroTests(unittest.TestCase):
    def test_counted_roundtrip_and_source_with_newlines(self):
        fields = (b"visible\r\nsource\x00still counted", b"{ControlLink}0@Shared.request", b"Var2", b"Var3", b"Var4")
        data = HEADER + record(fields=fields) + record()
        program = parse_macro(data)
        self.assertEqual(program.to_bytes(), data)
        self.assertEqual(program.instructions[0].fields[0], fields[0])
        self.assertEqual(len(program.instructions), 2)

    def test_empty_slot_and_header_only(self):
        self.assertEqual(parse_macro(b"").to_bytes(), b"")
        with self.assertRaises(AgentError):
            parse_macro(HEADER)

    def test_exact_operand_replacement_preserves_visible_source(self):
        data = HEADER + record()
        program = parse_macro(data)
        output = program.replace_operand(0, 1, b"{ControlLink}0@Shared.request", b"{ControlLink}0@Runtime.Shared.request")
        reread = parse_macro(output)
        self.assertEqual(reread.instructions[0].fields[0], program.instructions[0].fields[0])
        self.assertEqual(reread.instructions[0].fields[1], b"{ControlLink}0@Runtime.Shared.request")
        reverse = reread.replace_operand(0, 1, b"{ControlLink}0@Runtime.Shared.request", b"{ControlLink}0@Shared.request")
        self.assertEqual(reverse, data)

    def test_reject_source_and_incorrect_expected_or_index(self):
        program = parse_macro(HEADER + record())
        cases = [(0, 0, program.instructions[0].fields[0], b"changed"),
                 (0, 1, b"stale", b"$10"), (-1, 1, b"stale", b"$10"),
                 (0, 5, b"stale", b"$10"), (True, 1, b"stale", b"$10")]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(AgentError):
                program.replace_operand(*args)

    def test_display_addresses_and_source_statements_are_not_operands(self):
        program = parse_macro(HEADER + record())
        for operand in (b"DIA_TAG@{ControlLink}0.Shared.request", b"BITON $1", b"$1\r\nENDIF", b"{ControlLink}0@", b"Shared.request"):
            with self.subTest(operand=operand), self.assertRaises(AgentError):
                program.replace_operand(0, 1, program.instructions[0].fields[1], operand)
        self.assertEqual(parse_parsed_address(b"{ControlLink}0@Runtime.Shared.flags[2]")["path"], "Runtime.Shared.flags[2]")
        with self.assertRaises(AgentError):
            parse_parsed_address(b"{ControlLink}" + b"1" * 5000 + b"@Shared.request")

    def test_legacy_display_operand_can_be_inspected_without_acceptance(self):
        fields = (b"BITOFF DIA_TAG@{ControlLink}0.Shared.request",
                  b"DIA_TAG@{ControlLink}0.Shared.request", b"Var2", b"Var3", b"Var4")
        program = parse_macro(HEADER + record(fields=fields))
        self.assertEqual(program.inspect()["operand_status"], "INVALID_DISPLAY_FORM")
        self.assertEqual(program.inspect()["display_form_parsed_operands"],
                         [{"instruction_index": 0, "field_index": 1}])

    def test_unknown_opcode_roundtrips_but_blocks_all_writes(self):
        data = HEADER + record() + record(opcode=b"\x99\x88\x77\x66")
        program = parse_macro(data)
        self.assertEqual(program.to_bytes(), data)
        self.assertEqual(program.inspect()["unknown_opcodes"], ["99887766"])
        with self.assertRaises(AgentError):
            program.replace_operand(0, 1, program.instructions[0].fields[1], b"$1")

    def test_truncation_lengths_flags_and_trailing_bytes(self):
        data = HEADER + record()
        mutants = [b"bad" + data, data[:7], data[:12], data[:-1],
                   data[:8] + struct.pack("<I", 0xFFFFFFFF) + data[12:],
                   data[:-14] + b"\x02" + data[-13:], data + b"x"]
        for mutant in mutants:
            with self.subTest(size=len(mutant)), self.assertRaises(AgentError):
                parse_macro(mutant)

    def test_builder_validates_flags_and_field_types(self):
        for instruction in (MacroInstruction(b"bad", (b"",) * 5),
                            MacroInstruction(b"1234", (b"",) * 5, b"bad"),
                            MacroInstruction(b"1234", (b"",) * 4),
                            MacroInstruction(b"1234", ("text",) * 5)):
            with self.subTest(instruction=instruction), self.assertRaises(AgentError):
                MacroProgram((instruction,)).to_bytes()

    def receipt(self, data):
        return {"artifact_sha256": hashlib.sha256(data).hexdigest(),
                "source_sha256": hashlib.sha256(b"neutral-source").hexdigest(),
                "candidate_sha256": hashlib.sha256(b"neutral-candidate").hexdigest()}

    def inspect(self, data, receipt=None):
        receipt = self.receipt(data) if receipt is None else receipt
        return inspect_compiled(data, artifact_sha=hashlib.sha256(data).hexdigest(),
                                source_sha=hashlib.sha256(b"neutral-source").hexdigest(),
                                candidate_sha=hashlib.sha256(b"neutral-candidate").hexdigest(),
                                receipt=receipt)

    def test_compiled_observation_is_partial_counted_scan(self):
        data = b"opaque" + descriptor(b"Runtime.Shared.request") + b"opaque"
        result = self.inspect(data)
        self.assertEqual(result["descriptor_count"], 1)
        self.assertEqual(result["descriptors"][0]["symbol"], "Runtime.Shared.request")
        self.assertFalse(result["full_cin_acceptance"])
        self.assertEqual(result["compile_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(result["runtime_acceptance"], "NOT_VERIFIED")

    def test_compiled_stale_source_candidate_and_actual_sha_rejected(self):
        data = descriptor(b"Shared.request")
        for name in ("artifact_sha256", "source_sha256", "candidate_sha256"):
            receipt = self.receipt(data)
            receipt[name] = "0" * 64
            with self.subTest(name=name), self.assertRaises(AgentError):
                self.inspect(data, receipt)
        with self.assertRaises(AgentError):
            inspect_compiled(data, artifact_sha="0" * 64, source_sha="1" * 64,
                             candidate_sha="2" * 64, receipt={})
        with self.assertRaises(AgentError):
            self.inspect(data, {})

    def test_gzip_domain_and_invalid_count_remain_observations(self):
        invalid = bytes.fromhex("7300000000000001ff") + b"\xff\xffshort"
        data = b"neutral-header" + gzip.compress(descriptor(b"Shared.request") + invalid, mtime=0)
        result = self.inspect(data)
        self.assertEqual(result["scan_domain"], "decompressed_observation_bytes")
        self.assertEqual(result["descriptor_count"], 1)
        self.assertEqual(len(result["ignored_signatures"]), 1)
        with self.assertRaises(AgentError):
            self.inspect(gzip.compress(b"tiny", mtime=0)[:-3])
        with self.assertRaises(AgentError):
            self.inspect(gzip.compress(b"one", mtime=0) + gzip.compress(b"two", mtime=0))


if __name__ == "__main__":
    unittest.main()
