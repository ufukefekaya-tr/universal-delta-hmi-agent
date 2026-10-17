"""Original, transactional native adapters for explicitly qualified profiles."""
from copy import deepcopy
from collections import Counter
import hashlib
import re

from ..errors import HmiError
from .codec import Envelope
from .records import Document
from .numeric import (NUMERIC_FIELDS, FIXED_DECIMAL_MODEL, configure_numeric,
                      fixed_decimal_contract, verify_numeric_fields)
from .identity import canonical_model_id, model_ids_match
from . import macro_semantics
from .resources import ResourceTables
from .address_contract import AddressNamespace
from .storage_conversion import (storage_contract, validate_source as validate_storage_source,
                                 convert_storage, configure_converted, verify_converted)

# Fields observed in installed native examples. This list authorizes no enum
# meaning: each editable property still needs a qualified profile mapping.
_PROPERTIES = {"X", "Y", "Width", "Height", "Type", "SubType", "Style",
               "BorderColor", "nAngle", "opacity", "animated", "antialiasing",
               "bFreeze", "RoundRadius", "FgColor", "BgColor", "FontColor",
               "FontAlign", "FontBold", "FontItalic", "FontUnderline",
               "FontSize", "FontSize0", "FontRatio0", "FontName0", "Twinkles",
               "SoundIndex", "PictureAlign", "PictureStretch", "StretchMode",
               "TransEffect", "TransColor", "Penetrate", "ConFirmWindow",
               "Variation", "Order", "CloseScreen", "GoToScreenID"}
_OPS = {"set_property", "set_text", "bind", "clone_element", "clone_screen", "append_literal_page", "delete_element", "convert_numeric_storage",
        "rename_screen", "reorder_elements", "reorder_screens",
        "configure_numeric", "configure_goto", "configure_macro", "configure_alarm", "set_unit_caption"}
_ARGUMENTS = {
    "convert_numeric_storage": {"op", "screen_id", "element_id", "data_type"},
    "set_property": {"op", "screen_id", "element_id", "key", "value", "state_index"},
    "set_text": {"op", "screen_id", "element_id", "state_index", "language", "text"},
    "set_unit_caption": {"op", "screen_id", "element_id", "text", "expected_unit_baseline_sha256"},
    "bind": {"op", "screen_id", "element_id", "read", "write"},
    "clone_element": {"op", "source_screen", "source_element", "target_screen", "element_id"},
    "clone_screen": {"op", "source_screen", "screen_id", "name"},
    "append_literal_page": {"op", "screen_id", "name"},
    "delete_element": {"op", "screen_id", "element_id"},
    "rename_screen": {"op", "screen_id", "name"},
    "reorder_elements": {"op", "screen_id", "element_ids"},
    "reorder_screens": {"op", "screen_ids"},
    "configure_numeric": {"op", "screen_id", "element_id", "kind", "data_type", "minimum", "maximum",
                          "integer_digits", "fractional_digits", "gain", "offset", "value_model"},
    "configure_goto": {"op", "screen_id", "element_id", "target_screen"},
    "configure_macro": {"op", "owner", "field", "expected_program_sha256", "statements"},
    "configure_alarm": {"op", "expected_alarm_sha256", "updates"},
}

# Names observed in the read-only B prefix holdout; no field semantics or
# inherited behavior follows from retaining their exact source bytes.
_PRESERVED_GLOBALS = {"Application", "Multi-Language", "Global-Keypad", "Recipe", "Recipe32", "EnhanceRcp",
                      "Ethernet", "SIP", "RemoteCtrl", "VNCCtrl", "RTC", "VideoList", "LOG", "FTP", "FTPFile"}
_PRESERVED_STRUCTURAL = {"clone_element", "clone_screen", "append_literal_page", "delete_element", "rename_screen", "reorder_elements", "reorder_screens"}

# Exact observed DIAScreen serialized profile; retaining opaque bytes grants
# no driver, macro, command, renderer or family-wide format authority.
_DIA_PREFIX_POLICY = "diascreen_opaque_source_v1"
_DIA_PREFIX_NAMES = ("Application", "Multi-Language", "Global-Camera", "Event-Trigger", "Global-Keypad",
    "Recipe", "Recipe32", "EnhanceRcp", "Ethernet", "Modbus_TCP_Server", "WEB_OUTPUT", "SIP",
    "RemoteCtrl", "VNCCtrl", "RTC", "LOG", "FTP", "FTPFile", "DataExchange", "DataExchangeEnd",
    "LuaData", "ExtraZA_ZGSection")
_DIA_OPAQUE_LINES = {"Ethernet", "WEB_OUTPUT", "LuaData"}
_DIA_GEOMETRY = {"x": "X", "y": "Y", "width": "Width", "height": "Height"}

# Observed rich B page/literal shapes, pinned to immutable source bytes below.
# These names are framing bounds, not interpretations of flags or enum values.
# An opaque graph outside these records can still depend on owner/page counts.
_LITERAL_PAGE_FIELDS = {"VER", "ID", "wTextLen", "DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY",
                        "IsSubScreen", "IsKeypadScreen", "IsUseFrame", "IsUseTitleBar", "IsScreenRotate",
                        "wTitleTextLen000", "TitleTextFontName000", "TitleTextFontSize000", "TitleTextFontColor",
                        "wScreenDESCTextLen000", "RefreshRate", "IsPrintScreen", "HardCopyLeft", "HardCopyTop",
                        "HardCopyRight", "HardCopyBottom", "BaseScreenID", "ScreenAction", "BgColor", "Hidden",
                        "CycleMacroDelayTime", "ScreenLockVar", "OpenMacroLen", "CloseMacroLen", "CycleMacroLen"}
_LITERAL_ELEMENT_FIELDS = {"nPartsID", "Type", "SubType", "X", "Y", "Width", "Height", "GroupID", "Style",
                           "BorderColor", "PrintSuccessiveData", "ReadMemType", "WriteMemType", "ReadLink", "WriteLink",
                           "ReadVar", "WriteVar", "MemLen", "MemFmt", "Level", "OffsetReadMemType", "OffsetWriteMemType",
                           "OffsetReadVar", "OffsetWriteVar", "OffsetMemLen", "OffsetMemFmt", "nAngle", "bFreeze",
                           "wDescTextLen", "wDescTextLen0", "SmoothFont", "VisibleLink", "VisibleVar", "PosVary"}
_LITERAL_STATE_FIELDS = {"Value", "FgColor", "BgColor", "FontColor", "FontSize0", "FontRatio0", "FontName0",
                         "wTextLen0", "FontAlign", "FontBold", "FontItalic", "FontUnderline", "UsePictureCoord",
                         "PictureAlign", "TransEffect", "TransColor", "StretchMode", "PictureStretch", "Twinkles", "SoundIndex"}

# Shapes observed in the isolated vendor control sample. These bounds alone
# grant neither behavior meanings nor driver/PLC authority: exact source-local
# donors and separate property witnesses are mandatory for this mode.
_CONTROL_KINDS = {"set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display"}
_CONTROL_COMMON = (_LITERAL_ELEMENT_FIELDS - {"wDescTextLen", "SmoothFont", "PosVary"})
_CONTROL_BUTTON = {"PushTime", "SetLowSecurity", "InterLockLink", "InterLockVar", "InterLockLevel",
                   "ConFirmWindow", "NoMessage", "DispAsterisk", "BeforeExecMacroLen", "AfterExecMacroLen"}
_CONTROL_INPUT = {"TriggerLink", "TriggerVar", "Order", "MinValue", "MaxValue", "IntNum", "DotNum", "LeadingZero",
                  "GainValue", "OffsetValue", "Roundoff", "Variation", "SetLowSecurity", "InterLockLink", "InterLockVar",
                  "InterLockLevel", "BeforeExecMacroLen", "AfterExecMacroLen", "DispAsterisk", "FastRefresh", "Active",
                  "KeyPadLeft", "KeyPadTop", "KeyPadRight", "KeyPadBottom", "TitleHeight", "RangeFontSize", "RangeFontColor",
                  "NoMessage", "ShowOverRange", "UseCustKeypad", "KeypadScreenID"}
_CONTROL_INPUT |= {f"{name}{index:03}-000" for index in range(5) for name in ("wKPFStringLen", "KPFontSize", "KPFontName")}
_CONTROL_INPUT |= {f"{name}{index:03}" for index in range(5) for name in ("KPFontColor", "KPBkgndColor")}
_CONTROL_DISPLAY = {"IntNum", "DotNum", "LeadingZero", "GainValue", "OffsetValue", "Roundoff", "FastRefresh"}
_CONTROL_GEOMETRY = {"x": "X", "y": "Y", "width": "Width", "height": "Height"}
_CONTROL_STYLE = {"color": "FontColor", "fill": "BgColor", "state_fill": "BgColor", "font_size": "FontSize0"}

# Numeric-looking unknown records can contain PINs or captions. Only these
# observed engineering keys may expose a scalar; this grants no enum meaning.
_CALIBRATION_NUMERIC_FIELDS = (_PROPERTIES | _LITERAL_PAGE_FIELDS | _LITERAL_ELEMENT_FIELDS
    | _LITERAL_STATE_FIELDS | NUMERIC_FIELDS | {
        "TriggerLink", "TriggerMemType", "InterLockLink", "InterLockMemType", "InterLockValue",
        "ReadCtrlLink", "ReadCtrlVarSize", "ReadStatusLink", "ReadStatusVarSize", "CtrlMemFmt", "StatusMemFmt",
        "CtrlAreaSampleCycle", "CtrlScreen", "CtrlRecipe", "CtrlStartup", "CtrlMacro", "CtrlAlarm",
        "CtrlBacklight", "CtrlBuzzer", "CtrlLanguage", "CtrlPassword", "CtrlPrint", "CtrlHistory"})
_CALIBRATION_DRIVER_NUMERIC = re.compile(
    r"(?:HMIStationNr|DefPLCStationNr|PortNr|Interface|databits|stopbits|baud|parity|HMIPortNr|"
    r"CommDelayTime|CommTimeout|CommRetry|RemotePLCMode|RemotePLCServerPort)[0-9]+$")
_CALIBRATION_ADDRESS_FIELDS = {"ReadVar", "WriteVar", "OffsetReadVar", "OffsetWriteVar", "TriggerVar",
    "InterLockVar", "VisibleVar", "ScreenLockVar", "ReadCtrlVar", "ReadStatusVar", "UnitSrcVar", "UnitDisplayVar"}

# The exact observed default companion names are not enum interpretations.
# Their raw records stay immutable during caption-only edits. In particular,
# UnitDirection is not translated into a guessed position or pixel width.
_UNIT_REQUIRED = {"UnitType", "UnitSrc", "UnitSrcVar", "UnitDisplay", "UnitDisplayVar",
                  "UnitPercent", "UnitPercent1Var", "UnitPercent2Var", "UnitCustom1Var_1",
                  "UnitCustom2Var_1", "BackupUnitSrc", "BackupUnitDisplay", "ConvertConstByUnit",
                  "ShowUnit", "UnitDirection", "UnitFontSize0", "UnitFontName0",
                  "UnitTextLen0", "UnitBold", "UnitItalic", "UnitUnderline", "UnitFontColor"}


def _unit_related(key):
    # Include observed BackupUnit*/ConvertConstByUnit and unqualified kind
    # prefixes. A naming prefix is no authority to ignore an effective field.
    return isinstance(key, str) and "unit" in key.casefold()


def _unit_fields(section):
    """Control complete raw unit ownership without interpreting conversions."""
    controlled = set()
    for record in section.records:
        key = record.key
        if not _unit_related(key):
            continue
        controlled.add(key)
        for prefix in ("UnitTextLen", "UnitFontSize", "UnitFontName"):
            if key.startswith(prefix):
                index = key[len(prefix):]
                _identity(index, key)
                break
    section.check_unique(controlled)
    return controlled


def _string(value, label):
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\0"):
        raise HmiError("INVALID_VALUE", "Expected a nonempty string without control terminators", field=label)
    return value


def _integer(value, label, minimum=0, maximum=0x7FFFFFFF):
    if type(value) is not int or not minimum <= value <= maximum:
        raise HmiError("INVALID_INTEGER", "Integer is outside the qualified range", field=label)
    return value


def _identity(value, label):
    value = _string(value, label)
    maximum = str(0x7FFFFFFF)
    if (not re.fullmatch(r"0|[1-9][0-9]*", value) or len(value) > len(maximum)
            or (len(value) == len(maximum) and value > maximum)):
        raise HmiError("INVALID_ID", "Native identity must be a canonical nonnegative integer string", field=label)
    return value


def _decimal(value, label):
    if not re.fullmatch(r"-?[0-9]+", value):
        raise HmiError("NATIVE_INTEGER", "Native field is not a decimal integer", field=label)
    # A parser resource limit, not a PLC datatype conversion. This leaves all
    # signed/unsigned 64-bit values exact while bounding int() on native input.
    if len(value.lstrip("-")) > 64:
        raise HmiError("NATIVE_LIMIT", "Native integer exceeds the parser digit limit", field=label)
    return int(value)


def _target_string(value, label):
    if isinstance(value, str):
        return value
    if type(value) is int and 0 <= value <= 0xFFFFFFFF:
        return str(value)
    raise HmiError("INVALID_PROFILE", "Target metadata must be a string or uint32 integer", field=label)


def _value(section, field, required=True):
    record = section.one(field, required)
    return record.value.decode("latin-1") if record else None


def _controlled_fields(section):
    if section.name == "Application":
        return {"ModelName", "Version", "PanelName"}
    if section.name == "Screen":
        return {"ID", "wTextLen", "DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"}
    if section.name == "Element":
        controls = _PROPERTIES | {"nPartsID", "ReadVar", "ReadLink", "ReadMemType", "WriteVar", "WriteLink", "WriteMemType", "GoToScreenName"}
        if _value(section, "Type", False) in {"5", "6"} and _value(section, "SubType", False) == "1":
            controls |= NUMERIC_FIELDS | _unit_fields(section)
        return controls
    if section.name == "State":
        controls = _PROPERTIES | {"Value"}
        for record in section.records:
            if record.key and re.fullmatch(r"wTextLen[0-9]+", record.key):
                language = record.key[8:]
                if len(language) > 1 and language.startswith("0"):
                    raise HmiError("NATIVE_TEXT", "Native language text field needs a canonical index", field=record.key)
                controls.add(record.key)
        return controls
    return set()


