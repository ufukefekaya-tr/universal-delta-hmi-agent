"""Original synthetic blank/library adversaries, never vendor qualification."""
from copy import deepcopy
import hashlib
import struct
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.program import BlankProgram, _tag_extent
from test_native import control_generation_fixture, qualify_control_generation


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def resource_tail(initialized=False, payload=None):
    # Header-looking bytes intentionally live inside framed opaque resources.
    blob = payload if payload is not None else b"[Tag]\r\nTagLinkCount=99\r\nLinkSize=0\r\n"
    return (b"[SubMacro]\r\n[Global_Auxkey]\r\n[Alarm]\r\nVersion=1\r\nAlarmCount=0\r\n"
            b"[History]\r\nHistoryCount=0\r\n[TextBank]\r\nwFont001=Arial\r\n"
            + (b"[Tag]\r\nTagLinkCount=1\r\nLinkSize=0\r\n" if initialized else b"[Tag]\r\nTagLinkCount=0\r\n")
            + b"[EthernetIPTag]\r\nTagTotalSize=0\r\n[SRAM_DATA]\r\n" + struct.pack("<I", len(blob)) + blob + b"\r\n"
            + b"[SysMessage]\0\0\0\r\nLangName0=English\r\n[Picture]\r\nSize=" + str(len(blob)).encode() + b"\r\n" + blob + b"\r\n"
            + b"[Background]\r\nSize=0\r\n\r\n[DeviceTable]\r\nDisplayFormat=0\r\nEnableDownload=0\r\nDisplayLength=0\r\n[END]\r\n")


def repin(target, library, schema):
    result = deepcopy(schema)
    contract = result["blank_program"]
    contract.update(target_sha256=sha(target), library_sha256=sha(library))
    adapter = NativeAdapter(library, "delta_dopsoft2" if library[6:10] == b"\0\0\0\0" else "delta_diascreen")
    profile = {"family": adapter.family, "model_id": adapter.model_id, "editor_version": adapter.editor_version,
               "native_schema": contract["library_schema"]}
    contract["library_schema"] = qualify_control_generation(library, profile)["native_schema"]
    return result


def blank_program_fixture(family="delta_dopsoft2"):
    raw, profile = control_generation_fixture(family)
    adapter = NativeAdapter(raw, family)
    stream = b"".join(section.bytes() for section in adapter.document.sections)
    library = adapter.envelope.encode(stream + resource_tail(True))
    library_profile = qualify_control_generation(library, profile)
    adapter = NativeAdapter(library, family)
    first_page = next(i for i, s in enumerate(adapter.document.sections) if s.name == "Screen")
    target_body = b"".join(section.bytes() for section in adapter.document.sections[:first_page])
    for page in _groups(adapter.document):
        target_body += page["section"].bytes() + adapter._plain_extent(page).bytes()
    target_body += resource_tail(False)
    target = adapter.envelope.encode(target_body)
    schema = deepcopy(library_profile["native_schema"])
    schema.pop("control_generation")
    schema["blank_program"] = {"qualified": True, "contract_version": 1, "mode": "blank_program",
                               "target_sha256": sha(target), "library_sha256": sha(library),
                               "library_schema": deepcopy(library_profile["native_schema"]),
                               "tag_resource": "initialize_empty_source_tag_link"}
    return target, library, schema


def control_operations(schema, kinds=("set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display")):
    result = []
    for index, kind in enumerate(kinds, 20):
        pin = schema["blank_program"]["library_schema"]["control_generation"]["donors"][kind]
        identity = str(index)
        result += [{"op": "clone_element", "source_screen": pin["screen_id"], "source_element": pin["element_id"],
                    "target_screen": "1", "element_id": identity},
                   {"op": "set_property", "screen_id": "1", "element_id": identity, "key": "x", "value": 55}]
        direction = "read" if kind == "numeric_display" else "write"
        address = "{Link2}1@D0" if kind.startswith("numeric_") else "{Link2}1@M0"
        result.append({"op": "bind", "screen_id": "1", "element_id": identity,
                       direction: {"address": address, "link": 1, "mem_type": 0}})
        if kind.startswith("numeric_"):
            op = {"op": "configure_numeric", "screen_id": "1", "element_id": identity, "kind": kind,
                  "data_type": "UINT", "integer_digits": 5, "fractional_digits": 0, "gain": 1, "offset": 0}
            if kind == "numeric_input":
                op.update(minimum=0, maximum=65535)
            result.append(op)
        else:
            result += [{"op": "set_text", "screen_id": "1", "element_id": identity, "state_index": state,
                        "language": 0, "text": "AÇIK" if state else "KAPALI"} for state in (0, 1)]
    return result


