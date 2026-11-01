# SPDX-License-Identifier: Apache-2.0
"""Original synthetic templates and durable lifecycle counterexamples; no vendor assets."""
from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from tests.test_extended import fixture
from tests.fixtures import wide, line
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.extended import template_catalog as catalog
from universal_diascreen_hmi.extended import template_lifecycle as lifecycle
from universal_diascreen_hmi.extended import neutral_screens
from universal_diascreen_hmi.resources import _header


def neutral_fixture():
    raw, profile = fixture(); q = Project(raw); stock = q.pages[1]
    page = q.file.payload[stock.section.start:stock.end].replace(wide('wTextLen', 'Second'), wide('wTextLen', 'Blank')+wide('wTitleTextLen000', 'Blank'))
    body = q.file.payload[:q.pages[0].section.start].replace(b'DefaultScreen=1\r\n', b'DefaultScreen=2\r\n')+page+q.file.payload[q.index.tail_start:]
    body=body.replace(b'DefaultScreen=2\r\n',b'DefaultScreen=2\r\nControllerName1=Synthetic Driver\r\nCommName1=Link1\r\nDefPLCStationNr1=0\r\nInterface1=1\r\nPLCPort1=502\r\nPLCIP1=0\r\nInterface0=0\r\n')
    raw = q.file.encode(body); q = Project(raw); profile['indexed_layout_sha256'] = layout_digest(q)
    profile['background_sha256'].pop('1'); profile['reviewed_resources']['source_payload_sha256'] = sha(body)
    for frame in profile['reviewed_resources']['frames']:
        section = frame['section']; start = body.index(('['+section+']\r\n').encode())
        frame['header_start'] = start
    return raw, profile


