# SPDX-License-Identifier: Apache-2.0
"""Counted native macro records; no source compiler or runtime acceptance.

Visible source and parsed operands are independent fields. An unknown opcode is
readable and roundtrips, but disables operand edits for the whole program.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import struct
from collections.abc import Mapping
import zlib

from .errors import AgentError


HEADER = bytes.fromhex("02524556")
TAIL = bytes.fromhex("0101010100000000000000000d0a")
KNOWN_OPCODES = {
    bytes.fromhex("0a00011b"): "BITON",
    bytes.fromhex("0a00011c"): "BITOFF",
    bytes.fromhex("2507031e"): "WORD_ASSIGN",
    bytes.fromhex("140e0348"): "IF_WORD_EQUAL",
    bytes.fromhex("0000005c"): "ELSE",
    bytes.fromhex("0000005d"): "ENDIF",
    bytes.fromhex("240f0700"): "WORD_ADD",
}
MAX_BLOB_BYTES = 8 * 1024 * 1024
MAX_FIELD_BYTES = 65536
MAX_RECORDS = 10000
_SYMBOL_PART = rb"[A-Za-z_][A-Za-z_0-9]*(?:\[-?\d+(?:,-?\d+)*\])*"
_SYMBOL_PATH = _SYMBOL_PART + rb"(?:\." + _SYMBOL_PART + rb")*"
_PARSED_ADDRESS = re.compile(rb"\{([A-Za-z_][A-Za-z_0-9]*)\}(\d+)@(" + _SYMBOL_PATH + rb")\Z")
_BOOL_DESCRIPTOR = bytes.fromhex("7300000000000001ff")


def _fail(code: str, message: str, **details):
    raise AgentError(code, message, **details)


def parse_parsed_address(value: bytes | str) -> dict:
    if isinstance(value, str):
        try:
            value = value.encode("ascii")
        except UnicodeEncodeError:
            _fail("MACRO_OPERAND", "Unsupported parsed address encoding")
    if not isinstance(value, bytes) or len(value) > MAX_FIELD_BYTES:
        _fail("MACRO_OPERAND", "Expected bounded parsed address bytes")
    if b"DIA_TAG@" in value.upper():
        _fail("MACRO_DISPLAY_OPERAND", "Object display syntax cannot be a parsed operand")
    match = _PARSED_ADDRESS.fullmatch(value)
    if not match:
        _fail("MACRO_OPERAND", "Expected {Link}station@Symbol parsed address syntax")
    if len(match[2]) > 9:
        _fail("MACRO_OPERAND", "Station number exceeds the bounded address profile")
    return {"link": match[1].decode("ascii"), "station": int(match[2]),
            "path": match[3].decode("ascii")}


def _check_operand(value: bytes):
    if not isinstance(value, bytes) or len(value) > MAX_FIELD_BYTES:
        _fail("MACRO_OPERAND", "Expected bounded operand bytes")
    if b"DIA_TAG@" in value.upper():
        _fail("MACRO_DISPLAY_OPERAND", "Object display syntax cannot be a parsed operand")
    if value.startswith(b"{"):
        parse_parsed_address(value)
    elif not re.fullmatch(rb"(?:\$\d+|[-+]?\d+(?:\.\d+)?|Var[1-4])", value):
        _fail("MACRO_OPERAND", "Unsupported parsed operand grammar")


@dataclass(frozen=True)
class MacroInstruction:
    opcode: bytes
    fields: tuple[bytes, bytes, bytes, bytes, bytes]
    tail: bytes = TAIL

    @property
    def known(self) -> bool:
        return self.opcode in KNOWN_OPCODES


Instruction = MacroInstruction


@dataclass(frozen=True)
class MacroProgram:
    instructions: tuple[MacroInstruction, ...]

    def to_bytes(self) -> bytes:
        if not self.instructions:
            return b""
        if len(self.instructions) > MAX_RECORDS:
            _fail("MACRO_LIMIT", "Too many macro records")
        output = bytearray(HEADER)
        for instruction in self.instructions:
            if not isinstance(instruction.opcode, bytes) or len(instruction.opcode) != 4:
                _fail("MACRO_OPCODE", "Macro opcode must have four bytes")
            if len(instruction.fields) != 5 or instruction.tail != TAIL:
                _fail("MACRO_FRAMING", "Unsupported field count or record flags")
            output.extend(instruction.opcode)
            for field in instruction.fields:
                if not isinstance(field, bytes) or len(field) > MAX_FIELD_BYTES:
                    _fail("MACRO_LIMIT", "Invalid or oversized macro field")
                output.extend(struct.pack("<I", len(field)))
                output.extend(field)
            output.extend(instruction.tail)
            if len(output) > MAX_BLOB_BYTES:
                _fail("MACRO_LIMIT", "Macro blob exceeds the bounded profile")
        return bytes(output)

    def replace_operand(self, instruction_index: int, field_index: int,
                        expected: bytes, new: bytes) -> bytes:
        """Change one exact parsed field; field zero remains byte-identical."""
        if any(not instruction.known for instruction in self.instructions):
            _fail("MACRO_UNKNOWN_OPCODE", "Unknown opcode prevents macro writes")
        if type(instruction_index) is not int or not 0 <= instruction_index < len(self.instructions):
            _fail("MACRO_INDEX", "Instruction index is outside the program")
        if type(field_index) is not int or field_index not in range(1, 5):
            _fail("MACRO_SOURCE_IMMUTABLE", "Only parsed fields 1 through 4 may be replaced")
        if not isinstance(expected, bytes) or not isinstance(new, bytes):
            _fail("MACRO_OPERAND", "Expected and replacement operands must be bytes")
        current = self.instructions[instruction_index]
        if current.fields[field_index] != expected:
            _fail("MACRO_EXPECTED", "Parsed operand no longer matches the expected bytes")
        _check_operand(new)
        fields = list(current.fields)
        fields[field_index] = new
        changed = list(self.instructions)
        changed[instruction_index] = MacroInstruction(current.opcode, tuple(fields), current.tail)
        encoded = MacroProgram(tuple(changed)).to_bytes()
        reread = parse_macro(encoded)
        if reread.instructions[instruction_index].fields[0] != current.fields[0]:
            _fail("MACRO_PRESERVATION", "Visible macro source changed unexpectedly")
        return encoded

    def inspect(self) -> dict:
        display_operands = [{"instruction_index": number, "field_index": field}
                            for number, item in enumerate(self.instructions)
                            for field in range(1, 5) if b"DIA_TAG@" in item.fields[field].upper()]
        return {"record_count": len(self.instructions),
                "unknown_opcodes": sorted({item.opcode.hex() for item in self.instructions if not item.known}),
                "display_form_parsed_operands": display_operands,
                "operand_status": "INVALID_DISPLAY_FORM" if display_operands else "NOT_SEMANTICALLY_VERIFIED",
                "support": "OBSERVED_RECORD_PROFILE_OFFLINE_ONLY",
                "runtime_acceptance": "NOT_VERIFIED"}


def parse_macro(blob: bytes) -> MacroProgram:
    if not isinstance(blob, bytes):
        _fail("MACRO_INPUT", "Macro blob must be bytes")
    if not blob:
        return MacroProgram(())
    if len(blob) > MAX_BLOB_BYTES:
        _fail("MACRO_LIMIT", "Macro blob exceeds the bounded profile")
    if not blob.startswith(HEADER):
        _fail("MACRO_HEADER", "Unsupported native macro signature")
    position, instructions = len(HEADER), []
    while position < len(blob):
        if len(instructions) >= MAX_RECORDS:
            _fail("MACRO_LIMIT", "Too many macro records")
        if position + 4 > len(blob):
            _fail("MACRO_TRUNCATED", "Truncated macro opcode", offset=position)
        opcode = blob[position:position + 4]
        position += 4
        fields = []
        for _ in range(5):
            if position + 4 > len(blob):
                _fail("MACRO_TRUNCATED", "Truncated field length", offset=position)
            length = struct.unpack_from("<I", blob, position)[0]
            position += 4
            if length > MAX_FIELD_BYTES:
                _fail("MACRO_LIMIT", "Macro field exceeds the bounded profile")
            if position + length > len(blob):
                _fail("MACRO_TRUNCATED", "Truncated macro field", offset=position)
            fields.append(blob[position:position + length])
            position += length
        tail = blob[position:position + len(TAIL)]
        if tail != TAIL:
            _fail("MACRO_FRAMING", "Unsupported or truncated macro flags/trailer", offset=position)
        position += len(TAIL)
        instructions.append(MacroInstruction(opcode, tuple(fields), tail))
    if not instructions:
        _fail("MACRO_FRAMING", "A nonempty macro header requires a record")
    return MacroProgram(tuple(instructions))


def _sha(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        _fail("COMPILED_RECEIPT", "A complete SHA-256 identity is required", field=field)
    return value.lower()


def inspect_compiled(data: bytes, *, artifact_sha: str, source_sha: str,
                     candidate_sha: str, receipt: Mapping) -> dict:
    """Inspect one observed BOOL descriptor signature, with caller-linked provenance.

    This is not a CIN parser, compiler receipt authenticator, or evidence of runtime
    success. Offsets belong to the named scan buffer, not native source fields.
    """
    if not isinstance(data, bytes) or len(data) > 32 * 1024 * 1024:
        _fail("COMPILED_LIMIT", "Compiled observation must be bounded bytes")
    identities = {"artifact_sha256": _sha(artifact_sha, "artifact_sha"),
                  "source_sha256": _sha(source_sha, "source_sha"),
                  "candidate_sha256": _sha(candidate_sha, "candidate_sha")}
    actual = hashlib.sha256(data).hexdigest()
    if identities["artifact_sha256"] != actual:
        _fail("COMPILED_IDENTITY", "Compiled bytes do not match the supplied artifact identity")
    if not isinstance(receipt, Mapping):
        _fail("COMPILED_RECEIPT", "A source/candidate/artifact observation receipt is required")
    for name, expected in identities.items():
        if _sha(receipt.get(name), name) != expected:
            _fail("COMPILED_RECEIPT", "Compiled receipt identity does not match", field=name)
    buffer = data
    scan_domain, compressed_offset = "raw_artifact_bytes", None
    offset = data.find(b"\x1f\x8b\x08")
    if offset >= 0:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            buffer = decoder.decompress(data[offset:], 32 * 1024 * 1024 + 1)
        except zlib.error as exc:
            _fail("COMPILED_GZIP", "Unsupported compressed observation", reason=str(exc))
        if len(buffer) > 32 * 1024 * 1024 or not decoder.eof:
            _fail("COMPILED_LIMIT", "Truncated or oversized compressed observation")
        if decoder.unused_data.startswith(b"\x1f\x8b"):
            _fail("COMPILED_GZIP", "Multiple compressed streams are ambiguous")
        scan_domain, compressed_offset = "decompressed_observation_bytes", offset
    descriptors, ignored = [], []
    position = 0
    while True:
        position = buffer.find(_BOOL_DESCRIPTOR, position)
        if position < 0:
            break
        if len(descriptors) + len(ignored) >= 10000:
            _fail("COMPILED_LIMIT", "Descriptor scan exceeds the bounded profile")
        start = position + len(_BOOL_DESCRIPTOR)
        if start + 2 > len(buffer):
            ignored.append({"offset": position, "reason": "truncated_count"})
        else:
            count = struct.unpack_from("<H", buffer, start)[0]
            end = start + 2 + count
            name = buffer[start + 2:end]
            if count == 0 or count > 4096 or end > len(buffer):
                ignored.append({"offset": position, "reason": "invalid_count"})
            elif not re.fullmatch(_SYMBOL_PATH, name):
                ignored.append({"offset": position, "reason": "unsupported_symbol_encoding"})
            else:
                descriptors.append({"offset": position, "symbol": name.decode("ascii"),
                                    "symbol_byte_length": count, "observed_type_hint": "BOOL"})
        position += 1
    return {**identities, "scan_domain": scan_domain, "gzip_offset": compressed_offset,
            "descriptors": descriptors, "descriptor_count": len(descriptors),
            "ignored_signatures": ignored, "coverage": "PARTIAL_BOOL_SIGNATURE_SCAN",
            "provenance": "CALLER_LINKED_SHA_RECEIPT_ONLY", "full_cin_acceptance": False,
            "compile_acceptance": "NOT_ESTABLISHED", "runtime_acceptance": "NOT_VERIFIED"}
