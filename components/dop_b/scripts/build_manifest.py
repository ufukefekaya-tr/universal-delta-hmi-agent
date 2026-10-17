"""Freeze distributable files, excluding this self-referential manifest."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    entries = {}
    for name in sorted(set(names)):
        if not name or name == 'reports/manifest.json':
            continue
        path = ROOT / name
        if not path.is_file():
            raise SystemExit('Manifest cannot include a missing file: '+name)
        raw = path.read_bytes()
        entries[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    artifact_revision = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = {'framework_version': '0.1.0', 'scope': 'FRAMEWORK_SNAPSHOT_WITH_OPEN_NATIVE_GOALS',
                'excluded': {'reports/manifest.json': 'Self reference; hash via Git after commit'},
                'artifact_revision_sha256': artifact_revision, 'files': entries}
    (ROOT / 'reports/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline=chr(10))
    print(json.dumps({'files': len(entries), 'artifact_revision_sha256': artifact_revision}))


if __name__ == '__main__':
    main()
