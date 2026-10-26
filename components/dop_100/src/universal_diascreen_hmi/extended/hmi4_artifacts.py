# SPDX-License-Identifier: Apache-2.0
"""New-only project ZIPs and metadata-only contract rebinds; never vendor packages."""
from io import BytesIO
from pathlib import Path
import json,zipfile
from .hmi4_bootstrap import *
from .hmi4_inspect import endpoint,audit_contract,contract_rows
def init(service):
    with service.journal.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS hmi4_artifact_plans (id TEXT PRIMARY KEY,kind TEXT NOT NULL,record BLOB NOT NULL,payload BLOB NOT NULL)')
def store(service,kind,record,payload):
    record={**record,'kind':kind,'engine_sha256':identity(),'payload_sha256':sha(payload)};h=sha(canonical(record))
    with service.journal.connect() as db:
        values=(h,kind,canonical(record),payload);old=db.execute('SELECT * FROM hmi4_artifact_plans WHERE id=?',(h,)).fetchone()
        require(old is None or tuple(old)==values,'PLAN_DRIFT','Artifact plan collision')
        if old is None:db.execute('INSERT INTO hmi4_artifact_plans VALUES (?,?,?,?)',values)
    return dict(plan_sha256=h,approval_sha256_required=h,kind=kind,candidate_sha256=record['candidate_sha256'],artifact_sha256=sha(payload),applied=False,vendor_qualified=False)
def load(service,h):
    hash_value(h)
    with service.journal.connect() as db:r=db.execute('SELECT kind,record,payload FROM hmi4_artifact_plans WHERE id=?',(h,)).fetchone()
    require(r is not None,'PLAN_UNKNOWN','Unknown artifact plan');record=json.loads(r[1]);data=bytes(r[2])
    require(sha(canonical(record))==h and sha(data)==record['payload_sha256'] and record['engine_sha256']==identity(),'PLAN_DRIFT','Artifact plan/engine changed')
    return r[0],record,data
def zip_bytes(raw,profile,name,revision):
    require(isinstance(name,str) and Path(name).name==name and name.endswith('.dpa') and len(name)<=160 and ':' not in name,'PACKAGE_NAME','Simple .dpa filename required')
    files={name:raw,'profile.json':canonical(profile)+b'\n'}
    manifest=dict(schema='delta.offline.hmi-project-package.v1',scope='NATIVE_PROJECT_FILES_ONLY_NOT_VENDOR_TRANSFER_PACKAGE',revision=revision,dpa=name,candidate_sha256=sha(raw),profile_sha256=sha(canonical(profile)),endpoint=endpoint(Project(raw)),vendor_compile='NOT_RUN',runtime='NOT_RUN',files={n:sha(b) for n,b in files.items()})
    files['MANIFEST.json']=canonical(manifest)+b'\n';buf=BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in files.items():
            info=zipfile.ZipInfo(n,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,b)
    return buf.getvalue()
def inspect_zip(raw,expected_candidate_sha256=None,expected_endpoint=None):
    require(len(raw)<=128*1024*1024,'ZIP_LIMIT','Bounded offline ZIP required')
    with zipfile.ZipFile(BytesIO(raw)) as z:
        infos=z.infolist();names=[x.filename for x in infos]
        require(1<=len(infos)<=200 and len(set(names))==len(names) and all(not x.flag_bits&1 and x.file_size<=128*1024*1024 and not x.is_dir() and Path(x.filename).name==x.filename and ':' not in x.filename and '\\' not in x.filename and '/' not in x.filename for x in infos),'ZIP_SCOPE','Flat bounded unique unencrypted ZIP files required')
        require(sum(x.file_size for x in infos)<=256*1024*1024,'ZIP_LIMIT','Unpacked ZIP exceeds bound')
        native=[n for n in names if n.lower().endswith('.dpa')];require(len(native)==1,'PACKAGE_DPA','Exactly one DPA required')
        require('MANIFEST.json' in names and 'profile.json' in names,'PACKAGE_MANIFEST','Profile/manifest required')
        manifest=json.loads(z.read('MANIFEST.json'));project=z.read(native[0]);profile=json.loads(z.read('profile.json'));q=Project(project);profile_check(q,profile)
        require(manifest.get('schema')=='delta.offline.hmi-project-package.v1' and manifest['dpa']==native[0] and manifest['candidate_sha256']==sha(project) and manifest['profile_sha256']==sha(canonical(profile)),'PACKAGE_BINDING','Native/profile manifest mismatch')
        require(set(manifest['files'])==set(names)-{'MANIFEST.json'} and all(sha(z.read(n))==h for n,h in manifest['files'].items()),'PACKAGE_HASH','Package member hash mismatch')
        require(expected_candidate_sha256 is None or expected_candidate_sha256==sha(project),'ARTIFACT_HASH','Package native differs')
        ep=endpoint(q)
        require(expected_endpoint is None or all(ep.get(k)==v for k,v in expected_endpoint.items()),'ENDPOINT','Package endpoint differs')
    return dict(status='OFFLINE_PROJECT_PACKAGE_PASS',zip_sha256=sha(raw),candidate_sha256=sha(project),profile_sha256=sha(canonical(profile)),endpoint=ep,files=names,vendor_transfer_package=False,vendor_compile='NOT_RUN')
