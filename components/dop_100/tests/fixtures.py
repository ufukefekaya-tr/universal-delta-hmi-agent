# SPDX-License-Identifier: Apache-2.0
"""Original neutral files generated from observed framing, never vendor assets."""
import gzip
import struct
from universal_diascreen_hmi.errors import digest
from universal_diascreen_hmi.resources import flat_dib


def line(key, value):
    return f'{key}={value}\r\n'.encode('ascii')


def wide(key, value):
    blob = value.encode('utf-16-le') + b'\0\0'
    return line(key, len(blob)) + blob + b'\r\n'


def state(value, caption, fill=0x222222):
    values = {'Value': value, 'FontName0': 'Arial', 'FontSize0': 16, 'FontAlign': 34,
              'FontBold': 0, 'FontItalic': 0, 'FontUnderline': 0, 'FontRatio0': 100,
              'FontColor': 0xffffff, 'FgColor': fill, 'BgColor': fill, 'FillStyle': 1,
              'TransEffect': 0, 'Twinkles': 0, 'UsePictureCoord': 0,
              'FgFillType': 6, 'BgFillType': 6, 'FgFillStyle': 1, 'BgFillStyle': 1,
              'FgFillAngle': 'None', 'BgFillAngle': 'None'}
    for side in ('Fg', 'Bg'):
        for suffix in ('Color', 'EndColor', *(f'StopColor{i}' for i in range(5))):
            values[side + 'Fill' + suffix] = fill
    return b'[State]\r\n' + b''.join(line(k, v) for k, v in values.items()) + wide('wTextLen0', caption)


def element(identity, name, typ=1, subtype=3, x=10, y=10, caption='START', address='Main.Start'):
    values = {'nPartsID': identity, 'Type': typ, 'SubType': subtype,
              'X': x, 'Y': y, 'Width': 110, 'Height': 48, 'Style': 0, 'BorderColor': 0x555555,
              'ReadVar': 'DIA_TAG@{Link1}0.' + address,
              'WriteVar': 'DIA_TAG@{Link1}0.' + address if typ in (1, 6) else 'None',
              'TriggerVar': 'DIA_TAG@{Link1}0.Main.Trigger', 'InterLockVar': 'None', 'VisibleVar': 'None',
              'MemLen': 6 if typ == 6 else 0, 'MemFmt': 5 if typ == 6 else 2,
              'MinValue': '0', 'MaxValue': '999', 'IntNum': 3, 'DotNum': 0,
              'GainValue': '1.0', 'OffsetValue': '0.0', 'FontUnknownControl': 7,
              'BeforeExecMacroLen': 0, 'GoToScreenID': 2, 'GoToScreenName': 'Second'}
    blob = b'[Element]\r\n' + b''.join(line(k, v) for k, v in values.items()) + wide('wDescTextLen0', name)
    if typ in (5, 6):
        return blob + state(0, '')
    return blob + state(0, caption) + state(1, caption + ' ON', 0x285544)


def xml():
    return b'''<?xml version="1.0" encoding="UTF-8"?>
<Symbolconfiguration xmlns="http://www.3s-software.com/schemas/Symbolconfiguration.xsd">
<TypeList><TypeSimple name="BoolType" size="1" typeclass="Bool" iecname="BOOL"/>
<TypeSimple name="RealType" size="8" typeclass="Real" iecname="LREAL"/>
<TypeUserDef name="MainType" size="32" nativesize="32" typeclass="Userdef" pouclass="STRUCTURE" iecname="MainType">
<UserDefElement iecname="Start" type="BoolType" byteoffset="0" access="ReadWrite"/>
<UserDefElement iecname="Start2" type="BoolType" byteoffset="1" access="ReadWrite"/>
<UserDefElement iecname="Trigger" type="BoolType" byteoffset="2" access="Read"/>
<UserDefElement iecname="Value" type="RealType" byteoffset="8" access="ReadWrite"/>
<UserDefElement iecname="Display" type="RealType" byteoffset="16" access="Read"/>
</TypeUserDef></TypeList><NodeList><Node name="Application"><Node name="Main" type="MainType" access="ReadWrite"/></Node></NodeList>
</Symbolconfiguration>'''


