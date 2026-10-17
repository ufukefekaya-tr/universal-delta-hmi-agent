"""Source-pinned removal of inert B10 literals, without a layout bypass.

This is a stored-file contract. A descriptor hash is not external authority;
the public service must separately match its registered static evidence book.
No vendor code, private assets, or customer paths are embedded here.
"""
from copy import deepcopy
import hashlib
import re
import struct

from ..errors import HmiError
from . import (NativeAdapter, _groups, _LITERAL_PAGE_FIELDS,
               _LITERAL_ELEMENT_FIELDS, _LITERAL_STATE_FIELDS,
               _CONTROL_COMMON, _CONTROL_BUTTON, _CONTROL_INPUT, _CONTROL_DISPLAY)
from .identity import canonical_model_id
from .records import is_wide, unsigned
from .resources import ResourceTables, _line, _record, _suffix_boundary


_SHA = re.compile(r"[0-9a-f]{64}")
_IDENTITY = re.compile(r"[1-9][0-9]{0,9}")
_MACRO = re.compile(r"[A-Za-z0-9_]*MacroLen[0-9]*")
_FIELD = re.compile(rb"([A-Za-z][A-Za-z0-9_ -]*)=(.*)")
_HEADER = re.compile(rb"\[([A-Za-z0-9][A-Za-z0-9_ -]*)\]")
_MODEL, _VERSION, _FAMILY = 2953863504, "4.00.07.04", "delta_dopsoft2"
_MAX_OWNERS, _MAX_PAGES = 4096, 256

