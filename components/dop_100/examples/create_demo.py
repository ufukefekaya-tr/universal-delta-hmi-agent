# SPDX-License-Identifier: Apache-2.0
"""Create one neutral 400x240 source/profile example in a fresh destination.

This repository example uses its synthetic test fixture, never vendor assets.
The output is an offline framing exercise, not a compiled or usable panel app.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from tests.fixtures import native, profile
from universal_diascreen_hmi.errors import digest
from universal_diascreen_hmi.operations import canonical


def create(destination):
    destination = Path(destination).resolve()
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError('Destination must be a new directory inside an existing parent')
    source, selected = native(), profile()
    if selected['panel'] != {'width': 400, 'height': 240}:
        raise ValueError('This example is restricted to the neutral 400x240 fixture')
    receipt = {'schema_version': 1, 'scope': 'SYNTHETIC_FILE_EXAMPLE_ONLY',
               'source': 'source.dpa', 'source_sha256': digest(source),
               'profile': 'profile.json', 'profile_sha256': digest(canonical(selected)),
               'vendor_compile': 'NOT_RUN', 'runtime': 'NOT_RUN',
               'review': 'Inspect this synthetic source before planning; no proprietary source boundary is approved here'}
    destination.mkdir(exist_ok=False)
    files = {'source.dpa': source, 'profile.json': canonical(selected) + b'\n',
             'IDENTITY.json': (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode('utf8')}
    for name, data in files.items():
        with (destination / name).open('xb') as stream:
            stream.write(data)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', help='Explicit fresh directory; existing paths are refused')
    args = parser.parse_args(argv)
    try:
        result = create(args.destination)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