class BlankProgramTests(unittest.TestCase):
    def setUp(self):
        self.target_raw, self.library_raw, self.schema = blank_program_fixture()
        self.family = "delta_dopsoft2"
        self.target = NativeAdapter(self.target_raw, self.family)
        self.library = NativeAdapter(self.library_raw, self.family)
        self.program = BlankProgram(self.target, self.library, self.schema)

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code is not None:
            self.assertEqual(caught.exception.code, code)

    def mutate(self, adapter, before, after):
        self.assertIn(before, adapter.envelope.body)
        return NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(before, after, 1)), adapter.family)

    def reprogram(self, target=None, library=None):
        target = target or self.target
        library = library or self.library
        schema = repin(target.original, library.original, self.schema)
        return BlankProgram(target, library, schema)

    def test_both_families_exact_noop_and_clean_six_bound_controls(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            with self.subTest(family=family):
                target_raw, library_raw, schema = blank_program_fixture(family)
                target, library = NativeAdapter(target_raw, family), NativeAdapter(library_raw, family)
                program = BlankProgram(target, library, schema)
                self.assertTrue(program.check())
                self.assertEqual(program.apply([]), target_raw)
                self.assertTrue(program.verify(target))
                output = program.apply(control_operations(schema))
                candidate = NativeAdapter(output, family)
                self.assertTrue(program.verify(candidate))
                owners = _groups(candidate.document)[0]["elements"]
                self.assertEqual([owner["id"] for owner in owners], ["20", "21", "22", "23", "24", "25"])
                self.assertEqual(owners[3]["states"][0].one("wTextLen0").text(), "KAPALI")
                self.assertEqual(owners[3]["states"][1].one("wTextLen0").text(), "AÇIK")
                self.assertEqual(candidate._preserved_prefix(candidate.document), target._preserved_prefix(target.document))
                self.assertEqual(candidate.envelope.thumbnail, target.envelope.thumbnail)
                self.assertEqual(candidate.envelope.prefix[:37], target.envelope.prefix[:37])
                self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
                self.assertEqual(target.original, target_raw)
                self.assertEqual(library.original, library_raw)

    def test_owned_tag_transition_preserves_header_looking_opaque_payloads(self):
        start, end = _tag_extent(self.target.document.tail)
        self.assertEqual(self.target.document.tail[start:end], b"[Tag]\r\nTagLinkCount=0\r\n")
        output = self.program.output_tail(True)
        self.assertEqual(output, self.library.document.tail)
        self.assertEqual(self.program.output_tail(False), self.target.document.tail)
        self.assertEqual(output.count(b"TagLinkCount=99"), 2)
        self.error(lambda: self.program.output_tail(1), "INVALID_PROGRAM_STATE")

    def test_shape_errors_are_typed_and_contract_is_exact(self):
        for value in (None, [], "wrong", True, {}):
            self.error(lambda: BlankProgram(self.target, self.library, value).check())
            broken = deepcopy(self.schema); broken["blank_program"] = value
            self.error(lambda: BlankProgram(self.target, self.library, broken).check())
        for key, value in (("qualified", 1), ("contract_version", True), ("mode", "control_generation"),
                           ("target_sha256", "0" * 64), ("library_sha256", "a"), ("library_schema", None),
                           ("tag_resource", "replace_tag_text"), ("extra", 0)):
            broken = deepcopy(self.schema); broken["blank_program"][key] = value
            self.error(lambda: BlankProgram(self.target, self.library, broken).check())
        for key in ("control_generation", "literal_generation", "preserved_layout"):
            broken = deepcopy(self.schema); broken[key] = {}
            self.error(lambda: BlankProgram(self.target, self.library, broken).check())
        for value in (None, [], "adapter"):
            self.error(lambda: BlankProgram(value, self.library, self.schema).check())
            self.error(lambda: BlankProgram(self.target, value, self.schema).library_profile())
        self.error(lambda: self.program.apply({}), "INVALID_OPERATIONS")
        self.error(lambda: self.program.verify(None), "INVALID_PROGRAM_CANDIDATE")

    def test_library_schema_malformed_or_wrong_profile_rejected(self):
        for field in ("control_generation", "donors", "maintained"):
            for value in (None, []):
                broken = deepcopy(self.schema)
                holder = broken["blank_program"]["library_schema"]
                if field == "donors":
                    holder = holder["control_generation"]
                elif field == "maintained":
                    holder = holder["control_generation"]["donors"]
                holder[field] = value
                self.error(lambda: BlankProgram(self.target, self.library, broken).check())
        broken = deepcopy(self.schema); broken["blank_program"]["library_schema"]["model_id"] = "99"
        self.error(lambda: BlankProgram(self.target, self.library, broken).check(), "PROFILE_MISMATCH")
        broken = deepcopy(self.schema); broken["blank_program"]["library_schema"]["native_candidate"] = {}
        self.error(lambda: BlankProgram(self.target, self.library, broken).check(), "UNQUALIFIED_BLANK_PROGRAM")

    def test_nonempty_target_and_seventh_library_owner_are_rejected(self):
        extra_library_raw = self.library.apply(control_operations(self.schema, ("set_on",)), self.program.library_profile())
        extra_library = NativeAdapter(extra_library_raw, self.family)
        self.error(lambda: self.reprogram(library=extra_library).check(), "INVALID_PROGRAM_LIBRARY")
        output = NativeAdapter(self.program.apply(control_operations(self.schema, ("set_on",))), self.family)
        self.error(lambda: self.reprogram(target=output).check(), "NONEMPTY_PROGRAM_TARGET")

    def test_only_observed_name_and_inline_metadata_save_difference_allowed(self):
        def add_metadata(adapter, name, blob):
            body = adapter.envelope.body.replace(b"[Application]\r\n", b"[Application]\r\nName=" + name + b"\r\nMeMeCode=" + struct.pack("<I", len(blob)) + blob + b"\r\n", 1)
            return NativeAdapter(adapter.envelope.encode(body), adapter.family)
        target = add_metadata(self.target, b"TARGET", b"t\r\n[Screen]\r\n")
        library = add_metadata(self.library, b"LIBRARY", b"l\x00different")
        program = self.reprogram(target, library)
        self.assertTrue(program.check())
        candidate = NativeAdapter(program.apply(control_operations(program.schema, ("set_on",))), self.family)
        self.assertEqual(candidate.application.one("Name").value, b"TARGET")
        self.assertEqual(candidate.application.one("MeMeCode").raw, target.application.one("MeMeCode").raw)
        target = self.mutate(self.target, b"Version=0.0", b"Version=0.1")
        self.error(lambda: self.reprogram(target=target).check(), "PROGRAM_LINEAGE")

    def test_unknown_global_or_native_lineage_changes_fail_even_rehashed(self):
        raw = self.target.envelope.body.replace(b"[Application]\r\n", b"[Application]\r\nUnknownNew=1\r\n", 1)
        target = NativeAdapter(self.target.envelope.encode(raw), self.family)
        self.error(lambda: self.reprogram(target=target).check(), "PROGRAM_LINEAGE")
        changed_prefix = bytes([self.target.envelope.prefix[0] ^ 1]) + self.target.envelope.prefix[1:]
        target = NativeAdapter(Envelope(self.target.envelope.thumbnail, changed_prefix, self.target.envelope.body).encode(self.target.envelope.body), self.family)
        self.error(lambda: self.reprogram(target=target).check(), "PROGRAM_LINEAGE")
        target = self.mutate(self.target, b"DocSizeX=100", b"DocSizeX=101")
        self.error(lambda: self.reprogram(target=target).check(), "PROGRAM_LINEAGE")
        target = self.mutate(self.target, b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnexpected=1\r\n")
        self.error(lambda: self.reprogram(target=target).check())

    def test_source_projection_mutations_and_bad_declared_length_are_rejected(self):
        target = NativeAdapter(self.target_raw, self.family)
        target.document.tail += b"x"
        self.error(lambda: BlankProgram(target, self.library, self.schema).check(), "INVALID_PROGRAM_SOURCE")
        prefix = self.target.envelope.prefix[:37] + bytes(value ^ 0x64 for value in (1).to_bytes(4, "little"))
        raw = Envelope(self.target.envelope.thumbnail, prefix, self.target.envelope.body).encode(self.target.envelope.body)
        target = NativeAdapter(raw, self.family)
        self.error(lambda: self.reprogram(target=target).check(), "CONTROL_BODY_LENGTH")

    def test_nonempty_or_unowned_tag_and_changed_opaque_payload_rejected(self):
        for before, after in ((b"TagLinkCount=0\r\n", b"TagLinkCount=1\r\nLinkSize=0\r\n"),
                              (b"TagLinkCount=0\r\n", b"TagLinkCount=0\r\nExtra=1\r\n"),
                              (b"[Tag]\r\nTagLinkCount=0\r\n", b""),
                              (b"[END]\r\n", b"[UnknownResource]\r\n[END]\r\n")):
            target = self.mutate(self.target, before, after)
            self.error(lambda: self.reprogram(target=target).check())
        target = self.mutate(self.target, b"TagLinkCount=99", b"TagLinkCount=98")
        self.error(lambda: self.reprogram(target=target).check(), "PROGRAM_LINEAGE")
        library = self.mutate(self.library, b"LinkSize=0\r\n[EthernetIPTag]", b"LinkSize=3\r\nx\r\n[EthernetIPTag]")
        self.error(lambda: self.reprogram(library=library).check(), "UNQUALIFIED_PROGRAM_TAG")

    def test_bound_controls_only_fresh_ids_and_exact_metadata(self):
        clone = control_operations(self.schema, ("maintained",))[0]
        self.error(lambda: self.program.apply([clone]), "CONTROL_ADDRESS_SCOPE")
        for identity in ("0", "1", "6", "20"):
            ops = control_operations(self.schema, ("set_on",))
            if identity == "20":
                ops += [clone]
            else:
                ops[0]["element_id"] = identity
            self.error(lambda: self.program.apply(ops), "DUPLICATE_ELEMENT")
        for address in ("{Link2}1@M1", "{Link1}1@M0", "{Link2}2@M0"):
            ops = control_operations(self.schema, ("set_on",)); ops[2]["write"]["address"] = address
            self.error(lambda: self.program.apply(ops), "CONTROL_ADDRESS_SCOPE")
        for field in ("link", "mem_type"):
            ops = control_operations(self.schema, ("set_on",)); ops[2]["write"][field] = 2
            self.error(lambda: self.program.apply(ops), "CONTROL_ADDRESS_SCOPE")
        self.error(lambda: self.program.apply([{"op": "delete_element", "screen_id": "1", "element_id": "1"}]), "CONTROL_GENERATION_SCOPE")

    def test_saved_corruption_unknown_fields_donors_and_unbound_controls_rejected(self):
        candidate = NativeAdapter(self.program.apply(control_operations(self.schema)), self.family)
        for before, after in ((b"Style=0\r\n", b"Style=1\r\n"), (b"ReadMemType=0", b"ReadMemType=1"),
                              (b"FontName0=Arial", b"FontName0=Other"), (b"VisibleVar=None", b"VisibleVar={Link2}1@M0"),
                              (b"SoundIndex=0", b"SoundIndex=1"), (b"nPartsID=20", b"nPartsID=1"),
                              (b"WriteVar={Link2}1@M0", b"WriteVar=None"), (b"Value=1", b"Value=2")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after)))
        # Retaining a source donor in a supposedly clean program is forbidden.
        page = _groups(candidate.document)[0]
        old = _groups(self.library.document)[0]["elements"][0]
        donor = b"".join(s.bytes() for s in self.library.document.sections[old["start"]:old["end"]])
        body = candidate.envelope.body.replace(page["section"].bytes() + b"[AuxKeyElement]\r\n",
                                               page["section"].bytes() + b"[AuxKeyElement]\r\n" + donor, 1)
        self.error(lambda: self.program.verify(NativeAdapter(candidate.envelope.encode(body), self.family)), "DUPLICATE_ELEMENT")

    def test_candidate_target_globals_tail_thumbnail_page_are_exact(self):
        candidate = NativeAdapter(self.program.apply(control_operations(self.schema)), self.family)
        for before, after in ((b"Version=0.0", b"Version=0.1"), (b"DocSizeX=100", b"DocSizeX=101"),
                              (b"TagLinkCount=1\r\nLinkSize=0\r\n", b"TagLinkCount=0\r\n"),
                              (b"TagLinkCount=99", b"TagLinkCount=98"),
                              (b"[Application]\r\n", b"[Application]\r\nUnknownNew=1\r\n")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after)))
        bmp = bytearray(candidate.envelope.thumbnail); bmp[10] ^= 1
        output = NativeAdapter(Envelope(bytes(bmp), candidate.envelope.prefix, candidate.envelope.body).encode(candidate.envelope.body), self.family)
        self.error(lambda: self.program.verify(output), "PROGRAM_MISMATCH")


if __name__ == "__main__":
    unittest.main()
