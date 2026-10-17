"""Original neutral DIA byte fixtures; no manufacturer asset or vendor acceptance.

The serialized target is deliberately the bounded observed identity so pure
guards can be exercised. Mock provenance/approval tests are not human evidence.
"""
from copy import deepcopy
import asyncio
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.records import Document, Record
from universal_hmi.service import FileService
import test_native as neutral

ROOT = Path(__file__).resolve().parents[1]
POLICY = 'diascreen_opaque_source_v1'
NAMES = ('Application', 'Multi-Language', 'Global-Camera', 'Event-Trigger', 'Global-Keypad',
    'Recipe', 'Recipe32', 'EnhanceRcp', 'Ethernet', 'Modbus_TCP_Server', 'WEB_OUTPUT', 'SIP',
    'RemoteCtrl', 'VNCCtrl', 'RTC', 'LOG', 'FTP', 'FTPFile', 'DataExchange', 'DataExchangeEnd',
    'LuaData', 'ExtraZA_ZGSection')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dia_profile(raw):
    """Bind synthetic source raw bytes without using the native contract builder."""
    adapter = NativeAdapter(raw, 'delta_diascreen')
    parts = adapter.document.sections[:_groups(adapter.document)[0]['start']]
    schema = dict(qualified=True, properties={key: dict(field=field, scope='element', type='int', min=0, max=800)
        for key, field in {'x':'X', 'y':'Y', 'width':'Width', 'height':'Height'}.items()},
        kinds={'text': {'Type':'10', 'SubType':'6'}}, preserved_layout=dict(qualified=True,
        contract_version=2, mode='existing_owner_edits', source_sha256=sha(raw),
        prefix_sha256=sha(b''.join(s.bytes() for s in parts)), prefix_policy=POLICY,
        sections=[dict(name=s.name, sha256=sha(s.bytes())) for s in parts]))
    return dict(id='neutral_dia_v2', family='delta_diascreen', model_id=268502784,
        editor_version='6.0.00209.8338', resolution=[800,480], fixture_kind='synthetic',
        capabilities={'text':'OFFLINE_PASS', 'native_preserved':'OFFLINE_PASS'}, native_schema=schema)


def diascreen_candidate_fixture():
    """Three asymmetric pages, live and dynamic owners, framed opaque metadata."""
    template = Envelope.decode(neutral.synthetic_file(), 'delta_diascreen')
    app = (b'[Application]\r\nModelName=268502784\r\nVersion=6.0.00209.8338\r\n'
        b'PanelSeries=DOP-100 series\r\nPanelName=Neutral invented DIA\r\n'
        b'MeMeCode=' + struct.pack('<I', 12) + b'[Screen]\r\n!?\r\n\r\n')
    prefix = app
    for name in NAMES[1:]:
        prefix += b'[' + name.encode() + b']\r\nNeutral=A\r\nNeutral=B\r\n'
        if name in {'Ethernet','WEB_OUTPUT','LuaData'}:
            prefix += b'\xff\x00opaque neutral\r\n'
    pages = b''
    for sid, x, caption in [('2',21,'AB'), ('7',53,'CD'), ('12',87,'EF')]:
        pages += (b'[Screen]\r\nVER=16\r\nID=' + sid.encode() + b'\r\n' + neutral._wide('wTextLen','Page '+sid)
            + b'DocSizeX=800\r\nDocSizeY=480\r\nPanelSizeX=800\r\nPanelSizeY=480\r\nOrder=0\r\n[AuxKeyElement]\r\n')
        for index,(eid, kind, visible) in enumerate([('4',10,'None'), ('5',10,'!M1'), ('8',1,'None')]):
            binding = b'None' if kind == 10 else b'!M9'
            pages += (b'[Element]\r\nnPartsID='+eid.encode()+b'\r\nOrder=0004\r\nType='+str(kind).encode()
                + b'\r\nSubType='+(b'6' if kind==10 else b'1')+b'\r\nX='+str(x+100*index).encode()+b'\r\nY=31\r\nWidth=41\r\nHeight=51\r\n'
                + b'ReadVar='+binding+b'\r\nWriteVar='+binding+b'\r\nReadLink=1\r\nWriteLink=1\r\n'
                + b'OffsetReadVar=None\r\nOffsetWriteVar=None\r\nVisibleVar='+visible.encode()+b'\r\n'
                + b'UnknownOwner=\xff\x00\r\nBeforeExecMacroLen=0\r\n[State]\r\nValue=0\r\nFontColor=17\r\n'
                + neutral._wide('wTextLen0',caption)+b'UnknownState=kept\r\n')
            if kind==1:
                pages += b'[State]\r\nValue=1\r\n'+neutral._wide('wTextLen0','ON')
    body = prefix+pages+b'[SubMacro]\r\nOpaque resource\x00\r\n[Screen]\r\nnot a page\r\n'
    envelope_prefix = bytearray(range(41));struct.pack_into('<I',envelope_prefix,37,len(body))
    raw = Envelope(template.thumbnail,bytes(envelope_prefix),body).encode(body)
    return raw, dia_profile(raw)


