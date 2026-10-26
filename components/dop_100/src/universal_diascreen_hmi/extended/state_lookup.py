# SPDX-License-Identifier: Apache-2.0
"""Source-template WORD16 lookup; never a general signed/unsigned type coercion."""
from .hmi4_bootstrap import *
from .hmi4_inspect import field,family,element_hash,contract_rows,address
from universal_diascreen_hmi.operations import token_patch

HEADER=set('Type SubType CombineType X Y Width Height Style BorderColor ReadMemType ReadLink ReadVar MemLen MemFmt Level antialiasing bFreeze AutoResizeByText AutoResizeMargin nPartsID RelatedFileBrowserPartID wDescTextLen0 wDescTextLen1 wDescTextLen2 ChangeTime VisibleLink VisibleVar VisibleCondition'.split())
STATE=set('Value FgColor BgColor FillStyle BorderStyle FontColor FontAlign FontBold FontItalic FontUnderline FgFillType FgFillColor FgFillEndColor FgFillStyle FgFillAngleArg FgFillXArg FgFillYArg UsePictureCoord PictureAlign TransEffect TransColor StretchMode PictureStretch Twinkles'.split())|{s+str(n)for s in ('FontSize','FontRatio','FontName','wTextLen')for n in range(3)}|{s+str(n)for s in ('FgFillStopPos','FgFillStopColor')for n in range(5)}

def closed(sec,keys,wide):
    require(len(sec.tokens)==len(keys) and {t.key for t in sec.tokens}==keys,'LOOKUP_SCHEMA','Only the complete observed plain-text lookup schema is supported')
    require(all(t.kind==('wide' if t.key in wide else 'scalar')for t in sec.tokens),'LOOKUP_SCHEMA','Unknown counted/macro/resource variants are not lookup templates')

def domain(tag):
    require(tag.get('type')=='INT' and tag.get('words')==1 and tag.get('access')=='READ_ONLY','LOOKUP_TYPE','Only explicit read-only INT positive enum domains are supported')
    values=tag.get('enum');require(isinstance(values,(list,dict)) and 1<=len(values)<=128,'LOOKUP_ENUM','Complete declared enum set required')
    raw=list(values);require(all(type(v)is int or isinstance(v,str) and __import__('re').fullmatch(r'[0-9]{1,5}',v)for v in raw),'LOOKUP_ENUM','Bounded nonnegative integer enum values required')
    nums=[int(v)for v in raw];require(all(0<=v<=32767 for v in nums) and len(set(nums))==len(nums),'LOOKUP_ENUM','Unique nonnegative INT enum domain required');return set(nums)

def text_map(q,e):
    return [dict(value=q.index.number(st,'Value'),texts=[q.index.text(st,'wTextLen'+str(n),'').rstrip('\0')for n in range(3)])for st in e.states]

def coverage(tag,view,states):
    from .hmi4_transaction import texts
    produced=domain(tag);maximum=max(produced)
    require(maximum<=127,'LOOKUP_VIEW_RANGE','This plain text lookup supports indices0..127 only')
    indices=list(range(maximum+1));holes=sorted(set(indices)-produced)
    if view is None:
        require(not holes,'LOOKUP_DENSE_INDEXED','Sparse State.Value is withdrawn: use an explicit dense indexed view without changing the PLC enum')
    else:
        require(isinstance(view,dict) and set(view)=={'mode','maximum','unknown_texts'} and view['mode']=='DENSE_INDEXED' and type(view['maximum'])is int and view['maximum']==maximum,'LOOKUP_VIEW','Explicit dense view must end at the actual produced maximum')
        templates=texts(view['unknown_texts']);require(all(t.count('{value}')==1 and '{'not in t.replace('{value}','') and '}'not in t.replace('{value}','') for t in templates),'LOOKUP_UNKNOWN_TEXT','Each unknown text template must include exactly one numeric {value} placeholder')
    require(isinstance(states,list) and 1<=len(states)<=128 and all(isinstance(row,dict) and type(row.get('value'))is int for row in states),'LOOKUP_STATES','Explicit ordered index rows required')
    require([row['value']for row in states]==indices,'LOOKUP_DENSE_INDEXED','State rows must be ordered dense indices0..maximum; sparse, duplicate, reordered and missing rows are refused')
    mapping=[]
    for row in states:
        words=texts(row.get('texts'))
        if row['value']in holes:
            require(words==texts([t.replace('{value}',str(row['value']))for t in templates]),'LOOKUP_UNKNOWN_TEXT','Non-produced display indices need the exact declared numeric unknown text')
        mapping.append(dict(value=row['value'],texts=words))
    return dict(encoding='DENSE_STATE_INDEX',produced_values=sorted(produced),view_values=indices,unknown_values=holes,view=view,text_map_sha256=sha(canonical(mapping)))

