# SPDX-License-Identifier: Apache-2.0
"""Original, bounded SVG model of saved native layers; never vendor pixels.

Only the explicit ``flat-v1`` profile is modeled. Font bytes, when supplied,
come from the caller; this module never searches a computer's font directories.
The background digest covers one exact 40-byte DIB header plus padded pixels.
Resource suffixes are read, never reserialized or changed here.
"""
import base64
from decimal import Decimal, InvalidOperation
import html
import json
import struct
import zlib

from .errors import AgentError, digest, require
from .resources import resource_frames

LEVEL = 'OFFLINE_MODEL_ONLY'
TYPES = {'10.2', '10.3', '10.6', '1.3', '1.4', '1.7', '1.10', '2.1', '5.1', '6.1'}
NUMERIC = {'5.1', '6.1'}
BINARY_COMMAND = {'1.3', '1.4'}
STATIC = {'10.2', '10.3', '10.6', '1.7', '1.10'}
MAX_PIXELS = 16 * 1024 * 1024


def _supported(ok, message, **details):
    require(ok, 'UNSUPPORTED_RENDER', message, **details)


def _xml(text, attribute=False):
    _supported(all(c in '\t\n\r' or 0x20 <= ord(c) <= 0xd7ff or 0xe000 <= ord(c) <= 0xfffd
                   or 0x10000 <= ord(c) <= 0x10ffff for c in text), 'Text is not representable in XML 1.0')
    return html.escape(text, quote=attribute)


def _color(value):
    _supported(0 <= value <= 0xffffff, 'Color must be observed 24-bit BGR')
    return '#%02x%02x%02x' % (value & 255, (value >> 8) & 255, (value >> 16) & 255)


