"""Create blank-target/control-library contracts without native production.

All inputs belong to the selected workspace. No vendor executable, computer
control, fixed author path, macro, PLC connection or machine approval is added.
"""
import argparse
import copy
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, canonical_model_id
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.native.program import BlankProgram
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT = Path(__file__).resolve().parents[1]


def calibrate(workspace, target, library, library_profile, output_dir, source_reference, review_reference):
    service = FileService(workspace, ROOT / 'profiles')
    def read_native(relative):
        with service._path(relative, exists=True).open('rb') as stream:
            raw = stream.read(MAX_PAYLOAD + 1)
        if len(raw) > MAX_PAYLOAD:
            raise HmiError('NATIVE_CALIBRATION', 'Native calibration input is oversized')
        return raw
    target_bytes, library_bytes = read_native(target), read_native(library)
    profile_bytes, profile = _json_object(service._path(library_profile, exists=True), 'NATIVE_CALIBRATION')
    service._validate_profile(profile)
    family = profile['family']
    original, donor = NativeAdapter(target_bytes, family), NativeAdapter(library_bytes, family)
    library_spec = profile['native_schema'].get('native_candidate')
    if not isinstance(library_spec, dict) or library_spec.get('mode') != 'control_generation':
        raise HmiError('NATIVE_CALIBRATION', 'Library needs an existing six-control property calibration')
    library_calibration = service._load_control_calibration(dict(source_bytes=library_bytes,
        source_sha256=byte_hash(library_bytes),profile=profile,inventory=donor.inspect()),library_spec)
    library_schema = {k:copy.deepcopy(v) for k,v in profile['native_schema'].items() if k != 'native_candidate'}
    schema = {k:copy.deepcopy(v) for k,v in library_schema.items() if k != 'control_generation'}
    schema['blank_program'] = dict(qualified=True,contract_version=1,mode='blank_program',
        target_sha256=byte_hash(target_bytes),library_sha256=byte_hash(library_bytes),
        library_schema=library_schema,tag_resource='initialize_empty_source_tag_link')
    BlankProgram(original,donor,schema).check()
    identifier = 'blank_program_v1'
    generated = copy.deepcopy(profile)
    address_scope = ('source-qualified driver address regions' if 'address_namespace' in library_schema
                     else 'captured M0/D0')
    numeric_scope = ('UINT fixed-decimal DISPLAY; INPUT zero-decimal only' if 'value_models' in library_schema['numeric']
                     else 'UINT zero-decimal')
    generated.update(id=identifier,native_schema=schema,
        limitation=f'Blank-target/source-library controls only; {address_scope} and {numeric_scope}. Full program, pixels, vendor/runtime/physical qualification pending.')
    witness = dict(contract_version=1,mode='blank_program',target_sha256=byte_hash(target_bytes),
        family=family,model_id=canonical_model_id(original.model_id),serialized_version=original.editor_version,
        resolution=profile['resolution'],schema_sha256=canonical_hash(schema),source_origin='user_vendor_project',
        source_reference=source_reference,review_reference=review_reference,
        library=dict(path=library,sha256=byte_hash(library_bytes),profile_path=library_profile,profile_sha256=byte_hash(profile_bytes)))
    witness_output=output_dir+'/program_calibration.json'
    raw=(json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate']=dict(qualified=True,contract_version=1,mode='blank_program',path=witness_output,sha256=byte_hash(raw))
    # Require explicit provenance before output; the service later binds this
    # witness to the target, library profile and every property dependency.
    for reference in (source_reference,review_reference):
        if not isinstance(reference,str) or not reference.strip() or len(reference)>1000 or any(c in reference for c in '\r\n\0'):
            raise HmiError('NATIVE_CALIBRATION', 'Explicit source/review references are required')
    dependencies=[(target,byte_hash(target_bytes),len(target_bytes)),(library,byte_hash(library_bytes),len(library_bytes)),
        (library_profile,byte_hash(profile_bytes),len(profile_bytes)),(library_spec['path'],library_calibration['sha256'],library_calibration['bytes'])]
    dependencies += [(path.relative_to(service.workspace).as_posix(),digest,size) for path,digest,size in library_calibration['property_files']]
    def fresh(_):
        for relative,digest,size in dependencies:
            try:
                with service._path(relative,exists=True).open('rb') as stream:
                    current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','A blank-program calibration source became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Blank target/library/property source changed during calibration')
        for path,digest,size in library_calibration.get('registry_files', []):
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise HmiError('CALIBRATION_CHANGED','Registered address authority became a link')
            try:
                with path.open('rb') as stream:
                    current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','Registered address authority became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Registered address authority changed during calibration')
    receipts=[service._write_new(witness_output,raw,fresh),
        service._write_new(output_dir+'/profiles/'+identifier+'.json',(json.dumps(generated,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(scope='BLANK_TARGET_SOURCE_LIBRARY_CONTRACTS',target_sha256=byte_hash(target_bytes),
        library_sha256=byte_hash(library_bytes),outputs=receipts,native_output='NOT_CREATED',
        vendor='NOT_RUN',physical='NOT_RUN',program_writer_complete=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','target','library','library-profile','output-dir','source-reference','review-reference'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    print(json.dumps(calibrate(args.workspace,args.target,args.library,args.library_profile,args.output_dir,
                              args.source_reference,args.review_reference),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
