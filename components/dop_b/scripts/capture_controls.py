"""Capture immutable native facts for control/driver qualification.

No native output, behavior enum, primitive conversion, PLC connection or
qualification flag is generated. Use the evidence to identify the missing
vendor property/reference tests; descriptions are never behavior authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter
from universal_hmi.service import FileService, byte_hash

ROOT = Path(__file__).resolve().parents[1]


def capture(workspace, source_path, family, output_path):
    service = FileService(workspace, ROOT / 'profiles')
    if service._path(output_path).suffix.lower() != '.json':
        raise HmiError('CAPTURE_FORMAT', 'Capture output must be a new JSON evidence file')
    source = service._path(source_path, exists=True)
    suffix = '.dps' if family == 'delta_dopsoft2' else '.dpa'
    if source.suffix.lower() != suffix:
        raise HmiError('OUTPUT_FORMAT', 'Source suffix must match the content adapter')
    raw = source.read_bytes()
    facts = NativeAdapter(raw, family).calibration_inventory()
    data = (json.dumps(facts, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    def source_unchanged():
        with source.open('rb') as file:
            return file.read(len(raw) + 1) == raw
    if not source_unchanged():
        raise HmiError('SOURCE_CHANGED', 'Source changed during calibration capture')
    def verify(candidate):
        if json.loads(candidate.decode('utf-8')) != facts:
            raise HmiError('SAVE_INTEGRITY', 'Saved capture differs from immutable source observations')
        if not source_unchanged():
            raise HmiError('SOURCE_CHANGED', 'Source changed before capture could be saved')
    receipt = service._write_new(output_path, data, verify)
    try:
        if not source_unchanged():
            raise HmiError('SOURCE_CHANGED', 'Source changed after capture was linked')
    except (OSError, HmiError) as exc:
        # No path-based unlink can atomically prove continued ownership under
        # concurrent replacement. Retain this UNVERIFIED observation record;
        # fail the capture and require a fresh revision, never delete a writer's
        # replacement even when its bytes happen to equal our original JSON.
        raise HmiError('SOURCE_CHANGED', 'Source changed or disappeared after capture was linked; output is retained and not accepted',
            original_capture_receipt=receipt, capture_acceptance='FAIL', output_retained=True) from exc
    return {'scope': facts['scope'], 'source_sha256': byte_hash(raw), 'capture': receipt,
            'observed_owners': len(facts['owners']), 'controller_blocks': len(facts['driver_blocks']),
            'qualification': 'UNVERIFIED', 'native_output': 'NOT_CREATED', 'emission_authority': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--source', required=True, help='Workspace-relative existing native source')
    parser.add_argument('--family', required=True, choices=['delta_dopsoft2', 'delta_diascreen'])
    parser.add_argument('--output', required=True, help='New workspace-relative JSON evidence path')
    args = parser.parse_args()
    try:
        result = capture(args.workspace, args.source, args.family, args.output)
    except (HmiError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'FAIL', **(exc.as_dict() if isinstance(exc, HmiError) else {'code': 'IO_OR_JSON', 'message': str(exc)})}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
