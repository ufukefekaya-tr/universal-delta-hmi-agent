# SPDX-License-Identifier: Apache-2.0
"""Original span-indexed native reader. Unedited bytes are authoritative.

The file is indexed rather than normalized into a generated serialization.
Edits replace explicitly identified byte intervals; opaque suffixes stay intact.
"""
from dataclasses import dataclass, field
import gzip
import re
import struct
import zlib

from universal_diascreen_hmi.errors import AgentError, digest, require

LIMIT = 128 * 1024 * 1024
RESOURCE_HEADERS = {'SubMacro', 'Global_Auxkey', 'Alarm', 'History', 'TextBank',
                    'Tag', 'EthernetIPTag', 'SRAM_DATA', 'Picture', 'Background',
                    'SlotFile', 'CWPFile', 'DeviceTable', 'DIATag', 'END'}
PREAMBLE_HEADERS = {'Multi-Language', 'Global-Camera', 'Event-Trigger', 'Global-Keypad', 'Recipe',
                    'Recipe32', 'EnhanceRcp', 'Installment', 'Device', 'Ethernet', 'Modbus_TCP_Server',
                    'Modbus_COM_Server', 'WEB_OUTPUT', 'SIP', 'ExtendedMem', 'UerDefindDataTypeEnd',
                    'RemoteCtrl', 'VNCCtrl', 'RTC', 'LOG', 'FTP', 'FTPFile', 'AdvDataExchange',
                    'AdvDataExchangeEnd', 'LuaData', 'ExtraZA_ZGSection'}
WIDE = re.compile(r'(?:w[A-Za-z0-9_]*Len[0-9_-]*|G[DHBA]wKPFStringLen[0-9_-]+|TitleTextLen[0-9_-]+|UnitTextLen[0-9]+)\Z')
MACRO = re.compile(r'[A-Za-z0-9_]*MacroLen[0-9]*\Z')


def integer(value, maximum=LIMIT):
    raw = value if isinstance(value, bytes) else str(value).encode('ascii')
    require(bool(re.fullmatch(rb'[0-9]{1,12}', raw)), 'FRAME_LENGTH', 'Invalid bounded decimal length')
    number = int(raw)
    require(number <= maximum, 'FRAME_LIMIT', 'Declared length exceeds limit')
    return number


def scalar_int(raw, label):
    require(bool(re.fullmatch(rb'-?[0-9]{1,12}', raw)), 'NATIVE_INTEGER', 'Expected integer field', field=label)
    return int(raw)


class NativeFile:
    def __init__(self, original):
        require(isinstance(original, bytes) and 54 <= len(original) <= LIMIT,
                'CONTAINER', 'Native file size is outside bounds')
        require(original[:2] == b'BM' and original[6:10] == b'PDAB',
                'FAMILY', 'Only DIAScreen PDAB containers are accepted; DOP-B/DPS is excluded')
        thumb_size = struct.unpack_from('<I', original, 34)[0]
        boundary = 54 + thumb_size
        require(54 <= boundary < len(original), 'THUMBNAIL', 'Invalid thumbnail boundary')
        decoder = zlib.decompressobj(31)
        try:
            encoded = decoder.decompress(original[boundary:], LIMIT + 1)
        except zlib.error as exc:
            raise AgentError('GZIP', 'Invalid compressed native payload') from exc
        require(len(encoded) <= LIMIT and decoder.eof and not decoder.unconsumed_tail
                and not decoder.unused_data, 'GZIP', 'One complete bounded gzip member is required')
        decoded = bytes(b ^ 100 for b in encoded)
        require(len(decoded) > 41 and decoded[41:].startswith(b'[Application]\r\n'),
                'LAYOUT', 'Unrecognized native prefix or Application framing')
        self.original = original
        self.thumbnail = original[:boundary]
        self.prefix = decoded[:41]
        self.payload = decoded[41:]
        self.source_sha256 = digest(original)
        self.declared_length = struct.unpack('<I', bytes(b ^ 100 for b in self.prefix[37:41]))[0]

    def encode(self, payload):
        require(isinstance(payload, bytes) and len(payload) + 41 <= LIMIT, 'PAYLOAD_LIMIT', 'Candidate is too large')
        if payload == self.payload:
            return self.original
        prefix = self.prefix
        if len(payload) != len(self.payload):
            require(self.declared_length == len(self.payload), 'PREFIX_LENGTH',
                    'Length-changing save requires a source-matched declared length')
            prefix = prefix[:37] + bytes(b ^ 100 for b in struct.pack('<I', len(payload)))
        encoded = bytes(b ^ 100 for b in prefix + payload)
        candidate = self.thumbnail + gzip.compress(encoded, mtime=0)
        reread = NativeFile(candidate)
        require(reread.payload == payload and reread.thumbnail == self.thumbnail,
                'REREAD', 'Encoded candidate does not roundtrip')
        return candidate


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    key: str | None
    value: bytes = b''
    blob_start: int | None = None
    blob_end: int | None = None
    kind: str = 'scalar'

    def raw(self, body):
        return body[self.start:self.end]

    def blob(self, body):
        return body[self.blob_start:self.blob_end] if self.blob_start is not None else None

    def text(self, body):
        require(self.kind == 'wide', 'FIELD_TYPE', 'Field is not counted UTF-16')
        blob = self.blob(body)
        if not blob:
            return ''
        try:
            return blob[:-2].decode('utf-16-le', errors='strict')
        except UnicodeDecodeError as exc:
            raise AgentError('UTF16', 'Malformed counted UTF-16') from exc


