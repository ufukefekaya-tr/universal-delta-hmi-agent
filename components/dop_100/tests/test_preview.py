# SPDX-License-Identifier: Apache-2.0
"""Neutral synthetic preview tests, independent of proprietary project files."""
import gzip
import struct
import unittest

from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project
from universal_diascreen_hmi.preview import decode_dib, render_gallery, render_preview


def wide(key, value):
    raw = value.encode('utf-16-le') + b'\0\0'
    return key.encode() + b'=' + str(len(raw)).encode() + b'\r\n' + raw + b'\r\n'


def dib(width=160, signed_height=100, bits=24, color=(20, 30, 40)):
    stride = ((width * bits + 31) // 32) * 4
    pixel = bytes((color[2], color[1], color[0])) + (b'\0' if bits == 32 else b'')
    row = pixel * width + b'\0' * (stride - width * (bits // 8))
    data = row * abs(signed_height)
    return struct.pack('<IiiHHIIiiII', 40, width, signed_height, 1, bits, 0, len(data), 0, 0, 0, 0) + data


def state(value=0, text='Ready', **fields):
    options = {'BgColor': 0x302010, 'FgColor': 0x302010, 'FontColor': 0xe0e0e0,
               'FontName0': 'Arial', 'FontSize0': 10, 'FontAlign': 34, 'FontRatio0': 100,
               'FontBold': 0, 'FontItalic': 0, 'FontUnderline': 0, 'FillStyle': 1,
               'TransEffect': 0, 'Twinkles': 0, 'UsePictureCoord': 0, **fields}
    raw = b'[State]\r\nValue=' + str(value).encode() + b'\r\n'
    raw += b''.join(str(k).encode() + b'=' + str(v).encode() + b'\r\n' for k, v in options.items())
    return raw + wide('wTextLen0', text)


def element(part=1, kind='10.6', states=None, **fields):
    typ, subtype = kind.split('.')
    options = {'Type': typ, 'SubType': subtype, 'nPartsID': part, 'X': 10, 'Y': 10,
               'Width': 130, 'Height': 32, 'Style': 0, 'BorderColor': 0x302010,
               'ReadVar': 'None', **fields}
    raw = b'[Element]\r\n' + b''.join(str(k).encode() + b'=' + str(v).encode() + b'\r\n' for k, v in options.items())
    return raw + b''.join(states if states is not None else [state()])


def project(elements=None, image=None, suffix=b'', second=False):
    image = dib() if image is None else image
    app = b'[Application]\r\nPanelResWidth=160\r\nPanelResHeight=100\r\nDefaultScreen=1\r\n'
    page = b'[Screen]\r\nID=1\r\nPictureOffset=0\r\n[AuxKeyElement]\r\n'
    body = app + page + (element() if elements is None else elements)
    if second:
        body += b'[Screen]\r\nID=2\r\nPictureOffset=0\r\n[AuxKeyElement]\r\n' + element()
    body += b'[Background]\r\nSize=' + str(len(image)).encode() + b'\r\n' + image + b'\r\n[END]\r\n' + suffix
    prefix = b'\0' * 37 + bytes(x ^ 100 for x in struct.pack('<I', len(body)))
    header = bytearray(54)
    header[:2], header[6:10] = b'BM', b'PDAB'
    struct.pack_into('<I', header, 34, 0)
    native = bytes(header) + gzip.compress(bytes(x ^ 100 for x in prefix + body), mtime=0)
    return Project(native), {'schema_version': 1, 'family': 'diascreen-dop100', 'panel': {'width': 160, 'height': 100},
                             'preview_model': 'flat-v1', 'background_sha256': {'1': digest(image), '2': digest(image)}}


def sfnt(cmap_override=None):
    """A small synthetic metrics font; no outlines or installed font dependency."""
    head, hhea, maxp = bytearray(54), bytearray(36), bytearray(6)
    struct.pack_into('>H', head, 18, 1000)
    struct.pack_into('>hh', hhea, 4, 800, -200)
    struct.pack_into('>H', hhea, 34, 2)
    struct.pack_into('>H', maxp, 4, 2)
    hmtx = struct.pack('>HhHh', 500, 0, 500, 0)
    # Map printable ASCII to glyph1 with one group per code; format12 permits it.
    groups = b''.join(struct.pack('>III', code, code, 1) for code in range(32, 127))
    sub = struct.pack('>HHIII', 12, 0, 16 + len(groups), 0, 95) + groups
    cmap = struct.pack('>HHHHI', 0, 1, 3, 10, 12) + sub if cmap_override is None else cmap_override
    tables = {b'head': bytes(head), b'hhea': bytes(hhea), b'maxp': bytes(maxp), b'hmtx': hmtx, b'cmap': cmap}
    offset = 12 + 16 * len(tables)
    directory, body = b'', b''
    for name, raw in tables.items():
        directory += struct.pack('>4sIII', name, 0, offset, len(raw))
        body += raw
        offset += len(raw)
    return struct.pack('>IHHHH', 0x10000, len(tables), 0, 0, 0) + directory + body


class PreviewTests(unittest.TestCase):
    def unsupported(self, call):
        with self.assertRaises(AgentError) as result:
            call()
        self.assertEqual(result.exception.code, 'UNSUPPORTED_RENDER')

    def test_offline_label_escape_no_font_claim_and_source_preserved(self):
        q, profile = project(element(states=[state(text='A<&>')]))
        before = q.file.original, q.index.body
        view = render_preview(q, profile)
        self.assertEqual(view['level'], 'OFFLINE_MODEL_ONLY')
        self.assertIn('SYNTHETIC', view['svg'])
        self.assertIn('A&lt;&amp;&gt;', view['svg'])
        self.assertTrue(any(i['code'] == 'FONT_METRICS_NOT_VERIFIED' for i in view['issues']))
        self.assertEqual(before, (q.file.original, q.index.body))
        self.assertEqual(view['layer_digest'], render_preview(q, profile)['layer_digest'])

    def test_dib_channel_stride_orientation_and_32bit_unused_alpha(self):
        for bits in (24, 32):
            for sign in (1, -1):
                rows = [[(255, 0, 0), (0, 255, 0), (0, 0, 255)], [(1, 2, 3), (4, 5, 6), (7, 8, 9)]]
                stride = ((3 * bits + 31) // 32) * 4
                pixels = b''
                for row in rows[::-1] if sign == 1 else rows:
                    part = b''.join(bytes((b, g, r)) + (b'\xff' if bits == 32 else b'') for r, g, b in row)
                    pixels += part + b'\0' * (stride - len(part))
                frame = struct.pack('<IiiHHIIiiII', 40, 3, sign * 2, 1, bits, 0, len(pixels), 0, 0, 0, 0) + pixels
                result = decode_dib(frame)
                self.assertEqual(result['rgb'], b''.join(bytes(pixel) for row in rows for pixel in row))
                self.assertEqual(result['frame_sha256'], digest(frame))
        self.unsupported(lambda: decode_dib(dib()[:-1]))
        self.unsupported(lambda: decode_dib(dib(), -1))

    def test_wrong_page_background_and_ambiguous_resource(self):
        q, profile = project(second=True)
        profile['background_sha256']['2'] = '0' * 64
        self.unsupported(lambda: render_preview(q, dict(profile, page_id=2)))
        fake = b'\r\n[Background]\r\nSize=1\r\nx\r\n'
        q, profile = project()
        q = Project(q.file.encode(q.index.body.replace(b'\r\n[END]\r\n', fake + b'[END]\r\n')))
        self.unsupported(lambda: render_preview(q, profile))
        q, profile = project()
        saved = q.index.body[q.index.tail_start:]
        embedded = b'\r\n' + saved
        body = q.index.body[:q.index.tail_start] + b'[Picture]\r\nSize=' + str(len(embedded)).encode() + b'\r\n' + embedded + b'\r\n[END]\r\n'
        q = Project(q.file.encode(body))
        self.unsupported(lambda: render_preview(q, profile))

    def test_actual_value_selection_commands_and_no_unknown_fallback(self):
        raw = element(kind='1.3', ReadVar='Local.A', states=[state(1, 'On'), state(0, 'Off')])
        q, profile = project(raw)
        view = render_preview(q, profile, {'Local.A': 1})
        self.assertEqual(view['samples'][0]['text'], 'On')
        self.assertEqual(view['samples'][0]['role'], 'command')
        self.unsupported(lambda: render_preview(q, profile, {'Local.A': 7}))
        gallery = render_gallery(q, profile)
        self.assertEqual(len(gallery), 5)
        self.assertEqual(gallery[1]['samples'][0]['state_value'], 1)
        self.assertTrue(all(v['case'].startswith('SYNTHETIC_') for v in gallery))
        q, profile = project(element(kind='1.7', ReadVar='Local.Mode', SetValue=1, states=[state(0, 'Choose')]))
        self.assertEqual(render_preview(q, profile, {'Local.Mode': 1})['samples'][0]['text'], 'Choose')

    def test_unknown_effect_gradient_radius_and_family(self):
        for fields in ({'FontRatio0': 75}, {'TransEffect': 1}, {'PictureOffset': 99},
                       {'FgFillColor': 1, 'FgFillEndColor': 2}, {'FontName0': 'Unknown'}, {'PictureWidth': 34},
                       {'GradFillMode': 6}, {'FgFillMode': 6}, {'FontUnknownControl': 7}, {'RoundRadius': 4}):
            q, profile = project(element(states=[state(**fields)]))
            self.unsupported(lambda: render_preview(q, profile))
        for fields in ({'RoundRadius': 4}, {'GradFillMode': 6}, {'Style': 9}, {'PictureOffset': 34},
                       {'VisibleVar': 'Local.Visibility'}, {'PosVary': 1}):
            q, profile = project(element(**fields))
            self.unsupported(lambda: render_preview(q, profile))
        q, profile = project()
        self.unsupported(lambda: render_preview(q, dict(profile, preview_model='other')))
        self.unsupported(lambda: render_preview(q, dict(profile, schema_version=2)))
        self.unsupported(lambda: render_preview(q, dict(profile, family='other')))
        q, profile = project(element(states=[state(FontName0='Unknown')]))
        self.unsupported(lambda: render_preview(q, dict(profile, fonts={'Unknown': True})))

    def test_metrics_missing_glyph_overflow_and_occlusion(self):
        font = {'Arial': sfnt()}
        q, profile = project(element(states=[state(text='Fit')]))
        view = render_preview(q, profile, fonts=font)
        self.assertFalse(view['issues'])
        self.assertEqual(view['samples'][0]['bounds_basis'], 'SFNT_ADVANCE_ESTIMATE')
        q, profile = project(element(states=[state(text='\u25cf')]))
        self.unsupported(lambda: render_preview(q, profile, fonts=font))
        q, profile = project(element(Width=10, states=[state(text='Long text')]))
        self.unsupported(lambda: render_preview(q, profile, fonts=font))
        q, profile = project(element() + element(part=2, states=[state(text='')]))
        self.unsupported(lambda: render_preview(q, profile, fonts=font))
        q, profile = project(element() + element(part=2, Style=3, states=[state(text='')]))
        self.assertEqual(render_preview(q, profile, fonts=font)['level'], 'OFFLINE_MODEL_ONLY')

    def test_all_states_checked_not_only_selected(self):
        q, profile = project(element(kind='1.4', ReadVar='Local.A', states=[state(0, 'Off'), state(1, 'On', FontRatio0=40)]))
        self.unsupported(lambda: render_preview(q, profile, {'Local.A': 0}))
        q, profile = project(element(kind='1.4', ReadVar='Local.A', states=[state(0, 'Off'), state(1, '\u25cf')]))
        self.unsupported(lambda: render_preview(q, profile, {'Local.A': 0}, {'Arial': sfnt()}))

    def test_font_input_css_name_and_malformed_metrics(self):
        name = "Font';}svg{fill:red}/*"
        q, profile = project(element(states=[state(text='Fit', FontName0=name)]))
        view = render_preview(q, profile, fonts={name: sfnt()})
        self.assertNotIn("Font';}", view['svg'])
        self.assertIn('preview-font-0', view['svg'])
        q, profile = project()
        self.unsupported(lambda: render_preview(q, profile, fonts={'Arial': b'bad'}))
        self.unsupported(lambda: render_preview(q, profile, fonts={'Arial': 'font.ttf'}))
        sub = struct.pack('>HHHHHHH', 4, 32, 0, 4, 4, 1, 0) + struct.pack('>HHHHHHHHH', 65, 65535, 0, 65, 65535, 0, 1, 2, 1)
        cmap = struct.pack('>HHHHI', 0, 1, 3, 1, 12) + sub
        q, profile = project(element(states=[state(text='A')]))
        self.unsupported(lambda: render_preview(q, profile, fonts={'Arial': sfnt(cmap)}))

    def test_xml_control_characters_rejected(self):
        q, profile = project(element(states=[state(text='A\x01B')]))
        self.unsupported(lambda: render_preview(q, profile))

    def test_numeric_exponent_is_bounded(self):
        q, profile = project(element(kind='5.1', ReadVar='Local.Number', IntNum=2, DotNum=1, MemFmt=1))
        self.unsupported(lambda: render_preview(q, profile, {'Local.Number': '1e10000000'}))

    def test_shared_address_fixture_conflict_and_numeric_cases(self):
        raw = element(kind='1.4', ReadVar='Local.Shared', states=[state(0, 'Off'), state(1, 'On')])
        raw += element(part=2, kind='5.1', Y=50, ReadVar='Local.Shared', IntNum=2, DotNum=1, MemFmt=1, MinValue=-2, MaxValue=9)
        q, profile = project(raw)
        self.unsupported(lambda: render_gallery(q, profile))
        q, profile = project(element(kind='5.1', ReadVar='Local.Number', IntNum=2, DotNum=1, MemFmt=1, MinValue=-2, MaxValue=9))
        gallery = render_gallery(q, profile)
        self.assertEqual(gallery[2]['samples'][0]['text'], '-2.0')
        self.assertEqual(gallery[3]['samples'][0]['text'], '9.0')
        self.assertEqual(gallery[4]['samples'][0]['text'], '-99.9')


if __name__ == '__main__':
    unittest.main()
