# SPDX-License-Identifier: Apache-2.0
"""Original neutral lookup fixtures; no customer native artifacts."""
import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from tests.test_extended import fixture as base_fixture
from universal_diascreen_hmi.operations import token_patch
from tests.fixtures import line,wide
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.extended.hmi4_inspect import element_hash,audit_contract,native_type
from universal_diascreen_hmi.extended import state_lookup as lookup,hmi4_transaction as tx

def fixture():
 raw,p=base_fixture();q=Project(raw);e=q.element(1,13);patch=token_patch(q,e.section,'ReadVar','{'+p['link']+'}'+str(p['station'])+'@M13','neutral direct source read')
 patches=[patch,Patch(e.states[0].start,e.states[0].start,b'',line('ReadLink',2),'neutral direct-link2 source')];body,_=apply_spans(q.file.payload,patches);out=q.file.encode(body);p['reviewed_resources']=tx.map_resources(q,p,body,patches);p['indexed_layout_sha256']=layout_digest(Project(out));return out,p

def donor_fixture(raw):
 q=Project(raw);e=q.element(1,10)
 header=dict(Type=7,SubType=1,CombineType=0,X=10,Y=10,Width=200,Height=40,Style=32768,BorderColor=11842740,ReadMemType=0,ReadLink=1,ReadVar='$1',MemLen=1,MemFmt=2,Level=0,antialiasing=0,bFreeze=0,AutoResizeByText=0,AutoResizeMargin=0,nPartsID=10,RelatedFileBrowserPartID=-1,ChangeTime=500,VisibleLink=1,VisibleVar='None',VisibleCondition=1)
 head=b'[Element]\r\n'+b''.join(line(k,v)for k,v in header.items())+b''.join(wide('wDescTextLen'+str(n),'')for n in range(3));frames=[]
 for value in (0,1):
  fields={k:0 for k in lookup.STATE if not k.startswith('wTextLen')};fields.update(Value=value,FontAlign=33,PictureAlign=34,TransEffect=1,StretchMode=2,FgFillType=1,FgFillStyle=1,FgFillAngleArg='None',FgFillXArg='None',FgFillYArg='None')
  for n in range(3):fields.update({'FontSize'+str(n):14,'FontRatio'+str(n):100,'FontName'+str(n):'Arial'})
  frames.append(b'[State]\r\n'+b''.join(line(k,v)for k,v in sorted(fields.items()))+b''.join(wide('wTextLen'+str(n),'')for n in range(3)))
 body=q.file.payload[:e.section.start]+head+b''.join(frames)+q.file.payload[e.end:];return q.file.encode(body)

