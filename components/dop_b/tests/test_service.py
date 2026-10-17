"""Integration tests exercise source protection and actual decoded candidates."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import runpy

from universal_hmi.errors import HmiError
from universal_hmi.service import FileService, byte_hash as service_byte_hash
from test_native import synthetic_file, _wide, macro_fixture, macro_profile, preserved_layout_fixture, qualify_preserved_layout
from universal_hmi.native import NativeAdapter, canonical_model_id, _groups
from universal_hmi.model import canonical_hash
from universal_hmi.native.codec import Envelope
from test_resources import alarm_public_fixture
from test_native import control_generation_fixture
from test_program import blank_program_fixture
from universal_hmi.native.resources import ResourceTables, alarm_view_context

ROOT = Path(__file__).resolve().parents[1]


class ExistingEntryPermissionServiceTests(unittest.TestCase):
    """Classified stored entry gate, with independent complete-body expectations."""
    def setUp(self):
        from test_existing_entry_permission import entry_permission_fixture
        from test_existing_edit import page_png
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source,_,_,namespace,actions=entry_permission_fixture()
        (self.root/'source.dps').write_bytes(self.source)
        (self.root/'namespace.json').write_bytes(namespace)
        (self.root/'actions.json').write_bytes(actions)
        self.actions=json.loads(actions)['actions']
        self.authority_dir=self.root/'authorities';self.authority_dir.mkdir()
        for name in ('inert_literals','presentation','background','integer_numeric','entry_permission'):
            filename='dopsoft2_b10_'+name+'.json'
            (self.authority_dir/filename).write_bytes((ROOT/'profiles/existing_contracts'/filename).read_bytes())
        patcher=patch.object(FileService,'_existing_authority_dir',return_value=self.authority_dir)
        patcher.start();self.addCleanup(patcher.stop)
        self.helper=runpy.run_path(str(ROOT/'scripts/qualify_existing_edit.py'))['qualify']
        result=self.qualify('qualified')
        self.assertEqual(result['native_output'],'NOT_CREATED')
        self.profile_dir=self.root/'qualified/profiles'
        self.profile_path=self.profile_dir/'existing_edit_permission_v1.json'
        self.service=FileService(self.root,self.profile_dir)
        self.sid=self.service.open_project('existing_edit_permission_v1','source.dps')['session_id']
        self.design=json.loads((self.root/'qualified/design.json').read_bytes())
        self.inventory=json.loads((self.root/'qualified/source_inventory.json').read_bytes())
        (self.root/'background.png').write_bytes(page_png())

    def qualify(self,directory,**changes):
        args=dict(integer_numeric=True,entry_permission=True,
                  permission_namespace='namespace.json',action_contract='actions.json')
        args.update(changes)
        return self.helper(self.root,'source.dps',directory,'ORIGINAL NEUTRAL TEST SOURCE',
                           'STATIC CONTRACT TEST; NO VENDOR OR HUMAN MACHINE ACCEPTANCE',**args)

    def owner(self,design,sid,eid):
        return next(e for s in design['screens'] if s['native_id']==sid
                    for e in s['elements'] if e['native_id']==eid)

    def permission(self,design,sid,eid,level=1):
        action=next(a for a in self.actions if a['screen_id']==sid and a['element_id']==eid)
        # Independent action-entry pin implementation rather than native helper.
        digest=service_byte_hash(json.dumps(action,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        owner=self.owner(design,sid,eid)
        owner.update(kind='native_entry_permission',presentation={},entry_permission=dict(
            permission_address='{Link2}0@X7',enable_level=level,action_classification_sha256=digest))
        return owner

    def changed(self):
        design=deepcopy(self.design)
        button=self.permission(design,'12','61')
        state=next(o for o in self.inventory['owners'] if o['element_id']=='61')['states'][0]
        button['presentation']=dict(visual={'native_style':0},states=[{**state,'font_color':0}])
        for sid,eid,typ,low,high,level in [('7','34','INT',-999,999,0),('12','137','UINT',0,500,1)]:
            owner=self.permission(design,sid,eid,level)
            owner.update(kind='native_integer_numeric',integer_numeric=dict(data_type=typ,
                value_model='integer_fixed_decimal',integer_digits=3,fractional_digits=0,
                raw_minimum=low,raw_maximum=high))
        first=design['screens'][0];first['elements']=[e for e in first['elements'] if e['native_id']!='11']
        frame=next(b for b in self.inventory['backgrounds'] if b['screen_id']=='1')
        first['native_background']=dict(frame_sha256=frame['frame_sha256'],asset_path='background.png',
            asset_sha256=service_byte_hash((self.root/'background.png').read_bytes()))
        return design

    def plan(self,design=None,operations=None,key='permission'):
        return self.service.plan_changes(self.sid,self.changed() if design is None else design,operations,key)

    def approve(self,plan):
        payload={k:v for k,v in plan.items() if k.endswith('_sha256')}
        payload.update(approved=True,authority='direct_human',human_reference='TEST APPROVAL MOCK ONLY')
        (self.root/'approval.json').write_text(json.dumps(payload),encoding='utf-8')
        return 'approval.json'

    def expected_body(self):
        # Reconstruct original sections/records directly, never call an emitter,
        # existing-edit oracle or permission/numeric primitive implementation.
        original=NativeAdapter(self.source,'delta_dopsoft2');pages=_groups(original.document)
        dead=next(o for o in pages[0]['elements'] if o['id']=='11')
        values={};state_values={}
        for page in pages:
            for owner in page['elements']:
                if owner['id'] in {'61','34','137'}:
                    eid=owner['id'];changes={'InterLockVar':b'{Link2}0@X7','InterLockLevel':b'0' if eid=='34' else b'1'}
                    if eid=='61':
                        changes['Style']=b'0';state_values[id(owner['states'][0])]={'FontColor':b'0'}
                    else:
                        changes.update(IntNum=b'3',DotNum=b'0',MinValue=b'-999' if eid=='34' else b'0',
                                       MaxValue=b'999' if eid=='34' else b'500')
                        from decimal import Decimal
                        for field in ('MinValue','MaxValue'):
                            if Decimal(owner['section'].one(field).value.decode())==Decimal(changes[field].decode()):
                                changes[field]=owner['section'].one(field).value
                    values[id(owner['section'])]=changes
        values.update(state_values);chunks=[]
        for i,section in enumerate(original.document.sections):
            if dead['start']<=i<dead['end']:continue
            chunks.append(section.header)
            for record in section.records:
                value=values.get(id(section),{}).get(record.key)
                chunks.append(record.raw if value is None else record.key.encode()+b'='+value+b'\r\n')
        tail=original.document.tail;at=tail.index(b'[Background]\r\nSize=')
        start=tail.index(b'\r\n',at+len(b'[Background]\r\n'))+2
        pixels=b''.join((b'\xff\0\0\xff' if y<48 else b'\0\0\xff\xff')*128 for y in range(96))
        header=__import__('struct').pack('<IiiHHIIiiII',40,128,96,1,32,0,128*96*4,0,0,0,0)
        return b''.join(chunks)+tail[:start]+header+pixels+tail[start+40+128*96*4:]

    def test_all_five_edit_categories_saved_body_original_bindings_and_replay(self):
        plan=self.plan()
        self.assertEqual(sum(o['op']=='set_existing_entry_permission' for o in plan['operations']),3)
        self.assertFalse(self.service.validate(self.sid,plan['plan_id'])['findings'])
        preview=self.service.preview(self.sid,plan['plan_id'])
        self.assertIn('UNKNOWN',preview['html']);self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
        result=self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        self.assertEqual(result['scope'],'SOURCE_PINNED_EXISTING_ENTRY_PERMISSION_STORED_ONLY')
        self.service.save_as(self.sid,'permission.dps')
        raw=(self.root/'permission.dps').read_bytes();candidate=NativeAdapter(raw,'delta_dopsoft2')
        self.assertEqual(candidate.envelope.body,self.expected_body())
        original=NativeAdapter(self.source,'delta_dopsoft2')
        self.assertEqual(candidate.envelope.prefix,original.envelope.prefix_for_body(self.expected_body()))
        self.assertEqual(candidate.envelope.thumbnail,original.envelope.thumbnail)
        # Textual Link2 deliberately differs from native link=1; no numeric link inference.
        for page in _groups(candidate.document):
            for owner in page['elements']:
                if owner['id'] in {'61','34','137'}:
                    self.assertEqual(owner['section'].one('InterLockLink').value,b'1')
        sid=self.service.open_project('existing_edit_permission_v1','source.dps')['session_id']
        replay=self.service.plan_changes(sid,self.changed(),None,'replay')
        self.assertEqual(replay['plan_id'],plan['plan_id'])
        self.service.apply_plan(sid,replay['plan_id'],'approval.json');self.service.save_as(sid,'replay.dps')
        self.assertEqual((self.root/'replay.dps').read_bytes(),raw)
        self.assertEqual((self.root/'source.dps').read_bytes(),self.source)

    def test_no_intent_is_complete_byte_noop_even_with_permission_profile(self):
        plan=self.plan(self.design);self.assertEqual(plan['operations'],[])
        self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan));self.service.save_as(self.sid,'noop.dps')
        self.assertEqual((self.root/'noop.dps').read_bytes(),self.source)

    def test_permission_radix_type_direction_station_and_link_are_not_guessed(self):
        for address in ('{Link2}0@X8','{Link2}0@D1','{Link2}1@X7','{Link1}0@X7','{Link2}0@X1000'):
            design=self.changed();self.owner(design,'12','61')['entry_permission']['permission_address']=address
            with self.subTest(address=address),self.assertRaises(HmiError):self.plan(design,key=address)

    def test_action_pin_role_and_owned_write_binding_must_match_original(self):
        for field,value in [('action_class','stop_request'),('write_address','{Link2}0@M1'),('mem_fmt',0)]:
            original=(self.root/'actions.json').read_bytes();contract=json.loads(original)
            contract['actions'][0][field]=value
            (self.root/'actions.json').write_text(json.dumps(contract),encoding='utf-8')
            with self.subTest(field=field),self.assertRaises(HmiError):self.qualify('forged-'+field)
            self.assertFalse((self.root/('forged-'+field)).exists())
            (self.root/'actions.json').write_bytes(original)
        for key,value in [('action_classification_sha256','0'*64),('enable_level',True)]:
            design=self.changed();self.owner(design,'12','61')['entry_permission'][key]=value
            with self.subTest(field=key),self.assertRaises(HmiError):self.plan(design,key=key)

    def test_both_project_raw_contracts_are_fresh_at_all_transaction_phases(self):
        plan=self.plan();approval=self.approve(plan);self.service.apply_plan(self.sid,plan['plan_id'],approval)
        for name in ('namespace.json','actions.json'):
            path=self.root/name;original=path.read_bytes();path.write_bytes(original+b' ')
            for action in (lambda:self.plan(key='permission'),lambda:self.service.validate(self.sid,plan['plan_id']),
                    lambda:self.service.preview(self.sid,plan['plan_id']),lambda:self.service.apply_plan(self.sid,plan['plan_id'],approval),
                    lambda:self.service.save_as(self.sid,'drift.dps')):
                with self.subTest(name=name),self.assertRaises(HmiError):action()
            path.write_bytes(original)
        self.assertFalse((self.root/'drift.dps').exists())

    def test_after_link_raw_contract_race_removes_candidate_and_temporary_file(self):
        plan=self.plan();self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        path=self.root/'actions.json';original=path.read_bytes();link=os.link
        def race(src,dst,*args,**kwargs):
            result=link(src,dst,*args,**kwargs);path.write_bytes(original+b' ');return result
        with patch('universal_hmi.service.os.link',race),self.assertRaises(HmiError):self.service.save_as(self.sid,'raced.dps')
        self.assertFalse((self.root/'raced.dps').exists());self.assertEqual(list(self.root.glob('.uhmi-*')),[])

    def test_static_permission_and_driver_books_cannot_be_promoted_by_rehashing(self):
        path=self.authority_dir/'dopsoft2_b10_entry_permission.json';original=path.read_bytes()
        book=json.loads(original);book['runtime']='OFFLINE_PASS';path.write_text(json.dumps(book),encoding='utf-8')
        with self.assertRaises(HmiError):self.qualify('forged-book')
        self.assertFalse((self.root/'forged-book').exists());path.write_bytes(original)
        namespace=json.loads((self.root/'namespace.json').read_bytes())
        namespace['regions']['BOOL'][0]['maximum']=65535
        (self.root/'namespace.json').write_text(json.dumps(namespace),encoding='utf-8')
        with self.assertRaises(HmiError):self.qualify('forged-range')
        self.assertFalse((self.root/'forged-range').exists())

    def test_emitter_permission_link_binding_and_numeric_corruption_are_independently_refused(self):
        plan=self.plan();emit=self.service._emit
        for field,value in [('InterLockVar',b'{Link2}0@X6'),('InterLockLevel',b'0'),('InterLockLink',b'2'),
                ('WriteVar',b'{Link2}0@M1'),('MemFmt',b'0')]:
            def tamper(session,ops,design=None):
                candidate=NativeAdapter(emit(session,ops,design),'delta_dopsoft2')
                owner=next(o for p in _groups(candidate.document) for o in p['elements'] if o['id']=='61')
                owner['section'].one(field).set_value(value)
                return candidate.envelope.encode(candidate.document.bytes())
            with self.subTest(field=field),patch.object(self.service,'_emit',tamper):
                result=self.service.validate(self.sid,plan['plan_id'])
                self.assertEqual(result['findings'][0]['code'],'NATIVE_CANDIDATE_MISMATCH')

    def test_changed_permission_level_cannot_reuse_approval_or_partial_operation_list(self):
        plan=self.plan();approval=self.approve(plan);design=self.changed()
        self.owner(design,'12','61')['entry_permission']['enable_level']=0
        alternate=self.plan(design,key='level0')
        with self.assertRaises(HmiError):self.service.apply_plan(self.sid,alternate['plan_id'],approval)
        partial=self.plan(operations=plan['operations'][:-1],key='partial')
        self.assertEqual(self.service.validate(self.sid,partial['plan_id'])['findings'][0]['code'],'NATIVE_CANDIDATE_SCOPE')

    def test_helper_requires_explicit_inputs_and_original_namespace(self):
        for options in ({'permission_namespace':None},{'action_contract':None},{'entry_permission':False},
                {'permission_namespace':'../namespace.json'},{'entry_permission':1}):
            with self.subTest(options=options),self.assertRaises(HmiError):self.qualify('bad',**options)
        self.assertFalse((self.root/'bad').exists())


class ExistingIntegerNumericServiceTests(unittest.TestCase):
    """Original neutral source configuration, never vendor/runtime acceptance."""
    def setUp(self):
        from test_existing_edit import existing_edit_fixture,page_png
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        raw,*_=existing_edit_fixture();original=NativeAdapter(raw,'delta_dopsoft2')
        for page in _groups(original.document):
            for owner in page['elements']:
                if owner['id']=='31':owner['section'].one('IntNum').set_value(b'4')
                if owner['id']=='34':
                    for key,value in {'DotNum':b'0','IntNum':b'5','MinValue':b'0.000000','MaxValue':b'100.000000'}.items():
                        owner['section'].one(key).set_value(value)
        self.source=original.envelope.encode(original.document.bytes())
        (self.root/'source.dps').write_bytes(self.source)
        self.authority_dir=self.root/'authorities';self.authority_dir.mkdir()
        for name in ('inert_literals','presentation','background','integer_numeric'):
            filename='dopsoft2_b10_'+name+'.json'
            (self.authority_dir/filename).write_bytes((ROOT/'profiles/existing_contracts'/filename).read_bytes())
        patcher=patch.object(FileService,'_existing_authority_dir',return_value=self.authority_dir)
        patcher.start();self.addCleanup(patcher.stop)
        self.helper=runpy.run_path(str(ROOT/'scripts/qualify_existing_edit.py'))['qualify']
        result=self.helper(self.root,'source.dps','qualified','ORIGINAL NEUTRAL TEST SOURCE',
                           'INDEPENDENT STATIC CONTRACT TEST',integer_numeric=True)
        self.assertEqual(result['native_output'],'NOT_CREATED')
        self.profile_dir=self.root/'qualified/profiles'
        self.profile_path=self.profile_dir/'existing_edit_numeric_v1.json'
        self.service=FileService(self.root,self.profile_dir)
        self.sid=self.service.open_project('existing_edit_numeric_v1','source.dps')['session_id']
        self.design=json.loads((self.root/'qualified/design.json').read_bytes())
        self.inventory=json.loads((self.root/'qualified/source_inventory.json').read_bytes())
        (self.root/'background.png').write_bytes(page_png())

    def numeric(self,design,sid,eid,**settings):
        screen=next(s for s in design['screens'] if s['native_id']==sid)
        owner=next(e for e in screen['elements'] if e['native_id']==eid)
        values=dict(data_type='INT',value_model='integer_fixed_decimal',integer_digits=1,fractional_digits=4)
        values.update(settings)
        owner.update(kind='native_integer_numeric',presentation={},integer_numeric=values)
        return owner

    def changed(self):
        design=deepcopy(self.design)
        display=self.numeric(design,'1','31')
        state=next(o for o in self.inventory['owners'] if o['element_id']=='31')['states'][0]
        display.update(x=80,y=45,width=44,height=22,presentation=dict(visual={'native_style':0},
            states=[{**state,'font_color':0,'surface_color':0xFFFFFF}]))
        self.numeric(design,'7','34',integer_digits=5,fractional_digits=0,raw_minimum=-32768,raw_maximum=32767)
        first=design['screens'][0];first['elements']=[e for e in first['elements'] if e['native_id']!='11']
        frame=next(b for b in self.inventory['backgrounds'] if b['screen_id']=='1')
        first['native_background']=dict(frame_sha256=frame['frame_sha256'],asset_path='background.png',
            asset_sha256=service_byte_hash((self.root/'background.png').read_bytes()))
        return design

    def plan(self,design=None,operations=None,key='numeric'):
        return self.service.plan_changes(self.sid,self.changed() if design is None else design,operations,key)

    def approve(self,plan):
        payload={k:v for k,v in plan.items() if k.endswith('_sha256')}
        payload.update(approved=True,authority='direct_human',human_reference='ORIGINAL TEST APPROVAL MOCK ONLY')
        (self.root/'approval.json').write_text(json.dumps(payload),encoding='utf-8')
        return 'approval.json'

    def expected_body(self):
        # Direct original record reconstruction; no primitive/oracle implementation calls.
        source=NativeAdapter(self.source,'delta_dopsoft2');sections=source.document.sections
        pages=_groups(source.document);dead=next(o for o in pages[0]['elements'] if o['id']=='11')
        wanted={}
        for page in pages:
            for owner in page['elements']:
                if owner['id']=='31':
                    wanted[id(owner['section'])]={'IntNum':b'1','DotNum':b'4','X':b'80','Y':b'45',
                        'Width':b'44','Height':b'22','Style':b'0'}
                    wanted[id(owner['states'][0])]={'FontColor':b'0','BgColor':b'16777215'}
                if owner['id']=='34':wanted[id(owner['section'])]={'IntNum':b'5','DotNum':b'0',
                    'MinValue':b'-32768','MaxValue':b'32767'}
        chunks=[]
        for index,section in enumerate(sections):
            if dead['start']<=index<dead['end']:continue
            chunks.append(section.header)
            for record in section.records:
                replacement=wanted.get(id(section),{}).get(record.key)
                chunks.append(record.raw if replacement is None else record.key.encode()+b'='+replacement+b'\r\n')
        tail=source.document.tail;at=tail.index(b'[Background]\r\nSize=')
        start=tail.index(b'\r\n',at+len(b'[Background]\r\n'))+2
        pixels=b''.join((b'\xff\0\0\xff' if y<48 else b'\0\0\xff\xff')*128 for y in range(96))
        header=__import__('struct').pack('<IiiHHIIiiII',40,128,96,1,32,0,128*96*4,0,0,0,0)
        return b''.join(chunks)+tail[:start]+header+pixels+tail[start+40+128*96*4:]

    def test_mixed_numeric_presentation_background_full_body_and_fresh_replay(self):
        plan=self.plan();self.assertEqual([o['op'] for o in plan['operations']],
            ['delete_literal','configure_existing_integer_numeric','set_existing_presentation',
             'set_existing_background','configure_existing_integer_numeric'])
        self.assertFalse(self.service.validate(self.sid,plan['plan_id'])['findings'])
        preview=self.service.preview(self.sid,plan['plan_id'])
        self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN');self.assertIn('UNKNOWN',preview['html'])
        applied=self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        self.assertEqual(applied['scope'],'SOURCE_PINNED_EXISTING_WORD_NUMERIC_PRESENTATION_BACKGROUND')
        saved=self.service.save_as(self.sid,'numeric.dps')
        candidate=NativeAdapter((self.root/'numeric.dps').read_bytes(),'delta_dopsoft2')
        self.assertEqual(candidate.envelope.body,self.expected_body())
        original=NativeAdapter(self.source,'delta_dopsoft2')
        self.assertEqual(candidate.envelope.thumbnail,original.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix,original.envelope.prefix_for_body(self.expected_body()))
        self.assertEqual(saved['sha256'],self.service.diff(self.sid)['candidate_sha256'])
        self.assertEqual((self.root/'source.dps').read_bytes(),self.source)
        sid=self.service.open_project('existing_edit_numeric_v1','source.dps')['session_id']
        replay=self.service.plan_changes(sid,self.changed(),None,'replay')
        self.assertEqual(replay['plan_id'],plan['plan_id'])
        self.service.apply_plan(sid,replay['plan_id'],'approval.json');self.service.save_as(sid,'numeric-replay.dps')
        self.assertEqual((self.root/'numeric-replay.dps').read_bytes(),(self.root/'numeric.dps').read_bytes())

    def test_original_and_explicit_numeric_noop_preserve_complete_file_and_limit_spelling(self):
        for explicit in (False,True):
            design=deepcopy(self.design)
            if explicit:
                self.numeric(design,'1','31',integer_digits=4,fractional_digits=1)
                self.numeric(design,'7','34',integer_digits=5,fractional_digits=0,raw_minimum=0,raw_maximum=100)
            plan=self.plan(design,key=str(explicit))
            self.assertFalse(self.service.validate(self.sid,plan['plan_id'])['findings'])
            self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
            path='noop-'+str(explicit)+'.dps';self.service.save_as(self.sid,path)
            self.assertEqual((self.root/path).read_bytes(),self.source)

    def test_existing_storage_and_fractional_input_cannot_be_reinterpreted(self):
        for settings in ({'data_type':'UINT'},{'integer_digits':2,'fractional_digits':3},
                {'integer_digits':4,'fractional_digits':1,'raw_minimum':0,'raw_maximum':100},
                {'integer_digits':5,'fractional_digits':0,'raw_minimum':0,'raw_maximum':0}):
            design=deepcopy(self.design);self.numeric(design,'7','34',**settings)
            with self.subTest(settings=settings),self.assertRaises(HmiError):self.plan(design,key=str(settings))
        (self.root/'source.dps').write_bytes(self.source+b'changed')
        with self.assertRaises(HmiError):self.plan()
        self.assertFalse((self.root/'numeric.dps').exists())

    def test_registry_freshness_covers_repeat_validation_preview_apply_and_after_link_save(self):
        design=self.changed();plan=self.plan(design);approval=self.approve(plan)
        self.service.apply_plan(self.sid,plan['plan_id'],approval)
        book=self.authority_dir/'dopsoft2_b10_integer_numeric.json';original=book.read_bytes()
        book.write_bytes(original+b' ')
        for action in (lambda:self.plan(design,key='numeric'),lambda:self.service.validate(self.sid,plan['plan_id']),
                lambda:self.service.preview(self.sid,plan['plan_id']),lambda:self.service.apply_plan(self.sid,plan['plan_id'],approval),
                lambda:self.service.save_as(self.sid,'drift.dps')):
            with self.assertRaises(HmiError):action()
        book.write_bytes(original);original_link=os.link
        def race(src,dst,*args,**kwargs):
            result=original_link(src,dst,*args,**kwargs);book.write_bytes(original+b' ');return result
        with patch('universal_hmi.service.os.link',race),self.assertRaises(HmiError):self.service.save_as(self.sid,'raced.dps')
        self.assertFalse((self.root/'raced.dps').exists());self.assertEqual(list(self.root.glob('.uhmi-*')),[])

    def test_registered_facts_cannot_be_forged_even_with_new_descriptor_hash(self):
        book=self.authority_dir/'dopsoft2_b10_integer_numeric.json'
        facts=json.loads(book.read_bytes());facts['fractional_input']='OFFLINE_PASS'
        book.write_text(json.dumps(facts),encoding='utf-8')
        with self.assertRaises(HmiError) as caught:
            self.helper(self.root,'source.dps','forged','TEST SOURCE','TEST REVIEW',integer_numeric=True)
        self.assertEqual(caught.exception.code,'EXISTING_EDIT_AUTHORITY')
        self.assertFalse((self.root/'forged').exists())

    def test_independent_expected_body_rejects_emitter_numeric_and_binding_tampering(self):
        plan=self.plan();emit=self.service._emit
        for before,after in ((b'MemFmt=1\r\n',b'MemFmt=2\r\n'),(b'DotNum=4\r\n',b'DotNum=1\r\n'),
                (b'MinValue=-32768\r\n',b'MinValue=-32767\r\n')):
            def tamper(session,ops,design=None):
                candidate=NativeAdapter(emit(session,ops,design),'delta_dopsoft2')
                self.assertIn(before,candidate.envelope.body)
                return candidate.envelope.encode(candidate.envelope.body.replace(before,after,1))
            with self.subTest(before=before),patch.object(self.service,'_emit',tamper):
                result=self.service.validate(self.sid,plan['plan_id'])
                self.assertEqual(result['findings'][0]['code'],'NATIVE_CANDIDATE_MISMATCH')

    def test_explicit_ops_and_changed_numeric_settings_cannot_reuse_approval(self):
        plan=self.plan();approval=self.approve(plan)
        alternate=self.changed();next(e for e in alternate['screens'][0]['elements'] if e['native_id']=='31')['integer_numeric'].update(
            integer_digits=4,fractional_digits=1)
        changed=self.plan(alternate,key='alternate')
        with self.assertRaises(HmiError):self.service.apply_plan(self.sid,changed['plan_id'],approval)
        supplied=self.plan(operations=plan['operations'][:-1],key='partial')
        self.assertEqual(self.service.validate(self.sid,supplied['plan_id'])['findings'][0]['code'],'NATIVE_CANDIDATE_SCOPE')

    def test_capability_claim_without_numeric_descriptor_cannot_configure_numeric(self):
        profile=json.loads(self.profile_path.read_bytes());del profile['native_schema']['existing_integer_numeric']
        # A changed profile/witness is not an authority substitute.
        self.profile_path.write_text(json.dumps(profile),encoding='utf-8')
        with self.assertRaises(HmiError):FileService(self.root,self.profile_dir).open_project('existing_edit_numeric_v1','source.dps')


class ExistingEditServiceTests(unittest.TestCase):
    """Neutral original byte source; modeled approval only, no vendor claims."""
    def setUp(self):
        from test_existing_edit import existing_edit_fixture,page_png
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source,*_=existing_edit_fixture()
        (self.root/'source.dps').write_bytes(self.source)
        self.authority_dir=self.root/'authorities';self.authority_dir.mkdir()
        for name in ('inert_literals','presentation','background'):
            filename='dopsoft2_b10_'+name+'.json'
            (self.authority_dir/filename).write_bytes((ROOT/'profiles/existing_contracts'/filename).read_bytes())
        patcher=patch.object(FileService,'_existing_authority_dir',return_value=self.authority_dir)
        patcher.start();self.addCleanup(patcher.stop)
        self.helper=runpy.run_path(str(ROOT/'scripts/qualify_existing_edit.py'))['qualify']
        result=self.helper(self.root,'source.dps','qualified','ORIGINAL NEUTRAL TEST SOURCE','INDEPENDENT TEST CONTRACT')
        self.assertEqual(result['native_output'],'NOT_CREATED')
        self.profile_dir=self.root/'qualified/profiles'
        self.profile_path=self.profile_dir/'existing_edit_v1.json'
        self.service=FileService(self.root,self.profile_dir)
        self.sid=self.service.open_project('existing_edit_v1','source.dps')['session_id']
        self.design=json.loads((self.root/'qualified/design.json').read_bytes())
        self.inventory=json.loads((self.root/'qualified/source_inventory.json').read_bytes())
        (self.root/'background.png').write_bytes(page_png())

    def changed(self):
        design=deepcopy(self.design);first=design['screens'][0]
        first['elements']=[e for e in first['elements'] if e['native_id']!='11']
        owner=next(e for e in first['elements'] if e['native_id']=='21')
        state=next(o for o in self.inventory['owners'] if o['element_id']=='21')['states'][0]
        owner.update(kind='native_presentation',x=100,y=2,width=20,height=22,presentation=dict(visual={'native_style':0},
            states=[{**state,'font_size':24,'font_ratio':150,'font_color':0xFFFFFF,'surface_color':1}]))
        frame=next(b for b in self.inventory['backgrounds'] if b['screen_id']=='1')
        first['native_background']=dict(frame_sha256=frame['frame_sha256'],asset_path='background.png',
            asset_sha256=service_byte_hash((self.root/'background.png').read_bytes()))
        return design

    def plan(self,design=None,operations=None,key='edit'):
        return self.service.plan_changes(self.sid,self.changed() if design is None else design,operations,key)

    def approve(self,plan):
        payload={k:v for k,v in plan.items() if k.endswith('_sha256')}
        payload.update(approved=True,authority='direct_human',human_reference='ORIGINAL TEST APPROVAL MOCK ONLY')
        (self.root/'approval.json').write_text(json.dumps(payload),encoding='utf-8')
        return 'approval.json'

    def test_mixed_full_lifecycle_independent_candidate_restoration_and_replay(self):
        plan=self.plan();self.assertEqual([o['op'] for o in plan['operations']],['delete_literal','set_existing_presentation','set_existing_background'])
        self.assertFalse(self.service.validate(self.sid,plan['plan_id'])['findings'])
        preview=self.service.preview(self.sid,plan['plan_id'])
        self.assertIn('data-native-background="requested-opaque-png-only"',preview['html'])
        self.assertIn('BACKGROUND ONLY',preview['html']);self.assertIn('NATIVE CONTROLS NOT RENDERED',preview['html'])
        self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
        self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        saved=self.service.save_as(self.sid,'candidate.dps')
        candidate=NativeAdapter((self.root/'candidate.dps').read_bytes(),'delta_dopsoft2')
        source=NativeAdapter(self.source,'delta_dopsoft2')
        self.assertEqual(saved['sha256'],self.service.diff(self.sid)['candidate_sha256'])
        # Independent exact original record map, no emitter expected_body/spans.
        old_pages=_groups(source.document);old=next(o for o in old_pages[0]['elements'] if o['id']=='21')
        dead=next(o for o in old_pages[0]['elements'] if o['id']=='11')
        wanted={('Element','X'):b'100',('Element','Y'):b'2',('Element','Width'):b'20',('Element','Height'):b'22',('Element','Style'):b'0',
            ('State','FontSize0'):b'24',('State','FontRatio0'):b'150',('State','FontColor'):b'16777215',('State','FgColor'):b'1'}
        chunks=[]
        for i,section in enumerate(source.document.sections):
            if dead['start']<=i<dead['end']:continue
            chunks.append(section.header)
            for record in section.records:
                value=wanted.get((section.name,record.key)) if i==old['start'] or section is old['states'][0] else None
                chunks.append(record.raw if value is None else record.key.encode()+b'='+value+b'\r\n')
        tail=source.document.tail
        frame=self.inventory['backgrounds'][0]
        # Construct the actual expected bottom-up BGRFF rows directly from known RGB rows.
        pixels=b''.join((b'\xff\0\0\xff' if y<48 else b'\0\0\xff\xff')*128 for y in range(96))
        header=__import__('struct').pack('<IiiHHIIiiII',40,128,96,1,32,0,128*96*4,0,0,0,0)
        at=tail.index(b'[Background]\r\nSize=')
        start=tail.index(b'\r\n',at+len(b'[Background]\r\n'))+2
        self.assertEqual(service_byte_hash(tail[start:start+40+128*96*4]),frame['frame_sha256'])
        expected_tail=tail[:start]+header+pixels+tail[start+40+128*96*4:]
        self.assertEqual(candidate.envelope.body,b''.join(chunks)+expected_tail)
        self.assertEqual(candidate.envelope.thumbnail,source.envelope.thumbnail)
        self.assertEqual((self.root/'source.dps').read_bytes(),self.source)
        reopened=self.service.open_project('existing_edit_v1','source.dps')['session_id']
        replay=self.service.plan_changes(reopened,self.changed(),None,'replay')
        self.assertEqual(replay['plan_id'],plan['plan_id'])
        self.service.apply_plan(reopened,replay['plan_id'],'approval.json');self.service.save_as(reopened,'replay.dps')
        self.assertEqual((self.root/'candidate.dps').read_bytes(),(self.root/'replay.dps').read_bytes())

    def test_exact_noop_and_geometry_only_variant(self):
        plan=self.plan(self.design);self.assertEqual(plan['operations'],[])
        self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan));self.service.save_as(self.sid,'noop.dps')
        self.assertEqual((self.root/'noop.dps').read_bytes(),self.source)
        design=deepcopy(self.design);e=next(e for e in design['screens'][0]['elements'] if e['native_id']=='21')
        e.update(kind='native_presentation',x=90,presentation={})
        plan=self.plan(design,key='geometry');self.assertEqual(set(plan['operations'][0]),{'op','screen_id','element_id','owner_sha256','geometry'})
        self.assertFalse(self.service.validate(self.sid,plan['plan_id'])['findings'])

    def test_asset_changes_or_disappearance_block_every_phase_and_repeat(self):
        design=self.changed();plan=self.plan(design);approval=self.approve(plan)
        self.service.apply_plan(self.sid,plan['plan_id'],approval)
        asset=self.root/'background.png';raw=asset.read_bytes()
        for missing in (False,True):
            if missing:asset.unlink()
            else:asset.write_bytes(raw+b'junk')
            for phase,action in [('repeat_plan',lambda:self.plan(design,key='edit')),
                    ('preview',lambda:self.service.preview(self.sid,plan['plan_id'])),
                    ('save',lambda:self.service.save_as(self.sid,'changed.dps'))]:
                with self.subTest(missing=missing,phase=phase):
                    with self.assertRaises(HmiError) as caught:action()
                    self.assertEqual(caught.exception.code,'EXISTING_EDIT_ASSET')
            result=self.service.validate(self.sid,plan['plan_id'])
            self.assertFalse(result['offline_pass'])
            self.assertEqual(result['findings'][0]['code'],'EXISTING_EDIT_ASSET')
            with self.assertRaises(HmiError) as caught:self.service.apply_plan(self.sid,plan['plan_id'],approval)
            self.assertEqual(caught.exception.code,'VALIDATION')
            asset.write_bytes(raw)
        self.assertFalse((self.root/'changed.dps').exists())

    def test_atomic_save_rechecks_asset_after_link_and_removes_only_own_output(self):
        plan=self.plan();self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        original_link=os.link
        def race(src,dst,*args,**kwargs):
            result=original_link(src,dst,*args,**kwargs)
            (self.root/'background.png').write_bytes(b'changed after link')
            return result
        with patch('universal_hmi.service.os.link',race),self.assertRaises(HmiError):self.service.save_as(self.sid,'raced.dps')
        self.assertFalse((self.root/'raced.dps').exists());self.assertEqual(list(self.root.glob('.uhmi-*')),[])
        self.assertEqual((self.root/'source.dps').read_bytes(),self.source)

    def test_public_expected_bytes_reject_emitter_visual_or_unrelated_tampering(self):
        plan=self.plan();original_emit=self.service._emit
        def tamper(session,ops,design=None):
            data=original_emit(session,ops,design)
            native=NativeAdapter(data,'delta_dopsoft2')
            body=native.envelope.body.replace(b'FgColor=1\r\n',b'FgColor=2\r\n',1)
            return native.envelope.encode(body)
        with patch.object(self.service,'_emit',tamper):
            result=self.service.validate(self.sid,plan['plan_id'])
            self.assertEqual(result['findings'][0]['code'],'NATIVE_CANDIDATE_MISMATCH')

    def test_explicit_ops_cannot_hide_extra_changes_and_metadata_is_exact(self):
        auto=self.plan()
        for ops in ([],auto['operations'][:-1],auto['operations']+[auto['operations'][1]]):
            plan=self.plan(operations=ops,key=str(len(ops)))
            self.assertEqual(self.service.validate(self.sid,plan['plan_id'])['findings'][0]['code'],'NATIVE_CANDIDATE_SCOPE')
        for change in ('caption','binding','state_hash','owner_hash','kind','path','page_frame'):
            design=self.changed();owner=next(e for e in design['screens'][0]['elements'] if e['native_id']=='21')
            if change=='caption':owner['text']='Changed'
            elif change=='binding':owner['binding']={'write':'X0'}
            elif change=='state_hash':owner['presentation']['states'][0]['state_sha256']='0'*64
            elif change=='owner_hash':owner['source_owner_sha256']='0'*64
            elif change=='kind':owner['kind']='native_preserved'
            elif change=='path':design['screens'][0]['native_background']['asset_path']='../background.png'
            else:design['screens'][0]['native_background']['frame_sha256']=self.inventory['backgrounds'][1]['frame_sha256']
            with self.subTest(change=change),self.assertRaises(HmiError):self.plan(design,key=change)

    def test_authority_forgery_rehash_and_registry_freshness_do_not_open_capability(self):
        plan=self.plan()
        for name in ('presentation','background'):
            path=self.authority_dir/('dopsoft2_b10_'+name+'.json');raw=path.read_bytes()
            path.write_bytes(raw+b' ')
            with self.assertRaises(HmiError) as caught:self.service.validate(self.sid,plan['plan_id'])
            self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED');path.write_bytes(raw)
            book=json.loads(raw);book['model_id']=True
            path.write_text(json.dumps(book),encoding='utf-8')
            try:
                with self.assertRaises(HmiError):self.helper(self.root,'source.dps','forged-'+name,'TEST SOURCE','TEST REVIEW')
            finally:path.write_bytes(raw)

    def test_approval_rebind_and_original_retention_mode_remain_exact(self):
        auto=self.plan();approval=self.approve(auto)
        design=self.changed();design['screens'][0]['elements'][0]['presentation']={}
        changed=self.plan(design,key='rebind')
        with self.assertRaises(HmiError) as caught:self.service.apply_plan(self.sid,changed['plan_id'],approval)
        self.assertEqual(caught.exception.code,'STALE_APPROVAL')
        design=self.changed();e=next(e for e in design['screens'][0]['elements'] if e['native_id']=='21')
        e['kind']='native_preserved';e.pop('presentation')
        with self.assertRaises(HmiError) as caught:self.plan(design,key='old-retention')
        self.assertEqual(caught.exception.code,'NATIVE_PRESERVED_MISMATCH')

    def test_malformed_candidate_modes_are_typed_refusals_without_sessions(self):
        original=json.loads(self.profile_path.read_bytes())
        for mode in (None,False,0,[],{},['existing_edit'],{'mode':'existing_edit'}):
            with self.subTest(mode=mode):
                bad=deepcopy(original);bad['native_schema']['native_candidate']['mode']=mode
                self.profile_path.write_text(json.dumps(bad),encoding='utf-8')
                service=FileService(self.root,self.profile_dir)
                with self.assertRaises(HmiError) as caught:service.open_project('existing_edit_v1','source.dps')
                self.assertEqual(caught.exception.code,'NATIVE_CALIBRATION')
                self.assertEqual(service.sessions,{})
        self.profile_path.write_text(json.dumps(original),encoding='utf-8')


class ExistingProgramServiceTests(unittest.TestCase):
    """Original neutral byte fixtures; never a vendor or pixel claim."""
    def setUp(self):
        from test_existing_program import existing_program_fixture
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, _ = existing_program_fixture()
        (self.root / 'source.dps').write_bytes(self.source)
        self.authority_dir = self.root / 'authorities'; self.authority_dir.mkdir()
        self.authority = self.authority_dir / 'dopsoft2_b10_inert_literals.json'
        self.authority.write_bytes((ROOT / 'profiles/existing_contracts/dopsoft2_b10_inert_literals.json').read_bytes())
        mocked = patch.object(FileService, '_existing_authority_dir', return_value=self.authority_dir)
        mocked.start(); self.addCleanup(mocked.stop)
        self.helper = runpy.run_path(str(ROOT / 'scripts/calibrate_existing.py'))['calibrate']
        self.helper(self.root, 'source.dps', 'calibrated', 'ORIGINAL NEUTRAL BYTE FIXTURE', 'INDEPENDENT TEST CONTRACT')
        self.profile_dir = self.root / 'calibrated/profiles'
        self.profile_path = self.profile_dir / 'existing_program_v1.json'
        self.witness_path = self.root / 'calibrated/existing_calibration.json'
        self.service = FileService(self.root, self.profile_dir)
        self.sid = self.service.open_project('existing_program_v1', 'source.dps')['session_id']
        source = NativeAdapter(self.source, 'delta_dopsoft2')
        inventory = source.inspect()
        self.deleted = []
        self.design = dict(schema_version=1, project_id='original-inert-test', profile_id='existing_program_v1',
                           tags=[], macros=[], alarms=[], screens=[])
        profile = json.loads(self.profile_path.read_bytes())
        for page in inventory['screens']:
            elements = []
            for owner in page['elements']:
                if (owner['native_fields']['Type'], owner['native_fields']['SubType']) == ('10', '6'):
                    self.deleted.append((page['id'], owner['id']))
                    continue
                elements.append(dict(id='p'+page['id']+'e'+owner['id'], native_id=owner['id'], kind='native_preserved',
                    text='', source_owner_sha256=source.owner_extent_sha256(page['id'], owner['id']), **owner['geometry']))
            self.design['screens'].append(dict(id='page'+page['id'], native_id=page['id'], name=page['name'],
                width=profile['resolution'][0], height=profile['resolution'][1], elements=elements))

    def approve(self, receipt):
        # Test-only modeled human approval; no runtime/production assertion.
        payload = {k: receipt[k] for k in ('source_sha256', 'profile_sha256', 'design_sha256',
            'bindings_sha256', 'operations_sha256', 'calibration_sha256')}
        payload.update(approved=True, authority='direct_human', human_reference='ORIGINAL UNIT TEST APPROVAL MOCK')
        (self.root / 'approval.json').write_text(json.dumps(payload), encoding='utf-8')
        return 'approval.json'

    def plan(self, design=None, operations=None, key='inert'):
        return self.service.plan_changes(self.sid, self.design if design is None else design, operations, key)

    def test_automatic_plan_saved_body_subtraction_restoration_and_survivor_hashes(self):
        plan = self.plan(); self.assertGreaterEqual(len(self.deleted), 3)
        self.assertEqual([(p['screen_id'], p['element_id']) for p in plan['operations']], self.deleted)
        self.assertFalse(self.service.validate(self.sid, plan['plan_id'])['findings'])
        self.assertEqual(self.service.preview(self.sid, plan['plan_id'])['render_kind'], 'CONCEPTUAL_IR')
        approval = self.approve(plan)
        applied = self.service.apply_plan(self.sid, plan['plan_id'], approval)
        self.assertEqual(applied['scope'], 'SOURCE_PINNED_INERT_LITERAL_DELETION'); self.assertFalse(applied['program_writer_complete'])
        saved = self.service.save_as(self.sid, 'candidate.dps')
        candidate = NativeAdapter((self.root / 'candidate.dps').read_bytes(), 'delta_dopsoft2')
        source = NativeAdapter(self.source, 'delta_dopsoft2')
        offsets = [0]
        for section in source.document.sections: offsets.append(offsets[-1] + len(section.bytes()))
        ranges = []
        for page in _groups(source.document):
            for owner in page['elements']:
                if (page['id'], owner['id']) in self.deleted: ranges.append((offsets[owner['start']], offsets[owner['end']]))
        chunks = []; cursor = 0
        for start, end in sorted(ranges): chunks.append(source.envelope.body[cursor:start]); cursor = end
        chunks.append(source.envelope.body[cursor:]); self.assertEqual(candidate.envelope.body, b''.join(chunks))
        restored = []; cursor = removed = 0
        for start, end in sorted(ranges):
            stop = start - removed; restored.extend((candidate.envelope.body[cursor:stop], source.envelope.body[start:end]))
            cursor, removed = stop, removed + end - start
        restored.append(candidate.envelope.body[cursor:]); self.assertEqual(b''.join(restored), source.envelope.body)
        for page in candidate.inspect()['screens']:
            for owner in page['elements']: self.assertEqual(candidate.owner_extent_sha256(page['id'], owner['id']), source.owner_extent_sha256(page['id'], owner['id']))
        self.assertEqual(candidate.document.tail, source.document.tail)
        self.assertEqual((self.root / 'source.dps').read_bytes(), self.source)
        self.assertEqual(saved['sha256'], self.service.diff(self.sid)['candidate_sha256'])
        self.assertEqual(applied, self.service.apply_plan(self.sid, plan['plan_id'], approval))
        self.assertEqual(saved, self.service.save_as(self.sid, 'candidate.dps'))

    def test_noop_keeps_entire_source_file_byte_exact(self):
        source = NativeAdapter(self.source, 'delta_dopsoft2'); design = deepcopy(self.design)
        for screen, page in zip(design['screens'], source.inspect()['screens']):
            screen['elements'] = [dict(id='old'+owner['id'], native_id=owner['id'], kind='native_preserved', text='',
                source_owner_sha256=source.owner_extent_sha256(page['id'], owner['id']), **owner['geometry']) for owner in page['elements']]
        plan = self.plan(design); self.assertEqual(plan['operations'], [])
        self.service.apply_plan(self.sid, plan['plan_id'], self.approve(plan)); self.service.save_as(self.sid, 'noop.dps')
        self.assertEqual((self.root / 'noop.dps').read_bytes(), self.source)

    def test_omitting_live_owner_is_refused_before_plan_exists(self):
        design = deepcopy(self.design); next(s for s in design['screens'] if s['elements'])['elements'].pop()
        with self.assertRaises(HmiError) as caught: self.plan(design)
        self.assertEqual(caught.exception.code, 'NONINERT_LITERAL')

    def test_retained_owner_override_hash_geometry_order_and_missing_page_are_refused(self):
        for variant in ('hash', 'geometry', 'order', 'page', 'name', 'newowner'):
            design = deepcopy(self.design); screen = next(s for s in design['screens'] if len(s['elements']) >= 2)
            if variant == 'hash': screen['elements'][0]['source_owner_sha256'] = '0'*64
            elif variant == 'geometry': screen['elements'][0]['x'] += 1
            elif variant == 'order': screen['elements'].reverse()
            elif variant == 'page': design['screens'].pop()
            elif variant == 'name': screen['name'] = 'Other'
            else: screen['elements'].append({**screen['elements'][0], 'id':'fresh','native_id':'9999'})
            with self.subTest(variant=variant), self.assertRaises(HmiError): self.plan(design, key=variant)

    def test_explicit_operations_cannot_hide_undeclared_delete_or_live_mutation(self):
        auto = self.plan(); variants = [[], auto['operations'][:-1], auto['operations']+[auto['operations'][0]],
            [dict(op='set_property',screen_id='1',element_id='1',key='x',value=3)]]
        for i, ops in enumerate(variants):
            receipt = self.plan(operations=ops, key='explicit'+str(i))
            self.assertEqual(self.service.validate(self.sid, receipt['plan_id'])['findings'][0]['code'], 'NATIVE_CANDIDATE_SCOPE')

    def test_exact_source_profile_witness_and_registry_drift_stop_application(self):
        plan = self.plan(); files = [('source.dps','SOURCE_CHANGED'), ('calibrated/profiles/existing_program_v1.json','PROFILE_CHANGED'),
            ('calibrated/existing_calibration.json','CALIBRATION_CHANGED'), ('authorities/dopsoft2_b10_inert_literals.json','CALIBRATION_CHANGED')]
        for name, code in files:
            path=self.root/name; original=path.read_bytes(); path.write_bytes(original+b' ')
            try:
                with self.subTest(name=name), self.assertRaises(HmiError) as caught: self.service.validate(self.sid,plan['plan_id'])
                self.assertEqual(caught.exception.code,code)
            finally: path.write_bytes(original)

    def test_forged_rehashed_static_facts_are_not_authority(self):
        original = json.loads(self.authority.read_bytes())
        for key,value in [('model_id',True),('mode','source_other'),('owner_kind',{'Type':'6','SubType':'1'}),
                          ('mutation_policy','any_owner'),('evidence',{}),('acceptance_scope','VENDOR_PASS')]:
            bad=deepcopy(original); bad[key]=value
            with self.subTest(key=key),self.assertRaises(HmiError) as caught: FileService._validate_existing_book(bad)
            self.assertEqual(caught.exception.code,'EXISTING_AUTHORITY')

    def test_helper_creates_only_witnesses_never_native_and_rejects_source_registry_races(self):
        self.assertEqual(sorted(p.name for p in (self.root/'calibrated').rglob('*.dps')),[])
        original_write=FileService._write_new
        def race(service,path,data,verifier):
            self.authority.write_bytes(self.authority.read_bytes()+b' ')
            return original_write(service,path,data,verifier)
        with patch.object(FileService,'_write_new',race),self.assertRaises(HmiError) as caught:
            self.helper(self.root,'source.dps','raced','TEST SOURCE','TEST REVIEW')
        self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'raced/existing_calibration.json').exists())

    def test_helper_disappearing_and_unreadable_dependencies_are_typed_and_temporary_files_removed(self):
        original_write = FileService._write_new
        for label, path in [('source', self.root/'source.dps'), ('registry', self.authority)]:
            raw = path.read_bytes()
            def disappear(service, output, data, verifier):
                path.unlink()
                return original_write(service, output, data, verifier)
            try:
                with patch.object(FileService, '_write_new', disappear), self.assertRaises(HmiError) as caught:
                    self.helper(self.root, 'source.dps', 'missing-'+label, 'TEST SOURCE', 'TEST REVIEW')
                self.assertEqual(caught.exception.code, 'CALIBRATION_CHANGED')
                self.assertFalse((self.root/('missing-'+label)/'existing_calibration.json').exists())
                self.assertEqual(list((self.root/('missing-'+label)).glob('.uhmi-*')), [])
            finally: path.write_bytes(raw)
        for label, path in [('source', self.root/'source.dps'), ('registry', self.authority)]:
            original_open = Path.open
            def deny(service, output, data, verifier):
                def guarded_open(candidate, *args, **kwargs):
                    if candidate == path: raise PermissionError('TEST denied freshness read')
                    return original_open(candidate, *args, **kwargs)
                with patch.object(Path, 'open', guarded_open):
                    return original_write(service, output, data, verifier)
            with patch.object(FileService, '_write_new', deny), self.assertRaises(HmiError) as caught:
                self.helper(self.root, 'source.dps', 'denied-'+label, 'TEST SOURCE', 'TEST REVIEW')
            self.assertEqual(caught.exception.code, 'CALIBRATION_CHANGED')
            self.assertFalse((self.root/('denied-'+label)/'existing_calibration.json').exists())
            self.assertEqual(list((self.root/('denied-'+label)).glob('.uhmi-*')), [])


class ControlGenerationServiceTests(unittest.TestCase):
    """Original byte fixtures exercise real public gates; no vendor claim."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, _ = control_generation_fixture()
        (self.root/'source.dps').write_bytes(self.source)
        image = b'\x89PNG\r\n\x1a\nORIGINAL TEST WITNESS ONLY'
        (self.root/'property.png').write_bytes(image)
        kinds = ['set_on','set_off','momentary','maintained','numeric_input','numeric_display']
        witnesses = {kind:dict(screen_id='1',element_id=str(i+1),path='property.png',sha256=service_byte_hash(image)) for i,kind in enumerate(kinds)}
        (self.root/'properties.json').write_text(json.dumps(witnesses))
        helper = runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        helper(self.root,'source.dps','delta_dopsoft2','properties.json','calibration','ORIGINAL TEST ONLY: no actual vendor image/acceptance')
        self.profile_dir = self.root/'calibration/profiles'
        self.service = FileService(self.root,self.profile_dir)
        self.session = self.service.open_project('source_controls_v1','source.dps')['session_id']
        original = NativeAdapter(self.source,'delta_dopsoft2')
        source_page = original.inspect()['screens'][0]
        elements = [dict(id='old'+e['id'],native_id=e['id'],kind='native_preserved',text='',**e['geometry'],
            source_owner_sha256=original.owner_extent_sha256('1',e['id'])) for e in source_page['elements']]
        self.tags = [dict(id=tid,address='{Link2}1@'+address,data_type=typ,access='ReadWrite',channel='Link2',station='1',
            byte_order='device_default',word_order='device_default',native_binding={'link':1,'mem_type':0})
            for tid,address,typ in [('bit','M0','BOOL'),('number','D0','UINT')]]
        for i,kind in enumerate(kinds[:4]):
            elements.append(dict(id='new'+str(i),native_id=str(101+i),kind='button',x=i*25,y=35,width=24,height=12,
                behavior=kind,role='request',binding={'read':'bit','write':'bit'},font_size=6,
                states=[dict(value=0,text='OFF',fill='#777777'),dict(value=1,text='ON',fill='#00AA00')]))
        for i,kind in enumerate(kinds[4:]):
            elements.append(dict(id='numeric'+str(i),native_id=str(105+i),kind=kind,x=i*50,y=55,width=45,height=12,
                binding={'read':'number',**({'write':'number'} if i==0 else {})},minimum=0,maximum=9999,fractional=0,format='decimal',font_size=6))
        self.design = dict(schema_version=1,project_id='original-control-test',profile_id='source_controls_v1',tags=self.tags,macros=[],alarms=[],
            screens=[dict(id='screen',native_id='1',name=source_page['name'],width=100,height=80,elements=elements)])

    def plan(self, design=None):
        return self.service.plan_changes(self.session,self.design if design is None else design,None,'case')

    def approve(self, receipt):
        approval = {key:value for key,value in receipt.items() if key.endswith('_sha256')}
        approval.update(approved=True,authority='direct_human',human_reference='ORIGINAL TEST ONLY — no real human acceptance')
        (self.root/'approval.json').write_text(json.dumps(approval))
        return 'approval.json'

    def test_all_six_controls_public_save_reopen_preservation_length_and_states(self):
        receipt = self.plan()
        self.assertEqual(self.service.validate(self.session,receipt['plan_id'])['findings'],[])
        applied = self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.assertEqual(applied['scope'],'APPEND_SOURCE_CALIBRATED_CONTROLS')
        self.assertFalse(applied['program_writer_complete'])
        saved = self.service.save_as(self.session,'candidate.dps')
        candidate = NativeAdapter((self.root/'candidate.dps').read_bytes(),'delta_dopsoft2')
        original = NativeAdapter(self.source,'delta_dopsoft2')
        self.assertEqual(candidate.envelope.declared_body_length(),len(candidate.envelope.body))
        self.assertEqual(candidate.envelope.prefix[:37],original.envelope.prefix[:37])
        self.assertEqual(candidate.document.tail,original.document.tail)
        for i in range(1,7):
            self.assertEqual(candidate.owner_extent_sha256('1',str(i)),original.owner_extent_sha256('1',str(i)))
        owners = candidate.inspect()['screens'][0]['elements']
        self.assertEqual(len(owners),12)
        self.assertEqual([e['subtype'] for e in owners[6:10]],['1','2','3','4'])
        self.assertEqual([t['text'] for t in owners[9]['texts']],['OFF','ON'])
        self.assertEqual(owners[9]['bindings']['read']['address'],'{Link2}1@M0')
        self.assertNotIn('MinValue',owners[-1]['native_fields'])
        self.assertEqual(saved['sha256'],self.service.diff(self.session)['candidate_sha256'])
        self.assertEqual((self.root/'source.dps').read_bytes(),self.source)
        with self.assertRaises(HmiError):
            self.service.save_as(self.session,'source.dps')

    def test_property_witness_change_after_open_closes_plan(self):
        (self.root/'property.png').write_bytes(b'\x89PNG\r\n\x1a\nCHANGED')
        with self.assertRaises(HmiError) as ctx:
            self.plan()
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED')

    def test_property_witness_change_after_apply_closes_save(self):
        receipt = self.plan()
        self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        (self.root/'property.png').write_bytes(b'CHANGED')
        with self.assertRaises(HmiError):
            self.service.save_as(self.session,'candidate.dps')
        self.assertFalse((self.root/'candidate.dps').exists())

    def test_new_address_outside_captured_namespace_is_not_authorized(self):
        design = deepcopy(self.design)
        design['tags'][0]['address'] = '{Link2}1@M1'
        with self.assertRaises(HmiError) as ctx:
            self.plan(design)
        self.assertEqual(ctx.exception.code,'CONTROL_ADDRESS_SCOPE')

    def test_read_only_command_rejected_before_native_emission(self):
        design = deepcopy(self.design)
        design['tags'][0]['access'] = 'Read'
        with self.assertRaises(HmiError) as ctx:
            self.plan(design)
        self.assertEqual(ctx.exception.code,'VALIDATION')

    def test_reference_donors_cannot_disappear_or_be_reinterpreted(self):
        for mutate in ('delete','caption','geometry'):
            with self.subTest(case=mutate):
                design = deepcopy(self.design)
                if mutate=='delete':del design['screens'][0]['elements'][0]
                elif mutate=='caption':design['screens'][0]['elements'][0]['text']='Not retained'
                else:design['screens'][0]['elements'][0]['x']+=1
                with self.assertRaises(HmiError):
                    self.plan(design)

    def test_unknown_new_color_order_is_rejected(self):
        design = deepcopy(self.design)
        design['screens'][0]['elements'][6]['states'][1]['fill']='#AA0000'
        with self.assertRaises(HmiError) as ctx:
            self.plan(design)
        self.assertEqual(ctx.exception.code,'CONTROL_COLOR_UNVERIFIED')

    def test_explicit_operation_cannot_smuggle_original_owner_edit(self):
        good = self.plan()
        ops = good['operations'] + [dict(op='set_property',screen_id='1',element_id='1',key='x',value=0)]
        receipt = self.service.plan_changes(self.session,self.design,ops,'smuggle')
        self.assertTrue(self.service.validate(self.session,receipt['plan_id'])['findings'])

    def test_idempotency_and_exact_approval_rebinding(self):
        receipt = self.plan()
        self.assertEqual(self.plan(),receipt)
        self.approve(receipt)
        (self.root/'source.dps').write_bytes(self.source+b'CHANGED')
        with self.assertRaises(HmiError):
            self.service.apply_plan(self.session,receipt['plan_id'],'approval.json')

    def test_fake_synthetic_qualification_authority_is_rejected(self):
        receipt = self.plan()
        approval_path = self.approve(receipt)
        approval = json.loads((self.root/approval_path).read_text())
        approval.update(authority='neutral_fixture_qualification',purpose='qualification_only')
        (self.root/approval_path).write_text(json.dumps(approval))
        with self.assertRaises(HmiError):
            self.service.apply_plan(self.session,receipt['plan_id'],approval_path)

    def test_rehashed_malformed_nested_control_contracts_fail_before_session(self):
        profile_path = self.profile_dir/'source_controls_v1.json'
        original_profile = json.loads(profile_path.read_bytes())
        witness_path = self.root/'calibration/control_calibration.json'
        original_witness = json.loads(witness_path.read_bytes())
        for case in ('contract_none','contract_list','donors_none','pin_none','pin_list'):
            with self.subTest(case=case):
                profile, witness = deepcopy(original_profile), deepcopy(original_witness)
                schema = profile['native_schema']
                if case.startswith('contract_'):
                    schema['control_generation'] = None if case.endswith('none') else []
                elif case=='donors_none':
                    schema['control_generation']['donors'] = None
                else:
                    schema['control_generation']['donors']['maintained'] = None if case.endswith('none') else []
                witness['schema_sha256'] = canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'})
                raw = (json.dumps(witness)+'\n').encode()
                witness_path.write_bytes(raw)
                schema['native_candidate']['sha256'] = service_byte_hash(raw)
                profile_path.write_text(json.dumps(profile))
                service = FileService(self.root,self.profile_dir)
                with self.assertRaises(HmiError) as ctx:
                    service.open_project('source_controls_v1','source.dps')
                self.assertEqual(ctx.exception.code,'UNQUALIFIED_CONTROL_GENERATION')
                self.assertEqual(service.sessions,{})
                self.assertFalse((self.root/'candidate.dps').exists())

    def test_calibration_builder_bounds_property_reads_and_invalid_witness_shape(self):
        helper = runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        witnesses = json.loads((self.root/'properties.json').read_bytes())
        witnesses['maintained'] = None
        (self.root/'bad-properties.json').write_text(json.dumps(witnesses))
        with self.assertRaisesRegex(ValueError,'Witness must bind'):
            helper(self.root,'source.dps','delta_dopsoft2','bad-properties.json','bad-calibration','TEST ONLY')
        self.assertFalse((self.root/'bad-calibration').exists())
        with (self.root/'property.png').open('wb') as stream:
            stream.write(b'\x89PNG\r\n\x1a\n')
            stream.truncate(10*1024*1024+2)
        with self.assertRaisesRegex(ValueError,'fingerprint/format'):
            helper(self.root,'source.dps','delta_dopsoft2','properties.json','oversize-calibration','TEST ONLY')
        self.assertFalse((self.root/'oversize-calibration').exists())


