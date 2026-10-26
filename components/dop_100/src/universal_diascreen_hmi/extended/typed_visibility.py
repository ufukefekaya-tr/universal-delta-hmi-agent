# SPDX-License-Identifier: Apache-2.0
"""Readonly BOOL visibility over existing numeric/static native fields only."""
import re
from .hmi4_bootstrap import *
from .hmi4_inspect import address,field,family,element_hash,contract_rows,native_type

FAMILIES={(5,1),(10,6)}

def shape(q,e):
    s=e.section
    require(family(q,e) in FAMILIES,'VISIBILITY_FAMILY','Only source readonly numeric5/1 and static10/6 visibility is qualified')
    require(field(q,s,'WriteVar') in ('','None') and all(not t.blob(q.file.payload) for sec in [s,*e.states] for t in sec.tokens if t.kind=='macro'),'VISIBILITY_OWNER','Visibility edits require readonly macro-free owners')
    if family(q,e)==(5,1):
        binding=address(field(q,s,'ReadVar'))
        require(native_type(q,e) in ('INT','DINT','REAL') and binding and binding['address'].startswith('D') and q.index.number(s,'ReadLink',-1)==2,'VISIBILITY_OWNER','Numeric visibility requires an existing direct typed numeric reader')
    else:require(field(q,s,'ReadVar') in ('','None'),'VISIBILITY_OWNER','Only an unbound source static label is qualified')
    require(all(s.one(k,optional=True) is not None for k in ('VisibleVar','VisibleLink','VisibleCondition')),'VISIBILITY_FIELDS','Existing visibility fields are required; no fields are synthesized')
    require(all(q.index.number(s,k,0)==0 for k in ('ReadMemType','WriteMemType','OffsetLength')) and all(not(t.key and t.key.startswith('Visible') and t.key not in ('VisibleVar','VisibleLink','VisibleCondition')) for t in s.tokens),'VISIBILITY_VARIANT','Indirect or unknown visibility variants remain unqualified')
    condition=q.index.number(s,'VisibleCondition',-1)
    require(condition in (0,1),'VISIBILITY_CONDITION','Only existing source conditions0/1 are qualified')
    original=field(q,s,'VisibleVar');link=q.index.number(s,'VisibleLink',-1)
    local=link==1 and re.fullmatch(r'\$[0-9]+\.0',original or '')
    direct=address(original)
    require(local or (link==2 and direct and re.fullmatch('M[0-9]+',direct['address'])),'VISIBILITY_SOURCE','Source must already use a direct/local BOOL visibility operand')
    return condition

def readback(q,e,contract):
    condition=shape(q,e);s=e.section;b=address(field(q,s,'VisibleVar'))
    require(b and q.index.number(s,'VisibleLink',-1)==2,'VISIBILITY_LINK','Direct PLC link2 BOOL visibility required')
    tag=contract_rows(contract).get(b['address'])
    require(tag and tag['type']=='BOOL' and type(tag['words']) is int and tag['words']==0 and tag['access']=='READ_ONLY','VISIBILITY_TAG','Visibility requires an exact readonly BOOL zero-word contract tag')
    require(b['link']==field(q,q.app,'CommName1') and b['station']==q.index.number(q.app,'DefPLCStationNr1'),'VISIBILITY_LINK','Visibility must use the actual source link/station')
    return dict(role='READ_ONLY_BOOL_VISIBILITY',**b,visible_when=condition==0,visible_condition=condition,native_qualified=False,runtime_qualified=False)

def values(q,e,spec,contract,profile):
    require(isinstance(spec,dict) and set(spec)=={'address','type','access','link','station','visible_when'},'VISIBILITY_SPEC','Complete typed visibility identity and boolean visible_when required')
    require(contract is not None,'CONTRACT','Visibility edits need a hash-bound typed contract')
    condition=shape(q,e)
    require(type(spec['visible_when']) is bool and spec['visible_when']==(condition==0),'VISIBILITY_CONDITION','visible_when must match the existing source condition; condition is never rewritten')
    require(spec['type']=='BOOL' and spec['access']=='READ_ONLY','VISIBILITY_TAG','Only readonly BOOL visibility is qualified')
    require(isinstance(spec['address'],str) and re.fullmatch('M[0-9]+',spec['address']),'VISIBILITY_TAG','Explicit M BOOL address required')
    tag=contract_rows(contract).get(spec['address'])
    require(tag and tag['type']=='BOOL' and type(tag['words']) is int and tag['words']==0 and tag['access']=='READ_ONLY','VISIBILITY_TAG','Visibility tag must match the exact readonly BOOL contract')
    require(isinstance(spec['link'],str) and spec['link']==profile['link'] and type(spec['station']) is int and spec['station']==profile['station'],'VISIBILITY_LINK','Visibility must retain the reviewed source link/station')
    # Link2 is accepted only when an actual readonly numeric source owner already
    # carries the direct PLC BOOL tuple. No native enum is guessed from a label.
    witnesses=[]
    for page in q.pages:
        for owner in page.elements:
            if family(q,owner)!=(5,1):continue
            b=address(field(q,owner.section,'VisibleVar'))
            if not b or not b['address'].startswith('M') or b['link']!=profile['link'] or b['station']!=profile['station'] or q.index.number(owner.section,'VisibleLink',-1)!=2:continue
            try:shape(q,owner)
            except ValueError:continue
            witnesses.append(dict(page_id=page.page_id,element_id=q.index.number(owner.section,'nPartsID'),element_sha256=element_hash(q,owner)))
    require(witnesses,'VISIBILITY_WITNESS','Same-source direct PLC BOOL numeric visibility witness is required')
    return dict(VisibleVar='{'+spec['link']+'}'+str(spec['station'])+'@'+spec['address'],VisibleLink=2),witnesses
