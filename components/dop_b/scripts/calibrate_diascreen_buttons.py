"""Portable source calibration for explicit-address maintained append.

No native output, vendor execution or address allocation occurs here. Review
metadata is not evidence that a human review or machine authorization happened.
"""
import argparse
import json
from pathlib import Path
import re

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups
from universal_hmi.native.diascreen_bound_buttons import DiaScreenBoundButtons, MODE
from universal_hmi.service import FileService, byte_hash, _json_object
from universal_hmi.validation import validate_design


ROOT=Path(__file__).resolve().parents[1]


def capture_contract(adapter, namespace, review_sha256, donor_screen, donor_element, target_screen):
    pages=_groups(adapter.document)
    if not pages:
        raise HmiError('DIA_BOUND_BUTTON','A retained source page graph is required')
    return dict(qualified=True,contract_version=1,mode=MODE,family='delta_diascreen',
        model_id=adapter.model_id,serialized_version=adapter.editor_version,
        source_sha256=byte_hash(adapter.original),namespace=namespace,review_sha256=review_sha256,
        prefix_sha256=byte_hash(b''.join(s.bytes() for s in adapter.document.sections[:pages[0]['start']])),
        tail_sha256=byte_hash(adapter.document.tail),target_screen_id=target_screen,
        pages=[dict(screen_id=p['id'],header_sha256=byte_hash(p['section'].bytes()),
            aux_sha256=byte_hash(adapter.document.sections[p['start']+1].bytes()),
            owners=[o['id'] for o in p['elements']]) for p in pages],
        donor=dict(screen_id=donor_screen,element_id=donor_element,
            owner_sha256=adapter.owner_extent_sha256(donor_screen,donor_element)))


