"""Meaningful refusal cases for phased acceptance, not wording checks."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('goal_validation', ROOT / 'tools/check_goals.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GoalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads((ROOT / 'goals/hmi-skill-transition.json').read_text('utf8'))
        # Definitions are maintained while real acceptance advances independently.
        for goal in self.doc['goals']:
            goal.update(state='IN_PROGRESS' if goal['id'] == 'G0' else 'PENDING', evidence=[], accepted_subjects=[], open_findings=[], reopen_reason=None,
                        next_step=goal['workflow'][0]['id'])
            for step in goal['workflow']:
                step['completed'] = False

    def test_current_definition_has_ordered_acceptance_gates(self):
        self.assertEqual(module.validate(self.doc)['status'], 'PASS')

    def test_cycle_and_unknown_dependency_refused(self):
        for dependency in ('G5', 'ABSENT'):
            altered = copy.deepcopy(self.doc)
            altered['goals'][0]['dependencies'] = [dependency]
            with self.assertRaises(ValueError):
                module.validate(altered)

    def test_no_pass_from_file_production_or_missing_review(self):
        altered = copy.deepcopy(self.doc)
        altered['goals'][0]['state'] = 'PASS'
        with self.assertRaises(ValueError):
            module.validate(altered)

    def test_skill_cannot_start_before_mcp_acceptance(self):
        altered = copy.deepcopy(self.doc)
        altered['goals'][3]['state'] = 'IN_PROGRESS'
        with self.assertRaisesRegex(ValueError, 'prerequisite|requires accepted MCP'):
            module.validate(altered)

    def test_no_active_work_before_any_prerequisite_passes(self):
        for state in ('READY', 'IN_PROGRESS', 'PASS'):
            altered = copy.deepcopy(self.doc)
            altered['goals'][1]['state'] = state
            with self.assertRaisesRegex(ValueError, 'prerequisite'):
                module.validate(altered)

    def test_exact_evidence_and_open_findings_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / 'reports/hmi_skill/g0.json'
            report.parent.mkdir(parents=True)
            altered = copy.deepcopy(self.doc)
            goal = altered['goals'][0]
            subject = root / 'source.py'
            subject.write_bytes(b'neutral source')
            subjects = [{'path': 'source.py', 'sha256': hashlib.sha256(subject.read_bytes()).hexdigest()}]
            goal['accepted_subjects'] = subjects
            report.write_text(json.dumps({'schema': 'delta.hmi.goal-evidence.v1', 'task': altered['task'], 'goal_id': 'G0', 'status': 'PASS', 'definition_sha256': module.definition_hash(goal), 'subjects': subjects, 'checks': {'inventory': 'PASS'}}), encoding='utf8')
            goal.update(state='PASS', next_step=None, evidence=[{'path': 'reports/hmi_skill/g0.json', 'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}])
            for step in goal['workflow']:
                step['completed'] = True
            module.validate(altered, root)
            goal['open_findings'] = [{'severity': 'important', 'status': 'OPEN'}]
            with self.assertRaisesRegex(ValueError, 'finding'):
                module.validate(altered, root)
            goal['open_findings'] = []
            report.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'drift'):
                module.validate(altered, root)

    def test_failed_or_other_goal_receipt_cannot_be_rehashed_into_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / 'reports/hmi_skill/g0.json'
            report.parent.mkdir(parents=True)
            subject = root / 'source.py'
            subject.write_bytes(b'neutral source')
            subjects = [{'path': 'source.py', 'sha256': hashlib.sha256(subject.read_bytes()).hexdigest()}]
            for change in ({'status': 'FAIL'}, {'goal_id': 'G1'}, {'checks': {}}, {'checks': {'critical': 'FAIL'}}, {'task': 'OTHER'}, {'definition_sha256': '0' * 64}, {'subjects': []}):
                altered = copy.deepcopy(self.doc)
                goal = altered['goals'][0]
                goal['accepted_subjects'] = subjects
                receipt = {'schema': 'delta.hmi.goal-evidence.v1', 'task': altered['task'], 'goal_id': 'G0', 'status': 'PASS', 'definition_sha256': module.definition_hash(goal), 'subjects': subjects, 'checks': {'inventory': 'PASS'}}
                receipt.update(change)
                report.write_text(json.dumps(receipt), encoding='utf8')
                goal.update(state='PASS', next_step=None, evidence=[{'path': 'reports/hmi_skill/g0.json', 'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}])
                for step in goal['workflow']:
                    step['completed'] = True
                with self.assertRaises(ValueError):
                    module.validate(altered, root)

    def test_accepted_source_drift_invalidates_previous_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.py'
            source.write_bytes(b'current source')
            report = root / 'reports/hmi_skill/g0.json'
            report.parent.mkdir(parents=True)
            altered = copy.deepcopy(self.doc)
            goal = altered['goals'][0]
            subjects = [{'path': 'source.py', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]
            goal.update(state='PASS', next_step=None, accepted_subjects=subjects)
            for step in goal['workflow']:
                step['completed'] = True
            report.write_text(json.dumps({'schema': 'delta.hmi.goal-evidence.v1', 'task': altered['task'], 'goal_id': 'G0', 'status': 'PASS', 'definition_sha256': module.definition_hash(goal), 'subjects': subjects, 'checks': {'inventory': 'PASS'}}), encoding='utf8')
            goal['evidence'] = [{'path': 'reports/hmi_skill/g0.json', 'sha256': hashlib.sha256(report.read_bytes()).hexdigest()}]
            module.validate(altered, root)
            source.write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError, 'subject drift'):
                module.validate(altered, root)

    def test_reopening_does_not_erase_the_reason(self):
        altered = copy.deepcopy(self.doc)
        altered['goals'][0].update(state='REOPENED', reopen_reason=None)
        with self.assertRaisesRegex(ValueError, 'reason'):
            module.validate(altered)
