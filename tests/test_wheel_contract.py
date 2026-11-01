"""Forged metadata must fail even with exact members and a fresh valid RECORD."""
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wheel_contract_test',ROOT/'tools/wheel_contract.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class WheelContractTests(unittest.TestCase):
    def fixture(self):
        source={'pyproject.toml':b'''[project]
name="universal-delta-hmi-agent"
version="0.4.0"
description="Neutral wheel test"
requires-python=">=3.14"
license="Apache-2.0"
license-files=["LICENSE"]
readme="README.md"
dependencies=["mcp==2.3.0"]
[project.scripts]
delta-hmi="delta_hmi.cli:main"
''','src/delta_hmi/__init__.py':b'# Original neutral test code\n','LICENSE':b'Neutral license fixture','README.md':b'Original neutral readme\n'}
        meta='universal_delta_hmi_agent-0.4.0.dist-info'
        headers=b'Metadata-Version: 2.4\nName: universal-delta-hmi-agent\nVersion: 0.4.0\nSummary: Neutral wheel test\nLicense-Expression: Apache-2.0\nRequires-Python: >=3.14\nDescription-Content-Type: text/markdown\nLicense-File: LICENSE\nRequires-Dist: mcp==2.3.0\nDynamic: license-file\n\n'
        entries={'delta_hmi/__init__.py':source['src/delta_hmi/__init__.py'],meta+'/licenses/LICENSE':source['LICENSE'],meta+'/METADATA':headers+source['README.md'],meta+'/WHEEL':b'Wheel-Version: 1.0\nGenerator: setuptools (84.0.0)\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n',meta+'/entry_points.txt':b'[console_scripts]\ndelta-hmi = delta_hmi.cli:main\n',meta+'/top_level.txt':b'delta_hmi\n'}
        return source,meta,entries

    def write(self,path,meta,entries):
        data=dict(entries);stream=io.StringIO();writer=csv.writer(stream,lineterminator='\n')
        for key,raw in data.items():writer.writerow([key,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='),len(raw)])
        writer.writerow([meta+'/RECORD','','']);data[meta+'/RECORD']=stream.getvalue().encode()
        with zipfile.ZipFile(path,'w') as z:
            for key,raw in data.items():z.writestr(key,raw)

    def test_metadata_dependency_body_identity_and_extra_member_attacks(self):
        source,meta,entries=self.fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(mod.contract,'source_entries',return_value=source):
            q=Path(tmp)/'neutral.whl';self.write(q,meta,entries);self.assertEqual(mod.audit(q,'gateway')['status'],'PASS')
            for old,new in [(b'>=3.14',b'>=99'),(b'mcp==2.3.0',b'unreviewed-sentinel==99'),(b'Name: universal-',b'Name: forged\nName: universal-'),(b'Original neutral readme',b'UNREVIEWED PRIVATE BODY'),(b'Summary: Neutral wheel test',b'Summary: Unreviewed text')]:
                changed=dict(entries);changed[meta+'/METADATA']=changed[meta+'/METADATA'].replace(old,new);self.write(q,meta,changed)
                with self.assertRaises(ValueError):mod.audit(q,'gateway')
            changed={**entries,'delta_hmi/private.py':b'unreviewed'};self.write(q,meta,changed)
            with self.assertRaisesRegex(ValueError,'membership'):mod.audit(q,'gateway')
            for member in ('WHEEL','entry_points.txt','top_level.txt'):
                changed=dict(entries);changed[meta+'/'+member]+=b'UNREVIEWED PAYLOAD\n';self.write(q,meta,changed)
                with self.assertRaises(ValueError):mod.audit(q,'gateway')