def _png(width, height, rgb):
    def chunk(kind, value):
        return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff)
    rows = b''.join(b'\0' + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def decode_dib(blob, offset=0):
    """Read one BI_RGB frame, including its native stride and orientation."""
    _supported(isinstance(blob, bytes) and isinstance(offset, int) and not isinstance(offset, bool)
               and 0 <= offset <= len(blob) - 40, 'Invalid background DIB offset')
    header, width, signed_height, planes, bits, compression, size, _, _, used, _ = struct.unpack_from('<IiiHHIIiiII', blob, offset)
    height = abs(signed_height)
    _supported(header == 40 and width > 0 and height > 0 and width * height <= MAX_PIXELS
               and planes == 1 and bits in (24, 32) and compression == 0 and used == 0,
               'Only bounded 24/32-bit BI_RGB DIB frames are modeled')
    stride = ((width * bits + 31) // 32) * 4
    amount = stride * height
    _supported(size in (0, amount) and offset + 40 + amount <= len(blob), 'Truncated or inconsistent DIB pixels')
    frame = blob[offset:offset + 40 + amount]
    pixels = frame[40:]
    rgb = bytearray(width * height * 3)
    step = bits // 8
    for y in range(height):
        source_y = height - 1 - y if signed_height > 0 else y
        row = pixels[source_y * stride:source_y * stride + width * step]
        target = bytearray(width * 3)
        target[0::3], target[1::3], target[2::3] = row[2::step], row[1::step], row[0::step]
        rgb[y * width * 3:(y + 1) * width * 3] = target
    return {'width': width, 'height': height, 'rgb': bytes(rgb), 'frame_sha256': digest(frame),
            'frame_length': len(frame), 'offset': offset, 'bits': bits, 'stride': stride}


def _background_blob(project):
    # Ownership comes from the safe resource walk or a separately reviewed,
    # source-hash-bound locator. A matching digest alone does not prove that a
    # header embedded inside another resource is a real Background section.
    try:
        backgrounds = resource_frames(project, 'Background', 'Size')
        pictures = resource_frames(project, 'Picture', 'Size')
    except AgentError as exc:
        raise AgentError('UNSUPPORTED_RENDER', 'Background resource ownership is not qualified', cause=exc.code) from exc
    _supported(len(backgrounds) == 1, 'Background resource is absent or ambiguous')
    frame = backgrounds[0]
    _supported(not any(p.blob_start <= frame.start < p.blob_end for p in pictures),
               'Background header is nested in a picture resource')
    return project.index.body[frame.blob_start:frame.blob_end]


class _Font:
    """Small independent SFNT cmap/hmtx reader, without outline rendering."""
    def __init__(self, raw):
        _supported(isinstance(raw, bytes) and 12 <= len(raw) <= 32 * 1024 * 1024,
                   'Font must be bounded SFNT bytes')
        _supported(raw[:4] in (b'\0\1\0\0', b'OTTO', b'true'), 'Unknown font container')
        self.raw, self.tables = raw, {}
        count = self.u16(4)
        _supported(1 <= count <= 512 and 12 + 16 * count <= len(raw), 'Invalid SFNT directory')
        for at in range(12, 12 + 16 * count, 16):
            tag, _, offset, size = struct.unpack_from('>4sIII', raw, at)
            _supported(tag not in self.tables and offset + size <= len(raw), 'Invalid or duplicate SFNT table')
            self.tables[tag] = (offset, size)
        head, head_size = self.table(b'head')
        hhea, hhea_size = self.table(b'hhea')
        maxp, maxp_size = self.table(b'maxp')
        _supported(head_size >= 20 and hhea_size >= 36 and maxp_size >= 6, 'Short font metrics tables')
        self.units = self.u16(head + 18)
        self.ascent, self.descent = self.s16(hhea + 4), self.s16(hhea + 6)
        self.metrics, self.glyphs = self.u16(hhea + 34), self.u16(maxp + 4)
        hmtx, amount = self.table(b'hmtx')
        _supported(16 <= self.units <= 16384 and 0 < self.metrics <= self.glyphs
                   and amount >= self.metrics * 4 + (self.glyphs - self.metrics) * 2,
                   'Inconsistent font metrics')
        self.advances = [self.u16(hmtx + i * 4) for i in range(self.metrics)]
        cmap, cmap_size = self.table(b'cmap')
        _supported(cmap_size >= 4, 'Short cmap')
        entries = self.u16(cmap + 2)
        _supported(4 + entries * 8 <= cmap_size, 'Truncated cmap directory')
        choices = []
        for i in range(entries):
            platform, encoding, rel = struct.unpack_from('>HHI', raw, cmap + 4 + i * 8)
            if platform not in (0, 3) or platform == 3 and encoding not in (1, 10):
                continue
            _supported(rel + 2 <= cmap_size, 'Invalid cmap subtable offset')
            sub = cmap + rel
            form = self.u16(sub)
            if form in (4, 12):
                length = self.u32(sub + 4) if form == 12 else self.u16(sub + 2)
                _supported(rel + length <= cmap_size, 'Truncated cmap subtable')
                choices.append((form, sub, length))
        _supported(bool(choices), 'No supported Unicode cmap format 4 or 12')
        self.form, self.cmap, self.cmap_size = max(choices)
        if self.form == 12:
            _supported(self.cmap_size >= 16, 'Short cmap12 header')
            self.groups = self.u32(self.cmap + 12)
            _supported(16 + self.groups * 12 <= self.cmap_size and self.groups <= 200000,
                       'Invalid cmap12 groups')
            previous = -1
            for i in range(self.groups):
                start, end, glyph = struct.unpack_from('>III', raw, self.cmap + 16 + i * 12)
                _supported(previous < start <= end <= 0x10ffff and glyph + end - start < self.glyphs,
                           'Unsorted or invalid cmap12 glyph range')
                previous = end
        else:
            _supported(self.cmap_size >= 16, 'Short cmap4 header')
            doubled = self.u16(self.cmap + 6)
            _supported(doubled > 0 and doubled % 2 == 0, 'Invalid cmap4 segment count')
            self.segments = doubled // 2
            _supported(self.segments > 0 and 16 + self.segments * 8 <= self.cmap_size, 'Invalid cmap4 segments')
            previous = -1
            for i in range(self.segments):
                end = self.u16(self.cmap + 14 + i * 2)
                start = self.u16(self.cmap + 16 + self.segments * 2 + i * 2)
                _supported(previous < start <= end, 'Unsorted or overlapping cmap4 segments')
                previous = end

    def u16(self, at):
        _supported(0 <= at <= len(self.raw) - 2, 'Font field outside bytes')
        return struct.unpack_from('>H', self.raw, at)[0]

    def s16(self, at):
        _supported(0 <= at <= len(self.raw) - 2, 'Font field outside bytes')
        return struct.unpack_from('>h', self.raw, at)[0]

    def u32(self, at):
        _supported(0 <= at <= len(self.raw) - 4, 'Font field outside bytes')
        return struct.unpack_from('>I', self.raw, at)[0]

    def table(self, name):
        _supported(name in self.tables, 'Required font table absent', table=name.decode('ascii'))
        return self.tables[name]

    def glyph(self, code):
        if self.form == 12:
            left, right = 0, self.groups
            while left < right:
                middle = (left + right) // 2
                start, end, glyph = struct.unpack_from('>III', self.raw, self.cmap + 16 + middle * 12)
                if code < start:
                    right = middle
                elif code > end:
                    left = middle + 1
                else:
                    result = glyph + code - start
                    return result if result < self.glyphs else 0
            return 0
        if code > 0xffff:
            return 0
        n, at = self.segments, self.cmap
        ends, starts = at + 14, at + 16 + 2 * n
        deltas, offsets = at + 16 + 4 * n, at + 16 + 6 * n
        for i in range(n):
            if self.u16(starts + 2 * i) <= code <= self.u16(ends + 2 * i):
                delta, offset = self.s16(deltas + 2 * i), self.u16(offsets + 2 * i)
                if offset == 0:
                    result = (code + delta) & 0xffff
                    return result if result < self.glyphs else 0
                pos = offsets + 2 * i + offset + 2 * (code - self.u16(starts + 2 * i))
                _supported(offset % 2 == 0 and at + 16 + 8 * n <= pos <= at + self.cmap_size - 2,
                           'cmap4 glyph reference escapes glyphIdArray')
                glyph = self.u16(pos)
                result = (glyph + delta) & 0xffff if glyph else 0
                return result if result < self.glyphs else 0
        return 0

    def width(self, text, size):
        glyphs = [self.glyph(ord(c)) for c in text]
        _supported(all(glyphs), 'Font lacks a required glyph', reason='MISSING_GLYPH')
        return sum(self.advances[min(g, self.metrics - 1)] for g in glyphs) * size / self.units


def _image_effects(section):
    for token in section.tokens:
        key = token.key or ''
        if key.startswith(('Picture', 'PIB')) and key != 'PictureAlign':
            _supported(token.value in (b'', b'0', b'None'), 'Unsupported picture reference')
        if 'Effect' in key or key in ('ImageStretch', 'UsePictureCoord', 'Twinkles', 'PosVary', 'SizeVary', 'ColorVary'):
            _supported(token.value in (b'', b'0', b'None'), 'Unsupported dynamic drawing effect')
        if 'Radius' in key:
            _supported(token.value == b'0', 'Unqualified rounded geometry')


def _state_profile(project, element, state, fonts, profile):
    idx = project.index
    number = lambda key, default=0: idx.number(state, key, default)
    family = idx.scalar(state, 'FontName0', 'Arial')
    _supported(family == 'Arial' or family in fonts, 'Unqualified font family')
    _xml(family, True)
    _supported(number('FontRatio0', 100) == 100 and number('FontItalic') == 0
               and number('FontUnderline') == 0 and number('FillStyle', 1) == 1
               and number('TransEffect') == 0 and number('Twinkles') == 0
               and number('UsePictureCoord') == 0, 'Unsupported state font, image or effect')
    _supported(number('FontAlign', 34) in (18, 33, 34, 36) and 1 <= number('FontSize0', 16) <= 256
               and number('FontBold') in (0, 1), 'Unsupported font alignment or size')
    _image_effects(state)
    font_keys = {'FontName0', 'FontSize0', 'FontAlign', 'FontRatio0', 'FontBold', 'FontItalic', 'FontUnderline', 'FontColor'}
    fill_keys = {'FillStyle'}
    for prefix in ('FgFill', 'BgFill', 'BorderFill'):
        fill_keys.update(prefix + suffix for suffix in ('Type', 'Color', 'EndColor', 'Style', 'AngleArg', 'XArg', 'YArg'))
        fill_keys.update(prefix + suffix + str(i) for suffix in ('StopPos', 'StopColor') for i in range(5))
    for token in state.tokens:
        key = token.key or ''
        _supported(not key.startswith('Font') or key in font_keys, 'Unknown font property')
        _supported('Grad' not in key and ('Fill' not in key or key in fill_keys), 'Unknown gradient/fill property')
        if key.endswith(('FillType', 'FillStyle')):
            _supported(token.value == b'1', 'Unknown fill type or style')
        if key.endswith(('FillAngleArg', 'FillXArg', 'FillYArg')):
            _supported(token.value == b'None', 'Dynamic fill coordinates are not modeled')
    for prefix in ('FgFill', 'BgFill', 'BorderFill'):
        colors = [token.value for token in state.tokens if token.key and
                  (token.key in (prefix + 'Color', prefix + 'EndColor') or token.key.startswith(prefix + 'StopColor'))]
        _supported(len(set(colors)) <= 1, 'Nonflat fill is outside flat-v1')
    return family


def _bounds(x, y, width, height, text, size, alignment, font):
    lines = text.split('\n')
    widths = [font.width(line, size) if font else len(line) * size * .65 for line in lines]
    line_height = (font.ascent - font.descent) * size / font.units if font else size * 1.2
    total = max(line_height, size) * len(lines) + 2 * (len(lines) - 1)
    horizontal = alignment & 7
    tx = x + 4 if horizontal == 1 else x + width - 4 if horizontal == 4 else x + width / 2
    top = y + 4 if alignment & 16 else y + (height - total) / 2
    left = tx if horizontal == 1 else tx - max(widths, default=0) if horizontal == 4 else tx - max(widths, default=0) / 2
    return (left, top, left + max(widths, default=0), top + total), tx, top, max(line_height, size)


def _intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _kind(project, element):
    return '%d.%d' % (project.index.number(element.section, 'Type'), project.index.number(element.section, 'SubType'))


def _numeric(project, element, value):
    if value is None:
        return ''
    places = project.index.number(element.section, 'DotNum', 0)
    _supported(0 <= places <= 9, 'Unsupported numeric decimal count')
    try:
        number = Decimal(str(value))
        _supported(number.is_finite() and len(str(value)) <= 128 and number.adjusted() <= 64
                   and number.as_tuple().exponent >= -64, 'Invalid or unbounded numeric preview value')
        return format(number, '.%df' % places)
    except (InvalidOperation, ValueError) as exc:
        raise AgentError('UNSUPPORTED_RENDER', 'Invalid numeric preview value') from exc


def render_preview(project, profile, values=None, fonts=None):
    """Return escaped SVG plus explicit offline evidence and synthetic samples.

    ``profile.page_id`` selects a page; otherwise the saved DefaultScreen does.
    Values use exact saved ReadVar strings. No value is read from a live target.
    """
    _supported(isinstance(profile, dict) and profile.get('preview_model') == 'flat-v1', 'Explicit flat-v1 model required')
    _supported(profile.get('schema_version') == 1 and type(profile.get('schema_version')) is int
               and profile.get('family') == 'diascreen-dop100', 'Unsupported preview profile schema or family')
    panel = profile.get('panel', {})
    width, height = panel.get('width'), panel.get('height')
    _supported(type(width) is int and type(height) is int and width > 0 and height > 0
               and width * height <= MAX_PIXELS, 'Bounded profile panel dimensions required')
    idx = project.index
    _supported(idx.number(project.app, 'PanelResWidth') == width and idx.number(project.app, 'PanelResHeight') == height,
               'Profile does not match saved panel dimensions')
    page_id = profile.get('page_id', idx.number(project.app, 'DefaultScreen'))
    page = project.page(page_id)
    values, fonts = dict(values or {}), dict(fonts or {})
    _supported(all(isinstance(name, str) and name and len(name) <= 200 for name in fonts), 'Invalid font name')
    parsed_fonts = {name: _Font(raw) for name, raw in fonts.items()}
    font_aliases = {name: 'preview-font-' + str(n) for n, name in enumerate(fonts)}
    background = decode_dib(_background_blob(project), idx.number(page.section, 'PictureOffset', 0))
    _supported((background['width'], background['height']) == (width, height), 'Background has another page size')
    expected = profile.get('background_sha256', {}).get(str(page_id))
    _supported(expected == background['frame_sha256'], 'Background frame does not match this page', page_id=page_id)
    issues, samples, layers = [], [], []
    if not parsed_fonts:
        issues.append({'code': 'FONT_METRICS_NOT_VERIFIED', 'message': 'Text bounds are estimates; no font-fit PASS is claimed.'})
    for element in page.elements:
        sec = element.section
        kind = _kind(project, element)
        _supported(kind in TYPES, 'Unqualified element type', type=kind)
        box = tuple(idx.number(sec, key) for key in ('X', 'Y', 'Width', 'Height'))
        x, y, w, h = box
        _supported(0 <= x < x + w <= width and 0 <= y < y + h <= height, 'Element escapes panel')
        style = idx.number(sec, 'Style', 0)
        _image_effects(sec)
        _supported(idx.scalar(sec, 'VisibleVar', 'None') in ('', 'None'), 'Dynamic visibility is outside flat-v1')
        _supported(style in (0, 3) and idx.number(sec, 'RoundRadius', 0) == 0
                   and idx.number(sec, 'EnableCustomRadius', 0) == 0
                   and idx.number(sec, 'GradFillMode', 0) == 0, 'Unsupported element style, radius or gradient')
        for key in ('GradFillStartColor', 'GradFillEndColor'):
            token = sec.one(key, optional=True)
            other = sec.one('GradFillEndColor' if key.endswith('StartColor') else 'GradFillStartColor', optional=True)
            _supported(not token or not other or token.value == other.value, 'Nonflat element gradient')
        _supported(bool(element.states), 'Element has no state')
        for state in element.states:
            state_family = _state_profile(project, element, state, fonts, profile)
            state_font = parsed_fonts.get(state_family)
            state_text = idx.text(state, 'wTextLen0', '') if kind not in NUMERIC else ''
            _xml(state_text)
            if state_font and state_text:
                bounds, _, _, _ = _bounds(x, y, w, h, state_text, idx.number(state, 'FontSize0', 16),
                                          idx.number(state, 'FontAlign', 34), state_font)
                _supported(x <= bounds[0] and y <= bounds[1] and bounds[2] <= x + w and bounds[3] <= y + h,
                           'An unselected state overflows the font-metric estimate', reason='TEXT_OVERFLOW')
        read = idx.scalar(sec, 'ReadVar', 'None')
        val = values.get(read, 0 if kind not in NUMERIC else None)
        if kind in NUMERIC:
            _supported(len(element.states) == 1, 'Numeric element has ambiguous states')
            chosen, text = element.states[0], _numeric(project, element, val)
        elif kind in STATIC:
            _supported(len(element.states) == 1 and idx.number(element.states[0], 'Value') == 0,
                       'Static element needs one saved Value0 state')
            chosen = element.states[0]
            text = idx.text(chosen, 'wTextLen0', '')
        else:
            selected = [state for state in element.states if str(idx.number(state, 'Value')) == str(val)]
            _supported(len(selected) == 1, 'Preview value has no exact saved state', page_id=page_id, element_id=idx.number(sec, 'nPartsID'))
            chosen = selected[0]
            text = idx.text(chosen, 'wTextLen0', '')
        family = idx.scalar(chosen, 'FontName0', 'Arial')
        font = parsed_fonts.get(family)
        if font is None and not any(i.get('font') == family for i in issues):
            issues.append({'code': 'FONT_METRICS_NOT_VERIFIED', 'font': family, 'message': 'Browser font substitution and text fit are not verified.'})
        size, align = idx.number(chosen, 'FontSize0', 16), idx.number(chosen, 'FontAlign', 34)
        text_box, tx, top, line_height = _bounds(x, y, w, h, text, size, align, font)
        if text and font:
            _supported(x <= text_box[0] and y <= text_box[1] and text_box[2] <= x + w and text_box[3] <= y + h,
                       'Font-metric estimate overflows element', reason='TEXT_OVERFLOW')
        sample = {'page_id': page_id, 'element_id': idx.number(sec, 'nPartsID'), 'type': kind,
                  'role': 'command' if kind.startswith('1.') and kind != '1.10' else 'input' if kind.startswith('6.') else 'feedback' if kind in NUMERIC | {'2.1'} else 'decorative',
                  'read': read, 'state_value': idx.number(chosen, 'Value'), 'text': text,
                  'synthetic': True, 'text_bounds': list(text_box),
                  'bounds_basis': 'SFNT_ADVANCE_ESTIMATE' if font else 'UNVERIFIED_ESTIMATE'}
        samples.append(sample)
        layers.append({'element': element, 'kind': kind, 'box': box, 'style': style, 'state': chosen,
                       'text': text, 'text_box': text_box, 'tx': tx, 'top': top, 'line_height': line_height,
                       'font': font, 'family': family, 'size': size, 'align': align})
    for i, layer in enumerate(layers):
        if layer['text'] and layer['font']:
            for later in layers[i + 1:]:
                lx, ly, lw, lh = later['box']
                _supported(later['style'] == 3 or not _intersects(layer['text_box'], (lx, ly, lx + lw, ly + lh)),
                           'Later opaque layer covers text estimate', reason='TEXT_OCCLUSION')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height + 28}" viewBox="0 0 {width} {height + 28}">',
           '<title>SYNTHETIC SAVED-LAYER MODEL — vendor pixels and runtime not verified</title>',
           f'<rect width="{width}" height="28" fill="#222831"/><text x="6" y="19" fill="white" font-size="11">SYNTHETIC · SAVED-LAYER MODEL · VENDOR PIXELS / RUNTIME NOT VERIFIED</text>']
    if fonts:
        svg.append('<defs><style>')
        for name, raw in fonts.items():
            svg.append("@font-face{font-family:'" + font_aliases[name] + "';src:url(data:font/ttf;base64," + base64.b64encode(raw).decode() + ")}")
        svg.append('</style></defs>')
    svg.append('<g transform="translate(0 28)">')
    png = base64.b64encode(_png(width, height, background['rgb'])).decode()
    svg.append(f'<image width="{width}" height="{height}" href="data:image/png;base64,{png}"/>')
    for layer in layers:
        x, y, w, h = layer['box']
        st = layer['state']
        if layer['style'] == 0:
            fill = _color(idx.number(st, 'BgColor', 0))
            border = _color(idx.number(layer['element'].section, 'BorderColor', idx.number(st, 'BgColor', 0)))
            if layer['kind'] in ('10.3', '2.1'):
                svg.append(f'<ellipse cx="{x + w/2:g}" cy="{y + h/2:g}" rx="{w/2:g}" ry="{h/2:g}" fill="{fill}" stroke="{border}"/>')
            else:
                svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{border}"/>')
        if layer['text']:
            anchor = {1: 'start', 2: 'middle', 4: 'end'}[layer['align'] & 7]
            foreground = _color(idx.number(st, 'FontColor', 0xffffff))
            family = _xml(font_aliases.get(layer['family'], layer['family']), True)
            bold = 'bold' if idx.number(st, 'FontBold', 0) else 'normal'
            svg.append(f'<text x="{layer["tx"]:g}" y="{layer["top"]:g}" dominant-baseline="text-before-edge" text-anchor="{anchor}" font-family="{family}" font-size="{layer["size"]}" font-weight="{bold}" fill="{foreground}">')
            for n, line in enumerate(layer['text'].split('\n')):
                svg.append(f'<tspan x="{layer["tx"]:g}" dy="{0 if n == 0 else layer["line_height"] + 2:g}">{_xml(line)}</tspan>')
            svg.append('</text>')
    svg.append('</g></svg>')
    evidence = {'source_payload': digest(project.file.payload), 'page': page_id,
                'background': background['frame_sha256'], 'samples': samples,
                'fonts': {name: digest(raw) for name, raw in fonts.items()}}
    return {'svg': ''.join(svg), 'level': LEVEL, 'issues': issues,
            'layer_digest': digest(json.dumps(evidence, sort_keys=True, ensure_ascii=True).encode()), 'samples': samples}


