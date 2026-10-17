"""Clean blank-target assembly from a separately pinned six-control library.

Only cloned, explicitly bound controls enter the output. Library globals,
thumbnail and calibration owners never become target content. This is an
offline byte/shape contract, not vendor, runtime or physical qualification.
"""
from copy import deepcopy
import hashlib
import re
import struct

from ..errors import HmiError
from . import NativeAdapter, _groups
from .records import MAX_RECORDS, unsigned
from .resources import ResourceTables, _line, _record, _suffix_boundary


_SHA = re.compile(r"[0-9a-f]{64}")
_HEADER = re.compile(rb"\[([A-Za-z0-9][A-Za-z0-9_ -]*)\]")
_FIELD = re.compile(rb"([A-Za-z][A-Za-z0-9_ -]*)=(.*)")
_EMPTY_TAG = b"[Tag]\r\nTagLinkCount=0\r\n"
_INITIALIZED_TAG = b"[Tag]\r\nTagLinkCount=1\r\nLinkSize=0\r\n"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _tag_extent(tail):
    """Return the owned Tag extent after a complete bounded framing walk.

    A picture, SRAM database, tag link block or wide/macro payload may contain
    arbitrary header-looking bytes. Their declared frame is skipped intact.
    No substring search establishes ownership or mutation authority.
    """
    resources = ResourceTables.parse(tail)
    suffix = resources.suffix
    boundary = _suffix_boundary(suffix)
    if boundary.get("complete") is not True or "Tag" not in boundary["sections"]:
        raise HmiError("UNQUALIFIED_PROGRAM_TAG", "Program tag initialization requires a completely framed owned Tag resource")
    base = len(resources.prefix) + len(resources.alarm.bytes())
    pos = count = 0
    current = None
    tag_start = tag_end = None
    while pos < len(suffix):
        start = pos
        line, pos = _line(suffix, pos)
        count += 1
        if count > MAX_RECORDS:
            raise HmiError("RESOURCE_LIMIT", "Program resource walk exceeds its record bound")
        header = _HEADER.fullmatch(line)
        name = header[1].decode("ascii") if header else "SysMessage" if line == b"[SysMessage]\0\0\0" else None
        if name is not None:
            if current == "Tag":
                tag_end = start
            current = name
            if name == "Tag":
                tag_start = start
            if name in {"SRAM_DATA", "100_SRAM_DATA"}:
                size = struct.unpack_from("<I", suffix, pos)[0]
                pos += 4 + size + 2  # Complete boundary walk proved framing.
            continue
        match = _FIELD.fullmatch(line)
        if match and current == "Tag" and match[1] == b"LinkSize":
            pos += unsigned(match[2], "LinkSize")
        elif match and current in {"Picture", "Background", "Codesys"} and match[1] in {b"Size", b"size"}:
            pos += unsigned(match[2], match[1].decode("ascii")) + 2
        elif match and ((current == "EthernetIPTag" and match[1] == b"TagTotalSize")
                        or (current == "DIATag" and match[1] == b"DIATagResource")
                        or (current == "DeviceTable" and match[1] == b"DisplayLength")):
            # Complete suffix qualification admitted only exact scalar zero.
            continue
        else:
            _, pos = _record(suffix, start, line, pos, current)
    if tag_start is None or tag_end is None:
        raise HmiError("UNQUALIFIED_PROGRAM_TAG", "Owned Tag section lacks a following framed boundary")
    return base + tag_start, base + tag_end


