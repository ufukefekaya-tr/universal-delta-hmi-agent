import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from universal_hmi.reference_pack import create_pack, import_pack
from universal_hmi.job_policy import digest
from universal_hmi.errors import HmiError


class ReferencePackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'blank.dps').write_bytes(b'ORIGINAL TEST ONLY')

    def test_private_transfer_exact_bytes_and_hash(self):
        archive=self.root/'private.zip'
        report=create_pack(self.root,['blank.dps'],archive,provenance='Test original bytes, transfer authorized')
        result=import_pack(archive,report['sha256'],self.root/'new')
        self.assertEqual((Path(result['path'])/'blank.dps').read_bytes(),b'ORIGINAL TEST ONLY')
        with self.assertRaises(HmiError):import_pack(archive,report['sha256'],self.root/'new')

    def test_tampered_archive_rejected_before_extraction(self):
        archive=self.root/'private.zip';r=create_pack(self.root,['blank.dps'],archive,provenance='test')
        with archive.open('ab') as f:f.write(b'changed')
        with self.assertRaises(HmiError):import_pack(archive,r['sha256'],self.root/'new')
        self.assertFalse((self.root/'new').exists())

    def test_malicious_zip_paths_duplicates_and_links(self):
        for i,name in enumerate(('../escape','C:/escape','a\\b','NUL.txt','/escape')):
            archive=self.root/f'bad{i}.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr(name,b'x');z.writestr('reference-manifest.json',b'{}')
            with self.assertRaises(HmiError):import_pack(archive,digest(archive.read_bytes()),self.root/f'new{i}')
        archive=self.root/'link.zip'
        with zipfile.ZipFile(archive,'w') as z:
            entry=zipfile.ZipInfo('link');entry.create_system=3;entry.external_attr=0o120777<<16
            z.writestr(entry,b'outside');z.writestr('reference-manifest.json',b'{}')
        with self.assertRaises(HmiError):import_pack(archive,digest(archive.read_bytes()),self.root/'newlink')

    def test_case_collisions_and_missing_provenance_rejected(self):
        for files,provenance in [(['blank.dps','BLANK.DPS'],'test'),(['blank.dps'],'')]:
            with self.assertRaises(HmiError):create_pack(self.root,files,self.root/'bad.zip',provenance=provenance)

    def test_missing_source_is_structured_error_on_every_platform(self):
        from universal_hmi.job_policy import relative_file
        with self.assertRaises(HmiError):relative_file(self.root,'missing.dps',exists=True)
        with self.assertRaises(HmiError):create_pack(self.root,['missing.dps'],self.root/'bad.zip',provenance='TEST ONLY')

    def test_verified_snapshot_survives_archive_path_replacement(self):
        archive=self.root/'private.zip'
        report=create_pack(self.root,['blank.dps'],archive,provenance='TEST ONLY')
        real_zip=zipfile.ZipFile
        def replace_path_then_open(*args,**kwargs):
            archive.write_bytes(b'REPLACED AFTER HASH')
            return real_zip(*args,**kwargs)
        with patch('universal_hmi.reference_pack.zipfile.ZipFile',replace_path_then_open):
            result=import_pack(archive,report['sha256'],self.root/'new')
        self.assertEqual((Path(result['path'])/'blank.dps').read_bytes(),b'ORIGINAL TEST ONLY')

    def test_reserved_manifest_directory_rejected(self):
        archive=self.root/'bad.zip';name='reference-manifest.json/child';raw=b'test'
        manifest=dict(schema_version=1,kind='PRIVATE_REFERENCE_PACK',provenance='TEST ONLY',
                      files={name:{'sha256':digest(raw),'bytes':len(raw)}})
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('reference-manifest.json',json.dumps(manifest));z.writestr(name,raw)
        with self.assertRaises(HmiError):import_pack(archive,digest(archive.read_bytes()),self.root/'new')
        self.assertFalse((self.root/'new').exists())