@dataclass
class Section:
    name: str
    start: int
    header_end: int
    end: int
    tokens: list = field(default_factory=list)

    def one(self, key, optional=False):
        found = [t for t in self.tokens if t.key == key]
        require(len(found) <= 1, 'AMBIGUOUS_FIELD', 'Duplicate native field', section=self.name, field=key)
        require(found or optional, 'MISSING_FIELD', 'Native field is absent', section=self.name, field=key)
        return found[0] if found else None


class NativeIndex:
    def __init__(self, body):
        require(isinstance(body, bytes) and len(body) <= LIMIT, 'PAYLOAD', 'Invalid native payload')
        self.body = body
        self.sections = []
        self.tail_start = len(body)
        self.stop_reason = 'end'
        self.unqualified_records = []
        pos = 0
        current = None
        records = 0
        while pos < len(body):
            records += 1
            require(records < 300000,
                    'RECORD_LIMIT', 'Native index is too large')
            begin = pos
            if current and current.name == 'Application' and body.startswith(b'MeMeCode=', pos):
                nstart = pos + 9
                require(nstart + 4 <= len(body), 'FRAME_SHORT', 'Inline binary length is missing')
                amount = struct.unpack_from('<I', body, nstart)[0]
                bstart, bend = nstart + 4, nstart + 4 + amount
                require(amount <= LIMIT and bend + 2 <= len(body) and body[bend:bend+2] == b'\r\n',
                        'FRAME_SHORT', 'Inline binary frame is truncated')
                pos = bend + 2
                current.tokens.append(Token(begin, pos, 'MeMeCode', str(amount).encode(), bstart, bend, 'opaque'))
                continue
            newline = body.find(b'\r\n', pos)
            require(newline >= 0, 'LINE_END', 'Editable stream has no CRLF terminator', offset=pos)
            line = body[pos:newline]
            pos = newline + 2
            if current and current.name == 'LuaData' and line.startswith(b'<EXTENT>LuaXmlFileLen='):
                amount = integer(line.split(b'=', 1)[1])
                bstart, bend = pos, pos + amount
                require(bend <= len(body) and body[bend:bend+2] == b'\r\n', 'FRAME_SHORT', 'Lua XML opaque extent is truncated')
                pos = bend + 2
                current.tokens.append(Token(begin, pos, 'LuaXmlFileLen', str(amount).encode(), bstart, bend, 'blob'))
                continue
            header = re.fullmatch(rb'\[([A-Za-z][A-Za-z0-9_ -]*)\]', line)
            if header:
                name = header[1].decode('ascii')
                if current:
                    current.end = begin
                if name in RESOURCE_HEADERS or name not in {'Application', 'Screen', 'AuxKeyElement', 'Element', 'State'} | PREAMBLE_HEADERS:
                    self.tail_start = begin
                    self.stop_reason = 'resource:' + name if name in RESOURCE_HEADERS else 'unknown_section:' + name
                    break
                current = Section(name, begin, pos, len(body))
                self.sections.append(current)
                continue
            require(current is not None, 'SECTION', 'Native record occurs before a section')
            match = re.fullmatch(rb'([A-Za-z][A-Za-z0-9_ -]*)=([^\r\n]*)', line)
            if not match:
                require(b'\r' not in line and b'\n' not in line, 'LINE_END', 'Unframed embedded newline')
                current.tokens.append(Token(begin, pos, None, kind='raw'))
                if line:
                    self.unqualified_records.append(begin)
                continue
            key, value = match[1].decode('ascii'), match[2]
            # TZ compatibility patch HMI-001: observed 6.6.2.48 Application
            # communication metadata is an inline three-line record. Size counts
            # the following field-name bytes plus its C terminator, not a blob
            # after the size line. Preserve the entire record as one opaque token;
            # this adds indexing coverage without granting a generic edit path.
            comm_size = re.fullmatch(r'CommAdvFieldSize([0-9]+)', key)
            if current.name == 'Application' and comm_size:
                versions = [t.value for t in current.tokens
                            if t.key in ('Version', 'ApplicationVersion', 'NewVersion') and t.value]
                require(versions and all(v == b'6.6.2.48' for v in versions),
                        'COMM_ADV_VERSION', 'Communication metadata version is not qualified')
                suffix = comm_size[1].encode('ascii')
                amount = integer(value, 4096)
                field_end = body.find(b'\r\n', pos)
                require(field_end >= 0, 'COMM_ADV_FRAME', 'Communication field line is truncated')
                field_line = body[pos:field_end]
                expected = b'CommAdvField' + suffix + b'='
                require(field_line.startswith(expected) and len(field_line) - len(expected) + 1 == amount
                        and b'\0' not in field_line and b'\n' not in field_line and b'\r' not in field_line,
                        'COMM_ADV_FRAME', 'Communication field length or owner differs')
                default_start = field_end + 2
                default_end = body.find(b'\r\n', default_start)
                require(default_end >= 0, 'COMM_ADV_FRAME', 'Communication default line is truncated')
                default_line = body[default_start:default_end]
                require(default_line.startswith(b'CommAdvDefValue' + suffix + b'=')
                        and b'\0' not in default_line and b'\n' not in default_line and b'\r' not in default_line,
                        'COMM_ADV_FRAME', 'Communication default owner differs')
                pos = default_end + 2
                current.tokens.append(Token(begin, pos, key, value, kind='opaque'))
                continue
            count, kind = None, 'scalar'
            if WIDE.fullmatch(key):
                count, kind = integer(value), 'wide'
            elif MACRO.fullmatch(key):
                count, kind = integer(value), 'macro'
            elif key in ('SysKeyPwd', 'HmiID', 'AppCommentMulti', 'FTPPwdLen', 'EipDTBase64Len'):
                count, kind = integer(value), 'blob'
            elif key in ('CustomerPalette', 'PointLen'):
                count, kind = integer(value) * (4 if key == 'CustomerPalette' else 8), 'blob'
            elif key in ('RcpGroup', 'Rcp32Group'):
                width_key = 'RcpLen' if key == 'RcpGroup' else 'Rcp32Len'
                count = integer(current.one(width_key).value) * integer(value) * (2 if key == 'RcpGroup' else 4)
                kind = 'blob'
            elif re.search(r'(?:Len|Length|Bytes|Size)[0-9]*$', key) and value != b'0' and not (
                    current.name in PREAMBLE_HEADERS and re.fullmatch(r'Length[0-9]{3}', key)) and key not in {
                    'RcpLen', 'Rcp32Len', 'FontSize0', 'FontSize1', 'ElementFontSize', 'ReduceFontSize',
                    'ScrollSize', 'USBCachSize', 'ReadCtrlVarSize', 'CustomerScrollbarPictureSize', 'MemLen',
                    'LanguageFontSize0', 'LanguageFontSize1', 'LanguageFontSize2', 'FontSize2', 'UnitFontSize1', 'UnitFontSize2', 'TitleTextFontSize001', 'TitleTextFontSize002', 'GDRangeFontSize', 'GHRangeFontSize', 'GBRangeFontSize', 'GARangeFontSize',
                    'AccountLen', 'DirectoryLen', 'GetFileNameResultLen', 'NameLen', 'PasswordLen', 'RTCLength',
                    'SelectedLen', 'ByteLen0', 'TitleTextFontSize000', 'UnitFontSize0', 'RangeFontSize', 'StringLen', 'OffsetLength'}:
                # A new length-like owner is not safely assumed to be scalar.
                self.tail_start = begin
                self.stop_reason = 'unknown_frame:' + key
                break
            bstart = bend = None
            if count is not None:
                require(count <= LIMIT and pos + count <= len(body), 'FRAME_SHORT', 'Counted data is truncated', field=key)
                bstart, bend = pos, pos + count
                pos = bend
                if count:
                    if kind == 'macro':
                        require(body[bstart:bend].endswith(b'\r\n'), 'MACRO_FRAME', 'Macro byte length includes final CRLF')
                    else:
                        require(body[pos:pos+2] == b'\r\n', 'FRAME_END', 'Counted data terminator is missing', field=key)
                        pos += 2
                if kind == 'wide' and count:
                    require(count >= 2 and count % 2 == 0 and body[bend-2:bend] == b'\0\0',
                            'UTF16', 'Counted UTF-16 requires an even byte length and terminal NUL')
                    try:
                        body[bstart:bend-2].decode('utf-16-le', 'strict')
                    except UnicodeDecodeError as exc:
                        raise AgentError('UTF16', 'Invalid UTF-16 native text') from exc
            current.tokens.append(Token(begin, pos, key, value, bstart, bend, kind))
        if current:
            current.end = self.tail_start
        require(self.sections and self.sections[0].name == 'Application', 'SECTION', 'Application section is required')

    def scalar(self, sec, key, default=None):
        token = sec.one(key, optional=default is not None)
        return token.value.decode('latin-1') if token else default

    def number(self, sec, key, default=None):
        token = sec.one(key, optional=default is not None)
        return scalar_int(token.value, key) if token else default

    def text(self, sec, key, default=None):
        token = sec.one(key, optional=default is not None)
        return token.text(self.body) if token else default

    def block(self, sections):
        return self.body[sections[0].start:sections[-1].end]