def calibrate(workspace, source_path, output, namespace_path, authority_id,
              donor_screen, donor_element, target_screen, origin, source_reference,
              review_reference, review_artifact, profiles_dir=None):
    paths=FileService(workspace,profiles_dir or ROOT/'profiles')
    def locate(relative):
        try:
            return paths._path(relative,exists=True)
        except OSError as exc:
            raise HmiError('NATIVE_CALIBRATION','Bound calibration input path is missing or unreadable') from exc
    source_file=locate(source_path)
    if source_file.suffix.lower()!='.dpa':
        raise HmiError('OUTPUT_FORMAT','This separate contract requires genuine DPA content/extension')
    kinds={'original_neutral_fixture':'synthetic','user_vendor_project':'user_vendor_project',
           'manufacturer_installed_example':'manufacturer_installed_example'}
    if not isinstance(origin,str) or origin not in kinds:
        raise HmiError('NATIVE_CALIBRATION','Explicit original/user/manufacturer origin is required')
    for reference in (source_reference,review_reference):
        if not isinstance(reference,str) or not reference.strip() or len(reference)>1000 or any(c in reference for c in '\r\n\0'):
            raise HmiError('NATIVE_CALIBRATION','Bounded explicit provenance references are required')
    if not isinstance(authority_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',authority_id):
        raise HmiError('NATIVE_CALIBRATION','Address authority needs a simple portable registry ID')
    authority_file=paths.profiles_dir/'driver_contracts'/(authority_id+'.json')
    if not paths._registry_file_ok(authority_file):
        raise HmiError('NATIVE_CALIBRATION','Address authority may not traverse a registry link')
    authority_raw,_=_json_object(authority_file,'NATIVE_CALIBRATION')
    namespace_raw,namespace=_json_object(locate(namespace_path),'NATIVE_CALIBRATION')
    review_raw,review=_json_object(locate(review_artifact),'NATIVE_CALIBRATION')
    raw=source_file.read_bytes();adapter=NativeAdapter(raw,'delta_diascreen')
    descriptor=capture_contract(adapter,namespace,byte_hash(review_raw),donor_screen,donor_element,target_screen)
    program=DiaScreenBoundButtons(raw,descriptor,authority_raw)
    FileService._check_diascreen_bound_review(review,descriptor)
    schema={'qualified':True,'diascreen_bound_buttons':descriptor}
    identifier='diascreen_bound_buttons_v1'
    profile=dict(id=identifier,family='delta_diascreen',model=adapter.inspect()['panel_name'],
        model_id=int(adapter.model_id),editor_version=adapter.editor_version,resolution=[800,480],
        driver=namespace['driver']['name'],fixture_kind=kinds[origin],
        capabilities={'native_preserved':'OFFLINE_PASS','button':'OFFLINE_PASS'},numeric_types=[],native_schema=schema,
        limitation='Source-bound maintained BOOL stored append only. Exact new M addresses are explicit selections, not fresh memory. Old globals/macros/resources retained. Source font/state appearance is UNKNOWN; preview is conceptual. No clean program/vendor/runtime/native-pixel/panel acceptance.')
    witness=dict(contract_version=1,mode='diascreen_bound_buttons',source_sha256=byte_hash(raw),
        family='delta_diascreen',model_id=int(adapter.model_id),serialized_version=adapter.editor_version,
        resolution=[800,480],schema_sha256=canonical_hash(schema),source_origin=origin,
        source_reference=source_reference,review_reference=review_reference,
        review={'path':review_artifact,'sha256':byte_hash(review_raw)},
        namespace_authority={'id':authority_id,'sha256':byte_hash(authority_raw)})
    encode=lambda data:(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf8')
    witness_raw=encode(witness);witness_path=output+'/CALIBRATION.json'
    schema['native_candidate']=dict(qualified=True,contract_version=1,mode='diascreen_bound_buttons',
        path=witness_path,sha256=byte_hash(witness_raw))
    design=dict(schema_version=1,project_id='bound-maintained-development',profile_id=identifier,
        screens=[],tags=[],macros=[],alarms=[])
    for p in adapter.inspect()['screens']:
        design['screens'].append(dict(id='page_'+p['id'],native_id=p['id'],name=p['name'],
            width=800,height=480,elements=[dict(id='source_'+p['id']+'_'+o['id'],native_id=o['id'],
                kind='native_preserved',text='',source_owner_sha256=adapter.owner_extent_sha256(p['id'],o['id']),
                **o['geometry']) for o in p['elements']]))
    findings=validate_design(design,profile)
    if findings:
        raise HmiError('VALIDATION','Original source inventory is not representable',findings=findings)
    authority_output=output+'/profiles/driver_contracts/'+authority_id+'.json'
    published=False
    def fresh(_):
        try:
            unchanged=(source_file.read_bytes()==raw and paths._registry_file_ok(authority_file)
                and authority_file.read_bytes()==authority_raw
                and locate(namespace_path).read_bytes()==namespace_raw
                and locate(review_artifact).read_bytes()==review_raw)
            if published:
                # Re-resolve every workspace ancestor on every publication;
                # the output registry can differ from the reader registry.
                unchanged=unchanged and paths._path(authority_output,exists=True).read_bytes()==authority_raw
        except OSError as exc:
            raise HmiError('SOURCE_CHANGED','Calibration source or published authority disappeared') from exc
        if not unchanged:
            raise HmiError('SOURCE_CHANGED','Source/namespace/review/authority changed during calibration')
    authority_target=paths._path(authority_output)
    outputs=[]
    if authority_target.exists():
        _,existing=_json_object(authority_target,'NATIVE_CALIBRATION')
        if authority_target.read_bytes()!=authority_raw:
            raise HmiError('NATIVE_CALIBRATION','Existing output authority differs; it cannot be overwritten')
    else:
        outputs.append(paths._write_new(authority_output,authority_raw,fresh))
    published=True
    fresh(None)
    outputs.extend([paths._write_new(witness_path,witness_raw,fresh),
        paths._write_new(output+'/profiles/'+identifier+'.json',encode(profile),fresh),
        paths._write_new(output+'/design.json',encode(design),fresh)])
    return {'outputs':outputs,**program.source_metadata(),'program_writer_complete':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','output','namespace','authority-id','donor-screen','donor-element',
                 'target-screen','origin','source-reference','review-reference','review-artifact'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--profiles')
    a=parser.parse_args()
    print(json.dumps(calibrate(a.workspace,a.source,a.output,a.namespace,a.authority_id,a.donor_screen,
        a.donor_element,a.target_screen,a.origin,a.source_reference,a.review_reference,a.review_artifact,a.profiles),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
