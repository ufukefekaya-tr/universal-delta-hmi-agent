"""Durable job orchestration over the existing guarded file service.

Trusted host agents deposit reviews outside the writable workspace. Missing
reviews produce WAITING_REVIEWS, never invented human approval or fake PASS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .errors import HmiError
from .job_policy import TaskPolicy, canonical, digest, no_links, relative_file, read_object
from .job_store import JobStore
from .service import FileService

DELIVERY_FILES = frozenset(('project.dps', 'preview-normal.html', 'preview-on.html', 'preview-invalid.html',
                            'checks.json', 'reviews.json', 'design.json', 'bindings.json'))


def write_json(path, value):
    path = no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as handle:
            handle.write(canonical(value) + b'\n')
            handle.flush()
            os.fsync(handle.fileno())
        no_links(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_directory(source, destination):
    """Atomic no-replace directory publication on the two supported platforms."""
    no_links(source); no_links(destination)
    if os.name == 'nt':
        os.rename(source, destination)  # Windows rejects an existing destination.
    elif sys.platform.startswith('linux'):
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, 'renameat2', None)
        if rename is None:
            raise HmiError('JOB_PLATFORM', 'Atomic no-replace rename requires Linux renameat2')
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        raise HmiError('JOB_PLATFORM', 'Atomic publication is qualified for Windows and Linux only')


class JobRunner:
    def __init__(self, policy_path, state_dir):
        self.policy = TaskPolicy(policy_path)
        self.state_dir = no_links(state_dir).absolute()
        for writable in (self.policy.workspace, self.policy.output_root):
            if self.state_dir.is_relative_to(writable):
                raise HmiError('JOB_POLICY', 'Job state must be outside native-file workspace/output roots')
        self.store = JobStore(self.state_dir)

    def _service(self, authorize=None):
        return FileService(self.policy.workspace, self.policy.profiles_root, task_authorizer=authorize)

    def _plan(self, job):
        self.policy.authorize_job(job)
        service = self._service()
        opened = service.open_project(job['profile_id'], job['source_path'])
        sid = opened['session_id']
        if service.sessions[sid]['profile']['family'] != 'delta_dopsoft2':
            raise HmiError('JOB_FAMILY', 'This release job pipeline is DOP-B only')
        receipt = service.plan_changes(sid, job['design'], None, 'job-plan')
        self.policy.authorize_plan(receipt['operations'])
        checked = service.validate(sid, receipt['plan_id'])
        if not checked['offline_pass']:
            raise HmiError('JOB_VALIDATION', 'Job cannot be emitted', findings=checked['findings'])
        samples = {}; active = {}
        for tag in job['design'].get('tags', []):
            tag_id = tag['id']
            if tag['data_type']=='BOOL':
                samples[tag_id]=0;active[tag_id]=1
            else:
                elements=[e for page in job['design']['screens'] for e in page['elements']
                          if e.get('binding',{}).get('read')==tag_id and e['kind'] in ('numeric_input','numeric_display')]
                lower=max([e.get('minimum',0) for e in elements] or [0])
                upper=min([e.get('maximum',lower) for e in elements] or [lower])
                samples[tag_id]=max(lower,min(0,upper));active[tag_id]=upper
        previews = {}
        for name, kwargs in [('normal', {'values':samples}), ('on', {'values':active}), ('invalid', {'valid': False})]:
            previews[name] = service.preview(sid, receipt['plan_id'], **kwargs)['html']
        subject = digest(canonical({'job': job, 'policy_sha256': self.policy.sha256,
                    'contract': {k: v for k, v in receipt.items() if k.endswith('_sha256')},
                    'operations': receipt['operations'],
                    'previews': {k: digest(v.encode()) for k, v in previews.items()}}))
        return service, sid, receipt, checked, previews, subject

    def preflight(self, job):
        _, _, receipt, checked, _, subject = self._plan(job)
        return {'status': 'PREFLIGHT_PASS', 'subject_sha256': subject,
                'policy_sha256': self.policy.sha256, 'plan': receipt,
                'validation': checked, 'vendor': 'NOT_RUN', 'physical': 'NOT_RUN'}

    def submit(self, key, job):
        self.preflight(job)
        return self.store.submit(key, {'policy_sha256': self.policy.sha256, 'job': job},
                                 max_seconds=self.policy.data['max_seconds'])

    def status(self, job_id):
        result = self.store.status(job_id)
        diagnostic = no_links(self.state_dir / (job_id + '.recovery.json'))
        if result['status'] != 'COMPLETED' and diagnostic.is_file():
            result['recovery'] = read_object(diagnostic)[1]
        return result

    def launch(self, job_id):
        record = self.status(job_id)
        if record['status'] not in ('QUEUED', 'WAITING_REVIEWS', 'RUNNING'):
            return record
        self.start_dispatcher()
        return record

    def start_dispatcher(self):
        # Start only this package's worker; no shell or job-supplied executable.
        log = no_links(self.state_dir / 'dispatcher.log')
        with log.open('ab') as output:
            options = {'stdin': subprocess.DEVNULL, 'stdout': output, 'stderr': output,
                       'cwd': str(self.state_dir), 'close_fds': True}
            if os.name == 'nt':
                options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                options['start_new_session'] = True
            subprocess.Popen([sys.executable, '-I', '-B', '-m', 'universal_hmi.cli', 'dispatch-jobs',
                              '--policy', str(self.policy.path), '--state', str(self.state_dir)], **options)

    def supervise(self, job_id):
        """Fixed child process with a hard wall-time bound, including long parser calls."""
        current = self.status(job_id)
        if current['status'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
            return current
        remaining = max(1, self.policy.data['max_seconds'] - current['active_seconds'])
        if current['publication_sha256']:
            remaining = 60  # Reconcile already pinned bytes only.
        output_path = no_links(self.state_dir / (job_id + '.execution.log'))
        with output_path.open('ab') as log:
            options = {'stdin':subprocess.DEVNULL,'stdout':log,'stderr':log,'cwd':str(self.state_dir)}
            if os.name == 'nt': options['creationflags'] = subprocess.CREATE_NO_WINDOW
            child = subprocess.Popen([sys.executable,'-I','-B','-m','universal_hmi.cli','worker-job',
                '--policy',str(self.policy.path),'--state',str(self.state_dir),'--job-id',job_id], **options)
            try:
                child.wait(timeout=remaining + 2)
            except subprocess.TimeoutExpired:
                child.kill();child.wait(timeout=10)
                self.store.enforce_budget(job_id)
        return self.status(job_id)

    def dispatch(self, *, idle_seconds=86400, poll_seconds=2):
        """Restartable queue consumer. Review file changes automatically resume waiting jobs."""
        idle_since = time.monotonic()
        while time.monotonic() - idle_since < idle_seconds:
            pending = self.store.pending()
            if not pending:
                # A dead child can leave an unexpired lease. Stay to reclaim it.
                if not self.store.has_unfinished():
                    return {'status':'DISPATCH_IDLE'}
                time.sleep(poll_seconds)
                continue
            progressed = False
            for record in pending:
                job_id = record['job_id']
                folder = relative_file(self.policy.reviews_root,job_id)
                if record['status']=='WAITING_REVIEWS':
                    missing = record['details'].get('missing_review')
                    if missing in TaskPolicy.ROLES and not no_links(folder / (missing+'.json')).is_file():
                        continue
                result = self.supervise(job_id)
                if result['status'] != record['status']:
                    progressed = True
            if progressed:idle_since=time.monotonic()
            time.sleep(poll_seconds)
        return {'status':'DISPATCH_IDLE_TIMEOUT','pending_jobs':len(self.store.pending())}

    def _reviews(self, job_id, subject, candidate=None):
        reports = {}
        previous = None
        roles = TaskPolicy.ROLES if candidate else TaskPolicy.ROLES[:3]
        for role in roles:
            target = candidate if role == 'technical_native' else subject
            chain = previous if role in ('aesthetic_second', 'technical_native') else None
            report = self.policy.review(job_id, role, target, chain)
            if report is None:
                return reports, role
            reports[role] = report
            previous = report['sha256']
        return reports, None

    def run(self, job_id):
        owner = uuid.uuid4().hex
        if not self.store.claim(job_id, owner, lease_seconds=60):
            return self.status(job_id)
        stopped = threading.Event()
        lost = []

        def keepalive():
            while not stopped.wait(10):
                try:
                    self.store.heartbeat(job_id, owner)
                except Exception as exc:
                    lost.append(exc); return
        thread = threading.Thread(target=keepalive, daemon=True); thread.start()
        started = time.monotonic()

        def live():
            if lost:
                raise HmiError('JOB_LEASE', 'Worker lost its lease')
            current = self.status(job_id)
            if current['status'] != 'RUNNING' or current['owner'] != owner or current['lease_expires_at'] <= time.time():
                raise HmiError('JOB_CANCELLED', 'Job is cancelled or owned by another worker')
            if current['active_seconds'] > self.policy.data['max_seconds']:
                raise HmiError('JOB_TIMEOUT', 'Job execution budget exhausted')
            self.policy.fresh()

        try:
            payload = self.store.payload(job_id)
            if payload['policy_sha256'] != self.policy.sha256:
                raise HmiError('JOB_POLICY_CHANGED', 'Job belongs to another task policy')
            job = payload['job']
            final = relative_file(self.policy.output_root, job_id)
            intent = self.store.publication_intent(job_id)
            if intent:
                # Resolve a pinned publication only; never regenerate under an old intent.
                choices = [final] if final.exists() else list(self.policy.output_root.glob(f'.staging-{job_id}-*'))
                matching = [p for p in choices if p.is_dir() and (p / 'manifest.json').is_file()
                            and digest((p / 'manifest.json').read_bytes()) == intent]
                if len(matching) != 1:
                    raise HmiError('JOB_RECOVERY', 'Pinned delivery absent or ambiguous; preserve evidence')
                staged = matching[0]
                result = self._verify_package(job_id, staged)
                def recover():
                    self.policy.fresh()
                    self._verify_package(job_id, staged, trusted=(intent, payload))
                    if staged != final:
                        publish_directory(staged, final)
                    return dict(result, path=str(final))
                return self.store.publish(job_id, owner, intent, recover)
            if final.exists():
                raise HmiError('JOB_RESULT_CHANGED', 'Unpinned delivery directory is forbidden')
            service, sid, receipt, checked, previews, subject = self._plan(job)
            live()
            work_rel = f'.headless/{job_id}/{owner}'
            work = relative_file(self.policy.workspace, work_rel)
            work.mkdir(parents=True, exist_ok=False)
            for name, html in previews.items():
                (work / f'preview-{name}.html').write_bytes(html.encode('utf-8'))
            reports, missing = self._reviews(job_id, subject)
            request = {'job_id': job_id, 'subject_sha256': subject, 'policy_sha256': self.policy.sha256,
                       'plan': receipt, 'validation': checked, 'work_path': str(work),
                       'previews': [f'preview-{n}.html' for n in previews], 'missing_review': missing,
                       'preview_sha256': {f'preview-{n}.html':digest(html.encode('utf-8')) for n,html in previews.items()},
                       'review_order': list(TaskPolicy.ROLES)}
            write_json(self.state_dir / f'{job_id}.review-request.json', request)
            if missing:
                self.store.transition(job_id, owner, 'WAITING_REVIEWS', request)
                return self.status(job_id)
            review_pins = {k: v['sha256'] for k, v in reports.items()}

            def authorize(session, plan, approval):
                live()
                if approval.get('policy_sha256') != self.policy.sha256 or approval.get('job_id') != job_id:
                    raise HmiError('JOB_AUTHORITY', 'Approval is not bound to this trusted job')
                self.policy.authorize_plan(plan['operations'])
                current, absent = self._reviews(job_id, subject)
                if absent or {k: v['sha256'] for k, v in current.items()} != review_pins:
                    raise HmiError('JOB_REVIEW_CHANGED', 'Reviewed intent changed before save')
            service.task_authorizer = authorize
            approval = {k: v for k, v in receipt.items() if k.endswith('_sha256')}
            approval.update(approved=True, authority='task_start', policy_sha256=self.policy.sha256, job_id=job_id)
            write_json(work / 'authority.json', approval)
            applied = service.apply_plan(sid, receipt['plan_id'], work_rel + '/authority.json')
            native = service.save_as(sid, work_rel + '/project.dps')
            difference = service.diff(sid)
            live()
            candidate_subject = digest(canonical({'subject_sha256': subject,
                'candidate_sha256': native['sha256'], 'diff': difference}))
            reports, missing = self._reviews(job_id, subject, candidate_subject)
            request.update(candidate_subject_sha256=candidate_subject, candidate_sha256=native['sha256'],
                           missing_review=missing, diff=difference)
            write_json(work / 'checks.json', {'validation': checked, 'applied': applied, 'diff': difference})
            write_json(self.state_dir / f'{job_id}.review-request.json', request)
            if missing:
                self.store.transition(job_id, owner, 'WAITING_REVIEWS', request)
                return self.status(job_id)
            stage = relative_file(self.policy.output_root, f'.staging-{job_id}-{owner}')
            stage.mkdir(exist_ok=False)
            native_bytes = no_links(work / 'project.dps').read_bytes()
            if digest(native_bytes) != native['sha256']:
                raise HmiError('JOB_RESULT_CHANGED', 'Native candidate changed after validation')
            contents = {'project.dps':native_bytes,
                        **{f'preview-{name}.html':html.encode('utf-8') for name,html in previews.items()}}
            for name, raw in contents.items():
                with (stage / name).open('xb') as dest:
                    dest.write(raw);dest.flush();os.fsync(dest.fileno())
            write_json(stage / 'checks.json', {'validation': checked, 'applied': applied, 'diff': difference})
            write_json(stage / 'reviews.json', reports)
            write_json(stage / 'design.json', job['design'])
            write_json(stage / 'bindings.json', {'tags': job['design'].get('tags', []),
                                               'operations': receipt['operations']})
            entries = {p.name: {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}
                       for p in stage.iterdir() if p.is_file()}
            if sum(p['bytes'] for p in entries.values()) > self.policy.data['max_output_bytes']:
                raise HmiError('JOB_SIZE', 'Delivery exceeds task budget')
            manifest = {'schema_version': 1, 'job_id': job_id, 'job_sha256': digest(canonical(payload)),
                        'policy_sha256': self.policy.sha256, 'subject_sha256': subject,
                        'candidate_subject_sha256': candidate_subject, 'files': entries,
                        'status': 'OFFLINE_DELIVERY_COMPLETE', 'vendor': 'NOT_RUN',
                        'native_visual': 'NOT_RUN', 'physical': 'NOT_RUN'}
            write_json(stage / 'manifest.json', manifest)
            write_json(stage / 'COMPLETE.json', {'manifest_sha256': digest((stage / 'manifest.json').read_bytes())})
            manifest_sha = digest((stage / 'manifest.json').read_bytes())
            live()
            self._verify_package(job_id, stage, trusted=(manifest_sha,payload))
            self.store.pin_publication(job_id, owner, manifest_sha)
            result = self._verify_package(job_id, stage)
            def publish():
                self.policy.fresh()
                self._verify_package(job_id, stage, trusted=(manifest_sha,payload))
                publish_directory(stage, final)
                return dict(result, path=str(final))
            return self.store.publish(job_id, owner, manifest_sha, publish)
        except Exception as exc:
            error = exc.as_dict() if isinstance(exc, HmiError) else {'code': 'JOB_IO', 'message': str(exc)}
            current = self.status(job_id)
            if self.store.publication_intent(job_id):
                write_json(self.state_dir / (job_id+'.recovery.json'),
                           {'code':'RECOVERY_BLOCKED','error':error,'action':'Reconcile pinned artifact; never regenerate or self-approve'})
            elif current['status'] == 'RUNNING' and current['owner'] == owner:
                self.store.transition(job_id, owner, 'FAILED', error)
            return self.status(job_id)
        finally:
            stopped.set(); thread.join(timeout=2)

    def _verify_package(self, job_id, root, *, trusted=None):
        no_links(root)
        intent,payload = trusted if trusted else (self.store.publication_intent(job_id),self.store.payload(job_id))
        raw, manifest = read_object(root / 'manifest.json')
        _, complete = read_object(root / 'COMPLETE.json')
        if (intent != digest(raw)
                or complete != {'manifest_sha256': digest(raw)} or manifest.get('job_id') != job_id
                or manifest.get('policy_sha256') != self.policy.sha256
                or manifest.get('job_sha256') != digest(canonical(payload))):
            raise HmiError('JOB_RESULT_CHANGED', 'Completion manifest does not match this job')
        expected = manifest.get('files')
        if not isinstance(expected, dict) or set(expected) != DELIVERY_FILES or set(p.name for p in root.iterdir()) != DELIVERY_FILES | {'manifest.json', 'COMPLETE.json'}:
            raise HmiError('JOB_RESULT_CHANGED', 'Delivery file set changed')
        for name, pin in expected.items():
            p = relative_file(root, name, exists=True)
            if not p.is_file() or pin != {'sha256': digest(p.read_bytes()), 'bytes': p.stat().st_size}:
                raise HmiError('JOB_RESULT_CHANGED', 'Delivery content changed', path=name)
        difference = read_object(root / 'checks.json')[1]['diff']
        candidate = digest(canonical({'subject_sha256': manifest['subject_sha256'],
            'candidate_sha256': digest((root / 'project.dps').read_bytes()), 'diff': difference}))
        if candidate != manifest['candidate_subject_sha256']:
            raise HmiError('JOB_RESULT_CHANGED', 'Native file does not match reviewed candidate')
        reports, missing = self._reviews(job_id, manifest['subject_sha256'], manifest['candidate_subject_sha256'])
        if missing or read_object(root / 'reviews.json')[1] != reports:
            raise HmiError('JOB_REVIEW_CHANGED', 'Final reviews absent or changed')
        return {'path': str(root), 'manifest_sha256': digest(raw), 'status': 'OFFLINE_DELIVERY_COMPLETE',
                'vendor': 'NOT_RUN', 'native_visual': 'NOT_RUN', 'physical': 'NOT_RUN'}

    def result(self, job_id):
        record = self.status(job_id)
        if record['status'] != 'COMPLETED':
            raise HmiError('JOB_NOT_COMPLETE', 'No complete delivery exists', status=record['status'])
        result = self._verify_package(job_id, relative_file(self.policy.output_root, job_id, exists=True))
        if result['manifest_sha256'] != record['details'].get('manifest_sha256'):
            raise HmiError('JOB_RESULT_CHANGED', 'Published manifest changed')
        return result
