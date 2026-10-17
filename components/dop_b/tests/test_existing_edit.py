"""Neutral original-source composition tests, not vendor/pixel acceptance."""
from copy import deepcopy
import gzip
import tempfile
from pathlib import Path
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.existing_edit import ExistingEdit
from universal_hmi.native.records import Record
from test_existing_background import dib, png
from test_existing_presentation import presentation_fixture
from test_existing_program import existing_schema, existing_tail, sha


WIDTH, HEIGHT = 128, 96
FRAME_SIZE = 40 + WIDTH * HEIGHT * 4


def page_png(top=b"\xff\x00\x00", bottom=b"\x00\x00\xff"):
    """Explicit red/blue asymmetric rows; no native encoder is called."""
    return png(b"".join(b"\0" + (top if y < HEIGHT // 2 else bottom) * WIDTH
                        for y in range(HEIGHT)), WIDTH, HEIGHT)


def existing_edit_fixture():
    """Synthetic three-page graph with existing controls and fixed backgrounds."""
    raw, _, presentation = presentation_fixture()
    source = NativeAdapter(raw, "delta_dopsoft2")
    frames = [dib(WIDTH, HEIGHT, b"\x00\x00\x00\xff" * (WIDTH * HEIGHT)),
              dib(WIDTH, HEIGHT, b"\x55\x55\x55\xff" * (WIDTH * HEIGHT)),
              dib(WIDTH, HEIGHT, b"\x11\x22\x33\xff" * (WIDTH * HEIGHT))]
    for index, page in enumerate(_groups(source.document)):
        page["section"].one("PanelSizeX").set_value(str(WIDTH).encode())
        page["section"].one("PanelSizeY").set_value(str(HEIGHT).encode())
        value = str(index * FRAME_SIZE).encode()
        page["section"].records.append(Record(b"PictureOffset=" + value + b"\r\n",
                                               "PictureOffset", value))
    source.document.tail = existing_tail(background=b"".join(frames))
    raw = source.envelope.encode(source.document.bytes())
    presentation["source_sha256"] = sha(raw)
    background = {**presentation, "mode": "fixed_opaque_page_background_v1",
                  "authority_sha256": sha(b"SYNTHETIC BACKGROUND AUTHORITY")}
    return raw, existing_schema(raw), presentation, background


class ExistingEditTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema, self.presentation, self.background = existing_edit_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = ExistingEdit(self.source, self.schema, self.presentation, self.background)

    def owner(self, sid="1", eid="11", source=None):
        return next(o for p in _groups((source or self.source).document) if p["id"] == sid
                    for o in p["elements"] if o["id"] == eid)

    def extent(self, sid, eid, source=None):
        source = source or self.source
        owner = self.owner(sid, eid, source)
        return b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])

    def delete(self, sid="1", eid="11", source=None):
        return {"op": "delete_literal", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(self.extent(sid, eid, source))}

    def present(self, sid="1", eid="21", source=None, **fields):
        return {"op": "set_existing_presentation", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(self.extent(sid, eid, source)), **fields}

    def state(self, sid="1", eid="21", value="0", source=None, **fields):
        state = next(s for s in self.owner(sid, eid, source)["states"]
                     if s.one("Value").value == value.encode())
        return {"value": value, "state_sha256": sha(state.bytes()), **fields}

    def frame(self, sid="1", asset=None):
        inventory = next(f for f in self.program._background.frame_inventory()
                         if f["screen_id"] == sid)
        asset = page_png() if asset is None else asset
        digest = sha(asset)
        return {"op": "set_existing_background", "screen_id": sid,
                "frame_sha256": inventory["frame_sha256"], "asset_sha256": digest}, {digest: asset}

    def mixed(self):
        first, assets = self.frame()
        last, more = self.frame("12", page_png(b"\x00\xff\x00", b"\xff\xff\x00"))
        assets.update(more)
        return [self.delete(), self.delete("7", "29"), self.delete("12", "53"),
                self.present(geometry={"x": 100, "y": 2, "width": 20, "height": 22},
                             visual={"native_style": 0}, states=[
                                 self.state(surface_color=1, font_color=0xFFFFFF, font_size=24, font_ratio=150),
                                 self.state(value="1", surface_color=0xAABBCC)]),
                self.present("1", "31", visual={"native_style": 0, "border_color": 0xFEDCBA},
                             states=[self.state("1", "31", surface_color=1)]),
                self.present("12", "47", states=[self.state("12", "47", font_color=42, font_ratio=33)]),
                first, last], assets

    def candidate(self, operations, assets=None):
        return NativeAdapter(self.program.apply(operations, assets), self.source.family)

    def error(self, function, code=None):
        with self.assertRaises(HmiError) as raised:
            function()
        if code:
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def mutate(self, candidate, before, after):
        self.assertIn(before, candidate.envelope.body)
        return NativeAdapter(candidate.envelope.encode(candidate.envelope.body.replace(before, after, 1)),
                             candidate.family)

    def test_three_page_mixed_original_pins_fields_and_survivors(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        self.assertTrue(self.program.verify(candidate, operations, assets))
        self.assertEqual(candidate.envelope.body, self.program.expected_body(operations, assets))
        self.assertEqual([p["id"] for p in _groups(candidate.document)], ["1", "7", "12"])
        deleted, changed = {"11", "29", "53"}, {"21", "31", "47"}
        for old, saved in zip(_groups(self.source.document), _groups(candidate.document)):
            self.assertEqual(old["section"].bytes(), saved["section"].bytes())
            self.assertEqual([o["id"] for o in saved["elements"]],
                             [o["id"] for o in old["elements"] if o["id"] not in deleted])
            for owner in old["elements"]:
                if owner["id"] not in deleted | changed:
                    self.assertEqual(self.extent(old["id"], owner["id"]),
                                     self.extent(saved["id"], owner["id"], candidate))
        momentary = self.owner("1", "21", candidate)
        self.assertEqual(momentary["section"].one("X").value, b"100")
        self.assertEqual(momentary["states"][0].one("FgColor").value, b"1")
        self.assertEqual(momentary["states"][1].one("FgColor").value, b"11189196")
        self.assertEqual(momentary["states"][0].one("BgColor").raw,
                         self.owner("1", "21")["states"][0].one("BgColor").raw)
        numeric = self.owner("1", "31", candidate)
        self.assertEqual(numeric["states"][0].one("BgColor").value, b"1")
        self.assertEqual(numeric["states"][0].one("FgColor").raw,
                         self.owner("1", "31")["states"][0].one("FgColor").raw)
        for key in ("MemFmt", "DotNum", "ReadVar", "WriteVar", "GainValue", "OffsetValue"):
            self.assertEqual(numeric["section"].one(key).raw, self.owner("1", "31")["section"].one(key).raw)
        self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)

    def test_background_asymmetric_pixels_after_earlier_deletions_and_scalar_growth(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        # Tail offsets remain unchanged even though all its BODY coordinates moved.
        marker = b"[Background]\r\nSize=" + str(FRAME_SIZE * 3).encode() + b"\r\n"
        offset = candidate.document.tail.index(marker) + len(marker)
        first = candidate.document.tail[offset:offset + FRAME_SIZE]
        middle = candidate.document.tail[offset + FRAME_SIZE:offset + 2 * FRAME_SIZE]
        last = candidate.document.tail[offset + 2 * FRAME_SIZE:offset + 3 * FRAME_SIZE]
        self.assertEqual(first[40:44], bytes.fromhex("ff0000ff"))  # bottom blue
        self.assertEqual(first[-4:], bytes.fromhex("0000ffff"))  # top red
        self.assertEqual(last[40:44], bytes.fromhex("00ffffff"))  # bottom yellow
        self.assertEqual(last[-4:], bytes.fromhex("00ff00ff"))  # top green
        old = self.source.document.tail
        self.assertEqual(middle, old[offset + FRAME_SIZE:offset + 2 * FRAME_SIZE])
        self.assertEqual(candidate.document.tail[:offset], old[:offset])
        self.assertEqual(candidate.document.tail[offset + 3 * FRAME_SIZE:], old[offset + 3 * FRAME_SIZE:])

    def test_independent_raw_expectation_and_full_source_restoration(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        spans = self.program.spans(operations, assets)
        self.assertTrue(any(raw == b"" for _, _, raw in spans))
        self.assertTrue(any(len(raw) > end - start for start, end, raw in spans))
        self.assertTrue(any(0 < len(raw) < end - start for start, end, raw in spans))
        expected, restored, cursor, saved_cursor, delta = [], [], 0, 0, 0
        for start, end, raw in spans:
            expected.extend((self.source.envelope.body[cursor:start], raw)); cursor = end
            saved_start = start + delta
            restored.extend((candidate.envelope.body[saved_cursor:saved_start], self.source.envelope.body[start:end]))
            saved_cursor = saved_start + len(raw)
            delta += len(raw) - (end - start)
        expected.append(self.source.envelope.body[cursor:])
        restored.append(candidate.envelope.body[saved_cursor:])
        self.assertEqual(b"".join(expected), candidate.envelope.body)
        self.assertEqual(b"".join(restored), self.source.envelope.body)
        # expected_body does not depend on the mutator entry point.
        self.program.apply = lambda *args: self.fail("Expectation invoked mutation")
        self.assertEqual(self.program.expected_body(operations, assets), candidate.envelope.body)

    def test_operation_order_cannot_rebase_pins_or_change_output(self):
        operations, assets = self.mixed()
        expected = self.program.apply(operations, assets)
        for order in (list(reversed(operations)), operations[3:] + operations[:3],
                      operations[::2] + operations[1::2]):
            self.assertEqual(self.program.apply(order, assets), expected)

    def test_first_middle_last_deletions_and_presentation_on_final_owner(self):
        for sid, eid in (("1", "11"), ("1", "13"), ("12", "53")):
            with self.subTest(sid=sid, eid=eid):
                operation, assets = self.frame("7")
                operations = [self.present("12", "71", geometry={"x": 101, "y": 11, "width": 26, "height": 21}),
                              self.delete(sid, eid), operation]
                candidate = self.candidate(operations, assets)
                self.assertEqual(self.owner("12", "71", candidate)["section"].one("X").value, b"101")
                self.assertNotIn(eid, [o["id"] for p in _groups(candidate.document) for o in p["elements"]])

    def test_noop_complete_file_and_same_requested_pixels_preserved(self):
        self.assertTrue(self.program.check())
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source))
        noop, assets = self.frame(asset=page_png(bytes(3), bytes(3)))
        operations = [noop, self.present(geometry={"x": 10, "y": 10, "width": 30, "height": 20})]
        self.assertEqual(self.program.spans(operations, assets), [])
        self.assertEqual(self.program.apply(operations, assets), self.raw)
        compressed = self.source.envelope.thumbnail + gzip.compress(
            bytes(v ^ 0x64 for v in self.source.envelope.prefix + self.source.envelope.body), mtime=73)
        self.assertNotEqual(compressed, self.raw)
        self.error(lambda: self.program.verify(NativeAdapter(compressed, self.source.family), operations, assets),
                   "EXISTING_EDIT_PRESERVATION")

    def test_delete_presentation_conflict_even_when_presentation_is_noop(self):
        for request in (self.present(eid="11", states=[self.state(eid="11", font_color=1)]),
                        self.present(eid="11", geometry={"x": 10, "y": 10, "width": 30, "height": 20})):
            for operations in ([self.delete(), request], [request, self.delete()]):
                self.error(lambda: self.program.apply(operations), "EXISTING_EDIT_CONFLICT")

    def test_duplicate_native_targets_remain_refused(self):
        for operation, assets, code in ((self.delete(), {}, "DUPLICATE_LITERAL_DELETION"),
            (self.present(states=[self.state(font_color=7)]), {}, "DUPLICATE_PRESENTATION_OWNER"),
            (*self.frame(), "DUPLICATE_BACKGROUND_PAGE")):
            self.error(lambda: self.program.apply([operation, deepcopy(operation)], assets), code)

    def test_typed_malformed_operations_and_asset_coverage_before_output(self):
        for operations in (None, {}, "", [None], [True], [[]], [{"op": []}], [{"op": {}}],
                           [{"op": "set_text"}], [self.delete()] * 4097):
            self.error(lambda: self.program.apply(operations))
        cyclic = []; cyclic.append(cyclic)
        self.error(lambda: self.program.apply(cyclic))
        operation, assets = self.frame()
        for malformed in ([], None, {"x": b"png"}, {next(iter(assets)): bytearray(next(iter(assets.values())))},
                          {sha(b"changed"): next(iter(assets.values()))}):
            if malformed is None:
                # Omitted assets mean {}, which cannot satisfy this operation.
                self.error(lambda: self.program.apply([operation], malformed))
            else:
                self.error(lambda: self.program.apply([operation], malformed))
        self.error(lambda: self.program.apply([], assets), "BACKGROUND_ASSET_COVERAGE")
        self.error(lambda: self.program.apply([operation], {**assets, sha(b"bad"): b"bad"}), "BACKGROUND_ASSET_COVERAGE")
        wrong = png(b"\0\xff\x00\x00", 1, 1)
        bad, bad_assets = self.frame(asset=wrong)
        self.error(lambda: self.program.apply([bad], bad_assets), "PNG_CANVAS")

    def test_original_pins_not_rebased_candidate_owner_hashes(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        request = self.present(source=candidate, states=[self.state(source=candidate, font_color=3)])
        self.error(lambda: self.program.apply([request]), "EXISTING_PRESENTATION_PIN")
        bad, used = self.frame()
        bad["frame_sha256"] = sha(b"unrelated")
        self.error(lambda: self.program.apply([bad], used), "BACKGROUND_FRAME_PIN")
        for bad in (self.delete(), self.present(states=[self.state(font_color=3)])):
            bad["owner_sha256"] = "0" * 64
            self.error(lambda: self.program.apply([bad]))

    def test_descriptor_adapter_and_source_freshness(self):
        for primitive in (self.program._graph, self.program._presentation, self.program._background):
            program = ExistingEdit(self.source, self.schema, self.presentation, self.background)
            member = (program._graph if isinstance(primitive, type(program._graph)) else
                      program._presentation if isinstance(primitive, type(program._presentation)) else program._background)
            member.contract["authority_sha256"] = "0" * 64
            self.error(lambda: program.apply([]))
        program = ExistingEdit(self.source, self.schema, self.presentation, self.background)
        program.source = NativeAdapter(self.raw, self.source.family)
        self.error(lambda: program.check(), "INVALID_EXISTING_EDIT_SOURCE")
        changed = self.mutate(self.source, b"FgColor=1193046", b"FgColor=1193047")
        self.error(lambda: ExistingEdit(changed, self.schema, self.presentation, self.background).check())
        cached = NativeAdapter(self.raw, self.source.family)
        cached.document.sections[0].records[0].set_value(b"0")
        self.error(lambda: ExistingEdit(cached, self.schema, self.presentation, self.background).check())

    def test_candidate_tamper_outside_approved_spans_is_rejected(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        for before, after in ((b"nPartsID=21", b"nPartsID=22"), (b"X=100", b"X=99"),
                              (b"MemFmt=1", b"MemFmt=2"), (b"DotNum=1", b"DotNum=0"),
                              (b"MinValue=-200.1", b"MinValue=-200.2"),
                              (b"ReadVar={Link2}1@D0", b"ReadVar={Link2}1@D1"),
                              (b"GoToScreenID=12", b"GoToScreenID=7"),
                              (b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD001=NEUTRAL9"),
                              (b"PictureOffset=0", b"PictureOffset=1")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after), operations, assets),
                       "EXISTING_EDIT_PRESERVATION")
        changed = NativeAdapter(candidate.original, candidate.family)
        self.owner("12", "47", changed)["states"][0].one("wTextLen0").set_text("Unapproved caption")
        changed = NativeAdapter(changed.envelope.encode(changed.document.bytes()), changed.family)
        self.error(lambda: self.program.verify(changed, operations, assets), "EXISTING_EDIT_PRESERVATION")
        self.error(lambda: self.program.verify(candidate), "EXISTING_EDIT_PRESERVATION")
        self.error(lambda: self.program.verify(None, operations, assets), "INVALID_EXISTING_EDIT_CANDIDATE")

    def test_candidate_deleted_owner_resurrection_reordering_and_background_tamper(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        changed = NativeAdapter(candidate.original, candidate.family)
        original = self.owner()
        old_parts = deepcopy(self.source.document.sections[original["start"]:original["end"]])
        changed.document.sections[3:3] = old_parts
        self.error(lambda: self.program.verify(NativeAdapter(changed.envelope.encode(changed.document.bytes()), changed.family),
                                               operations, assets), "EXISTING_EDIT_PRESERVATION")
        for changed_kind in ("order", "background", "thumbnail", "prefix"):
            thumbnail, prefix, body = candidate.envelope.thumbnail, candidate.envelope.prefix, candidate.envelope.body
            if changed_kind == "order":
                changed = NativeAdapter(candidate.original, candidate.family)
                owner = self.owner("12", "47", changed)
                parts = changed.document.sections[owner["start"]:owner["end"]]
                del changed.document.sections[owner["start"]:owner["end"]]
                changed.document.sections.extend(parts); body = changed.document.bytes()
            elif changed_kind == "background":
                marker = b"[Background]\r\nSize=" + str(FRAME_SIZE * 3).encode() + b"\r\n"
                frame_start = body.index(marker) + len(marker)
                # Corrupt the untouched middle frame, after length-changing
                # mutations moved its BODY offset. This is actual pixel data.
                body = bytearray(body); body[frame_start + FRAME_SIZE + 40] ^= 1; body = bytes(body)
            elif changed_kind == "thumbnail":
                thumbnail = thumbnail[:10] + bytes([thumbnail[10] ^ 1]) + thumbnail[11:]
            else:
                prefix = bytes([prefix[0] ^ 1]) + prefix[1:]
            altered = NativeAdapter(Envelope(thumbnail, prefix, body).encode(body), candidate.family)
            self.error(lambda: self.program.verify(altered, operations, assets), "EXISTING_EDIT_PRESERVATION")

    def test_saved_reopen_replay_and_source_unchanged(self):
        operations, assets = self.mixed()
        output = self.program.apply(operations, assets)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "neutral.dps"
            path.write_bytes(output)
            reopened = NativeAdapter(path.read_bytes(), self.source.family)
            self.assertTrue(self.program.verify(reopened, operations, assets))
            self.assertEqual(path.read_bytes(), self.program.apply(operations, assets))
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def test_composer_rejects_broken_primitive_span_boundaries_and_overlap(self):
        operation, assets = self.frame()
        tail_start = len(self.source.envelope.body) - len(self.source.document.tail)
        for spans in ([(0, 1, b"x")], [(tail_start, tail_start + 2, b"x")],
                      [(tail_start, tail_start + 1, bytearray(b"x"))]):
            program = ExistingEdit(self.source, self.schema, self.presentation, self.background)
            program._background.spans = lambda *args, result=spans: result
            self.error(lambda: program.apply([operation], assets), "EXISTING_EDIT_SPAN")
        program = ExistingEdit(self.source, self.schema, self.presentation, self.background)
        program._presentation._spans = lambda *args: [(0, 2, b"a"), (1, 3, b"b")]
        self.error(lambda: program.apply([]), "EXISTING_EDIT_CONFLICT")

    def integer_setup(self, with_descriptor=True):
        from test_existing_integer_numeric import integer_numeric_fixture
        self.raw, self.schema, descriptor = integer_numeric_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.presentation["source_sha256"] = self.background["source_sha256"] = sha(self.raw)
        self.program = ExistingEdit(self.source, self.schema, self.presentation, self.background,
                                    descriptor if with_descriptor else None)
        return descriptor

    def numeric(self, sid="1", eid="31", **fields):
        operation = {"op": "configure_existing_integer_numeric", "screen_id": sid, "element_id": eid,
                     "owner_sha256": sha(self.extent(sid, eid)), "data_type": "INT",
                     "value_model": "integer_fixed_decimal", "integer_digits": 1, "fractional_digits": 4}
        if eid == "34":
            operation.update(integer_digits=2, fractional_digits=0, raw_minimum=-99, raw_maximum=99)
        operation.update(fields)
        return operation

    def test_optional_numeric_same_owner_presentation_four_category_composition(self):
        self.integer_setup()
        operations, assets = self.mixed()
        operations += [self.numeric(), self.numeric("7", "34"),
                       self.present("7", "34", states=[self.state("7", "34", font_color=0x112233)])]
        candidate = self.candidate(operations, assets)
        self.assertTrue(self.program.verify(candidate, operations, assets))
        self.assertEqual(candidate.envelope.body, self.program.expected_body(operations, assets))
        self.assertEqual(candidate.original, self.program.apply(list(reversed(operations)), assets))
        display = self.owner("1", "31", candidate)
        self.assertEqual(display["section"].one("DotNum").value, b"4")
        self.assertEqual(display["section"].one("BorderColor").value, b"16702650")
        self.assertEqual(display["states"][0].one("BgColor").value, b"1")
        input_owner = self.owner("7", "34", candidate)
        self.assertEqual(input_owner["section"].one("MinValue").value, b"-99")
        self.assertEqual(input_owner["states"][0].one("FontColor").value, b"1122867")
        spans = self.program.spans(operations, assets)
        restored, cursor, delta = [], 0, 0
        for start, end, raw in spans:
            stop = start + delta
            restored.extend((candidate.envelope.body[cursor:stop], self.source.envelope.body[start:end]))
            cursor = stop + len(raw); delta += len(raw) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        self.assertEqual(b"".join(restored), self.source.envelope.body)

    def test_numeric_opcode_requires_optional_descriptor_and_old_noop_unchanged(self):
        self.integer_setup(with_descriptor=False)
        self.assertEqual(self.program.apply([]), self.raw)
        self.error(lambda: self.program.apply([self.numeric()]), "UNQUALIFIED_EXISTING_INTEGER_NUMERIC")
        candidate = self.candidate([self.present(states=[self.state(font_color=7)])])
        self.assertEqual(self.owner("1", "31", candidate)["section"].one("DotNum").value, b"1")

    def test_numeric_duplicate_delete_conflict_and_scalar_overlap_refused(self):
        self.integer_setup()
        operation = self.numeric()
        self.error(lambda: self.program.apply([operation, deepcopy(operation)]), "DUPLICATE_EXISTING_INTEGER_NUMERIC")
        request = self.numeric(eid="11", integer_digits=5, fractional_digits=0)
        self.error(lambda: self.program.apply([self.delete(), request]), "EXISTING_EDIT_CONFLICT")
        self.error(lambda: self.program.apply([request, self.delete()]), "EXISTING_EDIT_CONFLICT")
        location = next(iter(self.program._integer_numeric._changes([operation])))
        self.program._presentation._changes = lambda *args: {location: b"0"}
        self.error(lambda: self.program.apply([operation]), "EXISTING_EDIT_CONFLICT")

    def test_optional_numeric_descriptor_freshness_and_saved_numeric_tamper(self):
        self.integer_setup()
        operations = [self.numeric(), self.numeric("7", "34"), self.delete()]
        candidate = self.candidate(operations)
        for before, after in ((b"DotNum=4", b"DotNum=3"), (b"MinValue=-99", b"MinValue=-98"),
                              (b"MemFmt=1", b"MemFmt=2"), (b"ReadVar={Link2}1@D0", b"ReadVar={Link2}1@D1")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after), operations),
                       "EXISTING_EDIT_PRESERVATION")
        self.program._integer_numeric.contract["authority_sha256"] = "0" * 64
        self.error(lambda: self.program.apply([]), "UNQUALIFIED_EXISTING_INTEGER_NUMERIC")
        self.integer_setup()
        self.program._integer_numeric = None
        self.error(lambda: self.program.check(), "INVALID_EXISTING_EDIT_SOURCE")


