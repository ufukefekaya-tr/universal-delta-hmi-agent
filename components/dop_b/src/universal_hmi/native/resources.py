"""Bounded global Alarm resources; process/history/assets remain unchanged.

Parsing is structural framing evidence. Mutation additionally requires an
explicitly qualified source-local whole-tail fingerprint and full structural
suffix traversal. Unqualified binary resources are inspectable, never writable.
"""
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import math
import re
import struct

from ..errors import HmiError
from .codec import MAX_PAYLOAD
from .records import MAX_RECORDS, Document, Record, Section, is_wide, unsigned


_HEADER = re.compile(rb"\[([A-Za-z0-9][A-Za-z0-9_ -]*)\]")
_FIELD = re.compile(rb"([A-Za-z][A-Za-z0-9_ -]*)=(.*)")
_LATER = {"History", "TextBank", "NewTextBank", "Tag", "EthernetIPTag",
          "SRAM_DATA", "100_SRAM_DATA", "Picture", "Background", "SlotFile",
          "CWPFile", "DeviceTable", "DIATag", "Codesys", "MQTTFile", "SysMessage", "END"}
_ORDER = {"SubMacro": 0, "Global_Auxkey": 1, "Alarm": 2}
_SUFFIX_ORDER = {"History": 0, "TextBank": 1, "NewTextBank": 1,
                 "Tag": 2, "EthernetIPTag": 3, "SRAM_DATA": 4,
                 "100_SRAM_DATA": 4, "SysMessage": 5, "Picture": 6,
                 "Background": 7, "Codesys": 8, "DIATag": 9,
                 "DeviceTable": 10, "MQTTFile": 11, "END": 12}
_ENABLE = re.compile(r"AlarmEnable([0-9]{3,5})")
_TEXT = re.compile(r"wMessageLen([0-9]{3,5})-([0-9]+)")
_INDEXED = re.compile(r"Alarm(?:Enable|On)([0-9]{3,5})|AlarmTrigger(?:Operator|Max|Min)([0-9]{3,5})-[0-9]{3,5}")
_SCALAR_LEN = re.compile(r"(?:AlarmMemLen[0-9]+|WatchAddrReadLen[0-9-]+|ReadMemLen[0-9]*|ColumnReadLen[0-9]+)")
_SHA = re.compile(r"[0-9a-f]{64}")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?")
_GLOBALS = {"SampleCycle", "RecordNumber", "Hold", "AlmHoldPlace"}
_HISTORY_SCALARS = {
    "AutoStop#", "CSVTitleCol#", "CSVTitleRow#", "ColumnDataUnitCodeAddr#",
    "ColumnDisplayDotNum#", "ColumnDisplayUnitCodeAddr#", "ColumnDotNum#",
    "ColumnIntNum#", "ColumnIsCheck#", "ColumnMemFmt#", "ColumnMemPos#",
    "ColumnReadLen#", "DataClearStatusVar#", "DataClearVar#",
    "DataSamplingStatusVar#", "DataSamplingVar#", "DateFmt#",
    "EnableInterlock#", "EnableMultiFile#", "ExportCSV#", "HistoryClearStatusVar",
    "HistoryClearVar", "HistoryCount", "HistoryCtrlAddrContinue",
    "HistoryFlagAutoClear", "HistorySampleCycle", "HistorySamplingStatusVar",
    "HistorySamplingVar", "Hold#", "HoldPlace#", "InterlockVar#", "MultiFileName#",
    "MultiSaveTriggerNum#", "MultiSaveTriggerType#", "MultiSaveTriggerVar#",
    "Optimize", "ReadLink#", "ReadMemLen#", "ReadVar#", "SampleCycle#",
    "SampleNumber#", "Save#", "StrDateFmt#-#", "StrTimeFmt#-#", "TimeFmt#",
    "TimerCustom#", "TimerLink#", "TimerVar#", "Title#", "Trigger#",
    "UseDWORDinTrigger#", "UseKeepBuf#"}
_SUFFIX_SCALARS = {"History": _HISTORY_SCALARS,
                   "TextBank": {"wFont#"}, "NewTextBank": {"wFont#"},
                   "Tag": {"TagLinkCount"}, "SysMessage": {"LangName#"},
                   "DIATag": {"DIATagAutoSync"},
                   "DeviceTable": {"DisplayFormat", "EnableDownload"}}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _line(data, pos):
    end = data.find(b"\r\n", pos)
    if end < 0:
        raise HmiError("RESOURCE_FRAME", "Resource record lacks its CRLF terminator", offset=pos)
    line = data[pos:end]
    if b"\r" in line or b"\n" in line:
        raise HmiError("RESOURCE_FRAME", "Resource record contains an unframed line ending", offset=pos)
    return line, end + 2


def _record(data, start, line, pos, section):
    match = _FIELD.fullmatch(line)
    if match is None:
        if b"\0" in line or any(byte > 127 for byte in line):
            raise HmiError("UNSUPPORTED_RESOURCE_FRAME", "Unknown resource binary framing", section=section)
        return Record(data[start:pos]), pos
    key, value = match[1].decode("ascii"), match[2]
    kind = None
    if is_wide(key) or (section == "History" and re.fullmatch(r"ColumnLen[0-9]+", key)):
        kind = "wide"
    elif re.fullmatch(r"[A-Za-z0-9_]*MacroLen[0-9]*", key):
        kind = "macro"
    elif "Len" in key and not _SCALAR_LEN.fullmatch(key):
        raise HmiError("UNSUPPORTED_RESOURCE_FRAME", "Unknown length-bearing resource field", field=key)
    if kind is None:
        if b"\0" in value:
            raise HmiError("UNSUPPORTED_RESOURCE_FRAME", "Unframed resource binary value", field=key)
        return Record(data[start:pos], key, value), pos
    count = unsigned(value, key)
    if count > len(data) - pos:
        raise HmiError("RESOURCE_FRAME", "Resource frame exceeds the remaining bytes", field=key)
    blob = data[pos:pos + count]
    pos += count
    if count:
        if kind == "macro":
            if not blob.endswith(b"\r\n"):
                raise HmiError("RESOURCE_FRAME", "Macro frame must include its final CRLF", field=key)
        else:
            if data[pos:pos + 2] != b"\r\n":
                raise HmiError("RESOURCE_FRAME", "Resource frame lacks its trailing CRLF", field=key)
            pos += 2
            if count < 2 or count % 2 or not blob.endswith(b"\0\0"):
                raise HmiError("RESOURCE_TEXT", "Wide resource string requires even bytes and terminal NUL", field=key)
            try:
                text = blob[:-2].decode("utf-16-le", "strict")
            except UnicodeDecodeError as exc:
                raise HmiError("RESOURCE_TEXT", "Wide resource string has invalid UTF-16", field=key) from exc
            if "\0" in text:
                raise HmiError("RESOURCE_TEXT", "Wide resource string contains an embedded NUL", field=key)
    return Record(data[start:pos], key, value, blob, kind), pos


