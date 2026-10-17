# SPDX-License-Identifier: Apache-2.0
"""Original bounded access to selected counted resources in the opaque suffix."""
from dataclasses import dataclass
import re
import struct

from .errors import AgentError, digest, require
from .native import LIMIT, Patch, integer


@dataclass(frozen=True)
class Resource:
    section: str
    start: int
    length_start: int
    blob_start: int
    blob_end: int
    metadata: dict


def _header(body, found, section, count_key):
    marker = ('[' + section + ']\r\n').encode('ascii')
    require(body.startswith(marker, found), 'RESOURCE_LOCATION', 'Reviewed resource header differs')
    cursor = found + len(marker)
    metadata = {}
    allowed = {'DIATagResource', 'DIATagDevName', 'DIATagLinkName', 'DIATagStationNr',
               'DiaTagXmlPath', 'DiaTagProjectName', 'DIATagDevType',
               'DIATagXmlLastTimeStampH', 'DIATagXmlLastTimeStampL', 'DiaTagPrjFilePath',
               'DiaTagDeviceID', 'DiaTagUseRelativePath', count_key}
    for _ in range(100):
        end = body.find(b'\r\n', cursor)
        require(end >= 0 and end - cursor <= 32768, 'RESOURCE_FRAME', 'Resource header is truncated')
        match = re.fullmatch(rb'([A-Za-z][A-Za-z0-9_]*)=([^\r\n]*)', body[cursor:end])
        require(match is not None, 'RESOURCE_FRAME', 'Unqualified resource header')
        key, value = match[1].decode('ascii'), match[2]
        require(key in allowed and key not in metadata, 'RESOURCE_HEADER', 'Unknown or duplicate resource metadata')
        metadata[key] = value.decode('latin-1')
        if key == count_key:
            amount = integer(value)
            start, stop = end + 2, end + 2 + amount
            require(stop <= len(body), 'RESOURCE_SHORT', 'Resource data is truncated')
            return Resource(section, found, cursor, start, stop, metadata)
        cursor = end + 2
    raise AgentError('RESOURCE_HEADER', 'Too many resource metadata fields')


def validate_reviewed_resources(project, layout):
    require(isinstance(layout, dict) and layout.get('reviewed_boundary_ack') is True
            and layout.get('source_payload_sha256') == digest(project.file.payload),
            'RESOURCE_LAYOUT_HASH', 'Reviewed boundaries require the exact payload hash and explicit review acknowledgement')
    rows = layout.get('frames')
    require(isinstance(rows, list) and len(rows) <= 128, 'RESOURCE_LAYOUT', 'Invalid reviewed resource list')
    result = []
    for item in rows:
        section = item.get('section')
        require(section in ('Picture', 'Background', 'DIATag'), 'RESOURCE_LAYOUT', 'Resource type is outside the reviewed contract')
        offset = item.get('header_start')
        require(type(offset) is int and project.index.tail_start <= offset < len(project.file.payload), 'RESOURCE_LAYOUT', 'Invalid reviewed resource position')
        frame = _header(project.file.payload, offset, section, 'size' if section == 'DIATag' else 'Size')
        require(digest(project.file.payload[frame.start:frame.blob_start]) == item.get('header_sha256')
                and digest(project.file.payload[frame.blob_start:frame.blob_end]) == item.get('blob_sha256'),
                'RESOURCE_LAYOUT_HASH', 'Reviewed header/blob digest mismatch')
        require(all(frame.start >= x.blob_end or frame.blob_end <= x.start for x in result),
                'RESOURCE_NESTED', 'Reviewed resources overlap or nest')
        result.append(frame)
    return result


