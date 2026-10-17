"""Optional read-only probe of user-supplied native input; never copies it."""
import argparse
import hashlib
import json
from pathlib import Path

from universal_hmi.native import NativeAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--family', choices=['delta_diascreen', 'delta_dopsoft2'], required=True)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    adapter = NativeAdapter(raw, args.family)
    inventory = adapter.inspect()
    noop = adapter.apply([], {})
    unchanged = hashlib.sha256(args.source.read_bytes()).hexdigest() == before
    report = {'scope': 'READ_ONLY_FORMAT_PROBE', 'family': args.family, 'source_sha256': before,
              'model_id': inventory['model_id'], 'editor_version': inventory['editor_version'],
              'screens': len(inventory['screens']),
              'elements': sum(len(s['elements']) for s in inventory['screens']),
              'states': sum(len(e['states']) for s in inventory['screens'] for e in s['elements']),
              'decoded_document_equal': adapter.document.bytes() == adapter.envelope.body,
              'noop_byte_equal': noop == raw, 'source_unchanged': unchanged,
              'opaque_tail': inventory['opaque_tail'],
              'vendor_compile': 'NOT_RUN', 'native_feature_qualification': 'UNVERIFIED', 'redistributed': False}
    report['probe_pass'] = all(report[key] for key in ('decoded_document_equal', 'noop_byte_equal', 'source_unchanged'))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['probe_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