class MultipageProgramServiceTests(unittest.TestCase):
    """Original byte fixtures and TEST ONLY authority; no vendor qualification."""
    plan = ControlGenerationServiceTests.plan
    approve = ControlGenerationServiceTests.approve

    def setUp(self):
        from test_multipage import multipage_fixture
        ControlGenerationServiceTests.setUp(self)
        self.target,self.library,self.layout,schema = multipage_fixture()
        # Exercise the real typed model gate using original constructed bytes;
        # the number alone is never evidence of a vendor-created project.
        self.target,self.library,self.layout = tuple(Envelope.decode(raw,'delta_dopsoft2').encode(
            Envelope.decode(raw,'delta_dopsoft2').body.replace(b'ModelName=SYNTHETIC\r\n',b'ModelName=2953863504\r\n'))
            for raw in (self.target,self.library,self.layout))
        for name,raw in [('blank.dps',self.target),('library.dps',self.library),('layout.dps',self.layout)]:
            (self.root/name).write_bytes(raw)
        control_helper=runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        control_helper(self.root,'library.dps','delta_dopsoft2','properties.json','program_library','ORIGINAL TEST ONLY')
        self.library_profile_path='program_library/profiles/source_controls_v1.json'
        profile=json.loads((self.root/self.library_profile_path).read_bytes())
        descriptor=schema['multipage_program']
        self.properties={}
        for kind in ('text','indicator','goto'):
            raw=json.dumps(dict(scope='VENDOR_CREATED_REFERENCE_PROPERTY_ONLY',
                type={'text':'Literal Text','indicator':'Multistate Indicator','goto':'Goto Screen'}[kind],
                test_only='Original synthetic property fixture, not an actual vendor observation')).encode()
            relative=kind+'_property.json';(self.root/relative).write_bytes(raw);self.properties[kind]=relative
            descriptor['aux_donors'][kind]['property_witness_sha256']=service_byte_hash(raw)
        self.authority_dir=self.root/'layout_registry';self.authority_dir.mkdir()
        self.book=dict(schema_version=1,authority_kind='vendor_source_static_layout_contract',family=profile['family'],
            serialized_version=profile['editor_version'],model_id=profile['model_id'],layout_sha256=service_byte_hash(self.layout),
            page_donor=descriptor['page_donor'],aux_donors=descriptor['aux_donors'],new_page_action=0,page_id_max=65535,
            evidence={'test_only':'Original fixture authority; not vendor evidence'},acceptance_scope='OFFLINE_STORED_LAYOUT_ONLY')
        (self.authority_dir/'test_only.json').write_text(json.dumps(self.book))
        self.authority_patch=patch.object(FileService,'_layout_authority_dir',return_value=self.authority_dir)
        self.authority_patch.start();self.addCleanup(self.authority_patch.stop)
        self.helper=runpy.run_path(str(ROOT/'scripts/calibrate_multipage.py'))['calibrate']
        self.helper(self.root,'blank.dps','library.dps',self.library_profile_path,'layout.dps',self.properties,'multipage','TEST SOURCE','TEST REVIEW')
        self.profile_dir=self.root/'multipage/profiles'
        self.service=FileService(self.root,self.profile_dir)
        self.session=self.service.open_project('multipage_program_v1','blank.dps')['session_id']
        base=[e for e in self.design['screens'][0]['elements'] if e['kind']!='native_preserved']
        self.design['profile_id']='multipage_program_v1'
        self.design['screens']=[dict(id='home',native_id='1',name='Original',width=100,height=80,elements=base[:2]+[
            dict(id='title',native_id='201',kind='text',x=0,y=0,width=98,height=14,text='ÖLÇÜM',font_size=6),
            dict(id='next',native_id='203',kind='goto',x=0,y=60,width=40,height=14,text='DEĞERLER',target_screen='values',font_size=6)]),
            dict(id='values',native_id='2',name='Values',width=100,height=80,elements=base[4:]+[
                dict(id='lamp',native_id='202',kind='indicator',x=0,y=0,width=40,height=14,role='request',binding={'read':'bit'},font_size=6,
                    states=[dict(value=0,text='KAPALI',fill='#555555'),dict(value=1,text='AÇIK',fill='#00AA00')]),
                dict(id='next2',native_id='204',kind='goto',x=50,y=0,width=45,height=14,text='KOMUT',target_screen='commands',font_size=6)]),
            dict(id='commands',native_id='3',name='Commands',width=100,height=80,elements=base[2:4]+[
                dict(id='back',native_id='205',kind='goto',x=0,y=60,width=40,height=14,text='GERİ',target_screen='home',font_size=6)])]

    def test_mixed_public_plan_approve_save_reopen_matches_complete_ir(self):
        plan=self.plan();self.assertFalse(self.service.validate(self.session,plan['plan_id'])['findings'])
        applied=self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        self.assertEqual(applied['scope'],'BLANK_TARGET_THREE_SOURCE_MULTIPAGE');self.assertFalse(applied['program_writer_complete'])
        saved=self.service.save_as(self.session,'mixed.dps')
        candidate=NativeAdapter((self.root/'mixed.dps').read_bytes(),'delta_dopsoft2')
        pages=candidate.inspect()['screens']
        self.assertEqual([p['id'] for p in pages],['1','2','3'])
        self.assertEqual([[e['id'] for e in p['elements']] for p in pages],[['101','102','201','203'],['105','106','202','204'],['103','104','205']])
        self.assertEqual([p['native_fields']['ScreenAction'] for p in pages][1:],['0','0'])
        self.assertEqual(candidate._preserved_prefix(candidate.document),NativeAdapter(self.target,'delta_dopsoft2')._preserved_prefix(NativeAdapter(self.target,'delta_dopsoft2').document))
        self.assertNotIn(b'HMIPortNr0=1660265583',candidate.envelope.body)
        self.assertEqual(candidate.document.tail,NativeAdapter(self.library,'delta_dopsoft2').document.tail)
        self.assertEqual(pages[1]['elements'][2]['bindings']['write']['address'],'None')
        self.assertEqual([t['text'] for t in pages[1]['elements'][2]['texts']],['KAPALI','AÇIK'])
        self.assertEqual(pages[0]['elements'][-1]['native_fields']['GoToScreenID'],'2')
        self.assertEqual(pages[0]['elements'][-1]['native_fields']['GoToScreenName'],'Values')
        self.assertEqual(saved['sha256'],self.service.diff(self.session)['candidate_sha256'])
        for name,data in [('blank.dps',self.target),('library.dps',self.library),('layout.dps',self.layout)]:
            self.assertEqual((self.root/name).read_bytes(),data)

    def test_text_and_goto_only_preserve_target_tail_and_page_only_noop_is_exact(self):
        design=deepcopy(self.design);design['tags']=[]
        for page in design['screens']:page['elements']=[e for e in page['elements'] if e['kind'] in {'text','goto'}]
        plan=self.plan(design);self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan));self.service.save_as(self.session,'literals.dps')
        self.assertEqual(NativeAdapter((self.root/'literals.dps').read_bytes(),'delta_dopsoft2').document.tail,NativeAdapter(self.target,'delta_dopsoft2').document.tail)
        design['screens']=design['screens'][:1];design['screens'][0]['elements']=[]
        plan=self.service.plan_changes(self.session,design,None,'noop');self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan));self.service.save_as(self.session,'noop.dps')
        self.assertEqual((self.root/'noop.dps').read_bytes(),self.target)

    def test_every_auxiliary_source_and_property_dependency_is_fresh(self):
        for relative in ['layout.dps','library.dps',self.library_profile_path,'program_library/control_calibration.json',*self.properties.values(),'property.png']:
            with self.subTest(path=relative):
                service=FileService(self.root,self.profile_dir);sid=service.open_project('multipage_program_v1','blank.dps')['session_id']
                path=self.root/relative;original=path.read_bytes();path.write_bytes(original+b'CHANGED')
                try:
                    with self.assertRaises(HmiError) as ctx:service.plan_changes(sid,self.design,None,'fresh')
                    self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED')
                finally:path.write_bytes(original)

    def test_registered_authority_change_after_apply_prevents_native_output(self):
        plan=self.plan();self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        path=self.authority_dir/'test_only.json';path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(HmiError) as ctx:self.service.save_as(self.session,'stale.dps')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'stale.dps').exists())

    def test_page_identity_reference_and_indicator_write_intent_cannot_be_silently_changed(self):
        for case in ('name','id','old_owner','dangling','write','state_order','unknown_style','macro'):
            with self.subTest(case=case):
                design=deepcopy(self.design)
                if case=='name':design['screens'][1]['name']='Türkçe'
                elif case=='id':design['screens'][1]['native_id']='65536'
                elif case=='old_owner':design['screens'][1]['elements'][0]['native_id']='1'
                elif case=='dangling':design['screens'][0]['elements'][-1]['target_screen']='missing'
                elif case=='write':design['screens'][1]['elements'][2]['binding']['write']='bit'
                elif case=='state_order':design['screens'][1]['elements'][2]['states'].reverse()
                elif case=='unknown_style':design['screens'][0]['elements'][2]['font']='Arial'
                else:design['macros']=[dict(id='unqualified')]
                with self.assertRaises(HmiError):self.plan(design)

    def test_explicit_changed_plan_never_overrides_approved_ir(self):
        original=self.plan()
        operations=deepcopy(original['operations'])
        next(op for op in operations if op.get('kind')=='indicator')['states'][1]['text']='WRONG'
        receipt=self.service.plan_changes(self.session,self.design,operations,'wrong-state')
        self.assertTrue(self.service.validate(self.session,receipt['plan_id'])['findings'])
        with self.assertRaises(HmiError):self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))

    def test_rehashed_caller_descriptor_cannot_promote_unknown_authority(self):
        profile_path=self.profile_dir/'multipage_program_v1.json';profile=json.loads(profile_path.read_bytes())
        witness_path=self.root/'multipage/multipage_calibration.json';witness=json.loads(witness_path.read_bytes())
        profile['native_schema']['multipage_program']['authority_sha256']='0'*64
        witness['schema_sha256']=canonical_hash({k:v for k,v in profile['native_schema'].items() if k!='native_candidate'})
        raw=json.dumps(witness).encode();witness_path.write_bytes(raw)
        profile['native_schema']['native_candidate']['sha256']=service_byte_hash(raw);profile_path.write_text(json.dumps(profile))
        service=FileService(self.root,self.profile_dir)
        with self.assertRaises(HmiError) as ctx:service.open_project('multipage_program_v1','blank.dps')
        self.assertEqual(ctx.exception.code,'LAYOUT_AUTHORITY');self.assertEqual(service.sessions,{})

    def test_helper_does_not_write_when_reference_changes_before_atomic_publication(self):
        write=FileService._write_new
        def race(service,relative,data,before_publish=None):
            (self.root/'layout.dps').write_bytes(self.layout+b'CHANGED')
            return write(service,relative,data,before_publish)
        with patch.object(FileService,'_write_new',race):
            with self.assertRaises(HmiError) as ctx:self.helper(self.root,'blank.dps','library.dps',self.library_profile_path,'layout.dps',self.properties,'race','TEST','TEST')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'race/multipage_calibration.json').exists())
        self.assertFalse(list((self.root/'race').glob('*.tmp')))


