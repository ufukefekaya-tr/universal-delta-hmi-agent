"""Bind a blank target, original controls and separate reviewed auxiliary source.

This creates only portable JSON contracts. Native machine output still needs
an approved design; no vendor executable, UI, PLC or panel action is included.
"""
import argparse
import copy
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, canonical_model_id
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.native.multipage import MultiPageProgram
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT = Path(__file__).resolve().parents[1]


def calibrate(workspace, target, controls, controls_profile, layout, properties,
              output_dir, source_reference, review_reference):
    service = FileService(workspace, ROOT / 'profiles')
    dependencies = []

    def read_native(relative):
        with service._path(relative, exists=True).open('rb') as stream:
            data = stream.read(MAX_PAYLOAD + 1)
        if len(data) > MAX_PAYLOAD:
            raise HmiError('NATIVE_CALIBRATION', 'Native reference exceeds its bound')
        dependencies.append((relative, byte_hash(data), len(data)))
        return data

    for reference in (source_reference, review_reference):
        if not isinstance(reference,str) or not reference.strip() or len(reference)>1000 or any(c in reference for c in '\r\n\0'):
            raise HmiError('NATIVE_CALIBRATION', 'Explicit source and review references are required')
    target_bytes, controls_bytes, layout_bytes = read_native(target), read_native(controls), read_native(layout)
    profile_bytes, profile = _json_object(service._path(controls_profile, exists=True), 'NATIVE_CALIBRATION')
    service._validate_profile(profile)
    dependencies.append((controls_profile,byte_hash(profile_bytes),len(profile_bytes)))
    family = profile['family']
    target_native, controls_native, layout_native = [NativeAdapter(data,family) for data in (target_bytes,controls_bytes,layout_bytes)]
    spec = profile['native_schema'].get('native_candidate')
    if not isinstance(spec,dict) or spec.get('mode')!='control_generation':
        raise HmiError('NATIVE_CALIBRATION', 'Original controls need a source-qualified six-donor profile')
    calibration = service._load_control_calibration(dict(source_bytes=controls_bytes,source_sha256=byte_hash(controls_bytes),
        profile=profile,inventory=controls_native.inspect()),spec)
    dependencies.append((spec['path'],calibration['sha256'],calibration['bytes']))
    dependencies.extend((p.relative_to(service.workspace).as_posix(),digest,size) for p,digest,size in calibration['property_files'])
    directory = service._layout_authority_dir()
    if not directory.is_dir() or directory.is_symlink() or getattr(directory,'is_junction',lambda:False)():
        raise HmiError('LAYOUT_AUTHORITY', 'Reviewed layout registry is required')
    paths = sorted(directory.glob('*.json'))
    if not 1<=len(paths)<=128:
        raise HmiError('LAYOUT_AUTHORITY', 'Layout registry is empty or oversized')
    matches = []
    for path in paths:
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)() or not path.resolve().is_relative_to(directory.resolve()):
            raise HmiError('LAYOUT_AUTHORITY', 'Registry sources must not traverse links')
        raw, book = _json_object(path,'LAYOUT_AUTHORITY')
        if book.get('layout_sha256') == byte_hash(layout_bytes):
            matches.append((path,raw,book))
    if len(matches)!=1:
        raise HmiError('LAYOUT_AUTHORITY', 'Layout source needs one exact registered reviewed contract')
    authority_path, authority_bytes, book = matches[0]
    controls_schema = {k:copy.deepcopy(v) for k,v in profile['native_schema'].items() if k!='native_candidate'}
    schema = {k:copy.deepcopy(v) for k,v in controls_schema.items() if k!='control_generation'}
    descriptor = dict(qualified=True,contract_version=1,mode='multipage_program',target_sha256=byte_hash(target_bytes),
        controls_sha256=byte_hash(controls_bytes),controls_schema=controls_schema,layout_sha256=byte_hash(layout_bytes),
        page_donor=copy.deepcopy(book.get('page_donor')),aux_donors=copy.deepcopy(book.get('aux_donors')),authority_sha256=byte_hash(authority_bytes))
    schema['multipage_program'] = descriptor
    registry_files = [*calibration.get('registry_files',[]),service._layout_authority(descriptor,profile)]
    MultiPageProgram(target_native,controls_native,layout_native,schema).check()
    if not isinstance(properties,dict) or set(properties)!=set(descriptor['aux_donors']):
        raise HmiError('NATIVE_CALIBRATION', 'Three exact auxiliary property references are required')
    property_refs = {}
    for kind, relative in properties.items():
        raw, observed = _json_object(service._path(relative,exists=True),'NATIVE_CALIBRATION')
        digest = byte_hash(raw)
        if (digest != descriptor['aux_donors'][kind]['property_witness_sha256']
                or observed.get('scope')!='VENDOR_CREATED_REFERENCE_PROPERTY_ONLY'
                or observed.get('type')!={'text':'Literal Text','indicator':'Multistate Indicator','goto':'Goto Screen'}[kind]):
            raise HmiError('NATIVE_CALIBRATION', 'Auxiliary property reference differs from the reviewed source pin')
        property_refs[kind] = dict(path=relative,sha256=digest)
        dependencies.append((relative,digest,len(raw)))
    identifier = 'multipage_program_v1'
    generated = copy.deepcopy(profile)
    generated.update(id=identifier,native_schema=schema,
        limitation='Source-qualified mixed ordinary pages with six typed controls, literal text, BOOL read-only indicators and goto. ASCII page names, conservative colors; macros/alarms/native pixels/vendor/runtime/physical acceptance remain open.')
    generated['capabilities'].update({kind:'OFFLINE_PASS' for kind in ('text','indicator','goto','pages')})
    witness = dict(contract_version=1,mode='multipage_program',target_sha256=byte_hash(target_bytes),family=family,
        model_id=canonical_model_id(target_native.model_id),serialized_version=target_native.editor_version,
        resolution=profile['resolution'],schema_sha256=canonical_hash(schema),source_origin='user_vendor_project',
        source_reference=source_reference,review_reference=review_reference,
        controls=dict(path=controls,sha256=byte_hash(controls_bytes),profile_path=controls_profile,profile_sha256=byte_hash(profile_bytes)),
        layout=dict(path=layout,sha256=byte_hash(layout_bytes),properties=property_refs))
    witness_path = output_dir+'/multipage_calibration.json'
    raw = (json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate'] = dict(qualified=True,contract_version=1,mode='multipage_program',path=witness_path,sha256=byte_hash(raw))

    def fresh(_):
        for relative,digest,size in dependencies:
            try:
                with service._path(relative,exists=True).open('rb') as stream:
                    current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','A multipage calibration source became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','A multipage calibration source changed during output')
        for path,digest,size in registry_files:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise HmiError('CALIBRATION_CHANGED','Registered authority became a link')
            try:
                with path.open('rb') as stream:
                    current=stream.read(size+1)
            except OSError as exc:
                raise HmiError('CALIBRATION_CHANGED','Registered authority became unavailable') from exc
            if len(current)!=size or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Registered authority changed during calibration')
    receipts = [service._write_new(witness_path,raw,fresh),service._write_new(output_dir+'/profiles/'+identifier+'.json',
                 (json.dumps(generated,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(scope='THREE_SOURCE_MULTIPAGE_CONTRACTS',target_sha256=byte_hash(target_bytes),
                controls_sha256=byte_hash(controls_bytes),layout_sha256=byte_hash(layout_bytes),outputs=receipts,
                native_output='NOT_CREATED',vendor='NOT_RUN',native_pixels='NOT_RUN',physical='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','target','controls','controls-profile','layout','indicator-property','text-property','goto-property',
                 'output-dir','source-reference','review-reference'):
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    print(json.dumps(calibrate(args.workspace,args.target,args.controls,args.controls_profile,args.layout,
        dict(indicator=args.indicator_property,text=args.text_property,goto=args.goto_property),
        args.output_dir,args.source_reference,args.review_reference),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
