# SPDX-License-Identifier: Apache-2.0
"""Small shared serialization, identity and filesystem boundaries."""
import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone


class Error(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise Error(code, message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hash_value(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value), 'HASH', 'Complete lowercase SHA-256 required')
    return value


def engine_identity():
    root=Path(__file__).resolve().parent.parent
    files={p.relative_to(root).as_posix():sha(p.read_bytes()) for p in sorted(root.rglob('*.py'))}
    reference=os.environ.get('DIA_HMI_REFERENCE_ROOT')
    if reference:files['trusted-host-registry']=sha(no_links(Path(reference)/'registry.json').read_bytes())
    return sha(canonical(files))


def now():
    return datetime.now(timezone.utc).isoformat()


def no_links(path):
    path = Path(path).absolute()
    require(all(':' not in part for part in path.parts if part != path.anchor),
            'PATH_STREAM', 'NTFS alternate data streams are excluded')
    for part in (path, *path.parents):
        require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()),
                'PATH_LINK', 'Symlink/junction input is excluded')
    return path


def write_new(path, data):
    no_links(path)
    with Path(path).open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def atomic_json(path, value):
    path = no_links(path)
    temporary = path.with_name(path.name + '.' + os.urandom(8).hex() + '.tmp')
    try:
        write_new(temporary, canonical(value) + b'\n')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
