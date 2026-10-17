import importlib.util
import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_builder', ROOT / 'scripts/build_release.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleasePackageTests(unittest.TestCase):
    def test_source_allowlist_excludes_private_runtime_vendor_and_git(self):
        files = [p.relative_to(ROOT).as_posix() for p in builder.source_files()]
        for prefix in ('.git/', '.agent-state/', '.venv/', '.local/', 'dist/', 'vendor/'):
            self.assertFalse(any(p.startswith(prefix) for p in files), prefix)
        self.assertFalse(any('.egg-info/' in p for p in files))
        self.assertIn('scripts/bootstrap.lock.json', files)
        self.assertEqual([p for p in files if p.startswith('projects/')], ['projects/README.md'])
        self.assertIn('src/universal_hmi/data/assets-manifest.json', files)
        self.assertIn('reports/headless/STATUS.json', files)
        self.assertIn('reports/VERIFICATION.md', files)
        self.assertIn('reports/FINAL_REVIEW.md', files)
        self.assertIn('examples/neutral_800x480.json', files)
        self.assertFalse(any(p.startswith('reports/history/') for p in files))

    def test_public_license_and_notice_inventory_are_complete(self):
        import hashlib
        files={p.relative_to(ROOT).as_posix() for p in builder.source_files()}
        for required in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','licenses/inventory.json'):
            self.assertIn(required,files)
        metadata=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']
        self.assertEqual(metadata['license'],'Apache-2.0')
        self.assertEqual(metadata['version'],builder.VERSION)
        self.assertNotIn(b'\r\n',builder.source_bytes(ROOT/'scripts/build_release.py'))
        notice_file=next((ROOT/'licenses/texts').glob('*.txt'))
        self.assertEqual(builder.source_bytes(notice_file),notice_file.read_bytes())
        inventory=json.loads((ROOT/'licenses/inventory.json').read_bytes())
        self.assertEqual(len(inventory['wheels']),34)
        self.assertEqual(len(inventory['runtimes']),2)
        for group in ('wheels','runtimes'):
            for item in inventory[group]:
                self.assertTrue(item['notices'])
                for notice in item['notices']:
                    self.assertIn(notice['path'],files)
                    raw=(ROOT/notice['path']).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),notice['sha256'])
                for component in item.get('linked_library_licenses',[]):
                    for path in component.get('license_paths',[]):
                        self.assertIn('python/'+path,{n['source_member'] for n in item['notices']})

    def test_bad_archive_paths_links_devices_and_oversize_are_rejected(self):
        for name, kind, link, size in [('../outside', tarfile.REGTYPE, '', 0),
                                       ('/outside', tarfile.REGTYPE, '', 0),
                                       ('python/C:drive', tarfile.REGTYPE, '', 0),
                                       ('python/link', tarfile.SYMTYPE, '../../outside', 0),
                                       ('python/device', tarfile.CHRTYPE, '', 0),
                                       ('python/huge', tarfile.REGTYPE, '', 2_000_000_001)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / 'runtime.tar.gz'
                member = tarfile.TarInfo(name)
                member.type, member.linkname, member.size = kind, link, size
                if size:
                    with gzip.open(archive, 'wb') as stream:
                        stream.write(member.tobuf() + b'\0' * 1024)
                else:
                    with tarfile.open(archive, 'w:gz') as stream:
                        stream.addfile(member)
                with self.assertRaises((ValueError, tarfile.TarError)):
                    builder.safe_extract_runtime(archive, Path(temporary) / 'install')

    def test_valid_regular_runtime_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'runtime.tar.gz'
            with tarfile.open(archive, 'w:gz') as stream:
                member = tarfile.TarInfo('python/bin/python3')
                member.size = 4
                stream.addfile(member, io.BytesIO(b'test'))
            builder.safe_extract_runtime(archive, Path(temporary) / 'install')
            self.assertEqual((Path(temporary) / 'install/python/bin/python3').read_bytes(), b'test')

    def test_offline_wheelhouse_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'fake.whl').write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                builder.check_wheelhouse(temporary, {'dependencies': []})

    def test_all_lock_pins_have_hashes_and_only_official_sources(self):
        lock = json.loads((ROOT / 'scripts/bootstrap.lock.json').read_bytes())
        self.assertEqual([d['requirement'] for d in lock['dependencies']], (ROOT / 'requirements.lock').read_text().splitlines())
        for dependency in lock['dependencies']:
            self.assertTrue(dependency['wheels'])
            for wheel in dependency['wheels']:
                self.assertRegex(wheel['sha256'], '^[a-f0-9]{64}$')
                self.assertTrue(wheel['url'].startswith('https://files.pythonhosted.org/'))
        linux = lock['runtimes']['linux_x86_64']
        script = (ROOT / 'scripts/bootstrap.sh').read_text()
        for key in ('url', 'filename', 'sha256'):
            self.assertIn(linux[key], script)

    def test_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            a, b = Path(temporary) / 'a.zip', Path(temporary) / 'b.zip'
            builder.write_zip(a, [('z', b'one'), ('a', b'two')])
            builder.write_zip(b, [('a', b'two'), ('z', b'one')])
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_generated_mcp_config_requires_paired_job_paths(self):
        script = str(ROOT / 'scripts/configure_mcp.py')
        base = subprocess.run([sys.executable, script], capture_output=True, text=True, check=True)
        self.assertEqual(len(tomllib.loads(base.stdout)['mcp_servers']['universal_hmi']['enabled_tools']), 9)
        jobs = subprocess.run([sys.executable, script, '--job-policy', 'policy.json', '--job-state', 'state', '--profiles', 'registry'], capture_output=True, text=True, check=True)
        result = tomllib.loads(jobs.stdout)['mcp_servers']['universal_hmi']
        self.assertEqual(result['enabled_tools'][-5:], ['preflight_job', 'submit_job', 'job_status', 'job_result', 'cancel_job'])
        self.assertIn('--job-policy', result['args'])
        self.assertIn('--profiles', result['args'])
        unpaired = subprocess.run([sys.executable, script, '--job-policy', 'policy.json'], capture_output=True, text=True)
        self.assertNotEqual(unpaired.returncode, 0)


if __name__ == '__main__':
    unittest.main()
