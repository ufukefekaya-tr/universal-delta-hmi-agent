"""Create portable stored source-control clone contracts, not a native output.

The separately supplied source review is metadata, not proof of a real review
or license. Caller authority and later exact approval remain necessary. Every
source address/numeric/style/macro setting is immutable in this contract.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.diascreen_control_append import DiaScreenControlAppend, DONOR_IDS
from universal_hmi.service import FileService, _json_object, byte_hash
from universal_hmi.validation import validate_design

ROOT = Path(__file__).resolve().parents[1]


def capture_schema(adapter, authority_sha256):
    """Capture raw identity only; the separate native check rejects bad shapes."""
    pages = _groups(adapter.document)
    if not pages:
        raise HmiError('DIA_CONTROL_SOURCE', 'A source with observed pages is required')
    donors = {kind: dict(screen_id=sid, element_id=eid,
                        owner_sha256=adapter.owner_extent_sha256(sid, eid))
              for kind, (sid, eid) in DONOR_IDS.items()}
    pinned = []
    for page in pages:
        section = page['section']
        aux = adapter.document.sections[page['start'] + 1]
        pinned.append(dict(screen_id=page['id'], header_sha256=byte_hash(section.bytes()),
            aux_sha256=byte_hash(aux.bytes()), element_count=len(page['elements']),
            **{key: int(section.one(field).value) for key, field in {
                'doc_width': 'DocSizeX', 'doc_height': 'DocSizeY',
                'panel_width': 'PanelSizeX', 'panel_height': 'PanelSizeY'}.items()}))
    descriptor = dict(qualified=True, contract_version=1, mode='diascreen_source_control_append_v1',
        source_sha256=byte_hash(adapter.original), family='delta_diascreen', model_id='268502784',
        editor_version='6.0.00205.8268', authority_sha256=authority_sha256,
        prefix_sha256=byte_hash(b''.join(s.bytes() for s in adapter.document.sections[:pages[0]['start']])),
        tail_sha256=byte_hash(adapter.document.tail), target_screen_id='20', pages=pinned, donors=donors)
    schema = {'diascreen_control_append': descriptor}
    DiaScreenControlAppend(adapter, schema).check()
    return schema


def calibrate(workspace, source_path, output, origin, source_reference, review_reference, review_artifact):
    paths = FileService(workspace, ROOT / 'profiles')
    source_file = paths._path(source_path, exists=True)
    if source_file.suffix.lower() != '.dpa':
        raise HmiError('OUTPUT_FORMAT', 'This separate source-clone contract requires DPA content and extension')
    origins = {'original_neutral_fixture': 'synthetic', 'user_vendor_project': 'user_vendor_project',
               'manufacturer_installed_example': 'manufacturer_installed_example'}
    if not isinstance(origin, str) or origin not in origins:
        raise HmiError('NATIVE_CALIBRATION', 'An explicit original/user/manufacturer source origin is required')
    for reference in (source_reference, review_reference):
        if (not isinstance(reference, str) or not reference.strip() or len(reference) > 1000
                or any(c in reference for c in '\r\n\0')):
            raise HmiError('NATIVE_CALIBRATION', 'Source and review references must be bounded explicit text')
    raw = source_file.read_bytes()
    adapter = NativeAdapter(raw, 'delta_diascreen')
    review_raw, review = _json_object(paths._path(review_artifact, exists=True), 'NATIVE_CALIBRATION')
    captured = capture_schema(adapter, byte_hash(review_raw))
    descriptor = captured['diascreen_control_append']
    FileService._check_diascreen_control_authority(review, descriptor)
    inventory = adapter.inspect()
    schema = {'qualified': True, **captured}
    identifier = 'diascreen_source_clones_v1'
    profile = dict(id=identifier, family='delta_diascreen', model=inventory['panel_name'], model_id=268502784,
        editor_version=adapter.editor_version, resolution=[800, 480],
        driver='PRESERVED_SOURCE_DRIVER_UNVERIFIED', fixture_kind=origins[origin],
        capabilities={'native_preserved': 'OFFLINE_PASS', 'native_control_clone': 'OFFLINE_PASS'},
        numeric_types=[], native_schema=schema,
        limitation='Stored source copies only. Original addresses shared with controls/macros; no logical read sample, fresh memory, generic control, blank program, runtime, native-pixel or vendor acceptance.')
    witness = dict(contract_version=1, mode='diascreen_control_append', source_sha256=byte_hash(raw),
        family='delta_diascreen', model_id=268502784, serialized_version=adapter.editor_version,
        resolution=[800, 480], schema_sha256=canonical_hash(schema), source_origin=origin,
        source_reference=source_reference, review_reference=review_reference,
        authority={'path': review_artifact, 'sha256': byte_hash(review_raw)})
    witness_path = output + '/CALIBRATION.json'
    encode = lambda data: (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    witness_raw = encode(witness)
    schema['native_candidate'] = dict(qualified=True, contract_version=1, mode='diascreen_control_append',
                                    path=witness_path, sha256=byte_hash(witness_raw))
    design = dict(schema_version=1, project_id='source-control-append', profile_id=identifier,
                  tags=[], macros=[], alarms=[], screens=[])
    for page in inventory['screens']:
        fields = page['native_fields']
        design['screens'].append(dict(id='page_' + page['id'], native_id=page['id'], name=page['name'],
            width=int(fields['DocSizeX']), height=int(fields['DocSizeY']), elements=[
                dict(id='source_' + page['id'] + '_' + owner['id'], native_id=owner['id'],
                     kind='native_preserved', text='', **owner['geometry'],
                     source_owner_sha256=adapter.owner_extent_sha256(page['id'], owner['id']))
                for owner in page['elements']]))
    findings = validate_design(design, profile)
    if findings:
        raise HmiError('VALIDATION', 'Source contract cannot represent every retained page and owner', findings=findings)
    def fresh(_):
        if source_file.read_bytes() != raw or paths._path(review_artifact, exists=True).read_bytes() != review_raw:
            raise HmiError('SOURCE_CHANGED', 'Source or review artifact changed during calibration')
    outputs = [paths._write_new(witness_path, witness_raw, fresh),
               paths._write_new(output + '/profiles/' + identifier + '.json', encode(profile), fresh),
               paths._write_new(output + '/design.json', encode(design), fresh)]
    return dict(source_sha256=byte_hash(raw), scope='STORED_CONTROL_APPEND_SHARED_SOURCE_BINDINGS',
                outputs=outputs, native_pixels='NOT_RUN', vendor='NOT_RUN', runtime='NOT_RUN', program_writer_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'source', 'output', 'origin', 'source-reference', 'review-reference', 'review-artifact'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(calibrate(args.workspace, args.source, args.output, args.origin,
                             args.source_reference, args.review_reference, args.review_artifact), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
