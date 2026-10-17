"""Recreate only original synthetic profiles, never vendor qualification."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = ['text', 'button', 'numeric_input', 'numeric_display', 'indicator', 'goto',
         'alarm_strip', 'alarm_table', 'alarm_history', 'alarms', 'macros',
         'macro_trigger:startup', 'macro_trigger:clock', 'macro_trigger:button',
         'macro_op:assign', 'macro_op:bit_on', 'macro_op:bit_off', 'macro_op:if']


def main():
    destination = ROOT / 'profiles'
    destination.mkdir(exist_ok=True)
    for family, identifier, resolution in [
            ('delta_dopsoft2', 'synthetic_dopsoft2', [800, 480]),
            ('delta_diascreen', 'synthetic_diascreen', [1024, 600])]:
        profile = {
            'id': identifier, 'family': family, 'model': 'ORIGINAL_SYNTHETIC_FIXTURE',
            'model_id': 'SYNTHETIC', 'editor_version': '0.0', 'resolution': resolution,
            'driver': 'SIMULATED_ONLY', 'fixture_kind': 'synthetic',
            'capabilities': {key: 'OFFLINE_PASS' for key in KINDS},
            'numeric_types': ['INT', 'UINT', 'DINT', 'UDINT', 'REAL', 'LREAL'],
            'limitation': 'Common IR tests only. Synthetic native schema supports observed toy fields. No vendor or panel acceptance.',
            'native_schema': {
                'qualified': True, 'cloning': True,
                'kinds': {'button': {'Type': '1'}},
                'binding_contract': {'data_type': 'BOOL', 'channel': 'SIM', 'station': '0', 'byte_order': 'little', 'word_order': 'little'},
                'state_fill': {'field': 'BgColor', 'encoding': 'rgb24'},
                'properties': {key.lower(): {'field': key, 'type': 'int', 'min': 0, 'max': resolution[0]}
                               for key in ('X', 'Y', 'Width', 'Height')} | {
                    'behavior': {'field': 'SubType', 'type': 'enum', 'values': {'momentary': 1, 'maintained': 2}},
                    'color': {'field': 'FontColor', 'scope': 'state', 'type': 'int', 'min': 0, 'max': 16777215}},
                'bindings': {direction: {'field': native + 'Var', 'link_field': native + 'Link', 'mem_type_field': native + 'MemType'}
                             for direction, native in [('read', 'Read'), ('write', 'Write')]}}
        }
        (destination / (identifier + '.json')).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline=chr(10))
    for identifier, family, model, model_id, resolution, editor in [
            ('dop_b07s411_dopsoft2', 'delta_dopsoft2', 'DOP-B07S411', '2953265424', [800, 480], 'DOPSoft 2.00.07'),
            ('dop_110is_diascreen', 'delta_diascreen', 'DOP-110IS', '268505092', [1024, 600], 'DIAScreen')]:
        profile = dict(id=identifier, family=family, model=model, model_id=model_id,
                       editor_version='UNVERIFIED', target_editor=editor, resolution=resolution,
                       driver='UNVERIFIED', fixture_kind='vendor', numeric_types=[],
                       capabilities={key: 'UNVERIFIED' for key in KINDS}, native_schema={'qualified': False},
                       limitation='Root-selected qualification target. Await fresh exact-model vendor fixtures, calibrated fields and human compile/emulator/panel evidence.')
        (destination / (identifier + '.json')).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline=chr(10))


if __name__ == '__main__':
    main()
