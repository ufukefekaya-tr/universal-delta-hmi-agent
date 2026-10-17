"""Wholly original synthetic format tests; these are not vendor fixtures."""
from copy import deepcopy
import gzip
import hashlib
import random
import struct
import unittest
from unittest.mock import patch

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, canonical_model_id, model_ids_match
from universal_hmi.native.codec import Envelope
from universal_hmi.native.records import Document
from universal_hmi.native.macros import MacroLine, MacroProgram, MARKER, EMPTY_LINE
from universal_hmi.native.numeric import verify_numeric_fields
from universal_hmi.native.macro_semantics import DESCRIPTORS, macro_record
from universal_hmi.native.resources import ResourceTables


def _wide(key, text):
    blob = text.encode("utf-16-le") + b"\0\0"
    return key.encode() + b"=" + str(len(blob)).encode() + b"\r\n" + blob + b"\r\n"


def synthetic_file(family="delta_diascreen", model_id="SYNTHETIC", editor_version="0.0"):
    header = bytearray(54)
    header[:2] = b"BM"
    header[6:10] = b"PDAB" if family == "delta_diascreen" else b"\0" * 4
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<I", header, 34, 4)
    body = (b"[Application]\r\nModelName=" + model_id.encode() + b"\r\nVersion=" + editor_version.encode()
            + b"\r\nPanelName=Original synthetic fixture\r\nUnknown=untouched\r\nSysKeyPwd=8\r\nA\r\n[B]\x00!\r\n"
            + b"[Screen]\r\nVER=16\r\nID=1\r\n" + _wide("wTextLen", "Main")
            + b"DocSizeX=100\r\nDocSizeY=80\r\nPanelSizeX=100\r\nPanelSizeY=80\r\n"
            + b"[AuxKeyElement]\r\n[Element]\r\nnPartsID=1\r\nType=1\r\nSubType=1\r\n"
            + b"X=10\r\nY=20\r\nWidth=30\r\nHeight=20\r\nReadVar=!D1\r\nReadLink=1\r\nReadMemType=0\r\n"
            + b"WriteVar=!M1\r\nWriteLink=1\r\nWriteMemType=0\r\nUnknownBinary=\xff\x00\x82\r\n"
            + b"BeforeExecMacroLen=4\r\nxx\r\n"
            + b"[State]\r\nValue=0\r\nFontColor=0\r\n" + _wide("wTextLen0", "OFF")
            + b"[State]\r\nValue=1\r\nFontColor=1\r\n" + _wide("wTextLen0", "ON")
            + b"[SubMacro]\r\nOpaque resources\x00\r\n[Screen]\r\nThis is opaque, never a screen\r\n")
    return Envelope(bytes(header) + b"PIXL", bytes(range(41)), b"").encode(body)


def synthetic_profile(family="delta_diascreen"):
    return {"family": family, "model_id": "SYNTHETIC", "editor_version": "0.0",
            "native_schema": {"qualified": True, "cloning": True,
                              "properties": {key.lower(): {"field": key, "type": "int", "min": 0, "max": 100}
                                             for key in ("X", "Y", "Width", "Height")}
                              | {"behavior": {"field": "SubType", "type": "enum", "values": {"momentary": 1, "maintained": 2}},
                                 "color": {"field": "FontColor", "scope": "state", "type": "int", "min": 0, "max": 0xFFFFFF}},
                              "bindings": {direction: {"field": native + "Var", "link_field": native + "Link",
                                                       "mem_type_field": native + "MemType"}
                                           for direction, native in (("read", "Read"), ("write", "Write"))}}}


def numeric_fixture(data_type="UINT", kind="numeric_input", family="delta_diascreen"):
    """Invented payload with observed field names; never a vendor fixture."""
    representations = {"INT": ("1", "1"), "UINT": ("1", "2"), "DINT": ("2", "1"),
                       "UDINT": ("2", "2"), "REAL": ("2", "5"), "LREAL": ("7", "8")}
    # LREAL enums are deliberately fictitious to test exact 64-bit contracts.
    mem_len, mem_fmt = representations[data_type]
    source = synthetic_file(family)
    envelope = Envelope.decode(source, family)
    properties = (f"MemLen={mem_len}\r\nMemFmt={mem_fmt}\r\nIntNum=5\r\nDotNum=0\r\n"
                  "GainValue=1.0\r\nOffsetValue=0.000000\r\nHiddenNumericSetting=retained\r\n").encode()
    if kind == "numeric_input":
        properties += b"MinValue=0\r\nMaxValue=100\r\n"
    body = envelope.body.replace(b"Type=1\r\nSubType=1\r\n", (b"Type=6\r\n" if kind == "numeric_input" else b"Type=5\r\n")
                                 + b"SubType=1\r\n" + properties, 1)
    return envelope.encode(body)


def numeric_profile(family="delta_diascreen"):
    profile = synthetic_profile(family)
    profile["native_schema"]["numeric"] = {
        "qualified": True,
        "kinds": {"numeric_input": {"Type": "6", "SubType": "1"},
                  "numeric_display": {"Type": "5", "SubType": "1"}},
        "types": {"INT": {"MemLen": "1", "MemFmt": "1", "bits": 16, "format": "signed"},
                  "UINT": {"MemLen": "1", "MemFmt": "2", "bits": 16, "format": "unsigned"},
                  "DINT": {"MemLen": "2", "MemFmt": "1", "bits": 32, "format": "signed"},
                  "UDINT": {"MemLen": "2", "MemFmt": "2", "bits": 32, "format": "unsigned"},
                  "REAL": {"MemLen": "2", "MemFmt": "5", "bits": 32, "format": "floating"},
                  "LREAL": {"MemLen": "7", "MemFmt": "8", "bits": 64, "format": "floating"}},
    }
    return profile


def unit_fixture(family="delta_diascreen", text="mm", enabled="1"):
    """Original unit-caption bytes; installed vendor assets are never copied."""
    source = numeric_fixture(family=family)
    envelope = Envelope.decode(source, family)
    companions = (b"UnitType=0\r\nUnitSrc=0\r\nUnitSrcVar=None\r\nUnitDisplay=0\r\nUnitDisplayVar=None\r\n"
                  b"UnitPercent=0\r\nUnitPercent1Var=0.0\r\nUnitPercent2Var=100.0\r\n"
                  b"UnitCustom1Var_1=1.0\r\nUnitCustom2Var_1=0.0\r\nBackupUnitSrc=0\r\n"
                  b"BackupUnitDisplay=0\r\nConvertConstByUnit=0\r\nShowUnit=" + enabled.encode()
                  + b"\r\nUnitDirection=0\r\nUnitFontSize0=14\r\nUnitFontName0=Arial\r\n"
                  + _wide("UnitTextLen0", text)
                  + b"UnitBold=1\r\nUnitItalic=0\r\nUnitUnderline=0\r\nUnitFontColor=4473924\r\n")
    return envelope.encode(envelope.body.replace(b"HiddenNumericSetting=retained\r\n",
                                                b"HiddenNumericSetting=retained\r\n" + companions, 1))


def unit_profile(family="delta_diascreen"):
    profile = numeric_profile(family)
    profile["native_schema"]["unit_caption"] = {
        "qualified": True, "owner": "Element", "field": "UnitTextLen0",
        "kinds": deepcopy(profile["native_schema"]["numeric"]["kinds"])}
    return profile


def layout_fixture(family="delta_diascreen"):
    """Independent byte-assembled page/owner blocks, never vendor data."""
    envelope = Envelope.decode(synthetic_file(family), family)
    prefix, rest = envelope.body.split(b"[Screen]\r\n", 1)
    page, tail = (b"[Screen]\r\n" + rest).split(b"[SubMacro]\r\n", 1)
    page_prefix, element = page.split(b"[Element]\r\n", 1)
    element = b"[Element]\r\n" + element
    pages = []
    for page_id in ("1", "2", "3"):
        header = page_prefix.replace(b"ID=1\r\n", b"ID=" + page_id.encode() + b"\r\n", 1)
        header = header.replace(_wide("wTextLen", "Main"), _wide("wTextLen", "Page " + page_id))
        blocks = [element.replace(b"nPartsID=1\r\n", b"nPartsID=" + identity.encode() + b"\r\n", 1)
                  .replace(b"ReadVar=!D1\r\n", b"ReadVar=!D" + page_id.encode() + identity.encode() + b"\r\n", 1)
                  for identity in ("1", "2", "3")]
        pages.append(header + b"".join(blocks))
    return envelope.encode(prefix + b"".join(pages) + b"[SubMacro]\r\n" + tail)


def layout_profile(family="delta_diascreen"):
    profile = synthetic_profile(family)
    profile["native_schema"]["structure"] = {
        "qualified": True, "rename_screen": {"field": "wTextLen"},
        "reorder_elements": {"ordering": "section-sequence", "extent": "element-and-states"},
        "reorder_screens": {"ordering": "section-sequence", "extent": "screen-and-elements"}}
    return profile


def preserved_layout_fixture(family="delta_dopsoft2", model_id="SYNTHETIC", editor_version="0.0"):
    """Original retained-prefix/Order data; values qualify no vendor semantics."""
    envelope = Envelope.decode(layout_fixture(family), family)
    application, pages = envelope.body.split(b"[Screen]\r\n", 1)
    application = application.replace(b"ModelName=SYNTHETIC\r\n", b"ModelName=" + model_id.encode() + b"\r\n", 1)
    application = application.replace(b"Version=0.0\r\n", b"Version=" + editor_version.encode() + b"\r\n", 1) + b"\r\n\r\n\r\n"
    prefix = b""
    for name in ("Multi-Language", "Global-Keypad", "Recipe", "Recipe32", "EnhanceRcp", "Ethernet", "SIP",
                 "RemoteCtrl", "VNCCtrl", "RTC", "VideoList", "LOG", "FTP", "FTPFile"):
        prefix += b"[" + name.encode() + b"]\r\nNeutralField=A\r\nNeutralField=B\r\n"
        if name == "Global-Keypad":
            prefix += b"InitialMacroLen=4\r\nxx\r\n"
        elif name == "Recipe":
            prefix += b"RcpLen=5\r\nRcpGroup=1\r\n[Screen]\r\n\r\n"
        elif name == "Recipe32":
            prefix += b"Rcp32Len=1\r\nRcp32Group=1\r\nSYNT\r\n"
    pages = b"[Screen]\r\n" + pages
    pages = pages.replace(b"ID=1\r\n", b"ID=1\r\nOrder=0\r\nOriginalPageField=kept\r\n", 1)
    pages = pages.replace(b"nPartsID=1\r\nType=1", b"nPartsID=1\r\nOrder=0\r\nType=1")
    pages = pages.replace(b"[State]\r\nValue=0\r\n", b"[State]\r\nValue=0\r\nOrder=0007\r\n", 1)
    source = envelope.encode(application + prefix + pages)
    profile = synthetic_profile(family)
    profile.update(model_id=model_id, editor_version=editor_version)
    profile["native_schema"]["properties"]["order"] = {"field": "Order", "type": "int", "min": 0, "max": 100}
    return source, qualify_preserved_layout(source, profile)


def qualify_preserved_layout(source, profile):
    """Pin exact original synthetic bytes, including deliberately bad fixtures."""
    profile = deepcopy(profile)
    adapter = NativeAdapter(source, profile["family"])
    first_screen = next(index for index, section in enumerate(adapter.document.sections) if section.name == "Screen")
    sections = adapter.document.sections[:first_screen]
    raw = b"".join(section.bytes() for section in sections)
    profile["native_schema"]["preserved_layout"] = {
        "qualified": True, "contract_version": 1, "mode": "existing_owner_edits",
        "source_sha256": hashlib.sha256(source).hexdigest(), "prefix_sha256": hashlib.sha256(raw).hexdigest(),
        "sections": [{"name": section.name, "sha256": hashlib.sha256(section.bytes()).hexdigest()} for section in sections]}
    return profile


