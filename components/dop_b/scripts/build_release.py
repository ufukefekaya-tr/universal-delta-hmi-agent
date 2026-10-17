"""Build a bounded portable release, or install it using the published hash lock."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.1'
STAMP = (2026, 1, 1, 0, 0, 0)
SOURCE_DIRS = ('src', 'profiles', 'templates', 'scripts', 'docs', 'prompts', 'tools', 'tests', 'kaizen', 'reports/headless', 'reports/public_release', 'licenses')
SOURCE_FILES = ('AGENTS.md', 'SYSTEM_PROMPT.md', 'INDEX.md', 'README.md', 'pyproject.toml',
                'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'projects/README.md', 'MANIFEST.in', 'requirements.lock', '.gitignore', '.gitattributes', '.mcp.json.example')
SUFFIXES = {'.py', '.json', '.md', '.toml', '.sh', '.ps1', '.lock', '.txt', '.example'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_file(path, root):
    path, root = Path(path), Path(root).resolve()
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f'Unsafe or missing release file: {path}')
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise ValueError(f'Linked release input: {path}')
        current = current.parent
    return path


def sync_assets(root=ROOT):
    root = Path(root).resolve()
    target = root / 'src/universal_hmi/data'
    for parent in (target, *target.parents):
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Linked package asset destination')
    expected = {}
    for name in ('profiles', 'templates'):
        for path in sorted((root / name).rglob('*')):
            if path.is_dir():
                if path.is_symlink() or path.is_junction():
                    raise ValueError('Linked asset directory')
                continue
            safe_file(path, root)
            if path.suffix not in {'.json', '.md'}:
                raise ValueError(f'Unexpected asset extension: {path}')
            if path.suffix == '.json':
                json.loads(path.read_bytes())
            relative = path.relative_to(root)
            expected[relative.as_posix()] = sha(path)
            destination = target / relative
            for parent in (destination, *destination.parents):
                if parent == root:
                    break
                if parent.is_symlink() or parent.is_junction():
                    raise ValueError('Linked package asset destination')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    for path in target.rglob('*'):
        if path.is_file() and path.name != 'assets-manifest.json' and path.relative_to(target).as_posix() not in expected:
            raise ValueError(f'Stale package asset: {path}; remove deliberately before release')
    (target / 'assets-manifest.json').write_text(json.dumps(expected, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return expected


def source_files(root=ROOT):
    root = Path(root).resolve()
    result = [safe_file(root / name, root) for name in SOURCE_FILES]
    for directory in SOURCE_DIRS:
        for path in sorted((root / directory).rglob('*')):
            relative = path.relative_to(root)
            if relative.parts[0] == 'licenses' and len(relative.parts)>2 and relative.parts[1]!='texts':
                continue
            if any(part.startswith('.') or part.endswith('.egg-info') or part in {'__pycache__', 'vendor', 'private', 'node_modules'} for part in relative.parts):
                continue
            if path.is_file() and (path.suffix in SUFFIXES or relative.parts[0] == 'licenses'):
                result.append(safe_file(path, root))
    # Current public summaries are shipped; historical logs and private evidence
    # trees are deliberately outside the source bundle's documentation boundary.
    for path in sorted((root / 'reports').glob('*')):
        if path.is_file() and path.suffix in {'.md', '.json'}:
            result.append(safe_file(path, root))
    for path in sorted((root / 'examples').glob('*')):
        if path.is_file() and path.suffix in {'.md', '.json', '.html', '.png'}:
            result.append(safe_file(path, root))
    return sorted(set(result))


def source_bytes(path, root=ROOT):
    """Portable authored text matches Git LF checkout; licensed notice bytes stay exact."""
    relative = Path(path).relative_to(root).as_posix()
    raw = Path(path).read_bytes()
    if relative.startswith('licenses/texts/') or Path(path).suffix == '.png':
        return raw
    try:
        return raw.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
    except UnicodeDecodeError:
        return raw


def write_zip(path, members):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(members):
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            archive.writestr(info, raw)


def safe_extract_runtime(archive, destination):
    """Extract only bounded regular files/directories and internal relative links."""
    destination = Path(destination).resolve()
    with tarfile.open(archive, 'r:gz') as stream:
        members = stream.getmembers()
        if len(members) > 50000 or sum(x.size for x in members) > 2_000_000_000:
            raise ValueError('Runtime archive exceeds bounds')
        names = set()
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or '\\' in member.name or ':' in member.name
                    or not name.parts or name.parts[0] != 'python' or member.name in names):
                raise ValueError('Unsafe runtime archive path')
            names.add(member.name)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('Runtime archive contains special device')
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                base = destination / name.parent if member.issym() else destination
                if link.is_absolute() or '\\' in member.linkname or ':' in member.linkname or not (base / str(link)).resolve().is_relative_to(destination / 'python'):
                    raise ValueError('Runtime link escapes installation')
        stream.extractall(destination, filter='data')


def requirements_text(lock):
    return ''.join(item['requirement'] + ' ' + ' '.join('--hash=sha256:' + wheel['sha256'] for wheel in item['wheels']) + '\n'
                   for item in lock['dependencies'])


def check_wheelhouse(path, lock):
    allowed = {wheel['filename']: wheel['sha256'] for dep in lock['dependencies'] for wheel in dep['wheels']}
    for wheel in Path(path).iterdir():
        if wheel.name not in allowed or not wheel.is_file() or sha(wheel) != allowed[wheel.name]:
            raise ValueError(f'Unpinned wheelhouse artifact: {wheel.name}')


def build(output, wheelhouse=None, runtime_bundle=None):
    output = Path(output).resolve()
    if output == ROOT or not output.is_relative_to(ROOT / 'dist'):
        raise ValueError('Release output must be under this checkout dist directory')
    output.mkdir(parents=True, exist_ok=True)
    sync_assets()
    lock = json.loads((ROOT / 'scripts/bootstrap.lock.json').read_bytes())
    # Build a copied tree: setuptools never writes generated metadata into source.
    with tempfile.TemporaryDirectory(prefix='hmi-build-') as temporary:
        stage = Path(temporary) / 'source'
        for path in source_files():
            dest = stage / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        env = dict(os.environ, SOURCE_DATE_EPOCH='1767225600')
        subprocess.run([sys.executable, '-m', 'pip', '--isolated', 'wheel', '--no-deps', '--no-build-isolation',
                        '--no-index', '--wheel-dir', str(output), str(stage)], check=True, env=env)
    wheel_path = output / f'universal_hmi_agents-{VERSION}-py3-none-any.whl'
    with zipfile.ZipFile(wheel_path) as archive:
        members = [(name, archive.read(name)) for name in archive.namelist()]
    write_zip(wheel_path, members)
    members = [(path.relative_to(ROOT).as_posix(), source_bytes(path)) for path in source_files()]
    members.append(('wheels/' + wheel_path.name, wheel_path.read_bytes()))
    bundle_manifest = {'schema_version': 1, 'version': VERSION, 'files': {'wheels/' + wheel_path.name: sha(wheel_path)}}
    if wheelhouse:
        check_wheelhouse(wheelhouse, lock)
        for path in sorted(Path(wheelhouse).iterdir()):
            members.append(('wheelhouse/' + path.name, path.read_bytes()))
            bundle_manifest['files']['wheelhouse/' + path.name] = sha(path)
    if runtime_bundle:
        known = {entry['filename']: entry['sha256'] for entry in lock['runtimes'].values()}
        for path in sorted(Path(runtime_bundle).iterdir()):
            if path.name not in known or sha(path) != known[path.name]:
                raise ValueError('Runtime bundle has unpinned files')
            members.append(('runtime-bundle/' + path.name, path.read_bytes()))
            bundle_manifest['files']['runtime-bundle/' + path.name] = sha(path)
    members.append(('release-manifest.json', (json.dumps(bundle_manifest, sort_keys=True, indent=2) + '\n').encode()))
    source_zip = output / f'universal-hmi-agents-{VERSION}-source.zip'
    write_zip(source_zip, members)
    manifest = {'schema_version': 1, 'version': VERSION, 'artifacts': {path.name: sha(path) for path in (wheel_path, source_zip)},
                'assets': sync_assets(), 'offline_bundle_supplied': bool(wheelhouse and runtime_bundle),
                'acceptance': 'BUILD_ONLY_NOT_FRESH_HOST_ACCEPTANCE'}
    (output / 'release-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return manifest


def install(offline=False):
    if sys.version_info[:2] != (3, 14):
        raise ValueError('Pinned runtime requires Python 3.14')
    lock = json.loads((ROOT / 'scripts/bootstrap.lock.json').read_bytes())
    wheels = sorted((ROOT / 'wheels').glob(f'universal_hmi_agents-{VERSION}-*.whl'))
    if len(wheels) != 1:
        raise ValueError('Install requires the release ZIP with exactly one bundled application wheel')
    manifest = json.loads((ROOT / 'release-manifest.json').read_bytes())
    relative = wheels[0].relative_to(ROOT).as_posix()
    if manifest['files'].get(relative) != sha(wheels[0]):
        raise ValueError('Application wheel hash mismatch')
    target = ROOT / '.venv'
    python = target / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(target)], check=True)
    with tempfile.TemporaryDirectory(prefix='hmi-install-') as temporary:
        requirements = Path(temporary) / 'requirements.txt'
        requirements.write_text(requirements_text(lock), encoding='utf-8')
        args = [str(python), '-m', 'pip', '--isolated', 'install', '--require-hashes', '--only-binary=:all:', '-r', str(requirements)]
        if offline:
            check_wheelhouse(ROOT / 'wheelhouse', lock)
            args += ['--no-index', '--find-links', str(ROOT / 'wheelhouse')]
        else:
            args += ['--index-url', 'https://pypi.org/simple']
        subprocess.run(args, check=True)
    subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--force-reinstall', '--no-deps', '--no-index', str(wheels[0])], check=True)
    subprocess.run([str(python), '-m', 'universal_hmi.cli', 'doctor'], check=True, cwd=ROOT)
    print(json.dumps({'status': 'INSTALLED', 'python': str(python), 'offline': offline, 'acceptance': 'DOCTOR_ONLY'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / VERSION)
    parser.add_argument('--wheelhouse', type=Path)
    parser.add_argument('--runtime-bundle', type=Path)
    parser.add_argument('--sync-assets', action='store_true')
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    try:
        if args.install:
            install(args.offline)
        elif args.sync_assets:
            print(json.dumps(sync_assets(), sort_keys=True))
        else:
            print(json.dumps(build(args.output, args.wheelhouse, args.runtime_bundle), sort_keys=True))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'code': 'INSTALL_OR_BUILD_FAILED', 'detail': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
