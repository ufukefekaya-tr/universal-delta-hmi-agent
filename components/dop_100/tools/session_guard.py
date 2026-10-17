# SPDX-License-Identifier: Apache-2.0
"""Original repository-local scope guard. It cannot grant authority."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.agent-state/EXTRACT-20261017'
CONTROL = ('AGENTS.md', 'SYSTEM_PROMPT.md', 'INDEX.md')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def epoch():
    stream = bytearray()
    for name in CONTROL:
        raw = (ROOT / name).read_bytes()
        if git('show', 'HEAD:' + name) != raw:
            raise ValueError('Uncommitted control plane: ' + name)
        stream.extend(name.encode() + b'\0' + raw + b'\0')
    return digest(stream)


def load(name):
    return json.loads((STATE / name).read_text(encoding='utf-8'))


def status():
    return digest(git('status', '--porcelain=v1', '-z', '--untracked-files=all'))


def check(action='resume', paths=()):
    envelope = load('TASK_ENVELOPE.json')
    cp = load('SESSION_CHECKPOINT.json')
    if epoch() != envelope['policy_epoch'] or cp['policy_epoch'] != epoch():
        raise ValueError('Policy epoch mismatch')
    if cp['envelope_sha256'] != digest((STATE / 'TASK_ENVELOPE.json').read_bytes()):
        raise ValueError('Envelope mismatch')
    if git('rev-parse', 'HEAD').decode().strip() != cp['head']:
        raise ValueError('HEAD mismatch; checkpoint must be reconciled')
    if status() != cp['status_sha256']:
        raise ValueError('Worktree membership/status changed since checkpoint')
    for name in paths:
        path = Path(name)
        full = (ROOT / path).resolve()
        if path.is_absolute() or not full.is_relative_to(ROOT):
            raise ValueError('Path escapes repository')
        rel = full.relative_to(ROOT).as_posix()
        if rel in CONTROL or rel.startswith('.git/'):
            raise ValueError('Protected control plane or Git data')
        if not any(rel == p.rstrip('/') or p.endswith('/') and rel.startswith(p)
                   for p in envelope['allowed_write_paths']):
            raise ValueError('Path outside task scope: ' + rel)
    if action == 'commit':
        staged = git('diff', '--cached', '--name-only', '-z').split(b'\0')
        names = [n.decode() for n in staged if n]
        if not names:
            raise ValueError('Empty staged mutation')
        check('edit', names)
    return envelope


def checkpoint(gate, next_step):
    envelope = load('TASK_ENVELOPE.json')
    old = load('SESSION_CHECKPOINT.json')
    if epoch() != envelope['policy_epoch']:
        raise ValueError('Policy changed')
    old.update(sequence=old['sequence'] + 1, head=git('rev-parse', 'HEAD').decode().strip(),
               status_sha256=status(), completed_gate=gate, next_step=next_step)
    (STATE / 'SESSION_CHECKPOINT.json').write_text(json.dumps(old, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['resume', 'action', 'checkpoint'])
    parser.add_argument('--kind', default='edit', choices=['edit', 'commit'])
    parser.add_argument('--path', action='append', default=[])
    parser.add_argument('--gate', default='')
    parser.add_argument('--next', default='')
    args = parser.parse_args()
    if args.mode == 'checkpoint':
        checkpoint(args.gate, args.next)
    else:
        check(args.kind if args.mode == 'action' else 'resume', args.path)
    print('SESSION_GUARD_OK')
