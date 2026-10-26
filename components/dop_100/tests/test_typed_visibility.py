# SPDX-License-Identifier: Apache-2.0
"""Neutral visibility pairs, typed-role separation and durable transaction guards."""
from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from tests.test_extended import fixture as base_fixture
from tests.fixtures import line
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended.hmi4_inspect import field,element_hash,native_type,audit_contract
from universal_diascreen_hmi.extended import hmi4_transaction as tx,typed_visibility as visible
from universal_diascreen_hmi.extended.hmi4_service import Service

def fixture():
    raw,p=base_fixture();q=Project(raw);patches=[]
    for eid,changes,extra in [
        (12,dict(Type=5,WriteVar='None',ReadVar='{Link1}0@D120',VisibleVar='{Link1}0@M12',TriggerVar='None'),dict(ReadLink=2,ReadMemType=0,VisibleLink=2,VisibleCondition=0)),
        (13,dict(Type=10,SubType=6,ReadVar='None',WriteVar='None',VisibleVar='$15.0',TriggerVar='None'),dict(VisibleLink=1,VisibleCondition=1))]:
        e=q.element(1,eid);patches += [token_patch(q,e.section,k,v,'neutral fixture')for k,v in changes.items()]
        patches.append(Patch(e.states[0].start,e.states[0].start,b'',b''.join(line(k,v)for k,v in extra.items()),'neutral existing fields'))
    patches.append(Patch(q.pages[0].section.start,q.pages[0].section.start,b'',line('CommName1','Link1')+line('DefPLCStationNr1',0),'neutral source endpoint'))
    body,_=apply_spans(q.file.payload,patches);raw=q.file.encode(body);p['indexed_layout_sha256']=layout_digest(Project(raw));p['reviewed_resources']=tx.map_resources(q,p,body,patches);return raw,p

class VisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw,cls.profile=fixture();cls.q=Project(cls.raw);cls.numeric=(1,12);cls.dash=(1,13);cls.witness=(1,12);cls.target=2
    def refused(self,code,fn):
        with self.assertRaises(Exception)as cm:fn()
        self.assertEqual(getattr(cm.exception,'code',None),code,str(cm.exception))
    def spec(self):
        c=dict(tags=[dict(address='D100',type='REAL',words=2,access='READ_ONLY'),dict(address='M100',type='BOOL',words=0,access='READ_ONLY')]);ops=[]
        for (p,i),newid,truth in [(self.numeric,990,True),(self.dash,991,False)]:
            op=dict(op='clone_element',page_id=p,element_id=i,expected_element_sha256=element_hash(self.q,self.q.element(p,i)),new_page_id=self.target,new_element_id=newid,retain_bindings=True,retain_macros=False,visibility=dict(address='M100',type='BOOL',access='READ_ONLY',link=self.profile['link'],station=self.profile['station'],visible_when=truth))
            if truth:op['binding']=dict(address='D100',type='REAL',access='READ_ONLY',link=self.profile['link'],station=self.profile['station'])
            ops.append(op)
        return dict(version=1,contract=c,contract_sha256=sha(canonical(c)),operations=ops)
    def build(self,s=None):return tx.build(self.raw,self.profile,s or self.spec())
    def test_pair_source_conditions_separate_real_bool_and_unowned_preservation(self):
        s=self.spec();b=self.build(s);q=Project(b['candidate']);c=s['contract'];n=q.element(self.target,990);d=q.element(self.target,991)
        self.assertEqual(native_type(q,n),'REAL');self.assertEqual(field(q,n.section,'ReadVar'),'{'+self.profile['link']+'}'+str(self.profile['station'])+'@D100')
        for k in ('MemLen','MemFmt','GainValue','OffsetValue','DotNum','HiWordFirst','HiDwordFirst'):
            self.assertEqual(field(self.q,self.q.element(*self.numeric).section,k),field(q,n.section,k))
        self.assertEqual([visible.readback(q,e,c)['visible_when']for e in (n,d)],[True,False]);self.assertEqual([q.index.number(e.section,'VisibleCondition')for e in (n,d)],[0,1])
        self.assertEqual(audit_contract(q,c,sha(canonical(c)),True)['status'],'PASS')
        for state in (False,True):self.assertEqual([r for r,e in [('numeric',n),('dash',d)]if visible.readback(q,e,c)['visible_when']==state],['numeric'if state else'dash'])
        self.assertTrue(b['proof']['application_auth_globalmacros_exact']);self.assertTrue(b['proof']['resource_bytes_exact']);self.assertTrue(b['proof']['exact_inverse'])
        for p in self.q.pages:
            for e in p.elements:self.assertEqual(element_hash(self.q,e),element_hash(q,q.element(p.page_id,self.q.index.number(e.section,'nPartsID'))))
    def test_condition_boolean_unknown_and_wrong_role_refuse(self):
        for value in (False,0,1,'true',None):
            s=self.spec();s['operations'][0]['visibility']['visible_when']=value;self.refused('VISIBILITY_CONDITION',lambda:self.build(s))
        for key,value,code in [('condition',1,'VISIBILITY_SPEC'),('access','HMI_WRITE','VISIBILITY_TAG'),('type','INT','VISIBILITY_TAG'),('address','D100','VISIBILITY_TAG'),('link','Other','VISIBILITY_LINK'),('station',True,'VISIBILITY_LINK')]:
            s=self.spec();s['operations'][0]['visibility'][key]=value;self.refused(code,lambda:self.build(s))
    def test_wrong_contract_type_width_access_and_hash_refuse(self):
        for mode,code in [('type','TAG_WIDTH'),('width','TAG_WIDTH'),('access','VISIBILITY_TAG'),('hash','CONTRACT_HASH')]:
            s=self.spec();tag=s['contract']['tags'][1]
            if mode=='type':tag['type']='INT'
            if mode=='width':tag['words']=1
            if mode=='access':tag['access']='HMI_WRITE'
            s['contract_sha256']='0'*64 if mode=='hash'else sha(canonical(s['contract']));self.refused(code,lambda:self.build(s))
    def test_wrong_family_and_unsupported_operation_refuse(self):
        e=next(e for p in self.q.pages for e in p.elements if (self.q.index.number(e.section,'Type'),self.q.index.number(e.section,'SubType'))==(1,3));s=self.spec();op=s['operations'][0];op.update(page_id=e.page_id,element_id=self.q.index.number(e.section,'nPartsID'),expected_element_sha256=element_hash(self.q,e));op.pop('binding');self.refused('VISIBILITY_FAMILY',lambda:self.build(s))
        s=self.spec();s['operations'][0]['op']='navigation';self.refused('OPERATION_SCOPE',lambda:self.build(s))
    def test_same_source_direct_witness_is_mandatory(self):
        p,i=self.witness;e=self.q.element(p,i);patches=[token_patch(self.q,e.section,'VisibleVar','$19.0','fixture removes direct witness'),token_patch(self.q,e.section,'VisibleLink',1,'fixture local link')];body,_=apply_spans(self.q.file.payload,patches);q=Project(self.q.file.encode(body));profile=deepcopy(self.profile);profile['indexed_layout_sha256']=layout_digest(q);profile['reviewed_resources']=tx.map_resources(self.q,self.profile,body,patches);s=self.spec()
        for op in s['operations']:op['expected_element_sha256']=element_hash(q,q.element(op['page_id'],op['element_id']))
        self.refused('VISIBILITY_WITNESS',lambda:tx.build(q.file.original,profile,s))
    def test_audit_cannot_hide_numeric_mismatch_behind_valid_bool(self):
        s=self.spec();b=self.build(s);q=Project(b['candidate']);s['contract']['tags'][0]['type']='DINT';r=audit_contract(q,s['contract'],sha(canonical(s['contract'])),True);self.assertEqual(r['status'],'FAIL');self.assertTrue(any(x.get('visibility')and x['status']=='PASS'for x in r['rows']));self.assertTrue(any(x['status']=='FAIL'for x in r['rows']))
        c=dict(tags=[dict(address='M100',type='BOOL',words=0,access='HMI_WRITE')]);self.assertEqual(audit_contract(q,c,sha(canonical(c)),True)['status'],'FAIL')
    def test_macro_indirect_unknown_condition_and_missing_fields_refuse(self):
        e=self.q.element(*self.numeric)
        for key,value,code in [('ReadMemType',1,'VISIBILITY_VARIANT'),('VisibleCondition',3,'VISIBILITY_CONDITION'),('VisibleLink',0,'VISIBILITY_SOURCE')]:
            patch=token_patch(self.q,e.section,key,value,'negative fixture');body,_=apply_spans(self.q.file.payload,[patch]);q=Project(self.q.file.encode(body));self.refused(code,lambda:visible.shape(q,q.element(*self.numeric)))
        for extra,code in [(b'VisibleOffsetVar=$10\r\n','VISIBILITY_VARIANT'),(b'AfterExecMacroLen=3\r\nX\r\n','VISIBILITY_OWNER')]:
            patch=Patch(e.states[0].start,e.states[0].start,b'',extra,'negative fixture');body,_=apply_spans(self.q.file.payload,[patch]);q=Project(self.q.file.encode(body));self.refused(code,lambda:visible.shape(q,q.element(*self.numeric)))
        token=e.section.one('VisibleCondition');patch=Patch(token.start,token.end,self.q.file.payload[token.start:token.end],b'','negative missing field');body,_=apply_spans(self.q.file.payload,[patch]);q=Project(self.q.file.encode(body));self.refused('VISIBILITY_FIELDS',lambda:visible.shape(q,q.element(*self.numeric)))
    def test_fresh_restore_exact_approval_newonly_save_and_readonly_audit(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);(root/'source.dpa').write_bytes(self.raw)
            def session():
                s=Service(root,allow_write=True);s.open_project('source.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)));s.inspect();return s
            spec=self.spec();s=session();p=s.plan_native_update(sha(self.raw),spec,sha(canonical(spec)));h=p['plan_sha256'];s=session();s.restore_plan(h);self.refused('APPROVAL',lambda:s.apply_plan(h,'0'*64));s.apply_plan(h,h);s.save_new('visibility.dpa',p['candidate_sha256']);self.assertEqual((root/'source.dpa').read_bytes(),self.raw)
            saved=(root/'visibility.dpa').read_bytes();q=Project(saved);self.assertEqual(sha(saved),p['candidate_sha256']);self.assertEqual(audit_contract(q,spec['contract'],spec['contract_sha256'],True)['status'],'PASS');self.refused('REPLAY_OR_UNKNOWN',lambda:session().restore_plan(h))

if __name__=='__main__':unittest.main()
