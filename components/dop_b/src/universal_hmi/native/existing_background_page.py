"""Pinned same-size page-background edits in original body coordinates.

Authority registration belongs to the public caller. This module proves the
closed source graph, exact page/frame ownership and byte-scoped replacement;
stored pixels are not an executed editor, panel or visual acceptance claim.
"""
from copy import deepcopy
import struct

from ..errors import HmiError
from . import NativeAdapter, _groups
from .existing_background import MAX_IMAGE_BYTES, frame_pixels_from_png
from .existing_program import (ExistingProgram, _bounded, _id, _sha, _SHA,
                               _MODEL, _VERSION, _FAMILY)
from .records import unsigned
from .resources import ResourceTables, _line, _record, _HEADER, _FIELD


_DESCRIPTOR_KEYS = {"qualified", "contract_version", "mode", "source_sha256",
                    "family", "model_id", "editor_version", "authority_sha256"}
_OPERATION_KEYS = {"op", "screen_id", "frame_sha256", "asset_sha256"}
_MAX_PAGES = 256


def background_contract(descriptor):
    """Validate a separate background descriptor without granting authority."""
    _bounded(descriptor)
    if (not isinstance(descriptor, dict) or set(descriptor) != _DESCRIPTOR_KEYS
            or descriptor.get("qualified") is not True
            or type(descriptor.get("contract_version")) is not int
            or descriptor["contract_version"] != 1
            or descriptor.get("mode") != "fixed_opaque_page_background_v1"
            or descriptor.get("family") != _FAMILY
            or type(descriptor.get("model_id")) is not int or descriptor["model_id"] != _MODEL
            or descriptor.get("editor_version") != _VERSION):
        raise HmiError("UNQUALIFIED_EXISTING_BACKGROUND", "Background requires its separate exact static B10 descriptor")
    for key in ("source_sha256", "authority_sha256"):
        if not isinstance(descriptor[key], str) or not _SHA.fullmatch(descriptor[key]):
            raise HmiError("UNQUALIFIED_EXISTING_BACKGROUND", "Background pins require canonical SHA-256", field=key)
    return deepcopy(descriptor)


