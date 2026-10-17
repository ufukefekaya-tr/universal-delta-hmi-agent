"""Extend a source-qualified library with stored UINT decimal presentation.

Only new profile/calibration JSON is produced. Integer input F>0 remains
unqualified; no compiler, keypad, vendor UI, DLL or PLC is executed.
"""
import argparse
import copy
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter
from universal_hmi.native.numeric import fixed_decimal_contract
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.service import FileService, byte_hash, _json_object
from universal_hmi.value_model import FIXED_MODEL

ROOT=Path(__file__).resolve().parents[1]


def calibrate(workspace,source,library_profile,output_dir,review_reference):
    service=FileService(workspace,ROOT/'profiles')
    source_path=service._path(source,exists=True)
    try:
        with source_path.open('rb') as stream:source_bytes=stream.read(MAX_PAYLOAD+1)
    except OSError as exc:
        raise HmiError('NATIVE_CALIBRATION','Control library source became unavailable') from exc
    if len(source_bytes)>MAX_PAYLOAD:
        raise HmiError('NATIVE_CALIBRATION','Control library source is oversized')
    profile_path=service._path(library_profile,exists=True)
    profile_bytes,profile=_json_object(profile_path,'NATIVE_CALIBRATION')
    service._validate_profile(profile)
    schema=copy.deepcopy(profile['native_schema']);numeric=schema.get('numeric')
    spec=schema.get('native_candidate')
    if (not isinstance(numeric,dict) or 'value_models' in numeric or not isinstance(spec,dict)
            or spec.get('mode')!='control_generation'):
        raise HmiError('NATIVE_CALIBRATION','An unextended property-qualified numeric library is required')
    native=NativeAdapter(source_bytes,profile['family'])
    baseline=service._load_control_calibration(dict(source_bytes=source_bytes,source_sha256=byte_hash(source_bytes),
        profile=profile,inventory=native.inspect()),spec)
    authority_path=service._numeric_authority_dir()/'dopsoft2_b10_uint_presentation.json'
    authority_bytes,book=_json_object(authority_path,'NUMERIC_AUTHORITY')
    service._validate_numeric_book(book)
    descriptor=dict(qualified=True,contract_version=1,mode=FIXED_MODEL,types=['UINT'],max_fractional_digits=4,
        max_total_digits=5,storage_domain='raw_integer',limit_domain='display',input_lowering='UNVERIFIED',
        source_sha256=byte_hash(source_bytes),authority_sha256=byte_hash(authority_bytes),review_reference=review_reference)
    numeric['value_models']={FIXED_MODEL:descriptor};numeric['max_fractional_digits']=4
    fixed_decimal_contract(schema)
    registered=service._numeric_authority(schema,profile,byte_hash(source_bytes))
    schema.pop('native_candidate');native.verify_control_generation(schema)
    generated=copy.deepcopy(profile);identifier='source_controls_fixed_decimal_v1'
    generated.update(id=identifier,native_schema=schema,
        limitation='Source-qualified UINT fixed-decimal DISPLAY stored configuration, F0..4/I+F<=5. INPUT F>0/compiler/keypad/pixels/vendor/runtime/physical remain unqualified.')
    generated['capabilities'].update({'numeric_value_model:'+FIXED_MODEL:'OFFLINE_PASS',
        'numeric_fixed_decimal_display':'OFFLINE_PASS','numeric_fixed_decimal_input':'UNVERIFIED'})
    witness=copy.deepcopy(baseline['witness']);witness['schema_sha256']=canonical_hash(schema);witness['review_reference']=review_reference
    witness_output=output_dir+'/control_calibration.json'
    raw=(json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate']=dict(qualified=True,contract_version=1,mode='control_generation',path=witness_output,sha256=byte_hash(raw))
    dependencies=[(source_path,byte_hash(source_bytes),len(source_bytes)),(profile_path,byte_hash(profile_bytes),len(profile_bytes)),
        (service._path(spec['path'],exists=True),baseline['sha256'],baseline['bytes']),registered,
        *baseline['property_files'],*baseline.get('registry_files',[])]
    def fresh(_):
        for path,digest,size in dependencies:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise HmiError('CALIBRATION_CHANGED','A numeric calibration source became a link')
            try:
                with path.open('rb') as stream:current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','A numeric calibration source became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Numeric source/profile/property or registered authority changed during calibration')
    outputs=[service._write_new(witness_output,raw,fresh),
        service._write_new(output_dir+'/profiles/'+identifier+'.json',(json.dumps(generated,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(scope='SOURCE_QUALIFIED_UINT_FIXED_DECIMAL_DISPLAY',source_sha256=byte_hash(source_bytes),outputs=outputs,
        native_output='NOT_CREATED',input_fractional_lowering='UNVERIFIED',native_pixels='NOT_RUN',vendor='NOT_RUN',
        physical='NOT_RUN',program_writer_complete=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','library-profile','output-dir','review-reference'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();print(json.dumps(calibrate(args.workspace,args.source,args.library_profile,args.output_dir,args.review_reference),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