class LookupTests(unittest.TestCase):
 def setUp(self):
  self.raw,self.profile=fixture();self.q=Project(self.raw);self.donor=donor_fixture(self.raw);self.dq=Project(self.donor)
 def spec(self,values=range(32)):
  values=list(values);c=dict(tags=[dict(address='D100',type='INT',words=1,access='READ_ONLY',enum=values)])
  op=dict(op='state_lookup',page_id=1,element_id=13,expected_element_sha256=element_hash(self.q,self.q.element(1,13)),donor=dict(path='donor.dpa',source_sha256=sha(self.donor),page_id=1,element_id=10,element_sha256=element_hash(self.dq,self.dq.element(1,10)),template_state_value=0),binding=dict(address='D100',type='INT',access='READ_ONLY',link=self.profile['link'],station=self.profile['station']),states=[dict(value=v,texts=['State '+str(v)]*3,sizes=[14]*3,alignment=33,bold=0,colors=dict(font='#123456',background='#FFFFFF',foreground='#FFFFFF'))for v in values])
  return dict(version=1,contract=c,contract_sha256=sha(canonical(c)),operations=[op])
 def build(self,s=None):return tx.build(self.raw,self.profile,s or self.spec(),lookup_sources={sha(self.donor):self.dq})
 def refused(self,code,f):
  with self.assertRaises(Exception)as c:f()
  self.assertEqual(getattr(c.exception,'code',None),code,str(c.exception))
 def test_32_and_sparse_exact_domains_preserve_unowned_bytes(self):
  for values in (range(32),):
   spec=self.spec(values);b=self.build(spec);q=Project(b['candidate']);e=q.element(1,13);self.assertEqual([q.index.number(st,'Value')for st in e.states],list(values));self.assertIsNone(native_type(q,e));self.assertEqual(element_hash(q,q.element(1,10)),element_hash(self.q,self.q.element(1,10)));self.assertTrue(b['proof']['application_auth_globalmacros_exact']);self.assertTrue(b['proof']['resource_bytes_exact'])
   c=spec['contract'];self.assertEqual(audit_contract(q,c,sha(canonical(c)),True,lookup_markers=b['profile']['state_lookups'])['status'],'PASS');self.assertEqual(audit_contract(q,c,sha(canonical(c)),True)['status'],'FAIL')
  self.refused('LOOKUP_DENSE_INDEXED',lambda:self.build(self.spec((0,3,31))))
 def test_missing_duplicate_extra_negative_boolean_enum_refuse(self):
  for variant in ('missing','duplicate','extra','negative','bool'):
   s=self.spec();op=s['operations'][0]
   if variant=='missing':op['states'].pop()
   if variant=='duplicate':op['states'][1]['value']=0
   if variant=='extra':op['states'].append({**op['states'][0],'value':32})
   if variant=='negative':s['contract']['tags'][0]['enum'][0]=-1
   if variant=='bool':op['states'][0]['value']=False
   s['contract_sha256']=sha(canonical(s['contract']));self.refused('LOOKUP_STATES'if variant=='bool'else'LOOKUP_ENUM'if variant=='negative'else'LOOKUP_DENSE_INDEXED',lambda:self.build(s))
 def test_dependency_and_font_variants_refuse(self):
  e=self.dq.element(1,10)
  for old,new,code in [(b'VisibleVar=None',b'VisibleVar=$2','LOOKUP_DEPENDENCY'),(b'ChangeTime=500',b'EventID=1\r\nChangeTime=500','LOOKUP_SCHEMA'),(b'FontName0=Arial',b'FontName0=Unknown','LOOKUP_FONT')]:
   body=self.dq.file.payload[:e.section.start]+self.dq.file.payload[e.section.start:e.end].replace(old,new,1)+self.dq.file.payload[e.end:];q=Project(self.dq.file.encode(body));self.refused(code,lambda:lookup.verify_donor(q,q.element(1,10),self.q))
 def test_no_unsigned_or_bool_general_coercion_and_writer_refuse(self):
  for typ,words,adr,access in [('BOOL',0,'M100','READ_ONLY'),('DINT',2,'D100','READ_ONLY'),('INT',1,'D100','HMI_WRITE')]:
   s=self.spec();tag=s['contract']['tags'][0];tag.update(type=typ,words=words,address=adr,access=access);s['operations'][0]['binding']['address']=adr;s['contract_sha256']=sha(canonical(s['contract']));self.refused('LOOKUP_TYPE',lambda:self.build(s))
 def test_fresh_session_donor_drift_restore_and_save(self):
  with tempfile.TemporaryDirectory()as d:
   ws=Path(d);(ws/'source.dpa').write_bytes(self.raw);(ws/'donor.dpa').write_bytes(self.donor)
   def session():
    s=Service(ws,allow_write=True);s.open_project('source.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)));s.inspect();return s
   s=session();spec=self.spec();p=s.plan_native_update(sha(self.raw),spec,sha(canonical(spec)));h=p['plan_sha256'];(ws/'donor.dpa').write_bytes(b'drift');self.refused('LOOKUP_DONOR_HASH',lambda:s.apply_plan(h,h));(ws/'donor.dpa').write_bytes(self.donor);s=session();s.restore_plan(h);s.apply_plan(h,h);s.save_new('lookup.dpa',p['candidate_sha256']);self.assertEqual((ws/'source.dpa').read_bytes(),self.raw);self.assertEqual(sha((ws/'lookup.dpa').read_bytes()),p['candidate_sha256'])
