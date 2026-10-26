# SPDX-License-Identifier: Apache-2.0
"""Logical AS228T register preflight. This module never serializes native fields.

D/M ranges: Delta AS Hardware & Operation Manual, 2022-05-30, table 2.2.1.
PLC memory width is distinct from DIA driver MemLen/MemFmt and word order.
"""
from decimal import Decimal, InvalidOperation
import re

from .catalog import TYPES
from .common import canonical, hash_value, require, sha

FIELDS = {'name', 'address', 'iec_type', 'width_bits', 'register_words', 'access',
          'word_order', 'scale'}
ROOT_FIELDS = {'schema_version', 'address_space', 'purpose', 'model', 'link', 'station', 'tags', 'bindings'}
SOURCE = 'https://filecenter.deltaww.com/Products/download/06/060301/Manual/DELTA_IA-PLC_AS_HOM_EN_20220530.pdf'


def decimal_value(value):
    require(isinstance(value, str) and len(value) <= 64
            and re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value),
            'REGISTER_SCALE', 'Scale requires bounded plain decimal strings')
    try:
        result = Decimal(value)
    except InvalidOperation:
        require(False, 'REGISTER_SCALE', 'Invalid decimal scale')
    require(result.is_finite(), 'REGISTER_SCALE', 'Finite scale required')
    return result


def address_layout(address, iec_type):
    require(isinstance(address, str) and len(address) <= 16, 'REGISTER_ADDRESS', 'Bounded register address required')
    match = re.fullmatch(r'(D|M)(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?', address)
    require(match is not None, 'REGISTER_ADDRESS', 'Only canonical D/M addresses are admitted by this preflight')
    area, number, bit = match.groups()
    number = int(number)
    is_bool = iec_type == 'BOOL'
    if area == 'M':
        require(is_bool and bit is None and number <= 8191, 'REGISTER_ADDRESS_TYPE', 'M0..M8191 requires BOOL without a bit suffix')
        return area, number, 1, 0, 1
    require(number <= 29999, 'REGISTER_RANGE', 'D address exceeds D29999')
    if is_bool:
        require(bit is not None and int(bit) <= 15, 'REGISTER_ADDRESS_TYPE', 'BOOL in D requires an explicit bit 0..15')
        return area, number, 1 << int(bit), 1, 1
    require(bit is None, 'REGISTER_ADDRESS_TYPE', 'Numeric D address cannot select a bit')
    words = TYPES[iec_type] // 16
    require(number + words - 1 <= 29999, 'REGISTER_RANGE', 'Multi-word value crosses D29999')
    return area, number, 0xffff, words, words


