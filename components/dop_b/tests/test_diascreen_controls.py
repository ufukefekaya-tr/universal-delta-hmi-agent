"""Invented DIA stored-control fixtures, never manufacturer/runtime evidence."""
from copy import deepcopy
import hashlib
import struct
import tempfile
from pathlib import Path
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.codec import Envelope
from universal_hmi.native.records import Record
from universal_hmi.native.diascreen_control_append import DiaScreenControlAppend
import test_native as neutral


PREFIX = ('Application','Multi-Language','Global-Camera','Event-Trigger','Global-Keypad',
    'Recipe','Recipe32','EnhanceRcp','Ethernet','Modbus_TCP_Server','SIP','RemoteCtrl',
    'VNCCtrl','RTC','LOG','FTP','FTPFile','DataExchange','DataExchangeEnd','LuaData','ExtraZA_ZGSection')
IDENTITIES = {'momentary':('13','3'),'maintained':('5','66'),
    'numeric_input':('2','19'),'numeric_display':('6','10')}
COMMON = '''Type SubType CombineType X Y Width Height GroupID Style BorderColor
PrintSuccessiveData ReadMemType WriteMemType ReadLink WriteLink ReadVar WriteVar MemLen MemFmt
Level OffsetReadMemType OffsetWriteMemType OffsetReadVar OffsetWriteVar OffsetMemLen OffsetMemFmt
nAngle opacity animated antialiasing bFreeze UseBMPText nPartsID nKeypadTabOrder
RelatedFileBrowserPartID wDescTextLen0'''.split()
BUTTON_HEAD = 'ButtonOnMacroLen ButtonOffMacroLen PushTime ModifierKey HotKey WriteReadImmediately'.split()
BUTTON_TAIL = '''SetLowSecurity VisibleLink VisibleVar InterLockLink InterLockVar InterLockLevel
InterLockViewMode ConFirmWindow NoMessage DispAsterisk BeforeExecMacroLen AfterExecMacroLen'''.split()
UNIT = '''UnitType UnitSrc UnitSrcVar UnitDisplay UnitDisplayVar UnitPercent UnitPercent1Var
UnitPercent2Var UnitCustom1Var_1 UnitCustom2Var_1 BackupUnitSrc BackupUnitDisplay'''.split()
INPUT = '''TriggerLink TriggerVar Order MinValue MaxValue IntNum DotNum LeadingZero GainValue
OffsetValue Roundoff Variation SetLowSecurity VisibleLink VisibleVar InterLockLink InterLockVar
InterLockLevel InterLockViewMode BeforeExecMacroLen AfterExecMacroLen DispAsterisk Active KeyPadLeft
KeyPadTop KeyPadRight KeyPadBottom TitleHeight'''.split()
STATE = '''Value FgColor BgColor FillStyle BorderStyle FontColor FontSize0 FontRatio0 FontName0
wTextLen0 FontAlign FontBold FontItalic FontUnderline UsePictureCoord PictureAlign TransEffect
TransColor StretchMode PictureStretch Twinkles SoundIndex'''.split()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def wide(key,text):
    return neutral._wide(key,text)


def owner(document,sid,eid):
    return next(e for p in _groups(document) if p['id']==sid for e in p['elements'] if e['id']==eid)


def extent(document,item):
    return b''.join(s.bytes() for s in document.sections[item['start']:item['end']])


