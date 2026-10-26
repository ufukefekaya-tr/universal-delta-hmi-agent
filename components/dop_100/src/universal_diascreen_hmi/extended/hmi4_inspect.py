# SPDX-License-Identifier: Apache-2.0
"""Complete indexed native inventory, typed affine scaling, navigation and ABI audit."""
from decimal import Decimal,InvalidOperation
import re
from .hmi4_bootstrap import *
NATIVE_FIELDS=('Type','SubType','X','Y','Width','Height','Style','nPartsID','ReadVar','WriteVar','ReadLink','WriteLink','MemLen','MemFmt','ReadMemType','WriteMemType','Level','GainValue','OffsetValue','DotNum','IntNum','MinValue','MaxValue','HiWordFirst','HiDwordFirst','Order','Variation','VisibleLink','VisibleVar','VisibleCondition','InterLockVar','InterLockLevel','InterLockViewMode','TriggerVar','ReadOffsetVar','WriteOffsetVar','GoToScreenID','GoToScreenName','SetValue','EventID','SetLowSecurity','ScaleFontSize','ScaleFontColor','ScaleColor','ScaleDock','ScaleWidth','ScaleStyle','MainScale','SubScale')
def dec(x):
    require(isinstance(x,(str,int)) and not isinstance(x,bool),'DECIMAL','Exact decimal string/integer required')
    try:v=Decimal(str(x))
    except InvalidOperation:require(False,'DECIMAL','Invalid decimal')
    require(v.is_finite() and abs(v)<=Decimal('1e15'),'DECIMAL','Bounded finite decimal required');return v
def element_hash(q,e):return sha(q.file.payload[e.section.start:e.end])
def field(q,s,k,default=''):return q.index.scalar(s,k,default)
def family(q,e):return q.index.number(e.section,'Type'),q.index.number(e.section,'SubType')
def address(v):
    m=re.fullmatch(r'\{([^{}]+)\}([0-9]+)@([MD][0-9]+)',v or '')
    return dict(link=m[1],station=int(m[2]),address=m[3]) if m else None
def native_type(q,e):
    t,sub=family(q,e);s=e.section
    if t in (1,2) and q.index.number(s,'MemLen',-1)==0 and q.index.number(s,'MemFmt',-1)==2:return 'BOOL'
    if (t,sub) in ((5,1),(6,1),(1,7)):
        return {(1,1):'INT',(2,1):'DINT',(2,5):'REAL',(1,2):'UINT_OR_WORD',(2,2):'UDINT_OR_DWORD'}.get((q.index.number(s,'MemLen',-1),q.index.number(s,'MemFmt',-1)),'UNQUALIFIED')
    return None
def numeric(q,e):
    t,sub=family(q,e)
    if (t,sub) not in ((5,1),(6,1)):return None
    s=e.section;typ=native_type(q,e);gain=dec(field(q,s,'GainValue','1'));offset=dec(field(q,s,'OffsetValue','0'));dots=q.index.number(s,'DotNum',0)
    factor=Decimal(1) if typ=='REAL' else Decimal(10)**dots
    return dict(iec_type=typ,words=q.index.number(s,'MemLen'),native_gain=str(gain),native_offset=str(offset),decimals=dots,effective_gain=str(gain/factor),effective_offset=str(offset/factor),formula='display=(raw*gain+offset)' if typ=='REAL' else 'display=(raw*gain+offset)/10^DotNum',inverse='raw=(display*factor-offset)/gain',factor=str(factor),display_min=field(q,s,'MinValue'),display_max=field(q,s,'MaxValue'),units=[q.index.text(s,'UnitTextLen'+str(j),'').rstrip('\0') for j in range(3)],runtime_qualified=False)
def state_row(q,s):
    return dict(value=q.index.number(s,'Value'),text=[q.index.text(s,'wTextLen'+str(n),'').rstrip('\0') for n in range(3)],font=[field(q,s,'FontName'+str(n),'Arial') for n in range(3)],size=[q.index.number(s,'FontSize'+str(n),14) for n in range(3)],bold=q.index.number(s,'FontBold',0),alignment=q.index.number(s,'FontAlign',34),colorref={k:q.index.number(s,k) for k in ('FontColor','BgColor','FgColor') if s.one(k,optional=True)})
def row(q,p,e):
    s=e.section
    return dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),element_sha256=element_hash(q,e),native={k:field(q,s,k) for k in NATIVE_FIELDS if s.one(k,optional=True)},iec_type=native_type(q,e),numeric=numeric(q,e),states=[state_row(q,st) for st in e.states],macros=[dict(field=t.key,bytes=len(t.blob(q.file.payload)),sha256=sha(t.blob(q.file.payload))) for sec in [s,*e.states] for t in sec.tokens if t.kind=='macro'])