def encode_token(token, value, body):
    require(token.key is not None, 'RAW_WRITE', 'Opaque records are not generic properties')
    if token.kind == 'wide':
        require(isinstance(value, str) and '\0' not in value, 'TEXT', 'Text must not contain NUL')
        try:
            blob = value.encode('utf-16-le', 'strict') + b'\0\0'
        except UnicodeEncodeError as exc:
            raise AgentError('TEXT', 'Invalid Unicode surrogate') from exc
        return token.key.encode() + b'=' + str(len(blob)).encode() + b'\r\n' + blob + b'\r\n'
    require(token.kind == 'scalar', 'COUPLED_FIELD', 'Counted lengths and opaque fields cannot be edited independently')
    require(isinstance(value, (str, int)) and not isinstance(value, bool), 'SCALAR', 'Expected a string or integer')
    text = str(value)
    require('\r' not in text and '\n' not in text and '\0' not in text, 'SCALAR', 'Scalar contains framing characters')
    try:
        raw = text.encode('ascii', 'strict')
    except UnicodeEncodeError as exc:
        raise AgentError('SCALAR', 'Scalar is not ASCII; use a counted text field') from exc
    return token.key.encode() + b'=' + raw + b'\r\n'


@dataclass(frozen=True)
class Patch:
    start: int
    end: int
    old: bytes
    new: bytes
    reason: str