def verify_donor(q,e,target):
    from .source_intake import complete_prefix
    complete_prefix(q)
    require(q.metadata()==target.metadata(),'LOOKUP_TARGET','Donor model/native version/resolution must match source')
    require(family(q,e)==(7,1),'LOOKUP_FAMILY','Source-observed Type7/SubType1 plain text lookup required')
    closed(e.section,HEADER,{'wDescTextLen'+str(n)for n in range(3)})
    require(all(q.index.number(e.section,k)==v for k,v in [('CombineType',0),('ReadMemType',0),('MemLen',1),('MemFmt',2),('Level',0),('RelatedFileBrowserPartID',-1)]),'LOOKUP_DEPENDENCY','Indirect/group/security/resource variants remain unsupported')
    require(field(q,e.section,'VisibleVar')=='None','LOOKUP_DEPENDENCY','A lookup donor with visibility dependencies cannot be imported')
    require(1<=len(e.states)<=128,'LOOKUP_SCHEMA','Bounded source state frames required')
    fonts={field(target,st,'FontName'+str(n))for pg in target.pages for el in pg.elements for st in el.states for n in range(3)}
    for st in e.states:
        closed(st,STATE,{'wTextLen'+str(n)for n in range(3)})
        require(all(field(q,st,k)=='None'for k in ('FgFillAngleArg','FgFillXArg','FgFillYArg')) and all(q.index.number(st,k)==0 for k in ('UsePictureCoord','PictureStretch')),'LOOKUP_DEPENDENCY','Picture/indirect fill templates remain unsupported')
        require(all(field(q,st,'FontName'+str(n)) in fonts for n in range(3)),'LOOKUP_FONT','Donor fonts must already be present in the source; font names are preserved')

