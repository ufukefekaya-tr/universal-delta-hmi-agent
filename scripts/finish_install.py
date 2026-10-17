"""Install isolated family environments from the trusted release contents."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def executable(root):
    return root / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')


def run(*args):
    subprocess.run([str(a) for a in args], check=True, env={k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONPATH','PYTHONHOME'}})


def materialize_internal_links(root):
    """Expand only internal links in a freshly verified installation before pinning."""
    root = root.resolve(strict=True)
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if hasattr(path, 'is_junction') and path.is_junction():
                raise ValueError('Runtime junction is forbidden')
            if not path.is_symlink():
                continue
            target = path.resolve(strict=True)
            if not target.is_relative_to(root) or path.is_relative_to(target):
                raise ValueError('Runtime link escapes installation or creates a cycle')
            path.unlink()
            if target.is_dir():
                shutil.copytree(target, path, symlinks=False)
            else:
                shutil.copy2(target, path)


def main():
    base = ROOT / '.local'
    backends = {name: base / 'backends' / name for name in ('dop_b', 'dop_100')}
    config_file = base / 'gateway.json'
    if config_file.exists() or backends['dop_100'].exists():
        raise ValueError('Existing installation is preserved; use a fresh directory')
    dop_b = backends['dop_b']
    python = executable(dop_b)
    materialize_internal_links(dop_b)
    run(python, '-I', '-B', '-m', 'venv', '--copies', ROOT / '.venv')
    gateway_python = executable(ROOT)
    lock = json.loads((dop_b / 'scripts/bootstrap.lock.json').read_text('utf8'))
    requirements = base / 'pins/gateway-requirements.lock'
    requirements.parent.mkdir(parents=True, exist_ok=True)
    requirements.write_text('\n'.join(d['requirement'] + ' ' + ' '.join(
        '--hash=sha256:' + w['sha256'] for w in d['wheels']) for d in lock['dependencies']) + '\n', encoding='utf8')
    run(gateway_python, '-I', '-B', '-m', 'pip', 'install', '--no-index', '--require-hashes',
        '--find-links', dop_b / 'wheelhouse', '-r', requirements)
    run(gateway_python, '-I', '-B', '-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '--no-index', ROOT)

    # Each family receives its own interpreter, stdlib and site-packages.
    dia = backends['dop_100']
    shutil.copytree(dop_b / '.runtime/python', dia / '.runtime/python')
    dia_runtime = dia / ('.runtime/python/python.exe' if os.name == 'nt' else '.runtime/python/bin/python3')
    run(dia_runtime, '-I', '-B', '-m', 'venv', '--copies', dia / '.venv')
    dia_python = executable(dia)
    run(dia_python, '-I', '-B', '-m', 'pip', 'install', '--no-index', '--find-links', dop_b / 'wheelhouse', 'setuptools==84.0.0')
    with tempfile.TemporaryDirectory(prefix='dia-build-', dir=base) as scratch:
        staged = Path(scratch) / 'source'
        shutil.copytree(ROOT / 'components/dop_100', staged, ignore=shutil.ignore_patterns('*.egg-info','build','dist','__pycache__'))
        run(dia_python, '-I', '-B', '-m', 'pip', 'install', '--no-deps', '--no-build-isolation', '--no-index', staged)
    materialize_internal_links(dia)
    sys.path.insert(0, str(ROOT / 'src'))
    from delta_hmi.config import tree_files, tree_sha256, GatewayConfig
    value = {'schema_version': 1, 'backends': {}}
    rel = lambda path: path.relative_to(base).as_posix()
    for name, backend in backends.items():
        interpreter = executable(backend)
        module = 'universal_hmi' if name == 'dop_b' else 'universal_diascreen_hmi'
        package = Path(subprocess.check_output([str(interpreter), '-I', '-B', '-c',
            f'import {module},pathlib; print(pathlib.Path({module}.__file__).parent)'], text=True).strip())
        if not package.resolve().is_relative_to(backend.resolve()):
            raise ValueError('Backend package escaped its installation')
        roots = {key: base / 'families' / name / key for key in ('workspace', 'profiles', 'state')}
        for path in roots.values():
            path.mkdir(parents=True, exist_ok=False)
        if name == 'dop_b':
            for item in (package / 'data/profiles').iterdir():
                if item.is_dir():
                    shutil.copytree(item, roots['profiles'] / item.name)
                elif item.suffix == '.json' and json.loads(item.read_text('utf8')).get('family') == 'delta_dopsoft2':
                    shutil.copy2(item, roots['profiles'] / item.name)
        else:
            # Synthetic framing example, never a vendor-qualified panel application.
            demo = roots['workspace'] / 'neutral-demo'
            run(dia_python, '-I', '-B', ROOT / 'examples/create_gateway_demo.py', demo)
            shutil.copy2(demo / 'profile.json', roots['profiles'] / 'synthetic_diascreen.json')
        manifest = base / 'pins' / (name + '.json')
        imports = ['.venv', '.runtime/python']
        manifest.write_text(json.dumps({'package_prefix': package.relative_to(backend).as_posix(),
            'import_roots': imports, 'files': [{'path': folder + '/' + path, 'sha256': sha}
            for folder in imports for path, sha in tree_files(backend / folder).items()]}, indent=2) + '\n', encoding='utf8')
        entry = {'enabled': True, 'root': rel(backend), 'python': rel(interpreter),
            'python_sha256': digest(interpreter), 'source_manifest': rel(manifest),
            'source_manifest_sha256': digest(manifest), 'profiles_sha256': tree_sha256(roots['profiles']),
            **{key: rel(path) for key, path in roots.items()}}
        if name == 'dop_100':
            entry['allow_write'] = True  # Exact-plan consent still required on apply.
        value['backends'][name] = entry
    config_file.write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')
    config = GatewayConfig.load(config_file)
    for backend in config.backends.values():
        backend.verify()
    print(json.dumps({'status': 'BOTH_FILE_BACKENDS_INSTALLED', 'configuration': str(config_file),
        'python': str(gateway_python), 'vendor': 'NOT_RUN', 'physical': 'NOT_RUN'}))


if __name__ == '__main__':
    main()