def make_schema(source,authority_sha256='a'*64):
    """Neutral pin builder; constructing a digest does not confer authority."""
    if isinstance(source,bytes):source=NativeAdapter(source,'delta_diascreen')
    pages=_groups(source.document)
    pins=[]
    for p in pages:
        s=p['section'];aux=source.document.sections[p['start']+1]
        pins.append(dict(screen_id=p['id'],header_sha256=sha(s.bytes()),aux_sha256=sha(aux.bytes()),
            doc_width=int(s.one('DocSizeX').value),doc_height=int(s.one('DocSizeY').value),
            panel_width=int(s.one('PanelSizeX').value),panel_height=int(s.one('PanelSizeY').value),
            element_count=len(p['elements'])))
    prefix=b''.join(s.bytes() for s in source.document.sections[:pages[0]['start']])
    return {'diascreen_control_append':dict(qualified=True,contract_version=1,
        mode='diascreen_source_control_append_v1',source_sha256=sha(source.original),family='delta_diascreen',
        model_id='268502784',editor_version='6.0.00205.8268',authority_sha256=authority_sha256,
        prefix_sha256=sha(prefix),tail_sha256=sha(source.document.tail),target_screen_id='20',pages=pins,
        donors={kind:dict(screen_id=sid,element_id=eid,owner_sha256=sha(extent(source.document,owner(source.document,sid,eid))))
            for kind,(sid,eid) in IDENTITIES.items()})}


def donor_bytes(kind,eid):
    keys=COMMON.copy()
    if kind in ('momentary','maintained'):
        keys += BUTTON_HEAD + (['OffVoice'] if kind=='momentary' else []) + BUTTON_TAIL
    elif kind=='numeric_display':
        keys += 'IntNum DotNum LeadingZero GainValue OffsetValue Roundoff VisibleLink VisibleVar'.split()+UNIT+['HiWordFirst']
    else:
        keys += INPUT+UNIT
        for i in range(6):
            keys += [f'wKPFStringLen{i:03}-000',f'KPFontSize{i:03}-000',f'KPFontName{i:03}-000',f'KPFontColor{i:03}',f'KPBkgndColor{i:03}']
        keys += 'RangeFontSize RangeFontColor NoMessage ShowOverRange UseCustKeypad KeypadScreenID HiWordFirst'.split()
    values={key:'0' for key in keys}
    values.update(Type='1' if kind in ('momentary','maintained') else '6' if kind=='numeric_input' else '5',
        SubType={'momentary':'3','maintained':'4','numeric_input':'1','numeric_display':'1'}[kind],
        X='165',Y='150',Width='52',Height='33',Style={'momentary':'3','maintained':'0','numeric_input':'2','numeric_display':'2'}[kind],
        BorderColor='1193046',ReadMemType='3' if kind=='numeric_input' else '0',ReadLink='1',WriteLink='1',
        ReadVar='$510' if kind=='numeric_display' else 'None',WriteVar={'momentary':'$2.1','maintained':'$430.0','numeric_input':'$120','numeric_display':'None'}[kind],
        MemLen='0' if kind in ('momentary','maintained') else '1',MemFmt='2',OffsetReadVar='None',OffsetWriteVar='None',
        OffsetMemLen='1',OffsetMemFmt='2',opacity='255',nPartsID=eid,RelatedFileBrowserPartID='-1',
        VisibleLink='1',VisibleVar='None',InterLockLink='1',InterLockVar='None',InterLockLevel='1',TriggerLink='1',TriggerVar='None',
        MinValue='0',MaxValue='100',IntNum='3' if kind=='numeric_input' else '4',DotNum='0',GainValue='1.0',OffsetValue='0.000000',ShowOverRange='1')
    values.update(UnitType='0',UnitSrc='0',UnitSrcVar='None',UnitDisplay='0',UnitDisplayVar='None',
        UnitPercent='0',UnitPercent1Var='0.0',UnitPercent2Var='100.0',UnitCustom1Var_1='1.0',UnitCustom2Var_1='0.0',
        BackupUnitSrc='0',BackupUnitDisplay='0')
    raw=b'[Element]\r\n'
    for key in keys:
        if key=='wDescTextLen0':raw += wide(key,'Neutral donor '+kind)
        elif key.startswith('wKPFStringLen'):raw += wide(key,'Invented keypad '+key[-7:-4])
        elif key.startswith('KPFontName'):raw += key.encode()+b'=Arial\r\n'
        else:raw += key.encode()+b'='+values[key].encode()+b'\r\n'
    for value in range(2 if kind in ('momentary','maintained') else 1):
        values={key:'0' for key in STATE}
        values.update(Value=str(value),FgColor=str(66051+value),BgColor=str(1056816+value),FontColor=str(660000+value),
            FontSize0='18',FontRatio0='100',FontName0='Arial',FillStyle='0',BorderStyle='1',
            TransEffect='1' if kind=='momentary' else '0',StretchMode='2' if kind=='momentary' else '0',PictureStretch='1' if kind=='momentary' else '0')
        raw += b'[State]\r\n'
        for key in STATE:
            raw += wide(key,f'Neutral {kind} {value}') if key=='wTextLen0' else key.encode()+b'='+values[key].encode()+b'\r\n'
    return raw


