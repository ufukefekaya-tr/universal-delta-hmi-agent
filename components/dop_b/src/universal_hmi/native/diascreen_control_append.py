"""Bounded, source-local DIAScreen stored control cloning.

This does not allocate internal addresses or assert runtime button behavior.
All original records/resources stay intact; each clone intentionally shares its
donor's stored binding. Registered source authority belongs to the caller.
"""
from copy import deepcopy
import hashlib
import re

from ..errors import HmiError
from . import NativeAdapter, _groups, _screen_extent, _element_extent
from .codec import MAX_PAYLOAD
from .existing_program import _bounded


FAMILY = "delta_diascreen"
MODEL = "268502784"
VERSION = "6.0.00205.8268"
MODE = "diascreen_source_control_append_v1"
PREFIX_NAMES = ("Application", "Multi-Language", "Global-Camera", "Event-Trigger",
    "Global-Keypad", "Recipe", "Recipe32", "EnhanceRcp", "Ethernet",
    "Modbus_TCP_Server", "SIP", "RemoteCtrl", "VNCCtrl", "RTC", "LOG", "FTP",
    "FTPFile", "DataExchange", "DataExchangeEnd", "LuaData", "ExtraZA_ZGSection")
DONOR_IDS = {"momentary": ("13", "3"), "maintained": ("5", "66"),
    "numeric_input": ("2", "19"), "numeric_display": ("6", "10")}
_SHA = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[1-9][0-9]{0,9}")
_PAGE_KEYS = {"screen_id", "header_sha256", "aux_sha256", "doc_width", "doc_height",
    "panel_width", "panel_height", "element_count"}
_CONTRACT_KEYS = {"qualified", "contract_version", "mode", "source_sha256", "family",
    "model_id", "editor_version", "authority_sha256", "prefix_sha256", "tail_sha256",
    "target_screen_id", "pages", "donors"}
_OP_KEYS = {"op", "screen_id", "element_id", "donor_kind", "x", "y", "width", "height", "captions"}
_COMMON = tuple("""Type SubType CombineType X Y Width Height GroupID Style BorderColor
PrintSuccessiveData ReadMemType WriteMemType ReadLink WriteLink ReadVar WriteVar
MemLen MemFmt Level OffsetReadMemType OffsetWriteMemType OffsetReadVar OffsetWriteVar
OffsetMemLen OffsetMemFmt nAngle opacity animated antialiasing bFreeze UseBMPText
nPartsID nKeypadTabOrder RelatedFileBrowserPartID wDescTextLen0""".split())
_BUTTON_HEAD = tuple("ButtonOnMacroLen ButtonOffMacroLen PushTime ModifierKey HotKey WriteReadImmediately".split())
_BUTTON_TAIL = tuple("""SetLowSecurity VisibleLink VisibleVar InterLockLink InterLockVar
InterLockLevel InterLockViewMode ConFirmWindow NoMessage DispAsterisk BeforeExecMacroLen AfterExecMacroLen""".split())
_UNIT = tuple("""UnitType UnitSrc UnitSrcVar UnitDisplay UnitDisplayVar UnitPercent
UnitPercent1Var UnitPercent2Var UnitCustom1Var_1 UnitCustom2Var_1 BackupUnitSrc BackupUnitDisplay""".split())
_INPUT_HEAD = tuple("""TriggerLink TriggerVar Order MinValue MaxValue IntNum DotNum LeadingZero
GainValue OffsetValue Roundoff Variation SetLowSecurity VisibleLink VisibleVar InterLockLink
InterLockVar InterLockLevel InterLockViewMode BeforeExecMacroLen AfterExecMacroLen DispAsterisk
Active KeyPadLeft KeyPadTop KeyPadRight KeyPadBottom TitleHeight""".split())
_KEYPAD = tuple(key for i in range(6) for key in (f"wKPFStringLen{i:03}-000",
    f"KPFontSize{i:03}-000", f"KPFontName{i:03}-000", f"KPFontColor{i:03}", f"KPBkgndColor{i:03}"))
