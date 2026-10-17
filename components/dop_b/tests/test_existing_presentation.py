"""Neutral constructed presentation adversaries, never vendor/pixel evidence."""
from copy import deepcopy
import gzip
import struct
import tempfile
from pathlib import Path
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.existing_program import ExistingProgram
from universal_hmi.native.existing_presentation import ExistingPresentation, presentation_contract
from test_existing_program import existing_program_fixture, existing_schema, sha
from test_native import control_generation_fixture


def presentation_fixture():
    """All qualified kinds in an original three-page synthetic closed graph."""
    raw, _ = existing_program_fixture()
    source = NativeAdapter(raw, "delta_dopsoft2")
    library_raw, _ = control_generation_fixture()
    library = NativeAdapter(library_raw, "delta_dopsoft2")
    donors = _groups(library.document)[0]["elements"]
    # Append missing set-on/set-off/maintained shapes; keep asymmetric names,
    # states, page IDs and fake owner-looking bytes inside untouched SRAM.
    for index, eid in ((0, "61"), (1, "67"), (3, "71")):
        donor = donors[index]
        parts = deepcopy(library.document.sections[donor["start"]:donor["end"]])
        parts[0].one("nPartsID").set_value(eid.encode())
        source.document.sections.extend(parts)
    for page in _groups(source.document):
        page["section"].one("PanelSizeX").set_value(b"1024")
        page["section"].one("PanelSizeY").set_value(b"600")
        for owner in page["elements"]:
            for state in owner["states"]:
                value = int(state.one("Value").value)
                state.one("FgColor").set_value(str(0x123456 + value).encode())
                state.one("BgColor").set_value(str(0x654321 + value).encode())
            if owner["id"] == "11":
                owner["states"][0].one("FontSize0").set_value(b"0")
                owner["states"][0].one("FontRatio0").set_value(b"48")
            if owner["id"] in {"31", "34"}:
                # This is preservation of an existing signed fractional shape,
                # not qualification of numeric editing or a signed donor.
                owner["section"].one("MemFmt").set_value(b"1")
                owner["section"].one("DotNum").set_value(b"1")
                if owner["id"] == "34":
                    owner["section"].one("MinValue").set_value(b"-200.1")
                    owner["section"].one("MaxValue").set_value(b"345.6")
    body = source.document.bytes()
    raw = source.envelope.encode(body)
    descriptor = {"qualified": True, "contract_version": 1, "mode": "variable_scalar_records_v1",
                  "source_sha256": sha(raw), "family": "delta_dopsoft2", "model_id": 2953863504,
                  "editor_version": "4.00.07.04", "authority_sha256": sha(b"SYNTHETIC PRESENTATION AUTHORITY")}
    return raw, existing_schema(raw), descriptor


class ExistingPresentationTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema, self.descriptor = presentation_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = ExistingPresentation(self.source, self.schema, self.descriptor)

    def owner(self, sid="1", eid="11", source=None):
        return next(o for p in _groups((source or self.source).document) if p["id"] == sid
                    for o in p["elements"] if o["id"] == eid)

    def op(self, sid="1", eid="11", source=None, **fields):
        source = source or self.source
        owner = self.owner(sid, eid, source)
        return {"op": "set_existing_presentation", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])), **fields}

    def state(self, value="0", sid="1", eid="11", source=None, **fields):
        state = next(s for s in self.owner(sid, eid, source)["states"] if s.one("Value").value == value.encode())
        return {"value": value, "state_sha256": sha(state.bytes()), **fields}

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def candidate(self, operations):
        return NativeAdapter(self.program.apply(operations), self.source.family)

    def mutated(self, source, before, after):
        self.assertIn(before, source.envelope.body)
        return NativeAdapter(source.envelope.encode(source.envelope.body.replace(before, after, 1)), source.family)

    def reprogram(self, source):
        descriptor = deepcopy(self.descriptor); descriptor["source_sha256"] = sha(source.original)
        return ExistingPresentation(source, existing_schema(source.original), descriptor)

    def test_noop_and_explicit_equal_scalars_preserve_complete_file(self):
        self.assertTrue(self.program.check())
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source))
        op = self.op(geometry={"x": 10, "y": 10, "width": 30, "height": 20})
        self.assertEqual(self.program.apply([op]), self.raw)
        self.assertTrue(self.program.verify(self.source, [op]))
        envelope = self.source.envelope
        payload = (envelope.prefix + envelope.body).translate(bytes(i ^ 0x64 for i in range(256)))
        alternate = NativeAdapter(envelope.thumbnail + gzip.compress(payload, mtime=9), self.source.family)
        self.assertNotEqual(alternate.original, self.raw)
        self.error(lambda: self.program.verify(alternate, [op]), "EXISTING_PRESENTATION_PRESERVATION")

    def test_geometry_and_scalar_digit_growth_shrink_independent_expected_restore(self):
        operations = [self.op(geometry={"x": 123, "y": 207, "width": 100, "height": 300},
                              states=[self.state(font_size=24, font_ratio=200, font_color=0xFFFFFF)]),
                      self.op("1", "31", visual={"native_style": 0, "border_color": 12345},
                              states=[self.state(sid="1", eid="31", surface_color=1, font_color=0)]),
                      self.op("12", "71", visual={"native_style": 2},
                              states=[self.state("1", "12", "71", surface_color=0xFFFFFF, font_ratio=33)])]
        candidate = self.candidate(operations)
        self.assertTrue(self.program.verify(candidate, operations))
        expected = self.program.expected_body(operations)
        self.assertEqual(candidate.envelope.body, expected)
        self.assertNotEqual(len(expected), len(self.source.envelope.body))
        self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(), len(expected))
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)
        self.assertEqual(candidate.document.tail, self.source.document.tail)
        old = self.owner("1", "31")["section"]
        new = self.owner("1", "31", candidate)["section"]
        for key in ("MemFmt", "MemLen", "IntNum", "DotNum", "ReadVar", "GainValue", "OffsetValue"):
            self.assertEqual(new.one(key).raw, old.one(key).raw)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "neutral_candidate.dps"
            path.write_bytes(candidate.original)
            reopened = NativeAdapter(path.read_bytes(), self.source.family)
            self.assertTrue(self.program.verify(reopened, operations))
        # The expected path must not invoke the mutable serializer/apply path.
        self.program.apply = lambda _: self.fail("expected_body invoked apply")
        self.assertEqual(self.program.expected_body(operations), expected)

    def test_all_qualified_types_map_surface_to_exact_source_role(self):
        targets = [("12", "61"), ("12", "67"), ("1", "21"), ("12", "71"),
                   ("7", "41"), ("7", "23"), ("1", "31"), ("7", "34")]
        for sid, eid in targets:
            with self.subTest(eid=eid):
                old = self.owner(sid, eid)
                numeric = old["section"].one("Type").value in {b"5", b"6"}
                operations = [self.op(sid, eid, visual={"native_style": 0},
                    states=[self.state(sid=sid, eid=eid, surface_color=0x112233, font_color=0x445566)])]
                saved = self.owner(sid, eid, self.candidate(operations))["states"][0]
                changed, kept = ("BgColor", "FgColor") if numeric else ("FgColor", "BgColor")
                self.assertEqual(saved.one(changed).value, b"1122867")
                self.assertEqual(saved.one(kept).raw, old["states"][0].one(kept).raw)
                self.assertEqual(saved.one("FontColor").value, b"4478310")
                for record in old["states"][0].records:
                    if record.key not in {changed, "FontColor"}:
                        self.assertEqual(saved.one(record.key).raw, record.raw)

    def test_asymmetric_two_states_and_all_native_style_values(self):
        for style in (0, 1, 2, 3):
            for sid, eid in (("1", "21"), ("1", "31")):
                operation = self.op(sid, eid, visual={"native_style": style})
                saved = self.owner(sid, eid, self.candidate([operation]))
                self.assertEqual(saved["section"].one("Style").value, str(style).encode())
        operation = self.op("1", "21", visual={"native_style": 1}, states=[
            self.state("1", "1", "21", surface_color=0xA1B2C3),
            self.state("0", "1", "21", surface_color=0x123456)])
        saved = self.owner("1", "21", self.candidate([operation]))
        self.assertEqual([s.one("FgColor").value for s in saved["states"]], [b"1193046", b"10597059"])
        self.assertEqual([s.one("BgColor").raw for s in saved["states"]],
                         [s.one("BgColor").raw for s in self.owner("1", "21")["states"]])

    def test_font_size_ratio_exact_native_members_and_old_zero_48_preserved(self):
        original = self.owner()["states"][0]
        operation = self.op(states=[self.state(font_color=0x1234)])
        saved = self.owner(source=self.candidate([operation]))["states"][0]
        self.assertEqual(saved.one("FontSize0").raw, original.one("FontSize0").raw)
        self.assertEqual(saved.one("FontRatio0").raw, original.one("FontRatio0").raw)
        for size in (8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 48, 64, 72):
            operation = self.op(states=[self.state(font_size=size)])
            saved = self.owner(source=self.candidate([operation]))["states"][0]
            self.assertEqual(saved.one("FontSize0").value, str(size).encode())
        for ratio in (33, 50, 100, 150, 200):
            operation = self.op(states=[self.state(font_ratio=ratio)])
            saved = self.owner(source=self.candidate([operation]))["states"][0]
            self.assertEqual(saved.one("FontRatio0").value, str(ratio).encode())
        for field, invalid in (("font_size", (0, 9, 15, 96, 128, 224, 255)),
                               ("font_ratio", (0, 48, 99, 101, 255))):
            for value in invalid:
                self.error(lambda: self.program.apply([self.op(states=[self.state(**{field: value})])]))

    def test_text_only_and_fixed_border_roles_reject_unsupported_surface(self):
        for sid, eid in (("1", "21"), ("7", "23"), ("1", "31"), ("7", "34")):
            operation = self.op(sid, eid, visual={"native_style": 3},
                                states=[self.state(sid=sid, eid=eid, surface_color=1)])
            self.error(lambda: self.program.apply([operation]), "UNQUALIFIED_PRESENTATION_ROLE")
        for sid, eid in (("1", "21"), ("7", "23"), ("7", "41")):
            self.error(lambda: self.program.apply([self.op(sid, eid, visual={"native_style": 0, "border_color": 1})]),
                       "UNQUALIFIED_PRESENTATION_ROLE")
        for style in (1, 2, 3):
            self.error(lambda: self.program.apply([self.op("1", "31", visual={"native_style": style, "border_color": 1})]),
                       "UNQUALIFIED_PRESENTATION_ROLE")
        self.error(lambda: self.program.apply([self.op(visual={"native_style": 3})]), "UNQUALIFIED_PRESENTATION_ROLE")
        self.error(lambda: self.program.apply([self.op(states=[self.state(surface_color=1)])]), "UNQUALIFIED_PRESENTATION_ROLE")
        text = self.op("1", "21", visual={"native_style": 3}, states=[self.state(sid="1", eid="21", font_color=1)])
        self.assertTrue(self.program.verify(self.candidate([text]), [text]))
        for value in (-1, 4, 16, True, "flat", 0.0):
            self.error(lambda: self.program.apply([self.op("1", "21", visual={"native_style": value})]))

    def test_signed_fractional_input_behavior_storage_keypad_and_caption_untouched(self):
        operation = self.op("7", "34", visual={"native_style": 0, "border_color": 0xABCDEF},
                            geometry={"x": 600, "y": 400, "width": 240, "height": 90},
                            states=[self.state(sid="7", eid="34", font_size=28, font_ratio=150, surface_color=0xFFFFFF)])
        original = self.owner("7", "34")
        saved = self.owner("7", "34", self.candidate([operation]))
        mutable = {"X", "Y", "Width", "Height", "Style", "BorderColor"}
        for record in original["section"].records:
            if record.key not in mutable:
                self.assertEqual(saved["section"].one(record.key).raw, record.raw)
        for key in ("MemFmt", "DotNum", "MinValue", "MaxValue", "UseCustKeypad", "TriggerVar", "WriteVar"):
            self.assertEqual(saved["section"].one(key).raw, original["section"].one(key).raw)
        self.assertEqual(saved["states"][0].one("wTextLen0").raw, original["states"][0].one("wTextLen0").raw)

    def test_duplicate_owners_states_and_unapproved_fields_are_refused(self):
        operation = self.op(states=[self.state(font_color=1)])
        self.error(lambda: self.program.apply([operation, deepcopy(operation)]), "DUPLICATE_PRESENTATION_OWNER")
        duplicate = self.op("1", "21", states=[self.state(sid="1", eid="21", font_color=1)] * 2)
        self.error(lambda: self.program.apply([duplicate]), "DUPLICATE_PRESENTATION_STATE")
        for field in ("caption", "address", "numeric", "Type", "SubType", "macro", "script", "state_order"):
            wrong = deepcopy(operation); wrong[field] = "changed"
            self.error(lambda: self.program.apply([wrong]), "INVALID_PRESENTATION_OPERATION")
        for key in ("caption", "FontName0", "Value", "ReadVar", "wTextLen0", "opacity"):
            wrong = deepcopy(operation); wrong["states"][0][key] = "changed"
            self.error(lambda: self.program.apply([wrong]), "INVALID_PRESENTATION_STATE")
        self.error(lambda: self.program.apply([self.op(visual={"native_style": 1, "flat": True})]), "INVALID_PRESENTATION_VISUAL")

    def test_pins_and_exact_source_state_value_selection(self):
        for field in ("owner_sha256",):
            for value in (None, [], {}, True, "0" * 64, "A" * 64):
                wrong = self.op(states=[self.state(font_color=1)]); wrong[field] = value
                self.error(lambda: self.program.apply([wrong]), "EXISTING_PRESENTATION_PIN")
        for value in (None, [], {}, True, "0" * 64):
            wrong = self.op(states=[self.state(font_color=1)]); wrong["states"][0]["state_sha256"] = value
            self.error(lambda: self.program.apply([wrong]), "EXISTING_PRESENTATION_PIN")
        wrong = self.op("1", "21", states=[self.state(sid="1", eid="21", font_color=1)])
        wrong["states"][0]["value"] = "1"
        self.error(lambda: self.program.apply([wrong]), "EXISTING_PRESENTATION_PIN")
        for value in (None, [], {}, True, 0, "00", "-1", "2", " 0", "０"):
            wrong = self.op(states=[self.state(font_color=1)]); wrong["states"][0]["value"] = value
            self.error(lambda: self.program.apply([wrong]))

    def test_typed_malformed_deep_cyclic_and_empty_operations(self):
        operation = self.op(states=[self.state(font_color=1)])
        for value in (None, {}, True, "", 1):
            self.error(lambda: self.program.apply(value), "INVALID_OPERATIONS")
        for field in ("op", "screen_id", "element_id", "geometry", "visual", "states"):
            for value in (None, [], {}, True, 0, 1.5, ""):
                wrong = deepcopy(operation); wrong[field] = value
                self.error(lambda: self.program.apply([wrong]))
        cycle = []; cycle.append(cycle)
        deep = []; holder = deep
        for _ in range(12):
            holder.append([]); holder = holder[0]
        for value in (cycle, deep, [operation] * 4097):
            self.error(lambda: self.program.apply(value))
        for wrong in (self.op(), self.op(states=[]), self.op(visual={}), self.op(geometry={}),
                      self.op(states=[self.state()])):
            self.error(lambda: self.program.apply([wrong]))

    def test_geometry_numeric_limits_colors_and_boolean_refusal(self):
        for field in ("x", "y", "width", "height"):
            for value in (-1, 65536, True, 1.5, "1", None, [], {}):
                geometry = {"x": 10, "y": 10, "width": 30, "height": 20}; geometry[field] = value
                self.error(lambda: self.program.apply([self.op(geometry=geometry)]))
        for geometry in ({"x": 0, "y": 0, "width": 0, "height": 10},
                         {"x": 1000, "y": 0, "width": 30, "height": 10},
                         {"x": 0, "y": 599, "width": 30, "height": 2}):
            self.error(lambda: self.program.apply([self.op(geometry=geometry)]))
        edge = self.op(geometry={"x": 1023, "y": 599, "width": 1, "height": 1})
        self.assertTrue(self.program.verify(self.candidate([edge]), [edge]))
        for field in ("font_color", "surface_color", "font_size", "font_ratio"):
            for value in (-1, 0x1000000, True, "1", [], {}):
                self.error(lambda: self.program.apply([self.op("1", "21", states=[self.state(sid="1", eid="21", **{field: value})])]))

    def test_descriptor_exact_keys_copy_freshness_and_graph_independence(self):
        for value in (None, [], {}, True, 1, "descriptor"):
            self.error(lambda: presentation_contract(value))
        for field, value in (("qualified", 1), ("contract_version", True), ("mode", "preserved_layout"),
                             ("family", "delta_diascreen"), ("model_id", "2953863504"),
                             ("editor_version", "4.00.07.05"), ("source_sha256", "bad"),
                             ("authority_sha256", "A" * 64), ("extra", 0)):
            descriptor = deepcopy(self.descriptor); descriptor[field] = value
            self.error(lambda: ExistingPresentation(self.source, self.schema, descriptor))
        descriptor = deepcopy(self.descriptor)
        program = ExistingPresentation(self.source, self.schema, descriptor)
        descriptor["source_sha256"] = "0" * 64
        self.assertTrue(program.check())
        for field, value in (("source_sha256", "0" * 64), ("authority_sha256", "0" * 64),
                             ("qualified", False), ("extra", None), ("model_id", [])):
            program = ExistingPresentation(self.source, self.schema, self.descriptor); program.contract[field] = value
            self.error(lambda: program.apply([]), "UNQUALIFIED_EXISTING_PRESENTATION")
        program.contract = None
        self.error(lambda: program.check(), "UNQUALIFIED_EXISTING_PRESENTATION")
        descriptor = deepcopy(self.descriptor); descriptor["source_sha256"] = "0" * 64
        self.error(lambda: ExistingPresentation(self.source, self.schema, descriptor).check(), "INVALID_PRESENTATION_SOURCE")
        self.assertTrue(ExistingProgram(self.source, self.schema).check())
        with self.assertRaises(HmiError):
            ExistingProgram(self.source, self.schema).apply([self.op(states=[self.state(font_color=1)])])

    def test_source_graph_changed_and_rehashed_unsafe_native_fields_refused(self):
        changed = self.mutated(self.source, b"Style=0", b"Style=1")
        self.error(lambda: ExistingPresentation(changed, self.schema, self.descriptor).check())
        for before, after in ((b"GroupID=0", b"GroupID=1"),
                              (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnknown=1\r\n"),
                              (b"BeforeExecMacroLen=0\r\n", b"BeforeExecMacroLen=2\r\n\r\n"),
                              (b"Type=10", b"Type=\xff"),
                              (b"FgColor=1193046", b"FgColor=1193046\r\nFgColor=1"),
                              (b"UsePictureCoord=0", b"UsePictureCoord=1")):
            self.error(lambda: self.reprogram(self.mutated(self.source, before, after)).apply([]))
        for before, after in ((b"Style=0", b"Style=16"),
                              (b"FontColor=0", b"FontColor=+0"),
                              (b"FontColor=0", b"FontColor=\xff")):
            source = self.mutated(self.source, before, after)
            # Style is the literal's immutable field: only numeric/button role
            # mapping requires a qualified style, while a changed font target
            # must independently prove canonical scalar framing.
            if before.startswith(b"Style"):
                target = next(o for p in _groups(source.document) for o in p["elements"] if o["section"].one("Type").value == b"1")
                target["section"].one("Style").set_value(b"16")
                source = NativeAdapter(source.envelope.encode(source.document.bytes()), source.family)
                operation = self.op("1", "21", source, states=[self.state(sid="1", eid="21", source=source, font_color=1)])
            else:
                operation = self.op(source=source, states=[self.state(source=source, font_color=1)])
            self.error(lambda: self.reprogram(source).apply([operation]))

    def test_candidate_neighbor_numeric_caption_address_resource_identity_tamper(self):
        operations = [self.op(states=[self.state(font_color=1)])]
        candidate = self.candidate(operations)
        for before, after in ((b"X=10", b"X=11"), (b"nPartsID=21", b"nPartsID=22"),
                              (b"MemFmt=1", b"MemFmt=2"), (b"DotNum=1", b"DotNum=0"),
                              (b"MinValue=-200.1", b"MinValue=-200.2"),
                              (b"ReadVar={Link2}1@D0", b"ReadVar={Link2}1@D1"),
                              (b"Value=1", b"Value=2"), (b"GoToScreenID=12", b"GoToScreenID=7"),
                              (b"TagLinkCount=1", b"TagLinkCount=0"),
                              (b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD001=NEUTRAL9")):
            self.error(lambda: self.program.verify(self.mutated(candidate, before, after), operations),
                       "EXISTING_PRESENTATION_PRESERVATION")
        changed = NativeAdapter(candidate.original, candidate.family)
        self.owner(source=changed)["states"][0].one("wTextLen0").set_text("Unapproved caption")
        changed = NativeAdapter(changed.envelope.encode(changed.document.bytes()), changed.family)
        self.error(lambda: self.program.verify(changed, operations), "EXISTING_PRESENTATION_PRESERVATION")
        self.error(lambda: self.program.verify(candidate), "EXISTING_PRESENTATION_PRESERVATION")
        self.error(lambda: self.program.verify(None, operations), "INVALID_PRESENTATION_CANDIDATE")
        for component in ("thumbnail", "prefix"):
            thumbnail, prefix = candidate.envelope.thumbnail, candidate.envelope.prefix
            if component == "thumbnail":
                data = bytearray(thumbnail); data[10] ^= 1; thumbnail = bytes(data)
            else:
                prefix = bytes([prefix[0] ^ 1]) + prefix[1:]
            changed = NativeAdapter(Envelope(thumbnail, prefix, candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
            self.error(lambda: self.program.verify(changed, operations), "EXISTING_PRESENTATION_PRESERVATION")


if __name__ == "__main__":
    unittest.main()