def host_catalog(root):
    root.mkdir(); raw, profile = neutral_fixture(); target = dict(family='diascreen-dop100', model='268502788', editor_version='6.6.2.48', width=800, height=480)
    qualification = dict(decoder='DIASCREEN_PDAB_COUNTED_V1', operations=['template_copy', 'neutral_page', 'target_transition'])
    entries=[]
    for identity in ('blank_a','blank_b'):
        profile_raw=canonical(profile); (root/(identity+'.dpa')).write_bytes(raw); (root/(identity+'.json')).write_bytes(profile_raw)
        receipt=dict(schema='delta.hmi.template-review.v1', template_id=identity, seed_sha256=sha(raw), profile_sha256=sha(profile_raw), target_sha256=sha(canonical(target)),
                     descriptor_sha256=sha(canonical(dict(template_id=identity,target=target,qualification=qualification))), coverage=catalog.coverage(Project(raw)),
                     origin='ORIGINAL_SYNTHETIC_OFFLINE_FIXTURE', reuse_rights='AUTHORIZED_LOCAL_TEMPLATE_REUSE',reviewer='independent-synthetic-test-contract',
                     auth_review='NO_CUSTOMER_CREDENTIALS_OR_PROJECT_CONTENT',opaque_review='EXACT_OWNERS_REVIEWED_NO_CUSTOMER_ASSETS',status='PASS')
        review_raw=canonical(receipt); (root/(identity+'.review.json')).write_bytes(review_raw)
        entries.append(dict(id=identity, seed=dict(path=identity+'.dpa',sha256=sha(raw)),profile=dict(path=identity+'.json',sha256=sha(profile_raw)),
                            review=dict(path=identity+'.review.json',sha256=sha(review_raw)),target=target,qualification=qualification))
    value=dict(schema=catalog.SCHEMA,templates=entries,transitions=[{'from':'blank_a','to':'blank_b'}]); (root/'catalog.json').write_bytes(canonical(value))
    return raw,profile,value


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.host=self.root/'host';self.work=self.root/'work';self.work.mkdir()
        self.raw,self.profile,self.registry=host_catalog(self.host)
        self.env=patch.dict(os.environ,{'DIA_HMI_TEMPLATE_ROOT':str(self.host)});self.env.start();self.addCleanup(self.env.stop)
    def service(self,write=True):return Service(self.work,allow_write=write)
    def refusal(self,code,fn):
        with self.assertRaises(Exception) as cm:fn()
        self.assertEqual(getattr(cm.exception,'code',None),code,str(cm.exception))
    def propose(self,s,path='new.dpa',**updates):
        info=s.inspect_template('blank_a')
        args=dict(template_id='blank_a',output_path=path,**{k:info[k] for k in ('seed_sha256','profile_sha256','catalog_sha256','engine_sha256')});args.update(updates)
        return s.create_project(**args)
    def copy(self,path='new.dpa'):
        s=self.service();p=self.propose(s,path);h=p['plan_sha256'];s.inspect_native_plan(h);s.apply_project_plan(h,h);s.inspect();return s
    def test_copy_then_native_page_apply_save_and_fresh_restore(self):
        s=self.copy();self.assertEqual((self.work/'new.dpa').read_bytes(),self.raw)
        proposal=s.create_neutral_screen(sha(self.raw),'blank_a',3,'Ayarlar',0x123456);h=proposal['plan_sha256']
        q=Project(self.raw);self.assertEqual(proposal['proof']['stock_page_sha256'],sha(q.file.payload[q.pages[0].section.start:q.pages[0].end]))
        self.assertEqual(proposal['proof']['seed_sha256'],sha(self.raw));self.assertNotEqual(proposal['proof']['stock_page_sha256'],sha(self.raw))
        s=self.service();s.open_project('new.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)));s.inspect();s.restore_plan(h);s.apply_plan(h,h)
        s.inspect();self.assertEqual(len(s.inspect_neutral_screens(sha(s.current),'blank_a')['pages']),2)
        s.save_as('two.dpa',sha(s.current));saved=(self.work/'two.dpa').read_bytes();self.assertEqual(saved,s.current)
        self.assertEqual((self.work/'new.dpa').read_bytes(),self.raw);self.assertEqual((self.host/'blank_a.dpa').read_bytes(),self.raw)
        s=self.service();s.open_project('new.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)));s.inspect();s.restore_candidate(h,h)
        self.assertEqual(s.current,saved)
    def test_plan_pins_inspection_approval_and_write_gates(self):
        s=self.service()
        for field in ('seed_sha256','profile_sha256','catalog_sha256','engine_sha256'):
            self.refusal('TEMPLATE_PIN',lambda:self.propose(s,**{field:'0'*64}))
        p=self.propose(s);h=p['plan_sha256']
        self.refusal('INSPECTION_REQUIRED',lambda:s.apply_project_plan(h,h));s.inspect_native_plan(h)
        self.refusal('APPROVAL',lambda:s.apply_project_plan(h,'0'*64))
        r=self.service(False);r.inspect_native_plan(h);self.refusal('WRITE_DISABLED',lambda:r.apply_project_plan(h,h))
        self.assertFalse((self.work/'new.dpa').exists())
    def test_new_only_and_paths(self):
        s=self.service();(self.work/'exists.dpa').write_bytes(self.raw)
        self.refusal('OUTPUT_EXISTS',lambda:self.propose(s,'exists.dpa'))
        for name in ('../seed.dpa','/outside.dpa','sub/../bad.dpa','bad\\name.dpa','bad:stream.dpa'):
            self.refusal('TEMPLATE_OUTPUT',lambda:self.propose(s,name))
        self.refusal('TEMPLATE_OUTPUT',lambda:self.propose(s,'bad.dps'))
        self.assertEqual((self.work/'exists.dpa').read_bytes(),self.raw)
    def test_two_same_seed_projects_are_separate_plan_namespaces(self):
        a=self.copy('a.dpa');b=self.copy('b.dpa')
        p=a.create_neutral_screen(sha(self.raw),'blank_a',3,'Settings',0);q=b.create_neutral_screen(sha(self.raw),'blank_a',3,'Settings',0)
        self.assertNotEqual(p['plan_sha256'],q['plan_sha256'])
        self.refusal('PLAN_SOURCE',lambda:b.restore_plan(p['plan_sha256']))
        a.apply_plan(p['plan_sha256'],p['plan_sha256']);b.apply_plan(q['plan_sha256'],q['plan_sha256'])
        self.assertEqual(a.current,b.current)
    def test_response_loss_discovers_effect_by_plan_and_reconciles_no_write(self):
        s=self.service();p=self.propose(s);h=p['plan_sha256'];s.inspect_native_plan(h)
        original=lifecycle.write_owned
        def interrupted(journal,oid,path,data):original(journal,oid,path,data);raise OSError('synthetic post-write loss')
        with patch.object(lifecycle,'write_owned',interrupted):
            with self.assertRaises(OSError):s.apply_project_plan(h,h)
        s=self.service();again=self.propose(s);self.assertEqual(again['plan_sha256'],h)
        op=s.inspect_native_plan(h)['operation'];self.assertEqual(op['state'],'UNKNOWN_OUTCOME')
        before=(self.work/'new.dpa').stat().st_mtime_ns
        with patch.object(lifecycle,'write_owned',side_effect=AssertionError('recovery must never write')):
            recovered=s.reconcile_operation(op['operation_id']);self.assertEqual(recovered['state'],'SUCCEEDED')
            self.assertEqual(recovered['session_source'],'ATTACHED_VERIFIED_TEMPLATE_COPY')
        self.assertEqual((self.work/'new.dpa').stat().st_mtime_ns,before)
        s.inspect();p=s.create_neutral_screen(sha(s.current),'blank_a',3,'Recovered',0);nh=p['plan_sha256'];s.apply_plan(nh,nh);s.save_as('recovered.dpa',sha(s.current))
        self.refusal('PENDING_WORK',lambda:s.apply_project_plan(h,h))
    def test_prepared_only_same_bytes_cannot_become_success(self):
        s=self.service();p=self.propose(s);h=p['plan_sha256']
        op=s.journal.reserve('template:new.dpa','qualified_template_copy',dict(plan_sha256=h));(self.work/'new.dpa').write_bytes(self.raw)
        self.assertEqual(s.reconcile_operation(op)['state'],'UNKNOWN_OUTCOME')
    def test_catalog_receipt_seed_and_profile_drift_refuse(self):
        for name in ('blank_a.dpa','blank_a.json','blank_a.review.json'):
            with self.subTest(name=name):
                p=self.host/name;old=p.read_bytes();p.write_bytes(old+b' ')
                self.refusal('TEMPLATE_DRIFT',lambda:catalog.load('blank_a'));p.write_bytes(old)
        s=self.service();p=self.propose(s);(self.host/'catalog.json').write_bytes(canonical({**self.registry,'transitions':[]}))
        self.refusal('ENGINE_DRIFT',lambda:s.inspect_native_plan(p['plan_sha256']))
    def test_review_scope_substitution_and_duplicate_json_refuse(self):
        value=deepcopy(self.registry);value['templates'][0]['qualification']['operations']=['template_copy']
        (self.host/'catalog.json').write_bytes(canonical(value));self.refusal('TEMPLATE_REVIEW',lambda:catalog.load('blank_a'))
        (self.host/'catalog.json').write_bytes(b'{"schema":1,"schema":2}')
        self.refusal('CATALOG_DUPLICATE',catalog.catalog)
    def test_header_version_not_profile_allowlist_selects_exact_target(self):
        value=deepcopy(self.registry);entry=value['templates'][0];profile=deepcopy(self.profile);profile['application_versions'].append('9.9.9.9')
        raw=canonical(profile);(self.host/'blank_a.json').write_bytes(raw);entry['profile']['sha256']=sha(raw);entry['target']['editor_version']='9.9.9.9'
        receipt=catalog.document((self.host/'blank_a.review.json').read_bytes());receipt.update(profile_sha256=sha(raw),target_sha256=sha(canonical(entry['target'])),descriptor_sha256=sha(canonical(dict(template_id='blank_a',target=entry['target'],qualification=entry['qualification']))))
        raw=canonical(receipt);(self.host/'blank_a.review.json').write_bytes(raw);entry['review']['sha256']=sha(raw);(self.host/'catalog.json').write_bytes(canonical(value))
        self.refusal('TEMPLATE_TARGET',lambda:catalog.load('blank_a'))
    def test_applied_neutral_plan_cannot_save_after_seed_or_review_change(self):
        s=self.copy();p=s.create_neutral_screen(sha(self.raw),'blank_a',3,'Three',0);h=p['plan_sha256'];s.apply_plan(h,h)
        for name in ('blank_a.dpa','blank_a.review.json'):
            pin=self.host/name;old=pin.read_bytes();pin.write_bytes(old+b' ')
            self.refusal('TEMPLATE_DRIFT',lambda:s.save_as('never.dpa',sha(s.current)));pin.write_bytes(old)
        self.assertFalse((self.work/'never.dpa').exists())
    def test_neutral_descendant_artifact_recovery_rechecks_seed_and_review(self):
        from universal_diascreen_hmi.extended import hmi4_artifacts as artifacts
        s=self.copy();p=s.create_neutral_screen(sha(s.current),'blank_a',3,'Three',0);h=p['plan_sha256'];s.apply_plan(h,h);s.inspect()
        before=dict(tags=[dict(address='D100',type='INT',words=1,access='READ_ONLY')],source_digest='0'*64);after={**before,'source_digest':'1'*64}
        package=s.plan_offline_package(sha(s.current),'neutral.zip','neutral.dpa',dict(ip='0.0.0.0',port=502))['plan_sha256']
        rebind=s.plan_contract_rebind(sha(s.current),before,sha(canonical(before)),after,sha(canonical(after)))['plan_sha256']
        for ph in (package,rebind):
            kind,record,data=artifacts.load(s,ph);oid=s.journal.reserve('hmi4artifact:'+ph,kind,dict(plan_sha256=ph,**record));s.journal.transition(oid,'RUNNING')
            for name in ('blank_a.dpa','blank_a.review.json'):
                path=self.host/name;original=path.read_bytes();path.write_bytes(original+b' ')
                self.refusal('TEMPLATE_DRIFT',lambda:s.reconcile_operation(oid));path.write_bytes(original)
                self.assertEqual(s.inspect_operation(oid)['state'],'RUNNING')
    def test_missing_catalog_and_workspace_overlap(self):
        with patch.dict(os.environ,{'DIA_HMI_TEMPLATE_ROOT':''}):
            self.refusal('TEMPLATE_UNAVAILABLE',lambda:self.service().inspect_template('blank_a'))
        self.refusal('CATALOG_OVERLAP',lambda:Service(self.host))
    def test_hardlinked_seed_refuses(self):
        seed=self.host/'blank_a.dpa';alias=self.host/'alias.dpa'
        os.link(seed,alias)
        self.refusal('OUTPUT_FILE',lambda:catalog.load('blank_a'))
    def test_target_transition_only_registered_exact_blank(self):
        s=self.copy();p=s.configure_target(sha(self.raw),'blank_a','blank_b','target.dpa');h=p['plan_sha256'];s.inspect_native_plan(h);s.apply_project_plan(h,h)
        self.assertEqual(s.inspect_target_configuration(sha(s.current))['model'],'268502788')
        s.inspect()
        self.refusal('TEMPLATE_TRANSITION',lambda:s.configure_target(sha(s.current),'blank_b','blank_a','bad.dpa'))
    def test_target_reads_native_application_and_refuses_profile_disagreement(self):
        s=self.copy();r=s.inspect_target_configuration(sha(self.raw))
        self.assertEqual(r['native_application_communication']['driver'],'Synthetic Driver');self.assertEqual(r['status'],'NATIVE_READBACK_PASS')
        self.assertEqual(r['native_application_communication']['ipv4'],'0.0.0.0')
        q=Project(self.raw);changed=q.file.encode(q.file.payload.replace(b'CommName1=Link1',b'CommName1=Other'))
        (self.work/'different.dpa').write_bytes(changed);p=deepcopy(self.profile);p['indexed_layout_sha256']=layout_digest(Project(changed))
        delta=len(Project(changed).file.payload)-len(q.file.payload);p['reviewed_resources']['source_payload_sha256']=sha(Project(changed).file.payload)
        for f in p['reviewed_resources']['frames']:f['header_start']+=delta
        s=self.service();s.open_project('different.dpa',sha(changed),p,sha(canonical(p)))
        self.refusal('TARGET_CONFIGURATION',lambda:s.inspect_target_configuration(sha(changed)))
    def test_stale_transition_and_creation_session_cannot_write(self):
        s=self.copy();p=s.configure_target(sha(self.raw),'blank_a','blank_b','target.dpa');h=p['plan_sha256'];s.inspect_native_plan(h)
        native=s.create_neutral_screen(sha(self.raw),'blank_a',3,'Settings',0);nh=native['plan_sha256'];s.apply_plan(nh,nh)
        self.refusal('TEMPLATE_TRANSITION',lambda:s.apply_project_plan(h,h));self.assertFalse((self.work/'target.dpa').exists())
        fresh=self.service();p=self.propose(fresh,'other.dpa');h=p['plan_sha256'];fresh.inspect_native_plan(h)
        fresh.open_project('new.dpa',sha(self.raw),self.profile,sha(canonical(self.profile)))
        self.refusal('PENDING_WORK',lambda:fresh.apply_project_plan(h,h));self.assertFalse((self.work/'other.dpa').exists())
    def test_neutral_name_id_color_and_one_byte_ancestry_refuse(self):
        s=self.copy()
        for args,code in [((True,'Three',0),'NEUTRAL_PAGE_ID'),((2,'Three',0),'NEUTRAL_PAGE_ID'),((3,'blank',0),'NEUTRAL_PAGE_NAME'),
                          ((3,'A'*65,0),'NEUTRAL_PAGE_NAME'),((3,'\ud800',0),'NEUTRAL_PAGE_NAME'),((3,'Three',True),'NEUTRAL_PAGE_COLOR'),((3,'Three',0x1000000),'NEUTRAL_PAGE_COLOR')]:
            self.refusal(code,lambda:s.create_neutral_screen(sha(self.raw),'blank_a',*args))
        info=s.inspect_template('blank_a');pins={k:info[k] for k in ('template_id','seed_sha256','profile_sha256','catalog_sha256','review_sha256')}
        q=Project(self.raw)
        for old,new,code in [(b'PictureOffset=0',b'PictureOffset=1','NEUTRAL_PAGE_SCHEMA'),(b'PanelName=DOP-107EV',b'PanelName=DOP-107EX','NEUTRAL_PREAMBLE'),(b'OpaqueTailWithoutCRLF',b'OpaqueTailWithoutCRLg','NEUTRAL_RESOURCES')]:
            raw=q.file.encode(q.file.payload.replace(old,new));self.refusal(code,lambda:neutral_screens.audit(raw,self.profile,pins))
    def test_real_stdio_template_transport_and_readback(self):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
        proc=subprocess.Popen([sys.executable,'-B','-m','universal_diascreen_hmi.cli','--workspace',str(self.work),'--allow-write'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        counter=0
        def call(method,params):
            nonlocal counter;counter+=1;proc.stdin.write(canonical(dict(jsonrpc='2.0',id=counter,method=method,params=params))+b'\n');proc.stdin.flush()
            line=proc.stdout.readline();self.assertTrue(line,proc.stderr.read().decode() if proc.poll() is not None else 'No reply')
            response=json.loads(line);self.assertNotIn('error',response);return response['result']
        try:
            call('initialize',{});tools=call('tools/list',{})['tools'];names={t['name'] for t in tools};self.assertEqual(len(names),83)
            def tool(name,args):
                r=call('tools/call',dict(name=name,arguments=args));self.assertFalse(r['isError'],r);return r['structuredContent']
            info=tool('inspect_template',dict(template_id='blank_a'))
            p=tool('create_project',dict(template_id='blank_a',output_path='pipe.dpa',**{k:info[k] for k in ('seed_sha256','profile_sha256','catalog_sha256','engine_sha256')}));h=p['plan_sha256']
            tool('inspect_native_plan',dict(plan_sha256=h));tool('apply_project_plan',dict(plan_sha256=h,approval_sha256=h))
            self.assertEqual(tool('inspect_target_configuration',dict(candidate_sha256=sha(self.raw)))['model'],'268502788')
            tool('inspect',{});p=tool('create_neutral_screen',dict(candidate_sha256=sha(self.raw),template_id='blank_a',new_page_id=3,name='Settings',background_color=0));nh=p['plan_sha256']
            applied=tool('apply_plan',dict(plan_sha256=nh,approval_sha256=nh));saved=tool('save_as',dict(path='pipe-saved.dpa',candidate_sha256=applied['candidate_sha256']))
            self.assertEqual(saved['sha256'],sha((self.work/'pipe-saved.dpa').read_bytes()));self.assertEqual(len(Project((self.work/'pipe-saved.dpa').read_bytes()).pages),2)
        finally:
            proc.terminate();proc.communicate(timeout=10)


if __name__=='__main__':unittest.main()