def inventory(q,profile,page_id=None):
    profile_check(q,profile);pages=[q.page(page_id)] if page_id is not None else q.pages
    require(not q.index.unqualified_records and (q.index.stop_reason=='end' or q.index.stop_reason.startswith('resource:')),'INDEX_INCOMPLETE','Partial native page counts are not a complete inventory')
    return dict(candidate_sha256=sha(q.file.original),model=q.metadata(),pages=len(q.pages),objects=sum(len(p.elements) for p in q.pages),coverage=dict(stop_reason=q.index.stop_reason,indexed_bytes=q.index.tail_start,opaque_bytes=len(q.file.payload)-q.index.tail_start,unqualified_records=len(q.index.unqualified_records)),items=[row(q,p,e) for p in pages for e in p.elements],native_qualified=False,vendor_compile='NOT_RUN')
def endpoint(q):
    n=q.index.number(q.app,'PLCIP1')&0xffffffff
    return dict(ip='.'.join(str(n>>s&255) for s in (24,16,8,0)),port=q.index.number(q.app,'PLCPort1'),station=q.index.number(q.app,'DefPLCStationNr1'),driver=field(q,q.app,'ControllerName1'),native_version=field(q,q.app,'Version'),runtime_test='NOT_RUN')
def navigation(q):
    edges=[]
    for p in q.pages:
        for e in p.elements:
            s=e.section;dest=q.index.number(s,'GoToScreenID',0)
            if dest:
                edges.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),target=dest,name=field(q,s,'GoToScreenName'),level=q.index.number(s,'Level',0)))
    ids={p.page_id for p in q.pages};dangling=[e for e in edges if e['target'] not in ids]
    reached={q.index.number(q.app,'DefaultScreen')}
    while True:
        new=reached|{e['target'] for e in edges if e['page_id'] in reached}
        if new==reached:break
        reached=new
    return dict(edges=edges,dangling=dangling,reachable=sorted(reached),unreachable=sorted(ids-reached),status='PASS' if not dangling else 'FAIL',scope='Native navigation and field levels; not runtime authorization')
def contract_rows(contract):
    require(isinstance(contract,dict) and set(contract)<={'schema','tags','forbidden_writes','source_digest','parameters','endpoint','model'} and isinstance(contract.get('tags'),list),'CONTRACT','Exact typed contract object required')
    require(len(contract['tags'])<=4096,'CONTRACT','Tag count exceeds limit');out={}
    for t in contract['tags']:
        require(isinstance(t,dict) and all(k in t for k in ('address','type','words','access')),'TAG','Typed address/width/access required')
        allowed={'tag','address','type','words','access','level','HiWordFirst','HiDwordFirst','enum','numeric_input'}
        require(set(t)<=allowed,'TAG_FIELD_UNQUALIFIED','Unsupported tag constraint/metadata; use explicit numeric_input fields for native gain/range/format')
        adr=t['address'];require(isinstance(adr,str) and re.fullmatch('[MD][0-9]+',adr) and adr not in out,'TAG_DUPLICATE','Unique explicit M/D register required')
        require(t['type'] in ('BOOL','INT','DINT','REAL'),'TYPE_NOT_IMPLEMENTED','Native BOOL/INT/DINT/REAL only; other logical types remain unsupported')
        require(t['words']==(0 if t['type']=='BOOL' else 1 if t['type']=='INT' else 2),'TAG_WIDTH','Wrong native word width')
        require(t['access'] in ('READ_ONLY','HMI_WRITE','PARAMETER_EDIT'),'TAG_ACCESS','Explicit supported access required')
        require(adr.startswith('M' if t['type']=='BOOL' else 'D'),'ADDRESS_SPACE','BOOL uses M; numeric uses D')
        if 'enum' in t:
            values=t['enum'];require(isinstance(values,(dict,list)) and 1<=len(values)<=128 and all(not isinstance(v,bool) and re.fullmatch('-?[0-9]+',str(v)) for v in values),'ENUM','Bounded declared integer enum keys/values required')
        out[adr]=t
    require(isinstance(contract.get('forbidden_writes',[]),list),'CONTRACT','Explicit write restrictions required')
    return out