# Closed, observed configuration namespaces. These names are not writable and
# do not confer enum meanings. Unknown fields cannot be presumed reference-free.
_APPLICATION = set("""ActiveSmtp AlarmCSVGroup AlarmExportCSV BackgroundMacroLen Baud
CheckUsbUsages ClockMacroDelayTime ClockMacroLen ClockMacroPriority ComPort CommInt
CommOptLimitEnable CtrlAreaSampleCycle CtrlCurve CtrlEnRecipe CtrlEnRecipeNo
CtrlHistoryClear CtrlHistorySample CtrlMemFmt CtrlNormal CtrlRecipe CtrlRecipeNo
CtrlScreen CtrlSystem CustomPaperCx CustomPaperCy CustomPrintTypeScreen CustomerPalette
DataBits DefaultMemFmt DefaultPrintScreenH DefaultPrintScreenW DefaultScreen
ElementFontColor ElementFontName ElementFontSize EnableCustomerLogo EnableHmiID EthIp
EthPort ExportCSV FullTimeZone GUID GotoSaveScrID HeightPrintTypeScreenLink
HeightPrintTypeScreenVar HmiID HoldPlace InitialMacroLen IntRetry Interface IsGotoSaveScr
IsReadSaveScr LeftPrintTypeScreenLink LeftPrintTypeScreenVar LevelPrompt LevelPromptNWnd
LineBrkBackgndMacro MeMeCode ModelName MultiBaseScreen Name NeedExpireTime NeedPWD
OptimizeType PanelName PanelRotate PanelSeries Parity PasswdExpireTime PrintScrCount
PrnScrRatioH PrnScrRatioW ReadCtrlFlagAutoClear ReadCtrlLink ReadCtrlVar ReadCtrlVarSize
ReadPrintTypeScreenLink ReadPrintTypeScreenVar ReadSaveScrLink ReadSaveScrVar
ReadStatusLink ReadStatusVar SaveScr SaveScrCount SaveScrDelayTime ScreenBkColor
ScrollSize ShowAfterReadDataFlag ShowUsbMsgInAlarm ShowUsbMsgInHistory ShowUsbMsgInRecipe
SmtpAccount SmtpHWInf SmtpIP SmtpPassword SmtpPort SmtpSecurity SmtpSender
SpeedupPageChange StartLevel StartupDelayTime StatusCurve StatusEnRecipe StatusEnRecipeNo
StatusHistoryClear StatusHistorySample StatusMemFmt StatusNormal StatusRecipe StatusRecipeNo
StatusScreen StatusSystem StopBits StopUpload SysErrorTime SysFontName SysKeyMode SysKeyPwd
TopPrintTypeScreenLink TopPrintTypeScreenVar TwinkleTime USBCachSize Version WarpText
WidthPrintTypeScreenLink WidthPrintTypeScreenVar""".split())
_APP_INDEXED = set("""CommDelayTime CommName CommOptEnable CommPLCPassword CommRetry
CommTimeout ControllerName ControllerSection DefPLCStationNr HMIPortNr HMIStationNr
Interface PortNr PrintAutoNextPage PrintDirection PrintInterface PrintMarginBottom
PrintMarginLeft PrintMarginRight PrintMarginTop PrinterName PrinterPaper PrinterSection
RemotePLCClientHWInf RemotePLCClientIP RemotePLCClientPort RemotePLCMode RemotePLCServerHWInf
RemotePLCServerPort baud databits parity stopbits""".split())
_GLOBALS = {
    "Multi-Language": set("DefaultLanguage UseLanguageTab UseTextBankFont LanguageEnable0 LanguageFlag0 LanguageFontName0 LanguageFontSize0 LanguageValue0 wLanguageNameLen0".split()),
    "Recipe": set("EnableRcp RcpGroup RcpLen ReadRcpLink ReadRcpVar".split()),
    "Recipe32": set("EnableRcp32 ReadRcp32Link ReadRcp32Var".split()),
    "EnhanceRcp": set("EnRcpVER EnableEnRcp ReadEnRecipeVar".split()),
    "Ethernet": set("CommEthPort CommHWInf Enable HMIName ModbusHWInf ModbusPort RefreshTime RowPerPage".split()),
    "SIP": {"Enable", "Lang"},
    "RemoteCtrl": set("RemoCloseUntilConn RemoEnable RemoHWInf RemoPWD RemoPort RemoScantime RemoShowDisconnMsg".split()),
    "VNCCtrl": set("VNCEnable VNCHWInf VNCPWD VNCPort VNCWebPort".split()),
    "RTC": set("EnableRTC PollingTime RTCAddr0 RTCAddr1 RTCAddr2 RTCLength RTCLinkname RTCPLCStation RTCStartAddr RTCTriggerAddr TriggerType UpdateDirection".split()),
    "VideoList": {"ListTotalSize"},
    "LOG": set("LogDateFmt LogEnable LogEnableAddrVar LogEnableByAddr LogFontSize LogHoldPlace LogOutOfSpace LogTimeFmt LogTitleFontColor LogTitleFontSize".split()),
    "FTP": set("ActiveFTPServer FTPAnonymousOn FTPHWInf FTPLoginID FTPPwdLen FTPRootDisk FTPServerPort".split()),
    "FTPFile": set("AccountAddrVar AccountLen CreateAddrVar DeleteAddrVar DirectoryAddrVar DirectoryLen DownloadQuantityAddrVar DuplicateAddrVar FTPFileEnable FileDownloadTriggerAddrVar FileSlotChangeAddrVar FileSlotDeleteAddrVar FileSlotIDAddrVar FileSlotNewAddrVar FileSlotSaveAddrVar FileSlotSaveasAddrVar GetFileNameAddrIndexVar GetFileNameAddrResultVar GetFileNameResultLen GetFileNameTriggerAddrVar IPAddrVar LoginAddrVar LogoutAddrVar NameAddrVar NameLen PasswordAddrVar PasswordLen PortAddrVar RenameAddrVar SearchAddrVar SelAddrVar SelectedLen StateAddrVar SwitchAddrVar".split()),
}
_LOG_TITLE = {f"wLogTitles{name}Len000" for name in
              "Account Action ChgValue Date Desc Level PrevValue Screen Time".split()}
_LOG_TITLE |= {f"wLogTitlesOrderLen{i:03}" for i in range(9)}
_GLOBALS["LOG"] |= _LOG_TITLE
_KEYPAD = set()
for _prefix in ("GA", "GB", "GD", "GH"):
    _KEYPAD |= {_prefix + k for k in "KPApplyMode KPScreenID KPTitleHeight KPUseCust KeyPadBottom KeyPadLeft KeyPadRight KeyPadTop RangeFontColor RangeFontSize".split()}
    for _index in range(6 if _prefix == "GA" else 5):
        _KEYPAD |= {f"{_prefix}{key}{_index:03}" for key in ("KPBkgndColor", "KPFontColor")}
        _KEYPAD |= {f"{_prefix}{key}{_index:03}-000" for key in ("KPFontName", "KPFontSize", "wKPFStringLen")}
