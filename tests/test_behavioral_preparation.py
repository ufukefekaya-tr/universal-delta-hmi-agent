"""Neutral setup must not overwrite host configs or read ambient catalogs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BehavioralPreparationTests(unittest.TestCase):
    def run_prepare(self, root, **updates):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DIA_HMI_")}
        env.update(updates)
        return subprocess.run([sys.executable, "-I", "-B", str(ROOT / "tools/prepare_behavioral_cases.py"), str(root)], env=env, capture_output=True, text=True, timeout=30)

    def test_existing_config_refused_before_any_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".local").mkdir()
            target = root / ".local/eval-skill-missing.json"
            target.write_bytes(b"host-owned sentinel")
            result = self.run_prepare(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("EXISTING_EVALUATION_PRESERVED", result.stderr)
            self.assertEqual(target.read_bytes(), b"host-owned sentinel")
            self.assertFalse((root / ".local/eval").exists())

    def test_ambient_catalog_rejected_before_import_or_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for key in ("DIA_HMI_REFERENCE_ROOT", "DIA_HMI_TEMPLATE_ROOT", "DIA_HMI_FONT_ROOT"):
                result = self.run_prepare(root, **{key: str(root / "do-not-read")})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AMBIENT_CATALOG_OR_FONT_FORBIDDEN", result.stderr)
                self.assertEqual(list(root.iterdir()), [])

    def test_linked_local_directory_cannot_write_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            if os.name == "nt":
                shell = shutil.which("pwsh") or shutil.which("powershell")
                quote = lambda p: "'" + str(p).replace("'", "''") + "'"
                made = subprocess.run([shell, "-NoProfile", "-Command", "New-Item -ItemType Junction -Path " + quote(root / ".local") + " -Target " + quote(outside) + " | Out-Null"], capture_output=True, text=True)
                self.assertEqual(made.returncode, 0, made.stderr)
            else:
                (root / ".local").symlink_to(outside, target_is_directory=True)
            result = self.run_prepare(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Links/junctions", result.stderr)
            self.assertEqual(list(outside.iterdir()), [])