class ExistingEntryEditTests(unittest.TestCase):
    """Numeric, appearance and entry all refer to the same disabled original."""

    owner = ExistingEditTests.owner
    extent = ExistingEditTests.extent
    delete = ExistingEditTests.delete
    present = ExistingEditTests.present
    state = ExistingEditTests.state
    frame = ExistingEditTests.frame
    candidate = ExistingEditTests.candidate
    error = ExistingEditTests.error
    mutate = ExistingEditTests.mutate

    def setUp(self):
        from test_existing_entry_permission import entry_permission_fixture, parse_entry_json
        self.raw, self.schema, self.entry, self.namespace_raw, self.action_raw = entry_permission_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        common = {k: v for k, v in self.entry.items() if k not in ("address_namespace_sha256", "action_contract_sha256")}
        self.presentation = {**common, "mode": "variable_scalar_records_v1",
                             "authority_sha256": sha(b"SYNTHETIC PRESENTATION AUTHORITY")}
        self.background = {**common, "mode": "fixed_opaque_page_background_v1",
                           "authority_sha256": sha(b"SYNTHETIC BACKGROUND AUTHORITY")}
        self.integer = {**common, "mode": "existing_word_integer_numeric_v1",
                        "authority_sha256": sha(b"SYNTHETIC INTEGER NUMERIC AUTHORITY")}
        self.actions = parse_entry_json(self.action_raw)["actions"]
        self.program = self.make()

    def make(self, **optional):
        request = {"entry_permission_descriptor": self.entry, "address_namespace_raw": self.namespace_raw,
                   "action_contract_raw": self.action_raw}
        request.update(optional)
        return ExistingEdit(self.source, self.schema, self.presentation, self.background, self.integer, **request)

    def permission(self, sid="7", eid="34", **fields):
        from universal_hmi.native.existing_entry_permission import action_classification_sha256
        action = next(a for a in self.actions if (a["screen_id"], a["element_id"]) == (sid, eid))
        return {"op": "set_existing_entry_permission", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(self.extent(sid, eid)), "permission_address": "{Link2}0@X10",
                "enable_level": 0, "action_classification_sha256": action_classification_sha256(action), **fields}

    def numeric(self, sid="7", eid="34", **fields):
        signed = self.owner(sid, eid)["section"].one("MemFmt").value == b"1"
        return {"op": "configure_existing_integer_numeric", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(self.extent(sid, eid)), "data_type": "INT" if signed else "UINT",
                "value_model": "integer_fixed_decimal", "integer_digits": 3, "fractional_digits": 0,
                "raw_minimum": -99 if signed else 0, "raw_maximum": 321 if signed else 999, **fields}

    def mixed(self):
        background, assets = self.frame("7")
        operations = [self.delete(), self.present("7", "34", geometry={"x": 30, "y": 40, "width": 70, "height": 20},
                visual={"native_style": 0, "border_color": 0xFEDCBA}, states=[self.state("7", "34", font_size=22, surface_color=0xAABBCC)]),
                self.permission(), self.numeric(), self.permission("12", "137", enable_level=1),
                self.numeric("12", "137"), self.present("12", "61", states=[self.state("12", "61", surface_color=0x123456)]),
                self.permission("12", "61", permission_address="{Link2}0@M1"), background]
        return operations, assets

    def test_numeric_entry_presentation_background_delete_original_source_union(self):
        operations, assets = self.mixed()
        candidate = self.candidate(operations, assets)
        self.assertTrue(self.program.verify(candidate, operations, assets))
        self.assertEqual(candidate.envelope.body, self.program.expected_body(operations, assets))
        section = self.owner("7", "34", candidate)["section"]
        expected = {"InterLockVar": b"{Link2}0@X10", "InterLockLevel": b"0", "InterLockLink": b"1",
                    "MemLen": b"1", "MemFmt": b"1", "IntNum": b"3", "DotNum": b"0", "MinValue": b"-99",
                    "MaxValue": b"321", "Style": b"0", "BorderColor": b"16702650", "X": b"30", "Y": b"40"}
        for field, value in expected.items():
            self.assertEqual(section.one(field).value, value)
        self.assertEqual(self.owner("7", "34", candidate)["states"][0].one("BgColor").value, b"11189196")
        self.assertEqual(self.owner("12", "61", candidate)["section"].one("MemFmt").value, b"2")
        for page in _groups(self.source.document):
            saved = next(p for p in _groups(candidate.document) if p["id"] == page["id"])
            self.assertEqual(saved["section"].bytes(), page["section"].bytes())
        self.assertNotIn("11", {o["id"] for p in _groups(candidate.document) for o in p["elements"]})
        self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)

    def test_order_reversal_no_rebase_saved_replay_and_complete_restoration(self):
        operations, assets = self.mixed()
        output = self.program.apply(operations, assets)
        self.assertEqual(output, self.program.apply(list(reversed(operations)), assets))
        self.assertEqual(output, self.program.apply(operations, assets))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "neutral_composed_entry.dps"
            path.write_bytes(output)
            candidate = NativeAdapter(path.read_bytes(), self.source.family)
        spans, cursor, delta, restored = self.program.spans(operations, assets), 0, 0, []
        for start, end, replacement in spans:
            saved_start = start + delta; saved_end = saved_start + len(replacement)
            restored.extend((candidate.envelope.body[cursor:saved_start], self.source.envelope.body[start:end]))
            cursor = saved_end; delta += len(replacement) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        self.assertEqual(b"".join(restored), self.source.envelope.body)
        self.assertTrue(self.program.verify(candidate, operations, assets))

    def test_optional_trio_all_absent_or_present_and_unqualified_operation(self):
        old = ExistingEdit(self.source, self.schema, self.presentation, self.background, self.integer)
        self.assertEqual(old.apply([]), self.raw)
        self.error(lambda: old.apply([self.permission()]), "UNQUALIFIED_EXISTING_ENTRY_PERMISSION")
        for missing in ("entry_permission_descriptor", "address_namespace_raw", "action_contract_raw"):
            self.error(lambda missing=missing: self.make(**{missing: None}), "UNQUALIFIED_EXISTING_ENTRY_PERMISSION")
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source))

    def test_delete_entry_conflict_duplicate_and_overlapping_scalar_refused(self):
        invalid_target = {**self.permission(), "screen_id": "1", "element_id": "11", "owner_sha256": sha(self.extent("1", "11"))}
        self.error(lambda: self.program.apply([self.delete(), invalid_target]), "EXISTING_EDIT_CONFLICT")
        self.error(lambda: self.program.apply([invalid_target, self.delete()]), "EXISTING_EDIT_CONFLICT")
        self.error(lambda: self.program.apply([self.permission(), self.permission()]), "DUPLICATE_ENTRY_OPERATION")
        location = next(iter(self.program._entry_permission._changes([self.permission()])))
        self.program._presentation._changes = lambda *args: {location: b"None"}
        self.error(lambda: self.program.apply([self.permission()]), "EXISTING_EDIT_CONFLICT")

    def test_numeric_noop_checks_original_before_entry_then_active_source_refused(self):
        from universal_hmi.native.existing_integer_numeric import ExistingIntegerNumeric
        operations = [self.permission(), self.numeric(integer_digits=5, raw_minimum=-32768, raw_maximum=32767)]
        candidate = self.candidate(operations)
        self.assertTrue(self.program.verify(candidate, operations))
        for field in ("IntNum", "DotNum", "MinValue", "MaxValue"):
            self.assertEqual(self.owner("7", "34", candidate)["section"].one(field).raw,
                             self.owner("7", "34")["section"].one(field).raw)
        self.error(lambda: ExistingIntegerNumeric._target(self.owner("7", "34", candidate)), "EXISTING_INTEGER_NUMERIC_BEHAVIOR")

    def test_raw_dependency_descriptor_primitive_freshness_and_final_tamper(self):
        operations = [self.permission(), self.numeric()]
        candidate = self.candidate(operations)
        for before, after in ((b"InterLockVar={Link2}0@X10", b"InterLockVar={Link2}0@X11"),
                              (b"InterLockLevel=0", b"InterLockLevel=1"), (b"InterLockLink=1", b"InterLockLink=2"),
                              (b"MinValue=-99", b"MinValue=-98"), (b"WriteVar={Link2}0@D0", b"WriteVar={Link2}0@D1")):
            self.error(lambda before=before, after=after: self.program.verify(self.mutate(candidate, before, after), operations),
                       "EXISTING_EDIT_PRESERVATION")
        self.program._entry_permission.action_contract_raw += b" "
        self.error(lambda: self.program.apply([]), "ENTRY_ARTIFACT_PIN")
        self.program = self.make()
        self.program._entry_permission.contract["authority_sha256"] = "0" * 64
        self.error(self.program.check, "UNQUALIFIED_EXISTING_ENTRY_PERMISSION")
        self.program = self.make()
        self.program._entry_permission = None
        self.error(self.program.check, "INVALID_EXISTING_EDIT_SOURCE")


if __name__ == "__main__":
    unittest.main()