_GLOBALS["Global-Keypad"] = _KEYPAD
_LITERAL_FIELDS = _LITERAL_ELEMENT_FIELDS - {"wDescTextLen"}
_GOTO_FIELDS = _CONTROL_COMMON | _CONTROL_BUTTON | {
    "TriggerLink", "TriggerVar", "GoToScreenID", "GoToScreenName", "CloseScreen",
    "Variation", "Order", "CancelActBit"}
_ELEMENT_FIELDS = {
    ("10", "6"): _LITERAL_FIELDS,
    ("1", "1"): _CONTROL_COMMON | _CONTROL_BUTTON | {"ButtonOnMacroLen"},
    ("1", "2"): _CONTROL_COMMON | _CONTROL_BUTTON | {"ButtonOffMacroLen"},
    ("1", "3"): _CONTROL_COMMON | _CONTROL_BUTTON | {"OffVoice", "ButtonOnMacroLen", "ButtonOffMacroLen"},
    ("1", "4"): _CONTROL_COMMON | _CONTROL_BUTTON | {"OffVoice", "ButtonOnMacroLen", "ButtonOffMacroLen"},
    ("1", "10"): _GOTO_FIELDS,
    ("2", "1"): _CONTROL_COMMON,
    ("5", "1"): _CONTROL_COMMON | _CONTROL_DISPLAY,
    ("6", "1"): _CONTROL_COMMON | _CONTROL_INPUT,
}
_ALARM_FIELDS = set("""Version AlarmCount AlarmCSVGroup AlarmExportCSV
AlarmTurnOffScrnSaver AlmHoldPlace BackgroundColor ContinueAddr Direction EanbleMovingSign
Hold MoveCount MoveTime Position ReadAlarmLink ReadAlarmVar RecordNumber SampleCycle
ScreenDisplayMode wFont001 wFontRatio001 wMessageSize001""".split())
_SUFFIX = ["History", "TextBank", "Tag", "EthernetIPTag", "SRAM_DATA",
           "SysMessage", "Picture", "Background", "DeviceTable", "END"]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded(value, depth=0, seen=None, budget=None):
    """Reject cyclic, deep, non-JSON, or oversized inputs before copying."""
    seen = set() if seen is None else seen
    budget = [100000, 2 * 1024 * 1024] if budget is None else budget
    budget[0] -= 1
    if depth > 10 or budget[0] < 0:
        raise HmiError("INVALID_EXISTING_PROGRAM", "Existing-program input exceeds its structural bound")
    if value is None or type(value) in (bool, int):
        if type(value) is int and value.bit_length() > 64:
            raise HmiError("INVALID_EXISTING_PROGRAM", "Input integer exceeds its bound")
        return
    if isinstance(value, str):
        budget[1] -= len(value)
        if len(value) > 4096 or budget[1] < 0:
            raise HmiError("INVALID_EXISTING_PROGRAM", "Input text exceeds its bound")
        return
    if type(value) not in (dict, list) or id(value) in seen:
        raise HmiError("INVALID_EXISTING_PROGRAM", "Existing-program input must be bounded acyclic JSON")
    seen.add(id(value))
    for key, item in value.items() if type(value) is dict else enumerate(value):
        if type(value) is dict and not isinstance(key, str):
            raise HmiError("INVALID_EXISTING_PROGRAM", "Input object keys must be strings")
        if type(value) is dict:
            _bounded(key, depth + 1, seen, budget)
        _bounded(item, depth + 1, seen, budget)
    seen.remove(id(value))


