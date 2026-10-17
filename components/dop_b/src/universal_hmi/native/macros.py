"""Original bounded framing codec for the observed native REV macro stream.

Instructions, operand encodings and flags remain opaque. Roundtrip framing is
not command, address, clock, or runtime qualification and does not authorize
rewriting macro source independently from its operands.
"""
from dataclasses import dataclass
import hashlib
import struct

from ..errors import HmiError
from .codec import MAX_PAYLOAD


MARKER = b"\x02REV"
EMPTY_LINE = b"\0\0\0\x67"
MAX_LINES = 100_000
MAX_FIELD_BYTES = 1_048_576


@dataclass(frozen=True)
class MacroLine:
    descriptor: bytes
    strings: tuple[bytes, ...] = ()
    flags: bytes = b""

    def bytes(self):
        if not isinstance(self.descriptor, bytes) or len(self.descriptor) != 4:
            raise HmiError("MACRO_FRAME", "Macro descriptor must contain exactly four opaque bytes")
        if self.descriptor == EMPTY_LINE:
            if self.strings != () or self.flags != b"":
                raise HmiError("MACRO_FRAME", "An empty macro line cannot contain operands or flags")
            return self.descriptor + b"\r\n"
        if not isinstance(self.strings, tuple) or len(self.strings) != 5:
            raise HmiError("MACRO_FRAME", "Macro instruction requires source and four operand byte strings")
        if not isinstance(self.flags, bytes) or len(self.flags) != 12:
            raise HmiError("MACRO_FRAME", "Macro flags must contain exactly twelve opaque bytes")
        fields = []
        for value in self.strings:
            if not isinstance(value, bytes):
                raise HmiError("MACRO_FRAME", "Macro strings remain opaque bytes; no encoding is inferred")
            if len(value) > MAX_FIELD_BYTES:
                raise HmiError("MACRO_LIMIT", "Macro field exceeds the parser resource limit")
            fields.append(struct.pack("<I", len(value)) + value)
        return self.descriptor + b"".join(fields) + self.flags + b"\r\n"


@dataclass(frozen=True)
class MacroProgram:
    lines: tuple[MacroLine, ...]

    @classmethod
    def parse(cls, data):
        if not isinstance(data, bytes):
            raise HmiError("MACRO_FRAME", "Native macro data must be bytes")
        if len(data) > MAX_PAYLOAD:
            raise HmiError("MACRO_LIMIT", "Macro program exceeds the parser resource limit")
        if not data.startswith(MARKER):
            raise HmiError("UNSUPPORTED_MACRO_FORMAT", "Macro version marker is not the observed REV format")
        position = len(MARKER)
        lines = []
        while position < len(data):
            if len(lines) >= MAX_LINES:
                raise HmiError("MACRO_LIMIT", "Macro instruction count exceeds the parser resource limit")
            if len(data) - position < 4:
                raise HmiError("MACRO_FRAME", "Macro descriptor is truncated", offset=position)
            descriptor = data[position:position + 4]
            position += 4
            fields = []
            flags = b""
            if descriptor != EMPTY_LINE:
                for field_index in range(5):
                    if len(data) - position < 4:
                        raise HmiError("MACRO_FRAME", "Macro field length is truncated", offset=position, field=field_index)
                    count = struct.unpack_from("<I", data, position)[0]
                    position += 4
                    if count > MAX_FIELD_BYTES:
                        raise HmiError("MACRO_LIMIT", "Macro field length exceeds the parser resource limit", field=field_index)
                    if count > len(data) - position:
                        raise HmiError("MACRO_FRAME", "Macro field exceeds the remaining program bytes", field=field_index)
                    fields.append(data[position:position + count])
                    position += count
                if len(data) - position < 12:
                    raise HmiError("MACRO_FRAME", "Macro flags are truncated", offset=position)
                flags = data[position:position + 12]
                position += 12
            if data[position:position + 2] != b"\r\n":
                raise HmiError("MACRO_FRAME", "Macro line requires its exact CRLF terminator", offset=position)
            position += 2
            lines.append(MacroLine(descriptor, tuple(fields), flags))
        return cls(tuple(lines))

    def bytes(self):
        if not isinstance(self.lines, tuple) or len(self.lines) > MAX_LINES:
            raise HmiError("MACRO_LIMIT", "Macro program must use a bounded immutable line tuple")
        encoded = [MARKER]
        total = len(MARKER)
        for line in self.lines:
            if not isinstance(line, MacroLine):
                raise HmiError("MACRO_FRAME", "Macro program contains a non-line value")
            data = line.bytes()
            total += len(data)
            if total > MAX_PAYLOAD:
                raise HmiError("MACRO_LIMIT", "Macro program exceeds the serializer resource limit")
            encoded.append(data)
        return b"".join(encoded)

    def inspect(self):
        """Framing evidence only, without proprietary source or operand data."""
        return {"format": "REV_FRAMING_ONLY", "semantic_qualification": "UNVERIFIED",
                "line_count": len(self.lines),
                "empty_line_count": sum(line.descriptor == EMPTY_LINE for line in self.lines),
                "sha256": hashlib.sha256(self.bytes()).hexdigest(),
                "lines": [{"descriptor_hex": line.descriptor.hex(),
                           "string_byte_counts": [len(value) for value in line.strings],
                           "flags_sha256": hashlib.sha256(line.flags).hexdigest()}
                          for line in self.lines]}
