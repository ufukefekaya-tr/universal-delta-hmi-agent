# SPDX-License-Identifier: Apache-2.0
"""Reusable atomic page/element transactions over observed native owners."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import base64,re,struct
from .hmi4_bootstrap import *
from .hmi4_inspect import element_hash,family,native_type,field,dec,address,check_binding,contract_rows
SUPPORTED={(1,3),(1,4),(1,7),(1,10),(2,1),(5,1),(6,1),(7,1),(10,6)}
GEOMETRY={'X','Y','Width','Height'}
STYLE={'FontAlign':{33,34,36},'FontBold':{0,1}}
def ident(v):require(type(v) is int and 0<=v<=65534,'SELECTOR','Bounded integer identity required');return v
def texts(v):
    require(isinstance(v,list) and len(v)==3 and all(isinstance(t,str) and '\0' not in t and len(t.encode('utf-16-le'))<=4096 and all(ord(c)>=32 or c=='\n' for c in t) for t in v),'TEXT','Three bounded UTF-16 language strings required');return v
def rgb_colorref(value):
    require(isinstance(value,str) and re.fullmatch('#[0-9A-Fa-f]{6}',value),'COLOR','RGB hex color required')
    r,g,b=(int(value[i:i+2],16) for i in (1,3,5));return r|(g<<8)|(b<<16)
def png_dib(value):
    require(isinstance(value,str) and len(value)<=4*1024*1024,'PNG','Bounded PNG base64 required')
    try:raw=base64.b64decode(value,validate=True)
    except ValueError:require(False,'PNG','Invalid base64')
    try:from PIL import Image
    except ImportError:require(False,'DEPENDENCY_UNAVAILABLE','Pinned optional Pillow is required for background PNG operations')
    try:
        with Image.open(BytesIO(raw)) as im:
            require(im.format=='PNG' and im.size==(800,480) and im.mode=='RGB','PNG','Opaque RGB PNG800x480 required')
            im.load();pixels=im.tobytes('raw','BGR',2400,-1)
    except (OSError,ValueError,Image.DecompressionBombError):require(False,'PNG','Invalid, excessive or truncated image data')
    return struct.pack('<IiiHHIIiiII',40,800,480,1,24,0,1152000,0,0,0,0)+pixels
def map_resources(q,profile,payload,patches):
    frames=validate_reviewed_resources(q,profile.get('reviewed_resources'));rows=[]
    for frame in frames:
        offset=frame.start+sum(len(p.new)-len(p.old) for p in patches if p.end<=frame.start)
        from universal_diascreen_hmi.resources import _header
        f=_header(payload,offset,frame.section,'size' if frame.section=='DIATag' else 'Size')
        rows.append(dict(section=f.section,header_start=f.start,header_sha256=sha(payload[f.start:f.blob_start]),blob_sha256=sha(payload[f.blob_start:f.blob_end])))
    return dict(reviewed_boundary_ack=True,source_payload_sha256=sha(payload),frames=rows)
def checked_selector(q,op):
    p=ident(op.get('page_id'));i=ident(op.get('element_id'));e=q.element(p,i)
    require(op.get('expected_element_sha256')==element_hash(q,e),'ELEMENT_DRIFT','Exact source element hash required')
    return p,i,e
def macro_free(q,e):return all(not t.blob(q.file.payload) for sec in [e.section,*e.states] for t in sec.tokens if t.kind=='macro')
def rect_check(vals):
    require(all(type(vals[k]) is int for k in GEOMETRY),'GEOMETRY','Integer rectangle required')
    require(0<=vals['X']<vals['X']+vals['Width']<=800 and 0<=vals['Y']<vals['Y']+vals['Height']<=480,'GEOMETRY','Rectangle escapes800x480')
def build(raw,profile,spec,lookup_sources=None):
    require(isinstance(spec,dict) and set(spec)<={'version','operations','contract','contract_sha256','policy'} and spec.get('version')==1,'SPEC','Exact version1 native specification required')
    operations=spec.get('operations');require(isinstance(operations,list) and 1<=len(operations)<=1000,'OPERATIONS','1..1000 explicit operations required')
    q=Project(raw);profile_check(q,profile)
    require(not q.index.unqualified_records and q.index.stop_reason in ('end','resource:SubMacro','resource:Alarm'),'INDEX_UNQUALIFIED','Unknown counted/indexed records cannot be edited')
    require(field(q,q.app,'ModelName')=='268502788' and q.index.number(q.app,'PanelResWidth')==800 and q.index.number(q.app,'PanelResHeight')==480 and all(field(q,q.app,k)=='6.6.2.48' for k in ('Version','NewVersion')),'TARGET','Observed DOP-107EV800x480 native6.6.2.48 only')
    contract=spec.get('contract')
    if contract is not None:
        require(spec.get('contract_sha256')==sha(canonical(contract)),'CONTRACT_HASH','Exact typed contract required');contract_rows(contract)
    policy=spec.get('policy',{});require(isinstance(policy,dict) and set(policy)<={'forbidden_writes','endpoint'},'POLICY','Unknown policy rejected')
    frames=validate_reviewed_resources(q,profile.get('reviewed_resources'));background=next((f for f in frames if f.section=='Background'),None)
    # All edits resolve against the original exact source. Each owner is written once.
    replacements={};removed=set();extras={};headers={};clones=[];claimed=set();proof=[];resource_patches=[];background_appends=[];bg_owned=[]
    original_ids={p.page_id:{q.index.number(e.section,'nPartsID') for e in p.elements} for p in q.pages};source_page_ids=set(original_ids);new_page_ids=set(original_ids)
    for op in operations:
        require(isinstance(op,dict) and isinstance(op.get('op'),str),'OPERATION','Named operation object required')
        if op['op']=='clone_page':
            pid=ident(op.get('new_page_id'));require(pid not in new_page_ids,'PAGE_ID','New page identity collides');new_page_ids.add(pid)
    require(len(new_page_ids)<=96,'PAGE_LIMIT','At most96 source-qualified pages per native project')
    def claim(p,i):
        require((p,i) not in claimed,'DUPLICATE_OWNER','Combine changes to the same source owner in one operation');claimed.add((p,i))
    def make(e,op,values=None):
        values=dict(values or {});s=e.section
        if 'visibility' in op:
            from .typed_visibility import values as visibility_values
            visible,_=visibility_values(q,e,op['visibility'],contract,profile);values.update(visible)
        for k in op.get('fields',{}):require(k in GEOMETRY,'FIELD_SCOPE','Only geometry in fields; binding/type/auth/enum require their qualified operation')
        values.update(op.get('fields',{}));rect_check({k:values.get(k,q.index.number(s,k)) for k in GEOMETRY})
        patches=[token_patch(q,s,k,v,'native owned field') for k,v in values.items()]
        byvalue={q.index.number(st,'Value'):st for st in e.states}
        states=op.get('states',[])
        require(isinstance(states,list) and len(states)<=len(e.states),'STATES','Explicit existing state values required')
        seen=set()
        for stspec in states:
            require(isinstance(stspec,dict) and set(stspec)<={'value','texts','sizes','alignment','bold','colors'},'STATE_SCOPE','Unknown state field rejected')
            value=stspec.get('value');require(type(value) is int and value in byvalue and value not in seen,'STATE_VALUE','Unique original State.Value required');seen.add(value);st=byvalue[value]
            if 'texts' in stspec:
                for n,t in enumerate(texts(stspec['texts'])):patches.append(token_patch(q,st,'wTextLen'+str(n),t,'native counted language text'))
            if 'sizes' in stspec:
                sizes=stspec['sizes'];require(isinstance(sizes,list) and len(sizes)==3 and all(type(z) is int and 8<=z<=56 for z in sizes),'FONT','Three bounded font sizes required')
                for n,v in enumerate(sizes):patches.append(token_patch(q,st,'FontSize'+str(n),v,'native language font size'))
            for public,key in [('alignment','FontAlign'),('bold','FontBold')]:
                if public in stspec:
                    v=stspec[public];require(type(v) is int and v in STYLE[key],'STYLE','Observed native font enum only');patches.append(token_patch(q,st,key,v,'native text style'))
            colors=stspec.get('colors',{});require(isinstance(colors,dict) and set(colors)<={'font','background','foreground'},'COLOR','Unknown color owner')
            for public,key in [('font','FontColor'),('background','BgColor'),('foreground','FgColor')]:
                if public in colors:patches.append(token_patch(q,st,key,rgb_colorref(colors[public]),'native COLORREF BGR'))
        return block(q,s.start,e.end,patches)
    for op in operations:
        kind=op['op']
        common={'op','page_id','element_id','expected_element_sha256','fields','states'}
        allowed={
          'edit_element':common|{'visibility'},
          'numeric_display':common|{'display','visibility'},
          'bind_element':common|{'binding','visibility'},
          'move_element':common|{'new_page_id','new_element_id','retain_macros','visibility'},
          'clone_element':common|{'new_page_id','new_element_id','retain_bindings','retain_macros','binding','visibility'},
          'replace_element':common|{'donor_page_id','donor_element_id','donor_sha256','retain_bindings','retain_macros','visibility'},
          'delete_element':{'op','page_id','element_id','expected_element_sha256'},
          'state_lookup':common|{'donor','binding','view'},
          'edit_page':{'op','page_id','expected_page_sha256','titles','descriptions','name','background_page_id'},
          'clone_page':{'op','page_id','expected_page_sha256','new_page_id','name','titles','retain_macros','png_base64'},
          'navigation':common|{'target_page_id','target_name'},
          'background_png':{'op','page_id','expected_dib_sha256','png_base64','shared_page_ids'},
        }.get(kind)
        require(allowed is not None and set(op)<=allowed,'OPERATION_SCOPE','Unsupported operation or unknown argument')
        if kind in ('edit_page','clone_page'):
            pid=ident(op.get('page_id'));p=q.page(pid);require(op.get('expected_page_sha256')==sha(q.file.payload[p.section.start:p.end]),'PAGE_DRIFT','Exact source page hash required')
            target=ident(op.get('new_page_id')) if kind=='clone_page' else pid
            key=('page',target);require(key not in claimed,'DUPLICATE_OWNER','Page header owner repeated');claimed.add(key)
            values={}
            if kind=='clone_page':
                require('name' in op and op['name'] not in {q.index.text(pg.section,'wTextLen','').rstrip('\0') for pg in q.pages},'PAGE_NAME','Explicit unique new page name required')
                require(type(op.get('retain_macros')) is bool,'MACRO_SCOPE','Explicit page macro retention required')
                if not op['retain_macros']:
                    require(all(not t.blob(q.file.payload) for sec in [p.section,*p.aux,*[x for e in p.elements for x in [e.section,*e.states]]] for t in sec.tokens if t.kind=='macro'),'MACRO_SCOPE','Nonempty source macros cannot be silently cloned/cleared')
                values['ID']=target
            if 'name' in op:
                require(isinstance(op['name'],str) and 1<=len(op['name'])<=120 and '\0' not in op['name'],'PAGE_NAME','Bounded counted page name');values['wTextLen']=op['name']
            for public,stem in [('titles','wTitleTextLen'),('descriptions','wScreenDESCTextLen')]:
                if public in op:
                    for n,t in enumerate(texts(op[public])):values[stem+f'{n:03d}']=t
            if 'background_page_id' in op:values['PictureOffset']=q.index.number(q.page(ident(op['background_page_id'])).section,'PictureOffset')
            if 'png_base64' in op:
                require(background is not None,'BACKGROUND','Reviewed background bank required');dib=png_dib(op['png_base64'])
                values['PictureOffset']=background.blob_end-background.blob_start+sum(len(b) for b in background_appends);background_appends.append(dib)
            head_end=p.elements[0].section.start if p.elements else p.end
            head=block(q,p.section.start,head_end,[token_patch(q,p.section,k,v,'native page header owner') for k,v in values.items()])
            if kind=='clone_page':clones.append((target,head+q.file.payload[head_end:p.end]))
            else:headers[pid]=head
            proof.append(dict(op=kind,page_id=pid,target_page_id=target,fields=values));continue
        if kind=='background_png':
            require(background is not None,'BACKGROUND','Reviewed background bank required');pid=ident(op.get('page_id'));offset=q.index.number(q.page(pid).section,'PictureOffset')
            owners=sorted(p.page_id for p in q.pages if q.index.number(p.section,'PictureOffset')==offset)
            require(op.get('shared_page_ids')==owners,'BACKGROUND_SHARED','Explicit complete list of pages sharing this DIB required')
            require(offset not in bg_owned,'DUPLICATE_OWNER','DIB owner repeated');bg_owned.append(offset)
            start=background.blob_start+offset;end=start+1152040
            from universal_diascreen_hmi.preview import decode_dib
            old=q.file.payload[start:end];decoded=decode_dib(old,0)
            require(decoded['width']==800 and decoded['height']==480 and len(old)==1152040 and sha(old)==op.get('expected_dib_sha256') and end<=background.blob_end,'DIB_OWNER','Exact source800x480 24bit DIB owner required')
            new=png_dib(op['png_base64']);resource_patches.append(Patch(start,end,old,new,'native same-size source-qualified DIB'));proof.append(dict(op=kind,page_ids=owners,source_dib_sha256=sha(old),candidate_dib_sha256=sha(new)));continue
        p,i,e=checked_selector(q,op);claim(p,i);values={};donor=e
        if kind=='state_lookup':
            from .state_lookup import build as lookup_build
            require(contract is not None and lookup_sources is not None and op['donor']['source_sha256'] in lookup_sources,'LOOKUP_DONOR','An immutable read donor context and typed contract are required')
            new,lookup_proof=lookup_build(q,e,op,lookup_sources[op['donor']['source_sha256']],contract,profile)
            replacements[(p,i)]=new;proof.append(dict(op=kind,page_id=p,element_id=i,target_page_id=p,target_element_id=i,new_block_sha256=sha(new),lookup=lookup_proof));continue
        login=family(q,e)==(12,3) and kind in ('edit_element','clone_element','move_element','replace_element')
        require(family(q,e) in SUPPORTED or login,'ELEMENT_FAMILY','Unqualified source family cannot be written')
        if kind=='delete_element':
            require(family(q,e) in ((2,1),(10,6)) and field(q,e.section,'WriteVar') in ('','None') and macro_free(q,e),
                'DELETE_SCOPE','Only source-owned macro-free read-only indicators/static labels may be removed')
            require(q.index.number(e.section,'EventID',0)==0 and q.index.number(e.section,'RelatedFileBrowserPartID',-1)==-1,
                'DELETE_DEPENDENCY','Event/file-browser dependent owners cannot be removed')
            known={'nPartsID','rPartID','RelatedFileBrowserPartID','EventID'}
            require(not any(t.key and t.key not in known and t.key.endswith(('PartID','EventID')) for t in e.section.tokens),
                'DELETE_DEPENDENCY','Unknown source dependency variants remain read-only')
            incoming=False
            for z in q.page(p).elements:
                if z is e:continue
                for t in z.section.tokens:
                    if t.key and t.key!='nPartsID' and t.key.endswith('PartID'):
                        require(t.kind=='scalar' and re.fullmatch(rb'-?[0-9]{1,12}',t.value) is not None,
                            'DELETE_DEPENDENCY','Unknown/non-numeric incoming dependency remains read-only')
                        incoming = incoming or int(t.value)==i
            require(q.index.number(e.section,'rPartID',-1)==-1 and not incoming,
                'DELETE_DEPENDENCY','Grouped/referenced source owners cannot be removed')
            removed.add((p,i));proof.append(dict(op=kind,page_id=p,element_id=i,source_sha256=element_hash(q,e),deleted=True));continue
        if login and kind in ('clone_element','replace_element'):
            require(op.get('retain_bindings') is True and (op.get('retain_macros') is True or macro_free(q,e)),'LOGIN_RETENTION','System-login source actions/security must be retained exactly')
        if login and kind=='move_element':require(op.get('retain_macros') is True or macro_free(q,e),'LOGIN_RETENTION','System-login actions must be retained exactly')
        if kind in ('clone_element','replace_element'):
            require(type(op.get('retain_bindings')) is bool and type(op.get('retain_macros')) is bool,'RETAIN_FLAGS','Explicit binding/macro retention required')
            if kind=='replace_element':
                donor=q.element(ident(op.get('donor_page_id')),ident(op.get('donor_element_id')))
                require(op.get('donor_sha256')==element_hash(q,donor),'DONOR_DRIFT','Exact source donor hash required')
                donor_login=family(q,donor)==(12,3)
                require(family(q,donor) in SUPPORTED or donor_login,'ELEMENT_FAMILY','Unqualified donor family')
                if donor_login:require(op.get('retain_bindings') is True and (op.get('retain_macros') is True or macro_free(q,donor)),'LOGIN_RETENTION','System-login donor actions/security must be retained exactly')
                values['nPartsID']=i
            if not op['retain_bindings'] and 'binding' not in op:
                require(not any(address(field(q,donor.section,k)) for k in ('ReadVar','WriteVar','VisibleVar','InterLockVar','TriggerVar')),'DONOR_BINDING','Use a native unbound/static donor; no synthetic field stripping')
            if not op['retain_macros']:require(macro_free(q,donor),'MACRO_SCOPE','Nonempty macros need explicit retention')
        if kind in ('clone_element','move_element'):
            target=ident(op.get('new_page_id'));newid=ident(op.get('new_element_id'));require(target in source_page_ids,'PAGE_ID','Target must be an existing source page; new-page edits use a subsequent inspected plan')
            require(newid not in original_ids[target] or (kind=='move_element' and (target,newid)==(p,i)),'ELEMENT_ID','Target element identity collides')
            require((target,newid) not in claimed or (target,newid)==(p,i),'DUPLICATE_OWNER','New object identity claimed');claimed.add((target,newid));original_ids[target].add(newid)
            if kind=='move_element':
                require(type(op.get('retain_macros')) is bool and (op['retain_macros'] or macro_free(q,e)),'MACRO_SCOPE','Explicit macro retention required')
                require(q.index.number(e.section,'RelatedFileBrowserPartID',-1)==-1 and q.index.number(e.section,'EventID',0)==0,'ELEMENT_DEPENDENCY','Linked object/event cannot be moved by this source family')
                removed.add((p,i))
            values['nPartsID']=newid
        if kind=='navigation':
            target=ident(op.get('target_page_id'));require(target in new_page_ids,'NAVIGATION','Missing target page')
            require(e.section.one('GoToScreenID',optional=True) is not None,'NAVIGATION','Source is not a native navigation control')
            name=op.get('target_name');require(isinstance(name,str) and re.fullmatch('[A-Za-z0-9_ .-]{1,120}',name),'NAVIGATION','Explicit ASCII native target name required')
            known={field(q,z.section,'GoToScreenName') for pg in q.pages for z in pg.elements if q.index.number(z.section,'GoToScreenID',0)==target}
            if target in source_page_ids:known.add(q.index.text(q.page(target).section,'wTextLen','').rstrip('\0'))
            known.update(x['name'] for x in operations if x['op']=='clone_page' and x['new_page_id']==target and 'name' in x)
            require(name in known,'NAVIGATION_NAME','Target name must match its source-known native alias or explicit new page name')
            values.update(GoToScreenID=target,GoToScreenName=name)
        if kind=='numeric_display':
            require(family(q,e) in ((5,1),(6,1)) and native_type(q,e) in ('INT','DINT','REAL'),'NUMERIC_TYPE','Observed INT/DINT/REAL numeric family required')
            require(q.index.number(e.section,'ReadMemType',0)==0 and q.index.number(e.section,'WriteMemType',0)==0 and q.index.number(e.section,'OffsetLength',0)==0,'MEMORY_VARIANT','Offset/indirect numeric variants remain read-only')
            d=op.get('display');require(isinstance(d,dict) and set(d)<={'gain','offset','decimals','integer_digits','minimum','maximum','native_units'},'NUMERIC_SPEC','Explicit display fields only')
            dots=d.get('decimals',q.index.number(e.section,'DotNum',0));digits=d.get('integer_digits',q.index.number(e.section,'IntNum',1));require(type(dots) is int and 0<=dots<=6 and type(digits) is int and 1<=digits<=10,'NUMERIC_DIGITS','Bounded native digits')
            real=native_type(q,e)=='REAL';factor=Decimal(1) if real else Decimal(10)**dots
            values.update(DotNum=dots,IntNum=digits)
            if 'gain' in d:
                v=dec(d['gain']);require(v!=0 and abs(v)<=1000000,'NUMERIC_SCALE','Nonzero bounded effective gain');values['GainValue']=format(v*factor,'f')
            if 'offset' in d:values['OffsetValue']=format(dec(d['offset'])*factor,'f')
            if not real and dots!=q.index.number(e.section,'DotNum',0):
                oldfactor=Decimal(10)**q.index.number(e.section,'DotNum',0)
                if 'gain' not in d:values['GainValue']=format(dec(field(q,e.section,'GainValue','1'))/oldfactor*factor,'f')
                if 'offset' not in d:values['OffsetValue']=format(dec(field(q,e.section,'OffsetValue','0'))/oldfactor*factor,'f')
            if 'minimum' in d:values['MinValue']=format(dec(d['minimum']),'f')
            if 'maximum' in d:values['MaxValue']=format(dec(d['maximum']),'f')
            if 'native_units' in d:
                for n,t in enumerate(texts(d['native_units'])):values['UnitTextLen'+str(n)]=t
            minimum=dec(values.get('MinValue',field(q,e.section,'MinValue','-1000000000000')));maximum=dec(values.get('MaxValue',field(q,e.section,'MaxValue','1000000000000')));require(minimum<=maximum,'NUMERIC_RANGE','Numeric min exceeds max')
        if kind=='bind_element' or 'binding' in op:
            bind_e=donor
            require(contract is not None,'CONTRACT','Typed binding edits need a hash-bound contract')
            b=op.get('binding');require(isinstance(b,dict) and set(b)<={'address','type','access','link','station','level','HiWordFirst','HiDwordFirst','constant'},'BINDING_SPEC','Exact binding fields only')
            require(all(k in b for k in ('address','type','access','link','station')),'BINDING_SPEC','Complete explicit binding identity required')
            tags=contract_rows(contract);tag=tags.get(b['address']);require(tag and tag['type']==b['type'] and tag['access']==b['access'],'TAG_MISSING','Exact typed contract entry required')
            typ=native_type(q,bind_e);require(typ==b['type'],'TYPE_PRESERVE','Use a donor with the exact intended IEC native type; type enums are not invented')
            require(q.index.number(bind_e.section,'ReadMemType',0)==0 and q.index.number(bind_e.section,'WriteMemType',0)==0 and q.index.number(bind_e.section,'OffsetLength',0)==0,'MEMORY_VARIANT','Offset/indirect binding variants remain read-only')
            for key,link in [('ReadVar','ReadLink'),('WriteVar','WriteLink')]:
                if address(field(q,bind_e.section,key)):require(q.index.number(bind_e.section,link)==2,'BINDING_LINK','Only source-observed direct native link2 is qualified')
            require(macro_free(q,bind_e),'MACRO_BINDING','Retargeting macro-bearing objects needs a separately qualified macro contract')
            require(isinstance(b['link'],str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,30}',b['link']) and type(b['station']) is int and 0<=b['station']<=255,'BINDING_SPEC','Explicit native link/station')
            require(b['link']==profile['link'] and b['station']==profile['station'],'BINDING_LINK','Binding differs from reviewed project link/station')
            value='{'+b['link']+'}'+str(b['station'])+'@'+b['address']
            if bind_e.section.one('ReadVar',optional=True) and field(q,bind_e.section,'ReadVar') not in ('','None'):values['ReadVar']=value
            if bind_e.section.one('WriteVar',optional=True) and field(q,bind_e.section,'WriteVar') not in ('','None'):
                require(b['access']!='READ_ONLY','READ_ONLY','Native writer cannot bind a read-only tag');values['WriteVar']=value
            if 'level' in b:
                require(type(b['level']) is int and b['level'] in {q.index.number(z.section,'Level',0) for pg in q.pages for z in pg.elements},'LEVEL','Source-observed field security level required')
                require(tag.get('level')==b['level'],'TAG_LEVEL','Explicit contract field level required');values['Level']=b['level']
            for k in ('HiWordFirst','HiDwordFirst'):
                if k in b:require(b[k]==q.index.number(bind_e.section,k,0) and tag.get(k)==b[k],'WORD_ORDER','Only unchanged observed word order and matching contract is qualified')
            if 'constant' in b:
                require(family(q,bind_e)==(1,7) and type(b['constant']) is int and -32768<=b['constant']<=32767,'ENUM','Observed INT constant button required');values['SetValue']=b['constant']
        new=make(donor,op,values)
        if kind in ('clone_element','move_element'):extras.setdefault(target,[]).append(new)
        else:replacements[(p,i)]=new
        proof.append(dict(op=kind,page_id=p,element_id=i,target_page_id=target if kind in ('clone_element','move_element') else p,target_element_id=newid if kind in ('clone_element','move_element') else i,source_sha256=element_hash(q,e),donor_sha256=element_hash(q,donor),new_block_sha256=sha(new)))
    patches=[]
    for p in q.pages:
        head_end=p.elements[0].section.start if p.elements else p.end
        chunks=[headers.get(p.page_id,q.file.payload[p.section.start:head_end])]
        for e in p.elements:
            i=q.index.number(e.section,'nPartsID')
            if (p.page_id,i) not in removed:chunks.append(replacements.get((p.page_id,i),q.file.payload[e.section.start:e.end]))
        chunks.extend(extras.get(p.page_id,[]));new=b''.join(chunks);old=q.file.payload[p.section.start:p.end]
        if new!=old:patches.append(Patch(p.section.start,p.end,old,new,'atomic native page owner'))
    if clones:patches.append(Patch(q.index.tail_start,q.index.tail_start,b'',b''.join(b for _,b in clones),'source-derived native page frames'))
    patches+=resource_patches
    if background_appends:
        data=b''.join(background_appends);old=q.file.payload[background.length_start:background.blob_start]
        new=b'Size='+str(background.blob_end-background.blob_start+len(data)).encode()+b'\r\n'
        patches+=[Patch(background.length_start,background.blob_start,old,new,'counted background bank size'),Patch(background.blob_end,background.blob_end,b'',data,'native RGB24 background append')]
    require(patches,'NO_CHANGE','Native transaction is a no-op')
    require(len(q.file.payload)+sum(len(p.new)-len(p.old) for p in patches)<=128*1024*1024,'PAYLOAD_LIMIT','Native payload exceeds128MiB')
    payload,ledger=apply_spans(q.file.payload,patches);require(restore_spans(payload,ledger)==q.file.payload,'INVERSE','Exact source payload inverse required')
    raw_after=q.file.encode(payload);final=Project(raw_after);validate_references(final)
    for item in proof:
        if item.get('deleted'):require(all(final.index.number(z.section,'nPartsID')!=item['element_id'] for z in final.page(item['page_id']).elements),'TARGET_READBACK','Deleted source owner still exists')
        if 'new_block_sha256' in item:
            fe=final.element(item['target_page_id'],item['target_element_id']);require(element_hash(final,fe)==item['new_block_sha256'],'TARGET_READBACK','Every claimed replacement/clone/move must exist with its exact target bytes')
    if 'endpoint' in policy:
        from .hmi4_inspect import endpoint
        ep=policy['endpoint'];require(isinstance(ep,dict) and set(ep)=={'ip','port'} and all(endpoint(final)[k]==v for k,v in ep.items()),'ENDPOINT','Explicit production endpoint policy differs')
    require(q.file.payload[:q.pages[0].section.start]==payload[:final.pages[0].section.start] and q.file.prefix[:37]==final.file.prefix[:37] and q.file.thumbnail==final.file.thumbnail,'APPLICATION_PRESERVE','Application/auth/global macros/prefix/thumbnail must be unchanged')
    unowned=0
    for p in q.pages:
        for e in p.elements:
            eid=q.index.number(e.section,'nPartsID')
            if (p.page_id,eid) in claimed:continue
            fe=final.element(p.page_id,eid);require(element_hash(q,e)==element_hash(final,fe),'UNOWNED','Unowned native element changed');unowned+=1
    for op in operations:
        if 'visibility' in op:
            from .typed_visibility import readback as visibility_readback
            vp,vi=(op['new_page_id'],op['new_element_id']) if op['op'] in ('clone_element','move_element') else (op['page_id'],op['element_id'])
            detail=visibility_readback(final,final.element(vp,vi),contract)
            require(all(detail[k]==op['visibility'][k] for k in ('address','link','station','visible_when')),'VISIBILITY_READBACK','Exact typed visibility must survive native encode/reopen')
            from .typed_visibility import values as visibility_values
            source_owner=q.element(op['donor_page_id'],op['donor_element_id']) if op['op']=='replace_element' else q.element(op['page_id'],op['element_id'])
            _,witnesses=visibility_values(q,source_owner,op['visibility'],contract,profile)
            item=next(x for x in proof if x.get('op')==op['op'] and x.get('page_id')==op['page_id'] and x.get('element_id')==op['element_id'])
            item['visibility']=dict(**detail,source_witnesses=witnesses)
        if op['op']=='state_lookup':
            from .state_lookup import readback
            marker=next(x['lookup']for x in proof if x.get('op')=='state_lookup' and x['page_id']==op['page_id'] and x['element_id']==op['element_id'])
            readback(final,final.element(op['page_id'],op['element_id']),marker,contract_rows(contract)[op['binding']['address']]);continue
        if op['op']=='bind_element' or 'binding' in op:
            p,i=(op['new_page_id'],op['new_element_id']) if op['op']=='clone_element' else (op['page_id'],op['element_id'])
            check_binding(final,final.element(p,i),contract)
    for p in final.pages:
        for e in p.elements:
            write=address(field(final,e.section,'WriteVar'))
            if write:require(write['address'] not in policy.get('forbidden_writes',[]),'RESERVED_WRITE','Forbidden write still present')
    fp=deepcopy(profile);fp['indexed_layout_sha256']=layout_digest(final);fp['reviewed_resources']=map_resources(q,profile,payload,patches)
    # Historical closed reconstruction metadata becomes lineage, never a new acceptance claim.
    for key in ('machine_candidate','r06_candidate','r07_candidate','home_native_pilot','r08_clean17','r09_clean17'):
        if key in fp:fp.setdefault('source_lineage',{})[key]=fp.pop(key)
    fp['state_lookups']=[m for m in profile.get('state_lookups',[]) if (m['page_id'],m['element_id']) not in claimed]+[x['lookup']for x in proof if 'lookup'in x]
    fp['hmi4_native_update']=dict(engine_sha256=identity(),specification_sha256=sha(canonical(spec)),source_sha256=sha(raw),native_qualified=False,vendor_compile='NOT_RUN')
    if resource_patches or background_appends:
        from universal_diascreen_hmi.preview import decode_dib
        frame=next(f for f in validate_reviewed_resources(final,fp['reviewed_resources']) if f.section=='Background');blob=payload[frame.blob_start:frame.blob_end]
        fp['background_sha256']={str(p.page_id):decode_dib(blob,final.index.number(p.section,'PictureOffset'))['frame_sha256'] for p in final.pages}
    profile_check(final,fp)
    return dict(candidate=raw_after,profile=fp,ledger=ledger,proof=dict(operations=proof,pages=len(final.pages),objects=sum(len(p.elements) for p in final.pages),unowned_objects_exact=unowned,application_auth_globalmacros_exact=True,resource_bytes_exact=not(resource_patches or background_appends),resource_DIB_changes=len(resource_patches),resource_DIB_appends=len(background_appends),exact_inverse=True,native_qualified=False,vendor_compile='NOT_RUN'))
