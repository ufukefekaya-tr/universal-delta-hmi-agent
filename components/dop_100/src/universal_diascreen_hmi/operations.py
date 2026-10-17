# SPDX-License-Identifier: Apache-2.0
"""Original exact-plan compiler. No generic arbitrary native property writer."""
from decimal import Decimal, InvalidOperation, localcontext
import json
import re

from .errors import AgentError, digest, require
from .native import Patch, Project, apply_spans, encode_token, restore_spans, layout_digest
from .resources import embedded_xml, flat_dib, resource, resource_patch, map_reviewed_resources

ELEMENT_VISUAL = {'X', 'Y', 'Width', 'Height', 'Style', 'BorderColor'}
STATE_VISUAL = {'FontName0', 'FontSize0', 'FontAlign', 'FontBold', 'FontItalic',
                'FontUnderline', 'FontRatio0', 'FontColor', 'FgColor', 'BgColor',
                'FgFillColor', 'FgFillEndColor', 'BgFillColor', 'BgFillEndColor',
                *('FgFillStopColor' + str(n) for n in range(5)),
                *('BgFillStopColor' + str(n) for n in range(5))}
ADDRESS_ROLES = {'ReadVar': 'read', 'WriteVar': 'write', 'TriggerVar': 'read',
                 'InterLockVar': 'read', 'VisibleVar': 'read', 'DisplayDotVar': 'read',
                 'UnitSrcVar': 'read', 'UnitDisplayVar': 'read', 'ReadOffsetVar': 'read',
                 'WriteOffsetVar': 'read', 'UnitPercent1Var': 'read', 'UnitPercent2Var': 'read'}
OP_FIELDS = {
    'set_property': {'page_id', 'element_id', 'state_value', 'field', 'value', 'expected'},
    'set_text': {'page_id', 'element_id', 'state_value', 'description', 'field', 'text'},
    'rebind': {'page_id', 'element_id', 'field', 'expected_address', 'address', 'xml_index'},
    'numeric': {'page_id', 'element_id', 'spec', 'xml_index'},
    'button_behavior': {'page_id', 'element_id', 'behavior'},
    'navigation': {'page_id', 'element_id', 'target_page_id'},
    'delete_element': {'page_id', 'element_id'}, 'reorder_element': {'page_id', 'order'},
    'clone_element': {'donor_id', 'donor_page_id', 'donor_element_id', 'page_id', 'new_element_id', 'name', 'rect', 'retain_bindings', 'retain_macros'},
    'clone_screen': {'donor_id', 'donor_page_id', 'new_page_id', 'name', 'content', 'retain_bindings', 'retain_macros'},
    'delete_screen': {'page_id'}, 'default_screen': {'page_id'},
    'replace_xml': {'xml', 'xml_index', 'expected_xml_sha256'},
    'flat_background': {'resource_index', 'page_ids', 'rgb', 'expected_bank_sha256'},
    'clear_macro': {'section_index', 'slot', 'expected_macro_sha256'},
    'patch_macro_operand': {'section_index', 'slot', 'expected_macro_sha256', 'instruction_index', 'field_index', 'expected', 'value'},
    'donor_macro': {'section_index', 'slot', 'expected_macro_sha256', 'source_bound_ack', 'donor_hex', 'donor_sha256'},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def whole(value, label, low=0, high=2147483647):
    require(type(value) is int and low <= value <= high, 'INTEGER', 'Expected a bounded integer', field=label)
    return value


def decimal(value, label):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), 'NUMERIC_LITERAL', 'Use explicit decimal strings or integers', field=label)
    text = str(value)
    require(bool(re.fullmatch(r'-?[0-9]{1,40}(?:\.[0-9]{1,20})?', text)),
            'NUMERIC_LITERAL', 'Scientific notation and nonfinite literals are outside the observed contract', field=label)
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise AgentError('NUMERIC_LITERAL', 'Invalid decimal literal') from exc
    require(number.is_finite(), 'NUMERIC_LITERAL', 'Nonfinite numeric value')
    return number


def token_patch(q, section, key, value, reason):
    token = section.one(key)
    return Patch(token.start, token.end, token.raw(q.file.payload), encode_token(token, value, q.file.payload), reason)