class ExistingBackgroundPage:
    """Resolve immutable PNG assets to complete original DIB frame spans.

    Operations have exactly op/screen_id/frame_sha256/asset_sha256. Assets have
    canonical digest keys and immutable PNG values, with exact used coverage.
    Every returned span addresses the original uncompressed native BODY,
    including when another transaction removes earlier owners or grows text.
    """

    def __init__(self, source, existing_graph_schema, background_descriptor):
        self.contract = background_contract(background_descriptor)
        self._contract_snapshot = tuple(sorted(self.contract.items()))
        self.source = source
        self._graph = ExistingProgram(source, existing_graph_schema)

    def check(self):
        descriptor = background_contract(self.contract)
        if tuple(sorted(descriptor.items())) != self._contract_snapshot:
            raise HmiError("UNQUALIFIED_EXISTING_BACKGROUND", "Background descriptor changed after construction")
        if self._graph.source is not self.source:
            raise HmiError("INVALID_BACKGROUND_SOURCE", "Background source cannot be replaced after construction")
        self._graph.check()
        if descriptor["source_sha256"] != _sha(self.source.original):
            raise HmiError("INVALID_BACKGROUND_SOURCE", "Background descriptor differs from the immutable source bytes")
        return True

    def _background_range(self):
        """Walk actual resource lengths; section-like opaque pixels are inert."""
        table = ResourceTables.parse(self.source.document.tail)
        suffix = table.suffix
        body_base = len(self.source.envelope.body) - len(suffix)
        pos, current, found = 0, None, None
        while pos < len(suffix):
            start = pos
            line, pos = _line(suffix, pos)
            header = _HEADER.fullmatch(line)
            if header or line == b"[SysMessage]\0\0\0":
                current = header[1].decode("ascii") if header else "SysMessage"
                if current == "SRAM_DATA":
                    # The closed graph has already verified this exact length,
                    # header and terminator. Never inspect opaque contents.
                    count = struct.unpack_from("<I", suffix, pos)[0]
                    pos += 4 + count + 2
                continue
            field = _FIELD.fullmatch(line)
            if field is not None and current in {"Picture", "Background"} and field[1] == b"Size":
                count = unsigned(field[2], "Size")
                if current == "Background":
                    if found is not None:
                        raise HmiError("UNQUALIFIED_EXISTING_BACKGROUND", "Background resource is repeated")
                    found = (body_base + pos, body_base + pos + count)
                pos += count + 2
            elif field is not None and current == "Tag" and field[1] == b"LinkSize":
                pos += unsigned(field[2], "LinkSize")
            elif (field is not None and current == "DeviceTable"
                  and field[1] == b"DisplayLength" and field[2] == b"0"):
                continue  # Explicit empty device payload, already graph-checked.
            else:
                _, pos = _record(suffix, start, line, pos, current)
        if found is None:
            raise HmiError("UNQUALIFIED_EXISTING_BACKGROUND", "Source has no completely framed background resource")
        return found

    def _frames(self):
        self.check()
        start, end = self._background_range()
        frames, pos = {}, start
        body = self.source.envelope.body
        while pos < end:
            fields = struct.unpack_from("<IiiHHIIiiII", body, pos)
            width, height, image_size = fields[1], fields[2], fields[6]
            size = 40 + image_size
            if size > MAX_IMAGE_BYTES:
                raise HmiError("IMAGE_LIMIT", "Source background frame exceeds the bounded byte budget")
            frames[pos - start] = (pos, pos + size, width, height)
            pos += size
        result = []
        for page in _groups(self.source.document):
            record = page["section"].one("PictureOffset", False)
            if record is None:
                continue  # Closed graph permits this only when Background is empty.
            offset = unsigned(record.value, "PictureOffset")
            first, last, width, height = frames[offset]
            result.append({"screen_id": page["id"], "frame_sha256": _sha(body[first:last]),
                           "width": width, "height": height, "start": first, "end": last})
        return result

    def frame_inventory(self):
        """Return detached original-page frame identities, without artwork."""
        return [{key: value for key, value in frame.items() if key not in {"start", "end"}}
                for frame in self._frames()]

    @staticmethod
    def _assets(assets):
        if type(assets) is not dict or len(assets) > _MAX_PAGES:
            raise HmiError("INVALID_BACKGROUND_ASSETS", "Background assets require a bounded digest-to-bytes object")
        total = 0
        for digest, png in assets.items():
            if (not isinstance(digest, str) or not _SHA.fullmatch(digest)
                    or not isinstance(png, bytes)):
                raise HmiError("INVALID_BACKGROUND_ASSETS", "Assets require canonical SHA keys and immutable PNG bytes")
            total += len(png)
            if len(png) > MAX_IMAGE_BYTES or total > MAX_IMAGE_BYTES:
                raise HmiError("IMAGE_LIMIT", "Background PNG assets exceed the bounded byte budget")
            if _sha(png) != digest:
                raise HmiError("BACKGROUND_ASSET_PIN", "Background PNG differs from its digest key")
        return assets

    def spans(self, operations, assets):
        """Return sorted disjoint original BODY ranges and same-size frames."""
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > _MAX_PAGES:
            raise HmiError("INVALID_OPERATIONS", "Background operations require a bounded list")
        assets = self._assets(assets)
        frames = {frame["screen_id"]: frame for frame in self._frames()}
        seen, used, spans = set(), set(), []
        for operation in operations:
            if (not isinstance(operation, dict) or set(operation) != _OPERATION_KEYS
                    or operation.get("op") != "set_existing_background"):
                raise HmiError("INVALID_BACKGROUND_OPERATION", "Only exact pinned set_existing_background requests are supported")
            sid = _id(operation["screen_id"], "screen_id", 65535)
            if sid in seen:
                raise HmiError("DUPLICATE_BACKGROUND_PAGE", "A background page can be targeted only once")
            seen.add(sid)
            frame = frames.get(sid)
            if frame is None:
                raise HmiError("MISSING_BACKGROUND_PAGE", "Target page has no original uniquely owned background frame")
            digest = operation["frame_sha256"]
            if not isinstance(digest, str) or not _SHA.fullmatch(digest) or digest != frame["frame_sha256"]:
                raise HmiError("BACKGROUND_FRAME_PIN", "Background frame differs from its immutable source pin")
            asset = operation["asset_sha256"]
            if not isinstance(asset, str) or not _SHA.fullmatch(asset) or asset not in assets:
                raise HmiError("BACKGROUND_ASSET_PIN", "Background request requires its exact supplied PNG digest")
            used.add(asset)
            first, last = frame["start"], frame["end"]
            original = self.source.envelope.body[first:last]
            replacement = frame_pixels_from_png(original, assets[asset])
            if len(replacement) != last - first or replacement[:40] != original[:40]:
                raise HmiError("EXISTING_BACKGROUND_PRESERVATION", "Background conversion changed frame size or header")
            if replacement != original:
                spans.append((first, last, replacement))
        if used != set(assets):
            raise HmiError("BACKGROUND_ASSET_COVERAGE", "Background assets must exactly cover referenced PNG digests")
        return sorted(spans)

    def _expected(self, spans):
        body, cursor, pieces = self.source.envelope.body, 0, []
        for start, end, frame in spans:
            pieces.extend((body[cursor:start], frame))
            cursor = end
        pieces.append(body[cursor:])
        return b"".join(pieces)

    def expected_body(self, operations, assets):
        """Reconstruct source fragments independently from mutating apply()."""
        return self._expected(self.spans(operations, assets))

    def apply(self, operations, assets):
        spans = self.spans(operations, assets)
        if not spans:
            return self.source.original
        body = bytearray(self.source.envelope.body)
        for start, end, frame in spans:
            body[start:end] = frame
        expected = self._expected(spans)
        if bytes(body) != expected:
            raise HmiError("EXISTING_BACKGROUND_PRESERVATION", "Background mutation differs from source-span reconstruction")
        raw = self.source.envelope.encode(expected)
        self.verify(NativeAdapter(raw, self.source.family), operations, assets)
        return raw

    def verify(self, candidate, operations=None, assets=None):
        operations = [] if operations is None else operations
        assets = {} if assets is None else assets
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_BACKGROUND_CANDIDATE", "Background verification requires a native adapter")
        candidate._preserved_byte_binding("INVALID_BACKGROUND_CANDIDATE")
        spans = self.spans(operations, assets)
        expected = self._expected(spans)
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.body != expected):
            raise HmiError("EXISTING_BACKGROUND_PRESERVATION", "Candidate differs outside exactly approved background frames")
        if not spans and candidate.original != self.source.original:
            raise HmiError("EXISTING_BACKGROUND_PRESERVATION", "A no-op must preserve the complete original file")
        restored = bytearray(candidate.envelope.body)
        for start, end, _ in spans:
            restored[start:end] = self.source.envelope.body[start:end]
        if bytes(restored) != self.source.envelope.body:
            raise HmiError("EXISTING_BACKGROUND_PRESERVATION", "Frame restoration did not recover the complete source body")
        return True
