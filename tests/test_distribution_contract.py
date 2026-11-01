"""Adversarial exact-membership packaging, independent of keyword scanning."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import gzip
import io
import tarfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package_contract_test',ROOT/'tools/package_contract.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class DistributionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.env=patch.object(mod,'ROOT',self.root);self.env.start();self.addCleanup(self.env.stop)
        def put(key,raw):
            p=self.root/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return {'path':key,'sha256':mod.digest(raw)}
        rows=[put('LICENSE',b'original neutral test license'),put('README.md',b'original neutral test metadata')]
        for key in mod.SKILL:rows.append(put('skills/delta-hmi/'+key,b'original neutral instruction fixture'))
        components={}
        for family in ('dop_b','dop_100'):
            raw=b'# original neutral code fixture\n';key='src/neutral.py';put('components/'+family+'/'+key,raw)
            components[family]={'files':[{'path':key,'sha256':mod.digest(raw)}]}
        rows.append(put('templates/component_files.json',json.dumps({'components':components}).encode()))
        rows.append(put('templates/releases.lock.json',json.dumps({'dop_b':{'archive':'pinned.zip','sha256':'0'*64,'bytes':1,'linux_archive':'pinned.tar.gz','linux_sha256':'1'*64}}).encode()))
        put('reports/IMPLEMENTATION_MANIFEST.json',json.dumps({'files':rows}).encode())

    def test_exact_source_skill_and_tar_readback(self):
        for name in ('source.zip','source.tar.gz'):
            result=mod.build(self.root/'dist'/name)
            self.assertEqual(result['status'],'TWO_FAMILY_FILE_MCP_OFFLINE')
            self.assertEqual(mod.audit(result['path'])['status'],'PASS')
        result=mod.build(self.root/'dist/skill.zip',skill=True)
        self.assertEqual(set(mod.read_archive(result['path'])),{'delta-hmi/'+p for p in mod.SKILL})
        self.assertEqual(mod.audit(result['path'])['status'],'PASS')

    def test_inventory_external_content_is_never_read(self):
        sentinel=[]
        for folder in ('reports','components/dop_b','skills/delta-hmi'):
            p=self.root/folder/'unlisted-private.txt';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'DO NOT READ');sentinel.append(p)
        original=Path.read_bytes
        def read(path):
            if path in sentinel:raise AssertionError('Unlisted content was read')
            return original(path)
        with patch.object(Path,'read_bytes',read):
            entries=mod.source_entries()
            self.assertFalse(any(p.relative_to(self.root).as_posix() in entries for p in sentinel))
            staged=mod.stage_source(self.root/'staged')
            self.assertFalse(any((staged/p.relative_to(self.root)).exists() for p in sentinel))
            component=mod.stage_source(self.root/'component-staged','dop_b')
            self.assertEqual({p.relative_to(component).as_posix() for p in component.rglob('*') if p.is_file()},{'src/neutral.py'})

    def test_changed_component_and_hardlinked_reviewed_file_refuse(self):
        p=self.root/'components/dop_b/src/neutral.py';old=p.read_bytes();p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'drift'):mod.build(self.root/'dist/no.zip')
        self.assertFalse((self.root/'dist/no.zip').exists());p.write_bytes(old)
        alias=self.root/'hardlink';os.link(self.root/'README.md',alias)
        with self.assertRaisesRegex(ValueError,'Hardlinked'):mod.source_entries()

    def test_extra_missing_and_duplicate_archive_members_refuse(self):
        p=self.root/'dist/source.zip';mod.build(p);members=mod.read_archive(p)
        for label,updates,remove in [('extra',{'unrequested.txt':b'private'},None),('missing',{},'LICENSE')]:
            changed={**members,**updates}
            if remove:del changed[remove]
            q=self.root/'dist'/(label+'.zip');mod.write_archive(q,changed)
            with self.assertRaises(ValueError):mod.audit(q)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(p,'a') as z:z.writestr('LICENSE',b'duplicate')
        with self.assertRaisesRegex(ValueError,'duplicate'):mod.audit(p)

    def test_wrong_skill_prefix_and_backend_pin_refuse(self):
        q=self.root/'dist/wrong-skill.zip';mod.write_archive(q,{'wrong/'+p:b'fixture' for p in mod.SKILL})
        with self.assertRaisesRegex(ValueError,'skill'):mod.audit(q)
        archive=self.root/'wrong.zip';archive.write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'Pinned backend'):mod.build(self.root/'dist/no.zip',archive)
        self.assertFalse((self.root/'dist/no.zip').exists())

    def test_manifest_duplicate_case_alias_and_traversal_refuse(self):
        p=self.root/'reports/IMPLEMENTATION_MANIFEST.json';v=json.loads(p.read_text());old=p.read_bytes()
        for row in ({'path':'README.MD','sha256':mod.digest(b'x')},{'path':'../outside','sha256':mod.digest(b'x')},{'path':'docs/private.dpa','sha256':mod.digest(b'x')}):
            p.write_text(json.dumps({'files':v['files']+[row]}))
            with self.assertRaises(ValueError):mod.source_entries()
            p.write_bytes(old)

    def test_existing_output_preserved(self):
        q=self.root/'dist/existing.zip';q.parent.mkdir();q.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):mod.build(q)
        self.assertEqual(q.read_bytes(),b'keep')

    def test_component_control_must_be_pinned_before_component_read(self):
        p=self.root/'reports/IMPLEMENTATION_MANIFEST.json';v=json.loads(p.read_text());original=p.read_bytes()
        for missing in (True,False):
            rows=[dict(r) for r in v['files'] if not missing or r['path']!='templates/component_files.json']
            if not missing:next(r for r in rows if r['path']=='templates/component_files.json')['sha256']='0'*64
            p.write_text(json.dumps({'files':rows}))
            read=Path.read_bytes
            def guarded(path):
                if 'components' in path.parts:raise AssertionError('Component payload read before control gate')
                return read(path)
            with patch.object(Path,'read_bytes',guarded),self.assertRaisesRegex(ValueError,'component control'):mod.source_entries()
            p.write_bytes(original)

    def test_windows_case_aliases_of_private_directories_refuse(self):
        for p in ('reports/.AGENT-STATE/private.txt','components/dop_b/.VENV/private.txt','reports/private.EGG-INFO/PKG-INFO'):
            with self.assertRaisesRegex(ValueError,'Private'):mod.name(p)

    def test_directory_and_pax_metadata_bounded_before_parser_expansion(self):
        q=self.root/'dist/metadata.zip';mod.write_archive(q,{'docs/a.txt':b'a'})
        with patch.object(mod,'MAX_DIRECTORY',1),self.assertRaisesRegex(ValueError,'directory metadata'):mod.read_archive(q)
        q=self.root/'metadata.tar.gz'
        with tarfile.open(q,'w:gz',format=tarfile.PAX_FORMAT) as z:
            entry=tarfile.TarInfo('docs/a.txt');entry.size=1;entry.pax_headers={'comment':'x'*2000};z.addfile(entry,io.BytesIO(b'a'))
        with patch.object(mod,'MAX_TAR',1024),self.assertRaisesRegex(ValueError,'Decompressed TAR metadata'):mod.read_archive(q)

    def test_source_version_claim_cannot_change_independently(self):
        q=self.root/'dist/source.zip';mod.build(q);data=mod.read_archive(q)
        manifest=json.loads(data['PACKAGE_MANIFEST.json']);manifest['versions']['dop_100']='99';data['PACKAGE_MANIFEST.json']=json.dumps(manifest).encode()
        q=self.root/'dist/wrong-version.zip';mod.write_archive(q,data)
        with self.assertRaisesRegex(ValueError,'scope/version'):mod.audit(q)
