"""Produce new JSON contracts for an explicit source-pinned static INT16/F0 clone.

Original source/properties remain UINT. No signed property witness, vendor
compiler, DLL, GUI, PLC or panel is invoked or claimed.
"""
import argparse
import copy
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.native.storage_conversion import storage_contract, validate_source
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT=Path(__file__).resolve().parents[1]


def calibrate(workspace,source,library_profile,output_dir,review_reference):
    service=FileService(workspace,ROOT/'profiles')
    source_path=service._path(source,exists=True)
    try:
        with source_path.open('rb') as stream:source_bytes=stream.read(MAX_PAYLOAD+1)
    except OSError as exc:
        raise HmiError('NATIVE_CALIBRATION','Original UINT control source became unavailable') from exc
    if len(source_bytes)>MAX_PAYLOAD:
        raise HmiError('NATIVE_CALIBRATION','Control library source is oversized')
    profile_path=service._path(library_profile,exists=True)
    profile_bytes,profile=_json_object(profile_path,'NATIVE_CALIBRATION');service._validate_profile(profile)
    schema=copy.deepcopy(profile['native_schema']);spec=schema.get('native_candidate')
    if 'storage_conversion' in schema or not isinstance(spec,dict) or spec.get('mode')!='control_generation':
        raise HmiError('NATIVE_CALIBRATION','An original source-qualified UINT library is required; no repeat conversion or downgrade')
    native=NativeAdapter(source_bytes,profile['family'])
    baseline=service._load_control_calibration(dict(source_bytes=source_bytes,source_sha256=byte_hash(source_bytes),
        profile=profile,inventory=native.inspect()),spec)
    authority_path=service._numeric_authority_dir()/'dopsoft2_b10_int16_conversion.json'
    authority_bytes,book=_json_object(authority_path,'STORAGE_AUTHORITY');service._validate_storage_book(book)
    donors=schema['control_generation']['donors']
    schema['storage_conversion']=dict(qualified=True,contract_version=1,mode='source_uint16_to_int16_f0',
        source_sha256=byte_hash(source_bytes),authority_sha256=byte_hash(authority_bytes),
        input_donor_sha256=donors['numeric_input']['owner_sha256'],display_donor_sha256=donors['numeric_display']['owner_sha256'],
        review_reference=review_reference)
    schema['numeric']['types']['INT']={'MemLen':'1','MemFmt':'1','bits':16,'format':'signed'}
    schema['binding_contracts']['INT']=dict(copy.deepcopy(schema['binding_contracts']['UINT']),data_type='INT')
    generated=copy.deepcopy(profile);identifier='source_controls_int16_static_v1'
    generated.update(id=identifier,native_schema=schema,
        numeric_types=list(dict.fromkeys([*profile['numeric_types'],'INT'])),
        limitation='Explicit STATIC_SOURCE_QUALIFIED fresh UINT16-to-INT16/F0 clone transformation; existing donor/property proof stays UINT. Signed donor, fractional input/scaling, pixels, vendor/runtime/physical acceptance remain open.')
    generated['capabilities'].update(numeric_int16_static_transform='OFFLINE_PASS',numeric_signed_donor_property='UNVERIFIED')
    storage_contract(schema);validate_source(native,schema)
    registered=service._storage_authority(schema,generated,byte_hash(source_bytes))
    schema.pop('native_candidate');native.verify_control_generation(schema)
    witness=copy.deepcopy(baseline['witness']);witness['schema_sha256']=canonical_hash(schema);witness['review_reference']=review_reference
    witness_output=output_dir+'/control_calibration.json';raw=(json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate']=dict(qualified=True,contract_version=1,mode='control_generation',path=witness_output,sha256=byte_hash(raw))
    dependencies=[(source_path,byte_hash(source_bytes),len(source_bytes)),(profile_path,byte_hash(profile_bytes),len(profile_bytes)),
        (service._path(spec['path'],exists=True),baseline['sha256'],baseline['bytes']),registered,*baseline['property_files'],*baseline.get('registry_files',[])]
    def fresh(_):
        for path,digest,size in dependencies:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise HmiError('CALIBRATION_CHANGED','A storage calibration dependency became a link')
            try:
                with path.open('rb') as stream:current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','A storage calibration dependency became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Original source/profile/properties or registered storage authority changed')
    outputs=[service._write_new(witness_output,raw,fresh),service._write_new(output_dir+'/profiles/'+identifier+'.json',
        (json.dumps(generated,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(scope='STATIC_SOURCE_QUALIFIED_INT16_F0_CLONES',source_sha256=byte_hash(source_bytes),outputs=outputs,
        native_output='NOT_CREATED',signed_donor_property='NOT_FOUND',fractional_input_lowering='UNVERIFIED',
        native_pixels='NOT_RUN',vendor='NOT_RUN',physical='NOT_RUN',program_writer_complete=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('workspace','source','library-profile','output-dir','review-reference'):parser.add_argument('--'+key,required=True)
    args=parser.parse_args();print(json.dumps(calibrate(args.workspace,args.source,args.library_profile,args.output_dir,args.review_reference),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