def diascreen_controls_fixture():
    """Six neutral pages; 26 original target owners and mixed Doc/Panel sizes."""
    template=Envelope.decode(neutral.synthetic_file(),'delta_diascreen')
    prefix=(b'[Application]\r\nModelName=268502784\r\nVersion=6.0.00205.8268\r\nPanelSeries=DOP-100 series\r\n'
        b'PanelName=Invented controls fixture\r\nControllerName0=NULL\r\nControllerSection0=NULL\r\nCommName0=Link2\r\n'
        b'MeMeCode='+struct.pack('<I',12)+b'[Screen]\r\n!?\r\nInitialMacroLen=4\r\nnn\r\n')
    for name in PREFIX[1:]:
        prefix += b'['+name.encode()+b']\r\nNeutralKept=exact\r\n'
        if name in ('Ethernet','LuaData'):prefix += b'\xff\x00neutral opaque\r\n'
    pages=b''
    for sid in ('20','2','5','6','13','24'):
        dw,dh=(126,96) if sid=='24' else (800,480)
        pages += (b'[Screen]\r\nVER=16\r\nID='+sid.encode()+b'\r\n'+wide('wTextLen','Neutral page '+sid)
            +f'DocSizeX={dw}\r\nDocSizeY={dh}\r\nPanelSizeX=800\r\nPanelSizeY=480\r\nScreenAction=18\r\nEnableCycleMacro=1\r\n'.encode()
            +b'OpenMacroLen=0\r\nCloseMacroLen=0\r\nCycleMacroLen=0\r\n[AuxKeyElement]\r\n')
        if sid=='20':
            for eid in range(1,27):
                pages += (f'[Element]\r\nnPartsID={eid}\r\nGroupID=0\r\nType=10\r\nSubType=6\r\nX=1\r\nY={eid}\r\nWidth=140\r\nHeight=1\r\nUnknownRetained=asymmetric\r\n'.encode()
                    +b'[State]\r\nValue=0\r\n'+wide('wTextLen0','Original '+str(eid)))
        elif sid=='24':
            pages += b'[Element]\r\nnPartsID=96\r\nGroupID=0\r\nType=10\r\nSubType=6\r\nX=1\r\nY=1\r\nWidth=20\r\nHeight=10\r\n[State]\r\nValue=0\r\n'+wide('wTextLen0','Aux')
        else:
            kind=next(k for k,(s,e) in IDENTITIES.items() if s==sid)
            pages += donor_bytes(kind,IDENTITIES[kind][1])
    # Marker-looking bytes in opaque resources are deliberately never owners.
    body=prefix+pages+b'[History]\r\nNeutral tail\x00\r\n[Screen]\r\n[nPartsID=98]\r\n'
    pre=bytearray(range(41));pre[37:41]=struct.pack('<I',len(body)).translate(bytes(i^0x64 for i in range(256)))
    raw=Envelope(template.thumbnail,bytes(pre),body).encode(body)
    return raw,make_schema(raw)


