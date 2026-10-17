"""Original neutral resource fixtures; no vendor payload or artwork."""
from copy import deepcopy
import hashlib
import struct
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native.codec import Envelope
from universal_hmi.native.records import Document
from universal_hmi.native.resources import ResourceTables, alarm_ir_operations, expected_alarm_tail, alarm_view_context


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wide(key, text):
    blob = text.encode("utf-16-le") + b"\0\0"
    return key.encode() + b"=" + str(len(blob)).encode() + b"\r\n" + blob + b"\r\n"


def fixture(suffix=b"[History]\r\nHistoryCount=0\r\n[END]\r\n", prefix=b""):
    data = prefix + b"[Alarm]\r\nVersion=16\r\nAlarmCount=8\r\nContinueAddr=0\r\nReadAlarmLink=1\r\nSampleCycle=0.500000\r\nRecordNumber=10\r\nHold=0\r\nAlmHoldPlace=0\r\n"
    for index in ("001", "002"):
        data += (f"AlarmEnable{index}=1\r\nAlarmVar{index}=$10\r\nAlarmMemLen{index}=2\r\nAlarmTriggerFmt{index}=2\r\nAlarmTriggerIntNum{index}=5\r\nAlarmTriggerDotNum{index}=0\r\nAlarmTriggerCount{index}=1\r\nAlarmTriggerOperator{index}-001=3\r\nAlarmTriggerMin{index}-001=0\r\nAlarmTriggerMax{index}-001=10\r\n".encode())
        data += wide(f"wMessageLen{index}-0", "Fault " + index)
    return data + b"Unknown=A\r\nUnknown=B\r\n" + suffix


def guards(table, index):
    keys = ["ContinueAddr", "ReadAlarmLink", "AlarmVar" + index,
            "AlarmMemLen" + index, "AlarmTriggerFmt" + index,
            "AlarmTriggerIntNum" + index, "AlarmTriggerDotNum" + index,
            "AlarmTriggerCount" + index, "AlarmEnable" + index,
            "AlarmTriggerOperator" + index + "-001"]
    return {key: table.alarm.one(key).value.decode() for key in keys}


def schema(table):
    fields = {}
    for index in ("001", "002"):
        fields["AlarmEnable" + index] = {"kind": "enum", "values": ["0", "1"], "preconditions": guards(table, index)}
        fields["wMessageLen" + index + "-0"] = {"kind": "text", "max_bytes": 128, "preconditions": {"AlarmEnable" + index: "1"}}
        pair = {"minimum_field": "AlarmTriggerMin" + index + "-001", "maximum_field": "AlarmTriggerMax" + index + "-001", "operator_field": "AlarmTriggerOperator" + index + "-001", "operator_value": "3", "relation": "ordered"}
        for kind in ("Min", "Max"):
            fields["AlarmTrigger" + kind + index + "-001"] = {"kind": "integer", "minimum": "0", "maximum": "65535", "storage": {"bits": 16, "format": "unsigned"}, "pair": pair, "preconditions": guards(table, index)}
    fields["SampleCycle"] = {"kind": "decimal", "minimum": "0.1", "maximum": "10", "preconditions": {"RecordNumber": "10"}}
    return {"alarm": {"qualified": True, "version": "16", "donor_tail_sha256": sha(table.original), "suffix_sha256": sha(table.suffix), "fields": fields}}


def operation(table, updates):
    return {"op": "configure_alarm", "expected_alarm_sha256": sha(table.alarm.bytes()), "updates": [{"field": key, "value": value} for key, value in updates]}


def alarm_bool_tail():
    """Wholly original BOOL resource data, including unrelated history/text."""
    data = (b"[SubMacro]\r\nSubMacroCount=0\r\n[Global_Auxkey]\r\n"
            b"[Alarm]\r\nVersion=16\r\nAlarmCount=8\r\nContinueAddr=0\r\nReadAlarmLink=1\r\n"
            b"SampleCycle=0.500000\r\nRecordNumber=10\r\nHold=0\r\nAlmHoldPlace=0\r\n")
    for index, letter in (("001", "A"), ("002", "B")):
        data += (f"AlarmEnable{index}=1\r\nAlarmVar{index}=DEMO.ALARM_{letter}\r\nAlarmOn{index}=1\r\n"
                 f"AlarmMemLen{index}=1\r\nAlarmScreenID{index}=1\r\n").encode()
        data += wide(f"wMessageLen{index}-0", "Fault " + letter)
        data += wide(f"wMessageLen{index}-1", "Other language " + letter)
    data += b"AlarmEnable003=0\r\n" + wide("wMessageLen003-0", "Disabled donor")
    data += b"Unknown=A\r\nUnknown=B\r\n"
    return (data + b"[History]\r\nHistoryCount=1\r\nReadVar001=DEMO.TREND_UINT\r\nReadMemLen001=2\r\n"
            b"Hold001=1\r\nTimeFmt001=0\r\nDateFmt001=4\r\n" + wide("ColumnLen001", "Retained trend") + b"[END]\r\n")


