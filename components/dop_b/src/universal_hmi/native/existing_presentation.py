"""Bounded existing-owner presentation, separate from exact preservation.

The registered evidence authority is checked by the public caller. This module
checks a pinned closed native graph and canonical scalar transformations. The
source editor reads actual CRLF lengths and emits scalar strings with their
actual lengths; no binary, caption, macro, address, or resource frame is edited.
Stored configuration acceptance is not vendor, runtime, or pixel acceptance.
"""
from copy import deepcopy
import re

from ..errors import HmiError
from . import NativeAdapter, _groups
from .existing_program import (ExistingProgram, _bounded, _id, _sha, _SHA,
                               _MODEL, _VERSION, _FAMILY)


_DESCRIPTOR_KEYS = {"qualified", "contract_version", "mode", "source_sha256",
                    "family", "model_id", "editor_version", "authority_sha256"}
_BUTTON = {("1", subtype) for subtype in ("1", "2", "3", "4", "10")}
_NUMERIC = {("5", "1"), ("6", "1")}
_SURFACE = _BUTTON | {("2", "1")}
_LITERAL = ("10", "6")
_FONT_SIZES = frozenset((8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36,
                         40, 48, 64, 72))
_FONT_RATIOS = frozenset((33, 50, 100, 150, 200))
_CANONICAL = re.compile(rb"0|[1-9][0-9]{0,9}")
_STATE_VALUE = re.compile(r"0|[1-9][0-9]{0,9}")
_STATE_KEYS = {"value", "state_sha256", "font_size", "font_ratio", "font_color",
               "surface_color"}


def presentation_contract(descriptor):
    """Validate the standalone descriptor; a hash alone is not trust."""
    _bounded(descriptor)
    if (not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_KEYS
            or descriptor.get("qualified") is not True
            or type(descriptor.get("contract_version")) is not int
            or descriptor["contract_version"] != 1
            or descriptor.get("mode") != "variable_scalar_records_v1"
            or descriptor.get("family") != _FAMILY
            or type(descriptor.get("model_id")) is not int
            or descriptor["model_id"] != _MODEL
            or descriptor.get("editor_version") != _VERSION):
        raise HmiError("UNQUALIFIED_EXISTING_PRESENTATION",
                       "Presentation requires its separate exact static B10 descriptor")
    for key in ("source_sha256", "authority_sha256"):
        if not isinstance(descriptor[key], str) or not _SHA.fullmatch(descriptor[key]):
            raise HmiError("UNQUALIFIED_EXISTING_PRESENTATION",
                           "Presentation descriptor pins require canonical SHA-256", field=key)
    return deepcopy(descriptor)


def _integer(value, label, low=0, high=0xFFFFFF):
    if type(value) is not int or not low <= value <= high:
        raise HmiError("INVALID_PRESENTATION_VALUE", "Presentation value must be a bounded integer", field=label)
    return value


def _scalar(record, maximum=0xFFFFFFFF):
    if (record.kind is not None or record.blob is not None
            or not _CANONICAL.fullmatch(record.value)
            or record.raw != record.key.encode("ascii") + b"=" + record.value + b"\r\n"
            or int(record.value) > maximum):
        raise HmiError("UNQUALIFIED_PRESENTATION_FIELD",
                       "Target field is outside the canonical ordinary scalar frame", field=record.key)
    return int(record.value)


def _pin(value, actual, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value) or value != actual:
        raise HmiError("EXISTING_PRESENTATION_PIN", "Presentation target differs from its exact immutable pin", field=label)