def qualified_xml(q, profile, index=0):
    frame, data = embedded_xml(q, index)
    link = frame.metadata.get('DIATagLinkName')
    station = frame.metadata.get('DIATagStationNr')
    explicit = profile.get('catalog_bindings', {}).get(str(index), {})
    metadata_match = link == profile['link'] and station == str(profile['station'])
    reviewed_match = (not link or not station) and (not link or link == profile['link']) and (not station or station == str(profile['station'])) and explicit.get('reviewed') is True and explicit.get('xml_sha256') == digest(data) and explicit.get('link') == profile['link'] and explicit.get('station') == profile['station']
    require(metadata_match or reviewed_match, 'CATALOG_TARGET', 'Selected XML catalog is not associated with the profiled link and station')
    return frame, data


def state(q, element, value):
    whole(value, 'state Value')
    found = [s for s in element.states if q.index.number(s, 'Value') == value]
    require(len(found) == 1, 'STATE_VALUE', 'The exact native state Value is absent')
    return found[0]


def rect(q, element, changes, profile):
    fields = {k: q.index.number(element.section, k) for k in ('X', 'Y', 'Width', 'Height')}
    fields.update(changes)
    for key, value in fields.items():
        whole(value, key, 1 if key in ('Width', 'Height') else 0)
    panel = profile['panel']
    require(fields['X'] + fields['Width'] <= panel['width'] and fields['Y'] + fields['Height'] <= panel['height'],
            'OFF_CANVAS', 'Element rectangle extends outside the profiled panel')


def target(q, operation):
    return q.element(whole(operation.get('page_id'), 'page_id'), whole(operation.get('element_id'), 'element_id'))


def _replace_block(q, start, end, edits):
    patches = [Patch(p.start - start, p.end - start, p.old, p.new, p.reason) for p in edits]
    return apply_spans(q.file.payload[start:end], patches)[0]


def _name(q, element):
    return q.index.text(element.section, 'wDescTextLen0', '')


def validate_references(q):
    pages = {p.page_id for p in q.pages}
    require(pages, 'NO_PAGES', 'A native candidate must retain a page')
    default = q.index.number(q.app, 'DefaultScreen', 0)
    require(default in pages, 'DEFAULT_PAGE', 'Default screen points to a missing page')
    for p in q.pages:
        for e in p.elements:
            token = e.section.one('GoToScreenID', optional=True)
            # Only navigation controls own a live page jump. Inactive donor fields are preserved.
            if token and q.index.number(e.section, 'Type') == 1 and q.index.number(e.section, 'SubType') == 10:
                require(int(token.value) in pages, 'DANGLING_NAVIGATION', 'Navigation points to a missing page')


def address_inventory(q, include_macros=True):
    rows = []
    owners = {}
    for p in q.pages:
        owners[p.section.start] = {'page_id': p.page_id}
        for sec in p.aux:
            owners[sec.start] = {'page_id': p.page_id, 'auxiliary': True}
        for e in p.elements:
            for sec in (e.section, *e.states):
                owners[sec.start] = {'page_id': p.page_id, 'element_id': q.index.number(e.section, 'nPartsID')}
    for si, sec in enumerate(q.index.sections):
            for token in sec.tokens:
                if token.key and (token.key.endswith(('Var', 'Addr', 'Address')) or b'DIA_TAG@' in token.value):
                    address = token.value.decode('latin-1')
                    if address not in ('None', ''):
                        rows.append({**owners.get(sec.start, {}), 'section_index': si,
                                     'field': token.key, 'address': address,
                                     'role': ADDRESS_ROLES.get(token.key, 'source_qualified_read_or_unknown'),
                                     'semantics': 'No physical-feedback meaning inferred'})
    if include_macros:
        from .macros import parse_macro
        for si, sec in enumerate(q.index.sections):
            for token in sec.tokens:
                if token.kind == 'macro' and token.blob(q.file.payload):
                    program = parse_macro(token.blob(q.file.payload))
                    for n, instruction in enumerate(program.instructions):
                        for f, value in enumerate(instruction.fields):
                            if b'@' in value:
                                rows.append({'section': si, 'slot': token.key, 'instruction': n, 'field': f,
                                             'address': value.decode('latin-1'), 'role': 'macro_visible' if f == 0 else 'macro_parsed'})
    return rows