class BlankProgramServiceTests(unittest.TestCase):
    """Blank target/library public flows with original synthetic bytes."""
    plan = ControlGenerationServiceTests.plan
    approve = ControlGenerationServiceTests.approve

    def setUp(self):
        # Reuse the independent IR, tags and explicit TEST ONLY property pins.
        ControlGenerationServiceTests.setUp(self)
        self.target, self.library, _ = blank_program_fixture()
        (self.root/'blank.dps').write_bytes(self.target)
        (self.root/'library.dps').write_bytes(self.library)
        control_helper = runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        control_helper(self.root,'library.dps','delta_dopsoft2','properties.json','program_library','ORIGINAL TEST ONLY')
        self.helper = runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        self.library_profile_path = 'program_library/profiles/source_controls_v1.json'
        self.helper(self.root,'blank.dps','library.dps',self.library_profile_path,'program','TEST SOURCE','TEST REVIEW')
        self.profile_dir = self.root/'program/profiles'
        self.service = FileService(self.root,self.profile_dir)
        self.session = self.service.open_project('blank_program_v1','blank.dps')['session_id']
        self.design['profile_id']='blank_program_v1'
        self.design['screens'][0]['elements']=[e for e in self.design['screens'][0]['elements'] if e['kind']!='native_preserved']

    def test_clean_public_save_has_only_ir_controls_and_exact_target_globals(self):
        plan = self.plan()
        self.assertFalse(self.service.validate(self.session,plan['plan_id'])['findings'])
        applied = self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        self.assertEqual(applied['scope'],'BLANK_TARGET_SOURCE_LIBRARY_CONTROLS')
        self.assertFalse(applied['program_writer_complete'])
        saved = self.service.save_as(self.session,'clean.dps')
        original = NativeAdapter(self.target,'delta_dopsoft2')
        candidate = NativeAdapter((self.root/'clean.dps').read_bytes(),'delta_dopsoft2')
        owners=candidate.inspect()['screens'][0]['elements']
        self.assertEqual([e['id'] for e in owners],['101','102','103','104','105','106'])
        self.assertEqual(candidate._preserved_prefix(candidate.document),original._preserved_prefix(original.document))
        self.assertEqual(candidate.envelope.thumbnail,original.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix[:37],original.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(),len(candidate.envelope.body))
        self.assertEqual(candidate.document.tail,NativeAdapter(self.library,'delta_dopsoft2').document.tail)
        self.assertEqual(saved['sha256'],self.service.diff(self.session)['candidate_sha256'])
        self.assertEqual((self.root/'blank.dps').read_bytes(),self.target)
        self.assertEqual((self.root/'library.dps').read_bytes(),self.library)

    def test_empty_public_program_preserves_every_blank_byte(self):
        design=deepcopy(self.design);design['tags']=[];design['screens'][0]['elements']=[]
        plan=self.plan(design)
        self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        self.service.save_as(self.session,'empty.dps')
        self.assertEqual((self.root/'empty.dps').read_bytes(),self.target)

    def test_every_library_dependency_is_fresh_before_plan(self):
        dependencies=['library.dps',self.library_profile_path,'program_library/control_calibration.json','property.png']
        for name in dependencies:
            with self.subTest(path=name):
                service=FileService(self.root,self.profile_dir)
                sid=service.open_project('blank_program_v1','blank.dps')['session_id']
                path=self.root/name;before=path.read_bytes();path.write_bytes(before+b'CHANGED')
                try:
                    with self.assertRaises(HmiError) as ctx:
                        service.plan_changes(sid,self.design,None,'changed')
                    self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED')
                finally:path.write_bytes(before)

    def test_library_change_after_apply_prevents_output(self):
        plan=self.plan();self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        (self.root/'library.dps').write_bytes(self.library+b'CHANGED')
        with self.assertRaises(HmiError) as ctx:self.service.save_as(self.session,'clean.dps')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED')
        self.assertFalse((self.root/'clean.dps').exists())

    def test_rehashed_malformed_program_contracts_fail_without_sessions(self):
        profile_path=self.profile_dir/'blank_program_v1.json';base=json.loads(profile_path.read_bytes())
        witness_path=self.root/'program/program_calibration.json';base_witness=json.loads(witness_path.read_bytes())
        for key,value in [('blank_program',None),('blank_program',[]),('library_schema',None),('library_schema',[]),('library',None),('library',[])]:
            with self.subTest(key=key,value=value):
                profile,witness=deepcopy(base),deepcopy(base_witness);schema=profile['native_schema']
                if key=='blank_program':schema[key]=value
                elif key=='library_schema':schema['blank_program'][key]=value
                else:witness[key]=value
                witness['schema_sha256']=canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'})
                raw=(json.dumps(witness)+'\n').encode();witness_path.write_bytes(raw)
                schema['native_candidate']['sha256']=service_byte_hash(raw);profile_path.write_text(json.dumps(profile))
                service=FileService(self.root,self.profile_dir)
                with self.assertRaises(HmiError):service.open_project('blank_program_v1','blank.dps')
                self.assertEqual(service.sessions,{})

    def test_donor_retention_old_identity_or_missing_page_intent_rejected(self):
        for case in ('donor_retained','old_id','missing_page'):
            with self.subTest(case=case):
                design=deepcopy(self.design)
                if case=='donor_retained':design['screens'][0]['elements'][0]['kind']='native_preserved'
                elif case=='old_id':design['screens'][0]['elements'][0]['native_id']='1'
                else:design['screens']=[]
                with self.assertRaises(HmiError):self.plan(design)

    def test_rehashed_auxiliary_profiles_are_typed_before_session_or_output(self):
        library_path=self.root/self.library_profile_path
        original_library=json.loads(library_path.read_bytes())
        witness_path=self.root/'program/program_calibration.json'
        original_witness=json.loads(witness_path.read_bytes())
        profile_path=self.profile_dir/'blank_program_v1.json'
        original_profile=json.loads(profile_path.read_bytes())
        cases=[('id',None),('id',[]),('id',''),('id','unsafe/name'),
               ('resolution',None),('resolution',{}),('resolution',[1024]),
               ('resolution',[True,600]),('resolution',[0,600]),('resolution',[1024,'600']),
               ('family',[]),('editor_version',None),('editor_version','bad\nversion'),
               ('capabilities',[]),('native_schema',[]),('model_id',None)]
        cases += [(key,'REMOVE') for key in ('id','resolution','family','editor_version','capabilities','native_schema','model_id')]
        for index,(key,value) in enumerate(cases):
            with self.subTest(key=key,value=value):
                library=deepcopy(original_library)
                if value=='REMOVE':library.pop(key)
                else:library[key]=value
                raw=(json.dumps(library)+'\n').encode();library_path.write_bytes(raw)
                witness=deepcopy(original_witness);witness['library']['profile_sha256']=service_byte_hash(raw)
                raw_witness=(json.dumps(witness)+'\n').encode();witness_path.write_bytes(raw_witness)
                profile=deepcopy(original_profile)
                profile['native_schema']['native_candidate']['sha256']=service_byte_hash(raw_witness)
                profile_path.write_text(json.dumps(profile))
                service=FileService(self.root,self.profile_dir)
                with self.assertRaises(HmiError):service.open_project('blank_program_v1','blank.dps')
                self.assertEqual(service.sessions,{})
                output='invalid_profile_'+str(index)
                with self.assertRaises(HmiError):
                    self.helper(self.root,'blank.dps','library.dps',self.library_profile_path,output,'TEST','TEST')
                self.assertFalse((self.root/output).exists())

    def test_explicit_source_edit_delete_or_extra_clone_cannot_escape_ir(self):
        plan=self.plan()
        for op in [dict(op='delete_element',screen_id='1',element_id='1'),
                   dict(op='set_property',screen_id='1',element_id='1',key='x',value=0),
                   dict(op='clone_element',source_screen='1',source_element='1',target_screen='1',element_id='999')]:
            with self.subTest(operation=op['op']):
                receipt=self.service.plan_changes(self.session,self.design,plan['operations']+[op],op['op'])
                self.assertTrue(self.service.validate(self.session,receipt['plan_id'])['findings'])

    def test_captured_address_scope_and_readonly_are_preserved(self):
        for case in ('new_address','readonly','decimal'):
            with self.subTest(case=case):
                design=deepcopy(self.design)
                if case=='new_address':design['tags'][0]['address']='{Link2}1@M1'
                elif case=='readonly':design['tags'][0]['access']='Read'
                else:design['screens'][0]['elements'][-2]['fractional']=1
                with self.assertRaises(HmiError):self.plan(design)

    def test_helper_rejects_nonempty_target_and_existing_output(self):
        with self.assertRaises(HmiError) as ctx:
            self.helper(self.root,'library.dps','library.dps',self.library_profile_path,'bad','TEST','TEST')
        self.assertEqual(ctx.exception.code,'NONEMPTY_PROGRAM_TARGET')
        self.assertFalse((self.root/'bad').exists())
        raw=(self.root/'program/program_calibration.json').read_bytes()
        with self.assertRaises(HmiError) as ctx:
            self.helper(self.root,'blank.dps','library.dps',self.library_profile_path,'program','TEST','TEST')
        self.assertEqual(ctx.exception.code,'OUTPUT_EXISTS')
        self.assertEqual((self.root/'program/program_calibration.json').read_bytes(),raw)

    def test_saved_target_corruption_is_not_hidden_by_library_reassembly(self):
        plan=self.plan();self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        active=self.service._session(self.session)['applied'];before=active['data']
        envelope=Envelope.decode(before,'delta_dopsoft2')
        active['data']=envelope.encode(envelope.body.replace(b'TagLinkCount=1',b'TagLinkCount=2',1))
        with self.assertRaises(HmiError):self.service.save_as(self.session,'corrupt.dps')
        self.assertFalse((self.root/'corrupt.dps').exists())


class DriverNamespaceServiceTests(unittest.TestCase):
    """Original byte fixtures and installed factual data, not vendor acceptance."""
    plan = ControlGenerationServiceTests.plan
    approve = ControlGenerationServiceTests.approve

    def setUp(self):
        ControlGenerationServiceTests.setUp(self)
        target,library,_ = blank_program_fixture()
        driver=(b'ControllerSection0=Delta\r\nControllerName0=Delta DVP PLC\r\n'
                b'CommName0=Link2\r\nDefPLCStationNr0=1\r\nPrinterSection0=NULL\r\n')
        def framed(raw):
            native=NativeAdapter(raw,'delta_dopsoft2')
            document=deepcopy(native.document)
            next(s for s in document.sections if s.name=='Application').one('Version').set_value(b'4.00.07.04')
            body=document.bytes().replace(b'[Multi-Language]\r\n',driver+b'[Multi-Language]\r\n',1)
            return native.envelope.encode(body)
        self.target,self.library=framed(target),framed(library)
        (self.root/'blank.dps').write_bytes(self.target);(self.root/'library.dps').write_bytes(self.library)
        self.authority_dir=self.root/'authorities';self.authority_dir.mkdir()
        self.authority_path=self.authority_dir/'delta_dvp_serial_2016.json'
        self.authority_path.write_bytes((ROOT/'profiles/driver_contracts/delta_dvp_serial_2016.json').read_bytes())
        redirect=patch.object(FileService,'_driver_authority_dir',return_value=self.authority_dir)
        redirect.start();self.addCleanup(redirect.stop)
        control_helper=runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        control_helper(self.root,'library.dps','delta_dopsoft2','properties.json','base','ORIGINAL TEST ONLY')
        self.helper=runpy.run_path(str(ROOT/'scripts/calibrate_dvp_namespace.py'))['calibrate']
        self.helper(self.root,'library.dps','base/profiles/source_controls_v1.json','dvp','ORIGINAL TEST ONLY')
        program_helper=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        program_helper(self.root,'blank.dps','library.dps','dvp/profiles/source_controls_dvp_v1.json','program','TEST SOURCE','TEST REVIEW')
        self.profile_dir=self.root/'program/profiles'
        self.service=FileService(self.root,self.profile_dir)
        self.session=self.service.open_project('blank_program_v1','blank.dps')['session_id']
        self.design['profile_id']='blank_program_v1'
        elements=[e for e in self.design['screens'][0]['elements'] if e['kind']!='native_preserved']
        self.design['screens'][0]['elements']=elements
        tags=[]
        for index,(element,suffix) in enumerate(zip(elements,('M1','M10','S2','M4095','D10000','D11999'))):
            tag=deepcopy(self.tags[0 if index<4 else 1])
            tag['id']='binding'+str(index);tag['address']='{Link2}1@'+suffix
            if index==5:tag['access']='Read'
            element['binding']={direction:tag['id'] for direction in element['binding']}
            tags.append(tag)
        self.design['tags']=tags

    def test_distinct_typed_addresses_save_clean_and_preserve_metadata(self):
        limitation=json.loads((self.profile_dir/'blank_program_v1.json').read_bytes())['limitation']
        self.assertIn('source-qualified driver address regions',limitation)
        self.assertNotIn('captured M0/D0',limitation)
        receipt=self.plan();self.assertEqual(self.service.validate(self.session,receipt['plan_id'])['findings'],[])
        self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        saved=self.service.save_as(self.session,'distinct.dps')
        candidate=NativeAdapter((self.root/'distinct.dps').read_bytes(),'delta_dopsoft2')
        original=NativeAdapter(self.target,'delta_dopsoft2')
        owners=candidate.inspect()['screens'][0]['elements']
        self.assertEqual([v['id'] for v in owners],['101','102','103','104','105','106'])
        for owner,tag in zip(owners,self.design['tags']):
            self.assertEqual(owner['bindings']['read']['address'],tag['address'])
            self.assertEqual(owner['native_fields']['ReadLink'],'1')
            self.assertEqual(owner['native_fields']['ReadMemType'],'0')
            if owner['id']!='106':self.assertEqual(owner['bindings']['write']['address'],tag['address'])
        self.assertEqual(candidate._preserved_prefix(candidate.document),original._preserved_prefix(original.document))
        self.assertEqual(candidate.envelope.thumbnail,original.envelope.thumbnail)
        self.assertEqual(saved['sha256'],self.service.diff(self.session)['candidate_sha256'])
        self.assertEqual((self.root/'library.dps').read_bytes(),self.library)

    def test_driver_endpoints_and_extended_d_words_are_allowed(self):
        for index,suffixes in ((0,('M0','M20','M4095','S0','S1023')),(4,('D0','D9999','D10000','D11999'))):
            for suffix in suffixes:
                with self.subTest(suffix=suffix):
                    design=deepcopy(self.design);design['tags'][index]['address']='{Link2}1@'+suffix
                    # One catalog identity owns each hardware address. Move
                    # another fixture tag when this endpoint is already used.
                    if suffix=='M4095':design['tags'][3]['address']='{Link2}1@M30'
                    if suffix=='D11999':design['tags'][5]['address']='{Link2}1@D11000'
                    receipt=self.service.plan_changes(self.session,design,None,suffix)
                    self.assertFalse(self.service.validate(self.session,receipt['plan_id'])['findings'])

    def test_invalid_grammar_range_region_and_station_are_rejected(self):
        for index,address in [(0,'{Link2}1@'+s) for s in ('M4096','S1024','M01','m1','M1.0','D1','M-1','M1x')]+[(4,'{Link2}1@D12000'),(4,'{Link2}1@M1'),(0,'{Link1}1@M1'),(0,'{Link2}2@M1')]:
            with self.subTest(address=address):
                design=deepcopy(self.design);design['tags'][index]['address']=address
                with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,address)

    def test_namespace_keeps_readonly_width_and_native_binding_guards(self):
        for field,value in [('access','Read'),('data_type','UINT'),('native_binding',{'link':2,'mem_type':0})]:
            with self.subTest(field=field):
                design=deepcopy(self.design);design['tags'][0][field]=value
                with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,field)
        design=deepcopy(self.design);design['screens'][0]['elements'][4]['fractional']=1
        with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'decimal')

    def test_same_prefix_substring_does_not_change_other_owner(self):
        receipt=self.plan();before=self.service._emit(self.service._session(self.session),receipt['operations'])
        design=deepcopy(self.design);design['tags'][0]['address']='{Link2}1@M2'
        second=self.service.plan_changes(self.session,design,None,'M2')
        after=self.service._emit(self.service._session(self.session),second['operations'])
        a,b=NativeAdapter(before,'delta_dopsoft2'),NativeAdapter(after,'delta_dopsoft2')
        self.assertEqual(a.owner_extent_sha256('1','102'),b.owner_extent_sha256('1','102'))
        self.assertEqual(b.inspect()['screens'][0]['elements'][1]['bindings']['write']['address'],'{Link2}1@M10')

    def test_registry_change_after_open_or_apply_closes_mutation(self):
        receipt=self.plan();self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.authority_path.write_bytes(self.authority_path.read_bytes()+b'CHANGED')
        with self.assertRaises(HmiError) as caught:self.service.save_as(self.session,'changed.dps')
        self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'changed.dps').exists())
        with self.assertRaises(HmiError):self.service.plan_changes(self.session,self.design,None,'changed')

    def test_rehashed_unregistered_or_widened_namespace_cannot_open(self):
        profile_path=self.root/'dvp/profiles/source_controls_dvp_v1.json'
        original=json.loads(profile_path.read_bytes())
        witness_path=self.root/'dvp/control_calibration.json'
        original_witness=json.loads(witness_path.read_bytes())
        for variant in ('unregistered','widened','foreign_driver','foreign_version'):
            profile,witness=deepcopy(original),deepcopy(original_witness)
            schema=profile['native_schema'];namespace=schema['address_namespace']
            if variant=='unregistered':namespace['authority_sha256']='0'*64
            elif variant=='widened':namespace['regions']['UINT'][0]['maximum']=12000
            elif variant=='foreign_driver':namespace['driver']['name']='Other Driver'
            else:profile['editor_version']='4.00.99.99'
            witness['schema_sha256']=canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'})
            raw=(json.dumps(witness)+'\n').encode();witness_path.write_bytes(raw)
            schema['native_candidate']['sha256']=service_byte_hash(raw);profile_path.write_text(json.dumps(profile))
            service=FileService(self.root,profile_path.parent)
            with self.assertRaises(HmiError):service.open_project('source_controls_dvp_v1','library.dps')
            self.assertEqual(service.sessions,{})

    def test_helper_malformed_registered_facts_fail_before_output(self):
        original=json.loads(self.authority_path.read_bytes())
        cases=[('driver',None),('driver',[]),('driver',{}),('driver',{'company':None,'name':'Delta DVP PLC'}),
               ('regions',None),('regions',[]),('serialized_version',None),('evidence',[])]
        for index,(key,value) in enumerate(cases):
            with self.subTest(key=key,value=value):
                book=deepcopy(original);book[key]=value;self.authority_path.write_text(json.dumps(book))
                output='invalid'+str(index)
                with self.assertRaises(HmiError):
                    self.helper(self.root,'library.dps','base/profiles/source_controls_v1.json',output,'TEST REVIEW')
                self.assertFalse((self.root/output).exists())

    def test_rehashed_deep_namespace_is_typed_before_public_and_helper_copies(self):
        profile_path=self.root/'dvp/profiles/source_controls_dvp_v1.json'
        profile=json.loads(profile_path.read_bytes())
        nested='invalid review'
        for _ in range(500):nested=[nested]
        profile['native_schema']['address_namespace']['review_reference']=nested
        witness_path=self.root/'dvp/control_calibration.json'
        witness=json.loads(witness_path.read_bytes())
        witness['schema_sha256']=canonical_hash({k:v for k,v in profile['native_schema'].items() if k!='native_candidate'})
        raw=(json.dumps(witness)+'\n').encode();witness_path.write_bytes(raw)
        profile['native_schema']['native_candidate']['sha256']=service_byte_hash(raw)
        profile_path.write_text(json.dumps(profile))
        service=FileService(self.root,profile_path.parent)
        with self.assertRaises(HmiError):service.open_project('source_controls_dvp_v1','library.dps')
        self.assertEqual(service.sessions,{})
        program_helper=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        with self.assertRaises(HmiError):
            program_helper(self.root,'blank.dps','library.dps','dvp/profiles/source_controls_dvp_v1.json','deep-program','TEST','TEST')
        self.assertFalse((self.root/'deep-program').exists())
        with self.assertRaises(HmiError):
            self.helper(self.root,'library.dps','dvp/profiles/source_controls_dvp_v1.json','deep-namespace','TEST')
        self.assertFalse((self.root/'deep-namespace').exists())

    def test_metadata_decoder_and_breadth_limits_are_typed(self):
        from universal_hmi.service import _json_object
        path=self.root/'bounded.json'
        path.write_bytes(b'{"nested":'+b'['*1500+b'0'+b']'*1500+b'}')
        with self.assertRaises(HmiError) as caught:_json_object(path,'METADATA_BOUND')
        self.assertEqual(caught.exception.code,'METADATA_BOUND')
        path.write_text(json.dumps({'wide':[0]*250001}))
        with self.assertRaises(HmiError) as caught:_json_object(path,'METADATA_BOUND')
        self.assertEqual(caught.exception.code,'METADATA_BOUND')

    def test_authority_unavailable_during_helper_save_is_typed_and_cleans_temporary(self):
        original_open=Path.open
        original_write=FileService._write_new
        attempted=[]
        def missing_authority(path,*args,**kwargs):
            if path==self.authority_path:
                attempted.append(path)
                raise FileNotFoundError('authority removed during save')
            return original_open(path,*args,**kwargs)
        def guarded_write(service,output,data,verifier):
            def verify(saved):
                with patch.object(Path,'open',new=missing_authority):
                    return verifier(saved)
            return original_write(service,output,data,verify)
        program_helper=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        for kind in ('namespace','program'):
            with self.subTest(kind=kind),patch.object(FileService,'_write_new',new=guarded_write):
                output='missing-authority-'+kind
                with self.assertRaises(HmiError) as caught:
                    if kind=='namespace':
                        self.helper(self.root,'library.dps','base/profiles/source_controls_v1.json',output,'TEST REVIEW')
                    else:
                        program_helper(self.root,'blank.dps','library.dps','dvp/profiles/source_controls_dvp_v1.json',output,'TEST SOURCE','TEST REVIEW')
                self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED')
                self.assertEqual(list((self.root/output).rglob('*')),[])
        self.assertEqual(len(attempted),2)