def build(q,e,op,donor,contract,profile):
    from .hmi4_transaction import macro_free,texts,rgb_colorref,rect_check,GEOMETRY,STYLE
    dq=donor;d=op['donor'];de=dq.element(d['page_id'],d['element_id']);require(element_hash(dq,de)==d['element_sha256'],'LOOKUP_DONOR_HASH','Donor owner differs');verify_donor(dq,de,q)
    require(family(q,e)in ((10,6),(2,1),(6,1),(7,1)) and macro_free(q,e) and field(q,e.section,'WriteVar')in ('','None'),'LOOKUP_TARGET','Only macro-free readonly source owners may be replaced')
    require(q.index.number(e.section,'Level',0)==0 and q.index.number(e.section,'CombineType',0)==0 and q.index.number(e.section,'rPartID',-1)==-1 and q.index.number(e.section,'RelatedFileBrowserPartID',-1)==-1 and q.index.number(e.section,'EventID',0)==0 and field(q,e.section,'VisibleVar')in ('','None'),'LOOKUP_TARGET','Target group/event/security/visibility dependencies must be absent')
    require(not any(t.key and t.key.endswith(('PartID','EventID')) and t.key not in ('nPartsID','rPartID','RelatedFileBrowserPartID','EventID')for t in e.section.tokens),'LOOKUP_TARGET','Unknown target dependency')
    b=op.get('binding');require(isinstance(b,dict) and set(b)=={'address','type','access','link','station'} and b['type']=='INT' and b['access']=='READ_ONLY' and b['link']==profile['link'] and type(b['station'])is int and b['station']==profile['station'],'LOOKUP_BINDING','Exact readonly profile link/station and INT binding required')
    tag=contract_rows(contract).get(b['address']);require(tag is not None,'TAG_MISSING','Lookup tag missing')
    states=op.get('states');require(isinstance(states,list) and 1<=len(states)<=128,'LOOKUP_STATES','Explicit bounded state list required')
    covered=coverage(tag,op.get('view'),states);values=set(covered['view_values'])
    seen=set();frames=[];template=next((st for st in de.states if dq.index.number(st,'Value')==d['template_state_value']),None);require(template is not None,'LOOKUP_TEMPLATE','Exact existing State.Value template required')
    for row in states:
        require(isinstance(row,dict) and set(row)=={'value','texts','sizes','alignment','bold','colors'},'LOOKUP_STATE','Complete explicit language/style fields required')
        value=row['value'];require(type(value)is int and value in values and value not in seen,'LOOKUP_ENUM','State values must equal the declared unique enum');seen.add(value)
        sizes=row['sizes'];require(isinstance(sizes,list) and len(sizes)==3 and all(type(n)is int and 8<=n<=56 for n in sizes),'FONT','Three bounded font sizes required')
        colors=row['colors'];require(isinstance(colors,dict) and set(colors)=={'font','background','foreground'},'COLOR','Explicit three colors required')
        require(type(row['alignment'])is int and row['alignment']in STYLE['FontAlign'] and type(row['bold'])is int and row['bold']in STYLE['FontBold'],'STYLE','Observed native style only')
        changes={'Value':value,'FontAlign':row['alignment'],'FontBold':row['bold']}
        for n,text in enumerate(texts(row['texts'])):changes['wTextLen'+str(n)]=text;changes['FontSize'+str(n)]=sizes[n]
        for public,key in [('font','FontColor'),('background','BgColor'),('foreground','FgColor')]:changes[key]=rgb_colorref(colors[public])
        frames.append(apply_spans(dq.file.payload[template.start:template.end],[Patch(p.start-template.start,p.end-template.start,p.old,p.new,p.reason)for p in [token_patch(dq,template,k,v,'source-derived lookup state')for k,v in changes.items()]])[0])
    require(seen==values,'LOOKUP_ENUM','Missing/extra display indices are not accepted')
    fields=op.get('fields',{});require(isinstance(fields,dict) and set(fields)<=GEOMETRY,'FIELD_SCOPE','Only explicit source geometry can be changed');rect={k:fields.get(k,q.index.number(e.section,k))for k in GEOMETRY};rect_check(rect)
    changes={**rect,'nPartsID':q.index.number(e.section,'nPartsID'),'ReadLink':2,'ReadVar':'{'+b['link']+'}'+str(b['station'])+'@'+b['address']}
    # Only source-observed direct link2 is used; never copy donor controller settings.
    require(any(q.index.number(z.section,'ReadLink',0)==2 and address(field(q,z.section,'ReadVar')) for pg in q.pages for z in pg.elements),'LOOKUP_BINDING','Source direct-link2 evidence required')
    head=apply_spans(dq.file.payload[de.section.start:de.states[0].start],[Patch(p.start-de.section.start,p.end-de.section.start,p.old,p.new,p.reason)for p in [token_patch(dq,de.section,k,v,'source-derived lookup owner')for k,v in changes.items()]])[0]
    result=head+b''.join(frames);return result,dict(role='LOOKUP_WORD16_NONNEGATIVE',page_id=op['page_id'],element_id=op['element_id'],address=b['address'],binding=dict(address=b['address'],link=b['link'],station=b['station']),values=covered['view_values'],**covered,owner_sha256=sha(result),donor=d,provenance='GENERATED_PLAN',unmapped_runtime_value='OUTSIDE_VIEW_UNQUALIFIED',native_qualified=False)

