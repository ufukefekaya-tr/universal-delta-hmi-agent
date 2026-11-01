"""A component guard must read its own committed controls in an umbrella tree."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

class VendoredGuardTests(unittest.TestCase):
    def test_control_epoch_uses_component_git_prefix(self):
        root=Path(__file__).resolve().parents[1]/'components/dop_100'
        spec=importlib.util.spec_from_file_location('vendored_dia_guard',root/'tools/session_guard.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        stream=b''.join(name.encode()+b'\0'+(root/name).read_bytes()+b'\0' for name in guard.CONTROL)
        self.assertEqual(guard.epoch(),hashlib.sha256(stream).hexdigest())

if __name__=='__main__':unittest.main()