def validate_all_bindings(q, catalog, profile):
    from .symbols import validate_reference
    from .macros import parse_macro
    for owner in address_inventory(q, include_macros=False):
        if owner['address'].startswith('DIA_TAG@'):
            require(owner['field'] in ADDRESS_ROLES, 'ADDRESS_ROLE', 'XML replacement has an unqualified address dependency', field=owner['field'])
            validate_reference(owner['address'], ADDRESS_ROLES[owner['field']], catalog, profile['link'], profile['station'])
    for sec in q.index.sections:
        for token in sec.tokens:
            if token.kind != 'macro' or not token.blob(q.file.payload):
                continue
            program = parse_macro(token.blob(q.file.payload))
            require(not program.inspect()['unknown_opcodes'], 'XML_MACRO_DEPENDENCY', 'Unknown macro semantics prevent XML replacement')
            for n, instruction in enumerate(program.instructions):
                for f, value in enumerate(instruction.fields[1:], 1):
                    if value.startswith(b'{'):
                        qualified_operand(q, program, n, f, value, profile, catalog)
                if b'DIA_TAG@' in instruction.fields[0]:
                    require(any(v.startswith(b'{') for v in instruction.fields[1:]), 'XML_MACRO_DEPENDENCY', 'Visible remote reference has no qualified parsed operand')


def numeric_changes(q, e, spec, profile):
    require(q.index.number(e.section, 'Type') in (5, 6), 'CONTROL_TYPE', 'Target is not a numeric control')
    contracts = profile.get('numeric_types', {})
    kind = spec.get('iec_type')
    require(kind != 'TIME', 'TIME_INTERFACE', 'TIME needs an explicit real PLC millisecond interface; no silent coercion')
    require(kind in contracts and contracts[kind].get('evidence'), 'NUMERIC_TYPE', 'Numeric type has no source-qualified native contract')
    contract = contracts[kind]
    minimum, maximum = decimal(spec.get('minimum'), 'minimum'), decimal(spec.get('maximum'), 'maximum')
    require(minimum <= maximum, 'NUMERIC_RANGE', 'Minimum exceeds maximum')
    bits = whole(contract.get('bits'), 'numeric bits', 1, 64)
    if not contract.get('floating', False):
        lower = -(1 << (bits - 1)) if contract.get('signed') else 0
        upper = (1 << (bits - 1)) - 1 if contract.get('signed') else (1 << bits) - 1
        require(minimum == minimum.to_integral_value() and maximum == maximum.to_integral_value()
                and lower <= minimum <= maximum <= upper, 'NUMERIC_DOMAIN', 'Limits exceed integer type domain')
    digits = whole(spec.get('integer_digits'), 'integer_digits', 1, 20)
    decimals = whole(spec.get('decimals'), 'decimals', 0, 15)
    quantum = Decimal(1).scaleb(-decimals)
    with localcontext() as ctx:
        ctx.prec = 128
        require(all(v == v.quantize(quantum) for v in (minimum, maximum)), 'NUMERIC_PRECISION',
                'Limits must be exactly representable at the declared decimal places; no rounding guess')
    largest = max(abs(minimum), abs(maximum))
    needed = len(str(int(largest)))
    require(needed <= digits and needed <= profile.get('numeric_literal_digits', 15),
            'DISPLAY_RANGE', 'Explicit limits exceed declared display/literal digits; limits are never guessed')
    gain, offset = decimal(spec.get('gain'), 'gain'), decimal(spec.get('offset'), 'offset')
    require(gain != 0, 'NUMERIC_SCALE', 'Zero gain cannot provide an invertible input scale')
    mapping = {'MemLen': whole(contract['MemLen'], 'MemLen'), 'MemFmt': whole(contract['MemFmt'], 'MemFmt'),
               'MinValue': str(minimum), 'MaxValue': str(maximum), 'IntNum': digits, 'DotNum': decimals,
               'GainValue': str(gain), 'OffsetValue': str(offset)}
    result = [token_patch(q, e.section, key, value, 'typed numeric ' + key) for key, value in mapping.items()]
    if 'unit' in spec:
        result.append(token_patch(q, e.section, 'UnitTextLen0', spec['unit'], 'counted numeric unit'))
    return result


