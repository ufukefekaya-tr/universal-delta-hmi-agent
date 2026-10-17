"""Lossless records; length-delimited strings and macros are never line-split."""
from dataclasses import dataclass, field
import re
import struct

from ..errors import HmiError
from .codec import MAX_PAYLOAD

_SECTION = re.compile(rb"\[([A-Za-z][A-Za-z0-9_ -]*)\]")
_FIELD = re.compile(rb"([A-Za-z][A-Za-z0-9_ -]*)=(.*)")
# Opaque resource tables follow the editable screen stream. Their internal
# binary syntax is deliberately outside V1; preserve the complete suffix.
_TAIL = {"SubMacro", "Global_Auxkey", "Alarm", "History", "TextBank", "Tag",
         "EthernetIPTag", "SRAM_DATA", "Picture", "Background", "SlotFile",
         "CWPFile", "DeviceTable", "END"}
MAX_RECORDS = 2_000_000


def unsigned(value, label):
    if not re.fullmatch(rb"[0-9]+", value):
        raise HmiError("NATIVE_FRAME", "A framed length must be a nonnegative integer", field=label)
    # Check before int() so an adversarial decimal length cannot bypass our
    # explicit error contract through Python's integer conversion digit limit.
    digits = value.lstrip(b"0") or b"0"
    maximum = str(MAX_PAYLOAD).encode("ascii")
    if len(digits) > len(maximum) or (len(digits) == len(maximum) and digits > maximum):
        raise HmiError("NATIVE_LIMIT", "A framed length exceeds the payload limit", field=label)
    return int(digits)


def is_wide(key):
    return ((key.startswith("w") and "Len" in key)
            or re.fullmatch(r"G[DHBA]wKPFStringLen[0-9-]+", key) is not None
            or re.fullmatch(r"TitleTextLen[0-9-]+", key) is not None
            # Observed numeric-unit captions belong to Element, not State.
            # Their decimal length counts UTF-16LE bytes including NUL; do
            # not extend this rule to arbitrary keys containing TextLen.
            or re.fullmatch(r"UnitTextLen[0-9]+", key) is not None)


@dataclass
class Record:
    raw: bytes
    key: str | None = None
    value: bytes = b""
    blob: bytes | None = None
    kind: str | None = None

    def set_value(self, value, force=False):
        if self.value == value and not force:
            return
        if self.kind == "inline_binary":
            raise HmiError("NATIVE_OPAQUE_FIELD", "Opaque inline binary fields are read-only", field=self.key)
        self.value = value
        self.raw = self.key.encode("ascii") + b"=" + value + b"\r\n"
        if self.blob is not None:
            self.raw += self.blob
            if self.kind != "macro":
                self.raw += b"\r\n"

    def text(self):
        if self.kind != "wide":
            raise HmiError("NATIVE_TEXT", "Field is not a native wide text")
        if not self.blob:
            return ""
        try:
            return self.blob[:-2].decode("utf-16-le", "strict")
        except UnicodeDecodeError as exc:
            raise HmiError("NATIVE_TEXT", "Native UTF-16 text is malformed", field=self.key) from exc

    def set_text(self, text):
        if not isinstance(text, str) or "\0" in text:
            raise HmiError("INVALID_TEXT", "Text must be a string without embedded NUL")
        if self.kind == "wide" and self.text() == text:
            return
        try:
            self.blob = text.encode("utf-16-le", "strict") + b"\0\0"
        except UnicodeEncodeError as exc:
            raise HmiError("INVALID_TEXT", "Text contains an invalid Unicode surrogate") from exc
        self.kind = "wide"
        self.set_value(str(len(self.blob)).encode("ascii"), force=True)


@dataclass
class Section:
    name: str
    header: bytes
    records: list[Record] = field(default_factory=list)

    def check_unique(self, controlled):
        seen = set()
        for record in self.records:
            if record.key not in controlled:
                continue
            if record.key in seen:
                raise HmiError("AMBIGUOUS_FIELD", "Controlled native field appears more than once",
                               section=self.name, field=record.key)
            seen.add(record.key)

    def fields(self, controlled=()):
        self.check_unique(controlled)
        return {r.key: r.value.decode("latin-1") for r in self.records if r.key is not None}

    def one(self, key, required=True):
        matches = [r for r in self.records if r.key == key]
        if len(matches) > 1:
            raise HmiError("AMBIGUOUS_FIELD", "Native field appears more than once", section=self.name, field=key)
        if not matches:
            if required:
                raise HmiError("MISSING_NATIVE_FIELD", "Qualified native field is absent", section=self.name, field=key)
            return None
        return matches[0]

    def bytes(self):
        return self.header + b"".join(r.raw for r in self.records)


