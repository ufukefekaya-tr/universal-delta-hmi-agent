# SPDX-License-Identifier: Apache-2.0
"""Original synthetic native tests; no customer project or PLC data."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
import builtins
import base64
from io import BytesIO
from tests.fixtures import payload,wrap,profile,line,wide
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended import hmi4_transaction as tx
from universal_diascreen_hmi.extended.hmi4_inspect import element_hash,numeric,contract_rows
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.resources import flat_dib,_header

def fixture():
    body=payload().replace(b'PanelName=Synthetic panel',b'PanelName=DOP-107EV').replace(b'ModelName=1\r\n',b'ModelName=268502788\r\n').replace(b'PanelResWidth=400',b'PanelResWidth=800').replace(b'PanelResHeight=240',b'PanelResHeight=480')
    body=body.replace(b'ApplicationVersion=6.6.2.48',b'Version=6.6.2.48')
    body=body.replace(b'MemLen=6\r\n',b'MemLen=2\r\n')
    # Replace the explicit neutral generated DIB rather than scanning opaque bytes.
    old=flat_dib(400,240,0x111111);new=flat_dib(800,480,0x111111)
    body=body.replace(line('Size',len(old))+old,line('Size',len(new))+new)
    body=body.replace(b'FontSize0=16\r\n',b'FontSize0=16\r\nFontSize1=16\r\nFontSize2=16\r\nFontName1=Arial\r\nFontName2=Arial\r\n')
    for caption in ('START','START ON','OFF','OFF ON',''):
        body=body.replace(wide('wTextLen0',caption),wide('wTextLen0',caption)+wide('wTextLen1',caption)+wide('wTextLen2',caption))
    raw=wrap(body);q=Project(raw);p=profile();p.update(panel=dict(width=800,height=480),model_name='268502788',indexed_layout_sha256=layout_digest(q),background_sha256={'1':sha(new),'2':sha(new)},numeric_types={'REAL':dict(bits=32,floating=True,MemLen=2,MemFmt=5,evidence='Synthetic source family')})
    frames=[]
    for section,key in [('Background','Size'),('DIATag','size')]:
        start=body.index(('['+section+']\r\n').encode());f=_header(body,start,section,key)
        frames.append(dict(section=section,header_start=start,header_sha256=sha(body[f.start:f.blob_start]),blob_sha256=sha(body[f.blob_start:f.blob_end])))
    p['reviewed_resources']=dict(reviewed_boundary_ack=True,source_payload_sha256=sha(body),frames=frames)
    return raw,p

class ExtendedTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.profile=fixture();self.q=Project(self.raw)
    def op(self,**extra):return dict(op='edit_element',page_id=1,element_id=10,expected_element_sha256=element_hash(self.q,self.q.element(1,10)),**extra)
    def build(self,operations):return tx.build(self.raw,self.profile,dict(version=1,operations=operations))
    def refused(self,code,fn):
        with self.assertRaises(Exception) as cm:fn()
        self.assertEqual(getattr(cm.exception,'code',None),code,str(cm.exception))
    def test_multilanguage_atomic_text_and_preserve(self):
        b=self.build([self.op(states=[dict(value=0,texts=['AÇ','OPEN','ОТВОРИ'])])]);q=Project(b['candidate'])
        self.assertEqual(q.index.text(q.element(1,10).states[0],'wTextLen2'),'ОТВОРИ')
        self.assertEqual(element_hash(q,q.element(1,11)),element_hash(self.q,self.q.element(1,11)))
        self.assertEqual(q.file.payload[:q.pages[0].section.start],self.q.file.payload[:self.q.pages[0].section.start])
    def test_real_decimal_format_not_integer_scale(self):
        op=dict(op='numeric_display',page_id=1,element_id=12,expected_element_sha256=element_hash(self.q,self.q.element(1,12)),display=dict(decimals=3))
        q=Project(self.build([op])['candidate']);n=numeric(q,q.element(1,12));self.assertEqual(n['factor'],'1');self.assertEqual(Decimal(n['effective_gain']),Decimal(1))
    def test_source_hash_guard(self):self.refused('ELEMENT_DRIFT',lambda:self.build([{**self.op(), 'expected_element_sha256':'0'*64}]))
    def test_unknown_property_guard(self):self.refused('FIELD_SCOPE',lambda:self.build([self.op(fields=dict(Password=123))]))
    def test_geometry_guard(self):self.refused('GEOMETRY',lambda:self.build([self.op(fields=dict(X=799))]))
    def test_duplicate_owner_guard(self):self.refused('DUPLICATE_OWNER',lambda:self.build([self.op(fields=dict(X=12)),self.op(fields=dict(Y=12))]))
    def test_type_width_and_unknown_constraints(self):
        self.refused('TAG_WIDTH',lambda:contract_rows(dict(tags=[dict(address='D100',type='DINT',words=1,access='READ_ONLY')])))
        self.refused('TAG_FIELD_UNQUALIFIED',lambda:contract_rows(dict(tags=[dict(address='D100',type='INT',words=1,access='READ_ONLY',gain=1000)])))
    def test_source_move_and_clone(self):
        op=self.op();op.update(op='move_element',new_page_id=2,new_element_id=30,retain_macros=True,fields=dict(X=20,Y=30))
        q=Project(self.build([op])['candidate']);self.assertEqual(q.index.scalar(q.element(2,30).section,'ReadVar'),self.q.index.scalar(self.q.element(1,10).section,'ReadVar'));self.assertEqual(len(q.pages[0].elements),3)
    def test_durable_fresh_process_state_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'source.dpa').write_bytes(self.raw)
            def session():
                s=Service(root,allow_write=True);s.open_project('source.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)));s.inspect();return s
            spec=dict(version=1,operations=[self.op(states=[dict(value=0,texts=['NEW']*3)])]);s=session();p=s.plan_native_update(sha(self.raw),spec,sha(canonical(spec)));ph=p['plan_sha256']
            s=session();s.restore_plan(ph);self.refused('APPROVAL',lambda:s.apply_plan(ph,'0'*64));s.apply_plan(ph,ph)
            s=session();s.restore_candidate(ph,ph);s.save_new('new.dpa',p['candidate_sha256'])
            self.assertEqual(sha((root/'new.dpa').read_bytes()),p['candidate_sha256']);self.assertEqual((root/'source.dpa').read_bytes(),self.raw)
            self.refused('REPLAY_OR_UNKNOWN',lambda:session().restore_plan(ph))
    def test_vendor_boundary_and_empty_reference_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            s=Service(d);(Path(d)/'source.dpa').write_bytes(self.raw);s.open_project('source.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)))
            self.refused('NOT_IMPLEMENTED',lambda:s.vendor_compile(sha(self.raw)))
            self.assertIsNone(s.capabilities()['active_reference'])

    def test_complete_release_manifest_guards(self):
        actual=release_inventory();value=dict(schema='delta.hmi.source-release.v1',version=VERSION,files=[dict(path=k,**v) for k,v in actual.items()])
        self.assertEqual(validate_release_manifest(value,actual)['status'],'SOURCE_MANIFEST_VERIFIED')
        for rows in ([],value['files'][:-1],value['files']+[value['files'][0]],[{**value['files'][0],'path':'../escape.py'}], [{**r,'sha256':'0'*64} for r in value['files']]):
            with self.subTest(rows=len(rows)):
                with self.assertRaises(Error):validate_release_manifest({**value,'files':rows},actual)

    def test_background_dependency_absent_is_structured_refusal(self):
        original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='PIL':raise ImportError('Neutral absent optional dependency')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',missing):self.refused('DEPENDENCY_UNAVAILABLE',lambda:tx.png_dib('AA=='))

    def test_background_bomb_is_structured_refusal(self):
        import types
        class Bomb(Exception):pass
        class Image:
            DecompressionBombError=Bomb
            @staticmethod
            def open(*args):raise Bomb()
        with patch.dict('sys.modules',{'PIL':types.SimpleNamespace(Image=Image)}):self.refused('PNG',lambda:tx.png_dib('AA=='))

    def test_background_truncated_pixels_or_dependency_refusal(self):
        try:from PIL import Image
        except ImportError:
            self.refused('DEPENDENCY_UNAVAILABLE',lambda:tx.png_dib('AA=='));return
        stream=BytesIO();Image.new('RGB',(800,480)).save(stream,format='PNG');raw=stream.getvalue()[:100]
        # The header is valid; the incomplete IDAT is detected only while loading.
        with Image.open(BytesIO(raw)) as image:self.assertEqual(image.size,(800,480))
        self.refused('PNG',lambda:tx.png_dib(base64.b64encode(raw).decode()))

    def test_transport_io_failure_never_claims_no_effect(self):
        from universal_diascreen_hmi.extended.transport import install,cli
        install()
        class Interrupted:
            def save_as(self,path,candidate_sha256):raise OSError('Neutral injected I/O interruption')
        self.refused('IO_FAILURE_RECONCILE_REQUIRED',lambda:cli.call_tool(Interrupted(),'save_as',dict(path='new.dpa',candidate_sha256='0'*64)))

if __name__=='__main__':unittest.main()