def apply_spans(source, patches):
    ordered = sorted(patches, key=lambda p: (p.start, p.end))
    last = 0
    chunks, ledger = [], []
    candidate_pos = 0
    for patch in ordered:
        require(0 <= patch.start <= patch.end <= len(source) and patch.start >= last,
                'PATCH_OVERLAP', 'Invalid or overlapping byte intervals')
        require(source[patch.start:patch.end] == patch.old, 'PRECONDITION', 'Exact old native bytes changed')
        unchanged = source[last:patch.start]
        chunks.extend((unchanged, patch.new))
        candidate_pos += len(unchanged)
        ledger.append({'source_start': patch.start, 'source_end': patch.end,
                       'candidate_start': candidate_pos, 'candidate_end': candidate_pos + len(patch.new),
                       'old_hex': patch.old.hex(), 'new_hex': patch.new.hex(), 'reason': patch.reason})
        candidate_pos += len(patch.new)
        last = patch.end
    chunks.append(source[last:])
    result = b''.join(chunks)
    require(restore_spans(result, ledger) == source, 'INVERSE', 'Full payload inverse failed')
    return result, ledger


def restore_spans(candidate, ledger):
    result = candidate
    for entry in reversed(ledger):
        a, b = entry['candidate_start'], entry['candidate_end']
        require(result[a:b].hex() == entry['new_hex'], 'INVERSE', 'Candidate changed outside recorded plan')
        result = result[:a] + bytes.fromhex(entry['old_hex']) + result[b:]
    return result


