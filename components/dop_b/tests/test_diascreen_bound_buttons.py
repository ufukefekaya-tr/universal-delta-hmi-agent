"""Original neutral records for stored maintained-address generation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.address_contract import source_driver_fingerprint
from universal_hmi.native.records import Section
from universal_hmi.native.diascreen_bound_buttons import DiaScreenBoundButtons
from test_diascreen_address import fixture as address_fixture, sha, encode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from calibrate_diascreen_buttons import capture_contract


def pins(raw, namespace, authority):
    a=NativeAdapter(raw,'delta_diascreen');namespace=deepcopy(namespace)
    namespace['source_sha256']=sha(raw)
    namespace['driver']['raw_span_sha256']=source_driver_fingerprint(a,'1')
    for directions in namespace['witnesses'].values():
        for witness in directions.values():
            witness['owner_sha256']=a.owner_extent_sha256(witness['screen_id'],witness['element_id'])
    donor=dict(screen_id='5',element_id='14',owner_sha256=a.owner_extent_sha256('5','14'))
    review=dict(contract_version=1,scope='BOUND_BUTTON_STORED_REVIEW',source_sha256=sha(raw),
        family='delta_diascreen',model_id=268502784,serialized_version='6.0.00209.8338',
        donor=donor,namespace_sha256=canonical_hash(namespace),review_reference='Original neutral tests only; no human/vendor/production qualification')
    review_raw=encode(review)
    contract=capture_contract(a,namespace,sha(review_raw),'5','14','5')
    return raw,contract,authority,review_raw


def fixture():
    raw,namespace,authority=address_fixture();a=NativeAdapter(raw,'delta_diascreen')
    pages=_groups(a.document)
    sections=a.document.sections[:pages[0]['start']]
    index=next(i for i,s in enumerate(sections) if s.name=='Modbus_TCP_Server')+1
    sections.insert(index,Section('WEB_OUTPUT',b'[WEB_OUTPUT]\r\n',[]))
    for p in pages:
        if p['id'] in {'2','5','6'}:
            parts=deepcopy(a.document.sections[p['start']:p['end']]);sections.extend(parts)
            if p['id']=='5':
                donor=deepcopy(parts[2:])
                for k,v in {'nPartsID':'14','Style':'2','antialiasing':'1',
                            'ReadVar':'{EtherLink1}1@D2005.0','WriteVar':'{EtherLink1}1@D2005.0'}.items():
                    donor[0].one(k).set_value(v.encode())
                for value,s in enumerate(donor[1:]):
                    for k,v in dict(Value=str(value),FgColor=str(16575083-value*1343597),
                            BgColor='11842740',FontColor='0',FillStyle='0',BorderStyle='0',
                            FontSize0='36',FontRatio0='100',FontAlign='34',FontBold='1',
                            FontItalic='0',FontUnderline='0',UsePictureCoord='0',PictureAlign='34',
                            TransEffect='0',TransColor='0',StretchMode='0',PictureStretch='0',
                            Twinkles='0',SoundIndex='0').items():s.one(k).set_value(v.encode())
                sections.extend(donor)
    a.document.sections=sections
    raw=a.envelope.encode(a.document.bytes())
    return pins(raw,namespace,authority)


def operations():
    return [dict(op='append_bound_button',screen_id='5',element_id='1001',
        x=10,y=300,width=260,height=60,address='{EtherLink1}1@M101',captions=['İSTEK KAPALI','İSTEK AÇIK'])]


def mutate_source(data, change):
    raw,c,authority,_=data;a=NativeAdapter(raw,'delta_diascreen')
    donor=next(o for p in _groups(a.document) if p['id']=='5' for o in p['elements'] if o['id']=='14')
    change(a,donor)
    changed=a.envelope.encode(a.document.bytes())
    return pins(changed,c['namespace'],authority)


class DiaScreenBoundButtonTests(unittest.TestCase):
    def setUp(self):
        self.data=fixture();self.raw,self.contract,self.authority,self.review=self.data
        self.program=DiaScreenBoundButtons(self.raw,self.contract,self.authority)

    def reject(self, fn):
        with self.assertRaises(HmiError):fn()

    def test_saved_reopen_new_explicit_bool_binding_type_and_two_turkish_states(self):
        ops=operations();raw=self.program.apply(ops)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'new.dpa';path.write_bytes(raw);a=NativeAdapter(path.read_bytes(),'delta_diascreen')
        self.assertTrue(self.program.verify(a,ops))
        owner=next(o for p in _groups(a.document) if p['id']=='5' for o in p['elements'] if o['id']=='1001')
        fields=owner['section'].fields()
        for k,v in {'Type':'1','SubType':'4','ReadVar':'{EtherLink1}1@M101','WriteVar':'{EtherLink1}1@M101',
                    'ReadLink':'2','WriteLink':'2','ReadMemType':'0','WriteMemType':'0','MemLen':'0','MemFmt':'2'}.items():
            self.assertEqual(v,fields[k])
        self.assertEqual(['İSTEK KAPALI','İSTEK AÇIK'],[s.one('wTextLen0').text() for s in owner['states']])
        self.assertNotEqual(self.raw,raw)

    def test_independent_raw_oracle_whole_body_and_original_restoration(self):
        op=operations()[0];raw=self.program.apply([op]);a=NativeAdapter(self.raw,'delta_diascreen')
        page=next(p for p in _groups(a.document) if p['id']=='5')
        donor=next(o for o in page['elements'] if o['id']=='14');out=[]
        replacements={'nPartsID':'1001','X':'10','Y':'300','Width':'260','Height':'60',
                      'ReadVar':'{EtherLink1}1@M101','WriteVar':'{EtherLink1}1@M101'}
        for n,s in enumerate(a.document.sections[donor['start']:donor['end']]):
            out.append(s.header)
            for r in s.records:
                if n==0 and r.key in replacements:out.append(r.key.encode()+b'='+replacements[r.key].encode()+b'\r\n')
                elif n and r.key=='wTextLen0':
                    blob=op['captions'][n-1].encode('utf-16-le')+b'\0\0'
                    out.append(b'wTextLen0='+str(len(blob)).encode()+b'\r\n'+blob+b'\r\n')
                else:out.append(r.raw)
        pos=sum(len(s.bytes()) for s in a.document.sections[:page['end']])
        expected=a.envelope.body[:pos]+b''.join(out)+a.envelope.body[pos:]
        candidate=NativeAdapter(raw,'delta_diascreen');self.assertEqual(expected,candidate.envelope.body)
        self.assertEqual(a.envelope.thumbnail,candidate.envelope.thumbnail)
        fresh=next(o for p in _groups(candidate.document) for o in p['elements'] if o['id']=='1001')
        restored=b''.join(s.bytes() for i,s in enumerate(candidate.document.sections)
            if not fresh['start']<=i<fresh['end'])+candidate.document.tail
        self.assertEqual(a.envelope.body,restored)

    def test_empty_noop_exact_file_replay_and_two_instances(self):
        self.assertEqual(self.raw,self.program.apply([]));self.assertTrue(self.program.verify(self.raw,[]))
        self.assertEqual(self.program.apply(operations()),DiaScreenBoundButtons(self.raw,self.contract,self.authority).apply(operations()))
        op=operations();op[0]['address']='{EtherLink1}1@M102'
        self.assertNotEqual(self.program.apply(op),self.program.apply(operations()))

    def test_original_dotted_address_stays_provenance_and_refuses_as_new_scalar(self):
        self.reject(lambda:self.program.match_address('{EtherLink1}1@D2005.0'))
        for address in ('{EtherLink1}1@M0','{EtherLink1}1@M8191'):
            op=operations();op[0]['address']=address;self.assertTrue(self.program.verify(self.program.apply(op),op))

    def test_typed_operation_shape_geometry_ids_and_caption_failures(self):
        for key,value in [('x',True),('y',-1),('width',0),('height',[]),('x',799),('screen_id','2'),
                          ('element_id','14'),('element_id','01001'),('element_id',1001),('captions',[]),
                          ('captions',['SAME','same']),('captions',['\0','open']),('captions',['\ud800','open'])]:
            op=operations();op[0][key]=value
            self.reject(lambda:self.program.apply(op))
        self.reject(lambda:self.program.apply(operations()*2));self.reject(lambda:self.program.apply(operations()*17))
        for malformed in (None,{},[{}]):self.reject(lambda:self.program.apply(malformed))

    def test_channel_station_type_grammar_and_out_of_range_addresses_refuse(self):
        for value in (None,{},True,'{EtherLink2}1@M101','{EtherLink1}0@M101','{EtherLink1}1@M8192',
                      '{EtherLink1}1@D101','{EtherLink1}1@M0101','{EtherLink1}1@M-1','{EtherLink1}1@X0.0'):
            op=operations();op[0]['address']=value;self.reject(lambda:self.program.apply(op))

    def test_known_raw_legacy_font_record_preserved_without_normalization(self):
        legacy=bytes.fromhex('b74cb36ea5bfb6c2c5e9')
        changed=mutate_source(self.data,lambda a,o:[s.one('FontName0').set_value(legacy) for s in o['states']])
        raw,c,authority,_=changed;p=DiaScreenBoundButtons(raw,c,authority);out=NativeAdapter(p.apply(operations()),'delta_diascreen')
        new=next(o for page in _groups(out.document) for o in page['elements'] if o['id']=='1001')
        self.assertEqual([b'FontName0='+legacy+b'\r\n']*2,[s.one('FontName0').raw for s in new['states']])
        changed=mutate_source(self.data,lambda a,o:o['states'][0].one('FontName0').set_value(b'UnknownOpaque'))
        self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))

    def test_rehashed_live_dependencies_storage_behavior_and_unknown_fields_refuse(self):
        for key,value in [('VisibleVar','{EtherLink1}1@M5'),('InterLockVar','{EtherLink1}1@M5'),
            ('OffsetReadVar','{EtherLink1}1@M5'),('GroupID','7'),('SubType','3'),('MemLen','1'),('MemFmt','5'),
            ('ReadMemType','3'),('WriteReadImmediately','1'),('Style','3'),('antialiasing','0')]:
            changed=mutate_source(self.data,lambda a,o:o['section'].one(key).set_value(value.encode()))
            self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))
        def macro(a,o):
            r=o['section'].one('BeforeExecMacroLen')
            r.raw=b'BeforeExecMacroLen=6\r\n1234\r\n';r.value=b'6';r.blob=b'1234\r\n';r.kind='macro'
        changed=mutate_source(self.data,macro);self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))
        from universal_hmi.native.records import Record
        changed=mutate_source(self.data,lambda a,o:o['section'].records.append(Record(b'Unexpected=1\r\n','Unexpected',b'1')))
        self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))

    def test_rehashed_state_picture_sound_font_style_and_order_refuse(self):
        for key,value in [('Value','1'),('UsePictureCoord','1'),('SoundIndex','1'),('TransEffect','1'),
                          ('Twinkles','1'),('FontRatio0','99'),('FontBold','0'),('BorderStyle','1')]:
            changed=mutate_source(self.data,lambda a,o:o['states'][0].one(key).set_value(value.encode()))
            self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))
        changed=mutate_source(self.data,lambda a,o:o['states'][0].records.reverse())
        self.reject(lambda:DiaScreenBoundButtons(*changed[:3]))

    def test_source_namespace_authority_and_contract_pins_are_separate(self):
        for key,value in [('source_sha256','a'*64),('prefix_sha256','a'*64),('tail_sha256','a'*64),
                          ('serialized_version','6.4.0'),('model_id','268505092'),('review_sha256',True)]:
            c=deepcopy(self.contract);c[key]=value;self.reject(lambda:DiaScreenBoundButtons(self.raw,c,self.authority))
        c=deepcopy(self.contract);c['namespace']['source_sha256']='a'*64
        self.reject(lambda:DiaScreenBoundButtons(self.raw,c,self.authority))
        self.reject(lambda:DiaScreenBoundButtons(self.raw,self.contract,self.authority+b' '))
        self.reject(lambda:DiaScreenBoundButtons(bytearray(self.raw),self.contract,self.authority))

    def test_caller_dict_and_returned_metadata_cannot_mutate_private_snapshot(self):
        self.contract['donor']['owner_sha256']='a'*64
        self.contract['namespace']['driver']['native_link']='99'
        meta=self.program.source_metadata();meta['state_fills'][0]='#bad'
        self.assertNotEqual('#bad',self.program.source_metadata()['state_fills'][0])
        self.assertTrue(self.program.verify(self.program.apply(operations()),operations()))

    def test_saved_candidate_extra_change_not_hidden_by_restoration_only(self):
        out=NativeAdapter(self.program.apply(operations()),'delta_diascreen')
        owner=next(o for p in _groups(out.document) for o in p['elements'] if o['id']=='1001')
        owner['section'].one('ReadVar').set_value(b'{EtherLink1}1@M102')
        self.reject(lambda:self.program.verify(out.envelope.encode(out.document.bytes()),operations()))
        self.reject(lambda:self.program.verify(self.raw,operations()))


if __name__=='__main__':unittest.main()
