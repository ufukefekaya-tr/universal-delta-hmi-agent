"""Create a source-local inert-literal deletion profile; never native output.

Only the registered, independently reviewed stored-file B10 graph is admitted.
The generated witness is not a vendor compile, image or runtime acceptance.
"""
import argparse
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups, canonical_model_id
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.native.existing_program import ExistingProgram
from universal_hmi.service import FileService, byte_hash, _json_object


ROOT = Path(__file__).resolve().parents[1]


def calibrate(workspace, source, output_dir, source_reference, review_reference):
    service = FileService(workspace, ROOT / 'profiles')
    for value in (source_reference, review_reference):
        if not isinstance(value, str) or not value.strip() or len(value) > 1000 or any(c in value for c in '\r\n\0'):
            raise HmiError('NATIVE_CALIBRATION', 'Explicit bounded source and review references are required')
    with service._path(source, exists=True).open('rb') as stream:
        data = stream.read(MAX_PAYLOAD + 1)
    if len(data) > MAX_PAYLOAD:
        raise HmiError('NATIVE_CALIBRATION', 'Native source exceeds the bounded file size')
    original = NativeAdapter(data, 'delta_dopsoft2')
    book_path = service._existing_authority_dir() / 'dopsoft2_b10_inert_literals.json'
    book_raw, book = _json_object(book_path, 'EXISTING_AUTHORITY')
    service._validate_existing_book(book)
    schema = {'qualified': True, 'existing_program': dict(qualified=True, contract_version=1,
        mode='source_inert_literal_deletion', source_sha256=byte_hash(data), family=original.family,
        model_id=canonical_model_id(original.model_id), editor_version=original.editor_version,
        authority_sha256=byte_hash(book_raw))}
    ExistingProgram(original, schema).check()
    dimensions = [[int(p['section'].one('PanelSizeX').value), int(p['section'].one('PanelSizeY').value)]
                  for p in _groups(original.document)]
    if not dimensions or any(dim != dimensions[0] for dim in dimensions):
        raise HmiError('NATIVE_CALIBRATION', 'All source pages require one exact panel resolution')
    identifier = 'existing_program_v1'
    profile = dict(id=identifier, family=original.family, model_id=schema['existing_program']['model_id'],
        editor_version=original.editor_version, resolution=dimensions[0],
        capabilities={'native_preserved': 'OFFLINE_PASS'}, native_schema=schema,
        limitation='Exact source-pinned inert literal deletion only. Survivor bytes, addresses and background assets retained. No native visual/vendor/runtime qualification; full V1 remains open.')
    registry = service._existing_authority(schema, profile, byte_hash(data))
    witness = dict(contract_version=1, mode='existing_program', source_sha256=byte_hash(data),
        family=original.family, model_id=profile['model_id'], serialized_version=original.editor_version,
        resolution=dimensions[0], schema_sha256=canonical_hash(schema), source_origin='user_vendor_project',
        source_reference=source_reference, review_reference=review_reference)
    witness_path = output_dir + '/existing_calibration.json'
    witness_raw = (json.dumps(witness, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    schema['native_candidate'] = dict(qualified=True, contract_version=1, mode='existing_program',
        path=witness_path, sha256=byte_hash(witness_raw))

    def fresh(_):
        try:
            with service._path(source, exists=True).open('rb') as stream:
                current = stream.read(len(data) + 1)
        except (OSError, HmiError) as exc:
            raise HmiError('CALIBRATION_CHANGED', 'Source became unavailable during calibration') from exc
        if current != data:
            raise HmiError('CALIBRATION_CHANGED', 'Source changed while calibration was created')
        path, digest, length = registry
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise HmiError('CALIBRATION_CHANGED', 'Registered authority became a link')
        try:
            with path.open('rb') as stream:
                raw = stream.read(length + 1)
        except OSError as exc:
            raise HmiError('CALIBRATION_CHANGED', 'Registered authority became unavailable during calibration') from exc
        if len(raw) != length or byte_hash(raw) != digest:
            raise HmiError('CALIBRATION_CHANGED', 'Registered authority changed during calibration')

    outputs = [service._write_new(witness_path, witness_raw, fresh),
        service._write_new(output_dir + '/profiles/' + identifier + '.json',
            (json.dumps(profile, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), fresh)]
    return dict(scope='SOURCE_PINNED_INERT_LITERAL_DELETION_CALIBRATION', source_sha256=byte_hash(data),
        outputs=outputs, native_output='NOT_CREATED', vendor='NOT_RUN', native_pixels='NOT_RUN', physical='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'source', 'output-dir', 'source-reference', 'review-reference'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(calibrate(args.workspace, args.source, args.output_dir, args.source_reference,
                               args.review_reference), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
