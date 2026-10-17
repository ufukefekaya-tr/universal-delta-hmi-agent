"""Original three-page resource witnesses; no customer or vendor artwork."""
from copy import deepcopy
import gzip
import struct
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.existing_background import MAX_IMAGE_BYTES
from universal_hmi.native.existing_background_page import ExistingBackgroundPage, background_contract
from test_existing_background import png, dib, DIB_CORNERS, CORNER_ROWS
from test_existing_program import existing_program_fixture, existing_schema, existing_tail, sha


AFTER_BACKGROUND = (b"\r\n[DeviceTable]\r\nDisplayFormat=0\r\nEnableDownload=0\r\n"
                    b"DisplayLength=0\r\n[END]\r\n")


def background_fixture(order=(0, 1, 2), background=True):
    """Build three 2x2 pages and record frame positions while serializing.

    Positions are calculated from explicit fixture lengths, independently of
    production resource parsing. The retained SRAM includes decoy markers.
    """
    raw, _ = existing_program_fixture()
    base = NativeAdapter(raw, "delta_dopsoft2")
    pages = _groups(base.document)
    first = next(i for i, s in enumerate(base.document.sections) if s.name == "Screen")
    body = b"".join(s.bytes() for s in base.document.sections[:first])
    frames = [dib(), dib(pixels=b"\x44\x55\x66\xff" * 4), dib(pixels=b"\xff" * 16)] if background else []
    for page, offset in zip(pages, order):
        header = deepcopy(page["section"])
        for key in ("DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"):
            header.one(key).set_value(b"2")
        if background:
            from universal_hmi.native.records import Record
            header.records.append(Record(f"PictureOffset={offset * 56}\r\n".encode(), "PictureOffset", str(offset * 56).encode()))
        body += header.bytes() + b"[AuxKeyElement]\r\n"
    tail = existing_tail(background=b"".join(frames))
    decoy = b"[Background]\r\nSize=0\r\n[END]\r\n"
    old = b"[Element]\r\nnPartsID=999\r\n"
    # The same-size padded replacement remains inside the fixed SRAM frame.
    tail = tail.replace(old, decoy[:len(old)], 1)
    start = len(body) + len(tail) - len(AFTER_BACKGROUND) - len(b"".join(frames))
    body += tail
    raw = base.envelope.encode(body)
    descriptor = {"qualified": True, "contract_version": 1, "mode": "fixed_opaque_page_background_v1",
                  "source_sha256": sha(raw), "family": "delta_dopsoft2", "model_id": 2953863504,
                  "editor_version": "4.00.07.04", "authority_sha256": sha(b"SYNTHETIC BACKGROUND AUTHORITY")}
    positions = [(start + i * 56, start + (i + 1) * 56) for i in range(len(frames))]
    return raw, existing_schema(raw), descriptor, frames, positions


class ExistingBackgroundPageTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema, self.descriptor, self.frames, self.positions = background_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = ExistingBackgroundPage(self.source, self.schema, self.descriptor)
        self.asset = png()
        self.assets = {sha(self.asset): self.asset}

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code is not None:
            self.assertEqual(caught.exception.code, code)

    def op(self, sid="1", asset=None):
        frame = next(f for f in self.program.frame_inventory() if f["screen_id"] == sid)
        return {"op": "set_existing_background", "screen_id": sid,
                "frame_sha256": frame["frame_sha256"], "asset_sha256": sha(self.asset if asset is None else asset)}

    def repin(self, source):
        descriptor = deepcopy(self.descriptor)
        descriptor["source_sha256"] = sha(source.original)
        return ExistingBackgroundPage(source, existing_schema(source.original), descriptor)

    def mutate(self, before, after):
        self.assertIn(before, self.source.envelope.body)
        return NativeAdapter(self.source.envelope.encode(self.source.envelope.body.replace(before, after, 1)), self.source.family)

    def test_inventory_uses_unique_original_page_mapping_and_is_detached(self):
        self.assertTrue(self.program.check())
        expected = [{"screen_id": sid, "frame_sha256": sha(frame), "width": 2, "height": 2}
                    for sid, frame in zip(("1", "7", "12"), self.frames)]
        self.assertEqual(self.program.frame_inventory(), expected)
        inventory = self.program.frame_inventory()
        inventory[0]["screen_id"] = "999"
        self.assertEqual(self.program.frame_inventory(), expected)

    def test_asymmetric_pixels_saved_readback_and_full_source_restoration(self):
        operations = [self.op("12"), self.op("1"), self.op("7")]
        spans = self.program.spans(operations, self.assets)
        self.assertEqual([(s, e) for s, e, _ in spans], self.positions)
        oracle = bytearray(self.source.envelope.body)
        for (start, end), frame in zip(self.positions, self.frames):
            oracle[start:end] = frame[:40] + DIB_CORNERS
        self.assertEqual(self.program.expected_body(operations, self.assets), bytes(oracle))
        raw = self.program.apply(operations, self.assets)
        candidate = NativeAdapter(raw, self.source.family)
        self.assertTrue(self.program.verify(candidate, operations, self.assets))
        self.assertEqual(candidate.envelope.body, bytes(oracle))
        self.assertEqual(candidate.envelope.prefix, self.source.envelope.prefix)
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)
        self.assertEqual(candidate.document.sections, self.source.document.sections)
        for (start, end), frame in zip(self.positions, self.frames):
            self.assertEqual(candidate.envelope.body[start:start + 40], frame[:40])
            oracle[start:end] = frame
        self.assertEqual(bytes(oracle), self.source.envelope.body)
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def test_shared_png_does_not_need_duplicate_assets(self):
        operations = [self.op("7"), self.op("1")]
        self.assertEqual(len(self.program.spans(operations, self.assets)), 2)
        result = NativeAdapter(self.program.apply(operations, self.assets), self.source.family)
        third_start, third_end = self.positions[2]
        self.assertEqual(result.envelope.body[third_start:third_end], self.frames[2])

    def test_live_owners_addresses_states_and_sections_are_preserved(self):
        raw, _ = existing_program_fixture()
        source = NativeAdapter(raw, self.source.family)
        pages = _groups(source.document)
        width = int(pages[0]["section"].one("PanelSizeX").value)
        height = int(pages[0]["section"].one("PanelSizeY").value)
        from universal_hmi.native.records import Record
        frames = [dib(width, height, pixels=bytes((color, color, color, 255)) * (width * height))
                  for color in (17, 34, 51)]
        frame_size = len(frames[0])
        for index, page in enumerate(pages):
            value = str(index * frame_size).encode()
            page["section"].records.append(Record(b"PictureOffset=" + value + b"\r\n", "PictureOffset", value))
        source.document.tail = existing_tail(background=b"".join(frames))
        source = NativeAdapter(source.envelope.encode(source.document.bytes()), source.family)
        program = self.repin(source)
        frame = next(item for item in program.frame_inventory() if item["screen_id"] == "7")
        black = png((b"\0" + b"\0" * (width * 3)) * height, width, height)
        operation = {"op": "set_existing_background", "screen_id": "7",
                     "frame_sha256": frame["frame_sha256"], "asset_sha256": sha(black)}
        candidate = NativeAdapter(program.apply([operation], {sha(black): black}), source.family)
        self.assertTrue(program.verify(candidate, [operation], {sha(black): black}))
        self.assertEqual([section.bytes() for section in candidate.document.sections],
                         [section.bytes() for section in source.document.sections])
        # Literal labels, navigation, bit and numeric owners all remain live.
        self.assertEqual([len(page["elements"]) for page in _groups(candidate.document)], [5, 5, 3])
        self.assertEqual(candidate.document.tail, source.document.tail.replace(frames[1], dib(width, height), 1))
        self.error(lambda: NativeAdapter(source.envelope.encode(source.envelope.body.replace(
            b"nPartsID=21\r\n", b"nPartsID=11\r\n", 1)), source.family), "DUPLICATE_ELEMENT")

    def test_reordered_page_references_keep_original_body_coordinates(self):
        raw, schema, descriptor, frames, positions = background_fixture((2, 0, 1))
        program = ExistingBackgroundPage(NativeAdapter(raw, self.source.family), schema, descriptor)
        inventory = program.frame_inventory()
        self.assertEqual([f["frame_sha256"] for f in inventory], [sha(frames[i]) for i in (2, 0, 1)])
        operations = [{"op": "set_existing_background", "screen_id": frame["screen_id"],
                       "frame_sha256": frame["frame_sha256"], "asset_sha256": sha(self.asset)} for frame in inventory]
        self.assertEqual([(s, e) for s, e, _ in program.spans(operations, self.assets)], positions)

    def test_empty_and_explicit_identical_replacement_are_exact_file_noops(self):
        self.assertIs(self.program.apply([], {}), self.source.original)
        self.assertTrue(self.program.verify(self.source))
        black = png(b"\0" * 14)
        operation = self.op(asset=black)
        assets = {sha(black): black}
        self.assertEqual(self.program.spans([operation], assets), [])
        self.assertIs(self.program.apply([operation], assets), self.source.original)
        self.assertEqual(self.program.expected_body([operation], assets), self.source.envelope.body)
        self.assertTrue(self.program.verify(self.source, [operation], assets))

    def test_empty_background_has_no_writable_frame(self):
        raw, schema, descriptor, _, _ = background_fixture(background=False)
        program = ExistingBackgroundPage(NativeAdapter(raw, self.source.family), schema, descriptor)
        self.assertEqual(program.frame_inventory(), [])
        self.assertEqual(program.apply([], {}), raw)
        self.error(lambda: program.spans([self.op()], self.assets), "MISSING_BACKGROUND_PAGE")

    def test_descriptor_is_exact_separate_and_typed(self):
        for key, value in (("qualified", False), ("contract_version", True), ("contract_version", 2),
                           ("mode", "variable_scalar_records_v1"), ("family", "delta_diascreen"),
                           ("model_id", True), ("model_id", 1), ("editor_version", "4.00.07.05"),
                           ("source_sha256", "A" * 64), ("authority_sha256", "bad")):
            descriptor = deepcopy(self.descriptor); descriptor[key] = value
            with self.subTest(key=key, value=value):
                self.error(lambda: background_contract(descriptor), "UNQUALIFIED_EXISTING_BACKGROUND")
        for descriptor in (None, [], {}, self.descriptor | {"extra": 1}):
            self.error(lambda: background_contract(descriptor), "UNQUALIFIED_EXISTING_BACKGROUND")

    def test_descriptor_snapshots_source_binding_and_caller_mutation(self):
        descriptor = deepcopy(self.descriptor)
        program = ExistingBackgroundPage(self.source, self.schema, descriptor)
        descriptor["source_sha256"] = "0" * 64
        self.assertTrue(program.check())
        program.contract["authority_sha256"] = "0" * 64
        self.error(program.check, "UNQUALIFIED_EXISTING_BACKGROUND")
        changed = self.mutate(b"wFont001=Arial", b"wFont001=Other")
        program = ExistingBackgroundPage(changed, existing_schema(changed.original), self.descriptor)
        self.error(program.check, "INVALID_BACKGROUND_SOURCE")
        self.program.source = changed
        self.error(self.program.check, "INVALID_BACKGROUND_SOURCE")

    def test_source_adapter_changes_are_refused_before_output(self):
        self.source.document.sections[0].one("Version").set_value(b"4.00.07.05")
        self.error(lambda: self.program.apply([], {}), "INVALID_EXISTING_SOURCE")

    def test_operations_exact_keys_identity_pins_and_unique_page(self):
        operation = self.op()
        for key, value in (("op", "change_image"), ("screen_id", "01"), ("screen_id", 1),
                           ("screen_id", "65536"), ("screen_id", "2"), ("frame_sha256", "0" * 64),
                           ("frame_sha256", []), ("asset_sha256", "0" * 64), ("asset_sha256", True)):
            bad = deepcopy(operation); bad[key] = value
            with self.subTest(key=key, value=value):
                self.error(lambda: self.program.spans([bad], self.assets))
        for key in operation:
            bad = deepcopy(operation); del bad[key]
            self.error(lambda: self.program.spans([bad], self.assets), "INVALID_BACKGROUND_OPERATION")
        self.error(lambda: self.program.spans([operation | {"path": "not-accepted"}], self.assets), "INVALID_BACKGROUND_OPERATION")
        self.error(lambda: self.program.spans([operation, deepcopy(operation)], self.assets), "DUPLICATE_BACKGROUND_PAGE")
        self.error(lambda: self.program.spans([operation] * 257, self.assets), "INVALID_OPERATIONS")

    def test_operations_and_descriptors_refuse_cycles_or_nonjson(self):
        operations = []; operations.append(operations)
        self.error(lambda: self.program.spans(operations, self.assets), "INVALID_EXISTING_PROGRAM")
        descriptor = deepcopy(self.descriptor); descriptor["extra"] = descriptor
        self.error(lambda: background_contract(descriptor), "INVALID_EXISTING_PROGRAM")
        for value in (None, True, {}, "", 1):
            self.error(lambda: self.program.spans(value, self.assets), "INVALID_OPERATIONS")

    def test_assets_require_hash_bytes_bounded_size_and_exact_coverage(self):
        for assets in (None, [], {sha(self.asset): bytearray(self.asset)}, {"A" * 64: self.asset},
                       {sha(self.asset): {}}, {True: self.asset}):
            self.error(lambda: self.program.spans([self.op()], assets), "INVALID_BACKGROUND_ASSETS")
        self.error(lambda: self.program.spans([self.op()], {sha(self.asset): b"different"}), "BACKGROUND_ASSET_PIN")
        self.error(lambda: self.program.spans([self.op()], {}), "BACKGROUND_ASSET_PIN")
        black = png(b"\0" * 14)
        extras = self.assets | {sha(black): black}
        self.error(lambda: self.program.spans([self.op()], extras), "BACKGROUND_ASSET_COVERAGE")
        self.error(lambda: self.program.spans([], self.assets), "BACKGROUND_ASSET_COVERAGE")
        cycle = {}; cycle[sha(self.asset)] = cycle
        self.error(lambda: self.program.spans([self.op()], cycle), "INVALID_BACKGROUND_ASSETS")
        oversized = b"x" * (MAX_IMAGE_BYTES + 1)
        self.error(lambda: self.program.spans([], {"0" * 64: oversized}), "IMAGE_LIMIT")
        many = {f"{index:064x}": b"" for index in range(257)}
        self.error(lambda: self.program.spans([], many), "INVALID_BACKGROUND_ASSETS")

    def test_aggregate_assets_are_bounded_before_second_decode(self):
        first = b"x" * (MAX_IMAGE_BYTES // 2 + 1)
        second = b"y" * (MAX_IMAGE_BYTES // 2 + 1)
        self.error(lambda: self.program.spans([], {sha(first): first, sha(second): second}), "IMAGE_LIMIT")

    def test_wrong_canvas_or_nonopaque_asset_is_refused(self):
        wrong_canvas = png(b"\0\0\0\0", 1, 1)
        self.error(lambda: self.program.spans([self.op(asset=wrong_canvas)], {sha(wrong_canvas): wrong_canvas}), "PNG_CANVAS")
        rgba = bytes.fromhex("00 ff0000ff 00ff00ff 00 0000ffff ffff00fe")
        nonopaque = png(rgba, color=6)
        self.error(lambda: self.program.spans([self.op(asset=nonopaque)], {sha(nonopaque): nonopaque}), "PNG_ALPHA")

    def test_reserved_bytes_are_refused_only_for_requested_conversion(self):
        start, _ = self.positions[0]
        body = bytearray(self.source.envelope.body); body[start + 43] = 17
        source = NativeAdapter(self.source.envelope.encode(bytes(body)), self.source.family)
        program = self.repin(source)
        self.assertTrue(program.check())  # Existing graph is unchanged, no alpha reinterpretation.
        frame = program.frame_inventory()[0]
        operation = self.op(); operation["frame_sha256"] = frame["frame_sha256"]
        self.error(lambda: program.spans([operation], self.assets), "DIB_RESERVED")
        self.assertEqual(program.apply([], {}), source.original)
        other = program.frame_inventory()[1]
        operation = self.op("7"); operation["frame_sha256"] = other["frame_sha256"]
        candidate = NativeAdapter(program.apply([operation], self.assets), source.family)
        self.assertEqual(candidate.envelope.body[start:start + 56], source.envelope.body[start:start + 56])
        self.assertTrue(program.verify(candidate, [operation], self.assets))

    def test_closed_graph_rejects_aliases_shared_unowned_frames_and_base_pages(self):
        for before, after in ((b"PictureOffset=56\r\n", b"PictureOffset=0\r\n"),
                              (b"PictureOffset=56\r\n", b"PictureOffset=056\r\n"),
                              (b"PictureOffset=56\r\n", b"PictureOffset=57\r\n"),
                              (b"BaseScreenID=0\r\n", b"BaseScreenID=7\r\n"),
                              (b"PanelSizeX=2\r\n", b"PanelSizeX=3\r\n"),
                              (b"DisplayLength=0\r\n", b"DisplayLength=0\r\nMystery=1\r\n")):
            source = self.mutate(before, after)
            with self.subTest(before=before, after=after):
                self.error(self.repin(source).check)

    def test_malformed_nested_frame_and_incomplete_resource_are_refused(self):
        body = bytearray(self.source.envelope.body)
        struct.pack_into("<i", body, self.positions[1][0] + 4, 0)
        source = NativeAdapter(self.source.envelope.encode(bytes(body)), self.source.family)
        self.error(self.repin(source).check, "UNQUALIFIED_EXISTING_GRAPH")
        source = self.mutate(b"[Background]\r\nSize=168\r\n", b"[Background]\r\nSize=169\r\n")
        self.error(self.repin(source).check)

    def test_candidate_unapproved_pixels_headers_resources_and_sections_fail(self):
        operations = [self.op()]
        expected = self.program.expected_body(operations, self.assets)
        start, _ = self.positions[0]
        for index in (start + 40, start, self.positions[2][0] + 40):
            changed = bytearray(expected); changed[index] ^= 1
            candidate = NativeAdapter(self.source.envelope.encode(bytes(changed)), self.source.family)
            self.error(lambda: self.program.verify(candidate, operations, self.assets), "EXISTING_BACKGROUND_PRESERVATION")
        for before, after in ((b"HistoryCount=0", b"HistoryCount=1"),
                              (b"PanelSizeX=2", b"PanelSizeX=3"),
                              (b"[END]\r\n", b"[END]\r\nUnknown=1\r\n")):
            candidate = NativeAdapter(self.source.envelope.encode(expected.replace(before, after, 1)), self.source.family)
            self.error(lambda: self.program.verify(candidate, operations, self.assets), "EXISTING_BACKGROUND_PRESERVATION")

    def test_candidate_binding_thumbnail_prefix_and_file_noop_are_checked(self):
        self.error(lambda: self.program.verify(self.raw), "INVALID_BACKGROUND_CANDIDATE")
        candidate = NativeAdapter(self.raw, self.source.family)
        candidate.document.tail += b"x"
        self.error(lambda: self.program.verify(candidate), "INVALID_BACKGROUND_CANDIDATE")
        source = self.source
        # Same body, different gzip metadata: complete-file no-op must fail.
        payload = (source.envelope.prefix + source.envelope.body).translate(bytes(i ^ 0x64 for i in range(256)))
        altered = source.envelope.thumbnail + gzip.compress(payload, mtime=1)
        candidate = NativeAdapter(altered, source.family)
        self.error(lambda: self.program.verify(candidate), "EXISTING_BACKGROUND_PRESERVATION")
        operations = [self.op()]
        body = self.program.expected_body(operations, self.assets)
        thumb = bytearray(source.envelope.thumbnail); thumb[10] ^= 1
        candidate = NativeAdapter(Envelope(bytes(thumb), source.envelope.prefix, body).encode(body), source.family)
        self.error(lambda: self.program.verify(candidate, operations, self.assets), "EXISTING_BACKGROUND_PRESERVATION")
        prefix = bytes((source.envelope.prefix[0] ^ 1,)) + source.envelope.prefix[1:]
        candidate = NativeAdapter(Envelope(source.envelope.thumbnail, prefix, body).encode(body), source.family)
        self.error(lambda: self.program.verify(candidate, operations, self.assets), "EXISTING_BACKGROUND_PRESERVATION")


if __name__ == "__main__":
    unittest.main()
