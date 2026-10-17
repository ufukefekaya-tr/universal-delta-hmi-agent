"""Neutral existing-WORD numeric witnesses; no vendor or rendered proof."""
from copy import deepcopy
import gzip
import tempfile
from pathlib import Path
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.existing_integer_numeric import ExistingIntegerNumeric, integer_numeric_contract
from universal_hmi.native.records import Record
from test_existing_edit import existing_edit_fixture
from test_existing_program import existing_schema, sha


def integer_numeric_fixture():
    """Four immutable numeric originals in a three-page synthetic closed graph."""
    raw, _, presentation, _ = existing_edit_fixture()
    source = NativeAdapter(raw, "delta_dopsoft2")
    owners = {o["id"]: o for p in _groups(source.document) for o in p["elements"]}
    input_owner = owners["34"]
    for key, value in (("DotNum", b"0"), ("IntNum", b"5"),
                       ("MinValue", b"-32768.000000"), ("MaxValue", b"32767.000000")):
        input_owner["section"].one(key).set_value(value)
    for original, identity in ((input_owner, "137"), (owners["31"], "139")):
        parts = deepcopy(source.document.sections[original["start"]:original["end"]])
        parts[0].one("nPartsID").set_value(identity.encode())
        parts[0].one("MemFmt").set_value(b"2")
        parts[0].one("IntNum").set_value(b"5")
        parts[0].one("DotNum").set_value(b"0")
        if identity == "137":
            parts[0].one("MinValue").set_value(b"0.000000")
            parts[0].one("MaxValue").set_value(b"65535.000000")
        source.document.sections.extend(parts)
    raw = source.envelope.encode(source.document.bytes())
    descriptor = {**presentation, "mode": "existing_word_integer_numeric_v1",
                  "source_sha256": sha(raw), "authority_sha256": sha(b"SYNTHETIC INTEGER NUMERIC AUTHORITY")}
    return raw, existing_schema(raw), descriptor


class ExistingIntegerNumericTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema, self.descriptor = integer_numeric_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = ExistingIntegerNumeric(self.source, self.schema, self.descriptor)

    def owner(self, sid="1", eid="31", source=None):
        return next(o for p in _groups((source or self.source).document) if p["id"] == sid
                    for o in p["elements"] if o["id"] == eid)

    def op(self, sid="1", eid="31", source=None, **changes):
        source = source or self.source
        owner = self.owner(sid, eid, source)
        section = owner["section"]
        extent = b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])
        operation = {"op": "configure_existing_integer_numeric", "screen_id": sid, "element_id": eid,
                     "owner_sha256": sha(extent), "data_type": "INT" if section.one("MemFmt").value == b"1" else "UINT",
                     "value_model": "integer_fixed_decimal", "integer_digits": 5, "fractional_digits": 0}
        if section.one("Type").value == b"6":
            operation.update(raw_minimum=-32768 if operation["data_type"] == "INT" else 0,
                             raw_maximum=32767 if operation["data_type"] == "INT" else 65535)
        operation.update(changes)
        return operation

    def error(self, function, code=None):
        with self.assertRaises(HmiError) as raised:
            function()
        if code:
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def candidate(self, operations):
        return NativeAdapter(self.program.apply(operations), self.source.family)

    def mutate_owner(self, source, sid, eid, before, after):
        owner = self.owner(sid, eid, source)
        block = b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])
        self.assertIn(before, block)
        return NativeAdapter(source.envelope.encode(source.envelope.body.replace(block, block.replace(before, after, 1), 1)), source.family)

    def reprogram(self, source):
        descriptor = {**self.descriptor, "source_sha256": sha(source.original)}
        return ExistingIntegerNumeric(source, existing_schema(source.original), descriptor)

    def test_signed_and_unsigned_full_domain_display_digits_exact(self):
        for sid, eid, fractions in (("1", "31", (0, 1, 4)), ("12", "139", (0, 1, 2, 3, 4))):
            for fractional in fractions:
                with self.subTest(eid=eid, fractional=fractional):
                    operation = self.op(sid, eid, integer_digits=5 - fractional, fractional_digits=fractional)
                    candidate = self.candidate([operation])
                    self.assertTrue(self.program.verify(candidate, [operation]))
                    section = self.owner(sid, eid, candidate)["section"]
                    self.assertEqual(section.one("IntNum").value, str(5 - fractional).encode())
                    self.assertEqual(section.one("DotNum").value, str(fractional).encode())
                    self.assertIsNone(section.one("MinValue", False))
                    self.assertIsNone(section.one("MaxValue", False))

    def test_f0_inputs_canonical_boundaries_signed_unsigned_and_short_domains(self):
        cases = [("7", "34", -32768, 32767, 5), ("7", "34", -999, 999, 3),
                 ("7", "34", -9, -1, 1), ("7", "34", 0, 9, 1),
                 ("7", "34", "-32768", "-32767", 5),
                 ("12", "137", 0, 65535, 5), ("12", "137", 65534, 65535, 5),
                 ("12", "137", "0", "99", 2)]
        for sid, eid, minimum, maximum, digits in cases:
            with self.subTest(eid=eid, minimum=minimum, maximum=maximum):
                operation = self.op(sid, eid, raw_minimum=minimum, raw_maximum=maximum, integer_digits=digits)
                saved = self.owner(sid, eid, self.candidate([operation]))["section"]
                # Equivalent original decimal spellings stay unchanged.
                for field, value in (("MinValue", minimum), ("MaxValue", maximum)):
                    old = self.owner(sid, eid)["section"].one(field)
                    expected = old.raw if float(old.value) == int(value) else field.encode() + b"=" + str(value).encode() + b"\r\n"
                    self.assertEqual(saved.one(field).raw, expected)
                self.assertEqual(saved.one("IntNum").value, str(digits).encode())
                self.assertEqual(saved.one("DotNum").value, b"0")

    def test_only_numeric_scalars_change_all_other_owner_state_resource_bytes_exact(self):
        operations = [self.op(integer_digits=1, fractional_digits=4),
                      self.op("7", "34", raw_minimum=-12, raw_maximum=345, integer_digits=3)]
        candidate = self.candidate(operations)
        modified = {"31": {"IntNum", "DotNum"}, "34": {"IntNum", "MinValue", "MaxValue"}}
        for original_page, saved_page in zip(_groups(self.source.document), _groups(candidate.document)):
            self.assertEqual(original_page["section"].bytes(), saved_page["section"].bytes())
            self.assertEqual([o["id"] for o in original_page["elements"]], [o["id"] for o in saved_page["elements"]])
            for old, saved in zip(original_page["elements"], saved_page["elements"]):
                managed = modified.get(old["id"], set())
                for record in old["section"].records:
                    if record.key not in managed:
                        self.assertEqual(saved["section"].one(record.key).raw, record.raw)
                self.assertEqual([s.bytes() for s in saved["states"]], [s.bytes() for s in old["states"]])
        self.assertEqual(candidate.document.tail, self.source.document.tail)
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))

    def test_independent_raw_spans_restore_whole_body_and_expected_has_no_mutation_dependency(self):
        operations = [self.op(integer_digits=1, fractional_digits=4),
                      self.op("7", "34", raw_minimum=-9, raw_maximum=1, integer_digits=1)]
        candidate = self.candidate(operations)
        spans = self.program.spans(operations)
        expected, restored, cursor, saved_cursor, delta = [], [], 0, 0, 0
        for start, end, raw in spans:
            expected.extend((self.source.envelope.body[cursor:start], raw)); cursor = end
            stop = start + delta
            restored.extend((candidate.envelope.body[saved_cursor:stop], self.source.envelope.body[start:end]))
            saved_cursor = stop + len(raw); delta += len(raw) - (end - start)
        expected.append(self.source.envelope.body[cursor:]); restored.append(candidate.envelope.body[saved_cursor:])
        self.assertEqual(b"".join(expected), candidate.envelope.body)
        self.assertEqual(b"".join(restored), self.source.envelope.body)
        self.program.apply = lambda *args: self.fail("Expectation called mutation")
        self.assertEqual(self.program.expected_body(operations), candidate.envelope.body)

    def test_exact_noop_equivalent_original_spellings_and_noncanonical_gzip_refused(self):
        operations = [self.op(integer_digits=4, fractional_digits=1), self.op("7", "34"), self.op("12", "137")]
        self.assertEqual(self.program.spans(operations), [])
        self.assertEqual(self.program.apply(operations), self.raw)
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source, operations))
        changed = self.source.envelope.thumbnail + gzip.compress(
            bytes(b ^ 0x64 for b in self.source.envelope.prefix + self.source.envelope.body), mtime=91)
        self.assertNotEqual(changed, self.raw)
        self.error(lambda: self.program.verify(NativeAdapter(changed, self.source.family), operations),
                   "EXISTING_INTEGER_NUMERIC_PRESERVATION")

    def test_requested_representation_limits_and_all_fractional_inputs_fail_closed(self):
        for datatype in ("UINT", "DINT", "UDINT", "REAL", "LREAL", "TIME", None, [], {}):
            self.error(lambda: self.program.apply([self.op(data_type=datatype)]))
        for fractional in (1, 2, 4, 15, -1):
            for minimum, maximum in ((-32765, 32765), (-32500, 32500), (-32762, 32767)):
                self.error(lambda: self.program.apply([self.op("7", "34", fractional_digits=fractional,
                           raw_minimum=minimum, raw_maximum=maximum)]), "UNQUALIFIED_EXISTING_FRACTIONAL_INPUT")
        for fractional in (2, 3, 5, -1):
            self.error(lambda: self.program.apply([self.op(integer_digits=5 - fractional, fractional_digits=fractional)]))
        for integer, fractional in ((1, 0), (4, 0), (5, 1), (2, 4), (0, 4), (6, 0)):
            self.error(lambda: self.program.apply([self.op(integer_digits=integer, fractional_digits=fractional)]))

    def test_input_limits_strict_integral_order_width_and_digits(self):
        for low, high in ((-32769, 32767), (-32768, 32768), (0, 0), (1, 0), (True, 2), (0.0, 1),
                          ("-0", "1"), ("0.0", "1"), ("0", "1e1"), ("+0", "1"), ("01", "2"),
                          (" 0", "1"), ("NaN", "1"), (None, 1), ([], 1), ({}, 1), ("٠", "1")):
            self.error(lambda: self.program.apply([self.op("7", "34", raw_minimum=low, raw_maximum=high)]))
        self.error(lambda: self.program.apply([self.op("12", "137", raw_minimum=-1)]), "EXISTING_INTEGER_NUMERIC_LIMIT")
        self.error(lambda: self.program.apply([self.op("12", "137", raw_maximum=65536)]), "EXISTING_INTEGER_NUMERIC_LIMIT")
        self.error(lambda: self.program.apply([self.op("7", "34", raw_minimum=-100, raw_maximum=999, integer_digits=2)]),
                   "EXISTING_INTEGER_NUMERIC_DIGITS")

    def test_operation_shapes_duplicate_missing_pins_and_typed_bad_input(self):
        for operations in (None, {}, "", [None], [[]], [{"op": []}], [self.op()] * 4097):
            self.error(lambda: self.program.apply(operations))
        cyclic = []; cyclic.append(cyclic); self.error(lambda: self.program.apply(cyclic))
        deep = {}; pointer = deep
        for _ in range(40):
            pointer["child"] = {}; pointer = pointer["child"]
        self.error(lambda: self.program.apply([deep]))
        for value in (None, [], {}, True, 0.0, "5"):
            for field in ("integer_digits", "fractional_digits"):
                self.error(lambda: self.program.apply([self.op(**{field: value})]))
        for field, value in (("owner_sha256", "0" * 64), ("owner_sha256", []), ("screen_id", "01"),
                             ("element_id", "999"), ("value_model", "floating")):
            self.error(lambda: self.program.apply([self.op(**{field: value})]))
        operation = self.op()
        self.error(lambda: self.program.apply([operation, deepcopy(operation)]), "DUPLICATE_EXISTING_INTEGER_NUMERIC")
        for changes in ({"raw_minimum": 0}, {"MemFmt": "1"}, {"read": {"address": "D2"}},
                        {"gain": 1}, {"storage_conversion": True}, {"unit": "C"}):
            self.error(lambda: self.program.apply([self.op(**changes)]), "INVALID_EXISTING_INTEGER_NUMERIC_OPERATION")
        operation = self.op("7", "34"); del operation["raw_minimum"]
        self.error(lambda: self.program.apply([operation]), "INVALID_EXISTING_INTEGER_NUMERIC_OPERATION")

    def test_source_floating_width_format_fractional_input_and_scaling_rehashed_refused(self):
        for sid, eid, before, after in (("1", "31", b"MemLen=1", b"MemLen=2"),
            ("1", "31", b"MemFmt=1", b"MemFmt=3"), ("1", "31", b"DotNum=1", b"DotNum=2"),
            ("7", "34", b"DotNum=0", b"DotNum=1"), ("1", "31", b"GainValue=1.0", b"GainValue=2.0"),
            ("1", "31", b"OffsetValue=0.000000", b"OffsetValue=1.000000"),
            ("7", "34", b"MinValue=-32768.000000", b"MinValue=-32768.1")):
            source = self.mutate_owner(self.source, sid, eid, before, after)
            self.error(lambda: self.reprogram(source).apply([self.op(sid, eid, source)]))
        source = self.mutate_owner(self.source, "1", "31", b"GainValue=1.0", b"GainValue=1e0")
        source = self.mutate_owner(source, "1", "31", b"OffsetValue=0.000000", b"OffsetValue=-0.0")
        operation = self.op(source=source, integer_digits=1, fractional_digits=4)
        candidate = NativeAdapter(self.reprogram(source).apply([operation]), source.family)
        self.assertEqual(self.owner(source=candidate)["section"].one("GainValue").raw, b"GainValue=1e0\r\n")
        self.assertEqual(self.owner(source=candidate)["section"].one("OffsetValue").raw, b"OffsetValue=-0.0\r\n")

    def test_unsafe_conditional_dynamic_keypad_macro_fields_and_ambiguous_scalars_refused(self):
        cases = [(b"OffsetReadVar=None", b"OffsetReadVar={Link2}1@D2"),
                 (b"VisibleVar=None", b"VisibleVar={Link2}1@M1"),
                 (b"InterLockVar=None", b"InterLockVar={Link2}1@M2"),
                 (b"TriggerVar=None", b"TriggerVar={Link2}1@M3"),
                 (b"Active=0", b"Active=1"), (b"UseCustKeypad=0", b"UseCustKeypad=1"),
                 (b"KeypadScreenID=0", b"KeypadScreenID=12"), (b"Variation=0", b"Variation=1"),
                 (b"Roundoff=0", b"Roundoff=1"), (b"ReadMemType=0", b"ReadMemType=1"),
                 (b"BeforeExecMacroLen=0\r\n", b"BeforeExecMacroLen=2\r\n\r\n"),
                 (b"IntNum=5\r\n", b"IntNum=5\r\nIntNum=4\r\n"),
                 (b"MinValue=-32768.000000", b"MinValue=\xff"),
                 (b"GainValue=1.0", b"GainValue=NaN")]
        for before, after in cases:
            def rejected():
                source = self.mutate_owner(self.source, "7", "34", before, after)
                self.reprogram(source).apply([self.op("7", "34", source)])
            self.error(rejected)
        for key in ("MinValueVar", "MaxValueVar", "ConFirmWindow", "UnknownRef"):
            source = NativeAdapter(self.raw, self.source.family)
            self.owner("7", "34", source)["section"].records.append(Record(key.encode() + b"=0\r\n", key, b"0"))
            source = NativeAdapter(source.envelope.encode(source.document.bytes()), source.family)
            self.error(lambda: self.reprogram(source).apply([self.op("7", "34", source)]))

    def test_descriptor_exactness_freshness_source_and_cached_projection(self):
        for changes in ({"qualified": False}, {"contract_version": True}, {"mode": "variable_scalar_records_v1"},
                        {"family": "delta_diascreen"}, {"model_id": True}, {"editor_version": "2.00.07"},
                        {"authority_sha256": "0"}, {"source_sha256": []}, {"extra": 1}):
            descriptor = {**self.descriptor, **changes}
            self.error(lambda: integer_numeric_contract(descriptor))
        self.program.contract["authority_sha256"] = "0" * 64
        self.error(lambda: self.program.apply([]), "UNQUALIFIED_EXISTING_INTEGER_NUMERIC")
        changed = self.mutate_owner(self.source, "1", "31", b"DotNum=1", b"DotNum=4")
        self.error(lambda: ExistingIntegerNumeric(changed, self.schema, self.descriptor).check())
        cached = NativeAdapter(self.raw, self.source.family)
        self.owner(source=cached)["section"].one("DotNum").set_value(b"4")
        self.error(lambda: ExistingIntegerNumeric(cached, self.schema, self.descriptor).check())
        program = ExistingIntegerNumeric(self.source, self.schema, self.descriptor)
        program.source = NativeAdapter(self.raw, self.source.family)
        self.error(lambda: program.check(), "INVALID_INTEGER_NUMERIC_SOURCE")

    def test_non_numeric_original_and_wrong_original_pin_refused(self):
        self.error(lambda: self.program.apply([self.op(eid="21")]), "EXISTING_INTEGER_NUMERIC_KIND")
        operation = self.op(integer_digits=1, fractional_digits=4)
        candidate = self.candidate([operation])
        wrong = self.op(source=candidate)
        self.error(lambda: self.program.apply([wrong]), "EXISTING_INTEGER_NUMERIC_PIN")

    def test_saved_candidate_storage_scaling_binding_caption_limits_and_resource_tamper(self):
        operations = [self.op(integer_digits=1, fractional_digits=4),
                      self.op("7", "34", raw_minimum=-999, raw_maximum=999, integer_digits=3)]
        candidate = self.candidate(operations)
        for before, after in ((b"DotNum=4", b"DotNum=3"), (b"MemFmt=1", b"MemFmt=2"),
                              (b"MemLen=1", b"MemLen=2"), (b"GainValue=1.0", b"GainValue=2.0"),
                              (b"ReadVar={Link2}1@D0", b"ReadVar={Link2}1@D1"),
                              (b"FgColor=1193046", b"FgColor=1193047"),
                              (b"MinValue=-999", b"MinValue=-998"), (b"GoToScreenID=12", b"GoToScreenID=7")):
            body = candidate.envelope.body
            self.assertIn(before, body)
            changed = NativeAdapter(candidate.envelope.encode(body.replace(before, after, 1)), candidate.family)
            self.error(lambda: self.program.verify(changed, operations), "EXISTING_INTEGER_NUMERIC_PRESERVATION")
        self.error(lambda: self.program.verify(candidate), "EXISTING_INTEGER_NUMERIC_PRESERVATION")
        self.error(lambda: self.program.verify(None), "INVALID_INTEGER_NUMERIC_CANDIDATE")
        for component in ("thumbnail", "prefix", "resource"):
            thumbnail, prefix, body = candidate.envelope.thumbnail, candidate.envelope.prefix, candidate.envelope.body
            if component == "thumbnail":
                thumbnail = thumbnail[:10] + bytes([thumbnail[10] ^ 1]) + thumbnail[11:]
            elif component == "prefix":
                prefix = bytes([prefix[0] ^ 1]) + prefix[1:]
            else:
                body = body.replace(b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD001=NEUTRAL9", 1)
            changed = NativeAdapter(Envelope(thumbnail, prefix, body).encode(body), candidate.family)
            self.error(lambda: self.program.verify(changed, operations), "EXISTING_INTEGER_NUMERIC_PRESERVATION")

    def test_saved_reopen_replay_source_unchanged_and_order_invariant(self):
        operations = [self.op(integer_digits=1, fractional_digits=4),
                      self.op("7", "34", raw_minimum=-99, raw_maximum=99, integer_digits=2),
                      self.op("12", "139", integer_digits=2, fractional_digits=3)]
        output = self.program.apply(operations)
        self.assertEqual(output, self.program.apply(list(reversed(operations))))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "neutral_integer.dps"; path.write_bytes(output)
            candidate = NativeAdapter(path.read_bytes(), self.source.family)
            self.assertTrue(self.program.verify(candidate, operations))
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)


if __name__ == "__main__":
    unittest.main()