def existing_program_contract(schema):
    _bounded(schema)
    keys = {"qualified", "contract_version", "mode", "source_sha256", "family",
            "model_id", "editor_version", "authority_sha256"}
    contract = schema.get("existing_program") if isinstance(schema, dict) else None
    if (not isinstance(schema, dict) or schema.get("qualified") is not True
            or {"preserved_layout", "control_generation", "blank_program", "multipage_program", "literal_generation"} & set(schema)
            or not isinstance(contract, dict) or set(contract) != keys
            or contract.get("qualified") is not True
            or type(contract.get("contract_version")) is not int or contract["contract_version"] != 1
            or contract.get("mode") != "source_inert_literal_deletion"
            or contract.get("family") != _FAMILY or type(contract.get("model_id")) is not int
            or contract["model_id"] != _MODEL or contract.get("editor_version") != _VERSION):
        raise HmiError("UNQUALIFIED_EXISTING_PROGRAM", "Existing-program deletion requires its separate exact static B10 contract")
    for key in ("source_sha256", "authority_sha256"):
        if not isinstance(contract[key], str) or not _SHA.fullmatch(contract[key]):
            raise HmiError("UNQUALIFIED_EXISTING_PROGRAM", "Descriptor pins require canonical SHA-256", field=key)
    return deepcopy(contract)


def _id(value, label, maximum=0x7fffffff):
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value) or int(value) > maximum:
        raise HmiError("INVALID_EXISTING_ID", "Owner/page identity must be canonical and bounded", field=label)
    return value


def _ascii(record):
    """Native type/reference scalars have a typed strict-ASCII boundary."""
    try:
        return record.value.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Native relationship scalar is not ASCII", field=record.key) from exc


def _shape(section, allowed, blank=False):
    if section.header != ("[" + section.name + "]\r\n").encode("ascii"):
        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Section header framing is not qualified")
    keys = set()
    for record in section.records:
        key = record.key
        if key is None:
            if blank and record.raw == b"\r\n":
                continue
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Opaque native record cannot prove a closed reference graph", section=section.name)
        if key not in allowed or key in keys:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Unknown or repeated native field cannot prove a closed graph", section=section.name, field=key)
        keys.add(key)
        if _MACRO.fullmatch(key):
            if record.kind != "macro" or record.value != b"0" or record.blob != b"":
                raise HmiError("EXISTING_GRAPH_MACRO", "Every source macro must be explicitly empty", field=key)
        elif is_wide(key):
            if record.kind != "wide" or "\0" in record.text():
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Wide native field has unsupported framing", field=key)
        elif key == "MeMeCode" and section.name == "Application":
            if record.kind != "inline_binary" or len(record.blob or b"") != 48:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Application metadata is outside the observed inline frame")
        elif section.name == "Application" and key in {"SysKeyPwd", "HmiID", "CustomerPalette"}:
            expected = {"SysKeyPwd": 8, "HmiID": 12, "CustomerPalette": 64}[key]
            if record.kind != "blob" or len(record.blob or b"") != expected:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Configuration blob framing is not qualified", field=key)
        elif section.name == "FTP" and key == "FTPPwdLen":
            if record.kind != "blob" or len(record.blob or b"") > 256:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "FTP configuration frame is not qualified")
        elif section.name == "Recipe" and key == "RcpGroup":
            if record.kind != "blob" or record.value != b"0" or record.blob != b"":
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Populated recipe records require a separate dependency contract")
        elif record.kind is not None or record.blob is not None or b"\0" in record.value:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Native scalar has unknown framing", field=key)
    return keys


def _zero(section, keys, required=False):
    for key in keys:
        record = section.one(key, required)
        if record is not None and (record.kind is not None or record.value != b"0"):
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Native relationship/behavior flag is outside the inert source graph", field=key)