class RadixNamespaceServiceTests(unittest.TestCase):
    """Original native fixtures; reviewed driver facts are not a live PLC test."""
    plan=ControlGenerationServiceTests.plan
    approve=ControlGenerationServiceTests.approve

    def setUp(self):
        DriverNamespaceServiceTests.setUp(self)
        self.radix_authority=self.authority_dir/'delta_dvp_serial_radix_2016.json'
        self.radix_authority.write_bytes((ROOT/'profiles/driver_contracts/delta_dvp_serial_radix_2016.json').read_bytes())
        self.helper(self.root,'library.dps','dvp/profiles/source_controls_dvp_v1.json','radix','ORIGINAL TEST ONLY','delta_dvp_serial_radix_2016.json')
        self.radix_profile_path='radix/profiles/source_controls_dvp_v2.json'
        program=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        program(self.root,'blank.dps','library.dps',self.radix_profile_path,'radix-program','TEST SOURCE','TEST REVIEW')
        self.profile_dir=self.root/'radix-program/profiles';self.service=FileService(self.root,self.profile_dir)
        self.session=self.service.open_project('blank_program_v1','blank.dps')['session_id']
        for tag,suffix in zip(self.design['tags'][:4],('Y0','Y7','Y10','Y377')):tag['address']='{Link2}1@'+suffix

    def test_public_y_octal_addresses_save_and_preserve_source_driver_and_memory_metadata(self):
        plan=self.plan();self.assertFalse(self.service.validate(self.session,plan['plan_id'])['findings'])
        self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan));self.service.save_as(self.session,'radix.dps')
        native=NativeAdapter((self.root/'radix.dps').read_bytes(),'delta_dopsoft2');owners=native.inspect()['screens'][0]['elements']
        self.assertEqual([o['bindings']['write']['address'] for o in owners[:4]],['{Link2}1@Y0','{Link2}1@Y7','{Link2}1@Y10','{Link2}1@Y377'])
        for owner in owners[:4]:self.assertEqual((owner['native_fields']['ReadMemType'],owner['native_fields']['WriteMemType']),('0','0'))
        original=NativeAdapter(self.target,'delta_dopsoft2')
        self.assertEqual(native._preserved_prefix(native.document),original._preserved_prefix(original.document))
        self.assertEqual((self.root/'blank.dps').read_bytes(),self.target);self.assertEqual((self.root/'library.dps').read_bytes(),self.library)

    def test_x_write_is_refused_even_when_catalog_declares_readwrite(self):
        for address in ('X0','X7','X10','X377'):
            with self.subTest(address=address):
                design=deepcopy(self.design);design['tags'][0].update(address='{Link2}1@'+address,access='ReadWrite')
                with self.assertRaises(HmiError) as ctx:self.service.plan_changes(self.session,design,None,address)
                self.assertEqual(ctx.exception.code,'CONTROL_ADDRESS_SCOPE')

    def test_octal_invalid_digits_bounds_and_aliases_are_rejected(self):
        for address in ('Y8','Y9','Y18','Y78','Y378','Y400','Y000','Y01','y10','Y+10','Y-1','Y10.0','Y１０','Y10 ','Y0x10'):
            with self.subTest(address=address):
                design=deepcopy(self.design);design['tags'][0]['address']='{Link2}1@'+address
                with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,address)

    def test_v1_old_profile_remains_decimal_and_rejects_new_y_without_requalification(self):
        service=FileService(self.root,self.root/'program/profiles');sid=service.open_project('blank_program_v1','blank.dps')['session_id']
        with self.assertRaises(HmiError):service.plan_changes(sid,self.design,None,'old-profile')
        profile=json.loads((self.root/'dvp/profiles/source_controls_dvp_v1.json').read_bytes())
        self.assertEqual(profile['native_schema']['address_namespace']['contract_version'],1)
        self.assertEqual(set(profile['native_schema']['address_namespace']['regions']['BOOL'][0]),{'area','minimum','maximum'})

    def test_rehashed_radix_or_direction_changes_cannot_promote_unregistered_contract(self):
        profile_path=self.root/self.radix_profile_path;original=json.loads(profile_path.read_bytes())
        witness_path=self.root/'radix/control_calibration.json';original_witness=json.loads(witness_path.read_bytes())
        for case in ('radix','access','maximum','unknown_authority','version'):
            with self.subTest(case=case):
                profile,witness=deepcopy(original),deepcopy(original_witness);schema=profile['native_schema'];namespace=schema['address_namespace']
                if case=='radix':namespace['regions']['BOOL'][1]['radix']=10
                elif case=='access':namespace['regions']['BOOL'][0]['access']='ReadWrite'
                elif case=='maximum':namespace['regions']['BOOL'][1]['maximum']=511
                elif case=='unknown_authority':namespace['authority_sha256']='0'*64
                else:namespace.update(contract_version=1,mode='source_driver_decimal_regions')
                witness['schema_sha256']=canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'})
                raw=json.dumps(witness).encode();witness_path.write_bytes(raw);schema['native_candidate']['sha256']=service_byte_hash(raw)
                profile_path.write_text(json.dumps(profile));service=FileService(self.root,profile_path.parent)
                with self.assertRaises(HmiError):service.open_project('source_controls_dvp_v2','library.dps')
                self.assertEqual(service.sessions,{})

    def test_new_registry_change_and_old_upgrade_dependency_are_fresh_before_output(self):
        plan=self.plan();self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan))
        self.radix_authority.write_bytes(self.radix_authority.read_bytes()+b' ')
        with self.assertRaises(HmiError) as ctx:self.service.save_as(self.session,'stale.dps')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'stale.dps').exists())
        original_write=FileService._write_new
        self.radix_authority.write_bytes((ROOT/'profiles/driver_contracts/delta_dvp_serial_radix_2016.json').read_bytes())
        def race(service,relative,data,verifier):
            self.authority_path.write_bytes(self.authority_path.read_bytes()+b' ')
            return original_write(service,relative,data,verifier)
        with patch.object(FileService,'_write_new',race),self.assertRaises(HmiError) as ctx:
            self.helper(self.root,'library.dps','dvp/profiles/source_controls_dvp_v1.json','race','TEST','delta_dvp_serial_radix_2016.json')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'race/control_calibration.json').exists())

    def test_authority_selector_is_typed_and_cannot_escape_or_downgrade_contract(self):
        for index,value in enumerate((None,[],{},True,'../foreign.json','other.json')):
            with self.subTest(value=value),self.assertRaises(HmiError):
                self.helper(self.root,'library.dps','dvp/profiles/source_controls_dvp_v1.json','invalid'+str(index),'TEST',value)
        with self.assertRaises(HmiError):self.helper(self.root,'library.dps',self.radix_profile_path,'downgrade','TEST')


class FixedDecimalServiceTests(unittest.TestCase):
    """Original byte fixtures and registered facts; not genuine vendor images."""
    plan=ControlGenerationServiceTests.plan
    approve=ControlGenerationServiceTests.approve

    def setUp(self):
        DriverNamespaceServiceTests.setUp(self)
        for name in ('blank.dps','library.dps'):
            native=NativeAdapter((self.root/name).read_bytes(),'delta_dopsoft2')
            document=deepcopy(native.document)
            document.sections[0].one('ModelName').set_value(b'2953863504')
            (self.root/name).write_bytes(native.envelope.encode(document.bytes()))
        self.target=(self.root/'blank.dps').read_bytes();self.library=(self.root/'library.dps').read_bytes()
        controls=runpy.run_path(str(ROOT/'scripts/calibrate_controls.py'))['calibrate']
        controls(self.root,'library.dps','delta_dopsoft2','properties.json','fixed-base','ORIGINAL TEST ONLY')
        namespace=runpy.run_path(str(ROOT/'scripts/calibrate_dvp_namespace.py'))['calibrate']
        namespace(self.root,'library.dps','fixed-base/profiles/source_controls_v1.json','fixed-dvp','ORIGINAL TEST ONLY')
        self.numeric_authorities=self.root/'numeric-authorities';self.numeric_authorities.mkdir()
        self.numeric_authority=self.numeric_authorities/'dopsoft2_b10_uint_presentation.json'
        self.numeric_authority.write_bytes((ROOT/'profiles/numeric_contracts/dopsoft2_b10_uint_presentation.json').read_bytes())
        redirect=patch.object(FileService,'_numeric_authority_dir',return_value=self.numeric_authorities)
        redirect.start();self.addCleanup(redirect.stop)
        self.fixed_helper=runpy.run_path(str(ROOT/'scripts/calibrate_fixed_decimal.py'))['calibrate']
        self.fixed_helper(self.root,'library.dps','fixed-dvp/profiles/source_controls_dvp_v1.json','fixed-display','TEST REVIEW')
        program=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        program(self.root,'blank.dps','library.dps','fixed-display/profiles/source_controls_fixed_decimal_v1.json','fixed-program','TEST SOURCE','TEST REVIEW')
        self.profile_dir=self.root/'fixed-program/profiles';self.service=FileService(self.root,self.profile_dir)
        self.session=self.service.open_project('blank_program_v1','blank.dps')['session_id']
        self.design['screens'][0]['elements'][5].update(value_model='integer_fixed_decimal',fractional=2,minimum=0,maximum=999)

    def test_display_model_saves_exact_dotnum_without_inventing_input_fields(self):
        receipt=self.plan();self.assertFalse(self.service.validate(self.session,receipt['plan_id'])['findings'])
        self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt));self.service.save_as(self.session,'fixed.dps')
        saved=NativeAdapter((self.root/'fixed.dps').read_bytes(),'delta_dopsoft2')
        display=saved.inspect()['screens'][0]['elements'][5]['native_fields']
        self.assertEqual((display['MemLen'],display['MemFmt'],display['IntNum'],display['DotNum']),('1','2','1','2'))
        self.assertNotIn('MinValue',display);self.assertNotIn('MaxValue',display)
        self.assertEqual((self.root/'blank.dps').read_bytes(),self.target);self.assertEqual((self.root/'library.dps').read_bytes(),self.library)

    def test_fractional_input_is_unqualified_even_after_common_feature_pass(self):
        for raw in (29,58,123,999):
            with self.subTest(raw=raw):
                design=deepcopy(self.design);design['screens'][0]['elements'][4].update(value_model='integer_fixed_decimal',fractional=2,minimum=0,maximum=raw)
                with self.assertRaises(HmiError) as caught:self.service.plan_changes(self.session,design,None,'unsafe'+str(raw))
                self.assertEqual(caught.exception.code,'UNQUALIFIED_FIXED_DECIMAL')

    def test_fixed_digits_cannot_exceed_source_unsigned_word_capacity(self):
        for fractional,maximum in ((5,999),(4,65535),(4,65536)):
            design=deepcopy(self.design);design['screens'][0]['elements'][5].update(fractional=fractional,maximum=maximum)
            if fractional==4 and maximum==65535:
                self.assertFalse(self.service.validate(self.session,self.service.plan_changes(self.session,design,None,'full-display')['plan_id'])['findings'])
            else:
                with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'bad-digits')

    def test_numeric_authority_change_blocks_save_and_both_helpers(self):
        receipt=self.plan();self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.numeric_authority.write_bytes(self.numeric_authority.read_bytes()+b' ')
        with self.assertRaises(HmiError) as caught:self.service.save_as(self.session,'stale-fixed.dps')
        self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'stale-fixed.dps').exists())
        program=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        with self.assertRaises(HmiError):program(self.root,'blank.dps','library.dps','fixed-display/profiles/source_controls_fixed_decimal_v1.json','stale-program','TEST','TEST')
        self.assertFalse((self.root/'stale-program').exists())

    def test_rehashed_authority_source_model_version_or_storage_drift_fails_before_session(self):
        profile_path=self.root/'fixed-display/profiles/source_controls_fixed_decimal_v1.json';base=json.loads(profile_path.read_bytes())
        witness_path=self.root/'fixed-display/control_calibration.json';witness_base=json.loads(witness_path.read_bytes())
        for variant in ('unregistered','source','model','version','storage','input_lowering'):
            with self.subTest(variant=variant):
                profile,witness=deepcopy(base),deepcopy(witness_base);schema=profile['native_schema'];descriptor=schema['numeric']['value_models']['integer_fixed_decimal']
                if variant=='unregistered':descriptor['authority_sha256']='0'*64
                elif variant=='source':descriptor['source_sha256']='0'*64
                elif variant=='model':profile['model_id']=1
                elif variant=='version':profile['editor_version']='4.00.07.05'
                elif variant=='storage':schema['numeric']['types']['UINT']['MemFmt']='1'
                else:descriptor['input_lowering']='OFFLINE_PASS'
                witness['schema_sha256']=canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'})
                raw=(json.dumps(witness)+'\n').encode();witness_path.write_bytes(raw);schema['native_candidate']['sha256']=service_byte_hash(raw)
                profile_path.write_text(json.dumps(profile));service=FileService(self.root,profile_path.parent)
                with self.assertRaises(HmiError):service.open_project('source_controls_fixed_decimal_v1','library.dps')
                self.assertEqual(service.sessions,{})

    def test_explicit_raw_model_keeps_native_operations_and_bytes_unchanged(self):
        design=deepcopy(self.design);design['screens'][0]['elements'][5].pop('value_model');design['screens'][0]['elements'][5]['fractional']=0
        first=self.service.plan_changes(self.session,design,None,'raw-default')
        design['screens'][0]['elements'][5]['value_model']='raw'
        second=self.service.plan_changes(self.session,design,None,'raw-explicit')
        self.assertEqual(first['operations'],second['operations'])
        self.assertEqual(self.service._emit(self.service._session(self.session),first['operations']),self.service._emit(self.service._session(self.session),second['operations']))

    def test_helper_missing_authority_during_save_is_typed_and_no_output_survives(self):
        original=FileService._write_new;opened=Path.open
        def failing_open(path,*args,**kwargs):
            if path==self.numeric_authority:raise FileNotFoundError('removed during numeric save')
            return opened(path,*args,**kwargs)
        def write(service,output,data,verifier):
            def verify(saved):
                with patch.object(Path,'open',new=failing_open):return verifier(saved)
            return original(service,output,data,verify)
        with patch.object(FileService,'_write_new',new=write),self.assertRaises(HmiError) as caught:
            self.fixed_helper(self.root,'library.dps','fixed-dvp/profiles/source_controls_dvp_v1.json','missing-numeric','TEST REVIEW')
        self.assertEqual(caught.exception.code,'CALIBRATION_CHANGED');self.assertEqual(list((self.root/'missing-numeric').rglob('*')),[])