class ExistingPresentation:
    """Patch existing scalar records while preserving every other source byte.

    Operations are exact ``set_existing_presentation`` owner requests. Geometry
    is the full x/y/width/height object. Visual accepts native_style and optional
    border_color. State requests identify an original Value string and complete
    State SHA, then specify font_size/font_ratio/font_color/surface_color.
    COLORREF is an integer (0x00BBGGRR), not an RGB565 or alpha encoding.
    """

    def __init__(self, source, existing_graph_schema, presentation_descriptor):
        self.contract = presentation_contract(presentation_descriptor)
        self._contract_snapshot = tuple(sorted(self.contract.items()))
        self.source = source
        # The original graph authority and contract stay independent. Neither
        # its schema nor ExistingProgram's exact deletion semantics is widened.
        self._graph = ExistingProgram(source, existing_graph_schema)

    def check(self):
        descriptor = presentation_contract(self.contract)
        if tuple(sorted(descriptor.items())) != self._contract_snapshot:
            raise HmiError("UNQUALIFIED_EXISTING_PRESENTATION", "Presentation descriptor changed after construction")
        if self._graph.source is not self.source:
            raise HmiError("INVALID_PRESENTATION_SOURCE", "Presentation source cannot be replaced after construction")
        self._graph.check()
        if descriptor["source_sha256"] != _sha(self.source.original):
            raise HmiError("INVALID_PRESENTATION_SOURCE", "Presentation descriptor does not match the original source bytes")
        return True

    def _changes(self, operations):
        """Validate intent and resolve original record identities, before copy."""
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > 4096:
            raise HmiError("INVALID_OPERATIONS", "Presentation operations must be a bounded list")
        self.check()
        pages = _groups(self.source.document)
        owners = {(page["id"], owner["id"]): (page, owner)
                  for page in pages for owner in page["elements"]}
        sections = self.source.document.sections
        section_indices = {id(section): index for index, section in enumerate(sections)}
        changes, seen = {}, set()

        def change(section, key, value):
            record = section.one(key)
            _scalar(record)
            index = next(i for i, item in enumerate(section.records) if item is record)
            location = (section_indices[id(section)], index)
            if location in changes:
                raise HmiError("DUPLICATE_PRESENTATION_FIELD", "Repeated presentation record target is refused", field=key)
            changes[location] = str(value).encode("ascii")

        for operation in operations:
            required = {"op", "screen_id", "element_id", "owner_sha256"}
            optional = {"geometry", "visual", "states"}
            if (not isinstance(operation, dict) or not required <= set(operation)
                    or set(operation) - required - optional
                    or operation.get("op") != "set_existing_presentation"
                    or not set(operation) & optional):
                raise HmiError("INVALID_PRESENTATION_OPERATION", "Only exact pinned set_existing_presentation requests are supported")
            target = (_id(operation["screen_id"], "screen_id", 65535),
                      _id(operation["element_id"], "element_id"))
            if target in seen:
                raise HmiError("DUPLICATE_PRESENTATION_OWNER", "Repeated native presentation owner is refused")
            seen.add(target)
            found = owners.get(target)
            if found is None:
                raise HmiError("MISSING_PRESENTATION_OWNER", "Presentation target is absent from the pinned source")
            page, owner = found
            _pin(operation["owner_sha256"], _sha(b"".join(s.bytes() for s in sections[owner["start"]:owner["end"]])), "owner_sha256")
            section = owner["section"]
            pair = (section.one("Type").value.decode("ascii"), section.one("SubType").value.decode("ascii"))
            if pair not in _SURFACE | _NUMERIC | {_LITERAL}:
                raise HmiError("UNQUALIFIED_PRESENTATION_KIND", "Owner has no qualified presentation field-role contract")
            if pair == _LITERAL:
                self._graph._inert(owner)
            if "geometry" in operation:
                geometry = operation["geometry"]
                if not isinstance(geometry, dict) or set(geometry) != {"x", "y", "width", "height"}:
                    raise HmiError("INVALID_PRESENTATION_GEOMETRY", "Geometry requires exactly x/y/width/height")
                x, y = (_integer(geometry[k], k, 0, 65535) for k in ("x", "y"))
                width, height = (_integer(geometry[k], k, 1, 65535) for k in ("width", "height"))
                canvas_x = _scalar(page["section"].one("PanelSizeX"), 65535)
                canvas_y = _scalar(page["section"].one("PanelSizeY"), 65535)
                if x + width > canvas_x or y + height > canvas_y:
                    raise HmiError("INVALID_PRESENTATION_GEOMETRY", "Presentation rectangle exceeds the original page")
                for key, value in (("X", x), ("Y", y), ("Width", width), ("Height", height)):
                    change(section, key, value)
            visual = operation.get("visual", {})
            if "visual" in operation:
                if (not isinstance(visual, dict) or not visual
                        or set(visual) - {"native_style", "border_color"}):
                    raise HmiError("INVALID_PRESENTATION_VISUAL", "Visual requires only qualified style/border requests")
                if pair == _LITERAL:
                    raise HmiError("UNQUALIFIED_PRESENTATION_ROLE", "Inert literals support geometry and font/text color only")
            style = _scalar(section.one("Style"), 65535)
            if pair != _LITERAL and style not in (0, 1, 2, 3):
                raise HmiError("UNQUALIFIED_PRESENTATION_STYLE", "Existing native style has no qualified presentation mapping")
            if "native_style" in visual:
                style = _integer(visual["native_style"], "native_style", 0, 3)
                change(section, "Style", style)
            if "border_color" in visual:
                if pair not in _NUMERIC or style != 0:
                    raise HmiError("UNQUALIFIED_PRESENTATION_ROLE", "Border color is supported only for resulting numeric native style zero")
                change(section, "BorderColor", _integer(visual["border_color"], "border_color"))
            if "states" not in operation:
                continue
            requests = operation["states"]
            if not isinstance(requests, list) or not requests or len(requests) > len(owner["states"]):
                raise HmiError("INVALID_PRESENTATION_STATES", "State requests must be a nonempty bounded list")
            states = {state.one("Value").value.decode("ascii"): state for state in owner["states"]}
            values = set()
            for request in requests:
                if (not isinstance(request, dict) or not {"value", "state_sha256"} <= set(request)
                        or set(request) - _STATE_KEYS or not set(request) - {"value", "state_sha256"}):
                    raise HmiError("INVALID_PRESENTATION_STATE", "State requests require exact identity/hash and qualified visual fields")
                value = request["value"]
                if not isinstance(value, str) or not _STATE_VALUE.fullmatch(value):
                    raise HmiError("INVALID_PRESENTATION_STATE", "State Value must be the canonical original string")
                if value in values:
                    raise HmiError("DUPLICATE_PRESENTATION_STATE", "Repeated source state Value is refused")
                values.add(value)
                state = states.get(value)
                if state is None:
                    raise HmiError("MISSING_PRESENTATION_STATE", "State Value is absent from the pinned owner")
                _pin(request["state_sha256"], _sha(state.bytes()), "state_sha256")
                if "font_size" in request:
                    size = _integer(request["font_size"], "font_size", 1, 255)
                    if size not in _FONT_SIZES:
                        raise HmiError("UNQUALIFIED_PRESENTATION_FONT", "Font size is not an exact member of both qualified native lists")
                    change(state, "FontSize0", size)
                if "font_ratio" in request:
                    ratio = _integer(request["font_ratio"], "font_ratio", 1, 255)
                    if ratio not in _FONT_RATIOS:
                        raise HmiError("UNQUALIFIED_PRESENTATION_FONT", "Font ratio would be normalized by the native reader")
                    change(state, "FontRatio0", ratio)
                if "font_color" in request:
                    change(state, "FontColor", _integer(request["font_color"], "font_color"))
                if "surface_color" in request:
                    if pair == _LITERAL or style == 3:
                        raise HmiError("UNQUALIFIED_PRESENTATION_ROLE", "Text-only presentation has no qualified surface color")
                    field = "BgColor" if pair in _NUMERIC else "FgColor"
                    change(state, field, _integer(request["surface_color"], "surface_color"))
        # Explicit requests that already match the original scalar are real
        # no-ops: even gzip framing must remain the original byte sequence.
        return {location: value for location, value in changes.items()
                if sections[location[0]].records[location[1]].value != value}

    def _spans(self, changes):
        """Locate original raw record ranges; never serialize a mutated walk."""
        spans, offset = [], 0
        for section_index, section in enumerate(self.source.document.sections):
            offset += len(section.header)
            for record_index, record in enumerate(section.records):
                end = offset + len(record.raw)
                value = changes.get((section_index, record_index))
                if value is not None:
                    raw = record.key.encode("ascii") + b"=" + value + b"\r\n"
                    spans.append((offset, end, raw))
                offset = end
        return spans

    def expected_body(self, operations):
        """Independent source-span substitution, without calling apply()."""
        spans = self._spans(self._changes(operations))
        body, cursor, result = self.source.envelope.body, 0, []
        for start, end, raw in spans:
            result.extend((body[cursor:start], raw))
            cursor = end
        result.append(body[cursor:])
        return b"".join(result)

    def apply(self, operations):
        changes = self._changes(operations)
        if not changes:
            return self.source.original
        document = deepcopy(self.source.document)
        for (section_index, record_index), value in changes.items():
            document.sections[section_index].records[record_index].set_value(value)
        body = document.bytes()
        if body != self.expected_body(operations):
            raise HmiError("EXISTING_PRESENTATION_PRESERVATION", "Native scalar mutation differs from independent source spans")
        raw = self.source.envelope.encode(body)
        self.verify(NativeAdapter(raw, self.source.family), operations)
        return raw

    def verify(self, candidate, operations=None):
        operations = [] if operations is None else operations
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_PRESENTATION_CANDIDATE", "Presentation verification requires a native adapter")
        candidate._preserved_byte_binding("INVALID_PRESENTATION_CANDIDATE")
        changes = self._changes(operations)
        expected = self.expected_body(operations)
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.body != expected or candidate.document.tail != self.source.document.tail):
            raise HmiError("EXISTING_PRESENTATION_PRESERVATION", "Candidate differs outside exactly approved scalar records")
        if not changes and candidate.original != self.source.original:
            raise HmiError("EXISTING_PRESENTATION_PRESERVATION", "A no-op must preserve the complete original file")
        # Walk candidate offsets using the independently expected replacement
        # lengths, and restore original raw scalar spans byte for byte.
        restored, cursor, delta = [], 0, 0
        for start, end, raw in self._spans(changes):
            saved_start = start + delta
            saved_end = saved_start + len(raw)
            restored.extend((candidate.envelope.body[cursor:saved_start], self.source.envelope.body[start:end]))
            cursor = saved_end
            delta += len(raw) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        if b"".join(restored) != self.source.envelope.body:
            raise HmiError("EXISTING_PRESENTATION_PRESERVATION", "Scalar restoration did not recover the complete source body")
        return True
