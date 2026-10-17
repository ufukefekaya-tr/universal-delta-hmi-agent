"""Add reviewed decimal DVP driver regions to an existing control library.

Only source-local JSON contracts are produced. The immutable source driver,
native binding metadata and datatype storage remain unchanged. Runtime needs
the portable factual registry, never a vendor DLL, installation or UI.
"""
import argparse
import copy
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter
from universal_hmi.native.address_contract import AddressNamespace, source_driver_fingerprint
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT = Path(__file__).resolve().parents[1]


def calibrate(workspace, source, library_profile, output_dir, review_reference, authority_name='delta_dvp_serial_2016.json'):
    service = FileService(workspace, ROOT / 'profiles')
    source_path = service._path(source, exists=True)
    with source_path.open('rb') as stream:
        source_bytes = stream.read(MAX_PAYLOAD + 1)
    if len(source_bytes) > MAX_PAYLOAD:
        raise HmiError('NATIVE_CALIBRATION', 'Control library source is oversized')
    profile_bytes, profile = _json_object(service._path(library_profile, exists=True), 'NATIVE_CALIBRATION')
    service._validate_profile(profile)
    schema = copy.deepcopy(profile['native_schema'])
    spec = schema.get('native_candidate')
    if not isinstance(spec, dict) or spec.get('mode') != 'control_generation':
        raise HmiError('NATIVE_CALIBRATION', 'An unextended property-qualified control library is required')
    native = NativeAdapter(source_bytes, profile['family'])
    baseline = service._load_control_calibration(dict(source_bytes=source_bytes,source_sha256=byte_hash(source_bytes),
        profile=profile,inventory=native.inspect()),spec)
    if not isinstance(authority_name,str) or authority_name not in {'delta_dvp_serial_2016.json','delta_dvp_serial_radix_2016.json'}:
        raise HmiError('ADDRESS_AUTHORITY', 'Choose an exact reviewed DVP authority name')
    authority_path = service._driver_authority_dir() / authority_name
    authority_bytes, authority = _json_object(authority_path, 'ADDRESS_AUTHORITY')
    service._validate_address_book(authority)
    if ('address_namespace' in schema and not (authority['schema_version']==2
            and schema['address_namespace'].get('contract_version')==1
            and schema['address_namespace'].get('mode')=='source_driver_decimal_regions')):
        raise HmiError('NATIVE_CALIBRATION', 'Only an explicit reviewed v1 to v2 namespace upgrade is admitted')
    prefix = schema['control_generation']['address_prefix']
    drivers = []
    for driver in native.calibration_inventory()['driver_blocks']:
        index = driver['native_index']
        observed = {r['key']:r.get('observed_scalar') for r in driver['records']}
        if (observed.get('ControllerSection'+index) == authority['driver']['company']
                and observed.get('ControllerName'+index) == authority['driver']['name']
                and observed.get('CommName'+index) == prefix.split('}')[0][1:]
                and observed.get('DefPLCStationNr'+index) == prefix.split('}')[1][:-1]):
            drivers.append(dict(native_index=index, **authority['driver'], raw_span_sha256=source_driver_fingerprint(native,index)))
    if len(drivers) != 1:
        raise HmiError('ADDRESS_AUTHORITY', 'One unambiguous source driver must match the reviewed namespace')
    version=authority['schema_version']
    namespace = dict(qualified=True,contract_version=version,mode='source_driver_decimal_regions' if version==1 else 'source_driver_radix_regions',source_sha256=byte_hash(source_bytes),
        prefix=prefix,driver=drivers[0],regions=copy.deepcopy(authority['regions']),authority_sha256=byte_hash(authority_bytes),
        review_reference=review_reference)
    registered = service._address_authority(namespace,profile)
    AddressNamespace(namespace).validate_source(native,prefix)
    schema['address_namespace'] = namespace
    schema.pop('native_candidate')
    native.verify_control_generation(schema)
    generated = copy.deepcopy(profile)
    identifier = 'source_controls_dvp_v1' if version==1 else 'source_controls_dvp_v2'
    generated.update(id=identifier,native_schema=schema,
        limitation=('Source-qualified driver BOOL M/S and UINT D namespace; source driver/binding/storage unchanged. Actual PLC availability and vendor/runtime/physical acceptance pending.' if version==1 else
                    'Source-qualified radix8 X/Y and decimal M/S/D; normal-operation XRead/YReadWrite policy, exact source driver/binding/storage retained. Native pixels, CPU/feedback and vendor/runtime/physical acceptance pending.'))
    generated['capabilities']['driver_address_namespace'] = 'OFFLINE_PASS'
    witness = copy.deepcopy(baseline['witness'])
    witness['schema_sha256'] = canonical_hash(schema)
    witness['review_reference'] = review_reference
    witness_output = output_dir+'/control_calibration.json'
    witness_bytes = (json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate'] = dict(qualified=True,contract_version=1,mode='control_generation',path=witness_output,sha256=byte_hash(witness_bytes))
    dependencies = [(source_path,byte_hash(source_bytes),len(source_bytes)),
        (service._path(library_profile,exists=True),byte_hash(profile_bytes),len(profile_bytes)),
        (service._path(spec['path'],exists=True),baseline['sha256'],baseline['bytes']),registered,*baseline['property_files'],*baseline.get('registry_files',[])]
    def fresh(_):
        for path,digest,size in dependencies:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise HmiError('CALIBRATION_CHANGED','A calibration source became a link')
            try:
                with path.open('rb') as stream:
                    raw = stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','A calibration source became unavailable') from exc
            if len(raw)!=size or byte_hash(raw)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Control source/profile/property or address authority changed during calibration')
    outputs = [service._write_new(witness_output,witness_bytes,fresh),
        service._write_new(output_dir+'/profiles/'+identifier+'.json',(json.dumps(generated,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(scope='SOURCE_DRIVER_DECIMAL_REGIONS' if version==1 else 'SOURCE_DRIVER_RADIX_REGIONS',source_sha256=byte_hash(source_bytes),outputs=outputs,
        native_output='NOT_CREATED',vendor='NOT_RUN',physical='NOT_RUN',program_writer_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','library-profile','output-dir','review-reference'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--authority',default='delta_dvp_serial_2016.json',choices=('delta_dvp_serial_2016.json','delta_dvp_serial_radix_2016.json'))
    args = parser.parse_args()
    print(json.dumps(calibrate(args.workspace,args.source,args.library_profile,args.output_dir,args.review_reference,args.authority),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
