"""Create source-local stored-control contracts from explicit vendor witnesses.

No fixed PC path, IDE automation, native candidate, runtime qualification or
machine design approval is produced. Only this immutable reference's M0/D0
addresses and UINT objects are admitted in the current bounded milestone.
"""
import argparse
import json
from pathlib import Path

from universal_hmi.model import canonical_hash
from universal_hmi.native import NativeAdapter, _groups, canonical_model_id
from universal_hmi.service import FileService, byte_hash, _json_object

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'set_on','set_off','momentary','maintained','numeric_input','numeric_display'}


def calibrate(workspace, source, family, witness_path, output_dir, review_reference):
    service = FileService(workspace, ROOT / 'profiles')
    raw = service._path(source, exists=True).read_bytes()
    adapter = NativeAdapter(raw, family)
    _, witnesses = _json_object(service._path(witness_path, exists=True), 'PROPERTY_WITNESSES')
    if set(witnesses) != KINDS:
        raise ValueError('Six explicit typed property witnesses are required')
    donors, properties = {}, {}
    for kind, witness in witnesses.items():
        if not isinstance(witness, dict) or set(witness) != {'screen_id','element_id','path','sha256'}:
            raise ValueError('Witness must bind owner identity and exact property PNG/JPEG')
        with service._path(witness['path'], exists=True).open('rb') as image_file:
            image = image_file.read(10*1024*1024+1)
        if (len(image) > 10*1024*1024 or not (image.startswith(b'\x89PNG\r\n\x1a\n') or image.startswith(b'\xff\xd8\xff'))
                or byte_hash(image) != witness['sha256']):
            raise ValueError('Property image fingerprint/format differs')
        owner = next(e for s in adapter.inspect()['screens'] if s['id']==witness['screen_id'] for e in s['elements'] if e['id']==witness['element_id'])
        donors[kind] = dict(screen_id=witness['screen_id'], element_id=witness['element_id'],
            owner_sha256=adapter.owner_extent_sha256(witness['screen_id'], witness['element_id']),
            match={'Type':owner['type'],'SubType':owner['subtype']}, property_witness_sha256=witness['sha256'])
        properties[kind] = {'path':witness['path'], 'sha256':witness['sha256']}
    inventory = adapter.inspect()
    input_owner = next(e for s in inventory['screens'] for e in s['elements'] if s['id']==donors['numeric_input']['screen_id'] and e['id']==donors['numeric_input']['element_id'])
    address = input_owner['bindings']['write']['address']
    if not address.endswith('D0'):
        raise ValueError('Current source contract requires the witnessed D0 numeric address')
    prefix = address[:-2]
    raw_prefix, sections = adapter._preserved_prefix(adapter.document)
    pages = _groups(adapter.document)
    width, height = int(inventory['screens'][0]['native_fields']['PanelSizeX']), int(inventory['screens'][0]['native_fields']['PanelSizeY'])
    geometry = {key:dict(field=field,type='int',min=0,max=max(width,height)) for key,field in {'x':'X','y':'Y','width':'Width','height':'Height'}.items()}
    style = {key:dict(field=field,scope='state',type='int',min=1 if key=='font_size' else 0,max=128 if key=='font_size' else 0xFFFFFF)
             for key,field in {'font_size':'FontSize0','color':'FontColor','fill':'BgColor','state_fill':'BgColor'}.items()}
    binding = {direction:dict(field=direction.title()+'Var',link_field=direction.title()+'Link',mem_type_field=direction.title()+'MemType') for direction in ('read','write')}
    connection = dict(channel=prefix.split('}')[0][1:],station=prefix.split('}')[1][:-1],byte_order='device_default',word_order='device_default')
    schema = dict(qualified=True,properties=geometry|style,bindings=binding,
        binding_contracts={kind:dict(data_type=kind,**connection) for kind in ('BOOL','UINT')},
        numeric=dict(qualified=True,kinds={kind:donors[kind]['match'] for kind in ('numeric_input','numeric_display')},
            types={'UINT':dict(MemLen=input_owner['native_fields']['MemLen'],MemFmt=input_owner['native_fields']['MemFmt'],bits=16,format='unsigned')},
            max_integer_digits=5,max_fractional_digits=0),
        control_generation=dict(qualified=True,contract_version=1,mode='control_generation',source_sha256=byte_hash(raw),
            prefix_sha256=byte_hash(raw_prefix),sections=sections,address_prefix=prefix,donors=donors,
            pages=[dict(screen_id=page['id'],header_sha256=byte_hash(page['section'].bytes()),aux_sha256=byte_hash(adapter._plain_extent(page).bytes())) for page in pages]))
    adapter.verify_control_generation(schema)
    identifier = 'source_controls_v1'
    profile = dict(id=identifier,family=family,model=inventory['panel_name'],model_id=canonical_model_id(adapter.model_id),
        editor_version=adapter.editor_version,resolution=[width,height],driver='SOURCE_PINNED_UNVERIFIED_RUNTIME',fixture_kind='user_vendor_project',
        capabilities={kind:'OFFLINE_PASS' for kind in ('button','numeric_input','numeric_display','native_preserved')},numeric_types=['UINT'],native_schema=schema,
        limitation='Append-only stored-configuration candidate; M0/D0 only. No complete program, vendor/simulation/physical/pixel acceptance.')
    witness = dict(contract_version=1,mode='control_generation',source_sha256=byte_hash(raw),family=family,model_id=profile['model_id'],
        serialized_version=adapter.editor_version,resolution=profile['resolution'],schema_sha256=canonical_hash(schema),source_origin='user_vendor_project',
        source_reference=source,review_reference=review_reference,properties=properties)
    witness_output = output_dir + '/control_calibration.json'
    witness_bytes = (json.dumps(witness,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    schema['native_candidate'] = dict(qualified=True,contract_version=1,mode='control_generation',path=witness_output,sha256=byte_hash(witness_bytes))
    def fresh(_):
        if service._path(source,exists=True).read_bytes()!=raw:
            raise ValueError('Source changed during calibration')
    receipts = [service._write_new(witness_output,witness_bytes,fresh),
                service._write_new(output_dir+'/profiles/'+identifier+'.json',(json.dumps(profile,ensure_ascii=False,indent=2)+'\n').encode('utf-8'),fresh)]
    return dict(source_sha256=byte_hash(raw),scope='APPEND_SOURCE_CALIBRATED_CONTROLS',outputs=receipts,vendor='NOT_RUN',physical='NOT_RUN',program_writer_complete=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('workspace','source','family','witnesses','output-dir','review-reference'):
        parser.add_argument('--'+key,required=True)
    args = parser.parse_args()
    result = calibrate(args.workspace,args.source,args.family,args.witnesses,args.output_dir,args.review_reference)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
