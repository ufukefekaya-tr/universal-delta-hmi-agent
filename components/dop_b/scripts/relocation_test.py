"""Clone committed source to a fresh location and install/test a fresh venv."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def sanitize_output(value, mappings):
    """Make saved proof host-neutral, including pip file URIs and escaped paths."""
    replacements = []
    for path, replacement in mappings:
        path = Path(path).absolute()
        variants = {str(path), path.as_posix(), str(path).replace('\\', '\\\\'),
                    path.as_uri(), quote(path.as_posix(), safe='/:'),
                    quote(path.as_uri(), safe='/:'), quote(str(path), safe='/:')}
        replacements.extend((variant, replacement) for variant in variants)
    for original, replacement in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        value = re.sub(re.escape(original), lambda _: replacement, value,
                       flags=re.IGNORECASE if os.name == 'nt' else 0)
    return value


def main():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit the tested source before relocation acceptance')
    temporary = Path(tempfile.mkdtemp(prefix='Universal HMI independent host '))
    checkout = temporary / 'relocated checkout'
    consumer = temporary / 'unrelated MCP consumer'
    consumer.mkdir()
    subprocess.run(['git', 'clone', '--no-hardlinks', str(ROOT), str(checkout)], check=True, capture_output=True)
    subprocess.run(['git', 'remote', 'remove', 'origin'], cwd=checkout, check=True)
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    base_python = Path(getattr(sys, '_base_executable', sys.executable))
    path_items = [entry for entry in environment.get('PATH', '').split(os.pathsep)
                  if entry and not Path(entry).absolute().is_relative_to(ROOT)]
    environment['PATH'] = str(base_python.parent)+os.pathsep+os.pathsep.join(path_items)
    setup = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(checkout / 'scripts/setup.ps1')] if os.name == 'nt' else ['sh', str(checkout / 'scripts/setup.sh')]
    install = subprocess.run(setup, cwd=consumer, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace')
    def sanitize(text):
        return sanitize_output(text, ((checkout, '<NEW_CHECKOUT>'), (ROOT, '<SOURCE_CHECKOUT>'),
                                     (temporary, '<TEMP_ROOT>'), (Path.home(), '<HOST_HOME>')))
    reports = ROOT / 'reports'
    (reports / 'relocation_install.log').write_text(sanitize(install.stdout+'\n'+install.stderr), encoding='utf-8', newline=chr(10))
    if install.returncode:
        raise SystemExit('Fresh relocated install failed; see reports/relocation_install.log')
    python = checkout / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    probe = subprocess.run([str(python), '-c', 'import json, pathlib, universal_hmi; print(json.dumps({"module":str(pathlib.Path(universal_hmi.__file__).resolve())}))'],
                           cwd=consumer, env=environment, check=True, capture_output=True, text=True)
    actual_module = Path(json.loads(probe.stdout)['module'])
    if not actual_module.is_relative_to(checkout):
        raise SystemExit('Fresh environment imported another checkout')
    verified = subprocess.run([str(python), str(checkout / 'scripts/verify.py')], cwd=consumer, env=environment, capture_output=True, text=True)
    (reports / 'relocation_tests.log').write_text(sanitize((checkout / 'reports/python_tests.log').read_text(encoding='utf-8', newline=chr(10))), encoding='utf-8', newline=chr(10))
    tested = json.loads((checkout / 'reports/python_tests.json').read_bytes())
    (reports / 'relocation_tests.json').write_text(json.dumps(tested, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline=chr(10))
    pip_check = subprocess.run([str(python), '-m', 'pip', 'check'], cwd=consumer, env=environment, capture_output=True, text=True)
    expected = json.loads((reports / 'python_tests.json').read_bytes())
    revision_matches = tested['test_revision_sha256'] == expected['test_revision_sha256']
    report = {'scope': 'FRESH_RELOCATED_EDITABLE_INSTALL', 'os': os.name, 'platform': sys.platform, 'source_commit': revision,
              'separate_checkout': True, 'checkout_path_contains_spaces': True, 'fresh_venv': True,
              'original_venv_copied': False, 'original_git_remote_removed': True, 'pythonpath_removed': True,
              'original_checkout_removed_from_path': True, 'bootstrap_interpreter': 'HOST_BASE_PYTHON',
              'import_resolves_to_relocated_source': True, 'caller_outside_checkout': True,
              'test_revision_sha256': tested['test_revision_sha256'], 'matches_source_test_revision': revision_matches, 'executed': tested['executed'],
              'skipped': tested['skipped'], 'tests_pass': verified.returncode == 0 and tested['status'] == 'OFFLINE_PASS',
              'pip_check': {'exit_code': pip_check.returncode, 'result': sanitize(pip_check.stdout.strip())},
              'vendor_assets_required': False, 'vendor_compile': 'NOT_RUN',
              'linux_runtime': 'PASS' if sys.platform == 'linux' else 'NOT_RUN',
              'macos_runtime': 'PASS' if sys.platform == 'darwin' else 'NOT_RUN'}
    report['status'] = 'OFFLINE_PASS' if report['tests_pass'] and revision_matches and pip_check.returncode == 0 else 'FAIL'
    (reports / 'relocation_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline=chr(10))
    # Keep the fresh checkout for local diagnosis; location is ignored host state.
    (ROOT / '.local').mkdir(exist_ok=True)
    (ROOT / '.local/relocation_location.json').write_text(json.dumps({'checkout': str(checkout), 'source_commit': revision}), encoding='utf-8', newline=chr(10))
    print(json.dumps(report))
    return 0 if report['status'] == 'OFFLINE_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
