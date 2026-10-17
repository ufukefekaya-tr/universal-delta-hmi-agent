"""Run nonempty, unique tests and persist evidence; no vendor programs invoked."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def main():
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    identifiers = list(test_ids(suite))
    if not identifiers or len(identifiers) != len(set(identifiers)):
        raise SystemExit('Empty or duplicate test set cannot pass')
    hashes = {}
    for folder in ('src', 'tests', 'profiles', 'tools', 'scripts'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and not any(p.endswith('.egg-info') for p in path.parts):
                hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    start = time.monotonic()
    with (reports / 'python_tests.log').open('w', encoding='utf-8', newline=chr(10)) as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    checks = {}
    for name, args in [('repo', [str(ROOT / 'tools/check_repo.py'), '--json']),
                       ('doctor', ['-m', 'universal_hmi.cli', '--profiles', str(ROOT / 'profiles'), 'doctor'])]:
        process = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        checks[name] = {'exit_code': process.returncode,
                       'stdout': process.stdout.strip().replace(str(ROOT).replace('\\', '\\\\'), '<REPO>').replace(str(ROOT), '<REPO>'),
                       'stderr': process.stderr.strip().replace(str(ROOT), '<REPO>')}
    config = tomllib.loads((ROOT / 'scripts/codex_config.toml.example').read_text(encoding='utf-8', newline=chr(10)))
    server = config['mcp_servers']['universal_hmi']
    checks['codex_example'] = {'toml_valid': True, 'tool_count': len(server['enabled_tools']), 'registered_in_codex': False}
    passed = result.wasSuccessful() and not result.skipped and result.testsRun == len(identifiers) and all(
        check['exit_code'] == 0 for name, check in checks.items() if name != 'codex_example')
    report = {'scope': 'OFFLINE_FRAMEWORK_ONLY', 'status': 'OFFLINE_PASS' if passed else 'FAIL',
              'python': sys.version.split()[0], 'test_revision_sha256': revision,
              'source_hashes': hashes, 'discovered': len(identifiers), 'executed': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'elapsed_seconds': round(time.monotonic()-start, 3), 'test_ids': identifiers, 'checks': checks,
              'vendor_compile': 'NOT_RUN', 'physical_test': 'NOT_RUN'}
    (reports / 'python_tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline=chr(10))
    print(json.dumps({key: report[key] for key in ('status', 'executed', 'failures', 'errors', 'skipped', 'test_revision_sha256')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