@dataclass
class Document:
    sections: list[Section]
    tail: bytes

    @classmethod
    def parse(cls, body):
        if not isinstance(body, bytes):
            raise HmiError("NATIVE_PAYLOAD", "Native records require bytes")
        if len(body) > MAX_PAYLOAD:
            raise HmiError("NATIVE_LIMIT", "Native records exceed the payload limit")
        pos = 0
        sections = []
        current = None
        records = 0
        while pos < len(body):
            start = pos
            records += 1
            if records > MAX_RECORDS:
                raise HmiError("NATIVE_LIMIT", "Native section/record count exceeds the parser limit")
            # Observed DIAScreen Application.MeMeCode framing is inline, unlike
            # the following-line decimal-length frames below: exact ASCII key,
            # uint32 LE byte count, opaque bytes, CRLF. Never split its binary
            # payload on line endings or interpret it as section/field text.
            # value exposes only the derived count; raw remains authoritative.
            if current is not None and current.name == "Application" and body.startswith(b"MeMeCode=", pos):
                pos += len(b"MeMeCode=")
                if pos + 4 > len(body):
                    raise HmiError("NATIVE_FRAME", "Inline binary field lacks its uint32 length", field="MeMeCode")
                count = struct.unpack_from("<I", body, pos)[0]
                pos += 4
                if count > MAX_PAYLOAD:
                    raise HmiError("NATIVE_LIMIT", "Inline binary length exceeds the payload limit", field="MeMeCode")
                if pos + count > len(body):
                    raise HmiError("NATIVE_FRAME", "Inline binary frame runs past the payload", field="MeMeCode")
                blob = body[pos:pos + count]
                pos += count
                if body[pos:pos + 2] != b"\r\n":
                    raise HmiError("NATIVE_FRAME", "Inline binary frame lacks its trailing CRLF", field="MeMeCode")
                pos += 2
                current.records.append(Record(body[start:pos], "MeMeCode", str(count).encode("ascii"), blob, "inline_binary"))
                continue
            end = body.find(b"\r\n", pos)
            if end < 0:
                raise HmiError("NATIVE_CRLF", "Native record lacks its CRLF terminator", offset=pos)
            line = body[pos:end]
            pos = end + 2
            if b"\r" in line or b"\n" in line:
                raise HmiError("NATIVE_CRLF", "Native record contains an unframed line ending", offset=start)
            section = _SECTION.fullmatch(line)
            if section:
                name = section[1].decode("ascii")
                if name in _TAIL:
                    return cls(sections, body[start:])
                current = Section(name, body[start:pos])
                sections.append(current)
                continue
            if current is None:
                raise HmiError("NATIVE_SECTION", "Record occurs before a native section")
            match = _FIELD.fullmatch(line)
            if match is None:
                current.records.append(Record(body[start:pos]))
                continue
            key = match[1].decode("ascii")
            value = match[2]
            count = None
            kind = None
            if is_wide(key):
                count, kind = unsigned(value, key), "wide"
            elif re.fullmatch(r"[A-Za-z0-9_]*MacroLen[0-9]*", key):
                count, kind = unsigned(value, key), "macro"
            elif key in {"SysKeyPwd", "HmiID", "AppCommentMulti", "FTPPwdLen"}:
                count, kind = unsigned(value, key), "blob"
            elif key == "CustomerPalette":
                count, kind = unsigned(value, key) * 4, "blob"
            elif key == "PointLen":
                count, kind = unsigned(value, key) * 8, "blob"
            elif key in {"RcpGroup", "Rcp32Group"}:
                size_key = "RcpLen" if key == "RcpGroup" else "Rcp32Len"
                prior_sizes = [r for r in current.records if r.key == size_key]
                if not prior_sizes:
                    raise HmiError("NATIVE_FRAME", "Recipe group lacks its preceding size", field=key)
                size = prior_sizes[-1].value
                count = unsigned(size, size_key) * unsigned(value, key) * (2 if key == "RcpGroup" else 4)
                kind = "blob"
            blob = None
            if count is not None:
                if count > MAX_PAYLOAD or pos + count > len(body):
                    raise HmiError("NATIVE_FRAME", "Native frame runs past the payload", field=key)
                blob = body[pos:pos + count]
                pos += count
                if count:
                    if kind == "macro":
                        if not blob.endswith(b"\r\n"):
                            raise HmiError("NATIVE_FRAME", "Macro length must include its final CRLF", field=key)
                    else:
                        if body[pos:pos + 2] != b"\r\n":
                            raise HmiError("NATIVE_FRAME", "Native frame lacks its trailing CRLF", field=key)
                        pos += 2
                if kind == "wide" and count:
                    if count % 2 or count < 2 or not blob.endswith(b"\0\0"):
                        raise HmiError("NATIVE_TEXT", "UTF-16 frame needs even bytes and a terminal NUL", field=key)
                    Record(b"", key, value, blob, kind).text()
            current.records.append(Record(body[start:pos], key, value, blob, kind))
        return cls(sections, b"")

    def bytes(self):
        return b"".join(s.bytes() for s in self.sections) + self.tail