_ELEMENT_KEYS = {
    "maintained": _COMMON + _BUTTON_HEAD + _BUTTON_TAIL,
    "momentary": _COMMON + _BUTTON_HEAD + ("OffVoice",) + _BUTTON_TAIL,
    "numeric_input": _COMMON + _INPUT_HEAD + _UNIT + _KEYPAD + tuple(
        "RangeFontSize RangeFontColor NoMessage ShowOverRange UseCustKeypad KeypadScreenID HiWordFirst".split()),
    "numeric_display": _COMMON + tuple(
        "IntNum DotNum LeadingZero GainValue OffsetValue Roundoff VisibleLink VisibleVar".split()) + _UNIT + ("HiWordFirst",),
}
_STATE_KEYS = tuple("""Value FgColor BgColor FillStyle BorderStyle FontColor FontSize0 FontRatio0
FontName0 wTextLen0 FontAlign FontBold FontItalic FontUnderline UsePictureCoord PictureAlign
TransEffect TransColor StretchMode PictureStretch Twinkles SoundIndex""".split())


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fail(message, **context):
    raise HmiError("UNQUALIFIED_DIA_CONTROL_APPEND", message, **context)


def _digest(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail("Source-control pins require canonical SHA-256", field=label)
    return value


def _identity(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value) or int(value) > 0x7fffffff:
        _fail("Source-control identity must be a canonical bounded string", field=label)
    return value


def _integer(value, label, minimum=0, maximum=800):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail("Source-control integer is outside its exact range", field=label)
    return value


def diascreen_control_append_contract(schema):
    """Validate the exact descriptor; a digest alone is not authority proof."""
    _bounded(schema)
    if type(schema) is not dict or set(schema) != {"diascreen_control_append"}:
        _fail("Stored DIAScreen clones require their separate unmixed schema")
    c = schema["diascreen_control_append"]
    if (type(c) is not dict or set(c) != _CONTRACT_KEYS or c.get("qualified") is not True
            or type(c.get("contract_version")) is not int or c["contract_version"] != 1
            or c.get("mode") != MODE or c.get("family") != FAMILY or c.get("model_id") != MODEL
            or c.get("editor_version") != VERSION or c.get("target_screen_id") != "20"):
        _fail("Stored DIAScreen clone descriptor/profile is not qualified")
    for key in ("source_sha256", "authority_sha256", "prefix_sha256", "tail_sha256"):
        _digest(c[key], key)
    if type(c["pages"]) is not list or not 1 <= len(c["pages"]) <= 256:
        _fail("Original page inventory must be nonempty and bounded")
    seen = set()
    for p in c["pages"]:
        if type(p) is not dict or set(p) != _PAGE_KEYS:
            _fail("Original page pins require their exact field set")
        sid = _identity(p["screen_id"], "screen_id")
        if sid in seen:
            _fail("Original page pin is repeated")
        seen.add(sid)
        _digest(p["header_sha256"], "header_sha256")
        _digest(p["aux_sha256"], "aux_sha256")
        for key in ("doc_width", "doc_height", "panel_width", "panel_height"):
            _integer(p[key], key, 1, 800 if key.endswith("width") else 480)
        _integer(p["element_count"], "element_count", 0, 4096)
    if "20" not in seen:
        _fail("Original target page pin is absent")
    if type(c["donors"]) is not dict or set(c["donors"]) != set(DONOR_IDS):
        _fail("Exactly four source donor kinds must be pinned")
    for kind, (sid, eid) in DONOR_IDS.items():
        donor = c["donors"][kind]
        if (type(donor) is not dict or set(donor) != {"screen_id", "element_id", "owner_sha256"}
                or donor.get("screen_id") != sid or donor.get("element_id") != eid):
            _fail("Donor identity differs from the source-local observed variant", donor_kind=kind)
        _digest(donor["owner_sha256"], "owner_sha256")
    return deepcopy(c)


def _raw_extent(document, owner):
    return b"".join(s.bytes() for s in document.sections[owner["start"]:owner["end"]])


def _scalar(section, key):
    r = section.one(key)
    if r.kind is not None or r.blob is not None or r.raw != key.encode("ascii") + b"=" + r.value + b"\r\n":
        _fail("Native scalar framing differs from the ordinary source variant", field=key)
    try:
        return r.value.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("UNQUALIFIED_DIA_CONTROL_APPEND", "Native scalar is not ASCII", field=key) from exc


def _source_integer(section, key, minimum=0, maximum=800):
    value = _scalar(section, key)
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", value) or not minimum <= int(value) <= maximum:
        _fail("Native geometry/dimension does not have qualified decimal framing", field=key)
    return int(value)


def _shape(section, keys):
    if section.header != ("[" + section.name + "]\r\n").encode("ascii") or tuple(r.key for r in section.records) != keys:
        _fail("Donor field ordering/shape differs from the observed source variant", section=section.name)
    for r in section.records:
        if r.kind == "wide":
            r.text()
        elif r.kind == "macro":
            if r.value != b"0" or r.blob != b"" or r.raw != r.key.encode() + b"=0\r\n":
                _fail("Donor has a macro body or noncanonical macro frame", field=r.key)
        elif r.kind is not None:
            _fail("Donor contains an unqualified opaque field", field=r.key)
        else:
            _scalar(section, r.key)


def _equals(section, mapping):
    for key, expected in mapping.items():
        if _scalar(section, key) != expected:
            _fail("Donor has an unqualified stored configuration", field=key)


class DiaScreenControlAppend:
    """An immutable-source transaction; every original page is retained."""

    def __init__(self, source, schema):
        if not isinstance(source, NativeAdapter):
            _fail("Source-control transaction requires a native source adapter")
        self.source = source
        self.schema = schema
        self.contract = diascreen_control_append_contract(schema)
        self._schema_snapshot = deepcopy(schema)
        self._contract_snapshot = deepcopy(self.contract)
        self._last_operations = []
        self.check()

    def check(self):
        current = diascreen_control_append_contract(self.schema)
        if self.schema != self._schema_snapshot or self.contract != self._contract_snapshot or current != self.contract:
            _fail("Source-control descriptor changed during the transaction")
        a, c = self.source, self.contract
        if a.family != FAMILY:
            _fail("Source-control family must remain the observed DIAScreen family")
        a._preserved_byte_binding("UNQUALIFIED_DIA_CONTROL_APPEND")
        if (a.model_id != MODEL or a.editor_version != VERSION or _sha(a.original) != c["source_sha256"]
                or _scalar(a.application, "PanelSeries") != "DOP-100 series"
                or a.document.bytes() != a.envelope.body or a.envelope.declared_body_length() != len(a.envelope.body)):
            _fail("Source-control bytes/model/version/declaration do not match their source pins")
        pages = _groups(a.document)
        if not pages or len(pages) != len(c["pages"]):
            _fail("Original page inventory changed")
        prefix = a.document.sections[:pages[0]["start"]]
        if tuple(s.name for s in prefix) != PREFIX_NAMES or _sha(b"".join(s.bytes() for s in prefix)) != c["prefix_sha256"]:
            _fail("Source has a different ordered document-prefix variant")
        if _sha(a.document.tail) != c["tail_sha256"]:
            _fail("Original resource tail changed")
        all_ids, total = set(), 0
        for page, pin in zip(pages, c["pages"]):
            _screen_extent(a.document, page)
            aux = a.document.sections[page["start"] + 1]
            if (page["id"] != pin["screen_id"] or _sha(page["section"].bytes()) != pin["header_sha256"]
                    or aux.name != "AuxKeyElement" or aux.bytes() != b"[AuxKeyElement]\r\n"
                    or _sha(aux.bytes()) != pin["aux_sha256"] or len(page["elements"]) != pin["element_count"]):
                _fail("Original page header/auxiliary/owner inventory differs from its pin")
            for key, field in (("doc_width", "DocSizeX"), ("doc_height", "DocSizeY"),
                    ("panel_width", "PanelSizeX"), ("panel_height", "PanelSizeY")):
                if _source_integer(page["section"], field, 1, 800 if key.endswith("width") else 480) != pin[key]:
                    _fail("Original page dimension differs from its pin", screen_id=page["id"], field=field)
            if page["id"] == "20" and (pin["element_count"] != 26
                    or [pin[k] for k in ("doc_width", "doc_height", "panel_width", "panel_height")] != [800,480,800,480]):
                _fail("Target page must retain its observed 26-owner 800x480 source variant")
            for owner in page["elements"]:
                _element_extent(a.document, owner)
                if _scalar(owner["section"], "GroupID") != "0":
                    _fail("Source has an unqualified grouped owner")
                all_ids.add(owner["id"])
            total += len(page["elements"])
        if total > 4096 or all_ids & {"97", "98", "99", "100"}:
            _fail("Source owner inventory exceeds its bound or collides with new identities")
        self._pages = pages
        self._donors = {}
        for kind, pin in c["donors"].items():
            page = next((p for p in pages if p["id"] == pin["screen_id"]), None)
            owner = next((e for e in page["elements"] if e["id"] == pin["element_id"]), None) if page else None
            if owner is None or _sha(_raw_extent(a.document, owner)) != pin["owner_sha256"]:
                _fail("Original donor extent differs from its complete source pin", donor_kind=kind)
            if [_source_integer(page["section"], k, 1, m) for k,m in
                    (("DocSizeX",800),("DocSizeY",480),("PanelSizeX",800),("PanelSizeY",480))] != [800,480,800,480]:
                _fail("Selected donor page is outside the observed 800x480 variant")
            self._check_donor(kind, owner)
            self._donors[kind] = owner
        return True

    def _check_donor(self, kind, owner):
        s = owner["section"]
        _shape(s, _ELEMENT_KEYS[kind])
        common = dict(CombineType="0", GroupID="0", PrintSuccessiveData="0", ReadLink="1", WriteLink="1",
            MemFmt="2", Level="0", OffsetReadMemType="0", OffsetWriteMemType="0", OffsetReadVar="None",
            OffsetWriteVar="None", OffsetMemLen="1", OffsetMemFmt="2", nAngle="0", opacity="255",
            animated="0", antialiasing="0", bFreeze="0", UseBMPText="0", nKeypadTabOrder="0",
            RelatedFileBrowserPartID="-1", VisibleLink="1", VisibleVar="None")
        if kind in ("momentary", "maintained"):
            common.update(Type="1", SubType="3" if kind=="momentary" else "4", MemLen="0", ReadVar="None",
                WriteVar="$2.1" if kind=="momentary" else "$430.0", ReadMemType="0", WriteMemType="0",
                Style="3" if kind=="momentary" else "0", PushTime="0", ModifierKey="0", HotKey="0",
                WriteReadImmediately="0", SetLowSecurity="0", InterLockLink="1", InterLockVar="None",
                InterLockLevel="1", InterLockViewMode="0", ConFirmWindow="0", NoMessage="0", DispAsterisk="0")
            if kind=="momentary": common["OffVoice"]="0"
        else:
            common.update(Type="6" if kind=="numeric_input" else "5", SubType="1", MemLen="1", Style="2",
                WriteVar="$120" if kind=="numeric_input" else "None", ReadVar="None" if kind=="numeric_input" else "$510",
                WriteMemType="0", ReadMemType="3" if kind=="numeric_input" else "0",
                IntNum="3" if kind=="numeric_input" else "4", DotNum="0", LeadingZero="0",
                GainValue="1.0", OffsetValue="0.000000", Roundoff="0", HiWordFirst="0")
            common.update(UnitType="0", UnitSrc="0", UnitSrcVar="None", UnitDisplay="0", UnitDisplayVar="None",
                UnitPercent="0", UnitPercent1Var="0.0", UnitPercent2Var="100.0", UnitCustom1Var_1="1.0",
                UnitCustom2Var_1="0.0", BackupUnitSrc="0", BackupUnitDisplay="0")
            if kind=="numeric_input":
                common.update(TriggerLink="1", TriggerVar="None", Order="0", MinValue="0", MaxValue="100",
                    Variation="0", SetLowSecurity="0", InterLockLink="1", InterLockVar="None", InterLockLevel="1",
                    InterLockViewMode="0", DispAsterisk="0", Active="0", KeyPadLeft="0", KeyPadTop="0",
                    KeyPadRight="0", KeyPadBottom="0", TitleHeight="0", NoMessage="0", ShowOverRange="1",
                    UseCustKeypad="0", KeypadScreenID="0")
        _equals(s, common)
        for key,m in (("X",800),("Y",480),("Width",800),("Height",480)):
            _source_integer(s, key, 1 if key in ("Width","Height") else 0, m)
        expected_states = 2 if kind in ("momentary", "maintained") else 1
        if len(owner["states"]) != expected_states:
            _fail("Donor state count differs from its observed variant")
        for value, state in enumerate(owner["states"]):
            _shape(state, _STATE_KEYS)
            _equals(state, dict(Value=str(value), TransEffect="1" if kind=="momentary" else "0",
                StretchMode="2" if kind=="momentary" else "0", PictureStretch="1" if kind=="momentary" else "0"))

    def _operations(self, operations):
        self.check()
        _bounded(operations)
        if type(operations) is not list or len(operations) > 4:
            _fail("Append operations require a list of at most four new controls")
        seen, result = set(), []
        for op in operations:
            if type(op) is not dict or set(op) != _OP_KEYS or op.get("op") != "append_control":
                _fail("Only the exact append_control operation is admitted")
            if op["screen_id"] != "20" or not isinstance(op["donor_kind"], str) or op["donor_kind"] not in DONOR_IDS:
                _fail("Append must use the original target page and one observed donor kind")
            eid = _identity(op["element_id"], "element_id")
            if eid not in {"97", "98", "99", "100"} or eid in seen:
                _fail("New control identity is unqualified or repeated")
            seen.add(eid)
            for field,m in (("x",800),("y",480),("width",800),("height",480)):
                _integer(op[field], field, 1 if field in ("width","height") else 0, m)
            if op["x"] + op["width"] > 800 or op["y"] + op["height"] > 480:
                _fail("New control geometry extends beyond the original target page")
            captions = op["captions"]
            count = 2 if op["donor_kind"] in ("momentary", "maintained") else 0
            if type(captions) is not list or len(captions) != count:
                _fail("Only button primary state captions may be configured")
            for value, caption in enumerate(captions):
                if (type(caption) is not dict or set(caption) != {"value", "text"}
                        or type(caption.get("value")) is not int or caption["value"] != value
                        or not isinstance(caption.get("text"), str) or "\0" in caption["text"]
                        or len(caption["text"]) > 1024):
                    _fail("Primary button captions require exact ordered state 0/1 text")
                try:
                    caption["text"].encode("utf-16-le", "strict")
                except UnicodeEncodeError as exc:
                    raise HmiError("UNQUALIFIED_DIA_CONTROL_APPEND", "Caption contains an invalid Unicode surrogate") from exc
            result.append(deepcopy(op))
        return result

    def _cloned_sections(self, op):
        owner = self._donors[op["donor_kind"]]
        sections = deepcopy(self.source.document.sections[owner["start"]:owner["end"]])
        for key, value in {"nPartsID":op["element_id"], "X":op["x"], "Y":op["y"],
                "Width":op["width"], "Height":op["height"]}.items():
            sections[0].one(key).set_value(str(value).encode("ascii"))
        for caption, state in zip(op["captions"], sections[1:]):
            state.one("wTextLen0").set_text(caption["text"])
        return sections

    def _expected_clone(self, op):
        """Independent raw-record splice: never invoke setters or clone mutator."""
        owner = self._donors[op["donor_kind"]]
        source_parts = self.source.document.sections[owner["start"]:owner["end"]]
        values = {"nPartsID":op["element_id"], "X":str(op["x"]), "Y":str(op["y"]),
            "Width":str(op["width"]), "Height":str(op["height"])}
        parts = []
        for index, section in enumerate(source_parts):
            parts.append(section.header)
            for record in section.records:
                if index == 0 and record.key in values:
                    value = values[record.key].encode("ascii")
                    parts.append(record.raw if record.value == value else record.key.encode() + b"=" + value + b"\r\n")
                elif index > 0 and op["captions"] and record.key == "wTextLen0":
                    text = op["captions"][index-1]["text"]
                    if record.text() == text:
                        parts.append(record.raw)
                    else:
                        blob = text.encode("utf-16-le") + b"\0\0"
                        parts.append(b"wTextLen0=" + str(len(blob)).encode() + b"\r\n" + blob + b"\r\n")
                else:
                    parts.append(record.raw)
        return b"".join(parts)

    def _expected(self, operations):
        page = next(p for p in self._pages if p["id"] == "20")
        offset = sum(len(s.bytes()) for s in self.source.document.sections[:page["end"]])
        insertion = b"".join(self._expected_clone(op) for op in operations)
        body = self.source.envelope.body[:offset] + insertion + self.source.envelope.body[offset:]
        if len(body) + 41 > MAX_PAYLOAD:
            _fail("Appended native body exceeds its bounded payload")
        return body

    def expected_body(self, operations):
        operations = self._operations(operations)
        body = self._expected(operations)
        self._last_operations = deepcopy(operations)
        return body

    def apply(self, operations):
        operations = self._operations(operations)
        if not operations:
            self._last_operations = []
            return self.source.original
        document = deepcopy(self.source.document)
        page = next(p for p in _groups(document) if p["id"] == "20")
        new_sections = [section for op in operations for section in self._cloned_sections(op)]
        document.sections[page["end"]:page["end"]] = new_sections
        body = document.bytes()
        if body != self._expected(operations):
            _fail("Document emitter disagrees with independent original-record oracle")
        raw = self.source.envelope.encode(body)
        self.verify(raw, operations)
        self._last_operations = deepcopy(operations)
        return raw

    def verify(self, candidate, operations=None):
        operations = self._operations(self._last_operations if operations is None else operations)
        if isinstance(candidate, bytes):
            candidate = NativeAdapter(candidate, FAMILY)
        if not isinstance(candidate, NativeAdapter) or candidate.family != FAMILY:
            _fail("Candidate must be a coherent DIAScreen native file")
        candidate._preserved_byte_binding("UNQUALIFIED_DIA_CONTROL_APPEND")
        expected = self._expected(operations)
        if (candidate.envelope.body != expected or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.declared_body_length() != len(expected)
                or candidate.document.tail != self.source.document.tail
                or candidate.model_id != MODEL or candidate.editor_version != VERSION):
            _fail("Candidate differs from the complete controlled append/source-retention oracle")
        if not operations and candidate.original != self.source.original:
            _fail("Empty append must preserve every original file byte")
        pages = _groups(candidate.document)
        if [p["id"] for p in pages] != [p["id"] for p in self._pages]:
            _fail("Candidate changed the original page graph")
        new_ids = [op["element_id"] for op in operations]
        for before, after in zip(self._pages, pages):
            original_ids = [e["id"] for e in before["elements"]]
            if [e["id"] for e in after["elements"]] != original_ids + (new_ids if before["id"]=="20" else []):
                _fail("Candidate reordered or changed original/new owner identities")
            _screen_extent(candidate.document, after)
        # Independent whole-body restoration removes exactly new owner extents.
        target = next(p for p in pages if p["id"] == "20")
        omitted = {i for e in target["elements"] if e["id"] in new_ids for i in range(e["start"],e["end"])}
        restored = b"".join(s.bytes() for i,s in enumerate(candidate.document.sections) if i not in omitted) + candidate.document.tail
        if restored != self.source.envelope.body:
            _fail("Removing only new extents does not restore the original native body")
        return True