def _groups(doc):
    screens = []
    starts = [i for i, s in enumerate(doc.sections) if s.name == "Screen"]
    seen = set()
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(doc.sections)
        section = doc.sections[start]
        identity = _identity(_value(section, "ID"), "ID")
        if identity in seen:
            raise HmiError("DUPLICATE_SCREEN", "Native screen identity is duplicated", screen_id=identity)
        seen.add(identity)
        elements = []
        element_starts = [i for i in range(start + 1, end) if doc.sections[i].name == "Element"]
        seen_elements = set()
        for index, elem_start in enumerate(element_starts):
            elem_end = element_starts[index + 1] if index + 1 < len(element_starts) else end
            element = doc.sections[elem_start]
            elem_id = _identity(_value(element, "nPartsID"), "nPartsID")
            if elem_id in seen_elements:
                raise HmiError("DUPLICATE_ELEMENT", "Native element identity is duplicated", screen_id=identity, element_id=elem_id)
            seen_elements.add(elem_id)
            states = [s for s in doc.sections[elem_start + 1:elem_end] if s.name == "State"]
            elements.append({"id": elem_id, "start": elem_start, "end": elem_end,
                             "section": element, "states": states})
        screens.append({"id": identity, "start": start, "end": end, "section": section, "elements": elements})
    return screens


def _screen(doc, identity):
    identity = _identity(identity, "screen_id")
    matches = [s for s in _groups(doc) if s["id"] == identity]
    if not matches:
        raise HmiError("UNKNOWN_SCREEN", "Native screen does not exist", screen_id=identity)
    return matches[0]


def _element(screen, identity):
    identity = _identity(identity, "element_id")
    matches = [e for e in screen["elements"] if e["id"] == identity]
    if not matches:
        raise HmiError("UNKNOWN_ELEMENT", "Native element does not exist", screen_id=screen["id"], element_id=identity)
    return matches[0]


def _native_int(section, key):
    text = _value(section, key, False)
    if text is None:
        return None
    return _decimal(text, key)


def _element_extent(doc, element):
    for section in doc.sections[element["start"] + 1:element["end"]]:
        if section.name != "State":
            raise HmiError("UNQUALIFIED_STRUCTURE", "Element extent contains a section with unqualified ownership",
                           element_id=element["id"], section=section.name)


def _screen_extent(doc, screen):
    seen_element = seen_aux = False
    for section in doc.sections[screen["start"] + 1:screen["end"]]:
        if section.name == "Element":
            seen_element = True
        elif section.name == "State" and seen_element:
            continue
        elif section.name == "AuxKeyElement" and not seen_element and not seen_aux and not section.records:
            # Only the empty leading marker is calibrated by the structural
            # fixture. Populated, repeated or trailing auxiliary sections and
            # unknown sections may be global; never guess their ownership.
            seen_aux = True
        else:
            raise HmiError("UNQUALIFIED_STRUCTURE", "Screen extent contains a section with unqualified ownership",
                           screen_id=screen["id"], section=section.name)


