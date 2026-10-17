"""Create portable source-local editing contracts, never a native HMI output.

Existing literal edits and a separate appended literal-page experiment are
represented. Raw-byte calibration is not editor, driver, appearance or panel
acceptance. Opaque graph dependencies remain unknown after adding pages.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, canonical_model_id, _groups
from universal_hmi.service import FileService, byte_hash
from universal_hmi.validation import validate_design

ROOT = Path(__file__).resolve().parents[1]


def create_contracts(workspace, source_path, family, output, editable, origin, source_reference, review_reference,
                     mode='existing_owner_candidate', page_donor=None, text_donor=None, prefix_policy=None):
    if prefix_policy is not None and (prefix_policy != 'diascreen_opaque_source_v1'
            or family != 'delta_diascreen' or mode != 'existing_owner_candidate'):
        raise HmiError('NATIVE_CALIBRATION', 'Opaque DIAScreen retention is a separate existing-owner policy only')
    if origin == 'manufacturer_installed_example' and prefix_policy != 'diascreen_opaque_source_v1':
        raise HmiError('NATIVE_CALIBRATION', 'Installed-example provenance is scoped to the opt-in DIAScreen candidate policy')
    paths = FileService(workspace, ROOT / 'profiles')
    source_file = paths._path(source_path, exists=True)
    suffix = '.dps' if family == 'delta_dopsoft2' else '.dpa'
    if source_file.suffix.lower() != suffix:
        raise HmiError('OUTPUT_FORMAT', 'Source extension must also match the selected content adapter')
    source = source_file.read_bytes()
    adapter = NativeAdapter(source, family)
    inventory = adapter.inspect()
    first = inventory['screens'][0] if inventory['screens'] else None
    if first is None:
        raise HmiError('NATIVE_SOURCE_REQUIRED', 'A source with existing native pages is required')
    resolution = [int(first['native_fields'][key]) for key in ('DocSizeX', 'DocSizeY')]
    properties = {key: dict(field=field, scope='element', type='int', min=0, max=max(resolution))
                  for key, field in {'x': 'X', 'y': 'Y', 'width': 'Width', 'height': 'Height'}.items()}
    prefix, sections = adapter._preserved_prefix(adapter.document, prefix_policy=prefix_policy)
    schema = dict(qualified=True, properties=properties, kinds={'text': {'Type': '10', 'SubType': '6'}},
        preserved_layout=dict(qualified=True, contract_version=1, mode='existing_owner_edits', source_sha256=byte_hash(source),
                              prefix_sha256=byte_hash(prefix), sections=sections))
    if prefix_policy is not None:
        schema['preserved_layout'].update(contract_version=2, prefix_policy=prefix_policy)
    if mode not in ('existing_owner_candidate', 'literal_page_generation'):
        raise HmiError('NATIVE_CALIBRATION', 'Unknown source-local candidate mode')
    if mode == 'literal_page_generation':
        if editable or not isinstance(page_donor, str) or re.fullmatch(r'[1-9][0-9]{0,9}', page_donor) is None:
            raise HmiError('NATIVE_CALIBRATION', 'Generation needs an exact positive header donor and a separate literal donor')
        if not isinstance(text_donor, str) or re.fullmatch(r'[1-9][0-9]{0,9}/[1-9][0-9]{0,9}', text_donor) is None:
            raise HmiError('NATIVE_CALIBRATION', 'Generation needs a canonical screen/element literal donor')
        sid, eid = text_donor.split('/')
        page = next((s for s in _groups(adapter.document) if s['id'] == page_donor), None)
        if page is None:
            raise HmiError('NATIVE_CALIBRATION', 'Page donor is absent from immutable source')
        auxiliary = adapter._plain_extent(page)
        schema.pop('preserved_layout')
        schema['literal_generation'] = dict(qualified=True, contract_version=1, mode=mode,
            source_sha256=byte_hash(source), prefix_sha256=byte_hash(prefix), sections=sections,
            page_donor=dict(screen_id=page_donor, header_sha256=byte_hash(page['section'].bytes()), aux_sha256=byte_hash(auxiliary.bytes())),
            text_donor=dict(screen_id=sid, element_id=eid, owner_sha256=adapter.owner_extent_sha256(sid, eid)))
        editable = [text_donor]
    elif page_donor is not None or text_donor is not None:
        raise HmiError('NATIVE_CALIBRATION', 'Generation donors cannot be attached to existing-owner mode')
    profile_id = 'literal_generation_v1' if mode == 'literal_page_generation' else 'existing_owner_v1'
    profile = dict(id=profile_id, family=family, model_id=canonical_model_id(adapter.model_id),
        editor_version=adapter.editor_version, resolution=resolution, model='SOURCE_PINNED_EXISTING_MODEL',
        vendor_executable_build=None, vendor_acceptance='UNVERIFIED', driver='PRESERVE_SOURCE_UNQUALIFIED',
        fixture_kind='synthetic' if origin == 'original_neutral_fixture' else origin,
        capabilities={'text': 'OFFLINE_PASS', 'native_preserved': 'OFFLINE_PASS'}, native_schema=schema,
        limitation=('Header-only appended pages and literal objects; opaque graph dependencies UNKNOWN, no command/driver/vendor qualification'
                    if mode == 'literal_page_generation' else
                    'Existing owner caption/geometry with unchanged byte extents only; no full program writing or vendor qualification'))
    adapter._schema(profile)
    adapter.verify_layout_order(schema)
    owners = []
    seen = set()
    for reference in editable:
        if not isinstance(reference, str) or re.fullmatch(r'(0|[1-9][0-9]{0,9})/(0|[1-9][0-9]{0,9})', reference) is None:
            raise HmiError('INVALID_ID', 'Editable text must be a canonical screen/element identity')
        sid, eid = reference.split('/')
        if reference in seen or int(sid) > 2147483647 or int(eid) > 2147483647:
            raise HmiError('INVALID_ID', 'Editable owner is repeated or outside the native identity range')
        seen.add(reference)
        FileService._literal_text_owner(adapter.document, sid, eid)
        owners.append(dict(screen_id=sid, element_id=eid, kind='text', owner_sha256=adapter.owner_extent_sha256(sid, eid)))
    series = adapter.application.one('PanelSeries').value.decode('latin-1')
    witness = dict(contract_version=1, mode=mode, source_sha256=byte_hash(source), family=family,
        model_id=profile['model_id'], serialized_version=adapter.editor_version, resolution=resolution,
        schema_sha256=canonical_hash(schema), source_origin=origin, source_reference=source_reference,
        review_reference=review_reference, panel_series=series, editable_owners=owners)
    out = paths._path(output).relative_to(paths.workspace).as_posix()
    calibration_path = out + '/CALIBRATION.json'
    encode = lambda value: (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    witness_bytes = encode(witness)
    schema['native_candidate'] = dict(qualified=True, contract_version=1, mode=mode, path=calibration_path, sha256=byte_hash(witness_bytes))
    design = dict(schema_version=1, project_id='source-local', profile_id=profile_id, tags=[], macros=[], alarms=[], screens=[])
    for page in inventory['screens']:
        design['screens'].append(dict(id='page_' + page['id'], native_id=page['id'], name=page['name'], width=resolution[0], height=resolution[1],
            elements=[dict(id='owner_' + page['id'] + '_' + e['id'], native_id=e['id'], kind='native_preserved', text='', **e['geometry'],
                           source_owner_sha256=adapter.owner_extent_sha256(page['id'], e['id'])) for e in page['elements']]))
    findings = validate_design(design, profile)
    if findings:
        raise HmiError('VALIDATION', 'Source-local retained design is invalid', findings=findings)
    files = {calibration_path: witness_bytes, out + '/profiles/' + profile_id + '.json': encode(profile), out + '/design.json': encode(design)}
    if any(paths._path(path).exists() for path in files):
        raise HmiError('OUTPUT_EXISTS', 'Contracts already exist; use a new version directory')
    created = {}
    try:
        for path, data in files.items():
            if source_file.read_bytes() != source:
                raise HmiError('SOURCE_CHANGED', 'Source changed during calibration')
            created[path] = paths._write_new(path, data, lambda raw: json.loads(raw.decode('utf-8')))
        session = dict(profile=profile, source_bytes=source, source_sha256=byte_hash(source), inventory=inventory)
        session['calibration'] = paths._load_candidate_calibration(session)
        paths._candidate_document(session, design)
        if source_file.read_bytes() != source:
            raise HmiError('SOURCE_CHANGED', 'Source changed during calibration')
    except (HmiError, OSError, ValueError):
        for path, receipt in created.items():
            own = paths._path(path)
            if own.exists() and byte_hash(own.read_bytes()) == receipt['sha256']:
                own.unlink()
        raise
    return dict(status='SOURCE_LOCAL_CONTRACTS_ONLY', scope='APPEND_LITERAL_PAGES' if mode == 'literal_page_generation' else 'EXISTING_OWNER_TEXT_GEOMETRY', source_sha256=byte_hash(source),
                files={path: receipt['sha256'] for path, receipt in created.items()}, editable_owners=list(editable),
                retained_owners=sum(len(page['elements']) for page in inventory['screens']),
                native_output='NOT_CREATED', opaque_graph_dependencies='UNKNOWN', native_visual='NOT_RUN', vendor='NOT_RUN', physical='NOT_RUN', program_writer_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--family', required=True, choices=['delta_dopsoft2', 'delta_diascreen'])
    parser.add_argument('--output', required=True, help='New workspace-relative contract version directory')
    parser.add_argument('--edit-text', action='append', default=[], help='Exact existing screen/element identity; repeat for additional owners')
    parser.add_argument('--mode', choices=['existing_owner_candidate', 'literal_page_generation'], default='existing_owner_candidate')
    parser.add_argument('--page-donor', help='Immutable header-only donor screen ID, generation mode only')
    parser.add_argument('--text-donor', help='Immutable screen/element literal donor, generation mode only')
    parser.add_argument('--origin', choices=['user_vendor_project', 'original_neutral_fixture', 'manufacturer_installed_example'], default='user_vendor_project')
    parser.add_argument('--prefix-policy', choices=['diascreen_opaque_source_v1'], help='Opt-in source-local opaque DIAScreen prefix retention; existing-owner mode only')
    parser.add_argument('--source-reference', required=True, help='Ownership/provenance reference; public examples are not owned user projects')
    parser.add_argument('--review-reference', required=True)
    args = parser.parse_args()
    try:
        result = create_contracts(args.workspace, args.source, args.family, args.output, args.edit_text, args.origin, args.source_reference, args.review_reference,
                                  mode=args.mode, page_donor=args.page_donor, text_donor=args.text_donor, prefix_policy=args.prefix_policy)
    except (HmiError, OSError, ValueError) as exc:
        print(json.dumps(dict(status='FAIL', code=exc.code if isinstance(exc, HmiError) else 'IO_OR_JSON', message=str(exc))))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