def _put_fixture(values, address, value):
    if address in ('None', ''):
        return
    _supported(address not in values or Decimal(str(values[address])) == Decimal(str(value)),
               'Conflicting synthetic values share one ReadVar', reason='FIXTURE_CONFLICT')
    values[address] = value


def render_gallery(project, profile, fonts=None):
    """Render independent synthetic cases, not simultaneous PLC-valid states."""
    result = []
    idx = project.index
    for page in project.pages:
        for case in ('OFF', 'ON', 'MINIMUM', 'MAXIMUM_LONG', 'NEGATIVE'):
            values = {}
            for element in page.elements:
                sec, kind = element.section, _kind(project, element)
                address = idx.scalar(sec, 'ReadVar', 'None')
                states = [idx.number(st, 'Value') for st in element.states]
                if kind in BINARY_COMMAND:
                    _supported(set(states) == {0, 1}, 'Binary command fixture requires actual Value0/1')
                if kind in NUMERIC:
                    integers, dots = idx.number(sec, 'IntNum', 1), idx.number(sec, 'DotNum', 0)
                    _supported(1 <= integers <= 20 and 0 <= dots <= 9, 'Unbounded numeric fixture')
                    long = '9' * integers + ('.' + '9' * dots if dots else '')
                    value = (idx.scalar(sec, 'MinValue', '0') if case == 'MINIMUM' else
                             idx.scalar(sec, 'MaxValue', long) if case == 'MAXIMUM_LONG' else
                             '-' + long if case == 'NEGATIVE' and idx.number(sec, 'MemFmt', 2) != 2 else '0')
                    _put_fixture(values, address, value)
                elif kind in BINARY_COMMAND or kind == '2.1':
                    target = 1 if case == 'ON' else 0
                    _supported(target in states, 'Synthetic case has no actual saved state')
                    _put_fixture(values, address, target)
            view = render_preview(project, dict(profile, page_id=page.page_id), values, fonts)
            view.update(page_id=page.page_id, case='SYNTHETIC_' + case,
                        sample_scope='Independent visualization; simultaneous process validity is not asserted')
            result.append(view)
    return result
