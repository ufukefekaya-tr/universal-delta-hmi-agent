# SPDX-License-Identifier: Apache-2.0
"""Neutral dense-view and readonly text-map audit; no proprietary sample."""
import unittest,copy,tempfile
from pathlib import Path
from tests import test_state_lookup as base_tests
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.extended.hmi4_inspect import element_hash
from universal_diascreen_hmi.extended import state_lookup as lookup

class DenseTests(unittest.TestCase):
 def setUp(self):self.base=base_tests.LookupTests();self.base.setUp()
 def spec(self):
  s=self.base.spec();tag=s['contract']['tags'][0];tag['enum']=[0,101,102,104,105,106,107,111,112,113,117,118,119,121,122];op=s['operations'][0];templates=['Unknown code {value}']*3;op['view']=dict(mode='DENSE_INDEXED',maximum=122,unknown_texts=templates);style=op['states'][0];op['states']=[{**copy.deepcopy(style),'value':i,'texts':(['Code '+str(i)]*3 if i in tag['enum']else[t.replace('{value}',str(i))for t in templates])}for i in range(123)];s['contract_sha256']=sha(canonical(s['contract']));return s
 def test_dense_view_keeps_produced_enum_separate_and_numeric_unknowns(self):
  s=self.spec();original=copy.deepcopy(s['contract']);b=self.base.build(s);q=Project(b['candidate']);e=q.element(1,13);m=b['profile']['state_lookups'][0];self.assertEqual(s['contract'],original);self.assertEqual(m['produced_values'],original['tags'][0]['enum']);self.assertEqual(m['view_values'],list(range(123)));self.assertEqual(len(m['unknown_values']),108);self.assertEqual(lookup.text_map(q,e)[103]['texts'],['Unknown code 103']*3);self.assertEqual(lookup.text_map(q,e)[105]['texts'],['Code 105']*3);self.assertTrue(b['proof']['resource_bytes_exact'])
 def test_dense_holes_order_and_placeholder_guards(self):
  for mode,code in [('no_view','LOOKUP_DENSE_INDEXED'),('missing','LOOKUP_DENSE_INDEXED'),('reorder','LOOKUP_DENSE_INDEXED'),('hole','LOOKUP_UNKNOWN_TEXT'),('other_placeholder','LOOKUP_UNKNOWN_TEXT'),('maximum','LOOKUP_VIEW')]:
   s=self.spec();op=s['operations'][0]
   if mode=='no_view':op.pop('view')
   if mode=='missing':op['states'].pop(103)
   if mode=='reorder':op['states'][9],op['states'][10]=op['states'][10],op['states'][9]
   if mode=='hole':op['states'][103]['texts'][0]='Incorrect named fault'
   if mode=='other_placeholder':op['view']['unknown_texts'][0]='Code {value} {other}'
   if mode=='maximum':op['view']['maximum']=123
   self.base.refused(code,lambda:self.base.build(s))
 def test_readback_rejects_same_set_in_wrong_order(self):
  s=self.spec();b=self.base.build(s);q=Project(b['candidate']);e=q.element(1,13);a,z=e.states[9],e.states[10];body=q.file.payload[:a.start]+q.file.payload[z.start:z.end]+q.file.payload[a.start:a.end]+q.file.payload[z.end:];bad=Project(q.file.encode(body));m=copy.deepcopy(b['profile']['state_lookups'][0]);m['owner_sha256']=element_hash(bad,bad.element(1,13));self.base.refused('LOOKUP_DENSE_INDEXED',lambda:lookup.readback(bad,bad.element(1,13),m,s['contract']['tags'][0]))
 def candidate(self):
  spec=self.spec();b=self.base.build(spec);q=Project(b['candidate']);profile=copy.deepcopy(b['profile']);profile.pop('state_lookups');e=q.element(1,13);items=[dict(page_id=1,element_id=13,expected_element_sha256=element_hash(q,e),view=spec['operations'][0]['view'],states=lookup.text_map(q,e))];return b['candidate'],profile,items,spec['contract']
 def test_marker_free_source_audit_does_not_change_profile_or_plan(self):
  raw,profile,items,c=self.candidate()
  with tempfile.TemporaryDirectory()as d:
   ws=Path(d);(ws/'source.dpa').write_bytes(raw);s=Service(ws);s.open_project('source.dpa',sha(raw),profile,sha(canonical(profile)));before=canonical(s.current_profile);result=s.validate_bindings(sha(raw),c,sha(canonical(c)),True,items,sha(canonical(items)));self.assertEqual(result['status'],'PASS');self.assertFalse(result['profile_mutated']);self.assertEqual(canonical(s.current_profile),before);self.assertFalse(s.plans);self.assertEqual(result['rows'][0]['lookup']['provenance'],'SOURCE_EXPECTATION_MATCH');self.assertEqual((ws/'source.dpa').read_bytes(),raw)
 def test_source_audit_digest_owner_text_duplicates_and_station_refuse(self):
  raw,profile,items,c=self.candidate();q=Project(raw);e=q.element(1,13)
  with tempfile.TemporaryDirectory()as d:
   ws=Path(d);(ws/'source.dpa').write_bytes(raw);s=Service(ws);s.open_project('source.dpa',sha(raw),profile,sha(canonical(profile)));self.base.refused('LOOKUP_EXPECTATION_HASH',lambda:s.validate_bindings(sha(raw),c,sha(canonical(c)),True,items,'0'*64))
   for mode,code in [('owner','LOOKUP_OWNER_HASH'),('text','LOOKUP_UNKNOWN_TEXT'),('duplicate','LOOKUP_EXPECTATION_DUPLICATE')]:
    changed=copy.deepcopy(items)
    if mode=='owner':changed[0]['expected_element_sha256']='0'*64
    if mode=='text':changed[0]['states'][103]['texts'][0]='Wrong code'
    if mode=='duplicate':changed.append(copy.deepcopy(changed[0]))
    self.base.refused(code,lambda:s.validate_bindings(sha(raw),c,sha(canonical(c)),True,changed,sha(canonical(changed))))
   wrong=copy.deepcopy(profile);wrong['station']+=1;self.base.refused('LOOKUP_BINDING',lambda:lookup.source_expectation(q,e,items[0],c['tags'][0],wrong))
 def test_no_fake_contract_enum_expansion_for_holes(self):
  s=self.spec();b=self.base.build(s);q=Project(b['candidate']);m=b['profile']['state_lookups'][0];tag=copy.deepcopy(s['contract']['tags'][0]);tag['enum']=list(range(123));self.base.refused('LOOKUP_ENUM',lambda:lookup.readback(q,q.element(1,13),m,tag))

if __name__=='__main__':unittest.main()
