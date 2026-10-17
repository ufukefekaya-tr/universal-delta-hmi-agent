"""Regression for Windows short/long TEMP names in clean hosted CI."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('repo_ci',ROOT/'tools/ci.py')
ci=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CiEnvironmentTests(unittest.TestCase):
    def test_canonical_temp_environment_reaches_child_without_parent_env_mutation(self):
        original=dict(os.environ)
        previous=tempfile.tempdir
        try:
            env=ci.test_environment()
            result=subprocess.check_output([sys.executable,'-I','-B','-c',
                'import json,tempfile;print(json.dumps(tempfile.gettempdir()))'],env=env,text=True)
            self.assertEqual(Path(json.loads(result)).resolve(),Path(tempfile.gettempdir()).resolve())
            if os.name=='nt':
                for key in ('TMPDIR','TEMP','TMP'):
                    self.assertEqual(env[key],str(Path(env[key]).resolve(strict=True)))
            self.assertEqual(dict(os.environ),original)
        finally:
            tempfile.tempdir=previous

    def test_windows_alias_is_resolved_before_all_three_child_variables_are_set(self):
        previous=tempfile.tempdir
        canonical=Path(tempfile.gettempdir()).resolve(strict=True)
        try:
            with patch.object(ci.os,'name','nt'),patch.object(ci.tempfile,'gettempdir',return_value='SHORT~1'),patch.object(ci,'Path') as factory:
                factory.return_value.resolve.return_value=canonical
                env=ci.test_environment()
                factory.assert_called_once_with('SHORT~1')
                factory.return_value.resolve.assert_called_once_with(strict=True)
            for key in ('TMPDIR','TEMP','TMP'):
                self.assertEqual(env[key],str(canonical))
            self.assertEqual(tempfile.tempdir,str(canonical))
        finally:
            tempfile.tempdir=previous
