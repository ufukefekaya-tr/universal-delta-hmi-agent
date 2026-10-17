"""Original neutral graph fixtures; no vendor/runtime acceptance is implied."""
from copy import deepcopy
import hashlib
import gzip
import struct
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.records import Record
from universal_hmi.native.existing_program import ExistingProgram, existing_program_contract
from test_native import control_generation_fixture
from test_multipage import auxiliary_owner


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def existing_schema(raw):
    """Synthetic static descriptor; public authority is separately registered."""
    return {"qualified": True, "existing_program": {
        "qualified": True, "contract_version": 1, "mode": "source_inert_literal_deletion",
        "source_sha256": sha(raw), "family": "delta_dopsoft2", "model_id": 2953863504,
        "editor_version": "4.00.07.04", "authority_sha256": sha(b"SYNTHETIC INERT DELETION AUTHORITY")}}


def existing_tail(initialized=True, background=b""):
    # Harmless original bytes exercise opaque configuration restoration,
    # including fake section-looking bytes within fixed framed metadata.
    sram = bytearray(530)
    struct.pack_into("<II", sram, 0, 20, 2953863504)
    sram[20:24] = b"DOPB"
    opaque = b"[Element]\r\nnPartsID=999\r\n"
    sram[80:80 + len(opaque)] = opaque
    return (b"[SubMacro]\r\nSubMacroProtect001=0\r\nSubMacroPWD001=NEUTRAL8\r\n"
        b"[Global_Auxkey]\r\n[Alarm]\r\nVersion=16\r\nAlarmCount=0\r\n"
        b"[History]\r\nHistoryCount=0\r\n[TextBank]\r\nwFont001=Arial\r\n"
        + (b"[Tag]\r\nTagLinkCount=1\r\nLinkSize=0\r\n" if initialized else b"[Tag]\r\nTagLinkCount=0\r\n")
        + b"[EthernetIPTag]\r\nTagTotalSize=0\r\n[SRAM_DATA]\r\n" + struct.pack("<I", len(sram)) + bytes(sram) + b"\r\n"
        b"[SysMessage]\0\0\0\r\nLangName0=English\r\n[Picture]\r\nSize=0\r\n\r\n[Background]\r\nSize="
        + str(len(background)).encode() + b"\r\n" + background + b"\r\n"
        b"[DeviceTable]\r\nDisplayFormat=0\r\nEnableDownload=0\r\nDisplayLength=0\r\n[END]\r\n")


def existing_program_fixture():
    """Three neutral pages with asymmetric literals and retained live owners."""
    raw, _ = control_generation_fixture()
    a = NativeAdapter(raw, "delta_dopsoft2")
    donor_page = _groups(a.document)[0]
    app = (b"[Application]\r\nModelName=-1341103792\r\nVersion=4.00.07.04\r\n"
           b"InitialMacroLen=0\r\nBackgroundMacroLen=0\r\nClockMacroLen=0\r\n\r\n"
           b"MeMeCode=" + struct.pack("<I", 48) + bytes(range(48)) + b"\r\n"
           b"[Recipe]\r\nEnableRcp=0\r\nRcpLen=0\r\nRcpGroup=0\r\n\r\n")
    def control(index, identity):
        owner = donor_page["elements"][index]
        parts = deepcopy(a.document.sections[owner["start"]:owner["end"]])
        parts[0].one("nPartsID").set_value(str(identity).encode())
        return b"".join(part.bytes() for part in parts)
    def literal(identity, caption):
        holder = NativeAdapter(a.envelope.encode(app + donor_page["section"].bytes()
            + b"[AuxKeyElement]\r\n" + auxiliary_owner("text", identity) + existing_tail()), "delta_dopsoft2")
        owner = _groups(holder.document)[0]["elements"][0]
        owner["states"][0].one("wTextLen0").set_text(caption)
        return b"".join(section.bytes() for section in holder.document.sections[owner["start"]:owner["end"]])
    goto = auxiliary_owner("goto", 41).replace(b"GoToScreenID=1\r\n", b"GoToScreenID=12\r\n")
    pages = [("1", "Overview", [literal(11, "İlk"), control(2, 21), literal(13, "Middle caption"),
                                control(5, 31), literal(17, "End of overview")]),
             ("7", "Values", [goto, auxiliary_owner("indicator", 23), literal(29, "Ölçüm"),
                               control(4, 34), literal(37, "Last values label")]),
             ("12", "Notes", [literal(43, "A"), literal(47, "Çok daha uzun metin"), literal(53, "Son")])]
    body = app
    for sid, name, owners in pages:
        header = deepcopy(donor_page["section"])
        header.one("ID").set_value(sid.encode())
        header.one("wTextLen").set_text(name)
        header.one("wScreenDESCTextLen000").set_text(name)
        body += header.bytes() + b"[AuxKeyElement]\r\n" + b"".join(owners)
    body += existing_tail()
    prefix = a.envelope.prefix[:37] + bytes(v ^ 0x64 for v in struct.pack("<I", len(body)))
    raw = Envelope(a.envelope.thumbnail, prefix, body).encode(body)
    return raw, existing_schema(raw)


class ExistingProgramTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema = existing_program_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = ExistingProgram(self.source, self.schema)

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code:
            self.assertEqual(caught.exception.code, code)

    def delete(self, sid="1", eid="11", source=None):
        a = source or self.source
        page = next(p for p in _groups(a.document) if p["id"] == sid)
        owner = next(o for o in page["elements"] if o["id"] == eid)
        extent = b"".join(s.bytes() for s in a.document.sections[owner["start"]:owner["end"]])
        return {"op": "delete_literal", "screen_id": sid, "element_id": eid,
                "owner_sha256": sha(extent)}

    def mutate(self, before, after, source=None):
        a = source or self.source
        self.assertIn(before, a.envelope.body)
        return NativeAdapter(a.envelope.encode(a.envelope.body.replace(before, after, 1)), a.family)

    def reprogram(self, source):
        return ExistingProgram(source, existing_schema(source.original))

    def test_exact_noop_original_bytes_and_uninitialized_tag(self):
        self.assertTrue(self.program.check())
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source))
        source = self.mutate(b"TagLinkCount=1\r\nLinkSize=0\r\n", b"TagLinkCount=0\r\n")
        program = self.reprogram(source)
        self.assertTrue(program.check())
        out = NativeAdapter(program.apply([self.delete(source=source)]), source.family)
        self.assertEqual(out.document.tail, source.document.tail)

    def test_asymmetric_first_middle_last_multi_page_deletion_and_restoration(self):
        cases = [[self.delete()], [self.delete("1", "13")], [self.delete("12", "53")],
                 [self.delete("12", "53"), self.delete("1", "11"), self.delete("7", "29")],
                 [self.delete(page["id"], owner["id"]) for page in _groups(self.source.document)
                  for owner in page["elements"] if owner["section"].one("Type").value == b"10"]]
        before = self.raw
        for operations in cases:
            with self.subTest(targets=[op["element_id"] for op in operations]):
                output = self.program.apply(operations)
                candidate = NativeAdapter(output, self.source.family)
                self.assertTrue(self.program.verify(candidate, operations))
                selected = {op["element_id"] for op in operations}
                source_pages, saved_pages = _groups(self.source.document), _groups(candidate.document)
                self.assertEqual([p["id"] for p in saved_pages], ["1", "7", "12"])
                removed_bytes = 0
                for old, new in zip(source_pages, saved_pages):
                    self.assertEqual(old["section"].bytes(), new["section"].bytes())
                    survivors = [o for o in old["elements"] if o["id"] not in selected]
                    self.assertEqual([o["id"] for o in new["elements"]], [o["id"] for o in survivors])
                    for original, saved in zip(survivors, new["elements"]):
                        self.assertEqual(b"".join(s.bytes() for s in self.source.document.sections[original["start"]:original["end"]]),
                                         b"".join(s.bytes() for s in candidate.document.sections[saved["start"]:saved["end"]]))
                    removed_bytes += sum(len(b"".join(s.bytes() for s in self.source.document.sections[o["start"]:o["end"]]))
                                         for o in old["elements"] if o["id"] in selected)
                self.assertEqual(len(candidate.envelope.body), len(self.source.envelope.body) - removed_bytes)
                self.assertEqual(candidate.envelope.body, self.program.expected_body(operations))
                self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)
                self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])
                self.assertEqual(candidate.document.tail, self.source.document.tail)
                self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
        self.assertEqual(self.source.original, before)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def test_operations_invalid_identity_hash_nonliteral_and_duplicates_fail_before_output(self):
        for sid, eid in (("0", "11"), ("65536", "11"), ("1", "0"), ("1", "2147483648"),
                         ("01", "11"), ("1", "011"), ("1", "999"), ("2", "11")):
            op = self.delete(); op.update(screen_id=sid, element_id=eid)
            self.error(lambda: self.program.apply([op]))
        for eid in ("21", "31"):
            self.error(lambda: self.program.apply([self.delete("1", eid)]), "NONINERT_LITERAL")
        op = self.delete()
        self.error(lambda: self.program.apply([op, deepcopy(op)]), "DUPLICATE_LITERAL_DELETION")
        for digest in ("0" * 64, "ABC", None, [], {}, True):
            wrong = deepcopy(op); wrong["owner_sha256"] = digest
            self.error(lambda: self.program.apply([wrong]), "LITERAL_DELETION_PIN")
        for value in (None, {}, True, "", 1):
            self.error(lambda: self.program.apply(value), "INVALID_OPERATIONS")
        for field in ("op", "screen_id", "element_id"):
            for value in (None, [], {}, True, 0, 1.5, ""):
                wrong = deepcopy(op); wrong[field] = value
                self.error(lambda: self.program.apply([wrong]))
        wrong = deepcopy(op); wrong["extra"] = True
        self.error(lambda: self.program.apply([wrong]), "INVALID_EXISTING_OPERATION")
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def test_malformed_deep_cyclic_and_exact_descriptors(self):
        for value in (None, [], {}, True, 1, "schema"):
            self.error(lambda: existing_program_contract(value))
        for field, value in (("qualified", 1), ("contract_version", True), ("mode", "preserved_layout"),
                             ("source_sha256", "a"), ("authority_sha256", "A" * 64), ("family", "delta_diascreen"),
                             ("model_id", "2953863504"), ("editor_version", "4.00.07.05"), ("extra", 0)):
            schema = deepcopy(self.schema); schema["existing_program"][field] = value
            self.error(lambda: ExistingProgram(self.source, schema))
        for key in ("control_generation", "preserved_layout", "blank_program", "multipage_program", "literal_generation"):
            schema = deepcopy(self.schema); schema[key] = {}
            self.error(lambda: ExistingProgram(self.source, schema))
        cycle = []; cycle.append(cycle)
        deep = []; holder = deep
        for _ in range(12):
            holder.append([]); holder = holder[0]
        for value in (cycle, deep, [{"op": b"delete_literal"}], [self.delete()] * 4097):
            self.error(lambda: self.program.apply(value))

    def test_descriptor_copy_and_postconstruction_freshness(self):
        schema = deepcopy(self.schema)
        program = ExistingProgram(self.source, schema)
        schema["existing_program"]["source_sha256"] = "0" * 64
        self.assertTrue(program.check())
        for field, value in (("source_sha256", "0" * 64), ("authority_sha256", "0" * 64), ("extra", None),
                             ("model_id", []), ("qualified", False)):
            program = ExistingProgram(self.source, self.schema)
            program.contract[field] = value
            self.error(lambda: program.apply([]), "UNQUALIFIED_EXISTING_PROGRAM")
        program.contract = None
        self.error(lambda: program.check(), "UNQUALIFIED_EXISTING_PROGRAM")

    def test_all_closed_source_graph_guards_reject_rehashed_unsafe_variants(self):
        variants = ((b"GroupID=0", b"GroupID=1"), (b"VisibleVar=None", b"VisibleVar={Link2}1@M1"),
                    (b"PosVary=0", b"PosVary=1"), (b"ReadVar=None", b"ReadVar={Link2}1@D1"),
                    (b"WriteVar=None", b"WriteVar={Link2}1@D1"), (b"OffsetReadVar=None", b"OffsetReadVar={Link2}1@D1"),
                    (b"PrintSuccessiveData=0", b"PrintSuccessiveData=1"), (b"nAngle=0", b"nAngle=1"),
                    (b"bFreeze=0", b"bFreeze=1"), (b"InitialMacroLen=0\r\n", b"InitialMacroLen=2\r\n\r\n"),
                    (b"OpenMacroLen=0\r\n", b"OpenMacroLen=2\r\n\r\n"),
                    (b"BeforeExecMacroLen=0\r\n", b"BeforeExecMacroLen=2\r\n\r\n"),
                    (b"[SubMacro]\r\n", b"[SubMacro]\r\nSubMacro001Len=2\r\n\r\n"),
                    (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnknown=1\r\n"),
                    (b"nPartsID=11\r\n", b"nPartsID=11\r\nRelatedOwnerID=21\r\n"),
                    (b"Type=10\r\n", b"Type=99\r\n"), (b"UsePictureCoord=0", b"UsePictureCoord=1"),
                    (b"SoundIndex=0", b"SoundIndex=1"), (b"GoToScreenID=12", b"GoToScreenID=99"),
                    (b"KeypadScreenID=0", b"KeypadScreenID=12"), (b"BaseScreenID=0", b"BaseScreenID=7"),
                    (b"IsSubScreen=0", b"IsSubScreen=1"), (b"IsScreenRotate=0", b"IsScreenRotate=1"))
        for before, after in variants:
            with self.subTest(field=before.split(b"=")[0]):
                source = self.mutate(before, after)
                program = self.reprogram(source)
                op = self.delete(source=source)
                self.error(lambda: program.apply([op]))
                self.assertEqual(source.document.bytes(), source.envelope.body)

    def test_required_macro_relationship_and_empty_resource_frames(self):
        for field in (b"InitialMacroLen=0\r\n", b"BackgroundMacroLen=0\r\n", b"ClockMacroLen=0\r\n",
                      b"OpenMacroLen=0\r\n", b"CloseMacroLen=0\r\n", b"CycleMacroLen=0\r\n",
                      b"BeforeExecMacroLen=0\r\n", b"GroupID=0\r\n", b"GoToScreenID=12\r\n",
                      b"EnableRcp=0\r\n", b"RcpLen=0\r\n", b"RcpGroup=0\r\n", b"HistoryCount=0\r\n",
                      b"TagLinkCount=1\r\n", b"LinkSize=0\r\n", b"TagTotalSize=0\r\n",
                      b"AlarmCount=0\r\n", b"EnableDownload=0\r\n", b"Size=0\r\n\r\n"):
            with self.subTest(field=field):
                self.error(lambda: self.reprogram(self.mutate(field, b"")).check())

    def test_duplicate_and_inconsistent_tail_records_are_rejected(self):
        for before, after in ((b"SubMacroProtect001=0\r\n", b"SubMacroProtect001=0\r\nSubMacroProtect001=0\r\n"),
                              (b"[SubMacro]\r\n", b"[SubMacro]\r\nSubMacroLen001=0\r\n"),
                              (b"[SubMacro]\r\n", b"[SubMacro]\r\nSubMacro001Len=0\r\n"),
                              (b"SubMacroPWD001=NEUTRAL8\r\n", b"SubMacroPWD001=NEUTRAL8\r\nSubMacroPWD001=NEUTRAL8\r\n"),
                              (b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD001=SHORT"),
                              (b"SubMacroProtect001=0", b"SubMacroProtect001=2"),
                              (b"SubMacroProtect001=0", b"SubMacroProtect000=0"),
                              (b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD513=NEUTRAL8"),
                              (b"TagLinkCount=1", b"TagLinkCount=0"),
                              (b"LinkSize=0\r\n", b"LinkSize=0\r\nLinkSize=0\r\n"),
                              (b"[Global_Auxkey]\r\n", b""), (b"[Global_Auxkey]\r\n", b"[Global_Auxkey]\r\nUnknown=1\r\n"),
                              (b"[END]\r\n", b"[UnsolvedReferences]\r\n[END]\r\n")):
            source = self.mutate(before, after)
            self.error(lambda: self.reprogram(source).check())

    def test_nonascii_native_kind_and_goto_reference_are_typed(self):
        for before, after in ((b"Type=10", b"Type=\xff"), (b"SubType=6", b"SubType=\xff"),
                              (b"GoToScreenID=12", b"GoToScreenID=\xff")):
            source = self.mutate(before, after)
            self.error(lambda: self.reprogram(source).check(), "UNQUALIFIED_EXISTING_GRAPH")

    def test_cached_projection_wrong_identity_and_stale_source_are_rejected(self):
        for source in (None, "source", []):
            self.error(lambda: ExistingProgram(source, self.schema).check(), "INVALID_EXISTING_SOURCE")
        changed = self.mutate(b"Style=0", b"Style=1")
        self.error(lambda: ExistingProgram(changed, self.schema).check(), "INVALID_EXISTING_SOURCE")
        for before, after in ((b"ModelName=-1341103792", b"ModelName=99"),
                              (b"Version=4.00.07.04", b"Version=4.00.07.05")):
            self.error(lambda: self.reprogram(self.mutate(before, after)).check(), "INVALID_EXISTING_SOURCE")
        source = NativeAdapter(self.raw, self.source.family)
        source.document.tail += b"x"
        self.error(lambda: ExistingProgram(source, self.schema).check(), "INVALID_EXISTING_SOURCE")
        source = NativeAdapter(self.raw, self.source.family)
        source.document.sections[0].one("ModelName").set_value(b"99")
        self.error(lambda: ExistingProgram(source, self.schema).check(), "INVALID_EXISTING_SOURCE")
        bmp = bytearray(self.source.envelope.thumbnail); bmp[6:10] = b"PDAB"
        other = NativeAdapter(Envelope(bytes(bmp), self.source.envelope.prefix, self.source.envelope.body).encode(self.source.envelope.body), "delta_diascreen")
        self.error(lambda: self.reprogram(other).check(), "INVALID_EXISTING_SOURCE")
        prefix = self.source.envelope.prefix[:37] + bytes(v ^ 0x64 for v in struct.pack("<I", 1))
        bad = NativeAdapter(Envelope(self.source.envelope.thumbnail, prefix, self.source.envelope.body).encode(self.source.envelope.body), self.source.family)
        self.error(lambda: self.reprogram(bad).check(), "CONTROL_BODY_LENGTH")

    def test_full_background_frame_graph_preserved_and_invalid_references_rejected(self):
        a = NativeAdapter(self.raw, self.source.family)
        background = b""
        for index, page in enumerate(_groups(a.document)):
            width = int(page["section"].one("PanelSizeX").value)
            height = int(page["section"].one("PanelSizeY").value)
            offset = str(len(background)).encode()
            page["section"].records.append(Record(b"PictureOffset=" + offset + b"\r\n", "PictureOffset", offset))
            pixels = bytes((index, 127, 255, 255)) * (width * height)
            header = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0, len(pixels), 0, 0, 0, 0)
            background += header + pixels
        a.document.tail = existing_tail(background=background)
        raw = self.source.envelope.encode(a.document.bytes())
        source = NativeAdapter(raw, self.source.family)
        program = self.reprogram(source)
        self.assertTrue(program.check())
        operations = [self.delete(sid, eid, source) for sid, eid in (("1", "11"), ("7", "37"), ("12", "47"))]
        output = NativeAdapter(program.apply(operations), source.family)
        self.assertTrue(program.verify(output, operations))
        self.assertEqual(output.document.tail, source.document.tail)
        self.assertEqual(output.envelope.thumbnail, source.envelope.thumbnail)
        first_header = background[:40]
        for field_index, value in ((0, 108), (1, 101), (2, -100), (3, 2), (4, 24), (5, 1), (6, 1), (7, 1)):
            fields = list(struct.unpack("<IiiHHIIiiII", first_header)); fields[field_index] = value
            changed = self.mutate(first_header, struct.pack("<IiiHHIIiiII", *fields), source)
            self.error(lambda: self.reprogram(changed).check(), "UNQUALIFIED_EXISTING_GRAPH")
        changed = self.mutate(b"PictureOffset=0\r\n", b"PictureOffset=1\r\n", source)
        self.error(lambda: self.reprogram(changed).check(), "UNQUALIFIED_EXISTING_GRAPH")
        pages = _groups(source.document)
        second_offset = pages[1]["section"].one("PictureOffset").value
        changed = self.mutate(b"PictureOffset=" + second_offset + b"\r\n", b"PictureOffset=0\r\n", source)
        self.error(lambda: self.reprogram(changed).check(), "UNQUALIFIED_EXISTING_GRAPH")

    def test_unknown_globals_live_reference_fields_and_capacity_shapes_are_closed(self):
        for before, after in ((b"[Application]\r\n", b"[Application]\r\nUnknownOwnerCount=13\r\n"),
                              (b"nPartsID=21\r\n", b"nPartsID=21\r\nObjectReference=11\r\n"),
                              (b"HistoryCount=0", b"HistoryCount=1"), (b"AlarmCount=0", b"AlarmCount=-1"),
                              (b"AlarmCount=0", b"AlarmCount=01"), (b"AlarmCount=0", b"AlarmCount=32769"),
                              (b"AlarmCount=0\r\n", b"AlarmCount=0\r\nAlarmEnable001=1\r\n"),
                              (b"TagLinkCount=1", b"TagLinkCount=2"),
                              (b"Type=10\r\n", b"Type=10\r\nType=10\r\n"),
                              (b"nPartsID=13", b"nPartsID=11"),
                              (b"[Recipe]\r\n", b"[Recipe]\r\nopaque\r\n")):
            self.error(lambda: self.reprogram(self.mutate(before, after)).check())
        source = self.mutate(b"AlarmCount=0", b"AlarmCount=4096")
        self.assertTrue(self.reprogram(source).check())

    def test_noop_compressed_bytes_are_exact_and_repeated_apply_is_deterministic(self):
        envelope = self.source.envelope
        payload = (envelope.prefix + envelope.body).translate(bytes(i ^ 0x64 for i in range(256)))
        changed = NativeAdapter(envelope.thumbnail + gzip.compress(payload, mtime=9), self.source.family)
        self.assertEqual(changed.envelope, envelope)
        self.assertNotEqual(changed.original, self.raw)
        self.error(lambda: self.program.verify(changed), "EXISTING_PROGRAM_PRESERVATION")
        operations = [self.delete("1", "13")]
        self.assertEqual(self.program.apply(operations), self.program.apply(operations))

    def test_saved_candidate_survivor_resources_page_and_envelope_tamper(self):
        operations = [self.delete(), self.delete("12", "53")]
        candidate = NativeAdapter(self.program.apply(operations), self.source.family)
        for before, after in ((b"X=10", b"X=11"), (b"Style=0", b"Style=1"), (b"nPartsID=21", b"nPartsID=22"),
                              (b"ReadVar={Link2}1@D0", b"ReadVar={Link2}1@D1"), (b"Value=1", b"Value=2"),
                              (b"GoToScreenID=12", b"GoToScreenID=7"), (b"BgColor=16579836", b"BgColor=16579835"),
                              (b"Version=4.00.07.04", b"Version=4.00.07.05"), (b"TagLinkCount=1", b"TagLinkCount=0"),
                              (b"SubMacroPWD001=NEUTRAL8", b"SubMacroPWD001=NEUTRAL9")):
            tampered = self.mutate(before, after, candidate)
            self.error(lambda: self.program.verify(tampered, operations), "EXISTING_PROGRAM_PRESERVATION")
        bmp = bytearray(candidate.envelope.thumbnail); bmp[10] ^= 1
        changed = NativeAdapter(Envelope(bytes(bmp), candidate.envelope.prefix, candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
        self.error(lambda: self.program.verify(changed, operations), "EXISTING_PROGRAM_PRESERVATION")
        prefix = bytes([candidate.envelope.prefix[0] ^ 1]) + candidate.envelope.prefix[1:]
        changed = NativeAdapter(Envelope(candidate.envelope.thumbnail, prefix, candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
        self.error(lambda: self.program.verify(changed, operations), "EXISTING_PROGRAM_PRESERVATION")
        self.error(lambda: self.program.verify(candidate), "EXISTING_PROGRAM_PRESERVATION")
        self.error(lambda: self.program.verify(None, operations), "INVALID_EXISTING_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