def plan_package(service,candidate_sha256,output_path,dpa_name,expected_endpoint):
    service.checked(candidate_sha256,inspected=True);service.write_scope();output=service._path(output_path,output=True)
    require(output.suffix.lower()=='.zip','PACKAGE_PATH','New .zip output required')
    require(isinstance(expected_endpoint,dict) and set(expected_endpoint)=={'ip','port'},'ENDPOINT','Explicit endpoint gate required')
    raw=zip_bytes(service.current,service.current_profile,dpa_name,'MCP_CURRENT_CANDIDATE');inspect_zip(raw,candidate_sha256,expected_endpoint)
    record=dict(source_sha256=sha(service.source),candidate_sha256=candidate_sha256,profile_sha256=service.current_profile_sha256,path=output.relative_to(service.workspace).as_posix(),endpoint=expected_endpoint)
    return store(service,'offline_project_package',record,raw)
def plan_rebind(service,candidate_sha256,previous_contract,previous_sha256,contract,contract_sha256):
    service.checked(candidate_sha256,inspected=True);service.write_scope()
    require(previous_sha256==sha(canonical(previous_contract)) and contract_sha256==sha(canonical(contract)),'CONTRACT_HASH','Exact previous/new contracts required');contract_rows(previous_contract);contract_rows(contract)
    # Only source provenance may change. All declared ABI, labels, units, enums and limits remain exact.
    left={k:v for k,v in previous_contract.items() if k!='source_digest'};right={k:v for k,v in contract.items() if k!='source_digest'}
    left['tags']=sorted(left['tags'],key=lambda t:t['address']);right['tags']=sorted(right['tags'],key=lambda t:t['address'])
    require(canonical(left)==canonical(right),'CONTRACT_SEMANTIC_DRIFT','Rebind cannot hide ABI/meaning/scale/enum/limit changes')
    audit=audit_contract(service._project(),contract,contract_sha256)
    require(audit['status']=='PASS','CONTRACT_NATIVE_DRIFT','New contract differs from native fields')
    receipt=dict(status='COMPATIBLE_DECLARED_CONTRACT_NATIVE_UNCHANGED',candidate_sha256=candidate_sha256,previous_contract_sha256=previous_sha256,contract_sha256=contract_sha256,previous_source_digest=previous_contract.get('source_digest'),source_digest=contract.get('source_digest'),audit=audit,native_apply_replayed=False,native_save_replayed=False,PLC_runtime_accepted=False)
    return store(service,'contract_rebind',dict(source_sha256=sha(service.source),candidate_sha256=candidate_sha256,profile_sha256=service.current_profile_sha256),canonical(receipt)+b'\n')
def apply(service,plan_sha256,approval_sha256):
    service.write_scope();require(service.allow_write,'WRITE_DISABLED','--allow-write required');require(plan_sha256==approval_sha256,'APPROVAL','Exact immutable artifact plan approval required')
    kind,record,data=load(service,plan_sha256);service.checked(record['candidate_sha256']);require(record['source_sha256']==sha(service.source) and record['profile_sha256']==service.current_profile_sha256,'PLAN_SOURCE','Artifact source/profile changed')
    with worker_lease(service.workspace):
        previous=service.journal.find('hmi4artifact:'+plan_sha256)
        require(previous is None,'REPLAY_OR_UNKNOWN','Artifact intent already exists; inspect_artifact_plan and reconcile_operation instead of replaying')
        output=None
        if kind=='offline_project_package':output=service._path(record['path'],output=True);inspect_zip(data,record['candidate_sha256'],record['endpoint'])
        operation=service.journal.reserve('hmi4artifact:'+plan_sha256,kind,dict(plan_sha256=plan_sha256,**record));service.journal.transition(operation,'RUNNING')
        try:
            with immutable_read(service.source_path) as (source,unchanged):require(sha(source)==record['source_sha256'],'SOURCE_DRIFT','Artifact source file changed');unchanged()
            if output is not None:
                write_new(output,data)
                with immutable_read(output) as (saved,unchanged):require(saved==data,'SAVED_REREAD','ZIP write differs');inspect_zip(saved,record['candidate_sha256'],record['endpoint']);unchanged()
                result=dict(path=str(output),artifact_sha256=sha(data),candidate_sha256=record['candidate_sha256'],vendor_transfer_package=False)
            else:result=json.loads(data)
            service.journal.transition(operation,'SUCCEEDED',result)
        except BaseException:
            service.journal.transition(operation,'UNKNOWN_OUTCOME',dict(reason='Artifact outcome requires reconciliation'));raise
    return dict(operation_id=operation,status='SUCCEEDED',kind=kind,result=result)
def reconcile(service,operation_id):
    op=service.journal.inspect(operation_id)
    if op['state'] in ('SUCCEEDED','FAILED','TIMED_OUT'):return service.inspect_operation(operation_id)
    intent=op['intent'];kind,record,data=load(service,intent['plan_sha256']);require(kind==op['kind'],'OPERATION','Wrong artifact operation kind')
    with worker_lease(service.workspace):
        with service.journal.connect() as db:started=db.execute('SELECT 1 FROM events WHERE operation_id=? AND state=?',(operation_id,'RUNNING')).fetchone()
        if not started:return service.inspect_operation(operation_id)
        if kind=='contract_rebind':service.journal.transition(operation_id,'SUCCEEDED',json.loads(data))
        else:
            path=service._path(record['path'])
            if path.is_file():
                with immutable_read(path) as (saved,unchanged):
                    if saved==data:inspect_zip(saved,record['candidate_sha256'],record['endpoint']);unchanged();service.journal.transition(operation_id,'SUCCEEDED',dict(artifact_sha256=sha(data),candidate_sha256=record['candidate_sha256'],reconciled=True))
    return service.inspect_operation(operation_id)
