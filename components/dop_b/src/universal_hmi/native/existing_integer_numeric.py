"""Source-pinned existing WORD integer presentation and F0 input limits.

Only IntNum/DotNum and static input MinValue/MaxValue are writable. The
source's integer storage, address, scaling, keypad, states and resources stay
immutable. Fractional input lowering is explicitly outside this contract.
Authority registration and human vendor/runtime acceptance remain external.
"""
from copy import deepcopy
import re

from ..errors import HmiError
from . import NativeAdapter, _groups
from .existing_program import ExistingProgram, _bounded, _id, _sha, _SHA, _MODEL, _VERSION, _FAMILY
from .numeric import _number


_DESCRIPTOR_KEYS = {"qualified", "contract_version", "mode", "source_sha256",
                    "family", "model_id", "editor_version", "authority_sha256"}
_OPERATION_KEYS = {"op", "screen_id", "element_id", "owner_sha256", "data_type",
                   "value_model", "integer_digits", "fractional_digits"}
_INTEGER = re.compile(r"0|[1-9][0-9]{0,4}|-[1-9][0-9]{0,4}")
_UNSIGNED = re.compile(rb"0|[1-9][0-9]{0,9}")
_DOMAINS = {"INT": (-32768, 32767), "UINT": (0, 65535)}


def integer_numeric_contract(descriptor):
    """Validate a separate exact descriptor without conferring book authority."""
    _bounded(descriptor)
    if (not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_KEYS
            or descriptor.get("qualified") is not True
            or type(descriptor.get("contract_version")) is not int
            or descriptor["contract_version"] != 1
            or descriptor.get("mode") != "existing_word_integer_numeric_v1"
            or descriptor.get("family") != _FAMILY
            or type(descriptor.get("model_id")) is not int or descriptor["model_id"] != _MODEL
            or descriptor.get("editor_version") != _VERSION):
        raise HmiError("UNQUALIFIED_EXISTING_INTEGER_NUMERIC",
                       "Existing integer numeric edits require their separate exact static B10 descriptor")
    for field in ("source_sha256", "authority_sha256"):
        if not isinstance(descriptor[field], str) or not _SHA.fullmatch(descriptor[field]):
            raise HmiError("UNQUALIFIED_EXISTING_INTEGER_NUMERIC",
                           "Integer numeric provenance requires canonical SHA-256", field=field)
    return deepcopy(descriptor)


def _ordinary(record):
    if (record.kind is not None or record.blob is not None
            or record.raw != record.key.encode("ascii") + b"=" + record.value + b"\r\n"):
        raise HmiError("UNQUALIFIED_INTEGER_NUMERIC_FIELD",
                       "Numeric target requires its unambiguous ordinary scalar frame", field=record.key)
    return record.value


def _decimal(record):
    value = _ordinary(record)
    try:
        return _number(value.decode("ascii", "strict"), record.key)
    except (UnicodeDecodeError, HmiError) as exc:
        raise HmiError("UNQUALIFIED_INTEGER_NUMERIC_FIELD",
                       "Existing numeric scalar is outside the bounded ordinary decimal syntax", field=record.key) from exc


def _scalar(record, maximum=5):
    value = _ordinary(record)
    if not _UNSIGNED.fullmatch(value) or int(value) > maximum:
        raise HmiError("UNQUALIFIED_INTEGER_NUMERIC_FIELD",
                       "Numeric enum/digit field requires its canonical bounded integer", field=record.key)
    return int(value)


def _raw_limit(value, field, data_type):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and len(value) <= 6 and _INTEGER.fullmatch(value):
        number = int(value)
    else:
        raise HmiError("EXISTING_INTEGER_NUMERIC_LIMIT",
                       "F0 raw limits require canonical integer values", field=field)
    minimum, maximum = _DOMAINS[data_type]
    if not minimum <= number <= maximum:
        raise HmiError("EXISTING_INTEGER_NUMERIC_LIMIT",
                       "Raw input limit exceeds immutable source WORD storage", field=field)
    return number