def _suffix_boundary(suffix):
    """Walk calibrated frames to END; no content search inside opaque blobs.

    The lengths, not the contents of a picture, tag block, database or XML,
    establish ownership. Unsupported grammar cannot establish global uniqueness.
    """
    if not suffix:
        return {"complete": True, "sections": [], "record_count": 0}
    pos = records = 0
    current = None
    seen, sections = set(), []
    while pos < len(suffix):
        start = pos
        line, pos = _line(suffix, pos)
        records += 1
        if records > MAX_RECORDS:
            raise HmiError("RESOURCE_LIMIT", "Resource record count exceeds the limit")
        header = _HEADER.fullmatch(line)
        special = line == b"[SysMessage]\0\0\0"
        if header:
            name = header[1].decode("ascii")
        elif special:
            name = "SysMessage"
        else:
            name = None
        if name is not None:
            if name in _ORDER or name in seen:
                raise HmiError("RESOURCE_ORDER", "Global resource section is repeated or out of order", section=name)
            if name not in _SUFFIX_ORDER:
                return {"complete": False, "sections": sections, "record_count": records,
                        "unsupported": name}
            if name == "SysMessage" and not special:
                return {"complete": False, "sections": sections, "record_count": records,
                        "unsupported": "SysMessage header framing"}
            if current and _SUFFIX_ORDER[name] <= _SUFFIX_ORDER[current]:
                raise HmiError("RESOURCE_ORDER", "Following resource section is out of order", section=name)
            seen.add(name)
            sections.append(name)
            current = name
            if name == "END":
                if pos != len(suffix):
                    raise HmiError("RESOURCE_ORDER", "Bytes follow the terminal END resource")
                return {"complete": True, "sections": sections, "record_count": records}
            if name in {"SRAM_DATA", "100_SRAM_DATA"}:
                if pos + 4 > len(suffix):
                    raise HmiError("RESOURCE_FRAME", "Resource database lacks its uint32 length")
                count = struct.unpack_from("<I", suffix, pos)[0]
                pos += 4
                if count > MAX_PAYLOAD or count > len(suffix) - pos:
                    raise HmiError("RESOURCE_FRAME", "Resource database exceeds its bounded frame")
                pos += count
                if suffix[pos:pos + 2] != b"\r\n":
                    raise HmiError("RESOURCE_FRAME", "Resource database lacks its trailing CRLF")
                pos += 2
            continue
        if current is None:
            raise HmiError("RESOURCE_SECTION", "Suffix records occur before a resource section")
        match = _FIELD.fullmatch(line)
        if match and current == "Tag" and match[1] == b"LinkSize":
            count = unsigned(match[2], "LinkSize")
            if count > len(suffix) - pos:
                raise HmiError("RESOURCE_FRAME", "Tag link block exceeds its bounded frame")
            if count and (count < 2 or suffix[pos + count - 2:pos + count] != b"\r\n"):
                raise HmiError("RESOURCE_FRAME", "Tag link block must include its final CRLF")
            pos += count
            continue
        if match and current in {"Picture", "Background", "Codesys"} and match[1] in {b"Size", b"size"}:
            expected_key = b"size" if current == "Codesys" else b"Size"
            if match[1] != expected_key:
                return {"complete": False, "sections": sections, "record_count": records,
                        "unsupported": current + "." + match[1].decode("ascii")}
            count = unsigned(match[2], expected_key.decode("ascii"))
            if count > len(suffix) - pos:
                raise HmiError("RESOURCE_FRAME", "Resource asset exceeds its bounded frame")
            pos += count
            if suffix[pos:pos + 2] != b"\r\n":
                raise HmiError("RESOURCE_FRAME", "Resource asset lacks its trailing CRLF")
            pos += 2
            continue
        if match and ((current == "EthernetIPTag" and match[1] == b"TagTotalSize")
                      or (current == "DIATag" and match[1] == b"DIATagResource")
                      or (current == "DeviceTable" and match[1] == b"DisplayLength")):
            if match[2] != b"0":
                return {"complete": False, "sections": sections, "record_count": records,
                        "unsupported": current + "." + match[1].decode("ascii")}
            continue
        key = match[1].decode("ascii") if match else ""
        wide_column = current == "History" and re.fullmatch(r"ColumnLen[0-9]+", key)
        normalized = re.sub(r"[0-9]+", "#", key)
        if not wide_column and normalized not in _SUFFIX_SCALARS.get(current, set()):
            return {"complete": False, "sections": sections, "record_count": records,
                    "unsupported": current + "." + key}
        try:
            _, pos = _record(suffix, start, line, pos, current)
        except HmiError as exc:
            if exc.code != "UNSUPPORTED_RESOURCE_FRAME":
                raise
            return {"complete": False, "sections": sections, "record_count": records,
                    "unsupported": current}
    return {"complete": False, "sections": sections, "record_count": records,
            "unsupported": "missing END"}