class ExistingProgram:
    """Immutable source and exact complete-owner deletion operations."""

    def __init__(self, source, schema):
        self.contract = existing_program_contract(schema)
        # Public metadata remains inspectable, but may not be repinned after
        # construction to turn a different source into this transaction.
        self._contract_snapshot = tuple(sorted(self.contract.items()))
        self.source = source

    def _global_graph(self):
        source = self.source
        source._preserved_prefix(source.document)
        first = next(i for i, section in enumerate(source.document.sections) if section.name == "Screen")
        for section in source.document.sections[:first]:
            if section.name == "Application":
                allowed = _APPLICATION | {key + "0" for key in _APP_INDEXED}
            else:
                allowed = _GLOBALS.get(section.name, set())
            keys = _shape(section, allowed, blank=section.name in {"Application", "Recipe"})
            if section.name == "Application":
                required = {"ModelName", "Version", "InitialMacroLen", "BackgroundMacroLen", "ClockMacroLen"}
                if not required <= keys:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Application lacks its explicit identity/empty macro frames")
            if section.name in {"Recipe", "Recipe32", "EnhanceRcp", "VideoList"}:
                _zero(section, {"Recipe": {"EnableRcp", "RcpLen"}, "Recipe32": {"EnableRcp32"},
                                "EnhanceRcp": {"EnableEnRcp"}, "VideoList": {"ListTotalSize"}}[section.name], required=True)
                if section.name == "Recipe":
                    section.one("RcpGroup")
            if section.name == "Global-Keypad":
                _zero(section, {p + k for p in ("GA", "GB", "GD", "GH") for k in ("KPUseCust", "KPScreenID")})

    def _tail_graph(self, pages):
        resources = ResourceTables.parse(self.source.document.tail)
        boundary = _suffix_boundary(resources.suffix)
        if boundary.get("complete") is not True or boundary["sections"] != _SUFFIX:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source resource graph requires the complete known B suffix")
        pos = 0
        current = None
        seen = set()
        submacro_keys = set()
        while pos < len(resources.prefix):
            start = pos
            line, pos = _line(resources.prefix, pos)
            header = _HEADER.fullmatch(line)
            if header:
                current = header[1].decode("ascii")
                if current not in {"SubMacro", "Global_Auxkey"} or current in seen:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Unknown prefix resource section")
                seen.add(current)
                continue
            if current != "SubMacro":
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Global auxiliary keys must be empty")
            record, pos = _record(resources.prefix, start, line, pos, current)
            match = re.fullmatch(r"SubMacro(?:Protect|PWD)([0-9]{3})", record.key or "")
            if match is None or not 1 <= int(match[1]) <= 512:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Unknown global macro/reference record")
            if record.key in submacro_keys:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Repeated global macro/reference field", field=record.key)
            submacro_keys.add(record.key)
            _shape(type(resources.alarm)("SubMacro", b"[SubMacro]\r\n", [record]), {record.key})
            if record.key.startswith("SubMacroProtect") and record.value not in {b"0", b"1"}:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Macro protection flag is outside the observed scalar frame")
            if record.key.startswith("SubMacroPWD") and len(record.value) != 8:
                # The primary reader/writer copies a configuration string,
                # not an owner relation. Eight bytes is only the observed
                # accepted source shape; the vendor writer uses %s.
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Macro configuration string lacks its observed opaque scalar frame")
        if seen != {"SubMacro", "Global_Auxkey"}:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source prefix requires its complete empty macro/auxiliary sections")
        _shape(resources.alarm, _ALARM_FIELDS)
        capacity = resources.alarm.one("AlarmCount").value
        if not re.fullmatch(rb"0|[1-9][0-9]{0,4}", capacity) or int(capacity) > 32768:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Alarm capacity must be a canonical bounded scalar")
        resources.alarm.one("Version")
        if resources.inspect()["serialized_entry_count"] != 0:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Serialized alarms need their separate dependency contract")
        # This bounded graph has no serialized alarm entries or history owners.
        suffix = resources.suffix
        pos = 0
        current = None
        keys = set()
        tag_fields = {}
        suffix_fields = {}
        background = b""
        while pos < len(suffix):
            start = pos
            line, pos = _line(suffix, pos)
            header = _HEADER.fullmatch(line)
            name = header[1].decode("ascii") if header else "SysMessage" if line == b"[SysMessage]\0\0\0" else None
            if name is not None:
                current, keys = name, set()
                suffix_fields[name] = keys
                if name == "SRAM_DATA":
                    count = struct.unpack_from("<I", suffix, pos)[0]
                    blob = suffix[pos + 4:pos + 4 + count]
                    if (count != 530 or struct.unpack_from("<I", blob, 0)[0] != 20
                            or struct.unpack_from("<I", blob, 4)[0] != _MODEL or blob[20:24] != b"DOPB"):
                        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "SRAM configuration is outside the primary-reviewed B10 frame")
                    pos += 4 + count + 2
                continue
            match = _FIELD.fullmatch(line)
            if match is None:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Unknown resource record framing")
            key, value = match[1].decode("ascii"), match[2]
            if key in keys:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Repeated resource relationship field", field=key)
            keys.add(key)
            if current == "History" and key == "HistoryCount" and value == b"0":
                continue
            if current == "TextBank" and re.fullmatch(r"wFont[0-9]{3}", key):
                continue
            if current == "SysMessage" and re.fullmatch(r"LangName[0-9]", key):
                continue
            if current == "Tag" and ((key == "TagLinkCount" and value in {b"0", b"1"}) or (key == "LinkSize" and value == b"0")):
                tag_fields[key] = value
                continue
            if current == "EthernetIPTag" and key == "TagTotalSize" and value == b"0":
                continue
            if current == "DeviceTable" and key in {"DisplayFormat", "EnableDownload", "DisplayLength"} and value == b"0":
                continue
            if current in {"Picture", "Background"} and key == "Size":
                count = unsigned(value, key)
                if current == "Picture" and count != 0:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Picture assets need their separate dependency contract")
                if current == "Background":
                    background = suffix[pos:pos + count]
                pos += count + 2
                continue
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Unknown resource field cannot prove a closed graph", section=current, field=key)
        if tag_fields not in ({"TagLinkCount": b"0"}, {"TagLinkCount": b"1", "LinkSize": b"0"}):
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Tag link count and empty link size must form a complete witnessed frame")
        required_fields = {"History": {"HistoryCount"}, "EthernetIPTag": {"TagTotalSize"},
                           "Picture": {"Size"}, "Background": {"Size"},
                           "DeviceTable": {"DisplayFormat", "EnableDownload", "DisplayLength"}}
        if any(not fields <= suffix_fields[name] for name, fields in required_fields.items()):
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source suffix lacks mandatory empty resource frames")
        self._background_graph(background, pages)

    @staticmethod
    def _background_graph(background, pages):
        offsets = []
        pos = 0
        while pos < len(background):
            if len(background) - pos < 40:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Background lacks a complete fixed DIB header")
            fields = struct.unpack_from("<IiiHHIIiiII", background, pos)
            size, width, height, planes, bits, compression, image_size, xppm, yppm, used, important = fields
            if (size != 40 or width <= 0 or height <= 0 or planes != 1 or bits != 32
                    or compression != 0 or image_size != width * height * 4
                    or any((xppm, yppm, used, important)) or pos + 40 + image_size > len(background)):
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Background is outside the complete fixed BI_RGB32 frame")
            offsets.append((pos, width, height))
            pos += 40 + image_size
        referenced = []
        for page in pages:
            record = page["section"].one("PictureOffset", False)
            if not background:
                if record is not None:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Page picture offset has no background frame")
                continue
            if record is None or not re.fullmatch(rb"0|[1-9][0-9]{0,9}", record.value):
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Page lacks its canonical background offset")
            offset = int(record.value)
            target = next((frame for frame in offsets if frame[0] == offset), None)
            dimensions = (page["section"].one("PanelSizeX").value, page["section"].one("PanelSizeY").value)
            if target is None or dimensions != (str(target[1]).encode(), str(target[2]).encode()):
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Page background reference/dimensions differ from complete frames")
            referenced.append(offset)
        if sorted(referenced) != [frame[0] for frame in offsets]:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Background frame references must be unique and complete")

    def check(self):
        contract = existing_program_contract({"qualified": True, "existing_program": self.contract})
        if tuple(sorted(contract.items())) != self._contract_snapshot:
            raise HmiError("UNQUALIFIED_EXISTING_PROGRAM", "Existing-program descriptor changed after construction")
        source = self.source
        if not isinstance(source, NativeAdapter):
            raise HmiError("INVALID_EXISTING_SOURCE", "Existing program requires a native source adapter")
        source._preserved_byte_binding("INVALID_EXISTING_SOURCE")
        if (_sha(source.original) != contract["source_sha256"] or source.family != _FAMILY
                or canonical_model_id(source.model_id) != _MODEL or source.editor_version != _VERSION):
            raise HmiError("INVALID_EXISTING_SOURCE", "Source identity/bytes differ from the pinned B10 program")
        source._control_prefix_length(source)
        pages = _groups(source.document)
        if not pages or len(pages) > _MAX_PAGES:
            raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source page count is outside the bounded graph")
        self._global_graph()
        identities = set()
        page_ids = {_id(page["id"], "screen_id", 65535) for page in pages}
        for page in pages:
            source._plain_extent(page)
            keys = _shape(page["section"], _LITERAL_PAGE_FIELDS | {"PictureOffset"})
            if not _LITERAL_PAGE_FIELDS <= keys:
                raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Page lacks its complete observed header/empty macro shape")
            _zero(page["section"], {"BaseScreenID", "IsSubScreen", "IsKeypadScreen", "IsPrintScreen", "IsScreenRotate"}, required=True)
            for owner in page["elements"]:
                eid = _id(owner["id"], "element_id")
                if eid in identities or len(identities) >= _MAX_OWNERS:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source owner identities are repeated or exceed the bound")
                identities.add(eid)
                section = owner["section"]
                pair = (_ascii(section.one("Type")), _ascii(section.one("SubType")))
                if pair not in _ELEMENT_FIELDS:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Native owner kind has no closed reference contract")
                keys = _shape(section, _ELEMENT_FIELDS[pair])
                optional = {"PushTime"} if pair == ("1", "10") else {"OffVoice"} if pair == ("1", "4") else set()
                if not _ELEMENT_FIELDS[pair] - optional <= keys:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Owner lacks its complete known reference/behavior fields")
                _zero(section, {"GroupID"}, required=True)
                source._geometry(page, owner, {})
                states = set()
                for state in owner["states"]:
                    keys = _shape(state, _LITERAL_STATE_FIELDS)
                    if keys != _LITERAL_STATE_FIELDS:
                        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "State shape differs from the closed no-picture baseline")
                    value = state.one("Value").value
                    if not re.fullmatch(rb"0|[1-9][0-9]{0,9}", value) or value in states:
                        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "State identity is malformed or repeated")
                    states.add(value)
                    _zero(state, {"UsePictureCoord", "PictureStretch", "StretchMode", "TransEffect", "TransColor", "SoundIndex", "Twinkles"}, required=True)
                if not states:
                    raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Source owner has no framed state")
                if pair == ("1", "10"):
                    destination = _ascii(section.one("GoToScreenID"))
                    if destination not in page_ids:
                        raise HmiError("UNQUALIFIED_EXISTING_GRAPH", "Navigation references a missing page")
                if pair == ("6", "1"):
                    _zero(section, {"UseCustKeypad", "KeypadScreenID"}, required=True)
        self._tail_graph(pages)
        return True

    @staticmethod
    def _inert(owner):
        section, states = owner["section"], owner["states"]
        if (section.one("Type").value != b"10" or section.one("SubType").value != b"6"
                or set(record.key for record in section.records) != _LITERAL_FIELDS
                or len(states) != 1 or states[0].one("Value").value != b"0"):
            raise HmiError("NONINERT_LITERAL", "Only the complete observed inert literal extent can be deleted")
        for key in ("ReadVar", "WriteVar", "OffsetReadVar", "OffsetWriteVar", "VisibleVar"):
            if section.one(key).value != b"None":
                raise HmiError("NONINERT_LITERAL", "A bound or conditionally visible literal is not removable", field=key)
        for key in ("GroupID", "PosVary", "PrintSuccessiveData", "nAngle", "bFreeze"):
            if section.one(key).value != b"0":
                raise HmiError("NONINERT_LITERAL", "Literal behavior is outside the inert baseline", field=key)

    def _deletions(self, operations):
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > _MAX_OWNERS:
            raise HmiError("INVALID_OPERATIONS", "Existing-program operations must be a bounded list")
        self.check()
        pages = _groups(self.source.document)
        owners = {(page["id"], owner["id"]): owner for page in pages for owner in page["elements"]}
        result, seen = [], set()
        for operation in operations:
            if (not isinstance(operation, dict) or set(operation) != {"op", "screen_id", "element_id", "owner_sha256"}
                    or operation.get("op") != "delete_literal"):
                raise HmiError("INVALID_EXISTING_OPERATION", "Only an exact pinned delete_literal operation is supported")
            key = (_id(operation["screen_id"], "screen_id", 65535), _id(operation["element_id"], "element_id"))
            if key in seen:
                raise HmiError("DUPLICATE_LITERAL_DELETION", "Repeated native deletion target is refused")
            seen.add(key)
            owner = owners.get(key)
            if owner is None:
                raise HmiError("MISSING_EXISTING_OWNER", "Deletion target is absent from the pinned source")
            self._inert(owner)
            digest = operation["owner_sha256"]
            if not isinstance(digest, str) or not _SHA.fullmatch(digest):
                raise HmiError("LITERAL_DELETION_PIN", "Deletion requires a canonical owner extent hash")
            extent = b"".join(s.bytes() for s in self.source.document.sections[owner["start"]:owner["end"]])
            if _sha(extent) != digest:
                raise HmiError("LITERAL_DELETION_PIN", "Deletion target extent differs from its immutable pin")
            result.append(owner)
        return result

    def expected_body(self, operations):
        """Independent subtraction of source byte ranges, not a mutated walk."""
        owners = self._deletions(operations)
        lengths = [len(section.bytes()) for section in self.source.document.sections]
        offsets, total = [0], 0
        for length in lengths:
            total += length
            offsets.append(total)
        ranges = sorted((offsets[o["start"]], offsets[o["end"]]) for o in owners)
        body = self.source.envelope.body
        parts, cursor = [], 0
        for start, end in ranges:
            parts.append(body[cursor:start])
            cursor = end
        parts.append(body[cursor:])
        return b"".join(parts)

    def apply(self, operations):
        owners = self._deletions(operations)
        if not owners:
            return self.source.original
        document = deepcopy(self.source.document)
        for owner in sorted(owners, key=lambda owner: owner["start"], reverse=True):
            del document.sections[owner["start"]:owner["end"]]
        body = document.bytes()
        if body != self.expected_body(operations):
            raise HmiError("EXISTING_PROGRAM_PRESERVATION", "Native mutation differs from independent source subtraction")
        raw = self.source.envelope.encode(body)
        self.verify(NativeAdapter(raw, self.source.family), operations)
        return raw

    def verify(self, candidate, operations=None):
        operations = [] if operations is None else operations
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_EXISTING_CANDIDATE", "Verification requires a native candidate adapter")
        candidate._preserved_byte_binding("INVALID_EXISTING_CANDIDATE")
        body = self.expected_body(operations)
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(body)
                or candidate.envelope.body != body or candidate.document.tail != self.source.document.tail):
            raise HmiError("EXISTING_PROGRAM_PRESERVATION", "Candidate changed bytes outside exactly approved literal extents")
        if not operations and candidate.original != self.source.original:
            raise HmiError("EXISTING_PROGRAM_PRESERVATION", "A no-op must preserve the complete original file")
        # Restoring the removed source slices must recover the entire body. This
        # uses original offsets and candidate bytes, not retained object IDs.
        owners = self._deletions(operations)
        lengths = [len(section.bytes()) for section in self.source.document.sections]
        offsets = [0]
        for length in lengths:
            offsets.append(offsets[-1] + length)
        restored, cursor, removed = [], 0, 0
        for start, end in sorted((offsets[o["start"]], offsets[o["end"]]) for o in owners):
            stop = start - removed
            restored.extend((body[cursor:stop], self.source.envelope.body[start:end]))
            cursor, removed = stop, removed + end - start
        restored.append(body[cursor:])
        if b"".join(restored) != self.source.envelope.body:
            raise HmiError("EXISTING_PROGRAM_PRESERVATION", "Candidate restoration did not recover the complete source body")
        return True