def map_reviewed_resources(project, layout, payload, patches):
    """Carry a caller-reviewed boundary through only recorded exact byte edits."""
    if layout is None:
        return None
    previous = validate_reviewed_resources(project, layout)
    rows = []
    for frame in previous:
        require(all(p.end <= frame.start or p.start >= frame.blob_end or
                    (p.start == frame.length_start and p.end == frame.blob_end) for p in patches),
                'RESOURCE_LAYOUT', 'An edit removed a reviewed boundary')
        offset = frame.start + sum(len(p.new) - len(p.old) for p in patches if p.end <= frame.start)
        updated = _header(payload, offset, frame.section, 'size' if frame.section == 'DIATag' else 'Size')
        rows.append({'section': frame.section, 'header_start': offset,
                     'header_sha256': digest(payload[updated.start:updated.blob_start]),
                     'blob_sha256': digest(payload[updated.blob_start:updated.blob_end])})
    return {'reviewed_boundary_ack': True, 'source_payload_sha256': digest(payload), 'frames': rows}


def resource_frames(project, section, count_key):
    reviewed = getattr(project, 'reviewed_resources', None)
    if reviewed is not None:
        return [r for r in validate_reviewed_resources(project, reviewed) if r.section == section]
    body = project.file.payload
    results = []
    cursor = project.index.tail_start
    active = None
    while cursor < len(body):
        end = body.find(b'\r\n', cursor)
        require(end >= 0, 'RESOURCE_OWNER', 'Opaque resource ownership is unqualified; provide reviewed boundaries')
        row = body[cursor:end]
        head = re.fullmatch(rb'\[([A-Za-z0-9_ -]+)\]', row)
        if head:
            active = head[1].decode('ascii')
            if active in ('Picture', 'Background', 'DIATag'):
                frame = _header(body, cursor, active, 'size' if active == 'DIATag' else 'Size')
                if active == section:
                    results.append(frame)
                # Skip the entire counted owner, including any fake nested headers.
                cursor = frame.blob_end
                if body[cursor:cursor+2] == b'\r\n':
                    cursor += 2
                continue
            if active == 'END':
                return results
            require(active in ('SubMacro', 'Global_Auxkey'), 'RESOURCE_OWNER',
                    'Unknown preceding resource grammar needs source-hash-bound reviewed boundaries', section=active)
        elif row:
            require(active == 'SubMacro' and re.fullmatch(rb'SubMacro(?:Protect|PWD)[0-9]+=[0-9]+', row),
                    'RESOURCE_OWNER', 'Unqualified opaque resource record')
        cursor = end + 2
    return results


def resource(project, section, count_key, index=0):
    frames = resource_frames(project, section, count_key)
    require(type(index) is int and 0 <= index < len(frames), 'RESOURCE_INDEX', 'Resource index is invalid')
    return frames[index]


def resource_patch(project, frame, count_key, blob, expected_sha256):
    body = project.file.payload
    require(isinstance(blob, bytes) and len(blob) <= LIMIT, 'RESOURCE_LIMIT', 'Invalid replacement resource size')
    old_blob = body[frame.blob_start:frame.blob_end]
    require(digest(old_blob) == expected_sha256, 'RESOURCE_HASH', 'Resource hash changed')
    old = body[frame.length_start:frame.blob_end]
    new = count_key.encode() + b'=' + str(len(blob)).encode() + b'\r\n' + blob
    return Patch(frame.length_start, frame.blob_end, old, new, 'counted ' + frame.section + ' resource')


def embedded_xml(project, index=0):
    frame = resource(project, 'DIATag', 'size', index)
    return frame, project.file.payload[frame.blob_start:frame.blob_end]


def flat_dib(width, height, color):
    require(type(width) is int and type(height) is int and 1 <= width <= 8192 and 1 <= height <= 8192,
            'DIB_SIZE', 'DIB dimensions are outside bounds')
    require(type(color) is int and 0 <= color <= 0xffffff, 'DIB_COLOR', 'Expected packed RGB color')
    row_bytes = (width * 3 + 3) // 4 * 4
    require(row_bytes * height <= LIMIT // 2, 'DIB_LIMIT', 'DIB is too large')
    red, green, blue = color >> 16, color >> 8 & 255, color & 255
    row = bytes((blue, green, red)) * width + b'\0' * (row_bytes - width * 3)
    header = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, row_bytes * height, 0, 0, 0, 0)
    return header + row * height
