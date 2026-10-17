"""Isolated file sessions. No IDE, PLC, network or source overwrite operations."""
from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
import threading
import uuid

from .errors import HmiError
from .runtime_assets import profiles_root
from .model import canonical_hash
from .native import NativeAdapter, model_ids_match, canonical_model_id, _groups
from .native.numeric import verify_numeric_fields, fixed_decimal_contract
from .native.storage_conversion import storage_contract, verify_converted
from .native.resources import alarm_ir_operations, expected_alarm_tail, alarm_view_context
from .preview import render_preview
from .validation import validate_design
from .value_model import FIXED_MODEL, integer_digits


def byte_hash(data):
    return hashlib.sha256(data).hexdigest()


def _json_object(path, code):
    """Bound the actual read and reject ambiguous/nonstandard JSON metadata."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise HmiError(code, 'JSON objects cannot contain duplicate keys')
            result[key] = value
        return result
    def nonfinite(value):
        raise HmiError(code, 'JSON metadata cannot contain nonfinite constants')
    try:
        with path.open('rb') as file:
            raw = file.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise HmiError(code, 'JSON metadata exceeds its bounded size')
        obj = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=nonfinite)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise HmiError(code, 'Readable bounded UTF-8 JSON metadata is required') from exc
    if not isinstance(obj, dict):
        raise HmiError(code, 'JSON metadata must be an object')
    # Size alone cannot bound recursive copies/hashing of valid small JSON.
    # Walk iteratively before any consumer can deepcopy nested metadata.
    pending = [(obj, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 64 or nodes > 250000:
            raise HmiError(code, 'JSON metadata exceeds its bounded structural depth or node count')
        if isinstance(value, dict):
            pending.extend((item, depth+1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth+1) for item in value)
    return raw, obj


_UNIT_CONTEXT_FIELDS = frozenset({
    'UnitType', 'UnitSrc', 'UnitSrcVar', 'UnitDisplay', 'UnitDisplayVar',
    'UnitPercent', 'UnitPercent1Var', 'UnitPercent2Var', 'UnitCustom1Var_1',
    'UnitCustom2Var_1', 'BackupUnitSrc', 'BackupUnitDisplay', 'ConvertConstByUnit',
    'ShowUnit', 'UnitDirection', 'UnitFontSize0', 'UnitFontName0', 'UnitTextLen0',
    'UnitBold', 'UnitItalic', 'UnitUnderline', 'UnitFontColor'})

_ALARM_VIEW_KINDS = {'alarm_history': '1', 'alarm_table': '2', 'alarm_strip': '4'}


class FileService:
    """One workspace and read-only profile registry per server process.

    Native production remains fail-closed until a vendor-derived schema exists.
    Synthetic qualification exercises the transaction, not vendor compatibility.
    """

    def __init__(self, workspace, profiles_dir, *, task_authorizer=None):
        self.workspace = Path(workspace).resolve(strict=True)
        self.profiles_dir = Path(profiles_dir).resolve(strict=True)
        if not self.workspace.is_dir() or not self.profiles_dir.is_dir():
            raise HmiError("NOT_DIRECTORY", "Workspace and registry must be directories")
        self.task_authorizer = task_authorizer
        self.sessions = {}
        self.registry_lock = threading.RLock()

    def _path(self, relative, *, exists=False):
        if not isinstance(relative, str) or not relative or "\x00" in relative:
            raise HmiError("PATH", "An exact relative workspace path is required")
        raw = Path(relative)
        if raw.is_absolute() or ".." in raw.parts or ":" in relative:
            raise HmiError("PATH", "Absolute and traversing paths are forbidden")
        path = (self.workspace / raw).resolve(strict=exists)
        if not path.is_relative_to(self.workspace):
            raise HmiError("PATH", "Path escapes the selected workspace")
        # Refuse link/reparse indirection even if its target happens to be inside.
        current = self.workspace
        for part in raw.parts:
            current /= part
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
                raise HmiError("PATH_LINK", "Workspace paths must not traverse links")
        return path

    def _profile(self, identifier):
        if not isinstance(identifier, str) or not identifier or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identifier):
            raise HmiError("PROFILE_ID", "Profile ID must be a simple registry name")
        path = self.profiles_dir / (identifier + ".json")
        if path.is_symlink() or not path.resolve().is_relative_to(self.profiles_dir):
            raise HmiError("PROFILE_PATH", "Profile path must stay in registry")
        raw, profile = _json_object(path, 'PROFILE_JSON')
        self._validate_profile(profile, identifier)
        return path, raw, profile

    @staticmethod
    def _validate_profile(profile, identifier=None):
        """One typed gate for registry and auxiliary source profiles."""
        if not isinstance(profile, dict):
            raise HmiError('PROFILE_JSON', 'Profile metadata must be an object')
        profile_id = profile.get('id')
        if not isinstance(profile_id, str) or not profile_id or any(
                c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in profile_id):
            raise HmiError('PROFILE_ID', 'Profile ID must be a simple registry name')
        if identifier is not None and profile_id != identifier:
            raise HmiError("PROFILE_ID", "Registry filename and ID differ")
        if (profile.get('family') not in ('delta_diascreen', 'delta_dopsoft2')
                or not isinstance(profile.get('editor_version'), str) or not profile['editor_version']
                or any(c in profile['editor_version'] for c in '\r\n\0')
                or not isinstance(profile.get('resolution'), list) or len(profile['resolution']) != 2
                or any(type(v) is not int or not 0 < v <= 2147483647 for v in profile['resolution'])
                or not isinstance(profile.get('capabilities'), dict) or not isinstance(profile.get('native_schema'), dict)):
            raise HmiError('PROFILE_JSON', 'Profile target, resolution, capabilities and native mappings must be explicit typed fields')
        canonical_model_id(profile.get('model_id'))

    def _session(self, identifier):
        with self.registry_lock:
            if identifier not in self.sessions:
                raise HmiError("SESSION", "Unknown session; reopen the source")
            return self.sessions[identifier]

    def _registry_file_ok(self, path):
        """Check every registry ancestor against its initial canonical root."""
        try:
            relative = path.relative_to(self.profiles_dir)
            if any(part in ('.','..') for part in relative.parts):
                return False
            current = self.profiles_dir
            for part in (None, *relative.parts):
                if part is not None:
                    current /= part
                if current.is_symlink() or getattr(current,'is_junction',lambda:False)():
                    return False
            return path.is_file() and path.resolve(strict=True).is_relative_to(self.profiles_dir)
        except (OSError, ValueError):
            return False

    def _fresh(self, session):
        def same_file(path, expected_sha, expected_bytes):
            with path.open('rb') as file:
                raw = file.read(expected_bytes + 1)
            return len(raw) == expected_bytes and byte_hash(raw) == expected_sha
        try:
            source_same = session['source'] is None or same_file(session['source'], session['source_sha256'], len(session['source_bytes']))
        except OSError:
            source_same = False
        if not source_same:
            raise HmiError("SOURCE_CHANGED", "Source changed since open_project; reopen it")
        try:
            profile_same = same_file(session['profile_path'], session['profile_file_sha256'], session['profile_file_bytes'])
        except OSError:
            profile_same = False
        if not profile_same:
            raise HmiError("PROFILE_CHANGED", "Profile changed; reopen and approve the new contract")
        calibration = session.get('calibration')
        if calibration is not None:
            try:
                path = self._path(calibration['path'], exists=True)
                same = same_file(path, calibration['sha256'], calibration['bytes'])
            except (OSError, HmiError):
                same = False
            if not same:
                raise HmiError('CALIBRATION_CHANGED', 'Source-local calibration changed or disappeared; reopen and approve it')
            for path, expected_sha, expected_bytes in calibration.get('property_files', []):
                try:
                    same = same_file(path, expected_sha, expected_bytes)
                except OSError:
                    same = False
                if not same:
                    raise HmiError('CALIBRATION_CHANGED', 'A control property witness changed; reopen and approve it')
            for relative, expected_sha, expected_bytes in calibration.get('dependency_files', []):
                try:
                    same = same_file(self._path(relative, exists=True), expected_sha, expected_bytes)
                except (OSError, HmiError):
                    same = False
                if not same:
                    raise HmiError('CALIBRATION_CHANGED', 'A program library or its calibration changed; reopen and approve it')
            for path, expected_sha, expected_bytes in calibration.get('registry_files', []):
                try:
                    # The new DIA contract pins its own profile registry root.
                    # Legacy B contracts can intentionally use a separately
                    # registered shared authority catalog outside that root.
                    topology = (self._registry_file_ok(path) if calibration.get('mode') == 'diascreen_bound_buttons'
                        else not path.is_symlink() and not getattr(path,'is_junction',lambda:False)())
                    same = topology and same_file(path, expected_sha, expected_bytes)
                except OSError:
                    same = False
                if not same:
                    raise HmiError('CALIBRATION_CHANGED', 'A registered address or numeric authority changed; reopen and approve it')

    def open_project(self, profile_id, source_path=None):
        path, raw, profile = self._profile(profile_id)
        source = self._path(source_path, exists=True) if source_path else None
        data = source.read_bytes() if source else None
        inventory = NativeAdapter(data, profile["family"]).inspect() if data is not None else None
        identifier = str(uuid.uuid4())
        session = dict(profile=copy.deepcopy(profile), profile_path=path,
                       profile_sha256=canonical_hash(profile), profile_file_sha256=byte_hash(raw), profile_file_bytes=len(raw),
                       source=source, source_bytes=data, source_sha256=byte_hash(data) if data is not None else None,
                       inventory=inventory, plans={}, keys={}, applied=None, lock=threading.RLock())
        session['calibration'] = self._load_candidate_calibration(session)
        with self.registry_lock:
            self.sessions[identifier] = session
        return {"session_id": identifier, "source_sha256": session["source_sha256"],
                "profile_sha256": session["profile_sha256"], "inventory": inventory,
                "evidence": "UNVERIFIED" if profile.get("fixture_kind") != "synthetic" else "SYNTHETIC_ONLY"}

    def capabilities(self, profile_id):
        _, _, profile = self._profile(profile_id)
        return copy.deepcopy(profile)

    def inspect(self, session_id):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            inventory = copy.deepcopy(session["inventory"])
            if inventory is not None:
                try:
                    observed = NativeAdapter(session['source_bytes'], session['profile']['family']).calibration_inventory()
                    inventory['calibration_inventory'] = {key: value for key, value in observed.items()
                        if key not in {'owners', 'page_headers', 'global_sections'}}
                    inventory['calibration_inventory'].update(observed_owners=len(observed['owners']),
                        observed_pages=len(observed['page_headers']), observed_global_sections=len(observed['global_sections']),
                        complete_record_capture='scripts/capture_controls.py')
                except HmiError as exc:
                    if exc.code != 'CALIBRATION_LIMIT':
                        raise
                    inventory['calibration_inventory'] = {'scope': 'SOURCE_CALIBRATION_OBSERVATIONS_UNAVAILABLE',
                        'code': exc.code, 'qualification': 'UNVERIFIED', 'emission_authority': False}
            self._fresh(session)
            return inventory

    @staticmethod
    def _contract(session, design, operations):
        screens = design.get('screens', [])
        if not isinstance(screens, list) or any(not isinstance(s, dict) or not isinstance(s.get('elements'), list) or any(not isinstance(e, dict) for e in s['elements']) for s in screens):
            raise HmiError('PLAN_SHAPE', 'Screens and elements must be arrays of objects')
        result = {"source_sha256": session["source_sha256"],
                "profile_sha256": session["profile_sha256"],
                "design_sha256": canonical_hash(design),
                "bindings_sha256": canonical_hash({"tags": design.get("tags", []),
                    "bindings": [(s.get("id"), e.get("id"), e.get("binding", {}))
                        for s in design.get("screens", []) for e in s.get("elements", [])],
                    "alarms": [(a.get("id"), a.get("tag")) for a in design.get("alarms", [])]}),
                "operations_sha256": canonical_hash(operations)}
        if session.get('calibration') is not None:
            result['calibration_sha256'] = session['calibration']['sha256']
        return result

    def _load_candidate_calibration(self, session):
        """A raw-source bounded editing contract, never vendor qualification.

        An editable owner is an existing literal text with a primary wide
        caption. All other owner/global/visual bytes remain immutable. The
        witness is project-local and hashed into approval, not a registry flag.
        """
        profile = session['profile']
        schema = profile.get('native_schema', {})
        spec = schema.get('native_candidate') if isinstance(schema, dict) else None
        if spec is None:
            return None
        if isinstance(spec, dict) and spec.get('mode') == 'diascreen_control_append':
            return self._load_diascreen_control_calibration(session, spec)
        if isinstance(spec, dict) and spec.get('mode') == 'control_generation':
            return self._load_control_calibration(session, spec)
        if isinstance(spec, dict) and spec.get('mode') == 'diascreen_bound_buttons':
            return self._load_diascreen_bound_buttons(session, spec)
        if isinstance(spec, dict) and spec.get('mode') == 'blank_program':
            return self._load_program_calibration(session, spec)
        if isinstance(spec, dict) and spec.get('mode') == 'multipage_program':
            return self._load_multipage_calibration(session, spec)
        if (isinstance(spec, dict) and isinstance(spec.get('mode'), str)
                and spec['mode'] in {'existing_program', 'existing_edit'}):
            return self._load_existing_calibration(session, spec)

        def reject(message):
            raise HmiError('NATIVE_CALIBRATION', message)

        if (not isinstance(spec, dict) or set(spec) != {'qualified', 'contract_version', 'mode', 'path', 'sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(spec.get('mode'), str)
                or spec['mode'] not in {'existing_owner_candidate', 'literal_page_generation'}
                or not isinstance(spec.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256'])):
            reject('Candidate emission requires an exact source-local calibration reference')
        try:
            path = self._path(spec['path'], exists=True)
            raw, witness = _json_object(path, 'NATIVE_CALIBRATION')
            if byte_hash(raw) != spec['sha256']:
                reject('Calibration artifact differs from its profile SHA')
        except (OSError, UnicodeError, ValueError) as exc:
            raise HmiError('NATIVE_CALIBRATION', 'Calibration must be readable bounded UTF-8 JSON') from exc
        keys = {'contract_version', 'mode', 'source_sha256', 'family', 'model_id', 'serialized_version',
                'resolution', 'schema_sha256', 'source_origin', 'source_reference', 'review_reference',
                'panel_series', 'editable_owners'}
        if (not isinstance(witness, dict) or set(witness) != keys
                or type(witness.get('contract_version')) is not int or witness['contract_version'] != 1
                or witness.get('mode') != spec['mode']
                or not isinstance(witness.get('editable_owners'), list) or len(witness['editable_owners']) > 10000):
            reject('Calibration has an unknown or malformed contract')
        for key in ('source_sha256', 'schema_sha256'):
            if not isinstance(witness.get(key), str) or not re.fullmatch(r'[0-9a-f]{64}', witness[key]):
                reject('Calibration digests must be canonical SHA-256 values')
        for key in ('source_reference', 'review_reference'):
            if (not isinstance(witness.get(key), str) or not witness[key].strip()
                    or len(witness[key]) > 1000 or any(c in witness[key] for c in '\r\n\0')):
                reject('Calibration needs an exact source and review reference')
        origin = witness.get('source_origin')
        if not isinstance(origin, str) or origin not in {'original_neutral_fixture', 'user_vendor_project', 'manufacturer_installed_example'}:
            reject('Source origin must distinguish original fixtures from user vendor projects')
        installed_example = origin == 'manufacturer_installed_example'
        if installed_example or profile.get('fixture_kind') == 'manufacturer_installed_example':
            retained = schema.get('preserved_layout')
            if (not installed_example or profile.get('fixture_kind') != 'manufacturer_installed_example'
                    or spec['mode'] != 'existing_owner_candidate' or not isinstance(retained, dict)
                    or type(retained.get('contract_version')) is not int or retained['contract_version'] != 2
                    or retained.get('prefix_policy') != 'diascreen_opaque_source_v1'):
                reject('Installed examples require matching provenance and the separate opaque DIAScreen existing-owner policy')
        if ((origin == 'original_neutral_fixture') != (profile.get('fixture_kind') == 'synthetic')):
            reject('Fixture origin cannot be used to qualify a vendor project')
        if session['source_bytes'] is None or schema.get('qualified') is not True:
            reject('Candidate emission requires an immutable source and schema')
        original = NativeAdapter(session['source_bytes'], profile['family'])
        original._schema(profile)
        layout_key = 'literal_generation' if spec['mode'] == 'literal_page_generation' else 'preserved_layout'
        if layout_key not in schema:
            reject('Candidate editing requires a complete retained prefix/layout contract')
        original.verify_layout_order(schema)
        model = canonical_model_id(original.model_id)
        if (type(witness['model_id']) is not type(model)
                or not isinstance(witness['resolution'], list) or len(witness['resolution']) != 2
                or any(type(v) is not int or not 0 < v <= 2147483647 for v in witness['resolution'])):
            reject('Calibration model identity and resolution must have exact native scalar types')
        bounded_schema = {key: value for key, value in schema.items() if key != 'native_candidate'}
        if (witness['source_sha256'] != session['source_sha256']
                or witness['family'] != profile['family']
                or witness['model_id'] != model
                or witness['serialized_version'] != original.editor_version
                or witness['resolution'] != profile.get('resolution')
                or witness['schema_sha256'] != canonical_hash(bounded_schema)):
            reject('Calibration source, target or native mappings differ from the actual session')
        series = original.application.one('PanelSeries', False)
        if series is None:
            reject('Source lacks an explicit panel family marker')
        required = 'DOP-B series' if profile['family'] == 'delta_dopsoft2' else 'DOP-100 series'
        if series.kind is not None or series.value.decode('latin-1') != required or witness['panel_series'] != required:
            reject('Source panel family differs from the selected adapter')
        owners = {}
        actual = {(s['id'], e['id']): e for s in session['inventory']['screens'] for e in s['elements']}
        for owner in witness['editable_owners']:
            if (not isinstance(owner, dict) or set(owner) != {'screen_id', 'element_id', 'kind', 'owner_sha256'}
                    or owner.get('kind') != 'text'
                    or any(not isinstance(owner.get(k), str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}', owner[k])
                           or int(owner[k]) > 2147483647 for k in ('screen_id', 'element_id'))
                    or not isinstance(owner.get('owner_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', owner['owner_sha256'])):
                reject('Only explicitly fingerprinted existing literal text owners can be edited')
            identity = (owner['screen_id'], owner['element_id'])
            if identity in owners or identity not in actual:
                reject('Editable owner is missing or repeated')
            native = actual[identity]
            if original.owner_extent_sha256(*identity) != owner['owner_sha256']:
                reject('Editable owner raw extent differs from its calibration')
            self._literal_text_owner(original.document, *identity)
            owners[identity] = owner
        properties = schema.get('properties', {})
        for key, field in {'x': 'X', 'y': 'Y', 'width': 'Width', 'height': 'Height'}.items():
            prop = properties.get(key) if isinstance(properties, dict) else None
            if (not isinstance(prop, dict) or prop.get('field') != field or prop.get('type') != 'int'
                    or prop.get('scope', 'element') != 'element'):
                reject('Geometry requires exact native Element scalar mappings')
        kinds = schema.get('kinds')
        if not isinstance(kinds, dict) or kinds.get('text') != {'Type': '10', 'SubType': '6'}:
            reject('Literal text needs its exact observed Type/SubType mapping')
        if spec['mode'] == 'literal_page_generation':
            donor = schema['literal_generation']['text_donor']
            identity = (donor['screen_id'], donor['element_id'])
            if set(owners) != {identity} or owners[identity]['owner_sha256'] != donor['owner_sha256']:
                reject('Literal generation must pin exactly its immutable source donor')
        return {'path': spec['path'], 'sha256': spec['sha256'], 'bytes': len(raw), 'witness': witness, 'owners': owners, 'mode': spec['mode']}

    @staticmethod
    def _existing_authority_dir():
        return profiles_root() / 'existing_contracts'

    @staticmethod
    def _validate_existing_book(book):
        facts = {
            'schema_version': 1, 'authority_kind': 'manufacturer_static_inert_literal_contract',
            'family': 'delta_dopsoft2', 'serialized_version': '4.00.07.04',
            'model_id': 2953863504, 'mode': 'source_inert_literal_deletion',
            'owner_kind': {'Type': '10', 'SubType': '6'},
            'identity_policy': 'scalar_nPartsID_survivors_unchanged',
            'graph_policy': 'closed_empty_macro_group_aux_recipe_history_picture_graph',
            'background_policy': 'complete_unique_same_canvas_BI_RGB32_frames_preserved',
            'mutation_policy': 'subtract_exact_pinned_owner_extents_only',
            'acceptance_scope': 'OFFLINE_STORED_INERT_LITERAL_DELETION_ONLY',
            'evidence': {
                'editor_sha256': '9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb',
                'identity_reader': 'b6716a..b67178 scalar owner+4ec',
                'identity_writer': 'b66541..b66565 scalar nPartsID',
                'group_compiler': '7d43ee..7d43f8 GroupID0 skipped',
                'metadata_scope': '811f51..811f68 and 69c4be..69c5b7 global MeMeCode, not owner checksum',
                'configuration_scope': '250c7 fixed8char slot,884196..8841b7;885ddb..885e56;4dbfb9..4dbfed',
                'submacro_configuration': '816f10..816f39 %s writer;69ff1d..69ff9c reader;7a9df6/7a9e30 separate password string slot',
                'submacro_shape': '816da2 writer512 slots001..512;d42da0/69ffa6..6a0020 SubMacro%03dLen; observed password scalar8bytes only',
                'executed_vendor_code': False, 'vendor': 'NOT_RUN', 'native_pixels': 'NOT_RUN'}}
        if not isinstance(book, dict) or canonical_hash(book) != canonical_hash(facts):
            raise HmiError('EXISTING_AUTHORITY', 'Inert deletion requires the exact registered primary static facts and their limited scope')

    def _existing_authority(self, schema, profile, source_sha256):
        from .native.existing_program import existing_program_contract
        descriptor = existing_program_contract(schema)
        if (descriptor['source_sha256'] != source_sha256 or descriptor['family'] != profile['family']
                or type(profile.get('model_id')) is not int or descriptor['model_id'] != profile['model_id']
                or descriptor['editor_version'] != profile['editor_version']):
            raise HmiError('EXISTING_AUTHORITY', 'Static deletion facts differ from the exact source target')
        directory = self._existing_authority_dir()
        if not directory.is_dir() or directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)():
            raise HmiError('EXISTING_AUTHORITY', 'A local reviewed inert-deletion authority registry is required')
        paths = sorted(directory.glob('*.json'))
        if not 1 <= len(paths) <= 128:
            raise HmiError('EXISTING_AUTHORITY', 'Inert deletion authority registry is empty or oversized')
        found = []
        for path in paths:
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('EXISTING_AUTHORITY', 'Inert deletion registry must not traverse links')
            raw, book = _json_object(path, 'EXISTING_AUTHORITY')
            if byte_hash(raw) != descriptor['authority_sha256']:
                continue
            self._validate_existing_book(book)
            found.append((path, byte_hash(raw), len(raw)))
        if len(found) != 1:
            raise HmiError('EXISTING_AUTHORITY', 'One exact registered inert-deletion authority is required')
        return found[0]

    def _load_existing_calibration(self, session, spec):
        from .native.existing_program import ExistingProgram, existing_program_contract
        schema, profile = session['profile']['native_schema'], session['profile']
        mode = spec.get('mode') if isinstance(spec, dict) else None
        schema_keys = {'qualified', 'existing_program', 'native_candidate'}
        if mode == 'existing_edit':
            schema_keys |= {'existing_presentation', 'existing_background'}
            if 'existing_integer_numeric' in schema:
                schema_keys.add('existing_integer_numeric')
            if 'existing_entry_permission' in schema:
                schema_keys |= {'existing_entry_permission','entry_permission_inputs'}
        if (not isinstance(spec, dict) or set(spec) != {'qualified', 'contract_version', 'mode', 'path', 'sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(mode, str)
                or mode not in {'existing_program', 'existing_edit'}
                or not isinstance(spec.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256'])
                or set(schema) != schema_keys or session['source_bytes'] is None):
            raise HmiError('NATIVE_CALIBRATION', 'Existing-program deletion needs its separate exact source-local witness')
        descriptor = existing_program_contract(schema)
        registry = self._existing_authority(schema, profile, session['source_sha256'])
        raw, witness = _json_object(self._path(spec['path'], exists=True), 'NATIVE_CALIBRATION')
        keys = {'contract_version', 'mode', 'source_sha256', 'family', 'model_id', 'serialized_version',
                'resolution', 'schema_sha256', 'source_origin', 'source_reference', 'review_reference'}
        bounded = {k: v for k, v in schema.items() if k != 'native_candidate'}
        if (byte_hash(raw) != spec['sha256'] or set(witness) != keys
                or type(witness.get('contract_version')) is not int or witness['contract_version'] != 1
                or witness.get('mode') != mode or witness.get('source_origin') != 'user_vendor_project'
                or witness.get('source_sha256') != session['source_sha256'] or witness.get('family') != profile['family']
                or type(witness.get('model_id')) is not int or witness['model_id'] != descriptor['model_id']
                or witness.get('serialized_version') != descriptor['editor_version']
                or not isinstance(witness.get('resolution'), list) or len(witness['resolution']) != 2
                or any(type(n) is not int for n in witness['resolution']) or witness['resolution'] != profile['resolution']
                or witness.get('schema_sha256') != canonical_hash(bounded)):
            raise HmiError('NATIVE_CALIBRATION', 'Existing-program witness source, schema or target drifted')
        for key in ('source_reference', 'review_reference'):
            value = witness.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 1000 or any(c in value for c in '\r\n\0'):
                raise HmiError('NATIVE_CALIBRATION', 'Existing-program witness needs bounded explicit source/review references')
        original = NativeAdapter(session['source_bytes'], profile['family'])
        ExistingProgram(original, schema).check()
        registries, dependencies = [registry], []
        if mode == 'existing_edit':
            registries.extend(self._edit_authority(schema[key], profile, session['source_sha256'], role)
                for key, role in (('existing_presentation', 'presentation'), ('existing_background', 'background')))
            if 'existing_integer_numeric' in schema:
                registries.append(self._edit_authority(schema['existing_integer_numeric'], profile,
                    session['source_sha256'], 'integer_numeric'))
            if 'existing_entry_permission' in schema:
                _, _, _, dependency_files, permission_registries = self._edit_permission_inputs(session)
                dependencies.extend(dependency_files);registries.extend(permission_registries)
            self._edit_program(session).check()
        if any([int(p['section'].one('PanelSizeX').value), int(p['section'].one('PanelSizeY').value)] != profile['resolution']
               for p in _groups(original.document)):
            raise HmiError('NATIVE_CALIBRATION', 'Source page canvases differ from the exact profile')
        return dict(path=spec['path'], sha256=spec['sha256'], bytes=len(raw), witness=witness,
                    owners={}, mode=mode, registry_files=registries, dependency_files=dependencies)

    @staticmethod
    def _edit_book_facts(role):
        common = dict(schema_version=1, family='delta_dopsoft2', model_id=2953863504,
            serialized_version='4.00.07.04', acceptance_scope='OFFLINE_STORED_CONFIGURATION_ONLY',
            source_policy='original_source_pinned_closed_existing_graph', vendor='NOT_RUN', native_pixels='NOT_RUN')
        if role == 'presentation':
            common.update(authority_kind='manufacturer_static_existing_presentation_contract',
                mode='variable_scalar_records_v1', color_encoding='COLORREF_0x00BBGGRR',
                kinds={'buttons':['1','2','3','4','10'], 'indicator':['2','1'],
                       'numeric':[['5','1'],['6','1']], 'inert_literal':['10','6']},
                surfaces={'button_indicator':'State.FgColor','numeric':'State.BgColor'},
                native_styles={'button_indicator':[0,5,9,16], 'numeric':[0,5,10,16]},
                border_policy='numeric_result_native_style0_only',
                font_sizes=[8,10,12,14,16,18,20,22,24,28,32,36,40,48,64,72],
                font_ratios=[33,50,100,150,200],
                mutation_policy='canonical_variable_scalar_records_only',
                evidence={'editor_sha256':'9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb',
                    'sequential_reader':'6988cd/8ba0d0;8ba154..163;6990ce/87c250;87c27e..2c4;69987d/87cc4d',
                    'scalar_writer':'b66175/7b7bb9 actual scalar strlen plus CRLF; geometry b660a6..b6612b; State b6caf6..b6cbe3',
                    'font_tables':'d26798 and d26830 exact intersection; ratio87d09b..121',
                    'review':'reports/EXISTING_PRESENTATION_FOUNDATION.json'})
        elif role == 'background':
            common.update(authority_kind='manufacturer_static_existing_background_contract',
                mode='fixed_opaque_page_background_v1',
                resource_policy='unique_complete_PictureOffset_to_same_canvas_DIB40_BI_RGB32',
                image_policy='opaque_noninterlaced_RGB8_or_RGBA8_PNG_IHDR_IDAT_IEND_only',
                mutation_policy='same_size_frame_pixels_only_header_and_offsets_preserved',
                pixel_encoding='bottom_up_BGR_reservedFF_not_alpha',
                evidence={'editor_sha256':'9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb',
                    'page_link':'86656b..866593 page+70;6a05a8..6a0627;68d7ce/68d7ea/7b0de1',
                    'frame_copy':'7b0e8b..9a/c1e260;7b0f2a..5f;7b0f9a..fb8/c1e350',
                    'consumer':'834b65/68d811/8655ff;834f98..fa5/861014;8611b3..12f9/c1fb40 mode0;SetDIBits/BitBlt SRCCOPY',
                    'base_policy':'BaseScreenID0 only;866201..220/867ee3/861028/8686c2',
                    'review':'reports/EXISTING_BACKGROUND_FOUNDATION.json'})
        elif role == 'integer_numeric':
            common.update(authority_kind='manufacturer_static_existing_integer_numeric_contract',
                mode='existing_word_integer_numeric_v1',
                storage_policy='original_WORD_MemLen1_MemFmt1_INT_or2_UINT_immutable',
                mutation_fields=['IntNum','DotNum','MinValue','MaxValue'],
                identity_scale={'gain':'1','offset':'0','roundoff':'0'},
                display_fractional_digits={'INT':[0,1,4],'UINT':[0,1,2,3,4]},
                display_integer_digits='5-F_full_WORD_raw_domain',
                input_policy='original_F0_only_strict_integral_raw_minimum_less_than_maximum',
                raw_ranges={'INT':[-32768,32767],'UINT':[0,65535]},
                fractional_input='UNVERIFIED_REFUSED',
                conditional_operands='UNQUALIFIED_REFUSED',
                evidence={'editor_sha256':'9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb',
                    'renderer_sha256':'e6fa5b74d8d73415b1fd79b16aa19fc163f95113471eb8e9e1022f8615b19ab3',
                    'numeric_reader_writer':'b66b6a..b66bbb/b66321; MemLen/MemFmt/IntNum/DotNum native scalar fields',
                    'numeric_compiler':'617dcd..617e1a;7d86a5..7d86bd/7d884d..7d8865',
                    'signed_display':'100c93ea/100c93fa signed WORD;10131acf/10131b88 decimal insertion;10131c36..10131c90 restores minus',
                    'unsigned_display':'100c9453..100c949a;10131acf/10131b88',
                    'input_F0':'6181c5..61823f/6183a4..618419; integer limits only;100efd02..100efd29 identity bypass',
                    'digit_capacity':'7ad8fe;7adcca signed WORD;7adfb3 unsigned WORD',
                    'signed_F4_property_holdout':'NOT_FOUND',
                    'review':'reports/NUMERIC_LIMIT_RESEARCH_UPDATE.json',
                    'boundary':'stored settings and source/static text path only; no actual glyph/CRT/thread/runtime/vendor execution'})
        elif role == 'entry_permission':
            common.update(authority_kind='manufacturer_static_existing_entry_permission_contract',
                mode='existing_entry_permission_v1',
                owner_types=[[1,1],[6,1]],
                action_classes={'Type1_Sub1':'start_request','Type6_Sub1':'parameter_write'},
                action_policy='explicit_original_owner_write_binding_project_human_contract_only',
                mutation_fields=['InterLockVar','InterLockLevel'],
                channel_policy='retain_original_InterLockLink_equals_source_native_driver_index_plus1',
                permission_operand='registered_source_driver_external_BOOL_Read_canonical',
                baseline='original_disabled_interlock_plain_no_macro_offset_visibility_confirmation_trigger',
                numeric_policy='original_INT_UINT_WORD_F0_identity_only',
                enable_levels=[0,1],
                semantics='action_entry_or_keypad_open_only',
                read_failure='never_matches_enable_level0_or1_static_path',
                sample_age='UNQUALIFIED',commit_time='UNQUALIFIED',continuous='UNQUALIFIED',
                atomicity='UNQUALIFIED',quality_composition='UNQUALIFIED',
                active_vendor_holdout='NOT_FOUND',runtime='NOT_RUN',
                evidence={'editor_sha256':'9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb',
                    'renderer_sha256':'e6fa5b74d8d73415b1fd79b16aa19fc163f95113471eb8e9e1022f8615b19ab3',
                    'reader_writer':'616fdf..617073;616531..6165e3',
                    'compiler':'7d8f38..7d9074 capability0x24/nonliteral0or1;7c8415 native link minusone',
                    'Type1_loader':'100b3e57..100b3f38',
                    'Type6_loader':'100b5822..100b58a6',
                    'permission_helper':'100fd8bb..100fd916 returns-1 failure,0 mismatch,1 match',
                    'action_entry':'100dbd10/100dbd6e/100dbd73/100dbf19',
                    'keypad_entry':'100ef3bc/100ef3c1/100ef7f9',
                    'review':'reports/ENTRY_PERMISSION_RESEARCH.json',
                    'boundary':'Stored configuration and independently reviewed static path; no vendor/native pixel/runtime/freshness/safety acceptance'})
        else:
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'Unknown existing edit authority role')
        return common

    def _edit_authority(self, descriptor, profile, source_sha256, role):
        from .native.existing_presentation import presentation_contract
        from .native.existing_background_page import background_contract
        from .native.existing_integer_numeric import integer_numeric_contract
        validators = {'presentation':presentation_contract, 'background':background_contract,
                      'integer_numeric':integer_numeric_contract}
        if role == 'entry_permission':
            from .native.existing_entry_permission import entry_permission_contract
            validators['entry_permission'] = entry_permission_contract
        if role not in validators:
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'Unknown existing edit authority role')
        contract = validators[role](descriptor)
        if (contract['source_sha256'] != source_sha256 or contract['family'] != profile['family']
                or type(profile.get('model_id')) is not int or contract['model_id'] != profile['model_id']
                or contract['editor_version'] != profile['editor_version']):
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'Edit facts differ from the immutable source target')
        directory = self._existing_authority_dir()
        if not directory.is_dir() or directory.is_symlink() or getattr(directory,'is_junction',lambda:False)():
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'Reviewed local edit authority registry is required')
        paths = sorted(directory.glob('*.json'))
        if not 1 <= len(paths) <= 128:
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'Edit authority registry is empty or oversized')
        found = []
        for path in paths:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('EXISTING_EDIT_AUTHORITY', 'Edit registry cannot traverse links')
            raw, book = _json_object(path,'EXISTING_EDIT_AUTHORITY')
            if byte_hash(raw) == contract['authority_sha256']:
                if canonical_hash(book) != canonical_hash(self._edit_book_facts(role)):
                    raise HmiError('EXISTING_EDIT_AUTHORITY', 'Registered edit facts differ from the reviewed typed contract')
                found.append((path,byte_hash(raw),len(raw)))
        if len(found) != 1:
            raise HmiError('EXISTING_EDIT_AUTHORITY', 'One exact registered edit authority is required')
        return found[0]

    def _edit_permission_inputs(self, session):
        # Project raw artifacts are distinct from the registered static book.
        # Their paths stay workspace-relative and every call rechecks raw pins.
        from .native.address_contract import AddressNamespace
        from .native.existing_entry_permission import entry_permission_contract
        schema, profile = session['profile']['native_schema'], session['profile']
        descriptor = entry_permission_contract(schema['existing_entry_permission'])
        inputs = schema.get('entry_permission_inputs')
        if not isinstance(inputs,dict) or set(inputs)!={'address_namespace','action_contract'}:
            raise HmiError('EXISTING_ENTRY_INPUTS','Entry permission requires two exact project artifact references')
        raw_inputs, objects, dependencies = {}, {}, []
        for role in ('address_namespace','action_contract'):
            spec = inputs[role]
            expected = descriptor[role+'_sha256']
            if (not isinstance(spec,dict) or set(spec)!={'path','sha256'}
                    or not isinstance(spec.get('path'),str) or spec.get('sha256')!=expected):
                raise HmiError('EXISTING_ENTRY_INPUTS','Project artifact reference differs from its descriptor',field=role)
            raw, obj = _json_object(self._path(spec['path'],exists=True),'EXISTING_ENTRY_INPUTS')
            if byte_hash(raw)!=expected:
                raise HmiError('EXISTING_ENTRY_INPUTS','Project artifact raw bytes differ from their pin',field=role)
            raw_inputs[role], objects[role] = raw,obj
            dependencies.append((spec['path'],expected,len(raw)))
        namespace = objects['address_namespace']
        original = NativeAdapter(session['source_bytes'],profile['family'])
        AddressNamespace(namespace).validate_source(original,namespace['prefix'])
        registries = [self._edit_authority(descriptor,profile,session['source_sha256'],'entry_permission'),
                      self._address_authority(namespace,profile)]
        return descriptor,raw_inputs['address_namespace'],raw_inputs['action_contract'],dependencies,registries

    def _edit_program(self, session):
        from .native.existing_edit import ExistingEdit
        schema = session['profile']['native_schema']
        options = {}
        if 'existing_entry_permission' in schema:
            descriptor,namespace_raw,action_raw,_,_ = self._edit_permission_inputs(session)
            options = dict(entry_permission_descriptor=descriptor,address_namespace_raw=namespace_raw,
                           action_contract_raw=action_raw)
        return ExistingEdit(NativeAdapter(session['source_bytes'],session['profile']['family']),
            schema,schema['existing_presentation'],schema['existing_background'],
            schema.get('existing_integer_numeric'),**options)

    def _edit_assets(self, design):
        assets, files = {}, []
        if not isinstance(design,dict) or not isinstance(design.get('screens'),list):
            raise HmiError('EXISTING_EDIT_SCOPE','Existing edit needs explicit screen declarations')
        for screen in design['screens']:
            if not isinstance(screen,dict):
                raise HmiError('EXISTING_EDIT_SCOPE','Every edit screen must be an object')
            if 'native_background' not in screen:
                continue
            value = screen['native_background']
            if not isinstance(value,dict) or set(value) != {'frame_sha256','asset_path','asset_sha256'}:
                raise HmiError('EXISTING_EDIT_ASSET','Background needs exact frame/relative PNG path/SHA')
            digest = value['asset_sha256']
            if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
                raise HmiError('EXISTING_EDIT_ASSET','Asset needs canonical SHA-256')
            try:
                path = self._path(value['asset_path'],exists=True)
                with path.open('rb') as stream:
                    raw = stream.read(32*1024*1024+1)
            except (OSError,HmiError) as exc:
                raise HmiError('EXISTING_EDIT_ASSET','PNG asset disappeared or its path is unavailable') from exc
            if len(raw)>32*1024*1024 or byte_hash(raw) != digest:
                raise HmiError('EXISTING_EDIT_ASSET','PNG asset changed or exceeds its bounded size')
            assets[digest] = raw
            files.append((value['asset_path'],digest,len(raw)))
        return assets,files

    def _edit_operations(self, session, design):
        from .native.existing_program import _bounded
        _bounded(design)
        findings = validate_design(design, session['profile'])
        if findings:
            raise HmiError('VALIDATION', 'Existing edit requires a valid explicit IR', findings=findings)
        assets,_ = self._edit_assets(design)
        original = NativeAdapter(session['source_bytes'],session['profile']['family'])
        retained = copy.deepcopy(design)
        owners = {(p['id'],e['id']): e for p in session['inventory']['screens'] for e in p['elements']}
        operations = []
        for screen, plain in zip(design['screens'],retained['screens']):
            if (set(screen)-{'native_background'} != {'id','native_id','name','width','height','elements'}
                    or not isinstance(screen['native_id'],str)):
                raise HmiError('EXISTING_EDIT_SCOPE','Edit screens require complete original identities and explicit intent')
            sid = screen['native_id']
            plain.pop('native_background',None)
            for element, kept in zip(screen['elements'],plain['elements']):
                if element.get('kind') not in {'native_presentation','native_integer_numeric','native_entry_permission'}:
                    continue
                numeric = element['kind'] == 'native_integer_numeric'
                fields = {'id','native_id','kind','x','y','width','height','text','source_owner_sha256','presentation'}
                if numeric: fields.add('integer_numeric')
                if 'entry_permission' in element: fields.add('entry_permission')
                if element['kind']=='native_entry_permission' and 'entry_permission' not in element:
                    raise HmiError('EXISTING_EDIT_SCOPE','Entry permission kind requires its explicit payload')
                if (set(element) != fields
                        or element['text'] != '' or (sid,element['native_id']) not in owners):
                    raise HmiError('EXISTING_EDIT_SCOPE','Presentation cannot override content, bindings or behavior')
                if numeric:
                    if 'existing_integer_numeric' not in session['profile']['native_schema']:
                        raise HmiError('EXISTING_EDIT_SCOPE','Existing integer numeric requires its separate source-bound authority')
                    operations.append(dict(op='configure_existing_integer_numeric',screen_id=sid,
                        element_id=element['native_id'],owner_sha256=element['source_owner_sha256'],
                        **copy.deepcopy(element['integer_numeric'])))
                    kept.pop('integer_numeric')
                if 'entry_permission' in element:
                    if element['kind'] not in {'native_integer_numeric','native_entry_permission'}:
                        raise HmiError('EXISTING_EDIT_SCOPE','Permission intent requires its separate kind or numeric intent')
                    if 'existing_entry_permission' not in session['profile']['native_schema']:
                        raise HmiError('EXISTING_EDIT_SCOPE','Entry permission needs its separate source/action authority')
                    operations.append(dict(op='set_existing_entry_permission',screen_id=sid,
                        element_id=element['native_id'],owner_sha256=element['source_owner_sha256'],
                        **copy.deepcopy(element['entry_permission'])))
                    kept.pop('entry_permission')
                native = owners[(sid,element['native_id'])]
                request = element['presentation']
                if not isinstance(request,dict) or set(request)-{'visual','states'}:
                    raise HmiError('EXISTING_EDIT_SCOPE','Presentation requires only explicit visual/state requests')
                op = dict(op='set_existing_presentation',screen_id=sid,element_id=element['native_id'],owner_sha256=element['source_owner_sha256'])
                if any(element[k] != native['geometry'][k] for k in ('x','y','width','height')):
                    op['geometry'] = {k:element[k] for k in ('x','y','width','height')}
                op.update(copy.deepcopy(request))
                if set(op)-{'op','screen_id','element_id','owner_sha256'}:
                    operations.append(op)
                kept.pop('presentation');kept['kind']='native_preserved';kept.update(native['geometry'])
            if 'native_background' in screen:
                bg = screen['native_background']
                operations.append(dict(op='set_existing_background',screen_id=sid,frame_sha256=bg['frame_sha256'],asset_sha256=bg['asset_sha256']))
        _, deletions = self._existing_operations(session,retained)
        operations = deletions+operations
        self._edit_program(session).expected_body(operations,assets)
        return original,operations,assets

    @staticmethod
    def _edit_background_span(original, page, background, png):
        # Independently walk textual resource framing, skipping each declared
        # opaque block; payload bytes cannot impersonate a section header.
        from .native.resources import ResourceTables,_line,_record
        from .native.existing_background import frame_pixels_from_png
        import struct
        table = ResourceTables.parse(original.document.tail)
        suffix = table.suffix
        offset = len(original.envelope.body)-len(suffix)
        pos,current = 0,None
        while pos<len(suffix):
            start=pos;line,pos=_line(suffix,pos)
            if line.startswith(b'[') and line.endswith(b']'):
                current=line[1:-1].decode('ascii')
                if current == 'SRAM_DATA':
                    size=struct.unpack_from('<I',suffix,pos)[0]
                    pos+=4+size+2
                continue
            if line == b'[SysMessage]'+bytes(3):
                current='SysMessage';continue
            if current == 'Tag' and line.startswith(b'LinkSize='):
                pos+=int(line[9:]);continue
            if current == 'DeviceTable' and line == b'DisplayLength=0':
                continue
            if current in {'Picture','Background'} and line.startswith(b'Size='):
                size=int(line[5:])
                if current == 'Background':
                    frame_offset=int(page['section'].one('PictureOffset').value)
                    width=int(page['section'].one('PanelSizeX').value)
                    height=int(page['section'].one('PanelSizeY').value)
                    frame_size=40+width*height*4
                    frame=suffix[pos+frame_offset:pos+frame_offset+frame_size]
                    if len(frame)!=frame_size or byte_hash(frame)!=background['frame_sha256']:
                        raise HmiError('EXISTING_EDIT_BACKGROUND','Independent page frame pin differs')
                    replacement=frame_pixels_from_png(frame,png)
                    return offset+pos+frame_offset,offset+pos+frame_offset+frame_size,replacement
                pos+=size+2;continue
            _,pos=_record(suffix,start,line,pos,current)
        raise HmiError('EXISTING_EDIT_BACKGROUND','Independent framed Background resource is absent')

    def _edit_expected_body(self, session, design):
        # Independently derive raw scalar targets from IR and original sections,
        # not ExistingEdit.expected_body, its operations or mutated record walk.
        original,operations,assets = self._edit_operations(session,design)
        pages={p['id']:p for p in _groups(original.document)}
        targets,spans,omitted = {},[],set()
        for screen in design['screens']:
            page=pages[screen['native_id']]
            declared={e['native_id'] for e in screen['elements']}
            for owner in page['elements']:
                if owner['id'] not in declared:
                    omitted.update(range(owner['start'],owner['end']))
            owner_map={e['id']:e for e in page['elements']}
            for element in screen['elements']:
                if element['kind'] not in {'native_presentation','native_integer_numeric','native_entry_permission'}:continue
                owner=owner_map[element['native_id']];section=owner['section'];intent=element['presentation']
                values={field:str(element[key]).encode('ascii') for key,field in [('x','X'),('y','Y'),('width','Width'),('height','Height')]}
                for key,field in [('native_style','Style'),('border_color','BorderColor')]:
                    if key in intent.get('visual',{}):values[field]=str(intent['visual'][key]).encode('ascii')
                if element['kind']=='native_integer_numeric':
                    # Independent IR-to-original-record expectation, never
                    # call the new numeric primitive's settings/spans/emitter.
                    from decimal import Decimal
                    numeric=element['integer_numeric']
                    values.update(IntNum=str(numeric['integer_digits']).encode('ascii'),
                                  DotNum=str(numeric['fractional_digits']).encode('ascii'))
                    for key,field in [('raw_minimum','MinValue'),('raw_maximum','MaxValue')]:
                        if key in numeric:
                            old=section.one(field).value
                            requested=str(numeric[key]).encode('ascii')
                            values[field]=old if Decimal(old.decode('ascii'))==Decimal(numeric[key]) else requested
                if 'entry_permission' in element:
                    permission=element['entry_permission']
                    values.update(InterLockVar=permission['permission_address'].encode('ascii'),
                                  InterLockLevel=str(permission['enable_level']).encode('ascii'))
                targets[id(section)]=values
                state_map={state.one('Value').value.decode('ascii'):state for state in owner['states']}
                for state in intent.get('states',[]):
                    fields={}
                    for key,field in [('font_size','FontSize0'),('font_ratio','FontRatio0'),('font_color','FontColor'),
                            ('surface_color','BgColor' if section.one('Type').value in {b'5',b'6'} else 'FgColor')]:
                        if key in state:fields[field]=str(state[key]).encode('ascii')
                    targets[id(state_map[state['value']])]=fields
            if 'native_background' in screen:
                bg=screen['native_background']
                spans.append(self._edit_background_span(original,page,bg,assets[bg['asset_sha256']]))
        pos=0
        for index,section in enumerate(original.document.sections):
            end=pos+len(section.bytes())
            if index in omitted:
                spans.append((pos,end,b''));pos=end;continue
            cursor=pos+len(section.header)
            for record in section.records:
                value=targets.get(id(section),{}).get(record.key)
                stop=cursor+len(record.raw)
                if value is not None and value!=record.value:
                    spans.append((cursor,stop,record.key.encode('ascii')+b'='+value+b'\r\n'))
                cursor=stop
            pos=end
        spans.sort(key=lambda span:span[0]);chunks=[];cursor=0
        for start,end,raw in spans:
            if start<cursor or end>len(original.envelope.body):
                raise HmiError('EXISTING_EDIT_PRESERVATION','Independent original edit ranges overlap or exceed the body')
            chunks.extend((original.envelope.body[cursor:start],raw));cursor=end
        chunks.append(original.envelope.body[cursor:])
        return original,b''.join(chunks),operations,assets

    def _existing_operations(self, session, design):
        from .native.existing_program import ExistingProgram
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        program = ExistingProgram(original, session['profile']['native_schema'])
        program.check()
        if any(design.get(key) for key in ('tags', 'macros', 'alarms')):
            raise HmiError('EXISTING_PROGRAM_SCOPE', 'Inert deletion preserves every native address, macro and alarm')
        pages = session['inventory']['screens']
        identity = lambda obj: str(obj.get('native_id', obj['id']))
        if [identity(s) for s in design['screens']] != [s['id'] for s in pages]:
            raise HmiError('EXISTING_PROGRAM_SCOPE', 'Every original page must remain in its original order')
        operations = []
        for screen, page in zip(design['screens'], pages):
            if (screen['name'] != page['name'] or [screen['width'], screen['height']] != session['profile']['resolution']):
                raise HmiError('EXISTING_PROGRAM_SCOPE', 'Inert deletion cannot change page names or canvas dimensions')
            ids = [identity(e) for e in screen['elements']]
            retained = {eid for eid in ids}
            source_ids = [e['id'] for e in page['elements']]
            if ids != [eid for eid in source_ids if eid in retained]:
                raise HmiError('EXISTING_PROGRAM_SCOPE', 'Survivor identities/order must be an exact original subsequence')
            by_id = {e['id']: e for e in page['elements']}
            for element in screen['elements']:
                eid = identity(element)
                native = by_id[eid]
                if (set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'source_owner_sha256'}
                        or element['kind'] != 'native_preserved' or element['text'] != ''
                        or element['source_owner_sha256'] != original.owner_extent_sha256(page['id'], eid)
                        or any(element[k] != native['geometry'][k] for k in ('x', 'y', 'width', 'height'))):
                    raise HmiError('NATIVE_PRESERVED_MISMATCH', 'Every survivor requires its exact source extent and unchanged geometry')
            operations.extend(dict(op='delete_literal', screen_id=page['id'], element_id=eid,
                owner_sha256=original.owner_extent_sha256(page['id'], eid)) for eid in source_ids if eid not in retained)
        # Validate all omitted objects as inert before publishing a plan.
        program.expected_body(operations)
        return original, operations

    def _existing_expected_body(self, session, design):
        """Subtract approved omitted-owner ranges independently of the emitter."""
        original, operations = self._existing_operations(session, design)
        omitted = {(op['screen_id'], op['element_id']) for op in operations}
        offsets = [0]
        for section in original.document.sections:
            offsets.append(offsets[-1] + len(section.bytes()))
        ranges = sorted((offsets[owner['start']], offsets[owner['end']])
            for page in _groups(original.document) for owner in page['elements']
            if (page['id'], owner['id']) in omitted)
        chunks, cursor = [], 0
        for start, end in ranges:
            chunks.append(original.envelope.body[cursor:start])
            cursor = end
        chunks.append(original.envelope.body[cursor:])
        return original, b''.join(chunks), operations

    @staticmethod
    def _literal_text_owner(document, sid, eid):
        page = next((s for s in _groups(document) if s['id'] == sid), None)
        owner = next((e for e in page['elements'] if e['id'] == eid), None) if page else None
        if owner is None:
            raise HmiError('NATIVE_CALIBRATION', 'Literal text owner is absent')
        section = owner['section']
        if (section.one('Type').value != b'10' or section.one('SubType').value != b'6'
                or len(owner['states']) != 1 or owner['states'][0].one('Value').value != b'0'):
            raise HmiError('NATIVE_CALIBRATION', 'Literal text must have one explicit Value=0 State')
        for field in ('ReadVar', 'WriteVar'):
            record = section.one(field)
            if record.kind is not None or record.value != b'None':
                raise HmiError('NATIVE_CALIBRATION', 'Editable literal text cannot carry a live address')
        for field in ('OffsetReadVar', 'OffsetWriteVar', 'VisibleVar'):
            record = section.one(field, False)
            if record is not None and (record.kind is not None or record.value != b'None'):
                raise HmiError('NATIVE_CALIBRATION', 'Editable literal text requires inert offset and visibility operands')
        for part in (section, *owner['states']):
            if any(record.kind == 'macro' and record.blob for record in part.records):
                raise HmiError('NATIVE_CALIBRATION', 'Editable literal text cannot carry an executable macro')
        caption = owner['states'][0].one('wTextLen0')
        if caption.kind != 'wide' or caption.blob is None or len(caption.blob) < 2:
            raise HmiError('NATIVE_CALIBRATION', 'Editable literal text needs an existing primary UTF-16 caption')
        caption.text()
        return section, caption

    def _candidate_document(self, session, design):
        """Independent full-byte target from IR and immutable raw owners.

        This does not use the emitter's operations or profile property setters.
        Presentation and unrepresented objects are retained, never rendered or
        assigned behavior by this check.
        """
        if session['calibration']['mode'] == 'diascreen_bound_buttons':
            original, operations = self._diascreen_bound_intent(session, design)
            body = self._diascreen_bound_program(session).expected_body(operations)
            raw = original.envelope.encode(body) if operations else original.original
            return original, NativeAdapter(raw, original.family).document
        if session['calibration']['mode'] == 'diascreen_control_append':
            original, operations = self._diascreen_control_intent(session, design)
            body = self._diascreen_control_program(session).expected_body(operations)
            raw = original.envelope.encode(body) if operations else original.original
            return original, NativeAdapter(raw, original.family).document
        if session['calibration']['mode'] == 'existing_edit':
            original, body, _, _ = self._edit_expected_body(session, design)
            return original, NativeAdapter(original.envelope.encode(body) if body != original.envelope.body else original.original, original.family).document
        if session['calibration']['mode'] == 'existing_program':
            original, body, operations = self._existing_expected_body(session, design)
            expected = NativeAdapter(original.envelope.encode(body) if operations else original.original, original.family)
            return original, expected.document
        if session['calibration']['mode'] == 'multipage_program':
            return self._multipage_document(session, design)[0:2]
        if session['calibration']['mode'] == 'blank_program':
            return self._program_document(session, design)[0:2]
        if session['calibration']['mode'] == 'control_generation':
            return self._control_document(session, design)[0:2]
        if session['calibration']['mode'] == 'literal_page_generation':
            return self._generation_document(session, design)
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        document = copy.deepcopy(original.document)
        calibration = session['calibration']
        if any(design.get(key) for key in ('tags', 'macros', 'alarms')):
            raise HmiError('NATIVE_CANDIDATE_SCOPE', 'Existing-owner candidates preserve every address, macro and alarm resource')
        pages = session['inventory']['screens']
        identity = lambda obj: str(obj.get('native_id', obj['id']))
        if [identity(s) for s in design['screens']] != [s['id'] for s in pages]:
            raise HmiError('NATIVE_CANDIDATE_SCOPE', 'Candidate intent must retain every page in its source order')
        for screen, source in zip(design['screens'], pages):
            sid = source['id']
            if (screen['name'] != source['name'] or [screen['width'], screen['height']] != session['profile']['resolution']
                    or any(source['native_fields'].get(prefix + axis) != str(screen[key])
                           for prefix in ('DocSize', 'PanelSize') for axis, key in (('X', 'width'), ('Y', 'height')))
                    or [identity(e) for e in screen['elements']] != [e['id'] for e in source['elements']]):
                raise HmiError('NATIVE_CANDIDATE_SCOPE', 'Page names, dimensions and complete owner order must remain unchanged')
            for element, native in zip(screen['elements'], source['elements']):
                eid = native['id']
                if element['kind'] == 'native_preserved':
                    if (element.get('source_owner_sha256') != original.owner_extent_sha256(sid, eid)
                            or any(element[key] != native['geometry'][key] for key in ('x', 'y', 'width', 'height'))):
                        raise HmiError('NATIVE_PRESERVED_MISMATCH', 'Preserved owner hash or geometry differs from the immutable source')
                    continue
                if (element['kind'] != 'text' or (sid, eid) not in calibration['owners']
                        or set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text'}):
                    raise HmiError('NATIVE_CANDIDATE_SCOPE', 'Only calibrated existing text caption/geometry intent is supported')
                section, caption = self._literal_text_owner(document, sid, eid)
                for key, field in {'x': 'X', 'y': 'Y', 'width': 'Width', 'height': 'Height'}.items():
                    if element[key] == native['geometry'][key]:
                        # A retained numeric value is not permission to
                        # normalize its source spelling or raw byte extent.
                        continue
                    record = section.one(field)
                    value = str(element[key]).encode('ascii')
                    if len(value) != len(record.value):
                        raise HmiError('NATIVE_CANDIDATE_LENGTH', 'Changing the byte extent of a native geometry record is unqualified')
                    record.set_value(value)
                try:
                    text_length = len(element['text'].encode('utf-16-le', 'strict')) + 2
                except UnicodeEncodeError as exc:
                    raise HmiError('INVALID_TEXT', 'Primary caption contains an invalid Unicode surrogate') from exc
                if text_length != len(caption.blob):
                    raise HmiError('NATIVE_CANDIDATE_LENGTH', 'Changing the primary caption byte extent is unqualified')
                caption.set_text(element['text'])
        return original, document

    def _candidate_operations(self, session, design):
        if session['calibration']['mode'] == 'diascreen_bound_buttons':
            return self._diascreen_bound_intent(session, design)[1]
        if session['calibration']['mode'] == 'diascreen_control_append':
            return self._diascreen_control_intent(session, design)[1]
        if session['calibration']['mode'] == 'existing_edit':
            return self._edit_operations(session, design)[1]
        if session['calibration']['mode'] == 'existing_program':
            return self._existing_operations(session, design)[1]
        if session['calibration']['mode'] == 'multipage_program':
            return self._multipage_document(session, design)[2]
        if session['calibration']['mode'] == 'blank_program':
            return self._program_document(session, design)[2]
        if session['calibration']['mode'] == 'control_generation':
            return self._control_document(session, design)[2]
        if session['calibration']['mode'] == 'literal_page_generation':
            return self._generation_operations(session, design)
        self._candidate_document(session, design)
        operations = []
        for screen, source in zip(design['screens'], session['inventory']['screens']):
            for element, native in zip(screen['elements'], source['elements']):
                if element['kind'] == 'native_preserved':
                    continue
                for position, size, bound in (('x', 'width', screen['width']), ('y', 'height', screen['height'])):
                    changed = [(key, element[key]) for key in (size, position) if element[key] != native['geometry'][key]]
                    if native['geometry'][position] + element[size] > bound:
                        changed.reverse()
                    for key, value in changed:
                        operations.append(dict(op='set_property', screen_id=source['id'], element_id=native['id'], key=key, value=value))
                current = next(t['text'] for t in native['texts'] if t['state_index'] == 0 and t['language'] == 0)
                if current != element['text']:
                    operations.append(dict(op='set_text', screen_id=source['id'], element_id=native['id'], state_index=0, language=0, text=element['text']))
        return operations

    def _generation_document(self, session, design):
        """Build the whole expected body independently from approved IR.

        This deliberately does not use native operations or their setters.
        Original graph owners stay byte-exact; opaque graph dependencies are
        unknown, so this is an offline candidate experiment, not execution.
        """
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        schema = session['profile']['native_schema']
        original.verify_layout_order(schema)
        contract = schema['literal_generation']
        if any(design.get(key) for key in ('tags', 'macros', 'alarms')):
            raise HmiError('NATIVE_GENERATION_SCOPE', 'Literal page generation cannot change addresses, commands, macros or alarms')
        document = copy.deepcopy(original.document)
        pages = session['inventory']['screens']
        identity = lambda obj: str(obj.get('native_id', obj['id']))
        requested = design['screens']
        if [identity(s) for s in requested[:len(pages)]] != [s['id'] for s in pages]:
            raise HmiError('NATIVE_GENERATION_SCOPE', 'Every original page must be retained first, in source order')
        for screen, source in zip(requested, pages):
            sid = source['id']
            if (screen['name'] != source['name'] or [screen['width'], screen['height']] != session['profile']['resolution']
                    or any(source['native_fields'].get(prefix + axis) != str(screen[key])
                           for prefix in ('DocSize', 'PanelSize') for axis, key in (('X', 'width'), ('Y', 'height')))
                    or [identity(e) for e in screen['elements']] != [e['id'] for e in source['elements']]):
                raise HmiError('NATIVE_GENERATION_SCOPE', 'Original page names, dimensions and complete owner order must remain unchanged')
            for element, native in zip(screen['elements'], source['elements']):
                if (element['kind'] != 'native_preserved'
                        or set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'source_owner_sha256'}
                        or element['text'] != '' or element['source_owner_sha256'] != original.owner_extent_sha256(sid, native['id'])
                        or any(element[key] != native['geometry'][key] for key in ('x', 'y', 'width', 'height'))):
                    raise HmiError('NATIVE_GENERATION_SCOPE', 'Original owners must be represented by exact immutable native_preserved records')
        native_pages = _groups(original.document)
        header_page = next(s for s in native_pages if s['id'] == contract['page_donor']['screen_id'])
        donor_page = next(s for s in native_pages if s['id'] == contract['text_donor']['screen_id'])
        donor = next(e for e in donor_page['elements'] if e['id'] == contract['text_donor']['element_id'])
        used_pages = {s['id'] for s in native_pages}
        used_elements = {e['id'] for s in native_pages for e in s['elements']}
        for screen in requested[len(pages):]:
            sid = identity(screen)
            if (set(screen) != {'id', 'native_id', 'name', 'width', 'height', 'elements'}
                    or re.fullmatch(r'[1-9][0-9]{0,9}', sid) is None or int(sid) > 2147483647 or sid in used_pages
                    or [screen['width'], screen['height']] != session['profile']['resolution']
                    or not isinstance(screen['name'], str) or not screen['name'] or any(c in screen['name'] for c in '\r\n\0')):
                raise HmiError('NATIVE_GENERATION_SCOPE', 'New page identity, name and inherited dimensions must be explicit and valid')
            used_pages.add(sid)
            # Two sections only: never copy the source page object extent.
            header = copy.deepcopy(original.document.sections[header_page['start']:header_page['start'] + 2])
            header[0].one('ID').set_value(sid.encode('ascii'))
            header[0].one('wTextLen').set_text(screen['name'])
            document.sections.extend(header)
            for element in screen['elements']:
                eid = identity(element)
                if (element['kind'] != 'text' or set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text'}
                        or re.fullmatch(r'[1-9][0-9]{0,9}', eid) is None or int(eid) > 2147483647 or eid in used_elements):
                    raise HmiError('NATIVE_GENERATION_SCOPE', 'New owners need literal text intent and project-wide fresh positive identities')
                if (any(type(element[k]) is not int for k in ('x', 'y', 'width', 'height'))
                        or element['x'] < 0 or element['y'] < 0 or element['width'] < 1 or element['height'] < 1
                        or element['x'] + element['width'] > screen['width'] or element['y'] + element['height'] > screen['height']):
                    raise HmiError('NATIVE_GENERATION_SCOPE', 'New literal geometry must be completely inside the inherited page')
                used_elements.add(eid)
                blocks = copy.deepcopy(original.document.sections[donor['start']:donor['end']])
                blocks[0].one('nPartsID').set_value(eid.encode('ascii'))
                for key, field in {'x': 'X', 'y': 'Y', 'width': 'Width', 'height': 'Height'}.items():
                    if element[key] != int(blocks[0].one(field).value):
                        blocks[0].one(field).set_value(str(element[key]).encode('ascii'))
                blocks[1].one('wTextLen0').set_text(element['text'])
                document.sections.extend(blocks)
        return original, document

    def _generation_operations(self, session, design):
        self._generation_document(session, design)
        contract = session['profile']['native_schema']['literal_generation']
        donor = contract['text_donor']
        native = next(e for s in session['inventory']['screens'] if s['id'] == donor['screen_id']
                      for e in s['elements'] if e['id'] == donor['element_id'])
        operations = []
        for screen in design['screens'][len(session['inventory']['screens']):]:
            sid = screen['native_id']
            operations.append(dict(op='append_literal_page', screen_id=sid, name=screen['name']))
            for element in screen['elements']:
                eid = element['native_id']
                operations.append(dict(op='clone_element', source_screen=donor['screen_id'], source_element=donor['element_id'], target_screen=sid, element_id=eid))
                for position, size, bound in (('x', 'width', screen['width']), ('y', 'height', screen['height'])):
                    changed = [(key, element[key]) for key in (size, position) if element[key] != native['geometry'][key]]
                    if native['geometry'][position] + element[size] > bound:
                        changed.reverse()
                    for key, value in changed:
                        operations.append(dict(op='set_property', screen_id=sid, element_id=eid, key=key, value=value))
                text = next(t['text'] for t in native['texts'] if t['state_index'] == 0 and t['language'] == 0)
                if text != element['text']:
                    operations.append(dict(op='set_text', screen_id=sid, element_id=eid, state_index=0, language=0, text=element['text']))
        return operations

    def _candidate_matches(self, session, design, candidate):
        if session['calibration']['mode'] == 'diascreen_bound_buttons':
            _, operations = self._diascreen_bound_intent(session, design)
            self._diascreen_bound_program(session).verify(candidate, operations)
            return
        if session['calibration']['mode'] == 'diascreen_control_append':
            _, operations = self._diascreen_control_intent(session, design)
            self._diascreen_control_program(session).verify(candidate, operations)
            return
        if session['calibration']['mode'] == 'existing_edit':
            _, body, operations, assets = self._edit_expected_body(session, design)
            if candidate.envelope.body != body:
                raise HmiError('NATIVE_CANDIDATE_MISMATCH', 'Candidate differs from independent original IR/record/frame spans')
            self._edit_program(session).verify(candidate, operations, assets)
            return
        if session['calibration']['mode'] == 'existing_program':
            from .native.existing_program import ExistingProgram
            original, body, operations = self._existing_expected_body(session, design)
            if candidate.envelope.body != body:
                raise HmiError('NATIVE_CANDIDATE_MISMATCH', 'Candidate differs from independent IR/source range subtraction')
            ExistingProgram(original, session['profile']['native_schema']).verify(candidate, operations)
            return
        original, expected = self._candidate_document(session, design)
        if session['calibration']['mode'] == 'multipage_program':
            from .native.multipage import MultiPageProgram
            calibration = session['calibration']
            MultiPageProgram(original, calibration['library'], calibration['layout'],
                             session['profile']['native_schema']).verify(candidate)
        elif session['calibration']['mode'] == 'blank_program':
            from .native.program import BlankProgram
            BlankProgram(original, session['calibration']['library'], session['profile']['native_schema']).verify(candidate)
        else:
            candidate.verify_layout_order(session['profile']['native_schema'], original)
        if candidate.document.bytes() != expected.bytes():
            raise HmiError('NATIVE_CANDIDATE_MISMATCH', 'Saved bytes differ from approved text/geometry intent plus complete retained source')
        if expected.bytes() == original.document.bytes() and candidate.original != original.original:
            raise HmiError('NATIVE_CANDIDATE_MISMATCH', 'A semantic no-op must retain every original file byte')

    @staticmethod
    def _driver_authority_dir():
        return profiles_root() / 'driver_contracts'

    @staticmethod
    def _validate_address_book(book):
        keys = {'schema_version','authority_kind','family','serialized_version','driver','regions','evidence','acceptance_scope'}
        if (not isinstance(book, dict) or set(book) != keys or type(book.get('schema_version')) is not int
                or book['schema_version'] not in (1,2) or book.get('authority_kind') != 'manufacturer_static_driver_contract'
                or book.get('acceptance_scope') != 'OFFLINE_DRIVER_SYNTAX_ONLY'
                or book.get('family') not in ('delta_dopsoft2','delta_diascreen')
                or not isinstance(book.get('serialized_version'), str) or not book['serialized_version']
                or any(c in book['serialized_version'] for c in '\r\n\0')
                or not isinstance(book.get('driver'), dict) or set(book['driver']) != {'company','name'}
                or any(not isinstance(v, str) or not v or len(v)>256 or not v.isascii() or v!=v.strip()
                       or any(ord(c)<32 or ord(c)==127 for c in v) for v in book['driver'].values())
                or not isinstance(book.get('regions'), dict) or not isinstance(book.get('evidence'), dict)):
            raise HmiError('ADDRESS_AUTHORITY', 'Registered driver facts require exact typed identity, version and evidence fields')

    def _address_authority(self, namespace, profile):
        """Match an optional namespace to reviewed, installed factual data.

        Driver facts are portable repo data. A project profile cannot qualify
        arbitrary ranges merely by declaring an unrelated authority hash.
        """
        from .native.address_contract import AddressNamespace
        AddressNamespace(namespace)
        directory = self._driver_authority_dir()
        if (not directory.is_dir() or directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)()):
            raise HmiError('ADDRESS_AUTHORITY', 'A registered driver authority directory is required')
        paths = sorted(directory.glob('*.json'))
        if not 1 <= len(paths) <= 128:
            raise HmiError('ADDRESS_AUTHORITY', 'Driver authority registry is empty or exceeds its bound')
        found = []
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('ADDRESS_AUTHORITY', 'Registered driver authority must not traverse links')
            raw, book = _json_object(path, 'ADDRESS_AUTHORITY')
            if byte_hash(raw) != namespace['authority_sha256']:
                continue
            self._validate_address_book(book)
            if (book.get('family') != profile.get('family') or book.get('serialized_version') != profile.get('editor_version')
                    or book['schema_version'] != namespace['contract_version']
                    or book['driver'] != {k:namespace['driver'][k] for k in ('company','name')}
                    or book.get('regions') != namespace['regions'] or not isinstance(book.get('evidence'), dict)):
                raise HmiError('ADDRESS_AUTHORITY', 'Namespace differs from its registered driver, version or typed ranges')
            found.append((path, namespace['authority_sha256'], len(raw)))
        if len(found) != 1:
            raise HmiError('ADDRESS_AUTHORITY', 'One exact registered driver authority must match the namespace')
        return found[0]

    @staticmethod
    def _numeric_authority_dir():
        return profiles_root() / 'numeric_contracts'

    @staticmethod
    def _validate_numeric_book(book):
        keys={'schema_version','authority_kind','family','serialized_version','model_id','types',
              'value_model','max_fractional_digits','max_total_digits','input_lowering','evidence','acceptance_scope'}
        if (not isinstance(book,dict) or set(book)!=keys or type(book.get('schema_version')) is not int
                or book['schema_version']!=1 or book.get('authority_kind')!='manufacturer_static_numeric_presentation_contract'
                or book.get('acceptance_scope')!='OFFLINE_STORED_PRESENTATION_ONLY'
                or book.get('family') not in ('delta_dopsoft2','delta_diascreen')
                or not isinstance(book.get('serialized_version'),str) or not book['serialized_version']
                or len(book['serialized_version'])>256 or any(c in book['serialized_version'] for c in '\r\n\0')
                or type(book.get('model_id')) is not int or not 0<=book['model_id']<=0xffffffff
                or book.get('types')!={'UINT':{'MemLen':'1','MemFmt':'2','bits':16,'format':'unsigned'}}
                or book.get('value_model')!=FIXED_MODEL or book.get('input_lowering')!='UNVERIFIED'
                or type(book.get('max_fractional_digits')) is not int or book['max_fractional_digits']!=4
                or type(book.get('max_total_digits')) is not int or book['max_total_digits']!=5
                or not isinstance(book.get('evidence'),dict)):
            raise HmiError('NUMERIC_AUTHORITY','Registered numeric facts need exact typed identity/storage and presentation-only scope')

    def _numeric_authority(self, schema, profile, source_sha256):
        descriptor=fixed_decimal_contract(schema)
        if descriptor['source_sha256']!=source_sha256:
            raise HmiError('NUMERIC_AUTHORITY','Numeric presentation differs from its immutable source')
        directory=self._numeric_authority_dir()
        if not directory.is_dir() or directory.is_symlink() or getattr(directory,'is_junction',lambda:False)():
            raise HmiError('NUMERIC_AUTHORITY','A registered numeric authority directory is required')
        paths=sorted(directory.glob('*.json'))
        if not 1<=len(paths)<=128:
            raise HmiError('NUMERIC_AUTHORITY','Numeric authority registry is empty or exceeds its bound')
        found=[]
        for path in paths:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('NUMERIC_AUTHORITY','Registered numeric authority must not traverse links')
            raw,book=_json_object(path,'NUMERIC_AUTHORITY')
            if byte_hash(raw)!=descriptor['authority_sha256']:
                continue
            self._validate_numeric_book(book)
            if (book['family']!=profile.get('family') or book['serialized_version']!=profile.get('editor_version')
                    or book['model_id']!=profile.get('model_id') or book['types']!=(schema['numeric'].get('types') if storage_contract(schema) is None else {k:v for k,v in schema['numeric'].get('types',{}).items() if k in descriptor['types']})
                    or book['value_model']!=descriptor['mode'] or list(book['types'])!=descriptor['types']
                    or any(book[key]!=descriptor[key] for key in ('max_fractional_digits','max_total_digits','input_lowering'))):
                raise HmiError('NUMERIC_AUTHORITY','Numeric descriptor differs from its registered model/version/storage or lowering scope')
            found.append((path,descriptor['authority_sha256'],len(raw)))
        if len(found)!=1:
            raise HmiError('NUMERIC_AUTHORITY','One exact registered numeric authority must match the source contract')
        return found[0]

    @staticmethod
    def _validate_storage_book(book):
        if not isinstance(book,dict):
            raise HmiError('STORAGE_AUTHORITY','Storage book must be an object')
        for key in ('storage_from','storage_to'):
            value=book.get(key)
            if (not isinstance(value,dict) or set(value)!={'data_type','MemLen','MemFmt','bits','format'}
                    or type(value.get('bits')) is not int
                    or any(not isinstance(value.get(k),str) for k in ('data_type','MemLen','MemFmt','format'))):
                raise HmiError('STORAGE_AUTHORITY','Storage book requires bounded exact scalar type mappings')
        value=book.get('input_range')
        if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int for v in value):
            raise HmiError('STORAGE_AUTHORITY','Storage range must contain two exact integer endpoints')
        keys={'schema_version','authority_kind','family','serialized_version','model_id','mode',
              'storage_from','storage_to','permitted_storage_fields','input_range','input_relation',
              'fractional_digits','max_integer_digits','identity_scale','evidence','acceptance_scope'}
        if (not isinstance(book,dict) or set(book)!=keys or type(book.get('schema_version')) is not int
                or book['schema_version']!=1 or book.get('authority_kind')!='manufacturer_static_storage_conversion_contract'
                or book.get('family')!='delta_dopsoft2' or book.get('serialized_version')!='4.00.07.04'
                or type(book.get('model_id')) is not int or book['model_id']!=2953863504
                or book.get('mode')!='source_uint16_to_int16_f0'
                or canonical_hash(book.get('storage_from'))!=canonical_hash({'data_type':'UINT','MemLen':'1','MemFmt':'2','bits':16,'format':'unsigned'})
                or canonical_hash(book.get('storage_to'))!=canonical_hash({'data_type':'INT','MemLen':'1','MemFmt':'1','bits':16,'format':'signed'})
                or book.get('permitted_storage_fields')!=['MemFmt']
                or canonical_hash(book.get('input_range'))!=canonical_hash([-32768,32767])
                or book.get('input_relation')!='strict_minimum_less_than_maximum'
                or type(book.get('fractional_digits')) is not int or book['fractional_digits']!=0
                or type(book.get('max_integer_digits')) is not int or book['max_integer_digits']!=5
                or book.get('identity_scale')!={'gain':'1','offset':'0','roundoff':'0'}
                or book.get('acceptance_scope')!='STATIC_SOURCE_QUALIFIED_STORED_CONFIGURATION_ONLY'
                or not isinstance(book.get('evidence'),dict)):
            raise HmiError('STORAGE_AUTHORITY','Static storage facts require exact source family/model/version, width and F0 scope')
        evidence=book['evidence']
        required={'editor_sha256','renderer_sha256','native_reader','native_writer','native_setter','numeric_compiler',
                  'signed_word_range','signed_limits','compiled_format','signed_renderer','keypad_format','identity_bypass',
                  'signed_donor_property','executed_vendor_code'}
        if (set(evidence)!=required or evidence['signed_donor_property']!='NOT_FOUND'
                or evidence['executed_vendor_code'] is not False
                or evidence['editor_sha256']!='9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb'
                or evidence['renderer_sha256']!='e6fa5b74d8d73415b1fd79b16aa19fc163f95113471eb8e9e1022f8615b19ab3'
                or any(not isinstance(evidence[k],str) or not 1<=len(evidence[k])<=512
                       or any(ord(c)<32 or ord(c)==127 for c in evidence[k]) for k in required-{'executed_vendor_code'})):
            raise HmiError('STORAGE_AUTHORITY','Storage proof must preserve its exact primary evidence and absent signed-donor boundary')

    def _storage_authority(self, schema, profile, source_sha256):
        descriptor=storage_contract(schema)
        if descriptor is None or descriptor['source_sha256']!=source_sha256:
            raise HmiError('STORAGE_AUTHORITY','Storage transformation needs its exact original source')
        directory=self._numeric_authority_dir()
        if not directory.is_dir() or directory.is_symlink() or getattr(directory,'is_junction',lambda:False)():
            raise HmiError('STORAGE_AUTHORITY','A registered static storage authority directory is required')
        paths=sorted(directory.glob('*.json'))
        if not 1<=len(paths)<=128:
            raise HmiError('STORAGE_AUTHORITY','Storage authority registry is empty or oversized')
        found=[]
        for path in paths:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('STORAGE_AUTHORITY','Storage authority must not traverse links')
            raw,book=_json_object(path,'STORAGE_AUTHORITY')
            if byte_hash(raw)!=descriptor['authority_sha256']:continue
            self._validate_storage_book(book)
            if (book['family']!=profile.get('family') or book['model_id']!=profile.get('model_id')
                    or book['serialized_version']!=profile.get('editor_version') or book['mode']!=descriptor['mode']):
                raise HmiError('STORAGE_AUTHORITY','Storage proof differs from the source model/family/version')
            found.append((path,descriptor['authority_sha256'],len(raw)))
        if len(found)!=1:
            raise HmiError('STORAGE_AUTHORITY','One exact registered storage conversion authority is required')
        return found[0]

    def _diascreen_control_program(self, session):
        from .native.diascreen_control_append import DiaScreenControlAppend
        return DiaScreenControlAppend(NativeAdapter(session['source_bytes'], session['profile']['family']),
            {'diascreen_control_append': session['profile']['native_schema']['diascreen_control_append']})

    def _diascreen_bound_program(self, session):
        from .native.diascreen_bound_buttons import DiaScreenBoundButtons
        return DiaScreenBoundButtons(session['source_bytes'],
            session['profile']['native_schema']['diascreen_bound_buttons'],
            session['calibration']['namespace_authority_raw'])

    def _load_diascreen_bound_buttons(self, session, spec):
        from .native.diascreen_bound_buttons import DiaScreenBoundButtons, bound_button_contract
        schema = session['profile']['native_schema']
        if (set(spec) != {'qualified', 'contract_version', 'mode', 'path', 'sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(spec.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256'])
                or session['source_bytes'] is None or session['profile']['family'] != 'delta_diascreen'
                or set(schema) != {'qualified', 'diascreen_bound_buttons', 'native_candidate'}
                or schema.get('qualified') is not True):
            raise HmiError('NATIVE_CALIBRATION', 'Bound maintained controls need a separate exact source contract')
        descriptor = bound_button_contract(schema['diascreen_bound_buttons'])
        def metadata(relative):
            try:
                return _json_object(self._path(relative,exists=True),'NATIVE_CALIBRATION')
            except OSError as exc:
                raise HmiError('NATIVE_CALIBRATION','Bound source metadata path is missing or unreadable') from exc
        raw, witness = metadata(spec['path'])
        keys = {'contract_version', 'mode', 'source_sha256', 'family', 'model_id', 'serialized_version',
            'resolution', 'schema_sha256', 'source_origin', 'source_reference', 'review_reference',
            'review', 'namespace_authority'}
        bounded = {k:v for k,v in schema.items() if k != 'native_candidate'}
        if (byte_hash(raw) != spec['sha256'] or set(witness) != keys
                or type(witness.get('contract_version')) is not int or witness['contract_version'] != 1
                or witness['mode'] != 'diascreen_bound_buttons' or witness['family'] != 'delta_diascreen'
                or witness['source_sha256'] != session['source_sha256']
                or type(witness['model_id']) is not int or witness['model_id'] != 268502784
                or not model_ids_match(session['profile']['model_id'], witness['model_id'])
                or witness['serialized_version'] != descriptor['serialized_version']
                or session['profile']['editor_version'] != witness['serialized_version']
                or session['inventory']['editor_version'] != witness['serialized_version']
                or witness['resolution'] != [800,480] or session['profile']['resolution'] != [800,480]
                or witness['schema_sha256'] != canonical_hash(bounded)):
            raise HmiError('NATIVE_CALIBRATION', 'Bound-control witness differs from source/schema/profile')
        kinds = {'original_neutral_fixture':'synthetic', 'user_vendor_project':'user_vendor_project',
                 'manufacturer_installed_example':'manufacturer_installed_example'}
        origin = witness['source_origin']
        if not isinstance(origin,str) or origin not in kinds or session['profile'].get('fixture_kind') != kinds[origin]:
            raise HmiError('NATIVE_CALIBRATION', 'Bound-control origin must agree explicitly')
        for key in ('source_reference','review_reference'):
            if (not isinstance(witness[key],str) or not witness[key].strip() or len(witness[key]) > 1000
                    or any(c in witness[key] for c in '\r\n\0')):
                raise HmiError('NATIVE_CALIBRATION', 'Explicit bounded provenance references are required')
        review = witness['review']
        if (type(review) is not dict or set(review) != {'path','sha256'}
                or review['sha256'] != descriptor['review_sha256']):
            raise HmiError('NATIVE_CALIBRATION', 'Exact separate source review pin is required')
        review_raw, review_data = metadata(review['path'])
        self._check_diascreen_bound_review(review_data, descriptor)
        if byte_hash(review_raw) != review['sha256']:
            raise HmiError('NATIVE_CALIBRATION', 'Bound-control source review changed')
        authority = witness['namespace_authority']
        if (type(authority) is not dict or set(authority) != {'id','sha256'}
                or not isinstance(authority.get('id'),str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',authority['id'])
                or authority['sha256'] != descriptor['namespace']['authority_sha256']):
            raise HmiError('NATIVE_CALIBRATION', 'Exact portable registry address authority is required')
        authority_path = self.profiles_dir / 'driver_contracts' / (authority['id']+'.json')
        if not self._registry_file_ok(authority_path):
            raise HmiError('NATIVE_CALIBRATION', 'Address authority must remain inside the registry without links')
        authority_raw, _ = _json_object(authority_path,'NATIVE_CALIBRATION')
        if byte_hash(authority_raw) != authority['sha256']:
            raise HmiError('NATIVE_CALIBRATION', 'Registered address authority bytes differ')
        DiaScreenBoundButtons(session['source_bytes'],descriptor,authority_raw)
        return dict(path=spec['path'],sha256=spec['sha256'],bytes=len(raw),witness=witness,
            mode='diascreen_bound_buttons',owners={},namespace_authority_raw=authority_raw,
            dependency_files=[(review['path'],review['sha256'],len(review_raw))],
            registry_files=[(authority_path,authority['sha256'],len(authority_raw))])

    @staticmethod
    def _check_diascreen_bound_review(review, descriptor):
        keys = {'contract_version','scope','source_sha256','family','model_id','serialized_version',
                'donor','namespace_sha256','review_reference'}
        if (type(review) is not dict or set(review) != keys
                or type(review.get('contract_version')) is not int or review['contract_version'] != 1
                or review['scope'] != 'BOUND_BUTTON_STORED_REVIEW'
                or review['source_sha256'] != descriptor['source_sha256']
                or review['family'] != 'delta_diascreen' or type(review['model_id']) is not int
                or review['model_id'] != 268502784 or review['serialized_version'] != descriptor['serialized_version']
                or review['donor'] != descriptor['donor']
                or review['namespace_sha256'] != canonical_hash(descriptor['namespace'])
                or not isinstance(review['review_reference'],str) or not review['review_reference'].strip()
                or len(review['review_reference'])>1000 or any(c in review['review_reference'] for c in '\r\n\0')):
            raise HmiError('NATIVE_CALIBRATION','Review metadata must pin the exact original donor and namespace')

    def _diascreen_bound_intent(self, session, design):
        from .native.existing_program import _bounded
        _bounded(design)
        if design.get('macros') or design.get('alarms'):
            raise HmiError('DIA_BOUND_BUTTON','New macros/alarms are outside maintained append')
        program = self._diascreen_bound_program(session)
        original = NativeAdapter(session['source_bytes'],session['profile']['family'])
        from .native import _groups
        source_pages = _groups(original.document)
        screens = design.get('screens')
        if type(screens) is not list or len(screens) != len(source_pages):
            raise HmiError('DIA_BOUND_BUTTON','Every original page must remain in source order')
        tag_fields={'id','address','data_type','access','channel','station','native_binding'}
        tags=design.get('tags')
        if (type(tags) is not list or any(type(t) is not dict or set(t)!=tag_fields
                or not isinstance(t.get('id'),str) for t in tags)):
            raise HmiError('DIA_BOUND_BUTTON','Only explicit BOOL command tag metadata is admitted')
        tags={t['id']:t for t in tags};used=set();operations=[]
        descriptor=session['profile']['native_schema']['diascreen_bound_buttons']
        fills=program.source_metadata()['state_fills']
        kept_keys={'id','native_id','kind','x','y','width','height','text','source_owner_sha256'}
        new_keys={'id','native_id','kind','x','y','width','height','text','states','binding','behavior','role'}
        for screen,page in zip(screens,source_pages):
            if (type(screen) is not dict or set(screen)!={'id','native_id','name','width','height','elements'}
                    or screen['native_id']!=page['id'] or [screen['width'],screen['height']]!=[800,480]
                    or screen['name']!=page['section'].one('wTextLen').text()
                    or type(screen['elements']) is not list or len(screen['elements'])<len(page['elements'])):
                raise HmiError('DIA_BOUND_BUTTON','Original page identity/name/canvas/inventory must be retained')
            for element,owner in zip(screen['elements'],page['elements']):
                f=owner['section'].fields()
                if (type(element) is not dict or set(element)!=kept_keys
                        or element['native_id']!=owner['id'] or element['kind']!='native_preserved'
                        or element['text']!='' or element['source_owner_sha256']!=byte_hash(b''.join(
                            s.bytes() for s in original.document.sections[owner['start']:owner['end']]))
                        or any(type(element[k]) is not int or element[k]!=int(f[n]) for k,n in
                            (('x','X'),('y','Y'),('width','Width'),('height','Height')))):
                    raise HmiError('DIA_BOUND_BUTTON','Every original owner must remain byte-pinned and opaque')
            for element in screen['elements'][len(page['elements']):]:
                if (type(element) is not dict or set(element)!=new_keys or element['kind']!='button'
                        or element['behavior']!='maintained' or element['role']!='request' or element['text']!=''
                        or type(element['binding']) is not dict or set(element['binding'])!={'read','write'}
                        or not isinstance(element['binding']['read'],str)
                        or element['binding']['read']!=element['binding']['write']
                        or element['binding']['read'] not in tags):
                    raise HmiError('DIA_BOUND_BUTTON','Only explicit maintained same-command read/write requests are admitted')
                tag=tags[element['binding']['read']]
                binding=tag['native_binding']
                if (tag['data_type']!='BOOL' or tag['access']!='ReadWrite'
                        or type(binding) is not dict or set(binding)!={'link','mem_type'}
                        or str(binding['link'])!=descriptor['namespace']['driver']['native_link']
                        or str(binding['mem_type'])!='0'):
                    raise HmiError('DIA_BOUND_BUTTON','Command tag storage/access/native binding differs')
                # Private source namespace validates both directions and canonical grammar.
                lowered=program.match_address(tag['address'])
                if str(tag['channel'])!=lowered['channel'] or str(tag['station'])!=lowered['station']:
                    raise HmiError('DIA_BOUND_BUTTON','Tag channel/station differs from its native address')
                states=element['states']
                if (type(states) is not list or len(states)!=2 or any(type(s) is not dict
                        or set(s)!={'value','text','fill'} or type(s['value']) is not int
                        or s['value']!=v or s['fill']!=fills[v] for v,s in enumerate(states))):
                    raise HmiError('DIA_BOUND_BUTTON','Ordered state captions must retain source COLORREF metadata')
                operations.append(dict(op='append_bound_button',screen_id=page['id'],element_id=element['native_id'],
                    address=tag['address'],captions=[s['text'] for s in states],
                    **{k:element[k] for k in ('x','y','width','height')}))
                used.add(tag['id'])
        if used!=set(tags):
            raise HmiError('DIA_BOUND_BUTTON','Unused/dead tag declarations are outside the exact transaction')
        program.expected_body(operations)
        return original,operations

    def _load_diascreen_control_calibration(self, session, spec):
        """Stored copies only; no inferred logical binding or runtime semantics."""
        schema = session['profile']['native_schema']
        if (set(spec) != {'qualified', 'contract_version', 'mode', 'path', 'sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(spec.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256']) or session['source_bytes'] is None
                or set(schema) != {'qualified', 'diascreen_control_append', 'native_candidate'}
                or schema.get('qualified') is not True or session['profile']['family'] != 'delta_diascreen'
                or not isinstance(schema.get('diascreen_control_append'), dict)):
            raise HmiError('NATIVE_CALIBRATION', 'Source-control copies need the separate exact DIAScreen contract')
        raw, witness = _json_object(self._path(spec['path'], exists=True), 'NATIVE_CALIBRATION')
        keys = {'contract_version', 'mode', 'source_sha256', 'family', 'model_id', 'serialized_version',
                'resolution', 'schema_sha256', 'source_origin', 'source_reference', 'review_reference', 'authority'}
        bounded = {k: v for k, v in schema.items() if k != 'native_candidate'}
        if (byte_hash(raw) != spec['sha256'] or set(witness) != keys
                or type(witness.get('contract_version')) is not int or witness['contract_version'] != 1
                or witness['mode'] != 'diascreen_control_append'
                or witness['source_sha256'] != session['source_sha256']
                or witness['family'] != 'delta_diascreen'
                or type(witness['model_id']) is not int or witness['model_id'] != 268502784
                or not model_ids_match(session['profile']['model_id'], witness['model_id'])
                or witness['serialized_version'] != session['inventory']['editor_version']
                or session['profile']['editor_version'] != witness['serialized_version']
                or witness['resolution'] != [800, 480] or session['profile']['resolution'] != [800, 480]
                or witness['schema_sha256'] != canonical_hash(bounded)):
            raise HmiError('NATIVE_CALIBRATION', 'Source-control calibration differs from source or profile')
        origin = witness['source_origin']
        kinds = {'original_neutral_fixture': 'synthetic', 'user_vendor_project': 'user_vendor_project',
                 'manufacturer_installed_example': 'manufacturer_installed_example'}
        if not isinstance(origin, str) or origin not in kinds or session['profile'].get('fixture_kind') != kinds[origin]:
            raise HmiError('NATIVE_CALIBRATION', 'Source-control origin and profile must agree explicitly')
        for key in ('source_reference', 'review_reference'):
            if (not isinstance(witness[key], str) or not witness[key].strip()
                    or len(witness[key]) > 1000 or any(c in witness[key] for c in '\r\n\0')):
                raise HmiError('NATIVE_CALIBRATION', 'Source-control provenance references must be explicit')
        authority = witness['authority']
        if (not isinstance(authority, dict) or set(authority) != {'path', 'sha256'}
                or authority['sha256'] != schema['diascreen_control_append'].get('authority_sha256')):
            raise HmiError('NATIVE_CALIBRATION', 'Source-control review artifact must be pinned separately')
        review_raw, review = _json_object(self._path(authority['path'], exists=True), 'NATIVE_CALIBRATION')
        self._check_diascreen_control_authority(review, schema['diascreen_control_append'])
        if byte_hash(review_raw) != authority['sha256']:
            raise HmiError('NATIVE_CALIBRATION', 'Source-control review artifact changed')
        self._diascreen_control_program(session).check()
        return dict(path=spec['path'], sha256=spec['sha256'], bytes=len(raw), witness=witness,
                    mode='diascreen_control_append', owners={},
                    dependency_files=[(authority['path'], authority['sha256'], len(review_raw))])

    @staticmethod
    def _check_diascreen_control_authority(review, descriptor):
        keys = {'contract_version', 'scope', 'source_sha256', 'family', 'model_id',
                'serialized_version', 'donors', 'review_reference'}
        if (not isinstance(review, dict) or set(review) != keys
                or type(review.get('contract_version')) is not int or review['contract_version'] != 1
                or review['scope'] != 'STORED_CONTROL_APPEND_REVIEW'
                or review['source_sha256'] != descriptor.get('source_sha256')
                or review['family'] != 'delta_diascreen'
                or type(review['model_id']) is not int or review['model_id'] != 268502784
                or review['serialized_version'] != descriptor.get('editor_version')
                or review['donors'] != descriptor.get('donors')
                or not isinstance(review['review_reference'], str) or not review['review_reference'].strip()
                or len(review['review_reference']) > 1000 or any(c in review['review_reference'] for c in '\r\n\0')):
            raise HmiError('NATIVE_CALIBRATION', 'Source review must identify the exact immutable donors and stored-only scope')

    def _diascreen_control_intent(self, session, design):
        if any(design.get(k) for k in ('tags', 'macros', 'alarms')):
            raise HmiError('DIA_CONTROL_SCOPE', 'Stored source clones cannot declare tags, macros or alarms')
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        self._diascreen_control_program(session).check()
        # All page/owner extents have just passed the source-byte check. Hash
        # each complete extent once, without re-traversing a page per owner.
        from .native import _groups
        source_owner_hashes = {
            (page['id'], owner['id']): byte_hash(b''.join(
                part.bytes() for part in original.document.sections[owner['start']:owner['end']]))
            for page in _groups(original.document) for owner in page['elements']}
        source_pages = session['inventory']['screens']
        screens = design.get('screens')
        identity = lambda obj: str(obj.get('native_id', obj['id']))
        if not isinstance(screens, list) or len(screens) != len(source_pages):
            raise HmiError('DIA_CONTROL_SCOPE', 'Every source page must remain in source order')
        operations = []
        descriptor = session['profile']['native_schema']['diascreen_control_append']
        for screen, source in zip(screens, source_pages):
            if (set(screen) != {'id', 'native_id', 'name', 'width', 'height', 'elements'}
                    or identity(screen) != source['id'] or screen['name'] != source['name']
                    or [screen['width'], screen['height']] != [int(source['native_fields'][k]) for k in ('DocSizeX', 'DocSizeY')]
                    or len(screen['elements']) < len(source['elements'])):
                raise HmiError('DIA_CONTROL_SCOPE', 'Original page identity, size and complete owners must be preserved')
            for element, native in zip(screen['elements'], source['elements']):
                if (set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'source_owner_sha256'}
                        or identity(element) != native['id'] or element['kind'] != 'native_preserved'
                        or element['text'] != '' or element['source_owner_sha256'] != source_owner_hashes[(source['id'], native['id'])]
                        or any(element[k] != native['geometry'][k] for k in ('x', 'y', 'width', 'height'))):
                    raise HmiError('DIA_CONTROL_SCOPE', 'Original source owners cannot be edited, omitted or reinterpreted')
            for element in screen['elements'][len(source['elements']):]:
                if (set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'source_owner_sha256', 'clone'}
                        or element['kind'] != 'native_control_clone' or element['text'] != ''
                        or not isinstance(element['clone'], dict) or set(element['clone']) != {'donor_kind', 'captions'}):
                    raise HmiError('DIA_CONTROL_SCOPE', 'New owners need exact stored source-clone declarations')
                clone = element['clone']; donor = descriptor['donors'].get(clone.get('donor_kind'))
                if not isinstance(donor, dict) or element['source_owner_sha256'] != donor['owner_sha256']:
                    raise HmiError('DIA_CONTROL_SCOPE', 'Clone provenance differs from its immutable donor')
                operations.append(dict(op='append_control', screen_id=source['id'], element_id=identity(element),
                    donor_kind=clone['donor_kind'], captions=copy.deepcopy(clone['captions']),
                    **{k: element[k] for k in ('x', 'y', 'width', 'height')}))
        self._diascreen_control_program(session).expected_body(operations)
        return original, operations

    def _load_control_calibration(self, session, spec):
        """Bind a stored-configuration witness, never vendor/runtime acceptance."""
        if (set(spec) != {'qualified', 'contract_version', 'mode', 'path', 'sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(spec.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256']) or session['source_bytes'] is None):
            raise HmiError('NATIVE_CALIBRATION', 'Control candidate needs an exact source-local witness')
        path = self._path(spec['path'], exists=True)
        raw, witness = _json_object(path, 'NATIVE_CALIBRATION')
        schema = session['profile']['native_schema']
        bounded = {key: value for key, value in schema.items() if key != 'native_candidate'}
        required = {'contract_version', 'mode', 'source_sha256', 'family', 'model_id', 'serialized_version',
                    'resolution', 'schema_sha256', 'source_origin', 'source_reference', 'review_reference', 'properties'}
        if (byte_hash(raw) != spec['sha256'] or set(witness) != required
                or type(witness['contract_version']) is not int or witness['contract_version'] != 1
                or witness['mode'] != 'control_generation' or witness['source_origin'] != 'user_vendor_project'
                or session['profile'].get('fixture_kind') == 'synthetic'
                or witness['schema_sha256'] != canonical_hash(bounded)
                or witness['source_sha256'] != session['source_sha256']
                or witness['family'] != session['profile']['family']
                or witness['model_id'] != canonical_model_id(session['inventory']['model_id'])
                or witness['serialized_version'] != session['inventory']['editor_version']
                or witness['resolution'] != session['profile']['resolution']):
            raise HmiError('NATIVE_CALIBRATION', 'Control witness differs from immutable source/profile')
        for key in ('source_reference', 'review_reference'):
            if not isinstance(witness[key], str) or not witness[key].strip() or len(witness[key]) > 1000 or any(c in witness[key] for c in '\r\n\0'):
                raise HmiError('NATIVE_CALIBRATION', 'Control source and review references must be explicit')
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        original._schema(session['profile'])
        authorities = [self._address_authority(schema['address_namespace'], session['profile'])] if 'address_namespace' in schema else []
        if isinstance(schema.get('numeric'), dict) and 'value_models' in schema['numeric']:
            authorities.append(self._numeric_authority(schema, session['profile'], session['source_sha256']))
        if 'storage_conversion' in schema:
            authorities.append(self._storage_authority(schema, session['profile'], session['source_sha256']))
        original.verify_control_generation(schema)
        properties = witness['properties']
        pins = schema['control_generation']['donors']
        if not isinstance(properties, dict) or set(properties) != set(pins) or not properties:
            raise HmiError('NATIVE_CALIBRATION', 'Every control donor needs a property image witness')
        files = []
        for kind, evidence in properties.items():
            if not isinstance(evidence, dict) or set(evidence) != {'path', 'sha256'} or evidence['sha256'] != pins[kind].get('property_witness_sha256'):
                raise HmiError('NATIVE_CALIBRATION', 'Property witness does not match the donor pin')
            image_path = self._path(evidence['path'], exists=True)
            with image_path.open('rb') as image_file:
                image_bytes = image_file.read(10 * 1024 * 1024 + 1)
            if (len(image_bytes) > 10 * 1024 * 1024 or not (image_bytes.startswith(b'\x89PNG\r\n\x1a\n') or image_bytes.startswith(b'\xff\xd8\xff'))
                    or byte_hash(image_bytes) != evidence['sha256']):
                raise HmiError('NATIVE_CALIBRATION', 'A property image changed or is not bounded PNG/JPEG data')
            files.append((image_path, evidence['sha256'], len(image_bytes)))
        return dict(path=spec['path'], sha256=spec['sha256'], bytes=len(raw), witness=witness,
                    mode='control_generation', owners={}, property_files=files, registry_files=authorities)

    def _load_program_calibration(self, session, spec):
        """Open an immutable blank target and separate source-qualified library."""
        from .native.program import BlankProgram
        if (set(spec) != {'qualified','contract_version','mode','path','sha256'}
                or spec.get('qualified') is not True or type(spec.get('contract_version')) is not int
                or spec['contract_version'] != 1 or not isinstance(spec.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256']) or session['source_bytes'] is None):
            raise HmiError('NATIVE_CALIBRATION', 'Blank program needs its exact source-local witness')
        raw, witness = _json_object(self._path(spec['path'], exists=True), 'NATIVE_CALIBRATION')
        required = {'contract_version','mode','target_sha256','family','model_id','serialized_version',
                    'resolution','schema_sha256','source_origin','source_reference','review_reference','library'}
        schema = session['profile']['native_schema']
        if (byte_hash(raw) != spec['sha256'] or set(witness) != required
                or type(witness.get('contract_version')) is not int or witness['contract_version'] != 1
                or witness['mode'] != 'blank_program' or witness['source_origin'] != 'user_vendor_project'
                or session['profile'].get('fixture_kind') == 'synthetic'
                or witness['schema_sha256'] != canonical_hash({k:v for k,v in schema.items() if k != 'native_candidate'})
                or witness['target_sha256'] != session['source_sha256'] or witness['family'] != session['profile']['family']
                or witness['model_id'] != canonical_model_id(session['inventory']['model_id'])
                or witness['serialized_version'] != session['inventory']['editor_version']
                or witness['resolution'] != session['profile']['resolution']):
            raise HmiError('NATIVE_CALIBRATION', 'Blank target witness differs from immutable source/profile')
        for key in ('source_reference','review_reference'):
            if not isinstance(witness[key], str) or not witness[key].strip() or len(witness[key]) > 1000 or any(c in witness[key] for c in '\r\n\0'):
                raise HmiError('NATIVE_CALIBRATION', 'Blank source and review references must be explicit')
        lib = witness['library']
        if not isinstance(lib, dict) or set(lib) != {'path','sha256','profile_path','profile_sha256'}:
            raise HmiError('NATIVE_CALIBRATION', 'An exact separate library and source profile are required')
        for key in ('sha256','profile_sha256'):
            if not isinstance(lib[key], str) or not re.fullmatch(r'[0-9a-f]{64}', lib[key]):
                raise HmiError('NATIVE_CALIBRATION', 'Library fingerprints must be canonical SHA-256')
        profile_bytes, profile = _json_object(self._path(lib['profile_path'], exists=True), 'NATIVE_CALIBRATION')
        self._validate_profile(profile)
        with self._path(lib['path'], exists=True).open('rb') as stream:
            from .native.codec import MAX_PAYLOAD
            library_bytes = stream.read(MAX_PAYLOAD + 1)
        if len(library_bytes) > MAX_PAYLOAD or byte_hash(library_bytes) != lib['sha256'] or byte_hash(profile_bytes) != lib['profile_sha256']:
            raise HmiError('NATIVE_CALIBRATION', 'Library source/profile is changed or oversized')
        if profile.get('family') != session['profile']['family'] or not isinstance(profile.get('native_schema'), dict):
            raise HmiError('NATIVE_CALIBRATION', 'Library profile does not match the target family')
        library = NativeAdapter(library_bytes, session['profile']['family'])
        library_session = dict(source_bytes=library_bytes, source_sha256=lib['sha256'], profile=profile, inventory=library.inspect())
        library_spec = profile['native_schema'].get('native_candidate')
        if not isinstance(library_spec, dict) or library_spec.get('mode') != 'control_generation':
            raise HmiError('NATIVE_CALIBRATION', 'Library must have a six-control property/source calibration')
        library_calibration = self._load_control_calibration(library_session, library_spec)
        library_session['calibration'] = library_calibration
        target = NativeAdapter(session['source_bytes'], session['profile']['family'])
        target._schema(session['profile'])
        program = BlankProgram(target, library, schema)
        program.check()
        if schema['blank_program']['library_schema'] != {k:v for k,v in profile['native_schema'].items() if k != 'native_candidate'}:
            raise HmiError('NATIVE_CALIBRATION', 'Program library schema differs from its property-qualified source')
        dependencies = [(lib['path'], lib['sha256'],len(library_bytes)),
                        (lib['profile_path'],lib['profile_sha256'],len(profile_bytes)),
                        (library_spec['path'],library_calibration['sha256'],library_calibration['bytes'])]
        return dict(path=spec['path'], sha256=spec['sha256'], bytes=len(raw), witness=witness,
                    mode='blank_program', owners={}, library=library, library_session=library_session,
                    property_files=library_calibration['property_files'], dependency_files=dependencies,
                    registry_files=library_calibration.get('registry_files', []))

    @staticmethod
    def _layout_authority_dir():
        return profiles_root() / 'layout_contracts'

    def _layout_authority(self, descriptor, profile):
        """A project cannot authorize auxiliary donors with a qualified flag.

        Portable reviewed facts bind the actual model/version, complete source
        extent and property hashes. Registry hashes participate in freshness.
        """
        directory = self._layout_authority_dir()
        if not directory.is_dir() or directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)():
            raise HmiError('LAYOUT_AUTHORITY', 'A registered layout authority directory is required')
        paths = sorted(directory.glob('*.json'))
        if not 1 <= len(paths) <= 128:
            raise HmiError('LAYOUT_AUTHORITY', 'Layout authority registry is empty or exceeds its bound')
        matches = []
        keys = {'schema_version','authority_kind','family','serialized_version','model_id',
                'layout_sha256','page_donor','aux_donors','new_page_action','page_id_max','evidence','acceptance_scope'}
        for path in paths:
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or not path.resolve().is_relative_to(directory.resolve()):
                raise HmiError('LAYOUT_AUTHORITY', 'Registered layout authority must not traverse links')
            raw, book = _json_object(path, 'LAYOUT_AUTHORITY')
            if byte_hash(raw) != descriptor.get('authority_sha256'):
                continue
            if (set(book) != keys or type(book['schema_version']) is not int or book['schema_version'] != 1
                    or book['authority_kind'] != 'vendor_source_static_layout_contract'
                    or book['acceptance_scope'] != 'OFFLINE_STORED_LAYOUT_ONLY'
                    or type(book['model_id']) is not int or not 0 <= book['model_id'] <= 0xffffffff
                    or type(book['new_page_action']) is not int or book['new_page_action'] != 0
                    or type(book['page_id_max']) is not int or book['page_id_max'] != 65535
                    or not isinstance(book['evidence'], dict)
                    or book['family'] != profile['family'] or book['serialized_version'] != profile['editor_version']
                    or book['model_id'] != profile['model_id']
                    or any(book[key] != descriptor.get(key) for key in ('layout_sha256','page_donor','aux_donors'))):
                raise HmiError('LAYOUT_AUTHORITY', 'Auxiliary layout differs from the registered model/version/source contract')
            matches.append((path, byte_hash(raw), len(raw)))
        if len(matches) != 1:
            raise HmiError('LAYOUT_AUTHORITY', 'One exact reviewed layout authority must match the source contract')
        return matches[0]

    def _load_multipage_calibration(self, session, spec):
        from .native.multipage import MultiPageProgram
        from .native.codec import MAX_PAYLOAD
        reject = lambda message: HmiError('NATIVE_CALIBRATION', message)
        if (set(spec) != {'qualified','contract_version','mode','path','sha256'} or spec.get('qualified') is not True
                or type(spec.get('contract_version')) is not int or spec['contract_version'] != 1
                or not isinstance(spec.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', spec['sha256'])
                or session['source_bytes'] is None):
            raise reject('Multipage emission requires an exact source-local witness')
        raw, witness = _json_object(self._path(spec['path'], exists=True), 'NATIVE_CALIBRATION')
        schema, profile = session['profile']['native_schema'], session['profile']
        required = {'contract_version','mode','target_sha256','family','model_id','serialized_version',
                    'resolution','schema_sha256','source_origin','source_reference','review_reference','controls','layout'}
        if (byte_hash(raw) != spec['sha256'] or set(witness) != required
                or type(witness['contract_version']) is not int or witness['contract_version'] != 1
                or witness['mode'] != 'multipage_program' or witness['source_origin'] != 'user_vendor_project'
                or profile.get('fixture_kind') == 'synthetic'
                or witness['schema_sha256'] != canonical_hash({k:v for k,v in schema.items() if k != 'native_candidate'})
                or witness['target_sha256'] != session['source_sha256'] or witness['family'] != profile['family']
                or type(witness['model_id']) is not int or witness['model_id'] != canonical_model_id(session['inventory']['model_id'])
                or witness['serialized_version'] != session['inventory']['editor_version'] or witness['resolution'] != profile['resolution']):
            raise reject('Multipage witness differs from immutable target/profile')
        for key in ('source_reference','review_reference'):
            if not isinstance(witness[key], str) or not witness[key].strip() or len(witness[key]) > 1000 or any(c in witness[key] for c in '\r\n\0'):
                raise reject('Multipage source and review references must be explicit')
        lib, aux = witness['controls'], witness['layout']
        if (not isinstance(lib, dict) or set(lib) != {'path','sha256','profile_path','profile_sha256'}
                or not isinstance(aux, dict) or set(aux) != {'path','sha256','properties'}):
            raise reject('Separate immutable control and auxiliary sources are required')
        for obj, key in ((lib,'sha256'),(lib,'profile_sha256'),(aux,'sha256')):
            if not isinstance(obj[key], str) or not re.fullmatch(r'[0-9a-f]{64}', obj[key]):
                raise reject('Source digests must be canonical SHA-256')
        library_profile_bytes, library_profile = _json_object(self._path(lib['profile_path'], exists=True), 'NATIVE_CALIBRATION')
        self._validate_profile(library_profile)
        def native_bytes(reference):
            with self._path(reference['path'], exists=True).open('rb') as stream:
                data = stream.read(MAX_PAYLOAD + 1)
            if len(data) > MAX_PAYLOAD or byte_hash(data) != reference['sha256']:
                raise reject('Native library changed or exceeds its bound')
            return data
        library_bytes, layout_bytes = native_bytes(lib), native_bytes(aux)
        if byte_hash(library_profile_bytes) != lib['profile_sha256'] or library_profile['family'] != profile['family']:
            raise reject('Control profile changed or differs from the target family')
        library, layout = NativeAdapter(library_bytes, profile['family']), NativeAdapter(layout_bytes, profile['family'])
        library_session = dict(source_bytes=library_bytes, source_sha256=lib['sha256'], profile=library_profile, inventory=library.inspect())
        library_spec = library_profile['native_schema'].get('native_candidate')
        if not isinstance(library_spec, dict) or library_spec.get('mode') != 'control_generation':
            raise reject('Control library needs the existing six-donor calibration')
        library_calibration = self._load_control_calibration(library_session, library_spec)
        library_session['calibration'] = library_calibration
        target = NativeAdapter(session['source_bytes'], profile['family'])
        target._schema(profile)
        MultiPageProgram(target, library, layout, schema).check()
        descriptor = schema['multipage_program']
        if descriptor['controls_schema'] != {k:v for k,v in library_profile['native_schema'].items() if k != 'native_candidate'}:
            raise reject('Control mappings differ from their immutable property-qualified source')
        registry_files = [*library_calibration.get('registry_files', []), self._layout_authority(descriptor, profile)]
        properties = aux['properties']
        if not isinstance(properties, dict) or set(properties) != set(descriptor['aux_donors']):
            raise reject('Every auxiliary donor requires its pinned property witness')
        files = list(library_calibration['property_files'])
        for kind, reference in properties.items():
            if (not isinstance(reference, dict) or set(reference) != {'path','sha256'}
                    or reference['sha256'] != descriptor['aux_donors'][kind]['property_witness_sha256']):
                raise reject('Auxiliary property witness differs from its registered pin')
            path = self._path(reference['path'], exists=True)
            data, observed = _json_object(path, 'NATIVE_CALIBRATION')
            if (byte_hash(data) != reference['sha256'] or observed.get('scope') != 'VENDOR_CREATED_REFERENCE_PROPERTY_ONLY'
                    or observed.get('type') != {'text':'Literal Text','indicator':'Multistate Indicator','goto':'Goto Screen'}[kind]):
                raise reject('Auxiliary property metadata changed or lacks its explicit reference scope')
            files.append((path, reference['sha256'], len(data)))
        dependencies = [(lib['path'],lib['sha256'],len(library_bytes)),
                        (lib['profile_path'],lib['profile_sha256'],len(library_profile_bytes)),
                        (library_spec['path'],library_calibration['sha256'],library_calibration['bytes']),
                        (aux['path'],aux['sha256'],len(layout_bytes))]
        return dict(path=spec['path'],sha256=spec['sha256'],bytes=len(raw),witness=witness,
                    mode='multipage_program',owners={},library=library,layout=layout,library_session=library_session,
                    property_files=files,dependency_files=dependencies,registry_files=registry_files)

    def _multipage_document(self, session, design):
        """Independent IR expectation; never execute the operation emitter.

        Typed six-control bytes come from the existing strict IR compiler on
        its original donor context. Only generated owner extents enter the
        final graph. Auxiliary extents and page headers are patched directly
        from immutable raw donors; globals and resources belong to the target.
        """
        from .native.multipage import MultiPageProgram
        if any(design.get(key) for key in ('macros','alarms')):
            raise HmiError('MULTIPAGE_SCOPE', 'Multipage assembly preserves macro/alarm resources')
        calibration, schema = session['calibration'], session['profile']['native_schema']
        target = NativeAdapter(session['source_bytes'], session['profile']['family'])
        library, layout = calibration['library'], calibration['layout']
        MultiPageProgram(target, library, layout, schema).check()
        contract = schema['multipage_program']
        source = calibration['library_session']['inventory']['screens'][0]
        requested = design['screens']
        identity = lambda value: str(value.get('native_id', value['id']))
        originals = _groups(target.document)
        if not requested or len(requested) > 256 or sum(len(s['elements']) for s in requested) > 4096:
            raise HmiError('MULTIPAGE_SCOPE', 'Program needs one to 256 pages and at most 4096 objects')
        sid_map, used_owners = {}, {owner['id'] for page in _groups(library.document) for owner in page['elements']}
        for index, screen in enumerate(requested):
            sid, name = identity(screen), screen['name']
            if (set(screen) != {'id','native_id','name','width','height','elements'}
                    or not re.fullmatch(r'[1-9][0-9]{0,4}', sid) or int(sid) > 65535 or sid in sid_map
                    or [screen['width'],screen['height']] != session['profile']['resolution']
                    or not isinstance(name,str) or not name or len(name)>128 or not name.isascii() or name != name.strip()
                    or any(ord(c)<32 or ord(c)>126 for c in name)):
                raise HmiError('MULTIPAGE_SCOPE', 'Pages require unique uint16 IDs, printable ASCII names and exact target dimensions')
            if index == 0 and (sid != originals[0]['id'] or name != session['inventory']['screens'][0]['name']):
                raise HmiError('MULTIPAGE_SCOPE', 'The original blank first page ID/name must remain exact')
            sid_map[sid] = name
            for element in screen['elements']:
                eid = identity(element)
                if not re.fullmatch(r'[1-9][0-9]{0,9}',eid) or int(eid)>2147483647 or eid in used_owners:
                    raise HmiError('DUPLICATE_ELEMENT', 'New owners require project-wide unique IDs, distinct from the six source donors')
                used_owners.add(eid)
        controls = [copy.deepcopy(e) for s in requested for e in s['elements'] if e['kind'] in {'button','numeric_input','numeric_display'}]
        stage = copy.deepcopy(design)
        stage['profile_id'] = calibration['library_session']['profile']['id']
        retained = [dict(id='source_reference_'+source['id']+'_'+e['id'],native_id=e['id'],kind='native_preserved',
                         text='',**e['geometry'],source_owner_sha256=library.owner_extent_sha256(source['id'],e['id']))
                    for e in source['elements']]
        stage['screens'] = [dict(id=source['id'],native_id=source['id'],name=source['name'],
                                 width=source['native_fields']['DocSizeX'],height=source['native_fields']['DocSizeY'],elements=retained+controls)]
        stage['screens'][0]['width'],stage['screens'][0]['height'] = session['profile']['resolution']
        _, expected_controls, control_ops = self._control_document(calibration['library_session'], stage)
        generated = {owner['id']:copy.deepcopy(expected_controls.sections[owner['start']:owner['end']])
                     for owner in _groups(expected_controls)[0]['elements'][len(source['elements']):]}
        destinations = {identity(e):identity(s) for s in requested for e in s['elements']}
        for operation in control_ops:
            destination = destinations[operation['element_id']]
            operation['target_screen' if operation['op']=='clone_element' else 'screen_id'] = destination
        graph = dict(op='set_program_layout',screens=[dict(screen_id=identity(s),name=s['name'],elements=[identity(e) for e in s['elements']]) for s in requested])
        aux_ops, bound_indicator = [], False
        document = copy.deepcopy(target.document)
        document.sections = copy.deepcopy(target.document.sections[:originals[0]['start']])
        layout_pages = _groups(layout.document)
        donor_page = next(p for p in layout_pages if p['id']==contract['page_donor']['screen_id'])
        tags = {tag['id']:tag for tag in design['tags']}
        for index, screen in enumerate(requested):
            sid = identity(screen)
            if index == 0:
                header = copy.deepcopy(target.document.sections[originals[0]['start']:originals[0]['start']+2])
            else:
                header = copy.deepcopy(layout.document.sections[donor_page['start']:donor_page['start']+2])
                header[0].one('ID').set_value(sid.encode('ascii'))
                header[0].one('wTextLen').set_text(screen['name'])
                header[0].one('wScreenDESCTextLen000').set_text(screen['name'])
                header[0].one('ScreenAction').set_value(b'0')
            document.sections.extend(header)
            for element in screen['elements']:
                eid, kind = identity(element), element['kind']
                if eid in generated:
                    document.sections.extend(generated[eid])
                    continue
                if kind not in {'text','indicator','goto'}:
                    raise HmiError('MULTIPAGE_SCOPE', 'Object kind lacks an exact same-model auxiliary donor')
                allowed = {'id','native_id','kind','x','y','width','height','font_size','color','fill'}
                allowed |= {'text'} if kind=='text' else {'text','target_screen'} if kind=='goto' else {'states','binding','role','text'}
                if set(element)-allowed:
                    raise HmiError('MULTIPAGE_SCOPE', 'Auxiliary intent contains unqualified fields')
                pin = contract['aux_donors'][kind]
                page = next(p for p in layout_pages if p['id']==pin['screen_id'])
                owner = next(e for e in page['elements'] if e['id']==pin['element_id'])
                clone = copy.deepcopy(layout.document.sections[owner['start']:owner['end']])
                operation = dict(op='create_aux',kind=kind,screen_id=sid,element_id=eid,
                                 **{k:element[k] for k in ('x','y','width','height')})
                clone[0].one('nPartsID').set_value(eid.encode('ascii'))
                for key, field in {'x':'X','y':'Y','width':'Width','height':'Height'}.items():
                    clone[0].one(field).set_value(str(element[key]).encode('ascii'))
                if kind == 'indicator':
                    if set(element.get('binding',{}))!={'read'}:
                        raise HmiError('CONTROL_ADDRESS_SCOPE', 'Indicators require one read binding and cannot write')
                    tag = tags[element['binding']['read']]
                    prefix = contract['controls_schema']['control_generation']['address_prefix']
                    library._control_address(tag['address'],prefix,'M',contract['controls_schema'])
                    expected_binding = dict(link=int(clone[0].one('ReadLink').value),mem_type=int(clone[0].one('ReadMemType').value))
                    if (tag['data_type']!='BOOL' or tag.get('native_binding')!=expected_binding
                            or tag.get('channel')!=prefix.split('}')[0][1:] or str(tag.get('station'))!=prefix.split('}')[1][:-1]
                            or tag.get('byte_order')!='device_default' or tag.get('word_order')!='device_default'):
                        raise HmiError('CONTROL_ADDRESS_SCOPE', 'Indicator differs from the source BOOL read metadata')
                    clone[0].one('ReadVar').set_value(tag['address'].encode('ascii'))
                    operation['read'] = dict(address=tag['address'],**expected_binding)
                    states = element.get('states')
                    if (not isinstance(states,list) or len(states)!=2 or [s.get('value') for s in states]!=[0,1]
                            or any(set(s)!={'value','text','fill'} or type(s['value']) is not int for s in states)):
                        raise HmiError('MULTIPAGE_SCOPE', 'Bit indicators need explicit ordered Value0/1 text and fill')
                    bound_indicator = True
                else:
                    states = [dict(value=0,text=element['text'])]
                    operation['text'] = element['text']
                    if kind == 'goto':
                        destination = next((identity(s) for s in requested if s['id']==element['target_screen']),None)
                        if destination not in sid_map:
                            raise HmiError('MULTIPAGE_SCOPE', 'Goto must target a final declared page')
                        clone[0].one('GoToScreenID').set_value(destination.encode('ascii'))
                        clone[0].one('GoToScreenName').set_value(sid_map[destination].encode('ascii'))
                        operation['target_screen'] = destination
                native_states = []
                for index, declared in enumerate(states):
                    clone[index+1].one('wTextLen0').set_text(declared['text'])
                    styles = {k:element[k] for k in ('font_size','color','fill') if k in element}
                    if 'fill' in declared:
                        styles['fill'] = declared['fill']
                    converted = {}
                    for key, value in styles.items():
                        if key!='font_size':
                            if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value) or value[1:3].lower()!=value[5:7].lower():
                                raise HmiError('CONTROL_COLOR_UNVERIFIED', 'Color byte order is unqualified; R/B-equivalent colors only')
                            value = int(value[1:],16)
                        elif type(value) is not int or not 1<=value<=128:
                            raise HmiError('MULTIPAGE_SCOPE', 'Qualified font size is an integer from one to128')
                        clone[index+1].one({'font_size':'FontSize0','color':'FontColor','fill':'BgColor'}[key]).set_value(str(value).encode('ascii'))
                        converted[key] = value
                    native_states.append(dict(value=declared['value'],text=declared['text'],**({'fill':converted['fill']} if kind=='indicator' else {})))
                if kind=='indicator':
                    operation['states'] = native_states
                for key in ('font_size','color','fill'):
                    if key in element:
                        operation[key] = element[key] if key=='font_size' else int(element[key][1:],16)
                aux_ops.append(operation)
                document.sections.extend(clone)
        document.tail = library.document.tail if controls or bound_indicator else target.document.tail
        return target, document, [graph,*control_ops,*aux_ops]

    def _program_document(self, session, design):
        """Independent IR bytes: library donor clones placed on a blank target."""
        from .native.program import BlankProgram
        target = NativeAdapter(session['source_bytes'], session['profile']['family'])
        library = session['calibration']['library']
        program = BlankProgram(target, library, session['profile']['native_schema'])
        program.check()
        library_session = session['calibration']['library_session']
        expanded = copy.deepcopy(design)
        expanded['profile_id'] = library_session['profile']['id']
        source_pages = library_session['inventory']['screens']
        if len(expanded['screens']) != len(source_pages):
            raise HmiError('BLANK_PROGRAM_SCOPE', 'Intent must cover every blank target page')
        for screen, source in zip(expanded['screens'], source_pages):
            screen['elements'] = [dict(id='source_reference_'+source['id']+'_'+e['id'],native_id=e['id'],
                kind='native_preserved',text='',**e['geometry'],
                source_owner_sha256=library.owner_extent_sha256(source['id'],e['id'])) for e in source['elements']] + screen['elements']
        _, expected_library, operations = self._control_document(library_session, expanded)
        document = copy.deepcopy(target.document)
        target_pages, library_pages = _groups(target.document), _groups(expected_library)
        result = list(document.sections[:target_pages[0]['start']])
        count = 0
        for page, generated, source in zip(target_pages, library_pages, source_pages):
            result.extend(copy.deepcopy(target.document.sections[page['start']:page['end']]))
            for owner in generated['elements'][len(source['elements']):]:
                result.extend(copy.deepcopy(expected_library.sections[owner['start']:owner['end']]))
                count += 1
        document.sections = result
        # Lineage check proves this tail differs solely by the exact vendor-
        # witnessed empty Tag initialization. No native tail patcher is reused.
        document.tail = library.document.tail if count else target.document.tail
        return target, document, operations

    def _emit(self, session, operations, design=None):
        source = NativeAdapter(session['source_bytes'], session['profile']['family'])
        if session.get('calibration') is not None and session['calibration']['mode'] == 'diascreen_bound_buttons':
            return self._diascreen_bound_program(session).apply(operations)
        if session.get('calibration') is not None and session['calibration']['mode'] == 'diascreen_control_append':
            return self._diascreen_control_program(session).apply(operations)
        if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_edit':
            assets = self._edit_assets(design)[0]
            return self._edit_program(session).apply(operations, assets)
        if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_program':
            from .native.existing_program import ExistingProgram
            return ExistingProgram(source, session['profile']['native_schema']).apply(operations)
        if session.get('calibration') is not None and session['calibration']['mode'] == 'multipage_program':
            from .native.multipage import MultiPageProgram
            calibration = session['calibration']
            return MultiPageProgram(source, calibration['library'], calibration['layout'],
                                    session['profile']['native_schema']).apply(operations)
        if session.get('calibration') is not None and session['calibration']['mode'] == 'blank_program':
            from .native.program import BlankProgram
            return BlankProgram(source, session['calibration']['library'], session['profile']['native_schema']).apply(operations)
        return source.apply(operations, session['profile'])

    def _control_document(self, session, design):
        """Append typed controls; independent whole-body expectation from IR.

        Reference owners are retained and explicitly shown in the IR. This is
        an adapter development candidate, not a new machine program.
        """
        if any(design.get(key) for key in ('macros', 'alarms')):
            raise HmiError('CONTROL_GENERATION_SCOPE', 'This control milestone preserves macro/alarm resources')
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        schema = session['profile']['native_schema']
        donors = original.control_donors(schema)
        document = copy.deepcopy(original.document)
        source_pages = session['inventory']['screens']
        pages = _groups(original.document)
        identity = lambda value: str(value.get('native_id', value['id']))
        if [identity(s) for s in design['screens']] != [s['id'] for s in source_pages]:
            raise HmiError('CONTROL_GENERATION_SCOPE', 'Every original page must remain in source order')
        tags = {tag['id']: tag for tag in design['tags']}
        used = {owner['id'] for page in pages for owner in page['elements']}
        clones, patches = [], []
        result_sections = list(document.sections[:pages[0]['start']])
        for screen, source, raw_page in zip(design['screens'], source_pages, pages):
            sid = source['id']
            if screen['name'] != source['name'] or [screen['width'], screen['height']] != session['profile']['resolution']:
                raise HmiError('CONTROL_GENERATION_SCOPE', 'Control generation preserves source page names/dimensions')
            originals = screen['elements'][:len(source['elements'])]
            if [identity(e) for e in originals] != [e['id'] for e in source['elements']]:
                raise HmiError('CONTROL_GENERATION_SCOPE', 'Original source objects must be retained first')
            for element, native in zip(originals, source['elements']):
                if (set(element) != {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'source_owner_sha256'}
                        or element['kind'] != 'native_preserved' or element['text'] != ''
                        or element['source_owner_sha256'] != original.owner_extent_sha256(sid, native['id'])
                        or any(element[k] != native['geometry'][k] for k in ('x', 'y', 'width', 'height'))):
                    raise HmiError('CONTROL_GENERATION_SCOPE', 'Reference objects cannot be hidden, edited or reinterpreted')
            result_sections.extend(copy.deepcopy(original.document.sections[raw_page['start']:raw_page['end']]))
            for element in screen['elements'][len(source['elements']):]:
                eid = identity(element)
                if not re.fullmatch(r'[1-9][0-9]{0,9}', eid) or int(eid) > 2147483647 or eid in used:
                    raise HmiError('DUPLICATE_ELEMENT', 'Appended objects require fresh positive project-wide IDs')
                used.add(eid)
                numeric = element['kind'] in {'numeric_input', 'numeric_display'}
                kind = element.get('behavior') if element['kind'] == 'button' else element['kind']
                if kind not in donors or element['kind'] not in {'button', 'numeric_input', 'numeric_display'}:
                    raise HmiError('CONTROL_GENERATION_SCOPE', 'Object kind/behavior has no witnessed control donor')
                allowed = {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'binding', 'font_size', 'color', 'fill', 'role'}
                allowed |= {'format', 'fractional', 'minimum', 'maximum', 'value_model'} if numeric else {'states', 'behavior'}
                if set(element) - allowed or ('text' in element and numeric):
                    raise HmiError('CONTROL_GENERATION_SCOPE', 'Control intent contains unqualified presentation/unit fields')
                donor = donors[kind]
                pin = schema['control_generation']['donors'][kind]
                clone = copy.deepcopy(original.document.sections[donor['start']:donor['end']])
                clones.append(dict(op='clone_element', source_screen=pin['screen_id'], source_element=pin['element_id'], target_screen=sid, element_id=eid))
                section = clone[0]
                section.one('nPartsID').set_value(eid.encode('ascii'))
                geometry = {k: int(donor['section'].one(field).value) for k, field in {'x':'X','y':'Y','width':'Width','height':'Height'}.items()}
                for key, value in [('x',0),('y',0),('width',element['width']),('height',element['height']),('x',element['x']),('y',element['y'])]:
                    field = {'x':'X','y':'Y','width':'Width','height':'Height'}[key]
                    section.one(field).set_value(str(value).encode('ascii'))
                    patches.append(dict(op='set_property', screen_id=sid, element_id=eid, key=key, value=value))
                for direction in ('read', 'write'):
                    tag_id = element.get('binding', {}).get(direction)
                    field = direction.title() + 'Var'
                    if tag_id is None:
                        if section.one(field).value != b'None':
                            raise HmiError('CONTROL_ADDRESS_SCOPE', 'Inherited live binding must be explicitly declared')
                        continue
                    tag = tags[tag_id]
                    expected_type = tag['data_type'] if numeric and storage_contract(schema) is not None else 'UINT' if numeric else 'BOOL'
                    if numeric and expected_type not in schema['numeric']['types']:
                        raise HmiError('CONTROL_ADDRESS_SCOPE','Numeric type is outside the separately qualified storage contract')
                    prefix = schema['control_generation']['address_prefix']
                    original._control_address(tag['address'], prefix, 'D' if numeric else 'M', schema, direction=direction)
                    if (tag['data_type'] != expected_type
                            or tag.get('native_binding') != {'link':int(section.one(direction.title()+'Link').value), 'mem_type':int(section.one(direction.title()+'MemType').value)}
                            or tag.get('channel') != prefix.split('}')[0][1:]
                            or str(tag.get('station')) != prefix.split('}')[1][:-1]
                            or tag.get('byte_order') != 'device_default' or tag.get('word_order') != 'device_default'
                            or direction == 'write' and tag['access'] != 'ReadWrite'):
                        raise HmiError('CONTROL_ADDRESS_SCOPE', 'Binding differs from the exact source address, metadata or permission catalog')
                    section.one(field).set_value(tag['address'].encode('ascii'))
                    if tag['address'].encode('ascii') != donor['section'].one(field).value:
                        patches.append(dict(op='bind', screen_id=sid, element_id=eid,
                            **{direction:{'address':tag['address'], **tag['native_binding']}}))
                if numeric:
                    numeric_intent = self._numeric_intent(element, tags, schema)
                    if numeric_intent['data_type']=='INT' and storage_contract(schema) is not None:
                        # Explicit new-owner transformation, separate from ordinary numeric editing.
                        section.one('MemFmt').set_value(b'1')
                        patches.append(dict(op='convert_numeric_storage',screen_id=sid,element_id=eid,data_type='INT'))
                    # Independent expected values; do not call configure_numeric
                    # or the native operation emitter for whole-body validation.
                    verify_numeric_fields({**section.fields(), 'IntNum':str(numeric_intent['integer_digits']), 'DotNum':str(numeric_intent['fractional_digits']),
                        'GainValue':'1', 'OffsetValue':'0', **({'MinValue':str(numeric_intent['minimum']), 'MaxValue':str(numeric_intent['maximum'])} if kind=='numeric_input' else {})}, numeric_intent, schema)
                    settings = {'IntNum':str(numeric_intent['integer_digits']), 'DotNum':str(numeric_intent['fractional_digits']), 'GainValue':'1', 'OffsetValue':'0'}
                    if kind == 'numeric_input':
                        settings.update(MinValue=str(numeric_intent['minimum']), MaxValue=str(numeric_intent['maximum']))
                    for field, value in settings.items():
                        if Decimal(section.one(field).value.decode('ascii')) != Decimal(value):
                            section.one(field).set_value(value.encode('ascii'))
                    if numeric_intent['data_type']=='INT' and storage_contract(schema) is not None:
                        verify_converted(section,kind,schema)
                    patches.append(dict(op='configure_numeric', screen_id=sid, element_id=eid, **numeric_intent))
                for index, state in enumerate(clone[1:]):
                    declared = next((s for s in element.get('states', []) if s['value']==index), None)
                    if not numeric:
                        text = declared['text'] if declared else element.get('text')
                        if not isinstance(text, str):
                            raise HmiError('CONTROL_GENERATION_SCOPE', 'Both native command states need explicit text')
                        state.one('wTextLen0').set_text(text)
                        patches.append(dict(op='set_text', screen_id=sid, element_id=eid, state_index=index, language=0, text=text))
                    styles = [(k,element[k]) for k in ('font_size','color','fill') if k in element]
                    if declared:
                        styles.append(('state_fill', declared['fill']))
                    for key, value in styles:
                        if key != 'font_size':
                            # The witnesses show neutral colors. Until channel
                            # order is independently calibrated, use only colors
                            # whose R and B bytes agree in RGB/COLORREF encodings.
                            if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value) or value[1:3].lower()!=value[5:7].lower():
                                raise HmiError('CONTROL_COLOR_UNVERIFIED', 'Color byte order is unqualified; R/B-equivalent colors only')
                            value = int(value[1:],16)
                        field = {'font_size':'FontSize0','color':'FontColor','fill':'BgColor','state_fill':'BgColor'}[key]
                        state.one(field).set_value(str(value).encode('ascii'))
                        patches.append(dict(op='set_property', screen_id=sid, element_id=eid, state_index=index, key=key, value=value))
                result_sections.extend(clone)
        document.sections = result_sections
        return original, document, clones + patches

    def _compile_operations(self, session, design):
        """Compile intent into donor-preserving patches, never native templates.

        Every field/behavior still needs the selected profile's exact mapping.
        This compiler does not qualify a profile or open the production gate.
        Donors are stable IDs in this immutable source, never global file paths.
        """
        findings = validate_design(design, session['profile'])
        if findings:
            raise HmiError('VALIDATION', 'Cannot compile an invalid design', findings=findings)
        inventory = session['inventory']
        if inventory is None:
            raise HmiError('NATIVE_SOURCE_REQUIRED', 'Automatic native planning requires a source')
        profile = session['profile']
        schema = profile.get('native_schema', {})
        if schema.get('qualified') is not True:
            raise HmiError('NATIVE_SCHEMA_UNVERIFIED', 'Automatic planning needs calibrated native mappings')
        if session.get('calibration') is not None:
            return self._candidate_operations(session, design)
        if not model_ids_match(inventory['model_id'], profile.get('model_id')) or inventory['editor_version'] != profile.get('editor_version'):
            raise HmiError('NATIVE_TARGET_MISMATCH', 'Source model and editor differ from the selected profile')
        original_adapter = NativeAdapter(session['source_bytes'], profile['family'])
        original_adapter.verify_layout_order()
        alarm_operations = self._alarm_operations(session, design)
        self._alarm_views_preflight(session, design)
        macro_operations = self._macro_operations(session, design, preflight=True)

        def identity(item):
            value = str(item.get('native_id', item['id']))
            if not re.fullmatch(r'0|[1-9][0-9]{0,9}', value) or int(value) > 2147483647:
                raise HmiError('INVALID_ID', 'Automatic native planning needs canonical stable native IDs')
            return value

        screens = {s['id']: s for s in inventory['screens']}
        desired_screens = [identity(s) for s in design['screens']]
        if len(set(desired_screens)) != len(desired_screens) or not set(screens) <= set(desired_screens):
            raise HmiError('NATIVE_SCREEN_PLAN_UNVERIFIED', 'Account for every source page exactly once; page removal is unqualified')
        tags = {t['id']: t for t in design['tags']}
        page_clones, clones, operations, deletions, ordering = [], [], [], [], []
        original_screens = dict(screens)
        for sid in desired_screens:
            if sid in screens:
                continue
            donor = schema.get('screen_donor')
            if not isinstance(donor, dict) or set(donor) != {'screen_id'}:
                raise HmiError('NATIVE_DONOR_REQUIRED', 'New pages need an exact empty source-local page donor')
            source = original_screens.get(str(donor['screen_id']))
            if source is None or source['elements']:
                raise HmiError('NATIVE_SCREEN_DONOR_UNSAFE', 'Page donor must exist and contain no objects')
            if any(isinstance(m['owner'], dict) and m['owner'].get('screen_id') == source['id'] and (m['byte_count'] or m['schedule']) for m in inventory.get('macros', [])):
                raise HmiError('NATIVE_SCREEN_DONOR_UNSAFE', 'New pages cannot inherit executable or scheduled donor macros')
            original_adapter.page_baseline(source['id'])
            screen = next(s for s in design['screens'] if identity(s) == sid)
            page_clones.append(dict(op='clone_screen', source_screen=source['id'], screen_id=sid, name=screen['name']))
            screens[sid] = dict(source, id=sid, name=screen['name'])
        predicted_screens = list(original_screens) + [sid for sid in desired_screens if sid not in original_screens]
        if predicted_screens != desired_screens:
            ordering.append(dict(op='reorder_screens', screen_ids=desired_screens))

        def prop(screen_id, element_id, key, value, native, state_index=None):
            spec = schema.get('properties', {}).get(key)
            if not isinstance(spec, dict) or not spec.get('field'):
                raise HmiError('UNQUALIFIED_PROPERTY', 'Design property has no calibrated native mapping', property=key)
            expected = spec.get('values', {}).get(value) if spec.get('type') == 'enum' else value
            if expected is None:
                raise HmiError('UNQUALIFIED_ENUM', 'Behavior has no calibrated native enum', property=key)
            if str(native.get(spec['field'])) != str(expected):
                operation = dict(op='set_property', screen_id=screen_id, element_id=element_id, key=key, value=value)
                if state_index is not None:
                    operation['state_index'] = state_index
                operations.append(operation)

        for screen in design['screens']:
            sid = identity(screen)
            source_screen = screens[sid]
            if source_screen['name'] != screen['name']:
                operations.append(dict(op='rename_screen', screen_id=sid, name=screen['name']))
            for prefix in ('DocSize', 'PanelSize'):
                fields = source_screen['native_fields']
                if fields.get(prefix + 'X') != str(screen['width']) or fields.get(prefix + 'Y') != str(screen['height']):
                    raise HmiError('NATIVE_DESIGN_MISMATCH', 'Native page dimensions differ from the design')
            existing = {e['id']: e for e in source_screen['elements']}
            desired_ids = [identity(e) for e in screen['elements']]
            if len(set(desired_ids)) != len(desired_ids):
                raise HmiError('NATIVE_DESIGN_MISMATCH', 'Multiple design objects claim one native ID')
            predicted_order = [e['id'] for e in source_screen['elements'] if e['id'] in desired_ids]
            predicted_order += [eid for eid in desired_ids if eid not in existing]
            if predicted_order != desired_ids:
                ordering.append(dict(op='reorder_elements', screen_id=sid, element_ids=desired_ids))
            for element, eid in zip(screen['elements'], desired_ids):
                numeric = element['kind'] in {'numeric_input', 'numeric_display'}
                alarm_view = element['kind'] in _ALARM_VIEW_KINDS
                if element['kind'] not in {'button', 'text', 'indicator', 'goto'} and not numeric and not alarm_view:
                    raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Object kind has no calibrated source-local emitter')
                numeric_intent = self._numeric_intent(element, tags, schema) if numeric else None
                native = existing.get(eid)
                unit_source_sid, unit_source_eid = sid, eid
                if native is None:
                    donor = schema.get('donors', {}).get(element['kind'])
                    if numeric and isinstance(donor, dict):
                        donor = donor.get(numeric_intent['data_type'])
                    if not isinstance(donor, dict) or set(donor) != {'screen_id', 'element_id'}:
                        raise HmiError('NATIVE_DONOR_REQUIRED', 'New object needs an exact source-local donor', kind=element['kind'])
                    donor_screen = original_screens.get(str(donor['screen_id']))
                    native = next((e for e in donor_screen['elements'] if e['id'] == str(donor['element_id'])), None) if donor_screen else None
                    if native is None:
                        raise HmiError('NATIVE_DONOR_REQUIRED', 'Configured donor is absent from the immutable source')
                    unit_source_sid, unit_source_eid = donor_screen['id'], native['id']
                    clones.append(dict(op='clone_element', source_screen=donor_screen['id'], source_element=native['id'], target_screen=sid, element_id=eid))
                kind = schema.get('numeric', {}).get('kinds', {}).get(element['kind']) if numeric else schema.get('kinds', {}).get(element['kind'])
                if not isinstance(kind, dict) or not kind or any(str(native['native_fields'].get(k)) != str(v) for k, v in kind.items()):
                    raise HmiError('NATIVE_KIND_UNVERIFIED', 'Existing object or donor has the wrong native kind', element_id=eid)
                if alarm_view:
                    self._alarm_kind(schema, element['kind'])
                if numeric:
                    self._numeric_unit_owners(original_adapter, original_screens[unit_source_sid])
                unit_fields = self._numeric_unit_fields(element, native, schema) if numeric else set()
                if unit_fields:
                    original_adapter.unit_context_baseline(unit_source_sid, unit_source_eid)
                for field in (() if numeric else ('unit', 'format', 'minimum', 'maximum', 'fractional')):
                    if field in element:
                        raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Design field has no calibrated compiler mapping', field=field)
                if any(native['geometry'].get(k) != element[k] for k in ('x', 'y', 'width', 'height')):
                    # Move to a valid origin before resizing, so a valid final
                    # rectangle is not rejected by an intermediate patch.
                    for key, value in [('x', 0), ('y', 0), ('width', element['width']), ('height', element['height']), ('x', element['x']), ('y', element['y'])]:
                        spec = schema.get('properties', {}).get(key)
                        if not isinstance(spec, dict):
                            raise HmiError('UNQUALIFIED_GEOMETRY', 'Geometry mapping is incomplete')
                        operations.append(dict(op='set_property', screen_id=sid, element_id=eid, key=key, value=value))
                if alarm_view:
                    # Preserve complete source presentation instead of feeding
                    # Type11 through generic caption/style/binding writers.
                    continue
                if numeric:
                    operations.append(dict(op='configure_numeric', screen_id=sid, element_id=eid, **numeric_intent))
                elif element['kind'] == 'button':
                    prop(sid, eid, 'behavior', element['behavior'], native['native_fields'])
                if element['kind'] == 'goto':
                    self._navigation_contract(schema, kind)
                    target = next(s for s in design['screens'] if s['id'] == element['target_screen'])
                    target_id = identity(target)
                    operations.append(dict(op='configure_goto', screen_id=sid, element_id=eid, target_screen=target_id))
                for key, value, fields, index in self._visual_fields(element, native, schema, unit_fields):
                    prop(sid, eid, key, value, fields, index)
                state_specs = element.get('states', [])
                native_states = native.get('states', [])
                if not state_specs and 'text' not in element:
                    # A numeric caption has a separate unsupported ownership
                    # contract; every plain label/command/navigation does not.
                    if not numeric:
                        raise HmiError('NATIVE_TEXT_REQUIRED', 'Declare native caption text explicitly, including empty text')
                    if any(t['text'] for t in native['texts'] if t['language'] == 0):
                        raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Numeric donor contains an unmanaged caption')
                if any(type(s.get('value')) is not int for s in native_states):
                    raise HmiError('NATIVE_STATE_UNVERIFIED', 'Native state values must be explicit integers')
                if state_specs and sorted(s['value'] for s in state_specs) != sorted(s.get('value') for s in native_states):
                    raise HmiError('NATIVE_STATE_UNVERIFIED', 'Donor states must exactly match declared state values')
                if not state_specs and sorted(s['value'] for s in native_states) != schema.get('state_values', {}).get(element['kind']):
                    raise HmiError('NATIVE_STATE_UNVERIFIED', 'Undeclared donor states differ from the calibrated kind')
                texts = {(t['state_index'], t['language']): t['text'] for t in native['texts']}
                for state in native_states:
                    declared = next((s for s in state_specs if s['value'] == state['value']), None)
                    text = declared['text'] if declared else element.get('text')
                    if text is not None and texts.get((state['state_index'], 0)) != text:
                        operations.append(dict(op='set_text', screen_id=sid, element_id=eid, state_index=state['state_index'], language=0, text=text))
                    if declared:
                        fill = declared['fill']
                        encoding = schema.get('state_fill', {})
                        spec = schema.get('properties', {}).get('state_fill', {})
                        if (spec.get('field') != encoding.get('field') or spec.get('scope') != 'state'):
                            raise HmiError('NATIVE_STYLE_UNVERIFIED', 'State color needs an exact calibrated RGB mapping')
                        prop(sid, eid, 'state_fill', self._native_color(fill, encoding.get('encoding')), state['native_fields'], state['state_index'])
                bindings = {'op': 'bind', 'screen_id': sid, 'element_id': eid}
                for direction in ('read', 'write'):
                    tag_id = element.get('binding', {}).get(direction)
                    actual = native['bindings'].get(direction, {})
                    if tag_id:
                        tag = tags[tag_id]
                        contract = self._binding_contract(schema, tag)
                        if any(field not in contract or tag.get(field) != contract[field] for field in ('data_type', 'channel', 'station', 'byte_order', 'word_order')):
                            raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Binding engineering contract differs from calibration')
                        metadata = tag.get('native_binding')
                        if not isinstance(metadata, dict) or set(metadata) != {'link', 'mem_type'}:
                            raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Exact native binding metadata is required')
                        expected = {'address': tag['address'], **{k: str(v) for k, v in metadata.items()}}
                        if expected != actual:
                            bindings[direction] = {'address': expected['address'],
                                                   'link': int(metadata['link']), 'mem_type': int(metadata['mem_type'])}
                    elif actual.get('address') not in (None, '', 'None'):
                        raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Clearing a donor binding needs an exact native None contract')
                if len(bindings) > 3:
                    operations.append(bindings)
            deletions.extend(dict(op='delete_element', screen_id=sid, element_id=eid) for eid in existing if eid not in desired_ids)
        # All donors are cloned before any source-local patch or deletion; a
        # changed donor must never contaminate a later clone's planned fields.
        result = page_clones + clones + operations + macro_operations + alarm_operations + deletions + ordering
        # Validate structural qualification and owner boundaries before exposing
        # a reviewable plan. This is in-memory only, never a native file save.
        if page_clones or ordering or any(op['op'] == 'rename_screen' for op in operations):
            NativeAdapter(session['source_bytes'], profile['family']).apply(result, profile)
        return result

    @staticmethod
    def _native_color(value, encoding):
        if (not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value)
                or not isinstance(encoding, str) or encoding not in {'rgb24', 'colorref24'}):
            raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Color requires an exact supported 24-bit encoding')
        value = int(value[1:], 16)
        if encoding == 'colorref24':
            return ((value & 255) << 16) | (value & 0xff00) | (value >> 16)
        return value

    @staticmethod
    def _visual_fields(element, native, schema, unit_fields=frozenset()):
        """Exact mapped scalar intent, not a vendor pixel-rendering claim."""
        result = []
        keys = ('font_size', 'color', 'fill')
        visual = schema.get('visual')
        properties = schema.get('properties')
        if (not isinstance(visual, dict) or visual.get('qualified') is not True
                or set(visual) - {'qualified', 'companions', *keys} or not isinstance(properties, dict)):
            raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Appearance intent needs a bounded qualified style contract')
        companions = visual.get('companions')
        if not isinstance(companions, dict) or set(companions) != {'element', 'state'} or any(
                not isinstance(values, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items())
                for values in companions.values()):
            raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Style requires explicit native companion baselines')
        editable = {'element': set(), 'state': set()}
        expected_fields = {'font_size': {'FontSize0'}, 'color': {'FontColor'}, 'fill': {'BgColor'}}
        for key in keys:
            if key not in visual:
                continue
            mapping, prop = visual[key], properties.get(key)
            if (not isinstance(mapping, dict) or not isinstance(prop, dict) or prop.get('type') != 'int'
                    or not isinstance(mapping.get('field'), str) or not isinstance(mapping.get('scope'), str)
                    or mapping['field'] not in expected_fields[key] or mapping['scope'] not in editable
                    or prop.get('field') != mapping['field'] or prop.get('scope', 'element') != mapping['scope']):
                raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Style needs exact qualified scope and field mappings', field=key)
            editable[mapping['scope']].add(mapping['field'])
        if element.get('states'):
            mapping, prop = schema.get('state_fill'), properties.get('state_fill')
            if (not isinstance(mapping, dict) or not isinstance(prop, dict) or prop.get('type') != 'int'
                    or mapping.get('field') != 'BgColor' or prop.get('field') != 'BgColor' or prop.get('scope') != 'state'
                    or type(prop.get('min')) is not int or type(prop.get('max')) is not int):
                raise HmiError('NATIVE_STYLE_UNVERIFIED', 'State fill needs an exact bounded native mapping')
            for state in element['states']:
                value = FileService._native_color(state['fill'], mapping.get('encoding'))
                if not prop['min'] <= value <= prop['max']:
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'State fill is outside calibrated limits')
            editable['state'].add('BgColor')
        for scope, owners in [('element', [native['native_fields']]), ('state', [s['native_fields'] for s in native['states']])]:
            baseline = companions[scope]
            for fields in owners:
                for field, expected in baseline.items():
                    if fields.get(field) != expected:
                        raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Native style companion differs from the approved baseline', field=field)
                if any(field in fields for field in ('PIB Name', 'Picture Name', 'PictureOffset')):
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Picture-reference donors have no flat-style contract')
                # Appearance names can include a kind prefix (NumBgOpacity,
                # BtnPictureStretch, FieldFontSize). A leading-prefix check
                # alone misses genuine competing visual representations.
                observed = {field for field in fields if re.search(
                    r'(?:Font|Picture|PIB|Opacity|Color|Style|Trans|Shadow|Gradient)|^(?:Show|animated$|antialiasing$|Penetrate$|Border|RoundRadius$|Fill|LnrGrad|BDR|Grad|AutoResize|UseBMPText$|StretchMode$|Twinkles$|SoundIndex$|Fg|Visible|UnitTextLen|nAngle$|CutDraw$|TitleHeight$|bFreeze$)', field, re.I)}
                # Only the separately checked immutable numeric unit context
                # may account for its own appearance fields. Profile extras
                # do not make arbitrary appearance records editable.
                owned_units = unit_fields if scope == 'element' else set()
                unknown = observed - editable[scope] - set(baseline) - owned_units
                if unknown:
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Native appearance companion is not accounted for', fields=sorted(unknown))
        for key in ('font_size', 'color', 'fill'):
            if key not in element:
                continue
            mapping, prop = visual.get(key), properties.get(key)
            if not isinstance(mapping, dict) or not isinstance(prop, dict):
                raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Style needs exact qualified scope and field mappings', field=key)
            value = element[key]
            if key == 'font_size':
                if mapping.get('scale') != 1 or type(mapping.get('scale')) is not int:
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Font size scaling is not calibrated')
                if mapping['field'] != 'FontSize0' or mapping['scope'] != 'state' or any(s['native_fields'].get('FontRatio0') != '100' for s in native['states']):
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Only explicit State.FontSize0 with unscaled FontRatio0 is supported')
                if any(not isinstance(s['native_fields'].get('FontName0'), str) or not s['native_fields']['FontName0'].isascii() for s in native['states']):
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Narrow non-ASCII font names need separate encoding qualification')
            else:
                value = FileService._native_color(value, mapping.get('encoding'))
            lo, hi = prop.get('min'), prop.get('max')
            if type(lo) is not int or type(hi) is not int or not lo <= value <= hi:
                raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Style scalar is outside its calibrated limits', field=key)
            owners = [(None, native['native_fields'])] if mapping['scope'] == 'element' else [
                (state['state_index'], state['native_fields']) for state in native['states']]
            if not owners:
                raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Mapped native style owner is absent', field=key)
            for index, fields in owners:
                if mapping['field'] not in fields:
                    raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Mapped field is absent; donor fields cannot be invented', field=key)
                # Per-state fill is the common renderer's explicit override.
                if key == 'fill' and index is not None:
                    state_value = next(s['value'] for s in native['states'] if s['state_index'] == index)
                    if any(s['value'] == state_value for s in element.get('states', [])):
                        continue
                result.append((key, value, fields, index))
        return result

    @staticmethod
    def _navigation_contract(schema, kind):
        navigation = schema.get('navigation')
        if (not isinstance(navigation, dict) or navigation.get('qualified') is not True
                or navigation.get('field') != 'GoToScreenID' or not isinstance(kind, dict)
                or set(kind) != {'Type', 'SubType'} or navigation.get('match') != kind
                or any(not isinstance(v, str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}', v) for v in kind.values())):
            raise HmiError('UNQUALIFIED_NAVIGATION', 'Navigation requires complete exact canonical kind and target mappings')
        return navigation

    @staticmethod
    def _operation_intent(session, design, operations):
        """Public IR plans cannot acquire arbitrary low-level property powers."""
        schema = session['profile'].get('native_schema', {})
        objects = {(str(s.get('native_id', s['id'])), str(e.get('native_id', e['id']))): e
                   for s in design['screens'] for e in s['elements']}
        geometry = {'x': 'X', 'y': 'Y', 'width': 'Width', 'height': 'Height'}
        fields = geometry | {'behavior': 'SubType', 'color': 'FontColor', 'fill': 'BgColor',
                             'state_fill': 'BgColor', 'font_size': 'FontSize0'}
        alarm_operations = FileService._alarm_operations(session, design)
        expected_messages = alarm_operations[0] if alarm_operations else None
        if expected_messages is not None and sum(
                isinstance(op, dict) and op.get('op') == 'configure_alarm' for op in operations) != 1:
            raise HmiError('NATIVE_ALARM_OPERATION_COVERAGE', 'Changed approved alarm messages require one exact consolidated operation')
        for operation in operations:
            if not isinstance(operation, dict):
                raise HmiError('INVALID_OPERATION', 'Each operation must be an object')
            if operation.get('op') == 'configure_alarm':
                if expected_messages is None or operation != expected_messages:
                    raise HmiError('NATIVE_OPERATION_INTENT', 'Alarm operations may update only exact approved existing primary messages')
                continue
            element = objects.get((str(operation.get('screen_id')), str(operation.get('element_id'))))
            if operation.get('op') == 'clone_element':
                element = objects.get((str(operation.get('target_screen')), str(operation.get('element_id'))))
            owner = operation.get('owner')
            if operation.get('op') == 'configure_macro' and isinstance(owner, dict):
                element = objects.get((str(owner.get('screen_id')), str(owner.get('element_id'))))
            donor = objects.get((str(operation.get('source_screen')), str(operation.get('source_element'))))
            if ((element is not None and element.get('kind') == 'native_preserved')
                    or operation.get('op') == 'clone_element' and donor is not None and donor.get('kind') == 'native_preserved'):
                raise HmiError('NATIVE_PRESERVED_SCOPE', 'A retained unknown owner grants no edit, macro or clone authority')
            if element is not None and element.get('kind') in _ALARM_VIEW_KINDS:
                if operation.get('op') not in {'clone_element', 'set_property'} or (
                        operation.get('op') == 'set_property' and operation.get('key') not in geometry):
                    raise HmiError('NATIVE_OPERATION_INTENT', 'Source-preserved alarm views accept only clone and geometry intent')
                if operation.get('op') == 'clone_element':
                    donors = schema.get('donors')
                    donor = donors.get(element['kind']) if isinstance(donors, dict) else None
                    if (not isinstance(donor, dict) or set(donor) != {'screen_id', 'element_id'}
                            or str(operation.get('source_screen')) != str(donor['screen_id'])
                            or str(operation.get('source_element')) != str(donor['element_id'])):
                        raise HmiError('NATIVE_OPERATION_INTENT', 'Alarm view clones require their approved immutable donor')
            if operation.get('op') == 'set_text' and operation.get('language', 0) != 0:
                raise HmiError('NATIVE_OPERATION_INTENT', 'Non-primary native captions have no public IR emitter')
            if operation.get('op') == 'set_unit_caption':
                raise HmiError('NATIVE_OPERATION_INTENT', 'Embedded unit captions are a low-level record operation; public units require a separate text owner')
            if operation.get('op') != 'set_property':
                continue
            key = operation.get('key')
            element = objects.get((str(operation.get('screen_id')), str(operation.get('element_id'))))
            properties = schema.get('properties')
            prop = properties.get(key) if isinstance(properties, dict) and isinstance(key, str) else None
            if (not isinstance(key, str) or key not in fields or element is None or not isinstance(prop, dict)
                    or prop.get('field') != fields[key]):
                raise HmiError('NATIVE_OPERATION_INTENT', 'Native property is outside the represented IR contract')
            scope = prop.get('scope', 'element')
            state_owner = 'state_index' in operation
            if (not isinstance(scope, str) or scope not in {'state', 'element'} or state_owner != (scope == 'state')
                    or (key in geometry or key == 'behavior') and scope != 'element'):
                raise HmiError('NATIVE_OPERATION_INTENT', 'Native property owner differs from represented IR scope')
            if key == 'behavior' and element.get('kind') != 'button':
                raise HmiError('NATIVE_OPERATION_INTENT', 'Button behavior requires a declared command button')
            if key == 'state_fill' and not element.get('states'):
                raise HmiError('NATIVE_OPERATION_INTENT', 'State fill requires declared state values')
            if key in {'color', 'fill', 'font_size'} and key not in element:
                raise HmiError('NATIVE_OPERATION_INTENT', 'Style changes require explicit IR scalar intent')

    @staticmethod
    def _alarm_operations(session, design):
        schema = session['profile'].get('native_schema', {})
        if not design.get('alarms') and 'alarm_ir' not in schema:
            return []
        source = session.get('source_bytes')
        if source is None:
            raise HmiError('NATIVE_SOURCE_REQUIRED', 'Alarm messages require immutable source resources')
        adapter = NativeAdapter(source, session['profile']['family'])
        return alarm_ir_operations(adapter.document.tail, design['alarms'], design['tags'],
                                   schema)

    @staticmethod
    def _alarm_kind(schema, kind):
        kinds = schema.get('kinds') if isinstance(schema, dict) else None
        mapping = kinds.get(kind) if isinstance(kinds, dict) else None
        if mapping != {'Type': '11', 'SubType': _ALARM_VIEW_KINDS[kind]}:
            raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Alarm view needs its exact Type/SubType mapping')
        return mapping

    @staticmethod
    def _alarm_source_owner(session, screen_id, element_id, kind):
        screens = {s['id']: s for s in session['inventory']['screens']}
        page = screens.get(screen_id)
        native = next((e for e in page['elements'] if e['id'] == element_id), None) if page else None
        if native is not None:
            return screen_id, element_id
        schema = session['profile'].get('native_schema')
        donors = schema.get('donors') if isinstance(schema, dict) else None
        donor = donors.get(kind) if isinstance(donors, dict) else None
        if not isinstance(donor, dict) or set(donor) != {'screen_id', 'element_id'}:
            raise HmiError('NATIVE_DONOR_REQUIRED', 'Alarm view needs its immutable source-local donor')
        source_sid, source_eid = str(donor['screen_id']), str(donor['element_id'])
        page = screens.get(source_sid)
        if page is None or not any(e['id'] == source_eid for e in page['elements']):
            raise HmiError('NATIVE_DONOR_REQUIRED', 'Alarm view donor is absent from the immutable source')
        return source_sid, source_eid

    @staticmethod
    def _alarm_views_preflight(session, design, candidate=None):
        objects = {(str(s.get('native_id', s['id'])), str(e.get('native_id', e['id']))): e
                   for s in design['screens'] for e in s['elements']}
        views = {identity: element for identity, element in objects.items()
                 if element.get('kind') in _ALARM_VIEW_KINDS}
        for screen in (session.get('inventory') or {}).get('screens', []):
            for native in screen['elements']:
                if native['native_fields'].get('Type') == '11':
                    declared = views.get((screen['id'], native['id']))
                    if declared is None:
                        raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Every original Type11 owner must remain a declared supported alarm view')
        if not views:
            return
        if not design.get('alarms'):
            raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Alarm views require declared qualified messages')
        schema = session['profile'].get('native_schema', {})
        contract = schema.get('alarm_views')
        if (not isinstance(contract, dict) or set(contract) != {'qualified', 'contract_version', 'mode', 'owners'}
                or contract.get('qualified') is not True or type(contract.get('contract_version')) is not int
                or contract['contract_version'] != 1 or contract.get('mode') != 'preserve_source'
                or not isinstance(contract.get('owners'), list) or not 1 <= len(contract['owners']) <= 1000):
            raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Alarm views require an exact source-preserving owner contract')
        owners = {}
        for item in contract['owners']:
            if (not isinstance(item, dict) or set(item) != {'screen_id', 'element_id', 'kind', 'owner_sha256'}
                    or any(not isinstance(item.get(k), str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}', item[k])
                           or int(item[k]) > 2147483647 for k in ('screen_id', 'element_id'))
                    or not isinstance(item.get('kind'), str) or item['kind'] not in _ALARM_VIEW_KINDS
                    or not isinstance(item.get('owner_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['owner_sha256'])):
                raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Malformed source-preserving view owner')
            identity = (item['screen_id'], item['element_id'])
            if identity in owners:
                raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Alarm view owner identities cannot be repeated')
            owners[identity] = item
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        for (sid, eid), element in views.items():
            if (element.get('view_policy') != 'preserve_source' or element.get('text') != ''
                    or set(element) - {'id', 'native_id', 'kind', 'x', 'y', 'width', 'height', 'text', 'view_policy'}):
                raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Alarm presentation must be explicitly preserved with separate heading text')
            expected_kind = FileService._alarm_kind(schema, element['kind'])
            source_sid, source_eid = FileService._alarm_source_owner(session, sid, eid, element['kind'])
            owner = owners.get((source_sid, source_eid))
            source_context = alarm_view_context(original.document, source_sid, source_eid)
            if (owner is None or owner['kind'] != element['kind']
                    or owner['owner_sha256'] != source_context['owner_sha256']
                    or {'Type': source_context['type'], 'SubType': source_context['subtype']} != expected_kind):
                raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Original alarm owner differs from its calibrated raw context')
            if candidate is not None:
                saved_context = alarm_view_context(candidate.document, sid, eid)
                if source_context['immutable_sha256'] != saved_context['immutable_sha256']:
                    raise HmiError('NATIVE_ALARM_VIEW_UNVERIFIED', 'Saved alarm presentation differs from its immutable source owner')

    @staticmethod
    def _macro_key(owner, field):
        return canonical_hash({'owner': owner, 'field': field})

    def _macro_operations(self, session, design, *, preflight=False):
        """Resolve approved IR IDs to explicit source-local native owners.

        The whole profile is in the approval hash. Neither the IR trigger nor a
        template chooses an implicit owner, clock period, controller or width.
        Scheduling is an immutable exact raw-field contract, never a default.
        """
        if not design['macros']:
            return []
        schema = session['profile'].get('native_schema', {})
        macro_schema = schema.get('macros', {})
        mappings = schema.get('macro_bindings', {})
        if not isinstance(macro_schema, dict) or macro_schema.get('qualified') is not True or not isinstance(mappings, dict):
            raise HmiError('UNQUALIFIED_MACRO', 'Macro emission requires exact source-local templates and ID/owner mappings')
        internal_binding = schema.get('macro_internal_binding')
        if not isinstance(internal_binding, dict) or set(internal_binding) != {'link', 'mem_type'}:
            raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Macro internal memory link/type must be explicitly calibrated')
        tags = {t['id']: t for t in design['tags']}
        inventory = session['inventory']
        if inventory is None:
            raise HmiError('NATIVE_SOURCE_REQUIRED', 'Macros require an immutable native source')
        source_macros = inventory.get('macros', [])
        operations, claimed = [], set()

        def statements(items):
            result = []
            for statement in items:
                tag = tags[statement['tag']]
                contract = self._binding_contract(schema, tag)
                if any(field not in contract or tag.get(field) != contract[field]
                       for field in ('data_type', 'channel', 'station', 'byte_order', 'word_order')):
                    raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Macro tag engineering contract differs from the native mapping')
                if tag.get('native_binding') != internal_binding:
                    raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Macro tag is not the explicitly calibrated internal memory')
                if statement['op'] != 'if' and tag['access'] != 'ReadWrite':
                    raise HmiError('READ_ONLY_WRITE', 'Macro command cannot write a read-only tag')
                native = dict(op=statement['op'], address=tag['address'], datatype=tag['data_type'])
                if 'value' in statement:
                    native['value'] = statement['value']
                if statement['op'] == 'if':
                    native.update(comparison=statement.get('comparison', 'eq'),
                                  then=statements(statement['then']))
                    native['else'] = statements(statement.get('else', []))
                result.append(native)
            return result

        for macro in design['macros']:
            mapping = mappings.get(macro['id'])
            if not isinstance(mapping, dict) or set(mapping) != {'owner', 'field', 'trigger', 'schedule'}:
                raise HmiError('MACRO_OWNER_REQUIRED', 'Each macro ID needs an exact owner, field, trigger and scheduling contract')
            owner, field, trigger = mapping['owner'], mapping['field'], macro['trigger']
            if not isinstance(owner, dict) or mapping['trigger'] != trigger:
                raise HmiError('MACRO_TRIGGER_MISMATCH', 'IR macro trigger differs from its approved native owner mapping')
            if trigger == 'startup' and (owner != {'kind': 'application'} or field != 'InitialMacroLen'):
                raise HmiError('MACRO_TRIGGER_MISMATCH', 'Startup macro must belong to the application InitialMacroLen')
            if trigger == 'clock' and (owner != {'kind': 'application'} or field != 'ClockMacroLen'):
                raise HmiError('MACRO_TRIGGER_MISMATCH', 'Clock macro must belong to the application ClockMacroLen')
            if trigger == 'button':
                if set(owner) != {'kind', 'screen_id', 'element_id'} or owner['kind'] != 'element' or field not in {'BeforeExecMacroLen', 'AfterExecMacroLen', 'ButtonOnMacroLen', 'ButtonOffMacroLen'}:
                    raise HmiError('MACRO_TRIGGER_MISMATCH', 'Button macro needs an exact element and calibrated execution field')
                matched = [e for s in design['screens'] if str(s.get('native_id', s['id'])) == owner['screen_id']
                           for e in s['elements'] if str(e.get('native_id', e['id'])) == owner['element_id']]
                if len(matched) != 1 or matched[0]['kind'] != 'button':
                    raise HmiError('MACRO_OWNER_REQUIRED', 'Button macro owner must be one retained approved button')
            key = self._macro_key(owner, field)
            if key in claimed:
                raise HmiError('MACRO_OWNER_AMBIGUOUS', 'Two IR macros cannot claim the same native owner/field')
            claimed.add(key)
            matches = [m for m in source_macros if m['owner'] == owner and m['field'] == field]
            if len(matches) != 1 or matches[0]['owner_status'] != 'QUALIFIED':
                raise HmiError('MACRO_OWNER_AMBIGUOUS', 'Native macro owner/field is absent or ambiguous')
            schedule = mapping['schedule']
            if not isinstance(schedule, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in schedule.items()) or matches[0]['schedule'] != schedule:
                raise HmiError('MACRO_SCHEDULE_MISMATCH', 'Existing native macro scheduling must be preserved and fully acknowledged')
            if trigger == 'clock' and not {'ClockMacroDelayTime', 'ClockMacroPriority'} <= set(schedule):
                raise HmiError('MACRO_SCHEDULE_REQUIRED', 'Clock delay and priority must be explicit observed native fields')
            operations.append(dict(op='configure_macro', owner=copy.deepcopy(owner), field=field,
                                   expected_program_sha256=matches[0]['sha256'],
                                   statements=statements(macro['statements'])))
        if preflight:
            # Bounded in-memory compilation only. No approval, file write or
            # vendor execution is implied by this early semantic validation.
            NativeAdapter(session['source_bytes'], session['profile']['family']).apply(operations, session['profile'])
        return operations

    def _macros_match(self, session, design, candidate):
        """Decode saved bytes and compare declared intent and untouched owners."""
        original = NativeAdapter(session['source_bytes'], session['profile']['family'])
        expected = self._macro_operations(session, design)
        claimed = {self._macro_key(op['owner'], op['field']) for op in expected}
        for operation in expected:
            candidate.verify_macro_contract(operation, session['profile']['native_schema'], original)
        before = original.inspect().get('macros', [])
        after = candidate.inspect().get('macros', [])

        def preserved(records):
            result = []
            for record in records:
                key = self._macro_key(record['owner'], record['field'])
                if key not in claimed:
                    # Section offsets may shift as objects are cloned. Owner,
                    # bytes and schedule may not. New empty fields are inert.
                    if record['byte_count'] == 0 and not record['schedule']:
                        continue
                    result.append({k: record[k] for k in ('owner', 'field', 'sha256', 'byte_count', 'schedule', 'owner_status')})
            return sorted(result, key=canonical_hash)

        if preserved(before) != preserved(after):
            raise HmiError('UNDECLARED_MACRO_CHANGE', 'An unmanaged native macro was changed, removed or cloned')
        for operation in expected:
            key = self._macro_key(operation['owner'], operation['field'])
            matches = [m for m in after if self._macro_key(m['owner'], m['field']) == key]
            source = [m for m in before if self._macro_key(m['owner'], m['field']) == key]
            if len(matches) != 1 or matches[0]['owner_status'] != 'QUALIFIED' or matches[0]['schedule'] != source[0]['schedule']:
                raise HmiError('MACRO_OWNER_AMBIGUOUS', 'Saved macro owner or scheduling differs from the approved source contract')

    @staticmethod
    def _binding_contract(schema, tag):
        contracts = schema.get('binding_contracts', {})
        if not isinstance(contracts, dict):
            raise HmiError('INVALID_SCHEMA', 'Typed binding contracts must be an object')
        contract = contracts.get(tag['data_type'], schema.get('binding_contract', {}))
        if not isinstance(contract, dict):
            raise HmiError('INVALID_SCHEMA', 'Binding engineering contract must be an object')
        return contract

    @staticmethod
    def _numeric_intent(element, tags, schema):
        """Raw PLC bounds; fixed presentation requires explicit qualification."""
        direction = 'write' if element['kind'] == 'numeric_input' else 'read'
        tag = tags[element['binding'][direction]]
        numeric = schema.get('numeric', {})
        if not isinstance(numeric, dict) or numeric.get('qualified') is not True:
            raise HmiError('UNQUALIFIED_NUMERIC', 'Native numeric emitter needs an exact qualified mapping')
        data_type = tag['data_type']
        if data_type not in numeric.get('types', {}):
            raise HmiError('UNSUPPORTED_NUMERIC_TYPE', 'No exact native storage mapping; narrowing and TIME fallback are forbidden')
        if element.get('text'):
            raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Numeric labels require separately owned text objects')
        if (tag.get('unit') or element.get('unit')) and not element.get('unit_label'):
            raise HmiError('NATIVE_UNIT_OWNER_REQUIRED', 'A numeric engineering unit requires an explicit separate text owner')
        if 'minimum' not in element or 'maximum' not in element:
            raise HmiError('NUMERIC_LIMIT', 'Automatic planning requires explicit display/process bounds')
        lower, upper = Decimal(str(element['minimum'])), Decimal(str(element['maximum']))
        digits = max(1, lower.copy_abs().adjusted() + 1, upper.copy_abs().adjusted() + 1)
        value_model = element.get('value_model', 'raw')
        if value_model != 'raw':
            if value_model != FIXED_MODEL:
                raise HmiError('UNQUALIFIED_FIXED_DECIMAL', 'Unknown numeric value model cannot be silently omitted')
            descriptor = fixed_decimal_contract(schema)
            if data_type not in descriptor['types']:
                raise HmiError('UNQUALIFIED_FIXED_DECIMAL', 'Fixed presentation cannot change the witnessed storage type')
            if element['kind'] == 'numeric_input' and element.get('fractional', 0):
                raise HmiError('UNQUALIFIED_FIXED_DECIMAL', 'Fractional integer keypad-limit lowering remains unqualified')
            digits = integer_digits(element['minimum'],element['maximum'],data_type,element.get('fractional',0))
        result = dict(kind=element['kind'], data_type=data_type, integer_digits=digits,
                      fractional_digits=element.get('fractional', 0), gain=1, offset=0)
        if value_model == FIXED_MODEL:
            result['value_model'] = value_model
        if element['kind'] == 'numeric_input':
            result.update(minimum=element['minimum'], maximum=element['maximum'])
        return result

    @staticmethod
    def _numeric_unit_owners(adapter, screen):
        """Unknown global/page unit metadata cannot escape an empty Element."""
        if (any(record.key and 'unit' in record.key.casefold() for record in adapter.application.records)
                or any('unit' in key.casefold() for key in screen['native_fields'])):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Unit metadata has an unqualified application/page owner')

    @staticmethod
    def _numeric_unit_fields(element, native, schema):
        """Bound inactive embedded units and conversion metadata, never infer enums.

        The public design uses a separately positioned text owner. A profile's
        exact identity baseline is required even when ShowUnit is disabled:
        hiding its caption does not establish conversion/value identity.
        """
        fields = native['native_fields']
        observed = {key for key in fields if 'unit' in key.casefold()}
        if any('unit' in key.casefold() for state in native['states'] for key in state['native_fields']):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Numeric unit metadata has an unqualified native owner')
        if not observed:
            if element.get('unit_label'):
                raise HmiError('NATIVE_UNIT_UNVERIFIED', 'A linked unit owner needs an explicit inactive native unit baseline')
            return set()
        contract = schema.get('unit_context')
        if (not isinstance(contract, dict) or set(contract) != {'qualified', 'owner', 'value_model', 'fields'}
                or contract.get('qualified') is not True or contract.get('owner') != 'Element'
                or contract.get('value_model') != 'identity' or not isinstance(contract.get('fields'), dict)):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Numeric units require a separately qualified exact identity-conversion baseline')
        expected = contract['fields']
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in expected.items()):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Numeric unit baseline fields must be exact native string values')
        extra = observed - _UNIT_CONTEXT_FIELDS
        languages = set()
        for field in extra:
            match = re.fullmatch(r'Unit(?:TextLen|FontSize|FontName)([1-9][0-9]*)', field)
            if not match:
                raise HmiError('NATIVE_UNIT_UNVERIFIED', 'An unknown unit/conversion companion is not qualified', field=field)
            languages.add(match[1])
        for language in languages:
            if not {prefix + language for prefix in ('UnitTextLen', 'UnitFontSize', 'UnitFontName')} <= observed:
                raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Unit language companions are incomplete')
        if not _UNIT_CONTEXT_FIELDS <= observed or set(expected) != observed or any(fields[k] != v for k, v in expected.items()):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Native numeric unit/conversion metadata differs from the approved identity baseline')
        if any(fields[k] != 'None' for k in ('UnitSrcVar', 'UnitDisplayVar')):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'External unit-selection operands have no qualified value model')
        for key in ('UnitPercent1Var', 'UnitPercent2Var', 'UnitCustom1Var_1', 'UnitCustom2Var_1'):
            if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', fields[key]):
                raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Unit-conversion operands must be explicitly qualified finite literals', field=key)
        captions = native.get('unit_captions')
        if (fields.get('ShowUnit') != '0' or not isinstance(captions, list) or not captions
                or not any(isinstance(c, dict) and c.get('language') == 0 for c in captions)
                or any(not isinstance(c, dict) or c.get('text') != '' or c.get('byte_count') != 2 for c in captions)):
            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'A separate unit text owner requires disabled, empty embedded captions in every language')
        return observed

    @staticmethod
    def _numeric_matches(element, native, tags, schema):
        intent = FileService._numeric_intent(element, tags, schema)
        verify_numeric_fields(native['native_fields'], intent, schema)

    def plan_changes(self, session_id, design, operations, idempotency_key):
        session = self._session(session_id)
        if not isinstance(design, dict) or (operations is not None and not isinstance(operations, list)):
            raise HmiError("PLAN", "Design and an operation array (or null for automatic compilation) are required")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise HmiError("IDEMPOTENCY", "A nonempty idempotency key is required")
        with session["lock"]:
            self._fresh(session)
            if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_edit':
                self._edit_assets(design)
            fingerprint = canonical_hash({"design": design, "operations": operations})
            if idempotency_key in session["keys"]:
                prior = session["plans"][session["keys"][idempotency_key]]
                if prior["fingerprint"] != fingerprint:
                    raise HmiError("IDEMPOTENCY_CONFLICT", "Key was already used for a different plan")
                return copy.deepcopy(prior["receipt"])
            automatic = operations is None
            if automatic:
                operations = self._compile_operations(session, design)
            contract = self._contract(session, design, operations)
            plan_id = canonical_hash(contract)
            receipt = {"plan_id": plan_id, **contract,
                       "findings": validate_design(design, session["profile"]),
                       "operations": copy.deepcopy(operations),
                       "approval_required": True, "native_vendor_test": "NOT_RUN",
                       "planning_mode": "COMPILED_FROM_DESIGN" if automatic else "EXPLICIT_OPERATIONS"}
            session["plans"][plan_id] = dict(design=copy.deepcopy(design), operations=copy.deepcopy(operations),
                                             fingerprint=fingerprint, receipt=receipt)
            session["keys"][idempotency_key] = plan_id
            return copy.deepcopy(receipt)

    def _plan(self, session, plan_id):
        if plan_id not in session["plans"]:
            raise HmiError("PLAN_ID", "Unknown plan in this session")
        return session["plans"][plan_id]

    def preview(self, session_id, plan_id, output_path=None, values=None, states=None, valid=True):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            plan = self._plan(session, plan_id)
            if (session.get('calibration') is not None and session['calibration']['mode'] == 'diascreen_control_append'
                    and (values is not None or states is not None)):
                raise HmiError('DIA_CONTROL_SAMPLE_UNQUALIFIED', 'Source-clone preview has no logical process sample or runtime state contract')
            images = None
            if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_edit':
                assets, _ = self._edit_assets(plan['design'])
                # Validate source page ownership and PNG decoding before showing
                # even the background-only browser illustration.
                self._edit_operations(session, plan['design'])
                images = {s['native_id']: assets[s['native_background']['asset_sha256']]
                    for s in plan['design']['screens'] if 'native_background' in s}
            html = render_preview(plan["design"], session["profile"], values, states, valid, background_images=images)
            result = {"html": html, "design_sha256": plan["receipt"]["design_sha256"],
                      "render_kind": "CONCEPTUAL_IR", "native_visual_acceptance": "NOT_RUN"}
            if output_path:
                result["output"] = self._write_new(output_path, html.encode("utf-8"), None)
            return result

    def validate(self, session_id, plan_id):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            plan = self._plan(session, plan_id)
            findings = validate_design(plan["design"], session["profile"])
            if session["source_bytes"] is None:
                findings.append({"severity": "error", "code": "NATIVE_SOURCE_REQUIRED",
                                 "message": "Native production requires a vendor-derived source"})
            if not session["profile"].get("native_schema", {}).get("qualified"):
                findings.append({"severity": "error", "code": "NATIVE_SCHEMA_UNVERIFIED",
                                 "message": "This exact native schema is not qualified"})
            calibrated = session.get('calibration') is not None
            if session['profile'].get('fixture_kind') != 'synthetic' and not calibrated:
                findings.append({'severity': 'error', 'code': 'PRODUCTION_EMISSION_PENDING', 'message': 'This release has no full vendor-qualified compiler; real native emission is closed'})
            if not findings and calibrated:
                try:
                    expected_operations = self._candidate_operations(session, plan['design'])
                    if plan['operations'] != expected_operations:
                        raise HmiError('NATIVE_CANDIDATE_SCOPE', 'Operations must exactly cover the approved existing-owner text/geometry intent')
                    self._candidate_matches(session, plan['design'], NativeAdapter(self._emit(session, plan['operations'], plan['design']), session['profile']['family']))
                except HmiError as exc:
                    findings.append({'severity': 'error', 'code': exc.code, 'message': str(exc)})
                return {'findings': findings, 'offline_pass': not findings, 'vendor': 'NOT_RUN', 'physical': 'NOT_RUN',
                        'scope': self._candidate_scope(session),
                        'opaque_graph_dependencies': 'UNKNOWN', 'native_visual': 'NOT_RUN', 'program_writer_complete': False}
            if not findings and plan['design'].get('macros'):
                try:
                    self._macro_operations(session, plan['design'], preflight=True)
                except HmiError as exc:
                    findings.append({'severity': 'error', 'code': exc.code, 'message': str(exc)})
            if not findings:
                try:
                    self._alarm_operations(session, plan['design'])
                    self._alarm_views_preflight(session, plan['design'])
                except HmiError as exc:
                    findings.append({'severity': 'error', 'code': exc.code, 'message': str(exc)})
            if not findings:
                try:
                    self._operation_intent(session, plan['design'], plan['operations'])
                except HmiError as exc:
                    findings.append({'severity': 'error', 'code': exc.code, 'message': str(exc)})
            return {"findings": findings, "offline_pass": not findings, "vendor": "NOT_RUN", "physical": "NOT_RUN"}

    def _approval(self, session, plan, approval_path):
        try:
            path = self._path(approval_path, exists=True)
            _, approval = _json_object(path, 'APPROVAL')
        except (OSError, UnicodeError, ValueError) as exc:
            raise HmiError('APPROVAL', 'An exact readable UTF-8 approval object is required') from exc
        if not isinstance(approval, dict):
            raise HmiError('APPROVAL', 'Approval must be a JSON object')
        if approval.get("approved") is not True:
            raise HmiError("APPROVAL", "An approved receipt is required")
        authority = approval.get("authority")
        synthetic = session["profile"].get("fixture_kind") == "synthetic"
        if authority == "task_start":
            if self.task_authorizer is None:
                raise HmiError("APPROVAL", "Task-start authority requires a trusted server-side job authorizer")
            self.task_authorizer(session, plan, approval)
        elif authority == "neutral_fixture_qualification":
            actual = session.get('inventory') or {}
            if (not synthetic or approval.get("purpose") != "qualification_only"
                    or actual.get('model_id') != 'SYNTHETIC' or actual.get('editor_version') != '0.0'):
                raise HmiError("APPROVAL", "Qualification exception requires an actual original SYNTHETIC/0.0 source; origin labels are no authority")
        elif (authority != "direct_human" or not isinstance(approval.get('human_reference'), str)
                or not approval['human_reference'].strip() or len(approval['human_reference']) > 1000
                or any(c in approval['human_reference'] for c in '\r\n\0')):
            raise HmiError("APPROVAL", "Production requires a recorded direct human design approval")
        expected = {k: plan["receipt"][k] for k in self._contract(session, plan["design"], plan["operations"])}
        if any(approval.get(k) != v for k, v in expected.items()):
            raise HmiError("STALE_APPROVAL", "Approval does not match the exact source/design/profile/operations")
        return byte_hash(json.dumps(approval, sort_keys=True).encode())

    @staticmethod
    def _candidate_scope(session):
        if (session['calibration']['mode']=='existing_edit'
                and 'existing_entry_permission' in session['profile']['native_schema']):
            return 'SOURCE_PINNED_EXISTING_ENTRY_PERMISSION_STORED_ONLY'
        if (session['calibration']['mode']=='existing_edit'
                and 'existing_integer_numeric' in session['profile']['native_schema']):
            return 'SOURCE_PINNED_EXISTING_WORD_NUMERIC_PRESENTATION_BACKGROUND'
        return {'diascreen_bound_buttons':'SOURCE_BOUND_MAINTAINED_NEW_EXPLICIT_ADDRESS_STORED_ONLY',
                'diascreen_control_append':'STORED_CONTROL_APPEND_SHARED_SOURCE_BINDINGS',
                'control_generation':'APPEND_SOURCE_CALIBRATED_CONTROLS',
                'existing_edit':'SOURCE_PINNED_EXISTING_PRESENTATION_BACKGROUND',
                'existing_program':'SOURCE_PINNED_INERT_LITERAL_DELETION',
                'blank_program':'BLANK_TARGET_SOURCE_LIBRARY_CONTROLS',
                'multipage_program':'BLANK_TARGET_THREE_SOURCE_MULTIPAGE',
                'literal_page_generation':'APPEND_LITERAL_PAGES',
                'existing_owner_candidate':'EXISTING_OWNER_TEXT_GEOMETRY'}[session['calibration']['mode']]

    def _native_matches(self, session, design, inventory, candidate):
        """Cross-check controlled design against actual decoded native objects.

        A calibrated source reference is mandatory. Native style semantics remain
        UNVERIFIED without a vendor renderer; this never produces visual PASS.
        """
        schema = session["profile"]["native_schema"]
        profile = session['profile']
        if session.get('calibration') is not None:
            self._candidate_matches(session, design, candidate)
            return
        if profile.get('fixture_kind') != 'synthetic' or inventory['model_id'] != 'SYNTHETIC' or inventory['editor_version'] != '0.0':
            raise HmiError('NATIVE_TARGET_MISMATCH', 'Only original SYNTHETIC/0.0 transaction fixtures may be emitted in this release')
        if not model_ids_match(inventory['model_id'], profile.get('model_id')) or inventory['editor_version'] != profile.get('editor_version'):
            raise HmiError('NATIVE_TARGET_MISMATCH', 'Native model and editor must match even for a no-op')
        original = NativeAdapter(session['source_bytes'], profile['family'])
        original.verify_layout_order()
        candidate.verify_layout_order()
        self._alarm_operations(session, design)
        self._alarm_views_preflight(session, design, candidate)
        tags = {tag["id"]: tag for tag in design["tags"]}
        screens = {s["id"]: s for s in inventory["screens"]}
        source_screens = {s['id']: s for s in session['inventory']['screens']}
        if not set(source_screens) <= set(screens):
            raise HmiError('NATIVE_SCREEN_PLAN_UNVERIFIED', 'Source page deletion is unqualified')
        for sid in set(screens) - set(source_screens):
            donor = schema.get('screen_donor')
            source = source_screens.get(str(donor.get('screen_id'))) if isinstance(donor, dict) else None
            if not isinstance(donor, dict) or set(donor) != {'screen_id'} or source is None or source['elements']:
                raise HmiError('NATIVE_SCREEN_DONOR_UNSAFE', 'New pages need the immutable empty source donor baseline')
            if original.page_baseline(source['id']) != candidate.page_baseline(sid):
                raise HmiError('NATIVE_SCREEN_DONOR_UNSAFE', 'Saved new page has an undeclared page-level baseline')
        declared_screens = [str(s.get('native_id', s['id'])) for s in design['screens']]
        if len(set(declared_screens)) != len(declared_screens) or declared_screens != list(screens):
            raise HmiError('NATIVE_DESIGN_MISMATCH', 'Preview must account for every editable native screen in its actual order')
        for screen in design["screens"]:
            ref = str(screen.get("native_id", screen["id"]))
            if ref not in screens:
                raise HmiError("NATIVE_DESIGN_MISMATCH", "Design screen is absent from native output", screen_id=ref)
            elements = {e["id"]: e for e in screens[ref]["elements"]}
            if screens[ref]['name'] != screen['name']:
                raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved native page name differs from approved design')
            fields = screens[ref]['native_fields']
            for prefix in ('DocSize', 'PanelSize'):
                if fields.get(prefix + 'X') != str(screen['width']) or fields.get(prefix + 'Y') != str(screen['height']):
                    raise HmiError('NATIVE_DESIGN_MISMATCH', 'Native screen dimensions differ from preview')
            declared_elements = [str(e.get('native_id', e['id'])) for e in screen['elements']]
            if len(set(declared_elements)) != len(declared_elements) or declared_elements != list(elements):
                raise HmiError('NATIVE_DESIGN_MISMATCH', 'Preview must account for every editable native object in its actual layer order')
            for element in screen["elements"]:
                ref = str(element.get("native_id", element["id"]))
                native = elements.get(ref)
                if native is None:
                    raise HmiError("NATIVE_DESIGN_MISMATCH", "Design element is absent from native output", element_id=ref)
                numeric = element['kind'] in {'numeric_input', 'numeric_display'}
                alarm_view = element['kind'] in _ALARM_VIEW_KINDS
                if element['kind'] not in {'button', 'text', 'indicator', 'goto'} and not numeric and not alarm_view:
                    raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Object kind has no calibrated source-local emitter')
                kind = schema.get('numeric', {}).get('kinds', {}).get(element['kind']) if numeric else schema.get('kinds', {}).get(element['kind'])
                if not isinstance(kind, dict) or not kind or any(str(native['native_fields'].get(k)) != str(v) for k, v in kind.items()):
                    raise HmiError('NATIVE_KIND_UNVERIFIED', 'Native object kind does not match a calibrated mapping', element_id=ref)
                if numeric:
                    self._numeric_unit_owners(candidate, screens[str(screen.get('native_id', screen['id']))])
                unit_fields = self._numeric_unit_fields(element, native, schema) if numeric else set()
                visual_fields = self._visual_fields(element, native, schema, unit_fields) if not alarm_view else []
                for key in ("x", "y", "width", "height"):
                    if native.get("geometry", {}).get(key) != element[key]:
                        raise HmiError("NATIVE_DESIGN_MISMATCH", "Saved geometry differs from approved design", element_id=ref, field=key)
                if alarm_view:
                    # Complete owner/State/language/column/time bytes were
                    # already compared to the immutable source above.
                    continue
                for direction in ("read", "write"):
                    tag_id = element.get("binding", {}).get(direction)
                    actual_binding = native.get('bindings', {}).get(direction, {})
                    if tag_id:
                        tag = tags[tag_id]
                        contract = self._binding_contract(schema, tag)
                        for field in ('data_type', 'channel', 'station', 'byte_order', 'word_order'):
                            if field not in contract or tag.get(field) != contract[field]:
                                raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Native binding engineering contract differs from calibration', field=field)
                        metadata = tag.get('native_binding')
                        if not isinstance(metadata, dict) or set(metadata) != {'link', 'mem_type'}:
                            raise HmiError('NATIVE_BINDING_UNVERIFIED', 'Native binding metadata must be explicit and calibrated', element_id=ref)
                        expected_binding = {'address': tag['address'], **{k: str(v) for k, v in metadata.items()}}
                        if actual_binding != expected_binding:
                            raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved address/link/memory type differs from approved binding', element_id=ref)
                    elif actual_binding.get('address') not in (None, '', 'None'):
                        raise HmiError('NATIVE_DESIGN_MISMATCH', 'Native has a binding missing from approved design', element_id=ref, direction=direction)
                required = [(s["value"], s["text"]) for s in element.get("states", [])]
                native_states = native.get('states', [])
                native_values = [s.get('value') for s in native_states]
                if any(type(v) is not int for v in native_values):
                    raise HmiError('NATIVE_DESIGN_MISMATCH', 'Native states require explicit integer Values')
                expected_values = [v for v, text in required] if required else schema.get('state_values', {}).get(element['kind'])
                if not isinstance(expected_values, list) or sorted(native_values) != sorted(expected_values):
                    raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved native state values/count differ from the approved or calibrated state contract')
                if not required and 'text' not in element:
                    if not numeric:
                        raise HmiError('NATIVE_TEXT_REQUIRED', 'Declare every native caption explicitly')
                    if any(t['text'] for t in native['texts'] if t['language'] == 0):
                        raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Numeric donor contains an unmanaged caption')
                if not required and element.get("text") is not None:
                    required = [(v, element["text"]) for v in expected_values]
                actual = {(t["state_index"], t["language"]): t["text"] for t in native.get("texts", [])}
                for state, text in required:
                    matches = [s['state_index'] for s in native_states if s.get('value') == state]
                    if len(matches) != 1 or actual.get((matches[0], 0)) != text:
                        raise HmiError("NATIVE_DESIGN_MISMATCH", "Saved state text differs from approved design", element_id=ref, state=state)
                for state in element.get('states', []):
                    spec = schema.get('state_fill', {})
                    matches = [s for s in native.get('states', []) if s.get('value') == state['value']]
                    if len(matches) != 1 or matches[0]['native_fields'].get(spec.get('field')) != str(self._native_color(state['fill'], spec.get('encoding'))):
                        raise HmiError('NATIVE_STYLE_UNVERIFIED', 'Native state fill differs from calibrated design color')
                for key, value, fields, index in visual_fields:
                    spec = schema['properties'][key]
                    if fields.get(spec['field']) != str(value):
                        raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved native style scalar differs from approved intent', field=key)
                if element['kind'] == 'goto':
                    target = next(s for s in design['screens'] if s['id'] == element['target_screen'])
                    target_id = str(target.get('native_id', target['id']))
                    navigation = self._navigation_contract(schema, kind)
                    if (not isinstance(navigation, dict) or navigation.get('qualified') is not True
                            or navigation.get('field') != 'GoToScreenID' or navigation.get('match') != kind
                            or native['native_fields'].get('GoToScreenID') != target_id):
                        raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved navigation target differs from the exact qualified contract')
                    if 'GoToScreenName' in native['native_fields']:
                        if (navigation.get('name_field') != 'GoToScreenName' or navigation.get('name_encoding') != 'ascii'
                                or not target['name'].isascii() or any(c in target['name'] for c in '\r\n\x00')
                                or native['native_fields']['GoToScreenName'] != target['name']):
                            raise HmiError('NATIVE_DESIGN_MISMATCH', 'Saved navigation companion name differs from the target page')
                # Units require their own caption and geometry contract.
                for field in (() if numeric else ('unit', 'format', 'minimum', 'maximum', 'fractional')):
                    if field in element:
                        raise HmiError('NATIVE_FEATURE_UNVERIFIED', 'Declared design field has no native emitter in this release', field=field)
                if numeric:
                    self._numeric_matches(element, native, tags, schema)
                    source_sid, source_eid = str(screen.get('native_id', screen['id'])), ref
                    source_screen = source_screens.get(source_sid)
                    source_element = next((e for e in source_screen['elements'] if e['id'] == ref), None) if source_screen else None
                    if source_element is None:
                        donors = schema.get('donors')
                        kinds = donors.get(element['kind']) if isinstance(donors, dict) else None
                        data_type = tags[element['binding']['write' if element['kind'] == 'numeric_input' else 'read']]['data_type']
                        donor = kinds.get(data_type) if isinstance(kinds, dict) else None
                        if not isinstance(donor, dict) or set(donor) != {'screen_id', 'element_id'}:
                            raise HmiError('NATIVE_DONOR_REQUIRED', 'Numeric context requires the immutable source donor')
                        source_sid, source_eid = str(donor['screen_id']), str(donor['element_id'])
                        source_screen = source_screens.get(source_sid)
                        source_element = next((e for e in source_screen['elements'] if e['id'] == source_eid), None) if source_screen else None
                        if source_element is None:
                            raise HmiError('NATIVE_DONOR_REQUIRED', 'Numeric source donor is absent')
                    self._numeric_unit_owners(original, source_screen)
                    source_unit_fields = self._numeric_unit_fields(element, source_element, schema)
                    if unit_fields or source_unit_fields:
                        if original.unit_context_baseline(source_sid, source_eid) != candidate.unit_context_baseline(str(screen.get('native_id', screen['id'])), ref):
                            raise HmiError('NATIVE_UNIT_UNVERIFIED', 'Saved numeric unit context differs from its immutable source owner')
                if element.get("behavior"):
                    prop = schema.get("properties", {}).get("behavior", {})
                    expected = prop.get("values", {}).get(element["behavior"])
                    if expected is None or str(native["native_fields"].get(prop.get("field"))) != str(expected):
                        raise HmiError("NATIVE_DESIGN_MISMATCH", "Button native behavior differs from approved design", element_id=ref)
        self._macros_match(session, design, candidate)
        expected_tail = expected_alarm_tail(original.document.tail, design['alarms'], design['tags'], schema)
        if candidate.document.tail != expected_tail:
            raise HmiError('UNDECLARED_RESOURCE_CHANGE', 'Global resources differ from immutable source plus approved existing alarm messages')

    def apply_plan(self, session_id, plan_id, approval_path):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            plan = self._plan(session, plan_id)
            approval_sha = self._approval(session, plan, approval_path)
            validation = self.validate(session_id, plan_id)
            if validation["findings"]:
                raise HmiError("VALIDATION", "Plan has blocking validation findings", findings=validation["findings"])
            if session["applied"] and session["applied"]["plan_id"] == plan_id:
                return copy.deepcopy(session["applied"]["receipt"])
            data = self._emit(session, plan['operations'], plan['design'])
            candidate = NativeAdapter(data, session["profile"]["family"])
            inventory = candidate.inspect()
            self._native_matches(session, plan["design"], inventory, candidate)
            self._fresh(session)
            receipt = {"plan_id": plan_id, "candidate_sha256": byte_hash(data), "approval_sha256": approval_sha,
                       "offline_integrity": "PASS", "native_visual": "NOT_RUN", "vendor": "NOT_RUN", "physical": "NOT_RUN",
                       "purpose": "OFFLINE_NATIVE_CANDIDATE" if session.get('calibration') is not None and session['profile'].get('fixture_kind') != 'synthetic' else "SYNTHETIC_TRANSACTION_ONLY",
                       "production_native": "UNAVAILABLE", "program_writer_complete": False}
            if session.get('calibration') is not None:
                receipt.update(calibration_sha256=session['calibration']['sha256'],
                               scope=self._candidate_scope(session),
                               opaque_graph_dependencies='UNKNOWN')
            session["applied"] = dict(plan_id=plan_id, data=data, receipt=receipt, saved={}, approval_path=approval_path)
            return copy.deepcopy(receipt)

    def _write_new(self, output_path, data, verifier):
        destination = self._path(output_path)
        if destination.exists():
            raise HmiError("OUTPUT_EXISTS", "Output exists; choose a new revision path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Re-resolve after creating directories to detect path redirection.
        destination = self._path(output_path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".uhmi-", delete=False) as file:
                temporary = Path(file.name)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            saved = temporary.read_bytes()
            if saved != data:
                raise HmiError("SAVE_INTEGRITY", "Temporary file failed byte verification")
            if verifier:
                verifier(saved)
            # Atomic create-if-absent on same-volume filesystems. Never replace.
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise HmiError("OUTPUT_EXISTS", "Another writer created this revision") from exc
            return {"path": str(destination), "sha256": byte_hash(saved), "bytes": len(saved)}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_as(self, session_id, output_path):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            applied = session["applied"]
            if applied is None:
                raise HmiError("NOT_APPLIED", "Apply an approved plan first")
            plan = session['plans'][applied['plan_id']]
            self._approval(session, plan, applied['approval_path'])
            if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_edit':
                self._edit_assets(plan['design'])
            destination = self._path(output_path)
            if destination == session["source"]:
                raise HmiError("SOURCE_OVERWRITE", "Source overwrite is unavailable")
            if destination.suffix.lower() != (".dpa" if session["profile"]["family"] == "delta_diascreen" else ".dps"):
                raise HmiError("OUTPUT_FORMAT", "Output extension must match the selected adapter")
            if output_path in applied["saved"]:
                receipt = applied["saved"][output_path]
                if destination.exists() and byte_hash(destination.read_bytes()) == receipt["sha256"]:
                    return copy.deepcopy(receipt)
                raise HmiError("OUTPUT_CHANGED", "Previously saved output has changed")
            plan = session["plans"][applied["plan_id"]]

            def verify(data):
                candidate = NativeAdapter(data, session["profile"]["family"])
                inventory = candidate.inspect()
                self._native_matches(session, plan["design"], inventory, candidate)
                if byte_hash(data) != applied['receipt']['candidate_sha256']:
                    raise HmiError('SAVE_INTEGRITY', 'Applied candidate changed after its checked receipt')
                self._fresh(session)
                self._approval(session, plan, applied['approval_path'])

            receipt = self._write_new(output_path, applied["data"], verify)
            try:
                self._fresh(session)
                self._approval(session, plan, applied['approval_path'])
                if session.get('calibration') is not None and session['calibration']['mode'] == 'existing_edit':
                    self._edit_assets(plan['design'])
            except BaseException:
                # Own newly created candidate only; preserve source and other files.
                try:
                    own = self._path(output_path, exists=True)
                    if own.is_file() and byte_hash(own.read_bytes()) == receipt['sha256']:
                        own.unlink()
                except (OSError, HmiError):
                    pass
                raise
            receipt.update(vendor="NOT_RUN", physical="NOT_RUN", native_visual="NOT_RUN")
            applied["saved"][output_path] = receipt
            return copy.deepcopy(receipt)

    def diff(self, session_id):
        session = self._session(session_id)
        with session["lock"]:
            self._fresh(session)
            applied = session["applied"]
            return {"source_sha256": session["source_sha256"],
                    "candidate_sha256": byte_hash(applied["data"]) if applied else None,
                    "byte_equal": applied["data"] == session["source_bytes"] if applied else None,
                    "operations": copy.deepcopy(session["plans"][applied["plan_id"]]["operations"]) if applied else [],
                    "candidate_inventory": NativeAdapter(applied["data"], session["profile"]["family"]).inspect() if applied else None,
                    "limitation": "Semantic inventory and byte hashes; no vendor rendering or runtime assertion"}
