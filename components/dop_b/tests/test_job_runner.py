"""Job integration using original constructed bytes; never vendor evidence."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from universal_hmi.errors import HmiError
from universal_hmi.job_policy import canonical, digest, tree_digest
from universal_hmi.job_runner import JobRunner, write_json


class JobFixture(unittest.TestCase):
    def setUp(self):
        from test_service import ControlGenerationServiceTests
        self.fixture = ControlGenerationServiceTests('test_all_six_controls_public_save_reopen_preservation_length_and_states')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.fixture.root
        self.registry = self.base / 'registry'
        shutil.copytree(self.fixture.profile_dir, self.registry)
        self.output = self.base / 'delivery'; self.output.mkdir()
        self.reviews = self.base / 'reviews'; self.reviews.mkdir()
        self.state = self.base / 'state'
        ops = self.fixture.plan()['operations']
        self.policy = dict(schema_version=1, reference='UNIT TEST ONLY: not human production approval',
            workspace=str(self.workspace), profiles_root=str(self.registry),
            output_root=str(self.output), reviews_root=str(self.reviews),
            profile_tree_sha256=tree_digest(self.registry),
            input_files={p.relative_to(self.workspace).as_posix():digest(p.read_bytes())
                         for p in self.workspace.rglob('*') if p.is_file()},
            profiles=['source_controls_v1'], allowed_operations=sorted({p['op'] for p in ops}),
            author_id='test-author', reviewers={'technical_plan':'test-tech','aesthetic_first':'test-a',
                'aesthetic_second':'test-b','technical_native':'test-tech'}, max_seconds=120, max_output_bytes=8*1024**2)
        self.policy_path = self.base / 'policy.json'
        write_json(self.policy_path, self.policy)
        self.job = dict(schema_version=1, profile_id='source_controls_v1', source_path='source.dps', design=self.fixture.design)
        self.runner = JobRunner(self.policy_path, self.state)

    def reviews_for(self, job_id, subject, candidate=None):
        previous = None
        for role in self.runner.policy.ROLES if candidate else self.runner.policy.ROLES[:3]:
            report = dict(schema_version=1, job_id=job_id, role=role, reviewer_id=self.policy['reviewers'][role],
                subject_sha256=candidate if role=='technical_native' else subject,
                previous_review_sha256=previous if role in ('aesthetic_second','technical_native') else None,
                verdict='PASS', findings=[], evidence='UNIT TEST ONLY: synthetic review to test protocol, not acceptance')
            path = self.reviews / job_id / (role+'.json'); write_json(path,report)
            previous = digest(path.read_bytes())

    def complete(self):
        job_id = self.runner.submit('original', self.job)['job_id']
        first = self.runner.run(job_id)
        self.assertEqual(first['status'],'WAITING_REVIEWS',first)
        subject = first['details']['subject_sha256']
        self.reviews_for(job_id,subject)
        second = self.runner.run(job_id)
        self.assertEqual(second['status'],'WAITING_REVIEWS',second)
        self.assertEqual(second['details']['missing_review'],'technical_native')
        self.reviews_for(job_id,subject,second['details']['candidate_subject_sha256'])
        third = self.runner.run(job_id)
        self.assertEqual(third['status'],'COMPLETED',third)
        return job_id


class JobRunnerTests(JobFixture):
    def test_dispatcher_and_worker_ignore_mutable_import_roots(self):
        import os,time
        marker=self.state/'IMPORT_EXECUTED'
        payload='from pathlib import Path;Path('+repr(str(marker))+').write_text("poison")\n'
        (self.state/'sitecustomize.py').write_text(payload)
        shadow=self.state/'universal_hmi';shadow.mkdir()
        (shadow/'__init__.py').write_text(payload)
        (shadow/'cli.py').write_text(payload)
        with patch.dict(os.environ,{'PYTHONPATH':str(self.state)}):
            first=self.runner.submit('isolated-worker',self.job)['job_id']
            self.assertEqual(self.runner.supervise(first)['status'],'WAITING_REVIEWS')
            self.runner.store.cancel(first)
            second=self.runner.submit('isolated-dispatcher',self.job)['job_id']
            self.runner.start_dispatcher()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if self.runner.status(second)['status']=='WAITING_REVIEWS':break
                time.sleep(.1)
            self.assertEqual(self.runner.status(second)['status'],'WAITING_REVIEWS')
            self.runner.store.cancel(second)
            time.sleep(2.2)
        self.assertFalse(marker.exists(),'Mutable state/PYTHONPATH code executed')
        self.assertFalse((shadow/'__pycache__').exists())

    def test_server_start_resumes_durable_queue_without_submit(self):
        import asyncio,sys,time,subprocess
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        jid=self.runner.submit('restart',self.job)['job_id']
        child=subprocess.run([sys.executable,'-c',
            'import os,sys;from universal_hmi.job_store import JobStore;'
            's=JobStore(sys.argv[1]);assert s.claim(sys.argv[2],"dead",lease_seconds=1);os._exit(17)',
            str(self.state),jid],check=False)
        self.assertEqual(child.returncode,17)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli',
                '--profiles',str(self.registry),'serve','--workspace',str(self.workspace),
                '--job-policy',str(self.policy_path),'--job-state',str(self.state)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();deadline=time.monotonic()+20
                    while time.monotonic()<deadline:
                        r=await client.call_tool('job_status',{'job_id':jid})
                        self.assertFalse(r.is_error,str(r));state=r.structured_content
                        if state['status']=='WAITING_REVIEWS':return
                        await asyncio.sleep(.2)
                    self.fail(str(state))
        asyncio.run(exercise())
        self.runner.store.cancel(jid)

    def test_dispatch_recovers_dead_child_before_lease_expiry_without_resubmit(self):
        import subprocess,sys
        jid=self.runner.submit('early-exit',self.job)['job_id']
        child=subprocess.run([sys.executable,'-c',
            'import os,sys;from universal_hmi.job_store import JobStore;'
            's=JobStore(sys.argv[1]);assert s.claim(sys.argv[2],"dead-child",lease_seconds=1);os._exit(17)',
            str(self.state),jid],check=False)
        self.assertEqual(child.returncode,17)
        self.assertEqual(self.runner.status(jid)['status'],'RUNNING')
        self.assertEqual(self.runner.store.pending(),[])
        self.runner.dispatch(idle_seconds=3,poll_seconds=.05)
        recovered=self.runner.status(jid)
        self.assertEqual(recovered['status'],'WAITING_REVIEWS',recovered)
        self.assertEqual(recovered['attempts'],2)

    def test_mutated_work_preview_cannot_enter_reviewed_delivery(self):
        original_reviews=self.runner._reviews
        def mutate_after_candidate_review(jid,subject,candidate=None):
            result=original_reviews(jid,subject,candidate)
            if candidate and result[1] is None:
                for path in (self.workspace/'.headless'/jid).rglob('preview-normal.html'):
                    path.write_text('UNREVIEWED REPLACEMENT',encoding='utf-8')
            return result
        with patch.object(self.runner,'_reviews',mutate_after_candidate_review):jid=self.complete()
        self.assertNotIn('UNREVIEWED REPLACEMENT',(self.output/jid/'preview-normal.html').read_text(encoding='utf-8'))

    def test_invalid_stage_is_rejected_before_irreversible_pin(self):
        jid=self.runner.submit('bad-stage',self.job)['job_id']
        r=self.runner.run(jid);subject=r['details']['subject_sha256'];self.reviews_for(jid,subject)
        r=self.runner.run(jid);self.reviews_for(jid,subject,r['details']['candidate_subject_sha256'])
        original=write_json
        def corrupt_stage(path,value):
            if Path(path).name=='checks.json' and Path(path).parent.name.startswith('.staging-'):
                value=dict(value,diff={'tampered':True})
            return original(path,value)
        with patch('universal_hmi.job_runner.write_json',corrupt_stage):r=self.runner.run(jid)
        self.assertEqual(r['status'],'FAILED');self.assertIsNone(r['publication_sha256'])
        self.assertFalse((self.output/jid).exists())

    def test_crash_after_rename_reconciles_exact_pinned_package(self):
        import sqlite3
        from universal_hmi.job_runner import publish_directory
        def crash(source,dest):
            publish_directory(source,dest)
            raise OSError('simulated process crash after rename')
        # Prepare reviews without publishing.
        jid=self.runner.submit('crash',self.job)['job_id']
        r=self.runner.run(jid);subject=r['details']['subject_sha256'];self.reviews_for(jid,subject)
        r=self.runner.run(jid);self.reviews_for(jid,subject,r['details']['candidate_subject_sha256'])
        with patch('universal_hmi.job_runner.publish_directory',crash):r=self.runner.run(jid)
        self.assertEqual(r['status'],'RUNNING');self.assertEqual(r['recovery']['code'],'RECOVERY_BLOCKED')
        self.assertTrue((self.output/jid/'project.dps').exists())
        with self.assertRaises(HmiError):self.runner.store.cancel(jid)
        from contextlib import closing
        with closing(sqlite3.connect(self.state/'jobs.sqlite3')) as conn:
            conn.execute('UPDATE jobs SET lease_expires_at=0 WHERE job_id=?',(jid,));conn.commit()
        restarted=JobRunner(self.policy_path,self.state)
        self.assertEqual(restarted.run(jid)['status'],'COMPLETED')
        self.assertEqual(restarted.result(jid)['status'],'OFFLINE_DELIVERY_COMPLETE')

    def test_real_stdio_two_queued_jobs_resume_when_reviews_arrive(self):
        import asyncio, sys, time
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli',
                '--profiles',str(self.registry),'serve','--workspace',str(self.workspace),
                '--job-policy',str(self.policy_path),'--job-state',str(self.state)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),14)
                    async def call(name,**kw):
                        r=await client.call_tool(name,kw);self.assertFalse(r.is_error,str(r));return r.structured_content
                    await call('preflight_job',job=self.job)
                    ids=[(await call('submit_job',idempotency_key=k,job=self.job))['job_id'] for k in ('first','second')]
                    done=set();deadline=time.monotonic()+90;written={}
                    while len(done)<2 and time.monotonic()<deadline:
                        for jid in ids:
                            status=await call('job_status',job_id=jid)
                            self.assertNotIn(status['status'],('FAILED','CANCELLED'),status)
                            if status['status']=='WAITING_REVIEWS':
                                req=status['details'];candidate=req.get('candidate_subject_sha256')
                                key=(jid,candidate)
                                if key not in written:
                                    self.reviews_for(jid,req['subject_sha256'],candidate);written[key]=True
                            elif status['status']=='COMPLETED':
                                await call('job_result',job_id=jid);done.add(jid)
                        await asyncio.sleep(.3)
                    self.assertEqual(done,set(ids))
        asyncio.run(exercise())

    def test_real_service_emit_review_save_reopen_and_idempotency(self):
        from universal_hmi.native import NativeAdapter
        job_id = self.complete()
        self.assertEqual(self.runner.submit('original',self.job)['job_id'],job_id)
        result = self.runner.result(job_id)
        self.assertEqual(result['vendor'],'NOT_RUN')
        native = NativeAdapter((Path(result['path'])/'project.dps').read_bytes(),'delta_dopsoft2')
        self.assertEqual(len(native.inspect()['screens'][0]['elements']),12)
        self.assertEqual((self.workspace/'source.dps').read_bytes(),self.fixture.source)

    def test_no_reviews_never_publishes(self):
        job_id=self.runner.submit('missing',self.job)['job_id']
        self.assertEqual(self.runner.run(job_id)['status'],'WAITING_REVIEWS')
        self.assertFalse((self.output/job_id).exists())
        with self.assertRaises(HmiError):self.runner.result(job_id)

    def test_forged_final_directory_fails(self):
        job_id=self.runner.submit('forged',self.job)['job_id']
        (self.output/job_id).mkdir()
        self.assertEqual(self.runner.run(job_id)['status'],'FAILED')

    def test_rehashed_native_or_missing_file_cannot_reuse_reviews(self):
        job_id=self.complete(); root=self.output/job_id
        manifest=json.loads((root/'manifest.json').read_bytes())
        (root/'project.dps').write_bytes(b'FORGED')
        manifest['files']['project.dps']={'sha256':digest(b'FORGED'),'bytes':6}
        write_json(root/'manifest.json',manifest)
        write_json(root/'COMPLETE.json',{'manifest_sha256':digest((root/'manifest.json').read_bytes())})
        with self.assertRaises(HmiError):self.runner.result(job_id)

    def test_review_chain_change_revokes_result(self):
        job_id=self.complete()
        path=self.reviews/job_id/'aesthetic_first.json'
        report=json.loads(path.read_bytes());report['evidence']='changed';write_json(path,report)
        with self.assertRaises(HmiError):self.runner.result(job_id)

    def test_cancelled_job_does_not_emit(self):
        job_id=self.runner.submit('cancel',self.job)['job_id']
        self.runner.store.cancel(job_id)
        self.assertEqual(self.runner.run(job_id)['status'],'CANCELLED')
        self.assertFalse((self.output/job_id).exists())

    def test_missing_file_and_extra_file_rejected(self):
        job_id=self.complete(); root=self.output/job_id
        (root/'extra').write_text('extra')
        with self.assertRaises(HmiError):self.runner.result(job_id)
        (root/'extra').unlink();(root/'preview-normal.html').unlink()
        with self.assertRaises(HmiError):self.runner.result(job_id)