def inherited_content(q, donor, sections, op):
    """Cross-project references require identical dependency banks, not index reuse."""
    for sec in sections:
        for token in sec.tokens:
            if token.kind == 'macro' and token.blob(donor.file.payload):
                require(op.get('retain_macros') is True, 'DONOR_MACROS', 'Macro inheritance must be explicit')
            if token.key and token.key.endswith(('Var', 'Addr', 'Address')) and token.value not in (b'', b'None'):
                require(op.get('retain_bindings') is True, 'DONOR_BINDINGS', 'Binding inheritance must be explicit')
    if q.file.original != donor.file.original:
        for section, count in (('Background', 'Size'), ('Picture', 'Size'), ('DIATag', 'size')):
            from .resources import resource_frames
            left = [q.file.payload[f.start:f.blob_end] for f in resource_frames(q, section, count)]
            right = [donor.file.payload[f.start:f.blob_end] for f in resource_frames(donor, section, count)]
            require(left == right, 'DONOR_DEPENDENCIES', 'Cross-file donors require identical resource and symbol banks; copy/remap is unqualified')


def qualified_operand(q, program, instruction_index, field_index, value, profile, catalog=None):
    from .symbols import parse_symbols, validate_reference
    from .macros import parse_parsed_address
    require(instruction_index < len(program.instructions), 'MACRO_INDEX', 'Instruction is absent')
    instruction = program.instructions[instruction_index]
    contract = profile.get('macro_slots', {}).get(instruction.opcode.hex() + ':' + str(field_index))
    require(isinstance(contract, dict) and contract.get('evidence'), 'MACRO_SLOT_UNQUALIFIED', 'Opcode operand slot lacks a source-qualified contract')
    if contract.get('kind') == 'remote':
        parsed = parse_parsed_address(value)
        display = 'DIA_TAG@{' + parsed['link'] + '}' + str(parsed['station']) + '.' + parsed['path']
        role = contract.get('role')
        require(role in ('read', 'write'), 'MACRO_ROLE', 'Remote operand role must be explicit')
        if catalog is None:
            _, xml = qualified_xml(q, profile)
            catalog = parse_symbols(xml)
        resolved = validate_reference(display, role, catalog, profile['link'], profile['station'])['symbol']
        require(resolved['iec_type'] in contract.get('iec_types', []), 'MACRO_TYPE', 'Operand symbol type is outside the slot contract')
    elif contract.get('kind') == 'exact':
        require(value.decode('ascii') in contract.get('allowed', []), 'MACRO_VALUE', 'Operand literal/internal value is outside the exact contract')
    else:
        raise AgentError('MACRO_SLOT_UNQUALIFIED', 'Unqualified operand kind')


