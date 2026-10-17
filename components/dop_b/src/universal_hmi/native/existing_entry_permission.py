"""Source-bound stored entry permission for explicitly classified actions.

The original disabled SetOn or integer F0 input is never reclassified from its
label or subtype. A separate project contract identifies its full owner and
write binding, and records explicit human gating authorization. Only the two
ordinary InterLockVar/InterLockLevel scalars change; the native link is retained.
Registration and attribution are checked by the public caller. This module
does not establish data age, continuous protection, commit-time checking,
atomicity, vendor execution or physical acceptance.
"""
from copy import deepcopy
import json
import re

from ..errors import HmiError
from . import NativeAdapter, _groups
from .address_contract import AddressNamespace
from .existing_integer_numeric import ExistingIntegerNumeric
from .existing_program import (ExistingProgram, _bounded, _id, _sha, _SHA,
                               _MODEL, _VERSION, _FAMILY)


_DESCRIPTOR_KEYS = {"qualified", "contract_version", "mode", "source_sha256",
                    "family", "model_id", "editor_version", "authority_sha256",
                    "address_namespace_sha256", "action_contract_sha256"}
_ROOT_KEYS = {"contract_version", "mode", "source_sha256",
              "address_namespace_sha256", "actions"}
_ACTION_KEYS = {"screen_id", "element_id", "owner_sha256", "type", "subtype",
                "write_address", "write_link", "write_mem_type", "mem_len",
                "mem_fmt", "action_class", "gating_authorization"}
_OPERATION_KEYS = {"op", "screen_id", "element_id", "owner_sha256",
                   "permission_address", "enable_level", "action_classification_sha256"}
_SCALAR = re.compile(rb"0|[1-9][0-9]{0,9}")
_RAW_LIMIT = 2 * 1024 * 1024


def entry_permission_contract(descriptor):
    """Validate a separate descriptor; canonical hashes alone confer no trust."""
    _bounded(descriptor)
    if (not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_KEYS
            or descriptor.get("qualified") is not True
            or type(descriptor.get("contract_version")) is not int
            or descriptor["contract_version"] != 1
            or descriptor.get("mode") != "existing_entry_permission_v1"
            or descriptor.get("family") != _FAMILY
            or type(descriptor.get("model_id")) is not int or descriptor["model_id"] != _MODEL
            or descriptor.get("editor_version") != _VERSION):
        raise HmiError("UNQUALIFIED_EXISTING_ENTRY_PERMISSION",
                       "Entry permission requires its separate exact static B10 descriptor")
    for field in ("source_sha256", "authority_sha256", "address_namespace_sha256", "action_contract_sha256"):
        if not isinstance(descriptor[field], str) or not _SHA.fullmatch(descriptor[field]):
            raise HmiError("UNQUALIFIED_EXISTING_ENTRY_PERMISSION", "Entry descriptor pins require canonical SHA-256", field=field)
    return deepcopy(descriptor)


def parse_entry_json(raw):
    """Parse bounded immutable UTF-8 artifacts without duplicate keys or floats.

    A lexical depth check precedes the JSON parser; strings cannot smuggle
    apparent nesting. The parsed tree is independently bounded before copy.
    """
    if type(raw) is not bytes or not 1 <= len(raw) <= _RAW_LIMIT:
        raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifacts must be bounded immutable bytes")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact is not strict UTF-8") from exc
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > 10:
                raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact exceeds the bounded JSON depth")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact framing is incomplete")
    if quoted or depth:
        raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact framing is incomplete")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact contains a duplicate JSON key")
            result[key] = value
        return result

    def forbidden(_):
        raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifacts cannot contain floating or nonfinite numbers")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_float=forbidden, parse_constant=forbidden)
    except (ValueError, RecursionError) as exc:
        raise HmiError("INVALID_ENTRY_ARTIFACT", "Entry artifact is not bounded valid JSON") from exc
    _bounded(value)
    return value


