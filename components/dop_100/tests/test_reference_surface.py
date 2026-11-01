# SPDX-License-Identifier: Apache-2.0
"""External reference surface tested with entirely original synthetic data."""
from pathlib import Path
import os,tempfile,unittest
from unittest.mock import patch
from tests.test_template_lifecycle import neutral_fixture
from universal_diascreen_hmi.extended.common import canonical,sha,Error
from universal_diascreen_hmi.extended.hmi4_service import Service

class ReferenceSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.host=root/'host';self.host.mkdir();self.work=root/'work';self.work.mkdir();self.raw,self.profile=neutral_fixture()
        blobs={'neutral.dpa':self.raw,'profile.json':canonical(self.profile),
               'parameters.json':canonical(dict(parameters=[dict(address='D100',native=dict(MemLen=2,MemFmt=5))])),
               'tags.json':canonical(dict(tags=[dict(tag='Neutral.Value',address='D100',type='REAL',words=2,access='PARAMETER_EDIT')]))}
        for n,b in blobs.items():(self.host/n).write_bytes(b)
        entry=dict(revision='neutral_1',status='REFERENCE_ONLY',dpa=dict(path='neutral.dpa',sha256=sha(self.raw)),profile_sha256=sha(canonical(self.profile)))
        for key,name in [('profile','profile.json'),('parameters','parameters.json'),('tags','tags.json')]:entry[key]=dict(path=name,sha256=sha(blobs[name]))
        self.registry=dict(schema='delta.hmi.reference-registry.v1',active_revision='neutral_1',deliveries=[entry],font_sha256={})
        (self.host/'registry.json').write_bytes(canonical(self.registry));p=patch.dict(os.environ,{'DIA_HMI_REFERENCE_ROOT':str(self.host)});p.start();self.addCleanup(p.stop)
    def refusal(self,code,fn):
        with self.assertRaises(Exception) as cm:fn()
        self.assertEqual(getattr(cm.exception,'code',None),code,str(cm.exception))
    def test_catalog_contract_and_open_delivery_do_not_mix_sessions(self):
        s=Service(self.work,allow_write=True);listing=s.list_deliveries();self.assertEqual(len(listing['deliveries']),1)
        current=s.current_delivery();self.assertEqual(current['active_revision'],'neutral_1');self.assertIsNone(s.source)
        self.assertEqual(s.inspect_parameters()['matrix']['parameters'][0]['address'],'D100')
        c=s.get_reference_contract();self.assertEqual(c['contract']['tags'][0]['type'],'REAL');self.assertEqual(c['contract_sha256'],sha(canonical(c['contract'])))
        opened=s.open_delivery('neutral_1',sha(self.raw),sha(canonical(self.profile)));self.assertTrue(opened['staged_source'])
        self.assertEqual(s.source,self.raw);self.assertTrue(s.source_path.is_relative_to(self.work))
        before=s.source_path.read_bytes();s.current_delivery();s.get_reference_contract();self.assertEqual(s.source_path.read_bytes(),before)
        self.assertEqual((self.host/'neutral.dpa').read_bytes(),self.raw)
    def test_wrong_pin_readonly_staging_and_missing_data(self):
        s=Service(self.work)
        self.refusal('REFERENCE_HASH',lambda:s.open_delivery('neutral_1','0'*64,sha(canonical(self.profile))))
        self.refusal('WRITE_DISABLED',lambda:s.open_delivery('neutral_1',sha(self.raw),sha(canonical(self.profile))))
        s.open_delivery('neutral_1',sha(self.raw),sha(canonical(self.profile)),stage_source=False);self.assertEqual(s.source_path,self.host/'neutral.dpa')
        self.refusal('DELIVERY_UNKNOWN',lambda:s.get_reference_contract('absent'))
    def test_reference_escape_duplicate_and_file_drift_refuse(self):
        from universal_diascreen_hmi.extended import hmi4_registry as r
        self.refusal('CATALOG_PATH',lambda:r.read_pin(dict(path='../escape.dpa',sha256=sha(self.raw))))
        (self.host/'neutral.dpa').write_bytes(self.raw+b' ');self.refusal('REFERENCE_DRIFT',lambda:r.load())
        (self.host/'registry.json').write_bytes(b'{"schema":1,"schema":2}');self.refusal('CATALOG_DUPLICATE',r.registry)
    def test_unconfigured_catalog_is_empty_not_bundled(self):
        with patch.dict(os.environ,{'DIA_HMI_REFERENCE_ROOT':''}):
            s=Service(self.work);self.assertEqual(s.list_deliveries()['deliveries'],[])
            self.refusal('DELIVERY_UNKNOWN',s.current_delivery)

if __name__=='__main__':unittest.main()
