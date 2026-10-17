# SPDX-License-Identifier: Apache-2.0
"""Isolated file workspace, immutable proposals and explicit local application."""
from copy import deepcopy
from pathlib import Path
import re

from .errors import AgentError, digest, require
from .native import LIMIT, Project, layout_digest, restore_spans
from .operations import canonical, compile_changes, address_inventory, validate_references, whole
from .resources import embedded_xml, resource_frames, validate_reviewed_resources, flat_dib


def sha(value, label='sha256'):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'HASH', 'A lowercase complete SHA-256 is required', field=label)
    return value


def profile_check(project, profile):
    require(isinstance(profile, dict) and profile.get('schema_version') == 1 and type(profile['schema_version']) is int
            and profile.get('family') == 'diascreen-dop100', 'PROFILE', 'Explicit DIAScreen/DOP-100 schema1 profile required')
    panel = profile.get('panel', {})
    for key, native in (('width', 'PanelResWidth'), ('height', 'PanelResHeight')):
        require(type(panel.get(key)) is int and 1 <= panel[key] <= 8192 and panel[key] == project.index.number(project.app, native),
                'PROFILE_PANEL', 'Profile and native panel geometry differ', field=key)
    require(project.index.scalar(project.app, 'PanelSeries', '').startswith('DOP-100'), 'PROFILE_FAMILY', 'Native panel series is not DOP-100')
    versions = profile.get('application_versions')
    actual = [project.index.scalar(project.app, key, '') for key in ('Version', 'ApplicationVersion', 'NewVersion')]
    require(isinstance(versions, list) and versions and any(actual)
            and all(v in versions for v in actual if v), 'PROFILE_VERSION', 'Native application versions are not explicitly qualified')
    require(isinstance(profile.get('link'), str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', profile['link']), 'PROFILE_LINK', 'Explicit symbol link required')
    whole(profile.get('station'), 'station', 0, 65535)
    if 'model_name' in profile:
        require(str(profile['model_name']) == project.index.scalar(project.app, 'ModelName'), 'PROFILE_MODEL', 'Model identity differs')
    if 'reviewed_resources' in profile:
        validate_reviewed_resources(project, profile['reviewed_resources'])


class Session:
    def __init__(self, workspace, *, allow_write=False, read_roots=()):
        self.workspace = Path(workspace).resolve(strict=True)
        require(self.workspace.is_dir(), 'WORKSPACE', 'Workspace must be an existing directory')
        self.read_roots = [self.workspace, *(Path(p).resolve(strict=True) for p in read_roots)]
        require(all(p.is_dir() for p in self.read_roots), 'READ_ROOT', 'Read roots must be existing directories')
        self.allow_write = allow_write is True
        self.source_path = None
        self.source = self.current = None
        self.profile = self.current_profile = None
        self.profile_sha256 = None
        self.current_profile_sha256 = None
        self.donors = {}
        self.plans = {}
        self.applied = []
        self.inspected_sha = None

    def _path(self, value, *, output=False):
        require(isinstance(value, str) and value and '\0' not in value, 'PATH', 'A file path is required')
        supplied = Path(value)
        path = supplied if supplied.is_absolute() else self.workspace / supplied
        resolved = path.resolve(strict=False)
        roots = [self.workspace] if output else self.read_roots
        require(any(resolved.is_relative_to(root) for root in roots), 'PATH_SCOPE', 'Path escapes the explicit workspace/read roots')
        # Reject symlink/reparse links on the supplied path, including an existing leaf.
        for part in (path, *path.parents):
            require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()), 'PATH_LINK', 'Symlink/junction paths are not file-workspace inputs')
        if output:
            require(resolved.parent.is_dir() and not resolved.exists(), 'OUTPUT_EXISTS', 'Output must be a new file in an existing workspace directory')
        else:
            require(resolved.is_file(), 'INPUT', 'Input file is absent')
        return resolved

    def _read(self, path, limit=LIMIT):
        require(path.stat().st_size <= limit, 'INPUT_LIMIT', 'Input exceeds the bounded file profile')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
        require(len(data) <= limit, 'INPUT_LIMIT', 'Input grew beyond the bounded file profile')
        return data

    def _loaded(self):
        require(self.current is not None, 'NO_PROJECT', 'Open a source project first')
        require(digest(self._read(self.source_path)) == digest(self.source), 'SOURCE_DRIFT', 'Read-only source changed after opening')
        require(digest(canonical(self.profile)) == self.profile_sha256, 'PROFILE_DRIFT', 'Pinned profile changed')
        require(digest(canonical(self.current_profile)) == self.current_profile_sha256, 'PROFILE_DRIFT', 'Derived candidate profile changed outside an approved plan')

    def _project(self):
        self._loaded()
        q = Project(self.current)
        if self.current_profile.get('reviewed_resources') is not None:
            q.reviewed_resources = self.current_profile['reviewed_resources']
        return q

    def capabilities(self):
        return {'family': 'diascreen-dop100', 'schema_version': 1, 'transport': 'stdio',
                'write_enabled': self.allow_write, 'source_overwrite': False, 'save_new_only': True,
                'common_tools': ['open_project', 'capabilities', 'inspect', 'plan_changes', 'preview', 'validate', 'apply_plan', 'save_as', 'diff'],
                'operations': ['set_property', 'set_text', 'rebind', 'numeric', 'button_behavior', 'navigation',
                               'delete_element', 'reorder_element', 'clone_element', 'clone_screen', 'delete_screen',
                               'default_screen', 'replace_xml', 'flat_background', 'clear_macro', 'patch_macro_operand', 'donor_macro'],
                'excluded': ['GUI', 'IDE', 'PLC', 'network target', 'DOP-B/DPS', 'vendor compilation', 'overwrite_source', 'reload_editor'],
                'scope': 'SOURCE_QUALIFIED_OFFLINE_ONLY', 'picture_bank_write': 'DISCOVERED_UNQUALIFIED',
                'alarm_history': 'DISCOVERED_UNQUALIFIED', 'runtime_heartbeat': 'ROLLED_BACK_NOT_DEFAULT',
                'inventory_coverage': 'INDEXED_OWNERS_ONLY; opaque resource macros are not enumerated',
                'authorization': 'allow-write AND approval_sha256==immutable plan_sha256; local caller consent, not human identity proof'}

    def open_project(self, path, source_sha256, profile, profile_sha256):
        sha(source_sha256, 'source_sha256'); sha(profile_sha256, 'profile_sha256')
        require(isinstance(profile, dict) and digest(canonical(profile)) == profile_sha256, 'PROFILE_HASH', 'Profile hash differs from its canonical JSON')
        source_path = self._path(path)
        data = self._read(source_path)
        require(digest(data) == source_sha256, 'SOURCE_HASH', 'Source bytes differ from the explicit identity')
        if self.current is not None:
            same = source_path == self.source_path and source_sha256 == digest(self.source) and profile_sha256 == self.profile_sha256
            require(same or (not self.plans and not self.applied), 'PENDING_WORK', 'Rollback/discard explicitly before opening another project')
            if same:
                self._loaded()
                return {'source_sha256': source_sha256, 'candidate_sha256': digest(self.current), 'reused': True}
        q = Project(data)
        profile_check(q, profile)
        self.source_path, self.source, self.current = source_path, data, data
        self.profile = deepcopy(profile); self.current_profile = deepcopy(profile)
        self.profile_sha256 = profile_sha256
        self.current_profile_sha256 = profile_sha256
        self.donors.clear(); self.plans.clear(); self.applied.clear(); self.inspected_sha = None
        return {'source_sha256': source_sha256, 'candidate_sha256': source_sha256, 'profile_sha256': profile_sha256,
                'indexed_layout_sha256': layout_digest(q), 'inspection_required': True,
                'coverage': 'INDEXED_ONLY', 'stop_reason': q.index.stop_reason}

    def inspect(self, view='project', page_id=None, element_id=None, query=None, sort='layer'):
        require(isinstance(sort, str) and sort in ('layer', 'coordinate')
                and (sort == 'layer' or view in ('layout', 'text')),
                'INSPECT_SORT', 'Coordinate sorting is supported only for layout/text inspection')
        q = self._project()
        self.inspected_sha = digest(self.current)
        if view == 'project':
            return {'metadata': q.metadata(), 'source_sha256': digest(self.source), 'candidate_sha256': digest(self.current),
                    'profile_sha256': self.profile_sha256, 'indexed_layout_sha256': layout_digest(q),
                    'page_count_indexed': len(q.pages), 'element_count_indexed': sum(len(p.elements) for p in q.pages),
                    'indexed_bytes': q.index.tail_start, 'opaque_bytes': len(q.file.payload) - q.index.tail_start,
                    'unqualified_records': q.index.unqualified_records, 'stop_reason': q.index.stop_reason,
                    'coverage': 'INDEXED_ONLY; source review is required before writing; no total vendor-file coverage claim'}
        if view == 'design':
            from .contracts import design_ledger
            return design_ledger(q)
        if view == 'screens':
            return [{'page_id': p.page_id, 'name': q.index.text(p.section, 'wTextLen', ''), 'elements': len(p.elements),
                     'PictureOffset': q.index.scalar(p.section, 'PictureOffset', '')} for p in q.pages]
        if view in ('layout', 'element', 'find', 'text'):
            pages = q.pages if page_id is None else [q.page(whole(page_id, 'page_id'))]
            rows = []
            for p in pages:
                for layer_index, e in enumerate(p.elements):
                    eid = q.index.number(e.section, 'nPartsID')
                    if element_id is not None and eid != whole(element_id, 'element_id'):
                        continue
                    row = {'page_id': p.page_id, 'element_id': eid, 'layer_index': layer_index,
                           'name': q.index.text(e.section, 'wDescTextLen0', ''),
                           'type': [q.index.number(e.section, 'Type'), q.index.number(e.section, 'SubType')],
                           'rect': {k: q.index.number(e.section, k) for k in ('X', 'Y', 'Width', 'Height')},
                           'states': [{'value': q.index.number(s, 'Value'), 'text': q.index.text(s, 'wTextLen0', '')} for s in e.states]}
                    if view == 'find':
                        require(isinstance(query, str) and query, 'QUERY', 'Nonempty exact search text required')
                        if query.casefold() not in str(row).casefold():
                            continue
                    rows.append(row)
            if sort == 'coordinate':
                page_order = {p.page_id: i for i, p in enumerate(pages)}
                rows = sorted(rows, key=lambda row: (page_order[row['page_id']], row['rect']['Y'],
                                                    row['rect']['X'], row['layer_index']))
            if view == 'element':
                require(page_id is not None and element_id is not None and len(rows) == 1, 'ELEMENT_ID', 'Exact page and element identity required')
                return rows[0]
            if view == 'text':
                return '\n'.join(f"page={r['page_id']} id={r['element_id']} {r['rect']} {r['name']} " + ' | '.join(s['text'] for s in r['states']) for r in rows)
            return rows
        if view == 'addresses':
            return {'coverage': 'INDEXED_OWNERS_ONLY', 'rows': address_inventory(q)}
        if view == 'macros':
            from .macros import parse_macro
            return {'coverage': 'COUNTED_INDEXED_SLOTS_ONLY; opaque SubMacro/global resources remain unqualified',
                    'rows': [{'section_index': n, 'slot': t.key, 'sha256': digest(t.blob(q.file.payload)),
                              **parse_macro(t.blob(q.file.payload)).inspect(),
                              'instructions': [{'opcode': i.opcode.hex(), 'visible': i.fields[0].decode('latin-1'),
                                                'operands': [v.decode('latin-1') for v in i.fields[1:]]} for i in parse_macro(t.blob(q.file.payload)).instructions]}
                             for n, s in enumerate(q.index.sections) for t in s.tokens if t.kind == 'macro']}
        if view == 'symbols':
            from .symbols import parse_symbols
            _, data = embedded_xml(q)
            return {'xml_sha256': digest(data), 'symbols': parse_symbols(data).inventory()}
        if view == 'resources':
            results = []
            for section, key in (('Background', 'Size'), ('Picture', 'Size'), ('DIATag', 'size')):
                try:
                    results.append({'kind': section, 'frames': [{'start': f.start, 'bytes': f.blob_end - f.blob_start,
                                        'sha256': digest(q.file.payload[f.blob_start:f.blob_end])} for f in resource_frames(q, section, key)]})
                except AgentError as exc:
                    results.append({'kind': section, 'status': 'UNQUALIFIED', 'error': exc.as_dict()})
            return results
        if view == 'alarms':
            return {'presence_marker_only': b'[Alarm]\r\n' in q.file.payload[q.index.tail_start:],
                    'support': 'DISCOVERED_UNQUALIFIED', 'history_decoder': False,
                    'meaning': 'Marker may be inside opaque data; no alarm or healthy state is inferred. Current fault displays require a PLC interface contract.'}
        raise AgentError('INSPECT_VIEW', 'Unknown inspection view')

    def register_donor(self, donor_id, path, sha256):
        self._loaded()
        require(isinstance(donor_id, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', donor_id), 'DONOR_ID', 'Bounded neutral donor identity required')
        sha(sha256)
        data = self._read(self._path(path))
        require(digest(data) == sha256, 'DONOR_HASH', 'Donor hash differs')
        if donor_id in self.donors:
            require(digest(self.donors[donor_id].file.original) == sha256, 'DONOR_ID', 'Donor identity is immutable')
        donor = Project(data)
        profile_check(donor, {k: v for k, v in self.profile.items() if k != 'reviewed_resources'})
        require(not donor.index.unqualified_records and not donor.index.stop_reason.startswith(('unknown_',)), 'DONOR_INDEX', 'Donor ownership is unqualified')
        # A same-byte donor can reuse exact source-reviewed resources.
        if data == self.current and self.current_profile.get('reviewed_resources'):
            donor.reviewed_resources = self.current_profile['reviewed_resources']
        self.donors[donor_id] = donor
        return {'donor_id': donor_id, 'sha256': sha256, 'reuse': 'SOURCE_BOUND; resources/bindings/macros checked at clone'}

    def plan_changes(self, operations):
        self._loaded()
        require(self.inspected_sha == digest(self.current), 'INSPECTION_REQUIRED', 'Inspect the current candidate before planning')
        candidate, steps = compile_changes(self.current, deepcopy(operations), self.current_profile, self.donors)
        candidate_profile = deepcopy(self.current_profile)
        candidate_profile['indexed_layout_sha256'] = layout_digest(Project(candidate))
        if steps[-1]['reviewed_resources_after'] is not None:
            candidate_profile['reviewed_resources'] = steps[-1]['reviewed_resources_after']
        for op in operations:
            if op.get('op') == 'replace_xml':
                entry = candidate_profile.get('catalog_bindings', {}).get(str(op.get('xml_index', 0)))
                if entry is not None:
                    entry['xml_sha256'] = digest(op['xml'].encode('utf-8'))
            if op.get('op') == 'flat_background':
                color_hash = digest(flat_dib(self.profile['panel']['width'], self.profile['panel']['height'], op['rgb']))
                for pid in op['page_ids']:
                    candidate_profile.setdefault('background_sha256', {})[str(pid)] = color_hash
        record = {'source_sha256': digest(self.source), 'base_sha256': digest(self.current),
                  'base_profile_sha256': self.current_profile_sha256,
                  'candidate_sha256': digest(candidate), 'profile_sha256': self.profile_sha256,
                  'candidate_profile_sha256': digest(canonical(candidate_profile)),
                  'ledger_sha256': digest(canonical(steps)),
                  'operations': deepcopy(operations), 'donors': {k: digest(v.file.original) for k, v in sorted(self.donors.items())}}
        plan_sha = digest(canonical(record))
        self.plans[plan_sha] = {'record': record, 'candidate': candidate, 'profile': candidate_profile, 'steps': steps}
        return deepcopy({**record, 'plan_sha256': plan_sha, 'approval_sha256_required': plan_sha,
                'changes': [{'reason': e['reason'], 'source_start': e['source_start'], 'source_end': e['source_end'],
                             'old_bytes': len(bytes.fromhex(e['old_hex'])), 'new_bytes': len(bytes.fromhex(e['new_hex'])),
                             'old_sha256': digest(bytes.fromhex(e['old_hex'])), 'new_sha256': digest(bytes.fromhex(e['new_hex']))}
                            for step in steps for e in step['ledger']],
                'applied': False, 'preservation': 'FULL_PAYLOAD_INVERSE_AND_THUMBNAIL_PASS',
                'notice': 'Proposal only; vendor compile/runtime/pixel acceptance is not established'})

    def _plan_evidence(self, plan_sha256):
        sha(plan_sha256, 'plan_sha256')
        plan = self.plans.get(plan_sha256)
        require(plan is not None, 'PLAN_UNKNOWN', 'Plan is not in this process')
        record = plan['record']
        require(digest(canonical(record)) == plan_sha256 and digest(plan['candidate']) == record['candidate_sha256']
                and digest(canonical(plan['profile'])) == record['candidate_profile_sha256']
                and digest(canonical(plan['steps'])) == record['ledger_sha256'], 'PLAN_DRIFT', 'Immutable proposal bytes, profile, ledger or record changed')
        require(record['source_sha256'] == digest(self.source) and record['profile_sha256'] == self.profile_sha256,
                'PLAN_DRIFT', 'Proposal source/profile association changed')
        return plan

    def _checked_proposal(self, plan_sha256):
        self._loaded()
        plan = self._plan_evidence(plan_sha256)
        require(plan_sha256 not in self.applied, 'ALREADY_APPLIED', 'Use current inspection after applying a plan')
        record = plan['record']
        require(record['base_sha256'] == digest(self.current)
                and record['base_profile_sha256'] == self.current_profile_sha256
                and self.inspected_sha == digest(self.current),
                'STALE_PLAN', 'Plan base or required inspection is stale')
        require(record['donors'] == {k: digest(v.file.original) for k, v in sorted(self.donors.items())}, 'DONOR_DRIFT', 'Donor registry changed after planning')
        return plan

    def _review_project(self, plan_sha256):
        if plan_sha256 is None:
            self._loaded()
            data, profile = self.current, deepcopy(self.current_profile)
        else:
            plan = self._checked_proposal(plan_sha256)
            data, profile = plan['candidate'], deepcopy(plan['profile'])
        q = Project(data)
        if profile.get('reviewed_resources') is not None:
            q.reviewed_resources = profile['reviewed_resources']
        identity = {'view': 'current' if plan_sha256 is None else 'proposal', 'plan_sha256': plan_sha256,
                    'source_sha256': digest(self.source), 'candidate_sha256': digest(data),
                    'candidate_profile_sha256': digest(canonical(profile))}
        return q, profile, identity

    def apply_plan(self, plan_sha256, approval_sha256):
        self._loaded(); sha(plan_sha256); sha(approval_sha256, 'approval_sha256')
        require(self.allow_write, 'WRITE_DISABLED', 'Restart this isolated process with --allow-write to apply a reviewed local plan')
        require(approval_sha256 == plan_sha256, 'APPROVAL', 'Explicit approval must name the exact immutable plan')
        plan = self._checked_proposal(plan_sha256)
        record = plan['record']
        self.current, self.current_profile = plan['candidate'], deepcopy(plan['profile'])
        self.current_profile_sha256 = record['candidate_profile_sha256']
        self.applied.append(plan_sha256); self.inspected_sha = None
        return {'applied': True, 'plan_sha256': plan_sha256, 'candidate_sha256': digest(self.current), 'saved': False}

    def pending_changes(self):
        self._loaded()
        return {'plans': [{'plan_sha256': k, 'candidate_sha256': v['record']['candidate_sha256'], 'applied': k in self.applied}
                          for k, v in self.plans.items()], 'unsaved_candidate': self.current != self.source}

    def diff(self):
        self._loaded()
        return {'source_sha256': digest(self.source), 'candidate_sha256': digest(self.current),
                'applied': [{'plan_sha256': key, 'operations': deepcopy(self.plans[key]['record']['operations']),
                             'changes': [{'reason': e['reason'], 'source_start': e['source_start'], 'source_end': e['source_end'],
                                          'old_bytes': len(bytes.fromhex(e['old_hex'])), 'new_bytes': len(bytes.fromhex(e['new_hex'])),
                                          'old_sha256': digest(bytes.fromhex(e['old_hex'])), 'new_sha256': digest(bytes.fromhex(e['new_hex']))}
                                         for step in self.plans[key]['steps'] for e in step['ledger']]}
                            for key in self.applied]}

    def validate(self, plan_sha256=None):
        q, profile, identity = self._review_project(plan_sha256)
        errors = []
        try:
            validate_references(q); profile_check(q, profile)
            for p in q.pages:
                for e in p.elements:
                    from .operations import rect
                    rect(q, e, {}, profile)
        except AgentError as exc:
            errors.append(exc.as_dict())
        restored = q.file.payload
        chain = [*self.applied, *([] if plan_sha256 is None else [plan_sha256])]
        if chain:
            require(identity['candidate_sha256'] == self._plan_evidence(chain[-1])['record']['candidate_sha256'],
                    'PLAN_DRIFT', 'Selected candidate differs from its plan evidence')
        for key in reversed(chain):
            for step in reversed(self._plan_evidence(key)['steps']):
                require(digest(restored) == step['output_payload_sha256'], 'INVERSE', 'Unexpected candidate payload')
                restored = restore_spans(restored, step['ledger'])
        require(restored == Project(self.source).file.payload and q.file.thumbnail == Project(self.source).file.thumbnail,
                'PRESERVATION', 'Whole-payload inverse or thumbnail check failed')
        return {'status': 'OFFLINE_STRUCTURAL_PASS' if not errors else 'FAIL', 'errors': errors,
                'preservation': 'PASS', 'vendor_compile': 'NOT_RUN', 'pixel_fidelity': 'NOT_ESTABLISHED',
                'runtime': 'NOT_RUN', 'font_fit': 'PREVIEW_SEPARATE; requires pinned font metrics',
                **identity}

    def preview(self, page_id=None, values=None, gallery=False, plan_sha256=None):
        from .preview import render_preview, render_gallery
        q, profile, identity = self._review_project(plan_sha256)
        if page_id is not None:
            profile['page_id'] = whole(page_id, 'page_id')
        fonts = {}
        for name, descriptor in profile.get('fonts', {}).items():
            require(isinstance(descriptor, dict) and isinstance(descriptor.get('path'), str)
                    and not Path(descriptor['path']).is_absolute(), 'FONT_PATH', 'Font path must be workspace-relative')
            data = self._read(self._path(descriptor['path']), 32 * 1024 * 1024)
            require(digest(data) == sha(descriptor.get('sha256')), 'FONT_HASH', 'Pinned font changed')
            fonts[name] = data
        require(type(gallery) is bool, 'GALLERY', 'Gallery flag must be boolean')
        result = render_gallery(q, profile, fonts) if gallery else render_preview(q, profile, values, fonts)
        return {**identity, 'synthetic_values': True, 'live': False, 'result': result}

    def save_as(self, path, candidate_sha256):
        self._loaded(); sha(candidate_sha256, 'candidate_sha256')
        require(self.allow_write and self.applied, 'WRITE_DISABLED', 'Apply an approved plan before saving a new candidate')
        require(candidate_sha256 == digest(self.current), 'CANDIDATE_HASH', 'Save identity differs from the current candidate')
        require(self.validate()['status'] == 'OFFLINE_STRUCTURAL_PASS', 'VALIDATION', 'Offline structural validation has unresolved errors')
        output = self._path(path, output=True)
        require(output != self.source_path, 'SOURCE_OVERWRITE', 'Source overwrite is excluded')
        with output.open('xb') as stream:
            stream.write(self.current)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        saved = self._read(output)
        require(saved == self.current and Project(saved).file.payload == Project(self.current).file.payload, 'SAVED_REREAD', 'Saved bytes/reread differ')
        self._loaded()
        return {'path': output.relative_to(self.workspace).as_posix(), 'sha256': digest(saved),
                'saved_reread': 'PASS', 'source_unchanged': True, 'vendor_compile': 'NOT_RUN'}

    def rollback(self):
        self._loaded()
        self.current = self.source; self.current_profile = deepcopy(self.profile)
        self.current_profile_sha256 = self.profile_sha256
        self.plans.clear(); self.applied.clear(); self.inspected_sha = None
        return {'candidate_sha256': digest(self.current), 'discarded_in_memory': True, 'saved_files_deleted': False}

    def inspect_compiled(self, path, artifact_sha256, source_sha256, candidate_sha256, receipt):
        from .macros import inspect_compiled
        self._loaded()
        require(source_sha256 == digest(self.source) and candidate_sha256 == digest(self.current), 'COMPILED_STALE', 'Compiled observation must identify this source and candidate')
        return inspect_compiled(self._read(self._path(path), 32 * 1024 * 1024), artifact_sha=artifact_sha256,
                                source_sha=source_sha256, candidate_sha=candidate_sha256, receipt=receipt)

    def evaluate_status(self, values):
        from .contracts import evaluate_status
        self._loaded()
        return evaluate_status(values, self.profile.get('interface_contract', {}))