class ExistingIntegerNumeric:
    """Edit existing WORD numeric owners, never manufacture a new type witness."""

    def __init__(self, source, existing_graph_schema, integer_numeric_descriptor):
        self.contract = integer_numeric_contract(integer_numeric_descriptor)
        self._contract_snapshot = tuple(sorted(self.contract.items()))
        self.source = source
        self._graph = ExistingProgram(source, existing_graph_schema)

    def check(self):
        descriptor = integer_numeric_contract(self.contract)
        if tuple(sorted(descriptor.items())) != self._contract_snapshot:
            raise HmiError("UNQUALIFIED_EXISTING_INTEGER_NUMERIC", "Integer numeric descriptor changed after construction")
        if self._graph.source is not self.source:
            raise HmiError("INVALID_INTEGER_NUMERIC_SOURCE", "Integer numeric source cannot be replaced after construction")
        self._graph.check()
        if descriptor["source_sha256"] != _sha(self.source.original):
            raise HmiError("INVALID_INTEGER_NUMERIC_SOURCE", "Integer numeric descriptor differs from the immutable source bytes")
        return True

    @staticmethod
    def _target(owner):
        section = owner["section"]
        pair = (section.one("Type").value, section.one("SubType").value)
        if pair not in {(b"5", b"1"), (b"6", b"1")}:
            raise HmiError("EXISTING_INTEGER_NUMERIC_KIND", "Only existing Type5/1 and Type6/1 integer WORD owners are eligible")
        if section.one("MemLen").value != b"1" or section.one("MemFmt").value not in {b"1", b"2"}:
            raise HmiError("EXISTING_INTEGER_NUMERIC_STORAGE", "Source storage must remain its existing signed or unsigned WORD")
        data_type = "INT" if section.one("MemFmt").value == b"1" else "UINT"
        is_input = pair[0] == b"6"
        zero = {"Roundoff", "LeadingZero", "FastRefresh", "Level", "OffsetReadMemType", "OffsetWriteMemType",
                "ReadMemType", "WriteMemType", "nAngle", "bFreeze", "PrintSuccessiveData"}
        if is_input:
            zero |= {"Active", "UseCustKeypad", "KeypadScreenID", "Variation", "Order", "SetLowSecurity",
                     "DispAsterisk", "NoMessage", "BeforeExecMacroLen", "AfterExecMacroLen"}
        for key in zero:
            record = section.one(key)
            if record.value != b"0" or record.raw != key.encode() + b"=0\r\n":
                raise HmiError("EXISTING_INTEGER_NUMERIC_BEHAVIOR", "Target behavior is outside the disabled numeric baseline", field=key)
        disabled = {"OffsetReadVar", "OffsetWriteVar", "VisibleVar"}
        if is_input:
            disabled |= {"InterLockVar", "TriggerVar"}
        for key in disabled:
            if section.one(key).value != b"None":
                raise HmiError("EXISTING_INTEGER_NUMERIC_BEHAVIOR", "Target has an unsafe dynamic/conditional numeric address", field=key)
        # Dynamic limit and confirmation fields have no accepted source shape.
        # ExistingProgram already refuses unknown fields; retain this named
        # prerequisite if the graph contract gains more preserved kinds later.
        for key in ("MinValueVar", "MaxValueVar", "ConFirmWindow"):
            if section.one(key, False) is not None:
                raise HmiError("EXISTING_INTEGER_NUMERIC_BEHAVIOR", "Dynamic limits/confirmation are outside this numeric contract", field=key)
        if _decimal(section.one("GainValue")) != 1 or _decimal(section.one("OffsetValue")) != 0:
            raise HmiError("EXISTING_INTEGER_NUMERIC_SCALING", "Existing integer numeric edits require immutable identity scaling")
        _scalar(section.one("IntNum"))
        fractional = _scalar(section.one("DotNum"), 4)
        if is_input and fractional:
            raise HmiError("UNQUALIFIED_EXISTING_FRACTIONAL_INPUT", "An existing fractional input cannot be silently reinterpreted as F0")
        if not is_input and data_type == "INT" and fractional not in (0, 1, 4):
            raise HmiError("UNQUALIFIED_EXISTING_INTEGER_DISPLAY", "Signed source display is outside qualified F0/F1/F4")
        if is_input:
            low, high = _DOMAINS[data_type]
            minimum, maximum = (_decimal(section.one(key)) for key in ("MinValue", "MaxValue"))
            if (minimum != minimum.to_integral_value() or maximum != maximum.to_integral_value()
                    or not low <= minimum < maximum <= high):
                raise HmiError("EXISTING_INTEGER_NUMERIC_LIMIT", "Existing F0 input source must have strictly ordered integral WORD limits")
        return is_input, data_type

    def _changes(self, operations):
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > 4096:
            raise HmiError("INVALID_OPERATIONS", "Integer numeric operations require a bounded list")
        self.check()
        sections = self.source.document.sections
        owners = {(p["id"], o["id"]): o for p in _groups(self.source.document) for o in p["elements"]}
        section_indices = {id(section): i for i, section in enumerate(sections)}
        changes, seen = {}, set()

        def change(section, field, number):
            record = section.one(field)
            previous = _decimal(record) if field in {"MinValue", "MaxValue"} else _scalar(record)
            if previous == number:
                return  # Retain original equivalent vendor spelling byte for byte.
            record_index = next(i for i, r in enumerate(section.records) if r is record)
            changes[(section_indices[id(section)], record_index)] = str(number).encode("ascii")

        for operation in operations:
            if (not isinstance(operation, dict) or not _OPERATION_KEYS <= set(operation)
                    or set(operation) - _OPERATION_KEYS - {"raw_minimum", "raw_maximum"}
                    or operation.get("op") != "configure_existing_integer_numeric"
                    or operation.get("value_model") != "integer_fixed_decimal"):
                raise HmiError("INVALID_EXISTING_INTEGER_NUMERIC_OPERATION", "Only exact pinned integer numeric requests are supported")
            target = (_id(operation["screen_id"], "screen_id", 65535), _id(operation["element_id"], "element_id"))
            if target in seen:
                raise HmiError("DUPLICATE_EXISTING_INTEGER_NUMERIC", "Repeated native integer numeric owner is refused")
            seen.add(target)
            owner = owners.get(target)
            if owner is None:
                raise HmiError("MISSING_EXISTING_INTEGER_NUMERIC", "Numeric target is absent from the pinned source")
            digest = operation["owner_sha256"]
            extent = b"".join(s.bytes() for s in sections[owner["start"]:owner["end"]])
            if not isinstance(digest, str) or not _SHA.fullmatch(digest) or digest != _sha(extent):
                raise HmiError("EXISTING_INTEGER_NUMERIC_PIN", "Numeric target differs from its immutable original owner extent")
            is_input, data_type = self._target(owner)
            if operation["data_type"] != data_type:
                raise HmiError("EXISTING_INTEGER_NUMERIC_STORAGE", "Request cannot change or narrow existing WORD representation")
            integer, fractional = operation["integer_digits"], operation["fractional_digits"]
            if type(integer) is not int or type(fractional) is not int or not 1 <= integer <= 5:
                raise HmiError("EXISTING_INTEGER_NUMERIC_DIGITS", "Digit counts require bounded explicit integers")
            section = owner["section"]
            if is_input:
                if fractional != 0:
                    raise HmiError("UNQUALIFIED_EXISTING_FRACTIONAL_INPUT", "All fractional input lowering remains unqualified")
                if set(operation) != _OPERATION_KEYS | {"raw_minimum", "raw_maximum"}:
                    raise HmiError("INVALID_EXISTING_INTEGER_NUMERIC_OPERATION", "F0 input requires exactly its static raw minimum/maximum")
                minimum = _raw_limit(operation["raw_minimum"], "raw_minimum", data_type)
                maximum = _raw_limit(operation["raw_maximum"], "raw_maximum", data_type)
                if minimum >= maximum:
                    raise HmiError("EXISTING_INTEGER_NUMERIC_LIMIT", "Input raw limits must be strictly increasing")
                if integer < max(len(str(abs(minimum))), len(str(abs(maximum))), 1):
                    raise HmiError("EXISTING_INTEGER_NUMERIC_DIGITS", "Input integer digits cannot contain the declared raw limits")
                change(section, "MinValue", minimum)
                change(section, "MaxValue", maximum)
            else:
                allowed = (0, 1, 4) if data_type == "INT" else (0, 1, 2, 3, 4)
                if fractional not in allowed or integer != 5 - fractional:
                    raise HmiError("UNQUALIFIED_EXISTING_INTEGER_DISPLAY", "Display must cover its full WORD raw domain using qualified I=5-F")
                if set(operation) != _OPERATION_KEYS:
                    raise HmiError("INVALID_EXISTING_INTEGER_NUMERIC_OPERATION", "Display cannot acquire keypad-limit fields")
            change(section, "IntNum", integer)
            change(section, "DotNum", fractional)
        return changes

    def _spans(self, changes):
        spans, offset = [], 0
        for section_index, section in enumerate(self.source.document.sections):
            offset += len(section.header)
            for record_index, record in enumerate(section.records):
                end = offset + len(record.raw)
                if (section_index, record_index) in changes:
                    value = changes[(section_index, record_index)]
                    spans.append((offset, end, record.key.encode("ascii") + b"=" + value + b"\r\n"))
                offset = end
        return spans

    def spans(self, operations):
        return self._spans(self._changes(operations))

    def _expected(self, spans):
        body, cursor, result = self.source.envelope.body, 0, []
        for start, end, raw in spans:
            result.extend((body[cursor:start], raw)); cursor = end
        result.append(body[cursor:])
        return b"".join(result)

    def expected_body(self, operations):
        return self._expected(self.spans(operations))

    def apply(self, operations):
        changes = self._changes(operations)
        if not changes:
            return self.source.original
        document = deepcopy(self.source.document)
        for (section_index, record_index), value in changes.items():
            document.sections[section_index].records[record_index].set_value(value)
        body = document.bytes()
        if body != self.expected_body(operations):
            raise HmiError("EXISTING_INTEGER_NUMERIC_PRESERVATION", "Numeric mutation differs from independent original record spans")
        raw = self.source.envelope.encode(body)
        self.verify(NativeAdapter(raw, self.source.family), operations)
        return raw

    def verify(self, candidate, operations=None):
        operations = [] if operations is None else operations
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_INTEGER_NUMERIC_CANDIDATE", "Numeric verification requires a native candidate adapter")
        candidate._preserved_byte_binding("INVALID_INTEGER_NUMERIC_CANDIDATE")
        spans = self.spans(operations)
        expected = self._expected(spans)
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.body != expected or candidate.document.tail != self.source.document.tail):
            raise HmiError("EXISTING_INTEGER_NUMERIC_PRESERVATION", "Candidate differs outside approved original numeric scalar records")
        if not spans and candidate.original != self.source.original:
            raise HmiError("EXISTING_INTEGER_NUMERIC_PRESERVATION", "A numeric no-op must preserve the complete original file")
        restored, cursor, delta = [], 0, 0
        for start, end, raw in spans:
            saved_start = start + delta; saved_end = saved_start + len(raw)
            restored.extend((candidate.envelope.body[cursor:saved_start], self.source.envelope.body[start:end]))
            cursor = saved_end; delta += len(raw) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        if b"".join(restored) != self.source.envelope.body:
            raise HmiError("EXISTING_INTEGER_NUMERIC_PRESERVATION", "Numeric restoration failed to recover the complete source body")
        return True
