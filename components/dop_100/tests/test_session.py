# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project
from universal_diascreen_hmi.operations import canonical
from universal_diascreen_hmi.session import Session
from tests.fixtures import native, profile, payload, wrap


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root / 'source.dpa'; self.source.write_bytes(native())
        self.s = Session(self.root, allow_write=True)
        self.open(self.s)

    def open(self, session, p=None):
        p = p or profile()
        return session.open_project('source.dpa', digest(native()), p, digest(canonical(p)))

    def proposal(self, s=None):
        s = s or self.s; s.inspect()
        return s.plan_changes([{'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': 1, 'text': 'AÇIK'}])

    def apply(self, s=None):
        s = s or self.s; p = self.proposal(s)
        s.apply_plan(p['plan_sha256'], p['plan_sha256']); return p

    def test_inspect_before_plan_and_pins(self):
        with self.assertRaises(AgentError): self.s.plan_changes([{'op': 'delete_element', 'page_id': 1, 'element_id': 10}])
        self.assertEqual(self.s.inspect()['element_count_indexed'], 4)
        with self.assertRaises(AgentError): self.s.open_project('source.dpa', '0' * 64, profile(), digest(canonical(profile())))
        with self.assertRaises(AgentError): self.s.open_project('source.dpa', digest(native()), profile(), '0' * 64)

    def test_actual_apply_save_reread_diff_rollback_and_source(self):
        plan = self.apply()
        self.assertEqual(self.source.read_bytes(), native())
        result = self.s.save_as('candidate.dpa', plan['candidate_sha256'])
        q = Project((self.root / result['path']).read_bytes())
        self.assertEqual(q.index.text(q.element(1, 10).states[1], 'wTextLen0'), 'AÇIK')
        self.assertEqual(self.s.validate()['preservation'], 'PASS')
        self.assertTrue(self.s.diff()['applied'][0]['changes'])
        self.s.rollback(); self.assertEqual(self.s.current, native())
        self.assertTrue((self.root / 'candidate.dpa').exists())
        self.assertEqual(self.source.read_bytes(), native())

    def test_r04_pending_open_does_not_discard(self):
        self.proposal(); (self.root / 'other.dpa').write_bytes(native())
        with self.assertRaises(AgentError) as ctx: self.s.open_project('other.dpa', digest(native()), profile(), digest(canonical(profile())))
        self.assertEqual(ctx.exception.code, 'PENDING_WORK')
        self.assertEqual(len(self.s.pending_changes()['plans']), 1)
        self.assertTrue(self.open(self.s)['reused'])
        self.s.rollback(); self.s.open_project('other.dpa', digest(native()), profile(), digest(canonical(profile())))

    def test_r09_replay_and_stale_other_plan(self):
        one = self.proposal(); two = self.s.plan_changes([{'op': 'delete_element', 'page_id': 1, 'element_id': 11}])
        self.s.apply_plan(one['plan_sha256'], one['plan_sha256'])
        with self.assertRaises(AgentError) as ctx: self.s.apply_plan(one['plan_sha256'], one['plan_sha256'])
        self.assertEqual(ctx.exception.code, 'ALREADY_APPLIED')
        with self.assertRaises(AgentError): self.s.apply_plan(two['plan_sha256'], two['plan_sha256'])

    def test_write_switch_and_explicit_exact_approval(self):
        readonly = Session(self.root); self.open(readonly); p = self.proposal(readonly)
        with self.assertRaises(AgentError): readonly.apply_plan(p['plan_sha256'], p['plan_sha256'])
        p = self.proposal()
        with self.assertRaises(AgentError): self.s.apply_plan(p['plan_sha256'], '0' * 64)
        self.assertEqual(self.s.current, native())

    def test_newonly_output_source_and_traversal(self):
        p = self.apply()
        for path in ('source.dpa', '../escape.dpa', 'missing/new.dpa'):
            with self.assertRaises(AgentError): self.s.save_as(path, p['candidate_sha256'])
        self.s.save_as('new.dpa', p['candidate_sha256'])
        with self.assertRaises(AgentError): self.s.save_as('new.dpa', p['candidate_sha256'])

    def test_live_source_drift_blocks_apply(self):
        p = self.proposal(); self.source.write_bytes(native() + b'changed')
        with self.assertRaises(AgentError) as ctx: self.s.apply_plan(p['plan_sha256'], p['plan_sha256'])
        self.assertEqual(ctx.exception.code, 'SOURCE_DRIFT')

    def test_profile_mismatch_and_profile_mutation(self):
        p = deepcopy(profile()); p['panel']['width'] = 401
        with self.assertRaises(AgentError): self.s.open_project('source.dpa', digest(native()), p, digest(canonical(p)))
        self.s.profile['station'] = 99
        with self.assertRaises(AgentError): self.s.inspect()

    def test_returned_plan_is_not_mutable_internal_evidence(self):
        p = self.proposal(); p['operations'][0]['text'] = 'Tampered caller copy'
        self.s.apply_plan(p['plan_sha256'], p['plan_sha256'])
        self.assertEqual(self.s.diff()['applied'][0]['operations'][0]['text'], 'AÇIK')
        self.s.current_profile['station'] = 99
        with self.assertRaises(AgentError): self.s.inspect()

    def test_stored_proposal_tampering_stops_application(self):
        p = self.proposal(); self.s.plans[p['plan_sha256']]['record']['operations'][0]['text'] = 'tamper'
        with self.assertRaises(AgentError) as ctx: self.s.apply_plan(p['plan_sha256'], p['plan_sha256'])
        self.assertEqual(ctx.exception.code, 'PLAN_DRIFT')

    def test_multiple_approved_plans_inverse(self):
        self.apply(); self.s.inspect()
        p = self.s.plan_changes([{'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': 'X', 'value': 15}])
        self.s.apply_plan(p['plan_sha256'], p['plan_sha256'])
        self.assertEqual(self.s.validate()['status'], 'OFFLINE_STRUCTURAL_PASS')
        self.assertEqual(len(self.s.diff()['applied']), 2)

    def test_private_read_root_explicit_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as private:
            p = Path(private) / 'donor.dpa'; p.write_bytes(native())
            with self.assertRaises(AgentError): self.s.register_donor('other', str(p), digest(native()))
            allowed = Session(self.root, read_roots=[private]); self.open(allowed)
            self.assertEqual(allowed.register_donor('seed', str(p), digest(native()))['sha256'], digest(native()))
            try: (self.root / 'link.dpa').symlink_to(p)
            except OSError: return  # Some Windows accounts lack symlink privileges.
            with self.assertRaises(AgentError): allowed.register_donor('linked', 'link.dpa', digest(native()))

    def test_r17_compiled_receipt_current_source_candidate(self):
        data = b'neutral compiled observation'; (self.root / 'obs.cin').write_bytes(data)
        receipt = {'artifact_sha256': digest(data), 'source_sha256': digest(native()), 'candidate_sha256': digest(native())}
        value = self.s.inspect_compiled('obs.cin', digest(data), digest(native()), digest(native()), receipt)
        self.assertFalse(value['full_cin_acceptance'])
        self.apply()
        with self.assertRaises(AgentError): self.s.inspect_compiled('obs.cin', digest(data), digest(native()), digest(native()), receipt)

    def test_catalogs_never_claim_runtime_or_alarm_history(self):
        self.assertEqual(self.s.inspect('alarms')['support'], 'DISCOVERED_UNQUALIFIED')
        self.assertEqual(self.s.capabilities()['runtime_heartbeat'], 'ROLLED_BACK_NOT_DEFAULT')
        self.assertTrue(any(r['field'] == 'TriggerVar' for r in self.s.inspect('addresses')['rows']))
        self.assertTrue(self.s.inspect('symbols')['symbols'])
        self.assertEqual(self.s.validate()['runtime'], 'NOT_RUN')


if __name__ == '__main__': unittest.main()