def operations():
    result=[]
    for index,kind in enumerate(('momentary','maintained','numeric_input','numeric_display')):
        result.append(dict(op='append_control',screen_id='20',element_id=str(97+index),donor_kind=kind,
            x=180,y=80+index*80,width=120,height=40,
            captions=[dict(value=0,text='KAPALI ÇĞ'),dict(value=1,text='AÇIK')] if index<2 else []))
    return result


class DiascreenControlNativeTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.schema=diascreen_controls_fixture()
        self.source=NativeAdapter(self.raw,'delta_diascreen')
        self.program=DiaScreenControlAppend(self.source,self.schema)

    def changed_source(self,mutation,repin=True):
        doc=deepcopy(self.source.document);mutation(doc)
        a=NativeAdapter(self.source.envelope.encode(doc.bytes()),'delta_diascreen')
        return a,make_schema(a) if repin else deepcopy(self.schema)

    def test_four_controls_saved_reopen_replay_and_complete_restoration(self):
        ops=operations();new=self.program.apply(ops)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'neutral.dpa';p.write_bytes(new);candidate=NativeAdapter(p.read_bytes(),'delta_diascreen')
        self.assertTrue(self.program.verify(candidate,ops))
        self.assertEqual(candidate.envelope.body,self.program.expected_body(ops))
        self.assertEqual(new,DiaScreenControlAppend(self.source,deepcopy(self.schema)).apply(ops))
        page=_groups(candidate.document)[0];self.assertEqual(len(page['elements']),30)
        omitted={i for e in page['elements'][26:] for i in range(e['start'],e['end'])}
        restored=b''.join(s.bytes() for i,s in enumerate(candidate.document.sections) if i not in omitted)+candidate.document.tail
        self.assertEqual(restored,self.source.envelope.body)
        for p in _groups(self.source.document):
            for e in p['elements']:
                self.assertEqual(candidate.owner_extent_sha256(p['id'],e['id']),self.source.owner_extent_sha256(p['id'],e['id']))
        self.assertEqual(candidate.document.tail,self.source.document.tail)
        self.assertEqual(candidate.envelope.thumbnail,self.source.envelope.thumbnail)
        self.assertEqual(candidate.envelope.prefix[:37],self.source.envelope.prefix[:37])
        self.assertEqual(candidate.envelope.declared_body_length(),len(candidate.envelope.body))
        self.assertEqual(self.source.original,self.raw)

    def test_independent_raw_expected_clone_and_insertion(self):
        op=operations()[0];d=owner(self.source.document,'13','3');raw=extent(self.source.document,d)
        # Entire oracle is handwritten source-field substitution, not class helpers.
        for old,new in [(b'nPartsID=3\r\n',b'nPartsID=97\r\n'),(b'X=165\r\n',b'X=180\r\n'),
                (b'Y=150\r\n',b'Y=80\r\n'),(b'Width=52\r\n',b'Width=120\r\n'),(b'Height=33\r\n',b'Height=40\r\n')]:raw=raw.replace(old,new,1)
        raw=raw.replace(wide('wTextLen0','Neutral momentary 0'),wide('wTextLen0','KAPALI ÇĞ'),1)
        raw=raw.replace(wide('wTextLen0','Neutral momentary 1'),wide('wTextLen0','AÇIK'),1)
        end=self.source.envelope.body.index(b'[Screen]\r\nVER=16\r\nID=2\r\n')
        expected=self.source.envelope.body[:end]+raw+self.source.envelope.body[end:]
        self.assertEqual(NativeAdapter(self.program.apply([op]),'delta_diascreen').envelope.body,expected)

    def test_empty_operations_preserve_every_byte_and_verify_requires_identical_file(self):
        self.assertEqual(self.program.apply([]),self.raw)
        self.assertEqual(self.program.expected_body([]),self.source.envelope.body)
        self.assertTrue(self.program.verify(self.raw,[]))
        # A changed gzip header is a different file even though BODY is equal.
        changed=bytearray(self.raw);offset=len(self.source.envelope.thumbnail);changed[offset+4]^=1
        with self.assertRaises(HmiError):self.program.verify(bytes(changed),[])

    def test_shared_source_bindings_and_disabled_numeric_read_metadata_exact(self):
        candidate=NativeAdapter(self.program.apply(operations()),'delta_diascreen')
        for op in operations():
            s=owner(candidate.document,'20',op['element_id'])['section'];d=self.program._donors[op['donor_kind']]['section']
            for key in ('ReadVar','WriteVar','ReadMemType','WriteMemType','ReadLink','WriteLink','MemLen','MemFmt'):
                self.assertEqual(s.one(key).raw,d.one(key).raw)
        self.assertEqual(owner(candidate.document,'20','99')['section'].one('ReadMemType').value,b'3')
        self.assertEqual(owner(candidate.document,'20','99')['section'].one('ReadVar').value,b'None')

    def test_source_effects_font_colors_units_keypad_and_page24_preserved(self):
        candidate=NativeAdapter(self.program.apply(operations()),'delta_diascreen')
        new=owner(candidate.document,'20','97');old=owner(self.source.document,'13','3')
        for state,newstate in zip(old['states'],new['states']):
            for key in ('TransEffect','StretchMode','PictureStretch','FgColor','BgColor','FontSize0','FontRatio0'):
                self.assertEqual(state.one(key).raw,newstate.one(key).raw)
        new=owner(candidate.document,'20','99');old=owner(self.source.document,'2','19')
        for key in UNIT+[f'wKPFStringLen{i:03}-000' for i in range(6)]:self.assertEqual(old['section'].one(key).raw,new['section'].one(key).raw)
        p=next(p for p in _groups(candidate.document) if p['id']=='24')
        self.assertEqual(p['section'].one('DocSizeX').value,b'126');self.assertEqual(p['section'].one('PanelSizeX').value,b'800')

    def test_source_pin_and_descriptor_projection_freshness(self):
        for target in ('schema','contract','document','envelope','identity','raw'):
            raw,schema=diascreen_controls_fixture();a=NativeAdapter(raw,'delta_diascreen');p=DiaScreenControlAppend(a,schema)
            if target=='schema':schema['diascreen_control_append']['authority_sha256']='b'*64
            elif target=='contract':p.contract['authority_sha256']='b'*64
            elif target=='document':owner(a.document,'20','1')['section'].one('X').set_value(b'2')
            elif target=='envelope':a.envelope=Envelope(a.envelope.thumbnail,bytes(41),a.envelope.body)
            elif target=='identity':a.editor_version='OTHER'
            else:a.original=a.original+b' '
            with self.subTest(target=target),self.assertRaises(HmiError):p.apply([])

    def test_schema_exact_keys_types_unmixed_and_digest_grammar(self):
        for field,value in [('qualified',1),('contract_version',True),('mode',[]),('family',{}),('model_id',268502784),
                ('editor_version','6.0.00209.8338'),('source_sha256','f'*64),('authority_sha256','A'*64),
                ('prefix_sha256','f'*64),('tail_sha256','f'*64),('target_screen_id','2'),('pages',[]),('donors',{})]:
            schema=deepcopy(self.schema);schema['diascreen_control_append'][field]=value
            with self.subTest(field=field),self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)
        for key in ('qualified','native_candidate','control_generation','preserved_layout','numeric','arbitrary'):
            schema=deepcopy(self.schema);schema[key]={}
            with self.subTest(key=key),self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)
        schema=deepcopy(self.schema);schema['diascreen_control_append']['extra']=0
        with self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)

    def test_page_and_donor_pins_order_dimensions_and_full_owner_hash(self):
        for field,value in [('screen_id','21'),('header_sha256','f'*64),('aux_sha256','f'*64),
                ('doc_width',799),('panel_height',False),('element_count',25)]:
            schema=deepcopy(self.schema);schema['diascreen_control_append']['pages'][0][field]=value
            with self.subTest(field=field),self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)
        schema=deepcopy(self.schema);schema['diascreen_control_append']['pages'].reverse()
        with self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)
        for field,value in [('screen_id','20'),('element_id','3'),('owner_sha256','f'*64)]:
            schema=deepcopy(self.schema);schema['diascreen_control_append']['donors']['maintained'][field]=value
            with self.subTest(field=field),self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)

    def test_rehashed_donor_binding_type_numeric_macro_visibility_group_and_picture_refuse(self):
        cases=[('Type',b'2'),('SubType',b'1'),('WriteVar',b'$3.1'),('ReadVar',b'$2.1'),('MemLen',b'1'),
            ('MemFmt',b'1'),('GroupID',b'1'),('VisibleVar',b'$1.0'),('InterLockVar',b'$1.0'),('OffsetWriteVar',b'$1'),
            ('ModifierKey',b'1'),('ConFirmWindow',b'1'),('RelatedFileBrowserPartID',b'1')]
        for key,value in cases:
            a,schema=self.changed_source(lambda d:owner(d,'13','3')['section'].one(key).set_value(value))
            with self.subTest(key=key),self.assertRaises(HmiError):DiaScreenControlAppend(a,schema)
        for location,record in [('element',Record(b'PictureOffset=0\r\n','PictureOffset',b'0')),
                ('state',Record(b'PictureName=other\r\n','PictureName',b'other')),
                ('element',Record(b'BeforeExecMacroLen=4\r\nxx\r\n','BeforeExecMacroLen',b'4',b'xx\r\n','macro'))]:
            def mutate(d):
                e=owner(d,'13','3');part=e['section'] if location=='element' else e['states'][0];part.records.append(record)
            a,schema=self.changed_source(mutate)
            with self.subTest(location=location,key=record.key),self.assertRaises(HmiError):DiaScreenControlAppend(a,schema)
        for key,value in [('DotNum',b'1'),('GainValue',b'2.0'),('MinValue',b'-1'),('TriggerVar',b'$2.1'),('ReadMemType',b'0')]:
            a,schema=self.changed_source(lambda d:owner(d,'2','19')['section'].one(key).set_value(value))
            with self.subTest(key=key),self.assertRaises(HmiError):DiaScreenControlAppend(a,schema)

    def test_rehashed_source_prefix_variant_aux_shape_group_and_newid_collision_refuse(self):
        mutations=[lambda d:setattr(d.sections[2],'header',b'[Other]\r\n'),
            lambda d:d.sections.pop(3),lambda d:d.sections.insert(2,deepcopy(d.sections[1])),
            lambda d:d.sections[_groups(d)[0]['start']+1].records.append(Record(b'ID=1\r\n','ID',b'1')),
            lambda d:owner(d,'20','1')['section'].one('nPartsID').set_value(b'97'),
            lambda d:owner(d,'20','1')['section'].one('GroupID').set_value(b'1'),
            lambda d:d.sections[0].one('ModelName').set_value(b'268502785'),
            lambda d:d.sections[0].one('Version').set_value(b'6.0.00205.8269')]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index),self.assertRaises(HmiError):
                a,schema=self.changed_source(mutation)
                DiaScreenControlAppend(a,schema)

    def test_each_forbidden_operation_and_extra_intent_refuse_even_noop(self):
        for name in ('bind','set_text','set_property','configure_numeric','clone_element','clone_screen','delete_literal','convert_numeric_storage'):
            op=operations()[0];op['op']=name
            with self.subTest(name=name),self.assertRaises(HmiError):self.program.apply([op])
        for key,value in [('address','$2.1'),('font_size',18),('style',3),('states',[]),('macro',0),('data_type','UINT')]:
            op=operations()[0];op[key]=value
            with self.subTest(key=key),self.assertRaises(HmiError):self.program.apply([op])

    def test_ids_duplicates_cross_page_target_and_geometry_limits(self):
        for field,value in [('element_id','3'),('element_id','096'),('element_id','101'),('element_id','65536'),
                ('screen_id','24'),('x',-1),('y',True),('width',0),('height',481),('x',799),('y',479)]:
            op=operations()[0];op[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(HmiError):self.program.apply([op])
        with self.assertRaises(HmiError):self.program.apply([operations()[0],operations()[0]])
        with self.assertRaises(HmiError):self.program.apply(operations()+[operations()[0]])

    def test_caption_state_value_frame_and_unicode_limits(self):
        for captions in ([],[{'value':1,'text':'A'},{'value':0,'text':'B'}],
                [{'value':True,'text':'A'},{'value':1,'text':'B'}],
                [{'value':0,'text':'\ud800'},{'value':1,'text':'B'}],
                [{'value':0,'text':'A\0B'},{'value':1,'text':'B'}],
                [{'value':0,'text':'A'*1025},{'value':1,'text':'B'}],
                [{'value':0,'text':'A','language':0},{'value':1,'text':'B'}]):
            op=operations()[0];op['captions']=captions
            with self.subTest(captions=repr(captions)[:60]),self.assertRaises(HmiError):self.program.apply([op])
        op=operations()[2];op['captions']=[{'value':0,'text':'forbidden'}]
        with self.assertRaises(HmiError):self.program.apply([op])
        op=operations()[0];op['captions']=[{'value':0,'text':'[Screen]\r\n$120'},{'value':1,'text':'Ç😀'}]
        new=self.program.apply([op]);self.assertTrue(self.program.verify(new,[op]))

    def test_malformed_deep_cyclic_nonjson_inputs_raise_typed_and_leave_source_unchanged(self):
        for field in operations()[0]:
            for value in (None,[],{},True,0,1.5,''):
                if field in ('x','y') and type(value) is int and value==0:continue
                op=operations()[0];op[field]=value
                with self.subTest(field=field,value=value),self.assertRaises(HmiError):self.program.apply([op])
        cycle=[];cycle.append(cycle)
        deep=[];cursor=deep
        for _ in range(20):child=[];cursor.append(child);cursor=child
        for operations_bad in (cycle,deep,{},None,[set()],[[operations()[0]]]):
            with self.assertRaises(HmiError):self.program.apply(operations_bad)
        self.assertEqual(self.source.original,self.raw)
        self.assertEqual(self.source.document.bytes(),self.source.envelope.body)

    def test_candidate_new_state_address_type_format_effect_hidden_fields_and_tail_tamper_refuse(self):
        ops=operations();good=NativeAdapter(self.program.apply(ops),'delta_diascreen')
        for mutation in ('ReadVar','ReadMemType','MemLen','MemFmt','SubType','Style','nPartsID','unknown','caption','value','effects','new-state','original','page','tail'):
            doc=deepcopy(good.document);e=owner(doc,'20','97')
            if mutation in ('ReadVar','ReadMemType','MemLen','MemFmt','SubType','Style','nPartsID'):
                e['section'].one(mutation).set_value(b'$5.1' if mutation=='ReadVar' else b'1' if mutation=='MemFmt' else b'2')
            elif mutation=='unknown':e['section'].records.append(Record(b'Unknown=1\r\n','Unknown',b'1'))
            elif mutation=='caption':e['states'][0].one('wTextLen0').set_text('Other')
            elif mutation=='value':e['states'][0].one('Value').set_value(b'2')
            elif mutation=='effects':e['states'][0].one('TransEffect').set_value(b'0')
            elif mutation=='new-state':doc.sections.insert(e['end'],deepcopy(e['states'][0]))
            elif mutation=='original':owner(doc,'20','1')['section'].one('X').set_value(b'2')
            elif mutation=='page':_groups(doc)[-1]['section'].one('PanelSizeX').set_value(b'126')
            else:doc.tail += b'changed\r\n'
            raw=good.envelope.encode(doc.bytes())
            with self.subTest(mutation=mutation),self.assertRaises(HmiError):self.program.verify(raw,ops)

    def test_candidate_envelope_staleness_reorder_missing_extra_controls_and_wrong_request(self):
        ops=operations();good=NativeAdapter(self.program.apply(ops),'delta_diascreen')
        for field in ('prefix','thumbnail','cached'):
            a=NativeAdapter(good.original,'delta_diascreen')
            if field=='cached':owner(a.document,'20','97')['section'].one('X').set_value(b'181')
            else:
                prefix=a.envelope.prefix;thumb=a.envelope.thumbnail
                if field=='prefix':prefix=bytes([prefix[0]^1])+prefix[1:]
                else:thumb=thumb[:-1]+bytes([thumb[-1]^1])
                a=NativeAdapter(Envelope(thumb,prefix,a.envelope.body).encode(a.envelope.body),'delta_diascreen')
            with self.subTest(field=field),self.assertRaises(HmiError):self.program.verify(a,ops)
        with self.assertRaises(HmiError):self.program.verify(good,ops[:-1])
        with self.assertRaises(HmiError):self.program.verify(good,list(reversed(ops)))
        extra=deepcopy(ops);extra[0]['x']=181
        with self.assertRaises(HmiError):self.program.verify(good,extra)
        self.assertTrue(self.program.verify(good,ops))

    def test_rehashed_source_state_duplicate_values_effects_macro_and_nonascii_rejected(self):
        mutations=[lambda d:owner(d,'13','3')['states'][1].one('Value').set_value(b'0'),
            lambda d:owner(d,'13','3')['states'][0].one('TransEffect').set_value(b'0'),
            lambda d:owner(d,'13','3')['states'][0].records.append(deepcopy(owner(d,'13','3')['states'][0].one('wTextLen0'))),
            lambda d:owner(d,'13','3')['section'].one('Type').set_value(b'\xff'),
            lambda d:owner(d,'13','3')['section'].records.append(Record(b'ButtonOnMacroLen=0\r\n','ButtonOnMacroLen',b'0',b'','macro'))]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index),self.assertRaises(HmiError):
                a,schema=self.changed_source(mutation)
                DiaScreenControlAppend(a,schema)
        doc=deepcopy(self.source.document);e=owner(doc,'13','3')
        doc.sections.insert(e['end'],deepcopy(e['states'][0]))
        a=NativeAdapter(self.source.envelope.encode(doc.bytes()),'delta_diascreen')
        with self.assertRaises(HmiError):DiaScreenControlAppend(a,make_schema(a))

    def test_source_tail_drift_wrong_family_deep_schema_and_failed_request_no_output(self):
        a,schema=self.changed_source(lambda d:setattr(d,'tail',d.tail+b'new\r\n'),repin=False)
        with self.assertRaises(HmiError):DiaScreenControlAppend(a,schema)
        envelope=Envelope.decode(neutral.synthetic_file('delta_dopsoft2'),'delta_dopsoft2')
        raw=Envelope(envelope.thumbnail,self.source.envelope.prefix,self.source.envelope.body).encode(self.source.envelope.body)
        with self.assertRaises(HmiError):DiaScreenControlAppend(NativeAdapter(raw,'delta_dopsoft2'),self.schema)
        schema=deepcopy(self.schema);schema['cycle']=schema
        with self.assertRaises(HmiError):DiaScreenControlAppend(self.source,schema)
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'rejected.dpa'
            bad=operations();bad[-1]['captions']=[{'value':0,'text':'wrong'}]
            with self.assertRaises(HmiError):output.write_bytes(self.program.apply(bad))
            self.assertFalse(output.exists())
        self.assertEqual(self.source.document.bytes(),self.source.envelope.body)
        self.assertEqual(self.source.original,self.raw)


if __name__=='__main__':
    unittest.main()
