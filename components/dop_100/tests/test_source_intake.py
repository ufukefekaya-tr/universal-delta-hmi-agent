# SPDX-License-Identifier: Apache-2.0
"""Original neutral framing/copy/deletion regressions; no vendor/customer assets."""
from pathlib import Path
import tempfile,unittest
from tests.test_extended import fixture
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended.source_intake import complete_prefix,intake
from universal_diascreen_hmi.extended.native_resource_intake import Walk
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.extended.hmi4_inspect import element_hash,field
from universal_diascreen_hmi.extended import hmi4_transaction as tx

def gauge_source():
    raw,profile=fixture();q=Project(raw);e=q.element(1,10)
    old=q.file.payload[e.section.start:e.end];new=old.replace(b'Type=1\r\nSubType=3\r\n',b'Type=3\r\nSubType=1\r\nScaleFontSize=16\r\n',1)
    payload=q.file.payload[:e.section.start]+new+q.file.payload[e.end:];raw=q.file.encode(payload)
    q=Project(raw);profile['indexed_layout_sha256']=layout_digest(q)
    # Existing bounded frames shift by the exact owner delta; no tail scan.
    delta=len(new)-len(old);profile['reviewed_resources']['source_payload_sha256']=sha(payload)
    for f in profile['reviewed_resources']['frames']:f['header_start']+=delta
    return raw,profile

