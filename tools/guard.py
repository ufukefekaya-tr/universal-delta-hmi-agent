"""Small local mutation guard; no environment or network side effects."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ('AGENTS.md', 'SYSTEM_PROMPT.md', 'INDEX.md')

def epoch():
    value = hashlib.sha256()
    for name in CONTROL:
        raw = (ROOT / name).read_bytes()
        if subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT) != raw:
            raise ValueError('Uncommitted control policy: ' + name)
        value.update(name.encode() + b'\0' + raw + b'\0')
    return value.hexdigest()

def check():
    state = ROOT / '.agent-state/current'
    env = json.loads((state / 'TASK_ENVELOPE.json').read_text('utf8'))
    cp = json.loads((state / 'SESSION_CHECKPOINT.json').read_text('utf8'))
    if epoch() != env['policy_epoch'] or cp['policy_epoch'] != env['policy_epoch']:
        raise ValueError('Policy epoch changed')
    if cp['envelope_sha256'] != hashlib.sha256((state / 'TASK_ENVELOPE.json').read_bytes()).hexdigest():
        raise ValueError('Envelope changed')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != cp['head']:
        raise ValueError('Checkpoint HEAD changed')
    dirty = subprocess.check_output(['git','status','--porcelain=v1','-z','--untracked-files=all'],cwd=ROOT).decode().split('\0')
    for entry in filter(None, dirty):
        if entry[:2].strip().startswith(('R','C')):
            raise ValueError('Rename/copy requires explicit audit')
        path = entry[3:]
        if not any(path == p or (p.endswith('/') and path.startswith(p)) for p in env['allowed_write']):
            raise ValueError('Outside scope: '+path)
    return {'status':'PASS','policy_epoch':env['policy_epoch'],'head':head}

if __name__ == '__main__':
    print(json.dumps(check()))