def alarm_public_fixture(family="delta_diascreen"):
    """Return (source bytes, native_schema, alarm IR, tags), never vendor data.

    Both original envelopes use SYNTHETIC/0.0 and a 100 by 80 page. Source
    donors 10/11/12 are inert current/history/strip owners with original bytes.
    """
    header = bytearray(54)
    header[:2] = b"BM"
    header[6:10] = b"PDAB" if family == "delta_diascreen" else b"\0" * 4
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<I", header, 34, 4)
    body = (b"[Application]\r\nModelName=SYNTHETIC\r\nVersion=0.0\r\nPanelName=Original alarm fixture\r\n"
            b"[Screen]\r\nVER=16\r\nID=1\r\n" + wide("wTextLen", "Alarm page")
            + b"DocSizeX=100\r\nDocSizeY=80\r\nPanelSizeX=100\r\nPanelSizeY=80\r\n[AuxKeyElement]\r\n")
    for eid, subtype, y, height in (("10", "2", 5, 20), ("11", "1", 30, 20), ("12", "4", 55, 15)):
        body += (f"[Element]\r\nnPartsID={eid}\r\nType=11\r\nSubType={subtype}\r\nX=5\r\nY={y}\r\nWidth=90\r\nHeight={height}\r\n"
                 "ReadVar=None\r\nReadLink=1\r\nReadMemType=0\r\nWriteVar=None\r\nWriteLink=1\r\nWriteMemType=0\r\n"
                 "GroupIDVar=None\r\nEventCtrlVar=None\r\nSortCtrlVar=None\r\nSortOrderCtrlVar=None\r\nFilterCtrlVar=None\r\n"
                 "FreqFilterVar=None\r\nCategoryStartVar=None\r\nCategoryEndVar=None\r\nRelatedFileBrowserPartID=-1\r\n"
                 "FunctionKeyPartID0=-1\r\nFunctionKeyPartID1=-1\r\nShowTime=1\r\nTimeFmt=0\r\nShowDate=1\r\nDateFmt=4\r\n"
                 "BeforeExecMacroLen=0\r\nUnknownPresentation=A\r\nUnknownPresentation=B\r\n").encode()
        if subtype == "4":
            body += b"MoveCount=2\r\nMoveTime=300\r\nDirection=1\r\nEnableGroupID=10\r\n"
        else:
            body += b"EnableGroupIDFilter=0\r\nEnableCol0=1\r\nDisplayOrder0=0\r\nColWidth0=70\r\n"
            body += wide("TitleTextLen0-0", "Message") + wide("TitleTextLen0-1", "Other title")
        body += (b"[State]\r\nValue=0\r\nFontColor=0\r\nFontSize0=12\r\n" + wide("wTextLen0", "")
                 + b"StateUnknown=retained\r\n[State]\r\nValue=1\r\nX=777\r\nFontColor=1\r\n" + wide("wTextLen0", ""))
    tail = alarm_bool_tail()
    document = Document.parse(body + tail)
    table = ResourceTables.parse(tail)
    native_schema = {
        "qualified": True, "cloning": True,
        "properties": {key.lower(): {"field": key, "type": "int", "min": 0, "max": 100}
                       for key in ("X", "Y", "Width", "Height")},
        "kinds": {"alarm_table": {"Type": "11", "SubType": "2"}, "alarm_history": {"Type": "11", "SubType": "1"},
                  "alarm_strip": {"Type": "11", "SubType": "4"}},
        "donors": {kind: {"screen_id": "1", "element_id": eid}
                   for kind, eid in (("alarm_table", "10"), ("alarm_history", "11"), ("alarm_strip", "12"))},
        "alarm": {"qualified": True, "version": "16", "donor_tail_sha256": sha(tail),
                  "suffix_sha256": sha(table.suffix), "fields": {}},
        "alarm_ir": {"qualified": True, "contract_version": 1, "mode": "existing_bool_message", "coverage": "all_enabled", "entries": {}},
        "alarm_views": {"qualified": True, "contract_version": 1, "mode": "preserve_source", "owners": []}}
    alarms, tags = [], []
    for index, letter in (("001", "A"), ("002", "B")):
        aid, tid, field = "fault_" + letter.lower(), "alarm_" + letter.lower(), "wMessageLen" + index + "-0"
        guard_keys = ("ContinueAddr", "ReadAlarmLink", "AlarmEnable" + index, "AlarmVar" + index, "AlarmOn" + index, "AlarmMemLen" + index)
        pinned = {key: table.alarm.one(key).value.decode() for key in guard_keys}
        engineering = {"data_type": "BOOL", "channel": "SIM", "station": "0", "byte_order": "little", "word_order": "little"}
        binding = {"link": "1", "mem_type": "0"}
        native_schema["alarm_ir"]["entries"][aid] = {
            "index": index, "message_field": field, "message_record_sha256": sha(table.alarm.one(field).raw),
            "trigger": {"mode": "direct_bool", "active_value": 1, "link_owner": "global", "preconditions": pinned,
                        "storage": {"bits": 1, "format": "bit", "native_mem_len": "1"}},
            "tag_contract": engineering, "native_binding": binding}
        native_schema["alarm"]["fields"][field] = {"kind": "text", "max_bytes": 128, "preconditions": deepcopy(pinned)}
        alarms.append({"id": aid, "tag": tid, "text": table.alarm.one(field).text(), "history_policy": "preserve_source"})
        tags.append({"id": tid, "address": pinned["AlarmVar" + index], "access": "Read", **engineering, "native_binding": deepcopy(binding)})
    for kind, eid in (("alarm_table", "10"), ("alarm_history", "11"), ("alarm_strip", "12")):
        native_schema["alarm_views"]["owners"].append({"screen_id": "1", "element_id": eid, "kind": kind,
                                                    "owner_sha256": alarm_view_context(document, "1", eid)["owner_sha256"]})
    return Envelope(bytes(header) + b"PIXL", bytes(range(41)), b"").encode(body + tail), native_schema, alarms, tags


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.table = ResourceTables.parse(self.data)
        self.contract = schema(self.table)

    def assertError(self, code, call):
        with self.assertRaises(HmiError) as error:
            call()
        self.assertEqual(code, error.exception.code)

    def test_noop_preserves_every_byte(self):
        self.assertEqual(self.data, self.table.bytes())

    def test_capacity_entries_and_enabled_are_separate(self):
        report = self.table.inspect()
        self.assertEqual((8, 2, 2), (report["capacity"], report["serialized_entry_count"], report["enabled_entry_count"]))
        self.assertEqual("UNVERIFIED", report["semantic_qualification"])

    def test_missing_capacity_is_not_zero(self):
        report = ResourceTables.parse(self.data.replace(b"AlarmCount=8\r\n", b"")).inspect()
        self.assertIsNone(report["capacity"])

    def test_missing_capacity_keeps_mutation_closed(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmCount=8\r\n", b""))
        self.assertError("UNQUALIFIED_ALARM", lambda: table.apply(operation(table, [("AlarmEnable001", 0)]), schema(table)))

    def test_no_suffix_proves_complete_ownership(self):
        self.assertTrue(ResourceTables.parse(fixture(b"")).inspect()["suffix_parsed"])

    def test_unknown_repeated_fields_are_preserved(self):
        result = self.table.apply(operation(self.table, [("wMessageLen001-0", "New")]), self.contract)
        self.assertIn(b"Unknown=A\r\nUnknown=B\r\n", result)

    def test_message_changes_only_exact_record(self):
        before = self.table.alarm.one("wMessageLen001-0").raw
        result = self.table.apply(operation(self.table, [("wMessageLen001-0", "Arıza — ölçü 🙂")]), self.contract)
        self.assertEqual(result, self.data.replace(before, wide("wMessageLen001-0", "Arıza — ölçü 🙂"), 1))
        self.assertEqual(self.data, self.table.bytes())

    def test_message_unicode_nul_rejected(self):
        self.assertError("RESOURCE_TEXT", lambda: self.table.apply(operation(self.table, [("wMessageLen001-0", "a\0b")]), self.contract))

    def test_message_invalid_surrogate_rejected(self):
        self.assertError("RESOURCE_TEXT", lambda: self.table.apply(operation(self.table, [("wMessageLen001-0", "\ud800")]), self.contract))

    def test_message_byte_limit(self):
        self.assertError("RESOURCE_TEXT", lambda: self.table.apply(operation(self.table, [("wMessageLen001-0", "x" * 80)]), self.contract))

    def test_message_same_text_is_byte_noop(self):
        self.assertEqual(self.data, self.table.apply(operation(self.table, [("wMessageLen001-0", "Fault 001")]), self.contract))

    def test_message_must_pin_existing_entry(self):
        self.contract["alarm"]["fields"]["wMessageLen001-0"]["preconditions"] = {"Version": "16"}
        self.assertError("ALARM_PRECONDITION", lambda: self.table.apply(operation(self.table, [("wMessageLen001-0", "x")]), self.contract))

    def test_two_indexes_one_transaction(self):
        result = self.table.apply(operation(self.table, [("AlarmEnable001", 0), ("AlarmEnable002", 0)]), self.contract)
        self.assertEqual(0, ResourceTables.parse(result).inspect()["enabled_entry_count"])
        self.assertEqual(self.data, self.table.bytes())

    def test_duplicate_updates_rejected(self):
        self.assertError("INVALID_ALARM_OPERATION", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0), ("AlarmEnable001", 1)]), self.contract))

    def test_failed_batch_is_atomic(self):
        self.assertError("INVALID_ALARM_VALUE", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0), ("AlarmEnable002", 2)]), self.contract))
        self.assertEqual(self.data, self.table.bytes())

    def test_disabled_existing_entry_is_not_missing(self):
        data = self.data.replace(b"AlarmEnable001=1", b"AlarmEnable001=0")
        table = ResourceTables.parse(data)
        contract = schema(table)
        result = table.apply(operation(table, [("AlarmEnable001", 1)]), contract)
        self.assertEqual(2, ResourceTables.parse(result).inspect()["enabled_entry_count"])

    def test_absent_index_never_synthesized(self):
        self.contract["alarm"]["fields"]["AlarmEnable003"] = self.contract["alarm"]["fields"]["AlarmEnable001"]
        self.assertError("MISSING_NATIVE_FIELD", lambda: self.table.apply(operation(self.table, [("AlarmEnable003", 1)]), self.contract))

    def test_unbound_trigger_rejected(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmVar001=$10", b"AlarmVar001=None"))
        self.assertError("UNQUALIFIED_ALARM", lambda: table.apply(operation(table, [("AlarmEnable001", 0)]), schema(table)))

    def test_address_guard_is_required(self):
        del self.contract["alarm"]["fields"]["AlarmEnable001"]["preconditions"]["AlarmVar001"]
        self.assertError("ALARM_PRECONDITION", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0)]), self.contract))

    def test_stale_donor_rejected(self):
        self.contract["alarm"]["donor_tail_sha256"] = "0" * 64
        self.assertError("ALARM_PROVENANCE", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0)]), self.contract))

    def test_stale_alarm_rejected(self):
        op = operation(self.table, [("AlarmEnable001", 0)])
        op["expected_alarm_sha256"] = "0" * 64
        self.assertError("ALARM_SOURCE_CHANGED", lambda: self.table.apply(op, self.contract))

    def test_empty_updates_never_qualify(self):
        self.assertError("INVALID_ALARM_OPERATION", lambda: self.table.apply(operation(self.table, []), self.contract))

    def test_qualified_flag_alone_is_insufficient(self):
        self.assertError("ALARM_PROVENANCE", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0)]), {"alarm": {"qualified": True}}))

    def test_unknown_suffix_is_read_only_even_with_exact_hash(self):
        table = ResourceTables.parse(fixture(b"[SlotFile]\r\nSize=0\r\n[END]\r\n"))
        self.assertFalse(table.inspect()["suffix_parsed"])
        self.assertError("UNQUALIFIED_ALARM_SUFFIX", lambda: table.apply(operation(table, [("AlarmEnable001", 0)]), schema(table)))

    def test_missing_end_suffix_is_read_only(self):
        table = ResourceTables.parse(fixture(b"[History]\r\nHistoryCount=0\r\n"))
        self.assertFalse(table.inspect()["suffix_parsed"])

    def test_duplicate_alarm_after_history_rejected(self):
        self.assertError("RESOURCE_ORDER", lambda: ResourceTables.parse(fixture(b"[History]\r\nHistoryCount=0\r\n[Alarm]\r\n")))

    def test_duplicate_alarm_after_picture_rejected(self):
        self.assertError("RESOURCE_ORDER", lambda: ResourceTables.parse(fixture(b"[Picture]\r\nSize=0\r\n\r\n[Alarm]\r\n")))

    def test_duplicate_after_end_rejected(self):
        self.assertError("RESOURCE_ORDER", lambda: ResourceTables.parse(self.data + b"[Alarm]\r\n"))

    def test_fake_headers_inside_macro_are_skipped(self):
        blob = b"[Alarm]\r\n[History]\r\n"
        prefix = b"[SubMacro]\r\nSubMacroLen001=" + str(len(blob)).encode() + b"\r\n" + blob + b"[Global_Auxkey]\r\n"
        data = fixture(prefix=prefix)
        self.assertEqual(data, ResourceTables.parse(data).bytes())

    def test_fake_headers_inside_picture_and_database_are_skipped(self):
        blob = b"[Alarm]\r\n[END]\r\n"
        suffix = b"[100_SRAM_DATA]\r\n" + struct.pack("<I", len(blob)) + blob + b"\r\n[Picture]\r\nSize=" + str(len(blob)).encode() + b"\r\n" + blob + b"\r\n[END]\r\n"
        table = ResourceTables.parse(fixture(suffix))
        self.assertTrue(table.inspect()["suffix_parsed"])
        self.assertEqual(fixture(suffix), table.bytes())

    def test_history_column_is_a_wide_frame(self):
        suffix = b"[History]\r\n" + wide("ColumnLen01", "Time") + b"ColumnReadLen01=0\r\n[END]\r\n"
        table = ResourceTables.parse(fixture(suffix))
        self.assertTrue(table.inspect()["suffix_parsed"])

    def test_tag_link_includes_crlf(self):
        blob = b"[Alarm]\r\n"
        suffix = b"[Tag]\r\nLinkSize=" + str(len(blob)).encode() + b"\r\n" + blob + b"[END]\r\n"
        self.assertTrue(ResourceTables.parse(fixture(suffix)).inspect()["suffix_parsed"])

    def test_tag_link_missing_crlf_rejected(self):
        self.assertError("RESOURCE_FRAME", lambda: ResourceTables.parse(fixture(b"[Tag]\r\nLinkSize=3\r\nabc[END]\r\n")))

    def test_nonzero_unqualified_tag_resources_are_readonly(self):
        for suffix in (b"[DIATag]\r\nDIATagResource=1\r\n[END]\r\n", b"[DeviceTable]\r\nDisplayLength=2\r\n[END]\r\n", b"[EthernetIPTag]\r\nTagTotalSize=9\r\n[END]\r\n"):
            with self.subTest(suffix=suffix):
                self.assertFalse(ResourceTables.parse(fixture(suffix)).inspect()["suffix_parsed"])

    def test_special_system_message_header(self):
        self.assertTrue(ResourceTables.parse(fixture(b"[SysMessage]\0\0\0\r\nLangName0=Neutral\r\n[END]\r\n")).inspect()["suffix_parsed"])

    def test_unknown_preceding_section_rejected(self):
        self.assertError("UNSUPPORTED_RESOURCE_SECTION", lambda: ResourceTables.parse(b"[Alien]\r\n" + self.data))

    def test_populated_auxkey_unqualified(self):
        self.assertError("UNSUPPORTED_RESOURCE_FRAME", lambda: ResourceTables.parse(b"[Global_Auxkey]\r\nKey=1\r\n" + self.data))

    def test_repeated_controlled_field_rejected(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmEnable001=1", b"AlarmEnable001=1\r\nAlarmEnable001=0"))
        self.assertError("AMBIGUOUS_FIELD", table.inspect)

    def test_numeric_index_alias_rejected(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmEnable002=1", b"AlarmEnable0001=1"))
        self.assertError("AMBIGUOUS_ALARM_INDEX", table.inspect)

    def test_capacity_violation_rejected(self):
        self.assertError("RESOURCE_CAPACITY", lambda: ResourceTables.parse(self.data.replace(b"AlarmCount=8", b"AlarmCount=1")).inspect())

    def test_negative_frame_length_rejected(self):
        self.assertError("NATIVE_FRAME", lambda: ResourceTables.parse(self.data.replace(b"wMessageLen001-0=20", b"wMessageLen001-0=-2")))

    def test_huge_frame_length_rejected(self):
        self.assertError("NATIVE_LIMIT", lambda: ResourceTables.parse(self.data.replace(b"wMessageLen001-0=20", b"wMessageLen001-0=" + b"9" * 5000)))

    def test_odd_utf16_rejected(self):
        data = self.data.replace(wide("wMessageLen001-0", "Fault 001"), b"wMessageLen001-0=3\r\na\0\0\r\n")
        self.assertError("RESOURCE_TEXT", lambda: ResourceTables.parse(data))

    def test_invalid_utf16_rejected(self):
        data = self.data.replace(wide("wMessageLen001-0", "Fault 001"), b"wMessageLen001-0=4\r\n\x00\xd8\0\0\r\n")
        self.assertError("RESOURCE_TEXT", lambda: ResourceTables.parse(data))

    def test_embedded_utf16_nul_rejected(self):
        data = self.data.replace(wide("wMessageLen001-0", "Fault 001"), wide("wMessageLen001-0", "x\0y"))
        self.assertError("RESOURCE_TEXT", lambda: ResourceTables.parse(data))

    def test_truncated_database_rejected(self):
        self.assertError("RESOURCE_FRAME", lambda: ResourceTables.parse(fixture(b"[100_SRAM_DATA]\r\n" + struct.pack("<I", 100) + b"abc")))

    def test_missing_picture_crlf_rejected(self):
        self.assertError("RESOURCE_FRAME", lambda: ResourceTables.parse(fixture(b"[Picture]\r\nSize=0\r\n[END]\r\n")))

    def test_same_decimal_retains_vendor_spelling(self):
        self.assertEqual(self.data, self.table.apply(operation(self.table, [("SampleCycle", "0.5")]), self.contract))

    def test_typed_limit_change(self):
        result = self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", 20)]), self.contract)
        self.assertEqual(b"20", ResourceTables.parse(result).alarm.one("AlarmTriggerMax001-001").value)

    def test_pair_range_may_change_together(self):
        result = self.table.apply(operation(self.table, [("AlarmTriggerMin001-001", 20), ("AlarmTriggerMax001-001", 30)]), self.contract)
        self.assertEqual(b"20", ResourceTables.parse(result).alarm.one("AlarmTriggerMin001-001").value)

    def test_pair_range_inversion_rejected(self):
        self.assertError("INVALID_ALARM_RANGE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMin001-001", 20)]), self.contract))

    def test_missing_pair_mapping_rejected(self):
        del self.contract["alarm"]["fields"]["AlarmTriggerMax001-001"]["pair"]
        self.assertError("UNQUALIFIED_ALARM_RANGE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", 20)]), self.contract))

    def test_wrong_pair_index_rejected(self):
        self.contract["alarm"]["fields"]["AlarmTriggerMax001-001"]["pair"]["minimum_field"] = "AlarmTriggerMin002-001"
        self.assertError("UNQUALIFIED_ALARM_RANGE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", 20)]), self.contract))

    def test_width_limit_rejected(self):
        self.assertError("INVALID_ALARM_VALUE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", 65536)]), self.contract))

    def test_float_underflow_rejected(self):
        spec = self.contract["alarm"]["fields"]["AlarmTriggerMax001-001"]
        spec.update(kind="decimal", minimum="0", maximum="100", storage={"bits": 32, "format": "floating"})
        self.assertError("INVALID_ALARM_VALUE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", "1e-80")]), self.contract))

    def test_unknown_ascii_size_suffix_cannot_qualify(self):
        table = ResourceTables.parse(fixture(b"[Picture]\r\nMysterySize=5\r\nabcde\r\n[END]\r\n"))
        self.assertFalse(table.inspect()["suffix_parsed"])
        self.assertError("UNQUALIFIED_ALARM_SUFFIX", lambda: table.apply(operation(table, [("AlarmEnable001", 0)]), schema(table)))

    def test_unknown_ascii_scalar_suffix_cannot_qualify(self):
        self.assertFalse(ResourceTables.parse(fixture(b"[History]\r\nAlien=0\r\n[END]\r\n")).inspect()["suffix_parsed"])

    def test_retained_pair_limit_width_is_checked(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmTriggerMax001-001=10", b"AlarmTriggerMax001-001=65536"))
        contract = schema(table)
        for field in ("AlarmTriggerMin001-001", "AlarmTriggerMax001-001"):
            contract["alarm"]["fields"][field]["maximum"] = "100000"
        self.assertError("INVALID_ALARM_VALUE", lambda: table.apply(operation(table, [("AlarmTriggerMin001-001", 1)]), contract))

    def test_conflicting_pair_storage_is_rejected(self):
        self.contract["alarm"]["fields"]["AlarmTriggerMin001-001"].update(kind="decimal", storage={"bits": 32, "format": "floating"})
        self.assertError("UNQUALIFIED_ALARM_RANGE", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMin001-001", "0.1"), ("AlarmTriggerMax001-001", 20)]), self.contract))

    def test_unhashable_storage_values_fail_explicitly(self):
        for key, value in (("bits", []), ("format", {})):
            with self.subTest(key=key):
                contract = deepcopy(self.contract)
                contract["alarm"]["fields"]["AlarmTriggerMax001-001"]["storage"][key] = value
                self.assertError("INVALID_ALARM_SCHEMA", lambda: self.table.apply(operation(self.table, [("AlarmTriggerMax001-001", 20)]), contract))

    def test_unhashable_scalar_kind_fails_explicitly(self):
        self.contract["alarm"]["fields"]["AlarmEnable001"]["kind"] = []
        self.assertError("INVALID_ALARM_SCHEMA", lambda: self.table.apply(operation(self.table, [("AlarmEnable001", 0)]), self.contract))

    def test_trigger_count_must_match_serialized_triplets(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmTriggerCount001=1", b"AlarmTriggerCount001=2"))
        self.assertError("RESOURCE_TRIGGER_COUNT", table.inspect)

    def test_extra_subtrigger_is_not_hidden_by_count(self):
        extra = b"AlarmTriggerOperator001-002=3\r\nAlarmTriggerMin001-002=0\r\nAlarmTriggerMax001-002=5\r\n"
        table = ResourceTables.parse(self.data.replace(b"Unknown=A", extra + b"Unknown=A"))
        self.assertError("RESOURCE_TRIGGER_COUNT", table.inspect)

    def test_duplicate_trigger_scalar_is_rejected(self):
        table = ResourceTables.parse(self.data.replace(b"AlarmTriggerMax001-001=10", b"AlarmTriggerMax001-001=10\r\nAlarmTriggerMax001-001=11"))
        self.assertError("AMBIGUOUS_ALARM_TRIGGER", table.inspect)


class PublicAlarmTests(unittest.TestCase):
    def setUp(self):
        self.source, self.contract, self.alarms, self.tags = alarm_public_fixture()
        self.document = Document.parse(Envelope.decode(self.source, "delta_diascreen").body)
        self.tail = self.document.tail

    def assertError(self, code, call):
        with self.assertRaises(HmiError) as raised:
            call()
        if code is not None:
            self.assertEqual(code, raised.exception.code)

    def operations(self):
        return alarm_ir_operations(self.tail, self.alarms, self.tags, self.contract)

    def requalify(self, tail):
        """Explicitly pin invented alternate source bytes for negative tests."""
        self.tail = tail
        table = ResourceTables.parse(tail)
        self.contract["alarm"].update(donor_tail_sha256=sha(tail), suffix_sha256=sha(table.suffix))
        for entry in self.contract["alarm_ir"]["entries"].values():
            field = entry["message_field"]
            entry["message_record_sha256"] = sha(table.alarm.one(field).raw)
            guards = entry["trigger"]["preconditions"]
            for key in guards:
                record = table.alarm.one(key, False)
                if record is not None:
                    guards[key] = record.value.decode()
            self.contract["alarm"]["fields"][field]["preconditions"] = deepcopy(guards)

    def test_both_envelopes_candidate_changes_only_one_primary_message(self):
        from universal_hmi.native import NativeAdapter
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                source, schema, alarms, tags = alarm_public_fixture(family)
                adapter = NativeAdapter(source, family)
                original = adapter.document.tail
                alarms[0]["text"] = "Neutral changed message"
                operations = alarm_ir_operations(original, alarms, tags, schema)
                self.assertEqual(operations[0]["updates"], [{"field": "wMessageLen001-0", "value": "Neutral changed message"}])
                result = adapter.apply(operations, {"family": family, "model_id": "SYNTHETIC", "editor_version": "0.0", "native_schema": schema})
                candidate = NativeAdapter(result, family)
                self.assertEqual(candidate.document.tail, expected_alarm_tail(original, alarms, tags, schema))
                before, after = ResourceTables.parse(original), ResourceTables.parse(candidate.document.tail)
                self.assertEqual((before.prefix, before.suffix), (after.prefix, after.suffix))
                self.assertEqual([r.raw for r in before.alarm.records if r.key != "wMessageLen001-0"],
                                 [r.raw for r in after.alarm.records if r.key != "wMessageLen001-0"])
                for eid in ("10", "11", "12"):
                    self.assertEqual(alarm_view_context(adapter.document, "1", eid), alarm_view_context(candidate.document, "1", eid))
                self.assertEqual(source, adapter.original)
                self.assertEqual(adapter.document.tail, original)
                self.assertEqual(candidate.envelope.thumbnail, adapter.envelope.thumbnail)
                self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)

    def test_equal_messages_are_exact_noop(self):
        self.assertEqual(self.operations(), [])
        self.assertIs(expected_alarm_tail(self.tail, self.alarms, self.tags, self.contract), self.tail)

    def test_noop_preserves_noncanonical_length_spelling(self):
        table = ResourceTables.parse(self.tail)
        field = table.alarm.one("wMessageLen001-0")
        alternate = field.raw.replace(b"=" + field.value + b"\r\n", b"=000" + field.value + b"\r\n", 1)
        self.requalify(self.tail.replace(field.raw, alternate, 1))
        self.assertEqual(self.operations(), [])
        self.assertEqual(expected_alarm_tail(self.tail, self.alarms, self.tags, self.contract), self.tail)

    def test_absent_public_contract_preserves_opaque_legacy_tail(self):
        opaque = b"unparsed legacy resource\0[Alarm]"
        self.assertIs(expected_alarm_tail(opaque, [], [], {}), opaque)

    def test_empty_ir_does_not_bypass_declared_enabled_coverage(self):
        self.assertError("ALARM_COVERAGE", lambda: alarm_ir_operations(self.tail, [], self.tags, self.contract))
        self.assertError("ALARM_COVERAGE", lambda: expected_alarm_tail(self.tail, [], self.tags, self.contract))

    def test_missing_extra_and_repeated_enabled_mappings_are_closed(self):
        for mode in ("missing", "extra", "repeated", "disabled"):
            with self.subTest(mode=mode):
                self.setUp()
                if mode == "missing":
                    self.alarms.pop()
                elif mode == "extra":
                    self.contract["alarm_ir"]["entries"]["unused"] = deepcopy(self.contract["alarm_ir"]["entries"]["fault_a"])
                elif mode == "repeated":
                    self.contract["alarm_ir"]["entries"]["fault_b"] = deepcopy(self.contract["alarm_ir"]["entries"]["fault_a"])
                else:
                    self.contract["alarm_ir"]["entries"]["fault_b"]["index"] = "003"
                self.assertError("ALARM_COVERAGE", self.operations)

    def test_primary_message_index_language_and_raw_hash_are_pinned(self):
        for key, value, code in (("message_field", "wMessageLen002-0", "ALARM_COVERAGE"),
                                 ("message_field", "wMessageLen001-1", "ALARM_COVERAGE"),
                                 ("message_record_sha256", "0" * 64, "ALARM_SOURCE_CHANGED")):
            with self.subTest(key=key, value=value):
                self.setUp()
                self.contract["alarm_ir"]["entries"]["fault_a"][key] = value
                self.assertError(code, self.operations)

    def test_semantic_source_aliases_are_not_hidden(self):
        for extra in (wide("wMessageLen001-00", "Alias"), b"AlarmVar0001=DEMO.ALARM_A\r\n", b"AlarmOn0001=1\r\n"):
            with self.subTest(extra=extra[:30]):
                self.setUp()
                self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
                self.assertError("AMBIGUOUS_ALARM_INDEX", self.operations)

    def test_overlong_language_fails_explicitly(self):
        extra = wide("wMessageLen001-" + "9" * 5000, "bounded")
        self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
        self.assertError("NATIVE_LIMIT", self.operations)

    def test_unobserved_index_spellings_cannot_evade_alias_or_formatter_checks(self):
        for extra in (b"AlarmVar01=DEMO.ALARM_A\r\n", b"AlarmEnable000001=1\r\n",
                      wide("wMessageLen1-0", "Alias"), b"WatchAddr01-001=DEMO.VALUE\r\n"):
            with self.subTest(extra=extra[:35]):
                self.setUp()
                self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
                self.assertError("UNQUALIFIED_ALARM_INDEX", self.operations)

    def test_scalar_companion_subindexes_are_closed_on_rebased_noop_and_changed_source(self):
        for extra in (b"AlarmVar001-001=FOREIGN\r\n", b"AlarmOn001-001=0\r\n",
                      b"AlarmEnable001-001=0\r\n", b"AlarmScreenID001-001=2\r\n",
                      b"AlarmVar0001-001=FOREIGN\r\n", b"AlarmOn001-0001=0\r\n"):
            for changed in (False, True):
                with self.subTest(extra=extra, changed=changed):
                    self.setUp()
                    self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
                    if changed:
                        self.alarms[0]["text"] = "Changed plain message"
                    self.assertError("UNQUALIFIED_ALARM_INDEX", self.operations)
                    self.assertError("UNQUALIFIED_ALARM_INDEX", lambda: expected_alarm_tail(self.tail, self.alarms, self.tags, self.contract))

    def test_malformed_protected_suffixes_are_closed_before_projection_on_rebased_source(self):
        extras = [key.encode() + b"=FOREIGN\r\n" for key in (
            "AlarmVar-001", "AlarmOn-001", "AlarmVar001_001", "AlarmVar001--001", "AlarmVar001-X",
            "AlarmEnable-001", "AlarmScreenID001-X", "AlarmVar", "WatchAddr-001-001", "WatchAddr001-X",
            "WatchAddr001_001", "WatchAddr", "WatchAddrCount001--001", "WatchAddrReadLen-001-001",
            "AlarmLink-001", "AlarmTriggerFmt001-X", "AlarmTriggerCount-001", "AlarmTriggerOperator001-X")]
        extras += [wide(key, "Malformed donor") for key in (
            "wMessageLen-001-0", "wMessageLen001-X", "wMessageLen001_0", "wMessageLen001--0", "wMessageLen")]
        for extra in extras:
            for changed in (False, True):
                with self.subTest(extra=extra[:40], changed=changed):
                    self.setUp()
                    self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
                    if changed:
                        self.alarms[0]["text"] = "Changed plain message"
                    self.assertError("UNQUALIFIED_ALARM_INDEX", self.operations)
                    self.assertError("UNQUALIFIED_ALARM_INDEX", lambda: expected_alarm_tail(self.tail, self.alarms, self.tags, self.contract))

    def test_sparse_polarity_and_width_are_not_defaults(self):
        for field in (b"AlarmOn001=1\r\n", b"AlarmMemLen001=1\r\n"):
            with self.subTest(field=field):
                self.setUp()
                self.requalify(self.tail.replace(field, b"", 1))
                self.assertError("MISSING_NATIVE_FIELD", self.operations)

    def test_changed_source_direct_polarity_and_bool_width_are_closed(self):
        for old, new in ((b"ContinueAddr=0", b"ContinueAddr=1"), (b"AlarmOn001=1", b"AlarmOn001=0"),
                         (b"AlarmMemLen001=1", b"AlarmMemLen001=2"), (b"AlarmMemLen001=1", b"AlarmMemLen001=65535")):
            with self.subTest(new=new):
                self.setUp()
                self.requalify(self.tail.replace(old, new, 1))
                self.assertError("UNQUALIFIED_ALARM_TRIGGER", self.operations)

    def test_trigger_storage_requires_exact_bit_contract(self):
        for key, value in (("bits", True), ("bits", 16), ("format", "unsigned"), ("native_mem_len", "2"), ("format", [])):
            with self.subTest(key=key, value=value):
                self.setUp()
                self.contract["alarm_ir"]["entries"]["fault_a"]["trigger"]["storage"][key] = value
                self.assertError("UNQUALIFIED_ALARM_TRIGGER", self.operations)

    def test_numeric_per_entry_and_watch_companions_are_closed(self):
        for extra, code in ((b"AlarmTriggerFmt001=2\r\n", "UNQUALIFIED_ALARM_TRIGGER"),
                            (b"AlarmLink001=1\r\n", "UNQUALIFIED_ALARM_TRIGGER"),
                            (b"WatchAddr001-001=DEMO.VALUE\r\n", "UNQUALIFIED_ALARM_MESSAGE"),
                            (b"WatchAddrCount001=1\r\n", "UNQUALIFIED_ALARM_MESSAGE")):
            with self.subTest(extra=extra):
                self.setUp()
                self.requalify(self.tail.replace(b"Unknown=A\r\n", extra + b"Unknown=A\r\n", 1))
                self.assertError(code, self.operations)

    def test_replacement_and_existing_format_messages_are_closed_when_changed(self):
        self.alarms[0]["text"] = "Fault %d"
        self.assertError("UNQUALIFIED_ALARM_MESSAGE", self.operations)
        self.setUp()
        old = ResourceTables.parse(self.tail).alarm.one("wMessageLen001-0").raw
        self.requalify(self.tail.replace(old, wide("wMessageLen001-0", "Fault %d"), 1))
        self.assertError("UNQUALIFIED_ALARM_MESSAGE", self.operations)
        self.alarms[0]["text"] = "Fault %d"
        self.assertEqual(self.operations(), [])

    def test_history_policy_is_preservation_only(self):
        for policy in ("retain", "clear", None, []):
            with self.subTest(policy=policy):
                self.alarms[0]["history_policy"] = policy
                self.assertError("INVALID_ALARM_IR", self.operations)

    def test_tag_engineering_address_access_and_native_binding_are_exact(self):
        for key, value in (("address", "DEMO.OTHER"), ("data_type", "UINT"), ("channel", "OTHER"),
                           ("station", 0), ("byte_order", "big"), ("word_order", "big"), ("access", "Write"),
                           ("native_binding", {"link": "2", "mem_type": "0"})):
            with self.subTest(key=key):
                self.setUp()
                self.tags[0][key] = value
                self.assertError("INVALID_ALARM_TAG", self.operations)

    def test_public_schema_extra_keys_and_unhashable_values_fail_explicitly(self):
        for target in ("contract", "entry", "trigger", "storage", "tag_contract", "native_binding", "spec", "alarm", "low_contract"):
            with self.subTest(target=target):
                self.setUp()
                entry = self.contract["alarm_ir"]["entries"]["fault_a"]
                objects = {"contract": self.contract["alarm_ir"], "entry": entry, "trigger": entry["trigger"],
                           "storage": entry["trigger"]["storage"], "tag_contract": entry["tag_contract"],
                           "native_binding": entry["native_binding"], "spec": self.contract["alarm"]["fields"][entry["message_field"]],
                           "alarm": self.alarms[0], "low_contract": self.contract["alarm"]}
                objects[target]["unsupported"] = {}
                self.assertError(None, self.operations)
        for key in ("mode", "active_value", "link_owner"):
            with self.subTest(key=key):
                self.setUp()
                self.contract["alarm_ir"]["entries"]["fault_a"]["trigger"][key] = []
                self.assertError("UNQUALIFIED_ALARM_TRIGGER", self.operations)

    def test_low_level_source_and_semantic_guards_apply_to_noop(self):
        for target, key, value in (("alarm", "donor_tail_sha256", "0" * 64), ("alarm", "suffix_sha256", "0" * 64),
                                   ("alarm", "version", "17"), ("alarm", "qualified", False)):
            with self.subTest(key=key):
                self.setUp()
                self.contract[target][key] = value
                self.assertError(None, self.operations)
        self.setUp()
        del self.contract["alarm"]["fields"]["wMessageLen001-0"]["preconditions"]["AlarmOn001"]
        self.assertError("ALARM_PRECONDITION", self.operations)

    def test_noop_requires_qualified_complete_suffix(self):
        self.requalify(self.tail.replace(b"HistoryCount=1\r\n", b"HistoryCount=1\r\nAlienHistorySetting=0\r\n", 1))
        self.assertError("UNQUALIFIED_ALARM_SUFFIX", self.operations)

    def test_message_length_unicode_and_nul_errors_are_explicit(self):
        for message in ("x" * 100, "bad\0message", "bad\ud800message"):
            with self.subTest(message=repr(message)[:30]):
                self.alarms[0]["text"] = message
                self.assertError("RESOURCE_TEXT", self.operations)


class AlarmViewContextTests(unittest.TestCase):
    def setUp(self):
        source, _, _, _ = alarm_public_fixture()
        self.document = Document.parse(Envelope.decode(source, "delta_diascreen").body)

    def context(self, eid="10"):
        return alarm_view_context(self.document, "1", eid)

    def element(self, eid="10"):
        return next(section for section in self.document.sections if section.name == "Element" and section.one("nPartsID").value.decode() == eid)

    def assertError(self, call):
        with self.assertRaises(HmiError):
            call()

    def test_type_subtype_and_present_reference_inventory(self):
        for eid, subtype in (("10", "2"), ("11", "1"), ("12", "4")):
            with self.subTest(eid=eid):
                context = self.context(eid)
                self.assertEqual((context["type"], context["subtype"]), ("11", subtype))
                self.assertEqual(set(context), {"owner_sha256", "immutable_sha256", "type", "subtype", "reference_inventory"})
                self.assertIn({"section_index": 0, "field": "FunctionKeyPartID0", "value": "-1"}, context["reference_inventory"])
                self.assertEqual(len(context["owner_sha256"]), 64)

    def test_identity_geometry_changes_only_full_owner_hash(self):
        original = self.context()
        self.element().one("nPartsID").set_value(b"20")
        # All five excluded records change together; State.X remains immutable.
        element = self.element("20")
        for field, value in (("X", b"6"), ("Y", b"7"), ("Width", b"80"), ("Height", b"18")):
            element.one(field).set_value(value)
        changed = self.context("20")
        self.assertNotEqual(original["owner_sha256"], changed["owner_sha256"])
        self.assertEqual(original["immutable_sha256"], changed["immutable_sha256"])

    def test_columns_titles_time_unknown_and_state_geometry_are_immutable(self):
        mutations = (("element", "DateFmt", b"0"), ("element", "ColWidth0", b"50"),
                     ("element", "UnknownPresentation", b"altered"), ("state", "X", b"778"))
        for scope, key, value in mutations:
            with self.subTest(key=key):
                self.setUp()
                original = self.context()
                if scope == "element":
                    section = self.element()
                    if key == "UnknownPresentation":
                        next(record for record in section.records if record.key == key).set_value(value)
                    else:
                        section.one(key).set_value(value)
                else:
                    section = next(section for section in self.document.sections if section.name == "State" and section.one("X", False))
                    section.one(key).set_value(value)
                self.assertNotEqual(original["immutable_sha256"], self.context()["immutable_sha256"])
        self.setUp()
        original = self.context()
        self.element().one("TitleTextLen0-1").set_text("Changed other title")
        self.assertNotEqual(original["immutable_sha256"], self.context()["immutable_sha256"])

    def test_record_order_state_order_headers_and_empty_macros_are_hashed(self):
        for change in ("records", "states", "header", "empty_macro"):
            with self.subTest(change=change):
                self.setUp()
                original = self.context()
                element = self.element()
                position = self.document.sections.index(element)
                if change == "records":
                    element.records[-1], element.records[-2] = element.records[-2], element.records[-1]
                elif change == "states":
                    self.document.sections[position + 1], self.document.sections[position + 2] = self.document.sections[position + 2], self.document.sections[position + 1]
                elif change == "header":
                    self.document.sections[position + 1].header += b"\r\n"
                else:
                    element.one("BeforeExecMacroLen").raw = b"BeforeExecMacroLen=0000\r\n"
                self.assertNotEqual(original["immutable_sha256"], self.context()["immutable_sha256"])

    def test_active_functionkeys_filebrowser_variables_and_macros_are_closed(self):
        for key, value in (("FunctionKeyPartID0", b"0"), ("FunctionKeyPartID1", b"15"),
                           ("RelatedFileBrowserPartID", b"0"), ("WriteVar", b"DEMO.WRITE"),
                           ("GroupIDVar", b"DEMO.GROUP"), ("EventCtrlVar", b"DEMO.EVENT"),
                           ("FilterCtrlVar", b"DEMO.FILTER")):
            with self.subTest(key=key):
                self.setUp()
                self.element().one(key).set_value(value)
                self.assertError(self.context)
        self.setUp()
        macro = self.element().one("BeforeExecMacroLen")
        macro.blob = b"xx\r\n"
        macro.set_value(b"4", force=True)
        self.assertError(self.context)

    def test_reference_duplicates_aliases_and_unknown_actions_are_closed(self):
        from universal_hmi.native.records import Record
        for key, value in (("FunctionKeyPartID0", b"-1"), ("FunctionKeyPartID00", b"-1"),
                           ("FutureActionVar", b"None"), ("UnknownPartID", b"-1"),
                           ("GoToScreenID", b"0")):
            with self.subTest(key=key):
                self.setUp()
                self.element().records.append(Record(key.encode() + b"=" + value + b"\r\n", key, value))
                self.assertError(self.context)

    def test_foreign_view_fields_under_application_screen_and_state_are_closed(self):
        from universal_hmi.native.records import Record
        for owner, key, value in (("Application", "FunctionKeyPartID0", b"-1"), ("Screen", "GroupIDVar", b"None"),
                                  ("Screen", "ReadLink", b"1"), ("State", "ReadMemType", b"0"),
                                  ("State", "FunctionKeyPartID0", b"-1"), ("State", "TitleTextLen0-0", b"0"),
                                  ("State", "TimeFmt", b"0")):
            with self.subTest(owner=owner, key=key):
                self.setUp()
                section = next(section for section in self.document.sections if section.name == owner)
                section.records.append(Record(key.encode() + b"=" + value + b"\r\n", key, value))
                self.assertError(self.context)

    def test_legitimate_global_alarm_settings_are_preserved_as_opaque(self):
        from universal_hmi.native.records import Record
        original = self.context()
        application = self.document.sections[0]
        for key in ("AlarmMsgWarpText", "FDA_AlarmEnable", "DiskSpaceAlarmEnable", "ShowUsbMsgInAlarm", "AlarmExportCSV"):
            application.records.append(Record(key.encode() + b"=1\r\n", key, b"1"))
        self.assertEqual(original, self.context())

    def test_absent_reference_companions_remain_absent(self):
        self.element().records = [record for record in self.element().records if record.key not in {"ReadVar", "ReadLink", "ReadMemType"}]
        context = self.context()
        self.assertFalse(any(item["field"] in {"ReadVar", "ReadLink", "ReadMemType"} for item in context["reference_inventory"]))

    def test_frequency_unknown_extent_and_noncanonical_owner_ids_are_closed(self):
        from universal_hmi.native.records import Section
        self.element().one("SubType").set_value(b"3")
        self.assertError(self.context)
        self.setUp()
        position = self.document.sections.index(self.element())
        self.document.sections.insert(position + 1, Section("UnknownOwner", b"[UnknownOwner]\r\n"))
        self.assertError(self.context)
        self.setUp()
        self.element().one("nPartsID").set_value(b"010")
        self.assertError(self.context)


if __name__ == "__main__":
    unittest.main()