def edits():
    return [dict(op='set_property',screen_id='2',element_id='4',key='x',value=22),
        dict(op='set_text',screen_id='2',element_id='4',state_index=0,language=0,text='ÇĞ'),
        dict(op='set_property',screen_id='12',element_id='4',key='height',value=52)]


def raw_expected(raw):
    """Independent original range substitutions, not Document or emitter setters."""
    body=Envelope.decode(raw,'delta_diascreen').body
    first=body.index(b'[Screen]\r\nVER=16\r\nID=2\r\n')
    last=body.index(b'[Screen]\r\nVER=16\r\nID=12\r\n')
    a=body[:first];b=body[first:last];c=body[last:]
    b=b.replace(b'X=21\r\n',b'X=22\r\n',1).replace(neutral._wide('wTextLen0','AB'),neutral._wide('wTextLen0','ÇĞ'),1)
    c=c.replace(b'Height=51\r\n',b'Height=52\r\n',1)
    return a+b+c


class DiascreenNativeCandidateTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.profile=diascreen_candidate_fixture();self.adapter=NativeAdapter(self.raw,'delta_diascreen')
        self.schema=self.profile['native_schema']

    def changed_source(self, mutator):
        document=deepcopy(self.adapter.document);mutator(document)
        raw=self.adapter.envelope.encode(document.bytes())
        return NativeAdapter(raw,'delta_diascreen'),dia_profile(raw)

    def test_independent_body_reopen_restoration_and_exact_noop(self):
        self.assertTrue(self.adapter.verify_layout_order(self.schema))
        candidate=NativeAdapter(self.adapter.apply(edits(),self.profile),'delta_diascreen')
        self.assertEqual(candidate.envelope.body,raw_expected(self.raw))
        self.assertEqual(candidate.envelope.prefix,self.adapter.envelope.prefix)
        self.assertEqual(candidate.envelope.thumbnail,self.adapter.envelope.thumbnail)
        self.assertEqual(candidate.document.tail,self.adapter.document.tail)
        self.assertTrue(candidate.verify_layout_order(self.schema,self.adapter))
        self.assertEqual(self.adapter.apply([],self.profile),self.raw)
        noop=[dict(op='set_text',screen_id='2',element_id='4',text='AB')]
        self.assertEqual(self.adapter.apply(noop,self.profile),self.raw)
        # Masking each actual controlled source record restores every BODY byte.
        restored=candidate.envelope.body.replace(b'X=22\r\n',b'X=21\r\n',1).replace(
            neutral._wide('wTextLen0','ÇĞ'),neutral._wide('wTextLen0','AB'),1)
        split=restored.index(b'[Screen]\r\nVER=16\r\nID=12\r\n')
        restored=restored[:split]+restored[split:].replace(b'Height=52\r\n',b'Height=51\r\n',1)
        self.assertEqual(restored,self.adapter.envelope.body)
        for sid in ('2','7','12'):
            for eid in ('5','8'):
                self.assertEqual(candidate.owner_extent_sha256(sid,eid),self.adapter.owner_extent_sha256(sid,eid))
        self.assertEqual(self.adapter.original,self.raw)

    def test_default_v1_b_and_dia_policies_remain_closed_and_unchanged(self):
        for schema in (None,dict(qualified=True,preserved_layout={**self.schema['preserved_layout'],'contract_version':1})):
            with self.assertRaises(HmiError):self.adapter.verify_layout_order(schema)
        for family in ('delta_dopsoft2','delta_diascreen'):
            raw,p=neutral.preserved_layout_fixture(family)
            self.assertEqual(NativeAdapter(raw,family).apply([],p),raw)
        p=deepcopy(self.profile);p['native_schema']['preserved_layout'].pop('prefix_policy')
        with self.assertRaises(HmiError):self.adapter.apply([],p)

    def test_mixed_unknown_and_remapped_schema_rejected_even_before_noop_dispatch(self):
        for key in ('literal_generation','control_generation','blank_program','multipage_program','numeric','bindings','arbitrary'):
            p=deepcopy(self.profile);p['native_schema'][key]={}
            for operations in ([],edits()):
                with self.subTest(key=key,noop=not operations),self.assertRaises(HmiError):self.adapter.apply(operations,p)
                with self.assertRaises(HmiError):self.adapter.verify_layout_order(p['native_schema'])
        for field,value in [('field','SubType'),('scope','state'),('type','enum'),('max',801)]:
            p=deepcopy(self.profile);p['native_schema']['properties']['x'][field]=value
            with self.subTest(field=field),self.assertRaises(HmiError):self.adapter.apply([],p)

    def test_descriptor_shape_types_order_and_source_pins(self):
        for field,value in [('contract_version',True),('contract_version',1),('prefix_policy',[]),('mode',{}),
                ('qualified',1),('source_sha256','f'*64),('prefix_sha256','f'*64),('sections',[])]:
            p=deepcopy(self.profile);p['native_schema']['preserved_layout'][field]=value
            with self.subTest(field=field),self.assertRaises(HmiError):self.adapter.apply([],p)
        p=deepcopy(self.profile);p['native_schema']['preserved_layout']['sections'][0:2]=reversed(p['native_schema']['preserved_layout']['sections'][0:2])
        with self.assertRaises(HmiError):self.adapter.apply([],p)

    def test_unobserved_family_model_version_marker_or_each_page_dimensions_refuse(self):
        mutations=[lambda d:d.sections[0].one('ModelName').set_value(b'268502785'),
            lambda d:d.sections[0].one('Version').set_value(b'6.0.00209.8339'),
            lambda d:d.sections[0].one('PanelSeries').set_value(b'DOP-B series'),
            lambda d:_groups(d)[1]['section'].one('DocSizeX').set_value(b'801')]
        for mutate in mutations:
            a,p=self.changed_source(mutate)
            p['model_id']=a.model_id;p['editor_version']=a.editor_version
            with self.assertRaises(HmiError):a.apply([],p)
        template=Envelope.decode(neutral.synthetic_file('delta_dopsoft2'),'delta_dopsoft2')
        raw=template.encode(self.adapter.envelope.body);a=NativeAdapter(raw,'delta_dopsoft2')
        p=deepcopy(self.profile);p['family']='delta_dopsoft2';p['native_schema']['preserved_layout']['source_sha256']=sha(raw)
        with self.assertRaises(HmiError):a.apply([],p)

    def test_unknown_repeated_missing_and_nonopaque_unkeyed_sections_refuse_rehash(self):
        mutations=[lambda d:setattr(d.sections[2],'header',b'[Unknown]\r\n'),
            lambda d:d.sections.insert(2,deepcopy(d.sections[1])),lambda d:d.sections.pop(3),
            lambda d:d.sections[1].records.append(Record(b'opaque outside scope\r\n'))]
        for mutate in mutations:
            a,p=self.changed_source(mutate)
            with self.assertRaises(HmiError):a.apply([],p)

    def test_inert_owner_requirement_and_macros_are_not_inferred_from_text_type(self):
        for eid in ('5','8'):
            with self.subTest(eid=eid),self.assertRaises(HmiError):self.adapter.apply([dict(op='set_text',screen_id='2',element_id=eid,text='AB')],self.profile)
        for key,value in [('ReadVar',b'!M1'),('WriteVar',b'!M1'),('OffsetReadVar',b'!M1'),('OffsetWriteVar',b'!M1'),('VisibleVar',b'!M1')]:
            a,p=self.changed_source(lambda d:_groups(d)[0]['elements'][0]['section'].one(key).set_value(value))
            with self.subTest(key=key),self.assertRaises(HmiError):a.apply(edits(),p)
        for location in ('element','state','duplicate-empty'):
            def mutate(d):
                owner=_groups(d)[0]['elements'][0]
                part=owner['states'][0] if location=='state' else owner['section']
                if location=='duplicate-empty':part.records.append(deepcopy(part.one('BeforeExecMacroLen')))
                else:part.records.append(Record(b'AfterExecMacroLen=4\r\nxx\r\n','AfterExecMacroLen',b'4',b'xx\r\n','macro'))
            a,p=self.changed_source(mutate)
            with self.subTest(location=location),self.assertRaises(HmiError):a.apply(edits(),p)

    def test_every_forbidden_opcode_is_refused_including_byte_equivalent_bind(self):
        for name in ('bind','configure_numeric','configure_goto','configure_macro','configure_alarm','set_unit_caption',
                'clone_element','clone_screen','append_literal_page','delete_element','rename_screen','reorder_elements','reorder_screens','convert_numeric_storage'):
            operation=dict(op=name)
            if name=='bind':operation.update(screen_id='2',element_id='4',read=dict(address='None',link='1',mem_type='0'))
            with self.subTest(name=name),self.assertRaises(HmiError):self.adapter.apply([operation],self.profile)

    def test_individual_scalar_caption_extents_language_state_and_duplicate_refusals(self):
        invalid=[dict(op='set_property',screen_id='2',element_id='4',key='x',value=9),
            dict(op='set_property',screen_id='2',element_id='4',key='width',value=100),
            dict(op='set_property',screen_id='2',element_id='4',key='x',value=22,state_index=0),
            dict(op='set_text',screen_id='2',element_id='4',text='ABC'),
            dict(op='set_text',screen_id='2',element_id='4',text='AB',language=1),
            dict(op='set_text',screen_id='2',element_id='4',text='AB',state_index=True),
            dict(op='set_text',screen_id='2',element_id='4',text='\ud800A')]
        for operation in invalid:
            with self.subTest(operation=operation),self.assertRaises(HmiError):self.adapter.apply([operation],self.profile)
        with self.assertRaises(HmiError):self.adapter.apply([edits()[0],edits()[0]],self.profile)
        with self.assertRaises(HmiError):self.adapter.apply([edits()[1],edits()[1]],self.profile)

    def test_malformed_operation_values_raise_typed_errors_without_source_mutation(self):
        for field in ('op','key','value','screen_id','element_id'):
            for value in (None,[],{},True,1.5,''):
                operation=deepcopy(edits()[0]);operation[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(HmiError):self.adapter.apply([operation],self.profile)
        bad=deepcopy(edits()[0]);bad['value']=10**5000
        with self.assertRaises(HmiError):self.adapter.apply([bad],self.profile)
        self.assertEqual(self.adapter.original,self.raw)
        self.assertEqual(self.adapter.document.bytes(),self.adapter.envelope.body)

    def test_whole_body_mask_catches_every_unmanaged_change_and_compensated_lengths(self):
        good=NativeAdapter(self.adapter.apply(edits(),self.profile),'delta_diascreen')
        for mutation in ('prefix','page','owner','state','address','type','font','id','order','caption-language','tail','compensated'):
            document=deepcopy(good.document);page=_groups(document)[0];owner=page['elements'][0]
            if mutation=='prefix':document.sections[8].records[-1].raw=b'\xfe\x00opaque neutral\r\n'
            elif mutation=='page':page['section'].one('Order').set_value(b'1')
            elif mutation=='owner':owner['section'].one('UnknownOwner').set_value(b'other')
            elif mutation=='state':owner['states'][0].one('UnknownState').set_value(b'else')
            elif mutation=='address':owner['section'].one('WriteVar').set_value(b'!M1')
            elif mutation=='type':owner['section'].one('SubType').set_value(b'5')
            elif mutation=='font':owner['states'][0].one('FontColor').set_value(b'18')
            elif mutation=='id':owner['section'].one('nPartsID').set_value(b'3')
            elif mutation=='order':owner['section'].one('Order').set_value(b'0005')
            elif mutation=='caption-language':owner['states'][0].records.append(Record(neutral._wide('wTextLen1','ZZ'),'wTextLen1',b'6',b'Z\0Z\0\0\0','wide'))
            elif mutation=='tail':document.tail=document.tail.replace(b'Opaque',b'Changed',1)
            else:owner['section'].one('X').set_value(b'9');owner['section'].one('Y').set_value(b'031')
            candidate=NativeAdapter(good.envelope.encode(document.bytes()),'delta_diascreen')
            with self.subTest(mutation=mutation),self.assertRaises(HmiError):candidate.verify_layout_order(self.schema,self.adapter)

    def test_source_projection_candidate_projection_and_envelope_drift_refuse(self):
        candidate=NativeAdapter(self.adapter.apply(edits(),self.profile),'delta_diascreen')
        for side in ('source','candidate'):
            original=NativeAdapter(self.raw,'delta_diascreen');new=NativeAdapter(candidate.original,'delta_diascreen')
            target=original if side=='source' else new
            _groups(target.document)[0]['elements'][0]['section'].one('X').set_value(b'23')
            with self.assertRaises(HmiError):new.verify_layout_order(self.schema,original)
        for field in ('prefix','thumbnail'):
            envelope=candidate.envelope;prefix=envelope.prefix;thumbnail=envelope.thumbnail
            if field=='prefix':prefix=bytes([prefix[0]^1])+prefix[1:]
            else:thumbnail=thumbnail[:-1]+bytes([thumbnail[-1]^1])
            changed=Envelope(thumbnail,prefix,envelope.body).encode(envelope.body)
            with self.assertRaises(HmiError):NativeAdapter(changed,'delta_diascreen').verify_layout_order(self.schema,self.adapter)


class DiascreenCandidateServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.raw,self.native_profile=diascreen_candidate_fixture()
        (self.root/'source.dpa').write_bytes(self.raw)
        self.helper=runpy.run_path(str(ROOT/'scripts/calibrate_source.py'))['create_contracts']
        self.create();self.open()

    def create(self,origin='original_neutral_fixture',output='contracts'):
        return self.helper(self.root,'source.dpa','delta_diascreen',output,['2/4','7/4','12/4'],origin,
            'Original invented test fixture, no manufacturer proof','Independent unit contract test',prefix_policy=POLICY)

    def open(self):
        self.contracts=self.root/'contracts';self.registry=self.contracts/'profiles'
        self.service=FileService(self.root,self.registry)
        self.session=self.service.open_project('existing_owner_v1','source.dpa')['session_id']
        self.design=json.loads((self.contracts/'design.json').read_bytes())

    def changed(self):
        design=deepcopy(self.design)
        for si,text in ((0,'ÇĞ'),(2,'EF')):
            owner=design['screens'][si]['elements'][0];owner.pop('source_owner_sha256');owner.update(kind='text',text=text)
        design['screens'][0]['elements'][0]['x']=22
        design['screens'][2]['elements'][0]['height']=52
        return design

    def approve(self,receipt,direct=False):
        approval={k:v for k,v in receipt.items() if k.endswith('_sha256')}
        approval.update(approved=True,authority='direct_human' if direct else 'neutral_fixture_qualification',
            human_reference='MOCK UNIT RECEIPT ONLY; not a human or vendor approval',purpose='qualification_only')
        (self.root/'approval.json').write_text(json.dumps(approval));return 'approval.json'

    def test_helper_and_public_save_exact_body_diff_replay_source_retention(self):
        receipt=self.service.plan_changes(self.session,self.changed(),None,'edit')
        self.assertEqual(receipt['operations'],edits())
        self.assertTrue(self.service.validate(self.session,receipt['plan_id'])['offline_pass'])
        applied=self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt,direct=True))
        saved=self.service.save_as(self.session,'candidate.dpa')
        candidate=(self.root/'candidate.dpa').read_bytes()
        self.assertEqual(NativeAdapter(candidate,'delta_diascreen').envelope.body,raw_expected(self.raw))
        self.assertEqual(saved['sha256'],self.service.diff(self.session)['candidate_sha256'])
        self.assertEqual(saved['vendor'],'NOT_RUN');self.assertFalse(applied['program_writer_complete'])
        sid=self.service.open_project('existing_owner_v1','source.dpa')['session_id']
        replay=self.service.plan_changes(sid,self.changed(),None,'edit')
        self.assertEqual(receipt['plan_id'],replay['plan_id'])
        self.service.apply_plan(sid,replay['plan_id'],'approval.json');self.service.save_as(sid,'replay.dpa')
        self.assertEqual(candidate,(self.root/'replay.dpa').read_bytes())
        self.assertEqual((self.root/'source.dpa').read_bytes(),self.raw)

    def test_default_and_wrong_family_mode_or_manufacturer_origin_without_flag_refuse(self):
        for kwargs in ({},{'prefix_policy':POLICY,'mode':'literal_page_generation','page_donor':'2','text_donor':'2/4'}):
            with self.assertRaises(HmiError):self.helper(self.root,'source.dpa','delta_diascreen','bad',[],
                'original_neutral_fixture','Original test','Independent test',**kwargs)
        with self.assertRaises(HmiError):self.helper(self.root,'source.dpa','delta_diascreen','wrong-origin',[],
            'manufacturer_installed_example','MOCK source origin test','Unit test without flag')
        self.assertFalse((self.root/'bad').exists());self.assertFalse((self.root/'wrong-origin').exists())

    def test_manufacturer_provenance_is_explicit_non_synthetic_and_receipt_is_mock(self):
        self.create('manufacturer_installed_example','manufacturer')
        registry=self.root/'manufacturer/profiles';service=FileService(self.root,registry)
        profile=json.loads((registry/'existing_owner_v1.json').read_bytes())
        witness=json.loads((self.root/'manufacturer/CALIBRATION.json').read_bytes())
        self.assertEqual(profile['fixture_kind'],'manufacturer_installed_example')
        self.assertEqual(witness['source_origin'],'manufacturer_installed_example')
        sid=service.open_project('existing_owner_v1','source.dpa')['session_id']
        design=json.loads((self.root/'manufacturer/design.json').read_bytes())
        receipt=service.plan_changes(sid,design,None,'noop')
        with self.assertRaises(HmiError):service.apply_plan(sid,receipt['plan_id'],self.approve(receipt))
        applied=service.apply_plan(sid,receipt['plan_id'],self.approve(receipt,direct=True))
        self.assertEqual(applied['purpose'],'OFFLINE_NATIVE_CANDIDATE')
        self.assertFalse(applied['program_writer_complete'])

    def test_public_refuses_live_dynamic_or_uncalibrated_owner_and_non_geometry_intent(self):
        for index in (1,2):
            design=self.changed();owner=design['screens'][0]['elements'][index]
            owner.pop('source_owner_sha256');owner.update(kind='text',text='AB')
            with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'bad'+str(index))
        for field,value in [('font_size',18),('binding',{'read':'tag'}),('width',100),('text','ABC')]:
            design=self.changed();design['screens'][0]['elements'][0][field]=value
            with self.assertRaises(HmiError):self.service.plan_changes(self.session,design,None,'bad'+field)

    def test_public_explicit_forbidden_operations_no_output_and_source_bytes_unchanged(self):
        operation=dict(op='bind',screen_id='2',element_id='4',read=dict(address='None',link='1',mem_type='0'))
        receipt=self.service.plan_changes(self.session,self.changed(),edits()+[operation],'forbidden')
        result=self.service.validate(self.session,receipt['plan_id']);self.assertFalse(result['offline_pass'])
        with self.assertRaises(HmiError):self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt,direct=True))
        self.assertFalse((self.root/'candidate.dpa').exists())
        self.assertEqual((self.root/'source.dpa').read_bytes(),self.raw)

    def test_calibration_and_source_freshness_no_saved_output(self):
        for target in ('source.dpa','contracts/CALIBRATION.json'):
            path=self.root/target;before=path.read_bytes()
            receipt=self.service.plan_changes(self.session,self.changed(),None,target)
            path.write_bytes(before+b' ')
            try:
                with self.assertRaises(HmiError):self.service.apply_plan(self.session,receipt['plan_id'],self.approve(receipt,direct=True))
                self.assertFalse((self.root/'stale.dpa').exists())
            finally:path.write_bytes(before)

    def test_public_whole_ir_oracle_detects_allowed_but_unapproved_caption_and_geometry(self):
        design=self.changed();receipt=self.service.plan_changes(self.session,design,None,'oracle')
        good=NativeAdapter(self.raw,'delta_diascreen').apply(receipt['operations'],self.service.sessions[self.session]['profile'])
        for field,value in [('X',b'23'),('wTextLen0','ZZ')]:
            adapter=NativeAdapter(good,'delta_diascreen');document=deepcopy(adapter.document)
            owner=_groups(document)[0]['elements'][0]
            if field=='X':owner['section'].one(field).set_value(value)
            else:owner['states'][0].one(field).set_text(value)
            bad=NativeAdapter(adapter.envelope.encode(document.bytes()),'delta_diascreen')
            with self.assertRaises(HmiError):self.service._candidate_matches(self.service.sessions[self.session],design,bad)