def check_binding(q,e,contract,tag_address=None):
    tags=contract_rows(contract);s=e.section;typ=native_type(q,e)
    reads=address(field(q,s,'ReadVar'));writes=address(field(q,s,'WriteVar'));uses=[('read',reads),('write',writes)]
    require(any(x for _,x in uses),'BINDING','No native register binding')
    for role,b in uses:
        if b is None:continue
        if tag_address is not None and b['address']!=tag_address:continue
        t=tags.get(b['address']);require(t is not None,'TAG_MISSING','Binding missing from exact typed contract')
        require(typ==t['type'],'TAG_TYPE','Native IEC type differs from contract')
        if role=='write':require(t['access']!='READ_ONLY' and b['address'] not in contract.get('forbidden_writes',[]),'READ_ONLY','Write to read-only/reserved register rejected')
        if 'level' in t and role=='write':require(q.index.number(s,'Level',0)==t['level'],'TAG_LEVEL','Native field security differs')
        for key in ('HiWordFirst','HiDwordFirst'):
            if key in t:require(q.index.number(s,key,0)==t[key],'WORD_ORDER','Word order differs from explicit contract')
        if family(q,e)==(6,1) and 'numeric_input' in t:
            expected=t['numeric_input'];allowed={'MemLen','MemFmt','GainValue','OffsetValue','DotNum','IntNum','MinValue','MaxValue','HiWordFirst','HiDwordFirst','Level','ReadLink','WriteLink'}
            require(isinstance(expected,dict) and set(expected)<=allowed,'CONTRACT_NATIVE_FIELD','Unknown numeric-input contract field')
            for key,value in expected.items():
                actual=field(q,s,key);require(actual!='','TAG_NATIVE','Declared numeric input field is absent')
                equal=dec(actual)==dec(value) if key in {'GainValue','OffsetValue','MinValue','MaxValue'} else str(actual)==str(value)
                require(equal,'TAG_NATIVE','Numeric input '+key+' differs from exact contract')
        if family(q,e)==(6,1) and 'enum' in t:
            allowed={int(v) for v in t['enum']}
            require(typ in ('INT','DINT') and q.index.number(s,'DotNum',0)==0 and dec(field(q,s,'GainValue','1'))==1 and dec(field(q,s,'OffsetValue','0'))==0,'ENUM_INPUT','Enum input needs unscaled integral native format')
            low=dec(field(q,s,'MinValue'));high=dec(field(q,s,'MaxValue'))
            require(low==low.to_integral_value() and high==high.to_integral_value() and low<=high and high-low+1<=len(allowed) and all(v in allowed for v in range(int(low),int(high)+1)),'ENUM_INPUT','Numeric input admits undeclared enum values; use qualified bounds or source constant buttons')
    if family(q,e)==(1,7):
        t=tags[writes['address']];allowed=t.get('enum')
        require(allowed is not None and str(field(q,s,'SetValue')) in {str(v) for v in allowed},'ENUM','Constant button must target a declared sparse enum value')
    return dict(type=typ,read=reads,write=writes,status='PASS',scope='Native declared type/width/access/security/wordorder and optional numeric_input fields; not PLC behavioral equivalence')
def audit_contract(q,contract,contract_sha256,require_all=False,lookup_markers=()):
    hash_value(contract_sha256);require(sha(canonical(contract))==contract_sha256,'CONTRACT_HASH','Contract hash differs');tags=contract_rows(contract)
    rows=[];seen=set()
    for p in q.pages:
        for e in p.elements:
            s=e.section;bindings=[address(field(q,s,k)) for k in ('ReadVar','WriteVar')]
            visible=address(field(q,s,'VisibleVar'))
            if visible and visible['address'] in tags:
                try:
                    from .typed_visibility import readback as visibility_readback
                    detail=visibility_readback(q,e,contract)
                    rows.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),addresses=[visible['address']],status='PASS',visibility=detail));seen.add(visible['address'])
                except ValueError as error:rows.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),addresses=[visible['address']],status='FAIL',role='visibility',reason=str(error)))
            declared=[b['address'] for b in bindings if b and b['address'] in tags]
            if declared:
                try:
                    marker=next((m for m in lookup_markers if m.get('page_id')==p.page_id and m.get('element_id')==q.index.number(s,'nPartsID')),None)
                    if marker is not None:
                        from .state_lookup import readback
                        require(len(declared)==1,'LOOKUP_BINDING','One explicit lookup read address required');detail=readback(q,e,marker,tags[declared[0]])
                        rows.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),addresses=declared,status='PASS',lookup=detail));seen.update(declared);continue
                    # A partial contract audits only declared bindings; the full migration contract can require all.
                    if all(b is None or b['address'] in tags for b in bindings):check_binding(q,e,contract)
                    else:
                        for adr in declared:check_binding(q,e,contract,adr)
                    rows.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),addresses=declared,status='PASS'));seen.update(declared)
                except ValueError as error:rows.append(dict(page_id=p.page_id,element_id=q.index.number(s,'nPartsID'),addresses=declared,status='FAIL',reason=str(error)))
    missing=sorted(set(tags)-seen) if require_all else []
    return dict(status='PASS' if not missing and all(x['status']=='PASS' for x in rows) else 'FAIL',contract_sha256=contract_sha256,matched_addresses=len(seen),missing=missing,rows=rows,native_qualified=False)