def action_classification_sha256(action):
    """Pin the complete action using compact sorted ASCII-escaped UTF-8 JSON."""
    _bounded(action)
    if not isinstance(action, dict):
        raise HmiError("INVALID_ENTRY_ACTION_CONTRACT", "Action classification requires a bounded JSON object")
    return _sha(json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _singleline(value, limit=256, ascii_only=False):
    return (isinstance(value, str) and 1 <= len(value) <= limit and value == value.strip()
            and all(32 <= ord(c) != 127 and not 0xD800 <= ord(c) <= 0xDFFF for c in value)
            and len(value.splitlines()) == 1 and (not ascii_only or value.isascii()))


def _number(record, maximum=255):
    if (record.kind is not None or record.blob is not None
            or not _SCALAR.fullmatch(record.value)
            or record.raw != record.key.encode("ascii") + b"=" + record.value + b"\r\n"
            or int(record.value) > maximum):
        raise HmiError("UNQUALIFIED_ENTRY_FIELD", "Entry target scalar must use its canonical ordinary framing", field=record.key)
    return int(record.value)


def _address(record):
    if (record.kind is not None or record.blob is not None
            or record.raw != record.key.encode("ascii") + b"=" + record.value + b"\r\n"):
        raise HmiError("UNQUALIFIED_ENTRY_FIELD", "Entry address must retain its ordinary scalar framing", field=record.key)
    try:
        value = record.value.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("UNQUALIFIED_ENTRY_FIELD", "Entry source address is not ASCII", field=record.key) from exc
    if not _singleline(value, ascii_only=True):
        raise HmiError("UNQUALIFIED_ENTRY_FIELD", "Entry source address must be bounded and single-line", field=record.key)
    return value


class ExistingEntryPermission:
    """Separate original-source entry predicate with full-body restoration."""

    def __init__(self, source, existing_graph_schema, descriptor, address_namespace_raw, action_contract_raw):
        self.contract = entry_permission_contract(descriptor)
        self._contract_snapshot = tuple(sorted(self.contract.items()))
        self.source = source
        self._graph = ExistingProgram(source, existing_graph_schema)
        self.address_namespace_raw = address_namespace_raw
        self.action_contract_raw = action_contract_raw
        self._namespace_snapshot = address_namespace_raw
        self._action_snapshot = action_contract_raw
        # Validate raw hash/framing before parsing or recursive copy.
        self._artifacts()

    def _artifacts(self):
        for field, raw, snapshot in (("address_namespace_sha256", self.address_namespace_raw, self._namespace_snapshot),
                                     ("action_contract_sha256", self.action_contract_raw, self._action_snapshot)):
            if (type(raw) is not bytes or raw != snapshot or not 1 <= len(raw) <= _RAW_LIMIT
                    or _sha(raw) != self.contract[field]):
                raise HmiError("ENTRY_ARTIFACT_PIN", "Entry artifact bytes differ from their immutable pin", field=field)
        return (AddressNamespace(parse_entry_json(self.address_namespace_raw)), parse_entry_json(self.action_contract_raw))

    @staticmethod
    def _target(owner):
        section = owner["section"]
        pair = (_number(section.one("Type")), _number(section.one("SubType")))
        if pair == (6, 1):
            is_input, _ = ExistingIntegerNumeric._target(owner)  # ORIGINAL disabled source only.
            if not is_input:
                raise HmiError("UNQUALIFIED_ENTRY_KIND", "Entry target must remain its original numeric input")
        elif pair == (1, 1):
            if _number(section.one("MemLen")) != 0 or _number(section.one("MemFmt")) != 2:
                raise HmiError("UNQUALIFIED_ENTRY_STORAGE", "SetOn must retain its observed source BOOL storage")
            zero = {"PrintSuccessiveData", "Level", "ReadMemType", "WriteMemType", "OffsetReadMemType",
                    "OffsetWriteMemType", "nAngle", "bFreeze", "PushTime", "SetLowSecurity", "ConFirmWindow",
                    "NoMessage", "DispAsterisk"}
            for field in zero:
                if _number(section.one(field)) != 0:
                    raise HmiError("UNQUALIFIED_ENTRY_BEHAVIOR", "SetOn behavior is outside the plain disabled baseline", field=field)
            for field in ("BeforeExecMacroLen", "AfterExecMacroLen", "ButtonOnMacroLen"):
                record = section.one(field)
                if (record.kind != "macro" or record.blob != b"" or record.value != b"0"
                        or record.raw != field.encode("ascii") + b"=0\r\n"):
                    raise HmiError("UNQUALIFIED_ENTRY_BEHAVIOR", "SetOn entry requires the exact empty macro frame", field=field)
            for field in ("OffsetReadVar", "OffsetWriteVar", "VisibleVar", "InterLockVar"):
                if _address(section.one(field)) != "None":
                    raise HmiError("UNQUALIFIED_ENTRY_BEHAVIOR", "Entry target has an active conditional address", field=field)
        else:
            raise HmiError("UNQUALIFIED_ENTRY_KIND", "Only original SetOn and integer F0 input owners are eligible")
        if [state.one("Value").value for state in owner["states"]] != ([b"0", b"1"] if pair == (1, 1) else [b"0"]):
            raise HmiError("UNQUALIFIED_ENTRY_KIND", "Entry target state sequence differs from the observed plain source")
        if _address(section.one("InterLockVar")) != "None":
            raise HmiError("UNQUALIFIED_ENTRY_BEHAVIOR", "Only an original disabled entry permission can be configured")
        _number(section.one("InterLockLevel"), 1)
        return "start_request" if pair == (1, 1) else "parameter_write"

    def _actions(self, namespace, contract):
        if (not isinstance(contract, dict) or set(contract) != _ROOT_KEYS
                or type(contract.get("contract_version")) is not int or contract["contract_version"] != 1
                or contract.get("mode") != "existing_entry_action_classification_v1"
                or contract.get("source_sha256") != self.contract["source_sha256"]
                or contract.get("address_namespace_sha256") != self.contract["address_namespace_sha256"]
                or not isinstance(contract.get("actions"), list) or not 1 <= len(contract["actions"]) <= 4096):
            raise HmiError("INVALID_ENTRY_ACTION_CONTRACT", "Entry actions require their exact original-source classification contract")
        prefix = namespace.contract["prefix"]
        namespace.validate_source(self.source, prefix)
        driver_index = int(namespace.contract["driver"]["native_index"])
        if driver_index > 254:
            raise HmiError("ENTRY_CHANNEL_SCOPE", "Entry native driver index cannot fit its external one-based BYTE link")
        owners = {(p["id"], o["id"]): o for p in _groups(self.source.document) for o in p["elements"]}
        actions = {}
        for action in contract["actions"]:
            if not isinstance(action, dict) or set(action) != _ACTION_KEYS:
                raise HmiError("INVALID_ENTRY_ACTION_CONTRACT", "Entry action metadata must have its exact bounded shape")
            target = (_id(action["screen_id"], "screen_id", 65535), _id(action["element_id"], "element_id"))
            if target in actions:
                raise HmiError("DUPLICATE_ENTRY_ACTION", "Entry classification repeats an original owner")
            owner = owners.get(target)
            if owner is None:
                raise HmiError("MISSING_ENTRY_ACTION", "Classified action is absent from the pinned source")
            extent = b"".join(s.bytes() for s in self.source.document.sections[owner["start"]:owner["end"]])
            if not isinstance(action["owner_sha256"], str) or not _SHA.fullmatch(action["owner_sha256"]) or action["owner_sha256"] != _sha(extent):
                raise HmiError("ENTRY_ACTION_PIN", "Action metadata differs from its original complete owner extent")
            authorization = action["gating_authorization"]
            if (not isinstance(authorization, dict) or set(authorization) != {"authorized", "authority", "reference"}
                    or authorization.get("authorized") is not True or authorization.get("authority") != "human_project_contract"
                    or not _singleline(authorization.get("reference"))):
                raise HmiError("UNAUTHORIZED_ENTRY_ACTION", "Entry action requires an attributable explicit human project authorization")
            expected_class = self._target(owner)
            if action["action_class"] != expected_class:
                raise HmiError("UNAUTHORIZED_ENTRY_ACTION", "Stop, release, safety or unspecified action classifications are outside entry permission")
            section = owner["section"]
            for field, native in (("type", "Type"), ("subtype", "SubType"), ("write_link", "WriteLink"),
                                  ("write_mem_type", "WriteMemType"), ("mem_len", "MemLen"), ("mem_fmt", "MemFmt")):
                if type(action[field]) is not int or action[field] != _number(section.one(native)):
                    raise HmiError("ENTRY_ACTION_METADATA", "Classified action does not match its immutable native binding/storage", field=field)
            if _number(section.one("InterLockLink")) != driver_index + 1 or action["write_link"] != driver_index + 1:
                raise HmiError("ENTRY_CHANNEL_SCOPE", "Source entry and command links must select the qualified native driver")
            write_address = _address(section.one("WriteVar"))
            if not _singleline(action["write_address"], ascii_only=True) or action["write_address"] != write_address:
                raise HmiError("ENTRY_ACTION_METADATA", "Classified action write address differs from the original exact binding")
            data_type = "BOOL" if expected_class == "start_request" else "UINT"
            namespace.match(write_address, data_type, prefix, "write")
            read_address = _address(section.one("ReadVar"))
            if read_address != "None":
                if _number(section.one("ReadLink")) != driver_index + 1:
                    raise HmiError("ENTRY_CHANNEL_SCOPE", "Source read binding selects another native driver")
                namespace.match(read_address, data_type, prefix, "read")
            actions[target] = (owner, action_classification_sha256(action))
        return actions

    def check(self):
        descriptor = entry_permission_contract(self.contract)
        if tuple(sorted(descriptor.items())) != self._contract_snapshot:
            raise HmiError("UNQUALIFIED_EXISTING_ENTRY_PERMISSION", "Entry descriptor changed after construction")
        if self._graph.source is not self.source:
            raise HmiError("INVALID_ENTRY_SOURCE", "Entry source cannot be replaced after construction")
        self._graph.check()
        if descriptor["source_sha256"] != _sha(self.source.original):
            raise HmiError("INVALID_ENTRY_SOURCE", "Entry descriptor differs from the immutable source bytes")
        namespace, actions = self._artifacts()
        self._actions(namespace, actions)
        return True

    def _changes(self, operations):
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > 4096:
            raise HmiError("INVALID_OPERATIONS", "Entry operations require a bounded list")
        self.check()
        namespace, contract = self._artifacts()
        actions = self._actions(namespace, contract)
        section_indices = {id(s): i for i, s in enumerate(self.source.document.sections)}
        changes, seen = {}, set()
        for operation in operations:
            if (not isinstance(operation, dict) or set(operation) != _OPERATION_KEYS
                    or operation.get("op") != "set_existing_entry_permission"):
                raise HmiError("INVALID_ENTRY_OPERATION", "Only an exact pinned entry permission request is supported")
            target = (_id(operation["screen_id"], "screen_id", 65535), _id(operation["element_id"], "element_id"))
            if target in seen:
                raise HmiError("DUPLICATE_ENTRY_OPERATION", "Repeated native entry owner is refused")
            seen.add(target)
            if target not in actions:
                raise HmiError("UNAUTHORIZED_ENTRY_ACTION", "Entry target has no explicit original-source action classification")
            owner, classification = actions[target]
            section = owner["section"]
            extent = b"".join(s.bytes() for s in self.source.document.sections[owner["start"]:owner["end"]])
            for field, expected in (("owner_sha256", _sha(extent)), ("action_classification_sha256", classification)):
                value = operation[field]
                if not isinstance(value, str) or not _SHA.fullmatch(value) or value != expected:
                    raise HmiError("ENTRY_OPERATION_PIN", "Entry request differs from its exact source/action pin", field=field)
            address, level = operation["permission_address"], operation["enable_level"]
            if type(level) is not int or level not in (0, 1):
                raise HmiError("INVALID_ENTRY_LEVEL", "Entry enable level must be the explicit integer 0 or 1")
            namespace.match(address, "BOOL", namespace.contract["prefix"], "read")
            for field, value in (("InterLockVar", address.encode("ascii")), ("InterLockLevel", str(level).encode("ascii"))):
                record = section.one(field)
                if record.value != value:
                    ri = next(i for i, r in enumerate(section.records) if r is record)
                    changes[(section_indices[id(section)], ri)] = value
        return changes

    def _spans(self, changes):
        result, offset = [], 0
        for si, section in enumerate(self.source.document.sections):
            offset += len(section.header)
            for ri, record in enumerate(section.records):
                end = offset + len(record.raw)
                if (si, ri) in changes:
                    result.append((offset, end, record.key.encode("ascii") + b"=" + changes[(si, ri)] + b"\r\n"))
                offset = end
        return result

    def spans(self, operations):
        return self._spans(self._changes(operations))

    def _expected(self, spans):
        body, cursor, parts = self.source.envelope.body, 0, []
        for start, end, replacement in spans:
            parts.extend((body[cursor:start], replacement)); cursor = end
        parts.append(body[cursor:])
        return b"".join(parts)

    def expected_body(self, operations):
        return self._expected(self.spans(operations))

    def apply(self, operations):
        changes = self._changes(operations)
        if not changes:
            return self.source.original
        document = deepcopy(self.source.document)
        for (si, ri), value in changes.items():
            document.sections[si].records[ri].set_value(value)
        body = document.bytes()
        if body != self.expected_body(operations):
            raise HmiError("ENTRY_PRESERVATION", "Entry mutation differs from independent original record spans")
        raw = self.source.envelope.encode(body)
        self.verify(NativeAdapter(raw, self.source.family), operations)
        return raw

    def verify(self, candidate, operations=None):
        operations = [] if operations is None else operations
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_ENTRY_CANDIDATE", "Entry verification requires a native candidate adapter")
        candidate._preserved_byte_binding("INVALID_ENTRY_CANDIDATE")
        spans = self.spans(operations)
        expected = self._expected(spans)
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.body != expected or candidate.document.tail != self.source.document.tail):
            raise HmiError("ENTRY_PRESERVATION", "Candidate differs outside the two approved original entry scalar fields")
        if not spans and candidate.original != self.source.original:
            raise HmiError("ENTRY_PRESERVATION", "An entry no-op must preserve every original file byte")
        restored, cursor, delta = [], 0, 0
        for start, end, replacement in spans:
            saved_start = start + delta; saved_end = saved_start + len(replacement)
            restored.extend((candidate.envelope.body[cursor:saved_start], self.source.envelope.body[start:end]))
            cursor = saved_end; delta += len(replacement) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        if b"".join(restored) != self.source.envelope.body:
            raise HmiError("ENTRY_PRESERVATION", "Entry restoration failed to recover the complete source body")
        return True
