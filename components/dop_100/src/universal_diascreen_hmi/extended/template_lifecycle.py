# SPDX-License-Identifier: Apache-2.0
"""Durable, new-only qualified template copies. Never a vendor project constructor."""
import json
from .common import *
from .file_ownership import immutable_read, worker_lease
from .hmi4_bootstrap import Project, profile_check
from . import template_catalog as catalog


def init(service):
    with service.journal.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS template_plans (id TEXT PRIMARY KEY, record BLOB NOT NULL)')
    service.inspected_template_plans = set()


def exists(service, plan_id):
    with service.journal.connect() as db:
        return db.execute('SELECT 1 FROM template_plans WHERE id=?', (plan_id,)).fetchone() is not None


def source_check(service, record):
    binding = record.get('source_binding')
    if binding:
        with immutable_read(service._path(binding['path'])) as (raw, unchanged):
            require(sha(raw) == binding['sha256'], 'SOURCE_DRIFT', 'Blank transition source changed'); unchanged()
        require(raw == catalog.load(binding['template_id'])[0], 'TEMPLATE_TRANSITION', 'Source is no longer the exact registered blank')


def load(service, plan_id):
    service.project_creation.engine(); hash_value(plan_id)
    with service.journal.connect() as db:
        row = db.execute('SELECT record FROM template_plans WHERE id=?', (plan_id,)).fetchone()
    require(row is not None, 'PLAN_UNKNOWN', 'No template proposal with this identity')
    record = json.loads(row[0]); require(sha(canonical(record)) == plan_id, 'PLAN_DRIFT', 'Template proposal changed')
    require(record['engine_sha256'] == engine_identity(), 'ENGINE_DRIFT', 'Template proposal engine changed')
    raw, profile, info = catalog.require_pins(record['template_pins']); source_check(service, record)
    return record, raw, profile, info


def propose(service, template_id, output_path, seed_sha256, profile_sha256, catalog_sha256, engine_sha256, source_binding=None):
    service.project_creation.engine()
    raw, profile, info = catalog.load(template_id)
    require((seed_sha256, profile_sha256, catalog_sha256, engine_sha256) ==
            (info['seed_sha256'], info['profile_sha256'], info['catalog_sha256'], engine_identity()),
            'TEMPLATE_PIN', 'Inspect and explicitly pin the seed/profile/catalog/engine')
    require(isinstance(output_path,str) and output_path,'TEMPLATE_OUTPUT','Workspace-relative output path required')
    supplied=Path(output_path)
    require(not supplied.is_absolute() and ':' not in output_path and '\\' not in output_path
            and all(p not in ('','.','..') for p in output_path.split('/')),'TEMPLATE_OUTPUT','Normalized workspace-relative output required')
    output = no_links(service.workspace / supplied)
    require(output.suffix.lower() == '.dpa', 'TEMPLATE_OUTPUT', 'New workspace DPA required')
    require(service.current is None or source_binding is not None, 'PENDING_WORK', 'Creation needs an empty isolated session')
    record = dict(kind='qualified_template_copy', engine_sha256=engine_identity(),
                  template_pins={k: info[k] for k in ('template_id', 'seed_sha256', 'profile_sha256', 'catalog_sha256', 'review_sha256')},
                  path=output.relative_to(service.workspace).as_posix(), source_binding=source_binding)
    source_check(service, record); plan_id = sha(canonical(record))
    with service.journal.connect() as db:
        previous = db.execute('SELECT record FROM template_plans WHERE id=?', (plan_id,)).fetchone()
        require(previous is None or bytes(previous[0]) == canonical(record), 'PLAN_DRIFT', 'Template proposal collision')
        if previous is None:
            service._path(output_path,output=True)
            db.execute('INSERT INTO template_plans VALUES (?,?)', (plan_id, canonical(record)))
    return dict(plan_sha256=plan_id, approval_sha256_required=plan_id, candidate_sha256=sha(raw),
                candidate_profile_sha256=sha(canonical(profile)), applied=False,
                operation=service.journal.find('template:'+record['path']), **info)


def configure(service, candidate_sha256, from_template_id, target_template_id, output_path):
    service.checked(candidate_sha256, inspected=True)
    require(not service.applied and service.current == service.source and not service.plans,
            'TEMPLATE_TRANSITION', 'Only an unchanged registered blank can select another registered template')
    raw, profile, _ = catalog.load(from_template_id)
    require(service.current == raw and canonical(service.current_profile) == canonical(profile),
            'TEMPLATE_TRANSITION', 'An existing machine project cannot be converted')
    require({'from': from_template_id, 'to': target_template_id} in catalog.catalog()[1]['transitions'],
            'TEMPLATE_TRANSITION', 'Host did not register this blank-to-template relation')
    _, _, info = catalog.load(target_template_id)
    require('target_transition'in info['operations'],'TEMPLATE_QUALIFICATION','Target transition not qualified')
    require(service.source_path.is_relative_to(service.workspace),'TEMPLATE_TRANSITION','Stage exact blank in workspace first')
    binding = dict(path=service.source_path.relative_to(service.workspace).as_posix(), sha256=candidate_sha256, template_id=from_template_id)
    return propose(service, target_template_id, output_path, info['seed_sha256'], info['profile_sha256'], info['catalog_sha256'], engine_identity(), binding)


