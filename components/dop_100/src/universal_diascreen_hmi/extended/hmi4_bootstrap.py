# SPDX-License-Identifier: Apache-2.0
"""Portable source fingerprint and relative package imports; no project loaders."""
from pathlib import Path
import os,json,re
from .common import Error,canonical,sha,require,hash_value,no_links,write_new,engine_identity
HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('DIA_HMI_REFERENCE_ROOT',str(HERE))).absolute()
VERSION='0.4.0'
def identity():return engine_identity()
def release_inventory():
    root=HERE.parent
    rows={}
    for p in sorted(root.rglob('*.py')):
        no_links(p);require(p.stat().st_nlink==1,'RELEASE_LINK','Source hardlinks excluded')
        rows[p.relative_to(root).as_posix()]=dict(sha256=sha(p.read_bytes()),bytes=p.stat().st_size)
    require({'cli.py','session.py','extended/hmi4_bootstrap.py','extended/hmi4_service.py','extended/hmi4_transaction.py'}<=set(rows),'RELEASE_INVENTORY','Required source missing')
    return rows

def validate_release_manifest(value,actual):
    require(isinstance(value,dict) and set(value)=={'schema','version','files'} and value['schema']=='delta.hmi.source-release.v1' and value['version']==VERSION,'RELEASE_MANIFEST','Unqualified source manifest')
    rows=value['files'];require(isinstance(rows,list) and rows,'RELEASE_INVENTORY','Nonempty complete source inventory required')
    found={}
    for row in rows:
        require(isinstance(row,dict) and set(row)=={'path','sha256','bytes'},'RELEASE_MANIFEST','Malformed source row')
        name=row['path'];require(isinstance(name,str) and name and len(name)<=240 and '\\' not in name and ':' not in name and not Path(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')) and Path(name).as_posix()==name,'RELEASE_PATH','Normalized relative source path required')
        require(name not in found and isinstance(row['sha256'],str) and re.fullmatch('[a-f0-9]{64}',row['sha256']) is not None and type(row['bytes']) is int and row['bytes']>=0,'RELEASE_MANIFEST','Duplicate or invalid source row')
        found[name]=dict(sha256=row['sha256'],bytes=row['bytes'])
    require(found==actual,'RELEASE_DRIFT','Complete source membership, hashes and sizes must match')
    return dict(status='SOURCE_MANIFEST_VERIFIED',version=VERSION,files=len(found))

def verify_release():
    p=HERE/'RELEASE_MANIFEST.json'
    if not p.exists():return dict(status='SOURCE_FINGERPRINT_ONLY',version=VERSION,engine_sha256=identity())
    no_links(p);require(p.stat().st_nlink==1,'RELEASE_LINK','Manifest hardlinks excluded')
    result=validate_release_manifest(json.loads(p.read_bytes()),release_inventory())
    return dict(**result,manifest_sha256=sha(p.read_bytes()),engine_sha256=identity())
import universal_diascreen_hmi.native as _native
from .native_index import NativeIndex
_native.NativeIndex=NativeIndex
from universal_diascreen_hmi.native import Project,Patch,apply_spans,restore_spans,layout_digest
from universal_diascreen_hmi.operations import token_patch,validate_references
from universal_diascreen_hmi.session import profile_check
from universal_diascreen_hmi.resources import validate_reviewed_resources
from .file_ownership import immutable_read,worker_lease
def block(q,start,end,edits):
    return apply_spans(q.file.payload[start:end],[Patch(p.start-start,p.end-start,p.old,p.new,p.reason) for p in edits])[0]
from .core import Service as CoreService
