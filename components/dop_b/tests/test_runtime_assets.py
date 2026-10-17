import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from universal_hmi.runtime_assets import profiles_root, templates_root


class RuntimeAssetsTests(unittest.TestCase):
    def test_canonical_assets_match_every_packaged_byte(self):
        root = Path(__file__).resolve().parents[1]
        data = profiles_root().parent
        manifest = json.loads((data / 'assets-manifest.json').read_bytes())
        expected = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for name in ('profiles', 'templates') for p in (root / name).rglob('*') if p.is_file()}
        self.assertEqual(manifest, expected)
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((data / name).read_bytes()).hexdigest(), digest)
        self.assertTrue((templates_root() / 'TARGET_PROFILE.json').is_file())

    def test_source_checkout_absent_unrelated_cwd_read_only_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'installed/universal_hmi'
            shutil.copytree(profiles_root().parent.parent, package, ignore=shutil.ignore_patterns('__pycache__'))
            for path in (package / 'data').rglob('*'):
                if path.is_file():
                    path.chmod(0o444)
            cwd = root / 'unrelated'
            cwd.mkdir()
            program = ("import sys; sys.path.insert(0, " + repr(str(package.parent)) + "); "
                       "from universal_hmi.runtime_assets import profiles_root,templates_root; "
                       "assert profiles_root().joinpath('dop_b10s615_dopsoft2.json').is_file(); "
                       "assert profiles_root().joinpath('driver_contracts/delta_dvp_serial_2016.json').is_file(); "
                       "assert templates_root().joinpath('TARGET_PROFILE.json').is_file()")
            try:
                subprocess.run([sys.executable, '-I', '-c', program], cwd=cwd, check=True, capture_output=True)
            finally:
                for path in (package / 'data').rglob('*'):
                    if path.is_file():
                        path.chmod(0o666)


if __name__ == '__main__':
    unittest.main()