class BlankProgram:
    """Immutable blank target plus immutable exact typed control library."""

    def __init__(self, target, library, schema):
        self.target, self.library = target, library
        self.schema = deepcopy(schema)

    def library_profile(self):
        contract = self._contract()
        if not isinstance(self.library, NativeAdapter):
            raise HmiError("INVALID_PROGRAM_SOURCE", "Program library must be a native adapter")
        return {"family": self.library.family, "model_id": self.library.model_id,
                "editor_version": self.library.editor_version,
                "native_schema": deepcopy(contract["library_schema"])}

    def _contract(self):
        schema = self.schema
        contract = schema.get("blank_program") if isinstance(schema, dict) else None
        keys = {"qualified", "contract_version", "mode", "target_sha256", "library_sha256", "library_schema", "tag_resource"}
        if (not isinstance(schema, dict) or schema.get("qualified") is not True
                or {"control_generation", "literal_generation", "preserved_layout"} & set(schema)
                or not isinstance(contract, dict) or set(contract) != keys
                or contract.get("qualified") is not True or type(contract.get("contract_version")) is not int
                or contract["contract_version"] != 1 or contract.get("mode") != "blank_program"
                or contract.get("tag_resource") != "initialize_empty_source_tag_link"
                or not isinstance(contract.get("library_schema"), dict)):
            raise HmiError("UNQUALIFIED_BLANK_PROGRAM", "Blank program requires its exact separate target/library contract")
        for key in ("target_sha256", "library_sha256"):
            if not isinstance(contract.get(key), str) or not _SHA.fullmatch(contract[key]):
                raise HmiError("UNQUALIFIED_BLANK_PROGRAM", "Program source pins require canonical SHA-256 values", field=key)
        if {"blank_program", "native_candidate", "literal_generation", "preserved_layout"} & set(contract["library_schema"]):
            raise HmiError("UNQUALIFIED_BLANK_PROGRAM", "Library schema must be the distinct immutable control-generation contract")
        return contract

    @staticmethod
    def _globals(adapter):
        adapter._preserved_prefix(adapter.document)
        first = next(index for index, section in enumerate(adapter.document.sections) if section.name == "Screen")
        return adapter.document.sections[:first]

    @staticmethod
    def _same_global_lineage(target, library):
        left, right = BlankProgram._globals(target), BlankProgram._globals(library)
        if [section.name for section in left] != [section.name for section in right]:
            raise HmiError("PROGRAM_LINEAGE", "Target/library global section order differs")
        for before, after in zip(left, right):
            if before.name != "Application":
                if before.bytes() != after.bytes():
                    raise HmiError("PROGRAM_LINEAGE", "Target/library unmanaged global bytes differ", section=before.name)
                continue
            before.check_unique({"Name", "MeMeCode"})
            after.check_unique({"Name", "MeMeCode"})
            if before.header != after.header or len(before.records) != len(after.records):
                raise HmiError("PROGRAM_LINEAGE", "Application record shape differs")
            for original, donor in zip(before.records, after.records):
                if original.key != donor.key:
                    raise HmiError("PROGRAM_LINEAGE", "Application record order differs")
                if original.key in {"Name", "MeMeCode"}:
                    expected_kind = None if original.key == "Name" else "inline_binary"
                    if original.kind != expected_kind or donor.kind != expected_kind:
                        raise HmiError("PROGRAM_LINEAGE", "Observed application metadata framing differs", field=original.key)
                elif original.raw != donor.raw:
                    raise HmiError("PROGRAM_LINEAGE", "Application changed outside observed Name/MeMeCode save metadata", field=original.key)

    def _tail_transition(self):
        target_tail, library_tail = self.target.document.tail, self.library.document.tail
        start, end = _tag_extent(target_tail)
        donor_start, donor_end = _tag_extent(library_tail)
        if target_tail[start:end] != _EMPTY_TAG or library_tail[donor_start:donor_end] != _INITIALIZED_TAG:
            raise HmiError("UNQUALIFIED_PROGRAM_TAG", "Only the recorded empty TagLinkCount 0 to empty link 1 transition is admitted")
        if target_tail[:start] != library_tail[:donor_start] or target_tail[end:] != library_tail[donor_end:]:
            raise HmiError("PROGRAM_LINEAGE", "Target/library resource bytes differ outside owned empty Tag initialization")
        return target_tail[:start] + _INITIALIZED_TAG + target_tail[end:]

    def check(self):
        contract = self._contract()
        if not isinstance(self.target, NativeAdapter) or not isinstance(self.library, NativeAdapter):
            raise HmiError("INVALID_PROGRAM_SOURCE", "Blank program needs two native adapters")
        for label, adapter in (("target", self.target), ("library", self.library)):
            adapter._preserved_byte_binding("INVALID_PROGRAM_SOURCE")
            adapter._control_prefix_length(adapter)
            if _sha(adapter.original) != contract[label + "_sha256"]:
                raise HmiError("INVALID_PROGRAM_SOURCE", "Program source differs from its immutable pin", source=label)
        if (self.target.family != self.library.family or self.target.model_id != self.library.model_id
                or self.target.editor_version != self.library.editor_version
                or self.target.envelope.prefix[:37] != self.library.envelope.prefix[:37]):
            raise HmiError("PROGRAM_LINEAGE", "Target/library family, model, raw version or opaque envelope lineage differs")
        profile = self.library_profile()
        library_schema = self.library._schema(profile)
        donors = self.library.control_donors(library_schema)
        self.library.verify_control_generation(library_schema)
        left, right = _groups(self.target.document), _groups(self.library.document)
        if any(page["elements"] for page in left):
            raise HmiError("NONEMPTY_PROGRAM_TARGET", "Program target must have zero original owners")
        owners = {(page["id"], owner["id"]) for page in right for owner in page["elements"]}
        pins = library_schema["control_generation"]["donors"]
        if len(owners) != 6 or owners != {(pin["screen_id"], pin["element_id"]) for pin in pins.values()} or len(donors) != 6:
            raise HmiError("INVALID_PROGRAM_LIBRARY", "Program library must contain exactly the six immutable witnessed donors")
        if [page["id"] for page in left] != [page["id"] for page in right]:
            raise HmiError("PROGRAM_LINEAGE", "Target/library page identities or order differ")
        for blank, source in zip(left, right):
            if (blank["section"].bytes() != source["section"].bytes()
                    or self.target._plain_extent(blank).bytes() != self.library._plain_extent(source).bytes()):
                raise HmiError("PROGRAM_LINEAGE", "Target/library page header, dimensions or auxiliary bytes differ")
        self._same_global_lineage(self.target, self.library)
        self._tail_transition()
        return True

    def output_tail(self, has_controls):
        self.check()
        if type(has_controls) is not bool:
            raise HmiError("INVALID_PROGRAM_STATE", "Control presence must be an explicit Boolean")
        return self._tail_transition() if has_controls else self.target.document.tail

    def apply(self, operations):
        self.check()
        if not isinstance(operations, list):
            raise HmiError("INVALID_OPERATIONS", "Program operations must be a list")
        if not operations:
            return self.target.original
        appended = NativeAdapter(self.library.apply(operations, self.library_profile()), self.library.family)
        source_pages, candidate_pages = _groups(self.library.document), _groups(appended.document)
        body = b"".join(section.bytes() for section in self._globals(self.target))
        total = 0
        for blank, source, page in zip(_groups(self.target.document), source_pages, candidate_pages):
            body += blank["section"].bytes() + self.target._plain_extent(blank).bytes()
            for owner in page["elements"][len(source["elements"]):]:
                total += 1
                body += b"".join(section.bytes() for section in appended.document.sections[owner["start"]:owner["end"]])
        if total == 0:
            raise HmiError("PROGRAM_SCOPE", "Nonempty transaction must create a bound control")
        body += self._tail_transition()
        output = self.target.envelope.encode(body)
        self.verify(NativeAdapter(output, self.target.family))
        return output

    def verify(self, candidate):
        self.check()
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_PROGRAM_CANDIDATE", "Program verification needs a saved native adapter")
        candidate._preserved_byte_binding("INVALID_PROGRAM_CANDIDATE")
        candidate._control_prefix_length(candidate)
        if (candidate.family != self.target.family or candidate.model_id != self.target.model_id
                or candidate.editor_version != self.target.editor_version
                or candidate.envelope.prefix[:37] != self.target.envelope.prefix[:37]
                or candidate.envelope.thumbnail != self.target.envelope.thumbnail
                or candidate._preserved_prefix(candidate.document) != self.target._preserved_prefix(self.target.document)):
            raise HmiError("PROGRAM_MISMATCH", "Program changed target identity, globals, thumbnail or opaque envelope")
        blanks, pages, source_pages = _groups(self.target.document), _groups(candidate.document), _groups(self.library.document)
        if [page["id"] for page in pages] != [page["id"] for page in blanks]:
            raise HmiError("PROGRAM_MISMATCH", "Program changed target page identities or order")
        total = sum(len(page["elements"]) for page in pages)
        expected_tail = self._tail_transition() if total else self.target.document.tail
        if candidate.document.tail != expected_tail:
            raise HmiError("PROGRAM_MISMATCH", "Program changed target resources beyond empty owned Tag initialization")
        # Independently establish target framing first. Only then embed final
        # controls after the immutable donors to reuse the strict shape guard.
        context = b"".join(section.bytes() for section in self._globals(self.library))
        for blank, page, source in zip(blanks, pages, source_pages):
            if (page["section"].bytes() != blank["section"].bytes()
                    or candidate._plain_extent(page).bytes() != self.target._plain_extent(blank).bytes()):
                raise HmiError("PROGRAM_MISMATCH", "Program changed target page header or auxiliary framing")
            context += source["section"].bytes() + self.library._plain_extent(source).bytes()
            for owner in source["elements"]:
                context += b"".join(section.bytes() for section in self.library.document.sections[owner["start"]:owner["end"]])
            for owner in page["elements"]:
                context += b"".join(section.bytes() for section in candidate.document.sections[owner["start"]:owner["end"]])
        if not total:
            if candidate.original != self.target.original:
                raise HmiError("PROGRAM_MISMATCH", "Empty program must preserve every target byte")
            return True
        context += self.library.document.tail
        adapter = NativeAdapter(self.library.envelope.encode(context), self.library.family)
        adapter.verify_control_generation(self.library_profile()["native_schema"], self.library)
        return True