def validate_register_contract(contract, contract_sha256):
    hash_value(contract_sha256)
    require(isinstance(contract, dict) and set(contract) == ROOT_FIELDS,
            'REGISTER_CONTRACT', 'Exact register contract fields required')
    require(sha(canonical(contract)) == contract_sha256, 'CONTRACT_HASH', 'Register contract SHA differs')
    require(type(contract['schema_version']) is int and contract['schema_version'] == 1
            and contract['address_space'] == 'AS228T_REGISTER'
            and contract['model'] == 'AS228T'
            and contract['purpose'] == 'NEUTRAL_MCP_QUALIFICATION',
            'ADDRESS_SPACE', 'Explicit neutral AS228T register contract required')
    require(isinstance(contract['link'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', contract['link'])
            and type(contract['station']) is int and contract['station'] == 1,
            'REGISTER_LINK', 'Neutral link name and explicit station 1 required; no endpoint is inferred')
    tags, bindings = contract['tags'], contract['bindings']
    require(isinstance(tags, list) and 0 < len(tags) <= 4096
            and isinstance(bindings, list) and len(bindings) <= 8192,
            'REGISTER_CONTRACT', 'Bounded tag and role lists required')
    occupied, names, resolved, missing_order = {}, {}, [], []
    for row in tags:
        require(isinstance(row, dict) and set(row) == FIELDS, 'REGISTER_CONTRACT', 'Exact typed tag fields required')
        name, kind = row['name'], row['iec_type']
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name)
                and name.casefold() not in names, 'REGISTER_DUPLICATE', 'Unique bounded tag identifiers required')
        require(isinstance(kind, str) and kind in TYPES and type(row['width_bits']) is int
                and row['width_bits'] == TYPES[kind], 'REGISTER_WIDTH_TYPE', 'IEC type and logical width differ')
        area, start, mask, words, span = address_layout(row['address'], kind)
        require(type(row['register_words']) is int and row['register_words'] == words,
                'REGISTER_WIDTH_TYPE', 'Declared register span differs from the logical storage width')
        require(row['access'] in ('read', 'read_write'), 'REGISTER_ACCESS', 'Explicit read or read_write role required')
        order = row['word_order']
        allowed = ('NOT_APPLICABLE_BIT',) if kind == 'BOOL' else ('NOT_APPLICABLE_SINGLE_WORD',) if words == 1 else ('LOW_WORD_FIRST', 'HIGH_WORD_FIRST', 'UNKNOWN')
        require(order in allowed, 'REGISTER_WORD_ORDER', 'Explicit width-appropriate word order required')
        if order == 'UNKNOWN':
            missing_order.append(name)
        scale = row['scale']
        require(isinstance(scale, dict) and set(scale) == {'gain', 'offset', 'decimals', 'unit'},
                'REGISTER_SCALE', 'Exact scale fields required')
        gain, offset = decimal_value(scale['gain']), decimal_value(scale['offset'])
        require(gain != 0 and type(scale['decimals']) is int and 0 <= scale['decimals'] <= 15
                and isinstance(scale['unit'], str) and len(scale['unit']) <= 32
                and not any(ord(c) < 32 for c in scale['unit']), 'REGISTER_SCALE', 'Invalid gain, decimals or unit')
        if kind == 'BOOL':
            require(gain == 1 and offset == 0 and scale['decimals'] == 0 and scale['unit'] == '',
                    'REGISTER_SCALE', 'BOOL has no numeric scaling')
        for register in range(start, start + span):
            key = area, register
            require(not occupied.get(key, 0) & mask, 'REGISTER_OVERLAP', 'Tag storage overlaps an earlier declaration')
            occupied[key] = occupied.get(key, 0) | mask
        names[name.casefold()] = row
        resolved.append({'name': name, 'address': row['address'], 'iec_type': kind,
                         'width_bits': TYPES[kind], 'register_words': words, 'access': row['access'],
                         'declared_word_order': order, 'driver_word_order_verified': False,
                         'native_scale_applied': False})
    seen = set()
    for binding in bindings:
        require(isinstance(binding, dict) and set(binding) == {'tag', 'role'}
                and isinstance(binding['tag'], str) and binding['role'] in ('read', 'write'),
                'REGISTER_BINDING', 'Explicit tag/read-write role required')
        require(binding['tag'].casefold() in names, 'REGISTER_TAG_MISSING', 'Role references an undeclared tag')
        row = names[binding['tag'].casefold()]
        require(binding['tag'] == row['name'], 'REGISTER_BINDING', 'Binding must use the exact declared tag identity')
        key = binding['tag'], binding['role']
        require(key not in seen, 'REGISTER_BINDING_DUPLICATE', 'Duplicate tag role'); seen.add(key)
        require(binding['role'] != 'write' or row['access'] == 'read_write',
                'REGISTER_READ_ONLY', 'Read-only feedback cannot receive a write binding')
    return {'status': 'LOGICAL_REGISTER_CONTRACT_VALID', 'scope': 'READ_ONLY_PREFLIGHT_NO_NATIVE_IMPORT',
            'contract_sha256': contract_sha256, 'tags': resolved, 'tag_count': len(tags),
            'binding_count': len(bindings), 'address_space': 'AS228T_REGISTER',
            'range_source': SOURCE, 'missing_declared_word_order': missing_order,
            'native_write_ready': False, 'native_qualified': False, 'native_file_written': False,
            'vendor_compile': 'NOT_RUN', 'widget_scaling': 'DECLARED_ONLY_NOT_APPLIED',
            'remaining_native_gates': ['EXACT_DRIVER_SERIALIZATION', 'DRIVER_WORD_ORDER',
                                       'WIDGET_TYPE_AND_SCALE', 'NATIVE_BINDINGS_READBACK']}