def payload():
    app = b'[Application]\r\n' + b''.join(line(k, v) for k, v in {
        'ApplicationVersion': '6.6.2.48', 'NewVersion': '6.6.2.48', 'PanelSeries': 'DOP-100 series',
        'PanelName': 'Synthetic panel', 'ModelName': 1, 'PanelResWidth': 400, 'PanelResHeight': 240,
        'DefaultScreen': 1, 'InitialMacroLen': 0, 'ClockMacroLen': 0}.items())
    opaque = b'\x10\x00\r\n[Screen]\r\nID=999\x00'
    app += b'MeMeCode=' + struct.pack('<I', len(opaque)) + opaque + b'\r\n'
    screen = b'[Screen]\r\n' + line('ID', 1) + wide('wTextLen', 'First') + line('PictureOffset', 0)
    screen += line('BgColor', 0x111111) + b'[AuxKeyElement]\r\n'
    screen += element(10, 'Start', x=10, y=10)
    screen += element(11, 'Start2', x=140, y=10, address='Main.Start2')
    screen += element(12, 'Input', 6, 1, x=10, y=80, address='Main.Value')
    screen += element(13, 'State', 2, 1, x=140, y=80, caption='OFF', address='Main.Trigger')
    second = b'[Screen]\r\n' + line('ID', 2) + wide('wTextLen', 'Second') + line('PictureOffset', 0) + line('BgColor', 0x111111) + b'[AuxKeyElement]\r\n'
    dib = flat_dib(400, 240, 0x111111)
    tail = b'[SubMacro]\r\nSubMacroProtect001=0\r\n[Background]\r\n' + line('Size', len(dib)) + dib
    tail += b'\r\n[DIATag]\r\nDIATagLinkName=Link1\r\nDIATagStationNr=0\r\nDiaTagXmlPath=neutral.xml\r\n' + line('size', len(xml())) + xml()
    tail += b'\r\n[END]\r\nOpaqueTailWithoutCRLF\x00\xff'
    return app + screen + second + tail


def wrap(body):
    pixels = b'\0' * 16
    thumb = bytearray(54)
    thumb[:2] = b'BM'
    struct.pack_into('<I', thumb, 2, 70)
    thumb[6:10] = b'PDAB'
    struct.pack_into('<I', thumb, 10, 54)
    struct.pack_into('<IiiHHIIiiII', thumb, 14, 40, 2, 2, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    prefix = b'P' * 37 + bytes(b ^ 100 for b in struct.pack('<I', len(body)))
    return bytes(thumb) + pixels + gzip.compress(bytes(b ^ 100 for b in prefix + body), mtime=0)


def native():
    return wrap(payload())


def profile():
    from universal_diascreen_hmi.native import Project, layout_digest
    return {'schema_version': 1, 'family': 'diascreen-dop100', 'panel': {'width': 400, 'height': 240},
            'reviewed_index_ack': True, 'indexed_layout_sha256': layout_digest(Project(native())),
            'application_versions': ['6.6.2.48'], 'link': 'Link1', 'station': 0,
            'preview_model': 'flat-v1', 'background_sha256': {'1': digest(flat_dib(400, 240, 0x111111)), '2': digest(flat_dib(400, 240, 0x111111))},
            'numeric_literal_digits': 15,
            'numeric_types': {'LREAL': {'bits': 64, 'floating': True, 'MemLen': 6, 'MemFmt': 5, 'evidence': 'synthetic contract'}},
            'button_types': {'momentary': {'Type': 1, 'SubType': 3, 'evidence': 'observed source-bound family'},
                             'maintained': {'Type': 1, 'SubType': 4, 'evidence': 'observed source-bound family'}}}