class DiascreenCandidateSdkTests(unittest.TestCase):
    def test_neutral_three_page_candidate_through_all_nine_real_stdio_tools(self):
        fixture=DiascreenCandidateServiceTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        install=fixture.root/'isolated_install';shutil.copytree(ROOT/'src/universal_hmi',install/'src/universal_hmi')
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',str(fixture.registry),
                'serve','--workspace',str(fixture.root)],env={**os.environ,'PYTHONPATH':str(install/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    used=set()
                    async def call(name,**args):
                        used.add(name);result=await client.call_tool(name,args)
                        self.assertFalse(result.is_error,str(result));return result.structured_content
                    await call('capabilities',profile_id='existing_owner_v1')
                    sid=(await call('open_project',profile_id='existing_owner_v1',source_path='source.dpa'))['session_id']
                    inventory=await call('inspect',session_id=sid);self.assertEqual(len(inventory['inventory']['screens']),3)
                    receipt=await call('plan_changes',session_id=sid,design=fixture.changed(),idempotency_key='dia')
                    self.assertTrue((await call('validate',session_id=sid,plan_id=receipt['plan_id']))['offline_pass'])
                    preview=await call('preview',session_id=sid,plan_id=receipt['plan_id'])
                    self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
                    applied=await call('apply_plan',session_id=sid,plan_id=receipt['plan_id'],approval_path=fixture.approve(receipt,direct=True))
                    saved=await call('save_as',session_id=sid,output_path='sdk.dpa')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    self.assertEqual(used,{'capabilities','open_project','inspect','plan_changes','validate','preview','apply_plan','save_as','diff'})
                    raw=(fixture.root/'sdk.dpa').read_bytes()
                    self.assertEqual(NativeAdapter(raw,'delta_diascreen').envelope.body,raw_expected(fixture.raw))
                    self.assertEqual((fixture.root/'source.dpa').read_bytes(),fixture.raw)
                    self.assertFalse(applied['program_writer_complete']);self.assertEqual(saved['vendor'],'NOT_RUN')
        asyncio.run(exercise())


if __name__=='__main__':
    unittest.main()