class NativeAdapter:
    """Source bytes stay immutable; each apply is an isolated transaction."""

    def __init__(self, data: bytes, family: str):
        self.original = data
        self.family = family
        self.envelope = Envelope.decode(data, family)
        self.document = Document.parse(self.envelope.body)
        if not self.document.sections or self.document.sections[0].name != "Application":
            raise HmiError("NATIVE_APPLICATION", "Missing Application section")
        self.application = self.document.sections[0]
        # Preserve opaque repeated records, but reject ambiguity in every field
        # used by semantic projection or qualified mutation before any dict can
        # silently select a last value, including no-op transactions.
        for section in self.document.sections:
            section.check_unique(_controlled_fields(section))
        self.model_id = _value(self.application, "ModelName")
        canonical_model_id(self.model_id)
        self.editor_version = _value(self.application, "Version")
        _groups(self.document)

    def inspect(self) -> dict:
        screens = []
        for s in _groups(self.document):
            name_record = s["section"].one("wTextLen", False)
            elements = []
            for e in s["elements"]:
                fields = e["section"].fields(_controlled_fields(e["section"]))
                texts = []
                states = []
                for index, state in enumerate(e["states"]):
                    state_fields = state.fields(_controlled_fields(state))
                    state_value = _value(state, "Value", False)
                    if state_value is not None and re.fullmatch(r"-?[0-9]+", state_value):
                        state_value = _decimal(state_value, "Value")
                    states.append({"state_index": index, "value": state_value, "native_fields": state_fields})
                    for record in state.records:
                        if record.key and re.fullmatch(r"wTextLen[0-9]+", record.key):
                            language = _decimal(record.key[8:], record.key)
                            if language > 0x7FFFFFFF:
                                raise HmiError("NATIVE_INTEGER", "Native language index is outside the supported range", field=record.key)
                            texts.append({"state_index": index, "language": language, "text": record.text()})
                bindings = {}
                for direction, native in (("read", "Read"), ("write", "Write")):
                    if native + "Var" in fields:
                        bindings[direction] = {"address": fields[native + "Var"],
                                               "link": fields.get(native + "Link"),
                                               "mem_type": fields.get(native + "MemType")}
                geometry = {k: _native_int(e["section"], n) for k, n in
                            (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height"))}
                unit_captions = []
                if (fields.get("Type"), fields.get("SubType")) in {("5", "1"), ("6", "1")}:
                    for record in e["section"].records:
                        if record.key and re.fullmatch(r"UnitTextLen[0-9]+", record.key):
                            unit_captions.append({"language": int(_identity(record.key[11:], record.key)),
                                                  "text": record.text(), "byte_count": len(record.blob or b""),
                                                  "frame_complete": bool(record.blob and len(record.blob) >= 2),
                                                  "qualification": "UNVERIFIED"})
                elements.append({"id": e["id"], "type": fields.get("Type"), "subtype": fields.get("SubType"),
                                 "native_fields": fields, "geometry": geometry, "texts": texts, "states": states,
                                 "bindings": bindings, "unit_captions": unit_captions})
            screens.append({"id": s["id"], "name": name_record.text() if name_record else "",
                            "native_fields": s["section"].fields(_controlled_fields(s["section"])), "elements": elements})
        # Expose framing/preservation evidence without returning opaque binary
        # bytes or treating macro source/resource tails as qualified emitters.
        framed_records = []
        owners = macro_semantics.owner_sections(self.document)
        for index, section in enumerate(self.document.sections):
            for record in section.records:
                if record.blob and record.kind != "wide":
                    owner = owners.get(index)
                    if record.kind == "macro" and (owner is None or record.key not in macro_semantics.OWNER_FIELDS[owner["kind"]]):
                        owner = None
                    framed_records.append({"section": section.name, "section_index": index,
                                           "screen_id": owner.get("screen_id") if owner else None,
                                           "element_id": owner.get("element_id") if owner else None,
                                           "field": record.key, "kind": record.kind,
                                           "byte_count": len(record.blob),
                                           "sha256": hashlib.sha256(record.blob).hexdigest()})
        tail = self.document.tail
        resources = {"status": "EMPTY", "byte_count": 0, "semantic_qualification": "UNVERIFIED"}
        if tail:
            try:
                resources = ResourceTables.parse(tail).inspect() | {"status": "GLOBAL_RESOURCE_FRAMING_PASS"}
            except HmiError as exc:
                # Unqualified/malformed global resources remain byte-preserved
                # during ordinary read-only access and unrelated native edits.
                unsupported = exc.code.startswith(("UNSUPPORTED_", "UNQUALIFIED_", "MISSING_"))
                resources = {"status": "OPAQUE_UNSUPPORTED" if unsupported else "MALFORMED_RESOURCE",
                             "error_code": exc.code, "byte_count": len(tail),
                             "semantic_qualification": "UNVERIFIED"}
        return {"family": self.family, "format": "dpa" if self.family == "delta_diascreen" else "dps",
                "model_id": self.model_id, "editor_version": self.editor_version,
                "panel_name": _value(self.application, "PanelName", False),
                "source_sha256": hashlib.sha256(self.original).hexdigest(),
                "qualification": "UNVERIFIED", "screens": screens, "framed_records": framed_records,
                "macros": macro_semantics.inventory(self.document),
                "resources": resources,
                "opaque_tail": {"byte_count": len(tail), "sha256": hashlib.sha256(tail).hexdigest(),
                                "parsed": False}}

    @staticmethod
    def _calibration_records(section):
        """Observed framing, without exporting captions, macros or credentials.

        These are evidence rows, not native property/enum qualifications.
        Even a scalar zero must receive a separately justified interpretation.
        """
        result = []
        for record in section.records:
            row = {"key": record.key, "kind": record.kind or "scalar"}
            if record.key and re.search(r"password|passwd|pwd|passcode|pincode|pin$|secret|token|credential|login|account|username|userid|accesscode|authkey|accesskey|apikey|privatekey|encryptionkey", record.key, re.I):
                row["redacted"] = True
            else:
                row.update(raw_sha256=hashlib.sha256(record.raw).hexdigest(), bytes=len(record.raw))
                if record.blob is not None:
                    row.update(framed_bytes=len(record.blob), value_exported=False)
                elif record.key is not None:
                    try:
                        value = record.value.decode("ascii", "strict")
                    except UnicodeError:
                        value = None
                    engineering_key = record.key in {"ModelName", "Version", "PanelName", "PanelSeries"} or bool(
                        re.fullmatch(r"(?:ControllerSection|ControllerName|CommName)[0-9]+", record.key)) or record.key in _CALIBRATION_ADDRESS_FIELDS
                    numeric_literal = value is not None and bool(re.fullmatch(r"-?[0-9]{1,64}(?:\.[0-9]{1,64})?", value))
                    if (value is not None and len(value) <= 256 and all(32 <= ord(c) <= 126 for c in value)
                            and (engineering_key or (numeric_literal and (record.key in _CALIBRATION_NUMERIC_FIELDS
                                or _CALIBRATION_DRIVER_NUMERIC.fullmatch(record.key))))):
                        row["observed_scalar"] = value
                    else:
                        row["value_exported"] = False
            result.append(row)
        return result

    def calibration_inventory(self):
        """Source-bound input for command/type/driver qualification.

        No caption, description, field name, enum value or address presence is
        promoted to a button behavior, primitive datatype or write permission.
        This makes global/driver dependencies visible before a new machine
        program is built; it never authorizes copying them into that program.
        """
        self._preserved_byte_binding("INVALID_CALIBRATION_SOURCE")
        if sum(len(section.records) for section in self.document.sections) > 250000:
            raise HmiError("CALIBRATION_LIMIT", "Source observation capture exceeds its record limit")
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        records = self.application.records
        marker = re.compile(r"ControllerSection(0|[1-9][0-9]*)$")
        marker_counts = Counter(record.key for record in records if record.key and marker.fullmatch(record.key))
        marker_findings = []
        for index, record in enumerate(records):
            if record.key and record.key.startswith("ControllerSection"):
                if not marker.fullmatch(record.key):
                    marker_findings.append({"record": index, "key": record.key, "code": "NONCANONICAL_CONTROLLER_MARKER"})
                elif marker_counts[record.key] > 1:
                    marker_findings.append({"record": index, "key": record.key, "code": "REPEATED_CONTROLLER_MARKER"})
        boundaries = []
        for index, record in enumerate(records):
            if record.key and (marker.fullmatch(record.key) or record.key == "PrinterSection0"):
                boundaries.append((index, record.key))
        drivers = []
        for number, (start, key) in enumerate(boundaries):
            match = marker.fullmatch(key)
            if match is None:
                continue
            stop = boundaries[number + 1][0] if number + 1 < len(boundaries) else None
            span = records[start:stop] if stop is not None else records[start:]
            # An unterminated span is displayed as unresolved, not assumed to
            # encompass the remainder of Application as a controller block.
            section = deepcopy(self.application)
            section.records = deepcopy(span)
            keys = Counter(record.key for record in span if record.key is not None)
            drivers.append({"native_index": match[1], "start_record": start, "end_record_exclusive": stop,
                "marker_unique": marker_counts[key] == 1,
                "boundary_evidence": "OBSERVED_NEXT_MARKER" if stop is not None else "UNRESOLVED",
                "raw_span_sha256": digest(b"".join(record.raw for record in span)),
                "ambiguous_keys": sorted(key for key, count in keys.items() if count > 1),
                "records": self._calibration_records(section), "driver_semantics": "UNVERIFIED",
                "station_link_address_grammar": "UNVERIFIED", "byte_word_order": "UNVERIFIED"})
        pages = _groups(self.document)
        if sum(len(page['elements']) for page in pages) > 10000:
            raise HmiError("CALIBRATION_LIMIT", "Source observation capture exceeds its owner limit")
        prefix_stop = pages[0]["start"] if pages else len(self.document.sections)
        global_sections = [{"name": section.name, "section_index": index,
                            "raw_sha256": digest(section.bytes()), "records": self._calibration_records(section)}
                           for index, section in enumerate(self.document.sections[:prefix_stop])]
        owners = []
        def observed_enum(section, key):
            value = _value(section, key, False)
            return value if value is not None and re.fullmatch(r"-?[0-9]{1,64}", value) else None
        for page in pages:
            for element in page["elements"]:
                owner_sections = self.document.sections[element["start"]:element["end"]]
                raw = b"".join(part.bytes() for part in owner_sections)
                try:
                    _element_extent(self.document, element)
                    structure = "OBSERVED_ELEMENT_AND_STATES"
                except HmiError:
                    structure = "UNRESOLVED_SECTION_OWNERSHIP"
                owners.append({"screen_id": page["id"], "element_id": element["id"],
                    "raw_span_sha256": digest(raw), "section_ownership": structure,
                    "observed_type": observed_enum(element["section"], "Type"),
                    "observed_subtype": observed_enum(element["section"], "SubType"),
                    "sections": [{"name": part.name, "raw_sha256": digest(part.bytes()),
                                  "records": self._calibration_records(part)} for part in owner_sections],
                    "button_behavior": "UNVERIFIED", "primitive_width_format": "UNVERIFIED",
                    "read_write_permission": "UNVERIFIED", "picture_macro_conditional_semantics": "UNVERIFIED"})
        return {"scope": "SOURCE_CALIBRATION_OBSERVATIONS_ONLY", "source_sha256": digest(self.original),
                "family": self.family, "model_id": self.model_id, "serialized_version": self.editor_version,
                "vendor_executable_build": "UNVERIFIED", "driver_blocks": drivers,
                "controller_marker_findings": marker_findings, "global_sections": global_sections,
                "page_headers": [{"screen_id": page["id"], "raw_sha256": digest(page["section"].bytes()),
                                  "records": self._calibration_records(page["section"])} for page in pages],
                "owners": owners, "opaque_envelope": {"thumbnail_sha256": digest(self.envelope.thumbnail),
                    "prefix_sha256": digest(self.envelope.prefix), "tail_sha256": digest(self.document.tail),
                    "graph_dependencies": "UNKNOWN"},
                "qualification": "UNVERIFIED", "emission_authority": False,
                "vendor": "NOT_RUN", "physical": "NOT_RUN"}

    def _schema(self, profile):
        if not isinstance(profile, dict):
            raise HmiError("INVALID_PROFILE", "Profile must be an object")
        if profile.get("family") != self.family or not model_ids_match(profile.get("model_id"), self.model_id) or profile.get("editor_version") != self.editor_version:
            raise HmiError("PROFILE_MISMATCH", "Profile family, native model ID and editor version must match the source")
        schema = profile.get("native_schema")
        if not isinstance(schema, dict) or schema.get("qualified") is not True:
            raise HmiError("UNQUALIFIED_NATIVE", "Mutation requires an explicitly qualified native schema")
        for key in ("properties", "bindings"):
            if key in schema and not isinstance(schema[key], dict):
                raise HmiError("INVALID_SCHEMA", "Native schema mappings must be objects", field=key)
        for key in ("model_id", "editor_version"):
            if key in schema and ((key == "model_id" and not model_ids_match(schema[key], self.model_id))
                                  or (key == "editor_version" and _target_string(schema[key], key) != self.editor_version)):
                raise HmiError("PROFILE_MISMATCH", "Native schema target does not match the source", field=key)
        self._diascreen_contract(schema)
        return schema

    def page_baseline(self, screen_id):
        """Pure signature of a deliberately narrow original-plain page.

        This is not a vendor page qualification. Page-level inheritance,
        locks, macros, resources and unknown behavior must never become
        implicit defaults when an empty donor is cloned by the service.
        Objects may already exist on a saved new page: their complete known
        extents are checked, but their bytes are not part of this signature.
        """
        screen = _screen(self.document, screen_id)
        auxiliary = self._plain_extent(screen)
        section = screen["section"]
        required = {"VER", "ID", "wTextLen", "DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"}
        section.check_unique(required)
        if len(section.records) != len(required) or {record.key for record in section.records} != required:
            raise HmiError("UNQUALIFIED_PAGE_BASELINE", "Plain page has unknown, missing or unkeyed page records", screen_id=screen["id"])
        if section.one("VER").kind is not None or section.one("VER").value != b"16":
            raise HmiError("UNQUALIFIED_PAGE_BASELINE", "Plain page requires exact observed VER=16")
        for key in ("ID", "DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"):
            record = section.one(key)
            if record.kind is not None:
                raise HmiError("UNQUALIFIED_PAGE_BASELINE", "Plain page scalar cannot contain framed data", field=key)
            identity = _identity(record.value.decode("latin-1"), key)
            if key != "ID" and identity == "0":
                raise HmiError("UNQUALIFIED_PAGE_BASELINE", "Plain page dimensions must be positive", field=key)
        name = section.one("wTextLen")
        if name.kind != "wide" or name.blob is None or len(name.blob) < 2:
            raise HmiError("UNQUALIFIED_PAGE_BASELINE", "Plain page name needs a complete framed UTF-16 record")
        name.text()
        fixed = section.header + b"".join(record.raw for record in section.records if record.key not in {"ID", "wTextLen"}) + auxiliary.header
        return hashlib.sha256(fixed).hexdigest()

    @staticmethod
    def _unit_owner(document, screen_id, element_id, editable=True):
        screen = _screen(document, screen_id)
        _screen_extent(document, screen)
        element = _element(screen, element_id)
        _element_extent(document, element)
        for owner in (document.sections[0], screen["section"]):
            if any(_unit_related(record.key) for record in owner.records):
                raise HmiError("UNQUALIFIED_UNIT_OWNER", "Unit-related fields occur in an unqualified page/application owner")
        for state in element["states"]:
            if any(_unit_related(record.key) for record in state.records):
                raise HmiError("UNQUALIFIED_UNIT_OWNER", "Unit-related fields occur in an unqualified State owner")
        section = element["section"]
        section.check_unique({"Type", "SubType"})
        for key in ("Type", "SubType"):
            if section.one(key).kind is not None:
                raise HmiError("UNQUALIFIED_UNIT_OWNER", "Numeric unit kind must be an exact native scalar", field=key)
        if (_value(section, "Type"), _value(section, "SubType")) not in {("5", "1"), ("6", "1")}:
            raise HmiError("UNQUALIFIED_UNIT_OWNER", "Unit caption has no observed numeric Element owner")
        controls = _unit_fields(section)
        if not _UNIT_REQUIRED <= controls:
            raise HmiError("UNQUALIFIED_UNIT_BASELINE", "Numeric unit owner lacks observed companion records",
                           fields=sorted(_UNIT_REQUIRED - controls))
        for record in section.records:
            if record.key not in controls:
                continue
            if re.fullmatch(r"UnitTextLen[0-9]+", record.key):
                if record.kind != "wide" or record.blob is None:
                    raise HmiError("UNQUALIFIED_UNIT_FRAME", "Unit caption requires its exact UTF-16 framing", field=record.key)
                record.text()
            elif record.kind is not None:
                raise HmiError("UNQUALIFIED_UNIT_BASELINE", "Unit companion has unqualified binary framing", field=record.key)
        primary = section.one("UnitTextLen0")
        if editable and len(primary.blob) < 2:
            # Zero-length frames may be read and retained, but no installed
            # unit specimen calibrates changing one into a NUL text frame.
            raise HmiError("UNQUALIFIED_UNIT_FRAME", "Primary unit caption needs an existing NUL text frame")
        if section.one("ShowUnit").value not in (b"0", b"1"):
            raise HmiError("UNQUALIFIED_UNIT_BASELINE", "Unit visibility requires an observed exact scalar flag")
        if editable and section.one("ShowUnit").value != b"1":
            raise HmiError("INACTIVE_UNIT_CAPTION", "Unit caption editing requires an enabled native donor")
        return section

    @staticmethod
    def _unit_signature(section, include_caption=False):
        raw = b"".join(record.raw for record in section.records
                       if record.key in {"Type", "SubType", "ShowUnit"}
                       or (_unit_related(record.key)
                           and (include_caption or record.key != "UnitTextLen0")))
        return hashlib.sha256(raw).hexdigest()

    def unit_baseline(self, screen_id, element_id):
        """Pure source-local raw companion signature for an enabled unit.

        A caption is an Element-owned UTF-16 string. This signature does not
        qualify UnitDirection, conversion enums, font rendering or fit. Every
        unit-related raw companion (including BackupUnit/ConvertConstByUnit,
        secondary languages and unknown extensions) stays bound; primary
        caption bytes alone are excluded.
        """
        return self._unit_signature(self._unit_owner(self.document, screen_id, element_id))

    def unit_context_baseline(self, screen_id, element_id):
        """Read-only raw signature including every caption and companion.

        Disabled and zero-length frames can be retained without granting the
        caption mutation precondition. This is raw preservation evidence, not
        a conversion, placement or native visual qualification.
        """
        section = self._unit_owner(self.document, screen_id, element_id, editable=False)
        return self._unit_signature(section, include_caption=True)

    @staticmethod
    def _unit_mapping(schema, section):
        spec = schema.get("unit_caption")
        if not isinstance(spec, dict) or spec.get("qualified") is not True:
            raise HmiError("UNQUALIFIED_UNIT_CAPTION", "Unit caption edits require a separately qualified schema")
        if (set(spec) != {"qualified", "owner", "field", "kinds"}
                or spec["owner"] != "Element" or spec["field"] != "UnitTextLen0"):
            raise HmiError("INVALID_SCHEMA", "Unit caption mapping must declare its exact owner and primary field")
        kinds = spec["kinds"]
        if not isinstance(kinds, dict) or set(kinds) != {"numeric_input", "numeric_display"}:
            raise HmiError("INVALID_SCHEMA", "Unit caption mapping requires both exact numeric kinds")
        observed = []
        for kind, match in kinds.items():
            if not isinstance(match, dict) or set(match) != {"Type", "SubType"}:
                raise HmiError("INVALID_SCHEMA", "Unit numeric kind needs exact Type/SubType fields", field=kind)
            pair = (match["Type"], match["SubType"])
            expected = ("6", "1") if kind == "numeric_input" else ("5", "1")
            if pair != expected:
                raise HmiError("INVALID_SCHEMA", "Named unit numeric kind differs from its exact observed mapping", field=kind)
            observed.append(pair)
        if len(set(observed)) != 2:
            raise HmiError("INVALID_SCHEMA", "Unit numeric kinds must remain distinct")
        numeric = schema.get("numeric")
        if numeric is not None and (not isinstance(numeric, dict) or numeric.get("qualified") is not True
                                    or numeric.get("kinds") != kinds):
            raise HmiError("INVALID_SCHEMA", "Unit numeric kind mapping contradicts the numeric schema")
        if (_value(section, "Type"), _value(section, "SubType")) not in observed:
            raise HmiError("UNQUALIFIED_UNIT_OWNER", "Unit owner does not match its qualified numeric mapping")

    def _unit_preconditions(self, document, operation, schema, original_adapter):
        section = self._unit_owner(document, operation.get("screen_id"), operation.get("element_id"))
        self._unit_mapping(schema, section)
        expected = operation.get("expected_unit_baseline_sha256")
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise HmiError("INVALID_UNIT_BASELINE", "Unit caption operation requires a canonical baseline SHA-256")
        original = self._unit_owner(original_adapter.document, operation.get("screen_id"), operation.get("element_id"))
        if self._unit_signature(original) != expected or self._unit_signature(section) != expected:
            raise HmiError("UNIT_BASELINE_MISMATCH", "Unit companions differ from the immutable source baseline")
        return section

    def _unit_caption(self, document, operation, schema):
        section = self._unit_preconditions(document, operation, schema, self)
        section.one("UnitTextLen0").set_text(operation.get("text"))

    def verify_unit_caption(self, operation, schema, original_adapter):
        """Pure caption and source-companion check on a saved candidate."""
        if (not isinstance(original_adapter, NativeAdapter) or original_adapter.family != self.family
                or not model_ids_match(original_adapter.model_id, self.model_id)
                or original_adapter.editor_version != self.editor_version):
            raise HmiError("INVALID_UNIT_SOURCE", "Unit calibration requires the exact source target identity")
        if (not isinstance(operation, dict) or operation.get("op") != "set_unit_caption"
                or set(operation) != _ARGUMENTS["set_unit_caption"]):
            raise HmiError("INVALID_OPERATION", "Unit verification requires one exact caption operation")
        if not isinstance(schema, dict):
            raise HmiError("INVALID_SCHEMA", "Unit verification requires a native schema object")
        if schema.get("qualified") is not True:
            raise HmiError("UNQUALIFIED_NATIVE", "Unit verification requires an explicitly qualified native schema")
        text = operation.get("text")
        if not isinstance(text, str) or "\0" in text:
            raise HmiError("INVALID_TEXT", "Text must be a string without embedded NUL")
        try:
            text.encode("utf-16-le", "strict")
        except UnicodeEncodeError as exc:
            raise HmiError("INVALID_TEXT", "Text contains an invalid Unicode surrogate") from exc
        section = self._unit_preconditions(self.document, operation, schema, original_adapter)
        primary = section.one("UnitTextLen0")
        if primary.text() != text:
            raise HmiError("UNIT_CAPTION_MISMATCH", "Saved unit caption differs from its exact requested text")
        original = self._unit_owner(original_adapter.document, operation.get("screen_id"), operation.get("element_id")).one("UnitTextLen0")
        if original.text() == text and primary.raw != original.raw:
            raise HmiError("UNIT_CAPTION_MISMATCH", "Semantic unit no-op altered the original primary record bytes")
        return True

    def _plain_extent(self, screen):
        _screen_extent(self.document, screen)
        index = screen["start"] + 1
        if (index >= screen["end"] or self.document.sections[index].name != "AuxKeyElement"
                or self.document.sections[index].records):
            raise HmiError("UNQUALIFIED_STRUCTURE", "Plain page requires an immediate empty auxiliary marker", screen_id=screen["id"])
        for element in screen["elements"]:
            _element_extent(self.document, element)
        return self.document.sections[index]

    def owner_extent_sha256(self, screen_id, element_id):
        """Digest current parsed Element/States, including identity/geometry.

        This projection signature is saved-file evidence only after the
        preserved layout verifier binds the projection to original bytes.
        """
        screen = _screen(self.document, screen_id)
        self._plain_extent(screen)
        element = _element(screen, element_id)
        raw = b"".join(section.bytes() for section in self.document.sections[element["start"]:element["end"]])
        return hashlib.sha256(raw).hexdigest()

    def _diascreen_contract(self, schema):
        """Bound v2 before any verifier/emitter dispatch, including no-op."""
        if not isinstance(schema, dict):
            return None
        contract = schema.get("preserved_layout")
        if not isinstance(contract, dict) or ("prefix_policy" not in contract and contract.get("contract_version") != 2):
            return None
        if {"literal_generation", "control_generation", "blank_program",
                "multipage_program", "existing_program", "existing_edit"} & set(schema):
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Preserved layout cannot mix emission contracts")
        keys = {"qualified", "contract_version", "mode", "source_sha256", "prefix_sha256", "sections", "prefix_policy"}
        if (set(schema) - {"qualified", "properties", "kinds", "preserved_layout", "native_candidate"}
                or not {"qualified", "properties", "kinds", "preserved_layout"} <= set(schema)
                or schema.get("qualified") is not True or set(contract) != keys
                or contract.get("qualified") is not True or type(contract.get("contract_version")) is not int
                or contract["contract_version"] != 2 or contract.get("mode") != "existing_owner_edits"
                or contract.get("prefix_policy") != _DIA_PREFIX_POLICY):
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque DIAScreen editing needs its exact isolated v2 contract")
        for key in ("source_sha256", "prefix_sha256"):
            if not isinstance(contract.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", contract[key]):
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque source fingerprints must be canonical", field=key)
        entries = contract.get("sections")
        if not isinstance(entries, list) or len(entries) != len(_DIA_PREFIX_NAMES):
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque prefix needs the complete observed section sequence")
        for entry, name in zip(entries, _DIA_PREFIX_NAMES):
            if (not isinstance(entry, dict) or set(entry) != {"name", "sha256"} or entry.get("name") != name
                    or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque section fingerprints or order are unqualified")
        properties = schema.get("properties")
        if not isinstance(properties, dict) or set(properties) != set(_DIA_GEOMETRY):
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque editing maps only four Element geometry scalars")
        for key, field in _DIA_GEOMETRY.items():
            spec = properties[key]
            if (not isinstance(spec, dict) or set(spec) not in ({"field", "scope", "type"}, {"field", "scope", "type", "min", "max"})
                    or spec.get("field") != field or spec.get("scope") != "element" or spec.get("type") != "int"
                    or ("min" in spec and (type(spec["min"]) is not int or type(spec["max"]) is not int
                        or spec["min"] != 0 or spec["max"] != 800))):
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque geometry cannot be remapped or widened", field=key)
        if schema.get("kinds") != {"text": {"Type": "10", "SubType": "6"}}:
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque editing admits only the original inert literal kind")
        if "native_candidate" in schema:
            spec = schema["native_candidate"]
            if (not isinstance(spec, dict) or set(spec) != {"qualified", "contract_version", "mode", "path", "sha256"}
                    or spec.get("qualified") is not True or type(spec.get("contract_version")) is not int
                    or spec["contract_version"] != 1 or spec.get("mode") != "existing_owner_candidate"
                    or not isinstance(spec.get("path"), str) or not 1 <= len(spec["path"]) <= 1000
                    or any(c in spec["path"] for c in "\0\r\n")
                    or not isinstance(spec.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", spec["sha256"])):
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque policy cannot qualify another candidate mode")
        series = self.application.one("PanelSeries", False)
        if (self.family != "delta_diascreen" or not model_ids_match(self.model_id, 268502784)
                or self.application.one("Version").value != b"6.0.00209.8338"
                or series is None or series.kind is not None or series.value != b"DOP-100 series"):
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque policy is limited to its observed model/serialized profile")
        pages = _groups(self.document)
        if not pages:
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque editing requires existing source pages")
        for page in pages:
            for field, expected in (("DocSizeX", b"800"), ("DocSizeY", b"480"), ("PanelSizeX", b"800"), ("PanelSizeY", b"480")):
                record = page["section"].one(field)
                if record.kind is not None or record.value != expected:
                    raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque pages need the observed 800 by 480 canvas")
        return contract

    @staticmethod
    def _diascreen_literal_owner(document, screen_id, element_id):
        page = _screen(document, screen_id)
        _screen_extent(document, page)
        owner = _element(page, element_id)
        _element_extent(document, owner)
        section = owner["section"]
        for field, expected in (("Type", b"10"), ("SubType", b"6"), ("ReadVar", b"None"), ("WriteVar", b"None")):
            record = section.one(field)
            if record.kind is not None or record.value != expected:
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque target must be an original inert literal", field=field)
        if len(owner["states"]) != 1:
            raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque literal needs one original Value0 State")
        state = owner["states"][0]
        value = state.one("Value")
        if value.kind is not None or value.value != b"0":
            raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque literal needs exact Value0")
        for field in ("OffsetReadVar", "OffsetWriteVar", "VisibleVar"):
            record = section.one(field, False)
            if record is not None and (record.kind is not None or record.value != b"None"):
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque literal cannot have active offset/visibility operands")
        for part in (section, state):
            macro_keys = [record.key for record in part.records if record.kind == "macro"]
            if len(set(macro_keys)) != len(macro_keys) or any(record.kind == "macro" and
                    (record.value != b"0" or record.blob != b"" or record.raw != record.key.encode("ascii") + b"=0\r\n")
                    for record in part.records):
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque literal needs unambiguous empty owner/State macros")
        for field in _DIA_GEOMETRY.values():
            record = section.one(field)
            if (record.kind is not None or not re.fullmatch(rb"0|[1-9][0-9]{0,9}", record.value)
                    or record.raw != field.encode("ascii") + b"=" + record.value + b"\r\n"):
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque geometry needs a canonical existing scalar", field=field)
        caption = state.one("wTextLen0")
        if (caption.kind != "wide" or caption.blob is None or len(caption.blob) < 2
                or caption.value != str(len(caption.blob)).encode("ascii")
                or caption.raw != b"wTextLen0=" + caption.value + b"\r\n" + caption.blob + b"\r\n"
                or "\0" in caption.text()):
            raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque literal needs a complete primary UTF-16 frame")
        return owner, caption

    def _diascreen_operation(self, document, operation, seen):
        """Validate against the original source even for semantic no-op."""
        name = operation.get("op")
        required = {"op", "screen_id", "element_id", "key", "value"} if name == "set_property" else {"op", "screen_id", "element_id", "text"}
        optional = {"state_index", "language"} if name == "set_text" else set()
        if name not in {"set_property", "set_text"} or not required <= set(operation) or set(operation) - required - optional:
            raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque policy permits only existing primary text and Element geometry")
        for key in ("screen_id", "element_id"):
            if not isinstance(operation.get(key), str):
                raise HmiError("INVALID_ID", "Opaque target identities must be canonical strings", field=key)
        sid, eid = _identity(operation["screen_id"], "screen_id"), _identity(operation["element_id"], "element_id")
        original_owner, original_caption = self._diascreen_literal_owner(self.document, sid, eid)
        owner, caption = self._diascreen_literal_owner(document, sid, eid)
        if name == "set_property":
            key = operation["key"]
            if not isinstance(key, str) or key not in _DIA_GEOMETRY or type(operation["value"]) is not int:
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque geometry requires a canonical integer field")
            field = _DIA_GEOMETRY[key]
            value = str(_integer(operation["value"], "value", 0, 800)).encode("ascii")
            if len(value) != len(original_owner["section"].one(field).value):
                raise HmiError("NATIVE_CANDIDATE_LENGTH", "Opaque geometry must retain each original scalar extent")
            marker = (sid, eid, field)
            if marker in seen:
                raise HmiError("INVALID_OPERATION", "Opaque transaction repeats a controlled record")
            seen.add(marker)
            owner["section"].one(field).set_value(value)
            self._geometry(_screen(document, sid), owner, {})
        else:
            if any(type(operation.get(key, 0)) is not int or operation.get(key, 0) != 0 for key in ("state_index", "language")):
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Opaque text edits only original State0/language0")
            text = operation["text"]
            if not isinstance(text, str) or "\0" in text:
                raise HmiError("INVALID_TEXT", "Primary caption must be a string without NUL")
            if len(text) > len(original_caption.blob) // 2:
                raise HmiError("NATIVE_CANDIDATE_LENGTH", "Opaque caption exceeds its original UTF-16 extent")
            try:
                encoded = text.encode("utf-16-le", "strict") + b"\0\0"
            except UnicodeEncodeError as exc:
                raise HmiError("INVALID_TEXT", "Primary caption contains an invalid Unicode surrogate") from exc
            if len(encoded) != len(original_caption.blob):
                raise HmiError("NATIVE_CANDIDATE_LENGTH", "Opaque caption must retain its original UTF-16 extent")
            marker = (sid, eid, "wTextLen0")
            if marker in seen:
                raise HmiError("INVALID_OPERATION", "Opaque transaction repeats a controlled record")
            seen.add(marker)
            caption.set_text(text)

    def _verify_diascreen_body(self, original):
        """Restore every managed raw record; the entire source BODY must match.

        Original record identities are independent of operations and setters.
        Public IR verification separately binds the exact approved intent.
        """
        controlled = {}
        for page in _groups(original.document):
            for element in page["elements"]:
                try:
                    owner, caption = self._diascreen_literal_owner(original.document, page["id"], element["id"])
                except HmiError:
                    continue  # Every unsupported original owner stays entirely byte-exact.
                for field in _DIA_GEOMETRY.values():
                    record = owner["section"].one(field)
                    controlled[(owner["start"], next(i for i, r in enumerate(owner["section"].records) if r is record))] = "scalar"
                state = owner["states"][0]
                si = next(i for i in range(owner["start"] + 1, owner["end"]) if original.document.sections[i] is state)
                controlled[(si, next(i for i, r in enumerate(state.records) if r is caption))] = "caption"
        source_parts, candidate_parts = original.document.sections, self.document.sections
        if len(source_parts) != len(candidate_parts) or len(self.envelope.body) != len(original.envelope.body):
            raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque candidate changed BODY framing or size")
        restored = []
        for si, (source, candidate) in enumerate(zip(source_parts, candidate_parts)):
            if source.header != candidate.header or len(source.records) != len(candidate.records):
                raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque candidate changed section/record ownership")
            restored.append(candidate.header)
            for ri, (before, after) in enumerate(zip(source.records, candidate.records)):
                kind = controlled.get((si, ri))
                if kind is None:
                    restored.append(after.raw)
                    continue
                if before.key != after.key or before.kind != after.kind or len(before.raw) != len(after.raw):
                    raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque controlled record changed its individual frame")
                if kind == "scalar":
                    if (after.kind is not None or not re.fullmatch(rb"0|[1-9][0-9]{0,9}", after.value)
                            or len(before.value) != len(after.value)
                            or after.raw != after.key.encode("ascii") + b"=" + after.value + b"\r\n"):
                        raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque geometry changed scalar framing")
                elif (after.blob is None or before.value != after.value or len(before.blob) != len(after.blob)
                        or after.raw != b"wTextLen0=" + before.value + b"\r\n" + after.blob + b"\r\n"
                        or "\0" in after.text()):
                    raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque caption changed its primary frame")
                restored.append(before.raw)
        restored.append(self.document.tail)
        if (b"".join(restored) != original.envelope.body or self.envelope.prefix != original.envelope.prefix
                or (self.envelope.body == original.envelope.body and self.original != original.original)):
            raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Opaque candidate changed an unmanaged source byte")

    @staticmethod
    def _preserved_prefix(document, prefix_policy=None):
        starts = [index for index, section in enumerate(document.sections) if section.name == "Screen"]
        if not starts:
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Existing-owner layout requires an original screen")
        sections = document.sections[:starts[0]]
        if not sections or sections[0].name != "Application":
            raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Preserved global prefix must start with Application")
        if prefix_policy is not None:
            if prefix_policy != _DIA_PREFIX_POLICY or tuple(section.name for section in sections) != _DIA_PREFIX_NAMES:
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque prefix requires the exact observed section order")
            for section in sections:
                if section.name not in _DIA_OPAQUE_LINES and any(record.key is None and record.raw != b"\r\n" for record in section.records):
                    raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Opaque unkeyed metadata is outside observed sections", section=section.name)
            raw = b"".join(section.bytes() for section in sections)
            return raw, [{"name": section.name, "sha256": hashlib.sha256(section.bytes()).hexdigest()} for section in sections]
        seen = set()
        for section in sections:
            if section.name not in _PRESERVED_GLOBALS or section.name in seen:
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Global prefix contains an unknown or repeated section", section=section.name)
            seen.add(section.name)
            for record in section.records:
                # The genuine Application delimiters are exact empty CRLF
                # records. No other unkeyed metadata framing is qualified.
                if record.key is None and record.raw != b"\r\n":
                    raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Global prefix has unqualified unkeyed metadata", section=section.name)
        raw = b"".join(section.bytes() for section in sections)
        return raw, [{"name": section.name, "sha256": hashlib.sha256(section.bytes()).hexdigest()} for section in sections]

    def _preserved_sequence(self):
        """Exact owner identities, headers and Order records; no layer inference."""
        result = []
        for screen in _groups(self.document):
            auxiliary = self._plain_extent(screen)
            owners = []
            for element in screen["elements"]:
                self._geometry(screen, element, {})
                states, seen = [], set()
                for state in element["states"]:
                    identity = state.one("Value")
                    if identity.kind is not None:
                        raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "State identity must be an existing scalar Value")
                    value = _decimal(identity.value.decode("latin-1"), "Value")
                    if value in seen:
                        raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "State identity repeats within its owner", element_id=element["id"])
                    seen.add(value)
                    order = state.one("Order", False)
                    states.append((state.header, identity.raw, order.raw if order else None))
                section = element["section"]
                order = section.one("Order", False)
                owners.append((element["id"], section.header, section.one("nPartsID").raw,
                               order.raw if order else None, states))
            result.append((screen["id"], screen["section"].bytes(), auxiliary.bytes(), owners))
        return result

    def _preserved_byte_binding(self, code):
        """Reject cached projections/envelopes detached from immutable bytes."""
        try:
            envelope = Envelope.decode(self.original, self.family)
            document = Document.parse(envelope.body)
            application = document.sections[0]
            if (self.envelope != envelope or self.document != document
                    or self.application != application or application.name != "Application"
                    or self.model_id != _value(application, "ModelName")
                    or self.editor_version != _value(application, "Version")):
                raise HmiError(code, "Preserved adapter projection, envelope or identity differs from its actual file bytes")
        except HmiError as exc:
            if exc.code == code:
                raise
            raise HmiError(code, "Preserved adapter bytes cannot establish a coherent native projection") from exc

    @staticmethod
    def _literal_shape(section, allowed, required):
        keys = [record.key for record in section.records]
        if (any(key is None or key not in allowed for key in keys)
                or len(keys) != len(set(keys)) or not required <= set(keys)):
            raise HmiError("UNQUALIFIED_LITERAL_SHAPE", "Literal donor has missing, repeated or unqualified fields", section=section.name)

    @staticmethod
    def _literal_zero(section, keys):
        # Restrict generation to observed raw-zero variants. This does not
        # establish that zero disables the corresponding vendor behavior.
        for key in keys:
            record = section.one(key, False)
            if record is not None and (record.blob or record.value != b"0"):
                raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal donor variant is outside the bounded raw baseline", field=key)

    @staticmethod
    def _literal_normalized(section, source, fields):
        """Restore only managed raw records, including their source spelling."""
        result = deepcopy(section)
        for key in fields:
            old = source.one(key)
            index = next(index for index, record in enumerate(result.records) if record.key == key)
            result.records[index] = deepcopy(old)
        return result.bytes()

    def _literal_donors(self, schema):
        contract = schema.get("literal_generation")
        required = {"qualified", "contract_version", "mode", "source_sha256", "prefix_sha256", "sections", "page_donor", "text_donor"}
        if (schema.get("qualified") is not True or "preserved_layout" in schema
                or not isinstance(contract, dict) or set(contract) != required
                or contract.get("qualified") is not True or type(contract.get("contract_version")) is not int
                or contract["contract_version"] != 1 or contract.get("mode") != "literal_page_generation"
                or not isinstance(contract.get("sections"), list) or not 1 <= len(contract["sections"]) <= len(_PRESERVED_GLOBALS)):
            raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Literal generation requires its exact distinct source-local contract")
        for key in ("source_sha256", "prefix_sha256"):
            if not isinstance(contract.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", contract[key]):
                raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Literal generation needs canonical source fingerprints", field=key)
        for entry in contract["sections"]:
            if (not isinstance(entry, dict) or set(entry) != {"name", "sha256"}
                    or not isinstance(entry.get("name"), str) or entry["name"] not in _PRESERVED_GLOBALS
                    or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Literal global prefix needs exact names and fingerprints")
        self._preserved_byte_binding("INVALID_LITERAL_SOURCE")
        prefix, entries = self._preserved_prefix(self.document)
        if (hashlib.sha256(self.original).hexdigest() != contract["source_sha256"]
                or hashlib.sha256(prefix).hexdigest() != contract["prefix_sha256"] or entries != contract["sections"]):
            raise HmiError("INVALID_LITERAL_SOURCE", "Literal source or raw global prefix differs from its contract")
        page_pin, text_pin = contract.get("page_donor"), contract.get("text_donor")
        for pin, keys in ((page_pin, {"screen_id", "header_sha256", "aux_sha256"}),
                          (text_pin, {"screen_id", "element_id", "owner_sha256"})):
            if not isinstance(pin, dict) or set(pin) != keys:
                raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Literal donor needs its exact owner identity and fingerprints")
            for key in keys:
                if key.endswith("sha256"):
                    if not isinstance(pin[key], str) or not re.fullmatch(r"[0-9a-f]{64}", pin[key]):
                        raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Literal donor fingerprint is invalid", field=key)
                else:
                    _identity(pin[key], key)
        page = _screen(self.document, page_pin["screen_id"])
        auxiliary = self._plain_extent(page)
        header = page["section"]
        self._literal_shape(header, _LITERAL_PAGE_FIELDS, _LITERAL_PAGE_FIELDS)
        if _value(header, "VER") != "16":
            raise HmiError("UNQUALIFIED_LITERAL_SHAPE", "Literal page requires the observed raw VER 16 shape")
        self._literal_zero(header, {"OpenMacroLen", "CloseMacroLen", "CycleMacroLen", "BaseScreenID", "ScreenAction",
                                   "IsSubScreen", "IsKeypadScreen", "IsScreenRotate", "IsPrintScreen", "Hidden"})
        if _value(header, "ScreenLockVar") != "None":
            raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal page donor has a lock address")
        title = header.one("wTitleTextLen000", False)
        if title is not None and (title.kind != "wide" or title.blob != b"\0\0"):
            raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal page title must retain the observed empty wide baseline")
        for key in ("DocSizeX", "DocSizeY", "PanelSizeX", "PanelSizeY"):
            _integer(_native_int(header, key), key, 1)
        self._literal_wide(header.one("wTextLen"))
        if (hashlib.sha256(header.bytes()).hexdigest() != page_pin["header_sha256"]
                or hashlib.sha256(auxiliary.bytes()).hexdigest() != page_pin["aux_sha256"]):
            raise HmiError("INVALID_LITERAL_SOURCE", "Literal page donor differs from its raw header/auxiliary pins")
        text_page = _screen(self.document, text_pin["screen_id"])
        self._plain_extent(text_page)
        text = _element(text_page, text_pin["element_id"])
        element = text["section"]
        descriptions = {"wDescTextLen", "wDescTextLen0"}
        self._literal_shape(element, _LITERAL_ELEMENT_FIELDS, _LITERAL_ELEMENT_FIELDS - descriptions)
        if sum(element.one(key, False) is not None for key in descriptions) != 1:
            raise HmiError("UNQUALIFIED_LITERAL_SHAPE", "Literal owner requires exactly one observed description frame")
        if (_value(element, "Type"), _value(element, "SubType")) != ("10", "6"):
            raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal owner donor must be observed Type 10/SubType 6")
        for key in ("ReadVar", "WriteVar", "OffsetReadVar", "OffsetWriteVar", "VisibleVar"):
            if _value(element, key) != "None":
                raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal owner donor has an address-dependent field", field=key)
        self._literal_zero(element, {"GroupID", "Style", "Level", "PrintSuccessiveData", "nAngle", "bFreeze", "PosVary"})
        if len(text["states"]) != 1:
            raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal owner requires exactly one State")
        state = text["states"][0]
        self._literal_shape(state, _LITERAL_STATE_FIELDS, _LITERAL_STATE_FIELDS)
        self._literal_zero(state, {"SoundIndex", "Twinkles", "UsePictureCoord", "TransEffect", "TransColor", "StretchMode", "PictureStretch"})
        if _value(state, "Value") != "0":
            raise HmiError("UNQUALIFIED_LITERAL_BEHAVIOR", "Literal owner State must have exact Value 0")
        self._literal_wide(state.one("wTextLen0"))
        self._geometry(text_page, text, {})
        if self.owner_extent_sha256(text_page["id"], text["id"]) != text_pin["owner_sha256"]:
            raise HmiError("INVALID_LITERAL_SOURCE", "Literal text donor differs from its full raw owner pin")
        # This also checks every retained source owner's bounded framing and
        # geometry, without interpreting Order or inherited source behavior.
        self._preserved_sequence()
        return page, auxiliary, text

    @staticmethod
    def _literal_wide(record):
        if record.kind != "wide" or not record.blob or len(record.blob) < 2 or not record.blob.endswith(b"\0\0"):
            raise HmiError("UNQUALIFIED_LITERAL_SHAPE", "Literal caption must have complete native wide framing", field=record.key)
        record.text()

    def _verify_literal_generation(self, schema, original_adapter):
        self._preserved_byte_binding("INVALID_LITERAL_CANDIDATE")
        if original_adapter is None:
            original_adapter = self
        if (not isinstance(original_adapter, NativeAdapter) or original_adapter.family != self.family
                or original_adapter.model_id != self.model_id or original_adapter.editor_version != self.editor_version):
            raise HmiError("INVALID_LITERAL_SOURCE", "Literal candidate requires its exact immutable source identity")
        page_donor, auxiliary, text_donor = original_adapter._literal_donors(schema)
        source_prefix, source_entries = self._preserved_prefix(original_adapter.document)
        candidate_prefix, candidate_entries = self._preserved_prefix(self.document)
        if (candidate_prefix != source_prefix or candidate_entries != source_entries
                or self.envelope.thumbnail != original_adapter.envelope.thumbnail
                or self.envelope.prefix != original_adapter.envelope.prefix_for_body(self.envelope.body)
                or self.document.tail != original_adapter.document.tail):
            raise HmiError("LITERAL_GENERATION_MISMATCH", "Literal generation changed a raw global prefix, thumbnail, opaque prefix or tail")
        original_screens, screens = _groups(original_adapter.document), _groups(self.document)
        if len(screens) < len(original_screens):
            raise HmiError("LITERAL_GENERATION_MISMATCH", "Literal generation removed an original page")
        all_owner_ids = {element["id"] for screen in original_screens for element in screen["elements"]}
        for original, candidate in zip(original_screens, screens):
            original_raw = b"".join(section.bytes() for section in original_adapter.document.sections[original["start"]:original["end"]])
            candidate_raw = b"".join(section.bytes() for section in self.document.sections[candidate["start"]:candidate["end"]])
            if original_raw != candidate_raw:
                raise HmiError("LITERAL_GENERATION_MISMATCH", "Literal generation changed an original page or owner")
        for screen in screens[len(original_screens):]:
            if screen["id"] == "0":
                raise HmiError("INVALID_ID", "New literal page identity must be positive")
            aux = self._plain_extent(screen)
            header = screen["section"]
            self._literal_shape(header, _LITERAL_PAGE_FIELDS, {record.key for record in page_donor["section"].records})
            self._literal_wide(header.one("wTextLen"))
            if (aux.bytes() != auxiliary.bytes()
                    or self._literal_normalized(header, page_donor["section"], {"ID", "wTextLen"}) != page_donor["section"].bytes()):
                raise HmiError("LITERAL_GENERATION_MISMATCH", "New page differs from its source header outside ID/name")
            for element in screen["elements"]:
                if element["id"] == "0" or element["id"] in all_owner_ids:
                    raise HmiError("DUPLICATE_ELEMENT", "New literal owner identity is not project-wide fresh and positive")
                all_owner_ids.add(element["id"])
                self._literal_shape(element["section"], _LITERAL_ELEMENT_FIELDS, {record.key for record in text_donor["section"].records})
                if len(element["states"]) != 1:
                    raise HmiError("LITERAL_GENERATION_MISMATCH", "New literal owner must retain one complete State")
                state, original_state = element["states"][0], text_donor["states"][0]
                self._literal_shape(state, _LITERAL_STATE_FIELDS, {record.key for record in original_state.records})
                self._literal_wide(state.one("wTextLen0"))
                if (self._literal_normalized(element["section"], text_donor["section"], {"nPartsID", "X", "Y", "Width", "Height"}) != text_donor["section"].bytes()
                        or self._literal_normalized(state, original_state, {"wTextLen0"}) != original_state.bytes()):
                    raise HmiError("LITERAL_GENERATION_MISMATCH", "New owner differs from its source literal donor outside ID/geometry/caption")
                self._geometry(screen, element, {})
        return True

    @staticmethod
    def _control_fingerprint(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    @staticmethod
    def _control_shape(section, fields):
        keys = [record.key for record in section.records]
        if len(keys) != len(set(keys)) or set(keys) != fields:
            raise HmiError("UNQUALIFIED_CONTROL_SHAPE", "Control donor has missing, repeated or unobserved fields", section=section.name)
        for record in section.records:
            if record.kind == "wide":
                NativeAdapter._literal_wide(record)
            elif record.kind == "macro":
                if record.value != b"0" or record.blob != b"":
                    raise HmiError("UNQUALIFIED_CONTROL_BEHAVIOR", "Control generation cannot inherit an active macro", field=record.key)
            elif record.kind is not None or record.blob is not None:
                raise HmiError("UNQUALIFIED_CONTROL_SHAPE", "Control generation cannot inherit an image or opaque record", field=record.key)

    def _control_owner(self, page, owner, kind, prefix, schema, bound=False):
        """Check the observed bounded shape; preserve every unmanaged field."""
        section = owner["section"]
        if kind in {"numeric_input", "numeric_display"}:
            expected_type = "6" if kind == "numeric_input" else "5"
            if _value(section, "Type") != expected_type or _value(section, "SubType") != "1":
                raise HmiError("UNQUALIFIED_CONTROL_SHAPE", "Numeric donor differs from its observed input/display kind")
            fields = _CONTROL_COMMON | (_CONTROL_INPUT if kind == "numeric_input" else _CONTROL_DISPLAY)
        else:
            subtype = _value(section, "SubType")
            if _value(section, "Type") != "1" or subtype not in {"1", "2", "3", "4"}:
                raise HmiError("UNQUALIFIED_CONTROL_SHAPE", "Button donor is outside the observed binary control shapes")
            macros = {"ButtonOnMacroLen"} if subtype == "1" else {"ButtonOffMacroLen"} if subtype == "2" else {"ButtonOnMacroLen", "ButtonOffMacroLen"}
            fields = _CONTROL_COMMON | _CONTROL_BUTTON | macros | ({"OffVoice"} if subtype == "3" else set())
        self._control_shape(section, fields)
        zeros = {"GroupID", "PrintSuccessiveData", "Level", "OffsetReadMemType", "OffsetWriteMemType", "nAngle", "bFreeze",
                 "PushTime", "SetLowSecurity", "ConFirmWindow", "NoMessage", "DispAsterisk", "OffVoice", "Roundoff",
                 "LeadingZero", "Variation", "FastRefresh", "Active", "UseCustKeypad", "KeypadScreenID"}
        for key in zeros & fields:
            if section.one(key).value != b"0":
                raise HmiError("UNQUALIFIED_CONTROL_BEHAVIOR", "Control variant has an unqualified conditional or presentation flag", field=key)
        for key in {"OffsetReadVar", "OffsetWriteVar", "VisibleVar", "InterLockVar", "TriggerVar"} & fields:
            if section.one(key).value != b"None":
                raise HmiError("UNQUALIFIED_CONTROL_BEHAVIOR", "Control variant has an offset, lock, visibility or trigger address", field=key)
        self._geometry(page, owner, {})
        values = [state.one("Value").value for state in owner["states"]]
        if values != ([b"0"] if kind in {"numeric_input", "numeric_display"} else [b"0", b"1"]):
            raise HmiError("UNQUALIFIED_CONTROL_SHAPE", "Control State identities/order differ from the observed source")
        for state in owner["states"]:
            self._control_shape(state, _LITERAL_STATE_FIELDS)
            for key in {"UsePictureCoord", "TransEffect", "TransColor", "StretchMode", "PictureStretch", "Twinkles", "SoundIndex"}:
                if state.one(key).value != b"0":
                    raise HmiError("UNQUALIFIED_CONTROL_BEHAVIOR", "Control State has an unqualified image or animated effect", field=key)
            for key in {"FgColor", "BgColor", "FontColor"}:
                _integer(_native_int(state, key), key, 0, 0xFFFFFF)
            _integer(_native_int(state, "FontSize0"), "FontSize0", 1, 128)
        family = "D" if kind in {"numeric_input", "numeric_display"} else "M"
        for direction in ("Read", "Write"):
            address = _value(section, direction + "Var")
            if address != "None":
                self._control_address(address, prefix, family, schema, direction.lower())
        if kind == "numeric_display" and _value(section, "WriteVar") != "None":
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Numeric displays cannot acquire a write binding")
        required_direction = "Read" if kind == "numeric_display" else "Write"
        if bound and _value(section, required_direction + "Var") == "None":
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Appended controls require their explicit primary binding")
        if kind in {"numeric_input", "numeric_display"}:
            numeric = schema.get("numeric")
            storage = storage_contract(schema)
            converted = bound and _value(section, "MemFmt") == "1"
            if converted:
                verify_converted(section, kind, schema)
            elif (_value(section, "MemLen"), _value(section, "MemFmt")) != ("1", "2"):
                raise HmiError("UNQUALIFIED_CONTROL_NUMERIC", "Original numeric sources and unsigned clones must retain exact UINT16 storage")
            fixed = None
            if isinstance(numeric, dict) and "value_models" in numeric:
                fixed = fixed_decimal_contract(schema)
                source_contract = schema.get("control_generation")
                if (not isinstance(source_contract, dict)
                        or fixed["source_sha256"] != source_contract.get("source_sha256")):
                    raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fixed-decimal descriptor differs from its source-qualified control library")
            maximum_fractional = fixed["max_fractional_digits"] if fixed is not None else 0
            expected_types = {"UINT": {"MemLen": "1", "MemFmt": "2", "bits": 16, "format": "unsigned"}}
            if storage is not None:
                expected_types["INT"] = {"MemLen": "1", "MemFmt": "1", "bits": 16, "format": "signed"}
            if (not isinstance(numeric, dict) or numeric.get("types") != expected_types
                    or numeric.get("kinds") != {"numeric_input": {"Type": "6", "SubType": "1"}, "numeric_display": {"Type": "5", "SubType": "1"}}
                    or numeric.get("max_fractional_digits") != maximum_fractional):
                raise HmiError("UNQUALIFIED_CONTROL_NUMERIC", "Control generation requires its separately qualified exact numeric mappings")
            operation = {"kind": kind, "data_type": "INT" if converted else "UINT", "integer_digits": _native_int(section, "IntNum"),
                         "fractional_digits": _native_int(section, "DotNum"), "gain": _value(section, "GainValue"), "offset": _value(section, "OffsetValue")}
            if operation["fractional_digits"]:
                if fixed is None:
                    raise HmiError("UNQUALIFIED_FIXED_DECIMAL", "Fractional control objects require their explicit value-model contract")
                operation["value_model"] = FIXED_DECIMAL_MODEL
            if kind == "numeric_input":
                operation.update(minimum=_value(section, "MinValue"), maximum=_value(section, "MaxValue"))
            verify_numeric_fields({record.key: record.value.decode("latin-1") for record in section.records if record.kind is None}, operation, schema)

    @staticmethod
    def _control_address(address, prefix, family, schema=None, direction="read"):
        # Only the two captured external addresses are witnesses in this first
        # milestone. Neither an apparent M/D grammar nor a tag name authorizes
        # new driver ranges, channels or station values.
        if not isinstance(direction, str) or direction not in {"read", "write"}:
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Control binding direction must be read or write")
        if isinstance(schema, dict) and "address_namespace" in schema:
            data_type = {"M": "BOOL", "D": "UINT"}.get(family)
            return AddressNamespace(schema["address_namespace"]).match(address, data_type, prefix, direction)
        if address != prefix + family + "0":
            raise HmiError("CONTROL_ADDRESS_SCOPE", "Control address is outside the exact captured M0/D0 context")
        return address

    @staticmethod
    def _control_prefix_length(adapter):
        prefix = adapter.envelope.prefix
        if len(prefix) != 41 or int.from_bytes(bytes(value ^ 0x64 for value in prefix[37:41]), "little") != len(adapter.envelope.body):
            raise HmiError("CONTROL_BODY_LENGTH", "Control envelope declared length differs from the complete native body")

    def control_donors(self, schema):
        """Validate property-witness/source pins; no vendor/runtime acceptance."""
        contract = schema.get("control_generation") if isinstance(schema, dict) else None
        keys = {"qualified", "contract_version", "mode", "source_sha256", "prefix_sha256", "sections", "pages", "donors", "address_prefix"}
        if (not isinstance(schema, dict) or schema.get("qualified") is not True or {"literal_generation", "preserved_layout"} & set(schema)
                or not isinstance(contract, dict) or set(contract) != keys or contract.get("qualified") is not True
                or type(contract.get("contract_version")) is not int or contract["contract_version"] != 1 or contract.get("mode") != "control_generation"):
            raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "Control generation requires its exact distinct source-local contract")
        if not all(self._control_fingerprint(contract.get(key)) for key in ("source_sha256", "prefix_sha256")):
            raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "Control contract fingerprints must be canonical SHA-256 values")
        self._preserved_byte_binding("INVALID_CONTROL_SOURCE")
        self._control_prefix_length(self)
        prefix, sections = self._preserved_prefix(self.document)
        if (hashlib.sha256(self.original).hexdigest() != contract["source_sha256"]
                or hashlib.sha256(prefix).hexdigest() != contract["prefix_sha256"] or sections != contract["sections"]):
            raise HmiError("INVALID_CONTROL_SOURCE", "Control source or exact global prefix differs from its pins")
        if "address_namespace" in schema:
            AddressNamespace(schema["address_namespace"]).validate_source(self, contract["address_prefix"])
        if "storage_conversion" in schema:
            validate_storage_source(self, schema)
        pages = _groups(self.document)
        if not 1 <= len(pages) <= 10000 or not isinstance(contract["pages"], list):
            raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "Control generation requires bounded exact source page pins")
        observed_pages = [{"screen_id": page["id"], "header_sha256": hashlib.sha256(page["section"].bytes()).hexdigest(),
                           "aux_sha256": hashlib.sha256(self._plain_extent(page).bytes()).hexdigest()} for page in pages]
        if contract["pages"] != observed_pages:
            raise HmiError("INVALID_CONTROL_SOURCE", "Control page header, order or auxiliary pins differ")
        address_prefix = contract["address_prefix"]
        if not isinstance(address_prefix, str) or not re.fullmatch(r"\{Link[1-9][0-9]{0,3}\}(?:0|[1-9][0-9]{0,3})@", address_prefix):
            raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "Control address prefix is not canonical source-local syntax")
        pins = contract["donors"]
        if not isinstance(pins, dict) or set(pins) != _CONTROL_KINDS:
            raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "All six witnessed control kinds need separate exact donors")
        result, identities, button_matches = {}, set(), set()
        for kind, pin in pins.items():
            if (not isinstance(pin, dict) or set(pin) != {"screen_id", "element_id", "owner_sha256", "match", "property_witness_sha256"}
                    or not self._control_fingerprint(pin.get("owner_sha256")) or not self._control_fingerprint(pin.get("property_witness_sha256"))
                    or not isinstance(pin.get("match"), dict) or set(pin["match"]) != {"Type", "SubType"}):
                raise HmiError("UNQUALIFIED_CONTROL_GENERATION", "Control donor needs exact identity, native kind and property-witness fingerprints")
            page = _screen(self.document, pin["screen_id"])
            owner = _element(page, pin["element_id"])
            identity = (page["id"], owner["id"])
            if identity in identities or any(_value(owner["section"], key) != value for key, value in pin["match"].items()):
                raise HmiError("INVALID_CONTROL_SOURCE", "Control donor identity repeats or differs from its witnessed native kind")
            identities.add(identity)
            if kind not in {"numeric_input", "numeric_display"}:
                pair = tuple(sorted(pin["match"].items()))
                if pair in button_matches:
                    raise HmiError("INVALID_CONTROL_SOURCE", "Four witnessed button kinds require distinct source native shapes")
                button_matches.add(pair)
            if self.owner_extent_sha256(page["id"], owner["id"]) != pin["owner_sha256"]:
                raise HmiError("INVALID_CONTROL_SOURCE", "Control donor differs from its immutable owner fingerprint")
            self._control_owner(page, owner, kind, address_prefix, schema)
            result[kind] = owner
        # Prefix authority must be witnessed in typed owners, not only declared
        # by a profile. Existing source link/memtype records remain immutable.
        if (not any(_value(result[kind]["section"], "WriteVar") == address_prefix + "M0" for kind in _CONTROL_KINDS - {"numeric_input", "numeric_display"})
                or _value(result["numeric_input"]["section"], "WriteVar") != address_prefix + "D0"
                or _value(result["numeric_display"]["section"], "ReadVar") != address_prefix + "D0"):
            raise HmiError("INVALID_CONTROL_SOURCE", "Control source does not witness the shared typed address prefix")
        return result

    def verify_control_generation(self, schema, original_adapter=None):
        self._preserved_byte_binding("INVALID_CONTROL_CANDIDATE")
        self._control_prefix_length(self)
        source = self if original_adapter is None else original_adapter
        if (not isinstance(source, NativeAdapter) or source.family != self.family or source.model_id != self.model_id
                or source.editor_version != self.editor_version):
            raise HmiError("INVALID_CONTROL_SOURCE", "Control candidate needs its exact immutable source identity")
        donors = source.control_donors(schema)
        if (self._preserved_prefix(self.document) != source._preserved_prefix(source.document)
                or self.envelope.thumbnail != source.envelope.thumbnail or self.envelope.prefix[:37] != source.envelope.prefix[:37]
                or self.document.tail != source.document.tail):
            raise HmiError("CONTROL_GENERATION_MISMATCH", "Control generation changed globals, thumbnail, opaque prefix or tail")
        original_pages, pages = _groups(source.document), _groups(self.document)
        if [page["id"] for page in pages] != [page["id"] for page in original_pages]:
            raise HmiError("CONTROL_GENERATION_MISMATCH", "Control generation cannot add, remove or reorder pages")
        used = {owner["id"] for page in original_pages for owner in page["elements"]}
        prefix = schema["control_generation"]["address_prefix"]
        for old_page, page in zip(original_pages, pages):
            if page["section"].bytes() != old_page["section"].bytes() or self._plain_extent(page).bytes() != source._plain_extent(old_page).bytes():
                raise HmiError("CONTROL_GENERATION_MISMATCH", "Control generation changed an original page header or auxiliary extent")
            originals = old_page["elements"]
            if len(page["elements"]) < len(originals):
                raise HmiError("CONTROL_GENERATION_MISMATCH", "Control generation removed original owners")
            for old, owner in zip(originals, page["elements"]):
                before = b"".join(s.bytes() for s in source.document.sections[old["start"]:old["end"]])
                after = b"".join(s.bytes() for s in self.document.sections[owner["start"]:owner["end"]])
                if before != after:
                    raise HmiError("CONTROL_GENERATION_MISMATCH", "Control generation changed/reordered an original owner")
            for owner in page["elements"][len(originals):]:
                if owner["id"] == "0" or owner["id"] in used:
                    raise HmiError("DUPLICATE_ELEMENT", "Appended control identity must be positive and project-wide fresh")
                used.add(owner["id"])
                matches = [(kind, donor) for kind, donor in donors.items()
                           if all(_value(owner["section"], key) == _value(donor["section"], key) for key in ("Type", "SubType"))]
                if len(matches) != 1:
                    raise HmiError("CONTROL_GENERATION_MISMATCH", "Appended owner has no unique witnessed source donor")
                kind, donor = matches[0]
                self._control_owner(page, owner, kind, prefix, schema, bound=True)
                managed = {"nPartsID", "X", "Y", "Width", "Height", "ReadVar", "WriteVar"}
                if kind in {"numeric_input", "numeric_display"}:
                    managed |= NUMERIC_FIELDS - {"MemLen", "MemFmt"}
                    if _value(owner["section"], "MemFmt") == "1":
                        # _control_owner above already validated the exact
                        # explicit static INT16 transformation contract.
                        verify_converted(owner["section"], kind, schema)
                        managed.add("MemFmt")
                managed &= {record.key for record in donor["section"].records}
                if self._literal_normalized(owner["section"], donor["section"], managed) != donor["section"].bytes():
                    raise HmiError("CONTROL_GENERATION_MISMATCH", "Appended control differs outside managed donor fields")
                for state, old_state in zip(owner["states"], donor["states"]):
                    managed_state = {"BgColor", "FontColor", "FontSize0"}
                    if kind not in {"numeric_input", "numeric_display"}:
                        managed_state.add("wTextLen0")
                    if self._literal_normalized(state, old_state, managed_state) != old_state.bytes():
                        raise HmiError("CONTROL_GENERATION_MISMATCH", "Appended control changed state ordering or unmanaged presentation fields")
        return True

    def _control_operation(self, document, operation, schema, name, donors):
        if name not in {"clone_element", "set_property", "set_text", "bind", "configure_numeric", "convert_numeric_storage"}:
            raise HmiError("CONTROL_GENERATION_SCOPE", "Control generation cannot perform this operation", operation=name)
        if name == "clone_element":
            if set(operation) != _ARGUMENTS[name]:
                raise HmiError("INVALID_OPERATION", "Control cloning needs exact source/target identities")
            pin = next((pin for pin in schema["control_generation"]["donors"].values()
                        if pin["screen_id"] == operation.get("source_screen") and pin["element_id"] == operation.get("source_element")), None)
            if pin is None:
                raise HmiError("CONTROL_GENERATION_SCOPE", "Control cloning must use a witnessed immutable source donor")
            page = _screen(document, operation.get("target_screen"))
            identity = _identity(operation.get("element_id"), "element_id")
            if identity == "0" or any(owner["id"] == identity for page in _groups(document) for owner in page["elements"]):
                raise HmiError("DUPLICATE_ELEMENT", "Appended control identity must be positive and project-wide fresh")
            donor = _element(_screen(self.document, pin["screen_id"]), pin["element_id"])
            clone = deepcopy(self.document.sections[donor["start"]:donor["end"]])
            clone[0].one("nPartsID").set_value(identity.encode("ascii"))
            document.sections[page["end"]:page["end"]] = clone
            return
        page = _screen(document, operation.get("screen_id"))
        owner = _element(page, operation.get("element_id"))
        if any(old["id"] == owner["id"] for original in _groups(self.document) for old in original["elements"]):
            raise HmiError("CONTROL_GENERATION_SCOPE", "Control generation cannot edit original owners")
        kinds = [kind for kind, donor in donors.items() if all(_value(owner["section"], key) == _value(donor["section"], key) for key in ("Type", "SubType"))]
        if len(kinds) != 1:
            raise HmiError("CONTROL_GENERATION_SCOPE", "Appended control has no unique immutable donor")
        kind, prefix = kinds[0], schema["control_generation"]["address_prefix"]
        if name == "set_property":
            key = operation.get("key")
            spec = schema.get("properties", {}).get(key) if isinstance(key, str) else None
            field = (_CONTROL_GEOMETRY | _CONTROL_STYLE).get(key) if isinstance(key, str) else None
            state = key in _CONTROL_STYLE
            required_keys = {"op", "screen_id", "element_id", "key", "value"} | ({"state_index"} if state else set())
            if (set(operation) != required_keys or field is None or not isinstance(spec, dict) or spec.get("field") != field
                    or spec.get("type") != "int" or spec.get("scope", "element") != ("state" if state else "element")):
                raise HmiError("CONTROL_GENERATION_SCOPE", "Controls admit only exact geometry and explicit state color/font scalars")
            if state:
                _integer(operation["value"], key, 1 if key == "font_size" else 0, 128 if key == "font_size" else 0xFFFFFF)
            self._property(document, operation, schema)
        elif name == "set_text":
            if (kind in {"numeric_input", "numeric_display"} or set(operation) != {"op", "screen_id", "element_id", "state_index", "language", "text"}
                    or type(operation.get("state_index")) is not int or operation["state_index"] not in {0, 1}
                    or type(operation.get("language")) is not int or operation["language"] != 0):
                raise HmiError("CONTROL_GENERATION_SCOPE", "Only primary button 0/1 captions are editable")
            self._text(document, operation)
        elif name == "bind":
            directions = [direction for direction in ("read", "write") if direction in operation]
            if not directions or kind == "numeric_display" and "write" in directions:
                raise HmiError("CONTROL_ADDRESS_SCOPE", "Control binding direction differs from its witnessed kind")
            for direction in directions:
                binding = operation[direction]
                address = binding.get("address") if isinstance(binding, dict) else binding
                if address != "None" or direction == ("read" if kind == "numeric_display" else "write"):
                    self._control_address(address, prefix, "D" if kind in {"numeric_input", "numeric_display"} else "M", schema, direction)
                if isinstance(binding, dict):
                    for key, field in (("link", direction.title() + "Link"), ("mem_type", direction.title() + "MemType")):
                        if key in binding and binding[key] != _native_int(owner["section"], field):
                            raise HmiError("CONTROL_ADDRESS_SCOPE", "Control binding cannot change source-local metadata")
            self._bind(document, operation, schema)
        elif name == "convert_numeric_storage":
            if kind not in {"numeric_input", "numeric_display"}:
                raise HmiError("STORAGE_CONVERSION_SCOPE", "Only freshly cloned numeric owners admit the explicit format transformation")
            convert_storage(owner["section"], operation, schema)
        elif name == "configure_numeric":
            if operation.get("data_type") == "INT":
                if kind not in {"numeric_input", "numeric_display"} or operation.get("kind") != kind:
                    raise HmiError("STORAGE_CONVERSION_SCOPE", "Signed numeric settings require the matching witnessed numeric clone")
                configure_converted(owner["section"], operation, schema)
                return
            if (kind not in {"numeric_input", "numeric_display"} or operation.get("kind") != kind or operation.get("data_type") != "UINT"
                    or (operation.get("fractional_digits") != 0 and operation.get("value_model") != FIXED_DECIMAL_MODEL)):
                raise HmiError("UNQUALIFIED_CONTROL_NUMERIC", "Controls admit only witnessed UINT input/display configuration")
            configure_numeric(owner["section"], operation, schema)
        else:
            raise HmiError("CONTROL_GENERATION_SCOPE", "Control generation cannot perform this operation", operation=name)

    def verify_layout_order(self, schema=None, original_adapter=None):
        """Pure bounded sequence guard, including append-only and no-op cases.

        No native pixel or z-order claim follows from passing this guard.
        The default rejects existing Order and non-Application global prefixes.
        A qualified preserved_layout contract admits existing-owner edits only,
        retaining raw globals/pages, identities, State sequence and every Order.
        """
        opaque = self._diascreen_contract(schema)
        if isinstance(schema, dict) and "control_generation" in schema:
            return self.verify_control_generation(schema, original_adapter)
        if isinstance(schema, dict) and "literal_generation" in schema:
            return self._verify_literal_generation(schema, original_adapter)
        if isinstance(schema, dict) and "preserved_layout" in schema:
            contract = schema["preserved_layout"]
            if opaque is None and (schema.get("qualified") is not True or not isinstance(contract, dict)
                    or set(contract) != {"qualified", "contract_version", "mode", "source_sha256", "prefix_sha256", "sections"}
                    or contract.get("qualified") is not True or type(contract.get("contract_version")) is not int
                    or contract["contract_version"] != 1 or contract.get("mode") != "existing_owner_edits"
                    or not isinstance(contract.get("sections"), list) or not 1 <= len(contract["sections"]) <= len(_PRESERVED_GLOBALS)):
                raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Preserved layout requires its exact source-local existing-owner contract")
            for key in ("source_sha256", "prefix_sha256"):
                if not isinstance(contract.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", contract[key]):
                    raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Preserved layout needs canonical source fingerprints", field=key)
            for entry in (() if opaque is not None else contract["sections"]):
                if (not isinstance(entry, dict) or set(entry) != {"name", "sha256"}
                        or not isinstance(entry.get("name"), str) or entry["name"] not in _PRESERVED_GLOBALS
                        or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                    raise HmiError("UNQUALIFIED_PRESERVED_LAYOUT", "Preserved prefix entries need exact section names and fingerprints")
            self._preserved_byte_binding("INVALID_PRESERVED_CANDIDATE")
            if original_adapter is None:
                if hashlib.sha256(self.original).hexdigest() != contract["source_sha256"]:
                    raise HmiError("INVALID_PRESERVED_SOURCE", "Candidate layout verification requires the immutable original source")
                original_adapter = self
            if isinstance(original_adapter, NativeAdapter):
                original_adapter._preserved_byte_binding("INVALID_PRESERVED_SOURCE")
            if (not isinstance(original_adapter, NativeAdapter) or original_adapter.family != self.family
                    or not model_ids_match(original_adapter.model_id, self.model_id)
                    or original_adapter.application.one("Version").value != self.application.one("Version").value
                    or hashlib.sha256(original_adapter.original).hexdigest() != contract["source_sha256"]
                    or original_adapter.document.bytes() != Envelope.decode(original_adapter.original, original_adapter.family).body):
                raise HmiError("INVALID_PRESERVED_SOURCE", "Preserved layout source identity or immutable bytes do not match")
            if opaque is not None:
                original_adapter._diascreen_contract(schema)
            policy = _DIA_PREFIX_POLICY if opaque is not None else None
            original_prefix, sections = self._preserved_prefix(original_adapter.document, prefix_policy=policy)
            candidate_prefix, candidate_sections = self._preserved_prefix(self.document, prefix_policy=policy)
            if (hashlib.sha256(original_prefix).hexdigest() != contract["prefix_sha256"]
                    or sections != contract["sections"] or candidate_sections != sections or candidate_prefix != original_prefix
                    or self.envelope.thumbnail != original_adapter.envelope.thumbnail
                    or self.envelope.prefix != original_adapter.envelope.prefix_for_body(self.envelope.body)
                    or self.document.tail != original_adapter.document.tail
                    or self._preserved_sequence() != original_adapter._preserved_sequence()):
                raise HmiError("PRESERVED_LAYOUT_MISMATCH", "Preserved layout changed a raw global/page record, owner sequence, Order or uncontrolled envelope/tail")
            if opaque is not None:
                self._verify_diascreen_body(original_adapter)
            return True
        screens = _groups(self.document)
        if screens and screens[0]["start"] != 1:
            raise HmiError("UNQUALIFIED_STRUCTURE", "Layout sequence has unqualified prefix sections")
        for screen in screens:
            self._plain_extent(screen)
            for section in self.document.sections[screen["start"]:screen["end"]]:
                if section.one("Order", False) is not None:
                    raise HmiError("UNQUALIFIED_LAYER", "Native Order relationship to section sequence is unqualified")
        return True

    def macro_statements(self, owner, field, schema, original_adapter):
        """Decode a saved candidate under exact immutable source calibration."""
        self._macro_source(original_adapter)
        return macro_semantics.statements(self.document, original_adapter.document, owner, field, schema)

    def verify_macro_contract(self, operation, schema, original_adapter):
        """Pure semantic verification; never changes source or candidate bytes."""
        self._macro_source(original_adapter)
        return macro_semantics.verify(self.document, original_adapter.document, operation, schema)

    def _macro_source(self, original_adapter):
        if (not isinstance(original_adapter, NativeAdapter) or original_adapter.family != self.family
                or not model_ids_match(original_adapter.model_id, self.model_id)
                or original_adapter.editor_version != self.editor_version):
            raise HmiError("INVALID_MACRO_SOURCE", "Macro calibration requires the exact source target identity")

    def _property(self, doc, operation, schema):
        screen = _screen(doc, operation.get("screen_id"))
        element = _element(screen, operation.get("element_id"))
        key = _string(operation.get("key"), "key")
        spec = schema.get("properties", {}).get(key)
        if not isinstance(spec, dict) or spec.get("field") not in _PROPERTIES:
            raise HmiError("UNQUALIFIED_PROPERTY", "Property lacks a qualified observed native mapping", property=key)
        section = element["section"]
        if spec.get("scope", "element") == "state":
            index = _integer(operation.get("state_index", 0), "state_index")
            if index >= len(element["states"]):
                raise HmiError("UNKNOWN_STATE", "Native state does not exist")
            section = element["states"][index]
        elif spec.get("scope", "element") != "element":
            raise HmiError("INVALID_SCHEMA", "Property scope must be element or state")
        field = spec["field"]
        record = section.one(field)
        value = operation.get("value")
        kind = spec.get("type")
        if kind == "enum":
            values = spec.get("values")
            if not isinstance(values, dict) or not isinstance(value, str) or value not in values:
                raise HmiError("UNQUALIFIED_ENUM", "Behavior/value lacks a qualified native enum", property=key)
            value = values[value]
            encoded = str(_integer(value, key, -0x80000000)).encode("ascii")
        elif kind == "int":
            if field in {"Type", "SubType"}:
                raise HmiError("UNQUALIFIED_ENUM", "Native type/behavior needs an enum mapping")
            lo, hi = spec.get("min", -0x80000000), spec.get("max", 0x7FFFFFFF)
            if type(lo) is not int or type(hi) is not int or lo > hi:
                raise HmiError("INVALID_SCHEMA", "Integer property limits are invalid")
            encoded = str(_integer(value, key, max(lo, -0x80000000), min(hi, 0x7FFFFFFF))).encode("ascii")
        elif kind == "string" and field in {"FontName0"}:
            value = _string(value, key)
            try:
                encoded = value.encode(spec.get("encoding", "ascii"), "strict")
            except (UnicodeEncodeError, LookupError) as exc:
                raise HmiError("INVALID_VALUE", "Property cannot be encoded losslessly", property=key) from exc
        else:
            raise HmiError("INVALID_SCHEMA", "Native property needs an explicit supported type", property=key)
        record.set_value(encoded)
        self._geometry(screen, element, schema)

    def _geometry(self, screen, element, schema):
        mapping = schema.get("geometry", {"x": "X", "y": "Y", "width": "Width", "height": "Height"})
        if mapping != {"x": "X", "y": "Y", "width": "Width", "height": "Height"}:
            raise HmiError("INVALID_SCHEMA", "V1 geometry supports the observed X/Y/Width/Height fields")
        vals = [_native_int(element["section"], mapping[k]) for k in ("x", "y", "width", "height")]
        if any(v is None for v in vals):
            raise HmiError("UNQUALIFIED_GEOMETRY", "Element has no complete native geometry")
        x, y, width, height = vals
        if x < 0 or y < 0 or width <= 0 or height <= 0 or any(v > 0x7FFFFFFF for v in vals):
            raise HmiError("NATIVE_GEOMETRY", "Element geometry must have nonnegative position and positive size")
        limit_x = _native_int(screen["section"], "DocSizeX") or _native_int(screen["section"], "PanelSizeX")
        limit_y = _native_int(screen["section"], "DocSizeY") or _native_int(screen["section"], "PanelSizeY")
        if limit_x is None or limit_y is None or limit_x <= 0 or limit_y <= 0:
            raise HmiError("UNQUALIFIED_GEOMETRY", "Screen has no positive native document size")
        if x + width > limit_x or y + height > limit_y:
            raise HmiError("NATIVE_GEOMETRY", "Element extends beyond the native screen size")

    def _text(self, doc, operation):
        element = _element(_screen(doc, operation.get("screen_id")), operation.get("element_id"))
        index = _integer(operation.get("state_index"), "state_index")
        language = _integer(operation.get("language", 0), "language")
        if index >= len(element["states"]):
            raise HmiError("UNKNOWN_STATE", "Native state does not exist")
        element["states"][index].one("wTextLen" + str(language)).set_text(operation.get("text"))

    def _bind(self, doc, operation, schema):
        element = _element(_screen(doc, operation.get("screen_id")), operation.get("element_id"))
        directions = [key for key in ("read", "write") if key in operation]
        if not directions:
            raise HmiError("INVALID_BINDING", "Binding operation needs read and/or write")
        for direction in directions:
            spec = schema.get("bindings", {}).get(direction)
            expected = "Read" if direction == "read" else "Write"
            if not isinstance(spec, dict) or spec.get("field") != expected + "Var":
                raise HmiError("UNQUALIFIED_BINDING", "Binding lacks an observed qualified native field", direction=direction)
            binding = operation[direction]
            metadata = {"link": "link_field", "mem_type": "mem_type_field"}
            if isinstance(binding, str):
                if any(key in spec for key in metadata.values()):
                    raise HmiError("INVALID_BINDING", "This profile requires exact address and binding metadata")
                binding = {"address": binding}
            if not isinstance(binding, dict) or set(binding) - {"address", "link", "mem_type"}:
                raise HmiError("INVALID_BINDING", "Binding must contain only address/link/mem_type")
            address = _string(binding.get("address"), "address")
            try:
                encoded = address.encode("ascii", "strict")
            except UnicodeEncodeError as exc:
                raise HmiError("INVALID_BINDING", "Native address must be ASCII") from exc
            element["section"].one(spec["field"]).set_value(encoded)
            for key, schema_key in metadata.items():
                if schema_key in spec:
                    if spec[schema_key] != expected + ("Link" if key == "link" else "MemType"):
                        raise HmiError("UNQUALIFIED_BINDING", "Binding metadata uses an unobserved field")
                    value = _integer(binding.get(key), key)
                    element["section"].one(spec[schema_key]).set_value(str(value).encode("ascii"))
                elif key in binding:
                    raise HmiError("UNQUALIFIED_BINDING", "Binding metadata lacks a native mapping", field=key)

    def _structural(self, doc, operation, schema, name):
        if name == "append_literal_page":
            raise HmiError("UNQUALIFIED_LITERAL_GENERATION", "Header-only page generation requires its distinct literal contract")
        if schema.get("cloning") is not True:
            raise HmiError("UNQUALIFIED_STRUCTURE", "Structural edits require profile qualification")
        if name == "clone_screen":
            source = _screen(doc, operation.get("source_screen"))
            _screen_extent(doc, source)
            _screen_extent(doc, _groups(doc)[-1])
            new_id = _identity(operation.get("screen_id"), "screen_id")
            if any(s["id"] == new_id for s in _groups(doc)):
                raise HmiError("DUPLICATE_SCREEN", "Clone target screen already exists")
            clone = deepcopy(doc.sections[source["start"]:source["end"]])
            clone[0].one("ID").set_value(new_id.encode("ascii"))
            clone[0].one("wTextLen").set_text(operation.get("name"))
            doc.sections.extend(clone)
            target = _screen(doc, new_id)
            for element in target["elements"]:
                self._geometry(target, element, schema)
            return
        if name == "delete_element":
            screen = _screen(doc, operation.get("screen_id"))
            element = _element(screen, operation.get("element_id"))
            _element_extent(doc, element)
            del doc.sections[element["start"]:element["end"]]
            return
        source = _element(_screen(doc, operation.get("source_screen")), operation.get("source_element"))
        target = _screen(doc, operation.get("target_screen"))
        _element_extent(doc, source)
        _screen_extent(doc, target)
        new_id = _identity(operation.get("element_id"), "element_id")
        if any(e["id"] == new_id for e in target["elements"]):
            raise HmiError("DUPLICATE_ELEMENT", "Clone target element already exists")
        clone = deepcopy(doc.sections[source["start"]:source["end"]])
        clone[0].one("nPartsID").set_value(new_id.encode("ascii"))
        doc.sections[target["end"]:target["end"]] = clone
        self._geometry(_screen(doc, target["id"]), _element(_screen(doc, target["id"]), new_id), schema)

    def _literal_operation(self, document, operation, schema, name, donors):
        page_donor, auxiliary, text_donor = donors
        original_pages = {screen["id"] for screen in _groups(self.document)}
        if name == "append_literal_page":
            if set(operation) != _ARGUMENTS[name]:
                raise HmiError("INVALID_OPERATION", "New literal page requires exactly ID and name")
            identity = _identity(operation.get("screen_id"), "screen_id")
            if identity == "0":
                raise HmiError("INVALID_ID", "New literal page identity must be positive")
            if any(screen["id"] == identity for screen in _groups(document)):
                raise HmiError("DUPLICATE_SCREEN", "Literal page identity already exists")
            _string(operation.get("name"), "name")
            header = deepcopy(page_donor["section"])
            header.one("ID").set_value(identity.encode("ascii"))
            header.one("wTextLen").set_text(operation["name"])
            document.sections.extend([header, deepcopy(auxiliary)])
            return
        if name == "clone_element":
            if set(operation) != _ARGUMENTS[name]:
                raise HmiError("INVALID_OPERATION", "Literal clone requires exact source/target owner identities")
            pin = schema["literal_generation"]["text_donor"]
            if operation.get("source_screen") != pin["screen_id"] or operation.get("source_element") != pin["element_id"]:
                raise HmiError("LITERAL_GENERATION_SCOPE", "Literal clone can use only its immutable source donor")
            target = _screen(document, operation.get("target_screen"))
            if target["id"] in original_pages:
                raise HmiError("LITERAL_GENERATION_SCOPE", "Literal clones can be appended only to newly generated pages")
            identity = _identity(operation.get("element_id"), "element_id")
            if identity == "0":
                raise HmiError("INVALID_ID", "New literal owner identity must be positive")
            if any(element["id"] == identity for screen in _groups(document) for element in screen["elements"]):
                raise HmiError("DUPLICATE_ELEMENT", "New literal owner identity is already used in the project")
            # Never resolve a donor from the mutated document. It may contain
            # earlier appended pages/owners that are not calibration sources.
            clone = deepcopy(self.document.sections[text_donor["start"]:text_donor["end"]])
            clone[0].one("nPartsID").set_value(identity.encode("ascii"))
            document.sections[target["end"]:target["end"]] = clone
            target = _screen(document, target["id"])
            self._geometry(target, _element(target, identity), {})
            return
        if name not in {"set_property", "set_text"}:
            raise HmiError("LITERAL_GENERATION_SCOPE", "Literal generation cannot perform this native operation", operation=name)
        target = _screen(document, operation.get("screen_id"))
        if target["id"] in original_pages:
            raise HmiError("LITERAL_GENERATION_SCOPE", "Literal generation cannot change original owners")
        _element(target, operation.get("element_id"))
        if name == "set_property":
            if set(operation) != {"op", "screen_id", "element_id", "key", "value"}:
                raise HmiError("INVALID_OPERATION", "Literal geometry operation requires exact owner/key/value")
            key = operation.get("key")
            mapping = {"x": "X", "y": "Y", "width": "Width", "height": "Height"}
            spec = schema.get("properties", {}).get(key) if isinstance(key, str) else None
            if (not isinstance(key, str) or key not in mapping or not isinstance(spec, dict) or spec.get("field") != mapping[key]
                    or spec.get("type") != "int" or spec.get("scope", "element") != "element"):
                raise HmiError("LITERAL_GENERATION_SCOPE", "Literal generation permits only explicit integer owner geometry")
            self._property(document, operation, schema)
        else:
            if (set(operation) != {"op", "screen_id", "element_id", "state_index", "language", "text"}
                    or type(operation.get("state_index")) is not int or operation["state_index"] != 0
                    or type(operation.get("language")) is not int or operation["language"] != 0):
                raise HmiError("LITERAL_GENERATION_SCOPE", "Literal caption operation requires State 0/language 0")
            self._text(document, operation)

    def _layout(self, doc, operation, schema, name):
        structure = schema.get("structure")
        expected = {"rename_screen": {"field": "wTextLen"},
                    "reorder_elements": {"ordering": "section-sequence", "extent": "element-and-states"},
                    "reorder_screens": {"ordering": "section-sequence", "extent": "screen-and-elements"}}
        if (not isinstance(structure, dict) or structure.get("qualified") is not True
                or structure.get(name) != expected[name]):
            raise HmiError("UNQUALIFIED_STRUCTURE", "Layout operation lacks an exact qualified native mapping", operation=name)
        if name == "rename_screen":
            screen = _screen(doc, operation.get("screen_id"))
            record = screen["section"].one("wTextLen")
            old_name, new_name = record.text(), operation.get("name")
            # Resolve every target dependency before editing either record.
            # Unknown reference fields may contain a name-based destination;
            # guessing that they are harmless would produce a partial rename.
            companions = []
            for section in doc.sections:
                for item in section.records:
                    if (item.key and re.search(r"Screen(?:ID|Name)", item.key, re.IGNORECASE)
                            and (section.name != "Element" or item.key not in {"GoToScreenID", "GoToScreenName"})):
                        raise HmiError("UNQUALIFIED_NAVIGATION", "Page rename encounters an unknown native reference field", field=item.key)
            for page in _groups(doc):
                for element in page["elements"]:
                    section = element["section"]
                    target = section.one("GoToScreenID", False)
                    companion = section.one("GoToScreenName", False)
                    if target is None:
                        if companion is not None:
                            raise HmiError("UNQUALIFIED_NAVIGATION", "Navigation name has no qualified destination identity")
                        continue
                    target_id = _identity(target.value.decode("latin-1"), "GoToScreenID")
                    if target_id != screen["id"]:
                        continue
                    self._navigation_match(element, schema)
                    if companion is not None:
                        before, encoded = self._navigation_name(section, schema, new_name)
                        if before != old_name:
                            raise HmiError("NAVIGATION_NAME_MISMATCH", "Navigation companion differs from its current target name")
                        companions.append((companion, encoded))
            record.set_text(new_name)
            for companion, encoded in companions:
                companion.set_value(encoded)
            return
        if name == "reorder_elements":
            screen = _screen(doc, operation.get("screen_id"))
            _screen_extent(doc, screen)
            for element in screen["elements"]:
                _element_extent(doc, element)
            selected = screen["elements"]
            wanted = self._permutation(operation.get("element_ids"), [e["id"] for e in selected], "element_ids")
            # Native Order is a competing uncalibrated representation. A
            # section sequence alone must not claim that it controls z-order.
            for section in doc.sections[screen["start"]:screen["end"]]:
                if section.one("Order", False) is not None:
                    raise HmiError("UNQUALIFIED_LAYER", "Native Order relationship to section sequence is unqualified")
            if not selected or wanted == [e["id"] for e in selected]:
                return
            blocks = {e["id"]: doc.sections[e["start"]:e["end"]] for e in selected}
            doc.sections[selected[0]["start"]:screen["end"]] = [part for identity in wanted for part in blocks[identity]]
            return
        screens = _groups(doc)
        wanted = self._permutation(operation.get("screen_ids"), [s["id"] for s in screens], "screen_ids")
        if screens and screens[0]["start"] != 1:
            raise HmiError("UNQUALIFIED_STRUCTURE", "Screen sequence has unqualified prefix sections")
        for screen in screens:
            _screen_extent(doc, screen)
            for element in screen["elements"]:
                _element_extent(doc, element)
            if screen["section"].one("Order", False) is not None:
                raise HmiError("UNQUALIFIED_LAYER", "Native page Order relationship to section sequence is unqualified")
        if not screens or wanted == [s["id"] for s in screens]:
            return
        blocks = {s["id"]: doc.sections[s["start"]:s["end"]] for s in screens}
        doc.sections[screens[0]["start"]:] = [part for identity in wanted for part in blocks[identity]]

    @staticmethod
    def _permutation(value, current, label):
        if not isinstance(value, list) or len(value) != len(current):
            raise HmiError("INVALID_ORDER", "Native order must be a complete identity permutation", field=label)
        wanted = [_identity(identity, label) for identity in value]
        if len(set(wanted)) != len(wanted) or set(wanted) != set(current):
            raise HmiError("INVALID_ORDER", "Native order has missing, repeated or unknown identities", field=label)
        return wanted

    @staticmethod
    def _navigation_match(element, schema):
        spec = schema.get("navigation")
        if (not isinstance(spec, dict) or spec.get("qualified") is not True
                or spec.get("field") != "GoToScreenID" or not isinstance(spec.get("match"), dict)
                or set(spec["match"]) != {"Type", "SubType"}):
            raise HmiError("UNQUALIFIED_NAVIGATION", "Navigation needs an exact qualified donor mapping")
        for field, expected in spec["match"].items():
            if not isinstance(expected, str) or not re.fullmatch(r"0|[1-9][0-9]{0,9}", expected):
                raise HmiError("INVALID_SCHEMA", "Navigation enum mapping must use canonical decimal strings")
            if _value(element["section"], field) != expected:
                raise HmiError("NAVIGATION_DONOR_MISMATCH", "Navigation donor has a different native behavior", field=field)
        return spec

    @staticmethod
    def _navigation_name(section, schema, name):
        spec = schema["navigation"]
        if spec.get("name_field") != "GoToScreenName" or spec.get("name_encoding") != "ascii":
            raise HmiError("UNQUALIFIED_NAVIGATION", "Navigation companion needs an exact narrow-name encoding mapping")
        record = section.one("GoToScreenName")
        if record.kind is not None or not isinstance(name, str) or any(c in name for c in "\r\n\0"):
            raise HmiError("UNQUALIFIED_NAVIGATION", "Navigation name is not a qualified scalar string")
        try:
            return record.value.decode("ascii", "strict"), name.encode("ascii", "strict")
        except UnicodeError as exc:
            raise HmiError("UNQUALIFIED_NAVIGATION", "Navigation name cannot be encoded losslessly") from exc

    def _goto(self, doc, operation, schema):
        element = _element(_screen(doc, operation.get("screen_id")), operation.get("element_id"))
        spec = self._navigation_match(element, schema)
        target = _screen(doc, operation.get("target_screen"))
        companion = element["section"].one("GoToScreenName", False)
        encoded = None
        if companion is not None:
            old_id = _identity(_value(element["section"], spec["field"]), spec["field"])
            old_target = _screen(doc, old_id)
            current, encoded = self._navigation_name(element["section"], schema, target["section"].one("wTextLen").text())
            if current != old_target["section"].one("wTextLen").text():
                raise HmiError("NAVIGATION_NAME_MISMATCH", "Navigation companion differs from its current target name")
        element["section"].one(spec["field"]).set_value(target["id"].encode("ascii"))
        if companion is not None:
            companion.set_value(encoded)

    def apply(self, operations: list[dict], profile: dict) -> bytes:
        if not isinstance(operations, list):
            raise HmiError("INVALID_OPERATIONS", "Operations must be a list")
        if not operations:
            if (isinstance(profile, dict) and isinstance(profile.get("native_schema"), dict)
                    and ({"preserved_layout", "literal_generation", "control_generation"} & set(profile["native_schema"]))):
                self.verify_layout_order(self._schema(profile))
            return self.original
        schema = self._schema(profile)
        opaque = self._diascreen_contract(schema)
        retained = "preserved_layout" in schema
        literal = "literal_generation" in schema
        control = "control_generation" in schema
        if retained or literal or control:
            self.verify_layout_order(schema)
        literal_donors = self._literal_donors(schema) if literal else None
        control_donors = self.control_donors(schema) if control else None
        document = deepcopy(self.document)
        macro_targets = set()
        alarm_operation = None
        opaque_targets = set()
        for operation in operations:
            if not isinstance(operation, dict):
                raise HmiError("INVALID_OPERATION", "Each operation must be an object")
            name = operation.get("op")
            if not isinstance(name, str) or name not in _OPS:
                raise HmiError("UNSUPPORTED_OPERATION", "Unsupported native operation", operation=name)
            if set(operation) - _ARGUMENTS[name]:
                raise HmiError("INVALID_OPERATION", "Operation contains unknown arguments", operation=name)
            if opaque is not None:
                self._diascreen_operation(document, operation, opaque_targets)
                continue
            if control:
                self._control_operation(document, operation, schema, name, control_donors)
                continue
            if literal:
                self._literal_operation(document, operation, schema, name, literal_donors)
                continue
            if retained and (name in _PRESERVED_STRUCTURAL or name == "configure_alarm"):
                raise HmiError("PRESERVED_LAYOUT_SCOPE", "Existing-owner mode cannot change structure or global Alarm resources", operation=name)
            if name == "set_property":
                self._property(document, operation, schema)
            elif name == "set_text":
                self._text(document, operation)
            elif name == "set_unit_caption":
                self._unit_caption(document, operation, schema)
            elif name == "bind":
                self._bind(document, operation, schema)
            elif name == "configure_numeric":
                element = _element(_screen(document, operation.get("screen_id")), operation.get("element_id"))
                configure_numeric(element["section"], operation, schema)
            elif name == "configure_goto":
                self._goto(document, operation, schema)
            elif name in {"rename_screen", "reorder_elements", "reorder_screens"}:
                self._layout(document, operation, schema, name)
            elif name == "configure_macro":
                owner = macro_semantics.normalize_owner(operation.get("owner"))
                if retained and owner["kind"] != "element":
                    raise HmiError("PRESERVED_LAYOUT_SCOPE", "Existing-owner mode retains every global/page macro owner")
                field = operation.get("field")
                if not isinstance(field, str):
                    raise HmiError("INVALID_MACRO_OWNER", "Macro field must be a string")
                key = (tuple(sorted(owner.items())), field)
                if key in macro_targets:
                    raise HmiError("DUPLICATE_MACRO_UPDATE", "One transaction cannot configure the same macro twice")
                macro_targets.add(key)
                macro_semantics.configure(document, self.document, operation, schema)
            elif name == "configure_alarm":
                if alarm_operation is not None:
                    raise HmiError("DUPLICATE_ALARM_UPDATE", "All global Alarm updates must be consolidated into one operation")
                alarm_operation = operation
            else:
                self._structural(document, operation, schema, name)
        if alarm_operation is not None:
            document.tail = ResourceTables.parse(self.document.tail).apply(alarm_operation, schema)
        body = document.bytes()
        if body == self.envelope.body:
            return self.original
        # Re-read exactly the bytes to be returned; errors cannot leak partial
        # updates and the adapter's immutable source is never changed.
        output = self.envelope.encode(body)
        candidate = NativeAdapter(output, self.family)
        if retained or literal or control:
            candidate.verify_layout_order(schema, self)
        return output


__all__ = ["NativeAdapter", "canonical_model_id", "model_ids_match"]
