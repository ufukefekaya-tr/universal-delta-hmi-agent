"""File MCP transaction boundaries for original neutral maintained requests."""
from copy import deepcopy
import json
from pathlib import Path
import os
import tempfile
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter,_groups
from universal_hmi.model import canonical_hash
from universal_hmi.service import FileService
from test_diascreen_bound_buttons import fixture,encode,sha
from test_diascreen_bound_buttons import pins
from calibrate_diascreen_buttons import calibrate


def setup_files(root):
    raw,contract,authority,review=fixture()
    (root/'inputs').mkdir();registry=root/'out/profiles';(registry/'driver_contracts').mkdir(parents=True)
    (root/'inputs/source.dpa').write_bytes(raw)
    (root/'inputs/namespace.json').write_bytes(encode(contract['namespace']))
    (root/'inputs/review.json').write_bytes(review)
    (registry/'driver_contracts/neutral.json').write_bytes(authority)
    calibrate(root,'inputs/source.dpa','out','inputs/namespace.json','neutral','5','14','5',
        'original_neutral_fixture','Invented neutral source bytes','Original neutral tests; not a real review',
        'inputs/review.json',registry)
    profile=json.loads((registry/'diascreen_bound_buttons_v1.json').read_bytes())
    design=json.loads((root/'out/design.json').read_bytes())
    from universal_hmi.native.diascreen_bound_buttons import DiaScreenBoundButtons
    fills=DiaScreenBoundButtons(raw,contract,authority).source_metadata()['state_fills']
    design['tags']=[dict(id='command',address='{EtherLink1}1@M101',data_type='BOOL',access='ReadWrite',
        channel='EtherLink1',station='1',native_binding={'link':'2','mem_type':'0'})]
    screen=next(s for s in design['screens'] if s['native_id']=='5')
    screen['elements'].append(dict(id='new-command',native_id='1001',kind='button',x=10,y=300,
        width=260,height=60,text='',behavior='maintained',role='request',binding={'read':'command','write':'command'},
        states=[dict(value=i,text=text,fill=fills[i]) for i,text in enumerate(['İSTEK KAPALI','İSTEK AÇIK'])]))
    return raw,profile,design,registry


class DiaScreenBoundServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.raw,self.profile,self.design,self.registry=setup_files(self.root)
        self.service=FileService(self.root,self.registry)
        self.opened=self.service.open_project('diascreen_bound_buttons_v1','inputs/source.dpa')
        self.sid=self.opened['session_id']

    def reject(self,fn):
        with self.assertRaises(HmiError):fn()

    def plan(self,design=None,key='neutral-bound'):
        return self.service.plan_changes(self.sid,design or self.design,None,key)

    def approve(self,plan,path='approval.json'):
        payload={k:v for k,v in plan.items() if k.endswith('_sha256')}
        payload.update(approved=True,authority='direct_human',human_reference='ORIGINAL TEST APPROVAL MOCK ONLY; not a real human/production approval')
        (self.root/path).write_bytes(encode(payload))
        return path

    def test_actual_file_transaction_new_binding_saved_reopen_diff_and_source_unchanged(self):
        plan=self.plan();self.assertEqual([],self.service.validate(self.sid,plan['plan_id'])['findings'])
        self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        saved=self.service.save_as(self.sid,'candidate.dpa')
        raw=(self.root/'candidate.dpa').read_bytes();a=NativeAdapter(raw,'delta_diascreen')
        owner=next(o for p in _groups(a.document) for o in p['elements'] if o['id']=='1001')
        self.assertEqual('{EtherLink1}1@M101',owner['section'].fields()['ReadVar'])
        self.assertEqual('4',owner['section'].fields()['SubType'])
        self.assertEqual(self.raw,(self.root/'inputs/source.dpa').read_bytes())
        self.assertEqual(sha(raw),saved['sha256'])
        self.assertTrue(self.service.diff(self.sid))
        self.assertEqual(saved,self.service.save_as(self.sid,'candidate.dpa'))
        (self.root/'foreign.dpa').write_bytes(b'Existing unrelated file')
        self.reject(lambda:self.service.save_as(self.sid,'foreign.dpa'))
        self.assertEqual(b'Existing unrelated file',(self.root/'foreign.dpa').read_bytes())

    def test_plan_replay_empty_noop_and_native_appearance_unknown(self):
        first=self.plan();second=self.plan();self.assertEqual(first['plan_id'],second['plan_id'])
        html=self.service.preview(self.sid,first['plan_id'])['html']
        self.assertIn('Conceptual',html);self.assertIn('İSTEK',html)
        self.assertIn('UNKNOWN',html);self.assertIn('no native vendor rendering',html)
        empty=deepcopy(self.design);empty['tags']=[]
        next(s for s in empty['screens'] if s['native_id']=='5')['elements'].pop()
        plan=self.plan(empty,'empty');self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        self.service.save_as(self.sid,'noop.dpa');self.assertEqual(self.raw,(self.root/'noop.dpa').read_bytes())

    def test_wrong_native_link_storage_channel_station_readonly_and_dotted_address_refuse(self):
        for key,value in [('data_type','UINT'),('access','Read'),('channel','EtherLink2'),('station','0'),
                          ('address','{EtherLink1}1@D2005.0'),('native_binding',{'link':'1','mem_type':'0'}),
                          ('native_binding',{'link':'2','mem_type':'3'})]:
            d=deepcopy(self.design);d['tags'][0][key]=value;self.reject(lambda:self.plan(d,key))

    def test_wrong_behavior_feedback_separate_binding_source_fill_and_extra_intent_refuse(self):
        for key,value in [('behavior','momentary'),('role','feedback'),('font_size',12),
                          ('binding',{'read':'command','write':None})]:
            d=deepcopy(self.design);element=d['screens'][1]['elements'][-1]
            # Fixture page order is2,5,6.
            element[key]=value;self.reject(lambda:self.plan(d,key))
        d=deepcopy(self.design);d['screens'][1]['elements'][-1]['states'][0]['fill']='#ff0000'
        self.reject(lambda:self.plan(d,'changed-color'))

    def test_source_profile_calibration_review_and_registry_freshness_refuse(self):
        targets=['inputs/source.dpa','out/profiles/diascreen_bound_buttons_v1.json',
                 'out/CALIBRATION.json','inputs/review.json','out/profiles/driver_contracts/neutral.json']
        for relative in targets:
            plan=self.plan(key=relative);path=self.root/relative;old=path.read_bytes();path.write_bytes(old+b' ')
            self.reject(lambda:self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan)))
            path.write_bytes(old)

    def test_save_commit_time_authority_race_refuses_and_leaves_no_candidate(self):
        plan=self.plan();self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        path=self.registry/'driver_contracts/neutral.json';path.write_bytes(path.read_bytes()+b' ')
        self.reject(lambda:self.service.save_as(self.sid,'race.dpa'));self.assertFalse((self.root/'race.dpa').exists())

    def test_changed_design_requires_new_exact_approval(self):
        first=self.plan();d=deepcopy(self.design);d['tags'][0]['address']='{EtherLink1}1@M102'
        second=self.plan(d,'different');self.assertNotEqual(first['design_sha256'],second['design_sha256'])
        self.reject(lambda:self.service.apply_plan(self.sid,second['plan_id'],self.approve(first)))

    def test_opaque_original_pages_and_owners_cannot_be_omitted_or_reinterpreted(self):
        d=deepcopy(self.design);d['screens'][0]['elements'].pop();self.reject(lambda:self.plan(d,'omit'))
        d=deepcopy(self.design);d['screens'][0]['elements'][0]['x']+=1;self.reject(lambda:self.plan(d,'edit'))
        d=deepcopy(self.design);d['screens'].reverse();self.reject(lambda:self.plan(d,'order'))

    def test_correctly_rehashed_missing_review_or_witness_has_typed_calibration_refusal(self):
        profile_path=self.registry/'diascreen_bound_buttons_v1.json'
        original_profile=json.loads(profile_path.read_bytes())
        witness_path=self.root/'out/CALIBRATION.json'
        original_witness=json.loads(witness_path.read_bytes())
        for missing_kind in ('witness','review'):
            profile=deepcopy(original_profile)
            if missing_kind=='witness':
                profile['native_schema']['native_candidate']['path']='out/missing.json'
            else:
                witness=deepcopy(original_witness);witness['review']['path']='inputs/missing.json'
                witness_raw=encode(witness);witness_path.write_bytes(witness_raw)
                profile['native_schema']['native_candidate']['sha256']=sha(witness_raw)
            profile_path.write_bytes(encode(profile))
            service=FileService(self.root,self.registry)
            with self.assertRaises(HmiError) as caught:
                service.open_project('diascreen_bound_buttons_v1','inputs/source.dpa')
            self.assertEqual('NATIVE_CALIBRATION',caught.exception.code)
            self.assertFalse(service.sessions)
            witness_path.write_bytes(encode(original_witness));profile_path.write_bytes(encode(original_profile))

    def _topology_change(self, path, relocated):
        assert path.resolve().is_relative_to(self.root.resolve())
        assert relocated.resolve().is_relative_to(self.root.resolve())
        path.rename(relocated)
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(relocated),str(path))
        else:
            path.symlink_to(relocated,target_is_directory=True)
        def remove_link():
            assert path.resolve().is_relative_to(self.root.resolve())
            path.rmdir() if os.name=='nt' else path.unlink()
        self.addCleanup(remove_link)

    def test_registry_parent_same_byte_junction_after_open_refuses_save(self):
        plan=self.plan();self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        self._topology_change(self.registry/'driver_contracts',self.registry/'relocated_contracts')
        with self.assertRaises(HmiError) as caught:self.service.save_as(self.sid,'junction.dpa')
        self.assertEqual('CALIBRATION_CHANGED',caught.exception.code)
        self.assertFalse((self.root/'junction.dpa').exists())

    def test_entire_registry_same_byte_junction_after_open_refuses_save(self):
        plan=self.plan();self.service.apply_plan(self.sid,plan['plan_id'],self.approve(plan))
        self._topology_change(self.registry,self.root/'out/relocated_registry')
        with self.assertRaises(HmiError) as caught:self.service.save_as(self.sid,'root-junction.dpa')
        self.assertEqual('CALIBRATION_CHANGED',caught.exception.code)
        self.assertFalse((self.root/'root-junction.dpa').exists())

    def _default_inputs(self):
        # An invented source can use factual driver metadata without becoming
        # a vendor fixture. No manufacturer project bytes are copied here.
        from calibrate_diascreen_buttons import ROOT
        authority=(ROOT/'profiles/driver_contracts/delta_as_tcp_2024.json').read_bytes()
        book=json.loads(authority)
        raw,contract,_,_=fixture();a=NativeAdapter(raw,'delta_diascreen')
        a.application.one('ControllerName1').set_value(book['driver']['name'].encode())
        namespace=deepcopy(contract['namespace']);namespace['driver']['name']=book['driver']['name']
        namespace['authority_sha256']=sha(authority)
        raw,contract,_,review=pins(a.envelope.encode(a.document.bytes()),namespace,authority)
        (self.root/'inputs/default.dpa').write_bytes(raw)
        (self.root/'inputs/default_namespace.json').write_bytes(encode(contract['namespace']))
        (self.root/'inputs/default_review.json').write_bytes(review)
        return authority

    def test_default_calibrator_outputs_self_contained_portable_registry_and_opens(self):
        authority=self._default_inputs()
        result=calibrate(self.root,'inputs/default.dpa','portable','inputs/default_namespace.json',
            'delta_as_tcp_2024','5','14','5','original_neutral_fixture','Invented metadata fixture',
            'Original neutral test, not actual approval','inputs/default_review.json')
        target=self.root/'portable/profiles/driver_contracts/delta_as_tcp_2024.json'
        self.assertEqual(authority,target.read_bytes());self.assertEqual(4,len(result['outputs']))
        service=FileService(self.root,self.root/'portable/profiles')
        self.assertIn('session_id',service.open_project('diascreen_bound_buttons_v1','inputs/default.dpa'))

    def test_default_calibrator_cannot_overwrite_different_existing_output_authority(self):
        self._default_inputs();target=self.root/'portable/profiles/driver_contracts/delta_as_tcp_2024.json'
        target.parent.mkdir(parents=True);target.write_bytes(b'{}')
        with self.assertRaises(HmiError) as caught:
            calibrate(self.root,'inputs/default.dpa','portable','inputs/default_namespace.json',
                'delta_as_tcp_2024','5','14','5','original_neutral_fixture','Invented metadata fixture',
                'Original neutral test, not actual approval','inputs/default_review.json')
        self.assertEqual('NATIVE_CALIBRATION',caught.exception.code)
        self.assertEqual(b'{}',target.read_bytes());self.assertFalse((self.root/'portable/CALIBRATION.json').exists())


if __name__=='__main__':unittest.main()