def operation_patches(q, op, profile, donors=None):
    name = op.get('op')
    require(name in OP_FIELDS and set(op) <= OP_FIELDS[name] | {'op', 'operation_id'}, 'OPERATION_FIELDS', 'Unsupported operation or unrecognized fields are not silently ignored')
    if 'description' in op:
        require(type(op['description']) is bool, 'TEXT_FIELD', 'Description selector must be boolean')
    if name in ('set_property', 'set_text', 'rebind', 'numeric', 'button_behavior', 'navigation', 'delete_element'):
        e = target(q, op)
    if name == 'set_property':
        field_name = op.get('field')
        sec = e.section if 'state_value' not in op else state(q, e, op['state_value'])
        require(field_name in (ELEMENT_VISUAL if sec is e.section else STATE_VISUAL),
                'PROPERTY_NOT_QUALIFIED', 'Property is not an explicitly qualified existing visual field')
        value = op.get('value')
        old = sec.one(field_name)
        if 'expected' in op:
            require(old.value.decode('latin-1') == str(op['expected']), 'PRECONDITION', 'Expected property value differs')
        if field_name in ('X', 'Y', 'Width', 'Height'):
            rect(q, e, {field_name: value}, profile)
        elif field_name != 'FontName0':
            whole(value, field_name, 0, 0xffffff if 'Color' in field_name else 10000)
            if field_name == 'FontSize0':
                require(value >= 1, 'FONT_SIZE', 'Font size must be positive')
            if field_name == 'Style':
                require(value in (0, 3), 'STYLE_UNQUALIFIED', 'Only observed Style0/3 are qualified')
            if field_name == 'FontAlign':
                require(value in (18, 33, 34, 36), 'ALIGN_UNQUALIFIED', 'Unobserved native alignment')
            if field_name in ('FontBold', 'FontItalic', 'FontUnderline'):
                require(value in (0, 1), 'FONT_FLAG', 'Font flag must be0/1')
            if field_name == 'FontRatio0':
                require(value == 100, 'FONT_RATIO', 'Only source-qualified100 percent ratio is supported')
        return [token_patch(q, sec, field_name, value, 'qualified visual field ' + field_name)]
    if name == 'set_text':
        sec = e.section if op.get('description') else state(q, e, op.get('state_value'))
        key = op.get('field', 'wDescTextLen0' if op.get('description') else 'wTextLen0')
        require(key in {'wDescTextLen0', 'wDescTextLen1', 'wTextLen0', 'wTextLen1'}, 'TEXT_FIELD', 'Unqualified language field')
        return [token_patch(q, sec, key, op.get('text'), 'counted Unicode caption')]
    if name == 'rebind':
        from .symbols import parse_symbols, validate_reference, parse_address
        field_name = op.get('field')
        require(field_name in ADDRESS_ROLES, 'ADDRESS_ROLE', 'Unqualified address field')
        old = e.section.one(field_name).value.decode('latin-1')
        require(old == op.get('expected_address'), 'PRECONDITION', 'Exact address precondition failed; no substring rebind')
        _, xml = qualified_xml(q, profile, op.get('xml_index', 0))
        catalog = parse_symbols(xml)
        resolved = validate_reference(op.get('address'), ADDRESS_ROLES[field_name], catalog,
                           profile['link'], profile['station'])['symbol']
        if old.startswith('DIA_TAG@'):
            previous = catalog.resolve(parse_address(old)['path'])
            require((resolved['iec_type'], resolved['bits']) == (previous['iec_type'], previous['bits']),
                    'REBIND_TYPE', 'Rebind must preserve the original XML symbol type and width; use a qualified numeric/type workflow')
        else:
            contract = profile.get('binding_types', {}).get(field_name)
            require(isinstance(contract, dict) and contract.get('evidence') and resolved['iec_type'] in contract.get('iec_types', []),
                    'REBIND_TYPE', 'An unbound donor needs an explicit field type contract')
        return [token_patch(q, e.section, field_name, op['address'], 'typed exact address rebind')]
    if name == 'numeric':
        from .symbols import parse_symbols, validate_reference
        _, xml = qualified_xml(q, profile, op.get('xml_index', 0))
        role = 'write' if q.index.scalar(e.section, 'WriteVar', 'None') != 'None' else 'read'
        address = q.index.scalar(e.section, 'WriteVar' if role == 'write' else 'ReadVar')
        resolved = validate_reference(address, role, parse_symbols(xml), profile['link'], profile['station'])['symbol']
        spec = op.get('spec', {})
        require(resolved['numeric_coercion_supported'] and resolved['iec_type'] == spec.get('iec_type')
                and resolved['bits'] == profile.get('numeric_types', {}).get(spec.get('iec_type'), {}).get('bits'),
                'NUMERIC_BINDING_TYPE', 'Numeric type must match the actual XML-bound symbol width and type')
        return numeric_changes(q, e, spec, profile)
    if name == 'button_behavior':
        entry = profile.get('button_types', {}).get(op.get('behavior'))
        require(entry and entry.get('evidence'), 'BEHAVIOR_UNQUALIFIED', 'Behavior requires an explicit source-qualified type contract')
        require((entry.get('Type'), entry.get('SubType')) in ((1, 3), (1, 4)), 'BEHAVIOR_UNQUALIFIED', 'Only observed momentary1.3/maintained1.4 conversion is qualified; others need a donor workflow')
        require(q.index.number(e.section, 'Type') == 1, 'CONTROL_TYPE', 'Target is not a source button')
        patches = [token_patch(q, e.section, 'Type', entry['Type'], 'source-qualified button behavior'),
                   token_patch(q, e.section, 'SubType', entry['SubType'], 'source-qualified button behavior')]
        require({q.index.number(st, 'Value') for st in e.states} >= {0, 1}, 'BUTTON_STATES', 'Both boolean states are required')
        return patches
    if name == 'navigation':
        require(q.index.number(e.section, 'Type') == 1 and q.index.number(e.section, 'SubType') == 10,
                'CONTROL_TYPE', 'Navigation requires an existing navigation donor')
        page = q.page(whole(op.get('target_page_id'), 'target_page_id'))
        patches = [token_patch(q, e.section, 'GoToScreenID', page.page_id, 'explicit page navigation')]
        if e.section.one('GoToScreenName', optional=True):
            patches.append(token_patch(q, e.section, 'GoToScreenName', q.index.text(page.section, 'wTextLen'), 'coupled page navigation name'))
        return patches
    if name == 'delete_element':
        return [Patch(e.section.start, e.end, q.file.payload[e.section.start:e.end], b'', 'delete exact screen-local identity')]
    if name == 'reorder_element':
        page = q.page(whole(op.get('page_id'), 'page_id'))
        order = op.get('order')
        ids = [q.index.number(x.section, 'nPartsID') for x in page.elements]
        require(isinstance(order, list) and all(type(i) is int and i >= 0 for i in order)
                and len(order) == len(ids) and set(order) == set(ids), 'Z_ORDER', 'Order must list each existing identity once')
        elements = {q.index.number(x.section, 'nPartsID'): x for x in page.elements}
        require(ids, 'Z_ORDER', 'Empty screen has no order to change')
        first, last = page.elements[0].section.start, page.elements[-1].end
        new = b''.join(q.file.payload[elements[i].section.start:elements[i].end] for i in order)
        return [Patch(first, last, q.file.payload[first:last], new, 'atomic element/state z-order blocks')]
    if name == 'clone_element':
        donor = (donors or {}).get(op.get('donor_id'))
        require(donor is not None, 'DONOR', 'A separately hash-pinned donor is required')
        d = donor.element(whole(op.get('donor_page_id'), 'donor_page_id'), whole(op.get('donor_element_id'), 'donor_element_id'))
        page = q.page(whole(op.get('page_id'), 'page_id'))
        new_id = whole(op.get('new_element_id'), 'new_element_id')
        require(all(q.index.number(x.section, 'nPartsID') != new_id for x in page.elements), 'DUPLICATE_CLONE', 'Element identity already exists')
        caption = op.get('name')
        require(isinstance(caption, str) and caption and all(_name(q, x) != caption for x in page.elements), 'DUPLICATE_CLONE', 'Element name is missing or already exists')
        inherited_content(q, donor, [d.section, *d.states], op)
        require(op.get('retain_bindings') is True, 'DONOR_BINDINGS', 'Explicitly acknowledge inherited address fields; use a later typed rebind')
        edits = [token_patch(donor, d.section, 'nPartsID', new_id, 'fresh donor identity'),
                 token_patch(donor, d.section, 'wDescTextLen0', caption, 'fresh donor name')]
        geometry = op.get('rect')
        require(isinstance(geometry, dict) and set(geometry) == {'X', 'Y', 'Width', 'Height'}, 'GEOMETRY', 'Clone needs a complete explicit rectangle')
        rect(donor, d, geometry, profile)
        edits += [token_patch(donor, d.section, key, val, 'donor rectangle') for key, val in geometry.items()]
        clone = _replace_block(donor, d.section.start, d.end, edits)
        return [Patch(page.end, page.end, b'', clone, 'append source donor element/state block')]
    if name == 'clone_screen':
        donor = (donors or {}).get(op.get('donor_id'))
        require(donor is not None, 'DONOR', 'A separately pinned page donor is required')
        page = donor.page(whole(op.get('donor_page_id'), 'donor_page_id'))
        pid = whole(op.get('new_page_id'), 'new_page_id', 1, 65534)
        require(all(p.page_id != pid for p in q.pages), 'DUPLICATE_CLONE', 'Screen identity already exists')
        caption = op.get('name')
        require(isinstance(caption, str) and caption and all(q.index.text(p.section, 'wTextLen') != caption for p in q.pages), 'DUPLICATE_CLONE', 'Screen name is missing or already exists')
        require(op.get('content', 'frame') in ('frame', 'all'), 'CLONE_CONTENT', 'Choose frame or explicit full content')
        if op.get('content') == 'all':
            require(op.get('retain_bindings') is True and op.get('retain_macros') is True,
                    'CLONE_ACK', 'Full page cloning requires explicit inherited binding/macro acknowledgement')
        end = page.end if op.get('content') == 'all' else (page.elements[0].section.start if page.elements else page.end)
        inherited_content(q, donor, [s for s in donor.index.sections if page.section.start <= s.start < end], op)
        edits = [token_patch(donor, page.section, 'ID', pid, 'new page identity'),
                 token_patch(donor, page.section, 'wTextLen', caption, 'new page name')]
        clone = _replace_block(donor, page.section.start, end, edits)
        return [Patch(q.index.tail_start, q.index.tail_start, b'', clone, 'append donor screen/frame+aux')]
    if name == 'delete_screen':
        page = q.page(whole(op.get('page_id'), 'page_id'))
        return [Patch(page.section.start, page.end, q.file.payload[page.section.start:page.end], b'', 'delete exact screen identity')]
    if name == 'default_screen':
        page = q.page(whole(op.get('page_id'), 'page_id'))
        return [token_patch(q, q.app, 'DefaultScreen', page.page_id, 'explicit default page')]
    if name == 'replace_xml':
        from .symbols import parse_symbols, assert_additive_symbols
        require(isinstance(op.get('xml'), str), 'XML', 'XML replacement must be explicit Unicode text')
        blob = op['xml'].encode('utf-8')
        frame, previous = qualified_xml(q, profile, op.get('xml_index', 0))
        catalog = parse_symbols(blob)
        assert_additive_symbols(parse_symbols(previous), catalog)
        validate_all_bindings(q, catalog, profile)
        return [resource_patch(q, frame, 'size', blob, op.get('expected_xml_sha256'))]
    if name == 'flat_background':
        frame = resource(q, 'Background', 'Size', op.get('resource_index', 0))
        previous = q.file.payload[frame.blob_start:frame.blob_end]
        dib = flat_dib(profile['panel']['width'], profile['panel']['height'], whole(op.get('rgb'), 'rgb', 0, 0xffffff))
        page_ids = op.get('page_ids')
        require(isinstance(page_ids, list) and page_ids and len(set(page_ids)) == len(page_ids), 'BACKGROUND_PAGES', 'Select pages explicitly')
        patches = [resource_patch(q, frame, 'Size', previous + dib, op.get('expected_bank_sha256'))]
        patches += [token_patch(q, q.page(whole(pid, 'page_id')).section, 'PictureOffset', len(previous), 'new text-free background address') for pid in page_ids]
        return patches
    if name in ('clear_macro', 'patch_macro_operand', 'donor_macro'):
        from .macros import parse_macro
        section_index = whole(op.get('section_index'), 'section_index', 0, len(q.index.sections) - 1)
        sec = q.index.sections[section_index]
        token = sec.one(op.get('slot'))
        require(token.kind == 'macro', 'MACRO_SLOT', 'Target is not a counted macro slot')
        blob = token.blob(q.file.payload) or b''
        require(digest(blob) == op.get('expected_macro_sha256'), 'MACRO_HASH', 'Macro precondition failed')
        if name == 'clear_macro':
            new_blob = b''
        elif name == 'patch_macro_operand':
            program = parse_macro(blob)
            ins = whole(op.get('instruction_index'), 'instruction_index')
            field = whole(op.get('field_index'), 'field_index', 1, 4)
            require(isinstance(op.get('expected'), str) and isinstance(op.get('value'), str), 'MACRO_VALUE', 'Exact operand strings are required')
            try:
                expected, value = op['expected'].encode('ascii'), op['value'].encode('ascii')
            except UnicodeEncodeError as exc:
                raise AgentError('MACRO_VALUE', 'Operands must be native ASCII') from exc
            qualified_operand(q, program, ins, field, value, profile)
            new_blob = program.replace_operand(ins, field, expected, value)
        else:
            require(op.get('source_bound_ack') is True, 'MACRO_UNQUALIFIED', 'Donor macro reuse is source-bound and runtime-unqualified')
            try:
                new_blob = bytes.fromhex(op.get('donor_hex', ''))
            except ValueError as exc:
                raise AgentError('MACRO_DONOR', 'Invalid donor macro bytes') from exc
            require(digest(new_blob) == op.get('donor_sha256'), 'MACRO_DONOR', 'Donor macro hash changed')
            require(not parse_macro(new_blob).inspect()['unknown_opcodes'], 'MACRO_UNQUALIFIED', 'Unknown donor instructions remain read-only')
            program = parse_macro(new_blob)
            for n, instruction in enumerate(program.instructions):
                for f, value in enumerate(instruction.fields[1:], 1):
                    if value:
                        qualified_operand(q, program, n, f, value, profile)
        new = token.key.encode() + b'=' + str(len(new_blob)).encode() + b'\r\n' + new_blob
        return [Patch(token.start, token.end, token.raw(q.file.payload), new, 'explicit source-bound macro slot')]
    raise AgentError('OPERATION_UNSUPPORTED', 'Operation is not implemented or qualified', operation=name)


