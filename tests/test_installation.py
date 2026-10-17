"""Reject linked installation roots before downloads or runtime writes."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

def junction(shell, path, target):
    quote=lambda value: "'"+str(value).replace("'","''")+"'"
    return subprocess.run([shell,'-NoProfile','-Command',"New-Item -ItemType Junction -Path "+quote(path)+" -Target "+quote(target)+" | Out-Null"],capture_output=True,text=True)


class InstallationTests(unittest.TestCase):
    def test_materialization_refuses_external_runtime_link(self):
        spec=importlib.util.spec_from_file_location('install',ROOT/'scripts/finish_install.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);runtime=base/'runtime';runtime.mkdir();outside=base/'outside';outside.mkdir();(outside/'sentinel').write_text('preserve')
            if os.name=='nt':
                shell=shutil.which('pwsh') or shutil.which('powershell')
                result=junction(shell,runtime/'escape',outside)
                self.assertEqual(result.returncode,0,result.stderr)
            else:(runtime/'escape').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):mod.materialize_internal_links(runtime)
            self.assertEqual((outside/'sentinel').read_text(),'preserve')

    def test_download_cache_link_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);repo=base/'repo';(repo/'scripts').mkdir(parents=True);(repo/'.local').mkdir()
            outside=base/'outside';outside.mkdir();(outside/'sentinel').write_text('unchanged')
            if os.name=='nt':
                shell=shutil.which('pwsh') or shutil.which('powershell')
                if shell is None:self.skipTest('PowerShell unavailable')
                # Test only a new junction in the private temporary directory.
                result=junction(shell,repo/'.local/downloads',outside)
                if result.returncode:self.fail(result.stderr)
                shutil.copy2(ROOT/'scripts/bootstrap.ps1',repo/'scripts/bootstrap.ps1')
                command=[shell,'-NoProfile','-File',str(repo/'scripts/bootstrap.ps1')]
            else:
                (repo/'.local/downloads').symlink_to(outside,target_is_directory=True)
                shutil.copy2(ROOT/'scripts/bootstrap.sh',repo/'scripts/bootstrap.sh')
                command=['sh',str(repo/'scripts/bootstrap.sh')]
            run=subprocess.run(command,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('LINKED_INSTALL_PATH',run.stdout+run.stderr)
            self.assertEqual([p.name for p in outside.iterdir()],['sentinel'])
            self.assertEqual((outside/'sentinel').read_text(),'unchanged')


class PackagePrivacyTests(unittest.TestCase):
    def test_generated_component_metadata_never_enters_source_release(self):
        import uuid, zipfile
        spec=importlib.util.spec_from_file_location('packager',ROOT/'scripts/build_package.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        marker=ROOT/'components'/('private-'+uuid.uuid4().hex+'.egg-info')
        marker.mkdir();(marker/'PKG-INFO').write_text('PRIVATE BUILD METADATA SENTINEL')
        output=ROOT/'dist'/('privacy-'+uuid.uuid4().hex+'.zip')
        try:
            mod.build(output)
            with zipfile.ZipFile(output) as archive:
                self.assertFalse(any('.egg-info/' in name for name in archive.namelist()))
                self.assertIn('LICENSE',archive.namelist())
                self.assertIn('components/dop_b/LICENSE',archive.namelist())
                self.assertIn('components/dop_100/LICENSE',archive.namelist())
        finally:
            (marker/'PKG-INFO').unlink();marker.rmdir()
            if output.exists():output.unlink()