def inspect_plan(service, plan_id):
    record, raw, profile, info = load(service, plan_id)
    service.inspected_template_plans.add(plan_id)
    return dict(plan_sha256=plan_id, record=record, candidate_sha256=sha(raw), profile=profile,
                operation=service.journal.find('template:'+record['path']), **info)


def apply(service, plan_id, approval_sha256):
    require(service.allow_write, 'WRITE_DISABLED', '--allow-write required')
    require(plan_id == approval_sha256, 'APPROVAL', 'Exact template proposal approval required')
    require(plan_id in service.inspected_template_plans, 'INSPECTION_REQUIRED', 'Inspect this durable proposal before applying')
    with worker_lease(service.workspace):
        record, raw, profile, _ = load(service, plan_id)
        if service.current is not None:
            binding=record.get('source_binding')
            require(binding is not None,'PENDING_WORK','Creation proposal needs its original empty isolated session')
            service._loaded()
            _,source_profile,_=catalog.load(binding['template_id'])
            require(service.source_path==service.workspace/binding['path'] and service.current==service.source
                    and sha(service.current)==binding['sha256'] and not service.plans and not service.applied
                    and canonical(service.current_profile)==canonical(source_profile),
                    'TEMPLATE_TRANSITION','Transition source session changed after proposal')
        output = no_links(service._path(record['path'], output=True))
        operation = service.journal.reserve('template:'+record['path'], 'qualified_template_copy', dict(plan_sha256=plan_id))
        service.journal.transition(operation, 'RUNNING')
        creating = True
        try:
            write_new(output, raw); creating = False
            with immutable_read(output) as (saved, unchanged):
                require(saved == raw, 'SAVED_REREAD', 'Template copy bytes differ'); profile_check(Project(saved), profile)
                load(service, plan_id); unchanged()
                result = dict(path=record['path'], candidate_sha256=sha(saved), saved_reread='PASS',
                              byte_identical_seed=True, vendor_qualified=False, vendor_compile='NOT_RUN')
                service.journal.transition(operation, 'SUCCEEDED', result)
        except FileExistsError:
            service.journal.transition(operation, 'FAILED' if creating else 'UNKNOWN_OUTCOME', {'reason': 'OUTPUT_COLLISION_OR_INTERRUPTED_REREAD'}); raise
        except BaseException:
            service.journal.transition(operation, 'UNKNOWN_OUTCOME', {'reason': 'COPY_INTERRUPTED_INSPECT_REQUIRED'}); raise
    # The completed copy becomes the source of this isolated editing session.
    service.open_project(record['path'], sha(raw), profile, sha(canonical(profile)))
    return dict(**result, operation_id=operation)


def reconcile(service, operation_id):
    with worker_lease(service.workspace):
        operation = service.journal.inspect(operation_id)
        record, raw, profile, _ = load(service, operation['intent']['plan_sha256'])
        if operation['state'] in ('SUCCEEDED', 'FAILED', 'TIMED_OUT'):
            return attach_reconciled_source(service,operation_id,record,raw,profile)
        with service.journal.connect() as db:
            started = db.execute('SELECT 1 FROM events WHERE operation_id=? AND state=?', (operation_id, 'RUNNING')).fetchone()
        output = no_links(service.workspace / record['path'])
        if started and output.is_file():
            with immutable_read(output) as (saved, unchanged):
                if saved == raw:
                    profile_check(Project(saved), profile); load(service, operation['intent']['plan_sha256']); unchanged()
                    service.journal.transition(operation_id, 'SUCCEEDED', dict(reconciled=True, path=record['path'], candidate_sha256=sha(saved),
                        byte_identical_seed=True, saved_reread='PASS', vendor_qualified=False, vendor_compile='NOT_RUN'))
                    return attach_reconciled_source(service,operation_id,record,raw,profile)
        if operation['state'] != 'UNKNOWN_OUTCOME':
            service.journal.transition(operation_id, 'UNKNOWN_OUTCOME', {'reason': 'NO_EXACT_OWNED_COPY_EFFECT'})
        return service.inspect_operation(operation_id)


def attach_reconciled_source(service,operation_id,record,raw,profile):
    """Read-only disk recovery may attach the proven copy to an empty session."""
    result=service.inspect_operation(operation_id)
    if result['state']=='SUCCEEDED':
        if service.current is None:
            service.open_project(record['path'],sha(raw),profile,sha(canonical(profile)))
            result['session_source']='ATTACHED_VERIFIED_TEMPLATE_COPY'
        elif service.source_path==service.workspace/record['path']:
            result['session_source']='ALREADY_ATTACHED'
        else:result['session_source']='UNCHANGED_OTHER_SOURCE; open a new template recovery session'
    return result
