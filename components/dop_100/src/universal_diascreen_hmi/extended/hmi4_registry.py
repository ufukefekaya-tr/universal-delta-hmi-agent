# SPDX-License-Identifier: Apache-2.0
"""Read-only versioned reference catalog. Active machine semantics are data, not code."""
import json
from .hmi4_bootstrap import *
from .template_catalog import document,path_at
def root():return no_links(os.environ.get('DIA_HMI_REFERENCE_ROOT',str(ROOT))).resolve()
def registry():
    path=root()/'registry.json'
    if not os.environ.get('DIA_HMI_REFERENCE_ROOT'):return dict(schema='delta.hmi.reference-registry.v1',active_revision=None,deliveries=[],font_sha256={})
    with immutable_read(no_links(path)) as (raw,unchanged):value=document(raw);unchanged()
    require(value.get('schema')=='delta.hmi.reference-registry.v1' and isinstance(value.get('deliveries'),list) and len(value['deliveries'])<=128,'REGISTRY','Unknown trusted host reference catalog')
    revisions=set()
    for e in value['deliveries']:
        revision=e.get('revision');require(isinstance(revision,str) and re.fullmatch('[A-Za-z0-9_-]{1,80}',revision) and revision not in revisions,'REGISTRY','Bounded unique reference identity required');revisions.add(revision)
        for k in ('dpa','profile','parameters','tags'):
            if k in e:
                require(isinstance(e[k],dict) and set(e[k])=={'path','sha256'},'REGISTRY','Exact reference file pin required');path_at(root(),e[k]['path']);hash_value(e[k]['sha256'])
        require('dpa'in e and 'profile'in e,'REGISTRY','Reference source/profile required')
    require(value.get('active_revision') is None or value['active_revision']in revisions,'REGISTRY','Active reference is absent')
    return value

def entry(revision=None):
    reg=registry();revision=revision or reg['active_revision'];rows=[r for r in reg['deliveries'] if r['revision']==revision]
    require(len(rows)==1,'DELIVERY_UNKNOWN','Unknown versioned delivery');return rows[0]
def read_pin(pin):
    path=path_at(root(),pin['path'])
    with immutable_read(path) as (raw,unchanged):require(sha(raw)==pin['sha256'],'REFERENCE_DRIFT','Frozen reference changed');unchanged()
    return raw
def load(revision=None):
    e=entry(revision);raw=read_pin(e['dpa']);profile=json.loads(read_pin(e['profile']));q=Project(raw);profile_check(q,profile)
    require(sha(canonical(profile))==e['profile_sha256'],'PROFILE_HASH','Reference profile changed');return e,raw,profile
def list_deliveries():
    reg=registry();return dict(active_revision=reg['active_revision'],deliveries=[dict(revision=e['revision'],status=e['status'],availability=e.get('availability','PAIR_NOT_AUDITED'),dpa_sha256=e['dpa']['sha256'],profile_sha256=e['profile_sha256'],path=e['dpa']['path']) for e in reg['deliveries']],scope='Versioned native file references; not compiled artifacts')
def matrix(revision=None):
    e=entry(revision);require('parameters' in e,'PARAMETERS_UNAVAILABLE','No frozen matrix for this revision');return json.loads(read_pin(e['parameters']))
def reference_contract(revision=None):
    e=entry(revision);require('tags' in e,'CONTRACT_UNAVAILABLE','No frozen tag catalog for this revision')
    raw=json.loads(read_pin(e['tags']));source=raw['tags'];tags=[]
    parameters={p['address']:p for p in matrix(revision).get('parameters',[])} if 'parameters' in e else {}
    # Export the four currently source-qualified native types, not logical-only type promises.
    for t in source:
        if t.get('type') not in ('BOOL','INT','DINT','REAL'):continue
        row={k:t[k] for k in ('tag','address','type','words','access')}
        if 'enum' in t:row['enum']=t['enum']
        if t['address'] in parameters:
            source_fields=parameters[t['address']].get('native',{});keys={'MemLen','MemFmt','GainValue','OffsetValue','DotNum','IntNum','MinValue','MaxValue','HiWordFirst','HiDwordFirst','Level','ReadLink','WriteLink'}
            row['numeric_input']={k:v for k,v in source_fields.items() if k in keys}
        tags.append(row)
    contract=dict(schema='delta.native-bindings.v1',tags=tags,forbidden_writes=e.get('forbidden_writes',[]),endpoint=e.get('endpoint'))
    return dict(revision=e['revision'],status=e['status'],contract=contract,contract_sha256=sha(canonical(contract)),source_catalog_sha256=e['tags']['sha256'],total_source_tags=len(source),unsupported_types=sorted({t['type'] for t in source if t.get('type') not in ('BOOL','INT','DINT','REAL')}),native_qualified=False,live_PLC_accepted=False)
