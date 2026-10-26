# SPDX-License-Identifier: Apache-2.0
"""Read-only versioned reference catalog. Active machine semantics are data, not code."""
import json
from .hmi4_bootstrap import *
def registry():
    path=ROOT/'registry.json'
    if not os.environ.get('DIA_HMI_REFERENCE_ROOT'):return dict(schema='delta.hmi.reference-registry.v1',active_revision=None,deliveries=[],font_sha256={})
    value=json.loads(no_links(path).read_bytes());require(value.get('schema')=='delta.hmi.reference-registry.v1','REGISTRY','Unknown trusted host reference catalog');return value

def entry(revision=None):
    reg=registry();revision=revision or reg['active_revision'];rows=[r for r in reg['deliveries'] if r['revision']==revision]
    require(len(rows)==1,'DELIVERY_UNKNOWN','Unknown versioned delivery');return rows[0]
def read_pin(pin):
    path=no_links(ROOT/pin['path']);require(path.resolve().is_relative_to(ROOT),'REGISTRY_PATH','Reference escapes project')
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
