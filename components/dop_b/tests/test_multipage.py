"""Original byte-built multipage adversaries; not vendor qualification."""
from copy import deepcopy
import hashlib
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.multipage import MultiPageProgram, multipage_contract
from test_native import _wide
from test_program import blank_program_fixture, control_operations


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def auxiliary_owner(kind, identity):
    # Original constructed fields. Genuine source proof is separate/private.
    common = (b"[Element]\r\nType=" + {"text": b"10", "indicator": b"2", "goto": b"1"}[kind]
        + b"\r\nSubType=" + {"text": b"6", "indicator": b"1", "goto": b"10"}[kind]
        + b"\r\nX=10\r\nY=10\r\nWidth=30\r\nHeight=20\r\nGroupID=0\r\nStyle=0\r\n"
        b"BorderColor=11842740\r\nPrintSuccessiveData=0\r\nReadMemType=0\r\nWriteMemType=0\r\n"
        b"ReadLink=" + (b"0" if kind == "text" else b"1") + b"\r\nWriteLink=1\r\nReadVar="
        + (b"{Link2}1@M0" if kind == "indicator" else b"None")
        + b"\r\nWriteVar=None\r\nMemLen=" + (b"1" if kind == "text" else b"0")
        + b"\r\nMemFmt=2\r\nLevel=0\r\nOffsetReadMemType=0\r\nOffsetWriteMemType=0\r\n"
        b"OffsetReadVar=None\r\nOffsetWriteVar=None\r\nOffsetMemLen=1\r\nOffsetMemFmt=2\r\nnAngle=0\r\nbFreeze=0\r\n"
        b"nPartsID=" + str(identity).encode() + b"\r\n" + _wide("wDescTextLen0", "Neutral donor"))
    if kind == "text":
        common += b"SmoothFont=1\r\nVisibleLink=1\r\nVisibleVar=None\r\nPosVary=0\r\n"
    elif kind == "indicator":
        common += b"VisibleLink=1\r\nVisibleVar=None\r\n"
    else:
        common += (b"TriggerLink=1\r\nTriggerVar=None\r\nGoToScreenName=Original\r\nGoToScreenID=1\r\n"
            b"CloseScreen=1\r\nVariation=0\r\nOrder=0\r\nCancelActBit=None\r\nSetLowSecurity=0\r\n"
            b"VisibleLink=1\r\nVisibleVar=None\r\nInterLockLink=1\r\nInterLockVar=None\r\nInterLockLevel=1\r\n"
            b"ConFirmWindow=0\r\nNoMessage=0\r\nDispAsterisk=0\r\nBeforeExecMacroLen=0\r\nAfterExecMacroLen=0\r\n")
    for value in (range(2) if kind == "indicator" else range(1)):
        common += (b"[State]\r\nValue=" + str(value).encode()
            + b"\r\nFgColor=11842740\r\nBgColor=11842740\r\nFontColor=0\r\nFontSize0=12\r\nFontRatio0=100\r\n"
            b"FontName0=Arial\r\n" + _wide("wTextLen0", "")
            + b"FontAlign=34\r\nFontBold=0\r\nFontItalic=0\r\nFontUnderline=0\r\nUsePictureCoord=0\r\n"
            b"PictureAlign=34\r\nTransEffect=0\r\nTransColor=0\r\nStretchMode=0\r\nPictureStretch=0\r\nTwinkles=0\r\nSoundIndex=0\r\n")
    return common


