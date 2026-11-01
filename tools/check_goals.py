"""Validate phased goal records; scheduling stays with the existing checkpoint owner."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATES = {'PENDING', 'READY', 'IN_PROGRESS', 'BLOCKED', 'PASS', 'FAIL', 'REOPENED'}


def definition_hash(goal):
    keys = ('id', 'purpose', 'owner', 'dependencies', 'inputs', 'allowed_scope', 'protected_scope', 'acceptance', 'rollback')
    contract = {k: goal[k] for k in keys}
    contract['workflow'] = [{k: step[k] for k in ('id', 'action')} for step in goal['workflow']]
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def checked_path(root, name, prefix=None):
    path = Path(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or path.as_posix() != name or (prefix and not name.startswith(prefix)):
        raise ValueError('Unsafe evidence or subject path')
    target = root / path
    if not target.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (target, *target.parents)) or target.stat().st_nlink != 1:
        raise ValueError('Linked or escaping evidence refused')
    return target


def validate(document, root=ROOT):
    if document.get('schema') != 'delta.hmi.goal-workflow.v1':
        raise ValueError('Unknown goal workflow')
    goals = document.get('goals')
    if not isinstance(goals, list) or not goals:
        raise ValueError('Nonempty goals required')
    by_id = {g['id']: g for g in goals}
    if len(by_id) != len(goals) or document.get('current_goal') not in by_id:
        raise ValueError('Duplicate or missing goal identity')
    visiting, visited = set(), set()

    def visit(identity):
        if identity in visiting:
            raise ValueError('Cyclic goal dependency')
        if identity in visited:
            return
        if identity not in by_id:
            raise ValueError('Unknown dependency')
        visiting.add(identity)
        for dep in by_id[identity]['dependencies']:
            visit(dep)
        visiting.remove(identity)
        visited.add(identity)

    for goal in goals:
        visit(goal['id'])
        for key in ('purpose', 'owner', 'inputs', 'allowed_scope', 'protected_scope', 'acceptance', 'rollback', 'history'):
            if not goal.get(key):
                raise ValueError('Missing goal contract: ' + key)
        if goal['state'] not in STATES:
            raise ValueError('Unknown goal state')
        steps = goal.get('workflow', [])
        step_ids = [s['id'] for s in steps]
        if not steps or len(step_ids) != len(set(step_ids)) or any(not s.get('action') or type(s.get('completed')) is not bool for s in steps):
            raise ValueError('Invalid inner workflow')
        if goal['state'] == 'REOPENED' and not goal.get('reopen_reason'):
            raise ValueError('Reopening must retain its reason')
        if goal['state'] in ('READY', 'IN_PROGRESS', 'PASS') and any(by_id[d]['state'] != 'PASS' for d in goal['dependencies']):
            raise ValueError('Unaccepted prerequisite')
        if goal['state'] == 'PASS':
            if not all(s['completed'] for s in steps) or goal.get('next_step') is not None:
                raise ValueError('Incomplete workflow cannot pass')
            if any(f.get('severity') in ('important', 'critical') and f.get('status') != 'CLOSED' for f in goal.get('open_findings', [])):
                raise ValueError('Important finding remains open')
            if not goal.get('evidence'):
                raise ValueError('PASS needs exact evidence')
            subjects = goal.get('accepted_subjects')
            if not isinstance(subjects, list) or not subjects:
                raise ValueError('PASS needs exact accepted subjects')
            for subject in subjects:
                target = checked_path(root, subject['path'])
                if hashlib.sha256(target.read_bytes()).hexdigest() != subject.get('sha256'):
                    raise ValueError('Accepted subject drift; reopen affected goals')
            for record in goal['evidence']:
                name = record.get('path', '')
                target = checked_path(root, name, 'reports/hmi_skill/')
                if hashlib.sha256(target.read_bytes()).hexdigest() != record.get('sha256'):
                    raise ValueError('Goal evidence drift')
                receipt = json.loads(target.read_text('utf8'))
                if receipt.get('schema') != 'delta.hmi.goal-evidence.v1' or receipt.get('goal_id') != goal['id'] or receipt.get('status') != 'PASS':
                    raise ValueError('Wrong or failed goal evidence')
                if receipt.get('task') != document['task'] or receipt.get('definition_sha256') != definition_hash(goal) or receipt.get('subjects') != subjects:
                    raise ValueError('Goal task/definition/subject association differs')
                checks = receipt.get('checks')
                if not isinstance(checks, dict) or not checks or any(v != 'PASS' for v in checks.values()):
                    raise ValueError('Evidence has incomplete or failed checks')
    if by_id.get('G2', {}).get('state') != 'PASS':
        for identity in ('G3', 'G4', 'G5'):
            if identity in by_id and by_id[identity]['state'] not in ('PENDING', 'BLOCKED', 'REOPENED'):
                raise ValueError('Skill work requires accepted MCP G2')
    return {'status': 'PASS', 'goals': {g['id']: g['state'] for g in goals}, 'current_goal': document['current_goal']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--path', type=Path, default=ROOT / 'goals/hmi-skill-transition.json')
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(args.path.read_text('utf8')))))
