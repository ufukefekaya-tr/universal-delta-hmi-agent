# SPDX-License-Identifier: Apache-2.0
from .. import cli
from ..errors import AgentError
from .hmi4_bootstrap import Error
def install():
    S,H,I,O=cli.STRING,cli.HASH,cli.INTEGER,cli.OBJECT;B={'type':'boolean'}
    def schema(fields,required):return cli.object_schema(fields,required)
    extra={
      'intake_source_profile':(dict(path=S,source_sha256=H,expected_link=S,expected_station=I),('path','source_sha256','expected_link','expected_station')),
      'inspect_native_catalog':(dict(candidate_sha256=H,page_id=I),('candidate_sha256',)),
      'inspect_multilingual_text':(dict(candidate_sha256=H,page_id=I),('candidate_sha256',)),
      'inspect_numeric_bindings':(dict(candidate_sha256=H),('candidate_sha256',)),
      'inspect_navigation':(dict(candidate_sha256=H),('candidate_sha256',)),
      'inspect_endpoint':(dict(candidate_sha256=H,expected_endpoint=O),('candidate_sha256',)),
      'inspect_affine_scale':(dict(candidate_sha256=H,page_id=I,element_id=I,raw_value=S,display_value=S),('candidate_sha256','page_id','element_id')),
      'validate_bindings':(dict(candidate_sha256=H,contract=O,contract_sha256=H,require_all=B,lookup_expectations={'type':'array','items':O,'minItems':1,'maxItems':1000},lookup_expectations_sha256=H),('candidate_sha256','contract','contract_sha256')),
      'plan_register_import':(dict(candidate_sha256=H,contract=O,contract_sha256=H,bindings={'type':'array','items':O,'minItems':1,'maxItems':999}),('candidate_sha256','contract','contract_sha256','bindings')),
      'plan_native_update':(dict(candidate_sha256=H,specification=O,specification_sha256=H),('candidate_sha256','specification','specification_sha256')),
      'inspect_native_plan':(dict(plan_sha256=H),('plan_sha256',)),
      'restore_plan':(dict(plan_sha256=H),('plan_sha256',)),
      'restore_candidate':(dict(plan_sha256=H,approval_sha256=H),('plan_sha256','approval_sha256')),
      'save_new':(dict(path=S,candidate_sha256=H),('path','candidate_sha256')),
      'validate_native_candidate':(dict(candidate_sha256=H,include_font_fit=B),('candidate_sha256',)),
      'check_text_fit':(dict(candidate_sha256=H,page_id=I),('candidate_sha256',)),
      'preview_native_page':(dict(candidate_sha256=H,page_id=I,language=I,values=O),('candidate_sha256','page_id','language')),
      'plan_offline_package':(dict(candidate_sha256=H,output_path=S,dpa_name=S,expected_endpoint=O),('candidate_sha256','output_path','dpa_name','expected_endpoint')),
      'apply_offline_package':(dict(plan_sha256=H,approval_sha256=H),('plan_sha256','approval_sha256')),
      'inspect_artifact_plan':(dict(plan_sha256=H),('plan_sha256',)),
      'inspect_offline_package':(dict(path=S,artifact_sha256=H,candidate_sha256=H,expected_endpoint=O),('path','artifact_sha256','candidate_sha256','expected_endpoint')),
      'plan_contract_rebind':(dict(candidate_sha256=H,previous_contract=O,previous_sha256=H,contract=O,contract_sha256=H),('candidate_sha256','previous_contract','previous_sha256','contract','contract_sha256')),
      'apply_contract_rebind':(dict(plan_sha256=H,approval_sha256=H),('plan_sha256','approval_sha256')),
      **{name:(dict(candidate_sha256=H),('candidate_sha256',)) for name in ('vendor_open_save_reopen','vendor_compile','offline_simulator','build_transfer_package','inspect_transfer_package')},
      'inspect_operation':(dict(operation_id=S),('operation_id',)), 'reconcile_operation':(dict(operation_id=S),('operation_id',)),
      'inspect_numeric_fields':(dict(candidate_sha256=H,page_id=I,element_id=I),('candidate_sha256','page_id','element_id')),
      'configure_numeric_fields':(dict(candidate_sha256=H,page_id=I,element_id=I,expected_element_sha256=H,spec=O),('candidate_sha256','page_id','element_id','expected_element_sha256','spec')),
      'validate_register_contract':(dict(contract=O,contract_sha256=H),('contract','contract_sha256')),
      'create_screen':(dict(donor_id=S,donor_page_id=I,new_page_id=I,name=S),('donor_id','donor_page_id','new_page_id','name')),
      'create_element':(dict(donor_id=S,donor_page_id=I,donor_element_id=I,page_id=I,new_element_id=I,name=S,rect=O,retain_bindings=B,retain_macros=B),('donor_id','donor_page_id','donor_element_id','page_id','new_element_id','name','rect','retain_bindings','retain_macros')),
      'import_symbol_catalog':(dict(xml=S,contract=O,contract_sha256=H,expected_xml_sha256=H,bindings={'type':'array','items':O,'maxItems':999}),('xml','contract','contract_sha256','expected_xml_sha256','bindings')),
      'import_tags':(dict(address_space=S,xml=S,contract=O,contract_sha256=H,expected_xml_sha256=H,bindings={'type':'array','items':O,'maxItems':999}),('address_space','xml','contract','contract_sha256','expected_xml_sha256','bindings')),
      'verify_symbol_contract':(dict(contract=O,contract_sha256=H),('contract','contract_sha256')),
      'configure_native_service':(dict(family=S,candidate_sha256=H),('family','candidate_sha256')),
      'create_alarm_catalog':(dict(candidate_sha256=H),('candidate_sha256',)),
    }
    cli.COMMON.update({name:schema(fields,required) for name,(fields,required) in extra.items()})
    original=cli.call_tool
    def call(session,name,arguments):
        try:return original(session,name,arguments)
        except Error as error:raise AgentError(error.code,str(error)) from error
        except OSError as error:
            raise AgentError('IO_FAILURE_RECONCILE_REQUIRED','I/O failed; inspect durable operation state and artifacts before assuming the outcome or retrying') from error
    cli.call_tool=call