def multipage_fixture():
    target_raw, controls_raw, blank_schema = blank_program_fixture()
    target, controls = NativeAdapter(target_raw, "delta_dopsoft2"), NativeAdapter(controls_raw, "delta_dopsoft2")
    page = _groups(target.document)[0]
    header = deepcopy(page["section"])
    header.one("ID").set_value(b"2")
    header.one("wTextLen").set_text("Source_2")
    header.one("wScreenDESCTextLen000").set_text("Source_2")
    header.one("ScreenAction").set_value(b"-123456789")
    globals_raw = b"".join(section.bytes() for section in target.document.sections[:page["start"]])
    # Poisoned resave metadata must never leak from the auxiliary reference.
    globals_raw = globals_raw.replace(b"[Application]\r\n", b"[Application]\r\nHMIPortNr0=1660265583\r\n", 1)
    layout_body = (globals_raw + page["section"].bytes() + target._plain_extent(page).bytes()
        + header.bytes() + b"[AuxKeyElement]\r\n"
        + b"".join(auxiliary_owner(kind, identity) for kind, identity in (("indicator", 1), ("text", 2), ("goto", 3)))
        + controls.document.tail)
    layout_raw = target.envelope.encode(layout_body)
    layout = NativeAdapter(layout_raw, "delta_dopsoft2")
    schema = {key: deepcopy(value) for key, value in blank_schema.items() if key != "blank_program"}
    schema["multipage_program"] = {
        "qualified": True, "contract_version": 1, "mode": "multipage_program",
        "target_sha256": sha(target_raw), "controls_sha256": sha(controls_raw),
        "controls_schema": deepcopy(blank_schema["blank_program"]["library_schema"]),
        "layout_sha256": sha(layout_raw), "authority_sha256": sha(b"SYNTHETIC MULTIPAGE AUTHORITY"),
        "page_donor": {"screen_id": "2", "header_sha256": sha(header.bytes()), "aux_sha256": sha(b"[AuxKeyElement]\r\n")},
        "aux_donors": {kind: {"screen_id": "2", "element_id": str(identity),
            "owner_sha256": layout.owner_extent_sha256("2", str(identity)),
            "property_witness_sha256": sha(("SYNTHETIC PROPERTY " + kind).encode()),
            "match": {"Type": native_type, "SubType": subtype}}
            for kind, identity, native_type, subtype in (("indicator", 1, "2", "1"), ("text", 2, "10", "6"), ("goto", 3, "1", "10"))}}
    return target_raw, controls_raw, layout_raw, schema


def aux(kind, sid, eid, **kwargs):
    result = {"op": "create_aux", "kind": kind, "screen_id": sid, "element_id": eid,
              "x": 10, "y": 40, "width": 30, "height": 20}
    if kind == "indicator":
        result.update(states=[{"value": 0, "text": "KAPALI", "fill": 0x555555},
                              {"value": 1, "text": "AÇIK", "fill": 0x008000}],
                      read={"address": "{Link2}1@M0", "link": 1, "mem_type": 0})
    else:
        result["text"] = "ÖLÇÜM" if kind == "text" else "GERİ"
        if kind == "goto":
            result["target_screen"] = "1"
    result.update(kwargs)
    return result


def mixed_operations(schema):
    blank = {"blank_program": {"library_schema": schema["multipage_program"]["controls_schema"]}}
    operations = control_operations(blank)
    owner_sids = {"20": "1", "21": "2", "22": "3", "23": "3", "24": "2", "25": "3"}
    for operation in operations:
        operation["target_screen" if operation["op"] == "clone_element" else "screen_id"] = owner_sids[operation["element_id"]]
    graph = {"op": "set_program_layout", "screens": [
        {"screen_id": "1", "name": "Original", "elements": ["101", "20", "103"]},
        {"screen_id": "2", "name": "Values", "elements": ["21", "24", "102", "104"]},
        {"screen_id": "3", "name": "Commands", "elements": ["22", "23", "25", "105"]}]}
    return [graph] + operations + [aux("text", "1", "101", font_size=24), aux("indicator", "2", "102", font_size=20),
        aux("goto", "1", "103", target_screen="3"), aux("goto", "2", "104"), aux("goto", "3", "105", target_screen="2")]