def compile_changes(source, operations, profile, donors=None):
    require(isinstance(operations, list) and 0 < len(operations) <= 1000, 'PLAN', 'Plan requires 1..1000 explicit operations')
    original = Project(source)
    require(not original.index.unqualified_records and original.index.stop_reason in ('end', 'resource:SubMacro', 'resource:Global_Auxkey',
                'resource:Alarm', 'resource:History', 'resource:TextBank', 'resource:Tag', 'resource:EthernetIPTag',
                'resource:SRAM_DATA', 'resource:Picture', 'resource:Background', 'resource:SlotFile', 'resource:CWPFile',
                'resource:DeviceTable', 'resource:DIATag', 'resource:END'), 'INDEX_UNQUALIFIED', 'Unrecognized framing or records prevent edits')
    require(profile.get('reviewed_index_ack') is True and profile.get('indexed_layout_sha256') == layout_digest(original),
            'INDEX_REVIEW', 'Editing requires exact caller-reviewed indexed ownership boundaries')
    current = source
    steps = []
    reviewed = profile.get('reviewed_resources')
    ids = set()
    for n, operation in enumerate(operations):
        require(isinstance(operation, dict), 'OPERATION', 'Operation must be an object')
        operation_id = operation.get('operation_id', str(n))
        require(isinstance(operation_id, str) and operation_id not in ids, 'OPERATION_REPLAY', 'Duplicate operation identity')
        ids.add(operation_id)
        q = Project(current)
        if reviewed is not None:
            q.reviewed_resources = reviewed
        patches = operation_patches(q, operation, profile, donors)
        payload, ledger = apply_spans(q.file.payload, patches)
        reviewed = map_reviewed_resources(q, reviewed, payload, patches)
        current = q.file.encode(payload)
        Project(current)
        steps.append({'operation_id': operation_id, 'input_payload_sha256': digest(q.file.payload),
                      'output_payload_sha256': digest(payload), 'ledger': ledger, 'reviewed_resources_after': reviewed})
    final = Project(current)
    validate_references(final)
    restored = final.file.payload
    for step in reversed(steps):
        require(digest(restored) == step['output_payload_sha256'], 'INVERSE', 'Unexpected payload drift')
        restored = restore_spans(restored, step['ledger'])
        require(digest(restored) == step['input_payload_sha256'], 'INVERSE', 'Inverse step mismatch')
    require(restored == original.file.payload and final.file.thumbnail == original.file.thumbnail,
            'PRESERVATION', 'Full source inverse or thumbnail preservation failed')
    return current, steps
