"""Create an original-source existing appearance/background contract, no native output.

Relative project paths only; reviewed static B10 facts do not qualify runtime,
vendor compilation, actual native pixels or physical panel operation.
"""
import argparse
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups, canonical_model_id
from universal_hmi.native.codec import MAX_PAYLOAD
from universal_hmi.native.existing_edit import ExistingEdit
from universal_hmi.native.existing_background_page import ExistingBackgroundPage
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT = Path(__file__).resolve().parents[1]


def qualify(workspace, source, output_dir, source_reference, review_reference, integer_numeric=False,
            entry_permission=False, permission_namespace=None, action_contract=None):
    if type(integer_numeric) is not bool or type(entry_permission) is not bool:
        raise HmiError('NATIVE_CALIBRATION','Numeric and entry qualification require explicit Boolean options')
    if (entry_permission and (not isinstance(permission_namespace,str) or not isinstance(action_contract,str))) or (
            not entry_permission and (permission_namespace is not None or action_contract is not None)):
        raise HmiError('NATIVE_CALIBRATION','Entry permission requires two explicit project artifact paths')
    service = FileService(workspace, ROOT/'profiles')
    for value in (source_reference, review_reference):
        if not isinstance(value,str) or not value.strip() or len(value)>1000 or any(c in value for c in '\r\n\0'):
            raise HmiError('NATIVE_CALIBRATION','Explicit bounded source and review references are required')
    with service._path(source,exists=True).open('rb') as stream:
        data=stream.read(MAX_PAYLOAD+1)
    if len(data)>MAX_PAYLOAD:
        raise HmiError('NATIVE_CALIBRATION','Native source exceeds bounded size')
    original=NativeAdapter(data,'delta_dopsoft2')
    schema={'qualified':True}
    registries=[];permission_options={};dependencies=[]
    if entry_permission:
        namespace_raw,_=_json_object(service._path(permission_namespace,exists=True),'EXISTING_ENTRY_INPUTS')
        action_raw,_=_json_object(service._path(action_contract,exists=True),'EXISTING_ENTRY_INPUTS')
        dependencies=[(permission_namespace,byte_hash(namespace_raw),len(namespace_raw)),
                      (action_contract,byte_hash(action_raw),len(action_raw))]
        schema['entry_permission_inputs']={
            'address_namespace':dict(path=permission_namespace,sha256=byte_hash(namespace_raw)),
            'action_contract':dict(path=action_contract,sha256=byte_hash(action_raw))}
    contracts = [
            ('existing_program',None,'dopsoft2_b10_inert_literals.json','source_inert_literal_deletion'),
            ('existing_presentation','presentation','dopsoft2_b10_presentation.json','variable_scalar_records_v1'),
            ('existing_background','background','dopsoft2_b10_background.json','fixed_opaque_page_background_v1')]
    if integer_numeric:
        contracts.append(('existing_integer_numeric','integer_numeric','dopsoft2_b10_integer_numeric.json','existing_word_integer_numeric_v1'))
    if entry_permission:
        contracts.append(('existing_entry_permission','entry_permission','dopsoft2_b10_entry_permission.json','existing_entry_permission_v1'))
    for key,role,filename,mode in contracts:
        path=service._existing_authority_dir()/filename
        raw,book=_json_object(path,'EXISTING_EDIT_AUTHORITY')
        if role is None:service._validate_existing_book(book)
        elif canonical_hash(book)!=canonical_hash(service._edit_book_facts(role)):
            raise HmiError('EXISTING_EDIT_AUTHORITY','Registered typed facts drifted')
        schema[key]=dict(qualified=True,contract_version=1,mode=mode,source_sha256=byte_hash(data),
            family=original.family,model_id=canonical_model_id(original.model_id),editor_version=original.editor_version,
            authority_sha256=byte_hash(raw))
        registries.append((path,byte_hash(raw),len(raw)))
    if entry_permission:
        schema['existing_entry_permission'].update(address_namespace_sha256=byte_hash(namespace_raw),
                                                   action_contract_sha256=byte_hash(action_raw))
        permission_options=dict(entry_permission_descriptor=schema['existing_entry_permission'],
                                address_namespace_raw=namespace_raw,action_contract_raw=action_raw)
    program=ExistingEdit(original,schema,schema['existing_presentation'],schema['existing_background'],
                         schema.get('existing_integer_numeric'),**permission_options)
    program.check()
    pages=_groups(original.document)
    dimensions=[[int(p['section'].one('PanelSizeX').value),int(p['section'].one('PanelSizeY').value)] for p in pages]
    if not dimensions or any(d!=dimensions[0] for d in dimensions):
        raise HmiError('NATIVE_CALIBRATION','All source pages require one exact profile canvas')
    identifier=('existing_edit_permission_v1' if entry_permission else
                'existing_edit_numeric_v1' if integer_numeric else 'existing_edit_v1')
    capabilities={k:'OFFLINE_PASS' for k in ('native_preserved','native_presentation','native_background')}
    if integer_numeric: capabilities['native_integer_numeric']='OFFLINE_PASS'
    if entry_permission: capabilities['native_entry_permission']='OFFLINE_PASS'
    profile=dict(id=identifier,family=original.family,model_id=schema['existing_program']['model_id'],
        editor_version=original.editor_version,resolution=dimensions[0],
        capabilities=capabilities, native_schema=schema,
        limitation=('Original-source existing WORD integer numeric display/F0-input settings plus appearance/background; storage, scale, bindings, units and actions retained. Fractional input refused. Native fonts/composite/vendor/runtime/panel NOT_RUN.'
            if integer_numeric else 'Original-source stored appearance/background edits only. Captions, addresses, numeric configuration and actions retained. Native fonts/composite/vendor/runtime/panel NOT_RUN.'))
    if entry_permission:
        profile['limitation']='Original-source explicitly project-classified stored entry permission only; action entry/keypad opening, not maximum-age/quality/continuous/commit-time/atomic/runtime/safety acceptance. Original bindings/storage remain. Fractional input refused.'
        _,_,_,_,permission_registries=service._edit_permission_inputs(
            dict(profile=profile,source_bytes=data,source_sha256=byte_hash(data)))
        registries.extend(permission_registries)
    service._existing_authority(schema,profile,byte_hash(data))
    for key,role,_,_ in contracts[1:]:
        service._edit_authority(schema[key],profile,byte_hash(data),role)
    witness=dict(contract_version=1,mode='existing_edit',source_sha256=byte_hash(data),family=original.family,
        model_id=profile['model_id'],serialized_version=original.editor_version,resolution=dimensions[0],
        schema_sha256=canonical_hash(schema),source_origin='user_vendor_project',source_reference=source_reference,
        review_reference=review_reference)
    witness_path=output_dir+'/edit_calibration.json'
    witness_raw=(json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate']=dict(qualified=True,contract_version=1,mode='existing_edit',path=witness_path,sha256=byte_hash(witness_raw))
    backgrounds=ExistingBackgroundPage(original,schema,schema['existing_background']).frame_inventory()
    intent=dict(schema_version=1,project_id='existing_edit',profile_id=identifier,screens=[],tags=[],macros=[],alarms=[])
    observed=[]
    page_names={p['id']:p['name'] for p in original.inspect()['screens']}
    for page in pages:
        screen=dict(id='screen_'+page['id'],native_id=page['id'],name=page_names[page['id']],
            width=dimensions[0][0],height=dimensions[0][1],elements=[])
        for owner in page['elements']:
            section=owner['section']
            geometry={k:int(section.one(v).value) for k,v in [('x','X'),('y','Y'),('width','Width'),('height','Height')]}
            pin=original.owner_extent_sha256(page['id'],owner['id'])
            screen['elements'].append(dict(id='owner_'+owner['id'],native_id=owner['id'],kind='native_preserved',text='',source_owner_sha256=pin,**geometry))
            observed.append(dict(screen_id=page['id'],element_id=owner['id'],owner_sha256=pin,
                native_type=section.one('Type').value.decode('ascii'),native_subtype=section.one('SubType').value.decode('ascii'),
                states=[dict(value=s.one('Value').value.decode('ascii'),state_sha256=byte_hash(s.bytes())) for s in owner['states']]))
        intent['screens'].append(screen)
    def fresh(_):
        try:
            with service._path(source,exists=True).open('rb') as stream:current=stream.read(len(data)+1)
        except (OSError,HmiError) as exc:raise HmiError('CALIBRATION_CHANGED','Source became unavailable') from exc
        if current!=data:raise HmiError('CALIBRATION_CHANGED','Source changed during qualification')
        for relative,digest,length in dependencies:
            try:
                with service._path(relative,exists=True).open('rb') as stream:current=stream.read(length+1)
            except (OSError,HmiError) as exc:raise HmiError('CALIBRATION_CHANGED','Entry contract became unavailable') from exc
            if len(current)!=length or byte_hash(current)!=digest:
                raise HmiError('CALIBRATION_CHANGED','Entry namespace or action classification changed')
        for path,digest,length in registries:
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise HmiError('CALIBRATION_CHANGED','Authority became a link')
            try:
                with path.open('rb') as stream:raw=stream.read(length+1)
            except OSError as exc:raise HmiError('CALIBRATION_CHANGED','Authority became unavailable') from exc
            if len(raw)!=length or byte_hash(raw)!=digest:raise HmiError('CALIBRATION_CHANGED','Authority changed during qualification')
    outputs=[]
    for relative,obj in [(witness_path,witness), (output_dir+'/profiles/'+identifier+'.json',profile),
            (output_dir+'/source_inventory.json',dict(owners=observed,backgrounds=backgrounds)),
            (output_dir+'/design.json',intent)]:
        raw=(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        outputs.append(service._write_new(relative,raw,fresh))
    return dict(scope='SOURCE_PINNED_EXISTING_EDIT_CALIBRATION',source_sha256=byte_hash(data),outputs=outputs,
        native_output='NOT_CREATED',native_pixels='NOT_RUN',vendor='NOT_RUN',runtime='NOT_RUN',physical='NOT_RUN')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','source','output-dir','source-reference','review-reference'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--integer-numeric',action='store_true',
                        help='Qualify separate existing WORD numeric display/F0-input settings; no storage conversion')
    parser.add_argument('--entry-permission',action='store_true',help='Qualify separately classified stored action-entry permission; no runtime guarantee')
    parser.add_argument('--permission-namespace',help='Workspace-relative source-qualified registered external address namespace JSON')
    parser.add_argument('--action-contract',help='Workspace-relative explicit human project action-classification JSON')
    args=parser.parse_args()
    print(json.dumps(qualify(args.workspace,args.source,args.output_dir,args.source_reference,args.review_reference,
        args.integer_numeric,args.entry_permission,args.permission_namespace,args.action_contract),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