def readback(q,e,marker,tag):
    require(marker.get('role')=='LOOKUP_WORD16_NONNEGATIVE' and marker.get('owner_sha256')==element_hash(q,e),'LOOKUP_PROOF','Exact source-derived lookup owner proof required')
    require(family(q,e)==(7,1) and q.index.number(e.section,'MemLen')==1 and q.index.number(e.section,'MemFmt')==2 and field(q,e.section,'WriteVar')in ('','None') and field(q,e.section,'VisibleVar')=='None','LOOKUP_PROOF','Readonly WORD16 lookup changed')
    actual=text_map(q,e);covered=coverage(tag,marker.get('view'),actual)
    require([r['value']for r in actual]==marker['values'],'LOOKUP_ENUM','Readback display indices differ')
    if 'produced_values'in marker:require(marker['produced_values']==covered['produced_values'],'LOOKUP_ENUM','Actual PLC produced domain differs')
    if 'text_map_sha256'in marker:require(marker['text_map_sha256']==covered['text_map_sha256'],'LOOKUP_TEXT_MAP','Exact ordered three-language text map differs')
    b=address(field(q,e.section,'ReadVar'));require(b and b['address']==marker['address']==tag['address'] and q.index.number(e.section,'ReadLink')==2,'LOOKUP_BINDING','Readback binding differs')
    if 'binding'in marker:require(b==marker['binding'],'LOOKUP_BINDING','Exact native link/station/address differs')
    return dict(role=marker['role'],owner_sha256=element_hash(q,e),binding=b,values=covered['view_values'],**covered,native_format=dict(MemLen=1,MemFmt=2),signed_native_type=False,unmapped_runtime_value='OUTSIDE_VIEW_UNQUALIFIED',provenance=marker.get('provenance','LEGACY_DENSE_OWNER_HASH'),status='PASS_FILE_ONLY',vendor_runtime_accepted=False)

def source_expectation(q,e,expected,tag,profile):
    require(isinstance(expected,dict) and set(expected)<= {'page_id','element_id','expected_element_sha256','states','view'} and {'page_id','element_id','expected_element_sha256','states'}<=set(expected),'LOOKUP_EXPECTATION','Exact source selector/hash and full expected text map required')
    require(expected['expected_element_sha256']==element_hash(q,e),'LOOKUP_OWNER_HASH','Source lookup owner differs from caller inspection')
    verify_donor(q,e,q)
    binding=address(field(q,e.section,'ReadVar'));require(binding and binding['address']==tag['address'] and binding['link']==profile['link'] and binding['station']==profile['station'] and q.index.number(e.section,'ReadLink')==2,'LOOKUP_BINDING','Source lookup must read the exact reviewed profile/tag')
    require(isinstance(expected['states'],list) and all(isinstance(row,dict) and set(row)=={'value','texts'}for row in expected['states']),'LOOKUP_EXPECTATION','Only explicit index/text rows are source expectations')
    covered=coverage(tag,expected.get('view'),expected['states']);actual=text_map(q,e)
    require(actual==expected['states'],'LOOKUP_TEXT_MAP','Actual ordered native indices/texts differ from the full expected map')
    marker=dict(role='LOOKUP_WORD16_NONNEGATIVE',page_id=expected['page_id'],element_id=expected['element_id'],address=tag['address'],binding=binding,values=covered['view_values'],**covered,owner_sha256=element_hash(q,e),provenance='SOURCE_EXPECTATION_MATCH',unmapped_runtime_value='OUTSIDE_VIEW_UNQUALIFIED',native_qualified=False)
    readback(q,e,marker,tag);return marker
