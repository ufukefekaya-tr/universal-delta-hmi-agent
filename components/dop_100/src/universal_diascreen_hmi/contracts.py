# SPDX-License-Identifier: Apache-2.0
"""Read-only synthetic interface evidence. No PLC logic or live health inference."""
import csv
import io

from .errors import require, digest


def _bit(value):
    return bool(value) if type(value) in (int, bool) and value in (0, 1) else None


def evaluate_status(values, contract):
    require(isinstance(values, dict) and isinstance(contract, dict) and contract.get('schema_version') == 1,
            'INTERFACE_CONTRACT', 'Synthetic values and an explicit schema1 interface contract required')
    result = {'synthetic': True, 'live': False, 'runtime_acceptance': 'NOT_ESTABLISHED'}
    if 'fault' in contract:
        fields = contract['fault']
        require(isinstance(fields, dict) and set(fields) >= {'active', 'code', 'fresh'}, 'FAULT_CONTRACT', 'Active, raw code and fresh roles must be distinct')
        require(len({fields[k] for k in ('active', 'code', 'fresh')}) == 3, 'FAULT_CONTRACT', 'Fault roles cannot share one address')
        active, fresh = _bit(values.get(fields['active'])), _bit(values.get(fields['fresh']))
        code = values.get(fields['code'])
        valid_code = type(code) is int and 0 <= code <= 0xffffffff
        status = 'UNKNOWN' if fresh is not True or active is None or not valid_code else 'FAULT' if active else 'NO_ACTIVE_FAULT'
        result['fault'] = {'state': status, 'active': active, 'raw_code': code if valid_code else None,
                           'label': fields.get('catalog', {}).get(str(code), 'UNKNOWN_CODE') if valid_code else 'UNAVAILABLE',
                           'family': values.get(fields.get('family')), 'source': values.get(fields.get('source')),
                           'healthy_claim': False}
    if 'reference' in contract:
        fields = contract['reference']
        require(isinstance(fields, dict) and 'valid' in fields, 'REFERENCE_CONTRACT', 'Reference-valid latch role required')
        require(fields['valid'] != fields.get('physical_home'), 'REFERENCE_CONTRACT', 'Reference latch and physical home must have distinct addresses')
        result['reference'] = {'valid': _bit(values.get(fields['valid'])),
                               'physical_home': _bit(values.get(fields.get('physical_home'))),
                               'start_permit_inferred': False}
    if 'drive' in contract:
        fields = contract['drive']
        keys = ('request', 'ack', 'status', 'fresh', 'frequency')
        require(isinstance(fields, dict) and all(k in fields for k in keys) and len({fields[k] for k in keys}) == len(keys),
                'DRIVE_CONTRACT', 'Request, ACK, raw status, freshness and Hz need distinct roles')
        fresh = _bit(values.get(fields['fresh']))
        result['drive'] = {'request': _bit(values.get(fields['request'])), 'ack': values.get(fields['ack']),
                           'raw_status': values.get(fields['status']), 'fresh': fresh,
                           'frequency': values.get(fields['frequency']) if fresh is True else None,
                           'working_inferred': False}
    if 'transfer' in contract:
        fields = contract['transfer']
        keys = ('draft', 'readback', 'fresh', 'request', 'terminal_result')
        require(isinstance(fields, dict) and all(k in fields for k in keys) and len({fields[k] for k in keys}) == len(keys),
                'TRANSFER_CONTRACT', 'Draft, fresh readback, request and terminal result are separate source-qualified roles')
        result['transfer'] = {k: values.get(fields[k]) for k in keys}
        result['transfer']['applied_inferred'] = False
    return result


def validate_aesthetic_receipts(candidate_sha256, producer, receipts):
    require(isinstance(receipts, list) and len(receipts) == 2, 'REVIEW_ORDER', 'Two sequential independent reviews are required')
    first, second = receipts
    require(first.get('reviewer') and second.get('reviewer') and len({producer, first['reviewer'], second['reviewer']}) == 3,
            'REVIEW_INDEPENDENCE', 'Producer and both reviewer identities must differ')
    for row in receipts:
        require(row.get('candidate_sha256') == candidate_sha256 and row.get('review_sha256')
                and not row.get('open_important_findings', True), 'REVIEW_FINDINGS', 'Candidate pin and closed important findings required')
    require(second.get('challenges_review_sha256') == first['review_sha256'], 'REVIEW_ORDER', 'Second review must explicitly challenge the first exact report')
    require(first.get('scope') == second.get('scope') == 'visual-only', 'REVIEW_SCOPE', 'Visual approval does not authorize control or runtime changes')
    return {'status': 'CALLER_LINKED_SEQUENTIAL_REVIEWS', 'vendor_pixels': 'NOT_ESTABLISHED', 'runtime': 'NOT_ESTABLISHED'}


def design_ledger(project):
    from .operations import address_inventory
    idx = project.index
    addresses = address_inventory(project, False)
    rows = []
    for p in project.pages:
        for e in p.elements:
            identity = idx.number(e.section, 'nPartsID')
            rows.append({'page_id': p.page_id, 'element_id': identity,
                         'name': idx.text(e.section, 'wDescTextLen0', ''),
                         **{key: idx.number(e.section, key) for key in ('X', 'Y', 'Width', 'Height')},
                         'type': str(idx.number(e.section, 'Type')) + '.' + str(idx.number(e.section, 'SubType')),
                         'states': [{'value': idx.number(s, 'Value'), 'caption': idx.text(s, 'wTextLen0', '')} for s in e.states],
                         'addresses': [r for r in addresses if r.get('page_id') == p.page_id and r.get('element_id') == identity],
                         **{key: idx.scalar(e.section, key, '') for key in ('MemLen', 'MemFmt', 'MinValue', 'MaxValue', 'IntNum', 'DotNum', 'GainValue', 'OffsetValue')},
                         'scope': 'NATIVE_REFERENCE_ONLY; not a vendor CSV import or live polling counter'})
    out = io.StringIO(newline='')
    keys = ('page_id', 'element_id', 'name', 'X', 'Y', 'Width', 'Height', 'type', 'MemLen', 'MemFmt', 'MinValue', 'MaxValue', 'IntNum', 'DotNum', 'GainValue', 'OffsetValue')
    writer = csv.DictWriter(out, keys, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    return {'rows': rows, 'technical_csv': out.getvalue(), 'vendor_import': False,
            'source_sha256': project.file.source_sha256, 'source_payload_sha256': digest(project.file.payload)}
