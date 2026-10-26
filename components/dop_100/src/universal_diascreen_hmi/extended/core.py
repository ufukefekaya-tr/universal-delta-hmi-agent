# SPDX-License-Identifier: Apache-2.0
"""Generic durable plans and saved-file recovery extracted without machine builders."""
from copy import deepcopy
from universal_diascreen_hmi.session import Session
from universal_diascreen_hmi.native import Project
from universal_diascreen_hmi.errors import AgentError,digest
from universal_diascreen_hmi.operations import qualified_xml
from universal_diascreen_hmi.symbols import validate_reference
from .common import *
from .file_ownership import immutable_read,worker_lease
from .catalog import TYPES,validate_catalog
from .register_contract import validate_register_contract
from .journal import Journal
from .worker import VendorWorker
class Service(Session):
    def __init__(self,workspace,*,allow_write=False,read_roots=()):
        no_links(workspace);super().__init__(workspace,allow_write=allow_write,read_roots=read_roots)
        self.journal=Journal(self.workspace);self.worker=VendorWorker(self.journal)
        class Engine:
            def engine(_):
                require(engine_identity()==self.journal.engine_sha256,'ENGINE_DRIFT','Source engine changed')
        self.project_creation=Engine()
    def capabilities(self):
        r=super().capabilities()
        r.update(plan_persistence=True,file_save_reconciliation=True,symbolic_types=list(TYPES),vendor_routes=self.worker.capabilities())
        return r
    def create_screen(self, donor_id, donor_page_id, new_page_id, name):
        return self.plan_changes([dict(op='clone_screen', donor_id=donor_id, donor_page_id=donor_page_id,
                                      new_page_id=new_page_id, name=name, content='frame')])
    def create_element(self, donor_id, donor_page_id, donor_element_id, page_id,
                       new_element_id, name, rect, retain_bindings, retain_macros):
        return self.plan_changes([dict(op='clone_element', donor_id=donor_id, donor_page_id=donor_page_id,
                                      donor_element_id=donor_element_id, page_id=page_id,
                                      new_element_id=new_element_id, name=name, rect=rect,
                                      retain_bindings=retain_bindings, retain_macros=retain_macros)])
    def plan_changes(self, operations):
        # Parent plan storage is checked before adding anything to in-memory state.
        previous = deepcopy(self.plans)
        proposal = super().plan_changes(operations)
        identity = proposal['plan_sha256']
        try:
            self.journal.save_plan(identity, self.plans[identity], self.applied[-1] if self.applied else None)
        except Exception:
            self.plans = previous
            raise
        return {**proposal, 'durable_plan': True, 'engine_sha256': self.journal.engine_sha256}
    def restore_plan(self, plan_sha256):
        self._loaded(); hash_value(plan_sha256)
        plan, parent = self.journal.load_plan(plan_sha256)
        record = plan['record']
        require(record['source_sha256'] == sha(self.source) and record['profile_sha256'] == self.profile_sha256
                and record['base_sha256'] == sha(self.current)
                and record['base_profile_sha256'] == self.current_profile_sha256,
                'PLAN_SOURCE', 'Durable plan belongs to another source/profile/base')
        require(parent == (self.applied[-1] if self.applied else None), 'PLAN_CHAIN', 'Durable plan parent differs')
        require(self.inspected_sha == sha(self.current), 'INSPECTION_REQUIRED', 'Inspect current source before restoring a plan')
        require(self.journal.find('apply:' + record['source_sha256'] + ':' + plan_sha256) is None,
                'REPLAY_OR_UNKNOWN', 'Applied/unknown operation must not be restored as a new request')
        require(record['donors'] == {key: sha(value.file.original) for key, value in sorted(self.donors.items())},
                'DONOR_DRIFT', 'Restore exact donor registry first')
        self.plans[plan_sha256] = plan
        return {'plan_sha256': plan_sha256, 'candidate_sha256': record['candidate_sha256'],
                'restored_proposal_only': True, 'applied': False, 'native_qualified': False}
    def restore_candidate(self, plan_sha256, approval_sha256):
        """Recover previously applied in-memory state; never re-execute an apply/save."""
        self._loaded(); hash_value(plan_sha256); hash_value(approval_sha256)
        require(self.allow_write, 'WRITE_DISABLED', '--allow-write required for candidate recovery')
        require(plan_sha256 == approval_sha256, 'APPROVAL', 'Exact last plan identity required')
        require(not self.plans and not self.applied and self.current == self.source,
                'PENDING_WORK', 'Candidate recovery requires a freshly inspected unchanged source session')
        require(self.inspected_sha == sha(self.source), 'INSPECTION_REQUIRED', 'Inspect original source before recovery')
        chain = []; seen = set(); identity = plan_sha256
        while identity is not None:
            require(identity not in seen and len(chain) < 1000, 'PLAN_CHAIN', 'Cyclic or excessively long recovery chain')
            seen.add(identity)
            plan, parent = self.journal.load_plan(identity)
            record = plan['record']
            operation = self.journal.find('apply:' + record['source_sha256'] + ':' + identity)
            require(operation is not None and operation['state'] == 'SUCCEEDED'
                    and operation['result'].get('effect') == 'IN_MEMORY_ONLY',
                    'REPLAY_OR_UNKNOWN', 'No completed local apply evidence for recovered plan')
            chain.append((identity, plan)); identity = parent
        candidate, profile_sha = self.source, self.profile_sha256
        donors = {key: sha(value.file.original) for key, value in sorted(self.donors.items())}
        for identity, plan in reversed(chain):
            record = plan['record']
            require(record['source_sha256'] == sha(self.source) and record['profile_sha256'] == self.profile_sha256
                    and record['base_sha256'] == sha(candidate) and record['base_profile_sha256'] == profile_sha
                    and record['donors'] == donors, 'PLAN_CHAIN', 'Source/profile/base/donor recovery chain differs')
            candidate, profile_sha = plan['candidate'], record['candidate_profile_sha256']
        previous = self.current, self.current_profile, self.current_profile_sha256, self.plans, self.applied, self.inspected_sha
        try:
            self.plans = {identity: plan for identity, plan in reversed(chain)}
            self.applied = [identity for identity, _ in reversed(chain)]
            self.current = candidate; self.current_profile = deepcopy(chain[0][1]['profile'])
            self.current_profile_sha256 = profile_sha; self.inspected_sha = None
            require(self.validate()['status'] == 'OFFLINE_STRUCTURAL_PASS', 'VALIDATION', 'Recovered candidate failed inverse/source validation')
        except BaseException:
            self.current, self.current_profile, self.current_profile_sha256, self.plans, self.applied, self.inspected_sha = previous
            raise
        return {'candidate_sha256': sha(self.current), 'recovered_plan_sha256': plan_sha256,
                'plans_restored': len(chain), 'disk_written': False, 'replayed_operations': 0, 'native_qualified': False}
    def apply_plan(self, plan_sha256, approval_sha256):
        self.project_creation.engine()
        self._loaded(); hash_value(plan_sha256); hash_value(approval_sha256)
        require(self.allow_write, 'WRITE_DISABLED', '--allow-write required')
        require(plan_sha256 == approval_sha256, 'APPROVAL', 'Exact immutable approval required')
        plan = self._checked_proposal(plan_sha256)
        require(self.validate(plan_sha256)['status'] == 'OFFLINE_STRUCTURAL_PASS', 'VALIDATION', 'Proposal validation failed')
        record = plan['record']
        identity = self.journal.reserve('apply:' + record['source_sha256'] + ':' + plan_sha256, 'apply_plan',
            {'source_sha256': record['source_sha256'], 'candidate_sha256': record['candidate_sha256'], 'plan_sha256': plan_sha256})
        self.journal.transition(identity, 'RUNNING')
        try:
            result = super().apply_plan(plan_sha256, approval_sha256)
        except Exception:
            self.journal.transition(identity, 'UNKNOWN_OUTCOME', {'reason': 'APPLY_INTERRUPTED_INSPECT_REQUIRED'})
            raise
        self.journal.transition(identity, 'SUCCEEDED', {'candidate_sha256': result['candidate_sha256'], 'effect': 'IN_MEMORY_ONLY'})
        return {**result, 'operation_id': identity, 'effect': 'IN_MEMORY_ONLY'}
    def save_as(self, path, candidate_sha256):
        with worker_lease(self.workspace):
            return self._save_as_owned(path,candidate_sha256)
    def _save_as_owned(self, path, candidate_sha256):
        self.project_creation.engine()
        self._loaded(); hash_value(candidate_sha256)
        require(self.allow_write and self.applied, 'WRITE_DISABLED', 'An applied exact plan and --allow-write required')
        require(candidate_sha256 == sha(self.current), 'CANDIDATE_HASH', 'Wrong save candidate')
        output = self._path(path, output=True)
        require(self.source_path.is_relative_to(self.workspace), 'RECOVERY_SOURCE_SCOPE',
                'Durable save requires an immutable source copy within workspace; external originals remain read-only inputs')
        relative = output.relative_to(self.workspace).as_posix()
        intent = {'path': relative, 'source_path': self.source_path.relative_to(self.workspace).as_posix(),
                  'source_sha256': sha(self.source), 'candidate_sha256': candidate_sha256,
                  'plan_sha256': self.applied[-1]}
        require(self.validate()['status'] == 'OFFLINE_STRUCTURAL_PASS', 'VALIDATION', 'Unresolved structural validation')
        with immutable_read(self.source_path) as (source,source_unchanged):
            require(sha(source) == intent['source_sha256'], 'SOURCE_DRIFT', 'Save source changed')
            identity = self.journal.reserve('save:' + relative, 'save_as', intent)
            self.journal.transition(identity, 'RUNNING')
            creating = True
            try:
                write_new(output,self.current)
                creating = False
                with immutable_read(output) as (saved,output_unchanged):
                    require(saved == self.current and Project(saved).file.payload == Project(self.current).file.payload,
                            'SAVED_REREAD','Saved native bytes/readback differ')
                    self.project_creation.engine();source_unchanged();output_unchanged()
                    result = dict(path=relative,sha256=sha(saved),candidate_sha256=sha(saved),
                        saved_reread='PASS',source_unchanged=True,vendor_compile='NOT_RUN',native_qualified=False)
                    self.journal.transition(identity, 'SUCCEEDED', result)
            except FileExistsError:
                self.journal.transition(identity, 'FAILED' if creating else 'UNKNOWN_OUTCOME',
                    {'reason': 'OUTPUT_EXISTS_NOT_OWNED' if creating else 'SAVE_INTERRUPTED_RECONCILE_REQUIRED'})
                raise
            except Exception:
                self.journal.transition(identity, 'UNKNOWN_OUTCOME', {'reason': 'SAVE_INTERRUPTED_RECONCILE_REQUIRED'})
                raise
        return {**result, 'operation_id': identity}
    def inspect_operation(self, operation_id):
        row = self.journal.inspect(operation_id)
        # Durable intents may contain local source paths. Expose only neutral identities.
        return {key: row[key] for key in ('operation_id', 'kind', 'state', 'result')}
    def reconcile_operation(self,operation_id):
        self.journal.reconcile_save(operation_id);return self.inspect_operation(operation_id)
    def import_symbol_catalog(self, xml, contract, contract_sha256, expected_xml_sha256, bindings):
        self._loaded(); hash_value(expected_xml_sha256)
        require(self.inspected_sha == sha(self.current), 'INSPECTION_REQUIRED', 'Inspect current candidate first')
        _, old = qualified_xml(self._project(), self.current_profile, 0)
        require(sha(old) == expected_xml_sha256, 'XML_HASH', 'Old catalog hash differs')
        catalog = validate_catalog(xml, contract, contract_sha256)
        require(isinstance(bindings, list) and len(bindings) <= 999, 'BINDINGS', 'Explicit bounded bindings required')
        declared = {catalog.resolve(row['path'])['path'] for row in contract['symbols']}
        seen = set(); ops = [dict(op='replace_xml', xml=xml, xml_index=0, expected_xml_sha256=expected_xml_sha256,
                                  operation_id='typed-import:' + contract_sha256)]
        q = self._project()
        for binding in bindings:
            require(isinstance(binding, dict) and set(binding) == {'page_id', 'element_id', 'field', 'expected_address', 'address'}
                    and binding['field'] in ('ReadVar', 'WriteVar'), 'BINDINGS', 'Exact read/write binding required')
            key = binding['page_id'], binding['element_id'], binding['field']
            require(key not in seen, 'BINDING_DUPLICATE', 'Duplicate field binding'); seen.add(key)
            symbol = validate_reference(binding['address'], binding['field'], catalog, self.current_profile['link'], self.current_profile['station'])['symbol']
            require(symbol['path'] in declared, 'CONTRACT_MISSING', 'Binding absent from typed contract')
            element = q.element(binding['page_id'], binding['element_id']); typ = q.index.number(element.section, 'Type')
            require((typ in (1, 2) and symbol['bits'] == 1) or (typ in (5, 6) and symbol['numeric_coercion_supported']),
                    'BINDING_TYPE', 'Object family and type differ')
            ops.append(dict(op='rebind', **deepcopy(binding)))
        proposal = self.plan_changes(ops)
        return {**proposal, 'typed_contract_sha256': contract_sha256, 'native_qualified': False,
                'scope': 'EXISTING_DIA_TAG_XML_ONLY', 'scales_applied_to_widgets': False}
    def verify_symbol_contract(self, contract, contract_sha256):
        _, xml = qualified_xml(self._project(), self.current_profile, 0)
        validate_catalog(xml.decode('utf-8'), contract, contract_sha256)
        return {'status': 'SYMBOL_METADATA_MATCH', 'count': len(contract['symbols']),
                'contract_sha256': contract_sha256, 'xml_sha256': sha(xml), 'candidate_sha256': sha(self.current),
                'scale_scope': 'CALLER_METADATA_ONLY', 'native_qualified': False, 'as228t_registers': False}
    def _vendor(self, operation, candidate_sha256):
        self._loaded(); hash_value(candidate_sha256)
        require(candidate_sha256 == sha(self.current), 'CANDIDATE_HASH', 'Vendor operation candidate differs')
        return self.worker.execute(operation, sha(self.source), candidate_sha256)
    def vendor_compile(self, candidate_sha256):
        return self._vendor('vendor_compile', candidate_sha256)
    def vendor_open_save_reopen(self, candidate_sha256):
        return self._vendor('vendor_open_save_reopen', candidate_sha256)
    def offline_simulator(self, candidate_sha256):
        return self._vendor('offline_simulator', candidate_sha256)
    def build_transfer_package(self, candidate_sha256):
        return self._vendor('build_transfer_package', candidate_sha256)
    def inspect_transfer_package(self, candidate_sha256):
        return self._vendor('inspect_transfer_package', candidate_sha256)
    def create_alarm_catalog(self, candidate_sha256):
        self._loaded(); require(candidate_sha256 == sha(self.current), 'CANDIDATE_HASH', 'Candidate differs')
        require(False, 'NOT_IMPLEMENTED', 'Vendor alarm examples require schema/ownership qualification before writing')
    def configure_native_service(self, family, candidate_sha256):
        self._loaded(); require(candidate_sha256 == sha(self.current), 'CANDIDATE_HASH', 'Candidate differs')
        require(family in ('recipe', 'trend', 'account', 'picture_resource'), 'SERVICE_FAMILY', 'Explicit native family required')
        require(False, 'NOT_IMPLEMENTED', 'Native service schema is not qualified')
    def validate_register_contract(self, contract, contract_sha256):
        return validate_register_contract(contract, contract_sha256)
    def import_tags(self,address_space,xml,contract,contract_sha256,expected_xml_sha256,bindings):
        require(address_space=='DIA_TAG_SYMBOLCONFIGURATION','ADDRESS_SPACE','Use plan_register_import for typed native register bindings')
        return self.import_symbol_catalog(xml,contract,contract_sha256,expected_xml_sha256,bindings)
