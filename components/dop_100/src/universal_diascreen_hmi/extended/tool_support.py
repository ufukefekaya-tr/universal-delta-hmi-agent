# SPDX-License-Identifier: Apache-2.0
"""One support record supplies discovery descriptions and capability status."""
UNIMPLEMENTED = frozenset({'vendor_open_save_reopen','vendor_compile','offline_simulator','build_transfer_package','inspect_transfer_package','configure_native_service','create_alarm_catalog'})
CATALOG = frozenset({'list_deliveries','current_delivery','open_delivery','inspect_parameters','get_reference_contract'})
TEMPLATES = frozenset({'inspect_template','create_project','apply_project_plan','configure_target','create_neutral_screen','inspect_neutral_screens'})


def record(name):
    row=dict(tool=name,implemented=name not in UNIMPLEMENTED,headless=name not in UNIMPLEMENTED,
             support_level='SOURCE_BOUND_OFFLINE_FILE_SERVICE',vendor_qualified=False,runtime_qualified=False)
    if name in UNIMPLEMENTED:
        row.update(support_level='UNSUPPORTED_NOT_IMPLEMENTED',headless=False,
                   boundary='Explicit NOT_IMPLEMENTED refusal; host consent cannot enable an absent adapter')
    elif name in CATALOG:
        row.update(support_level='OPTIONAL_HOST_REFERENCE_CATALOG',boundary='Empty by default; private catalog files are never packaged')
    elif name in TEMPLATES:
        row.update(support_level='QUALIFIED_HOST_TEMPLATE_FILE_SERVICE',boundary='Exact host-owned neutral seed/profile/review; byte copy or stock-frame derivation, not vendor construction or model conversion')
    elif name=='inspect_native_resource_banks':
        row.update(boundary='Closed DOP-107EV native6.6.2.48 framing; not semantic alarm/history/tag support')
    elif name=='inspect_target_configuration':
        row.update(boundary='Actual Application readback separate from declared metadata; no template catalog or running IDE required')
    elif name in ('validate_register_contract','verify_symbol_contract'):
        row.update(boundary='Logical type contract audit is not native writer or runtime support')
    elif name in ('delete_element','plan_changes','apply_plan'):
        row.update(boundary='Deletion requires a closed inert indexed graph; macros/events/opaque resources/unknown fields refuse')
    else:row.update(boundary='Exact source/profile/plan pins; separate saved-file readback; no GUI, IDE or device execution')
    return row


def registry():
    from .. import cli
    from .transport import definitions
    names=set(cli.COMMON)|set(definitions())|set(cli.ALIASES)|set(cli.EDIT_ALIASES)|{'save'}
    return {name:record(name) for name in sorted(names)}


def description(name):
    r=record(name)
    return r['support_level']+': '+r['boundary']+'.'
