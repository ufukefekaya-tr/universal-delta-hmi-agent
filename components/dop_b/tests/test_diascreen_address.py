"""Invented DIA namespace records; manufacturer bytes are never fixtures."""
from copy import deepcopy
import hashlib
import json
import struct
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.address_contract import source_driver_fingerprint, AddressNamespace
from universal_hmi.native.diascreen_address import DiaScreenAddressNamespace
from universal_hmi.native.records import Record
from universal_hmi.native.codec import Envelope
from test_diascreen_controls import diascreen_controls_fixture


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()


def fixture():
    raw, _ = diascreen_controls_fixture()
    source = NativeAdapter(raw, 'delta_diascreen')
    source.application.one('Version').set_value(b'6.0.00209.8338')
    source.application.records = [r for r in source.application.records
        if not (r.key or '').startswith(('ControllerSection', 'ControllerName', 'CommName'))]
    items = {'ControllerSection1':'Delta', 'ControllerName1':'Invented AS source test driver',
             'DefPLCStationNr1':'1', 'CommName1':'EtherLink1', 'PrivateOpaqueDriver':'never public',
             'PrinterSection0':'NULL'}
    source.application.records += [Record((k+'='+v+'\r\n').encode(), k, v.encode()) for k,v in items.items()]
    locations = {'BOOL':{'read':('5','66'),'write':('5','66')},
                 'UINT':{'read':('6','10'),'write':('2','19')}}
    lookup = {(p['id'],o['id']):o['section'] for p in _groups(source.document) for o in p['elements']}
    maintained = lookup['5','66']
    for direction in ('Read','Write'):
        maintained.one(direction+'Var').set_value(b'{EtherLink1}1@M100')
        maintained.one(direction+'Link').set_value(b'2')
        maintained.one(direction+'MemType').set_value(b'0')
    display, entry = lookup['6','10'], lookup['2','19']
    display.one('ReadVar').set_value(b'{EtherLink1}1@D56');display.one('ReadLink').set_value(b'2')
    entry.one('WriteVar').set_value(b'{EtherLink1}1@D51');entry.one('WriteLink').set_value(b'2')
    # A stored read type3 is deliberately not used as a qualified read witness.
    entry.one('ReadVar').set_value(b'{EtherLink1}1@D51');entry.one('ReadLink').set_value(b'2')
    raw = source.envelope.encode(source.document.bytes())
    source = NativeAdapter(raw, 'delta_diascreen')
    regions = {'BOOL':[dict(area='M',minimum=0,maximum=8191,radix=10,access='ReadWrite')],
               'UINT':[dict(area='D',minimum=0,maximum=29999,radix=10,access='ReadWrite')]}
    authority = dict(schema_version=1,authority_kind='original_neutral_fixture',family='delta_diascreen',
        serialized_version='6.0.00209.8338',driver=dict(company='Delta',name='Invented AS source test driver'),
        regions=regions,evidence={'scope':'MOCK original records, no manufacturer/human/vendor authority'},
        acceptance_scope='OFFLINE_DRIVER_SYNTAX_ONLY')
    authority_raw = encode(authority)
    contract = dict(qualified=True,contract_version=1,mode='diascreen_source_driver_decimal_regions_v1',
        family='delta_diascreen',source_sha256=sha(raw),model_id='268502784',serialized_version='6.0.00209.8338',
        prefix='{EtherLink1}1@',driver=dict(native_index='1',native_link='2',company='Delta',
        name='Invented AS source test driver',raw_span_sha256=source_driver_fingerprint(source,'1')),
        regions=deepcopy(regions),authority_sha256=sha(authority_raw),witnesses={
        datatype:{direction:dict(screen_id=sid,element_id=eid,owner_sha256=source.owner_extent_sha256(sid,eid))
                  for direction,(sid,eid) in directions.items()} for datatype,directions in locations.items()})
    return raw, contract, authority_raw


class DiaScreenAddressTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.contract,self.authority=fixture()
        self.namespace=DiaScreenAddressNamespace(self.raw,self.contract,self.authority)

    def rejects(self, callback):
        with self.assertRaises(HmiError):callback()

    def test_active_source_pins_width_links_and_exact_lowering_metadata(self):
        value=self.namespace.match('{EtherLink1}1@M8191','BOOL','write')
        self.assertEqual(('2','0','EtherLink1','1','ReadWrite'),tuple(value[k] for k in
                         ('native_link','native_mem_type','channel','station','access')))
        self.assertEqual(8191,value['index']);self.assertEqual('M',value['area'])
        self.assertEqual('OFFLINE_SOURCE_DRIVER_SYNTAX_ONLY',value['scope'])

    def test_every_declared_scalar_address_and_both_directions(self):
        # Entire qualified domain, including all boundaries and interior values.
        for datatype,area,maximum in [('BOOL','M',8191),('UINT','D',29999)]:
            for index in range(maximum+1):
                for direction in ('read','write'):
                    result=self.namespace.match(f'{{EtherLink1}}1@{area}{index}',datatype,direction)
                    self.assertEqual(index,result['index'])

    def test_wrong_datatype_area_outside_bounds_and_unqualified_bit_grammar(self):
        for address,datatype in [('{EtherLink1}1@M8192','BOOL'),('{EtherLink1}1@D30000','UINT'),
            ('{EtherLink1}1@D1','BOOL'),('{EtherLink1}1@M1','UINT'),('{EtherLink1}1@D1.0','BOOL'),
            ('{EtherLink1}1@Y61.1','BOOL'),('{EtherLink1}1@X0.0','BOOL'),('{EtherLink1}1@S1','BOOL'),
            ('{EtherLink1}1@SM1','BOOL'),('{EtherLink1}1@SR1','UINT')]:
            with self.subTest(address=address):self.rejects(lambda:self.namespace.match(address,datatype))

    def test_canonical_prefix_station_decimal_grammar_and_bounded_operands(self):
        invalid=['{EtherLink2}1@M1','{EtherLink1}0@M1','{Link1}1@M1','{EtherLink01}1@M1',
            '{EtherLink1}01@M1','{EtherLink1}1@M01','{EtherLink1}1@M-1','{EtherLink1}1@M+1',
            '{EtherLink1}1@m1','{EtherLink1}1@M1\n','{EtherLink1}1@M1\0','{EtherLink1}1@M１',
            'DIA_TAG@{EtherLink1}1@M1','{EtherLink1}1@M'+('9'*10000),None,{},True]
        for address in invalid:
            with self.subTest(address=str(address)[:60]):self.rejects(lambda:self.namespace.match(address,'BOOL'))
        for kind in (None,True,{},'REAL','UDINT','TIME','bool'):
            self.rejects(lambda:self.namespace.match('{EtherLink1}1@M1',kind))
        for direction in (None,True,[],{},'Read','execute'):
            self.rejects(lambda:self.namespace.match('{EtherLink1}1@M1','BOOL',direction))

    def test_authority_raw_pin_metadata_duplicate_fields_and_nonfinite_refuse(self):
        for authority in [self.authority+b' ',b'{}',b'[]',b'{"x":NaN}',b'{"x":1,"x":2}',
                          b'\xff',b'['*2000+b'0'+b']'*2000,b'x'*(1024*1024+1)]:
            contract=deepcopy(self.contract);contract['authority_sha256']=sha(authority)
            # Whitespace-equivalent valid JSON needs a corresponding descriptor
            # pin; such bytes retain meaning, whereas malformed content refuses.
            if authority==self.authority+b' ':continue
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,contract,authority))
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,self.contract,self.authority+b' '))
        original=json.loads(self.authority)
        for key,value in [('family','delta_dopsoft2'),('serialized_version','bad'),('schema_version',True),
                          ('authority_kind','fake'),('acceptance_scope','VENDOR_PASS'),('driver',{}),('regions',{})]:
            data=deepcopy(original);data[key]=value;raw=encode(data);contract=deepcopy(self.contract)
            contract['authority_sha256']=sha(raw)
            with self.subTest(key=key):self.rejects(lambda:DiaScreenAddressNamespace(self.raw,contract,raw))

    def test_contract_shape_primitive_types_extra_missing_and_recursive_data(self):
        for key in self.contract:
            bad=deepcopy(self.contract);del bad[key]
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        mutations=[('qualified',1),('contract_version',True),('mode','control_generation'),
            ('family','delta_dopsoft2'),('model_id',268502784),('model_id','0268502784'),
            ('serialized_version','x\n'),('prefix','{Link1}1@'),('source_sha256','A'*64),
            ('authority_sha256','a'*63),('regions',{}),('witnesses',{}),('driver',{})]
        for key,value in mutations:
            bad=deepcopy(self.contract);bad[key]=value
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        bad=deepcopy(self.contract);bad['extra']=False
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        bad=deepcopy(self.contract);bad['regions']['BOOL'].append(bad)
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))

    def test_source_model_version_body_driver_and_witness_full_extent_drift(self):
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw+b'\0',self.contract,self.authority))
        for key,value in [('source_sha256','a'*64),('model_id','268505092'),('serialized_version','6.0.1')]:
            bad=deepcopy(self.contract);bad[key]=value
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        for key,value in [('native_index','0'),('native_link','1'),('raw_span_sha256','b'*64),
                          ('company','Other'),('name','Other')]:
            bad=deepcopy(self.contract);bad['driver'][key]=value
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        bad=deepcopy(self.contract);bad['prefix']='{EtherLink2}1@'
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        for field,value in [('screen_id','0'),('element_id','0'),('owner_sha256','c'*64)]:
            bad=deepcopy(self.contract);bad['witnesses']['BOOL']['read'][field]=value
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))

    def test_readtype3_never_becomes_direct_read_witness_or_native_output(self):
        bad=deepcopy(self.contract);bad['witnesses']['UINT']['read']=deepcopy(bad['witnesses']['UINT']['write'])
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        meta=self.namespace.inspect()
        self.assertEqual('NOT_CREATED',meta['native_output'])
        self.assertEqual('NOT_OPENED',meta['public_control_capability'])
        self.assertNotIn('PrivateOpaqueDriver',json.dumps(meta))
        self.assertNotIn('never public',json.dumps(meta))

    def test_region_shape_overlap_cross_type_boolean_bounds_and_access(self):
        for key,value in [('minimum',True),('maximum',True),('minimum',-1),('maximum',2147483648),
                          ('radix',8),('radix',True),('area','m'),('area','M\n'),('access','Write'),('access',True)]:
            bad=deepcopy(self.contract);bad['regions']['BOOL'][0][key]=value
            self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        bad=deepcopy(self.contract);bad['regions']['BOOL'].append(deepcopy(bad['regions']['BOOL'][0]))
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))
        bad=deepcopy(self.contract);bad['regions']['UINT'][0]['area']='M'
        self.rejects(lambda:DiaScreenAddressNamespace(self.raw,bad,self.authority))

    def test_readonly_region_refuses_write_and_can_coexist_with_source_write_witness(self):
        contract=deepcopy(self.contract);data=json.loads(self.authority)
        regions=[dict(area='D',minimum=0,maximum=50,radix=10,access='Read'),
                 dict(area='D',minimum=51,maximum=29999,radix=10,access='ReadWrite')]
        contract['regions']['UINT']=regions;data['regions']['UINT']=regions
        authority=encode(data);contract['authority_sha256']=sha(authority)
        ns=DiaScreenAddressNamespace(self.raw,contract,authority)
        self.assertEqual('Read',ns.match('{EtherLink1}1@D50','UINT')['access'])
        self.rejects(lambda:ns.match('{EtherLink1}1@D50','UINT','write'))
        self.assertEqual('ReadWrite',ns.match('{EtherLink1}1@D51','UINT','write')['access'])

    def test_caller_mutation_returned_metadata_and_two_projects_cannot_leak(self):
        self.contract['regions']['BOOL'][0]['maximum']=0
        self.contract['driver']['native_link']='99'
        self.assertEqual('2',self.namespace.match('{EtherLink1}1@M8191','BOOL')['native_link'])
        meta=self.namespace.inspect();meta['regions']['BOOL'][0]['maximum']=0
        self.assertEqual(8191,self.namespace.inspect()['regions']['BOOL'][0]['maximum'])
        raw,contract,authority=fixture();second=DiaScreenAddressNamespace(raw,contract,authority)
        self.assertEqual(self.namespace.match('{EtherLink1}1@D123','UINT'),second.match('{EtherLink1}1@D123','UINT'))
        contract['source_sha256']='a'*64
        self.rejects(lambda:DiaScreenAddressNamespace(raw,contract,authority))

    def test_existing_b_namespace_cannot_accept_new_dia_descriptor(self):
        self.rejects(lambda:AddressNamespace(self.contract))

    def test_rehashed_source_with_wrong_declared_body_length_is_not_qualified(self):
        original=NativeAdapter(self.raw,'delta_diascreen')
        prefix=original.envelope.prefix[:37]+struct.pack('<I',len(original.envelope.body)+1).translate(
            bytes(i^0x64 for i in range(256)))
        raw=Envelope(original.envelope.thumbnail,prefix,original.envelope.body).encode(original.envelope.body)
        contract=deepcopy(self.contract);contract['source_sha256']=sha(raw)
        self.rejects(lambda:DiaScreenAddressNamespace(raw,contract,self.authority))

    def test_rehashed_authority_kind_nonstring_values_have_typed_refusal(self):
        for value in ([],{},None,True,False,1,0,1.5,'unknown'):
            data=json.loads(self.authority);data['authority_kind']=value
            raw=encode(data);contract=deepcopy(self.contract);contract['authority_sha256']=sha(raw)
            with self.subTest(value=value):
                with self.assertRaises(HmiError) as caught:
                    DiaScreenAddressNamespace(self.raw,contract,raw)
                self.assertEqual('DIA_ADDRESS_AUTHORITY',caught.exception.code)


if __name__=='__main__':
    unittest.main()