@dataclass
class Element:
    section: Section
    states: list
    page_id: int
    index: int
    end: int


@dataclass
class Page:
    section: Section
    aux: list
    elements: list
    page_id: int
    end: int


class Project:
    def __init__(self, data):
        self.file = NativeFile(data)
        self.index = NativeIndex(self.file.payload)
        self.app = self.index.sections[0]
        self.pages = []
        current = element = None
        for section in self.index.sections[1:]:
            if section.name == 'Screen':
                if current:
                    current.end = section.start
                if element:
                    element.end = section.start
                pid = self.index.number(section, 'ID')
                require(all(p.page_id != pid for p in self.pages), 'PAGE_ID', 'Duplicate screen identity')
                current = Page(section, [], [], pid, self.index.tail_start)
                self.pages.append(current)
                element = None
            elif section.name == 'Element':
                require(current is not None, 'OWNER', 'Element has no screen')
                if element:
                    element.end = section.start
                element = Element(section, [], current.page_id, len(current.elements), self.index.tail_start)
                current.elements.append(element)
            elif section.name == 'State':
                require(element is not None, 'OWNER', 'State has no element')
                element.states.append(section)
            elif section.name == 'AuxKeyElement':
                require(current is not None and element is None, 'OWNER', 'Ambiguous auxiliary-key ownership')
                current.aux.append(section)
            else:
                require(current is None, 'SECTION_UNQUALIFIED', 'Unsupported section inside screen stream', section=section.name)
        for page in self.pages:
            identities = [self.index.number(e.section, 'nPartsID') for e in page.elements]
            require(len(set(identities)) == len(identities), 'ELEMENT_ID', 'Duplicate screen-local element identity')
            for e in page.elements:
                values = [self.index.number(st, 'Value') for st in e.states]
                require(len(set(values)) == len(values), 'STATE_ID', 'Duplicate state Value')

    def page(self, page_id):
        found = [p for p in self.pages if p.page_id == page_id]
        require(len(found) == 1, 'PAGE_ID', 'Screen identity was not found')
        return found[0]

    def element(self, page_id, element_id):
        require(isinstance(element_id, int) and not isinstance(element_id, bool) and element_id >= 0,
                'ELEMENT_ID', 'Element identity must be a nonnegative integer, never a negative index')
        found = [e for e in self.page(page_id).elements if self.index.number(e.section, 'nPartsID') == element_id]
        require(len(found) == 1, 'ELEMENT_ID', 'Screen-local element identity was not found')
        return found[0]

    def metadata(self):
        keys = ('Version', 'ApplicationVersion', 'NewVersion', 'PanelSeries', 'PanelName', 'ModelName',
                'PanelResWidth', 'PanelResHeight', 'DefaultScreen')
        return {k: self.index.scalar(self.app, k, '') for k in keys}


def layout_digest(project):
    """Digest of indexed ownership boundaries, for caller-reviewed scope only."""
    import json
    rows = [[s.name, s.start, s.end, [[t.key, t.kind, t.start, t.end] for t in s.tokens]]
            for s in project.index.sections]
    return digest(json.dumps(rows, separators=(',', ':'), ensure_ascii=True).encode('ascii'))