class PortabilityTests(unittest.TestCase):
    def test_host_config_preserves_linked_venv_interpreter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_dir = root / 'base'
            base_dir.mkdir()
            base = base_dir / 'python'
            base.write_bytes(b'placeholder interpreter')
            link_dir = root / 'venv'
            try:
                link_dir.symlink_to(base_dir, target_is_directory=True)
            except OSError:
                if os.name != 'nt':
                    raise
                linked = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link_dir), str(base_dir)], capture_output=True)
                self.assertEqual(linked.returncode, 0, linked.stderr.decode(errors='replace'))
            link = link_dir / 'python'
            self.assertNotEqual(link.absolute(), link.resolve())
            for kind in ('json', 'codex'):
                output = io.StringIO()
                with patch.object(sys, 'executable', str(link)), patch.object(sys, 'argv',
                        ['configure_mcp.py', '--format', kind]), contextlib.redirect_stdout(output):
                    runpy.run_path(str(ROOT / 'scripts/configure_mcp.py'), run_name='__main__')
                config = json.loads(output.getvalue())['mcpServers']['universal-hmi'] if kind == 'json' else tomllib.loads(output.getvalue())['mcp_servers']['universal_hmi']
                self.assertEqual(config['command'], str(link.absolute()))

    def test_private_project_design_preview_and_approval_are_ignored(self):
        for relative in ('projects/private/design.json', 'projects/private/preview/R001.html',
                         'projects/private/approval.json', 'projects/private/inputs/source.dpa',
                         'projects/private/delivery/candidate.dps', 'projects/private/evidence/test.json'):
            with self.subTest(path=relative):
                checked = subprocess.run(['git', 'check-ignore', '--no-index', '--quiet', '--', relative], cwd=ROOT)
                self.assertEqual(checked.returncode, 0)
        checked = subprocess.run(['git', 'check-ignore', '--no-index', '--quiet', '--', 'projects/README.md'], cwd=ROOT)
        self.assertEqual(checked.returncode, 1)

    def test_runtime_and_client_examples_have_no_author_machine_dependency(self):
        for folder in ('src', 'tools', 'scripts'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file() and path.suffix in ('.py', '.ps1', '.sh', '.cjs', '.example'):
                    text = path.read_text(encoding='utf-8')
                    with self.subTest(path=path.relative_to(ROOT)):
                        self.assertNotRegex(text, r'(?i)(Users[/\\][^/\\]+|\b[A-Z]:[/\\])')
        generic = json.loads((ROOT / '.mcp.json.example').read_bytes())['mcpServers']['universal-hmi']
        codex = tomllib.loads((ROOT / 'scripts/codex_config.toml.example').read_text())['mcp_servers']['universal_hmi']
        for config in (generic, codex):
            self.assertEqual(config['command'], 'python')
            self.assertEqual(config['args'], ['-m', 'universal_hmi.cli', 'serve'])
        lock = (ROOT / 'requirements.lock').read_text()
        self.assertIn('pywin32==312; sys_platform == "win32"', lock)

    def test_default_registry_and_host_config_work_outside_checkout_cwd(self):
        with tempfile.TemporaryDirectory(prefix='Unrelated working directory ') as cwd:
            doctor = subprocess.run([sys.executable, '-m', 'universal_hmi.cli', 'doctor'], cwd=cwd, capture_output=True, text=True)
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            from universal_hmi.runtime_assets import profiles_root
            self.assertEqual(Path(json.loads(doctor.stdout)['profiles']), profiles_root())
            for kind in ('json', 'codex'):
                generated = subprocess.run([sys.executable, str(ROOT / 'scripts/configure_mcp.py'), '--format', kind], cwd=cwd, capture_output=True, text=True)
                self.assertEqual(generated.returncode, 0, generated.stderr)
                config = json.loads(generated.stdout)['mcpServers']['universal-hmi'] if kind == 'json' else tomllib.loads(generated.stdout)['mcp_servers']['universal_hmi']
                self.assertEqual(Path(config['command']), Path(sys.executable).absolute())
                self.assertEqual(Path(config['args'][-1]), ROOT / 'projects')


def transaction_fixture():
    source = synthetic_file()
    envelope = Envelope.decode(source, 'delta_diascreen')
    body = envelope.body.replace(b'FontColor=0\r\n', b'FontColor=0\r\nBgColor=1122867\r\n').replace(b'FontColor=1\r\n', b'FontColor=1\r\nBgColor=39253\r\n')
    # The neutral button donor has no executable behavior. Opaque/nonempty
    # macros in imported projects are preserved, never cloned undeclared.
    body = body.replace(b'BeforeExecMacroLen=4\r\nxx\r\n', b'BeforeExecMacroLen=0\r\n')
    return envelope.encode(body)


def numeric_transaction_fixture(family='delta_diascreen', kind='numeric_input', mem_len='2', mem_fmt='5'):
    """Original datatype donor, never a copied vendor fixture."""
    envelope = Envelope.decode(synthetic_file(family), family)
    prefix = envelope.body.split(b'[State]\r\n', 1)[0]
    tail = b'[SubMacro]' + envelope.body.split(b'[SubMacro]', 1)[1]
    prefix = prefix.replace(b'Type=1\r\nSubType=1', b'Type=' + (b'6' if kind == 'numeric_input' else b'5') + b'\r\nSubType=1')
    prefix = prefix.replace(b'WriteVar=!M1', b'WriteVar=!D1' if kind == 'numeric_input' else b'WriteVar=None')
    prefix += (b'MemLen=' + mem_len.encode() + b'\r\nMemFmt=' + mem_fmt.encode()
               + b'\r\nIntNum=3\r\nDotNum=1\r\nGainValue=1.0\r\nOffsetValue=0.0\r\n')
    if kind == 'numeric_input':
        prefix += b'MinValue=0\r\nMaxValue=999\r\n'
    return envelope.encode(prefix + b'[State]\r\nValue=0\r\nFontColor=0\r\n' + _wide('wTextLen0', '') + tail)


def layout_transaction_fixture(family='delta_diascreen'):
    """Wholly original object/layout donors with deliberately synthetic kinds."""
    adapter = NativeAdapter(transaction_fixture(), 'delta_diascreen')
    app, screen, auxiliary, button, off, on = [s.bytes() for s in adapter.document.sections]
    paint = b'Style=0\r\nTransEffect=0\r\nAutoResizeByText=0\r\nUseBMPText=0\r\n'
    font = b'FontSize0=12\r\nFontRatio0=100\r\nFontName0=Arial\r\nFontAlign=0\r\nFontBold=0\r\nFontItalic=0\r\nFontUnderline=0\r\n'
    def object_bytes(eid, kind, subtype, x, y, read, write, states, extra=b''):
        body = button.replace(b'nPartsID=1', b'nPartsID=' + str(eid).encode())
        body = body.replace(b'Type=1\r\nSubType=1', b'Type=' + str(kind).encode() + b'\r\nSubType=' + str(subtype).encode())
        body = body.replace(b'X=10\r\nY=20', f'X={x}\r\nY={y}'.encode())
        body = body.replace(b'ReadVar=!D1', b'ReadVar=' + read).replace(b'WriteVar=!M1', b'WriteVar=' + write)
        return body + paint + extra + b''.join(state + font for state in states)
    objects = object_bytes(1, 1, 1, 0, 0, b'!D1', b'!M1', [off, on])
    objects += object_bytes(2, 77, 1, 40, 0, b'None', b'None', [off])
    objects += object_bytes(3, 78, 1, 0, 30, b'!D1', b'None', [off, on])
    objects += object_bytes(4, 1, 10, 40, 30, b'None', b'None', [off], b'GoToScreenID=2\r\nGoToScreenName=Blank\r\n')
    blank = screen.replace(b'ID=1', b'ID=2').replace(_wide('wTextLen', 'Main'), _wide('wTextLen', 'Blank')) + auxiliary
    envelope = Envelope.decode(synthetic_file(family), family)
    return envelope.encode(app + screen + auxiliary + objects + blank + adapter.document.tail)


def unit_transaction_fixture(family='delta_diascreen', kind='numeric_input'):
    """Original synthetic identity conversion plus a separately owned label.

    Enum zeros here define this test specimen. They do not qualify vendor
    conversion enums, placement, fonts or pixels.
    """
    envelope = Envelope.decode(numeric_transaction_fixture(family, kind), family)
    controls = {
        'UnitType': '0', 'UnitSrc': '0', 'UnitSrcVar': 'None',
        'UnitDisplay': '0', 'UnitDisplayVar': 'None', 'UnitPercent': '0',
        'UnitPercent1Var': '0.0', 'UnitPercent2Var': '100.0',
        'UnitCustom1Var_1': '1.0', 'UnitCustom2Var_1': '0.0',
        'BackupUnitSrc': '0', 'BackupUnitDisplay': '0', 'ConvertConstByUnit': '0',
        'ShowUnit': '0', 'UnitDirection': '3', 'UnitFontSize0': '12',
        'UnitFontName0': 'Arial', 'UnitBold': '0', 'UnitItalic': '0',
        'UnitUnderline': '0', 'UnitFontColor': '0'}
    unit_bytes = b''.join(f'{k}={v}\r\n'.encode() for k, v in controls.items()) + _wide('UnitTextLen0', '')
    paint = b'Style=0\r\nTransEffect=0\r\nAutoResizeByText=0\r\nUseBMPText=0\r\n'
    font = b'FontSize0=12\r\nFontRatio0=100\r\nFontName0=Arial\r\nFontAlign=0\r\nFontBold=0\r\nFontItalic=0\r\nFontUnderline=0\r\nBgColor=1122867\r\n'
    layout = NativeAdapter(layout_transaction_fixture(family), family)
    label = b''.join(s.bytes() for s in layout.document.sections[6:8])
    label = label.replace(b'X=40\r\nY=0', b'X=50\r\nY=20').replace(b'Width=30', b'Width=40')
    body = envelope.body.replace(b'[State]\r\n', unit_bytes + paint + b'[State]\r\n', 1)
    body = body.replace(b'[SubMacro]', font + label + b'[SubMacro]', 1)
    body = body.replace(b'BeforeExecMacroLen=4\r\nxx\r\n', b'BeforeExecMacroLen=0\r\n')
    return envelope.encode(body)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile_dir = self.root / 'registry'
        self.profile_dir.mkdir()
        self.profile_id = 'synthetic_diascreen'
        self.profile = json.loads((ROOT / 'profiles' / (self.profile_id + '.json')).read_bytes())
        self.profile['resolution'] = [100, 80]
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        (self.root / 'source.dpa').write_bytes(transaction_fixture())
        self.service = FileService(self.root, self.profile_dir)
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        self.design = dict(schema_version=1, project_id='neutral', profile_id=self.profile_id,
            screens=[dict(id='main', native_id='1', name='Main', width=100, height=80, elements=[
                dict(id='switch', native_id='1', kind='button', x=10, y=20, width=30, height=20,
                     behavior='maintained', role='request', binding={'read': 'state', 'write': 'command'},
                     states=[dict(value=0, text='OFF', fill='#112233'), dict(value=1, text='ON', fill='#009955')])])],
            tags=[dict(id='state', address='!D1', data_type='BOOL', access='Read', channel='SIM', station='0', byte_order='little', word_order='little', native_binding={'link': '1', 'mem_type': '0'}),
                  dict(id='command', address='!M1', data_type='BOOL', access='ReadWrite', channel='SIM', station='0', byte_order='little', word_order='little', native_binding={'link': '1', 'mem_type': '0'})],
            macros=[], alarms=[])
        self.ops = [dict(op='set_property', screen_id='1', element_id='1', key='behavior', value='maintained')]

    def plan(self, key='once', design=None, ops=None):
        return self.service.plan_changes(self.session, self.design if design is None else design,
                                         self.ops if ops is None else ops, key)

    def approve(self, receipt, path='approval.json'):
        approval = {key: value for key, value in receipt.items() if key.endswith('_sha256')}
        approval.update(approved=True, authority='neutral_fixture_qualification', purpose='qualification_only')
        (self.root / path).write_text(json.dumps(approval))
        return path

    def use_alarms(self, family='delta_diascreen'):
        self.profile_id = 'synthetic_diascreen' if family == 'delta_diascreen' else 'synthetic_dopsoft2'
        self.profile = json.loads((ROOT / 'profiles' / (self.profile_id + '.json')).read_bytes())
        self.alarm_source, schema, alarms, tags = alarm_public_fixture(family)
        self.profile.update(resolution=[100, 80], native_schema=schema)
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        extension = '.dpa' if family == 'delta_diascreen' else '.dps'
        self.alarm_path = 'alarms' + extension
        (self.root / self.alarm_path).write_bytes(self.alarm_source)
        self.session = self.service.open_project(self.profile_id, self.alarm_path)['session_id']
        source = NativeAdapter(self.alarm_source, family).inspect()['screens'][0]
        kinds = {'1': 'alarm_history', '2': 'alarm_table', '4': 'alarm_strip'}
        elements = [dict(id='view-' + e['id'], native_id=e['id'], kind=kinds[e['subtype']],
                         **e['geometry'], text='', view_policy='preserve_source') for e in source['elements']]
        self.design = dict(schema_version=1, project_id='neutral-alarms', profile_id=self.profile_id,
                           screens=[dict(id='alarms', native_id='1', name=source['name'], width=100, height=80,
                                         elements=elements)], tags=tags, macros=[], alarms=alarms)
        return extension

    def test_public_alarm_exact_noop_and_message_transaction_both_envelopes(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                extension = self.use_alarms(family)
                receipt = self.service.plan_changes(self.session, self.design, None, 'alarm-noop-' + family)
                self.assertEqual(receipt['findings'], [])
                self.assertEqual(receipt['operations'], [])
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertEqual(self.service.sessions[self.session]['applied']['data'], self.alarm_source)
                self.design['alarms'][0]['text'] = 'E001 — Basınç düşük'
                self.design['alarms'][1]['text'] = 'E002 — Kapak açık'
                receipt = self.service.plan_changes(self.session, self.design, None, 'alarm-changed-' + family)
                self.assertEqual(receipt['findings'], [])
                self.assertEqual([op['op'] for op in receipt['operations']], ['configure_alarm'])
                approval = self.approve(receipt)
                applied = self.service.apply_plan(self.session, receipt['plan_id'], approval)
                self.assertEqual(applied, self.service.apply_plan(self.session, receipt['plan_id'], approval))
                output = 'alarm-candidate' + extension
                saved = self.service.save_as(self.session, output)
                actual = NativeAdapter((self.root / output).read_bytes(), family)
                original = NativeAdapter(self.alarm_source, family)
                before, after = ResourceTables.parse(original.document.tail), ResourceTables.parse(actual.document.tail)
                self.assertEqual(after.alarm.one('wMessageLen001-0').text(), self.design['alarms'][0]['text'])
                self.assertEqual(after.alarm.one('wMessageLen002-0').text(), self.design['alarms'][1]['text'])
                changed = {'wMessageLen001-0', 'wMessageLen002-0'}
                self.assertEqual([r.raw for r in before.alarm.records if r.key not in changed],
                                 [r.raw for r in after.alarm.records if r.key not in changed])
                self.assertEqual((before.prefix, before.suffix), (after.prefix, after.suffix))
                self.assertEqual(actual.envelope.prefix, original.envelope.prefix)
                for eid in ('10', '11', '12'):
                    self.assertEqual(alarm_view_context(actual.document, '1', eid),
                                     alarm_view_context(original.document, '1', eid))
                self.assertEqual((self.root / self.alarm_path).read_bytes(), self.alarm_source)
                self.assertEqual(saved['sha256'], self.service.diff(self.session)['candidate_sha256'])
                self.assertEqual(applied['production_native'], 'UNAVAILABLE')
                self.assertEqual(applied['native_visual'], 'NOT_RUN')

    def test_public_alarm_views_clone_only_geometry_with_raw_states_preserved(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                extension = self.use_alarms(family)
                elements = self.design['screens'][0]['elements']
                for i, e in enumerate(elements):
                    e.update(x=5, y=5 + 20*i, width=35, height=15)
                for i, e in enumerate(deepcopy(elements)):
                    e.update(id=e['id'] + '-clone', native_id=str(25+i), x=55)
                    elements.append(e)
                receipt = self.service.plan_changes(self.session, self.design, None, 'alarm-clone-' + family)
                self.assertEqual(receipt['findings'], [])
                self.assertEqual(sum(op['op'] == 'clone_element' for op in receipt['operations']), 3)
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.service.save_as(self.session, 'alarm-clones' + extension)
                candidate = NativeAdapter((self.root / ('alarm-clones' + extension)).read_bytes(), family)
                source = NativeAdapter(self.alarm_source, family)
                for original_id, clone_id in zip(('10', '11', '12'), ('25', '26', '27')):
                    self.assertEqual(alarm_view_context(source.document, '1', original_id)['immutable_sha256'],
                                     alarm_view_context(candidate.document, '1', clone_id)['immutable_sha256'])
                self.assertEqual(candidate.document.tail, source.document.tail)

    def test_explicit_alarm_noop_cannot_omit_changed_message(self):
        self.use_alarms()
        self.design['alarms'][0]['text'] = 'New alarm'
        receipt = self.service.plan_changes(self.session, self.design, [], 'omitted-alarm')
        validation = self.service.validate(self.session, receipt['plan_id'])
        self.assertFalse(validation['offline_pass'])
        self.assertIn('NATIVE_ALARM_OPERATION_COVERAGE', [f['code'] for f in validation['findings']])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'VALIDATION')
        self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_changed_alarm_operation_must_be_exactly_one_and_final_tail_still_checked(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                self.use_alarms(family)
                self.design['alarms'][0]['text'] = 'Approved new message'
                receipt = self.service.plan_changes(self.session, self.design, None, 'single')
                duplicate = self.service.plan_changes(self.session, self.design, receipt['operations']*2, 'duplicate')
                self.assertIn('NATIVE_ALARM_OPERATION_COVERAGE', [f['code'] for f in
                              self.service.validate(self.session, duplicate['plan_id'])['findings']])
                source = NativeAdapter(self.alarm_source, family)
                # Final verification is independent of explicit operation coverage.
                with self.assertRaises(HmiError) as caught:
                    self.service._native_matches(self.service.sessions[self.session], self.design, source.inspect(), source)
                self.assertEqual(caught.exception.code, 'UNDECLARED_RESOURCE_CHANGE')

    def test_explicit_alarm_operation_cannot_change_trigger_history_or_foreign_text(self):
        for field, value in (('Hold', 1), ('AlarmVar001', 'OTHER.ADDRESS'), ('AlarmEnable003', 1),
                             ('wMessageLen001-1', 'Other'), ('wMessageLen003-0', 'Disabled')):
            with self.subTest(field=field):
                self.use_alarms()
                self.design['alarms'][0]['text'] = 'Approved text'
                receipt = self.service.plan_changes(self.session, self.design, None, 'approved-' + field)
                operation = deepcopy(receipt['operations'][0])
                operation['updates'].append(dict(field=field, value=value))
                rejected = self.service.plan_changes(self.session, self.design, [operation], 'malicious-' + field)
                validation = self.service.validate(self.session, rejected['plan_id'])
                self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in validation['findings']])
                with self.assertRaises(HmiError):
                    self.service.apply_plan(self.session, rejected['plan_id'], self.approve(rejected))
                self.assertEqual((self.root / self.alarm_path).read_bytes(), self.alarm_source)

    def test_source_preserved_view_rejects_style_text_binding_and_wrong_clone(self):
        operations = [dict(op='set_text', screen_id='1', element_id='10', text='Hidden', language=0, state_index=0),
                      dict(op='bind_address', screen_id='1', element_id='10', direction='write', address='DEMO.ALARM_A'),
                      dict(op='set_property', screen_id='1', element_id='10', key='color', value=12)]
        for i, operation in enumerate(operations):
            with self.subTest(operation=operation):
                self.use_alarms()
                receipt = self.service.plan_changes(self.session, self.design, [operation], 'view-intent-' + str(i))
                validation = self.service.validate(self.session, receipt['plan_id'])
                self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in validation['findings']])
                with self.assertRaises(HmiError):
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.use_alarms()
        extra = deepcopy(self.design['screens'][0]['elements'][0])
        extra.update(id='extra', native_id='25', x=5, y=72, width=90, height=5)
        self.design['screens'][0]['elements'].append(extra)
        receipt = self.service.plan_changes(self.session, self.design, [dict(op='clone_element', source_screen='1', source_element='11',
            target_screen='1', element_id='25')], 'wrong-view-donor')
        validation = self.service.validate(self.session, receipt['plan_id'])
        self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in validation['findings']])
        with self.assertRaises(HmiError):
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))

    def test_saved_alarm_presentation_and_unrelated_tail_drift_rejected(self):
        changes = [(b'ColWidth0=70', b'ColWidth0=71'), (b'TimeFmt=0', b'TimeFmt=2'),
                   (_wide('TitleTextLen0-1', 'Other title'), _wide('TitleTextLen0-1', 'Changed title')),
                   (b'StateUnknown=retained', b'StateUnknown=changed'),
                   (b'X=777', b'X=778'), (b'Unknown=A', b'Unknown=C'),
                   (b'Hold001=1', b'Hold001=0')]
        for i, (old, new) in enumerate(changes):
            with self.subTest(change=old):
                self.use_alarms()
                receipt = self.service.plan_changes(self.session, self.design, None, 'drift-' + str(i))
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                applied = self.service.sessions[self.session]['applied']
                envelope = Envelope.decode(applied['data'], 'delta_diascreen')
                self.assertIn(old, envelope.body)
                applied['data'] = envelope.encode(envelope.body.replace(old, new, 1))
                with self.assertRaises(HmiError):
                    self.service.save_as(self.session, 'drift.dpa')
                self.assertFalse((self.root / 'drift.dpa').exists())
                self.assertEqual(list(self.root.glob('.uhmi-*')), [])
                self.assertEqual((self.root / self.alarm_path).read_bytes(), self.alarm_source)

    def test_alarm_view_original_deletion_kind_and_owner_provenance_rejected(self):
        for case in ('delete', 'kind', 'sha', 'duplicate', 'no-policy'):
            with self.subTest(case=case):
                self.use_alarms()
                e = self.design['screens'][0]['elements'][0]
                if case == 'delete': self.design['screens'][0]['elements'].pop(0)
                elif case == 'kind': e['kind'] = 'alarm_history'
                elif case == 'sha': self.profile['native_schema']['alarm_views']['owners'][0]['owner_sha256'] = '0'*64
                elif case == 'duplicate': self.profile['native_schema']['alarm_views']['owners'].append(deepcopy(self.profile['native_schema']['alarm_views']['owners'][0]))
                else: e.pop('view_policy')
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.alarm_path)['session_id']
                with self.assertRaises(HmiError):
                    self.service.plan_changes(self.session, self.design, None, case)

    def test_alarm_tag_relation_and_contract_change_revokes_approval(self):
        self.use_alarms()
        receipt = self.service.plan_changes(self.session, self.design, None, 'relation')
        approved = self.approve(receipt)
        self.design['alarms'][0]['id'], self.design['alarms'][1]['id'] = self.design['alarms'][1]['id'], self.design['alarms'][0]['id']
        with self.assertRaises(HmiError):
            self.service.plan_changes(self.session, self.design, None, 'wrong-relation')
        # An actual source modification after approval invalidates the session.
        (self.root / self.alarm_path).write_bytes(self.alarm_source + b'changed')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], approved)
        self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')

    def test_alarm_history_semantics_not_inferred_and_empty_coverage_not_bypassed(self):
        for case in ('retain', 'clear_on_restart', 'empty', 'unqualified'):
            with self.subTest(case=case):
                self.use_alarms()
                if case == 'empty': self.design['alarms'] = []
                elif case == 'unqualified': self.profile['native_schema'].pop('alarm_ir')
                else: self.design['alarms'][0]['history_policy'] = case
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.alarm_path)['session_id']
                with self.assertRaises(HmiError):
                    self.service.plan_changes(self.session, self.design, None, case)

    def test_malformed_alarm_kind_and_donor_maps_close_with_typed_errors(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            for mapping in ('kinds', 'donors'):
                for bad in (None, []):
                    for automatic in (True, False):
                        with self.subTest(family=family, mapping=mapping, bad=bad, automatic=automatic):
                            self.use_alarms(family)
                            if mapping == 'donors':
                                extra = deepcopy(self.design['screens'][0]['elements'][0])
                                extra.update(id='extra', native_id='25', y=72, width=90, height=5)
                                self.design['screens'][0]['elements'].append(extra)
                            self.profile['native_schema'][mapping] = bad
                            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                            self.session = self.service.open_project(self.profile_id, self.alarm_path)['session_id']
                            expected = 'NATIVE_ALARM_VIEW_UNVERIFIED' if mapping == 'kinds' else 'NATIVE_DONOR_REQUIRED'
                            if automatic:
                                with self.assertRaises(HmiError) as caught:
                                    self.service.plan_changes(self.session, self.design, None, 'bad-map')
                                self.assertEqual(caught.exception.code, expected)
                            else:
                                receipt = self.service.plan_changes(self.session, self.design, [], 'bad-map')
                                validation = self.service.validate(self.session, receipt['plan_id'])
                                self.assertIn(expected, [f['code'] for f in validation['findings']])
                                with self.assertRaises(HmiError):
                                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                            self.assertIsNone(self.service.sessions[self.session]['applied'])
                            adapter = NativeAdapter(self.alarm_source, family)
                            with self.assertRaises(HmiError) as caught:
                                self.service._native_matches(self.service.sessions[self.session], self.design,
                                                             adapter.inspect(), adapter)
                            self.assertEqual(caught.exception.code, expected)

    def use_layout(self, family='delta_diascreen'):
        self.profile_id = 'synthetic_diascreen' if family == 'delta_diascreen' else 'synthetic_dopsoft2'
        self.profile = json.loads((ROOT / 'profiles' / (self.profile_id + '.json')).read_bytes())
        self.profile['resolution'] = [100, 80]
        schema = self.profile['native_schema']
        schema['structure'] = dict(qualified=True, rename_screen={'field': 'wTextLen'},
            reorder_elements={'ordering': 'section-sequence', 'extent': 'element-and-states'},
            reorder_screens={'ordering': 'section-sequence', 'extent': 'screen-and-elements'})
        schema['screen_donor'] = {'screen_id': '2'}
        schema['kinds'].update(text={'Type': '77', 'SubType': '1'}, indicator={'Type': '78', 'SubType': '1'}, goto={'Type': '1', 'SubType': '10'})
        schema['state_values'].update(text=[0], indicator=[0, 1], goto=[0])
        schema['donors'] = {kind: {'screen_id': '1', 'element_id': str(index)} for kind, index in [('button', 1), ('text', 2), ('indicator', 3), ('goto', 4)]}
        schema['navigation'] = dict(qualified=True, match=schema['kinds']['goto'], field='GoToScreenID', name_field='GoToScreenName', name_encoding='ascii')
        schema['properties']['font_size'] = dict(field='FontSize0', scope='state', type='int', min=6, max=96)
        schema['properties']['fill'] = dict(field='BgColor', scope='state', type='int', min=0, max=0xFFFFFF)
        schema['visual'] = dict(qualified=True,
            font_size={'field': 'FontSize0', 'scope': 'state', 'scale': 1},
            color={'field': 'FontColor', 'scope': 'state', 'encoding': 'rgb24'},
            fill={'field': 'BgColor', 'scope': 'state', 'encoding': 'rgb24'},
            companions={'element': {'Style': '0', 'TransEffect': '0', 'AutoResizeByText': '0', 'UseBMPText': '0'},
                'state': {'FontRatio0': '100', 'FontName0': 'Arial', 'FontAlign': '0', 'FontBold': '0', 'FontItalic': '0', 'FontUnderline': '0'}})
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.layout_source = layout_transaction_fixture(family)
        extension = '.dpa' if family == 'delta_diascreen' else '.dps'
        self.layout_path = 'layout' + extension
        (self.root / self.layout_path).write_bytes(self.layout_source)
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        self.design['profile_id'] = self.profile_id
        button = deepcopy(self.design['screens'][0]['elements'][0])
        button.update(x=0, y=0, font_size=14, color='#ffffff')
        text = dict(id='label', native_id='2', kind='text', x=40, y=0, width=30, height=20,
                    text='Ölçüm', font_size=12, color='#aabbcc', fill='#112233')
        indicator = dict(id='feedback', native_id='3', kind='indicator', x=0, y=30, width=30, height=20,
                         binding={'read': 'state'}, role='feedback', states=deepcopy(button['states']))
        goto = dict(id='navigation', native_id='4', kind='goto', x=40, y=30, width=30, height=20,
                    text='NEXT', target_screen='blank', font_size=12, color='#ffffff', fill='#112233')
        self.design['screens'] = [dict(id='main', native_id='1', name='Main', width=100, height=80, elements=[button, text, indicator, goto]),
                                  dict(id='blank', native_id='2', name='Blank', width=100, height=80, elements=[])]
        return extension

    def test_automatic_pages_labels_indicators_navigation_and_style_both_envelopes(self):
        base = deepcopy(self.design)
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                self.design = deepcopy(base)
                extension = self.use_layout(family)
                main, blank = self.design['screens']
                main['name'] = 'Home'
                detail = deepcopy(main)
                detail.update(id='detail', native_id='3', name='Detail')
                for e in detail['elements']:
                    e['id'] += '-detail'
                    e['native_id'] = str(int(e['native_id']) + 10)
                detail['elements'][-1]['target_screen'] = 'main'
                # Pure order change, no text overlap or guessed native Order.
                main['elements'] = list(reversed(main['elements']))
                self.design['screens'] = [detail, main, blank]
                receipt = self.service.plan_changes(self.session, self.design, None, family)
                self.assertEqual(receipt['findings'], [])
                operations = receipt['operations']
                self.assertEqual(operations[0]['op'], 'clone_screen')
                self.assertEqual(sum(op['op'] == 'clone_element' for op in operations), 4)
                approval = self.approve(receipt)
                applied = self.service.apply_plan(self.session, receipt['plan_id'], approval)
                self.assertEqual(self.service.apply_plan(self.session, receipt['plan_id'], approval), applied)
                path = 'layout-candidate' + extension
                saved = self.service.save_as(self.session, path)
                actual = NativeAdapter((self.root / path).read_bytes(), family)
                inventory = actual.inspect()
                self.assertEqual([s['id'] for s in inventory['screens']], ['3', '1', '2'])
                self.assertEqual([e['id'] for e in inventory['screens'][1]['elements']], ['4', '3', '2', '1'])
                elements = {e['id']: e for e in inventory['screens'][0]['elements']}
                self.assertEqual(elements['12']['texts'][0]['text'], 'Ölçüm')
                self.assertEqual(elements['12']['states'][0]['native_fields']['FontSize0'], '12')
                self.assertEqual(elements['12']['states'][0]['native_fields']['FontColor'], str(0xaabbcc))
                self.assertEqual(elements['14']['native_fields']['GoToScreenID'], '1')
                self.assertEqual(elements['14']['native_fields']['GoToScreenName'], 'Home')
                self.assertEqual(elements['13']['bindings']['write']['address'], 'None')
                source = NativeAdapter(self.layout_source, family)
                self.assertEqual(actual.document.tail, source.document.tail)
                self.assertEqual(actual.envelope.prefix, source.envelope.prefix)
                self.assertEqual((self.root / self.layout_path).read_bytes(), self.layout_source)
                self.assertEqual(applied['native_visual'], 'NOT_RUN')
                self.assertEqual(saved['sha256'], service_byte_hash((self.root / path).read_bytes()))

    def test_automatic_renamed_page_navigation_has_consistent_companion(self):
        self.use_layout()
        self.design['screens'][1]['name'] = 'Settings'
        receipt = self.service.plan_changes(self.session, self.design, None, 'rename-target')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        e = self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements'][-1]
        self.assertEqual(e['native_fields']['GoToScreenName'], 'Settings')

    def test_colorref24_is_explicit_and_channels_are_not_swapped(self):
        self.use_layout()
        schema = self.profile['native_schema']
        schema['state_fill']['encoding'] = 'colorref24'
        schema['visual']['color']['encoding'] = 'colorref24'
        schema['visual']['fill']['encoding'] = 'colorref24'
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        self.design['screens'][0]['elements'][1].update(color='#409bee', fill='#004080')
        receipt = self.service.plan_changes(self.session, self.design, None, 'colorref')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        elements = self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements']
        fields = elements[1]['states'][0]['native_fields']
        self.assertEqual(fields['FontColor'], str(0xee9b40))
        self.assertEqual(fields['BgColor'], str(0x804000))
        self.assertEqual(elements[0]['states'][0]['native_fields']['BgColor'], str(0x332211))
        self.assertEqual(FileService._native_color('#000000', 'colorref24'), 0)
        self.assertEqual(FileService._native_color('#ffffff', 'colorref24'), 0xffffff)
        with self.assertRaises(HmiError):
            FileService._native_color('#409bee', 'inferred')

    def test_native_captions_cannot_be_inherited_when_omitted_from_intent(self):
        for kind in ('text', 'goto', 'numeric_input'):
            if kind == 'numeric_input':
                self.use_numeric()
                envelope = Envelope.decode(self.numeric_source, 'delta_diascreen')
                source = envelope.encode(envelope.body.replace(_wide('wTextLen0', ''), _wide('wTextLen0', 'OLD LABEL')))
                (self.root / 'numeric.dpa').write_bytes(source)
                self.session = self.service.open_project(self.profile_id, 'numeric.dpa')['session_id']
            else:
                self.use_layout()
                next(e for e in self.design['screens'][0]['elements'] if e['kind'] == kind).pop('text')
            with self.subTest(kind=kind), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, self.design, None, kind)

    def test_new_page_requires_empty_inert_source_local_donor(self):
        for scenario in ('absent', 'nonempty', 'macro', 'scheduled'):
            with self.subTest(scenario=scenario):
                self.use_layout()
                self.design['screens'].append(dict(id='new', native_id='3', name='New', width=100, height=80, elements=[]))
                if scenario == 'absent':
                    self.profile['native_schema'].pop('screen_donor')
                elif scenario == 'nonempty':
                    self.profile['native_schema']['screen_donor']['screen_id'] = '1'
                else:
                    envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
                    marker = _wide('wTextLen', 'Blank')
                    extra = b'OpenMacroLen=4\r\nxx\r\n' if scenario == 'macro' else b'CycleMacroLen=0\r\nCycleMacroDelayTime=100\r\n'
                    (self.root / self.layout_path).write_bytes(envelope.encode(envelope.body.replace(marker, marker + extra)))
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
                with self.assertRaises(HmiError):
                    self.service.plan_changes(self.session, self.design, None, scenario)
                self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_new_page_donor_cannot_be_a_page_created_in_same_transaction(self):
        self.use_layout()
        self.profile['native_schema']['screen_donor']['screen_id'] = '3'
        self.design['screens'].extend(dict(id='page-' + str(i), native_id=str(i), name='New', width=100, height=80, elements=[]) for i in (3, 4))
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        with self.assertRaises(HmiError) as caught:
            self.service.plan_changes(self.session, self.design, None, 'created-donor')
        self.assertEqual(caught.exception.code, 'NATIVE_SCREEN_DONOR_UNSAFE')

    def test_structural_native_plan_cannot_omit_source_pages(self):
        self.use_layout()
        self.design['screens'].pop()
        self.design['screens'][0]['elements'][-1]['target_screen'] = 'main'
        with self.assertRaises(HmiError) as caught:
            self.service.plan_changes(self.session, self.design, None, 'page-deletion')
        self.assertEqual(caught.exception.code, 'NATIVE_SCREEN_PLAN_UNVERIFIED')

    def test_explicit_plan_cannot_hide_style_or_navigation_companion_changes(self):
        for scenario in ('font', 'color', 'fill', 'name'):
            self.use_layout()
            receipt = self.service.plan_changes(self.session, self.design, None, 'complete-' + scenario)
            operations = deepcopy(receipt['operations'])
            if scenario == 'name':
                operations = [op for op in operations if op['op'] != 'configure_goto']
                # A saved inconsistent companion must fail even without a goto op.
                envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
                altered = envelope.encode(envelope.body.replace(b'GoToScreenName=Blank', b'GoToScreenName=Wrong'))
                (self.root / self.layout_path).write_bytes(altered)
                self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            else:
                key = {'font': 'font_size', 'color': 'color', 'fill': 'fill'}[scenario]
                operations = [op for op in operations if not (op['op'] == 'set_property' and op.get('element_id') == '2' and op.get('key') == key)]
                if scenario == 'font':
                    self.design['screens'][0]['elements'][1]['font_size'] = 15
                elif scenario == 'fill':
                    self.design['screens'][0]['elements'][1]['fill'] = '#223344'
            receipt = self.plan(scenario, self.design, operations)
            with self.subTest(scenario=scenario), self.assertRaises(HmiError):
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_visual_mapping_companions_scale_alpha_and_unknown_features_reject(self):
        for scenario in ('no-baseline', 'ratio', 'scale', 'field', 'missing', 'alpha', 'image', 'gradient'):
            self.use_layout()
            visual = self.profile['native_schema']['visual']
            if scenario == 'no-baseline':
                visual.pop('companions')
            elif scenario == 'scale':
                visual['font_size']['scale'] = 2
            elif scenario == 'field':
                visual['font_size']['field'] = 'FontSize'
            elif scenario == 'alpha':
                self.design['screens'][0]['elements'][1]['color'] = '#ffffff80'
            else:
                envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
                body = envelope.body
                if scenario == 'ratio':
                    body = body.replace(b'FontRatio0=100', b'FontRatio0=50')
                elif scenario == 'missing':
                    body = body.replace(b'FontSize0=12\r\n', b'')
                elif scenario == 'image':
                    body = body.replace(b'Style=0\r\n', b'Style=0\r\nPicture Name=hidden image\r\n')
                else:
                    body = body.replace(b'Style=0\r\n', b'Style=0\r\nGradFillMode=3\r\n')
                (self.root / self.layout_path).write_bytes(envelope.encode(body))
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            with self.subTest(scenario=scenario), self.assertRaises(HmiError) as caught:
                self.service.plan_changes(self.session, self.design, None, scenario)
            self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')

    def test_new_noncommand_objects_reject_hidden_donor_write_binding_or_macro(self):
        for scenario in ('write', 'macro'):
            self.use_layout()
            extra = deepcopy(self.design['screens'][0]['elements'][1])
            extra.update(id='extra-label', native_id='9', x=40, y=60)
            self.design['screens'][0]['elements'].append(extra)
            envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
            marker = b'nPartsID=2\r\n'
            # Only the source text owner is altered; other donors stay intact.
            begin = envelope.body.index(marker)
            end = envelope.body.index(b'[Element]', begin)
            owner = envelope.body[begin:end]
            owner = owner.replace(b'WriteVar=None', b'WriteVar=!M1') if scenario == 'write' else owner.replace(b'BeforeExecMacroLen=0\r\n', b'BeforeExecMacroLen=4\r\nxx\r\n')
            (self.root / self.layout_path).write_bytes(envelope.encode(envelope.body[:begin] + owner + envelope.body[end:]))
            self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            with self.subTest(scenario=scenario), self.assertRaises(HmiError):
                receipt = self.service.plan_changes(self.session, self.design, None, scenario)
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_new_page_background_and_lock_rejected_for_automatic_and_explicit_plans(self):
        for field in (b'BaseScreenID=1\r\n', b'ScreenLockVar=!M1\r\n'):
            for automatic in (True, False):
                with self.subTest(field=field, automatic=automatic):
                    self.use_layout()
                    self.design['screens'].append(dict(id='new', native_id='3', name='New', width=100, height=80, elements=[]))
                    envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
                    source = envelope.encode(envelope.body.replace(_wide('wTextLen', 'Blank'), _wide('wTextLen', 'Blank') + field))
                    (self.root / self.layout_path).write_bytes(source)
                    self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
                    with self.assertRaises(HmiError) as caught:
                        operations = None if automatic else [dict(op='clone_screen', source_screen='2', screen_id='3', name='New')]
                        receipt = self.service.plan_changes(self.session, self.design, operations, 'unsafe-page')
                        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                    self.assertEqual(caught.exception.code, 'UNQUALIFIED_PAGE_BASELINE')
                    self.assertEqual((self.root / self.layout_path).read_bytes(), source)
                    self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_saved_new_page_cannot_gain_undeclared_page_baseline(self):
        self.use_layout()
        self.design['screens'].append(dict(id='new', native_id='3', name='New', width=100, height=80, elements=[]))
        receipt = self.service.plan_changes(self.session, self.design, None, 'new-page')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        applied = self.service.sessions[self.session]['applied']['data']
        envelope = Envelope.decode(applied, 'delta_diascreen')
        candidate = NativeAdapter(envelope.encode(envelope.body.replace(_wide('wTextLen', 'New'), _wide('wTextLen', 'New') + b'BaseScreenID=1\r\n')), 'delta_diascreen')
        with self.assertRaises(HmiError) as caught:
            self.service._native_matches(self.service.sessions[self.session], self.design, candidate.inspect(), candidate)
        self.assertEqual(caught.exception.code, 'UNQUALIFIED_PAGE_BASELINE')

    def test_state_only_indicator_fill_checks_appearance_even_for_exact_noop(self):
        for field in (b'GradFillMode=3\r\n', b'Picture Name=hidden-image\r\n', b'PIB Index=7\r\n', b'BtnPictureStretch=1\r\n', b'nAngle=90\r\n', b'VisibleVar=!M1\r\n', b'BtnTransColor=255\r\n'):
            self.use_layout()
            receipt = self.service.plan_changes(self.session, self.design, None, 'canonical')
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            envelope = Envelope.decode(self.service.sessions[self.session]['applied']['data'], 'delta_diascreen')
            # Other owners are already exactly equal to design. Only the
            # state-fill-only feedback indicator gains competing appearance.
            source = envelope.encode(envelope.body.replace(b'nPartsID=3\r\n', b'nPartsID=3\r\n' + field))
            (self.root / self.layout_path).write_bytes(source)
            self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            for automatic in (True, False):
                with self.subTest(field=field, automatic=automatic), self.assertRaises(HmiError) as caught:
                    receipt = self.service.plan_changes(self.session, self.design, None if automatic else [], str(automatic))
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')
                self.assertIsNone(self.service.sessions[self.session]['applied'])
            self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_kind_prefixed_numeric_appearance_cannot_bypass_companion_contract(self):
        for field in (b'NumBgOpacity=0\r\n', b'FieldFontSize=32\r\n', b'TargetOpacity=0\r\n', b'KPBkgndColor000=255\r\n', b'TitleHeight=10\r\n'):
            self.use_numeric(data_type='REAL')
            schema = self.profile['native_schema']
            schema['visual'] = dict(qualified=True, color={'field': 'FontColor', 'scope': 'state', 'encoding': 'rgb24'}, companions={'element': {}, 'state': {}})
            self.design['screens'][0]['elements'][0]['color'] = '#000000'
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            path = 'numeric.dpa'
            envelope = Envelope.decode((self.root / path).read_bytes(), 'delta_diascreen')
            source = envelope.encode(envelope.body.replace(b'nPartsID=1\r\n', b'nPartsID=1\r\n' + field))
            (self.root / path).write_bytes(source)
            self.session = self.service.open_project(self.profile_id, path)['session_id']
            for automatic in (True, False):
                with self.subTest(field=field, automatic=automatic), self.assertRaises(HmiError) as caught:
                    receipt = self.service.plan_changes(self.session, self.design, None if automatic else [], str(automatic))
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')
                self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_unstyled_text_and_numeric_objects_still_check_competing_appearance(self):
        for kind in ('text', 'numeric'):
            if kind == 'text':
                self.use_layout()
                label = self.design['screens'][0]['elements'][1]
                for key in ('color', 'font_size', 'fill'):
                    label.pop(key)
                path, marker = self.layout_path, b'nPartsID=2\r\n'
            else:
                self.use_numeric()
                path, marker = self.numeric_source_path, b'nPartsID=1\r\n'
            receipt = self.service.plan_changes(self.session, self.design, None, 'canonical')
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            envelope = Envelope.decode(self.service.sessions[self.session]['applied']['data'], 'delta_diascreen')
            source = envelope.encode(envelope.body.replace(marker, marker + b'PictureOffset=100\r\n'))
            (self.root / path).write_bytes(source)
            self.session = self.service.open_project(self.profile_id, path)['session_id']
            for automatic in (True, False):
                with self.subTest(kind=kind, automatic=automatic), self.assertRaises(HmiError) as caught:
                    receipt = self.service.plan_changes(self.session, self.design, None if automatic else [], str(automatic))
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')
            self.assertEqual((self.root / path).read_bytes(), source)

    def test_visual_schema_cannot_exempt_unqualified_appearance_through_extra_mapping(self):
        self.use_layout()
        self.profile['native_schema']['visual']['extra'] = {'field': 'GradFillMode', 'scope': 'element'}
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        with self.assertRaises(HmiError) as caught:
            self.service.plan_changes(self.session, self.design, None, 'extra-visual')
        self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')

    def test_competing_order_rejected_without_reorder_in_append_and_explicit_noop(self):
        for owner in ('screen', 'element', 'state'):
            for append in (True, False):
                self.use_layout()
                if append:
                    extra = deepcopy(self.design['screens'][0]['elements'][1])
                    extra.update(id='extra', native_id='9', x=40, y=60)
                    self.design['screens'][0]['elements'].append(extra)
                envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
                marker = {'screen': _wide('wTextLen', 'Main'), 'element': b'nPartsID=2\r\n', 'state': b'[State]\r\nValue=0\r\n'}[owner]
                source = envelope.encode(envelope.body.replace(marker, marker + b'Order=0\r\n', 1))
                (self.root / self.layout_path).write_bytes(source)
                self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
                with self.subTest(owner=owner, append=append), self.assertRaises(HmiError) as caught:
                    receipt = self.service.plan_changes(self.session, self.design, None if append else [], 'order')
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertEqual(caught.exception.code, 'UNQUALIFIED_LAYER')
                self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_unowned_opaque_macro_does_not_crash_empty_page_preflight(self):
        self.use_layout()
        envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
        source = envelope.encode(envelope.body.replace(b'FontColor=0\r\n', b'FontColor=0\r\nMysteryMacroLen=4\r\nxx\r\n', 1))
        (self.root / self.layout_path).write_bytes(source)
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        self.design['screens'].append(dict(id='new', native_id='3', name='New', width=100, height=80, elements=[]))
        receipt = self.service.plan_changes(self.session, self.design, None, 'opaque-macro')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        candidate = NativeAdapter(self.service.sessions[self.session]['applied']['data'], 'delta_diascreen')
        self.assertIn(b'MysteryMacroLen=4\r\nxx\r\n', candidate.envelope.body)
        self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_explicit_noop_navigation_requires_ascii_companion_encoding(self):
        self.use_layout()
        receipt = self.service.plan_changes(self.session, self.design, None, 'canonical')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        (self.root / self.layout_path).write_bytes(self.service.sessions[self.session]['applied']['data'])
        self.profile['native_schema']['navigation']['name_encoding'] = 'cp936'
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        receipt = self.service.plan_changes(self.session, self.design, [], 'encoding-noop')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')

    def test_explicit_noop_malformed_state_fill_returns_typed_error(self):
        for mapping in (None, [], True, {'field': [], 'encoding': 'rgb24'}):
            self.use_layout()
            receipt = self.service.plan_changes(self.session, self.design, None, 'canonical')
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            source = self.service.sessions[self.session]['applied']['data']
            (self.root / self.layout_path).write_bytes(source)
            self.profile['native_schema']['state_fill'] = mapping
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            receipt = self.service.plan_changes(self.session, self.design, [], 'malformed')
            with self.subTest(mapping=mapping), self.assertRaises(HmiError) as caught:
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')
            self.assertIsNone(self.service.sessions[self.session]['applied'])
            self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_explicit_extra_native_behavior_property_is_not_an_ir_transaction(self):
        for field in ('ConFirmWindow', 'CloseScreen', 'Variation'):
            self.use_layout()
            self.profile['native_schema']['properties']['unmodeled'] = dict(field=field, type='int', min=0, max=1)
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            envelope = Envelope.decode(self.layout_source, 'delta_diascreen')
            source = envelope.encode(envelope.body.replace(b'nPartsID=1\r\n', b'nPartsID=1\r\n' + field.encode() + b'=0\r\n'))
            (self.root / self.layout_path).write_bytes(source)
            self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
            automatic = self.service.plan_changes(self.session, self.design, None, 'auto')
            operations = automatic['operations'] + [dict(op='set_property', screen_id='1', element_id='1', key='unmodeled', value=1)]
            receipt = self.service.plan_changes(self.session, self.design, operations, 'explicit')
            validation = self.service.validate(self.session, receipt['plan_id'])
            self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in validation['findings']])
            with self.subTest(field=field), self.assertRaises(HmiError):
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertIsNone(self.service.sessions[self.session]['applied'])
            self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_partial_navigation_kind_cannot_pass_automatic_or_explicit_noop(self):
        self.use_layout()
        receipt = self.service.plan_changes(self.session, self.design, None, 'canonical')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        envelope = Envelope.decode(self.service.sessions[self.session]['applied']['data'], 'delta_diascreen')
        source = envelope.encode(envelope.body.replace(b'Type=1\r\nSubType=10', b'Type=1\r\nSubType=99'))
        (self.root / self.layout_path).write_bytes(source)
        self.profile['native_schema']['kinds']['goto'] = {'Type': '1'}
        self.profile['native_schema']['navigation']['match'] = {'Type': '1'}
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
        for automatic in (True, False):
            with self.subTest(automatic=automatic), self.assertRaises(HmiError) as caught:
                receipt = self.service.plan_changes(self.session, self.design, None if automatic else [], str(automatic))
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertEqual(caught.exception.code, 'UNQUALIFIED_NAVIGATION')
        self.assertEqual((self.root / self.layout_path).read_bytes(), source)

    def test_known_property_cannot_write_an_unrepresented_style_or_remapped_field(self):
        for scenario in ('absent-color', 'remapped-x'):
            self.use_layout()
            automatic = self.service.plan_changes(self.session, self.design, None, 'auto')
            operations = automatic['operations']
            if scenario == 'absent-color':
                operations.append(dict(op='set_property', screen_id='1', element_id='3', key='color', value=123))
            else:
                self.profile['native_schema']['properties']['x']['field'] = 'CloseScreen'
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.layout_path)['session_id']
                operations.append(dict(op='set_property', screen_id='1', element_id='1', key='x', value=1))
            receipt = self.service.plan_changes(self.session, self.design, operations, scenario)
            findings = self.service.validate(self.session, receipt['plan_id'])['findings']
            self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in findings])
            with self.assertRaises(HmiError):
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_save_receipt_detects_opaque_candidate_corruption_without_creating_output(self):
        receipt = self.plan()
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        applied = self.service.sessions[self.session]['applied']
        envelope = Envelope.decode(applied['data'], 'delta_diascreen')
        applied['data'] = envelope.encode(envelope.body.replace(b'UnknownBinary=\xff\x00\x82', b'UnknownBinary=\xff\x00\x83'))
        with self.assertRaises(HmiError) as caught:
            self.service.save_as(self.session, 'corrupted.dpa')
        self.assertEqual(caught.exception.code, 'SAVE_INTEGRITY')
        self.assertFalse((self.root / 'corrupted.dpa').exists())
        self.assertEqual((self.root / 'source.dpa').read_bytes(), transaction_fixture())

    def use_macros(self, family='delta_diascreen'):
        self.profile_id = 'synthetic_diascreen' if family == 'delta_diascreen' else 'synthetic_dopsoft2'
        self.profile = json.loads((ROOT / 'profiles' / (self.profile_id + '.json')).read_bytes())
        self.profile['resolution'] = [100, 80]
        source = macro_fixture(family)
        envelope = Envelope.decode(source, family)
        body = envelope.body.replace(b'FontColor=0\r\n', b'FontColor=0\r\nBgColor=1122867\r\n').replace(b'FontColor=1\r\n', b'FontColor=1\r\nBgColor=39253\r\n')
        self.macro_source = envelope.encode(body)
        self.profile['native_schema']['macros'] = macro_profile(family, self.macro_source)['native_schema']['macros']
        self.profile['native_schema']['macro_internal_binding'] = {'link': '0', 'mem_type': '0'}
        schedule = {'ClockMacroDelayTime': '100', 'ClockMacroPriority': '0', 'LineBrkBackgndMacro': '1'}
        self.profile['native_schema']['macro_bindings'] = {
            'boot': dict(owner={'kind': 'application'}, field='InitialMacroLen', trigger='startup', schedule=schedule),
            'tick': dict(owner={'kind': 'application'}, field='ClockMacroLen', trigger='clock', schedule=schedule),
            'click': dict(owner={'kind': 'element', 'screen_id': '1', 'element_id': '1'}, field='BeforeExecMacroLen', trigger='button', schedule={})}
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        extension = '.dpa' if family == 'delta_diascreen' else '.dps'
        self.macro_source_path = 'macros' + extension
        (self.root / self.macro_source_path).write_bytes(self.macro_source)
        self.session = self.service.open_project(self.profile_id, self.macro_source_path)['session_id']
        self.design['profile_id'] = self.profile_id
        self.design['tags'] += [dict(id=name, address=address, data_type=datatype, access='ReadWrite',
                                   channel='SIM', station='0', byte_order='little', word_order='little',
                                   native_binding={'link': '0', 'mem_type': '0'})
                              for name, address, datatype in (('counter', '$50', 'UINT'), ('large', '$60', 'UDINT'),
                                                            ('signed', '$62', 'DINT'), ('request-bit', '$52.0', 'BOOL'))]
        self.design['macros'] = [
            dict(id='boot', trigger='startup', statements=[
                dict(op='assign', tag='counter', value=0), dict(op='assign', tag='large', value=4000000000),
                dict(op='assign', tag='signed', value=-2000000000)]),
            dict(id='tick', trigger='clock', statements=[dict(op='if', tag='counter', value=0,
                then=[dict(op='assign', tag='counter', value=1)],
                **{'else': [dict(op='assign', tag='counter', value=2)]})]),
            dict(id='click', trigger='button', statements=[dict(op='bit_on', tag='request-bit'), dict(op='bit_off', tag='request-bit')])]
        return extension

    def test_automatic_macros_preserve_owners_widths_schedule_in_both_envelopes(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                # Each family is a separate project/session, never cross-donor.
                original_design = deepcopy(self.design)
                extension = self.use_macros(family)
                receipt = self.service.plan_changes(self.session, self.design, None, family)
                self.assertEqual(receipt['findings'], [])
                self.assertTrue(self.service.validate(self.session, receipt['plan_id'])['offline_pass'])
                approval = self.approve(receipt)
                applied = self.service.apply_plan(self.session, receipt['plan_id'], approval)
                self.assertEqual(self.service.apply_plan(self.session, receipt['plan_id'], approval), applied)
                saved = self.service.save_as(self.session, 'candidate-' + family + extension)
                source = NativeAdapter(self.macro_source, family)
                candidate = NativeAdapter((self.root / ('candidate-' + family + extension)).read_bytes(), family)
                operations = [op for op in receipt['operations'] if op['op'] == 'configure_macro']
                self.assertEqual(len(operations), 3)
                for op in operations:
                    self.assertTrue(candidate.verify_macro_contract(op, self.profile['native_schema'], source))
                boot = candidate.macro_statements({'kind': 'application'}, 'InitialMacroLen', self.profile['native_schema'], source)
                self.assertEqual([(s['datatype'], s['value']) for s in boot], [('UINT', 0), ('UDINT', 4000000000), ('DINT', -2000000000)])
                tick = candidate.macro_statements({'kind': 'application'}, 'ClockMacroLen', self.profile['native_schema'], source)
                self.assertEqual((tick[0]['then'][0]['value'], tick[0]['else'][0]['value']), (1, 2))
                self.assertEqual(saved['sha256'], self.service.diff(self.session)['candidate_sha256'])
                self.assertEqual((self.root / self.macro_source_path).read_bytes(), self.macro_source)
                self.design = original_design

    def test_explicit_noop_cannot_claim_new_macro_statements(self):
        self.use_macros()
        receipt = self.plan('unemitted-macro', ops=self.ops)
        self.assertEqual(receipt['findings'], [])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'MACRO_VERIFY')
        self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_macro_owner_trigger_schedule_and_duplicate_id_mapping_rejected(self):
        for scenario in ('owner', 'trigger', 'schedule', 'duplicate'):
            self.use_macros()
            bindings = self.profile['native_schema']['macro_bindings']
            if scenario == 'owner':
                bindings['click']['owner']['element_id'] = '99'
            elif scenario == 'trigger':
                bindings['tick']['field'] = 'InitialMacroLen'
            elif scenario == 'schedule':
                bindings['tick']['schedule']['ClockMacroDelayTime'] = '101'
            else:
                duplicate = deepcopy(self.design['macros'][0])
                duplicate['id'] = 'boot-second'
                self.design['macros'].append(duplicate)
                bindings['boot-second'] = deepcopy(bindings['boot'])
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            self.session = self.service.open_project(self.profile_id, self.macro_source_path)['session_id']
            with self.subTest(scenario=scenario), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, self.design, None, scenario)
            self.design['tags'] = self.design['tags'][:2]

    def test_macro_binding_templates_and_unsupported_comparison_fail_before_approval(self):
        for scenario in ('read-only', 'external', 'metadata', 'width', 'comparison', 'donor-sha'):
            self.use_macros()
            if scenario == 'read-only':
                self.design['tags'][2]['access'] = 'Read'
            elif scenario == 'external':
                self.design['tags'][2]['address'] = '{SIM}0@D50'
            elif scenario == 'metadata':
                self.design['tags'][2]['native_binding']['link'] = '1'
            elif scenario == 'width':
                self.design['tags'][2]['data_type'] = 'REAL'
            elif scenario == 'comparison':
                self.design['macros'][1]['statements'][0]['comparison'] = 'gt'
            else:
                self.profile['native_schema']['macros']['templates'][0]['donor']['line_sha256'] = '0' * 64
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.macro_source_path)['session_id']
            with self.subTest(scenario=scenario), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, self.design, None, scenario)
            self.design['tags'] = self.design['tags'][:2]

    def test_undeclared_macros_and_schedule_changes_are_detected_in_saved_file(self):
        self.use_macros()
        receipt = self.service.plan_changes(self.session, self.design, None, 'approved')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        data = self.service.sessions[self.session]['applied']['data']
        envelope = Envelope.decode(data, 'delta_diascreen')
        changed = envelope.encode(envelope.body.replace(b'ClockMacroDelayTime=100', b'ClockMacroDelayTime=101'))
        self.service.sessions[self.session]['applied']['data'] = changed
        with self.assertRaises(HmiError):
            self.service.save_as(self.session, 'changed-schedule.dpa')
        self.assertFalse((self.root / 'changed-schedule.dpa').exists())
        # The saved-file verifier also rejects a nonempty program at an owner
        # not declared by IR, even if that program is structurally valid.
        original = NativeAdapter(self.macro_source, 'delta_diascreen')
        hidden = dict(op='configure_macro', owner={'kind': 'application'}, field='BackgroundMacroLen',
                      expected_program_sha256=service_byte_hash(b''),
                      statements=[dict(op='bit_on', datatype='BOOL', address='$52.0')])
        candidate = original.apply(receipt['operations'] + [hidden], self.profile)
        self.service.sessions[self.session]['applied']['data'] = candidate
        with self.assertRaises(HmiError) as caught:
            self.service.save_as(self.session, 'hidden-program.dpa')
        self.assertEqual(caught.exception.code, 'UNDECLARED_MACRO_CHANGE')
        self.assertFalse((self.root / 'hidden-program.dpa').exists())

    def test_resource_tail_change_cannot_bypass_public_alarm_gate(self):
        receipt = self.plan()
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        applied = self.service.sessions[self.session]['applied']
        envelope = Envelope.decode(applied['data'], 'delta_diascreen')
        applied['data'] = envelope.encode(envelope.body.replace(b'Opaque resources', b'Changed resources'))
        with self.assertRaises(HmiError) as caught:
            self.service.save_as(self.session, 'hidden-resource.dpa')
        self.assertEqual(caught.exception.code, 'UNDECLARED_RESOURCE_CHANGE')
        self.assertFalse((self.root / 'hidden-resource.dpa').exists())

    def test_opaque_macro_preserved_but_not_cloned_as_unmanaged_behavior(self):
        envelope = Envelope.decode(transaction_fixture(), 'delta_diascreen')
        source = envelope.encode(envelope.body.replace(b'BeforeExecMacroLen=0\r\n', b'BeforeExecMacroLen=4\r\nxx\r\n'))
        (self.root / 'source.dpa').write_bytes(source)
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        receipt = self.plan('keep-opaque')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'keep-opaque.dpa')
        self.profile['native_schema']['donors'] = {'button': {'screen_id': '1', 'element_id': '1'}}
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        cloned = deepcopy(self.design['screens'][0]['elements'][0])
        cloned.update(id='cloned', native_id='2', x=60)
        self.design['screens'][0]['elements'].append(cloned)
        receipt = self.service.plan_changes(self.session, self.design, None, 'clone-opaque')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'UNDECLARED_MACRO_CHANGE')

    def test_approved_saved_roundtrip_and_repeated_calls(self):
        receipt = self.plan()
        self.assertEqual(receipt['findings'], [])
        self.assertEqual(self.plan(), receipt)
        approval = self.approve(receipt)
        applied = self.service.apply_plan(self.session, receipt['plan_id'], approval)
        self.assertEqual(self.service.apply_plan(self.session, receipt['plan_id'], approval), applied)
        saved = self.service.save_as(self.session, 'delivery/candidate.dpa')
        self.assertEqual(saved, self.service.save_as(self.session, 'delivery/candidate.dpa'))
        self.assertEqual((self.root / 'source.dpa').read_bytes(), transaction_fixture())
        diff = self.service.diff(self.session)
        self.assertFalse(diff['byte_equal'])
        self.assertEqual(diff['candidate_inventory']['screens'][0]['elements'][0]['subtype'], '2')
        self.assertEqual(saved['vendor'], 'NOT_RUN')

    def test_auto_compiler_replays_intent_and_preserves_exact_noop(self):
        # Call the public API directly so null exercises automatic compilation.
        receipt = self.service.plan_changes(self.session, self.design, None, 'automatic')
        self.assertEqual(receipt['planning_mode'], 'COMPILED_FROM_DESIGN')
        self.assertEqual(receipt['operations'], self.ops)
        self.assertEqual(self.service.plan_changes(self.session, self.design, None, 'automatic'), receipt)
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'compiled.dpa')
        self.assertEqual(self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements'][0]['subtype'], '2')
        self.design['screens'][0]['elements'][0]['behavior'] = 'momentary'
        noop = self.service.plan_changes(self.session, self.design, None, 'automatic-noop')
        self.assertEqual(noop['operations'], [])
        self.service.apply_plan(self.session, noop['plan_id'], self.approve(noop))
        self.service.save_as(self.session, 'compiled-noop.dpa')
        self.assertEqual((self.root / 'compiled-noop.dpa').read_bytes(), transaction_fixture())

    def test_auto_compiler_emits_text_color_geometry_and_exact_binding(self):
        design = deepcopy(self.design)
        element = design['screens'][0]['elements'][0]
        element.update(x=55, y=45, width=40, height=30)
        element['states'][0].update(text='KAPALI', fill='#ffee11')
        design['tags'][0]['address'] = '!D10'
        receipt = self.service.plan_changes(self.session, design, None, 'automatic-fields')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'fields.dpa')
        native = self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements'][0]
        self.assertEqual(native['geometry'], {'x':55,'y':45,'width':40,'height':30})
        self.assertEqual(native['texts'][0]['text'], 'KAPALI')
        self.assertEqual(native['states'][0]['native_fields']['BgColor'], str(0xffee11))
        self.assertEqual(native['bindings']['read']['address'], '!D10')
        self.assertEqual((self.root / 'source.dpa').read_bytes(), transaction_fixture())

    def test_auto_compiler_clones_immutable_donor_before_changing_it(self):
        self.profile['native_schema']['donors'] = {'button': {'screen_id':'1', 'element_id':'1'}}
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        design = deepcopy(self.design)
        original = design['screens'][0]['elements'][0]
        cloned = deepcopy(original)
        original.update(x=45, width=40)
        original['states'][0]['text'] = 'CHANGED DONOR'
        cloned.update(id='cloned', native_id='2')
        design['screens'][0]['elements'].append(cloned)
        receipt = self.service.plan_changes(self.session, design, None, 'clone')
        self.assertEqual(receipt['operations'][0]['op'], 'clone_element')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'cloned.dpa')
        actual = self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements']
        self.assertEqual([e['id'] for e in actual], ['1','2'])
        self.assertEqual(actual[1]['geometry'], {'x':10,'y':20,'width':30,'height':20})
        self.assertEqual(actual[1]['texts'][0]['text'], 'OFF')

    def test_auto_compiler_rejects_missing_donor_layer_change_and_unsupported_fields(self):
        for name in ('missing-donor', 'font', 'screen-name'):
            design = deepcopy(self.design)
            if name == 'missing-donor':
                design['screens'][0]['elements'][0]['native_id'] = '2'
            elif name == 'font':
                design['screens'][0]['elements'][0]['font_size'] = 20
            else:
                design['screens'][0]['name'] = 'Unemitted name'
            with self.subTest(name=name), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, name)
        self.assertEqual(self.service.sessions[self.session]['plans'], {})

    def test_explicit_plan_cannot_hide_wrong_page_name_or_layer_order(self):
        design = deepcopy(self.design)
        design['screens'][0]['name'] = 'UNEMITTED NAME'
        receipt = self.plan('wrong-name', design)
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')
        from universal_hmi.native import NativeAdapter
        source = NativeAdapter(transaction_fixture(), 'delta_diascreen').apply([
            dict(op='clone_element', source_screen='1', source_element='1', target_screen='1', element_id='2'),
            dict(op='set_property', screen_id='1', element_id='2', key='x', value=60)], self.profile)
        (self.root / 'source.dpa').write_bytes(source)
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        design = deepcopy(self.design)
        second = deepcopy(design['screens'][0]['elements'][0])
        second.update(id='second', native_id='2', x=60)
        design['screens'][0]['elements'].insert(0, second)
        operations = self.ops + [dict(op='set_property', screen_id='1', element_id='2', key='behavior', value='maintained')]
        receipt = self.plan('wrong-layer', design, operations)
        self.assertEqual(receipt['findings'], [])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')
        self.assertIsNone(self.service.sessions[self.session]['applied'])

    def use_numeric(self, family='delta_diascreen', kind='numeric_input', data_type='REAL', mem_len='2', mem_fmt='5'):
        self.profile_id = 'synthetic_diascreen' if family == 'delta_diascreen' else 'synthetic_dopsoft2'
        self.profile = json.loads((ROOT / 'profiles' / (self.profile_id + '.json')).read_bytes())
        self.profile['resolution'] = [100,80]
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        extension = '.dpa' if family == 'delta_diascreen' else '.dps'
        self.numeric_source_path = 'numeric' + extension
        self.numeric_source = numeric_transaction_fixture(family, kind, mem_len, mem_fmt)
        (self.root / self.numeric_source_path).write_bytes(self.numeric_source)
        self.session = self.service.open_project(self.profile_id, self.numeric_source_path)['session_id']
        element = dict(id='number', native_id='1', kind=kind, x=10,y=20,width=30,height=20,
                       minimum=-25.5 if data_type=='REAL' else 0, maximum=125.75 if data_type=='REAL' else 125,
                       fractional=2 if data_type=='REAL' else 0, format='decimal', binding={'read':'quantity'})
        if kind == 'numeric_input':
            element['binding']['write'] = 'quantity'
        self.design = dict(schema_version=1, project_id='numeric-neutral', profile_id=self.profile_id,
            screens=[dict(id='main',native_id='1',name='Main',width=100,height=80,elements=[element])],
            tags=[dict(id='quantity',address='!D1',data_type=data_type,access='ReadWrite' if kind=='numeric_input' else 'Read',
                       channel='SIM',station='0',byte_order='little',word_order='little',native_binding={'link':'1','mem_type':'0'})],macros=[],alarms=[])
        return extension

    def use_units(self, family='delta_diascreen', kind='numeric_input'):
        if not hasattr(self, '_unit_base_design'):
            self._unit_base_design = deepcopy(self.design)
        base = deepcopy(self._unit_base_design)
        self.design = deepcopy(base)
        extension = self.use_layout(family)
        visual = deepcopy(self.profile['native_schema']['visual'])
        properties = deepcopy(self.profile['native_schema']['properties'])
        self.design = base
        self.use_numeric(family, kind)
        schema = self.profile['native_schema']
        schema['visual'] = visual
        schema['properties'].update(properties)
        schema['kinds']['text'] = {'Type': '77', 'SubType': '1'}
        schema['state_values']['text'] = [0]
        schema['donors'] = {'text': {'screen_id': '1', 'element_id': '2'},
                            kind: {'REAL': {'screen_id': '1', 'element_id': '1'}}}
        self.unit_source = unit_transaction_fixture(family, kind)
        self.numeric_source = self.unit_source
        adapter = NativeAdapter(self.unit_source, family)
        fields = adapter.inspect()['screens'][0]['elements'][0]['native_fields']
        schema['unit_context'] = dict(qualified=True, owner='Element', value_model='identity',
                                      fields={k: v for k, v in fields.items() if 'unit' in k.casefold()})
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        (self.root / self.numeric_source_path).write_bytes(self.unit_source)
        self.session = self.service.open_project(self.profile_id, self.numeric_source_path)['session_id']
        number = self.design['screens'][0]['elements'][0]
        number.update(unit='mm', unit_label='unit-text', font_size=12, color='#ffffff', fill='#112233')
        self.design['tags'][0]['unit'] = 'mm'
        self.design['screens'][0]['elements'].append(dict(id='unit-text', native_id='2', kind='text',
            x=50, y=20, width=40, height=20, text='mm', font_size=12, color='#ffffff', fill='#112233'))
        return extension

    def test_linked_units_native_transactions_both_numeric_kinds_and_envelopes(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            for kind in ('numeric_input', 'numeric_display'):
                with self.subTest(family=family, kind=kind):
                    extension = self.use_units(family, kind)
                    before = NativeAdapter(self.unit_source, family)
                    receipt = self.service.plan_changes(self.session, self.design, None, 'unit-owner')
                    self.assertEqual(receipt['findings'], [])
                    self.assertNotIn('set_unit_caption', [op['op'] for op in receipt['operations']])
                    preview = self.service.preview(self.session, receipt['plan_id'])
                    self.assertNotIn('class="unit"', preview['html'])
                    self.assertEqual(preview['render_kind'], 'CONCEPTUAL_IR')
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                    path = family + '-' + kind + '-units' + extension
                    self.service.save_as(self.session, path)
                    candidate = NativeAdapter((self.root / path).read_bytes(), family)
                    number, label = candidate.inspect()['screens'][0]['elements']
                    self.assertEqual(before.unit_context_baseline('1', '1'), candidate.unit_context_baseline('1', '1'))
                    self.assertEqual([{k: c[k] for k in ('language', 'text', 'byte_count')} for c in number['unit_captions']],
                                     [{'language': 0, 'text': '', 'byte_count': 2}])
                    self.assertEqual(label['texts'][0]['text'], 'mm')
                    self.assertEqual(label['geometry'], {'x': 50, 'y': 20, 'width': 40, 'height': 20})
                    self.assertEqual(label['states'][0]['native_fields']['FontSize0'], '12')
                    self.assertEqual(candidate.document.tail, before.document.tail)
                    self.assertEqual((self.root / self.numeric_source_path).read_bytes(), self.unit_source)
                    # The saved source permits exact public no-op while the raw
                    # unit frame and all conversion records remain unchanged.
                    session = self.service.open_project(self.profile_id, path)['session_id']
                    noop = self.service.plan_changes(session, self.design, [], 'unit-noop')
                    self.service.apply_plan(session, noop['plan_id'], self.approve(noop))
                    self.assertTrue(self.service.diff(session)['byte_equal'])

    def test_linked_numeric_and_label_clones_pin_original_unit_context(self):
        self.use_units()
        elements = self.design['screens'][0]['elements']
        number = deepcopy(elements[0])
        number.update(id='second-number', native_id='3', y=50, unit_label='second-unit')
        label = deepcopy(elements[1])
        label.update(id='second-unit', native_id='4', y=50)
        elements.extend([number, label])
        receipt = self.service.plan_changes(self.session, self.design, None, 'unit-clones')
        self.assertEqual(sum(op['op'] == 'clone_element' for op in receipt['operations']), 2)
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'unit-clones.dpa')
        candidate = NativeAdapter((self.root / 'unit-clones.dpa').read_bytes(), 'delta_diascreen')
        before = NativeAdapter(self.unit_source, 'delta_diascreen')
        self.assertEqual(before.unit_context_baseline('1', '1'), candidate.unit_context_baseline('1', '3'))
        self.assertEqual([e['texts'][0]['text'] for e in candidate.inspect()['screens'][0]['elements'][1::2]], ['mm', 'mm'])

    def test_public_units_reject_unqualified_hidden_conversion_and_caption_context(self):
        scenarios = ('missing-context', 'missing-field', 'shown', 'caption', 'src-operand',
                     'display-operand', 'percent-operand', 'custom-operand', 'unknown-field',
                     'zero-frame', 'secondary-caption', 'duplicate', 'alias', 'foreign-state')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.use_units()
                schema = self.profile['native_schema']
                envelope = Envelope.decode(self.unit_source, 'delta_diascreen')
                body = envelope.body
                if scenario == 'missing-context':
                    schema.pop('unit_context')
                elif scenario == 'missing-field':
                    body = body.replace(b'BackupUnitSrc=0\r\n', b'')
                elif scenario == 'shown':
                    body = body.replace(b'ShowUnit=0\r\n', b'ShowUnit=1\r\n')
                elif scenario in ('caption', 'zero-frame'):
                    body = body.replace(_wide('UnitTextLen0', ''), _wide('UnitTextLen0', 'mm') if scenario == 'caption' else b'UnitTextLen0=0\r\n')
                elif scenario in ('src-operand', 'display-operand', 'percent-operand', 'custom-operand'):
                    key, value = {'src-operand': ('UnitSrcVar', 'None'), 'display-operand': ('UnitDisplayVar', 'None'),
                                  'percent-operand': ('UnitPercent1Var', '0.0'), 'custom-operand': ('UnitCustom1Var_1', '1.0')}[scenario]
                    body = body.replace(f'{key}={value}\r\n'.encode(), f'{key}=!D12\r\n'.encode())
                elif scenario == 'unknown-field':
                    body = body.replace(b'UnitType=0\r\n', b'UnitType=0\r\nNumericUnitImage=0\r\n')
                elif scenario == 'secondary-caption':
                    body = body.replace(_wide('UnitTextLen0', ''), _wide('UnitTextLen0', '') + b'UnitFontSize1=12\r\nUnitFontName1=Arial\r\n' + _wide('UnitTextLen1', 'mm'))
                elif scenario == 'duplicate':
                    body = body.replace(b'UnitDirection=3\r\n', b'UnitDirection=3\r\nUnitDirection=3\r\n')
                elif scenario == 'alias':
                    body = body.replace(_wide('UnitTextLen0', ''), _wide('UnitTextLen0', '') + _wide('UnitTextLen00', ''))
                else:
                    body = body.replace(b'[State]\r\n', b'[State]\r\nUnitDirection=3\r\n', 1)
                source = envelope.encode(body)
                (self.root / self.numeric_source_path).write_bytes(source)
                if scenario not in ('missing-context', 'duplicate', 'alias'):
                    fields = NativeAdapter(source, 'delta_diascreen').inspect()['screens'][0]['elements'][0]['native_fields']
                    schema['unit_context']['fields'] = {k: v for k, v in fields.items() if 'unit' in k.casefold()}
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                with self.assertRaises(HmiError):
                    session = self.service.open_project(self.profile_id, self.numeric_source_path)['session_id']
                    self.service.plan_changes(session, self.design, None, scenario)
                self.assertEqual((self.root / self.numeric_source_path).read_bytes(), source)
                self.assertFalse((self.root / 'candidate.dpa').exists())

    def test_explicit_unit_noop_cannot_bypass_unqualified_source_context(self):
        for scenario in ('no-schema', 'shown', 'foreign-operand'):
            with self.subTest(scenario=scenario):
                self.use_units()
                receipt = self.service.plan_changes(self.session, self.design, None, 'valid-unit')
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                source = self.service.sessions[self.session]['applied']['data']
                envelope = Envelope.decode(source, 'delta_diascreen')
                if scenario == 'no-schema':
                    self.profile['native_schema'].pop('unit_context')
                else:
                    old, new = (b'ShowUnit=0\r\n', b'ShowUnit=1\r\n') if scenario == 'shown' else (b'UnitSrcVar=None\r\n', b'UnitSrcVar=!D12\r\n')
                    source = envelope.encode(envelope.body.replace(old, new))
                    fields = NativeAdapter(source, 'delta_diascreen').inspect()['screens'][0]['elements'][0]['native_fields']
                    self.profile['native_schema']['unit_context']['fields'] = {k: v for k, v in fields.items() if 'unit' in k.casefold()}
                (self.root / self.numeric_source_path).write_bytes(source)
                (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
                self.session = self.service.open_project(self.profile_id, self.numeric_source_path)['session_id']
                noop = self.service.plan_changes(self.session, self.design, [], 'invalid-unit-noop')
                with self.assertRaises(HmiError) as caught:
                    self.service.apply_plan(self.session, noop['plan_id'], self.approve(noop))
                self.assertEqual(caught.exception.code, 'NATIVE_UNIT_UNVERIFIED')
                self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_saved_numeric_unit_context_corruption_is_rejected_before_output(self):
        for scenario in ('conversion', 'caption', 'direction', 'remove-all-without-label'):
            with self.subTest(scenario=scenario):
                self.use_units()
                if scenario == 'remove-all-without-label':
                    number = self.design['screens'][0]['elements'][0]
                    number.pop('unit_label')
                    number.pop('unit')
                    self.design['tags'][0].pop('unit')
                    # The unbound text remains explicitly modeled; numeric
                    # context must still be preserved when IR declares no unit.
                receipt = self.service.plan_changes(self.session, self.design, None, 'unit-save')
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                applied = self.service.sessions[self.session]['applied']
                envelope = Envelope.decode(applied['data'], 'delta_diascreen')
                if scenario == 'remove-all-without-label':
                    adapter = NativeAdapter(applied['data'], 'delta_diascreen')
                    body = b''.join(s.header + b''.join(r.raw for r in s.records if not r.key or 'unit' not in r.key.casefold()) for s in adapter.document.sections) + adapter.document.tail
                else:
                    old, new = {'conversion': (b'UnitCustom1Var_1=1.0\r\n', b'UnitCustom1Var_1=2.0\r\n'),
                                'caption': (_wide('UnitTextLen0', ''), _wide('UnitTextLen0', 'mm')),
                                'direction': (b'UnitDirection=3\r\n', b'UnitDirection=0\r\n')}[scenario]
                    body = envelope.body.replace(old, new)
                applied['data'] = envelope.encode(body)
                with self.assertRaises(HmiError):
                    self.service.save_as(self.session, 'corrupted-unit.dpa')
                self.assertFalse((self.root / 'corrupted-unit.dpa').exists())
                self.assertFalse(list(self.root.glob('.uhmi-*')))

    def test_embedded_unit_caption_low_level_operation_is_not_public_ir_authority(self):
        self.use_units()
        automatic = self.service.plan_changes(self.session, self.design, None, 'valid-public-unit')
        operations = automatic['operations'] + [dict(op='set_unit_caption', screen_id='1', element_id='1',
            text='mm', expected_unit_baseline_sha256='0' * 64)]
        receipt = self.service.plan_changes(self.session, self.design, operations, 'wrong-unit-owner')
        findings = self.service.validate(self.session, receipt['plan_id'])['findings']
        self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in findings])
        with self.assertRaises(HmiError):
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_foreign_unit_owners_rejected_even_with_unitless_numeric_element(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            for owner in ('Application', 'Screen'):
                with self.subTest(family=family, owner=owner):
                    self.use_numeric(family)
                    envelope = Envelope.decode(self.numeric_source, family)
                    injected = envelope.body.replace(f'[{owner}]\r\n'.encode(),
                                                      f'[{owner}]\r\nBackupUnitSrc=1\r\n'.encode(), 1)
                    source = envelope.encode(injected)
                    (self.root / self.numeric_source_path).write_bytes(source)
                    self.session = self.service.open_project(self.profile_id, self.numeric_source_path)['session_id']
                    with self.assertRaises(HmiError) as caught:
                        self.service.plan_changes(self.session, self.design, None, 'foreign-unit-auto')
                    self.assertEqual(caught.exception.code, 'NATIVE_UNIT_UNVERIFIED')
                    noop = self.service.plan_changes(self.session, self.design, [], 'foreign-unit-noop')
                    with self.assertRaises(HmiError) as caught:
                        self.service.apply_plan(self.session, noop['plan_id'], self.approve(noop))
                    self.assertEqual(caught.exception.code, 'NATIVE_UNIT_UNVERIFIED')
                    self.assertIsNone(self.service.sessions[self.session]['applied'])
                    self.assertEqual((self.root / self.numeric_source_path).read_bytes(), source)
                    # Read-only inspection/no-op remains lossless; this is a
                    # public numeric qualification gate, not blanket deletion.
                    self.assertEqual(NativeAdapter(source, family).apply([], {}), source)

    def test_saved_foreign_unit_owner_is_rejected_for_unitless_numeric_ir(self):
        for owner in ('Application', 'Screen'):
            with self.subTest(owner=owner):
                self.use_numeric()
                receipt = self.service.plan_changes(self.session, self.design, None, 'unitless-numeric')
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                applied = self.service.sessions[self.session]['applied']
                envelope = Envelope.decode(applied['data'], 'delta_diascreen')
                applied['data'] = envelope.encode(envelope.body.replace(f'[{owner}]\r\n'.encode(),
                                                                       f'[{owner}]\r\nBackupUnitSrc=1\r\n'.encode(), 1))
                with self.assertRaises(HmiError) as caught:
                    self.service.save_as(self.session, 'foreign-unit-owner.dpa')
                self.assertEqual(caught.exception.code, 'NATIVE_UNIT_UNVERIFIED')
                self.assertFalse((self.root / 'foreign-unit-owner.dpa').exists())
                self.assertFalse(list(self.root.glob('.uhmi-*')))

    def test_auto_numeric_input_and_display_preserve_storage_in_both_envelopes(self):
        for family in ('delta_diascreen','delta_dopsoft2'):
            for kind in ('numeric_input','numeric_display'):
                with self.subTest(family=family,kind=kind):
                    extension = self.use_numeric(family,kind)
                    receipt = self.service.plan_changes(self.session,self.design,None,'numeric')
                    self.assertEqual(receipt['findings'], [])
                    self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
                    self.service.save_as(self.session, family + '-' + kind + extension)
                    native = self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements'][0]
                    fields = native['native_fields']
                    self.assertEqual((fields['MemLen'],fields['MemFmt']),('2','5'))
                    self.assertEqual((fields['IntNum'],fields['DotNum']),('3','2'))
                    if kind=='numeric_input':
                        self.assertEqual((fields['MinValue'],fields['MaxValue']),('-25.5','125.75'))
                    self.assertEqual((self.root/self.numeric_source_path).read_bytes(),self.numeric_source)

    def test_numeric_donor_narrowing_and_unemitted_limits_are_rejected(self):
        self.use_numeric(data_type='REAL',mem_len='1',mem_fmt='1')
        receipt=self.service.plan_changes(self.session,self.design,None,'wrong-storage')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.assertEqual(caught.exception.code,'NUMERIC_DONOR_MISMATCH')
        self.assertIsNone(self.service.sessions[self.session]['applied'])
        self.use_numeric()
        # The native donor's existing max is999; explicit no-op cannot claim
        # that the approved process maximum125.75 has been emitted.
        receipt=self.plan('unemitted-limits',self.design,[])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.assertEqual(caught.exception.code,'NUMERIC_MISMATCH')

    def test_numeric_time_lreal_units_and_missing_process_bounds_fail_closed(self):
        self.use_numeric()
        for name in ('TIME','LREAL','unit','bounds'):
            design=deepcopy(self.design)
            element=design['screens'][0]['elements'][0]
            if name in ('TIME','LREAL'):
                design['tags'][0]['data_type']=name
                element.update(minimum=0,maximum=100,fractional=0)
            elif name=='unit':
                design['tags'][0]['unit']='mm'
            else:
                element.pop('maximum')
            with self.subTest(name=name),self.assertRaises(HmiError):
                self.service.plan_changes(self.session,design,None,name)
        self.assertEqual(self.service.sessions[self.session]['plans'],{})

    def test_explicit_numeric_noop_cannot_hide_noncanonical_storage_or_wrong_schema_width(self):
        for scenario in ('storage-spelling','schema-width'):
            self.use_numeric(data_type='UINT',mem_len='1',mem_fmt='2')
            self.design['screens'][0]['elements'][0].update(maximum=999,fractional=1)
            # UINT common-model precision is integral; prepare a valid zero
            # fractional donor while retaining exact no-op numeric spellings.
            self.design['screens'][0]['elements'][0]['fractional']=0
            envelope=Envelope.decode(self.numeric_source,'delta_diascreen')
            body=envelope.body.replace(b'DotNum=1',b'DotNum=0')
            if scenario=='storage-spelling':
                body=body.replace(b'MemLen=1\r\n',b'MemLen=1.0\r\n')
            else:
                self.profile['native_schema']['numeric']['types']['UINT']['bits']=32
                (self.profile_dir/(self.profile_id+'.json')).write_text(json.dumps(self.profile))
            (self.root/self.numeric_source_path).write_bytes(envelope.encode(body))
            self.session=self.service.open_project(self.profile_id,self.numeric_source_path)['session_id']
            receipt=self.plan(scenario,self.design,[])
            self.assertEqual(receipt['findings'],[])
            with self.subTest(scenario=scenario),self.assertRaises(HmiError):
                self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
            self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_explicit_plan_rejects_undeclared_state_and_changed_momentary_title(self):
        from universal_hmi.native import NativeAdapter
        envelope=Envelope.decode(transaction_fixture(),'delta_diascreen')
        extra=b'[State]\r\nValue=7\r\nBgColor=0\r\n'+_wide('wTextLen0','UNAPPROVED')
        (self.root/'source.dpa').write_bytes(envelope.encode(envelope.body.replace(b'[SubMacro]',extra+b'[SubMacro]',1)))
        self.session=self.service.open_project(self.profile_id,'source.dpa')['session_id']
        receipt=self.plan('extra-state')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.assertEqual(caught.exception.code,'NATIVE_DESIGN_MISMATCH')
        (self.root/'source.dpa').write_bytes(transaction_fixture())
        self.session=self.service.open_project(self.profile_id,'source.dpa')['session_id']
        design=deepcopy(self.design)
        element=design['screens'][0]['elements'][0]
        element.pop('states')
        element.update(behavior='momentary',text='START')
        operation=dict(op='set_text',screen_id='1',element_id='1',state_index=0,language=0,text='START')
        receipt=self.plan('changed-title',design,[operation])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt))
        self.assertEqual(caught.exception.code,'NATIVE_DESIGN_MISMATCH')
        auto=self.service.plan_changes(self.session,design,None,'constant-title')
        self.service.apply_plan(self.session,auto['plan_id'],self.approve(auto))
        actual=self.service.diff(self.session)['candidate_inventory']['screens'][0]['elements'][0]
        self.assertEqual([t['text'] for t in actual['texts']],['START','START'])

    def test_same_key_different_payload_rejected(self):
        self.plan()
        with self.assertRaises(HmiError) as caught:
            self.plan(ops=[])
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')

    def test_source_changed_after_open_blocks_all_mutation(self):
        receipt = self.plan()
        self.approve(receipt)
        (self.root / 'source.dpa').write_bytes(b'changed')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], 'approval.json')
        self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')
        self.assertEqual((self.root / 'source.dpa').read_bytes(), b'changed')

    def test_changed_profile_invalidates_approval(self):
        receipt = self.plan()
        self.approve(receipt)
        self.profile['driver'] = 'another'
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], 'approval.json')
        self.assertEqual(caught.exception.code, 'PROFILE_CHANGED')

    def test_old_design_approval_rejected(self):
        receipt = self.plan()
        approval = self.approve(receipt)
        design = deepcopy(self.design)
        design['screens'][0]['elements'][0]['x'] = 11
        changed = self.plan('new', design, self.ops)
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, changed['plan_id'], approval)
        self.assertEqual(caught.exception.code, 'STALE_APPROVAL')

    def test_donor_behavior_cannot_replace_approved_behavior(self):
        receipt = self.plan(ops=[])
        approval = self.approve(receipt)
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], approval)
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')

    def test_missing_and_read_only_tag_rejected(self):
        for tag in ['state', 'absent']:
            design = deepcopy(self.design)
            design['screens'][0]['elements'][0]['binding']['write'] = tag
            receipt = self.plan(tag, design)
            approval = self.approve(receipt)
            with self.assertRaises(HmiError) as caught:
                self.service.apply_plan(self.session, receipt['plan_id'], approval)
            self.assertEqual(caught.exception.code, 'VALIDATION')

    def test_paths_extensions_and_overwrite(self):
        for path in ['../other.dpa', 'C:/other.dpa']:
            with self.assertRaises(HmiError):
                self.service.open_project(self.profile_id, path)
        receipt = self.plan()
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        for path in ['source.dpa', 'delivery/bad.dps']:
            with self.assertRaises(HmiError):
                self.service.save_as(self.session, path)
        (self.root / 'existing.dpa').write_bytes(b'keep')
        with self.assertRaises(HmiError):
            self.service.save_as(self.session, 'existing.dpa')
        self.assertEqual((self.root / 'existing.dpa').read_bytes(), b'keep')

    def test_failed_reopen_leaves_no_partial_or_temp(self):
        receipt = self.plan()
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        with patch.object(self.service, '_native_matches', side_effect=HmiError('FAIL', 'injected')):
            with self.assertRaises(HmiError):
                self.service.save_as(self.session, 'delivery/candidate.dpa')
        self.assertFalse((self.root / 'delivery/candidate.dpa').exists())
        self.assertEqual(list((self.root / 'delivery').glob('.uhmi-*')), [])

    def test_sessions_do_not_share_plans_and_concurrency_is_serialized(self):
        second = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        receipt = self.plan()
        with self.assertRaises(HmiError):
            self.service.validate(second, receipt['plan_id'])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.plan(), range(12)))
        self.assertTrue(all(result == receipt for result in results))

    def test_synthetic_approval_cannot_authorize_vendor(self):
        receipt = self.plan()
        approval = self.approve(receipt)
        self.service.sessions[self.session]['profile']['fixture_kind'] = 'vendor'
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], approval)
        self.assertEqual(caught.exception.code, 'APPROVAL')

    def test_noop_preserves_every_source_byte(self):
        self.design['screens'][0]['elements'][0]['behavior'] = 'momentary'
        receipt = self.plan(ops=[])
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'noop.dpa')
        self.assertEqual((self.root / 'noop.dpa').read_bytes(), transaction_fixture())

    def test_review_counterexamples_fail_closed(self):
        scenarios = []
        design = deepcopy(self.design)
        scenarios.append(('extra', design, self.ops + [dict(op='clone_element', source_screen='1', source_element='1', target_screen='1', element_id='2')]))
        scenarios.append(('link', design, self.ops + [dict(op='bind', screen_id='1', element_id='1', read={'address':'!D1', 'link':'99', 'mem_type':'99'})]))
        kind = deepcopy(design)
        kind['screens'][0]['elements'][0]['kind'] = 'text'
        scenarios.append(('kind', kind, self.ops))
        for key, draft, ops in scenarios:
            with self.subTest(key=key):
                receipt = self.plan(key, draft, ops)
                with self.assertRaises(HmiError):
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_wrong_target_noop_is_not_a_loophole(self):
        (self.root / 'wrong.dpa').write_bytes(synthetic_file(model_id='WRONG', editor_version='9.9'))
        self.session = self.service.open_project(self.profile_id, 'wrong.dpa')['session_id']
        self.design['screens'][0]['elements'][0]['behavior'] = 'momentary'
        receipt = self.plan(ops=[])
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'APPROVAL')
        approval = json.loads((self.root / 'approval.json').read_bytes())
        approval.update(authority='direct_human', human_reference='Test-only authority: wrong native target must still fail')
        (self.root / 'approval.json').write_text(json.dumps(approval))
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], 'approval.json')
        self.assertEqual(caught.exception.code, 'NATIVE_TARGET_MISMATCH')

    def test_native_dimensions_match_even_with_mutation(self):
        self.profile['resolution'] = [1024, 600]
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        self.design['screens'][0].update(width=1024, height=600)
        receipt = self.plan()
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')

    def test_revoked_approval_blocks_save_and_repeat_save(self):
        receipt = self.plan()
        approval_path = self.approve(receipt)
        self.service.apply_plan(self.session, receipt['plan_id'], approval_path)
        self.service.save_as(self.session, 'saved.dpa')
        approval = json.loads((self.root / approval_path).read_bytes())
        approval['approved'] = False
        (self.root / approval_path).write_text(json.dumps(approval))
        for path in ['revoked.dpa', 'saved.dpa']:
            with self.assertRaises(HmiError):
                self.service.save_as(self.session, path)
        self.assertFalse((self.root / 'revoked.dpa').exists())

    def test_malformed_plan_is_structured_failure(self):
        for malformed in [dict(screens=None), dict(screens=[dict(elements=['bad'])])]:
            with self.assertRaises(HmiError) as caught:
                self.plan('malformed', malformed, [])
            self.assertEqual(caught.exception.code, 'PLAN_SHAPE')

    def test_actual_state_value_cannot_be_inferred_from_position(self):
        source = transaction_fixture()
        envelope = Envelope.decode(source, 'delta_diascreen')
        swapped = envelope.body.replace(b'Value=0\r\n', b'Value=X\r\n').replace(b'Value=1\r\n', b'Value=0\r\n').replace(b'Value=X\r\n', b'Value=1\r\n')
        (self.root / 'source.dpa').write_bytes(envelope.encode(swapped))
        self.session = self.service.open_project(self.profile_id, 'source.dpa')['session_id']
        receipt = self.plan()
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_DESIGN_MISMATCH')

    def test_unemitted_style_and_controller_contract_are_rejected(self):
        for field, value in [('font_size', 96), ('color', '#ff0000')]:
            design = deepcopy(self.design)
            design['screens'][0]['elements'][0][field] = value
            receipt = self.plan(field, design)
            with self.assertRaises(HmiError):
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        for field, value in [('station', '999'), ('channel', 'OTHER'), ('byte_order', 'bogus'), ('word_order', 'reverse')]:
            design = deepcopy(self.design)
            design['tags'][0][field] = value
            receipt = self.plan(field, design)
            with self.assertRaises(HmiError):
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))

    def test_state_color_is_compared_to_native_pixels_contract(self):
        design = deepcopy(self.design)
        design['screens'][0]['elements'][0]['states'][0]['fill'] = '#ff0000'
        receipt = self.plan('color', design)
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')

    def test_css_shorthand_or_alpha_is_not_rgb24_native(self):
        for color in ['#123', '#112233ff']:
            design = deepcopy(self.design)
            design['screens'][0]['elements'][0]['states'][0]['fill'] = color
            receipt = self.plan(color, design)
            with self.assertRaises(HmiError) as caught:
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
            self.assertEqual(caught.exception.code, 'NATIVE_STYLE_UNVERIFIED')


