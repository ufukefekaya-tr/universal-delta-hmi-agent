# SPDX-License-Identifier: Apache-2.0
"""Nine typed symbolic primitives; AS registers remain a separate capability."""
from .common import canonical, hash_value, require, sha
from universal_diascreen_hmi.operations import decimal
from universal_diascreen_hmi.symbols import parse_symbols

TYPES = {'BOOL': 1, 'INT': 16, 'UINT': 16, 'WORD': 16, 'DINT': 32, 'UDINT': 32, 'DWORD': 32, 'REAL': 32, 'LREAL': 64}
FIELDS = {'path', 'iec_type', 'bits', 'access', 'gain', 'offset', 'unit', 'word_order'}


def validate_catalog(xml, contract, contract_sha256):
    hash_value(contract_sha256)
    require(isinstance(contract, dict) and sha(canonical(contract)) == contract_sha256, 'CONTRACT_HASH', 'Typed contract SHA differs')
    require(set(contract) == {'schema_version', 'address_space', 'symbols'}
            and type(contract['schema_version']) is int and contract['schema_version'] == 1
            and contract['address_space'] == 'DIA_TAG_SYMBOLCONFIGURATION', 'ADDRESS_SPACE', 'Explicit symbolic catalog address space required')
    rows = contract['symbols']
    require(isinstance(rows, list) and 0 < len(rows) <= 4096 and isinstance(xml, str), 'SYMBOL_CONTRACT', 'Explicit bounded XML/contract required')
    catalog = parse_symbols(xml.encode('utf-8'))
    seen = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == FIELDS, 'SYMBOL_CONTRACT', 'Typed row fields differ')
        symbol = catalog.resolve(row['path'])
        require(symbol['path'] not in seen, 'SYMBOL_DUPLICATE', 'Duplicate canonical symbol')
        seen.add(symbol['path'])
        require(isinstance(row['iec_type'], str) and row['iec_type'] in TYPES
                and type(row['bits']) is int and row['bits'] == TYPES[row['iec_type']] == symbol['bits']
                and symbol['iec_type'].upper() == row['iec_type'], 'SYMBOL_WIDTH_TYPE', 'Actual XML type/width differs')
        require(row['access'] in ('read', 'read_write') and symbol['readable']
                and (row['access'] == 'read_write') == symbol['writable'], 'SYMBOL_ACCESS', 'Actual XML permission differs')
        require(decimal(row['gain'], 'gain') != 0, 'SYMBOL_SCALE', 'Zero gain is invalid')
        decimal(row['offset'], 'offset')
        require(isinstance(row['unit'], str) and len(row['unit']) <= 32
                and row['word_order'] == 'NOT_APPLICABLE_SYMBOLIC', 'SYMBOL_LAYOUT', 'No register word order can be inferred from XML')
    return catalog