class SourceIntakeTests(unittest.TestCase):
    def refused(self,code,fn):
        with self.assertRaises(Exception) as cm:fn()
        self.assertEqual(getattr(cm.exception,'code',None),code,str(cm.exception))
    def test_literal_gauge_font_does_not_hide_following_page(self):
        raw,profile=gauge_source();q=complete_prefix(Project(raw));self.assertEqual(len(q.pages),2)
        self.assertEqual(q.index.number(q.element(1,10).section,'ScaleFontSize'),16);profile_check(q,profile)
    def test_unknown_frame_is_not_a_complete_one_page_project(self):
        raw,profile=gauge_source();q=Project(raw);raw=q.file.encode(q.file.payload.replace(b'ScaleFontSize=',b'UnknownGaugeSize=',1))
        self.assertEqual(len(Project(raw).pages),1);self.refused('INDEX_INCOMPLETE',lambda:complete_prefix(Project(raw)))
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'source.dpa').write_bytes(raw);s=Service(d)
            self.refused('INDEX_INCOMPLETE',lambda:s.open_project('source.dpa',sha(raw),profile,sha(canonical(profile))))
            self.assertIsNone(s.source)
    def test_new_scalar_is_model_version_and_family_scoped(self):
        raw,_=gauge_source();q=Project(raw)
        for old,new in [(b'Type=3\r\nSubType=1',b'Type=3\r\nSubType=2'),(b'ModelName=268502788',b'ModelName=1'),(b'Version=6.6.2.48',b'Version=6.6.2.49')]:
            data=q.file.encode(q.file.payload.replace(old,new,1));self.refused('INDEX_INCOMPLETE',lambda:complete_prefix(Project(data)))
    def test_multilanguage_resource_fonts_are_scalar_but_unknowns_refuse(self):
        raw,_=gauge_source();w=Walk(Project(raw));w.owner='Alarm'
        for k in ('wFont002','wFontRatio003','wMessageSize003'):self.assertEqual(w.field_kind(k,b'16'),'scalar')
        self.refused('RESOURCE_FIELD',lambda:w.field_kind('wFont004',b'16'))
        w.owner='NewTextBank';self.assertEqual(w.field_kind('wFont003',b'Arial'),'scalar')
    def test_fresh_profile_never_uses_old_or_partial_resource_ack(self):
        raw,_=gauge_source();q=Project(raw)
        self.refused('SOURCE_HASH',lambda:intake(raw,'0'*64,'Link1',0))
        self.refused('SOURCE_LINK',lambda:intake(raw,sha(raw),'Wrong',0))
        # Deliberately incomplete synthetic tail cannot become a fresh accepted profile.
        body=q.file.payload.replace(b'DefaultScreen=1\r\n',b'DefaultScreen=1\r\nCommName1=Link1\r\nDefPLCStationNr1=0\r\n',1)
        data=q.file.encode(body)
        with self.assertRaises(Exception):intake(data,sha(data),'Link1',0)
    def test_readonly_delete_preserves_gauge_and_refuses_writer(self):
        raw,profile=gauge_source();q=Project(raw)
        op=dict(op='delete_element',page_id=1,element_id=13,expected_element_sha256=element_hash(q,q.element(1,13)))
        result=tx.build(raw,profile,dict(version=1,operations=[op]));f=Project(result['candidate'])
        self.assertEqual(element_hash(q,q.element(1,10)),element_hash(f,f.element(1,10)))
        op.update(element_id=12,expected_element_sha256=element_hash(q,q.element(1,12)))
        self.refused('DELETE_SCOPE',lambda:tx.build(raw,profile,dict(version=1,operations=[op])))
    def test_source_login_copy_retains_level_actions_and_empty_macros(self):
        raw,profile=fixture();q=Project(raw);e=q.element(1,11);old=q.file.payload[e.section.start:e.end]
        new=old.replace(b'Type=1\r\nSubType=3',b'Type=12\r\nSubType=3\r\nLevel=0\r\nActionMarker=neutral-source-action',1)
        for k in ('ReadVar','WriteVar','TriggerVar'):
            t=e.section.one(k);new=new.replace(k.encode()+b'='+t.value,k.encode()+b'=None',1)
        body=q.file.payload[:e.section.start]+new+q.file.payload[e.end:];raw=q.file.encode(body);q=Project(raw)
        profile['indexed_layout_sha256']=layout_digest(q);profile['reviewed_resources']['source_payload_sha256']=sha(body)
        for frame in profile['reviewed_resources']['frames']:frame['header_start']+=len(new)-len(old)
        op=dict(op='clone_element',page_id=1,element_id=11,expected_element_sha256=element_hash(q,q.element(1,11)),new_page_id=2,new_element_id=30,retain_bindings=True,retain_macros=False)
        result=tx.build(raw,profile,dict(version=1,operations=[op]));f=Project(result['candidate']);cloned=f.element(2,30)
        self.assertEqual(field(f,cloned.section,'Level'),'0');self.assertEqual(field(f,cloned.section,'ActionMarker'),'neutral-source-action')
        op['retain_bindings']=False;self.refused('LOGIN_RETENTION',lambda:tx.build(raw,profile,dict(version=1,operations=[op])))
    def test_delete_event_browser_and_unknown_incoming_dependencies_refuse(self):
        for owner,key,value in [(13,'EventID',77),(13,'RelatedFileBrowserPartID',12),(13,'UnknownWidgetPartID',12),(10,'RelatedFileBrowserPartID',13),(10,'UnknownWidgetPartID',13),(10,'rPartID','00013'),(10,'RelatedFileBrowserPartID','00013'),(10,'UnknownWidgetPartID','opaque-expression')]:
            with self.subTest(owner=owner,key=key):
                raw,profile=gauge_source();q=Project(raw);e=q.element(1,owner);insert=(key+'='+str(value)+'\r\n').encode();at=e.section.end
                body=q.file.payload[:at]+insert+q.file.payload[at:];raw=q.file.encode(body);q=Project(raw)
                profile['indexed_layout_sha256']=layout_digest(q);profile['reviewed_resources']['source_payload_sha256']=sha(body)
                for frame in profile['reviewed_resources']['frames']:frame['header_start']+=len(insert)
                op=dict(op='delete_element',page_id=1,element_id=13,expected_element_sha256=element_hash(q,q.element(1,13)))
                self.refused('DELETE_DEPENDENCY',lambda:tx.build(raw,profile,dict(version=1,operations=[op])))

if __name__=='__main__':unittest.main()
