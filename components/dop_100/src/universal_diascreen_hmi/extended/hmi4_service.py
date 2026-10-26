# SPDX-License-Identifier: Apache-2.0
"""Shared reusable CLI/MCP service; no private project generator imports."""
from copy import deepcopy
import json
from .hmi4_bootstrap import *
from . import hmi4_inspect as inspect4
from . import hmi4_transaction as transaction
from . import hmi4_registry as reference
from . import hmi4_visual as visual
from . import hmi4_artifacts as artifacts
class Service(CoreService):
    def __init__(self,workspace,*,allow_write=False,read_roots=()):
        verify_release();reference_roots=[(ROOT/e['dpa']['path']).parent for e in reference.registry()['deliveries']]
        super().__init__(workspace,allow_write=allow_write,read_roots=[*read_roots,*reference_roots])
        self.extension_identity=identity()
        with self.journal.connect() as db:
            row=db.execute('SELECT value FROM metadata WHERE name=?',('hmi4_engine_sha256',)).fetchone()
            require(row is None or row[0]==self.extension_identity,'ENGINE_DRIFT','Workspace belongs to different HMI4 engine')
            if row is None:db.execute('INSERT INTO metadata VALUES (?,?)',('hmi4_engine_sha256',self.extension_identity))
            db.execute('CREATE TABLE IF NOT EXISTS hmi4_bases (id TEXT PRIMARY KEY,raw BLOB NOT NULL,profile BLOB NOT NULL)')
        artifacts.init(self)
    def checked(self,candidate_sha256,inspected=False):
        self._loaded();hash_value(candidate_sha256);require(candidate_sha256==sha(self.current),'CANDIDATE_HASH','Wrong current native candidate')
        require(identity()==self.extension_identity,'ENGINE_DRIFT','Active engine files changed')
        if inspected:require(self.inspected_sha==candidate_sha256,'INSPECTION_REQUIRED','Inspect the exact current native source first')
    def write_scope(self):
        require(identity()==self.extension_identity,'ENGINE_DRIFT','Active engine changed')
        if self.source is not None:
            forbidden={e['dpa']['sha256'] for e in reference.registry()['deliveries'] if e['status']=='USER_CANCELLED'}
            require(sha(self.source) not in forbidden and sha(self.current) not in forbidden,'CANCELLED_SOURCE','Cancelled machine revisions are historical read-only references')
    def capabilities(self):
        r=super().capabilities()
        for name in [n for n in r if n.startswith(('r06_','r07_','r08_','r09_'))]:r.pop(name)
        r.update(adapter_version=VERSION,engine_sha256=identity(),overall='SOURCE_QUALIFIED_NATIVE_FILE_SERVICES',active_reference=reference.registry()['active_revision'],vendor_qualified=False,device_access=False)
        r['source_integrity']=verify_release()
        r['native_transactions']=dict(implemented=True,headless=True,native_qualified=False,operations=['edit_element','numeric_display','bind_element','move_element','clone_element','replace_element','edit_page','clone_page','navigation','background_png'],types=['BOOL','INT','DINT','REAL'],source_owners='Explicit source block hashes; source-derived families; no new macro opcodes',preserved='Application/auth/global macros/prefix/thumbnail and unowned objects',page_limit=96)
        r['native_inspection']=dict(complete_indexed_inventory=True,numeric_fields=True,affine_scale=True,states_and_fonts=3,navigation=True,resources='REVIEWED_BOUNDARIES_ONLY',parameter_matrix='VERSIONED_REFERENCE_AND_ACTUAL_NATIVE')
        r['register_driver']='SOURCE_QUALIFIED_BOOL_INT_DINT_REAL_WIDGET_BINDINGS; not runtime driver qualification'
        r['typed_register_bindings']=dict(implemented=True,headless=True,types=['BOOL','INT','DINT','REAL'],tool='plan_register_import',native_tag_alias_table=False,word_order_runtime='NOT_QUALIFIED')
        r['numeric_scale_fields']=dict(implemented=True,headless=True,types=['INT','DINT','REAL'],native_qualified=False,tools=['configure_numeric_fields','plan_native_update','inspect_affine_scale'])
        r['native_visuals']=dict(font_fit=True,saved_layer_PNG=True,colorref='BGR',scope='SYNTHETIC_NOT_VENDOR_PIXELS')
        r['offline_project_package']=dict(implemented=True,headless=True,new_only=True,journal_reconciliation=True,vendor_transfer_package=False)
        r['contract_rebind']=dict(implemented=True,native_replay=False,required='Same declared ABI/meaning/scale/enums/limits; only source_digest can differ',PLC_runtime_accepted=False)
        r['retired_revisions_read_only']=True
        r['qualification_state']='SOURCE_BOUND_FILE_TESTED_VENDOR_UNQUALIFIED'
        return r
    def list_deliveries(self):return reference.list_deliveries()
    def current_delivery(self):
        e=reference.entry();return dict(active_revision=e['revision'],status=e['status'],dpa_path=e['dpa']['path'],candidate_sha256=e['dpa']['sha256'],profile_sha256=e['profile_sha256'],endpoint=e.get('endpoint'),vendor_compile='NOT_RUN')
    def open_delivery(self,revision,candidate_sha256,profile_sha256,stage_source=True):
        e,raw,profile=reference.load(revision);require(candidate_sha256==sha(raw) and profile_sha256==sha(canonical(profile)),'REFERENCE_HASH','Explicit reference candidate/profile pins required')
        if stage_source:
            require(e['status']!='USER_CANCELLED','CANCELLED_SOURCE','Cancelled reference cannot be staged for editing')
            require(self.allow_write,'WRITE_DISABLED','--allow-write required to stage a new immutable workspace source')
            name='source_'+e['revision']+'_'+candidate_sha256[:12]+'.dpa';p=no_links(self.workspace/name)
            if p.exists():
                with immutable_read(p) as (b,unchanged):require(b==raw,'SOURCE_DRIFT','Staged source differs');unchanged()
            else:write_new(p,raw)
            path=name
        else:path=str(ROOT/e['dpa']['path'])
        opened=super().open_project(path,candidate_sha256,profile,profile_sha256)
        return {**opened,'reference_revision':e['revision'],'reference_status':e['status'],'staged_source':stage_source}
    def inspect_native_catalog(self,candidate_sha256,page_id=None):
        self.checked(candidate_sha256);return inspect4.inventory(self._project(),self.current_profile,page_id)
    def inspect_numeric_bindings(self,candidate_sha256):
        self.checked(candidate_sha256);q=self._project()
        return dict(candidate_sha256=candidate_sha256,items=[inspect4.row(q,p,e) for p in q.pages for e in p.elements if inspect4.numeric(q,e) is not None],native_qualified=False)
    def inspect_numeric_fields(self,candidate_sha256,page_id,element_id):
        self.checked(candidate_sha256);q=self._project();e=q.element(page_id,element_id);require(inspect4.numeric(q,e) is not None,'NUMERIC_FAMILY','Numeric source family required')
        return inspect4.row(q,q.page(page_id),e)
    def configure_numeric_fields(self,candidate_sha256,page_id,element_id,expected_element_sha256,spec):
        self.checked(candidate_sha256,inspected=True);require(isinstance(spec,dict) and set(spec)=={'gain','offset','integer_digits','decimals'},'NUMERIC_SPEC','Exact legacy native-scale fields required')
        q=self._project();e=q.element(page_id,element_id);n=inspect4.numeric(q,e);require(n is not None,'NUMERIC_FAMILY','Numeric source family required')
        dots=spec['decimals'];require(type(dots) is int and 0<=dots<=6,'NUMERIC_DIGITS','Bounded decimals required')
        from decimal import Decimal
        factor=Decimal(1) if n['iec_type']=='REAL' else Decimal(10)**dots
        display=dict(gain=str(inspect4.dec(spec['gain'])/factor),offset=str(inspect4.dec(spec['offset'])/factor),integer_digits=spec['integer_digits'],decimals=dots)
        specification=dict(version=1,operations=[dict(op='numeric_display',page_id=page_id,element_id=element_id,expected_element_sha256=expected_element_sha256,display=display)])
        return self.plan_native_update(candidate_sha256,specification,sha(canonical(specification)))
    def plan_register_import(self,candidate_sha256,contract,contract_sha256,bindings):
        self.checked(candidate_sha256,inspected=True);require(isinstance(bindings,list) and 1<=len(bindings)<=999,'BINDINGS','Explicit bounded native widget bindings required')
        operations=[]
        for binding in bindings:
            require(isinstance(binding,dict) and set(binding)=={'page_id','element_id','expected_element_sha256','binding'},'BINDINGS','Exact selector and typed binding required');operations.append(dict(op='bind_element',**binding))
        specification=dict(version=1,operations=operations,contract=contract,contract_sha256=contract_sha256)
        return self.plan_native_update(candidate_sha256,specification,sha(canonical(specification)))
    def inspect_multilingual_text(self,candidate_sha256,page_id=None):
        data=self.inspect_native_catalog(candidate_sha256,page_id)
        return dict(candidate_sha256=candidate_sha256,items=[dict(page_id=r['page_id'],element_id=r['element_id'],element_sha256=r['element_sha256'],states=r['states']) for r in data['items']],native_languages=[0,1,2])
    def inspect_navigation(self,candidate_sha256):self.checked(candidate_sha256);return inspect4.navigation(self._project())
    def inspect_endpoint(self,candidate_sha256,expected_endpoint=None):
        self.checked(candidate_sha256);result=inspect4.endpoint(self._project())
        if expected_endpoint is not None:require(isinstance(expected_endpoint,dict) and set(expected_endpoint)=={'ip','port'} and all(result[k]==v for k,v in expected_endpoint.items()),'ENDPOINT','Native endpoint differs')
        return {**result,'status':'PASS'}
    def inspect_parameters(self,revision=None):return dict(revision=reference.entry(revision)['revision'],matrix=reference.matrix(revision),scope='Frozen per-field native parameter matrix; not PLC runtime values')
    def get_reference_contract(self,revision=None):return reference.reference_contract(revision)
    def validate_bindings(self,candidate_sha256,contract,contract_sha256,require_all=False):
        self.checked(candidate_sha256);return inspect4.audit_contract(self._project(),contract,contract_sha256,require_all)
    def inspect_affine_scale(self,candidate_sha256,page_id,element_id,raw_value=None,display_value=None):
        self.checked(candidate_sha256);q=self._project();n=inspect4.numeric(q,q.element(page_id,element_id));require(n is not None,'NUMERIC_FAMILY','Numeric input/display required')
        gain=inspect4.dec(n['native_gain']);offset=inspect4.dec(n['native_offset']);factor=inspect4.dec(n['factor']);require(gain!=0,'NUMERIC_SCALE','Zero gain has no inverse')
        result={**n,'candidate_sha256':candidate_sha256,'page_id':page_id,'element_id':element_id,'scope':'OFFLINE_NATIVE_FIELDS_AND_AFFINE_MATH_NOT_PANEL_RUNTIME'}
        if raw_value is not None:result['display_value']=str((inspect4.dec(raw_value)*gain+offset)/factor)
        if display_value is not None:result['raw_value']=str((inspect4.dec(display_value)*factor-offset)/gain)
        return result
    def plan_native_update(self,candidate_sha256,specification,specification_sha256):
        self.checked(candidate_sha256,inspected=True);self.write_scope();hash_value(specification_sha256)
        require(specification_sha256==sha(canonical(specification)),'SPEC_HASH','Exact immutable specification required')
        built=transaction.build(self.current,self.current_profile,specification)
        key=sha(canonical(dict(candidate_sha256=candidate_sha256,profile_sha256=self.current_profile_sha256)))
        with self.journal.connect() as db:
            old=db.execute('SELECT raw,profile FROM hmi4_bases WHERE id=?',(key,)).fetchone();values=(self.current,canonical(self.current_profile))
            require(old is None or (bytes(old[0]),bytes(old[1]))==values,'BASE_DRIFT','Native base collision')
            if old is None:db.execute('INSERT INTO hmi4_bases VALUES (?,?,?)',(key,*values))
        steps=[dict(operation_id='hmi4-native-update',input_payload_sha256=sha(Project(self.current).file.payload),output_payload_sha256=sha(Project(built['candidate']).file.payload),ledger=built['ledger'],reviewed_resources_after=built['profile']['reviewed_resources'])]
        record=dict(source_sha256=sha(self.source),base_sha256=candidate_sha256,base_profile_sha256=self.current_profile_sha256,profile_sha256=self.profile_sha256,candidate_sha256=sha(built['candidate']),candidate_profile_sha256=sha(canonical(built['profile'])),ledger_sha256=sha(canonical(steps)),operations=[dict(op='hmi4_native_update',specification=specification,specification_sha256=specification_sha256)],donors={key:sha(v.file.original) for key,v in sorted(self.donors.items())},hmi4_engine_sha256=identity(),hmi4_base_key=key)
        h=sha(canonical(record));plan=dict(record=record,candidate=built['candidate'],profile=built['profile'],steps=steps);self.journal.save_plan(h,plan,self.applied[-1] if self.applied else None);self.plans[h]=plan
        return dict(plan_sha256=h,approval_sha256_required=h,candidate_sha256=record['candidate_sha256'],candidate_profile_sha256=record['candidate_profile_sha256'],specification_sha256=specification_sha256,engine_sha256=identity(),proof=built['proof'],applied=False)
    def strict(self,p):
        r=p['record']
        if 'hmi4_engine_sha256' not in r:return
        require(r['hmi4_engine_sha256']==identity() and len(r['operations'])==1,'ENGINE_DRIFT','Exact native extension engine required');op=r['operations'][0]
        require(op['op']=='hmi4_native_update' and sha(canonical(op['specification']))==op['specification_sha256'],'PLAN_DRIFT','Native specification changed')
        with self.journal.connect() as db:row=db.execute('SELECT raw,profile FROM hmi4_bases WHERE id=?',(r['hmi4_base_key'],)).fetchone()
        require(row is not None,'BASE_UNKNOWN','Native plan base missing');raw=bytes(row[0]);profile=json.loads(row[1])
        require(sha(raw)==r['base_sha256'] and sha(canonical(profile))==r['base_profile_sha256'],'BASE_DRIFT','Native plan base changed')
        built=transaction.build(raw,profile,op['specification']);require(built['candidate']==p['candidate'] and canonical(built['profile'])==canonical(p['profile']) and canonical(built['ledger'])==canonical(p['steps'][0]['ledger']),'PLAN_DRIFT','Native plan reconstruction differs')
    def inspect_native_plan(self,plan_sha256):
        p,_=self.journal.load_plan(plan_sha256);self.strict(p);op=self.journal.find('apply:'+p['record']['source_sha256']+':'+plan_sha256)
        return dict(plan_sha256=plan_sha256,record=p['record'],profile=p['profile'],operation=op,native_qualified=False)
    def restore_plan(self,plan_sha256):
        self.write_scope();r=super().restore_plan(plan_sha256);self.strict(self.plans[plan_sha256]);return r
    def apply_plan(self,plan_sha256,approval_sha256):
        self.write_scope();require(self.allow_write,'WRITE_DISABLED','--allow-write required');require(plan_sha256==approval_sha256,'APPROVAL','Exact immutable plan approval required')
        p=self._checked_proposal(plan_sha256);self.strict(p)
        a=Project(self.current);b=Project(p['candidate'])
        require(a.file.payload[:a.pages[0].section.start]==b.file.payload[:b.pages[0].section.start],'APPLICATION_PRESERVE','Generic editing cannot alter Application/auth/global macros')
        return super().apply_plan(plan_sha256,approval_sha256)
    def restore_candidate(self,plan_sha256,approval_sha256):
        self.write_scope();r=super().restore_candidate(plan_sha256,approval_sha256)
        for p in self.plans.values():self.strict(p)
        return r
    def save_as(self,path,candidate_sha256):
        self.write_scope();self.checked(candidate_sha256)
        if self.applied:self.strict(self.plans[self.applied[-1]])
        return super().save_as(path,candidate_sha256)
    def save_new(self,path,candidate_sha256):return self.save_as(path,candidate_sha256)
    def validate_native_candidate(self,candidate_sha256,include_font_fit=False):
        self.checked(candidate_sha256);q=self._project();profile_check(q,self.current_profile);validate_references(q)
        result=dict(status='NATIVE_STRUCTURAL_FILE_PASS',candidate_sha256=candidate_sha256,profile_sha256=self.current_profile_sha256,pages=len(q.pages),objects=sum(len(p.elements) for p in q.pages),endpoint=inspect4.endpoint(q),navigation=inspect4.navigation(q),native_qualified=False,vendor_compile='NOT_RUN')
        if include_font_fit:result['font_fit']=visual.fit(q)
        return result
    def check_text_fit(self,candidate_sha256,page_id=None):self.checked(candidate_sha256);return visual.fit(self._project(),page_id)
    def preview_native_page(self,candidate_sha256,page_id,language,values=None):self.checked(candidate_sha256);return visual.render(self._project(),self.current_profile,page_id,language,values)
    def plan_offline_package(self,candidate_sha256,output_path,dpa_name,expected_endpoint):return artifacts.plan_package(self,candidate_sha256,output_path,dpa_name,expected_endpoint)
    def apply_offline_package(self,plan_sha256,approval_sha256):return artifacts.apply(self,plan_sha256,approval_sha256)
    def inspect_artifact_plan(self,plan_sha256):
        kind,record,_=artifacts.load(self,plan_sha256);operation=self.journal.find('hmi4artifact:'+plan_sha256)
        return dict(kind=kind,plan_sha256=plan_sha256,record=record,operation=operation)
    def inspect_offline_package(self,path,artifact_sha256,candidate_sha256,expected_endpoint):
        hash_value(artifact_sha256);hash_value(candidate_sha256);p=self._path(path)
        with immutable_read(p) as (raw,unchanged):require(sha(raw)==artifact_sha256,'ARTIFACT_HASH','Offline package hash differs');result=artifacts.inspect_zip(raw,candidate_sha256,expected_endpoint);unchanged()
        return result
    def plan_contract_rebind(self,candidate_sha256,previous_contract,previous_sha256,contract,contract_sha256):return artifacts.plan_rebind(self,candidate_sha256,previous_contract,previous_sha256,contract,contract_sha256)
    def apply_contract_rebind(self,plan_sha256,approval_sha256):return artifacts.apply(self,plan_sha256,approval_sha256)
    def reconcile_operation(self,operation_id):
        if self.journal.inspect(operation_id)['kind'] in ('offline_project_package','contract_rebind'):return artifacts.reconcile(self,operation_id)
        return super().reconcile_operation(operation_id)
