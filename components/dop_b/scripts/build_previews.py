"""Neutral conceptual samples; do not turn these into production approvals."""
import json
from pathlib import Path
from universal_hmi.preview import render_preview

ROOT = Path(__file__).resolve().parents[1]


def main():
    for size in ('800x480', '1024x600'):
        design = json.loads((ROOT / 'examples' / ('neutral_' + size + '.json')).read_bytes())
        profile = json.loads((ROOT / 'profiles' / (design['profile_id'] + '.json')).read_bytes())
        for name, active, speed in [('0', 0, 0), ('1', 1, 125.5), ('stale', 1, 125.5), ('long', 1, 99999999.9)]:
            values = dict(run_request=active, stop_request=0, run_feedback=active,
                          actual_speed=speed, speed_setpoint=150, alarm_active=active)
            sample_design = json.loads(json.dumps(design))
            if name == 'long':
                sample_design['alarms'][0]['text'] = 'Sample alarm with a deliberately long explanation: inspect the external sensor, acknowledge the cause and restore operation only after the condition has cleared.'
            states = {tag: 'stale' for tag in values} if name == 'stale' else {}
            html = render_preview(sample_design, profile, values=values, states=states)
            (ROOT / 'reports' / ('preview_' + size + '_' + name + '.html')).write_text(html, encoding='utf-8', newline=chr(10))


if __name__ == '__main__':
    main()