def _integer(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", value):
        raise HmiError("RESOURCE_INTEGER", "Resource integer needs canonical nonnegative decimal spelling", field=field)
    number = int(value)
    if number > 0xFFFFFFFF:
        raise HmiError("RESOURCE_INTEGER", "Resource integer exceeds uint32", field=field)
    return number


def _number(value, field):
    if type(value) is int:
        if value.bit_length() > 256:
            raise HmiError("RESOURCE_NUMBER", "Alarm number exceeds the decimal resource limit", field=field)
        value = str(value)
    elif type(value) is float:
        if not math.isfinite(value):
            raise HmiError("RESOURCE_NUMBER", "Alarm number must be finite", field=field)
        value = str(value)
    if not isinstance(value, str) or len(value) > 384 or not _DECIMAL.fullmatch(value):
        raise HmiError("RESOURCE_NUMBER", "Alarm number needs a bounded exact decimal", field=field)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise HmiError("RESOURCE_NUMBER", "Invalid alarm decimal", field=field) from exc
    if not result.is_finite() or not -324 <= result.adjusted() <= 308:
        raise HmiError("RESOURCE_NUMBER", "Alarm decimal exceeds the supported range", field=field)
    return result


def _ascii(value, field):
    try:
        return value.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("RESOURCE_TEXT", "Controlled scalar is not ASCII", field=field) from exc


def _numeric_value(value, spec, field, storage_required=False):
    kind = spec.get("kind")
    number = _number(value, field)
    low, high = _number(spec.get("minimum"), field), _number(spec.get("maximum"), field)
    if not isinstance(kind, str) or kind not in {"integer", "decimal"} or low > high or not low <= number <= high or (kind == "integer" and number != number.to_integral_value()):
        raise HmiError("INVALID_ALARM_VALUE", "Alarm numeric value exceeds its calibrated range", field=field)
    if not storage_required:
        return number
    storage = spec.get("storage")
    if not isinstance(storage, dict) or set(storage) != {"bits", "format"} or type(storage["bits"]) is not int or storage["bits"] not in {16, 32, 64} or not isinstance(storage["format"], str) or storage["format"] not in {"signed", "unsigned", "floating"}:
        raise HmiError("INVALID_ALARM_SCHEMA", "Trigger limits require a qualified storage width/format")
    bits, fmt = storage["bits"], storage["format"]
    if fmt == "floating":
        if bits == 16:
            raise HmiError("INVALID_ALARM_SCHEMA", "Floating alarm width is unqualified")
        try:
            represented = float(number)
            if bits == 32:
                represented = struct.unpack("<f", struct.pack("<f", represented))[0]
        except (OverflowError, struct.error) as exc:
            raise HmiError("INVALID_ALARM_VALUE", "Trigger limit exceeds its IEEE width") from exc
        if not math.isfinite(represented) or (number != 0 and represented == 0):
            raise HmiError("INVALID_ALARM_VALUE", "Trigger limit overflows or underflows its IEEE width")
    else:
        bounds = (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1) if fmt == "signed" else (0, 2 ** bits - 1)
        if number != number.to_integral_value() or not bounds[0] <= number <= bounds[1]:
            raise HmiError("INVALID_ALARM_VALUE", "Trigger limit exceeds its integer storage")
    return number


@dataclass
class ResourceTables:
    original: bytes
    prefix: bytes
    alarm: Section
    suffix: bytes

    @classmethod
    def parse(cls, tail):
        if not isinstance(tail, bytes) or len(tail) > MAX_PAYLOAD:
            raise HmiError("RESOURCE_LIMIT", "Resource tail must be bounded bytes")
        pos = records = 0
        current = None
        seen = set()
        alarm_start = None
        alarm = None
        while pos < len(tail):
            start = pos
            line, pos = _line(tail, pos)
            header = _HEADER.fullmatch(line)
            if header or line == b"[SysMessage]\0\0\0":
                name = header[1].decode("ascii") if header else "SysMessage"
                if alarm is not None and name in _LATER:
                    suffix = tail[start:]
                    _suffix_boundary(suffix)
                    return cls(tail, tail[:alarm_start], alarm, suffix)
                if name not in _ORDER:
                    raise HmiError("UNSUPPORTED_RESOURCE_SECTION", "Unknown section precedes the Alarm boundary", section=name)
                if name in seen or (current and _ORDER[name] <= _ORDER[current.name]):
                    raise HmiError("RESOURCE_ORDER", "Global resource section is repeated or out of order", section=name)
                seen.add(name)
                current = Section(name, tail[start:pos])
                if name == "Alarm":
                    alarm_start, alarm = start, current
                continue
            if current is None:
                raise HmiError("RESOURCE_SECTION", "Resource records occur before a section")
            if current.name == "Global_Auxkey":
                raise HmiError("UNSUPPORTED_RESOURCE_FRAME", "Populated global auxiliary keys require separate calibration")
            records += 1
            if records > MAX_RECORDS:
                raise HmiError("RESOURCE_LIMIT", "Resource record count exceeds the limit")
            record, pos = _record(tail, start, line, pos, current.name)
            current.records.append(record)
        if alarm is None:
            raise HmiError("MISSING_ALARM_RESOURCE", "No structurally framed Alarm resource exists")
        return cls(tail, tail[:alarm_start], alarm, b"")

    def bytes(self):
        return self.prefix + self.alarm.bytes() + self.suffix

    def inspect(self):
        controlled = {"Version", "AlarmCount", "ContinueAddr"}
        controlled.update(r.key for r in self.alarm.records if r.key and _ENABLE.fullmatch(r.key))
        self.alarm.check_unique(controlled)
        fields = self.alarm.fields(controlled)
        entries = []
        indexes = set()
        counts, triggers = {}, {}
        for record in self.alarm.records:
            count_match = re.fullmatch(r"AlarmTriggerCount([0-9]{3,5})", record.key or "")
            trigger_match = re.fullmatch(r"AlarmTrigger(Operator|Min|Max)([0-9]{3,5})-([0-9]{3,5})", record.key or "")
            if count_match:
                identity = int(count_match[1])
                if identity in counts:
                    raise HmiError("AMBIGUOUS_ALARM_TRIGGER", "Native trigger count repeats an index")
                counts[identity] = _integer(_ascii(record.value, record.key), record.key)
            if trigger_match:
                identity, subindex, part = int(trigger_match[2]), int(trigger_match[3]), trigger_match[1]
                parts = triggers.setdefault(identity, {}).setdefault(subindex, set())
                if part in parts:
                    raise HmiError("AMBIGUOUS_ALARM_TRIGGER", "Native trigger field repeats a serialized trigger")
                parts.add(part)
            match = _ENABLE.fullmatch(record.key or "")
            if match:
                identity = int(match[1])
                if identity in indexes:
                    raise HmiError("AMBIGUOUS_ALARM_INDEX", "Native alarm index has repeated spellings", index=identity)
                indexes.add(identity)
                spelling = _ascii(record.value, record.key)
                if spelling not in {"0", "1"}:
                    raise HmiError("RESOURCE_ENABLE", "Native alarm enable is not the observed 0/1 value", field=record.key)
                entries.append({"index": match[1], "enabled": spelling == "1"})
        capacity = _integer(fields["AlarmCount"], "AlarmCount") if "AlarmCount" in fields else None
        if capacity is not None and (len(entries) > capacity or any(i < 1 or i > capacity for i in indexes)):
            raise HmiError("RESOURCE_CAPACITY", "Serialized alarm entries exceed declared capacity")
        for identity in counts.keys() | triggers.keys():
            declared, actual = counts.get(identity), triggers.get(identity, {})
            if identity not in indexes or declared is None or len(actual) != declared or any(i < 1 or i > declared for i in actual) or any(parts != {"Operator", "Min", "Max"} for parts in actual.values()):
                raise HmiError("RESOURCE_TRIGGER_COUNT", "Declared trigger count differs from complete serialized triggers", index=identity)
        suffix = _suffix_boundary(self.suffix)
        return {"owner": "GLOBAL_ALARM", "semantic_qualification": "UNVERIFIED",
                "alarm_sha256": _sha(self.alarm.bytes()), "tail_sha256": _sha(self.bytes()),
                "prefix_sha256": _sha(self.prefix), "suffix_sha256": _sha(self.suffix),
                "version": fields.get("Version"),
                "capacity": capacity,
                "serialized_entry_count": len(entries), "enabled_entry_count": sum(e["enabled"] for e in entries),
                "entries": entries, "suffix_parsed": suffix["complete"], "suffix_framing": suffix}

    def _entry(self, index):
        matches = [r for r in self.alarm.records if r.key and _ENABLE.fullmatch(r.key)
                   and int(_ENABLE.fullmatch(r.key)[1]) == int(index)]
        if len(matches) != 1:
            raise HmiError("AMBIGUOUS_ALARM_INDEX" if matches else "MISSING_ALARM_INDEX",
                           "Alarm change requires exactly one existing serialized index", index=index)
        return matches[0]

    def apply(self, operation, schema):
        """One transactional batch on existing source-local Alarm records."""
        if not isinstance(operation, dict) or set(operation) != {"op", "expected_alarm_sha256", "updates"} or operation["op"] != "configure_alarm":
            raise HmiError("INVALID_ALARM_OPERATION", "Alarm operation requires exact provenance and update fields")
        contract = schema.get("alarm") if isinstance(schema, dict) else None
        if not isinstance(contract, dict) or contract.get("qualified") is not True:
            raise HmiError("UNQUALIFIED_ALARM", "Alarm mutation requires explicit source-local calibration")
        if not _suffix_boundary(self.suffix)["complete"]:
            raise HmiError("UNQUALIFIED_ALARM_SUFFIX", "Complete suffix ownership is required for global Alarm mutation")
        for key, actual in (("donor_tail_sha256", _sha(self.original)), ("suffix_sha256", _sha(self.suffix))):
            if not isinstance(contract.get(key), str) or not _SHA.fullmatch(contract[key]) or contract[key] != actual:
                raise HmiError("ALARM_PROVENANCE", "Qualified resource donor fingerprint does not match", field=key)
        expected = operation["expected_alarm_sha256"]
        if not isinstance(expected, str) or not _SHA.fullmatch(expected) or expected != _sha(self.alarm.bytes()):
            raise HmiError("ALARM_SOURCE_CHANGED", "Alarm source fingerprint does not match")
        version = _ascii(self.alarm.one("Version").value, "Version")
        if contract.get("version") != version:
            raise HmiError("ALARM_VERSION", "Alarm resource version does not match its calibrated profile")
        updates, mappings = operation["updates"], contract.get("fields")
        if not isinstance(updates, list) or not updates or len(updates) > 32768 or not isinstance(mappings, dict):
            raise HmiError("INVALID_ALARM_OPERATION", "Alarm updates require a nonempty bounded list and field mappings")
        inventory = self.inspect()  # Ambiguous controls cannot be hidden by a dict.
        if inventory["capacity"] is None:
            raise HmiError("UNQUALIFIED_ALARM", "Mutation requires an explicit native alarm capacity")
        work = deepcopy(self)
        seen = set()
        pairs = set()
        for update in updates:
            if not isinstance(update, dict) or set(update) != {"field", "value"}:
                raise HmiError("INVALID_ALARM_OPERATION", "Alarm update needs exact field and value")
            field = update["field"]
            if not isinstance(field, str) or field in seen:
                raise HmiError("INVALID_ALARM_OPERATION", "Alarm update field is invalid or repeated")
            seen.add(field)
            spec = mappings.get(field)
            if not isinstance(spec, dict):
                raise HmiError("UNQUALIFIED_ALARM_FIELD", "Alarm field has no calibrated mapping", field=field)
            source = self.alarm.one(field)
            guards = spec.get("preconditions")
            if not isinstance(guards, dict) or not guards:
                raise HmiError("ALARM_PRECONDITION", "Alarm mapping must pin its source-local companion fields", field=field)
            for guard, expected_value in guards.items():
                if not isinstance(guard, str) or not isinstance(expected_value, str) or self.alarm.one(guard).value.decode("latin-1") != expected_value:
                    raise HmiError("ALARM_PRECONDITION", "Alarm donor companion field does not match", field=guard)
            indexed = _INDEXED.fullmatch(field)
            if indexed:
                index = indexed[1] or indexed[2]
                self._entry(index)
                required = {"ContinueAddr", "ReadAlarmLink", "AlarmMemLen" + index}
                continuous = self.alarm.one("ContinueAddr").value
                if continuous == b"1":
                    required.add("ReadAlarmVar")
                    address = self.alarm.one("ReadAlarmVar").value
                elif continuous == b"0":
                    required.add("AlarmVar" + index)
                    address = self.alarm.one("AlarmVar" + index).value
                else:
                    raise HmiError("UNQUALIFIED_ALARM", "Alarm addressing mode is unqualified")
                if address in {b"", b"None"}:
                    raise HmiError("UNQUALIFIED_ALARM", "An unbound alarm trigger cannot be enabled or changed")
                for prefix in ("AlarmLink", "AlarmOn", "AlarmTriggerFmt", "AlarmTriggerIntNum", "AlarmTriggerDotNum", "AlarmTriggerCount"):
                    key = prefix + index
                    if self.alarm.one(key, False) is not None:
                        required.add(key)
                if not required <= guards.keys():
                    raise HmiError("ALARM_PRECONDITION", "Indexed alarm change lacks address/type/width preconditions", field=field)
            record = work.alarm.one(field)
            value = update["value"]
            if _TEXT.fullmatch(field):
                entry = self._entry(_TEXT.fullmatch(field)[1])
                if entry.key not in guards:
                    raise HmiError("ALARM_PRECONDITION", "Message change must pin its serialized alarm entry")
                maximum = spec.get("max_bytes")
                if spec.get("kind") != "text" or type(maximum) is not int or not 2 <= maximum <= 1048576 or not isinstance(value, str):
                    raise HmiError("INVALID_ALARM_SCHEMA", "Message mapping needs a bounded calibrated text length")
                try:
                    count = len(value.encode("utf-16-le", "strict")) + 2
                except UnicodeEncodeError as exc:
                    raise HmiError("RESOURCE_TEXT", "Alarm message has an invalid surrogate") from exc
                if count > maximum or "\0" in value or source.kind != "wide":
                    raise HmiError("RESOURCE_TEXT", "Alarm message violates its framed text contract")
                record.set_text(value)
            elif field in _GLOBALS or indexed:
                kind = spec.get("kind")
                if not isinstance(kind, str):
                    raise HmiError("INVALID_ALARM_SCHEMA", "Alarm scalar kind must be a string", field=field)
                if kind == "enum":
                    allowed = spec.get("values")
                    text = str(value) if type(value) is int else value
                    if not isinstance(allowed, list) or not allowed or not all(isinstance(v, str) and re.fullmatch(r"0|[1-9][0-9]{0,9}", v) for v in allowed) or len(set(allowed)) != len(allowed) or text not in allowed:
                        raise HmiError("INVALID_ALARM_VALUE", "Alarm enum is outside its calibrated values", field=field)
                    if field.startswith(("AlarmEnable", "AlarmOn")) and (set(allowed) - {"0", "1"}):
                        raise HmiError("INVALID_ALARM_SCHEMA", "Alarm bit values must use the observed 0/1 representation")
                    record.set_value(text.encode("ascii"))
                elif kind in {"integer", "decimal"}:
                    limit = field.startswith(("AlarmTriggerMin", "AlarmTriggerMax"))
                    number = _numeric_value(value, spec, field, limit)
                    if field.startswith(("AlarmEnable", "AlarmOn", "AlarmTriggerOperator")):
                        raise HmiError("INVALID_ALARM_SCHEMA", "Alarm control enumerations cannot use numeric reinterpretation")
                    if limit:
                        pair = spec.get("pair")
                        if not isinstance(pair, dict) or set(pair) != {"minimum_field", "maximum_field", "operator_field", "operator_value", "relation"} or pair.get("relation") != "ordered":
                            raise HmiError("UNQUALIFIED_ALARM_RANGE", "Trigger limit mutation requires a declared paired range/operator contract")
                        suffix = field.split("Min", 1)[1] if field.startswith("AlarmTriggerMin") else field.split("Max", 1)[1]
                        expected_pair = ("AlarmTriggerMin" + suffix, "AlarmTriggerMax" + suffix, "AlarmTriggerOperator" + suffix)
                        if tuple(pair[k] for k in ("minimum_field", "maximum_field", "operator_field")) != expected_pair or not isinstance(pair["operator_value"], str):
                            raise HmiError("UNQUALIFIED_ALARM_RANGE", "Trigger pair must belong to the same exact serialized trigger")
                        if guards.get(expected_pair[2]) != pair["operator_value"]:
                            raise HmiError("ALARM_PRECONDITION", "Trigger pair lacks its pinned operator")
                        self.alarm.one(expected_pair[0])
                        self.alarm.one(expected_pair[1])
                        pairs.add(expected_pair)
                    if _number(_ascii(source.value, field), field) != number:
                        text = format(number, "f")
                        if "." in text:
                            text = text.rstrip("0").rstrip(".")
                        if len(text) > 384:
                            raise HmiError("RESOURCE_NUMBER", "Emitted alarm literal exceeds its parser bound")
                        record.set_value(text.encode("ascii"))
                else:
                    raise HmiError("INVALID_ALARM_SCHEMA", "Alarm scalar mapping kind is unsupported", field=field)
            else:
                raise HmiError("UNSUPPORTED_ALARM_FIELD", "Alarm field has no calibrated mutation contract", field=field)
        for minimum, maximum, operator in pairs:
            if operator in seen:
                raise HmiError("UNQUALIFIED_ALARM_RANGE", "A paired range cannot change its operator in the same operation")
            specs = [mappings.get(key) for key in (minimum, maximum)]
            if not all(isinstance(s, dict) for s in specs) or any(specs[0].get(key) != specs[1].get(key) for key in ("kind", "storage", "pair")):
                raise HmiError("UNQUALIFIED_ALARM_RANGE", "Both paired limit mappings require one consistent type/storage/operator contract")
            for spec in specs:
                guards = spec.get("preconditions")
                if not isinstance(guards, dict) or not guards:
                    raise HmiError("ALARM_PRECONDITION", "Both paired limits must pin source-local companions")
                for guard, expected in guards.items():
                    if not isinstance(guard, str) or not isinstance(expected, str) or self.alarm.one(guard).value.decode("latin-1") != expected:
                        raise HmiError("ALARM_PRECONDITION", "Retained paired limit companion changed", field=guard)
            low = _numeric_value(_ascii(work.alarm.one(minimum).value, minimum), specs[0], minimum, True)
            high = _numeric_value(_ascii(work.alarm.one(maximum).value, maximum), specs[1], maximum, True)
            if low > high:
                raise HmiError("INVALID_ALARM_RANGE", "Resulting paired trigger range is inverted")
        result = work.bytes()
        reopened = ResourceTables.parse(result)
        if reopened.prefix != self.prefix or reopened.suffix != self.suffix:
            raise HmiError("ALARM_PRESERVATION", "Alarm change altered an unrelated global resource")
        reopened.inspect()
        return result


def _exact_keys(value, keys, code, message):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise HmiError(code, message)


_BOOL_COMPANION_PREFIXES = ("AlarmEnable", "AlarmVar", "AlarmOn", "AlarmMemLen", "AlarmScreenID")
_BOOL_COMPANION_KEY = re.compile(r"Alarm(?:Enable|Var|On|MemLen|ScreenID)[0-9]{3,5}")
_OTHER_ALARM_COMPANION_PREFIXES = ("AlarmLink", "AlarmTriggerFmt", "AlarmTriggerIntNum", "AlarmTriggerDotNum",
                                   "AlarmTriggerCount", "AlarmTriggerOperator", "AlarmTriggerMin", "AlarmTriggerMax")
_OTHER_ALARM_COMPANION_KEY = re.compile(r"(?:AlarmLink|AlarmTrigger(?:Fmt|IntNum|DotNum|Count))[0-9]{3,5}"
                                      r"|AlarmTrigger(?:Operator|Min|Max)[0-9]{3,5}-[0-9]{3,5}")
_WATCH_KEY = re.compile(r"WatchAddr[A-Za-z]*[0-9]{3,5}(?:-[0-9]{3,5})?")


def _alarm_aliases(section):
    """Validate protected namespaces and aliases before field projection.

    Malformed suffixes in a known address/polarity/message/formatter namespace
    are not opaque extension records. Other global and unknown keys retain
    their existing raw ownership; this is deliberately not an Alarm* ban.
    """
    seen = set()
    for record in section.records:
        key = record.key or ""
        if (key.startswith(_BOOL_COMPANION_PREFIXES) and not _BOOL_COMPANION_KEY.fullmatch(key)
                or key.startswith(_OTHER_ALARM_COMPANION_PREFIXES) and not _OTHER_ALARM_COMPANION_KEY.fullmatch(key)
                or key.startswith("wMessageLen") and not _TEXT.fullmatch(key)
                or key.startswith("WatchAddr") and not _WATCH_KEY.fullmatch(key)):
            raise HmiError("UNQUALIFIED_ALARM_INDEX", "Protected alarm field has an unqualified complete suffix", field=key)
        text = re.fullmatch(r"wMessageLen([0-9]+)-([0-9]+)", key)
        indexed = re.fullmatch(r"(Alarm[A-Za-z]+|WatchAddr[A-Za-z]*)([0-9]+)(?:-([0-9]+))?", key)
        if text:
            if not 3 <= len(text[1]) <= 5:
                raise HmiError("UNQUALIFIED_ALARM_INDEX", "Message index spelling is outside the bounded native grammar", field=key)
            identity = ("wMessageLen", int(text[1]), unsigned(text[2].encode("ascii"), key))
        elif indexed:
            if not 3 <= len(indexed[2]) <= 5 or (indexed[3] is not None and not 3 <= len(indexed[3]) <= 5):
                raise HmiError("UNQUALIFIED_ALARM_INDEX", "Alarm companion index spelling is outside the bounded native grammar", field=key)
            identity = (indexed[1], int(indexed[2]), int(indexed[3]) if indexed[3] else None)
        else:
            continue
        if identity in seen:
            raise HmiError("AMBIGUOUS_ALARM_INDEX", "Alarm field repeats a semantic index or language", field=key)
        seen.add(identity)


def alarm_ir_operations(tail: bytes, alarms: list, tags: list, schema: dict) -> list:
    """Resolve the qualified existing active-high BOOL message subset.

    Qualification is source-local. Nothing here creates alarm entries, infers
    native widths, changes history, or derives continuous trigger addresses.
    No-op requests pass the same source/type/coverage checks as changed text.
    An unrelated legacy tail remains opaque only when no public contract exists.
    """
    if not isinstance(alarms, list) or not isinstance(tags, list) or not isinstance(schema, dict):
        raise HmiError("INVALID_ALARM_IR", "Alarm IR, tags and schema need explicit arrays/object")
    if not isinstance(tail, bytes) or len(tail) > MAX_PAYLOAD:
        raise HmiError("RESOURCE_LIMIT", "Alarm IR source tail must be bounded bytes")
    if not alarms and "alarm_ir" not in schema:
        return []
    contract = schema.get("alarm_ir")
    _exact_keys(contract, {"qualified", "contract_version", "mode", "coverage", "entries"},
                "UNQUALIFIED_ALARM_IR", "Public alarms require an exact source-local BOOL message contract")
    if (contract["qualified"] is not True or type(contract["contract_version"]) is not int
            or contract["contract_version"] != 1 or contract["mode"] != "existing_bool_message"
            or contract["coverage"] != "all_enabled" or not isinstance(contract["entries"], dict)
            or len(contract["entries"]) > 32768 or len(alarms) > 32768):
        raise HmiError("UNQUALIFIED_ALARM_IR", "Public alarm contract is outside the existing BOOL message subset")
    table = ResourceTables.parse(tail)
    _alarm_aliases(table.alarm)
    inventory = table.inspect()
    if inventory["capacity"] is None or inventory["version"] is None:
        raise HmiError("UNQUALIFIED_ALARM_IR", "Public alarms require explicit source capacity and version")
    enabled = {int(item["index"]): item["index"] for item in inventory["entries"] if item["enabled"]}
    if len(alarms) != len(enabled) or set(contract["entries"]) != {
            item.get("id") for item in alarms if isinstance(item, dict) and isinstance(item.get("id"), str)}:
        raise HmiError("ALARM_COVERAGE", "Public alarms must map every enabled source entry exactly once")
    tag_map = {}
    for tag in tags:
        if not isinstance(tag, dict) or not isinstance(tag.get("id"), str) or not tag["id"] or tag["id"] in tag_map:
            raise HmiError("INVALID_ALARM_TAG", "Alarm tags require unique exact IDs")
        tag_map[tag["id"]] = tag
    low = schema.get("alarm")
    _exact_keys(low, {"qualified", "version", "donor_tail_sha256", "suffix_sha256", "fields"},
                "INVALID_ALARM_SCHEMA", "Public resource mapping requires exact qualification, provenance and fields")
    if not isinstance(low.get("fields"), dict):
        raise HmiError("UNQUALIFIED_ALARM", "Public message updates require a qualified low-level resource mapping")
    updates, all_updates, seen_ids, seen_indexes = [], [], set(), set()
    for alarm in alarms:
        _exact_keys(alarm, {"id", "tag", "text", "history_policy"}, "INVALID_ALARM_IR",
                    "Alarm IR needs exactly ID, tag, text and source history policy")
        aid, tag_id, message = alarm["id"], alarm["tag"], alarm["text"]
        if (not isinstance(aid, str) or not aid or aid.strip() != aid or aid in seen_ids
                or not isinstance(tag_id, str) or not tag_id or not isinstance(message, str) or not message
                or alarm["history_policy"] != "preserve_source"):
            raise HmiError("INVALID_ALARM_IR", "Public alarms require unique IDs, BOOL tags and preserve_source history")
        seen_ids.add(aid)
        entry = contract["entries"].get(aid)
        _exact_keys(entry, {"index", "message_field", "message_record_sha256", "trigger", "tag_contract", "native_binding"},
                    "UNQUALIFIED_ALARM_IR", "Alarm entry requires exact source, trigger and tag contracts")
        index, field = entry["index"], entry["message_field"]
        match = _TEXT.fullmatch(field) if isinstance(field, str) else None
        if (not isinstance(index, str) or not re.fullmatch(r"[0-9]{3,5}", index)
                or int(index) not in enabled or enabled[int(index)] != index or int(index) in seen_indexes
                or match is None or match[1] != index or unsigned(match[2].encode("ascii"), field) != 0):
            raise HmiError("ALARM_COVERAGE", "Alarm mapping needs one exact enabled index and its primary-language message")
        seen_indexes.add(int(index))
        source = table.alarm.one(field)
        if (source.kind != "wide" or not isinstance(entry["message_record_sha256"], str)
                or not _SHA.fullmatch(entry["message_record_sha256"])
                or entry["message_record_sha256"] != _sha(source.raw)):
            raise HmiError("ALARM_SOURCE_CHANGED", "Alarm message raw donor fingerprint does not match")
        trigger = entry["trigger"]
        _exact_keys(trigger, {"mode", "active_value", "link_owner", "preconditions", "storage"},
                    "UNQUALIFIED_ALARM_TRIGGER", "Alarm trigger requires an exact direct BOOL contract")
        required = {"ContinueAddr", "ReadAlarmLink", "AlarmEnable" + index,
                    "AlarmVar" + index, "AlarmOn" + index, "AlarmMemLen" + index}
        guards = trigger["preconditions"]
        _exact_keys(guards, required, "ALARM_PRECONDITION", "Direct BOOL alarms must pin all six explicit source companions")
        if (trigger["mode"] != "direct_bool" or type(trigger["active_value"]) is not int
                or trigger["active_value"] != 1 or trigger["link_owner"] != "global"):
            raise HmiError("UNQUALIFIED_ALARM_TRIGGER", "Only explicitly qualified direct active-high BOOL triggers are supported")
        storage = trigger["storage"]
        _exact_keys(storage, {"bits", "format", "native_mem_len"}, "UNQUALIFIED_ALARM_TRIGGER",
                    "BOOL storage needs its explicit bit and native width contract")
        if (type(storage["bits"]) is not int or storage["bits"] != 1 or storage["format"] != "bit"
                or storage["native_mem_len"] != "1"):
            raise HmiError("UNQUALIFIED_ALARM_TRIGGER", "Only the explicit qualified one-bit native width is bounded")
        for key, expected in guards.items():
            if not isinstance(expected, str) or table.alarm.one(key).value.decode("latin-1") != expected:
                raise HmiError("ALARM_PRECONDITION", "Alarm source companion differs from its pinned contract", field=key)
        if (guards["ContinueAddr"] != "0" or guards["AlarmEnable" + index] != "1"
                or guards["AlarmOn" + index] != "1" or guards["AlarmVar" + index] in {"", "None"}):
            raise HmiError("UNQUALIFIED_ALARM_TRIGGER", "Alarm addressing, enable or polarity is outside the direct BOOL subset")
        _integer(guards["ReadAlarmLink"], "ReadAlarmLink")
        if guards["AlarmMemLen" + index] != storage["native_mem_len"]:
            raise HmiError("UNQUALIFIED_ALARM_TRIGGER", "Source alarm width differs from its one-bit storage contract")
        # Numeric/per-entry/indirect trigger companions are not BOOL defaults.
        for record in table.alarm.records:
            key = record.key or ""
            indexed = re.fullmatch(r"(Alarm[A-Za-z]+)([0-9]{3,5})(?:-([0-9]{3,5}))?", key)
            if indexed and int(indexed[2]) == int(index) and (
                    indexed[2] != index or indexed[3] is not None
                    or indexed[1] not in {"AlarmEnable", "AlarmVar", "AlarmOn", "AlarmMemLen", "AlarmScreenID"}):
                raise HmiError("UNQUALIFIED_ALARM_TRIGGER", "BOOL source has an unqualified indexed trigger companion", field=key)
            watch = re.fullmatch(r"WatchAddr[A-Za-z]*([0-9]{3,5})(?:-([0-9]{3,5}))?", key)
            if watch and int(watch[1]) == int(index):
                raise HmiError("UNQUALIFIED_ALARM_MESSAGE", "Watch-address formatting requires a separate source contract", field=key)
        engineering = entry["tag_contract"]
        _exact_keys(engineering, {"data_type", "channel", "station", "byte_order", "word_order"},
                    "INVALID_ALARM_TAG", "Alarm tag contract must name datatype, station/channel and both byte orders")
        binding = entry["native_binding"]
        _exact_keys(binding, {"link", "mem_type"}, "INVALID_ALARM_TAG", "Alarm native binding needs exact link and memory type")
        tag = tag_map.get(tag_id)
        if (tag is None or engineering["data_type"] != "BOOL"
                or any(not isinstance(v, (str, int)) or isinstance(v, bool) for v in engineering.values())
                or any(tag.get(key) != value or type(tag.get(key)) is not type(value) for key, value in engineering.items())
                or tag.get("access") not in ("Read", "ReadWrite")
                or tag.get("address") != guards["AlarmVar" + index]
                or tag.get("native_binding") != binding):
            raise HmiError("INVALID_ALARM_TAG", "Alarm tag address, access or engineering contract differs from the source")
        if (any(not isinstance(value, str) for value in binding.values())
                or binding["link"] != guards["ReadAlarmLink"]):
            raise HmiError("INVALID_ALARM_TAG", "Alarm tag native link differs from the source-global link")
        _integer(binding["mem_type"], "mem_type")
        spec = low["fields"].get(field)
        _exact_keys(spec, {"kind", "max_bytes", "preconditions"}, "INVALID_ALARM_SCHEMA",
                    "Public message mapping permits only text length and the complete trigger guards")
        if spec["preconditions"] != guards:
            raise HmiError("ALARM_PRECONDITION", "Public and low-level message contracts must pin the same source companions")
        update = {"field": field, "value": message}
        all_updates.append(update)
        if source.text() != message:
            if "%" in message or "%" in source.text():
                raise HmiError("UNQUALIFIED_ALARM_MESSAGE", "Changed formatted alarm messages require a separate contract")
            updates.append(update)
    if seen_indexes != set(enabled):
        raise HmiError("ALARM_COVERAGE", "Public alarm mappings do not exactly cover enabled source entries")
    if not all_updates:
        # The empty qualified set still proves complete resource ownership.
        if (not inventory["suffix_parsed"] or low.get("qualified") is not True
                or low.get("version") != inventory["version"]
                or low.get("donor_tail_sha256") != _sha(tail) or low.get("suffix_sha256") != _sha(table.suffix)):
            raise HmiError("ALARM_PROVENANCE", "Empty public alarm coverage still needs exact source qualification")
        return []
    expected = _sha(table.alarm.bytes())
    # Validate every mapped message even if byte-identical; no-op is no bypass.
    table.apply({"op": "configure_alarm", "expected_alarm_sha256": expected, "updates": all_updates}, schema)
    return [{"op": "configure_alarm", "expected_alarm_sha256": expected, "updates": updates}] if updates else []


def expected_alarm_tail(tail: bytes, alarms: list, tags: list, schema: dict) -> bytes:
    """Reconstruct the entire expected tail from immutable source and IR."""
    operations = alarm_ir_operations(tail, alarms, tags, schema)
    result = tail
    for operation in operations:
        result = ResourceTables.parse(result).apply(operation, schema)
    return result


_VIEW_GEOMETRY = {"nPartsID", "X", "Y", "Width", "Height"}
_VIEW_VARIABLES = {"ReadVar", "WriteVar", "OffsetReadVar", "OffsetWriteVar", "GroupIDVar", "EventCtrlVar",
                   "SortCtrlVar", "SortOrderCtrlVar", "FilterCtrlVar", "FreqFilterVar", "CategoryStartVar", "CategoryEndVar"}
_VIEW_LINKS = {"ReadLink", "WriteLink", "ReadMemType", "WriteMemType", "OffsetReadLink", "OffsetWriteLink",
               "OffsetReadMemType", "OffsetWriteMemType"}
_VIEW_GROUP_PRESENTATION = {"EnableGroupID", "EnableGroupIDFilter"}
_VIEW_FOREIGN = _VIEW_VARIABLES | _VIEW_LINKS | _VIEW_GROUP_PRESENTATION | {
    "RelatedFileBrowserPartID", "ShowTime", "TimeFmt", "ShowDate", "DateFmt", "MoveCount", "MoveTime", "Direction"}


def _foreign_view_field(key):
    return (key in _VIEW_FOREIGN or re.fullmatch(r"(?:FunctionKeyPartID|EnableCol|DisplayOrder|ColWidth)[0-9]+", key)
            or re.fullmatch(r"TitleTextLen[0-9]+-[0-9]+", key))


def _view_identity(value, field):
    if (not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", value)
            or int(value) > 2147483647):
        raise HmiError("INVALID_ID", "Alarm owner identity must be a canonical nonnegative integer string", field=field)
    return value


def alarm_view_context(document, screen_id, element_id) -> dict:
    """Hash an inert source-local Type11 owner without projecting presentation.

    Every header, record, State, column, language and unknown byte is included.
    Only the first Element's exact identity/geometry records are excluded from
    the immutable digest, permitting approved cloning and geometry changes.
    """
    if not isinstance(document, Document):
        raise HmiError("UNQUALIFIED_ALARM_VIEW", "Alarm view context requires a parsed native document")
    screen_id, element_id = _view_identity(screen_id, "screen_id"), _view_identity(element_id, "element_id")
    for section in document.sections:
        if section.name in {"Application", "Screen", "State"}:
            for record in section.records:
                if _foreign_view_field(record.key or ""):
                    raise HmiError("UNQUALIFIED_ALARM_VIEW_REFERENCE", "Alarm view field occurs under a foreign owner",
                                   section=section.name, field=record.key)
    screens = [i for i, section in enumerate(document.sections) if section.name == "Screen"]
    seen_screens, target = set(), None
    for number, start in enumerate(screens):
        screen = document.sections[start]
        sid = _view_identity(_ascii(screen.one("ID").value, "ID"), "ID")
        if sid in seen_screens:
            raise HmiError("DUPLICATE_SCREEN", "Alarm owner screen identity is repeated")
        seen_screens.add(sid)
        if sid == screen_id:
            target = (start, screens[number + 1] if number + 1 < len(screens) else len(document.sections))
    if target is None:
        raise HmiError("UNKNOWN_SCREEN", "Alarm owner screen does not exist", screen_id=screen_id)
    start, end = target
    starts = [i for i in range(start + 1, end) if document.sections[i].name == "Element"]
    seen_elements, extent = set(), None
    for number, position in enumerate(starts):
        section = document.sections[position]
        eid = _view_identity(_ascii(section.one("nPartsID").value, "nPartsID"), "nPartsID")
        if eid in seen_elements:
            raise HmiError("DUPLICATE_ELEMENT", "Alarm owner element identity is repeated")
        seen_elements.add(eid)
        if eid == element_id:
            extent = document.sections[position:starts[number + 1] if number + 1 < len(starts) else end]
    if extent is None:
        raise HmiError("UNKNOWN_ELEMENT", "Alarm owner element does not exist", element_id=element_id)
    if any(section.name != "State" for section in extent[1:]):
        raise HmiError("UNQUALIFIED_ALARM_VIEW", "Alarm owner includes a section of unknown ownership")
    element = extent[0]
    element.check_unique(_VIEW_GEOMETRY | {"Type", "SubType"})
    kind = _ascii(element.one("Type").value, "Type")
    subtype = _ascii(element.one("SubType").value, "SubType")
    if kind != "11" or subtype not in {"1", "2", "4"}:
        raise HmiError("UNQUALIFIED_ALARM_VIEW", "Only current, history and strip Type11 owners are bounded")
    references = []
    for section_index, section in enumerate(extent):
        controlled = set()
        function_indexes = set()
        for record in section.records:
            key = record.key or ""
            function = re.fullmatch(r"FunctionKeyPartID[0-9]+", key)
            if key in _VIEW_VARIABLES or key in _VIEW_LINKS or function or key == "RelatedFileBrowserPartID":
                controlled.add(key)
                if function:
                    identity = unsigned(key[len("FunctionKeyPartID"):].encode("ascii"), key)
                    if identity in function_indexes:
                        raise HmiError("UNQUALIFIED_ALARM_VIEW_REFERENCE", "Function-key identity has repeated native spellings", field=key)
                    function_indexes.add(identity)
                value = _ascii(record.value, key)
                if key in _VIEW_LINKS:
                    _integer(value, key)
                if ((key in _VIEW_VARIABLES and value != "None")
                        or ((function or key == "RelatedFileBrowserPartID") and value != "-1")):
                    raise HmiError("UNQUALIFIED_ALARM_VIEW_REFERENCE", "Alarm view contains an active or unqualified reference", field=key)
                references.append({"section_index": section_index, "field": key, "value": value})
            elif (key.endswith(("Var", "Link", "MemType", "PartID", "ScreenID"))
                  or re.search(r"(?:Action|FunctionKey|FileBrowser|Ctrl|Filter|Group)", key)
                  and key not in _VIEW_GROUP_PRESENTATION):
                raise HmiError("UNQUALIFIED_ALARM_VIEW_REFERENCE", "Alarm view reference field has no bounded inert contract", field=key)
            if record.kind == "macro" and record.blob:
                raise HmiError("UNQUALIFIED_ALARM_VIEW_REFERENCE", "Alarm view contains executable macro bytes", field=key)
        section.check_unique(controlled)
    raw = b"".join(section.bytes() for section in extent)
    immutable = element.header + b"".join(record.raw for record in element.records if record.key not in _VIEW_GEOMETRY)
    immutable += b"".join(section.bytes() for section in extent[1:])
    return {"owner_sha256": _sha(raw), "immutable_sha256": _sha(immutable), "type": kind,
            "subtype": subtype, "reference_inventory": references}
