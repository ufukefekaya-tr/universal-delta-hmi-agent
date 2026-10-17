"""Neutral source/action contracts; never vendor or runtime permission proof."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.address_contract import source_driver_fingerprint
from universal_hmi.native.codec import Envelope
from universal_hmi.native.existing_entry_permission import (
    ExistingEntryPermission, action_classification_sha256, entry_permission_contract,
    parse_entry_json)
from universal_hmi.native.existing_integer_numeric import ExistingIntegerNumeric
from universal_hmi.native.records import Record
from test_existing_integer_numeric import integer_numeric_fixture
from test_existing_program import existing_schema, sha


_TARGETS = (("12", "61"), ("7", "34"), ("12", "137"))


def entry_json(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True).encode("utf-8") + b"\n"


def entry_contracts(source):
    """Source-local synthetic classification; raw static address book is real."""
    book_raw = (Path(__file__).resolve().parents[1] / "profiles" / "driver_contracts"
                / "delta_dvp_serial_radix_2016.json").read_bytes()
    book = json.loads(book_raw)
    namespace = {"qualified": True, "contract_version": 2, "mode": "source_driver_radix_regions",
                 "source_sha256": sha(source.original), "prefix": "{Link2}0@",
                 "driver": {"native_index": "0", **book["driver"],
                            "raw_span_sha256": source_driver_fingerprint(source, "0")},
                 "regions": deepcopy(book["regions"]), "authority_sha256": sha(book_raw),
                 "review_reference": "SYNTHETIC ORIGINAL SOURCE; REGISTERED STATIC ADDRESS FACTS"}
    namespace_raw = entry_json(namespace)
    owners = {(p["id"], o["id"]): o for p in _groups(source.document) for o in p["elements"]}
    actions = []
    for sid, eid in _TARGETS:
        owner = owners[(sid, eid)]
        section = owner["section"]
        extent = b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])
        action = {"screen_id": sid, "element_id": eid, "owner_sha256": sha(extent),
                  # One-byte transcription also permits deliberately invalid
                  # native bytes to reach the production strict-ASCII guard.
                  "write_address": section.one("WriteVar").value.decode("latin-1"),
                  "action_class": "start_request" if sid == "12" and eid == "61" else "parameter_write",
                  "gating_authorization": {"authorized": True, "authority": "human_project_contract",
                                           "reference": "SYNTHETIC TEST AUTHORIZATION; NO HUMAN MACHINE ACCEPTANCE"}}
        for key, native in (("type", "Type"), ("subtype", "SubType"), ("write_link", "WriteLink"),
                            ("write_mem_type", "WriteMemType"), ("mem_len", "MemLen"), ("mem_fmt", "MemFmt")):
            action[key] = int(section.one(native).value)
        actions.append(action)
    action_raw = entry_json({"contract_version": 1, "mode": "existing_entry_action_classification_v1",
                            "source_sha256": sha(source.original), "address_namespace_sha256": sha(namespace_raw),
                            "actions": actions})
    descriptor = {"qualified": True, "contract_version": 1, "mode": "existing_entry_permission_v1",
                  "source_sha256": sha(source.original), "family": "delta_dopsoft2", "model_id": 2953863504,
                  "editor_version": "4.00.07.04", "authority_sha256": sha(b"SYNTHETIC ENTRY PERMISSION AUTHORITY"),
                  "address_namespace_sha256": sha(namespace_raw), "action_contract_sha256": sha(action_raw)}
    return existing_schema(source.original), descriptor, namespace_raw, action_raw


def entry_permission_fixture():
    """Original disabled SetOn and signed/unsigned F0 inputs on three pages."""
    raw, _, _ = integer_numeric_fixture()
    source = NativeAdapter(raw, "delta_dopsoft2")
    driver = (b"ControllerSection0=Delta\r\nControllerName0=Delta DVP PLC\r\n"
              b"CommName0=Link2\r\nDefPLCStationNr0=0\r\nPrinterSection0=NULL\r\n")
    for line in driver.splitlines(keepends=True):
        key, value = line[:-2].split(b"=", 1)
        source.application.records.append(Record(line, key.decode(), value))
    # Source bindings are explicitly authored fixture input, not an MCP edit.
    body = source.document.bytes().replace(b"{Link2}1@", b"{Link2}0@")
    source = NativeAdapter(source.envelope.encode(body), source.family)
    return source.original, *entry_contracts(source)


class ExistingEntryPermissionTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.schema, self.descriptor, self.namespace_raw, self.action_raw = entry_permission_fixture()
        self.source = NativeAdapter(self.raw, "delta_dopsoft2")
        self.program = self.make()

    def make(self, source=None, descriptor=None, namespace_raw=None, action_raw=None):
        return ExistingEntryPermission(source or self.source, self.schema,
                                       self.descriptor if descriptor is None else descriptor,
                                       self.namespace_raw if namespace_raw is None else namespace_raw,
                                       self.action_raw if action_raw is None else action_raw)

    def owner(self, sid="12", eid="61", source=None):
        return next(o for p in _groups((source or self.source).document) if p["id"] == sid
                    for o in p["elements"] if o["id"] == eid)

    def extent(self, sid, eid, source=None):
        source = source or self.source
        owner = self.owner(sid, eid, source)
        return b"".join(s.bytes() for s in source.document.sections[owner["start"]:owner["end"]])

    def op(self, sid="12", eid="61", action_raw=None, source=None, **changes):
        actions = parse_entry_json(self.action_raw if action_raw is None else action_raw)["actions"]
        action = next(a for a in actions if a["screen_id"] == sid and a["element_id"] == eid)
        result = {"op": "set_existing_entry_permission", "screen_id": sid, "element_id": eid,
                  "owner_sha256": sha(self.extent(sid, eid, source)), "permission_address": "{Link2}0@X10",
                  "enable_level": 1, "action_classification_sha256": action_classification_sha256(action)}
        result.update(changes)
        return result

    def error(self, callback, code=None):
        with self.assertRaises(HmiError) as caught:
            callback()
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.source.original, self.raw)
        self.assertEqual(self.source.document.bytes(), self.source.envelope.body)

    def changed_contract(self, action_changes=None, namespace_changes=None):
        namespace = parse_entry_json(self.namespace_raw)
        if namespace_changes:
            namespace_changes(namespace)
        namespace_raw = entry_json(namespace)
        contract = parse_entry_json(self.action_raw)
        contract["address_namespace_sha256"] = sha(namespace_raw)
        if action_changes:
            action_changes(contract)
        action_raw = entry_json(contract)
        descriptor = {**self.descriptor, "address_namespace_sha256": sha(namespace_raw),
                      "action_contract_sha256": sha(action_raw)}
        return self.make(descriptor=descriptor, namespace_raw=namespace_raw, action_raw=action_raw), action_raw

    def rehashed_source(self, sid, eid, field, value):
        source = NativeAdapter(self.raw, self.source.family)
        self.owner(sid, eid, source)["section"].one(field).set_value(value)
        source = NativeAdapter(source.envelope.encode(source.document.bytes()), source.family)
        schema, descriptor, namespace_raw, action_raw = entry_contracts(source)
        return ExistingEntryPermission(source, schema, descriptor, namespace_raw, action_raw)

    def test_three_original_targets_both_enable_levels_and_immutable_storage(self):
        self.assertTrue(self.program.check())
        operations = [self.op(*target, enable_level=index % 2) for index, target in enumerate(_TARGETS)]
        candidate = NativeAdapter(self.program.apply(operations), self.source.family)
        self.assertTrue(self.program.verify(candidate, operations))
        self.assertEqual(candidate.envelope.body, self.program.expected_body(operations))
        for index, (sid, eid) in enumerate(_TARGETS):
            old, new = self.owner(sid, eid), self.owner(sid, eid, candidate)
            self.assertEqual(new["section"].one("InterLockVar").value, b"{Link2}0@X10")
            self.assertEqual(new["section"].one("InterLockLevel").value, str(index % 2).encode())
            for before, after in zip(old["section"].records, new["section"].records):
                if before.key not in ("InterLockVar", "InterLockLevel"):
                    self.assertEqual(before.raw, after.raw)
            self.assertEqual([s.bytes() for s in old["states"]], [s.bytes() for s in new["states"]])
        # Observed unsigned BOOL format2 stays exact; signed WORD is not changed.
        self.assertEqual(self.owner("12", "61", candidate)["section"].one("MemFmt").value, b"2")
        self.assertEqual(self.owner("7", "34", candidate)["section"].one("MemFmt").value, b"1")
        self.assertEqual(candidate.document.tail, self.source.document.tail)
        self.assertEqual(candidate.envelope.thumbnail, self.source.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix[:37], self.source.envelope.prefix[:37])

    def test_independent_source_record_oracle_and_restoration(self):
        operations = [self.op(enable_level=0), self.op("7", "34", permission_address="{Link2}0@M4095")]
        candidate = NativeAdapter(self.program.apply(operations), self.source.family)
        # Oracle constructed independently from raw original record spans.
        expected, cursor, restored, delta = [], 0, [], 0
        spans = self.program.spans(operations)
        for start, end, replacement in spans:
            self.assertTrue(self.source.envelope.body[start:end].startswith((b"InterLockVar=", b"InterLockLevel=")))
            expected.extend((self.source.envelope.body[cursor:start], replacement)); cursor = end
        expected.append(self.source.envelope.body[cursor:])
        self.assertEqual(candidate.envelope.body, b"".join(expected))
        cursor = 0
        for start, end, replacement in spans:
            saved_start = start + delta; saved_end = saved_start + len(replacement)
            restored.extend((candidate.envelope.body[cursor:saved_start], self.source.envelope.body[start:end]))
            cursor = saved_end; delta += len(replacement) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        self.assertEqual(b"".join(restored), self.source.envelope.body)

    def test_saved_reopen_replay_and_empty_complete_noop(self):
        operations = [self.op("12", "137", enable_level=0)]
        output = self.program.apply(operations)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "neutral_entry.dps"
            path.write_bytes(output)
            saved = NativeAdapter(path.read_bytes(), self.source.family)
            self.assertTrue(self.program.verify(saved, operations))
        self.assertEqual(output, self.program.apply(operations))
        self.assertEqual(self.program.apply([]), self.raw)
        self.assertTrue(self.program.verify(self.source))
        payload = (self.source.envelope.prefix + self.source.envelope.body).translate(bytes(i ^ 0x64 for i in range(256)))
        packed = self.source.envelope.thumbnail + gzip.compress(payload, mtime=1)
        self.assertNotEqual(packed, self.raw)
        self.error(lambda: self.program.verify(NativeAdapter(packed, self.source.family)), "ENTRY_PRESERVATION")

    def test_classification_hash_canonical_and_raw_artifact_pins_distinct(self):
        action = parse_entry_json(self.action_raw)["actions"][0]
        expected = hashlib.sha256(json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(action_classification_sha256(dict(reversed(list(action.items())))), expected)
        descriptor = dict(self.descriptor)
        self.error(lambda: self.make(descriptor=descriptor, action_raw=self.action_raw + b" "), "ENTRY_ARTIFACT_PIN")
        # Rehashing raw whitespace changes does not change the entry identity.
        descriptor["action_contract_sha256"] = sha(self.action_raw + b" ")
        program = self.make(descriptor=descriptor, action_raw=self.action_raw + b" ")
        self.assertEqual(program.apply([self.op()]), self.program.apply([self.op()]))

    def test_raw_json_duplicate_deep_truncated_nonutf8_float_and_length_refused(self):
        cases = [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'[' * 11 + b'0' + b']' * 11,
                 b'{"x":"unterminated}', b'{"x":}', b'\xff', b'{}\0', b'[]\n{}', b'{"x":1.0}',
                 b'{"x":NaN}', b'{"x":Infinity}', b'{"x":' + b'9' * 5000 + b'}', b' ' * (2 * 1024 * 1024 + 1), b'',
                 bytearray(b'{}'), None, {}]
        for raw in cases:
            self.error(lambda raw=raw: parse_entry_json(raw))
        self.assertEqual(parse_entry_json(b'{"x":"[quoted]\\\"{braces}"}'), {"x": '[quoted]"{braces}'})

    def test_exact_descriptor_shape_profile_and_hashes(self):
        cases = [{**self.descriptor, key: value} for key, value in
                 (("qualified", 1), ("contract_version", True), ("contract_version", 2),
                  ("mode", "entry_permission"), ("family", "delta_diascreen"), ("model_id", True),
                  ("model_id", 1), ("editor_version", "2.00.07"), ("authority_sha256", "G" * 64),
                  ("source_sha256", []), ("address_namespace_sha256", "x"), ("extra", "unknown"))]
        cases += [{k: v for k, v in self.descriptor.items() if k != "action_contract_sha256"}, [], None]
        cyclic = {}; cyclic["self"] = cyclic; cases.append(cyclic)
        for descriptor in cases:
            self.error(lambda descriptor=descriptor: entry_permission_contract(descriptor))

    def test_stop_release_safety_unspecified_roles_and_no_authorization_refused(self):
        for role in ("stop_request", "release", "safety", "momentary", "maintained", "", None, [], "parameter_write"):
            program, _ = self.changed_contract(lambda c, role=role: c["actions"][0].update(action_class=role))
            self.error(program.check, "UNAUTHORIZED_ENTRY_ACTION")
        for authorization in ({"authorized": False, "authority": "human_project_contract", "reference": "ref"},
                              {"authorized": True, "authority": "agent_guess", "reference": "ref"},
                              {"authorized": True, "authority": "human_project_contract", "reference": ""},
                              {"authorized": True, "authority": "human_project_contract", "reference": "x\ny"},
                              {"authorized": True, "authority": "human_project_contract", "reference": "\ud800"}, {}, None):
            program, _ = self.changed_contract(lambda c, a=authorization: c["actions"][0].update(gating_authorization=a))
            self.error(program.check, "UNAUTHORIZED_ENTRY_ACTION")

    def test_rehashed_action_wrong_identity_write_binding_and_storage_refused(self):
        for field, value in (("owner_sha256", "0" * 64), ("type", 6), ("subtype", 2), ("write_link", 2),
                             ("write_mem_type", 1), ("mem_len", 1), ("mem_fmt", 0), ("type", True),
                             ("write_address", "{Link2}0@M00"), ("write_address", "{Link2}0@M1"),
                             ("write_address", "{Link2}1@M0"), ("write_address", [])):
            program, _ = self.changed_contract(lambda c, f=field, v=value: c["actions"][0].update({f: v}))
            self.error(program.check)
        for change in (lambda c: c["actions"].append(deepcopy(c["actions"][0])),
                       lambda c: c["actions"][0].update(element_id="9999"),
                       lambda c: c.update(source_sha256="0" * 64),
                       lambda c: c.update(actions=[]), lambda c: c.update(extra="ignored")):
            program, _ = self.changed_contract(change)
            self.error(program.check)

    def test_disabled_original_and_unsafe_target_behavior_refused_after_repin(self):
        for target, field, value in ((("12", "61"), "ConFirmWindow", b"1"),
                (("12", "61"), "ButtonOnMacroLen", b"1"), (("12", "61"), "MemFmt", b"0"),
                (("12", "61"), "ReadMemType", b"1"), (("12", "61"), "OffsetReadVar", b"{Link2}0@D0"),
                (("12", "61"), "VisibleVar", b"{Link2}0@M2"), (("12", "61"), "InterLockVar", b"{Link2}0@M1"),
                (("7", "34"), "DotNum", b"1"), (("7", "34"), "MemLen", b"2"),
                (("7", "34"), "GainValue", b"2.0"), (("7", "34"), "TriggerVar", b"{Link2}0@M2"),
                (("7", "34"), "InterLockVar", b"{Link2}0@M2"), (("7", "34"), "Active", b"1"),
                (("7", "34"), "BeforeExecMacroLen", b"1")):
            self.error(lambda t=target, f=field, v=value: self.rehashed_source(*t, f, v).check())

    def test_other_subtypes_and_unclassified_owner_never_inferred_from_label(self):
        # SetOff, momentary, maintained, goto, display and literal all exist.
        for sid, eid in (("12", "67"), ("1", "21"), ("12", "71"), ("7", "41"), ("1", "31"), ("1", "11")):
            self.error(lambda sid=sid, eid=eid: self.program.apply([{**self.op(), "screen_id": sid, "element_id": eid,
                                                                    "owner_sha256": sha(self.extent(sid, eid))}]), "UNAUTHORIZED_ENTRY_ACTION")
        program, action_raw = self.changed_contract(lambda c: c["actions"].pop())
        self.error(lambda: program.apply([self.op("12", "137")]), "UNAUTHORIZED_ENTRY_ACTION")

    def test_namespace_read_bool_radix_boundaries_and_other_station_refused(self):
        for suffix in ("X0", "X7", "X10", "X77", "X100", "X377", "M0", "M1", "M10", "M4095", "Y377", "S1023"):
            self.assertTrue(self.program.verify(NativeAdapter(self.program.apply([self.op(permission_address="{Link2}0@" + suffix)]), self.source.family),
                                                [self.op(permission_address="{Link2}0@" + suffix)]))
        for address in ("{Link2}0@X8", "{Link2}0@X400", "{Link2}0@X00", "{Link2}0@D0", "{Link2}0@M4096",
                        "{Link2}1@M0", "{Link1}0@M0", "{Link02}0@M0", "{Link2}00@M0", "{Link2}0@M-1",
                        "{Link2}0@M١", "{Link2}0@M０", "{Link2}0@M0\n", "None", None, {}, []):
            self.error(lambda address=address: self.program.apply([self.op(permission_address=address)]), "CONTROL_ADDRESS_SCOPE")
        # Prefix text Link2 and native one-based link1 coexist by source facts.
        self.assertEqual(parse_entry_json(self.namespace_raw)["prefix"], "{Link2}0@")
        self.assertEqual(self.owner()["section"].one("InterLockLink").value, b"1")
        self.error(lambda: self.rehashed_source("12", "61", "InterLockLink", b"2").check(), "ENTRY_CHANNEL_SCOPE")

    def test_readonly_permission_allowed_but_readonly_command_binding_refused(self):
        self.assertTrue(self.program.verify(NativeAdapter(self.program.apply([self.op(permission_address="{Link2}0@X10")]), self.source.family),
                                           [self.op(permission_address="{Link2}0@X10")]))
        self.error(lambda: self.rehashed_source("12", "61", "WriteVar", b"{Link2}0@X10").check(), "CONTROL_ADDRESS_SCOPE")
        program, _ = self.changed_contract(namespace_changes=lambda n: n["regions"]["UINT"][0].update(access="Read"))
        self.error(program.check, "CONTROL_ADDRESS_SCOPE")

    def test_rehashed_namespace_actual_driver_station_channel_and_span_pins(self):
        for field, value in (("prefix", "{Link1}0@"), ("prefix", "{Link2}1@"), ("source_sha256", "0" * 64)):
            program, _ = self.changed_contract(namespace_changes=lambda n, f=field, v=value: n.update({f: v}))
            self.error(program.check, "INVALID_ADDRESS_SOURCE")
        for field, value in (("native_index", "1"), ("company", "Other"), ("name", "Other"), ("raw_span_sha256", "0" * 64)):
            program, _ = self.changed_contract(namespace_changes=lambda n, f=field, v=value: n["driver"].update({f: v}))
            self.error(program.check, "INVALID_ADDRESS_SOURCE")
        self.error(lambda: self.rehashed_source("12", "61", "WriteLink", b"2").check(), "ENTRY_CHANNEL_SCOPE")
        self.error(lambda: self.rehashed_source("12", "61", "InterLockLink", b"01").check(), "UNQUALIFIED_ENTRY_FIELD")

    def test_original_static_read_binding_and_ambiguous_scalar_framing(self):
        valid = self.rehashed_source("12", "61", "ReadVar", b"{Link2}0@M10")
        self.assertTrue(valid.check())
        source = NativeAdapter(valid.source.original, valid.source.family)
        self.owner(source=source)["section"].one("ReadLink").set_value(b"2")
        source = NativeAdapter(source.envelope.encode(source.document.bytes()), source.family)
        schema, descriptor, namespace_raw, action_raw = entry_contracts(source)
        self.error(lambda: ExistingEntryPermission(source, schema, descriptor, namespace_raw, action_raw).check(), "ENTRY_CHANNEL_SCOPE")
        for field, value in (("InterLockLevel", b"01"), ("InterLockLevel", b"2"), ("InterLockLevel", b"-1"),
                             ("InterLockVar", b"None "), ("WriteVar", b"{Link2}0@M\xff")):
            self.error(lambda f=field, v=value: self.rehashed_source("12", "61", f, v).check())

    def test_typed_operations_pins_duplicates_and_no_external_fields(self):
        malformed = [None, {}, [], True, "set", {**self.op(), "op": []}, {**self.op(), "extra": "unknown"}]
        cyclic = {}; cyclic["self"] = cyclic; malformed.append(cyclic)
        for operation in malformed:
            self.error(lambda operation=operation: self.program.apply([operation]))
        for field, value in (("enable_level", True), ("enable_level", False), ("enable_level", "1"),
                             ("enable_level", 2), ("enable_level", -1), ("enable_level", 1.0),
                             ("owner_sha256", "0" * 64), ("action_classification_sha256", "0" * 64),
                             ("screen_id", "01"), ("element_id", []), ("screen_id", {})):
            self.error(lambda field=field, value=value: self.program.apply([self.op(**{field: value})]))
        self.error(lambda: self.program.apply([self.op(), self.op()]), "DUPLICATE_ENTRY_OPERATION")
        self.error(lambda: self.program.apply({}), "INVALID_OPERATIONS")
        self.error(lambda: self.program.apply([self.op()] * 4097), "INVALID_OPERATIONS")

    def test_source_descriptor_raw_artifact_and_internal_source_freshness(self):
        self.program.contract["authority_sha256"] = "0" * 64
        self.error(self.program.check, "UNQUALIFIED_EXISTING_ENTRY_PERMISSION")
        self.program = self.make()
        self.program.address_namespace_raw += b" "
        self.error(self.program.check, "ENTRY_ARTIFACT_PIN")
        self.program = self.make()
        self.program.action_contract_raw += b" "
        self.error(self.program.check, "ENTRY_ARTIFACT_PIN")
        self.program = self.make()
        self.program.source = NativeAdapter(self.raw, self.source.family)
        self.error(self.program.check, "INVALID_ENTRY_SOURCE")
        altered = NativeAdapter(self.source.envelope.encode(self.source.envelope.body.replace(b"DefPLCStationNr0=0", b"DefPLCStationNr0=1")), self.source.family)
        self.error(lambda: self.make(source=altered).check())
        self.program = self.make()
        self.owner()["section"].one("InterLockLevel").set_value(b"0")
        with self.assertRaises(HmiError):
            self.program.check()
        self.source = NativeAdapter(self.raw, self.source.family)

    def test_candidate_other_field_link_level_state_tail_thumbnail_tamper_refused(self):
        operations = [self.op(enable_level=0)]
        candidate = NativeAdapter(self.program.apply(operations), self.source.family)
        for field, value in (("InterLockVar", b"{Link2}0@M20"), ("InterLockLevel", b"1"), ("InterLockLink", b"2"),
                             ("WriteVar", b"{Link2}0@M1"), ("MemFmt", b"1"), ("X", b"3"), ("Type", b"2")):
            changed = NativeAdapter(candidate.original, candidate.family)
            self.owner(source=changed)["section"].one(field).set_value(value)
            changed = NativeAdapter(changed.envelope.encode(changed.document.bytes()), changed.family)
            self.error(lambda changed=changed: self.program.verify(changed, operations), "ENTRY_PRESERVATION")
        changed = NativeAdapter(candidate.envelope.encode(candidate.envelope.body[:-2] + b"XX"), candidate.family)
        self.error(lambda: self.program.verify(changed, operations), "ENTRY_PRESERVATION")
        self.error(lambda: self.program.verify(candidate), "ENTRY_PRESERVATION")
        self.error(lambda: self.program.verify(candidate.original, operations), "INVALID_ENTRY_CANDIDATE")
        payload = (candidate.envelope.prefix + candidate.envelope.body).translate(bytes(i ^ 0x64 for i in range(256)))
        raw = candidate.envelope.thumbnail + gzip.compress(payload, mtime=1)
        self.assertTrue(self.program.verify(NativeAdapter(raw, candidate.family), operations))
        thumbnail = bytearray(candidate.envelope.thumbnail); thumbnail[11] ^= 1
        changed = NativeAdapter(bytes(thumbnail) + raw[len(thumbnail):], candidate.family)
        self.error(lambda: self.program.verify(changed, operations), "ENTRY_PRESERVATION")
        changed = NativeAdapter(candidate.original, candidate.family)
        self.owner(source=changed)["states"][0].one("FontColor").set_value(b"1")
        changed = NativeAdapter(changed.envelope.encode(changed.document.bytes()), changed.family)
        self.error(lambda: self.program.verify(changed, operations), "ENTRY_PRESERVATION")

    def test_active_permission_candidate_cannot_reopen_as_disabled_numeric_source(self):
        candidate = NativeAdapter(self.program.apply([self.op("7", "34")]), self.source.family)
        descriptor = {k: v for k, v in self.descriptor.items() if k not in ("address_namespace_sha256", "action_contract_sha256")}
        descriptor.update(mode="existing_word_integer_numeric_v1", source_sha256=sha(candidate.original))
        numeric = ExistingIntegerNumeric(candidate, existing_schema(candidate.original), descriptor)
        owner = self.owner("7", "34", candidate)
        self.error(lambda: numeric._target(owner), "EXISTING_INTEGER_NUMERIC_BEHAVIOR")


if __name__ == "__main__":
    unittest.main()