class ExistingOwnerCandidateTests(unittest.TestCase):
    """Original byte-assembled source gates; no vendor fixture or acceptance."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile_dir = self.root / 'registry'
        self.profile_dir.mkdir()
        self.configure()

    def configure(self, family='delta_dopsoft2', vendor_gate=False, source=None):
        self.family = family
        self.extension = '.dps' if family == 'delta_dopsoft2' else '.dpa'
        base, profile = preserved_layout_fixture(family, '-1106816944', '4.00.05.24')
        adapter = NativeAdapter(base, family)
        doc = deepcopy(adapter.document)
        series = 'DOP-B series' if family == 'delta_dopsoft2' else 'DOP-100 series'
        from universal_hmi.native.records import Record
        doc.sections[0].records.append(Record(b'PanelSeries=' + series.encode() + b'\r\n', 'PanelSeries', series.encode()))
        # One wholly original literal-text record, with all other invented
        # behaviors preserved as unknown objects rather than promoted.
        first = _groups(doc)[0]['elements'][0]
        first['section'].one('Type').set_value(b'10')
        first['section'].one('SubType').set_value(b'6')
        first['section'].one('ReadVar').set_value(b'None')
        first['section'].one('WriteVar').set_value(b'None')
        macro = first['section'].one('BeforeExecMacroLen')
        first['section'].records.remove(macro)
        first['states'][0].one('wTextLen0').set_text('X')
        doc.sections.pop(first['end'] - 1)
        for page in _groups(doc):
            for native, x in zip(page['elements'][1:], (60, 80)):
                native['section'].one('X').set_value(str(x).encode())
                native['section'].one('Width').set_value(b'10')
        self.source = source if source is not None else adapter.envelope.encode(doc.bytes())
        self.profile_id = 'original_existing_owner'
        profile = qualify_preserved_layout(self.source, profile)
        profile.update(id=self.profile_id, resolution=[100, 80], fixture_kind='user_vendor_project' if vendor_gate else 'synthetic',
                       capabilities={'text': 'OFFLINE_PASS', 'native_preserved': 'OFFLINE_PASS'},
                       model='ORIGINAL_BYTE_ASSEMBLED_FIXTURE', driver='PRESERVE_SOURCE_UNQUALIFIED')
        profile['native_schema']['kinds'] = {'text': {'Type': '10', 'SubType': '6'}}
        self.profile = profile
        self.write_contracts(vendor_gate)
        self.reopen()

    def write_contracts(self, vendor_gate=False):
        original = NativeAdapter(self.source, self.family)
        schema = self.profile['native_schema']
        schema.pop('native_candidate', None)
        self.witness = dict(contract_version=1, mode='existing_owner_candidate', source_sha256=service_byte_hash(self.source),
            family=self.family, model_id=canonical_model_id(original.model_id), serialized_version=original.editor_version,
            resolution=[100, 80], schema_sha256=canonical_hash(schema),
            source_origin='user_vendor_project' if vendor_gate else 'original_neutral_fixture',
            source_reference='Original byte-assembled test; no vendor asset or acceptance', review_reference='Test-only bound witness',
            panel_series='DOP-B series' if self.family == 'delta_dopsoft2' else 'DOP-100 series',
            editable_owners=[dict(screen_id='1', element_id='1', kind='text', owner_sha256=original.owner_extent_sha256('1', '1'))])
        self.persist_witness()
        (self.root / ('source' + self.extension)).write_bytes(self.source)
        self.design = dict(schema_version=1, project_id='original-candidate', profile_id=self.profile_id, tags=[], macros=[], alarms=[], screens=[])
        for screen in original.inspect()['screens']:
            elements = []
            for native in screen['elements']:
                elem = dict(id=screen['id'] + '_' + native['id'], native_id=native['id'], kind='native_preserved',
                            **native['geometry'], text='', source_owner_sha256=original.owner_extent_sha256(screen['id'], native['id']))
                if (screen['id'], native['id']) == ('1', '1'):
                    elem.pop('source_owner_sha256')
                    elem.update(kind='text', text='X')
                elements.append(elem)
            self.design['screens'].append(dict(id='s' + screen['id'], native_id=screen['id'], name=screen['name'], width=100, height=80, elements=elements))

    def persist_witness(self, raw=None):
        raw = json.dumps(self.witness, sort_keys=True).encode() if raw is None else raw
        (self.root / 'calibration.json').write_bytes(raw)
        self.profile['native_schema']['native_candidate'] = dict(qualified=True, contract_version=1, mode='existing_owner_candidate', path='calibration.json', sha256=service_byte_hash(raw))
        (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))

    def reopen(self):
        self.service = FileService(self.root, self.profile_dir)
        self.session = self.service.open_project(self.profile_id, 'source' + self.extension)['session_id']

    def approve(self, receipt, vendor_gate=False, force_neutral=False):
        approval = {key: value for key, value in receipt.items() if key.endswith('_sha256')}
        approval.update(approved=True, authority='neutral_fixture_qualification' if force_neutral else 'direct_human',
                        human_reference='TEST ONLY — not actual human acceptance', purpose='qualification_only')
        (self.root / 'approval.json').write_text(json.dumps(approval))
        return 'approval.json'

    def changed(self):
        design = deepcopy(self.design)
        design['screens'][0]['elements'][0].update(text='Ç', x=21, width=35)
        return design

    def test_both_envelopes_through_actual_candidate_save_and_noop(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                self.configure(family)
                changed = self.changed()
                receipt = self.service.plan_changes(self.session, changed, None, 'edit')
                self.assertIn('calibration_sha256', receipt)
                self.assertEqual(self.service.validate(self.session, receipt['plan_id'])['findings'], [])
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                saved = self.service.save_as(self.session, 'candidate' + self.extension)
                candidate = NativeAdapter((self.root / ('candidate' + self.extension)).read_bytes(), family)
                original = NativeAdapter(self.source, family)
                native = candidate.inspect()['screens'][0]['elements'][0]
                self.assertEqual(native['texts'][0]['text'], 'Ç')
                self.assertEqual(native['geometry']['x'], 21)
                self.assertEqual(native['geometry']['width'], 35)
                self.assertEqual(candidate.envelope.thumbnail, original.envelope.thumbnail)
                self.assertEqual(candidate.document.tail, original.document.tail)
                for sid, eid in [('1', '2'), ('1', '3'), ('2', '1'), ('3', '3')]:
                    self.assertEqual(candidate.owner_extent_sha256(sid, eid), original.owner_extent_sha256(sid, eid))
                self.assertEqual(saved['sha256'], self.service.diff(self.session)['candidate_sha256'])
                self.assertEqual(saved['vendor'], 'NOT_RUN')
                self.assertEqual((self.root / ('source' + self.extension)).read_bytes(), self.source)
                noop = self.service.plan_changes(self.session, self.design, None, 'noop')
                self.assertEqual(noop['operations'], [])
                self.service.apply_plan(self.session, noop['plan_id'], self.approve(noop))
                self.service.save_as(self.session, 'noop' + self.extension)
                self.assertEqual((self.root / ('noop' + self.extension)).read_bytes(), self.source)

    def test_offline_candidate_gate_is_not_vendor_program_readiness(self):
        self.configure(vendor_gate=True)
        receipt = self.service.plan_changes(self.session, self.changed(), None, 'user-gate')
        with self.assertRaises(HmiError):
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt, force_neutral=True))
        applied = self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt, vendor_gate=True))
        self.assertEqual(applied['purpose'], 'OFFLINE_NATIVE_CANDIDATE')
        self.assertEqual(applied['production_native'], 'UNAVAILABLE')
        self.assertFalse(applied['program_writer_complete'])
        self.assertEqual(applied['vendor'], 'NOT_RUN')
        raw = json.loads((self.root / 'approval.json').read_bytes())
        raw.pop('calibration_sha256')
        (self.root / 'approval.json').write_text(json.dumps(raw))
        with self.assertRaises(HmiError) as caught:
            self.service.save_as(self.session, 'stale' + self.extension)
        self.assertEqual(caught.exception.code, 'STALE_APPROVAL')

    def test_preserved_owner_cannot_be_relabelled_moved_or_cloned(self):
        cases = []
        for mutation in ('hash', 'move', 'relabel', 'delete', 'reorder', 'newpage', 'newowner', 'pagename', 'dimension', 'style', 'binding', 'alarm'):
            design = self.changed()
            target = design['screens'][0]['elements'][1]
            if mutation == 'hash': target['source_owner_sha256'] = '0' * 64
            elif mutation == 'move': target['x'] += 1
            elif mutation == 'relabel': target.update(kind='text', text='X'); target.pop('source_owner_sha256')
            elif mutation == 'delete': design['screens'][0]['elements'].pop()
            elif mutation == 'reorder': design['screens'][0]['elements'].reverse()
            elif mutation == 'newpage': design['screens'].append(deepcopy(design['screens'][0])); design['screens'][-1].update(id='new', native_id='4')
            elif mutation == 'newowner': design['screens'][0]['elements'].append(deepcopy(target)); design['screens'][0]['elements'][-1].update(id='new', native_id='4')
            elif mutation == 'pagename': design['screens'][0]['name'] = 'Changed'
            elif mutation == 'dimension': design['screens'][0]['width'] = 99
            elif mutation == 'style': design['screens'][0]['elements'][0]['font_size'] = 12
            elif mutation == 'binding': design['screens'][0]['elements'][0]['binding'] = {'read': 'x'}
            elif mutation == 'alarm': design['alarms'] = [{'id': 'alarm', 'tag': 'x', 'text': 'E1', 'history_policy': 'preserve_source'}]
            cases.append((mutation, design))
        for name, design in cases:
            with self.subTest(case=name), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, name)

    def test_explicit_operations_must_cover_exact_compiled_intent(self):
        changed = self.changed()
        automatic = self.service.plan_changes(self.session, changed, None, 'auto')
        for index, operations in enumerate(([], automatic['operations'][:-1], automatic['operations'] + [dict(op='bind', screen_id='1', element_id='2', read={'address': '!D1', 'link': '1', 'mem_type': '0'})],
                [dict(op='clone_element', source_screen='1', source_element='1', target_screen='1', element_id='4')])):
            receipt = self.service.plan_changes(self.session, changed, operations, 'bad' + str(index))
            validation = self.service.validate(self.session, receipt['plan_id'])
            self.assertFalse(validation['offline_pass'])
            self.assertIn('NATIVE_CANDIDATE_SCOPE', [f['code'] for f in validation['findings']])

    def test_calibration_is_fresh_for_plan_apply_and_saved_idempotency(self):
        receipt = self.service.plan_changes(self.session, self.changed(), None, 'bound')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.session, 'original' + self.extension)
        path = self.root / 'calibration.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        for action in (lambda: self.service.inspect(self.session), lambda: self.service.plan_changes(self.session, self.design, None, 'changed'),
                       lambda: self.service.validate(self.session, receipt['plan_id']), lambda: self.service.apply_plan(self.session, receipt['plan_id'], 'approval.json'),
                       lambda: self.service.save_as(self.session, 'original' + self.extension)):
            with self.assertRaises(HmiError) as caught: action()
            self.assertEqual(caught.exception.code, 'CALIBRATION_CHANGED')
        path.write_bytes(original)
        path.unlink()
        with self.assertRaises(HmiError) as caught: self.service.save_as(self.session, 'missing' + self.extension)
        self.assertEqual(caught.exception.code, 'CALIBRATION_CHANGED')

    def test_calibration_shape_identity_hash_and_owner_negatives(self):
        baseline = deepcopy(self.witness)
        mutations = [('contract_version', True), ('mode', 'anything'), ('source_sha256', '0' * 64), ('family', 'other'),
                     ('model_id', 1), ('model_id', float(self.witness['model_id'])), ('serialized_version', '2.00.07'), ('resolution', [99, 80]), ('resolution', [100.0, 80]), ('schema_sha256', '0' * 64),
                     ('source_origin', 'public_archive'), ('source_origin', []), ('source_origin', {}), ('source_reference', ''), ('review_reference', 'bad\nreference'), ('panel_series', 'HMC')]
        for key, value in mutations:
            with self.subTest(field=key):
                self.witness = deepcopy(baseline); self.witness[key] = value; self.persist_witness()
                with self.assertRaises(HmiError): self.reopen()
        for field, value in [('screen_id', '01'), ('element_id', '9'), ('kind', 'button'), ('owner_sha256', 'f' * 64)]:
            with self.subTest(owner=field):
                self.witness = deepcopy(baseline); self.witness['editable_owners'][0][field] = value; self.persist_witness()
                with self.assertRaises(HmiError): self.reopen()
        self.witness = deepcopy(baseline); self.witness['editable_owners'] *= 2; self.persist_witness()
        with self.assertRaises(HmiError): self.reopen()

    def test_calibration_json_duplicates_size_and_paths_are_rejected(self):
        raw = json.dumps(self.witness).encode()
        for bad in (raw.replace(b'"contract_version": 1', b'"contract_version": 1, "contract_version": 1'), b'{}' + b' ' * (1024 * 1024), b'\xff'):
            self.persist_witness(bad)
            with self.assertRaises(HmiError): self.reopen()
        for path in ('../calibration.json', '/calibration.json', 'registry/../calibration.json'):
            self.persist_witness()
            self.profile['native_schema']['native_candidate']['path'] = path
            (self.profile_dir / (self.profile_id + '.json')).write_text(json.dumps(self.profile))
            with self.assertRaises(HmiError): self.reopen()

    def test_unmanaged_raw_owner_page_global_and_state_changes_are_caught(self):
        design = self.changed()
        receipt = self.service.plan_changes(self.session, design, None, 'correct')
        good = NativeAdapter(self.source, self.family).apply(receipt['operations'], self.profile)
        for name in ('global', 'page', 'preserved', 'visual', 'extra-language', 'caption', 'geometry', 'prefix', 'tail'):
            candidate = NativeAdapter(good, self.family)
            doc = deepcopy(candidate.document)
            pages = _groups(doc)
            if name == 'global': doc.sections[1].records[0].set_value(b'other')
            elif name == 'page': pages[0]['section'].one('OriginalPageField').set_value(b'other')
            elif name == 'preserved': pages[0]['elements'][1]['section'].one('ReadVar').set_value(b'!D100')
            elif name == 'visual': pages[0]['elements'][0]['states'][0].one('FontColor').set_value(b'7')
            elif name == 'extra-language':
                from universal_hmi.native.records import Record
                doc.sections[pages[0]['elements'][0]['start'] + 1].records.append(Record(_wide('wTextLen1', 'Y'), 'wTextLen1', b'4', b'Y\0\0\0', 'wide'))
            elif name == 'caption': pages[0]['elements'][0]['states'][0].one('wTextLen0').set_text('X')
            elif name == 'geometry': pages[0]['elements'][0]['section'].one('X').set_value(b'22')
            elif name == 'prefix': doc.sections[0].one('PanelName').set_value(b'Changed')
            elif name == 'tail': doc.tail += b'foreign'
            bad = NativeAdapter(candidate.envelope.encode(doc.bytes()), self.family)
            with self.subTest(tamper=name), self.assertRaises(HmiError):
                self.service._native_matches(self.service.sessions[self.session], design, bad.inspect(), bad)

    def test_atomic_save_rechecks_calibration_and_approval_after_link(self):
        for tamper in ('calibration', 'approval'):
            with self.subTest(tamper=tamper):
                self.configure()
                receipt = self.service.plan_changes(self.session, self.changed(), None, 'atomic')
                self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                real_link = os.link
                def change_after_link(*args, **kwargs):
                    real_link(*args, **kwargs)
                    if tamper == 'calibration': (self.root / 'calibration.json').write_bytes(b'{}')
                    else:
                        approval = json.loads((self.root / 'approval.json').read_bytes()); approval['approved'] = False
                        (self.root / 'approval.json').write_text(json.dumps(approval))
                with patch('universal_hmi.service.os.link', side_effect=change_after_link), self.assertRaises(HmiError):
                    self.service.save_as(self.session, 'rejected' + self.extension)
                self.assertFalse((self.root / ('rejected' + self.extension)).exists())
                self.assertEqual((self.root / ('source' + self.extension)).read_bytes(), self.source)

    def test_failed_post_link_input_guards_remove_only_the_created_candidate(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            for failure in ('approval-list', 'approval-null', 'approval-json', 'approval-missing', 'source-missing', 'profile-missing'):
                with self.subTest(family=family, failure=failure):
                    self.configure(family)
                    receipt = self.service.plan_changes(self.session, self.changed(), None, 'failed-guard')
                    self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
                    real_link = os.link
                    def fail_after_link(*args, **kwargs):
                        real_link(*args, **kwargs)
                        approval = self.root / 'approval.json'
                        if failure == 'approval-list': approval.write_bytes(b'[]')
                        elif failure == 'approval-null': approval.write_bytes(b'null')
                        elif failure == 'approval-json': approval.write_bytes(b'{')
                        elif failure == 'approval-missing': approval.unlink()
                        elif failure == 'source-missing': (self.root / ('source' + self.extension)).unlink()
                        elif failure == 'profile-missing': (self.profile_dir / (self.profile_id + '.json')).unlink()
                    with patch('universal_hmi.service.os.link', side_effect=fail_after_link), self.assertRaises(HmiError):
                        self.service.save_as(self.session, 'failed' + self.extension)
                    self.assertFalse((self.root / ('failed' + self.extension)).exists())
                    self.assertFalse(list(self.root.glob('.uhmi-*')))
                    if failure != 'source-missing': self.assertEqual((self.root / ('source' + self.extension)).read_bytes(), self.source)

    def test_calibration_helper_from_another_cwd_creates_runnable_local_contracts(self):
        script = ROOT / 'scripts/calibrate_source.py'
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                self.configure(family)
                args = [sys.executable, str(script), '--workspace', str(self.root), '--source', 'source' + self.extension,
                        '--family', family, '--output', 'contracts/' + family, '--origin', 'original_neutral_fixture',
                        '--edit-text', '1/1', '--source-reference', 'Original fixture test; no vendor proof', '--review-reference', 'Independent tests']
                process = subprocess.run(args, cwd=self.profile_dir, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                created = json.loads(process.stdout)
                self.assertEqual(created['native_output'], 'NOT_CREATED')
                self.assertFalse(created['program_writer_complete'])
                contracts = self.root / 'contracts' / family
                service = FileService(self.root, contracts / 'profiles')
                session = service.open_project('existing_owner_v1', 'source' + self.extension)['session_id']
                design = json.loads((contracts / 'design.json').read_bytes())
                noop = service.plan_changes(session, design, None, 'helper-noop')
                self.assertTrue(service.validate(session, noop['plan_id'])['offline_pass'])
                element = design['screens'][0]['elements'][0]
                element.pop('source_owner_sha256'); element.update(kind='text', text='Ç', x=21, width=35)
                edited = service.plan_changes(session, design, None, 'helper-edit')
                self.assertTrue(service.validate(session, edited['plan_id'])['offline_pass'])
                self.assertEqual(len(created['files']), 3)
                self.assertEqual((self.root / ('source' + self.extension)).read_bytes(), self.source)
                repeated = subprocess.run(args, cwd=self.profile_dir, capture_output=True, text=True, encoding='utf-8')
                self.assertNotEqual(repeated.returncode, 0)
                self.assertIn('OUTPUT_EXISTS', repeated.stdout)

    def test_caption_and_geometry_extent_changes_are_explicitly_unqualified(self):
        for patch_value in ({'text': 'XX'}, {'x': 9}, {'width': 5}):
            design = deepcopy(self.design); design['screens'][0]['elements'][0].update(patch_value)
            with self.subTest(patch=patch_value), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, str(patch_value))

    def test_non_text_calibration_owner_and_family_conversion_are_refused(self):
        for field, value in [('ReadVar', b'!D1'), ('Type', b'6'), ('SubType', b'1')]:
            original = NativeAdapter(self.source, self.family)
            document = deepcopy(original.document)
            _groups(document)[0]['elements'][0]['section'].one(field).set_value(value)
            source = original.envelope.encode(document.bytes())
            with self.subTest(field=field), self.assertRaises(HmiError):
                self.configure(source=source)

    def test_actual_json_read_limit_rejects_artifacts_growing_after_stat(self):
        from types import SimpleNamespace
        def stale_stat(original, target):
            def stat(path, *args, **kwargs):
                actual = original(path, *args, **kwargs)
                if path == target:
                    return SimpleNamespace(st_size=1, st_mode=actual.st_mode, st_ino=actual.st_ino, st_dev=actual.st_dev)
                return actual
            return stat
        raw = json.dumps(self.witness).encode() + b' ' * (1024 * 1024)
        self.persist_witness(raw)
        original_stat = Path.stat
        with patch.object(Path, 'stat', stale_stat(original_stat, self.root / 'calibration.json')), self.assertRaises(HmiError) as caught:
            self.reopen()
        self.assertEqual(caught.exception.code, 'NATIVE_CALIBRATION')
        self.configure()
        receipt = self.service.plan_changes(self.session, self.changed(), None, 'bounded-approval')
        self.approve(receipt)
        path = self.root / 'approval.json'
        path.write_bytes(path.read_bytes() + b' ' * (1024 * 1024))
        with patch.object(Path, 'stat', stale_stat(original_stat, path)), self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], 'approval.json')
        self.assertEqual(caught.exception.code, 'APPROVAL')

    def test_malformed_profiles_are_typed_errors_and_neutral_labels_grant_no_vendor_authority(self):
        profile = self.profile_dir / (self.profile_id + '.json')
        for raw in (b'[]', b'null', b'{', b'{"id":"original_existing_owner","id":"original_existing_owner"}', b'{"x":NaN}'):
            profile.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(HmiError): self.reopen()
        self.configure()
        original = deepcopy(self.profile)
        for key, value in (('family', []), ('resolution', [100.0, 80]), ('native_schema', None), ('capabilities', []), ('model_id', True)):
            self.profile = deepcopy(original); self.profile[key] = value
            profile.write_text(json.dumps(self.profile))
            with self.subTest(field=key), self.assertRaises(HmiError): self.reopen()
        self.configure()
        receipt = self.service.plan_changes(self.session, self.changed(), None, 'labels-are-not-authority')
        with self.assertRaises(HmiError) as caught:
            self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt, force_neutral=True))
        self.assertEqual(caught.exception.code, 'APPROVAL')
        self.assertIsNone(self.service.sessions[self.session]['applied'])

    def test_freshness_uses_bounded_actual_reads_for_growing_inputs(self):
        for name, code in (('source', 'SOURCE_CHANGED'), ('profile', 'PROFILE_CHANGED'), ('calibration', 'CALIBRATION_CHANGED')):
            with self.subTest(input=name):
                self.configure()
                path = self.root / ('source' + self.extension) if name == 'source' else self.profile_dir / (self.profile_id + '.json') if name == 'profile' else self.root / 'calibration.json'
                expected = len(path.read_bytes()) + 1
                path.write_bytes(path.read_bytes() + b' ' * (2 * 1024 * 1024))
                sizes = []
                original_open = Path.open
                class BoundedReader:
                    def __init__(self, file): self.file = file
                    def __enter__(self): self.file.__enter__(); return self
                    def __exit__(self, *args): return self.file.__exit__(*args)
                    def read(self, size=-1): sizes.append(size); return self.file.read(size)
                def opened(target, *args, **kwargs):
                    file = original_open(target, *args, **kwargs)
                    return BoundedReader(file) if target == path else file
                with patch.object(Path, 'open', opened), self.assertRaises(HmiError) as caught:
                    self.service.inspect(self.session)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(sizes, [expected])

    def test_caption_only_and_noop_preserve_padded_geometry_records(self):
        adapter = NativeAdapter(self.source, self.family)
        document = deepcopy(adapter.document)
        owner = _groups(document)[0]['elements'][0]['section']
        owner.one('Y').set_value(b'0020'); owner.one('Height').set_value(b'020')
        source = adapter.envelope.encode(document.bytes())
        self.configure(source=source)
        design = deepcopy(self.design); design['screens'][0]['elements'][0]['text'] = 'Ç'
        receipt = self.service.plan_changes(self.session, design, None, 'caption-only-padded')
        self.assertEqual([op['op'] for op in receipt['operations']], ['set_text'])
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        saved = self.service.save_as(self.session, 'padded' + self.extension)
        actual = NativeAdapter((self.root / ('padded' + self.extension)).read_bytes(), self.family)
        part = _groups(actual.document)[0]['elements'][0]['section']
        self.assertEqual(part.one('Y').raw, owner.one('Y').raw)
        self.assertEqual(part.one('Height').raw, owner.one('Height').raw)
        self.assertEqual(saved['sha256'], self.service.diff(self.session)['candidate_sha256'])
        moved = deepcopy(design); moved['screens'][0]['elements'][0]['x'] = 21
        shifted = self.service.plan_changes(self.session, moved, None, 'padded-unmanaged-axis')
        self.assertTrue(self.service.validate(self.session, shifted['plan_id'])['offline_pass'])
        self.service.apply_plan(self.session, shifted['plan_id'], self.approve(shifted))
        self.service.save_as(self.session, 'padded-axis' + self.extension)
        axis = NativeAdapter((self.root / ('padded-axis' + self.extension)).read_bytes(), self.family)
        second = _groups(axis.document)[0]['elements'][0]['section']
        self.assertEqual(second.one('Y').raw, owner.one('Y').raw)
        self.assertEqual(second.one('Height').raw, owner.one('Height').raw)
        noop = self.service.plan_changes(self.session, self.design, None, 'padded-noop')
        self.assertEqual(noop['operations'], [])
        self.service.apply_plan(self.session, noop['plan_id'], self.approve(noop))
        self.service.save_as(self.session, 'padded-noop' + self.extension)
        self.assertEqual((self.root / ('padded-noop' + self.extension)).read_bytes(), source)

class LiteralPageGenerationTests(unittest.TestCase):
    """Real file transactions over wholly original source graphs.

    These fixtures establish emitter integrity, never vendor executability.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.configure()

    def configure(self, family='delta_dopsoft2', vendor_gate=False):
        from test_native import literal_generation_fixture
        self.family = family
        self.extension = '.dps' if family == 'delta_dopsoft2' else '.dpa'
        self.source, _ = literal_generation_fixture(family, '-1106816944' if vendor_gate else 'SYNTHETIC',
                                                     '4.00.05.24' if vendor_gate else '0.0')
        (self.root / ('source' + self.extension)).write_bytes(self.source)
        helper = runpy.run_path(str(ROOT / 'scripts/calibrate_source.py'))
        # Use the same portable setup entry point a new agent will use.
        if (self.root / 'contracts').exists():
            output = 'contracts_' + family + ('_vendor' if vendor_gate else '')
        else:
            output = 'contracts'
        result = helper['create_contracts'](self.root, 'source' + self.extension, family, output, [],
            'user_vendor_project' if vendor_gate else 'original_neutral_fixture',
            'Wholly original byte-assembled fixture; not vendor acceptance', 'Test-only raw graph contract',
            mode='literal_page_generation', page_donor='1', text_donor='1/1')
        self.assertEqual(result['native_output'], 'NOT_CREATED')
        self.assertEqual(result['opaque_graph_dependencies'], 'UNKNOWN')
        self.profile_dir = self.root / output / 'profiles'
        self.profile_id = 'literal_generation_v1'
        self.profile = json.loads((self.profile_dir / (self.profile_id + '.json')).read_bytes())
        self.design = json.loads((self.root / output / 'design.json').read_bytes())
        self.service = FileService(self.root, self.profile_dir)
        self.session = self.service.open_project(self.profile_id, 'source' + self.extension)['session_id']

    def added(self):
        design = deepcopy(self.design)
        width, height = self.profile['resolution']
        for sid, eid, name, caption in [('2', '11', 'Yeni sayfa', 'Ölçüm'), ('3', '12', 'İkinci', 'Durum')]:
            design['screens'].append(dict(id='new_page_' + sid, native_id=sid, name=name, width=width, height=height,
                elements=[dict(id='new_text_' + eid, native_id=eid, kind='text', text=caption,
                               x=1, y=1, width=min(width - 1, 70), height=20)]))
        return design

    def approve(self, receipt, neutral=True):
        approval = {key: value for key, value in receipt.items() if key.endswith('_sha256')}
        approval.update(approved=True, authority='neutral_fixture_qualification' if neutral else 'direct_human',
                        purpose='qualification_only', human_reference='TEST ONLY — not actual human approval')
        (self.root / 'approval.json').write_text(json.dumps(approval))
        return 'approval.json'

    def transaction(self, design=None, name='candidate', neutral=True):
        design = self.added() if design is None else design
        receipt = self.service.plan_changes(self.session, design, None, name)
        validation = self.service.validate(self.session, receipt['plan_id'])
        self.assertEqual(validation['findings'], [])
        self.assertEqual(validation['scope'], 'APPEND_LITERAL_PAGES')
        self.assertEqual(validation['opaque_graph_dependencies'], 'UNKNOWN')
        applied = self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt, neutral))
        self.assertFalse(applied['program_writer_complete'])
        self.assertEqual(applied['vendor'], 'NOT_RUN')
        self.assertEqual(applied['scope'], 'APPEND_LITERAL_PAGES')
        self.service.save_as(self.session, name + self.extension)
        return receipt, NativeAdapter((self.root / (name + self.extension)).read_bytes(), self.family)

    def test_both_envelopes_generate_real_saved_pages_without_source_object_inheritance(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                if family != self.family:
                    self.configure(family)
                receipt, candidate = self.transaction()
                original = NativeAdapter(self.source, family)
                self.assertEqual([s['id'] for s in candidate.inspect()['screens']], ['1', '2', '3'])
                self.assertEqual([e['type'] for s in candidate.inspect()['screens'][1:] for e in s['elements']], ['10', '10'])
                self.assertEqual([e['texts'][0]['text'] for s in candidate.inspect()['screens'][1:] for e in s['elements']], ['Ölçüm', 'Durum'])
                count = len(original.document.sections)
                self.assertEqual([s.bytes() for s in candidate.document.sections[:count]], [s.bytes() for s in original.document.sections])
                self.assertEqual(candidate.envelope.prefix, original.envelope.prefix)
                self.assertEqual(candidate.envelope.thumbnail, original.envelope.thumbnail)
                self.assertEqual(candidate.document.tail, original.document.tail)
                self.assertEqual((self.root / ('source' + self.extension)).read_bytes(), self.source)
                self.assertEqual(sum(op['op'] == 'append_literal_page' for op in receipt['operations']), 2)

    def test_literal_generation_noop_keeps_every_native_file_byte(self):
        receipt, candidate = self.transaction(self.design, 'noop')
        self.assertEqual(receipt['operations'], [])
        self.assertEqual(candidate.original, self.source)

    def test_original_owner_caption_and_original_page_name_edits_are_rejected(self):
        for variant in ('name', 'text', 'hash', 'geometry', 'remove-page', 'remove-owner', 'source-order'):
            design = self.added()
            if variant == 'name': design['screens'][0]['name'] = 'Changed'
            elif variant == 'text': design['screens'][0]['elements'][0].update(kind='text', text='Changed'); design['screens'][0]['elements'][0].pop('source_owner_sha256')
            elif variant == 'hash': design['screens'][0]['elements'][0]['source_owner_sha256'] = '0' * 64
            elif variant == 'geometry': design['screens'][0]['elements'][0]['x'] += 1
            elif variant == 'remove-page': design['screens'].pop(0)
            elif variant == 'remove-owner': design['screens'][0]['elements'].pop()
            else: design['screens'][0]['elements'].reverse()
            with self.subTest(variant=variant), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, 'bad-' + variant)

    def test_new_project_wide_id_collisions_zero_and_noncanonical_ids_are_rejected(self):
        for owner, value in [('page', '1'), ('page', '0'), ('page', '02'), ('element', '1'), ('element', '0'), ('element', '011'), ('element', '12')]:
            design = self.added()
            obj = design['screens'][1] if owner == 'page' else design['screens'][1]['elements'][0]
            obj['native_id'] = value
            with self.subTest(owner=owner, value=value), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, 'collision-' + owner + value)

    def test_generation_rejects_bindings_styles_commands_and_extra_screen_keys(self):
        for variant in ('tag', 'macro', 'alarm', 'style', 'binding', 'button', 'preserved-new', 'missing-native-id', 'screen-extra'):
            design = self.added()
            obj = design['screens'][1]['elements'][0]
            if variant == 'tag': design['tags'].append(dict(id='tag', address='!D1', access='ReadWrite', data_type='BOOL'))
            elif variant == 'macro': design['macros'].append({})
            elif variant == 'alarm': design['alarms'].append({})
            elif variant == 'style': obj['font_size'] = 18
            elif variant == 'binding': obj['binding'] = {'read': 'anything'}
            elif variant == 'button': obj['kind'] = 'button'
            elif variant == 'preserved-new': obj.update(kind='native_preserved', text='', source_owner_sha256='0' * 64)
            elif variant == 'missing-native-id': design['screens'][1].pop('native_id')
            else: design['screens'][1]['title'] = 'Undeclared'
            with self.subTest(variant=variant), self.assertRaises(HmiError):
                self.service.plan_changes(self.session, design, None, 'scope-' + variant)

    def test_explicit_missing_extra_and_wrong_operations_cannot_cover_generation_intent(self):
        design = self.added()
        good = self.service.plan_changes(self.session, design, None, 'correct')
        for variant in ('missing', 'extra', 'wrong-caption', 'wrong-donor', 'reorder'):
            ops = deepcopy(good['operations'])
            if variant == 'missing': ops.pop()
            elif variant == 'extra': ops.append(dict(op='delete_element', screen_id='1', element_id='2'))
            elif variant == 'wrong-caption': next(o for o in ops if o['op'] == 'set_text')['text'] = 'Forged'
            elif variant == 'wrong-donor': next(o for o in ops if o['op'] == 'clone_element')['source_element'] = '2'
            else: ops.reverse()
            bad = self.service.plan_changes(self.session, design, ops, variant)
            with self.subTest(variant=variant):
                self.assertTrue(self.service.validate(self.session, bad['plan_id'])['findings'])
                with self.assertRaises(HmiError): self.service.apply_plan(self.session, bad['plan_id'], self.approve(bad))
                self.assertFalse((self.root / ('bad' + self.extension)).exists())

    def test_saved_candidate_extra_block_or_retained_region_changes_cannot_be_delivered(self):
        receipt = self.service.plan_changes(self.session, self.added(), None, 'candidate')
        self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        session = self.service.sessions[self.session]
        raw = session['applied']['data']
        candidate = NativeAdapter(raw, self.family)
        for variant in ('extra-block', 'old-owner', 'header'):
            doc = deepcopy(candidate.document)
            if variant == 'extra-block': doc.sections.append(deepcopy(doc.sections[-1]))
            elif variant == 'old-owner': _groups(doc)[0]['elements'][1]['section'].one('X').set_value(b'1')
            else: _groups(doc)[1]['section'].one('BgColor').set_value(b'1')
            session['applied']['data'] = candidate.envelope.encode(doc.bytes())
            with self.subTest(variant=variant), self.assertRaises(HmiError): self.service.save_as(self.session, 'bad-' + variant + self.extension)
            self.assertFalse((self.root / ('bad-' + variant + self.extension)).exists())
        session['applied']['data'] = raw

    def test_generation_preview_is_text_intent_and_not_native_pixel_or_execution_proof(self):
        receipt = self.service.plan_changes(self.session, self.added(), None, 'preview')
        result = self.service.preview(self.session, receipt['plan_id'])
        self.assertIn('TEXT INTENT ONLY', result['html'])
        self.assertIn('SOURCE OBJECT', result['html'])
        self.assertEqual(result['native_visual_acceptance'], 'NOT_RUN')

    def test_generation_requires_exact_human_approval_for_non_synthetic_identity(self):
        self.configure(vendor_gate=True)
        receipt = self.service.plan_changes(self.session, self.added(), None, 'vendor-gate')
        with self.assertRaises(HmiError): self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.transaction(name='human-test-only', neutral=False)

    def test_new_header_only_empty_page_does_not_inherit_any_function_owner(self):
        design = self.added()
        design['screens'][1]['elements'] = []
        _, candidate = self.transaction(design)
        self.assertEqual(candidate.inspect()['screens'][1]['elements'], [])

    def test_calibration_freshness_blocks_source_and_witness_changes(self):
        receipt = self.service.plan_changes(self.session, self.added(), None, 'frozen')
        session = self.service.sessions[self.session]
        p = self.root / session['calibration']['path']
        p.write_bytes(p.read_bytes() + b' ')
        with self.assertRaises(HmiError) as raised: self.service.apply_plan(self.session, receipt['plan_id'], self.approve(receipt))
        self.assertEqual(raised.exception.code, 'CALIBRATION_CHANGED')


class ControlCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = runpy.run_path(str(ROOT / 'scripts/capture_controls.py'))['capture']

    def test_portable_capture_both_families_is_new_json_only_and_source_stays_exact(self):
        from test_native import CalibrationInventoryTests
        for family, extension in [('delta_dopsoft2', '.dps'), ('delta_diascreen', '.dpa')]:
            source = CalibrationInventoryTests().source(family)
            relative = 'input' + extension
            (self.root / relative).write_bytes(source)
            result = self.capture(self.root, relative, family, 'evidence/' + family + '.json')
            self.assertEqual(result['native_output'], 'NOT_CREATED')
            self.assertEqual(result['qualification'], 'UNVERIFIED')
            self.assertFalse(result['emission_authority'])
            facts = json.loads((self.root / 'evidence' / (family + '.json')).read_bytes())
            self.assertEqual(facts['source_sha256'], service_byte_hash(source))
            self.assertNotIn('123456', json.dumps(facts))
            self.assertEqual((self.root / relative).read_bytes(), source)
            with self.assertRaises(HmiError): self.capture(self.root, relative, family, 'evidence/' + family + '.json')

    def test_capture_outside_cwd_cli_uses_exact_workspace_paths(self):
        from test_native import CalibrationInventoryTests
        source = CalibrationInventoryTests().source()
        (self.root / 'input.dps').write_bytes(source)
        with tempfile.TemporaryDirectory(prefix='Unrelated capture caller ') as caller:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/capture_controls.py'), '--workspace', str(self.root),
                '--source', 'input.dps', '--family', 'delta_dopsoft2', '--output', 'evidence/capture.json'], cwd=caller, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['source_sha256'], service_byte_hash(source))
        self.assertEqual((self.root / 'input.dps').read_bytes(), source)

    def test_capture_rejects_path_escape_format_mismatch_and_source_overwrite(self):
        from test_native import CalibrationInventoryTests
        (self.root / 'input.dps').write_bytes(CalibrationInventoryTests().source())
        for source, family, output in [('input.dps', 'delta_dopsoft2', '../escape.json'), ('input.dps', 'delta_dopsoft2', 'input.dps'),
                                       ('input.dps', 'delta_diascreen', 'mismatch.json')]:
            with self.subTest(source=source, output=output), self.assertRaises(HmiError): self.capture(self.root, source, family, output)
        self.assertFalse((self.root / 'mismatch.json').exists())

    def test_changed_source_after_capture_link_fails_and_retains_unaccepted_observations(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        original = FileService._write_new
        def change(service, output, data, verifier, **kwargs):
            receipt = original(service, output, data, verifier, **kwargs)
            path.write_bytes(b'changed after link')
            return receipt
        with patch.object(FileService, '_write_new', change), self.assertRaises(HmiError) as raised:
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'evidence/capture.json')
        self.assertTrue((self.root / 'evidence/capture.json').exists())
        self.assertEqual(raised.exception.context['capture_acceptance'], 'FAIL')
        self.assertTrue(raised.exception.context['output_retained'])
        self.assertEqual(path.read_bytes(), b'changed after link')

    def test_source_disappearing_after_link_retains_unaccepted_capture(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        original = FileService._write_new
        def remove(service, output, data, verifier, **kwargs):
            receipt = original(service, output, data, verifier, **kwargs)
            path.unlink()
            return receipt
        with patch.object(FileService, '_write_new', remove), self.assertRaises(HmiError) as raised:
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'evidence/capture.json')
        self.assertTrue((self.root / 'evidence/capture.json').exists())
        self.assertEqual(raised.exception.code, 'SOURCE_CHANGED')

    def test_existing_output_survives_a_source_change_failure(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        (self.root / 'capture.json').write_bytes(b'user evidence')
        with self.assertRaises(HmiError): self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'capture.json')
        self.assertEqual((self.root / 'capture.json').read_bytes(), b'user evidence')

    def test_capture_cannot_masquerade_as_a_native_candidate(self):
        from test_native import CalibrationInventoryTests
        (self.root / 'input.dps').write_bytes(CalibrationInventoryTests().source())
        for output in ('candidate.dps', 'candidate.dpa', 'capture.txt'):
            with self.subTest(output=output), self.assertRaises(HmiError) as raised:
                self.capture(self.root, 'input.dps', 'delta_dopsoft2', output)
            self.assertEqual(raised.exception.code, 'CAPTURE_FORMAT')
            self.assertFalse((self.root / output).exists())

    def test_changed_foreign_output_is_preserved_on_post_link_source_failure(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        original = FileService._write_new
        def change(service, output, data, verifier, **kwargs):
            receipt = original(service, output, data, verifier, **kwargs)
            (self.root / output).write_bytes(b'foreign replacement')
            path.write_bytes(b'changed source')
            return receipt
        with patch.object(FileService, '_write_new', change), self.assertRaises(HmiError):
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'capture.json')
        self.assertEqual((self.root / 'capture.json').read_bytes(), b'foreign replacement')

    def test_foreign_identical_byte_replacement_survives_cleanup(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        original = FileService._write_new
        def change(service, output, data, verifier, **kwargs):
            receipt = original(service, output, data, verifier, **kwargs)
            new = self.root / 'foreign.json'
            new.write_bytes(data)
            destination = self.root / output
            old_id = destination.stat().st_ino
            os.replace(new, destination)
            self.assertNotEqual(old_id, destination.stat().st_ino)
            path.write_bytes(b'changed source')
            return receipt
        with patch.object(FileService, '_write_new', change), self.assertRaises(HmiError):
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'capture.json')
        self.assertTrue((self.root / 'capture.json').exists())

    def test_post_link_source_failure_never_calls_unlink_on_output(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        path.write_bytes(CalibrationInventoryTests().source())
        original_write = FileService._write_new
        original_unlink = Path.unlink
        def change(service, output, data, verifier):
            receipt = original_write(service, output, data, verifier)
            path.write_bytes(b'changed source')
            return receipt
        def unlink(target, *args, **kwargs):
            self.assertNotEqual(target, self.root / 'capture.json')
            return original_unlink(target, *args, **kwargs)
        with patch.object(FileService, '_write_new', change), patch.object(Path, 'unlink', unlink), self.assertRaises(HmiError):
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'capture.json')
        self.assertTrue((self.root / 'capture.json').exists())

    def test_grown_source_freshness_reads_are_bounded_by_original_size(self):
        from test_native import CalibrationInventoryTests
        path = self.root / 'input.dps'
        raw = CalibrationInventoryTests().source()
        path.write_bytes(raw)
        original_inventory = NativeAdapter.calibration_inventory
        original_open = Path.open
        sizes = []
        def grow(adapter):
            facts = original_inventory(adapter)
            path.write_bytes(raw + b'large replacement' * 50000)
            return facts
        class Tracked:
            def __init__(self, file): self.file = file
            def __enter__(self): return self
            def __exit__(self, *args): self.file.close()
            def read(self, size=-1):
                sizes.append(size)
                return self.file.read(size)
        def opened(target, *args, **kwargs):
            file = original_open(target, *args, **kwargs)
            return Tracked(file) if target == path and args == ('rb',) else file
        with patch.object(NativeAdapter, 'calibration_inventory', grow), patch.object(Path, 'open', opened), self.assertRaises(HmiError) as raised:
            self.capture(self.root, 'input.dps', 'delta_dopsoft2', 'capture.json')
        self.assertEqual(raised.exception.code, 'SOURCE_CHANGED')
        # Path.read_bytes owns its initial read; the freshness helper's opens
        # must each be bounded even when the replacement has already grown.
        self.assertEqual(sizes, [len(raw) + 1])
        self.assertFalse((self.root / 'capture.json').exists())