class MultiPageTests(unittest.TestCase):
    def setUp(self):
        self.target_raw, self.controls_raw, self.layout_raw, self.schema = multipage_fixture()
        self.target = NativeAdapter(self.target_raw, "delta_dopsoft2")
        self.controls = NativeAdapter(self.controls_raw, "delta_dopsoft2")
        self.layout = NativeAdapter(self.layout_raw, "delta_dopsoft2")
        self.program = MultiPageProgram(self.target, self.controls, self.layout, self.schema)

    def error(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code:
            self.assertEqual(caught.exception.code, code)

    def mutate(self, adapter, before, after):
        self.assertIn(before, adapter.envelope.body)
        return NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(before, after, 1)), adapter.family)

    def output(self):
        return NativeAdapter(self.program.apply(mixed_operations(self.schema)), self.target.family)

    def test_actual_mixed_three_page_graph_types_bindings_states_navigation_and_immutability(self):
        self.assertTrue(self.program.check())
        candidate = self.output()
        self.assertTrue(self.program.verify(candidate))
        pages = _groups(candidate.document)
        self.assertEqual([page["id"] for page in pages], ["1", "2", "3"])
        self.assertEqual([[owner["id"] for owner in page["elements"]] for page in pages],
                         [["101", "20", "103"], ["21", "24", "102", "104"], ["22", "23", "25", "105"]])
        self.assertEqual([page["section"].one("wTextLen").text() for page in pages], ["Original", "Values", "Commands"])
        self.assertEqual(pages[0]["section"].bytes(), _groups(self.target.document)[0]["section"].bytes())
        self.assertEqual([page["section"].one("ScreenAction").value for page in pages[1:]], [b"0", b"0"])
        indicator = pages[1]["elements"][2]
        self.assertEqual(indicator["section"].one("WriteVar").value, b"None")
        self.assertEqual([state.one("wTextLen0").text() for state in indicator["states"]], ["KAPALI", "AÇIK"])
        self.assertEqual([state.one("BgColor").value for state in indicator["states"]], [b"5592405", b"32768"])
        self.assertEqual(pages[0]["elements"][0]["states"][0].one("FontSize0").value, b"24")
        goto = pages[0]["elements"][2]["section"]
        self.assertEqual((goto.one("GoToScreenID").value, goto.one("GoToScreenName").value), (b"3", b"Commands"))
        self.assertEqual(candidate.envelope.thumbnail, self.target.envelope.thumbnail)
        self.assertEqual(candidate._preserved_prefix(candidate.document), self.target._preserved_prefix(self.target.document))
        self.assertNotIn(b"HMIPortNr0=1660265583", candidate.envelope.body)
        self.assertEqual(self.target.original, self.target_raw)
        self.assertEqual(self.controls.original, self.controls_raw)
        self.assertEqual(self.layout.original, self.layout_raw)
        self.assertEqual(self.program.apply(mixed_operations(self.schema)), candidate.original)

    def test_noop_and_empty_graph_preserve_every_byte(self):
        self.assertEqual(self.program.apply([]), self.target_raw)
        self.assertTrue(self.program.verify(self.target))
        graph = {"op": "set_program_layout", "screens": [{"screen_id": "1", "name": "Original", "elements": []}]}
        self.assertEqual(self.program.apply([graph]), self.target_raw)
        self.error(lambda: self.program.apply({}), "INVALID_OPERATIONS")
        self.error(lambda: self.program.verify(None), "INVALID_MULTIPAGE_CANDIDATE")

    def test_text_goto_pages_keep_original_tail_indicator_alone_initializes_owned_tag(self):
        graph = {"op": "set_program_layout", "screens": [
            {"screen_id": "1", "name": "Original", "elements": ["20"]},
            {"screen_id": "2", "name": "Second", "elements": ["21"]}]}
        candidate = NativeAdapter(self.program.apply([graph, aux("goto", "1", "20", target_screen="2"), aux("text", "2", "21")]), self.target.family)
        self.assertEqual(candidate.document.tail, self.target.document.tail)
        graph["screens"][0]["elements"] = ["22"]
        graph["screens"][1]["elements"] = []
        candidate = NativeAdapter(self.program.apply([graph, aux("indicator", "1", "22")]), self.target.family)
        self.assertEqual(candidate.document.tail, self.controls.document.tail)

    def test_page_uint16_name_and_original_header_invariants(self):
        for value in ("0", "65536", "01", "-1", 2, True, [], "9" * 5000):
            operations = mixed_operations(self.schema); operations[0]["screens"][1]["screen_id"] = value
            self.error(lambda: self.program.apply(operations))
        for value in ("", " ÖLÇÜM", "Ölçüm", "Name\nOther", "x" * 257, None, []):
            operations = mixed_operations(self.schema); operations[0]["screens"][1]["name"] = value
            self.error(lambda: self.program.apply(operations), "INVALID_PAGE_NAME")
        for field, value in (("name", "Changed"), ("screen_id", "2")):
            operations = mixed_operations(self.schema); operations[0]["screens"][0][field] = value
            self.error(lambda: self.program.apply(operations), "INVALID_PROGRAM_LAYOUT")
        graph = {"op": "set_program_layout", "screens": [{"screen_id": "1", "name": "Original", "elements": []},
                  {"screen_id": "65535", "name": "Maximum", "elements": ["20"]}]}
        candidate = NativeAdapter(self.program.apply([graph, aux("goto", "65535", "20", target_screen="65535")]), self.target.family)
        self.assertTrue(self.program.verify(candidate))

    def test_exact_graph_births_and_operations_no_missing_extra_duplicate_or_cross_page_edits(self):
        for change in range(6):
            operations = mixed_operations(self.schema)
            if change == 0:
                operations[0]["screens"][1]["elements"].append("20")
            elif change == 1:
                operations[0]["screens"][2]["elements"].append("200")
            elif change == 2:
                operations.append(aux("text", "1", "101"))
            elif change == 3:
                operations[1]["target_screen"] = "3"
            elif change == 4:
                operations.append({"op": "set_property", "screen_id": "1", "element_id": "101", "key": "x", "value": 5})
            else:
                operations.append({"op": "set_program_layout", "screens": []})
            self.error(lambda: self.program.apply(operations))
            self.assertEqual(self.program.apply([]), self.target_raw)
        operations = mixed_operations(self.schema); operations[0]["screens"][0]["elements"][0] = "1"
        self.error(lambda: self.program.apply(operations), "DUPLICATE_ELEMENT")

    def test_aux_kind_state_read_navigation_argument_and_unicode_validation(self):
        graph = {"op": "set_program_layout", "screens": [{"screen_id": "1", "name": "Original", "elements": ["20"]}]}
        mutations = (("read", {"address": "{Link2}1@M0", "link": True, "mem_type": 0}),
            ("read", {"address": "{Link2}1@M1", "link": 1, "mem_type": 0}),
            ("read", {"address": "{Link2}1@M0", "link": 2, "mem_type": 0}),
            ("read", {"address": "{Link2}1@D0", "link": 1, "mem_type": 0}),
            ("states", [{"value": 1, "text": "A", "fill": 0}, {"value": 0, "text": "B", "fill": 0}]),
            ("states", [{"value": 0, "text": "A", "fill": 0}]), ("write", {}), ("font_size", 0),
            ("fill", 0), ("color", 0xFF0000), ("x", -1), ("width", 0), ("height", 100))
        for key, value in mutations:
            operation = aux("indicator", "1", "20"); operation[key] = value
            self.error(lambda: self.program.apply([graph, operation]))
        self.error(lambda: self.program.apply([graph, aux("goto", "1", "20", target_screen="2")]), "UNKNOWN_SCREEN")
        for text in ("\0", "\ud800", "x" * 4097, None, 0):
            self.error(lambda: self.program.apply([graph, aux("text", "1", "20", text=text)]), "INVALID_TEXT")
        candidate = NativeAdapter(self.program.apply([graph, aux("text", "1", "20", text="ÇENE ÖLÇÜMÜ 🔧")]), self.target.family)
        self.assertEqual(_groups(candidate.document)[0]["elements"][0]["states"][0].one("wTextLen0").text(), "ÇENE ÖLÇÜMÜ 🔧")

    def test_saved_new_header_action_id_name_aux_and_reference_corruption_rejected(self):
        candidate = self.output()
        for before, after in ((b"ScreenAction=0\r\n", b"ScreenAction=2\r\n"),
            (b"ID=2\r\n", b"ID=65536\r\n"), (b"GoToScreenID=3", b"GoToScreenID=9"),
            (b"GoToScreenName=Commands", b"GoToScreenName=Other"),
            (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnexpected=1\r\n"),
            (b"DocSizeX=100", b"DocSizeX=101"), (b"ScreenLockVar=None", b"ScreenLockVar={Link2}1@M0")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after)))
        # Change ONLY the appended header action, retaining original page bytes.
        second = _groups(candidate.document)[1]["section"].bytes()
        changed = candidate.envelope.body.replace(second, second.replace(b"ScreenAction=0", b"ScreenAction=-123456789"), 1)
        self.error(lambda: self.program.verify(NativeAdapter(candidate.envelope.encode(changed), candidate.family)), "MULTIPAGE_MISMATCH")

    def test_saved_aux_unmanaged_fields_macros_address_storage_picture_and_state_corruption_rejected(self):
        candidate = self.output()
        page = _groups(candidate.document)[1]
        owner = next(owner for owner in page["elements"] if owner["id"] == "102")
        raw = b"".join(section.bytes() for section in candidate.document.sections[owner["start"]:owner["end"]])
        for before, after in ((b"FontRatio0=100", b"FontRatio0=99"), (b"ReadLink=1", b"ReadLink=2"),
            (b"WriteVar=None", b"WriteVar={Link2}1@M0"), (b"MemLen=0", b"MemLen=1"),
            (b"UsePictureCoord=0", b"UsePictureCoord=1"), (b"Value=1", b"Value=2"),
            (b"VisibleVar=None", b"VisibleVar={Link2}1@M0"),
            (b"[State]\r\n", b"BeforeExecMacroLen=0\r\n[State]\r\n"),
            (b"FontName0=Arial", b"FontName0=Other"), (b"BgColor=32768", b"BgColor=16711680")):
            changed = candidate.envelope.body.replace(raw, raw.replace(before, after, 1), 1)
            self.error(lambda: self.program.verify(NativeAdapter(candidate.envelope.encode(changed), candidate.family)))

    def test_saved_control_reuses_original_strict_guard_and_global_ids(self):
        candidate = self.output()
        for before, after in ((b"nPartsID=22", b"nPartsID=20"), (b"nPartsID=22", b"nPartsID=3"),
            (b"OffVoice=0", b"OffVoice=1"), (b"MinValue=0", b"MinValue=1.5"),
            (b"MaxValue=65535", b"MaxValue=65536"), (b"DotNum=0", b"DotNum=2")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after)))

    def test_global_driver_tail_thumbnail_and_unframed_owner_never_imported_or_changed(self):
        candidate = self.output()
        for before, after in ((b"Version=0.0", b"Version=0.1"),
            (b"TagLinkCount=1\r\nLinkSize=0", b"TagLinkCount=0"),
            (b"NeutralRetained=A", b"NeutralRetained=Changed"),
            (b"[Element]\r\n", b"[Unknown]\r\nX=1\r\n[Element]\r\n")):
            self.error(lambda: self.program.verify(self.mutate(candidate, before, after)))
        bmp = bytearray(candidate.envelope.thumbnail); bmp[10] ^= 1
        output = NativeAdapter(Envelope(bytes(bmp), candidate.envelope.prefix, candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
        self.error(lambda: self.program.verify(output), "MULTIPAGE_MISMATCH")

    def test_contract_source_pins_identity_and_projection_drift_reject_even_noop(self):
        for key, value in (("qualified", 1), ("contract_version", True), ("mode", "blank_program"),
            ("target_sha256", "0" * 64), ("controls_sha256", "a"), ("layout_sha256", "0" * 64),
            ("authority_sha256", "a"), ("controls_schema", {}), ("aux_donors", {}), ("extra", 1)):
            schema = deepcopy(self.schema); schema["multipage_program"][key] = value
            self.error(lambda: MultiPageProgram(self.target, self.controls, self.layout, schema).apply([]))
        for key in ("header_sha256", "aux_sha256"):
            schema = deepcopy(self.schema); schema["multipage_program"]["page_donor"][key] = "0" * 64
            self.error(lambda: MultiPageProgram(self.target, self.controls, self.layout, schema).check(), "INVALID_MULTIPAGE_SOURCE")
        for key in ("owner_sha256", "property_witness_sha256"):
            schema = deepcopy(self.schema); schema["multipage_program"]["aux_donors"]["indicator"][key] = "a"
            self.error(lambda: MultiPageProgram(self.target, self.controls, self.layout, schema).check())
        changed = self.mutate(self.layout, b"Version=0.0", b"Version=0.1")
        schema = deepcopy(self.schema); schema["multipage_program"]["layout_sha256"] = sha(changed.original)
        self.error(lambda: MultiPageProgram(self.target, self.controls, changed, schema).check(), "MULTIPAGE_LINEAGE")
        self.layout.document.tail += b"x"
        self.error(lambda: self.program.check(), "INVALID_MULTIPAGE_SOURCE")

    def test_rehashed_aux_source_still_rejects_active_pages_and_owners(self):
        for before, after in ((b"Hidden=0", b"Hidden=1"),
            (b"ScreenLockVar=None", b"ScreenLockVar={Link2}1@M0"),
            (b"UsePictureCoord=0", b"UsePictureCoord=1"),
            (b"ReadVar={Link2}1@M0", b"ReadVar={Link2}1@M1"),
            (b"MemLen=0", b"MemLen=1"),
            (b"CloseScreen=1", b"CloseScreen=0"),
            (b"BeforeExecMacroLen=0\r\n", b"BeforeExecMacroLen=3\r\nx\r\n")):
            layout = self.mutate(self.layout, before, after)
            schema = deepcopy(self.schema)
            descriptor = schema["multipage_program"]
            descriptor["layout_sha256"] = sha(layout.original)
            page = _groups(layout.document)[1]
            descriptor["page_donor"]["header_sha256"] = sha(page["section"].bytes())
            for pin in descriptor["aux_donors"].values():
                pin["owner_sha256"] = layout.owner_extent_sha256(pin["screen_id"], pin["element_id"])
            # Hidden/lock mutation can hit the unimported page1 rather than
            # page2. Deliberately mutate the selected template explicitly.
            if before.startswith((b"Hidden", b"ScreenLock")):
                header = page["section"].bytes()
                changed = layout.envelope.body.replace(header, header.replace(before, after, 1), 1)
                layout = NativeAdapter(layout.envelope.encode(changed), layout.family)
                descriptor["layout_sha256"] = sha(layout.original)
                descriptor["page_donor"]["header_sha256"] = sha(_groups(layout.document)[1]["section"].bytes())
            self.error(lambda: MultiPageProgram(self.target, self.controls, layout, schema).check())

    def test_page_and_owner_resource_boundaries_are_enforced_before_generation(self):
        graph = {"op": "set_program_layout", "screens": [{"screen_id": "1", "name": "Original", "elements": []}]}
        graph["screens"] += [{"screen_id": str(identity), "name": f"Page_{identity}", "elements": []}
                             for identity in range(2, 257)]
        candidate = NativeAdapter(self.program.apply([graph]), self.target.family)
        self.assertEqual(len(_groups(candidate.document)), 256)
        self.assertTrue(self.program.verify(candidate))
        graph["screens"].append({"screen_id": "257", "name": "Page_257", "elements": []})
        self.error(lambda: self.program.apply([graph]), "INVALID_PROGRAM_LAYOUT")
        graph = {"op": "set_program_layout", "screens": [{"screen_id": "1", "name": "Original",
                  "elements": [str(identity) for identity in range(20, 4117)]}]}
        self.error(lambda: self.program.apply([graph]), "MULTIPAGE_LIMIT")
        self.error(lambda: self.program.apply([{}] * 65537), "INVALID_OPERATIONS")

    def test_cyclic_deep_resource_and_wrong_type_inputs_are_typed_before_copy(self):
        cyclic = {}; cyclic["self"] = cyclic
        for value in (cyclic, None, [], True, {"qualified": True, "multipage_program": cyclic}):
            self.error(lambda: multipage_contract(value))
        deep = {}; current = deep
        for _ in range(100):
            current["next"] = {}; current = current["next"]
        self.error(lambda: multipage_contract(deep), "MULTIPAGE_LIMIT")
        for value in ([{"op": "create_aux"}], [cyclic], [float("inf")], [1 << 500]):
            self.error(lambda: self.program.apply(value))
        for value in (None, [], "adapter"):
            self.error(lambda: MultiPageProgram(value, self.controls, self.layout, self.schema).check(), "INVALID_MULTIPAGE_SOURCE")

    def test_json_container_operation_kind_and_property_keys_are_typed_and_atomic(self):
        before = [(adapter.original, adapter.envelope.body, adapter.document.bytes())
                  for adapter in (self.target, self.controls, self.layout)]
        for field in ("op", "kind", "key"):
            for value in ([], {}):
                with self.subTest(field=field, value_type=type(value).__name__):
                    if field == "key":
                        operations = mixed_operations(self.schema)
                        property_op = next(op for op in operations if op.get("op") == "set_property")
                        property_op["key"] = value
                        code = "INVALID_OPERATION"
                    else:
                        graph = {"op": "set_program_layout", "screens": [
                            {"screen_id": "1", "name": "Original", "elements": ["20"]}]}
                        create = aux("text", "1", "20")
                        create[field] = value
                        operations = [graph, create]
                        code = "PROGRAM_SCOPE" if field == "op" else "INVALID_AUX_OPERATION"
                    outputs = []
                    self.error(lambda: outputs.append(self.program.apply(operations)), code)
                    self.assertEqual(outputs, [])
                    self.assertEqual([(adapter.original, adapter.envelope.body, adapter.document.bytes())
                                      for adapter in (self.target, self.controls, self.layout)], before)


if __name__ == "__main__":
    unittest.main()