def literal_generation_fixture(family="delta_dopsoft2", model_id="SYNTHETIC", editor_version="0.0"):
    """Original byte-built rich header/literal, never vendor qualification."""
    envelope = Envelope.decode(synthetic_file(family, model_id, editor_version), family)
    prefix = (b"[Application]\r\nModelName=" + model_id.encode() + b"\r\nVersion=" + editor_version.encode()
              + b"\r\nPanelName=Neutral literal source\r\nPanelSeries="
              + (b"DOP-B series" if family == "delta_dopsoft2" else b"DOP-100 series") + b"\r\n\r\n\r\n\r\n")
    for name in ("Multi-Language", "Global-Keypad", "Recipe", "Recipe32", "EnhanceRcp", "Ethernet", "SIP",
                 "RemoteCtrl", "VNCCtrl", "RTC", "VideoList", "LOG", "FTP", "FTPFile"):
        prefix += b"[" + name.encode() + b"]\r\nNeutralRetained=A\r\nNeutralRetained=B\r\n"
    header = (b"[Screen]\r\nVER=16\r\nID=1\r\n" + _wide("wTextLen", "Original")
              + b"DocSizeX=100\r\nDocSizeY=80\r\nPanelSizeX=100\r\nPanelSizeY=80\r\n"
              + b"IsSubScreen=0\r\nIsKeypadScreen=0\r\nIsUseFrame=1\r\nIsUseTitleBar=1\r\nIsScreenRotate=0\r\n"
              + _wide("wTitleTextLen000", "") + b"TitleTextFontName000=Arial\r\nTitleTextFontSize000=12\r\nTitleTextFontColor=16777215\r\n"
              + _wide("wScreenDESCTextLen000", "Source")
              + b"RefreshRate=2\r\nIsPrintScreen=0\r\nHardCopyLeft=0\r\nHardCopyTop=0\r\nHardCopyRight=99\r\nHardCopyBottom=79\r\n"
              + b"BaseScreenID=0\r\nScreenAction=0\r\nBgColor=16579836\r\nHidden=0\r\nCycleMacroDelayTime=100\r\n"
              + b"ScreenLockVar=None\r\nOpenMacroLen=0\r\nCloseMacroLen=0\r\nCycleMacroLen=0\r\n[AuxKeyElement]\r\n")
    literal = (b"[Element]\r\nType=10\r\nSubType=6\r\nX=10\r\nY=10\r\nWidth=30\r\nHeight=20\r\n"
               + b"GroupID=0\r\nStyle=0\r\nBorderColor=11842740\r\nPrintSuccessiveData=0\r\n"
               + b"ReadMemType=0\r\nWriteMemType=0\r\nReadLink=1\r\nWriteLink=1\r\nReadVar=None\r\nWriteVar=None\r\n"
               + b"MemLen=1\r\nMemFmt=2\r\nLevel=0\r\nOffsetReadMemType=0\r\nOffsetWriteMemType=0\r\n"
               + b"OffsetReadVar=None\r\nOffsetWriteVar=None\r\nOffsetMemLen=1\r\nOffsetMemFmt=2\r\n"
               + b"nAngle=0\r\nbFreeze=0\r\nnPartsID=1\r\n" + _wide("wDescTextLen", "")
               + b"SmoothFont=1\r\nVisibleLink=1\r\nVisibleVar=None\r\nPosVary=0\r\n"
               + b"[State]\r\nValue=0\r\nFgColor=16579836\r\nBgColor=11842740\r\nFontColor=0\r\n"
               + b"FontSize0=28\r\nFontRatio0=100\r\nFontName0=Arial\r\n" + _wide("wTextLen0", "SOURCE")
               + b"FontAlign=34\r\nFontBold=0\r\nFontItalic=0\r\nFontUnderline=0\r\nUsePictureCoord=0\r\n"
               + b"PictureAlign=34\r\nTransEffect=0\r\nTransColor=0\r\nStretchMode=0\r\nPictureStretch=0\r\nTwinkles=0\r\nSoundIndex=0\r\n")
    retained = (b"[Element]\r\nnPartsID=2\r\nType=6\r\nSubType=1\r\nX=50\r\nY=10\r\nWidth=30\r\nHeight=20\r\nOrder=0\r\n"
                + b"ReadVar=!D1\r\nWriteVar=!D1\r\nReadLink=1\r\nWriteLink=1\r\nReadMemType=0\r\nWriteMemType=0\r\n"
                + b"[State]\r\nValue=0\r\n" + _wide("wTextLen0", "123") + b"[SubMacro]\r\nOpaqueNeutralTail\x00\r\n")
    source = envelope.encode(prefix + header + literal + retained)
    profile = synthetic_profile(family)
    profile.update(model_id=model_id, editor_version=editor_version)
    profile["native_schema"]["properties"] = {
        key: {"field": field, "type": "int", "min": 0 if key in {"x", "y"} else 1, "max": 100}
        for key, field in (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height"))}
    return source, qualify_literal_generation(source, profile)


def qualify_literal_generation(source, profile, page_id="1", text_page="1", text_id="1"):
    """Pin original fixture bytes, including deliberately invalid variants."""
    profile = deepcopy(profile)
    adapter = NativeAdapter(source, profile["family"])
    first_screen = next(index for index, section in enumerate(adapter.document.sections) if section.name == "Screen")
    sections = adapter.document.sections[:first_screen]
    prefix = b"".join(section.bytes() for section in sections)
    page = next(section for section in adapter.document.sections if section.name == "Screen" and section.one("ID").value.decode() == page_id)
    aux = adapter.document.sections[adapter.document.sections.index(page) + 1]
    profile["native_schema"]["literal_generation"] = {
        "qualified": True, "contract_version": 1, "mode": "literal_page_generation",
        "source_sha256": hashlib.sha256(source).hexdigest(), "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
        "sections": [{"name": section.name, "sha256": hashlib.sha256(section.bytes()).hexdigest()} for section in sections],
        "page_donor": {"screen_id": page_id, "header_sha256": hashlib.sha256(page.bytes()).hexdigest(), "aux_sha256": hashlib.sha256(aux.bytes()).hexdigest()},
        "text_donor": {"screen_id": text_page, "element_id": text_id, "owner_sha256": adapter.owner_extent_sha256(text_page, text_id)}}
    return profile


def control_generation_fixture(family="delta_dopsoft2"):
    """Original constructed shape adversary, never a copied vendor fixture."""
    from universal_hmi.native.__init__ import (_CONTROL_COMMON, _CONTROL_BUTTON, _CONTROL_INPUT,
                                             _CONTROL_DISPLAY, _LITERAL_STATE_FIELDS)
    raw, profile = literal_generation_fixture(family)
    adapter = NativeAdapter(raw, family)
    page_start = next(i for i, section in enumerate(adapter.document.sections) if section.name == "Screen")
    prefix = b"".join(section.bytes() for section in adapter.document.sections[:page_start])
    page = adapter.document.sections[page_start]
    header = page.bytes() + b"[AuxKeyElement]\r\n"
    owners = []
    for identity, kind in enumerate(("set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display"), 1):
        numeric = kind.startswith("numeric_")
        fields = set(_CONTROL_COMMON)
        if numeric:
            fields |= _CONTROL_INPUT if kind == "numeric_input" else _CONTROL_DISPLAY
        else:
            fields |= _CONTROL_BUTTON | ({"ButtonOnMacroLen"} if identity == 1 else {"ButtonOffMacroLen"} if identity == 2 else {"ButtonOnMacroLen", "ButtonOffMacroLen"})
            if identity == 3:
                fields.add("OffVoice")
        values = {key: "0" for key in fields}
        values.update(Type="6" if kind == "numeric_input" else "5" if kind == "numeric_display" else "1",
                      SubType="1" if numeric else str(identity), X="10", Y="10", Width="30", Height="20",
                      nPartsID=str(identity), Style="1" if kind == "numeric_input" else "2" if kind == "numeric_display" else "0",
                      BorderColor="11842740", ReadLink="1", WriteLink="1", MemLen="1" if numeric else "0", MemFmt="2",
                      OffsetMemLen="1", OffsetMemFmt="2", ReadVar="{Link2}1@D0" if kind == "numeric_display" else "None",
                      WriteVar="{Link2}1@D0" if kind == "numeric_input" else "{Link2}1@M0" if identity == 1 else "None",
                      OffsetReadVar="None", OffsetWriteVar="None", VisibleVar="None", VisibleLink="1")
        if kind != "numeric_display":
            values.update(InterLockVar="None", InterLockLink="1", InterLockLevel="1")
        if numeric:
            values.update(IntNum="4", DotNum="0", GainValue="1.0", OffsetValue="0.000000")
        if kind == "numeric_input":
            values.update(TriggerVar="None", TriggerLink="1", MinValue="0", MaxValue="9999", ShowOverRange="1")
        body = b"[Element]\r\n"
        for key in sorted(fields):
            if key.startswith("w"):
                body += _wide(key, "")
            else:
                value = "Arial" if key.startswith("KPFontName") else values[key]
                body += key.encode() + b"=" + value.encode() + b"\r\n"
        for index in range(1 if numeric else 2):
            state = {key: "0" for key in _LITERAL_STATE_FIELDS}
            state.update(Value=str(index), FontSize0="12", FontRatio0="100", FontName0="Arial", FontAlign="34", PictureAlign="34",
                         FgColor="11842740", BgColor="11842740")
            body += b"[State]\r\n"
            for key in sorted(_LITERAL_STATE_FIELDS):
                body += _wide(key, "1234" if numeric else "") if key == "wTextLen0" else key.encode() + b"=" + state[key].encode() + b"\r\n"
        owners.append(body)
    body = prefix + header + b"".join(owners) + adapter.document.tail
    prefix_bytes = adapter.envelope.prefix[:37] + bytes(value ^ 0x64 for value in len(body).to_bytes(4, "little"))
    raw = Envelope(adapter.envelope.thumbnail, prefix_bytes, body).encode(body)
    schema = profile["native_schema"]
    schema.pop("literal_generation")
    schema["bindings"] = {direction: {"field": direction.title() + "Var", "link_field": direction.title() + "Link", "mem_type_field": direction.title() + "MemType"}
                          for direction in ("read", "write")}
    schema["numeric"] = {"qualified": True, "kinds": {"numeric_input": {"Type": "6", "SubType": "1"}, "numeric_display": {"Type": "5", "SubType": "1"}},
                         "types": {"UINT": {"MemLen": "1", "MemFmt": "2", "bits": 16, "format": "unsigned"}},
                         "max_integer_digits": 5, "max_fractional_digits": 0}
    schema["properties"] |= {key: {"field": field, "scope": "state", "type": "int", "min": 1 if key == "font_size" else 0,
                                  "max": 128 if key == "font_size" else 0xFFFFFF}
                              for key, field in (("color", "FontColor"), ("fill", "BgColor"), ("state_fill", "BgColor"), ("font_size", "FontSize0"))}
    return raw, qualify_control_generation(raw, profile)


def qualify_control_generation(raw, profile):
    """Explicit synthetic property witnesses for guard tests only."""
    from universal_hmi.native.__init__ import _groups
    profile = deepcopy(profile)
    adapter = NativeAdapter(raw, profile["family"])
    prefix, sections = adapter._preserved_prefix(adapter.document)
    pages = _groups(adapter.document)
    kinds = ("set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display")
    profile["native_schema"]["control_generation"] = {
        "qualified": True, "contract_version": 1, "mode": "control_generation", "source_sha256": hashlib.sha256(raw).hexdigest(),
        "prefix_sha256": hashlib.sha256(prefix).hexdigest(), "sections": sections, "address_prefix": "{Link2}1@",
        "pages": [{"screen_id": page["id"], "header_sha256": hashlib.sha256(page["section"].bytes()).hexdigest(),
                   "aux_sha256": hashlib.sha256(adapter._plain_extent(page).bytes()).hexdigest()} for page in pages],
        "donors": {kind: {"screen_id": "1", "element_id": str(index), "owner_sha256": adapter.owner_extent_sha256("1", str(index)),
                          "match": {"Type": adapter.document.sections[owner["start"]].one("Type").value.decode(),
                                    "SubType": adapter.document.sections[owner["start"]].one("SubType").value.decode()},
                          "property_witness_sha256": hashlib.sha256(("SYNTHETIC PROPERTY " + kind).encode()).hexdigest()}
                   for index, (kind, owner) in enumerate(zip(kinds, pages[0]["elements"]), 1)}}
    return profile


def macro_fixture(family="delta_diascreen"):
    """Original neutral source-local donors; not vendor qualification data."""
    def line(op, source, arguments, width=0, signed=0):
        inactive = tuple(("Var" + str(index)).encode() for index in range(len(arguments) + 1, 5))
        return MacroLine(bytes.fromhex(DESCRIPTORS[op]), (source.encode(),) + tuple(value.encode() for value in arguments)
                         + inactive, b"\x01\x01\x01\x01" + struct.pack("<II", width, signed))
    donors = (
        line("assign", "$1 = 1", ("$1", "1")),
        line("assign", "$20 = 1 (DW)", ("$20", "1"), 1),
        line("assign", "$22 = -1 (Signed DW)", ("$22", "-1"), 1, 1),
        line("add", "$2 = $2 + 1", ("$2", "$2", "1")),
        line("bit_on", "BITON $3.0", ("$3.0",)),
        line("bit_off", "BITOFF $3.0", ("$3.0",)),
        line("if", "IF $1 == 1", ("$1", "1")),
        line("assign", "$1 = 1", ("$1", "1")),
        line("else", "ELSE", ()),
        line("assign", "$1 = 2", ("$1", "2")),
        line("endif", "ENDIF", ()),
    )
    payload = MacroProgram(donors).bytes()
    source = synthetic_file(family)
    envelope = Envelope.decode(source, family)
    body = envelope.body.replace(b"Unknown=untouched\r\n", b"Unknown=untouched\r\nInitialMacroLen=" + str(len(payload)).encode()
                                 + b"\r\n" + payload + b"ClockMacroLen=0\r\nBackgroundMacroLen=0\r\n"
                                 + b"ClockMacroDelayTime=100\r\nClockMacroPriority=0\r\nLineBrkBackgndMacro=1\r\n", 1)
    body = body.replace(b"BeforeExecMacroLen=4\r\nxx\r\n", b"BeforeExecMacroLen=0\r\nAfterExecMacroLen=0\r\n", 1)
    body = body.replace(b"ID=1\r\n", b"ID=1\r\nOpenMacroLen=0\r\nCloseMacroLen=0\r\nCycleMacroLen=0\r\n"
                         + b"CycleMacroDelayTime=100\r\nEnableCycleMacro=0\r\n", 1)
    return envelope.encode(body)


def macro_profile(family="delta_diascreen", source=None):
    source = macro_fixture(family) if source is None else source
    adapter = NativeAdapter(source, family)
    record = adapter.document.sections[0].one("InitialMacroLen")
    program = MacroProgram.parse(record.blob)
    descriptors = {value: key for key, value in DESCRIPTORS.items()}
    values, seen = [], set()
    for index, line in enumerate(program.lines):
        if line.descriptor == EMPTY_LINE:
            continue
        op = descriptors[line.descriptor.hex()]
        width, signed = struct.unpack("<II", line.flags[4:])
        datatype = ("CONTROL" if op in {"else", "endif"} else "BOOL" if op in {"bit_on", "bit_off"}
                    else {(0, 0): "UINT", (1, 0): "UDINT", (1, 1): "DINT"}[(width, signed)])
        if (op, datatype) in seen:
            continue
        seen.add((op, datatype))
        values.append({"op": op, "datatype": datatype, "descriptor_hex": line.descriptor.hex(), "flags_hex": line.flags.hex(),
                       "donor": {"owner": {"kind": "application"}, "field": "InitialMacroLen",
                                 "program_sha256": hashlib.sha256(record.blob).hexdigest(), "line_index": index,
                                 "line_sha256": hashlib.sha256(line.bytes()).hexdigest()}})
    profile = synthetic_profile(family)
    profile["native_schema"]["macros"] = {"qualified": True, "address_bounds": {"minimum": 0, "maximum": 1000},
                                          "templates": values}
    return profile


def _fixture_macro(source, owner, field, payload, family="delta_diascreen"):
    """Test fixture creation only; there is no public arbitrary-blob mutation."""
    envelope = Envelope.decode(source, family)
    document = Document.parse(envelope.body)
    record = macro_record(document, owner, field)
    record.blob = payload
    record.set_value(str(len(payload)).encode(), force=True)
    return envelope.encode(document.bytes())


def resource_native_fixture(family="delta_diascreen"):
    source = macro_fixture(family)
    adapter = NativeAdapter(source, family)
    tail = b"[SubMacro]\r\nMacroCount=0\r\n[Global_Auxkey]\r\n[Alarm]\r\nVersion=16\r\nAlarmCount=8\r\nContinueAddr=0\r\nReadAlarmLink=1\r\n"
    for index in ("001", "002"):
        tail += (f"AlarmEnable{index}=1\r\nAlarmVar{index}=$10\r\nAlarmMemLen{index}=2\r\nAlarmTriggerFmt{index}=2\r\n"
                 f"AlarmTriggerIntNum{index}=5\r\nAlarmTriggerDotNum{index}=0\r\nAlarmTriggerCount{index}=1\r\n"
                 f"AlarmTriggerOperator{index}-001=3\r\nAlarmTriggerMin{index}-001=0\r\nAlarmTriggerMax{index}-001=10\r\n").encode()
        tail += _wide("wMessageLen" + index + "-0", "Neutral fault " + index)
    tail += b"[History]\r\nHistoryCount=0\r\n[END]\r\n"
    body = b"".join(section.bytes() for section in adapter.document.sections) + tail
    return adapter.envelope.encode(body)


def resource_native_profile(family="delta_diascreen", source=None):
    source = resource_native_fixture(family) if source is None else source
    table = ResourceTables.parse(NativeAdapter(source, family).document.tail)
    controls = ("ContinueAddr", "ReadAlarmLink", "AlarmVar001", "AlarmMemLen001", "AlarmTriggerFmt001",
                "AlarmTriggerIntNum001", "AlarmTriggerDotNum001", "AlarmTriggerCount001", "AlarmEnable001",
                "AlarmTriggerOperator001-001")
    profile = macro_profile(family, source)
    profile["native_schema"]["alarm"] = {
        "qualified": True, "version": "16", "donor_tail_sha256": hashlib.sha256(table.original).hexdigest(),
        "suffix_sha256": hashlib.sha256(table.suffix).hexdigest(),
        "fields": {"AlarmEnable001": {"kind": "enum", "values": ["0", "1"],
                                       "preconditions": {key: table.alarm.one(key).value.decode() for key in controls}},
                   "wMessageLen002-0": {"kind": "text", "max_bytes": 128, "preconditions": {"AlarmEnable002": "1"}}}}
    return profile


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.source = synthetic_file()
        self.adapter = NativeAdapter(self.source, "delta_diascreen")
        self.profile = synthetic_profile()

    def apply(self, operations, profile=None):
        return self.adapter.apply(operations, self.profile if profile is None else profile)

    def inspect_output(self, output):
        return NativeAdapter(output, "delta_diascreen").inspect()

    def property(self, key="x", value=11):
        return {"op": "set_property", "screen_id": "1", "element_id": "1", "key": key, "value": value}

    def text(self, text="Çalışıyor – İğdır\r\nÖlçüm 🔧", state=0, language=0):
        return {"op": "set_text", "screen_id": "1", "element_id": "1", "state_index": state,
                "language": language, "text": text}

    def test_inspection_identity_and_opaque_suffix(self):
        result = self.adapter.inspect()
        self.assertEqual(result["model_id"], "SYNTHETIC")
        self.assertEqual(result["editor_version"], "0.0")
        self.assertEqual(result["qualification"], "UNVERIFIED")
        self.assertEqual([s["id"] for s in result["screens"]], ["1"])
        element = result["screens"][0]["elements"][0]
        self.assertEqual(element["id"], "1")
        self.assertEqual(element["bindings"]["read"]["address"], "!D1")
        self.assertEqual(element["texts"][1]["text"], "ON")
        frames = result["framed_records"]
        macro = next(item for item in frames if item["kind"] == "macro")
        self.assertEqual((macro["screen_id"], macro["element_id"], macro["field"], macro["byte_count"]),
                         ("1", "1", "BeforeExecMacroLen", 4))
        self.assertEqual(macro["sha256"], hashlib.sha256(b"xx\r\n").hexdigest())
        self.assertEqual(result["opaque_tail"], {"byte_count": len(self.adapter.document.tail),
                                                "sha256": hashlib.sha256(self.adapter.document.tail).hexdigest(),
                                                "parsed": False})

    def test_state_values_are_not_inferred_from_section_positions(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        swapped = envelope.body.replace(b"[State]\r\nValue=0", b"[State]\r\nValue=1", 1)
        swapped = swapped.replace(b"[State]\r\nValue=1\r\nFontColor=1", b"[State]\r\nValue=0\r\nFontColor=1", 1)
        result = NativeAdapter(envelope.encode(swapped), "delta_diascreen").inspect()
        states = result["screens"][0]["elements"][0]["states"]
        self.assertEqual([(s["state_index"], s["value"]) for s in states], [(0, 1), (1, 0)])
        self.assertEqual(states[0]["native_fields"]["Value"], "1")
        self.assertEqual(result["screens"][0]["elements"][0]["texts"][0]["text"], "OFF")

    def test_both_family_envelopes_noop_bytes(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                original = synthetic_file(family)
                self.assertEqual(NativeAdapter(original, family).apply([], {}), original)

    def test_noop_values_preserve_original_compression(self):
        self.assertEqual(self.apply([self.property(value=10), self.text("OFF")]), self.source)

    def test_equal_length_replacement_is_not_noop(self):
        output = self.apply([self.text("RUN")])
        self.assertEqual(self.inspect_output(output)["screens"][0]["elements"][0]["texts"][0]["text"], "RUN")
        self.assertNotEqual(output, self.source)

    def test_turkish_unicode_and_embedded_crlf(self):
        text = "Çalışıyor\r\n[Screen]\r\nİğdır ğöşü – 🔧"
        result = self.inspect_output(self.apply([self.text(text)]))
        self.assertEqual(result["screens"][0]["elements"][0]["texts"][0]["text"], text)
        self.assertEqual(len(result["screens"]), 1)

    def test_all_unknown_bytes_and_thumbnail_preserved(self):
        output = self.apply([self.property()])
        before = Envelope.decode(self.source, "delta_diascreen")
        after = Envelope.decode(output, "delta_diascreen")
        self.assertEqual(before.thumbnail, after.thumbnail)
        self.assertEqual(before.prefix, after.prefix)
        self.assertEqual(before.body.replace(b"X=10\r\n", b"X=11\r\n"), after.body)

    def test_exact_bind_does_not_replace_substrings(self):
        operation = {"op": "bind", "screen_id": "1", "element_id": "1",
                     "read": {"address": "!D12", "link": 2, "mem_type": 1}}
        output = self.apply([operation])
        result = self.inspect_output(output)["screens"][0]["elements"][0]
        self.assertEqual(result["bindings"]["read"], {"address": "!D12", "link": "2", "mem_type": "1"})
        self.assertEqual(result["bindings"]["write"]["address"], "!M1")
        self.assertEqual(self.adapter.inspect()["screens"][0]["elements"][0]["bindings"]["read"]["address"], "!D1")

    def test_bind_metadata_required_and_unknown_rejected(self):
        for binding in ("!D3", {"address": "!D3"}, {"address": "!D3", "link": 1, "mem_type": 0, "bad": 1},
                        {"address": "!D3\r\n[Screen]", "link": 1, "mem_type": 0},
                        {"address": "!D3", "link": True, "mem_type": 0}):
            with self.subTest(binding=binding), self.assertRaises(HmiError):
                self.apply([{"op": "bind", "screen_id": "1", "element_id": "1", "read": binding}])

    def test_address_string_for_explicit_address_only_profile(self):
        profile = deepcopy(self.profile)
        profile["native_schema"]["bindings"]["read"] = {"field": "ReadVar"}
        output = self.apply([{"op": "bind", "screen_id": "1", "element_id": "1", "read": "!D9"}], profile)
        self.assertEqual(self.inspect_output(output)["screens"][0]["elements"][0]["bindings"]["read"]["address"], "!D9")

    def test_profile_requires_exact_target_and_qualification(self):
        for changes in ({"family": "delta_dopsoft2"}, {"model_id": "OTHER"}, {"editor_version": "1.0"},
                        {"native_schema": {"qualified": False}}, {"native_schema": {"qualified": 1}}):
            profile = self.profile | changes
            with self.subTest(changes=changes), self.assertRaises(HmiError):
                self.apply([self.property()], profile)

    def test_native_bounds_override_permissive_profile(self):
        profile = deepcopy(self.profile)
        profile["native_schema"]["properties"]["x"].update(min=-99999, max=99999)
        for value in (-1, 71, 100000000, True, "11", 1.1):
            with self.subTest(value=value), self.assertRaises(HmiError):
                self.apply([self.property(value=value)], profile)
        with self.assertRaises(HmiError):
            self.apply([self.property("width", 0)])

    def test_unknown_fields_enum_and_unsupported_features_fail(self):
        for op in (self.property("X"), self.property("behavior", "invented"),
                   {"op": "create_alarm"}, {"op": "create_macro"}, {"op": "nonsense"}):
            with self.subTest(op=op), self.assertRaises(HmiError):
                self.apply([op])
        profile = deepcopy(self.profile)
        profile["native_schema"]["properties"]["alien"] = {"field": "UnseenVendorKey", "type": "int"}
        with self.assertRaises(HmiError):
            self.apply([self.property("alien", 0)], profile)

    def test_malformed_arguments_fail_with_explicit_error(self):
        for operations in (None, {}, [None], [{"op": []}], [self.property() | {"unexpected": 1}]):
            with self.subTest(operations=operations), self.assertRaises(HmiError):
                self.apply(operations)
        for key in ("properties", "bindings"):
            profile = deepcopy(self.profile)
            profile["native_schema"][key] = []
            with self.subTest(key=key), self.assertRaises(HmiError):
                self.apply([self.property()], profile)

    def test_enum_and_state_scoped_property(self):
        output = self.apply([self.property("behavior", "maintained"), self.property("color", 123)])
        self.assertEqual(self.inspect_output(output)["screens"][0]["elements"][0]["subtype"], "2")
        self.assertIn(b"FontColor=123\r\n", Envelope.decode(output, "delta_diascreen").body)

    def test_negative_indices_missing_state_and_language(self):
        for operation in (self.text(state=-1), self.text(state=True), self.text(state=2),
                          self.text(language=-1), self.text(language=1), self.text("bad\0value"), self.text("\ud800")):
            with self.subTest(operation=operation), self.assertRaises(HmiError):
                self.apply([operation])

    def test_clone_element_and_screen_preserve_contents(self):
        output = self.apply([{"op": "clone_element", "source_screen": "1", "source_element": "1",
                              "target_screen": "1", "element_id": "2"},
                             {"op": "clone_screen", "source_screen": "1", "screen_id": "2", "name": "İkinci"}])
        result = self.inspect_output(output)
        self.assertEqual([s["id"] for s in result["screens"]], ["1", "2"])
        self.assertEqual(result["screens"][1]["name"], "İkinci")
        self.assertEqual([e["id"] for e in result["screens"][1]["elements"]], ["1", "2"])
        self.assertEqual(result["screens"][1]["elements"][1]["texts"], result["screens"][0]["elements"][0]["texts"])

    def test_layout_rename_changes_only_owned_wide_record_and_noop_is_byte_exact(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            source = layout_fixture(family)
            adapter = NativeAdapter(source, family)
            profile = layout_profile(family)
            operation = {"op": "rename_screen", "screen_id": "2", "name": "Page 2"}
            self.assertEqual(adapter.apply([operation], profile), source)
            operation["name"] = "İkinci ölçüm 🔧"
            output = adapter.apply([operation], profile)
            before, after = adapter.envelope, Envelope.decode(output, family)
            self.assertEqual(after.body, before.body.replace(_wide("wTextLen", "Page 2"), _wide("wTextLen", operation["name"]), 1))
            self.assertEqual((before.prefix, before.thumbnail), (after.prefix, after.thumbnail))
            self.assertEqual(adapter.document.tail, NativeAdapter(output, family).document.tail)
            self.assertEqual(adapter.apply([], {}), source)

    def test_layout_exact_permutations_move_complete_owner_blocks_with_macros_and_states(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            source = layout_fixture(family)
            adapter = NativeAdapter(source, family)
            source_sections = adapter.document.sections
            page_blocks = [source_sections[index:index + 11] for index in (1, 12, 23)]
            self.assertEqual([block[0].one("ID").value for block in page_blocks], [b"1", b"2", b"3"])
            # Each block is Screen + Aux + 3 complete Element/State/State owners.
            page_one = page_blocks[0]
            reordered_one = page_one[:2] + page_one[8:11] + page_one[2:5] + page_one[5:8]
            expected = source_sections[:1] + page_blocks[2] + reordered_one + page_blocks[1]
            operations = [{"op": "reorder_elements", "screen_id": "1", "element_ids": ["3", "1", "2"]},
                          {"op": "reorder_screens", "screen_ids": ["3", "1", "2"]}]
            output = adapter.apply(operations, layout_profile(family))
            actual = NativeAdapter(output, family)
            self.assertEqual(actual.document.bytes(), b"".join(section.bytes() for section in expected) + adapter.document.tail)
            self.assertEqual(actual.envelope.prefix, adapter.envelope.prefix)
            self.assertEqual(actual.envelope.thumbnail, adapter.envelope.thumbnail)
            self.assertEqual([page["id"] for page in actual.inspect()["screens"]], ["3", "1", "2"])
            self.assertEqual([element["id"] for element in actual.inspect()["screens"][1]["elements"]], ["3", "1", "2"])
            self.assertEqual(adapter.apply([], {}), source)
            self.assertEqual(actual.apply(operations, layout_profile(family)), output)

    def test_layout_identity_order_and_reverse_roundtrip_preserve_original_body(self):
        source = layout_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        profile = layout_profile()
        identity = [{"op": "reorder_elements", "screen_id": "1", "element_ids": ["1", "2", "3"]},
                    {"op": "reorder_screens", "screen_ids": ["1", "2", "3"]}]
        self.assertEqual(adapter.apply(identity, profile), source)
        reverse = [{"op": "reorder_elements", "screen_id": "1", "element_ids": ["3", "2", "1"]},
                   {"op": "reorder_screens", "screen_ids": ["3", "2", "1"]}]
        changed = NativeAdapter(adapter.apply(reverse, profile), "delta_diascreen")
        restored = NativeAdapter(changed.apply(identity, profile), "delta_diascreen")
        self.assertEqual(restored.envelope.body, adapter.envelope.body)
        empty = self.adapter.apply([{"op": "delete_element", "screen_id": "1", "element_id": "1"}], self.profile)
        self.assertEqual(NativeAdapter(empty, "delta_diascreen").apply(
            [{"op": "reorder_elements", "screen_id": "1", "element_ids": []}], profile), empty)

    def test_layout_rejects_partial_duplicate_unknown_noncanonical_and_wrong_type_orders(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        for order in (None, "123", {}, ("1", "2", "3"), ["1", "2"], ["1", "1", "2"],
                      ["1", "2", "4"], ["01", "2", "3"], [1, "2", "3"], [True, "2", "3"],
                      [[], "2", "3"], ["9" * 5000, "2", "3"]):
            for name, key in (("reorder_elements", "element_ids"), ("reorder_screens", "screen_ids")):
                operation = {"op": name, key: order}
                if name == "reorder_elements":
                    operation["screen_id"] = "1"
                with self.subTest(name=name, order_kind=type(order).__name__), self.assertRaises(HmiError):
                    adapter.apply([self.property(), operation], layout_profile())
                self.assertEqual(adapter.apply([], {}), adapter.original)

    def test_layout_requires_exact_structural_qualification_and_preserves_unknown_boundaries(self):
        source = layout_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        operations = [{"op": "rename_screen", "screen_id": "1", "name": "New"},
                      {"op": "reorder_elements", "screen_id": "1", "element_ids": ["1", "2", "3"]},
                      {"op": "reorder_screens", "screen_ids": ["1", "2", "3"]}]
        for operation in operations:
            for structure in (None, [], {}, {"qualified": 1}, {"qualified": True, operation["op"]: {"field": "ID"}}):
                profile = layout_profile()
                profile["native_schema"]["structure"] = structure
                with self.subTest(operation=operation["op"], structure_kind=type(structure).__name__), self.assertRaises(HmiError):
                    adapter.apply([operation], profile)
        envelope = adapter.envelope
        for extra in (b"[UnknownOwner]\r\nUnknown=retained\r\n", b"[AuxKeyElement]\r\n",
                      b"[AuxKeyElement]\r\nUnknown=retained\r\n"):
            body = envelope.body.replace(b"[SubMacro]\r\n", extra + b"[SubMacro]\r\n", 1)
            altered = NativeAdapter(envelope.encode(body), "delta_diascreen")
            # Screen 3's tail cannot be moved or even certified as a no-op.
            for operation in (operations[2], {"op": "reorder_elements", "screen_id": "3", "element_ids": ["1", "2", "3"]}):
                with self.subTest(extra=extra, operation=operation["op"]), self.assertRaises(HmiError) as error:
                    altered.apply([operation], layout_profile())
                self.assertEqual(error.exception.code, "UNQUALIFIED_STRUCTURE")
                self.assertEqual(altered.apply([], {}), altered.original)
        body = envelope.body.replace(b"[Screen]\r\n", b"[UnknownPrefix]\r\nA=retained\r\n[Screen]\r\n", 1)
        with self.assertRaises(HmiError) as error:
            NativeAdapter(envelope.encode(body), "delta_diascreen").apply([operations[2]], layout_profile())
        self.assertEqual(error.exception.code, "UNQUALIFIED_STRUCTURE")

    def test_layout_competing_native_order_rejects_instead_of_assuming_layer_semantics(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        for token in (b"ID=1\r\n", b"nPartsID=1\r\n", b"Value=0\r\n"):
            body = adapter.envelope.body.replace(token, token + b"Order=7\r\n", 1)
            altered = NativeAdapter(adapter.envelope.encode(body), "delta_diascreen")
            operation = ({"op": "reorder_screens", "screen_ids": ["3", "2", "1"]} if token == b"ID=1\r\n"
                         else {"op": "reorder_elements", "screen_id": "1", "element_ids": ["3", "2", "1"]})
            with self.subTest(token=token), self.assertRaises(HmiError) as error:
                altered.apply([operation], layout_profile())
            self.assertEqual(error.exception.code, "UNQUALIFIED_LAYER")
            self.assertEqual(altered.apply([], {}), altered.original)

    def test_layout_rename_and_goto_update_qualified_companion_together(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        body = adapter.envelope.body.replace(b"Type=1\r\nSubType=1\r\n", b"Type=1\r\nSubType=10\r\nGoToScreenID=2\r\nGoToScreenName=Page 2\r\n", 1)
        adapter = NativeAdapter(adapter.envelope.encode(body), "delta_diascreen")
        profile = layout_profile()
        profile["native_schema"]["navigation"] = {"qualified": True, "match": {"Type": "1", "SubType": "10"},
                                                    "field": "GoToScreenID", "name_field": "GoToScreenName", "name_encoding": "ascii"}
        rename = {"op": "rename_screen", "screen_id": "2", "name": "Page 2"}
        self.assertEqual(adapter.apply([rename], profile), adapter.original)
        rename["name"] = "Second"
        output = adapter.apply([rename], profile)
        expected = body.replace(_wide("wTextLen", "Page 2"), _wide("wTextLen", "Second"), 1)
        expected = expected.replace(b"GoToScreenName=Page 2\r\n", b"GoToScreenName=Second\r\n", 1)
        self.assertEqual(Envelope.decode(output, "delta_diascreen").body, expected)
        candidate = NativeAdapter(output, "delta_diascreen")
        goto = {"op": "configure_goto", "screen_id": "1", "element_id": "1", "target_screen": "3"}
        moved = candidate.apply([goto], profile)
        expected = expected.replace(b"GoToScreenID=2\r\nGoToScreenName=Second\r\n", b"GoToScreenID=3\r\nGoToScreenName=Page 3\r\n", 1)
        self.assertEqual(Envelope.decode(moved, "delta_diascreen").body, expected)
        self.assertEqual(NativeAdapter(moved, "delta_diascreen").apply([goto], profile), moved)

    def test_layout_navigation_companion_missing_calibration_mismatch_and_unknown_refs_reject(self):
        original = NativeAdapter(layout_fixture(), "delta_diascreen")
        body = original.envelope.body.replace(b"Type=1\r\nSubType=1\r\n", b"Type=1\r\nSubType=10\r\nGoToScreenID=2\r\nGoToScreenName=Page 2\r\n", 1)
        profile = layout_profile()
        profile["native_schema"]["navigation"] = {"qualified": True, "match": {"Type": "1", "SubType": "10"},
                                                    "field": "GoToScreenID", "name_field": "GoToScreenName", "name_encoding": "ascii"}
        rename = {"op": "rename_screen", "screen_id": "2", "name": "New"}
        goto = {"op": "configure_goto", "screen_id": "1", "element_id": "1", "target_screen": "3"}
        mutations = (body.replace(b"GoToScreenName=Page 2", b"GoToScreenName=Wrong"),
                     body.replace(b"GoToScreenID=2\r\n", b"GoToScreenID=02\r\n"),
                     body.replace(b"GoToScreenID=2\r\n", b"OtherScreenID=2\r\n"),
                     body.replace(b"SubType=10\r\n", b"SubType=1\r\n", 1))
        for changed in mutations:
            adapter = NativeAdapter(original.envelope.encode(changed), "delta_diascreen")
            with self.subTest(changed=hashlib.sha256(changed).hexdigest()), self.assertRaises(HmiError):
                adapter.apply([rename], profile)
            self.assertEqual(adapter.apply([], {}), adapter.original)
        adapter = NativeAdapter(original.envelope.encode(body), "delta_diascreen")
        for mapping in ({}, {"name_field": "GoToScreenName"}, {"name_field": "Other", "name_encoding": "ascii"},
                        {"name_field": "GoToScreenName", "name_encoding": "utf-8"}):
            changed = deepcopy(profile)
            changed["native_schema"]["navigation"].pop("name_field")
            changed["native_schema"]["navigation"].pop("name_encoding")
            changed["native_schema"]["navigation"].update(mapping)
            for operation in (rename, goto):
                with self.subTest(mapping=mapping, operation=operation["op"]), self.assertRaises(HmiError):
                    adapter.apply([operation], changed)
        with self.assertRaises(HmiError):
            adapter.apply([rename | {"name": "Ölçüm"}], profile)
        # Reference-like fields in other owners and case aliases are equally
        # unqualified; only inspecting known GoTo objects would miss them.
        for token, reference in ((b"Unknown=untouched\r\n", b"StartScreenName=Page 2\r\n"),
                                 (b"ID=1\r\n", b"OtherScreenID=2\r\n"),
                                 (b"Value=0\r\n", b"GoToScreenName=Page 2\r\n"),
                                 (b"nPartsID=2\r\n", b"gotoscreenname=Page 2\r\n")):
            changed = body.replace(token, token + reference, 1)
            altered = NativeAdapter(original.envelope.encode(changed), "delta_diascreen")
            with self.subTest(reference=reference), self.assertRaises(HmiError) as error:
                altered.apply([rename], profile)
            self.assertEqual(error.exception.code, "UNQUALIFIED_NAVIGATION")
            self.assertEqual(altered.apply([], {}), altered.original)

    def test_plain_page_baseline_excludes_only_identity_name_and_defined_object_bytes(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            source = layout_fixture(family)
            adapter = NativeAdapter(source, family)
            signature = adapter.page_baseline("1")
            self.assertRegex(signature, r"^[0-9a-f]{64}$")
            self.assertEqual([adapter.page_baseline(identity) for identity in ("1", "2", "3")], [signature] * 3)
            self.assertTrue(adapter.verify_layout_order())
            changed = adapter.apply([{"op": "rename_screen", "screen_id": "1", "name": "Ölçüm"}, self.property()], layout_profile(family))
            candidate = NativeAdapter(changed, family)
            self.assertEqual(candidate.page_baseline("1"), signature)
            self.assertEqual(candidate.page_baseline("3"), signature)
            body = adapter.envelope.body.replace(b"DocSizeX=100\r\n", b"DocSizeX=99\r\n", 1)
            self.assertNotEqual(NativeAdapter(adapter.envelope.encode(body), family).page_baseline("1"), signature)
            self.assertEqual(adapter.apply([], {}), source)

    def test_plain_page_baseline_rejects_inherited_locks_backgrounds_and_unknown_records(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        for extra in (b"BaseScreenID=1\r\nScreenLockVar=!M1\r\n", b"BgColor=0\r\n", b"Order=0\r\n",
                      b"OpenMacroLen=0\r\n", b"Unknown=retained\r\n", b"unkeyed retained record\r\n",
                      b"VER=16\r\n", _wide("wUnexpectedLen", "Background")):
            body = adapter.envelope.body.replace(b"ID=1\r\n", b"ID=1\r\n" + extra, 1)
            source = adapter.envelope.encode(body)
            candidate = NativeAdapter(source, "delta_diascreen")
            with self.subTest(extra=extra[:40]), self.assertRaises(HmiError):
                candidate.page_baseline("1")
            self.assertEqual(candidate.apply([], {}), source)
            self.assertEqual(candidate.document.bytes(), body)
        # The baseline excludes name/ID from the signature, but those fields
        # must still exist and have an unambiguous, valid native encoding.
        for old, new in ((b"VER=16\r\n", b"VER=17\r\n"), (b"VER=16\r\n", b""),
                         (b"DocSizeX=100\r\n", b"DocSizeX=0\r\n"),
                         (b"PanelSizeX=100\r\n", b"PanelSizeX=0100\r\n"),
                         (_wide("wTextLen", "Page 1"), b"wTextLen=0\r\n")):
            source = adapter.envelope.encode(adapter.envelope.body.replace(old, new, 1))
            candidate = NativeAdapter(source, "delta_diascreen")
            with self.subTest(old=old[:30]), self.assertRaises(HmiError):
                candidate.page_baseline("1")
            self.assertEqual(candidate.apply([], {}), source)

    def test_plain_page_baseline_and_layout_guard_require_complete_auxiliary_and_owner_extents(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        for old, new in ((b"[AuxKeyElement]\r\n", b""),
                         (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nPopulated=1\r\n"),
                         (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\n[AuxKeyElement]\r\n"),
                         (b"[State]\r\nValue=1", b"[UnknownOwner]\r\nRetained=1\r\n[State]\r\nValue=1")):
            source = adapter.envelope.encode(adapter.envelope.body.replace(old, new, 1))
            candidate = NativeAdapter(source, "delta_diascreen")
            for action in (lambda: candidate.page_baseline("1"), candidate.verify_layout_order):
                with self.subTest(old=old, check=action), self.assertRaises(HmiError) as error:
                    action()
                self.assertEqual(error.exception.code, "UNQUALIFIED_STRUCTURE")
            self.assertEqual(candidate.apply([], {}), source)

    def test_layout_guard_rejects_order_even_for_zero_append_only_and_noop_pages(self):
        adapter = NativeAdapter(layout_fixture(), "delta_diascreen")
        for token in (b"ID=1\r\n", b"nPartsID=1\r\n", b"Value=0\r\n"):
            for value in ("0", "1"):
                body = adapter.envelope.body.replace(token, token + f"Order={value}\r\n".encode(), 1)
                source = adapter.envelope.encode(body)
                candidate = NativeAdapter(source, "delta_diascreen")
                with self.subTest(token=token, value=value), self.assertRaises(HmiError) as error:
                    candidate.verify_layout_order()
                self.assertEqual(error.exception.code, "UNQUALIFIED_LAYER")
                # An ordinary clone appends without reordering any owner. The
                # pure final guard still rejects its competing Order field.
                appended = candidate.apply([{"op": "clone_element", "source_screen": "1", "source_element": "2",
                                             "target_screen": "1", "element_id": "4"}], layout_profile())
                with self.assertRaises(HmiError) as error:
                    NativeAdapter(appended, "delta_diascreen").verify_layout_order()
                self.assertEqual(error.exception.code, "UNQUALIFIED_LAYER")
                self.assertEqual(candidate.apply([], {}), source)

    def test_plain_page_baseline_detects_saved_new_page_mutation_and_preserves_opaque_owner_bytes(self):
        source = layout_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        signature = adapter.page_baseline("1")
        cloned = adapter.apply([{"op": "clone_screen", "source_screen": "1", "screen_id": "4", "name": "New"}], layout_profile())
        candidate = NativeAdapter(cloned, "delta_diascreen")
        self.assertEqual(candidate.page_baseline("4"), signature)
        self.assertTrue(candidate.verify_layout_order())
        self.assertEqual(candidate.document.tail, adapter.document.tail)
        self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)
        self.assertIn(b"UnknownBinary=\xff\x00\x82\r\n", candidate.envelope.body)
        body = candidate.envelope.body.replace(b"ID=4\r\n", b"ID=4\r\nBaseScreenID=1\r\nScreenLockVar=!M1\r\n", 1)
        tampered = NativeAdapter(candidate.envelope.encode(body), "delta_diascreen")
        with self.assertRaises(HmiError) as error:
            tampered.page_baseline("4")
        self.assertEqual(error.exception.code, "UNQUALIFIED_PAGE_BASELINE")
        self.assertEqual(tampered.apply([], {}), tampered.original)

    def test_duplicate_clones_and_noncanonical_ids_rejected(self):
        for op in ({"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "1", "element_id": "1"},
                   {"op": "clone_screen", "source_screen": "1", "screen_id": "1", "name": "X"},
                   {"op": "clone_screen", "source_screen": "1", "screen_id": "-1", "name": "X"},
                   {"op": "clone_screen", "source_screen": "1", "screen_id": "02", "name": "X"}):
            with self.subTest(op=op), self.assertRaises(HmiError):
                self.apply([op])

    def test_delete_is_exact_and_transactional_failure_does_not_change_adapter(self):
        with self.assertRaises(HmiError):
            self.apply([self.property(), self.text(state=-1)])
        self.assertEqual(self.apply([]), self.source)
        self.assertEqual(self.adapter.inspect()["screens"][0]["elements"][0]["geometry"]["x"], 10)
        output = self.apply([{"op": "delete_element", "screen_id": "1", "element_id": "1"}])
        self.assertEqual(self.inspect_output(output)["screens"][0]["elements"], [])

    def test_structural_edits_reject_ambiguous_section_ownership_and_preserve_source(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        operations = ({"op": "delete_element", "screen_id": "1", "element_id": "1"},
                      {"op": "clone_element", "source_screen": "1", "source_element": "1",
                       "target_screen": "1", "element_id": "2"},
                      {"op": "clone_screen", "source_screen": "1", "screen_id": "2", "name": "Copy"})
        for extra in (b"[AuxKeyElement]\r\nUnknownScreenSetting=retained\r\n",
                      b"[AuxKeyElement]\r\n", b"[UncalibratedGlobal]\r\nUnknown=retained\r\n"):
            body = envelope.body.replace(b"[SubMacro]\r\n", extra + b"[SubMacro]\r\n", 1)
            source = envelope.encode(body)
            adapter = NativeAdapter(source, "delta_diascreen")
            for operation in operations:
                with self.subTest(extra=extra, operation=operation), self.assertRaises(HmiError) as context:
                    adapter.apply([self.property(), operation], self.profile)
                self.assertEqual(context.exception.code, "UNQUALIFIED_STRUCTURE")
                self.assertEqual(adapter.document.bytes(), body)
                self.assertEqual(adapter.apply([], {}), source)
            # Exact field edits still retain every unknown section byte.
            output = adapter.apply([self.property()], self.profile)
            self.assertEqual(Envelope.decode(output, "delta_diascreen").body,
                             body.replace(b"X=10\r\n", b"X=11\r\n", 1))

    def test_structural_insertions_reject_unknown_target_or_global_boundaries(self):
        source = self.apply([{"op": "clone_screen", "source_screen": "1", "screen_id": "2", "name": "Two"}])
        envelope = Envelope.decode(source, "delta_diascreen")
        body = envelope.body.replace(b"[SubMacro]\r\n", b"[UncalibratedGlobal]\r\nUnknown=retained\r\n[SubMacro]\r\n", 1)
        adapter = NativeAdapter(envelope.encode(body), "delta_diascreen")
        for operation in ({"op": "clone_element", "source_screen": "1", "source_element": "1",
                           "target_screen": "2", "element_id": "2"},
                          {"op": "clone_screen", "source_screen": "1", "screen_id": "3", "name": "Three"}):
            with self.subTest(operation=operation), self.assertRaises(HmiError) as context:
                adapter.apply([operation], self.profile)
            self.assertEqual(context.exception.code, "UNQUALIFIED_STRUCTURE")
            self.assertEqual(adapter.document.bytes(), body)
        # An auxiliary section with unknown contents is not a calibrated clone.
        original = Envelope.decode(self.source, "delta_diascreen")
        prefixed = original.body.replace(b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnknown=retained\r\n", 1)
        adapter = NativeAdapter(original.encode(prefixed), "delta_diascreen")
        with self.assertRaises(HmiError) as context:
            adapter.apply([{"op": "clone_screen", "source_screen": "1", "screen_id": "2", "name": "Copy"}], self.profile)
        self.assertEqual(context.exception.code, "UNQUALIFIED_STRUCTURE")
        self.assertEqual(adapter.document.bytes(), prefixed)

    def test_native_integer_and_language_digit_limits_fail_with_explicit_errors(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        huge = b"9" * 5000
        cases = ((b"\r\nID=1\r\n", b"\r\nID=" + huge + b"\r\n", "INVALID_ID"),
                 (b"nPartsID=1\r\n", b"nPartsID=" + huge + b"\r\n", "INVALID_ID"),
                 (b"X=10\r\n", b"X=" + huge + b"\r\n", "NATIVE_LIMIT"),
                 (b"X=10\r\n", b"X=-" + huge + b"\r\n", "NATIVE_LIMIT"),
                 (b"Value=0\r\n", b"Value=" + huge + b"\r\n", "NATIVE_LIMIT"),
                 (b"wTextLen0=8\r\n", b"wTextLen" + huge + b"=8\r\n", "NATIVE_LIMIT"),
                 (b"X=10\r\n", b"X=1x\r\n", "NATIVE_INTEGER"))
        for old, new, code in cases:
            with self.subTest(field=new[:30]), self.assertRaises(HmiError) as context:
                NativeAdapter(envelope.encode(envelope.body.replace(old, new, 1)), "delta_diascreen").inspect()
            self.assertEqual(context.exception.code, code)
        # Inspection preserves complete 64-bit values; the digit limit is not
        # an implicit narrowing to 32-bit or a fallback to missing data.
        for value in (-(2 ** 63), 2 ** 64 - 1):
            body = envelope.body.replace(b"Value=0\r\n", b"Value=" + str(value).encode() + b"\r\n", 1)
            adapter = NativeAdapter(envelope.encode(body), "delta_diascreen")
            self.assertEqual(adapter.inspect()["screens"][0]["elements"][0]["states"][0]["value"], value)
            self.assertEqual(adapter.document.bytes(), body)

    def test_argument_and_profile_integer_rendering_is_bounded_before_conversion(self):
        for operation in (self.property() | {"screen_id": "9" * 5000},
                          self.property() | {"element_id": "9" * 5000}, self.property(value=10 ** 5000)):
            with self.subTest(operation_kind=operation["op"]), self.assertRaises(HmiError):
                self.apply([operation])
        for key in ("model_id", "editor_version"):
            profile = deepcopy(self.profile)
            profile["native_schema"][key] = 10 ** 5000
            with self.subTest(key=key), self.assertRaises(HmiError) as context:
                self.apply([self.property()], profile)
            self.assertEqual(context.exception.code, "INVALID_PROFILE")
        profile = self.profile | {"model_id": 10 ** 5000}
        with self.assertRaises(HmiError) as context:
            self.apply([self.property()], profile)
        self.assertEqual(context.exception.code, "INVALID_PROFILE")

    def test_duplicate_controlled_fields_fail_before_last_value_projection(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        pairs = ((b"Type=1\r\n", b"Type=999\r\nType=1\r\n"),
                 (b"SubType=1\r\n", b"SubType=999\r\nSubType=1\r\n"),
                 (b"ReadVar=!D1\r\n", b"ReadVar=!WRONG\r\nReadVar=!D1\r\n"),
                 (b"ReadLink=1\r\n", b"ReadLink=99\r\nReadLink=1\r\n"),
                 (b"ReadMemType=0\r\n", b"ReadMemType=99\r\nReadMemType=0\r\n"),
                 (b"WriteVar=!M1\r\n", b"WriteVar=!WRONG\r\nWriteVar=!M1\r\n"),
                 (b"FontColor=0\r\n", b"BgColor=0\r\nBgColor=123\r\nFontColor=0\r\n"),
                 (b"DocSizeX=100\r\n", b"DocSizeX=999\r\nDocSizeX=100\r\n"),
                 (b"PanelSizeY=80\r\n", b"PanelSizeY=999\r\nPanelSizeY=80\r\n"),
                 (_wide("wTextLen0", "OFF"), _wide("wTextLen0", "DIFFERENT") + _wide("wTextLen0", "OFF")),
                 (_wide("wTextLen", "Main"), _wide("wTextLen", "Different") + _wide("wTextLen", "Main")))
        for old, new in pairs:
            body = envelope.body.replace(old, new, 1)
            with self.subTest(field=new[:25]), self.assertRaises(HmiError) as context:
                NativeAdapter(envelope.encode(body), "delta_diascreen")
            self.assertEqual(context.exception.code, "AMBIGUOUS_FIELD")
            # The low-level lossless parser retains every byte for diagnosis.
            self.assertEqual(Document.parse(body).bytes(), body)

    def test_noncanonical_native_language_alias_is_rejected(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        for replacement in (_wide("wTextLen00", "OFF"),
                            _wide("wTextLen00", "DIFFERENT") + _wide("wTextLen0", "OFF")):
            body = envelope.body.replace(_wide("wTextLen0", "OFF"), replacement, 1)
            with self.subTest(replacement=replacement[:20]), self.assertRaises(HmiError) as context:
                NativeAdapter(envelope.encode(body), "delta_diascreen")
            self.assertEqual(context.exception.code, "NATIVE_TEXT")
            self.assertEqual(Document.parse(body).bytes(), body)

    def test_legitimate_opaque_repeated_fields_remain_lossless(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        body = envelope.body.replace(b"[Application]\r\n", b"[Application]\r\nSmtpPassword=first\r\nSmtpPassword=second\r\nCommAdvOpaque=1\r\nCommAdvOpaque=2\r\n", 1)
        body = body.replace(b"[Screen]\r\n", b"[Recipe32]\r\nRcp32IntNum=0\r\nRcp32IntNum=1\r\nRcp32Len=0\r\nRcp32Len=0\r\nRcp32Group=0\r\nRcp32Group=0\r\n[Screen]\r\n", 1)
        body = body.replace(b"[Element]\r\n", b"[Element]\r\nMemLen=1\r\nMemLen=2\r\nMemFmt=0\r\nMemFmt=1\r\nRowHoverColor=0\r\nRowHoverColor=1\r\n", 1)
        source = envelope.encode(body)
        adapter = NativeAdapter(source, "delta_diascreen")
        self.assertEqual(adapter.inspect()["screens"][0]["elements"][0]["id"], "1")
        self.assertEqual(adapter.document.bytes(), body)
        self.assertEqual(adapter.apply([], {}), source)
        changed = adapter.apply([self.property()], self.profile)
        self.assertEqual(Envelope.decode(changed, "delta_diascreen").body,
                         body.replace(b"X=10\r\n", b"X=11\r\n", 1))

    def test_compressed_checksum_trailing_and_truncated_header(self):
        bad = bytearray(self.source)
        bad[-8] ^= 1
        for data in (bytes(bad), self.source[:-5], self.source + b"trailing", self.source[:50], b"NO" + self.source[2:]):
            with self.subTest(size=len(data)), self.assertRaises(HmiError):
                NativeAdapter(data, "delta_diascreen")
        with self.assertRaises(HmiError):
            NativeAdapter(self.source, "delta_dopsoft2")

    def test_expansion_limit(self):
        with patch("universal_hmi.native.codec.MAX_PAYLOAD", 20), self.assertRaises(HmiError) as context:
            NativeAdapter(self.source, "delta_diascreen")
        self.assertEqual(context.exception.code, "NATIVE_LIMIT")

    def test_strict_binary_and_crlf_framing(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        bodies = (envelope.body.replace(b"wTextLen0=8", b"wTextLen0=7", 1),
                  envelope.body.replace(b"wTextLen0=8", b"wTextLen0=99999", 1),
                  envelope.body.replace(b"BeforeExecMacroLen=4", b"BeforeExecMacroLen=3"),
                  envelope.body.replace(b"X=10\r\n", b"X=10\n"),
                  envelope.body.replace(b"SysKeyPwd=8", b"SysKeyPwd=-1"))
        for body in bodies:
            with self.subTest(body_size=len(body)), self.assertRaises(HmiError):
                NativeAdapter(envelope.encode(body), "delta_diascreen")

    def test_inline_binary_frame_keeps_line_endings_and_fake_sections_opaque(self):
        envelope = Envelope.decode(self.source, "delta_diascreen")
        # Independently invented bytes exercise framing, not vendor content.
        blob = b"\n\r\n[Screen]\r\nID=99\r\nMeMeCode=\0\xff"
        frame = b"MeMeCode=" + struct.pack("<I", len(blob)) + blob + b"\r\n"
        body = envelope.body.replace(b"[Application]\r\n", b"[Application]\r\n" + frame, 1)
        source = envelope.encode(body)
        adapter = NativeAdapter(source, "delta_diascreen")
        self.assertEqual(adapter.document.bytes(), body)
        self.assertEqual(adapter.apply([], {}), source)
        self.assertEqual([s["id"] for s in adapter.inspect()["screens"]], ["1"])
        record = adapter.application.one("MeMeCode")
        self.assertEqual((record.kind, record.blob, record.value), ("inline_binary", blob, str(len(blob)).encode()))
        metadata = next(item for item in adapter.inspect()["framed_records"] if item["field"] == "MeMeCode")
        self.assertEqual((metadata["screen_id"], metadata["element_id"], metadata["byte_count"], metadata["sha256"]),
                         (None, None, len(blob), hashlib.sha256(blob).hexdigest()))
        with self.assertRaises(HmiError) as context:
            record.set_value(b"2")
        self.assertEqual(context.exception.code, "NATIVE_OPAQUE_FIELD")
        changed = adapter.apply([self.property()], self.profile)
        self.assertEqual(Envelope.decode(changed, "delta_diascreen").body,
                         body.replace(b"X=10\r\n", b"X=11\r\n", 1))

    def test_inline_binary_frame_requires_bounded_header_payload_and_terminator(self):
        prefix = b"[Application]\r\nMeMeCode="
        cases = ((b"", "NATIVE_FRAME"), (b"\x01\x00", "NATIVE_FRAME"),
                 (struct.pack("<I", 10) + b"abc\r\n", "NATIVE_FRAME"),
                 (struct.pack("<I", 1) + b"x\n", "NATIVE_FRAME"),
                 (struct.pack("<I", 1) + b"x\r", "NATIVE_FRAME"),
                 (struct.pack("<I", 0xFFFFFFFF), "NATIVE_LIMIT"))
        for suffix, code in cases:
            with self.subTest(suffix=suffix), self.assertRaises(HmiError) as context:
                Document.parse(prefix + suffix)
            self.assertEqual(context.exception.code, code)
        empty = prefix + struct.pack("<I", 0) + b"\r\nVersion=0.0\r\n"
        self.assertEqual(Document.parse(empty).bytes(), empty)
        # No general relaxation of CRLF or guessed framing for arbitrary keys.
        for body in (b"[Application]\r\nOtherCode=\x01\n\r\n",
                     b"[Screen]\r\nMeMeCode=" + struct.pack("<I", 1) + b"\n\r\n"):
            with self.subTest(body=body), self.assertRaises(HmiError) as context:
                Document.parse(body)
            self.assertEqual(context.exception.code, "NATIVE_CRLF")

    def test_direct_parser_size_record_and_decimal_limits_are_explicit(self):
        with patch("universal_hmi.native.records.MAX_PAYLOAD", 8), self.assertRaises(HmiError) as context:
            Document.parse(b"[Application]\r\n")
        self.assertEqual(context.exception.code, "NATIVE_LIMIT")
        with patch("universal_hmi.native.records.MAX_RECORDS", 2), self.assertRaises(HmiError) as context:
            Document.parse(b"[Application]\r\nA=1\r\nB=2\r\n")
        self.assertEqual(context.exception.code, "NATIVE_LIMIT")
        with self.assertRaises(HmiError) as context:
            Document.parse(b"[Application]\r\nSysKeyPwd=" + b"9" * 5000 + b"\r\n")
        self.assertEqual(context.exception.code, "NATIVE_LIMIT")
        leading_zero = b"[Application]\r\nSysKeyPwd=" + b"0" * 5000 + b"\r\n"
        self.assertEqual(Document.parse(leading_zero).bytes(), leading_zero)

    def test_repeated_original_synthetic_roundtrips(self):
        generator = random.Random(11)
        source = self.source
        for i in range(30):
            text = "ğÇİ🔧\r\n" + str(i) + " ş" * generator.randrange(15)
            source = NativeAdapter(source, "delta_diascreen").apply([self.text(text)], self.profile)
            self.assertEqual(self.inspect_output(source)["screens"][0]["elements"][0]["texts"][0]["text"], text)

    def numeric_operation(self, data_type="UINT", kind="numeric_input", **changes):
        operation = {"op": "configure_numeric", "screen_id": "1", "element_id": "1", "kind": kind,
                     "data_type": data_type, "integer_digits": 5, "fractional_digits": 0, "gain": 1, "offset": 0}
        if kind == "numeric_input":
            operation.update(minimum=0, maximum=100)
        return operation | changes

    def test_numeric_noop_and_exact_change_preserve_every_other_byte(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                source = numeric_fixture(family=family)
                adapter = NativeAdapter(source, family)
                self.assertEqual(adapter.apply([self.numeric_operation()], numeric_profile(family)), source)
                output = adapter.apply([self.numeric_operation(maximum=999, integer_digits=3)], numeric_profile(family))
                before, after = Envelope.decode(source, family), Envelope.decode(output, family)
                self.assertEqual(before.body.replace(b"MaxValue=100\r\n", b"MaxValue=999\r\n")
                                 .replace(b"IntNum=5\r\n", b"IntNum=3\r\n"), after.body)
                self.assertEqual((before.thumbnail, before.prefix), (after.thumbnail, after.prefix))
                fields = NativeAdapter(output, family).inspect()["screens"][0]["elements"][0]["native_fields"]
                self.assertEqual((fields["MemLen"], fields["MemFmt"], fields["MaxValue"]), ("1", "2", "999"))

    def test_numeric_signed_unsigned_and_float_limits_emit_without_narrowing(self):
        cases = (("INT", -32768, 32767, 5, 0), ("UINT", 0, 65535, 5, 1),
                 ("DINT", -2147483648, 2147483647, 10, 0), ("UDINT", 0, 4294967295, 10, 0),
                 ("REAL", "-9999.25", "9999.75", 4, 2),
                 ("LREAL", "-9007199254740993.125", "9007199254740993.25", 16, 3))
        for data_type, minimum, maximum, integer, fractional in cases:
            with self.subTest(data_type=data_type):
                source = numeric_fixture(data_type)
                output = NativeAdapter(source, "delta_diascreen").apply([
                    self.numeric_operation(data_type, minimum=minimum, maximum=maximum,
                                           integer_digits=integer, fractional_digits=fractional)], numeric_profile())
                fields = self.inspect_output(output)["screens"][0]["elements"][0]["native_fields"]
                self.assertEqual((fields["MinValue"], fields["MaxValue"]), (str(minimum), str(maximum)))
                self.assertEqual((fields["IntNum"], fields["DotNum"]), (str(integer), str(fractional)))

    def test_numeric_rejects_donor_reinterpretation_and_failed_transaction_is_immutable(self):
        source = numeric_fixture("UINT")
        adapter = NativeAdapter(source, "delta_diascreen")
        for data_type in ("INT", "UDINT", "REAL", "LREAL"):
            with self.subTest(data_type=data_type), self.assertRaises(HmiError) as context:
                adapter.apply([self.property(), self.numeric_operation(data_type)], numeric_profile())
            self.assertEqual(context.exception.code, "NUMERIC_DONOR_MISMATCH")
            self.assertEqual(adapter.apply([], {}), source)
        with self.assertRaises(HmiError) as context:
            adapter.apply([self.numeric_operation(kind="numeric_display")], numeric_profile())
        self.assertEqual(context.exception.code, "NUMERIC_DONOR_MISMATCH")

    def test_numeric_display_does_not_invent_input_limit_fields(self):
        source = numeric_fixture("REAL", "numeric_display")
        adapter = NativeAdapter(source, "delta_diascreen")
        operation = self.numeric_operation("REAL", "numeric_display", integer_digits=8, fractional_digits=3)
        output = adapter.apply([operation], numeric_profile())
        fields = self.inspect_output(output)["screens"][0]["elements"][0]["native_fields"]
        self.assertNotIn("MinValue", fields)
        self.assertEqual((fields["IntNum"], fields["DotNum"]), ("8", "3"))
        with self.assertRaises(HmiError) as context:
            adapter.apply([operation | {"maximum": 5}], numeric_profile())
        self.assertEqual(context.exception.code, "INVALID_NUMERIC")

    def test_numeric_schema_evidence_and_storage_width_are_required(self):
        adapter = NativeAdapter(numeric_fixture(), "delta_diascreen")
        for mutate in (lambda p: p["native_schema"]["numeric"].update(qualified=False),
                       lambda p: p["native_schema"]["numeric"]["types"]["UINT"].update(bits=32),
                       lambda p: p["native_schema"]["numeric"]["types"]["UINT"].update(format="floating"),
                       lambda p: p["native_schema"]["numeric"]["types"]["UINT"].update(MemLen="01"),
                       lambda p: p["native_schema"]["numeric"]["kinds"].update(numeric_input={"Type": "6"}),
                       lambda p: p["native_schema"]["numeric"].update(max_integer_digits=99)):
            profile = numeric_profile()
            mutate(profile)
            with self.subTest(profile=profile), self.assertRaises(HmiError):
                adapter.apply([self.numeric_operation()], profile)

    def test_numeric_invalid_limits_digits_scaling_and_types_fail_explicitly(self):
        adapter = NativeAdapter(numeric_fixture(), "delta_diascreen")
        changes = ({"minimum": -1}, {"maximum": 65536}, {"minimum": 101}, {"maximum": "1.2"},
                   {"integer_digits": 2}, {"integer_digits": True}, {"fractional_digits": -1},
                   {"gain": 2}, {"offset": 1}, {"maximum": float("inf")}, {"maximum": float("nan")},
                   {"maximum": "1\r\nType=1"}, {"maximum": "9" * 5000}, {"maximum": 10 ** 5000},
                   {"maximum": "1e999"}, {"maximum": "0x20"}, {"kind": []}, {"data_type": "TIME"},
                   {"data_type": []}, {"minimum": True})
        for change in changes:
            with self.subTest(change_kind=tuple(change)), self.assertRaises(HmiError):
                adapter.apply([self.numeric_operation(**change)], numeric_profile())
            self.assertEqual(adapter.apply([], {}), numeric_fixture())

    def test_numeric_duplicate_fields_are_controlled_only_on_numeric_kind(self):
        source = numeric_fixture()
        envelope = Envelope.decode(source, "delta_diascreen")
        for field in ("MemLen", "MemFmt", "MinValue", "MaxValue", "IntNum", "DotNum", "GainValue", "OffsetValue"):
            body = envelope.body.replace(b"X=10\r\n", (field + "=999\r\nX=10\r\n").encode(), 1)
            with self.subTest(field=field), self.assertRaises(HmiError) as context:
                NativeAdapter(envelope.encode(body), "delta_diascreen")
            self.assertEqual(context.exception.code, "AMBIGUOUS_FIELD")
        # Existing unrelated opaque duplicate records remain lossless.
        self.test_legitimate_opaque_repeated_fields_remain_lossless()

    def test_numeric_absent_fields_do_not_get_synthesized(self):
        source = numeric_fixture()
        envelope = Envelope.decode(source, "delta_diascreen")
        body = envelope.body.replace(b"GainValue=1.0\r\n", b"")
        adapter = NativeAdapter(envelope.encode(body), "delta_diascreen")
        with self.assertRaises(HmiError) as context:
            adapter.apply([self.numeric_operation()], numeric_profile())
        self.assertEqual(context.exception.code, "MISSING_NATIVE_FIELD")
        self.assertEqual(adapter.document.bytes(), body)

    def test_numeric_final_verification_checks_exact_storage_even_without_mutations(self):
        fields = NativeAdapter(numeric_fixture(), "delta_diascreen").inspect()["screens"][0]["elements"][0]["native_fields"]
        schema = numeric_profile()["native_schema"]
        operation = self.numeric_operation()
        self.assertTrue(verify_numeric_fields(fields, operation, schema))
        self.assertTrue(verify_numeric_fields(fields | {"GainValue": "1.000", "MaxValue": "100.0"}, operation, schema))
        for change in ({"MemLen": "1.0"}, {"MemFmt": "02"}, {"IntNum": "5.0"}, {"DotNum": "00"},
                       {"MaxValue": "101"}, {"GainValue": "2"}, {"Type": "5"}):
            with self.subTest(change=change), self.assertRaises(HmiError):
                verify_numeric_fields(fields | change, operation, schema)
        invalid_schema = deepcopy(schema)
        invalid_schema["numeric"]["types"]["UINT"]["bits"] = 32
        with self.assertRaises(HmiError) as context:
            verify_numeric_fields(fields, operation, invalid_schema)
        self.assertEqual(context.exception.code, "INVALID_SCHEMA")

    def test_numeric_ieee_underflow_rejects_nonzero_limits_but_preserves_subnormals(self):
        for data_type, maximum in (("REAL", "1e-100"), ("REAL", "1e-60"), ("LREAL", "1e-324")):
            adapter = NativeAdapter(numeric_fixture(data_type), "delta_diascreen")
            operation = self.numeric_operation(data_type, maximum=maximum, integer_digits=1)
            with self.subTest(data_type=data_type, maximum=maximum), self.assertRaises(HmiError) as context:
                adapter.apply([operation], numeric_profile())
            self.assertEqual(context.exception.code, "NUMERIC_LIMIT")
            fields = adapter.inspect()["screens"][0]["elements"][0]["native_fields"] | {"MaxValue": maximum, "IntNum": "1"}
            with self.assertRaises(HmiError) as context:
                verify_numeric_fields(fields, operation, numeric_profile()["native_schema"])
            self.assertEqual(context.exception.code, "NUMERIC_LIMIT")
        for data_type, maximum in (("REAL", "1e-40"), ("REAL", "0.1"), ("LREAL", "1e-100"), ("LREAL", "5e-324")):
            with self.subTest(data_type=data_type, maximum=maximum):
                source = numeric_fixture(data_type)
                operation = self.numeric_operation(data_type, maximum=maximum, integer_digits=1)
                output = NativeAdapter(source, "delta_diascreen").apply([operation], numeric_profile())
                adapter = NativeAdapter(output, "delta_diascreen")
                fields = adapter.inspect()["screens"][0]["elements"][0]["native_fields"]
                self.assertTrue(verify_numeric_fields(fields, operation, numeric_profile()["native_schema"]))
                self.assertEqual(adapter.apply([operation], numeric_profile()), output)
                # Emission retains the exact decimal limit; IEEE conversion is
                # used only for checking representability, never serialization.
                from decimal import Decimal
                self.assertEqual(Decimal(fields["MaxValue"]), Decimal(maximum))
                self.assertEqual(adapter.apply([], {}), output)

    def test_numeric_public_verification_rejects_malformed_arguments_explicitly(self):
        fields = NativeAdapter(numeric_fixture(), "delta_diascreen").inspect()["screens"][0]["elements"][0]["native_fields"]
        operation, schema = self.numeric_operation(), numeric_profile()["native_schema"]
        for values in ((None, operation, schema), (fields, None, schema), (fields, operation, None),
                       ([], operation, schema), (fields, [], schema), (fields, operation, [])):
            with self.subTest(types=tuple(type(value).__name__ for value in values)), self.assertRaises(HmiError):
                verify_numeric_fields(*values)

    def test_navigation_exact_donor_target_and_noop(self):
        source = self.apply([{"op": "clone_screen", "source_screen": "1", "screen_id": "2", "name": "Two"}])
        envelope = Envelope.decode(source, "delta_diascreen")
        body = envelope.body.replace(b"SubType=1\r\n", b"SubType=10\r\nGoToScreenID=1\r\n", 1)
        adapter = NativeAdapter(envelope.encode(body), "delta_diascreen")
        profile = deepcopy(self.profile)
        profile["native_schema"]["navigation"] = {"qualified": True, "match": {"Type": "1", "SubType": "10"},
                                                    "field": "GoToScreenID"}
        operation = {"op": "configure_goto", "screen_id": "1", "element_id": "1", "target_screen": "2"}
        output = adapter.apply([operation], profile)
        self.assertEqual(Envelope.decode(output, "delta_diascreen").body,
                         body.replace(b"GoToScreenID=1\r\n", b"GoToScreenID=2\r\n", 1))
        self.assertEqual(NativeAdapter(output, "delta_diascreen").apply([operation], profile), output)
        for changes in ({"target_screen": "9"}, {"target_screen": "02"}, {"element_id": "2"}):
            with self.subTest(changes=changes), self.assertRaises(HmiError):
                adapter.apply([operation | changes], profile)
        with self.assertRaises(HmiError) as context:
            adapter.apply([operation], self.profile)
        self.assertEqual(context.exception.code, "UNQUALIFIED_NAVIGATION")

    def test_macro_framing_roundtrip_opaque_source_operands_flags_and_blank_lines(self):
        lines = (MacroLine(b"\x01\x02\x03\x04", (b"Invented source \r\n[Screen]\0", b"", b"\xff\0x", b"1", b"2"), bytes(range(12))),
                 MacroLine(EMPTY_LINE),
                 MacroLine(b"\xff\xff\xff\xff", (b"not a qualified opcode", b"opaque", b"operand", b"bytes", b"!D1"), b"\xff" * 12))
        original = MacroProgram(lines).bytes()
        parsed = MacroProgram.parse(original)
        self.assertEqual(parsed.lines, lines)
        self.assertEqual(parsed.bytes(), original)
        report = parsed.inspect()
        self.assertEqual((report["format"], report["semantic_qualification"], report["line_count"], report["empty_line_count"]),
                         ("REV_FRAMING_ONLY", "UNVERIFIED", 3, 1))
        self.assertEqual(report["sha256"], hashlib.sha256(original).hexdigest())
        self.assertNotIn("Invented", str(report))
        self.assertEqual(MacroProgram.parse(MARKER).bytes(), MARKER)

    def test_macro_truncated_lengths_flags_terminators_and_unrecognized_version_fail(self):
        line = MacroLine(b"\x01\x02\x03\x04", (b"source", b"", b"", b"", b""), b"\0" * 12).bytes()
        malformed = (MARKER + b"\x01", MARKER + b"\x01\x02\x03\x04\x01\0",
                     MARKER + b"\x01\x02\x03\x04" + struct.pack("<I", 999) + b"x\r\n",
                     MARKER + line[:-5], MARKER + line[:-2] + b"\n", MARKER + line + b"\0",
                     MARKER + EMPTY_LINE + b"\n", MARKER + EMPTY_LINE + b"\0\r\n")
        for data in malformed:
            with self.subTest(size=len(data)), self.assertRaises(HmiError) as context:
                MacroProgram.parse(data)
            self.assertEqual(context.exception.code, "MACRO_FRAME")
        for data in (b"", b"\x03REV", b"source=only\r\n"):
            with self.subTest(data=data), self.assertRaises(HmiError) as context:
                MacroProgram.parse(data)
            self.assertEqual(context.exception.code, "UNSUPPORTED_MACRO_FORMAT")
        with self.assertRaises(HmiError) as context:
            MacroProgram.parse("not bytes")
        self.assertEqual(context.exception.code, "MACRO_FRAME")

    def test_macro_framing_bounds_before_allocation_and_serializer_validation(self):
        with self.assertRaises(HmiError) as context:
            MacroProgram.parse(MARKER + b"\1\2\3\4" + struct.pack("<I", 0xFFFFFFFF))
        self.assertEqual(context.exception.code, "MACRO_LIMIT")
        original = MacroProgram((MacroLine(EMPTY_LINE), MacroLine(EMPTY_LINE))).bytes()
        with patch("universal_hmi.native.macros.MAX_LINES", 1), self.assertRaises(HmiError):
            MacroProgram.parse(original)
        with patch("universal_hmi.native.macros.MAX_PAYLOAD", 3), self.assertRaises(HmiError):
            MacroProgram.parse(MARKER)
        invalid = (MacroLine(b"x"), MacroLine(EMPTY_LINE, (b"illegal",)),
                   MacroLine(b"1234", (b"x",) * 4, b"\0" * 12),
                   MacroLine(b"1234", (b"x",) * 5, b"\0" * 11),
                   MacroLine(b"1234", ("not bytes",) * 5, b"\0" * 12))
        for line in invalid:
            with self.subTest(descriptor=line.descriptor), self.assertRaises(HmiError):
                MacroProgram((line,)).bytes()
        with patch("universal_hmi.native.macros.MAX_FIELD_BYTES", 2), self.assertRaises(HmiError):
            MacroProgram((MacroLine(b"1234", (b"large", b"", b"", b"", b""), b"\0" * 12),)).bytes()
        with patch("universal_hmi.native.macros.MAX_PAYLOAD", 5), self.assertRaises(HmiError):
            MacroProgram((MacroLine(EMPTY_LINE),)).bytes()

    def test_macro_random_original_roundtrips_do_not_decode_operand_bytes(self):
        generator = random.Random(39)
        for _ in range(30):
            descriptor = generator.randbytes(4)
            fields = tuple(generator.randbytes(generator.randrange(40)) for _ in range(5))
            program = MacroProgram((MacroLine(descriptor, fields, generator.randbytes(12)), MacroLine(EMPTY_LINE)))
            data = program.bytes()
            self.assertEqual(MacroProgram.parse(data).bytes(), data)

    def macro_operation(self, statements=None, owner=None, field="ClockMacroLen", source=None):
        owner = {"kind": "application"} if owner is None else owner
        source = macro_fixture() if source is None else source
        record = macro_record(NativeAdapter(source, "delta_diascreen").document, owner, field)
        return {"op": "configure_macro", "owner": owner, "field": field,
                "expected_program_sha256": hashlib.sha256(record.blob).hexdigest(),
                "statements": [{"op": "assign", "address": "$1", "datatype": "UINT", "value": 2}]
                              if statements is None else statements}

    def test_macro_inventory_owner_status_and_no_proprietary_source(self):
        adapter = NativeAdapter(macro_fixture(), "delta_diascreen")
        items = adapter.inspect()["macros"]
        self.assertEqual(len(items), 8)
        initial = next(item for item in items if item["field"] == "InitialMacroLen")
        self.assertEqual((initial["owner"], initial["status"], initial["line_count"]),
                         ({"kind": "application"}, "REV_FRAMING_PASS", 11))
        before = next(item for item in items if item["field"] == "BeforeExecMacroLen")
        self.assertEqual((before["owner"], before["status"], before["owner_status"]),
                         ({"kind": "element", "screen_id": "1", "element_id": "1"}, "EMPTY", "QUALIFIED"))
        self.assertEqual(initial["schedule"]["ClockMacroDelayTime"], "100")
        self.assertNotIn("BITON", str(items))
        self.assertNotIn("$1", str(items))

    def test_macro_readonly_preserves_opaque_and_malformed_rev(self):
        for payload, status in ((b"unknown native stream\r\n", "OPAQUE_UNSUPPORTED"),
                                (MARKER + b"\x01\r\n", "MALFORMED_REV"), (b"", "EMPTY")):
            source = _fixture_macro(macro_fixture(), {"kind": "application"}, "ClockMacroLen", payload)
            adapter = NativeAdapter(source, "delta_diascreen")
            item = next(item for item in adapter.inspect()["macros"] if item["field"] == "ClockMacroLen")
            self.assertEqual(item["status"], status)
            self.assertEqual(adapter.apply([], {}), source)
            if payload:
                with self.subTest(status=status), self.assertRaises(HmiError):
                    adapter.apply([self.macro_operation(source=source)], macro_profile(source=source))
        source = synthetic_file()
        self.assertEqual(NativeAdapter(source, "delta_diascreen").inspect()["macros"][0]["status"], "OPAQUE_UNSUPPORTED")

    def test_macro_exact_compilation_both_containers_and_token_locality(self):
        statements = [
            {"op": "assign", "datatype": "UINT", "address": "$1", "value": 12},
            {"op": "assign", "datatype": "UDINT", "address": "$20", "value": 4294967295},
            {"op": "assign", "datatype": "DINT", "address": "$22", "value": -2147483648},
            {"op": "bit_on", "datatype": "BOOL", "address": "$3.15"},
            {"op": "bit_off", "datatype": "BOOL", "address": "$4.0"},
            {"op": "add", "datatype": "UINT", "address": "$2", "left": "$2", "right": 3},
            {"op": "if", "datatype": "UINT", "address": "$1", "value": 2, "comparison": "eq",
             "then": [{"op": "bit_on", "datatype": "BOOL", "address": "$8.1"}],
             "else": [{"op": "assign", "datatype": "UINT", "address": "$1", "value": 0}]},
        ]
        for family in ("delta_diascreen", "delta_dopsoft2"):
            source = macro_fixture(family)
            adapter = NativeAdapter(source, family)
            operation = self.macro_operation(statements)
            profile = macro_profile(family)
            output = adapter.apply([operation], profile)
            candidate = NativeAdapter(output, family)
            schema = profile["native_schema"]
            self.assertEqual(candidate.macro_statements(operation["owner"], operation["field"], schema, adapter), statements)
            self.assertTrue(candidate.verify_macro_contract(operation, schema, adapter))
            before, after = Envelope.decode(source, family), Envelope.decode(output, family)
            initial = adapter.application.one("InitialMacroLen")
            self.assertEqual(candidate.application.one("InitialMacroLen").raw, initial.raw)
            self.assertEqual((before.prefix, before.thumbnail), (after.prefix, after.thumbnail))
            self.assertEqual(candidate.document.tail, adapter.document.tail)
            new_record = candidate.application.one("ClockMacroLen")
            self.assertEqual(before.body.replace(b"ClockMacroLen=0\r\n", new_record.raw, 1), after.body)
            emitted = MacroProgram.parse(new_record.blob)
            self.assertEqual(emitted.lines[0].strings[:3], (b"$1 = 12", b"$1", b"12"))
            self.assertEqual(emitted.lines[6].strings[:3], (b"IF $1 == 2", b"$1", b"2"))
            self.assertEqual(adapter.apply([operation], profile), output)
            with self.assertRaises(HmiError) as context:
                candidate.apply([operation], profile)
            self.assertEqual(context.exception.code, "STALE_MACRO_PROGRAM")

    def test_macro_nested_conditions_and_exact_initial_noop(self):
        source = macro_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        schema = macro_profile()["native_schema"]
        original = adapter.macro_statements({"kind": "application"}, "InitialMacroLen", schema, adapter)
        operation = self.macro_operation(original, field="InitialMacroLen", source=source)
        self.assertEqual(adapter.apply([operation], macro_profile()), source)
        nested = [{"op": "assign", "datatype": "UINT", "address": "$1", "value": 7}]
        for _ in range(4):
            nested = [{"op": "if", "datatype": "UINT", "address": "$1", "value": 1,
                       "then": nested, "else": [{"op": "bit_off", "datatype": "BOOL", "address": "$8.0"}]}]
        operation = self.macro_operation(nested)
        output = adapter.apply([operation], macro_profile())
        self.assertTrue(NativeAdapter(output, "delta_diascreen").verify_macro_contract(operation, schema, adapter))

    def test_macro_semantic_noop_preserves_blank_lines_case_spacing_and_compression(self):
        original = macro_fixture()
        program = MacroProgram.parse(NativeAdapter(original, "delta_diascreen").application.one("InitialMacroLen").blob)
        lines = list(program.lines)
        donor = lines[0]
        lines[0] = MacroLine(donor.descriptor, (b"\t $1   =  1 ",) + donor.strings[1:], donor.flags)
        conditional = lines[6]
        lines[6] = MacroLine(conditional.descriptor, (b"\tIf  $1 == 1  ",) + conditional.strings[1:], conditional.flags)
        lines.insert(3, MacroLine(EMPTY_LINE))
        lines.append(MacroLine(EMPTY_LINE))
        source = _fixture_macro(original, {"kind": "application"}, "InitialMacroLen", MacroProgram(tuple(lines)).bytes())
        envelope = Envelope.decode(source, "delta_diascreen")
        source = envelope.encode(envelope.body.replace(b"InitialMacroLen=", b"InitialMacroLen=00", 1))
        adapter = NativeAdapter(source, "delta_diascreen")
        profile = macro_profile(source=source)
        schema = profile["native_schema"]
        statements = adapter.macro_statements({"kind": "application"}, "InitialMacroLen", schema, adapter)
        operation = self.macro_operation(statements, field="InitialMacroLen", source=source)
        output = adapter.apply([operation], profile)
        self.assertEqual(output, source)
        self.assertTrue(NativeAdapter(output, "delta_diascreen").verify_macro_contract(operation, schema, adapter))
        # Independent saved-file verification also enforces exact no-op bytes.
        tampered_payload = MacroProgram(tuple(line for line in lines if line.descriptor != EMPTY_LINE)).bytes()
        tampered = _fixture_macro(output, {"kind": "application"}, "InitialMacroLen", tampered_payload)
        with self.assertRaises(HmiError) as context:
            NativeAdapter(tampered, "delta_diascreen").verify_macro_contract(operation, schema, adapter)
        self.assertEqual(context.exception.code, "MACRO_NOOP_CHANGED")

    def test_macro_owner_keys_fields_duplicates_and_missing_records_reject(self):
        source = macro_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        operation = self.macro_operation()
        for owner in ({"kind": "state", "screen_id": "1", "element_id": "1"},
                      {"kind": "application", "screen_id": "1"}, {"kind": "screen", "screen_id": True},
                      {"kind": "element", "screen_id": "1"}, {"kind": "element", "screen_id": "1", "element_id": "01"}):
            with self.subTest(owner=owner), self.assertRaises(HmiError):
                adapter.apply([operation | {"owner": owner}], macro_profile())
        for field in ("MissingMacroLen", "ButtonOnMacroLen", "BeforeExecMacroLen"):
            with self.subTest(field=field), self.assertRaises(HmiError):
                adapter.apply([operation | {"field": field}], macro_profile())
        envelope = Envelope.decode(source, "delta_diascreen")
        for body in (envelope.body.replace(b"ClockMacroLen=0\r\n", b"ClockMacroLen=0\r\nClockMacroLen=0\r\n", 1),
                     envelope.body.replace(b"[Screen]\r\n", b"[Application]\r\nInitialMacroLen=0\r\n[Screen]\r\n", 1),
                     envelope.body.replace(b"ClockMacroDelayTime=100\r\n", b"ClockMacroDelayTime=100\r\nClockMacroDelayTime=200\r\n", 1)):
            ambiguous = NativeAdapter(envelope.encode(body), "delta_diascreen")
            self.assertTrue(any(item["owner_status"] == "AMBIGUOUS" for item in ambiguous.inspect()["macros"]))
            with self.assertRaises(HmiError):
                ambiguous.apply([operation], macro_profile())
            self.assertEqual(ambiguous.apply([], {}), ambiguous.original)
        body = envelope.body.replace(b"[State]\r\nValue=0", b"[State]\r\nInitialMacroLen=0\r\nValue=0", 1)
        state_source = NativeAdapter(envelope.encode(body), "delta_diascreen")
        entry = next(item for item in state_source.inspect()["macros"] if item["section_index"] == 4)
        self.assertEqual((entry["owner"], entry["owner_status"]), (None, "UNQUALIFIED"))
        # Legacy framing diagnostics must also avoid inheriting element IDs.
        body = envelope.body.replace(b"[State]\r\nValue=0", b"[State]\r\nInitialMacroLen=4\r\nxx\r\nValue=0", 1)
        frame = next(item for item in NativeAdapter(envelope.encode(body), "delta_diascreen").inspect()["framed_records"]
                     if item["section"] == "State")
        self.assertEqual((frame["screen_id"], frame["element_id"]), (None, None))

    def test_macro_templates_require_program_line_descriptor_and_all_flags(self):
        adapter = NativeAdapter(macro_fixture(), "delta_diascreen")
        operation = self.macro_operation()
        mutations = (lambda p: p["macros"].update(qualified=False),
                     lambda p: p["macros"]["templates"][0]["donor"].update(program_sha256="0" * 64),
                     lambda p: p["macros"]["templates"][0]["donor"].update(line_sha256="0" * 64),
                     lambda p: p["macros"]["templates"][0].update(descriptor_hex="ffffffff"),
                     lambda p: p["macros"]["templates"][0].update(flags_hex="0" * 24),
                     lambda p: p["macros"]["templates"][1].update(datatype="UINT"),
                     lambda p: p["macros"]["templates"].append(deepcopy(p["macros"]["templates"][0])),
                     lambda p: p["macros"].update(address_bounds={"minimum": False, "maximum": 1000}))
        for mutation in mutations:
            profile = macro_profile()
            mutation(profile["native_schema"])
            with self.subTest(mutation=mutation), self.assertRaises(HmiError):
                adapter.apply([operation], profile)
            self.assertEqual(adapter.apply([], {}), adapter.original)

    def test_macro_source_operand_desynchronization_aliases_and_width_reject(self):
        base = macro_fixture()
        initial = MacroProgram.parse(NativeAdapter(base, "delta_diascreen").application.one("InitialMacroLen").blob)
        donor = initial.lines[0]
        mutations = (MacroLine(donor.descriptor, (b"$1 = 1", b"$9", b"1", b"Var3", b"Var4"), donor.flags),
                     MacroLine(donor.descriptor, (b"$1 = 1", b"$1", b"2", b"Var3", b"Var4"), donor.flags),
                     MacroLine(donor.descriptor, (b"[ALIAS] = 1", b"$1", b"1", b"Var3", b"Var4"), donor.flags),
                     MacroLine(donor.descriptor, (b"DIA_TAG@{Link1}0.Name = 1", b"DIA_TAG@{Link1}0.Name", b"1", b"Var3", b"Var4"), donor.flags),
                     MacroLine(donor.descriptor, (b"$1 = 1 (DW)", b"$1", b"1", b"Var3", b"Var4"), donor.flags),
                     MacroLine(donor.descriptor, donor.strings, donor.flags[:4] + struct.pack("<II", 1, 0)))
        for line in mutations:
            payload = MacroProgram((line,) + initial.lines[1:]).bytes()
            source = _fixture_macro(base, {"kind": "application"}, "InitialMacroLen", payload)
            adapter = NativeAdapter(source, "delta_diascreen")
            with self.subTest(source=line.strings[0]), self.assertRaises(HmiError):
                adapter.apply([self.macro_operation(source=source)], macro_profile(source=source))

    def test_macro_if_structure_orphans_repeated_else_and_unknown_commands_reject(self):
        base = macro_fixture()
        initial = MacroProgram.parse(NativeAdapter(base, "delta_diascreen").application.one("InitialMacroLen").blob)
        assign, conditional, alternate, end = (initial.lines[index] for index in (0, 6, 8, 10))
        for lines in ((alternate,), (end,), (conditional, assign),
                      (conditional, assign, alternate, assign, alternate, assign, end),
                      (conditional, end), (conditional, assign, alternate, end),
                      (MacroLine(b"\xff" * 4, (b"JUMP 1", b"1", b"Var2", b"Var3", b"Var4"), b"\0" * 12),)):
            source = _fixture_macro(base, {"kind": "application"}, "ClockMacroLen", MacroProgram(lines).bytes())
            adapter = NativeAdapter(source, "delta_diascreen")
            with self.subTest(lines=len(lines)), self.assertRaises(HmiError):
                adapter.apply([self.macro_operation(source=source)], macro_profile())
        profile = macro_profile()
        profile["native_schema"]["macros"]["templates"] = [item for item in profile["native_schema"]["macros"]["templates"] if item["op"] != "else"]
        operation = self.macro_operation([{"op": "if", "datatype": "UINT", "address": "$1", "value": 1,
                                          "then": [{"op": "bit_on", "datatype": "BOOL", "address": "$8.0"}],
                                          "else": [{"op": "bit_off", "datatype": "BOOL", "address": "$8.0"}]}])
        with self.assertRaises(HmiError) as context:
            NativeAdapter(base, "delta_diascreen").apply([operation], profile)
        self.assertEqual(context.exception.code, "UNQUALIFIED_MACRO_COMMAND")

    def test_macro_multi_owner_resolves_immutable_donors_and_rejects_duplicate_updates(self):
        source = macro_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        initial = self.macro_operation(field="InitialMacroLen")
        clock = self.macro_operation()
        button = self.macro_operation(owner={"kind": "element", "screen_id": "1", "element_id": "1"}, field="BeforeExecMacroLen")
        output = adapter.apply([initial, clock, button], macro_profile())
        reversed_output = adapter.apply([button, clock, initial], macro_profile())
        self.assertEqual(output, reversed_output)
        candidate = NativeAdapter(output, "delta_diascreen")
        for operation in (initial, clock, button):
            self.assertTrue(candidate.verify_macro_contract(operation, macro_profile()["native_schema"], adapter))
        with self.assertRaises(HmiError) as context:
            adapter.apply([clock, clock], macro_profile())
        self.assertEqual(context.exception.code, "DUPLICATE_MACRO_UPDATE")

    def test_macro_invalid_values_addresses_types_comparisons_and_bounds_fail(self):
        adapter = NativeAdapter(macro_fixture(), "delta_diascreen")
        changes = ({"value": 65536}, {"value": -1}, {"value": True}, {"value": "1"}, {"value": 0.5},
                   {"value": 10 ** 5000}, {"address": "$1001"}, {"address": "$01"}, {"address": "$1.0"},
                   {"address": "!D1"}, {"datatype": "REAL"}, {"datatype": "LREAL"}, {"datatype": []},
                   {"unknown": 1}, {"op": "call"})
        base = {"op": "assign", "datatype": "UINT", "address": "$1", "value": 1}
        for change in changes:
            with self.subTest(change=tuple(change)), self.assertRaises(HmiError):
                adapter.apply([self.macro_operation([base | change])], macro_profile())
        for statement in ({"op": "assign", "datatype": "UDINT", "address": "$1000", "value": 1},
                          {"op": "bit_on", "datatype": "BOOL", "address": "$1.16"},
                          {"op": "if", "datatype": "UINT", "address": "$1", "value": 1,
                           "comparison": "ne", "then": [base]}):
            with self.subTest(op=statement["op"]), self.assertRaises(HmiError):
                adapter.apply([self.macro_operation([statement])], macro_profile())
        with patch("universal_hmi.native.macro_semantics.MAX_STATEMENTS", 1), self.assertRaises(HmiError):
            adapter.apply([self.macro_operation([base, base])], macro_profile())

    def test_macro_final_verifier_checks_candidate_operands_unused_flags_and_exact_owner(self):
        source = macro_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        operation = self.macro_operation()
        profile = macro_profile()
        output = adapter.apply([operation], profile)
        payload = macro_record(NativeAdapter(output, "delta_diascreen").document, operation["owner"], operation["field"]).blob
        line = MacroProgram.parse(payload).lines[0]
        for changed in (MacroLine(line.descriptor, (b"$1 = 3", b"$1", b"3", b"Var3", b"Var4"), line.flags),
                        MacroLine(line.descriptor, line.strings[:4] + (b"mutated unused",), line.flags),
                        MacroLine(line.descriptor, line.strings, b"\0" * 4 + line.flags[4:])):
            candidate_bytes = _fixture_macro(output, operation["owner"], operation["field"], MacroProgram((changed,)).bytes())
            candidate = NativeAdapter(candidate_bytes, "delta_diascreen")
            with self.assertRaises(HmiError):
                candidate.verify_macro_contract(operation, profile["native_schema"], adapter)
        for invalid in (None, [], operation | {"unknown": True}, operation | {"expected_program_sha256": "0" * 64}):
            with self.subTest(kind=type(invalid).__name__), self.assertRaises(HmiError):
                NativeAdapter(output, "delta_diascreen").verify_macro_contract(invalid, profile["native_schema"], adapter)

    def test_global_alarm_inventory_and_batch_mutation_preserve_native_owners(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            source = resource_native_fixture(family)
            adapter = NativeAdapter(source, family)
            report = adapter.inspect()["resources"]
            self.assertEqual((report["status"], report["owner"], report["capacity"], report["serialized_entry_count"]),
                             ("GLOBAL_RESOURCE_FRAMING_PASS", "GLOBAL_ALARM", 8, 2))
            operation = {"op": "configure_alarm", "expected_alarm_sha256": report["alarm_sha256"],
                         "updates": [{"field": "AlarmEnable001", "value": "0"},
                                     {"field": "wMessageLen002-0", "value": "Arıza: ölçüm"}]}
            profile = resource_native_profile(family)
            macro = self.macro_operation()
            output = adapter.apply([macro, operation], profile)
            candidate = NativeAdapter(output, family)
            self.assertEqual(candidate.inspect()["resources"]["enabled_entry_count"], 1)
            self.assertTrue(candidate.verify_macro_contract(macro, profile["native_schema"], adapter))
            before = ResourceTables.parse(adapter.document.tail)
            after = ResourceTables.parse(candidate.document.tail)
            self.assertEqual((before.prefix, before.suffix), (after.prefix, after.suffix))
            self.assertEqual(after.alarm.one("wMessageLen002-0").text(), "Arıza: ölçüm")
            self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)
            self.assertEqual(adapter.apply([operation, macro], profile), output)
            self.assertEqual(adapter.apply([], {}), source)
            with self.assertRaises(HmiError) as error:
                adapter.apply([operation, operation], profile)
            self.assertEqual(error.exception.code, "DUPLICATE_ALARM_UPDATE")

    def test_global_alarm_failure_and_unknown_tail_are_preserved_offline(self):
        source = resource_native_fixture()
        adapter = NativeAdapter(source, "delta_diascreen")
        report = adapter.inspect()["resources"]
        operation = {"op": "configure_alarm", "expected_alarm_sha256": report["alarm_sha256"],
                     "updates": [{"field": "wMessageLen002-0", "value": "New fault"}]}
        profile = resource_native_profile()
        self.assertEqual(adapter.apply([operation], profile), adapter.apply([operation], profile))
        with self.assertRaises(HmiError) as error:
            adapter.apply([self.property(), operation | {"expected_alarm_sha256": "0" * 64}], profile)
        self.assertEqual(error.exception.code, "ALARM_SOURCE_CHANGED")
        self.assertEqual(adapter.apply([], {}), source)
        unknown = self.adapter.inspect()["resources"]
        self.assertEqual((unknown["status"], unknown["semantic_qualification"]), ("OPAQUE_UNSUPPORTED", "UNVERIFIED"))
        self.assertEqual(self.adapter.apply([], {}), self.source)
        with self.assertRaises(HmiError):
            self.adapter.apply([operation], self.profile)

    def test_signed_model_identity_matches_same_uint32_without_rewriting_native(self):
        signed, unsigned = "-1107091184", "3187876112"
        self.assertTrue(model_ids_match(signed, unsigned))
        self.assertEqual(canonical_model_id(signed), int(unsigned))
        for family in ("delta_dopsoft2", "delta_diascreen"):
            source = synthetic_file(family, model_id=signed)
            adapter = NativeAdapter(source, family)
            profile = synthetic_profile(family)
            profile.update(model_id=unsigned)
            profile["native_schema"]["model_id"] = int(unsigned)
            output = adapter.apply([self.property()], profile)
            self.assertEqual(NativeAdapter(output, family).inspect()["model_id"], signed)
            self.assertIn(b"ModelName=" + signed.encode() + b"\r\n", Envelope.decode(output, family).body)
            for change in ({"model_id": str(int(unsigned) + 1)}, {"editor_version": "other"},
                           {"family": "delta_diascreen" if family == "delta_dopsoft2" else "delta_dopsoft2"}):
                with self.subTest(change=change), self.assertRaises(HmiError) as context:
                    adapter.apply([self.property()], profile | change)
                self.assertEqual(context.exception.code, "PROFILE_MISMATCH")

    def unit_operation(self, adapter, text="Ölçüm 🔧"):
        return {"op": "set_unit_caption", "screen_id": "1", "element_id": "1", "text": text,
                "expected_unit_baseline_sha256": adapter.unit_baseline("1", "1")}

    def test_unit_caption_framing_inventory_separate_from_state_labels(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                source = unit_fixture(family, "mm\r\n[Screen]\r\nID=999 🔧")
                adapter = NativeAdapter(source, family)
                self.assertEqual(adapter.document.bytes(), adapter.envelope.body)
                result = adapter.inspect()
                self.assertEqual(len(result["screens"]), 1)
                owner = result["screens"][0]["elements"][0]
                self.assertEqual([entry["text"] for entry in owner["texts"]], ["OFF", "ON"])
                self.assertEqual(owner["unit_captions"], [{"language": 0, "text": "mm\r\n[Screen]\r\nID=999 🔧",
                                                         "byte_count": 48, "frame_complete": True,
                                                         "qualification": "UNVERIFIED"}])
                self.assertEqual(adapter.apply([self.unit_operation(adapter, owner["unit_captions"][0]["text"])], unit_profile(family)), source)

    def test_unit_caption_only_edit_preserves_companions_unknown_records_and_envelope(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                source = unit_fixture(family)
                adapter = NativeAdapter(source, family)
                operation = self.unit_operation(adapter, "İğdır °C 🔧\r\n[Element]\r\nUnitType=99")
                baseline = operation["expected_unit_baseline_sha256"]
                full = adapter.unit_context_baseline("1", "1")
                output = adapter.apply([operation], unit_profile(family))
                candidate = NativeAdapter(output, family)
                self.assertEqual(candidate.unit_baseline("1", "1"), baseline)
                self.assertNotEqual(candidate.unit_context_baseline("1", "1"), full)
                self.assertTrue(candidate.verify_unit_caption(operation, unit_profile(family)["native_schema"], adapter))
                self.assertEqual(candidate.envelope.body, adapter.envelope.body.replace(_wide("UnitTextLen0", "mm"),
                                                                                       _wide("UnitTextLen0", operation["text"]), 1))
                self.assertEqual(candidate.envelope.thumbnail, adapter.envelope.thumbnail)
                self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)
                self.assertEqual(candidate.document.tail, adapter.document.tail)
                self.assertEqual(adapter.original, source)
                self.assertEqual(adapter.document.bytes(), adapter.envelope.body)
                self.assertEqual(candidate.apply([self.unit_operation(candidate, operation["text"])], unit_profile(family)), output)

    def test_unit_context_disabled_and_zero_frames_are_readonly_not_mutation_authority(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            for enabled, zero in (("0", False), ("0", True), ("1", True)):
                with self.subTest(family=family, enabled=enabled, zero=zero):
                    source = unit_fixture(family, "", enabled)
                    envelope = Envelope.decode(source, family)
                    if zero:
                        source = envelope.encode(envelope.body.replace(_wide("UnitTextLen0", ""), b"UnitTextLen0=0\r\n", 1))
                    adapter = NativeAdapter(source, family)
                    self.assertEqual(adapter.document.bytes(), adapter.envelope.body)
                    self.assertEqual(len(adapter.unit_context_baseline("1", "1")), 64)
                    caption = adapter.inspect()["screens"][0]["elements"][0]["unit_captions"][0]
                    self.assertEqual(caption["text"], "")
                    self.assertEqual(caption["frame_complete"], not zero)
                    self.assertEqual(caption["byte_count"], 0 if zero else 2)
                    self.assertEqual(adapter.apply([], unit_profile(family)), source)
                    with self.assertRaises(HmiError) as context:
                        adapter.unit_baseline("1", "1")
                    self.assertEqual(context.exception.code, "UNQUALIFIED_UNIT_FRAME" if zero else "INACTIVE_UNIT_CAPTION")
                    with self.assertRaises(HmiError):
                        adapter.apply([{"op": "set_unit_caption", "screen_id": "1", "element_id": "1", "text": "",
                                        "expected_unit_baseline_sha256": "0" * 64}], unit_profile(family))

    def test_unit_enabled_empty_caption_has_real_nul_frame_and_exact_noop(self):
        adapter = NativeAdapter(unit_fixture(text=""), "delta_diascreen")
        self.assertEqual(adapter.apply([self.unit_operation(adapter, "")], unit_profile()), adapter.original)
        result = adapter.apply([self.unit_operation(adapter, "m/s")], unit_profile())
        self.assertEqual(NativeAdapter(result, "delta_diascreen").inspect()["screens"][0]["elements"][0]["unit_captions"][0]["text"], "m/s")

    def test_unit_framing_rejects_malformed_lengths_utf16_and_missing_terminators(self):
        replacements = (b"UnitTextLen0=x\r\n", b"UnitTextLen0=-2\r\n", b"UnitTextLen0=999999999999999999999\r\n",
                        b"UnitTextLen0=3\r\nx\x00\x00\r\n", b"UnitTextLen0=2\r\nx\x00\r\n",
                        b"UnitTextLen0=4\r\n\x00\xd8\x00\x00\r\n", b"UnitTextLen0=6\r\nx\x00\x00\x00\x00\x00X\n")
        for replacement in replacements:
            with self.subTest(replacement=replacement[:24]), self.assertRaises(HmiError) as context:
                source = unit_fixture()
                envelope = Envelope.decode(source, "delta_diascreen")
                NativeAdapter(envelope.encode(envelope.body.replace(_wide("UnitTextLen0", "mm"), replacement, 1)), "delta_diascreen")
            self.assertIn(context.exception.code, {"NATIVE_FRAME", "NATIVE_LIMIT", "NATIVE_TEXT"})
        with self.assertRaises(HmiError) as context:
            Document.parse(b"[Application]\r\nUnitTextLen0=6\r\nx\x00")
        self.assertEqual(context.exception.code, "NATIVE_FRAME")

    def test_unit_fields_require_canonical_unique_languages_and_companions(self):
        for key in ("UnitTextLen00", "UnitTextLen-1", "UnitTextLen2147483648", "UnitFontSize01", "UnitFontName00"):
            with self.subTest(key=key), self.assertRaises(HmiError) as context:
                source = unit_fixture()
                envelope = Envelope.decode(source, "delta_diascreen")
                replacement = _wide(key, "mm") if key.startswith("UnitTextLen") else key.encode() + b"=Arial\r\n"
                NativeAdapter(envelope.encode(envelope.body.replace(_wide("UnitTextLen0", "mm"), replacement, 1)), "delta_diascreen")
            self.assertEqual(context.exception.code, "INVALID_ID")
        for record in (_wide("UnitTextLen0", "other"), b"ShowUnit=1\r\n", b"UnitDirection=0\r\n", b"UnitUnknown=raw\r\nUnitUnknown=again\r\n"):
            with self.subTest(record=record[:24]), self.assertRaises(HmiError) as context:
                source = unit_fixture()
                envelope = Envelope.decode(source, "delta_diascreen")
                NativeAdapter(envelope.encode(envelope.body.replace(b"UnitBold=1\r\n", record + b"UnitBold=1\r\n", 1)), "delta_diascreen")
            self.assertEqual(context.exception.code, "AMBIGUOUS_FIELD")

    def test_unit_companion_baseline_covers_unknown_fields_secondary_captions_and_order(self):
        source = unit_fixture()
        envelope = Envelope.decode(source, "delta_diascreen")
        extra = b"UnitUnknown=opaque\xff\r\nUnitFontSize1=14\r\nUnitFontName1=Arial\r\n" + _wide("UnitTextLen1", "second")
        source = envelope.encode(envelope.body.replace(b"UnitBold=1\r\n", extra + b"UnitBold=1\r\n", 1))
        adapter = NativeAdapter(source, "delta_diascreen")
        operation = self.unit_operation(adapter, "new")
        candidate = NativeAdapter(adapter.apply([operation], unit_profile()), "delta_diascreen")
        self.assertTrue(candidate.verify_unit_caption(operation, unit_profile()["native_schema"], adapter))
        for before, after in ((b"UnitUnknown=opaque\xff", b"UnitUnknown=changed"), (_wide("UnitTextLen1", "second"), _wide("UnitTextLen1", "changed")),
                              (b"UnitDirection=0", b"UnitDirection=3"), (b"UnitType=0", b"UnitType=1"),
                              (b"BackupUnitSrc=0", b"BackupUnitSrc=1"), (b"BackupUnitDisplay=0", b"BackupUnitDisplay=2"),
                              (b"ConvertConstByUnit=0", b"ConvertConstByUnit=1"),
                              (b"UnitFontSize0=14\r\nUnitFontName0=Arial\r\n", b"UnitFontName0=Arial\r\nUnitFontSize0=14\r\n")):
            changed = NativeAdapter(candidate.envelope.encode(candidate.envelope.body.replace(before, after, 1)), "delta_diascreen")
            with self.subTest(before=before), self.assertRaises(HmiError) as context:
                changed.verify_unit_caption(operation, unit_profile()["native_schema"], adapter)
            self.assertEqual(context.exception.code, "UNIT_BASELINE_MISMATCH")

    def test_unit_baseline_requires_complete_known_owner_and_all_observed_fields(self):
        source = unit_fixture()
        envelope = Envelope.decode(source, "delta_diascreen")
        cases = ((b"Type=6\r\nSubType=1", b"Type=1\r\nSubType=1", "UNQUALIFIED_UNIT_OWNER"),
                 (b"UnitDirection=0\r\n", b"", "UNQUALIFIED_UNIT_BASELINE"),
                 (b"ShowUnit=1\r\n", b"ShowUnit=2\r\n", "UNQUALIFIED_UNIT_BASELINE"),
                 (b"[Application]\r\n", b"[Application]\r\nBackupUnitSrc=0\r\n", "UNQUALIFIED_UNIT_OWNER"),
                 (b"[Screen]\r\nVER=16", b"[Screen]\r\nBackupUnitDisplay=0\r\nVER=16", "UNQUALIFIED_UNIT_OWNER"),
                 (b"[State]\r\nValue=0", b"[State]\r\nBackupUnitSrc=0\r\nValue=0", "UNQUALIFIED_UNIT_OWNER"),
                 (b"[State]\r\nValue=0", b"[UnknownOwner]\r\n[State]\r\nValue=0", "UNQUALIFIED_STRUCTURE"),
                 (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nUnknown=1\r\n", "UNQUALIFIED_STRUCTURE"))
        for before, after, code in cases:
            with self.subTest(code=code), self.assertRaises(HmiError) as context:
                adapter = NativeAdapter(envelope.encode(envelope.body.replace(before, after, 1)), "delta_diascreen")
                adapter.unit_context_baseline("1", "1")
            self.assertEqual(context.exception.code, code)

    def test_unit_mapping_authority_is_separate_exact_and_numeric_consistent(self):
        adapter = NativeAdapter(unit_fixture(), "delta_diascreen")
        operation = self.unit_operation(adapter)
        profiles = []
        for value in (None, {}, {"qualified": False}, {"qualified": True, "owner": "State", "field": "UnitTextLen0", "kinds": {}},
                      {"qualified": True, "owner": "Element", "field": "UnitTextLen1", "kinds": {}},
                      {"qualified": True, "owner": "Element", "field": "UnitTextLen0", "kinds": {"numeric_input": {"Type": "6"}, "numeric_display": {"Type": "5", "SubType": "1"}}}):
            profile = unit_profile(); profile["native_schema"]["unit_caption"] = value; profiles.append(profile)
        profile = unit_profile(); profile["native_schema"]["unit_caption"]["kinds"]["numeric_input"]["Type"] = "5"; profiles.append(profile)
        profile = unit_profile(); profile["native_schema"]["numeric"]["kinds"] = {"numeric_input": {"Type": "5", "SubType": "1"}, "numeric_display": {"Type": "6", "SubType": "1"}}; profiles.append(profile)
        profile = unit_profile(); profile["native_schema"]["unit_caption"]["extra"] = True; profiles.append(profile)
        for profile in profiles:
            with self.subTest(spec=profile["native_schema"]["unit_caption"]), self.assertRaises(HmiError) as context:
                adapter.apply([operation], profile)
            self.assertIn(context.exception.code, {"UNQUALIFIED_UNIT_CAPTION", "INVALID_SCHEMA"})

    def test_unit_named_kinds_cannot_be_swapped_when_numeric_schema_is_absent(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            with self.subTest(family=family):
                source = NativeAdapter(unit_fixture(family), family)
                operation = self.unit_operation(source, text="kg")
                profile = unit_profile(family)
                candidate = NativeAdapter(source.apply([operation], profile), family)
                profile["native_schema"].pop("numeric")
                kinds = profile["native_schema"]["unit_caption"]["kinds"]
                kinds["numeric_input"], kinds["numeric_display"] = kinds["numeric_display"], kinds["numeric_input"]
                for check in (lambda: source.apply([operation], profile),
                              lambda: candidate.verify_unit_caption(operation, profile["native_schema"], source)):
                    with self.assertRaises(HmiError) as caught:
                        check()
                    self.assertEqual(caught.exception.code, "INVALID_SCHEMA")

    def test_unit_operation_rejects_stale_baseline_invalid_text_and_unknown_arguments(self):
        adapter = NativeAdapter(unit_fixture(), "delta_diascreen")
        operation = self.unit_operation(adapter)
        for baseline in (None, "0" * 64, "A" * 64, "x", [], 1):
            with self.subTest(baseline=baseline), self.assertRaises(HmiError) as context:
                adapter.apply([operation | {"expected_unit_baseline_sha256": baseline}], unit_profile())
            self.assertEqual(context.exception.code, "UNIT_BASELINE_MISMATCH" if baseline == "0" * 64 else "INVALID_UNIT_BASELINE")
        for text in (None, "bad\0caption", "\ud800", 4):
            with self.subTest(text_kind=type(text).__name__), self.assertRaises(HmiError) as context:
                adapter.apply([operation | {"text": text}], unit_profile())
            self.assertEqual(context.exception.code, "INVALID_TEXT")
        with self.assertRaises(HmiError) as context:
            adapter.apply([operation | {"UnitDirection": 3}], unit_profile())
        self.assertEqual(context.exception.code, "INVALID_OPERATION")
        with self.assertRaises(HmiError) as context:
            adapter.apply([self.property(), operation | {"expected_unit_baseline_sha256": "0" * 64}], unit_profile())
        self.assertEqual(context.exception.code, "UNIT_BASELINE_MISMATCH")
        self.assertEqual(adapter.document.bytes(), adapter.envelope.body)

    def test_unit_saved_caption_and_target_identity_verified_without_repair(self):
        adapter = NativeAdapter(unit_fixture(), "delta_diascreen")
        operation = self.unit_operation(adapter, "kg")
        output = adapter.apply([operation], unit_profile())
        candidate = NativeAdapter(output, "delta_diascreen")
        schema = unit_profile()["native_schema"]
        self.assertTrue(candidate.verify_unit_caption(operation, schema, adapter))
        with self.assertRaises(HmiError) as context:
            candidate.verify_unit_caption(operation | {"text": "different"}, schema, adapter)
        self.assertEqual(context.exception.code, "UNIT_CAPTION_MISMATCH")
        changed = NativeAdapter(candidate.envelope.encode(candidate.envelope.body.replace(b"ShowUnit=1", b"ShowUnit=0", 1)), "delta_diascreen")
        with self.assertRaises(HmiError) as context:
            changed.verify_unit_caption(operation, schema, adapter)
        self.assertEqual(context.exception.code, "INACTIVE_UNIT_CAPTION")
        with self.assertRaises(HmiError) as context:
            candidate.verify_unit_caption(operation, schema, NativeAdapter(unit_fixture("delta_dopsoft2"), "delta_dopsoft2"))
        self.assertEqual(context.exception.code, "INVALID_UNIT_SOURCE")
        self.assertEqual(candidate.original, output)
        self.assertEqual(candidate.document.bytes(), candidate.envelope.body)

    def test_unit_exact_framing_does_not_guess_similar_keys(self):
        document = Document.parse(b"[Application]\r\nUnitTextLength0=2\r\nx\r\nUnitTextLenOther=2\r\ny\r\n")
        self.assertEqual([record.kind for record in document.sections[0].records], [None, None, None, None])
        self.assertEqual(document.bytes(), b"[Application]\r\nUnitTextLength0=2\r\nx\r\nUnitTextLenOther=2\r\ny\r\n")

    def test_unit_kind_prefixed_unknown_fields_bound_and_verifier_checks_schema(self):
        source = unit_fixture()
        envelope = Envelope.decode(source, "delta_diascreen")
        source = envelope.encode(envelope.body.replace(b"UnitBold=1\r\n", b"NumericUnitScale=raw\r\nUnitBold=1\r\n", 1))
        adapter = NativeAdapter(source, "delta_diascreen")
        operation = self.unit_operation(adapter, "kg")
        output = adapter.apply([operation], unit_profile())
        candidate = NativeAdapter(output, "delta_diascreen")
        changed = NativeAdapter(candidate.envelope.encode(candidate.envelope.body.replace(b"NumericUnitScale=raw", b"NumericUnitScale=other", 1)), "delta_diascreen")
        with self.assertRaises(HmiError) as context:
            changed.verify_unit_caption(operation, unit_profile()["native_schema"], adapter)
        self.assertEqual(context.exception.code, "UNIT_BASELINE_MISMATCH")
        for schema, code in ((None, "INVALID_SCHEMA"), ({"qualified": False}, "UNQUALIFIED_NATIVE"),
                             (unit_profile()["native_schema"] | {"unit_caption": None}, "UNQUALIFIED_UNIT_CAPTION")):
            with self.subTest(code=code), self.assertRaises(HmiError) as context:
                candidate.verify_unit_caption(operation, schema, adapter)
            self.assertEqual(context.exception.code, code)
        self.assertEqual(candidate.original, output)

    def test_unit_semantic_noop_requires_exact_source_primary_record_bytes(self):
        for family in ("delta_diascreen", "delta_dopsoft2"):
            for initial_length in (b"6", b"0006"):
                with self.subTest(family=family, initial_length=initial_length):
                    source = unit_fixture(family)
                    envelope = Envelope.decode(source, family)
                    source = envelope.encode(envelope.body.replace(b"UnitTextLen0=6\r\n", b"UnitTextLen0=" + initial_length + b"\r\n", 1))
                    adapter = NativeAdapter(source, family)
                    operation = self.unit_operation(adapter, "mm")
                    schema = unit_profile(family)["native_schema"]
                    self.assertEqual(adapter.apply([operation], unit_profile(family)), source)
                    self.assertTrue(adapter.verify_unit_caption(operation, schema, adapter))
                    changed_length = b"0006" if initial_length == b"6" else b"6"
                    changed = NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(
                        b"UnitTextLen0=" + initial_length + b"\r\n", b"UnitTextLen0=" + changed_length + b"\r\n", 1)), family)
                    self.assertEqual(changed.inspect()["screens"][0]["elements"][0]["unit_captions"][0]["text"], "mm")
                    self.assertEqual(changed.unit_baseline("1", "1"), adapter.unit_baseline("1", "1"))
                    with self.assertRaises(HmiError) as context:
                        changed.verify_unit_caption(operation, schema, adapter)
                    self.assertEqual(context.exception.code, "UNIT_CAPTION_MISMATCH")
                    self.assertEqual(changed.document.bytes(), changed.envelope.body)
                    self.assertEqual(adapter.document.bytes(), adapter.envelope.body)

    def test_model_identity_boundaries_invalid_numbers_and_exact_opaque_ids(self):
        for first, second in ((-2147483648, 2147483648), (-1, 4294967295), ("0", 0), ("4294967295", -1)):
            with self.subTest(first=first):
                self.assertTrue(model_ids_match(first, second))
        self.assertFalse(model_ids_match("SYNTHETIC", "synthetic"))
        self.assertTrue(model_ids_match("SYNTHETIC", "SYNTHETIC"))
        for value in (True, None, [], 2 ** 32, -(2 ** 31) - 1, "4294967296", "-2147483649", "-0", "01", "+1",
                      "9" * 5000, 10 ** 5000, "bad\r\nModelName=1", "opaque" * 30):
            with self.subTest(value_kind=type(value).__name__), self.assertRaises(HmiError):
                canonical_model_id(value)


class PreservedLayoutTests(unittest.TestCase):
    def setUp(self):
        self.source, self.profile = preserved_layout_fixture()
        self.adapter = NativeAdapter(self.source, "delta_dopsoft2")
        self.schema = self.profile["native_schema"]

    def change(self, before, after):
        return NativeAdapter(self.adapter.envelope.encode(self.adapter.envelope.body.replace(before, after, 1)), self.adapter.family)

    def assertError(self, call, code=None):
        with self.assertRaises(HmiError) as raised:
            call()
        if code:
            self.assertEqual(raised.exception.code, code)

    def test_default_layout_checks_remain_strict_and_empty_legacy_apply_exact(self):
        self.assertError(self.adapter.verify_layout_order, "UNQUALIFIED_STRUCTURE")
        strict = NativeAdapter(layout_fixture(), "delta_diascreen")
        self.assertTrue(strict.verify_layout_order())
        ordered = NativeAdapter(strict.envelope.encode(strict.envelope.body.replace(b"nPartsID=1\r\n", b"nPartsID=1\r\nOrder=0\r\n", 1)), strict.family)
        self.assertError(ordered.verify_layout_order, "UNQUALIFIED_LAYER")
        self.assertEqual(self.adapter.apply([], {}), self.source)

    def test_both_original_envelopes_qualified_existing_x_write_preserves_every_other_byte(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            with self.subTest(family=family):
                source, profile = preserved_layout_fixture(family)
                adapter = NativeAdapter(source, family)
                self.assertTrue(adapter.verify_layout_order(profile["native_schema"]))
                operation = {"op": "set_property", "screen_id": "1", "element_id": "1", "key": "x", "value": 11}
                output = adapter.apply([operation], profile)
                expected = adapter.envelope.body.replace(b"X=10\r\n", b"X=11\r\n", 1)
                candidate = NativeAdapter(output, family)
                self.assertEqual(candidate.envelope.body, expected)
                self.assertTrue(candidate.verify_layout_order(profile["native_schema"], adapter))
                self.assertEqual((candidate.envelope.thumbnail, candidate.envelope.prefix, candidate.document.tail),
                                 (adapter.envelope.thumbnail, adapter.envelope.prefix, adapter.document.tail))
                self.assertEqual(adapter.original, source)
                self.assertEqual(adapter.document.bytes(), adapter.envelope.body)
                self.assertEqual(adapter.apply([], profile), source)
                self.assertEqual(adapter.apply([operation | {"value": 10}], profile), source)

    def test_candidate_needs_actual_original_source_and_signed_model_version_are_exact(self):
        candidate = self.change(b"X=10\r\n", b"X=11\r\n")
        self.assertError(lambda: candidate.verify_layout_order(self.schema), "INVALID_PRESERVED_SOURCE")
        self.assertTrue(candidate.verify_layout_order(self.schema, self.adapter))
        self.assertError(lambda: candidate.verify_layout_order(self.schema, candidate), "INVALID_PRESERVED_SOURCE")
        self.assertError(lambda: self.change(b"Version=0.0\r\n", b"Version=0.00\r\n").verify_layout_order(self.schema, self.adapter), "INVALID_PRESERVED_SOURCE")
        source, profile = preserved_layout_fixture(model_id="-1")
        signed = NativeAdapter(source, "delta_dopsoft2")
        profile["model_id"] = 4294967295
        self.assertEqual(signed.apply([], profile), source)
        alternate = NativeAdapter(signed.envelope.encode(signed.envelope.body.replace(b"ModelName=-1\r\n", b"ModelName=4294967295\r\n", 1)), signed.family)
        self.assertError(lambda: alternate.verify_layout_order(profile["native_schema"], signed), "PRESERVED_LAYOUT_MISMATCH")

    def test_contract_exact_keys_hashes_names_order_and_types_apply_even_to_noop(self):
        changes = (("qualified", False), ("contract_version", True), ("mode", "clone"),
                   ("source_sha256", "0" * 64), ("source_sha256", []), ("prefix_sha256", "0" * 64), ("sections", []))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                profile = deepcopy(self.profile)
                profile["native_schema"]["preserved_layout"][key] = value
                self.assertError(lambda: self.adapter.apply([], profile))
        for change in ("extra", "entry_extra", "entry_hash", "entry_name", "section_order"):
            with self.subTest(change=change):
                profile = deepcopy(self.profile)
                contract = profile["native_schema"]["preserved_layout"]
                if change == "extra":
                    contract["unexpected"] = True
                elif change == "entry_extra":
                    contract["sections"][0]["unexpected"] = True
                elif change == "entry_hash":
                    contract["sections"][0]["sha256"] = "0" * 64
                elif change == "entry_name":
                    contract["sections"][0]["name"] = []
                else:
                    contract["sections"][1:3] = reversed(contract["sections"][1:3])
                self.assertError(lambda: self.adapter.apply([], profile))

    def test_unknown_repeated_globals_and_nonempty_unkeyed_metadata_refuse_rebased_contract(self):
        cases = ((b"[Multi-Language]\r\n", b"[OtherGlobal]\r\n"),
                 (b"[Multi-Language]\r\n", b"[Application]\r\n"),
                 (b"[FTPFile]\r\n", b"[FTP]\r\n"),
                 (b"NeutralField=A\r\n", b"unkeyed metadata\r\nNeutralField=A\r\n"),
                 (b"NeutralField=A\r\n", b" \r\nNeutralField=A\r\n"))
        for before, after in cases:
            with self.subTest(after=after[:30]):
                changed = self.change(before, after)
                profile = qualify_preserved_layout(changed.original, self.profile)
                self.assertError(lambda: changed.verify_layout_order(profile["native_schema"]))

    def test_framed_recipe_embedded_header_blank_delimiters_and_foreign_global_macro_stay_raw(self):
        self.assertTrue(self.adapter.verify_layout_order(self.schema))
        self.assertEqual(sum(record.key is None for record in self.adapter.application.records), 3)
        inventory = self.adapter.inspect()
        global_macro = next(item for item in inventory["macros"] if item["field"] == "InitialMacroLen")
        self.assertIsNone(global_macro["owner"])
        self.assertEqual(global_macro["owner_status"], "UNQUALIFIED")
        self.assertEqual(len(inventory["screens"]), 3)
        candidate = self.change(b"NeutralField=A\r\n", b"NeutralField=C\r\n")
        self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")
        candidate = self.change(b"\r\n\r\n\r\n[Multi-Language]", b"\r\n\r\n[Multi-Language]")
        self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")

    def test_screen_metadata_auxiliary_and_unknown_extents_remain_strict(self):
        for before, after in ((b"OriginalPageField=kept", b"OriginalPageField=changed"),
                              (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nOpaque=1\r\n"),
                              (b"[AuxKeyElement]\r\n", b"[Element]\r\nnPartsID=20\r\n[AuxKeyElement]\r\n"),
                              (b"[State]\r\nValue=0", b"[UnknownOwner]\r\n[State]\r\nValue=0")):
            with self.subTest(after=after[:30]):
                self.assertError(lambda: self.change(before, after).verify_layout_order(self.schema, self.adapter))

    def test_order_raw_spelling_addition_removal_and_screen_element_state_sequence_cannot_change(self):
        for before, after in ((b"Order=0\r\n", b"Order=00\r\n"), (b"Order=0\r\n", b""),
                              (b"nPartsID=2\r\n", b"nPartsID=2\r\nOrder=0\r\n"),
                              (b"Order=0007\r\n", b"Order=7\r\n"),
                              (b"Value=0\r\n", b"Value=2\r\n"),
                              (b"nPartsID=2\r\n", b"nPartsID=20\r\n"), (b"ID=2\r\n", b"ID=20\r\n")):
            with self.subTest(after=after):
                self.assertError(lambda: self.change(before, after).verify_layout_order(self.schema, self.adapter))
        document = deepcopy(self.adapter.document)
        screens = [index for index, section in enumerate(document.sections) if section.name == "Screen"]
        first, second = document.sections[screens[0]:screens[1]], document.sections[screens[1]:screens[2]]
        document.sections[screens[0]:screens[2]] = second + first
        candidate = NativeAdapter(self.adapter.envelope.encode(document.bytes()), self.adapter.family)
        self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")
        document = deepcopy(self.adapter.document)
        start = next(index for index, section in enumerate(document.sections) if section.name == "Element")
        document.sections[start:start + 6] = document.sections[start + 3:start + 6] + document.sections[start:start + 3]
        candidate = NativeAdapter(self.adapter.envelope.encode(document.bytes()), self.adapter.family)
        self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")
        document = deepcopy(self.adapter.document)
        document.sections[start + 1], document.sections[start + 2] = document.sections[start + 2], document.sections[start + 1]
        candidate = NativeAdapter(self.adapter.envelope.encode(document.bytes()), self.adapter.family)
        self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")

    def test_structural_and_global_resource_operations_are_closed_even_when_noop(self):
        operations = ({"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "1", "element_id": "20"},
                      {"op": "clone_screen", "source_screen": "1", "screen_id": "20", "name": "New"},
                      {"op": "delete_element", "screen_id": "1", "element_id": "1"},
                      {"op": "rename_screen", "screen_id": "1", "name": "Page 1"},
                      {"op": "reorder_elements", "screen_id": "1", "element_ids": ["1", "2", "3"]},
                      {"op": "reorder_screens", "screen_ids": ["1", "2", "3"]},
                      {"op": "configure_alarm", "expected_alarm_sha256": "0" * 64, "updates": []},
                      {"op": "configure_macro", "owner": {"kind": "application"}, "field": "InitialMacroLen", "statements": [], "expected_program_sha256": "0" * 64})
        for operation in operations:
            with self.subTest(operation=operation["op"]):
                self.assertError(lambda: self.adapter.apply([operation], self.profile), "PRESERVED_LAYOUT_SCOPE")
        operation = {"op": "set_property", "screen_id": "1", "element_id": "1", "key": "order", "value": 0}
        self.assertEqual(self.adapter.apply([operation], self.profile), self.source)
        self.assertError(lambda: self.adapter.apply([operation | {"value": 1}], self.profile), "PRESERVED_LAYOUT_MISMATCH")

    def test_state_identity_and_geometry_have_no_implicit_defaults(self):
        for before, after in ((b"Value=0\r\n", b""), (b"Value=1\r\n", b"Value=0\r\n")):
            changed = self.change(before, after)
            profile = qualify_preserved_layout(changed.original, self.profile)
            self.assertError(lambda: changed.verify_layout_order(profile["native_schema"]))
        operation = {"op": "set_property", "screen_id": "1", "element_id": "1", "key": "x", "value": -1}
        self.assertError(lambda: self.adapter.apply([operation], self.profile))
        changed = self.change(b"Height=20\r\n", b"")
        profile = qualify_preserved_layout(changed.original, self.profile)
        self.assertError(lambda: changed.apply([], profile), "UNQUALIFIED_GEOMETRY")
        self.assertError(lambda: changed.apply([operation | {"value": 11}], profile), "UNQUALIFIED_GEOMETRY")
        for before, after in ((b"X=10\r\n", b"X=-1\r\n"), (b"Width=30\r\n", b"Width=0\r\n")):
            changed = self.change(before, after)
            profile = qualify_preserved_layout(changed.original, self.profile)
            self.assertError(lambda: changed.apply([], profile), "NATIVE_GEOMETRY")

    def test_full_owner_extent_digest_includes_identity_geometry_unknown_headers_and_every_state(self):
        original = self.adapter.owner_extent_sha256("1", "1")
        for before, after in ((b"X=10\r\n", b"X=11\r\n"), (b"nPartsID=1\r\n", b"nPartsID=20\r\n"),
                              (b"UnknownBinary=\xff\x00\x82\r\n", b"UnknownBinary=\xfe\x00\x82\r\n"),
                              (_wide("wTextLen0", "ON"), _wide("wTextLen0", "ALTERED"))):
            with self.subTest(before=before[:20]):
                candidate = self.change(before, after)
                eid = "20" if before.startswith(b"nPartsID") else "1"
                self.assertNotEqual(candidate.owner_extent_sha256("1", eid), original)
        changed = NativeAdapter(self.source, self.adapter.family)
        first_state = next(section for section in changed.document.sections if section.name == "State")
        first_state.header += b"\r\n"
        self.assertNotEqual(changed.owner_extent_sha256("1", "1"), original)
        self.assertError(lambda: self.change(b"[State]\r\nValue=0", b"[UnknownOwner]\r\n[State]\r\nValue=0").owner_extent_sha256("1", "1"))

    def test_saved_candidate_thumbnail_prefix_tail_and_mutated_source_object_are_not_rebased(self):
        for source in (self.adapter.envelope.encode(self.adapter.envelope.body + b"extra"),
                       Envelope(self.adapter.envelope.thumbnail[:-1] + b"X", self.adapter.envelope.prefix, b"").encode(self.adapter.envelope.body),
                       Envelope(self.adapter.envelope.thumbnail, b"X" + self.adapter.envelope.prefix[1:], b"").encode(self.adapter.envelope.body)):
            candidate = NativeAdapter(source, self.adapter.family)
            self.assertError(lambda: candidate.verify_layout_order(self.schema, self.adapter), "PRESERVED_LAYOUT_MISMATCH")
        self.adapter.application.one("Unknown").set_value(b"mutated")
        self.assertError(lambda: self.adapter.verify_layout_order(self.schema), "INVALID_PRESERVED_CANDIDATE")

    def test_saved_candidate_rejects_independent_document_and_record_metadata_projection(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            with self.subTest(family=family):
                source, profile = preserved_layout_fixture(family)
                original = NativeAdapter(source, family)
                operation = {"op": "set_property", "screen_id": "1", "element_id": "1", "key": "x", "value": 11}
                expected = NativeAdapter(original.apply([operation], profile), family)
                self.assertTrue(expected.verify_layout_order(profile["native_schema"], original))
                forged = NativeAdapter(source, family)
                forged.document = deepcopy(expected.document)
                self.assertEqual(forged.original, source)
                self.assertEqual(forged.envelope.body, original.envelope.body)
                self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], original), "INVALID_PRESERVED_CANDIDATE")
                forged = NativeAdapter(source, family)
                element = next(section for section in forged.document.sections if section.name == "Element")
                element.one("X").value = b"11"  # Raw bytes still say 10.
                self.assertEqual(forged.document.bytes(), original.envelope.body)
                self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], original), "INVALID_PRESERVED_CANDIDATE")
                forged = NativeAdapter(source, family)
                next(section for section in forged.document.sections if section.name == "State").name = "Element"
                self.assertEqual(forged.document.bytes(), original.envelope.body)
                self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], original), "INVALID_PRESERVED_CANDIDATE")

    def test_saved_candidate_rejects_forged_envelope_and_cached_identity(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            source, profile = preserved_layout_fixture(family)
            original = NativeAdapter(source, family)
            for kind in ("thumbnail", "prefix", "body", "model", "version", "application", "family"):
                with self.subTest(family=family, kind=kind):
                    forged = NativeAdapter(source, family)
                    envelope = forged.envelope
                    if kind == "thumbnail":
                        forged.envelope = Envelope(envelope.thumbnail[:-1] + b"X", envelope.prefix, envelope.body)
                    elif kind == "prefix":
                        forged.envelope = Envelope(envelope.thumbnail, b"X" + envelope.prefix[1:], envelope.body)
                    elif kind == "body":
                        forged.envelope = Envelope(envelope.thumbnail, envelope.prefix, envelope.body.replace(b"X=10\r\n", b"X=11\r\n", 1))
                    elif kind == "model":
                        forged.model_id = "OTHER"
                    elif kind == "version":
                        forged.editor_version = "9.9"
                    elif kind == "application":
                        forged.application = deepcopy(forged.application)
                        forged.application.one("PanelName").set_value(b"Detached application")
                    else:
                        forged.family = "delta_diascreen" if family == "delta_dopsoft2" else "delta_dopsoft2"
                    self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], original), "INVALID_PRESERVED_CANDIDATE")

    def test_original_source_projection_binding_remains_required(self):
        candidate = self.change(b"X=10\r\n", b"X=11\r\n")
        self.assertTrue(candidate.verify_layout_order(self.schema, self.adapter))
        original = NativeAdapter(self.source, self.adapter.family)
        original.editor_version = "9.9"
        self.assertError(lambda: candidate.verify_layout_order(self.schema, original), "INVALID_PRESERVED_SOURCE")
        original = NativeAdapter(self.source, self.adapter.family)
        original.application.one("Unknown").value = b"Forged cache"
        self.assertEqual(original.document.bytes(), original.envelope.body)
        self.assertError(lambda: candidate.verify_layout_order(self.schema, original), "INVALID_PRESERVED_SOURCE")


class LiteralGenerationTests(unittest.TestCase):
    def setUp(self):
        self.source, self.profile = literal_generation_fixture()
        self.adapter = NativeAdapter(self.source, self.profile["family"])
        self.schema = self.profile["native_schema"]

    @staticmethod
    def operations():
        return [{"op": "append_literal_page", "screen_id": "7", "name": "Yeni ölçüm"},
                {"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "7", "element_id": "20"},
                {"op": "set_property", "screen_id": "7", "element_id": "20", "key": "x", "value": 40},
                {"op": "set_text", "screen_id": "7", "element_id": "20", "state_index": 0, "language": 0, "text": "Başlık 🔧"}]

    def candidate(self):
        return NativeAdapter(self.adapter.apply(self.operations(), self.profile), self.adapter.family)

    def changed(self, adapter, before, after):
        return NativeAdapter(adapter.envelope.encode(adapter.envelope.body.replace(before, after, 1)), adapter.family)

    def assertError(self, call, code=None):
        with self.assertRaises(HmiError) as context:
            call()
        if code:
            self.assertEqual(context.exception.code, code)

    def test_both_families_append_actual_blocks_preserve_globals_source_and_opaque_envelope(self):
        for family in ("delta_dopsoft2", "delta_diascreen"):
            with self.subTest(family=family):
                source, profile = literal_generation_fixture(family)
                adapter = NativeAdapter(source, family)
                self.assertEqual(adapter.apply([], profile), source)
                candidate = NativeAdapter(adapter.apply(self.operations(), profile), family)
                self.assertTrue(candidate.verify_layout_order(profile["native_schema"], adapter))
                self.assertEqual(candidate.envelope.thumbnail, adapter.envelope.thumbnail)
                self.assertEqual(candidate.envelope.prefix, adapter.envelope.prefix)
                self.assertEqual(candidate.document.tail, adapter.document.tail)
                self.assertEqual(candidate._preserved_prefix(candidate.document), adapter._preserved_prefix(adapter.document))
                self.assertTrue(candidate.document.bytes().startswith(adapter.document.bytes()[:-len(adapter.document.tail)]))
                page = candidate.inspect()["screens"][-1]
                self.assertEqual((page["id"], page["name"]), ("7", "Yeni ölçüm"))
                self.assertEqual(len(page["elements"]), 1)
                owner = page["elements"][0]
                self.assertEqual((owner["id"], owner["type"], owner["subtype"]), ("20", "10", "6"))
                self.assertEqual(owner["geometry"], {"x": 40, "y": 10, "width": 30, "height": 20})
                self.assertEqual(owner["texts"][0]["text"], "Başlık 🔧")
                self.assertEqual(adapter.original, source)

    def test_header_only_page_copies_no_bound_numeric_function_or_state_objects(self):
        output = self.adapter.apply(self.operations()[:1], self.profile)
        candidate = NativeAdapter(output, self.adapter.family)
        self.assertEqual(candidate.inspect()["screens"][-1]["elements"], [])
        self.assertTrue(candidate.verify_layout_order(self.schema, self.adapter))
        self.assertEqual(sum(section.name == "Element" for section in candidate.document.sections), 2)

    def test_multiple_new_pages_and_owners_keep_transaction_order_without_identity_sorting(self):
        operations = self.operations()[:2] + [
            {"op": "append_literal_page", "screen_id": "4", "name": "Second"},
            {"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "7", "element_id": "10"},
            {"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "4", "element_id": "30"}]
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        self.assertEqual([page["id"] for page in candidate.inspect()["screens"]], ["1", "7", "4"])
        self.assertEqual([element["id"] for element in candidate.inspect()["screens"][1]["elements"]], ["20", "10"])

    def test_literal_clone_always_uses_original_donor_after_new_owner_mutation(self):
        operations = self.operations() + [
            {"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "7", "element_id": "21"}]
        candidate = NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family)
        last = candidate.inspect()["screens"][-1]["elements"][-1]
        self.assertEqual(last["texts"][0]["text"], "SOURCE")
        self.assertEqual(last["geometry"]["x"], 10)
        invalid = operations[:-1] + [dict(operations[-1], source_screen="7", source_element="20")]
        self.assertError(lambda: self.adapter.apply(invalid, self.profile), "LITERAL_GENERATION_SCOPE")

    def test_global_owner_collisions_source_and_other_new_pages_rejected(self):
        for identity in ("1", "2", "0", "01", "-1", "2147483648"):
            with self.subTest(identity=identity):
                operations = self.operations()[:2]
                operations[1]["element_id"] = identity
                self.assertError(lambda: self.adapter.apply(operations, self.profile))
        operations = self.operations()[:2] + [
            {"op": "append_literal_page", "screen_id": "4", "name": "Other"},
            {"op": "clone_element", "source_screen": "1", "source_element": "1", "target_screen": "4", "element_id": "20"}]
        self.assertError(lambda: self.adapter.apply(operations, self.profile), "DUPLICATE_ELEMENT")

    def test_new_page_id_positive_canonical_and_fresh(self):
        for identity in ("1", "0", "07", "-1", 7, True, "2147483648"):
            with self.subTest(identity=identity):
                self.assertError(lambda: self.adapter.apply([dict(self.operations()[0], screen_id=identity)], self.profile))
        self.assertError(lambda: self.adapter.apply(self.operations()[:1] * 2, self.profile), "DUPLICATE_SCREEN")

    def test_original_owner_edits_and_clone_target_source_page_are_rejected(self):
        for operation in (dict(self.operations()[2], screen_id="1", element_id="1"),
                          dict(self.operations()[3], screen_id="1", element_id="1"),
                          dict(self.operations()[1], target_screen="1")):
            with self.subTest(operation=operation):
                self.assertError(lambda: self.adapter.apply([operation], self.profile), "LITERAL_GENERATION_SCOPE")

    def test_every_other_native_operation_is_rejected_even_if_noop(self):
        for operation in ({"op": "clone_screen", "source_screen": "1", "screen_id": "7", "name": "X"},
                          {"op": "rename_screen", "screen_id": "1", "name": "Original"},
                          {"op": "reorder_screens", "screen_ids": ["1"]},
                          {"op": "reorder_elements", "screen_id": "1", "element_ids": ["1", "2"]},
                          {"op": "delete_element", "screen_id": "1", "element_id": "2"},
                          {"op": "bind", "screen_id": "7", "element_id": "20", "read": "None"},
                          {"op": "configure_numeric"}, {"op": "configure_goto"}, {"op": "configure_macro"},
                          {"op": "configure_alarm"}, {"op": "set_unit_caption"}):
            with self.subTest(operation=operation["op"]):
                self.assertError(lambda: self.adapter.apply(self.operations()[:2] + [operation], self.profile), "LITERAL_GENERATION_SCOPE")

    def test_append_operation_closed_outside_distinct_literal_contract(self):
        self.assertError(lambda: NativeAdapter(synthetic_file(), "delta_diascreen").apply(self.operations()[:1], synthetic_profile()), "UNQUALIFIED_LITERAL_GENERATION")
        source, profile = preserved_layout_fixture()
        self.assertError(lambda: NativeAdapter(source, "delta_dopsoft2").apply(self.operations()[:1], profile), "PRESERVED_LAYOUT_SCOPE")

    def test_exact_operation_shapes_and_unknown_arguments_rejected(self):
        for index in range(4):
            for alteration in ("extra", "missing"):
                operations = self.operations()
                if alteration == "extra":
                    operations[index]["extra"] = 1
                else:
                    operations[index].pop(next(key for key in operations[index] if key != "op"))
                with self.subTest(index=index, alteration=alteration):
                    self.assertError(lambda: self.adapter.apply(operations, self.profile))
        for operation in (None, [], {"op": []}, {"op": "made_up"}):
            self.assertError(lambda: self.adapter.apply([operation], self.profile))

    def test_literal_geometry_property_mapping_cannot_redirect_or_change_kind_style(self):
        for key in ("color", "behavior", "order", [], None):
            operations = self.operations()[:3]
            operations[2]["key"] = key
            self.assertError(lambda: self.adapter.apply(operations, self.profile))
        for spec in ({"field": "Type", "type": "int"}, {"field": "X", "type": "enum", "values": {"go": 11}},
                     {"field": "X", "type": "int", "scope": "state"}):
            profile = deepcopy(self.profile)
            profile["native_schema"]["properties"]["x"] = spec
            self.assertError(lambda: self.adapter.apply(self.operations()[:3], profile), "LITERAL_GENERATION_SCOPE")

    def test_geometry_bounds_and_boolean_values_fail_without_partial_source_mutation(self):
        for key, value in (("x", 71), ("y", 61), ("width", 91), ("height", 71),
                           ("x", -1), ("width", 0), ("height", -1), ("x", True), ("x", "4")):
            operations = self.operations()[:2] + [dict(self.operations()[2], key=key, value=value)]
            with self.subTest(key=key, value=value):
                self.assertError(lambda: self.adapter.apply(operations, self.profile))
                self.assertEqual(self.adapter.document.bytes(), self.adapter.envelope.body)
                self.assertEqual(self.adapter.original, self.source)

    def test_caption_only_primary_state_and_language_with_complete_unicode_framing(self):
        for state, language in ((1, 0), (0, 1), (True, 0), (0, False), ("0", 0)):
            operations = self.operations()[:2] + [dict(self.operations()[3], state_index=state, language=language)]
            self.assertError(lambda: self.adapter.apply(operations, self.profile), "LITERAL_GENERATION_SCOPE")
        for text in (None, "bad\0caption", "\ud800"):
            self.assertError(lambda: self.adapter.apply(self.operations()[:2] + [dict(self.operations()[3], text=text)], self.profile))
        operations = self.operations()[:2] + [dict(self.operations()[3], text="")]
        self.assertEqual(NativeAdapter(self.adapter.apply(operations, self.profile), self.adapter.family).inspect()["screens"][-1]["elements"][0]["texts"][0]["text"], "")

    def test_literal_contract_exact_shapes_fingerprints_donors_and_mode(self):
        for key, value in (("qualified", 1), ("contract_version", True), ("mode", "existing_owner_edits"),
                           ("source_sha256", "0" * 64), ("prefix_sha256", "G" * 64), ("sections", []),
                           ("page_donor", {}), ("text_donor", None)):
            profile = deepcopy(self.profile)
            profile["native_schema"]["literal_generation"][key] = value
            self.assertError(lambda: self.adapter.apply([], profile))
        profile = deepcopy(self.profile)
        profile["native_schema"]["literal_generation"]["extra"] = 1
        self.assertError(lambda: self.adapter.apply([], profile))
        for pin, key, value in (("page_donor", "header_sha256", "0" * 64), ("page_donor", "aux_sha256", "0" * 64),
                                ("text_donor", "owner_sha256", "0" * 64), ("text_donor", "element_id", "2"),
                                ("page_donor", "screen_id", "9")):
            profile = deepcopy(self.profile)
            profile["native_schema"]["literal_generation"][pin][key] = value
            self.assertError(lambda: self.adapter.apply([], profile))
        profile = deepcopy(self.profile)
        profile["native_schema"]["preserved_layout"] = {}
        self.assertError(lambda: self.adapter.apply([], profile), "UNQUALIFIED_LITERAL_GENERATION")

    def test_source_donor_behavior_address_and_unknown_variants_rejected_after_repin(self):
        variants = [(b"ReadVar=None\r\n", b"ReadVar=!D5\r\n"), (b"WriteVar=None\r\n", b"WriteVar=!D5\r\n"),
                    (b"OffsetReadVar=None\r\n", b"OffsetReadVar=!D5\r\n"), (b"OffsetWriteVar=None\r\n", b"OffsetWriteVar=!D5\r\n"),
                    (b"VisibleVar=None\r\n", b"VisibleVar=!M1\r\n"), (b"ScreenLockVar=None\r\n", b"ScreenLockVar=!M1\r\n"),
                    (b"GroupID=0\r\n", b"GroupID=1\r\n"), (b"PosVary=0\r\n", b"PosVary=1\r\n"),
                    (b"ScreenAction=0\r\n", b"ScreenAction=1\r\n"), (b"BaseScreenID=0\r\n", b"BaseScreenID=2\r\n"),
                    (b"Type=10\r\n", b"Type=1\r\n"), (b"SubType=6\r\n", b"SubType=3\r\n"),
                    (b"OpenMacroLen=0\r\n", b"OpenMacroLen=4\r\nxx\r\n"), (b"Value=0\r\n", b"Value=1\r\n"),
                    (b"VER=16\r\n", b"VER=17\r\n"),
                    (_wide("wTitleTextLen000", ""), _wide("wTitleTextLen000", "Old title"))]
        for key in (b"SoundIndex", b"Twinkles", b"UsePictureCoord", b"TransEffect", b"TransColor", b"StretchMode", b"PictureStretch", b"Style", b"Level"):
            variants.append((key + b"=0\r\n", key + b"=7\r\n"))
        for key in (b"Order", b"Variation", b"Action", b"FunctionKey", b"GoToScreenID", b"BeforeExecMacroLen", b"PictureID", b"UnknownFlag"):
            variants.append((b"Type=10\r\n", b"Type=10\r\n" + key + b"=0\r\n"))
        for before, after in variants:
            with self.subTest(variant=after):
                source = self.changed(self.adapter, before, after).original
                profile = qualify_literal_generation(source, self.profile)
                self.assertError(lambda: NativeAdapter(source, self.adapter.family).apply([], profile))

    def test_exact_observed_description_language_zero_variant_is_preserved(self):
        source = self.changed(self.adapter, b"wDescTextLen=2\r\n", b"wDescTextLen0=2\r\n").original
        profile = qualify_literal_generation(source, self.profile)
        adapter = NativeAdapter(source, self.adapter.family)
        output = adapter.apply(self.operations(), profile)
        candidate = NativeAdapter(output, adapter.family)
        self.assertEqual(adapter.envelope.body.count(b"wDescTextLen0=2\r\n"), 1)
        self.assertEqual(candidate.envelope.body.count(b"wDescTextLen0=2\r\n"), 2)
        self.assertTrue(candidate.verify_layout_order(profile["native_schema"], adapter))

    def test_missing_repeated_unkeyed_and_secondary_caption_donor_fields_fail(self):
        for before, after in ((b"VisibleVar=None\r\n", b""), (b"ReadVar=None\r\n", b"ReadVar=None\r\nReadVar=None\r\n"),
                              (b"FontName0=Arial\r\n", b"FontName0=Arial\r\n\r\n"),
                              (b"FontName0=Arial\r\n", b"FontName0=Arial\r\n" + _wide("wTextLen1", "Other")),
                              (b"ScreenLockVar=None\r\n", b""), (b"RefreshRate=2\r\n", b"RefreshRate=2\r\nUnknown=0\r\n"),
                              (_wide("wTextLen0", "SOURCE"), b"wTextLen0=0\r\n")):
            with self.subTest(variant=after):
                self.assertError(lambda: NativeAdapter(self.changed(self.adapter, before, after).original, self.adapter.family).apply(
                    [], qualify_literal_generation(self.changed(self.adapter, before, after).original, self.profile)))

    def test_missing_known_companions_never_infer_vendor_defaults_after_repin(self):
        for key, value in (("SoundIndex", "0"), ("Twinkles", "0"), ("TransEffect", "0"), ("Level", "0"),
                           ("GroupID", "0"), ("FontName0", "Arial"), ("SmoothFont", "1"), ("IsUseFrame", "1"),
                           ("HardCopyRight", "99"), ("CycleMacroDelayTime", "100")):
            source = self.changed(self.adapter, (key + "=" + value + "\r\n").encode(), b"").original
            profile = qualify_literal_generation(source, self.profile)
            self.assertError(lambda: NativeAdapter(source, self.adapter.family).apply([], profile), "UNQUALIFIED_LITERAL_SHAPE")
        source = self.changed(self.adapter, _wide("wDescTextLen", ""), _wide("wDescTextLen", "") + _wide("wDescTextLen0", "")).original
        self.assertError(lambda: NativeAdapter(source, self.adapter.family).apply([], qualify_literal_generation(source, self.profile)), "UNQUALIFIED_LITERAL_SHAPE")

    def test_source_pin_is_immutable_and_candidate_needs_actual_original(self):
        candidate = self.candidate()
        self.assertError(lambda: candidate.verify_layout_order(self.schema), "INVALID_LITERAL_SOURCE")
        self.assertError(lambda: candidate.apply([], self.profile), "INVALID_LITERAL_SOURCE")
        for before, after in ((b"Version=0.0\r\n", b"Version=0.00\r\n"), (b"NeutralRetained=A\r\n", b"NeutralRetained=C\r\n")):
            changed = self.changed(self.adapter, before, after)
            self.assertError(lambda: candidate.verify_layout_order(self.schema, changed))

    def test_mutated_original_owner_header_and_extra_sections_cannot_pass_saved_verifier(self):
        candidate = self.candidate()
        for before, after in ((b"ReadVar=!D1\r\n", b"ReadVar=!D2\r\n"), (b"BgColor=16579836\r\n", b"BgColor=1\r\n"),
                              (b"[AuxKeyElement]\r\n", b"[AuxKeyElement]\r\nX=1\r\n"),
                              (b"nPartsID=2\r\n", b"nPartsID=2\r\nOrder=1\r\n")):
            self.assertError(lambda: self.changed(candidate, before, after).verify_layout_order(self.schema, self.adapter))
        for body in (candidate.envelope.body.replace(b"[Screen]\r\nVER=16\r\nID=7", b"[Unknown]\r\nX=0\r\n[Screen]\r\nVER=16\r\nID=7"),
                     candidate.envelope.body.replace(b"nPartsID=20\r\n", b"nPartsID=20\r\nOrder=0\r\n"),
                     candidate.envelope.body.replace(_wide("wTextLen0", "Başlık 🔧"), _wide("wTextLen0", "Başlık 🔧") + b"[State]\r\nValue=1\r\n")):
            self.assertError(lambda: NativeAdapter(candidate.envelope.encode(body), candidate.family).verify_layout_order(self.schema, self.adapter))

    def test_new_header_owner_and_state_only_managed_records_may_change(self):
        candidate = self.candidate()
        prefix, added = candidate.envelope.body.split(b"[Screen]\r\nVER=16\r\nID=7", 1)
        for before, after in ((b"Style=0\r\n", b"Style=1\r\n"), (b"FontColor=0\r\n", b"FontColor=1\r\n"),
                              (b"ScreenAction=0\r\n", b"ScreenAction=1\r\n"), (b"Width=30\r\n", b"Width=0\r\n"),
                              (b"nPartsID=20\r\n", b"nPartsID=2\r\n"), (b"Value=0\r\n", b"Value=1\r\n"),
                              (b"Type=10\r\n", b"Type=6\r\n")):
            body = prefix + b"[Screen]\r\nVER=16\r\nID=7" + added.replace(before, after, 1)
            self.assertError(lambda: NativeAdapter(candidate.envelope.encode(body), candidate.family).verify_layout_order(self.schema, self.adapter))

    def test_saved_candidate_detached_projection_and_original_caches_fail(self):
        for target in ("candidate", "source"):
            for variant in ("raw", "value", "envelope", "model", "version", "application"):
                candidate, original = self.candidate(), NativeAdapter(self.source, self.adapter.family)
                modified = candidate if target == "candidate" else original
                if variant == "raw":
                    modified.document.sections[-1].records[0].raw = b"Value=9\r\n"
                elif variant == "value":
                    modified.document.sections[-1].records[0].value = b"9"
                elif variant == "envelope":
                    modified.envelope = Envelope(modified.envelope.thumbnail, b"x" * 41, modified.envelope.body)
                elif variant == "model":
                    modified.model_id = "OTHER"
                elif variant == "version":
                    modified.editor_version = "9.0"
                else:
                    modified.application = deepcopy(modified.application)
                    modified.application.one("PanelName").value = b"Cached only"
                self.assertError(lambda: candidate.verify_layout_order(self.schema, original))

    def test_candidate_thumbnail_opaque_prefix_tail_and_global_bytes_preserved(self):
        candidate = self.candidate()
        envelopes = [Envelope(candidate.envelope.thumbnail[:-1] + b"X", candidate.envelope.prefix, candidate.envelope.body),
                     Envelope(candidate.envelope.thumbnail, b"x" * 41, candidate.envelope.body)]
        for envelope in envelopes:
            self.assertError(lambda: NativeAdapter(envelope.encode(candidate.envelope.body), candidate.family).verify_layout_order(self.schema, self.adapter))
        self.assertError(lambda: self.changed(candidate, b"OpaqueNeutralTail", b"ChangedNeutralTail").verify_layout_order(self.schema, self.adapter))
        self.assertError(lambda: self.changed(candidate, b"NeutralRetained=A\r\n", b"NeutralRetained=C\r\n").verify_layout_order(self.schema, self.adapter))


class ControlGenerationTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.profile = control_generation_fixture()
        self.adapter = NativeAdapter(self.raw, self.profile["family"])
        self.schema = self.profile["native_schema"]

    def operations(self, kinds=("set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display")):
        operations = []
        for index, kind in enumerate(kinds, 20):
            pin = self.schema["control_generation"]["donors"][kind]
            eid = str(index)
            operations.append({"op": "clone_element", "source_screen": pin["screen_id"], "source_element": pin["element_id"], "target_screen": "1", "element_id": eid})
            direction, address = ("read", "{Link2}1@D0") if kind == "numeric_display" else ("write", "{Link2}1@D0" if kind == "numeric_input" else "{Link2}1@M0")
            operations.append({"op": "bind", "screen_id": "1", "element_id": eid, direction: {"address": address, "link": 1, "mem_type": 0}})
            operations.append({"op": "set_property", "screen_id": "1", "element_id": eid, "key": "x", "value": 55})
            if not kind.startswith("numeric_"):
                operations += [{"op": "set_text", "screen_id": "1", "element_id": eid, "state_index": state, "language": 0,
                                "text": "ÜFLEME AÇIK" if state else "ÜFLEME KAPALI"} for state in (0, 1)]
            else:
                operation = {"op": "configure_numeric", "screen_id": "1", "element_id": eid, "kind": kind, "data_type": "UINT",
                             "integer_digits": 5, "fractional_digits": 0, "gain": 1, "offset": 0}
                if kind == "numeric_input":
                    operation.update(minimum=0, maximum=65535)
                operations.append(operation)
        return operations

    def changed(self, adapter, before, after):
        body = adapter.envelope.body
        self.assertIn(before, body)
        return NativeAdapter(adapter.envelope.encode(body.replace(before, after, 1)), adapter.family)

    def assertError(self, call, code=None):
        with self.assertRaises(HmiError) as caught:
            call()
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_source_contract_noop_and_all_six_appended_controls(self):
        from universal_hmi.native.__init__ import _groups
        self.assertEqual(self.adapter.apply([], self.profile), self.raw)
        self.assertEqual(set(self.adapter.control_donors(self.schema)), {"set_on", "set_off", "momentary", "maintained", "numeric_input", "numeric_display"})
        output = self.adapter.apply(self.operations(), self.profile)
        candidate = NativeAdapter(output, self.profile["family"])
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        owners = _groups(candidate.document)[0]["elements"]
        self.assertEqual([owner["id"] for owner in owners], ["1", "2", "3", "4", "5", "6", "20", "21", "22", "23", "24", "25"])
        for identity in range(1, 7):
            self.assertEqual(candidate.owner_extent_sha256("1", str(identity)), self.adapter.owner_extent_sha256("1", str(identity)))
        self.assertEqual(owners[6]["states"][0].one("wTextLen0").text(), "ÜFLEME KAPALI")
        self.assertEqual(owners[6]["states"][1].one("wTextLen0").text(), "ÜFLEME AÇIK")
        self.assertEqual(candidate.envelope.prefix[:37], self.adapter.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
        self.assertEqual(candidate.document.tail, self.adapter.document.tail)
        self.assertEqual(self.adapter.original, self.raw)

    def test_explicit_state_color_font_and_source_clone_not_mutated_donor(self):
        ops = self.operations(("maintained",))
        ops += [{"op": "set_property", "screen_id": "1", "element_id": "20", "state_index": 1, "key": key, "value": value}
                for key, value in (("state_fill", 0x228822), ("color", 0xFFFFFF), ("font_size", 22))]
        ops += self.operations(("maintained",))[0:2]
        ops[-2]["element_id"], ops[-1]["element_id"] = "30", "30"
        output = self.adapter.apply(ops, self.profile)
        candidate = NativeAdapter(output, self.profile["family"])
        self.assertTrue(candidate.verify_control_generation(self.schema, self.adapter))
        from universal_hmi.native.__init__ import _element, _screen
        owner = _element(_screen(candidate.document, "1"), "30")
        self.assertEqual(owner["states"][1].one("wTextLen0").text(), "")
        self.assertEqual(owner["states"][1].one("FontSize0").value, b"12")

    def test_contract_exact_pins_property_witness_and_distinct_mode(self):
        cases = []
        for key, value in (("source_sha256", "0" * 64), ("prefix_sha256", "0" * 64), ("mode", "literal_page_generation"),
                           ("qualified", 1), ("contract_version", True), ("address_prefix", "{Link1}1@"), ("extra", 1)):
            p = deepcopy(self.profile); p["native_schema"]["control_generation"][key] = value; cases.append(p)
        for key in ("property_witness_sha256", "owner_sha256"):
            p = deepcopy(self.profile); p["native_schema"]["control_generation"]["donors"]["maintained"].pop(key); cases.append(p)
        p = deepcopy(self.profile); p["native_schema"]["control_generation"]["donors"]["maintained"] = deepcopy(p["native_schema"]["control_generation"]["donors"]["momentary"]); cases.append(p)
        p = deepcopy(self.profile); p["native_schema"]["control_generation"]["pages"][0]["header_sha256"] = "0" * 64; cases.append(p)
        for key in ("literal_generation", "preserved_layout"):
            p = deepcopy(self.profile); p["native_schema"][key] = {}; cases.append(p)
        for p in cases:
            with self.subTest(contract=p["native_schema"]["control_generation"]):
                self.assertError(lambda: self.adapter.apply([], p))

    def test_original_owners_cannot_be_mutated_and_new_pages_closed(self):
        forbidden = [{"op": "set_text", "screen_id": "1", "element_id": "1", "state_index": 0, "language": 0, "text": "changed"},
                     {"op": "set_property", "screen_id": "1", "element_id": "1", "key": "x", "value": 20},
                     {"op": "bind", "screen_id": "1", "element_id": "1", "write": {"address": "{Link2}1@M0", "link": 1, "mem_type": 0}},
                     {"op": "append_literal_page", "screen_id": "2", "name": "new"},
                     {"op": "delete_element", "screen_id": "1", "element_id": "1"}]
        for operation in forbidden:
            self.assertError(lambda: self.adapter.apply([operation], self.profile), "CONTROL_GENERATION_SCOPE")

    def test_clone_identity_and_immutable_donor_scope(self):
        clone = self.operations(("set_on",))[0]
        for change in ({"element_id": "0"}, {"element_id": "1"}, {"source_element": "99"}, {"target_screen": "2"}, {"source_screen": "2"}):
            self.assertError(lambda: self.adapter.apply([clone | change], self.profile))
        ops = self.operations(("set_on",))
        self.assertError(lambda: self.adapter.apply(ops + [clone | {"source_element": "20", "element_id": "30"}], self.profile), "CONTROL_GENERATION_SCOPE")
        self.assertError(lambda: self.adapter.apply(ops + [clone], self.profile), "DUPLICATE_ELEMENT")

    def test_exact_captured_address_and_metadata_only(self):
        for address in ("{Link2}1@M1", "{Link1}1@M0", "{Link2}2@M0", "{Link2}1@M00", "{Link2}1@D0", "None", "!M0"):
            ops = self.operations(("maintained",)); ops[1]["write"]["address"] = address
            self.assertError(lambda: self.adapter.apply(ops, self.profile), "CONTROL_ADDRESS_SCOPE")
        for key in ("link", "mem_type"):
            ops = self.operations(("maintained",)); ops[1]["write"][key] = 2
            self.assertError(lambda: self.adapter.apply(ops, self.profile), "CONTROL_ADDRESS_SCOPE")
        ops = self.operations(("numeric_input",)); ops[1]["write"]["address"] = "{Link2}1@D1"
        self.assertError(lambda: self.adapter.apply(ops, self.profile), "CONTROL_ADDRESS_SCOPE")
        ops = self.operations(("numeric_display",)); ops[1]["write"] = {"address": "{Link2}1@D0", "link": 1, "mem_type": 0}
        self.assertError(lambda: self.adapter.apply(ops, self.profile), "CONTROL_ADDRESS_SCOPE")
        self.assertError(lambda: self.adapter.apply([self.operations(("maintained",))[0]], self.profile), "CONTROL_ADDRESS_SCOPE")

    def test_numeric_width_sign_time_scaling_limits_and_caption_rejected(self):
        for change in ({"data_type": "LREAL"}, {"data_type": "TIME"}, {"data_type": "INT"}, {"fractional_digits": 1},
                       {"minimum": -1}, {"maximum": 65536}, {"minimum": 4, "maximum": 3}, {"gain": 2}, {"integer_digits": 4}):
            ops = self.operations(("numeric_input",)); ops[-1].update(change)
            self.assertError(lambda: self.adapter.apply(ops, self.profile))
        ops = self.operations(("numeric_input",))
        ops.append({"op": "set_text", "screen_id": "1", "element_id": "20", "state_index": 0, "language": 0, "text": "unsafe"})
        self.assertError(lambda: self.adapter.apply(ops, self.profile), "CONTROL_GENERATION_SCOPE")
        for mutate in (lambda s: s["numeric"]["types"].update(INT={"MemLen": "1", "MemFmt": "1", "bits": 16, "format": "signed"}),
                       lambda s: s["numeric"].update(max_fractional_digits=1), lambda s: s["numeric"]["types"]["UINT"].update(bits=32)):
            p = deepcopy(self.profile); mutate(p["native_schema"])
            self.assertError(lambda: self.adapter.apply([], p), "UNQUALIFIED_CONTROL_NUMERIC")

    def test_unknown_active_macro_and_conditional_donors_fail_even_re_pinned(self):
        for before, after in ((b"PushTime=0\r\n", b"PushTime=1\r\n"), (b"VisibleVar=None\r\n", b"VisibleVar={Link2}1@M0\r\n"),
                              (b"OffsetWriteVar=None\r\n", b"OffsetWriteVar={Link2}1@D0\r\n"),
                              (b"ButtonOnMacroLen=0\r\n", b"ButtonOnMacroLen=4\r\nxx\r\n"),
                              (b"GroupID=0\r\n", b"GroupID=0\r\nUnknownBehavior=0\r\n"),
                              (b"UsePictureCoord=0\r\n", b"UsePictureCoord=1\r\n"),
                              (b"Twinkles=0\r\n", b"Twinkles=1\r\n")):
            changed = self.changed(self.adapter, before, after)
            profile = qualify_control_generation(changed.original, self.profile)
            self.assertError(lambda: changed.apply([], profile))

    def test_style_scope_geometry_state_and_language_guard(self):
        for operation in ({"op": "set_property", "screen_id": "1", "element_id": "20", "key": "width", "value": 0},
                          {"op": "set_property", "screen_id": "1", "element_id": "20", "key": "x", "value": 95},
                          {"op": "set_property", "screen_id": "1", "element_id": "20", "key": "behavior", "value": "set_off"},
                          {"op": "set_property", "screen_id": "1", "element_id": "20", "key": "state_fill", "state_index": 2, "value": 3},
                          {"op": "set_property", "screen_id": "1", "element_id": "20", "key": "color", "state_index": 1, "value": 0x1000000},
                          {"op": "set_property", "screen_id": "1", "element_id": "20", "key": "font_size", "state_index": 1, "value": 0},
                          {"op": "set_text", "screen_id": "1", "element_id": "20", "state_index": 0, "language": 1, "text": "bad"}):
            self.assertError(lambda: self.adapter.apply(self.operations(("maintained",)) + [operation], self.profile))
        p = deepcopy(self.profile); p["native_schema"]["properties"]["x"]["field"] = "Style"
        self.assertError(lambda: self.adapter.apply(self.operations(("maintained",)), p), "CONTROL_GENERATION_SCOPE")

    def test_final_verifier_detects_original_global_tail_and_new_owner_tampering(self):
        output = self.adapter.apply(self.operations(("maintained",)), self.profile)
        candidate = NativeAdapter(output, self.profile["family"])
        for before, after in ((b"NeutralRetained=A\r\n", b"NeutralRetained=C\r\n"), (b"ScreenAction=0\r\n", b"ScreenAction=1\r\n"),
                              (b"nPartsID=1\r\n", b"nPartsID=7\r\n"), (b"OpaqueNeutralTail", b"ChangedNeutralTail"),
                              (b"nPartsID=20\r\n", b"nPartsID=0\r\n")):
            self.assertError(lambda: self.changed(candidate, before, after).verify_control_generation(self.schema, self.adapter))
        from universal_hmi.native.__init__ import _element, _screen
        for key, value in (("WriteMemType", b"1"), ("Style", b"1"), ("WriteVar", b"{Link2}1@M1")):
            document = deepcopy(candidate.document)
            _element(_screen(document, "1"), "20")["section"].one(key).set_value(value)
            changed = NativeAdapter(candidate.envelope.encode(document.bytes()), candidate.family)
            self.assertError(lambda: changed.verify_control_generation(self.schema, self.adapter))

    def test_envelope_declaration_and_projection_cannot_be_forged(self):
        output = self.adapter.apply(self.operations(("set_on",)), self.profile)
        candidate = NativeAdapter(output, self.profile["family"])
        for index in (0, 37, 40):
            prefix = bytearray(candidate.envelope.prefix); prefix[index] ^= 1
            envelope = Envelope(candidate.envelope.thumbnail, bytes(prefix), candidate.envelope.body)
            forged = NativeAdapter(envelope.encode(candidate.envelope.body), candidate.family)
            self.assertError(lambda: forged.verify_control_generation(self.schema, self.adapter))
        forged = NativeAdapter(output, candidate.family); forged.document.sections[0].one("PanelName").set_value(b"forged projection")
        self.assertError(lambda: forged.verify_control_generation(self.schema, self.adapter), "INVALID_CONTROL_CANDIDATE")
        self.assertError(lambda: candidate.verify_control_generation(self.schema), "INVALID_CONTROL_SOURCE")

    def test_declared_length_literal_growth_and_bad_candidate_declaration(self):
        raw, profile = literal_generation_fixture()
        envelope = Envelope.decode(raw, profile["family"])
        prefix = envelope.prefix[:37] + bytes(value ^ 0x64 for value in len(envelope.body).to_bytes(4, "little"))
        raw = Envelope(envelope.thumbnail, prefix, envelope.body).encode(envelope.body)
        profile = qualify_literal_generation(raw, profile)
        source = NativeAdapter(raw, profile["family"])
        operations = [{"op": "append_literal_page", "screen_id": "7", "name": "New"}]
        output = source.apply(operations, profile)
        candidate = NativeAdapter(output, profile["family"])
        self.assertTrue(candidate.verify_layout_order(profile["native_schema"], source))
        self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
        forged_prefix = bytearray(candidate.envelope.prefix); forged_prefix[40] ^= 1
        forged = NativeAdapter(Envelope(candidate.envelope.thumbnail, bytes(forged_prefix), candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
        self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], source), "LITERAL_GENERATION_MISMATCH")

    def test_declared_length_preserved_caption_growth_shrink_and_wrong_declaration(self):
        raw, profile = preserved_layout_fixture()
        envelope = Envelope.decode(raw, profile["family"])
        prefix = envelope.prefix[:37] + bytes(value ^ 0x64 for value in len(envelope.body).to_bytes(4, "little"))
        raw = Envelope(envelope.thumbnail, prefix, envelope.body).encode(envelope.body)
        profile = qualify_preserved_layout(raw, profile)
        source = NativeAdapter(raw, profile["family"])
        for text in ("", "Kaynak durumunu daha uzun bir Türkçe metinle göster"):
            output = source.apply([{"op": "set_text", "screen_id": "1", "element_id": "1", "state_index": 0, "language": 0, "text": text}], profile)
            candidate = NativeAdapter(output, profile["family"])
            self.assertTrue(candidate.verify_layout_order(profile["native_schema"], source))
            self.assertEqual(candidate.envelope.declared_body_length(), len(candidate.envelope.body))
            self.assertEqual(candidate.envelope.prefix[:37], source.envelope.prefix[:37])
            wrong = bytearray(candidate.envelope.prefix); wrong[37] ^= 1
            forged = NativeAdapter(Envelope(candidate.envelope.thumbnail, bytes(wrong), candidate.envelope.body).encode(candidate.envelope.body), candidate.family)
            self.assertError(lambda: forged.verify_layout_order(profile["native_schema"], source), "PRESERVED_LAYOUT_MISMATCH")


class CalibrationInventoryTests(unittest.TestCase):
    """Observed file facts cannot qualify command/type/driver semantics."""
    def source(self, family='delta_dopsoft2', body_edit=None):
        raw, _ = literal_generation_fixture(family)
        envelope = Envelope.decode(raw, family)
        driver = (b'ControllerSection0=Delta\r\nControllerName0=Delta DVP PLC\r\nCommName0=Link1\r\n'
                  b'DefPLCStationNr0=1\r\nCommPLCPassword0=DoNotExport123\r\n'
                  b'PinCode=123456\r\nText=123456\r\nUnknownNumber=123456\r\n'
                  b'UnknownValue=private text\r\nPrinterSection0=NULL\r\n'
                  b'ReadCtrlVar={Link1}1@D0\r\nCtrlScreen=0\r\n')
        body = envelope.body.replace(b'[Multi-Language]\r\n', driver + b'[Multi-Language]\r\n', 1)
        if body_edit:
            body = body_edit(body)
        return envelope.encode(body)

    def test_both_envelopes_capture_driver_owner_and_global_facts_without_qualifying_them(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                source = self.source(family)
                adapter = NativeAdapter(source, family)
                capture = adapter.calibration_inventory()
                self.assertEqual(capture['source_sha256'], hashlib.sha256(source).hexdigest())
                self.assertEqual(capture['qualification'], 'UNVERIFIED')
                self.assertFalse(capture['emission_authority'])
                self.assertEqual(capture['driver_blocks'][0]['native_index'], '0')
                self.assertEqual(capture['driver_blocks'][0]['boundary_evidence'], 'OBSERVED_NEXT_MARKER')
                self.assertEqual(capture['driver_blocks'][0]['driver_semantics'], 'UNVERIFIED')
                self.assertEqual(capture['owners'][0]['raw_span_sha256'], adapter.owner_extent_sha256('1', '1'))
                self.assertEqual(capture['owners'][0]['button_behavior'], 'UNVERIFIED')
                self.assertEqual(capture['opaque_envelope']['graph_dependencies'], 'UNKNOWN')
                self.assertEqual(adapter.original, source)

    def test_credentials_and_opaque_text_macro_payloads_are_not_exported(self):
        import json
        adapter = NativeAdapter(self.source(), 'delta_dopsoft2')
        capture = adapter.calibration_inventory()
        serialized = json.dumps(capture)
        self.assertNotIn('DoNotExport123', serialized)
        self.assertNotIn('private text', serialized)
        driver = capture['driver_blocks'][0]['records']
        secret = next(record for record in driver if record['key'] == 'CommPLCPassword0')
        self.assertEqual(secret, {'key': 'CommPLCPassword0', 'kind': 'scalar', 'redacted': True})
        wide = next(record for record in capture['page_headers'][0]['records'] if record['key'] == 'wTextLen')
        self.assertNotIn('observed_scalar', wide)
        self.assertFalse(wide['value_exported'])

    def test_numeric_credentials_and_unclassified_text_are_not_exported(self):
        private_keys = ['PIN', 'PinCode', 'Passcode', 'Passwd', 'AuthKey', 'UserID', 'AccessCode']
        withheld_keys = ['Caption', 'ArbitraryVar']
        rows = b''.join((key + '=123456\r\n').encode() for key in private_keys + withheld_keys)
        facts = NativeAdapter(self.source(body_edit=lambda b: b.replace(b'PrinterSection0=NULL', rows + b'PrinterSection0=NULL')), 'delta_dopsoft2').calibration_inventory()
        observed = {row['key']: row for row in facts['driver_blocks'][0]['records']}
        for key in private_keys:
            self.assertEqual(observed[key], {'key': key, 'kind': 'scalar', 'redacted': True})
        for key in withheld_keys:
            self.assertFalse(observed[key]['value_exported'])
            self.assertNotIn('observed_scalar', observed[key])
        self.assertEqual(observed['DefPLCStationNr0']['observed_scalar'], '1')

    def test_unclassified_type_strings_are_withheld_in_owner_summary(self):
        source = self.source(body_edit=lambda b: b.replace(b'Type=10\r\nSubType=6', b'Type=private-type\r\nSubType=private-subtype'))
        facts = NativeAdapter(source, 'delta_dopsoft2').calibration_inventory()
        self.assertIsNone(facts['owners'][0]['observed_type'])
        self.assertIsNone(facts['owners'][0]['observed_subtype'])
        import json
        self.assertNotIn('private-type', json.dumps(facts))
        self.assertNotIn('private-subtype', json.dumps(facts))

    def test_duplicate_driver_fields_and_missing_end_marker_stay_unresolved(self):
        adapter = NativeAdapter(self.source(body_edit=lambda b: b.replace(b'DefPLCStationNr0=1\r\n', b'DefPLCStationNr0=1\r\nDefPLCStationNr0=2\r\n')), 'delta_dopsoft2')
        facts = adapter.calibration_inventory()
        self.assertEqual(facts['driver_blocks'][0]['ambiguous_keys'], ['DefPLCStationNr0'])
        adapter = NativeAdapter(self.source(body_edit=lambda b: b.replace(b'PrinterSection0=NULL\r\n', b'')), 'delta_dopsoft2')
        facts = adapter.calibration_inventory()
        self.assertEqual(facts['driver_blocks'][0]['boundary_evidence'], 'UNRESOLVED')
        self.assertIsNone(facts['driver_blocks'][0]['end_record_exclusive'])

    def test_description_and_narrow_numeric_limits_cannot_supply_semantic_types(self):
        for text in ('Momentary', 'Maintained'):
            adapter = NativeAdapter(self.source(body_edit=lambda b: b.replace(_wide('wDescTextLen', ''), _wide('wDescTextLen', text))), 'delta_dopsoft2')
            self.assertIn(_wide('wDescTextLen', text), adapter.envelope.body)
            facts = adapter.calibration_inventory()
            self.assertTrue(all(owner['button_behavior'] == 'UNVERIFIED' for owner in facts['owners']))
            self.assertTrue(all(owner['primitive_width_format'] == 'UNVERIFIED' for owner in facts['owners']))
            self.assertTrue(all(owner['read_write_permission'] == 'UNVERIFIED' for owner in facts['owners']))

    def test_noncanonical_or_repeated_controller_markers_are_visible_not_qualifications(self):
        for raw, code in [(b'ControllerSection01=Delta\r\n', 'NONCANONICAL_CONTROLLER_MARKER'),
                          (b'ControllerSection0=Delta\r\n', 'REPEATED_CONTROLLER_MARKER')]:
            source = self.source(body_edit=lambda b: b.replace(b'PrinterSection0=NULL\r\n', raw + b'PrinterSection0=NULL\r\n'))
            facts = NativeAdapter(source, 'delta_dopsoft2').calibration_inventory()
            self.assertIn(code, [finding['code'] for finding in facts['controller_marker_findings']])
            self.assertFalse(facts['emission_authority'])
            if code == 'REPEATED_CONTROLLER_MARKER':
                self.assertTrue(all(not block['marker_unique'] for block in facts['driver_blocks']))

    def test_cached_native_projection_cannot_forge_captured_source_evidence(self):
        for variant in ('record', 'body', 'model', 'envelope'):
            adapter = NativeAdapter(self.source(), 'delta_dopsoft2')
            if variant == 'record': adapter.application.one('ModelName').value = b'fake'
            elif variant == 'body': adapter.document.tail += b'fake'
            elif variant == 'model': adapter.model_id = 'fake'
            else: adapter.envelope = Envelope(adapter.envelope.thumbnail, b'fake' + adapter.envelope.prefix[4:], adapter.envelope.body)
            with self.subTest(variant=variant), self.assertRaises(HmiError) as raised:
                adapter.calibration_inventory()
            self.assertEqual(raised.exception.code, 'INVALID_CALIBRATION_SOURCE')


if __name__ == "__main__":
    unittest.main()