if __name__ == '__main__':
    unittest.main()


class StaticIntegerStorageServiceTests(unittest.TestCase):
    """Original byte fixtures exercise static authority; no signed vendor witness."""
    plan=ControlGenerationServiceTests.plan
    approve=ControlGenerationServiceTests.approve

    def setUp(self):
        FixedDecimalServiceTests.setUp(self)
        self.storage_authority=self.numeric_authorities/'dopsoft2_b10_int16_conversion.json'
        self.storage_authority.write_bytes((ROOT/'profiles/numeric_contracts/dopsoft2_b10_int16_conversion.json').read_bytes())
        self.storage_helper=runpy.run_path(str(ROOT/'scripts/calibrate_integer_storage.py'))['calibrate']
        self.storage_helper(self.root,'library.dps','fixed-display/profiles/source_controls_fixed_decimal_v1.json','signed-library','STATIC ORIGINAL TEST ONLY')
        self.storage_profile_path='signed-library/profiles/source_controls_int16_static_v1.json'
        program=runpy.run_path(str(ROOT/'scripts/calibrate_program.py'))['calibrate']
        program(self.root,'blank.dps','library.dps',self.storage_profile_path,'signed-program','TEST SOURCE','STATIC TEST ONLY')
        self.profile_dir=self.root/'signed-program/profiles';self.service=FileService(self.root,self.profile_dir)
        self.session=self.service.open_project('blank_program_v1','blank.dps')['session_id']
        for e in self.design['screens'][0]['elements'][4:]:
            e.update(minimum=-32768,maximum=32767,fractional=0);e.pop('value_model',None)
        for t in self.design['tags'][4:]:t['data_type']='INT'

    def test_explicit_int16_operations_save_reopen_and_preserve_uint_sources(self):
        receipt=self.plan();conversions=[o for o in receipt['operations'] if o['op']=='convert_numeric_storage']
        self.assertEqual([o['element_id'] for o in conversions],['105','106'])
        self.assertFalse(self.service.validate(self.session,receipt['plan_id'])['findings'])
        self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt));self.service.save_as(self.session,'signed.dps')
        candidate=NativeAdapter((self.root/'signed.dps').read_bytes(),'delta_dopsoft2')
        original=NativeAdapter(self.target,'delta_dopsoft2')
        owners=candidate.inspect()['screens'][0]['elements'];a,b=owners[4:]
        self.assertEqual((a['native_fields']['MemLen'],a['native_fields']['MemFmt'],a['native_fields']['DotNum']),('1','1','0'))
        self.assertEqual((a['native_fields']['MinValue'],a['native_fields']['MaxValue']),('-32768','32767'))
        self.assertEqual((b['native_fields']['MemLen'],b['native_fields']['MemFmt']),('1','1'));self.assertNotIn('MinValue',b['native_fields'])
        self.assertEqual(a['native_fields']['OffsetMemFmt'],'2')
        self.assertEqual(candidate._preserved_prefix(candidate.document),original._preserved_prefix(original.document))
        self.assertEqual(candidate.envelope.thumbnail,original.envelope.thumbnail)
        self.assertEqual((self.root/'blank.dps').read_bytes(),self.target);self.assertEqual((self.root/'library.dps').read_bytes(),self.library)
        self.assertEqual(self.service.diff(self.session)['candidate_sha256'],service_byte_hash((self.root/'signed.dps').read_bytes()))

    def test_uint_and_fixed_display_remain_unchanged_without_conversion(self):
        design=deepcopy(self.design)
        for t in design['tags'][4:]:t['data_type']='UINT'
        for e in design['screens'][0]['elements'][4:]:e.update(minimum=0,maximum=999)
        design['screens'][0]['elements'][5].update(value_model='integer_fixed_decimal',fractional=2)
        receipt=self.service.plan_changes(self.session,design,None,'unsigned')
        self.assertFalse(any(o['op']=='convert_numeric_storage' for o in receipt['operations']))
        self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt));self.service.save_as(self.session,'unsigned.dps')
        owners=NativeAdapter((self.root/'unsigned.dps').read_bytes(),'delta_dopsoft2').inspect()['screens'][0]['elements']
        self.assertEqual((owners[4]['native_fields']['MemFmt'],owners[5]['native_fields']['MemFmt'],owners[5]['native_fields']['DotNum']),('2','2','2'))

    def test_signed_fractional_equal_limits_wrong_width_or_readonly_write_are_closed(self):
        variants=[('fractional',1),('maximum',-32768),('maximum',32768),('minimum',-32769)]
        for index,(key,value) in enumerate(variants):
            design=deepcopy(self.design);design['screens'][0]['elements'][4][key]=value
            if key=='fractional':design['screens'][0]['elements'][4]['value_model']='integer_fixed_decimal'
            with self.subTest(key=key,value=value),self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'bad'+str(index))
        for index,(key,value) in enumerate([('data_type','DINT'),('data_type','TIME'),('access','Read')]):
            design=deepcopy(self.design);design['tags'][4][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'tag'+str(index))

    def test_old_profile_refuses_int_and_ordinary_numeric_cannot_change_storage(self):
        old=FileService(self.root,self.root/'fixed-program/profiles');sid=old.open_project('blank_program_v1','blank.dps')['session_id']
        with self.assertRaises(HmiError):old.plan_changes(sid,self.design,None,'old')
        plan=self.plan();bad=deepcopy(plan['operations']);bad=[o for o in bad if o['op']!='convert_numeric_storage']
        rejected=self.service.plan_changes(self.session,self.design,bad,'removed-conversion')
        self.assertTrue(self.service.validate(self.session,rejected['plan_id'])['findings'])
        with self.assertRaises(HmiError):self.service.apply_plan(self.session,rejected['plan_id'],self.approve(rejected))

    def test_rehashed_storage_descriptor_cannot_forge_model_source_donor_or_authority(self):
        profile_path=self.root/self.storage_profile_path;profile=json.loads(profile_path.read_bytes());wpath=self.root/'signed-library/control_calibration.json';witness=json.loads(wpath.read_bytes())
        for key in ('source_sha256','input_donor_sha256','display_donor_sha256','authority_sha256'):
            p,w=deepcopy(profile),deepcopy(witness);schema=p['native_schema'];schema['storage_conversion'][key]='0'*64
            w['schema_sha256']=canonical_hash({k:v for k,v in schema.items() if k!='native_candidate'});raw=json.dumps(w).encode();wpath.write_bytes(raw);schema['native_candidate']['sha256']=service_byte_hash(raw);profile_path.write_text(json.dumps(p))
            service=FileService(self.root,profile_path.parent)
            with self.subTest(key=key),self.assertRaises(HmiError):service.open_project('source_controls_int16_static_v1','library.dps')
            self.assertFalse(service.sessions)
        profile_path.write_text(json.dumps(profile));wpath.write_text(json.dumps(witness))

    def test_storage_registry_stale_after_apply_prevents_native_save(self):
        plan=self.plan();self.service.apply_plan(self.session,plan['plan_id'],self.approve(plan));self.storage_authority.write_bytes(self.storage_authority.read_bytes()+b' ')
        with self.assertRaises(HmiError) as ctx:self.service.save_as(self.session,'stale-storage.dps')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'stale-storage.dps').exists())

    def test_helper_freshness_and_repeat_conversion_are_typed(self):
        with self.assertRaises(HmiError):self.storage_helper(self.root,'library.dps',self.storage_profile_path,'repeat','TEST')
        original_write=FileService._write_new
        def race(service,path,data,verifier):
            self.numeric_authority.write_bytes(self.numeric_authority.read_bytes()+b' ')
            return original_write(service,path,data,verifier)
        with patch.object(FileService,'_write_new',race),self.assertRaises(HmiError) as ctx:
            self.storage_helper(self.root,'library.dps','fixed-display/profiles/source_controls_fixed_decimal_v1.json','raced','TEST')
        self.assertEqual(ctx.exception.code,'CALIBRATION_CHANGED');self.assertFalse((self.root/'raced/control_calibration.json').exists())

    def test_malformed_static_registry_facts_do_not_generate_contracts(self):
        original=json.loads(self.storage_authority.read_bytes())
        for index,(key,value) in enumerate([('storage_to',None),('storage_to',[]),('input_range',[True,32767]),('input_relation','less_or_equal'),('family','delta_diascreen'),('fractional_digits',1),('model_id',True),('permitted_storage_fields',['MemLen','MemFmt']),('evidence',[]) ]):
            book=deepcopy(original);book[key]=value;self.storage_authority.write_text(json.dumps(book))
            with self.subTest(key=key),self.assertRaises(HmiError):self.storage_helper(self.root,'library.dps','fixed-display/profiles/source_controls_fixed_decimal_v1.json','invalid-storage'+str(index),'TEST')
            self.assertFalse((self.root/('invalid-storage'+str(index))/'control_calibration.json').exists())
